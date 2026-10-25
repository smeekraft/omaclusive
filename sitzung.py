#!/usr/bin/env python3
"""Sitzungsgeheimnis für den lokalen Omaclusive-Server.

Das Geheimnis entsteht beim Start und liegt in einer Datei mit Modus 0600
in einem Ordner mit Modus 0700. Andere Benutzerkonten auf demselben Rechner
können sie nicht lesen. Der Ordner ist das private Laufzeitverzeichnis,
wenn das privat ist und der Webserver es nicht ausliefert. Sonst ein
privater Ordner außerhalb der Web-Wurzel (normalerweise
~/.local/state/omaclusive/run/, nie ~/.local/share/omaclusive/run/).
Der Starter liest die Datei und gibt das Geheimnis nur dem Browser
dieses Benutzers.
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


def programm_ordner():
    """Ordner von server.py. Den liefert der lokale Server als statische Dateien aus."""
    return os.path.realpath(os.path.dirname(os.path.abspath(__file__)))


def liegt_in(pfad, wurzel):
    """True, wenn pfad die Wurzel selbst ist oder darunter liegt."""
    if not pfad or not wurzel:
        return False
    try:
        basis = os.path.realpath(wurzel)
        ziel = os.path.realpath(pfad)
    except (OSError, ValueError):
        return False
    if not basis or not ziel:
        return False
    try:
        return os.path.commonpath([basis, ziel]) == basis
    except ValueError:
        return False


def _web_wurzeln(home):
    # Installierte Kopie und der Ordner, aus dem dieser Prozess läuft.
    return (
        programm_ordner(),
        os.path.join(home, ".local", "share", "omaclusive"),
    )


def _ungeeignet(pfad, home):
    """True, wenn der Ordner von der Web-Wurzel ausgeliefert würde oder sie enthält."""
    for wurzel in _web_wurzeln(home):
        if liegt_in(pfad, wurzel) or liegt_in(wurzel, pfad):
            return True
    return False


def ordner(home=None):
    """Privater Ordner für das Sitzungsgeheimnis, nie unter der Web-Wurzel."""
    home = home or os.path.expanduser("~")
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime_privat(runtime):
        ziel = os.path.join(runtime, "omaclusive")
        if not _ungeeignet(ziel, home):
            return ziel
    for ziel in (
        os.path.join(home, ".local", "state", "omaclusive", "run"),
        os.path.join(home, ".omaclusive-private", "run"),
        os.path.join("/tmp", "omaclusive-%d" % os.getuid(), "run"),
    ):
        if not _ungeeignet(ziel, home):
            return ziel
    raise OSError("kein privater Sitzungsordner außerhalb der Web-Wurzel")


def datei(port, home=None):
    return os.path.join(ordner(home), "%d.session" % int(port))


def _ordner_sicher(ziel):
    """Legt den Ordner mit Modus 0700 an und folgt keinem Verweis."""
    if os.path.lexists(ziel) and os.path.islink(ziel):
        raise OSError("Sitzungsordner ist ein Verweis")
    os.makedirs(ziel, mode=0o700, exist_ok=True)
    if os.path.islink(ziel) or not os.path.isdir(ziel):
        raise OSError("Sitzungsordner ist kein Verzeichnis")
    os.chmod(ziel, 0o700)
    st = os.lstat(ziel)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise OSError("Sitzungsordner ist kein Verzeichnis")
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
        raise OSError("Sitzungsordner wäre für andere zugänglich")


def _schreiben(pfad, inhalt, home=None):
    """Schreibt eine neue Datei mit Modus 0600 und folgt keinem Verweis."""
    home = home or os.path.expanduser("~")
    ziel = os.path.dirname(pfad)
    if _ungeeignet(ziel, home):
        raise OSError("Sitzungsordner liegt in der Web-Wurzel")
    _ordner_sicher(ziel)
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
    _schreiben(datei(port, home), token + "\n", home)
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
    _schreiben(pfad, html, home)
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
