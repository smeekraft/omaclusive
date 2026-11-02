#!/usr/bin/env python3
"""Sitzungsgeheimnis für den lokalen Omaclusive-Server.

Das Geheimnis entsteht beim Start und liegt in einer Datei mit Modus 0600
in einem Ordner mit Modus 0700. Andere Benutzerkonten auf demselben Rechner
können sie nicht lesen. Der Ordner ist das private Laufzeitverzeichnis,
wenn das privat ist und der Webserver es nicht ausliefert. Sonst ein
privater Ordner außerhalb der Web-Wurzel (normalerweise
~/.local/state/omaclusive/run/, nie ~/.local/share/omaclusive/run/).
Das Datei-Geheimnis bekommen nur lokale Werkzeuge dieses Kontos (Starter,
zurueck.sh, Knopf-Brücken) im Kopf X-Omaclusive-Token. Der Browser bekommt es nie:
Der Starter holt damit einen Einmal-Code, den die Startseite per POST einlöst. Dafür gibt
der Server ein eigenes Browser-Token aus, das nur im Speicher und in sessionStorage der
Herkunft http://127.0.0.1:<port> liegt (kein Cookie, keine Adresse, kein Log).
"""
import hmac
import os
import re
import stat
import urllib.parse

_NAME = re.compile(r"[A-Za-z0-9_-]{20,128}")


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


_CODE = re.compile(r"[A-Za-z0-9_-]{20,128}")
# Ziel nach dem Start: eine Seite im Programmordner, optional mit Abfrage. Nie mit / am Anfang
# (sonst "//fremd.example"), nie mit Fragment.
_ZIEL = re.compile(r"(?:[A-Za-z0-9_-]{1,40}\.html)?(?:\?[A-Za-z0-9_=&%.-]{0,200})?")


def ziel_ok(seite):
    return isinstance(seite, str) and bool(_ZIEL.fullmatch(seite))


def boot_name(port, code):
    """Name der Startdatei. Hängt am Einmal-Code, damit der Server genau diese Datei löschen kann."""
    import hashlib
    kurz = hashlib.sha256(("boot:" + code).encode("ascii")).hexdigest()[:24]
    return "%d-%s.boot.html" % (int(port), kurz)


def boot_html(port, seite, code):
    """Kleine lokale Seite, die einen Einmal-Code per POST an den Server gibt.

    Kein Geheimnis in einer Adresse (auch nicht im Fragment), keins in der Befehlszeile.
    Der Code gilt nur einmal und nur kurz; der Server tauscht ihn gegen das Browser-Token,
    das nur im Speicher und in sessionStorage dieser einen Herkunft liegt.
    """
    import html as _html
    if not ziel_ok(seite or "") or not _CODE.fullmatch(code or ""):
        raise OSError("Startdaten ungültig")
    aktion = "http://127.0.0.1:%d/api/start" % int(port)
    return (
        "<!doctype html><meta charset=\"utf-8\"><meta name=\"referrer\" content=\"no-referrer\">"
        "<title>Omaclusive</title>"
        "<form method=\"post\" action=\"%s\" enctype=\"application/x-www-form-urlencoded\">"
        "<input type=\"hidden\" name=\"code\" value=\"%s\">"
        "<input type=\"hidden\" name=\"seite\" value=\"%s\">"
        "<noscript><button>Omaclusive starten</button></noscript></form>"
        "<script>document.forms[0].submit();</script>\n"
        % (aktion, _html.escape(code, quote=True), _html.escape(seite or "", quote=True))
    )


def startcode_holen(port, home=None, timeout=2.0):
    """Fragt den laufenden Server mit dem Datei-Geheimnis nach einem Einmal-Code."""
    import http.client
    import json
    geheimnis = lesen(port, home)
    con = http.client.HTTPConnection("127.0.0.1", int(port), timeout=timeout)
    try:
        con.request("POST", "/api/startcode", body=b"{}", headers={
            "Host": "127.0.0.1:%d" % int(port),
            "Content-Type": "application/json",
            "X-Omaclusive-Token": geheimnis,
        })
        antwort = con.getresponse()
        daten = json.loads(antwort.read(4096).decode("utf-8"))
    except (OSError, ValueError) as fehler:
        raise OSError("kein Startcode") from fehler
    finally:
        con.close()
    code = daten.get("code") if isinstance(daten, dict) else None
    if antwort.status != 200 or not isinstance(code, str) or not _CODE.fullmatch(code):
        raise OSError("kein Startcode")
    return code


def boot_schreiben(port, seite, home=None, code=None):
    """Schreibt die Startdatei (0600) in den privaten Sitzungsordner und gibt ihren Pfad zurück."""
    seite = seite or ""
    if not ziel_ok(seite):
        raise OSError("Seite ungültig")
    code = code or startcode_holen(port, home)
    pfad = os.path.join(ordner(home), boot_name(port, code))
    _schreiben(pfad, boot_html(port, seite, code), home)
    return pfad


def boot_url(port, seite, home=None):
    return "file://" + urllib.parse.quote(boot_schreiben(port, seite, home))


def _host_ok(headers, port):
    """Nur genau 127.0.0.1:<port>. Schützt vor DNS-Rebinding und fremden Namen."""
    host = str(headers.get("Host") or "").strip().lower()
    return host == "127.0.0.1:%d" % int(port)


def eigene_herkunft(port):
    return "http://127.0.0.1:%d" % int(port)


