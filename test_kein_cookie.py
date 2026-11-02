#!/usr/bin/env python3
"""Kein Geheimnis im Cookie, strenge Herkunft mit Port, Einmal-Start und die Funde aus
docs/security-review-2026-11-02.md.

Startet den echten Server auf 127.0.0.1 mit einer Wegwerf-Heimat. Ein zweiter Port spielt
die Seite eines anderen lokalen Kontos (omacom/omarchy-plugin-marketplace#12234).
"""
import http.client
import http.server
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

import sitzung

DIR = os.path.dirname(os.path.abspath(__file__))
ALLE_KOEPFE = []  # jede Antwort des Servers, für "nie Set-Cookie" und "nie CORS"
ZAEHLER = [0]


def ok(bedingung, text):
    ZAEHLER[0] += 1
    if not bedingung:
        print("FEHLER:", text)
        sys.exit(1)


def freier_port():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


def anfrage(port, methode, pfad, body=None, token=None, host=None, origin=None, kopf=None, roh=None):
    con = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    k = {"Host": host or ("127.0.0.1:%d" % port)}
    if origin:
        k["Origin"] = origin
    if token:
        k["X-Omaclusive-Token"] = token
    if kopf:
        k.update(kopf)
    daten = roh
    if body is not None:
        daten = json.dumps(body).encode()
        k["Content-Type"] = "application/json"
    con.request(methode, pfad, daten, k)
    antwort = con.getresponse()
    inhalt = antwort.read().decode("utf-8", "replace")
    koepfe = {name.lower(): wert for name, wert in antwort.getheaders()}
    ALLE_KOEPFE.append((methode, pfad, antwort.getheaders()))
    con.close()
    return antwort.status, inhalt, koepfe


def einloesen(port, code, seite="", origin="null"):
    form = urllib.parse.urlencode({"code": code, "seite": seite}).encode()
    return anfrage(port, "POST", "/api/start", origin=origin, roh=form,
                   kopf={"Content-Type": "application/x-www-form-urlencoded"})


def token_aus_start(html):
    m = re.search(r'setItem\("omaclusive-sitzung","([A-Za-z0-9_-]+)"\)', html)
    return m.group(1) if m else ""


def modus(pfad):
    return stat.S_IMODE(os.lstat(pfad).st_mode)


