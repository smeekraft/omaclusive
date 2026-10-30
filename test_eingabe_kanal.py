#!/usr/bin/env python3
"""Eingabekanal (WebSocket) nur mit Sitzungsgeheimnis, Server-Beweis für den Starter,
nichts Privates als statische Datei.

Startet den echten Server auf 127.0.0.1 mit einer Wegwerf-Heimat. Eine Attrappe spielt
das fremde Konto, das einen Port vorher belegt.
"""
import base64
import hashlib
import http.server
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time

import pflege
import sitzung

DIR = os.path.dirname(os.path.abspath(__file__))
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ok(bedingung, text):
    if not bedingung:
        print("FEHLER:", text)
        sys.exit(1)


def freier_port():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


def modus(pfad):
    return stat.S_IMODE(os.lstat(pfad).st_mode)


def anfrage(port, pfad, token=None):
    import http.client
    con = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    kopf = {"Host": "127.0.0.1:%d" % port}
    if token:
        kopf["X-Omaclusive-Token"] = token
    con.request("GET", pfad, headers=kopf)
    antwort = con.getresponse()
    roh = antwort.read().decode("utf-8", "replace")
    con.close()
    return antwort.status, roh


def handshake(port, token=None, keks=None, origin=None, host=None):
    """Roher WebSocket-Handshake. Gibt (status, socket oder None) zurück."""
    so = socket.create_connection(("127.0.0.1", port), timeout=5)
    schluessel = base64.b64encode(os.urandom(16)).decode()
    zeilen = [
        "GET /api/eingabe HTTP/1.1",
        "Host: %s" % (host or "127.0.0.1:%d" % port),
        "Upgrade: websocket",
        "Connection: Upgrade",
        "Sec-WebSocket-Key: " + schluessel,
        "Sec-WebSocket-Version: 13",
    ]
    if token:
        zeilen.append("X-Omaclusive-Token: " + token)
    if keks:
        zeilen.append("Cookie: omaclusive_session=" + keks)
    if origin:
        zeilen.append("Origin: " + origin)
    so.sendall(("\r\n".join(zeilen) + "\r\n\r\n").encode())
    kopf = b""
    while b"\r\n\r\n" not in kopf:
        stueck = so.recv(1)
        if not stueck:
            break
        kopf += stueck
    text = kopf.decode("latin-1")
    try:
        status = int(text.split(" ", 2)[1])
    except (IndexError, ValueError):
        status = 0
    if status != 101:
        so.close()
        return status, None
    erwartet = base64.b64encode(hashlib.sha1((schluessel + GUID).encode()).digest()).decode()
    ok("sec-websocket-accept: " + erwartet.lower() in text.lower(), "Sec-WebSocket-Accept stimmt")
    return status, so


def senden(so, text, opcode=0x1):
    daten = text.encode()
    maske = os.urandom(4)
    so.sendall(bytes((0x80 | opcode, 0x80 | len(daten))) + maske + bytes(b ^ maske[i % 4] for i, b in enumerate(daten)))


def empfangen(so, sekunden=1.5):
    """Nächster Textrahmen vom Server oder None."""
    so.settimeout(sekunden)
    try:
        kopf = so.recv(2)
        if len(kopf) < 2:
            return None
        daten = so.recv(kopf[1] & 0x7F) if kopf[1] & 0x7F else b""
    except socket.timeout:
        return None
    if kopf[0] & 0x0F != 0x1:
        return None
    return daten.decode()


def config_setzen(cfg, an):
    with open(os.path.join(DIR, "config.example.json"), encoding="utf-8") as handle:
        daten = json.load(handle)
    daten["eingabe"] = {"websocket": an}
    with open(cfg, "w", encoding="utf-8") as handle:
        json.dump(daten, handle)


