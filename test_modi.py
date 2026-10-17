#!/usr/bin/env python3
"""Tests für Modi, Pfad-Speicher und die Editor-API (echter Server auf 127.0.0.1, Wegwerf-HOME)."""
import copy
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import modi

DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("MODI_PORT", "8799"))


def ok(bedingung, text):
    if not bedingung:
        print("FEHLER:", text)
        sys.exit(1)


def laden(n):
    with open(os.path.join(DIR, n), encoding="utf-8") as h:
        return json.load(h)


# ---- modi.json ----
daten = laden("modi.json")
ok(daten["standard"] == "b", "Standard ist Modus b")
ok(sorted(daten["modi"]) == ["a", "b", "c"], "drei Modi")
for lang in ("de", "en"):
    zahlen = {}
    for k in "abc":
        v = modi.vorlage(k, lang)
        sauber, fehler, warn = modi.pruefe(v, max_ebenen=v["maxEbenen"])
        ok(not fehler and not warn, "Vorlage %s/%s gültig: %s %s" % (k, lang, fehler, warn))
        kart = sum(len(s["liste"]) for s in v["screens"].values())
        zahlen[k] = kart
        ok(sauber["screens"].keys() == v["screens"].keys(), "keine Ebene geht verloren")
    ok(zahlen["a"] <= 4, "Modus a hat höchstens 4 Karten insgesamt (%d)" % zahlen["a"])
    ok(zahlen["a"] < zahlen["b"] < zahlen["c"], "Modi steigen an: %s" % zahlen)
    va = modi.vorlage("a", lang)
    ok(list(va["screens"]) == ["start"], "Modus a: nur eine Ebene")
    ok(not any(k["aktion"]["typ"] == "untermenue" for k in va["screens"]["start"]["liste"]), "Modus a: kein Untermenü")
    ok(va["plugins"] is False and modi.vorlage("c", lang)["plugins"] is True and modi.vorlage("b", lang)["plugins"] is False, "Zusatzpaket nur in c")
    start_b = [k["wort"] for k in modi.vorlage("b", lang)["screens"]["start"]["liste"]]
    ok(len(start_b) == 6, "Modus b: sechs Bereiche (Sagen, Bilder, Filme, Radio, Aufgaben, Steuern)")
    typen_b = [k["aktion"]["typ"] for k in modi.vorlage("b", lang)["screens"]["start"]["liste"]]
    ok("radio" in typen_b and "aufgaben" in typen_b, "Modus b: Radio und Aufgaben als Hauptkacheln")
    ok(not any(k["aktion"]["typ"] in ("radio", "aufgaben") for k in va["screens"]["start"]["liste"]), "Modus a bleibt bei drei Karten")
ok(daten["modi"]["a"]["maxEbenen"] == 1 and daten["modi"]["b"]["maxEbenen"] == 2 and daten["modi"]["c"]["maxEbenen"] == 3, "Ebenen 1/2/3")
# Hilferuf in Modus a fragt vorher nach
ha = modi.vorlage("a", "de")["screens"]["start"]["liste"][0]
ok(ha["aktion"]["typ"] == "hilferuf" and ha.get("bestaetigen") is True, "Hilferuf in a mit Rückfrage")
# Modus c entspricht dem Baum in config.example (der Selbsttest nutzt ihn)
for lang, name in (("de", "config.example.json"), ("en", "config.example.en.json")):
    cfg = laden(name)
    ok(cfg["modus"] == "b" and cfg["einrichtung"].get("fertig") is not True, name + ": Standard b, nicht fertig")
    ok(cfg["screens"] == modi.vorlage("c", lang)["screens"], name + ": Baum gleicht Modus c")
    ok(cfg["knopf"]["modus"] == "zwei", name + ": Standard zwei Knöpfe")
    ok(not cfg.get("hoeren"), name + ": Mikrofon aus")
    ok(cfg["autostart"] is False, name + ": kein Autostart")

