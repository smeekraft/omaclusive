#!/usr/bin/env python3
"""Prüft das Fernsehen: Senderliste, ruhiger mpv-Aufruf (ohne Bedienleiste und Texte),
Knöpfe in mpv (links Zurück, rechts Pause, beide 3 s halten, Sperrzeit, ein Knopf) und
das ruhige Aufgeben, wenn kein Bild kommt. Die mpv-Teile laufen nur, wenn mpv und ffmpeg da sind
(ohne Bildschirm: --vo=null --ao=null, Tasten über mpvs IPC-Befehle keydown/keyup)."""
import http.server, json, os, shutil, socket, subprocess, sys, tempfile, threading, time
import fernsehen

DIR = os.path.dirname(os.path.abspath(__file__))
fehler = []


def ok(bed, text):
    if not bed:
        fehler.append(text)
        print("FEHLER:", text)


# ---- Senderliste ----
cfg = {"fernsehen": {"sender": [
    {"name": "Das Erste", "stream": "https://example.org/a.m3u8"},
    {"name": "", "stream": "https://example.org/b.m3u8"},
    {"name": "Kaputt", "stream": "file:///etc/passwd"},
    {"name": "Aus", "stream": "https://example.org/c.m3u8", "aus": True},
    {"name": "hr\n", "bild": "../x.svg", "stream": "https://example.org/d.m3u8"},
    {"name": "YT", "bild": "img/radio.svg", "stream": "https://www.youtube.com/@x/live"},
] + [{"name": "S%d" % i, "stream": "https://example.org/%d" % i} for i in range(10)]}}
l = fernsehen.sender_liste(cfg)
ok([s["name"] for s in l][:3] == ["Das Erste", "hr", "YT"], "nur gültige Sender, Reihenfolge bleibt")
ok(len(l) == fernsehen.MAX_SENDER, "höchstens %d Sender" % fernsehen.MAX_SENDER)
ok(l[1]["bild"] == "img/fernsehen.svg" and l[2]["bild"] == "img/radio.svg", "Bild nur aus img/, sonst Fernseher")
ok(fernsehen.sender_liste({}) == [] and fernsehen.sender_liste({"fernsehen": {"sender": "x"}}) == [], "ohne Sender leer")
for f in ("config.example.json", "config.example.en.json"):
    with open(os.path.join(DIR, f), encoding="utf-8") as h:
        ok(len(fernsehen.sender_liste(json.load(h))) == 3, f + ": drei Beispielsender")

# ---- ruhiger Aufruf (Fotosensibilität, WCAG 2.3.1) ----
b = fernsehen.mpv_befehl("https://example.org/a.m3u8", DIR, {})
for opt in ("--osc=no", "--osd-level=0", "--no-osd-bar", "--input-default-bindings=no", "--no-config",
            "--load-scripts=no", "--sid=no", "--fs", "--cursor-autohide=always"):
    ok(opt in b, "mpv-Aufruf hat " + opt)
ok(b[-2:] == ["--", "https://example.org/a.m3u8"], "Adresse kommt nach --, nie als Option")
ok(os.path.isfile(os.path.join(DIR, "mpv", "omaclusive_tv.lua")), "mpv-Skript liegt bei")

# ---- Knöpfe ----
k = fernsehen.knopf_einstellungen({})
ok(k["links"] == ["LEFT", "MBTN_LEFT"] and k["rechts"] == ["RIGHT", "MBTN_RIGHT"], "zwei Knöpfe: Pfeile und Maustasten")
ok(k["halten"] == 3000 and k["entprell"] == 300 and k["warten"] == 30, "Standardzeiten 3 s, 300 ms, 30 s")
k = fernsehen.knopf_einstellungen({"knopf": {"modus": "ein"}, "keys": {"links": ["a"], "rechts": "ArrowRight", "waehlen": [" ", "Enter"]}})
ok(k["ein"] and k["rechts"] == [] and k["links"][:4] == ["a", "RIGHT", "SPACE", "ENTER"], "ein Knopf: alle Tasten sind der Knopf")
ok(fernsehen.mpv_taste("ArrowLeft") == "LEFT" and fernsehen.mpv_taste("x;quit") == "", "Tastennamen sicher übersetzt")
ok(fernsehen.ergebnis(0, False) == "" and fernsehen.ergebnis(3, False) == "fehler" and fernsehen.ergebnis(2, False) == "fehler"
   and fernsehen.ergebnis(-15, True) == "", "Ende: 0 normal, 2/3 Fehler, von Omaclusive beendet nie Fehler")

# ---- mpv echt (ohne Bildschirm) ----
if not (shutil.which("mpv") and shutil.which("ffmpeg")):
    print("HINWEIS: mpv oder ffmpeg fehlt, mpv-Teile übersprungen")