def png():
    # 1x1 Pixel, damit /api/datei etwas Echtes ausliefert.
    import base64
    return base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def server_tests(port, home, logpfad):
    ok(sitzung.warte_auf_server(port, 10.0, home), "Server beweist das Geheimnis")
    geheim = sitzung.lesen(port, home)
    eigen = "http://127.0.0.1:%d" % port
    anderer = "http://127.0.0.1:%d" % (port + 1)

    # --- Einmal-Start statt Cookie/Fragment ---
    st, _, _ = anfrage(port, "POST", "/api/startcode", {})
    ok(st == 401, "Startcode ohne Geheimnis: 401 (%s)" % st)
    st, _, _ = anfrage(port, "POST", "/api/startcode", {}, token=geheim, origin=anderer)
    ok(st == 403, "Startcode von anderem Port: 403 (%s)" % st)
    code = sitzung.startcode_holen(port, home)
    ok(code != geheim and geheim not in code, "Startcode ist nicht das Geheimnis")
    boot = sitzung.boot_schreiben(port, "setup.html", home, code=code)
    with open(boot, encoding="utf-8") as handle:
        boot_html = handle.read()
    ok(geheim not in boot_html and code in boot_html and "#" + code not in boot_html, "Startdatei: Code nur im POST-Formular, kein Fragment")
    ok(modus(boot) == 0o600, "Startdatei 0600")
    st, _, _ = einloesen(port, code, "setup.html", origin=anderer)
    ok(st == 403, "Einlösen von anderem Port: 403 (%s)" % st)
    st, _, _ = einloesen(port, code, "setup.html", origin="http://localhost:%d" % port)
    ok(st == 403, "Einlösen von localhost: 403 (%s)" % st)
    st, _, _ = einloesen(port, code, "//evil.example/")
    ok(st == 400, "Ziel //evil.example: 400 (%s)" % st)
    st, html, k = einloesen(port, code, "setup.html")
    btoken = token_aus_start(html)
    ok(st == 200 and btoken and btoken != geheim and geheim not in html, "Einlösen gibt das Browser-Token, nicht das Datei-Geheimnis")
    ok('location.replace("/setup.html")' in html, "Weiter zur Zielseite ohne Token in der Adresse")
    ok("set-cookie" not in k, "Start setzt kein Cookie")
    ok("script-src 'nonce-" in k.get("content-security-policy", "") and "frame-ancestors 'none'" in k.get("content-security-policy", ""),
       "Startseite mit strenger CSP")
    ok(not os.path.exists(boot), "Startdatei ist nach dem Einlösen gelöscht")
    st, _, _ = einloesen(port, code, "setup.html")
    ok(st == 401, "Startcode gilt nur einmal: 401 (%s)" % st)
    st, _, _ = einloesen(port, "x" * 43)
    ok(st == 401, "erfundener Startcode: 401 (%s)" % st)
    st, _, _ = anfrage(port, "POST", "/api/startcode", {}, token=btoken)
    ok(st == 403, "Browser-Token holt keine Startcodes: 403 (%s)" % st)

    # --- Zugang: anderer Port / andere Herkunft bekommt 401/403, Cookies zählen nicht ---
    for methode, pfad, body in (("GET", "/api/pfad", None), ("GET", "/config.json", None),
                                ("POST", "/api/baustein", {"name": "status.volume"}), ("POST", "/api/back", {})):
        was = "%s %s" % (methode, pfad)
        st, _, _ = anfrage(port, methode, pfad, body)
        ok(st == 401, was + " ohne Geheimnis: 401 (%s)" % st)
        st, _, _ = anfrage(port, methode, pfad, body, token="x" * 43, origin=eigen)
        ok(st == 401, was + " falsches Geheimnis: 401 (%s)" % st)
        for tok in (geheim, btoken):
            st, _, _ = anfrage(port, methode, pfad, body, token=tok, kopf={"Cookie": "omaclusive_session=" + tok})
            ok(st == 200, was + " mit Kopf: 200 (%s)" % st)
            st, _, _ = anfrage(port, methode, pfad, body, kopf={"Cookie": "omaclusive_session=" + tok}, origin=eigen)
            ok(st == 401, was + " nur mit Cookie: 401, Cookies zählen nicht (%s)" % st)
            for beschreibung, extra in (
                ("Origin anderer Port", {"Origin": anderer}),
                ("Origin localhost", {"Origin": "http://localhost:%d" % port}),
                ("Origin fremd", {"Origin": "http://evil.example"}),
                ("Origin null", {"Origin": "null"}),
                ("Referer anderer Port", {"Referer": anderer + "/angriff.html"}),
                ("Sec-Fetch-Site same-site (anderer Port)", {"Sec-Fetch-Site": "same-site"}),
                ("Sec-Fetch-Site cross-site", {"Sec-Fetch-Site": "cross-site"}),
            ):
                st, _, _ = anfrage(port, methode, pfad, body, token=tok, kopf=extra)
                ok(st == 403, "%s %s: 403 (%s)" % (was, beschreibung, st))
            for host in ("127.0.0.1:%d" % (port + 1), "localhost:%d" % port, "evil.example:%d" % port, "127.0.0.1"):
                st, _, _ = anfrage(port, methode, pfad, body, token=tok, host=host)
                ok(st == 403, "%s Host %s: 403 (%s)" % (was, host, st))

    # --- DNS-Rebinding: auch statische Dateien nur mit Host 127.0.0.1:<port> ---
    st, _, _ = anfrage(port, "GET", "/index.html")
    ok(st == 200, "index.html lokal: 200")
    for host in ("evil.example:%d" % port, "localhost:%d" % port, "127.0.0.1:%d" % (port + 1)):
        st, inhalt, _ = anfrage(port, "GET", "/index.html", host=host)
        ok(st == 403 and "sitzung.js" not in inhalt, "statisch mit Host %s: 403 (%s)" % (host, st))
        st, _, _ = anfrage(port, "HEAD", "/index.html", host=host)
        ok(st == 403, "HEAD mit Host %s: 403 (%s)" % (host, st))
    st, _, _ = anfrage(port, "HEAD", "/api/pfad")
    ok(st == 405, "HEAD /api/*: 405 (%s)" % st)

    # --- Sicherheitsköpfe ---
    st, _, k = anfrage(port, "GET", "/index.html")
    ok(k.get("x-frame-options") == "DENY", "X-Frame-Options DENY")
    ok(k.get("referrer-policy") == "no-referrer", "Referrer-Policy no-referrer")
    ok(k.get("x-content-type-options") == "nosniff", "nosniff")
    ok(k.get("cross-origin-resource-policy") == "same-origin", "CORP same-origin")

    # --- Medien: Signatur für genau diese Adresse statt Cookie ---
    ordner = os.path.join(home, "Bilder", "Omaclusive")
    os.makedirs(ordner, exist_ok=True)
    for name in ("a.png", "b.png"):
        with open(os.path.join(ordner, name), "wb") as handle:
            handle.write(png())
    adresse = "/api/datei?quelle=bilder&name=a.png"
    sig = sitzung.signatur(btoken, adresse)
    st, _, _ = anfrage(port, "GET", adresse)
    ok(st == 401, "Bild ohne Signatur: 401 (%s)" % st)
    st, _, k = anfrage(port, "GET", adresse + "&sig=" + sig, kopf={"Sec-Fetch-Site": "same-origin"})
    ok(st == 200 and k.get("content-type") == "image/png", "Bild mit Signatur: 200 (%s)" % st)
    ok("sandbox" in k.get("content-security-policy", "") and k.get("x-content-type-options") == "nosniff",
       "Medien mit CSP sandbox und nosniff")
    st, _, _ = anfrage(port, "GET", "/api/datei?quelle=bilder&name=b.png&sig=" + sig)
    ok(st == 401, "Signatur gilt nicht für eine andere Datei: 401 (%s)" % st)
    st, _, _ = anfrage(port, "GET", adresse + "&sig=" + sitzung.signatur(geheim, adresse))
    ok(st == 401, "Signatur mit dem Datei-Geheimnis zählt nicht: 401 (%s)" % st)
    st, _, _ = anfrage(port, "GET", adresse + "&sig=" + sig, kopf={"Sec-Fetch-Site": "same-site"})
    ok(st == 403, "Signatur von anderem Port (same-site): 403 (%s)" % st)
    st, _, _ = anfrage(port, "GET", adresse + "&sig=" + sig, host="localhost:%d" % port)
    ok(st == 403, "Signatur mit fremdem Host: 403 (%s)" % st)
    st, _, _ = anfrage(port, "GET", "/api/pfad?sig=" + sitzung.signatur(btoken, "/api/pfad"))
    ok(st == 401, "Signatur öffnet keine anderen Wege: 401 (%s)" % st)
    st, _, _ = anfrage(port, "GET", "/config.json?sig=" + sitzung.signatur(btoken, "/config.json"))
    ok(st == 401, "Signatur öffnet config.json nicht: 401 (%s)" % st)

    # --- Kopfzeilen und Körper ---
    for wert in ("-1", "abc", "99999999"):
        anfang = time.monotonic()
        st, _, _ = anfrage(port, "POST", "/api/back", token=geheim, kopf={"Content-Length": wert, "Content-Type": "application/json"})
        ok(st == 400 and time.monotonic() - anfang < 5, "Content-Length %s: 400 ohne Hängen (%s)" % (wert, st))
    st, _, k = anfrage(port, "OPTIONS", "/api/pfad", origin=anderer, kopf={"Access-Control-Request-Method": "POST"})
    ok(st in (403, 405, 501) and "access-control-allow-origin" not in k, "kein CORS-Preflight (%s)" % st)

    # --- nie Set-Cookie, nie CORS, Geheimnisse nie im Log ---
    for methode, pfad, koepfe in ALLE_KOEPFE:
        namen = [n.lower() for n, _ in koepfe]
        ok("set-cookie" not in namen, "Set-Cookie bei %s %s" % (methode, pfad))
        ok(not any(n.startswith("access-control-") for n in namen), "CORS-Kopf bei %s %s" % (methode, pfad))
    with open(logpfad, encoding="utf-8", errors="replace") as handle:
        log = handle.read()
    for wert, name in ((geheim, "Datei-Geheimnis"), (btoken, "Browser-Token"), (code, "Startcode"), (sig, "Signatur")):
        ok(wert not in log, name + " steht im Server-Log")
    return geheim, btoken