# ---- Prüfung ----
v = modi.vorlage("c", "de")
bad = copy.deepcopy(v); bad["screens"]["start"]["liste"][0]["aktion"] = {"typ": "shell", "cmd": "rm -rf /"}
ok(modi.pruefe(bad)[1], "unbekannte Aktion wird abgelehnt")
bad = copy.deepcopy(v); bad["screens"]["steuern"]["liste"][0]["aktion"]["ziel"] = "start"
ok(any("Kreis" in f for f in modi.pruefe(bad)[1]), "Kreis wird abgelehnt")
bad = copy.deepcopy(v); bad["screens"]["start"]["liste"][0]["aktion"]["ziel"] = "gibtsnicht"
ok(modi.pruefe(bad)[1], "fehlende Ebene wird abgelehnt")
bad = copy.deepcopy(v); bad["screens"]["../x"] = {"name": "x", "liste": []}
ok(modi.pruefe(bad)[1], "Ebenen-Name mit Pfad wird abgelehnt")
bad = copy.deepcopy(v); bad["screens"]["start"]["liste"][0]["bild"] = "../../etc/passwd"
ok(modi.pruefe(bad)[1], "Bild außerhalb wird abgelehnt")
bad = copy.deepcopy(v); bad["screens"]["start"]["liste"][0]["bild"] = "https://x/y.svg"
ok(modi.pruefe(bad)[1], "fremdes Bild wird abgelehnt")
bad = copy.deepcopy(v); bad["screens"]["start"]["liste"][0]["aktion"] = {"typ": "baustein", "name": "system.format"}
ok(modi.pruefe(bad)[1], "unbekannter Baustein wird abgelehnt")
bad = copy.deepcopy(v); bad["screens"]["start"]["liste"][0]["aktion"] = {"typ": "datei", "pfad": "/home/x/../../etc/passwd"}
ok(modi.pruefe(bad)[1], "Datei mit .. wird abgelehnt")
bad = copy.deepcopy(v); bad["screens"]["start"]["liste"][0]["aktion"] = {"typ": "link", "url": "javascript:alert(1)"}
ok(modi.pruefe(bad)[1], "javascript-Link wird abgelehnt")
gut = copy.deepcopy(v); gut["screens"]["start"]["liste"][0]["aktion"] = {"typ": "link", "url": "https://example.org/a"}
ok(not modi.pruefe(gut)[1], "https-Link erlaubt")
bad = copy.deepcopy(v)
for k in bad["screens"]["start"]["liste"]: k["aus"] = True
ok(modi.pruefe(bad)[1], "am Start muss eine Karte sichtbar bleiben")
bad = copy.deepcopy(v); bad["screens"]["start"]["liste"][0]["wort"] = "A\x00B"
ok(modi.pruefe(bad)[1], "Steuerzeichen werden abgelehnt")
zu_tief = {"start": "start", "screens": {}}
for i, n in enumerate(["start", "e1", "e2", "e3"]):
    nxt = ["e1", "e2", "e3", None][i]
    liste = [{"wort": "x", "bild": "img/ja.svg", "aktion": ({"typ": "untermenue", "ziel": nxt} if nxt else {"typ": "hilferuf"})}]
    zu_tief["screens"][n] = {"name": n, "liste": liste}
ok(any("tief" in f for f in modi.pruefe(zu_tief)[1]), "vier Ebenen sind zu tief")
extra = copy.deepcopy(v); extra["screens"]["start"]["liste"][0]["boese"] = "<script>"; extra["screens"]["start"]["liste"][0]["wort"] = " Hallo  Welt "
s, f, w = modi.pruefe(extra)
ok(not f and "boese" not in s["screens"]["start"]["liste"][0] and s["screens"]["start"]["liste"][0]["wort"] == "Hallo Welt", "nur bekannte Felder, Leerzeichen bereinigt")
waise = copy.deepcopy(v); waise["screens"]["lose"] = {"name": "Lose", "liste": []}
ok("lose" not in modi.pruefe(waise)[0]["screens"], "unerreichbare Ebene fällt weg")
ok(modi.pruefe(copy.deepcopy(modi.vorlage("a", "de")) | {"screens": {"start": {"name": "S", "liste": [dict(modi.vorlage("a", "de")["screens"]["start"]["liste"][1], aktion={"typ": "untermenue", "ziel": "x"})]},
   "x": {"name": "X", "liste": [dict(modi.vorlage("a", "de")["screens"]["start"]["liste"][1], aktion={"typ": "untermenue", "ziel": "y"})]},
   "y": {"name": "Y", "liste": [modi.vorlage("a", "de")["screens"]["start"]["liste"][0]]}}}, max_ebenen=1)[2], "Warnung bei mehr Ebenen als der Modus")

