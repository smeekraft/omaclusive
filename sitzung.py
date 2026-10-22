#!/usr/bin/env python3
"""Sitzungsgeheimnis für den lokalen Omaclusive-Server.

Liegt außerhalb des Web-Ordners, nur für dieses Benutzerkonto lesbar:
  $XDG_RUNTIME_DIR/omaclusive/session-<port>   (Verzeichnis 0700, Datei 0600)
  sonst ~/.local/share/omaclusive/run/session-<port>

Der Start (start-talker.sh) liest die Datei und öffnet eine kleine lokale
Seite, die das Geheimnis einmal an den eigenen Browser übergibt. Andere
Konten auf demselben Rechner können die Datei nicht lesen. Es gibt keine
Anmeldung in der Oberfläche.
"""
import hmac, json, os, re, secrets, stat, sys, urllib.parse

_NAME = re.compile(r"[A-Za-z0-9_-]{20,200}")


def verzeichnis():
    """Ordner nur für dieses Konto. Legt ihn bei Bedarf an und zieht die Rechte an."""
    base = os.environ.get("XDG_RUNTIME_DIR") or ""
    ziel = None
    if base:
        try:
            st = os.stat(base)
        except OSError:
            st = None
        if st and stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) and st.st_uid == os.getuid():
            ziel = os.path.join(base, "omaclusive")
    if not ziel:
        ziel = os.path.join(os.path.expanduser("~"), ".local", "share", "omaclusive", "run")
    os.makedirs(ziel, mode=0o700, exist_ok=True)
    if os.path.islink(ziel):
        raise OSError("Sitzungsverzeichnis darf kein Verweis sein")
    os.chmod(ziel, 0o700)
    mode = os.stat(ziel).st_mode
    if mode & 0o077:
        raise OSError("Sitzungsverzeichnis ist für andere Konten zugänglich")
    return ziel


def datei(port):
    return os.path.join(verzeichnis(), "session-%d" % _port(port))


def _port(port):
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError("port")
    return port


def _oeffnen(pfad, flags):
    if os.path.islink(pfad):
        raise OSError("Sitzungsdatei darf kein Verweis sein")
    return os.open(pfad, flags | getattr(os, "O_NOFOLLOW", 0), 0o600)


def anlegen(port):
    """Neues Geheimnis schreiben. Gibt den Text zurück (ohne Zeilenumbruch)."""
    pfad = datei(port)
    if os.path.lexists(pfad) and os.path.islink(pfad):
        os.unlink(pfad)
    geheim = secrets.token_urlsafe(32)
    fd = _oeffnen(pfad, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, (geheim + "\n").encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(pfad, 0o600)
    if os.stat(pfad).st_mode & 0o077:
        raise OSError("Sitzungsdatei ist für andere Konten lesbar")
    return geheim


def lesen(port):
    """Geheimnis lesen. Wirft, wenn die Datei fehlt oder für andere lesbar ist."""
    pfad = datei(port)
    fd = _oeffnen(pfad, os.O_RDONLY)
    with os.fdopen(fd, "r", encoding="ascii") as handle:
        st = os.fstat(handle.fileno())
        if st.st_uid != os.getuid() or (st.st_mode & 0o077):
            raise OSError("Sitzungsdatei ist nicht privat")
        return handle.read().strip()


def gleich(a, b):
    """Zeitgleicher Vergleich. Leer oder ungleich ist falsch."""
    if not isinstance(a, str) or not isinstance(b, str) or not a or not b:
        return False
    return hmac.compare_digest(a, b)


def sichere_seite(raw):
    """Nur eine eigene Seite: /, /setup.html, /?test=1 und Ähnliches. Nie eine fremde Adresse."""
    raw = str(raw or "").strip() or "/"
    if not raw.startswith("/"):
        raw = "/" + raw
    pfad, sep, query = raw.partition("?")
    if pfad != "/" and not re.fullmatch(r"/[A-Za-z0-9._-]{1,80}", pfad):
        return "/"
    if ".." in pfad or pfad.startswith("//"):
        return "/"
    if not sep:
        return pfad
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}=[A-Za-z0-9._-]{0,40}", query):
        return pfad
    return pfad + "?" + query


def schreibe_boot(port, naechste):
    """Kleine lokale Seite (0600), die das Geheimnis einmal an den eigenen Browser gibt.

    Die Adresse der Seite enthält das Geheimnis nicht. Der Browser bekommt es
    erst in der Datei, die andere Konten nicht lesen können.
    """
    geheim = lesen(port)
    if not _NAME.fullmatch(geheim):
        raise OSError("Sitzung ungültig")
    seite = sichere_seite(naechste)
    url = "http://127.0.0.1:%d/api/sitzung?k=%s&next=%s" % (
        _port(port), geheim, urllib.parse.quote(seite, safe=""))
    html = (
        "<!doctype html>\n<html lang=\"de\"><head><meta charset=\"utf-8\">\n"
        "<meta name=\"referrer\" content=\"no-referrer\">\n"
        "<title>Omaclusive</title>\n"
        "<style>html,body{margin:0;height:100%;background:#000}</style>\n"
        "</head><body><script>\nlocation.replace(" + json.dumps(url) + ");\n</script></body></html>\n"
    )
    pfad = os.path.join(verzeichnis(), "boot-%d.html" % _port(port))
    if os.path.lexists(pfad) and os.path.islink(pfad):
        os.unlink(pfad)
    fd = _oeffnen(pfad, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, html.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(pfad, 0o600)
    return "file://" + urllib.parse.quote(pfad, safe="/")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "lesen" and len(argv) == 3:
            sys.stdout.write(lesen(argv[2]))
            return 0
        if cmd == "pfad" and len(argv) == 3:
            sys.stdout.write(datei(argv[2]))
            return 0
        if cmd == "boot" and len(argv) in (3, 4):
            sys.stdout.write(schreibe_boot(argv[2], argv[3] if len(argv) == 4 else "/"))
            return 0
    except (OSError, ValueError):
        return 1
    sys.stderr.write("Aufruf: sitzung.py lesen|pfad|boot PORT [seite]\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