class Hausbesetzer(http.server.BaseHTTPRequestHandler):
    """Fremdes Konto auf dem Port: antwortet wie der Server, kennt aber das Geheimnis nicht."""
    def do_GET(self):
        roh = json.dumps({"ok": True, "beweis": "0" * 64}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def log_message(self, *a):
        pass


def pruefe_hausbesetzer(home):
    port = freier_port()
    fremd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Hausbesetzer)
    threading.Thread(target=fremd.serve_forever, daemon=True).start()
    try:
        sitzung.anlegen(port, home)
        ok(not sitzung.server_echt(port, home), "fremder Server ohne Geheimnis gilt nicht als echt")
        env = dict(os.environ, HOME=home)
        env.pop("XDG_RUNTIME_DIR", None)
        start = time.monotonic()
        lauf = subprocess.run(
            ["bash", "-c", 'source "$1/startlib.sh"; omaclusive_server_starten "$1" "$2"', "_", DIR, str(port)],
            env=env, capture_output=True, text=True, timeout=30)
        ok(lauf.returncode != 0, "Starter verweigert den fremd belegten Port: %s %s" % (lauf.returncode, lauf.stderr))
        ok(time.monotonic() - start < 15, "Starter gibt nach kurzer Zeit auf")
        log = os.path.join(sitzung.ordner(home), "server.log")
        ok(os.path.isfile(log) and modus(log) == 0o600, "server.log liegt privat im Sitzungsordner")
        ok(not sitzung.liegt_in(log, DIR), "server.log liegt nicht in der Web-Wurzel")
    finally:
        fremd.shutdown()
        fremd.server_close()


def pruefe_pflege_rechte(home):
    pflege.speichern(home, pflege.leer())
    ok(modus(str(pflege.datei(home))) == 0o600, "pflege.json ist 0600")