# ---- Speicher (Wegwerf-Verzeichnis) ----
basis = tempfile.mkdtemp(prefix="omaclusive-modi-")
cfg = {"language": "de", "modus": "b"}
ok(str(modi.datei(cfg, basis)) == os.path.join(basis, ".config", "omaclusive", "pfad-b.json"), "fester Pfad pro Modus")
ok(modi.wirksam(cfg, basis)["quelle"] == "vorlage", "ohne Datei gilt die Vorlage")
eigen = modi.vorlage("b", "de"); eigen["screens"]["start"]["liste"].reverse(); eigen["screens"]["start"]["liste"][0]["aus"] = True
r = modi.schreibe_pfad(cfg, eigen, basis)
ok(r["ok"] and os.path.isfile(r["datei"]), "Speichern legt die Datei an")
w = modi.wirksam(cfg, basis)
ok(w["quelle"] == "datei" and w["screens"]["start"]["liste"][0].get("aus") is True, "eigener Pfad gilt")
ok(modi.wirksam({"language": "de", "modus": "a"}, basis)["quelle"] == "vorlage", "anderer Modus hat eigene Datei")
ok(modi.dateiname({"modus": "b", "pfadDatei": "../../x.json"}) == "pfad-b.json", "pfadDatei mit Pfadteilen wird ignoriert")
ok(modi.dateiname({"modus": "b", "pfadDatei": "/etc/passwd"}) == "pfad-b.json", "absoluter pfadDatei wird ignoriert")
ok(modi.dateiname({"modus": "b", "pfadDatei": "meiner.json"}) == "meiner.json", "schlichter Dateiname erlaubt")
with open(r["datei"], "w") as h: h.write("{kaputt")
ok(modi.wirksam(cfg, basis)["quelle"] == "vorlage", "kaputte Datei: Vorlage")
ok(modi.zuruecksetzen(cfg, basis) is True and not os.path.exists(r["datei"]), "Zurücksetzen löscht die Datei")
ok(modi.zuruecksetzen(cfg, basis) is False, "Zurücksetzen ohne Datei ist harmlos")
ok(not [n for n in os.listdir(os.path.join(basis, ".config", "omaclusive")) if n.endswith(".tmp")], "keine Reste")
c2 = {"language": "de"}
ok(modi.modus_setzen(c2, "a") and c2["modus"] == "a" and c2["zurueck"]["sekunden"] == 45 and c2["knopf"]["scanMs"] == 4500, "Modus a setzt Zeiten")
ok(not modi.modus_setzen(c2, "zzz") and c2["modus"] == "a", "unbekannter Modus ändert nichts")
shutil.rmtree(basis)