def in_prozess_tests(home):
    """Dinge, die man am laufenden Prozess besser direkt prüft: Fehlertext, Zeitlimit, Ablauf des Codes."""
    import server
    port = freier_port()
    server.PORT = port
    server.SESSION_TOKEN = "s" * 43
    server.BROWSER_TOKEN = "b" * 43
    alt_pfad, alt_timeout, alt_sek = server._pfad_antwort, server.H.timeout, server._STARTCODE_SEKUNDEN

    def kaputt():
        raise RuntimeError("GEHEIM-intern /home/geheim/pfad")

    server._pfad_antwort = kaputt
    server.H.timeout = 1
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), server.H)
    faden = threading.Thread(target=srv.serve_forever, daemon=True)
    faden.start()
    stderr_alt = sys.stderr
    try:
        sys.stderr = open(os.devnull, "w")
        st, inhalt, _ = anfrage(port, "GET", "/api/pfad", token=server.SESSION_TOKEN)
        sys.stderr.close()
        sys.stderr = stderr_alt
        ok(st == 500 and "GEHEIM" not in inhalt and "Traceback" not in inhalt and "/home" not in inhalt,
           "Fehler gibt 500 ohne Interna: %s %r" % (st, inhalt))
        # Hängende Verbindung wird nach dem Zeitlimit geschlossen
        so = socket.create_connection(("127.0.0.1", port), timeout=5)
        so.sendall(b"GET /index.html HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n" % port)
        anfang = time.monotonic()
        try:
            rest = so.recv(100)
        except socket.timeout:
            rest = None
        so.close()
        ok(rest == b"" and time.monotonic() - anfang < 4, "langsame Verbindung wird geschlossen")
        # Abgelaufener Startcode
        server._STARTCODE_SEKUNDEN = -1
        code = server._startcode_neu()
        ok(not server._startcode_einloesen(code), "abgelaufener Startcode gilt nicht")
        server._STARTCODE_SEKUNDEN = alt_sek
        code = server._startcode_neu()
        ok(server._startcode_einloesen(code) and not server._startcode_einloesen(code), "Startcode genau einmal")
    finally:
        if sys.stderr is not stderr_alt:
            sys.stderr = stderr_alt
        srv.shutdown()
        srv.server_close()
        server._pfad_antwort, server.H.timeout, server._STARTCODE_SEKUNDEN = alt_pfad, alt_timeout, alt_sek