else:
    tmp = tempfile.mkdtemp()
    film = os.path.join(tmp, "test.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=160x90:r=10:d=120",
                    "-f", "lavfi", "-i", "anullsrc=r=8000:cl=mono", "-t", "120", "-shortest", film], check=True)

    def starte(ziel, config=None, warten=None):
        c = dict(config or {})
        if warten:
            c["fernsehen"] = {"wartenSekunden": warten}
        cmd = fernsehen.mpv_befehl(ziel, DIR, c)
        cmd = [x for x in cmd if x not in ("--fs", "--force-window=immediate")]
        sock = os.path.join(tmp, "ipc-%d" % time.time_ns())
        cmd[1:1] = ["--vo=null", "--ao=null", "--input-ipc-server=" + sock]
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if os.path.exists(sock):
                break
            time.sleep(0.05)
        time.sleep(0.8)
        return p, sock

    def befehl(sock, *args):
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(2)
        s.connect(sock)
        s.sendall((json.dumps({"command": list(args)}) + "\n").encode())
        antwort = b""
        while not antwort.endswith(b"\n"):
            teil = s.recv(4096)
            if not teil:
                break
            antwort += teil
        s.close()
        for zeile in antwort.decode().splitlines():
            d = json.loads(zeile)
            if "error" in d:
                return d
        return {}

    def ende(p, sek):
        try:
            return p.wait(timeout=sek)
        except subprocess.TimeoutExpired:
            return None

    def weg(p):
        if p.poll() is None:
            p.kill()
            p.wait()

    p, s = starte(film)
    befehl(s, "keydown", "LEFT"); befehl(s, "keyup", "LEFT")
    ok(ende(p, 3) == 0, "links = Zurück (mpv endet mit 0)")
    weg(p)

    p, s = starte(film)
    befehl(s, "keydown", "RIGHT"); befehl(s, "keyup", "RIGHT"); time.sleep(0.3)
    ok(befehl(s, "get_property", "pause").get("data") is True, "rechts = Pause")
    time.sleep(0.4)
    befehl(s, "keydown", "RIGHT"); befehl(s, "keyup", "RIGHT")
    befehl(s, "keydown", "RIGHT"); befehl(s, "keyup", "RIGHT"); time.sleep(0.4)
    ok(befehl(s, "get_property", "pause").get("data") is False, "rechts nochmal = Weiter, der zu schnelle Druck gleich danach zählt nicht")
    befehl(s, "keydown", "LEFT"); time.sleep(0.05); befehl(s, "keydown", "RIGHT"); time.sleep(1.2)
    befehl(s, "keyup", "RIGHT"); befehl(s, "keyup", "LEFT"); time.sleep(0.3)
    ok(p.poll() is None, "beide kurz (1 s) gehalten: nichts passiert, auch kein Zurück")
    time.sleep(0.4)
    befehl(s, "keydown", "LEFT"); time.sleep(0.1); befehl(s, "keydown", "RIGHT")
    ok(ende(p, 2.5) is None, "beide gehalten: vor 3 s noch kein Zurück")
    ok(ende(p, 2) == 0, "beide 3 s gehalten = Zurück")
    weg(p)

    p, s = starte(film)
    befehl(s, "keypress", "ESC")
    ok(ende(p, 3) == 0, "Esc = Zurück")
    weg(p)

    p, s = starte(film, {"knopf": {"modus": "ein"}})
    befehl(s, "keydown", "LEFT"); befehl(s, "keyup", "LEFT"); time.sleep(0.3)
    ok(befehl(s, "get_property", "pause").get("data") is True and p.poll() is None, "ein Knopf kurz = Pause")
    time.sleep(0.4)
    befehl(s, "keydown", "SPACE")
    ok(ende(p, 2.5) is None and ende(p, 2) == 0, "ein Knopf 3 s halten = Zurück")
    weg(p)

    p, s = starte(os.path.join(tmp, "gibt-es-nicht.m3u8"))
    rc = ende(p, 10)
    ok(rc not in (None, 0), "Stream geht nicht auf: mpv endet mit Fehler (%s)" % rc)
    ok(fernsehen.ergebnis(rc, False) == "fehler", "das wird als Fehler gemeldet")
    weg(p)

    # Ein Server, der antwortet, aber nie Bilder liefert: nach der Wartezeit ruhig aufgeben (Code 3)
    class Haengt(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
            self.end_headers()
            try:
                for _ in range(400):
                    self.wfile.write(b"\0")
                    self.wfile.flush()
                    time.sleep(0.1)
            except Exception:
                pass

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Haengt)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    t0 = time.time()
    p, s = starte("http://127.0.0.1:%d/live.ts" % srv.server_address[1], warten=10)
    rc = ende(p, 25)
    ok(rc is not None and rc != 0, "kein Bild: mpv gibt nach der Wartezeit auf (Code %s nach %.0f s)" % (rc, time.time() - t0))
    weg(p)
    srv.shutdown()
    shutil.rmtree(tmp, ignore_errors=True)

if fehler:
    sys.exit(1)
print("FERNSEHEN_OK")