# ---- Live-API ----
home = tempfile.mkdtemp(prefix="omaclusive-home-")
cfgp = os.path.join(DIR, "config.json")
ok(not os.path.exists(cfgp), "config.json darf vorher nicht da sein")
c = laden("config.example.json"); c["modus"] = "b"
with open(cfgp, "w", encoding="utf-8") as h: json.dump(c, h)
srv = subprocess.Popen([sys.executable, "server.py"], cwd=DIR, env=dict(os.environ, PORT=str(PORT), HOME=home), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    def req(methode, pfad, body=None, host=None, origin=None):
        for _ in range(60):
            try:
                con = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
                kopf = {"Host": host or "127.0.0.1:%d" % PORT}
                if origin: kopf["Origin"] = origin
                if body is not None: kopf["Content-Type"] = "application/json"
                con.request(methode, pfad, json.dumps(body) if body is not None else None, kopf)
                a = con.getresponse(); t = a.read().decode()
                return a.status, (json.loads(t) if t[:1] in "{[" else t)
            except (ConnectionRefusedError, OSError):
                time.sleep(0.15)
        raise SystemExit("Server antwortet nicht")
    st, p = req("GET", "/api/pfad")
    ok(st == 200 and p["ok"] and p["modus"] == "b" and p["quelle"] == "vorlage", "GET /api/pfad: Vorlage b")
    ok(p["datei"] == os.path.join(home, ".config", "omaclusive", "pfad-b.json"), "feste Datei wird angezeigt: " + p["datei"])
    ok(p["ordner"]["bilder"].startswith(home) and p["bibliothek"] and len(p["modi"]) == 3, "Ordner, Bibliothek, Modi da")
    ok(all("zurueckSekunden" in m and "scanMs" in m for m in p["modi"]), "Modi liefern Zeiten")
    st, m = req("GET", "/api/modi"); ok(st == 200 and m["modus"] == "b", "GET /api/modi")
    neu = {"start": p["start"], "plugins": False, "screens": copy.deepcopy(p["screens"])}
    neu["screens"]["start"]["liste"].reverse()
    st, r = req("POST", "/api/pfad", neu)
    ok(st == 200 and r["ok"] and r["quelle"] == "datei", "POST /api/pfad speichert: %s" % r)
    ok(os.path.isfile(p["datei"]), "Datei liegt im festen Pfad")
    st, p2 = req("GET", "/api/pfad")
    ok(p2["quelle"] == "datei" and p2["screens"]["start"]["liste"][0]["wort"] == neu["screens"]["start"]["liste"][0]["wort"], "Reihenfolge bleibt")
    # Validierung
    böse = copy.deepcopy(neu); böse["screens"]["start"]["liste"][0]["aktion"] = {"typ": "shell", "cmd": "x"}
    st, r = req("POST", "/api/pfad", böse); ok(st == 400 and not r["ok"] and r["fehler"], "ungültiger Pfad: 400")
    st, r = req("POST", "/api/pfad", {"screens": "x"}); ok(st == 400, "Müll: 400")
    # nur lokal
    st, r = req("POST", "/api/pfad", neu, host="evil.example:%d" % PORT); ok(st == 403, "fremder Host: 403")
    st, r = req("POST", "/api/pfad", neu, origin="http://evil.example"); ok(st == 403, "fremde Herkunft: 403")
    st, r = req("POST", "/api/pfad/zuruecksetzen", {}, host="evil.example"); ok(st == 403, "Zurücksetzen nur lokal")
    st, r = req("POST", "/api/modus", {"modus": "a"}, origin="http://evil.example"); ok(st == 403, "Modus nur lokal")
    st, r = req("POST", "/api/config", {"x": 1}, host="evil.example"); ok(st == 403, "Config nur lokal")
    ok(not os.path.exists(os.path.join(home, ".config", "omaclusive", "pfad-evil.json")), "nichts außerhalb geschrieben")
    # Modus wechseln
    st, r = req("POST", "/api/modus", {"modus": "zzz"}); ok(st == 400, "unbekannter Modus: 400")
    st, r = req("POST", "/api/modus", {"modus": "a"}); ok(st == 200 and r["ok"], "Modus a setzen")
    st, pa = req("GET", "/api/pfad")
    ok(pa["modus"] == "a" and pa["quelle"] == "vorlage" and list(pa["screens"]) == ["start"], "Modus a: eigener Pfad von b gilt nicht")
    with open(cfgp, encoding="utf-8") as h: gespeichert = json.load(h)
    ok(gespeichert["modus"] == "a" and gespeichert["zurueck"]["sekunden"] == 45, "Modus in config.json")
    st, r = req("POST", "/api/modus", {"modus": "b"}); ok(r["ok"], "zurück zu b")
    st, r = req("POST", "/api/pfad/zuruecksetzen", {}); ok(st == 200 and r["quelle"] == "vorlage", "Zurücksetzen: Vorlage")
    ok(not os.path.exists(p["datei"]), "Datei ist weg")
    # Zu große Anfrage
    con = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    con.request("POST", "/api/pfad", b"x" * 10, {"Host": "127.0.0.1:%d" % PORT, "Content-Length": "5000000", "Content-Type": "application/json"})
    try:
        a = con.getresponse(); ok(a.status == 400, "zu große Anfrage: 400")
    except Exception:
        pass
    # Dateien werden nicht aus dem Pfad-Ordner geliefert
    st, _ = req("GET", "/.config/omaclusive/pfad-b.json"); ok(st == 404, "Pfad-Datei wird nicht über HTTP ausgeliefert")
finally:
    srv.terminate()
    try: srv.wait(5)
    except Exception: srv.kill()
    for n in ("config.json", "config.json.bak"):
        try: os.remove(os.path.join(DIR, n))
        except OSError: pass
    shutil.rmtree(home, ignore_errors=True)
print("MODI_OK")
