#!/usr/bin/env python3
"""Sitzungsgeheimnis für den lokalen Omaclusive-Server.

Das Geheimnis entsteht beim Start und liegt in einer Datei mit Modus 0600.
Andere Benutzerkonten auf demselben Rechner können sie nicht lesen.
Der Starter liest sie und gibt sie nur dem Browser dieses Benutzers.
"""
import hmac
import os
import re
import stat
import urllib.parse

_NAME = re.compile(r"[A-Za-z0-9_-]{20,128}")
_SEITE = re.compile(r"[A-Za-z0-9_./?=&%-]*")


def gleich(a, b):
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    ab, bb = a.encode("utf-8"), b.encode("utf-8")
    if len(ab) != len(bb):
        return False
    return hmac.compare_digest(ab, bb)


def runtime_privat(pfad):
    """Nur ein Verzeichnis, das diesem Benutzer gehört und für andere geschlossen ist."""
    if not pfad or not os.path.isdir(pfad) or os.path.islink(pfad):
        return False
    try:
        st = os.stat(pfad)
    except OSError:
        return False
    if st.st_uid != os.getuid():
        return False
    return stat.S_IMODE(st.st_mode) & 0o077 == 0


def ordner(home=None):
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime_privat(runtime):
        return os.path.join(runtime, "omaclusive")
    basis = home or os.path.expanduser("~")
    return os.path.join(basis, ".local", "share", "omaclusive", "run")


def datei(port, home=None):
    return os.path.join(ordner(home), "%d.session" % int(port))


def _schreiben(pfad, inhalt):
    """Schreibt eine neue Datei mit Modus 0600 und folgt keinem Verweis."""
    ziel = os.path.dirname(pfad)
    if os.path.lexists(ziel) and os.path.islink(ziel):
        raise OSError("Sitzungsordner ist ein Verweis")
    os.makedirs(ziel, mode=0o700, exist_ok=True)
    if os.path.islink(ziel) or not os.path.isdir(ziel):
        raise OSError("Sitzungsordner ist kein Verzeichnis")
    os.chmod(ziel, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(pfad, flags, 0o600)
    try:
        os.write(fd, inhalt.encode("ascii"))
    finally:
        os.close(fd)
    os.chmod(pfad, 0o600)
    st = os.lstat(pfad)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
        try:
            os.remove(pfad)
        except OSError:
            pass
        raise OSError("Sitzungsdatei wäre für andere lesbar")


def anlegen(port, home=None):
    import secrets
    token = secrets.token_urlsafe(32)
    _schreiben(datei(port, home), token + "\n")
    return token


def lesen(port, home=None):
    pfad = datei(port, home)
    st = os.lstat(pfad)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise OSError("Sitzungsdatei ungültig")
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
        raise OSError("Sitzungsdatei für andere lesbar")
    with open(pfad, "r", encoding="ascii") as handle:
        token = handle.read().strip()
    if not _NAME.fullmatch(token):
        raise OSError("Sitzungsdatei ungültig")
    return token


def boot_schreiben(port, seite, home=None):
    """Kleine lokale Seite, die das Geheimnis nur im Fragment an den Browser gibt.

    Das Fragment geht nicht an den Server und steht nicht in der Befehlszeile.
    Die Datei selbst hat Modus 0600.
    """
    token = lesen(port, home)
    seite = seite or ""
    if not isinstance(seite, str) or not _SEITE.fullmatch(seite):
        raise OSError("Seite ungültig")
    pfad = os.path.join(ordner(home), "%d.boot.html" % int(port))
    html = (
        "<!doctype html><meta charset=\"utf-8\"><title>Omaclusive</title><script>"
        "location.replace(\"http://127.0.0.1:%d/%s#%s\");</script>\n"
        % (int(port), seite, token)
    )
    _schreiben(pfad, html)
    return pfad


def boot_url(port, seite, home=None):
    return "file://" + urllib.parse.quote(boot_schreiben(port, seite, home))


def _host_ok(headers, port):
    erlaubt = {"127.0.0.1:%d" % port, "localhost:%d" % port}
    host = str(headers.get("Host") or "").strip().lower()
    return host in erlaubt


def _origin_ok(headers, port):
    origin = str(headers.get("Origin") or "").strip()
    if origin:
        erlaubt = {"http://127.0.0.1:%d" % port, "http://localhost:%d" % port}
        return origin.lower() in erlaubt
    referer = str(headers.get("Referer") or "").strip()
    if referer:
        teile = urllib.parse.urlparse(referer)
        name = (teile.hostname or "").lower()
        if teile.scheme != "http" or name not in ("127.0.0.1", "localhost") or teile.port != port:
            return False
    site = str(headers.get("Sec-Fetch-Site") or "").strip().lower()
    if site in ("cross-site", "same-site"):
        return False
    return True


def herkunft_ok(headers, port):
    """Host und, falls der Browser sie schickt, Origin/Referer müssen diese Schleife sein."""
    return _host_ok(headers, port) and _origin_ok(headers, port)


def token_aus(headers):
    kopf = str(headers.get("X-Omaclusive-Token") or "").strip()
    if kopf:
        return kopf
    keks = str(headers.get("Cookie") or "")
    for teil in keks.split(";"):
        teil = teil.strip()
        if teil.startswith("omaclusive_session="):
            return urllib.parse.unquote(teil.split("=", 1)[1].strip())
    return ""


def zugang_ok(headers, port, geheimnis):
    if not geheimnis or not herkunft_ok(headers, port):
        return False
    gegeben = token_aus(headers)
    return bool(gegeben) and gleich(gegeben, geheimnis)