def modul_tests():
    # Ziel nach dem Start
    for gut in ("", "setup.html", "index.html?selftest=1", "?test=1", "editor.html?lang=en"):
        ok(sitzung.ziel_ok(gut), "Ziel erlaubt: " + gut)
    for schlecht in ("//evil.example", "/setup.html", "http://evil.example/", "javascript:alert(1)", "a.html#x", "../x.html", "x.html\n"):
        ok(not sitzung.ziel_ok(schlecht), "Ziel abgelehnt: %r" % schlecht)
    # Token nie aus Cookie, WebSocket-Token aus dem Unterprotokoll
    ok(sitzung.token_aus({"Cookie": "omaclusive_session=" + "a" * 43}) == "", "token_aus liest kein Cookie")
    ok(sitzung.token_aus({"Sec-WebSocket-Protocol": "omaclusive, omaclusive-token." + "c" * 43}) == "c" * 43, "Token aus Unterprotokoll")
    ok(sitzung.pruefen({"Host": "127.0.0.1:8795"}, 8795, ["a" * 43]) == 401, "ohne Token 401")
    ok(sitzung.pruefen({"Host": "127.0.0.1:8795", "Origin": "http://127.0.0.1:8796", "X-Omaclusive-Token": "a" * 43}, 8795, ["a" * 43]) == 403,
       "anderer Port 403")
    ok(sitzung.pruefen({"Host": "127.0.0.1:8795", "X-Omaclusive-Token": "a" * 43}, 8795, ["", "a" * 43]) == 200, "richtiges Token 200")
    # Konstante Zeit: compare_digest, kein == auf Geheimnissen in sitzung.py/server.py
    for datei in ("sitzung.py", "server.py"):
        with open(os.path.join(DIR, datei), encoding="utf-8") as handle:
            text = handle.read()
        ok(not re.search(r"(TOKEN|geheimnis|token)\s*==|==\s*(SESSION_TOKEN|BROWSER_TOKEN)", text), datei + ": Geheimnis mit == verglichen")
    ok(re.search(r"ThreadingHTTPServer\(\(\"127\.0\.0\.1\", PORT\)", open(os.path.join(DIR, "server.py"), encoding="utf-8").read()),
       "Server bindet nur 127.0.0.1")
    # Kein Cookie mehr im Browser-Code, nirgends
    for datei in ("sitzung.js", "app.js", "pfad.js", "sprache.js", "index.html", "setup.html", "editor.html", "pflege.html"):
        with open(os.path.join(DIR, datei), encoding="utf-8") as handle:
            text = handle.read()
        setzt = [z for z in re.findall(r"document\.cookie\s*=[^\n]*", text) if "Max-Age=0" not in z]
        ok(not setzt, datei + ": setzt ein Cookie: %s" % setzt)
        ok(not re.search(r"localStorage\s*[.\[]", text), datei + ": localStorage")
        ok("location.hash" not in text, datei + ": liest das Fragment")
    with open(os.path.join(DIR, "sitzung.js"), encoding="utf-8") as handle:
        js = handle.read()
    ok("Max-Age=0" in js, "sitzung.js räumt das alte Cookie weg")
    # XSS: keine HTML-Vorlagen mit Daten in setup.html
    with open(os.path.join(DIR, "setup.html"), encoding="utf-8") as handle:
        setup = handle.read()
    ok(not re.search(r"innerHTML\s*=\s*`[^`]*\$\{", setup), "setup.html baut keine Kacheln aus HTML-Vorlagen")
    # Autostart: Pfad mit Leerzeichen und Sonderzeichen bleibt ein Argument
    import praxis
    zeile = praxis.autostart_text("/home/a b/x$y%z.sh").splitlines()[3]
    ok(zeile == 'Exec="/home/a b/x\\\\$y%%z.sh"', "Exec gequotet: " + zeile)
    ok(praxis.autostart_text("/home/a/start-talker.sh").splitlines()[3] == "Exec=/home/a/start-talker.sh", "normaler Pfad bleibt")
    try:
        praxis.autostart_text("/home/a\nExec=boese")
        ok(False, "Zeilenumbruch im Exec-Pfad")
    except ValueError:
        pass
    # Installer bringt alle Module mit, die der Server lädt
    with open(os.path.join(DIR, "install.sh"), encoding="utf-8") as handle:
        install = handle.read()
    liste = re.search(r"for f in (.*?); do", install, re.S).group(1).replace("\\\n", " ").split()
    with open(os.path.join(DIR, "server.py"), encoding="utf-8") as handle:
        module = set(re.findall(r"^\s*import ([a-z_]+)\s*$", handle.read(), re.M))
    for name in sorted(module):
        if os.path.isfile(os.path.join(DIR, name + ".py")):
            ok(name + ".py" in liste, "install.sh kopiert %s.py nicht" % name)
    for seite in ("index.html", "setup.html", "editor.html", "pflege.html", "sitzung.js"):
        ok(seite in liste, "install.sh kopiert %s nicht" % seite)