def _origin_ok(headers, port, null_erlaubt=False):
    """Origin (wenn da) muss genau diese Herkunft sein, inklusive Port. Cookies trennen keine Ports,
    Origin schon. Ohne Origin (GET im selben Ursprung, Werkzeuge ohne Browser) zählen Referer
    und Sec-Fetch-Site."""
    origin = str(headers.get("Origin") or "").strip()
    if origin:
        if null_erlaubt and origin == "null":
            return True
        return origin == eigene_herkunft(port)
    referer = str(headers.get("Referer") or "").strip()
    if referer:
        teile = urllib.parse.urlparse(referer)
        try:
            ref_port = teile.port
        except ValueError:
            return False
        if teile.scheme != "http" or (teile.hostname or "") != "127.0.0.1" or ref_port != int(port):
            return False
    site = str(headers.get("Sec-Fetch-Site") or "").strip().lower()
    if site and site not in ("same-origin", "none"):
        return False
    return True


def herkunft_ok(headers, port):
    """Host und, falls der Browser sie schickt, Origin/Referer/Sec-Fetch-Site müssen genau diese Herkunft sein."""
    return _host_ok(headers, port) and _origin_ok(headers, port)


WS_PROTOKOLL = "omaclusive"
_WS_TOKEN = "omaclusive-token."


def ws_protokolle(headers):
    roh = str(headers.get("Sec-WebSocket-Protocol") or "")
    return [teil.strip() for teil in roh.split(",") if teil.strip()]


def token_aus(headers):
    """Geheimnis nur aus dem eigenen Kopf X-Omaclusive-Token, beim WebSocket aus dem Unterprotokoll.
    Nie aus einem Cookie und nie aus der Adresse."""
    kopf = str(headers.get("X-Omaclusive-Token") or "").strip()
    if kopf:
        return kopf
    for teil in ws_protokolle(headers):
        if teil.startswith(_WS_TOKEN):
            return teil[len(_WS_TOKEN):]
    return ""


def eines_gleich(gegeben, geheimnisse):
    """Vergleicht mit jedem Geheimnis in konstanter Zeit, ohne früh abzubrechen."""
    treffer = False
    for g in geheimnisse:
        if g and gleich(gegeben, g):
            treffer = True
    return treffer


def pruefen(headers, port, geheimnisse):
    """200 bei gültigem Zugang, 403 bei fremder Herkunft (Host, Origin, Port), 401 ohne oder mit falschem Geheimnis."""
    if not herkunft_ok(headers, port):
        return 403
    gegeben = token_aus(headers)
    if not gegeben or not eines_gleich(gegeben, [g for g in geheimnisse if g]):
        return 401
    return 200


def zugang_ok(headers, port, geheimnis):
    geheimnisse = geheimnis if isinstance(geheimnis, (list, tuple)) else [geheimnis]
    return pruefen(headers, port, geheimnisse) == 200


def signatur(schluessel, pfad_und_abfrage):
    """Signatur für Medien-Adressen (img, video, PDF): HMAC-SHA256 über den Pfad mit Abfrage.
    Gilt nur für genau diese Datei und nur zum Lesen. Das Browser-Token selbst steht nie in der Adresse."""
    if not schluessel or not isinstance(pfad_und_abfrage, str):
        return ""
    return hmac.new(schluessel.encode("ascii"), ("medien\n" + pfad_und_abfrage).encode("utf-8"), "sha256").hexdigest()


def signatur_trennen(roh_pfad):
    """Zerlegt '/api/x?a=1&sig=abc' in ('/api/x?a=1', 'abc'). sig muss der letzte Parameter sein."""
    teile = urllib.parse.urlsplit(roh_pfad)
    abfrage = teile.query
    m = re.search(r"(?:^|&)sig=([0-9a-f]{64})$", abfrage)
    if not m:
        return None, ""
    rest = abfrage[: m.start()]
    return teile.path + ("?" + rest if rest else ""), m.group(1)


def signatur_ok(roh_pfad, schluessel):
    basis, sig = signatur_trennen(roh_pfad)
    if not basis or not schluessel:
        return False
    return gleich(sig, signatur(schluessel, basis))


_PROBE = re.compile(r"[A-Za-z0-9_-]{16,64}")


def beweis(geheimnis, probe):
    """Antwort des Servers auf /api/bereit?probe=...: zeigt, dass er das Geheimnis kennt, ohne es zu verraten."""
    if not geheimnis or not isinstance(probe, str) or not _PROBE.fullmatch(probe):
        return ""
    return hmac.new(geheimnis.encode("ascii"), ("bereit:" + probe).encode("ascii"), "sha256").hexdigest()


def server_echt(port, home=None, timeout=1.0):
    """True nur, wenn auf dem Port unser Server mit dem Geheimnis aus der Sitzungsdatei lauscht.

    Hat ein anderes Konto den Port vorher belegt, kennt es das Geheimnis nicht.
    Dann startet der Starter keinen Browser auf diesen Port.
    """
    import http.client
    import json
    import secrets
    try:
        geheimnis = lesen(port, home)
    except OSError:
        return False
    probe = secrets.token_urlsafe(24)
    con = http.client.HTTPConnection("127.0.0.1", int(port), timeout=timeout)
    try:
        con.request("GET", "/api/bereit?probe=" + probe, headers={"Host": "127.0.0.1:%d" % int(port)})
        antwort = con.getresponse()
        daten = json.loads(antwort.read(4096).decode("utf-8"))
    except (OSError, ValueError):
        return False
    finally:
        con.close()
    if antwort.status != 200 or not isinstance(daten, dict):
        return False
    return gleich(str(daten.get("beweis") or ""), beweis(geheimnis, probe))


def warte_auf_server(port, sekunden=5.0, home=None):
    import time
    ende = time.monotonic() + sekunden
    while True:
        if server_echt(port, home):
            return True
        if time.monotonic() >= ende:
            return False
        time.sleep(0.25)