def main():
    port = freier_port()
    home = tempfile.mkdtemp(prefix="omaclusive-eingabe-")
    cfg = os.path.join(DIR, "config.json")
    sicher = None
    if os.path.exists(cfg):
        sicher = os.path.join(home, "config.original")
        shutil.copy(cfg, sicher)
    config_setzen(cfg, False)
    env = dict(os.environ, HOME=home, PORT=str(port))
    env.pop("XDG_RUNTIME_DIR", None)
    alt_xdg = os.environ.pop("XDG_RUNTIME_DIR", None)
    srv = subprocess.Popen([sys.executable, "server.py"], cwd=DIR, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lecks = []
    offen = []
    try:
        ok(sitzung.warte_auf_server(port, 10.0, home), "Server beweist das Geheimnis")
        geheim = sitzung.lesen(port, home)
        origin = "http://127.0.0.1:%d" % port

        # /api/bereit verrät das Geheimnis nicht
        st, roh = anfrage(port, "/api/bereit?probe=" + "a" * 20)
        antwort = json.loads(roh)
        ok(st == 200 and antwort.get("beweis") == sitzung.beweis(geheim, "a" * 20) and geheim not in roh, "Beweis passt")
        st, roh = anfrage(port, "/api/bereit?probe=kurz")
        ok(json.loads(roh).get("beweis") == "", "zu kurze Probe bekommt keinen Beweis")

        # Kanal aus (Standard): auch mit Geheimnis kein Handshake
        st, so = handshake(port, keks=geheim, origin=origin)
        ok(st == 404 and so is None, "Kanal aus: 404 (%s)" % st)
        st, so = handshake(port)
        ok(st == 403 and so is None, "ohne Geheimnis: 403 (%s)" % st)

        config_setzen(cfg, True)
        for beschreibung, kw in (
            ("ohne Geheimnis", {}),
            ("ohne Geheimnis mit Origin", {"origin": origin}),
            ("falsches Geheimnis", {"token": "x" * 43}),
            ("falscher Keks", {"keks": "y" * 43, "origin": origin}),
            ("fremde Herkunft", {"keks": geheim, "origin": "http://127.0.0.1:8765"}),
            ("fremde Seite", {"keks": geheim, "origin": "http://evil.example"}),
            ("fremder Host", {"token": geheim, "host": "evil.example:%d" % port}),
        ):
            st, so = handshake(port, **kw)
            ok(st == 403 and so is None, "%s: 403 (%s)" % (beschreibung, st))

        # Oberfläche (Browser: Keks und Origin) und Brücke (Kopfzeile, ohne Origin)
        st, oberflaeche = handshake(port, keks=geheim, origin=origin)
        ok(st == 101, "Oberfläche mit Geheimnis: 101 (%s)" % st)
        offen.append(oberflaeche)
        st, bruecke = handshake(port, token=geheim)
        ok(st == 101, "Brücke mit Geheimnis: 101 (%s)" % st)
        offen.append(bruecke)
        for wort in ("left", "right", "back", "hold"):
            senden(bruecke, wort)
            ok(empfangen(oberflaeche) == wort, "Oberfläche bekommt " + wort)
        senden(bruecke, "poweroff")
        senden(bruecke, "x" * 100)
        ok(empfangen(oberflaeche, 0.5) is None, "unbekannte Wörter gehen nicht weiter")
        senden(bruecke, "", opcode=0x9)
        bruecke.settimeout(2)
        pong = bruecke.recv(2)
        ok(pong[:1] == b"\x8a", "Ping bekommt Pong")

        # Reconnect: nach dem Schließen gilt wieder dieselbe Prüfung
        bruecke.close()
        offen.remove(bruecke)
        st, so = handshake(port)
        ok(st == 403 and so is None, "Reconnect ohne Geheimnis: 403")
        st, bruecke = handshake(port, token=geheim)
        ok(st == 101, "Reconnect mit Geheimnis: 101")
        offen.append(bruecke)
        senden(bruecke, "right")
        ok(empfangen(oberflaeche) == "right", "nach Reconnect kommt die Eingabe an")

        # Statisch: nichts Privates, keine Ordnerliste, kein Verweis nach draußen
        draussen = os.path.join(home, "draussen.txt")
        with open(draussen, "w", encoding="utf-8") as handle:
            handle.write("GEHEIM-draussen")
        pflanzen = {
            "server.log": "GEHEIM-serverlog",
            ".config-abc.tmp": "GEHEIM-tmp",
            "notiz.bak": "GEHEIM-bak",
            "stimme.onnx.teil": "GEHEIM-teil",
        }
        for name, inhalt in pflanzen.items():
            pfad = os.path.join(DIR, name)
            with open(pfad, "w", encoding="utf-8") as handle:
                handle.write(inhalt)
            lecks.append(pfad)
        link = os.path.join(DIR, "verweis-draussen.txt")
        os.symlink(draussen, link)
        lecks.append(link)
        for url, geheimtext in [("/" + n, i) for n, i in pflanzen.items()] + [
                ("/verweis-draussen.txt", "GEHEIM-draussen"), ("/.git/HEAD", "ref:")]:
            for tok in (None, geheim):
                st, roh = anfrage(port, url, tok)
                ok(st == 404 and geheimtext not in roh, "statisch gesperrt: %s (%s)" % (url, st))
        for url in ("/img/", "/locales/", "/"):
            st, roh = anfrage(port, url)
            ok("Directory listing" not in roh, "keine Ordnerliste: " + url)
        st, roh = anfrage(port, "/index.html")
        ok(st == 200 and "sitzung.js" in roh, "index.html bleibt erreichbar")
        st, _ = anfrage(port, "/img/glatt/sagen.svg")
        ok(st == 200, "Bilder bleiben erreichbar")
        ok(modus(cfg) == 0o600, "config.json wird beim Start 0600")
    finally:
        for so in offen:
            try:
                so.close()
            except OSError:
                pass
        for pfad in lecks:
            try:
                os.remove(pfad)
            except OSError:
                pass
        srv.terminate()
        try:
            srv.wait(5)
        except subprocess.TimeoutExpired:
            srv.kill()
        if sicher:
            shutil.copy(sicher, cfg)
        else:
            for pfad in (cfg, cfg + ".bak"):
                try:
                    os.remove(pfad)
                except OSError:
                    pass

    try:
        pruefe_hausbesetzer(home)
        pruefe_pflege_rechte(home)
    finally:
        if alt_xdg is not None:
            os.environ["XDG_RUNTIME_DIR"] = alt_xdg
        shutil.rmtree(home, ignore_errors=True)
    print("EINGABE_KANAL_OK")


if __name__ == "__main__":
    main()