def stimmen_test(home):
    """Fehler beim Laden einer Stimme: fester Grund, keine Pfade oder Adressen an die Oberfläche."""
    import stimmen
    v = stimmen.liste()[0]
    alt_da, alt_lade = stimmen.da, stimmen.herunterladen

    def lade(_v):
        raise OSError("/home/geheim/.local/share/omaclusive/voices/x.onnx.teil: https://intern.example/")

    stimmen.da = lambda _v: False
    stimmen.herunterladen = lade
    stderr_alt = sys.stderr
    try:
        sys.stderr = open(os.devnull, "w")
        ok(stimmen.starten(v["id"], lambda fn: None)[0], "Stimme startet")
        for _ in range(100):
            if stimmen.status()["status"] != "laeuft":
                break
            time.sleep(0.02)
        z = stimmen.status()
        ok(z["status"] == "fehler" and z["fehler"] == "netz" and "/home" not in json.dumps(z), "Stimmenfehler ohne Interna: %s" % z)
    finally:
        sys.stderr.close()
        sys.stderr = stderr_alt
        stimmen.da, stimmen.herunterladen = alt_da, alt_lade


def main():
    modul_tests()
    port = freier_port()
    home = tempfile.mkdtemp(prefix="omaclusive-keks-")
    cfg = os.path.join(DIR, "config.json")
    sicher = None
    if os.path.exists(cfg):
        sicher = os.path.join(home, "config.original")
        shutil.copy(cfg, sicher)
    shutil.copy(os.path.join(DIR, "config.example.json"), cfg)
    env = dict(os.environ, HOME=home, PORT=str(port), PYTHONUNBUFFERED="1")
    env.pop("XDG_RUNTIME_DIR", None)
    alt_xdg = os.environ.pop("XDG_RUNTIME_DIR", None)
    logpfad = os.path.join(home, "server.err")
    log = open(logpfad, "w", encoding="utf-8")
    srv = subprocess.Popen([sys.executable, "server.py"], cwd=DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        server_tests(port, home, logpfad)
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()
        if sicher:
            shutil.copy(sicher, cfg)
        else:
            for pfad in (cfg, cfg + ".bak"):
                try:
                    os.remove(pfad)
                except OSError:
                    pass
        if alt_xdg is not None:
            os.environ["XDG_RUNTIME_DIR"] = alt_xdg
    try:
        os.environ["HOME"] = home
        in_prozess_tests(home)
        stimmen_test(home)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    ok(os.path.exists(cfg) == bool(sicher), "Test hinterlässt keine config.json")
    print("KEIN_COOKIE_OK %d Prüfungen" % ZAEHLER[0])


if __name__ == "__main__":
    main()
