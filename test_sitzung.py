#!/usr/bin/env python3
"""Sitzung, Herkunft und GET-Aktionen.

Andere lokale Konten dürfen den Rechner nicht ausschalten, nichts öffnen und
die Konfiguration nicht schreiben. Ein mitgeschicktes confirm ist kein Passwort.
GET führt keine Aktion aus. Die normale Seite bekommt das Geheimnis über die
Startdatei, ohne eine Anmeldung.
"""
import http.client
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse

import sitzung

DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("SITZUNG_PORT", "8801"))
DEBUG = int(os.environ.get("SITZUNG_DEBUG", "9351"))


def ok(bedingung, text):
    if not bedingung:
        print("FEHLER:", text)
        sys.exit(1)


def main():
    home = tempfile.mkdtemp(prefix="omaclusive-sitzung-")
    runtime = os.path.join(home, "xdg")
    os.makedirs(runtime, mode=0o700)
    os.chmod(runtime, 0o700)
    os.environ["XDG_RUNTIME_DIR"] = runtime
    os.environ["HOME"] = home
    cfgp = os.path.join(DIR, "config.json")
    ok(not os.path.exists(cfgp), "config.json darf vorher nicht da sein")
    with open(os.path.join(DIR, "config.example.json"), encoding="utf-8") as handle:
        config = json.load(handle)
    config["einrichtung"] = {"fertig": True, "stand": 2, "sprache": True}
    config["speak"] = False
    config["hoeren"] = False
    config["autostart"] = False
    config["modus"] = "b"
    with open(cfgp, "w", encoding="utf-8") as handle:
        json.dump(config, handle)
    env = dict(os.environ, PORT=str(PORT), HOME=home, XDG_RUNTIME_DIR=runtime)
    srv = subprocess.Popen(
        [sys.executable, "server.py"], cwd=DIR, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    chrome = None
    try:
        token = ""
        for _ in range(60):
            try:
                token = sitzung.lesen(PORT)
                break
            except OSError:
                time.sleep(0.1)
        ok(bool(token) and token == sitzung.lesen(PORT), "Sitzung liegt und bleibt gleich")
        pfad = sitzung.datei(PORT)
        ok(stat.S_IMODE(os.stat(pfad).st_mode) == 0o600, "Sitzungsdatei ist 0600")
        ok(stat.S_IMODE(os.stat(os.path.dirname(pfad)).st_mode) == 0o700, "Sitzungsordner ist 0700")
        ok(os.stat(pfad).st_uid == os.getuid(), "Sitzungsdatei gehört diesem Konto")
        ok(not pfad.startswith(DIR + os.sep), "Sitzung liegt nicht im Web-Ordner")

        def req(methode, pfad_http, body=None, host=None, origin=None, token_wert=None, extra=None, cookie=None):
            letzter = None
            for _ in range(60):
                try:
                    con = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
                    kopf = {"Host": host or ("127.0.0.1:%d" % PORT)}
                    if origin:
                        kopf["Origin"] = origin
                    if token_wert:
                        kopf["X-Omaclusive-Token"] = token_wert
                    if cookie:
                        kopf["Cookie"] = cookie
                    if extra:
                        kopf.update(extra)
                    daten = None
                    if body is not None:
                        kopf["Content-Type"] = "application/json"
                        daten = json.dumps(body)
                    con.request(methode, pfad_http, daten, kopf)
                    antwort = con.getresponse()
                    roh = antwort.read()
                    text = roh.decode("utf-8", "replace")
                    try:
                        inhalt = json.loads(text) if text[:1] in "{[" else text
                    except json.JSONDecodeError:
                        inhalt = text
                    return antwort.status, inhalt, {k.lower(): v for k, v in antwort.getheaders()}
                except (ConnectionRefusedError, OSError) as fehler:
                    letzter = fehler
                    time.sleep(0.1)
            raise SystemExit("Server antwortet nicht: %s" % letzter)

        st, bereit, _ = req("GET", "/api/bereit")
        ok(st == 200 and bereit.get("ok") is True, "Bereitschaft ohne Geheimnis")
        st, _, _ = req("GET", "/api/bereit", host="evil.example")
        ok(st == 403, "fremder Host auch bei der Bereitschaft")

        st, _, _ = req("GET", "/index.html")
        ok(st == 200, "die Seite selbst ist erreichbar")
        st, _, _ = req("GET", "/config.json")
        ok(st == 403, "config.json ohne Sitzung: 403")
        st, cfg, _ = req("GET", "/config.json", token_wert=token)
        ok(st == 200 and isinstance(cfg, dict) and cfg.get("modus") == "b", "config.json mit Sitzung")
        st, _, _ = req("GET", "/config.json.bak", token_wert=token)
        ok(st == 404, "Sicherung wird nicht ausgeliefert")

        st, _, _ = req("GET", "/api/modi")
        ok(st == 403, "Lesen ohne Sitzung: 403")
        st, modi, _ = req("GET", "/api/modi", token_wert=token)
        ok(st == 200 and modi.get("ok") is True, "Lesen mit Sitzung")
        st, _, _ = req("GET", "/api/modi?k=" + urllib.parse.quote(token))
        ok(st == 403, "Geheimnis in der Adresse gilt nicht für die Schnittstelle")
        st, _, _ = req("GET", "/api/modi", token_wert="falsch")
        ok(st == 403, "falsches Geheimnis: 403")
        st, _, _ = req("GET", "/api/modi", token_wert=token, host="evil.example:%d" % PORT)
        ok(st == 403, "fremder Host trotz Geheimnis: 403")
        st, _, _ = req("GET", "/api/modi", token_wert=token, origin="http://evil.example")
        ok(st == 403, "fremde Herkunft trotz Geheimnis: 403")
        st, _, _ = req("GET", "/api/modi", token_wert=token, extra={"Referer": "http://evil.example/a"})
        ok(st == 403, "fremder Referer: 403")
        st, _, _ = req("GET", "/api/modi", token_wert=token, extra={"Sec-Fetch-Site": "cross-site"})
        ok(st == 403, "cross-site: 403")
        st, _, _ = req(
            "GET", "/api/modi", token_wert=token,
            origin="http://127.0.0.1:%d" % PORT,
            extra={"Sec-Fetch-Site": "same-origin"},
        )
        ok(st == 200, "eigene Herkunft darf lesen")

        st, _, _ = req("GET", "/api/open?url=https://example.org")
        ok(st == 403, "GET /api/open ohne Sitzung: 403")
        st, _, _ = req("GET", "/api/open?url=https://example.org", token_wert=token)
        ok(st == 405, "GET /api/open tut nichts")
        st, _, _ = req("GET", "/api/back", token_wert=token)
        ok(st == 405, "GET /api/back tut nichts")
        st, _, _ = req("GET", "/api/baustein", token_wert=token)
        ok(st == 405, "GET /api/baustein tut nichts")
        st, _, _ = req("POST", "/api/open", {"url": "https://example.org"})
        ok(st == 403, "POST /api/open ohne Sitzung: 403")
        st, _, _ = req("POST", "/api/back")
        ok(st == 403, "POST /api/back ohne Sitzung: 403")

        aus = {"name": "system.poweroff", "confirm": True}
        st, _, _ = req("POST", "/api/baustein", aus)
        ok(st == 403, "confirm allein schaltet nicht aus")
        st, _, _ = req("POST", "/api/baustein", aus, token_wert=token, origin="http://evil.example")
        ok(st == 403, "Ausschalten von fremder Herkunft: 403")
        st, _, _ = req("POST", "/api/baustein", aus, token_wert=token, host="evil.example")
        ok(st == 403, "Ausschalten mit fremdem Host: 403")
        st, frage, _ = req(
            "POST", "/api/baustein", {"name": "system.poweroff", "confirm": False},
            token_wert=token, origin="http://127.0.0.1:%d" % PORT,
        )
        ok(st == 200 and frage.get("bestaetigen") is True and frage.get("ok") is False, "Rückfrage ohne Ausschalten: %s" % frage)
        st, nein, _ = req(
            "POST", "/api/baustein", {"name": "system.reboot", "confirm": False},
            token_wert=token,
        )
        ok(st == 200 and nein.get("bestaetigen") is True, "Neustart fragt nur")
        st, unbekannt, _ = req(
            "POST", "/api/baustein", {"name": "system.format", "confirm": True},
            token_wert=token, origin="http://127.0.0.1:%d" % PORT,
        )
        ok(st == 200 and unbekannt.get("ok") is False, "unbekannter Baustein läuft nicht: %s" % unbekannt)

        st, _, kopf = req("GET", "/api/sitzung?k=falsch&next=/")
        ok(st == 403 and "set-cookie" not in kopf, "falsche Übergabe setzt kein Cookie")
        st, _, kopf = req("GET", "/api/sitzung?k=%s&next=%s" % (urllib.parse.quote(token), urllib.parse.quote("/setup.html")))
        ok(st == 303 and kopf.get("location") == "/setup.html", "Übergabe leitet auf die eigene Seite: %s" % kopf.get("location"))
        cookie = kopf.get("set-cookie", "")
        ok(cookie.startswith("omaclusive=") and "HttpOnly" in cookie and token in cookie, "Cookie nur für diese Sitzung")
        ok("omaclusive=" in cookie and "Secure" not in cookie, "Cookie passt zu http://127.0.0.1")
        st, mit_cookie, _ = req("GET", "/api/pfad", cookie=cookie.split(";", 1)[0])
        ok(st == 200 and mit_cookie.get("ok") is True and mit_cookie.get("modus") == "b", "Cookie trägt die normale Seite")
        st, _, kopf = req("GET", "/api/sitzung?k=%s&next=https://evil.example" % urllib.parse.quote(token))
        ok(st == 303 and kopf.get("location") == "/", "keine Weiterleitung nach draußen: %s" % kopf.get("location"))

        boot = sitzung.schreibe_boot(PORT, "/")
        ok(token not in boot and boot.startswith("file://"), "Startadresse enthält das Geheimnis nicht")
        boot_pfad = urllib.parse.unquote(boot[len("file://"):])
        ok(stat.S_IMODE(os.stat(boot_pfad).st_mode) == 0o600, "Startdatei ist 0600")
        ok(token in open(boot_pfad, encoding="utf-8").read(), "das Geheimnis steht nur in der Startdatei")

        st, zurueck, _ = req("POST", "/api/back", token_wert=token)
        ok(st == 200 and zurueck.get("ok") is True, "POST /api/back mit Sitzung")

        if os.environ.get("OHNE_BROWSER") == "1":
            print("SITZUNG_OK ohne Browser")
            return
        chrome_bin = os.environ.get("CHROME") or shutil.which("google-chrome") or shutil.which("chromium")
        ok(bool(chrome_bin), "Chrome für den normalen Ablauf")
        profil = os.path.join(home, "profil")
        os.makedirs(profil, mode=0o700)
        chrome = subprocess.Popen(
            [chrome_bin, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
             "--disable-dev-shm-usage", "--remote-allow-origins=*", "--window-size=1480,780",
             "--user-data-dir=" + profil, "--remote-debugging-port=" + str(DEBUG), boot],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        cmdline = open("/proc/%d/cmdline" % chrome.pid, "rb").read().replace(b"\0", b" ").decode("utf-8", "replace")
        ok(token not in cmdline, "Befehlszeile enthält das Geheimnis nicht")
        pruef = subprocess.run(
            [shutil.which("node") or "node", os.path.join(DIR, "test_sitzung_browser.js")],
            env=dict(os.environ, PORT=str(PORT), DEBUG_PORT=str(DEBUG)),
            capture_output=True, text=True, timeout=40,
        )
        ok(pruef.returncode == 0, "normaler Ablauf: %s %s" % (pruef.stdout, pruef.stderr))
        ok("OBERFLAECHE_OK" in pruef.stdout, pruef.stdout)
    finally:
        if chrome:
            chrome.terminate()
            try:
                chrome.wait(5)
            except Exception:
                chrome.kill()
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            srv.kill()
        for name in ("config.json", "config.json.bak"):
            try:
                os.remove(os.path.join(DIR, name))
            except OSError:
                pass
        shutil.rmtree(home, ignore_errors=True)
    print("SITZUNG_OK")


if __name__ == "__main__":
    main()
