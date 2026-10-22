#!/usr/bin/env python3
"""Lokaler Mini-Server fuer Omaclusive (nur 127.0.0.1, keine Cloud).
Liefert die App aus. Standardport 8795."""
import http.server, json, os, re, datetime, subprocess, shutil, urllib.parse, signal, threading
import hilferuf, sitzung
from i18n import tr
DIR = os.path.dirname(os.path.abspath(__file__)); CFG = os.path.join(DIR, "config.json")
_cfg_lock = threading.Lock()
VPROF = os.path.expanduser("~/.local/share/omaclusive/video-profil")
CHILD = []
_film = {"proc": None}
_tv = {"proc": None, "gestoppt": False}
def browser(): return shutil.which("chromium") or shutil.which("google-chrome") or "chromium"
def launch(kind, target):
    back()
    if kind == "url":
        cmd = [browser(), "--user-data-dir=" + VPROF, "--app=" + target, "--start-fullscreen", "--autoplay-policy=no-user-gesture-required"]
    elif shutil.which("mpv") and os.path.isfile(target):
        cmd = ["mpv", "--fs", target]
    else:
        cmd = ["xdg-open", target]
    CHILD.append(subprocess.Popen(cmd, start_new_session=True))
def back():
    _tv["gestoppt"] = True
    for c in CHILD:
        try: os.killpg(c.pid, signal.SIGTERM)
        except Exception: pass
    CHILD.clear()
    subprocess.run(["pkill", "-f", "user-data-dir=" + VPROF])
def pick(folder):
    if shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", "--title=" + tr("Wo willst du hin?")] + (["--directory"] if folder else [])
    elif shutil.which("kdialog"):
        cmd = ["kdialog", "--getexistingdirectory" if folder else "--getopenfilename", os.path.expanduser("~")]
    else:
        return None
    r = subprocess.run(cmd, capture_output=True, text=True); return r.stdout.strip() or None
def _lade_config():
    try:
        with open(CFG, encoding="utf-8") as handle:
            daten = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return daten if isinstance(daten, dict) else {}
def _schreibe_config(daten):
    if os.path.exists(CFG): shutil.copy(CFG, CFG + ".bak")
    hilferuf.schreibe_atomar(CFG, daten)
def _config_aendern(fn):
    with _cfg_lock:
        config = _lade_config()
        if fn(config): _schreibe_config(config)
        return config
def _config_aendern_fn(fn):
    return _config_aendern(fn)
def _bewahre_kanaele(neu, alt):
    if not isinstance(neu, dict): return
    alt_h = alt.get("hilferuf") if isinstance(alt, dict) and isinstance(alt.get("hilferuf"), dict) else {}
    if not isinstance(neu.get("hilferuf"), dict):
        if alt_h: neu["hilferuf"] = dict(alt_h)
        return
    neu_h = neu["hilferuf"]
    kanal, antwort = str(neu_h.get("kanal") or ""), str(neu_h.get("antwort") or "")
    kanal_alt, antwort_alt = str(alt_h.get("kanal") or ""), str(alt_h.get("antwort") or "")
    alt_ok = hilferuf.gueltiger_kanal(kanal_alt) and hilferuf.gueltiger_kanal(antwort_alt) and kanal_alt != antwort_alt
    neu_ok = hilferuf.gueltiger_kanal(kanal) and hilferuf.gueltiger_kanal(antwort) and kanal != antwort
    if alt_ok and not neu_ok:
        neu_h["kanal"] = kanal_alt
        neu_h["antwort"] = antwort_alt
        if not str(neu_h.get("letzterTest") or "").strip():
            neu_h["letzterTest"] = str(alt_h.get("letzterTest") or "")
def _kanaele_sicher():
    return _config_aendern(lambda config: hilferuf.sicherstellen(config, hilferuf.heute()))
def _hilferuf_lokal(daten):
    ergebnis = {}
    def tun(config):
        speichern, wert = hilferuf.auftrag(config, daten)
        if isinstance(wert, dict): ergebnis.update(wert)
        return speichern
    _config_aendern(tun)
    return ergebnis
def _test_senden(config):
    ergebnis = hilferuf.sende(config, "test")
    ergebnis["faellig"] = True
    if ergebnis.get("ok"):
        tag = hilferuf.heute().isoformat()
        def setzen(aktuell):
            hilferuf.sicherstellen(aktuell, hilferuf.heute())
            aktuell["hilferuf"]["letzterTest"] = tag
            return True
        _config_aendern(setzen)
    return ergebnis
def _hilferuf_auftrag(daten):
    daten = daten if isinstance(daten, dict) else {}
    art = str(daten.get("art") or "zustand")
    if art in ("zustand", "speichern", "neu"): return _hilferuf_lokal(daten)
    config = _kanaele_sicher()
    if art == "test" and daten.get("nurWennFaellig") and not hilferuf.test_faellig(config.get("hilferuf"), hilferuf.heute()):
        return {"ok": True, "faellig": False}
    if art == "test": return _test_senden(config)
    return hilferuf.sende(config, "ruf")
def _gesehen(seit):
    return hilferuf.frage_gesehen(_kanaele_sicher(), seit)
PORT = int(os.environ.get("PORT", 8795))
SESSION = ""
def _hosts():
    return {"127.0.0.1:%d" % PORT, "localhost:%d" % PORT}
def _cookie(h, name):
    for teil in str(h.headers.get("Cookie") or "").split(";"):
        teil = teil.strip()
        if "=" not in teil: continue
        key, wert = teil.split("=", 1)
        if key.strip() == name: return wert.strip()
    return ""
def _herkunft_ok(h, nur_host=False):
    """Host muss dieser Rechner sein. Origin, Referer und Sec-Fetch-Site, falls gesetzt, auch.
    nur_host gilt für die einmalige Übergabe aus der lokalen Startdatei (die kommt von file://)."""
    if str(h.headers.get("Host") or "").lower() not in _hosts(): return False
    if nur_host: return True
    origins = {"http://" + e for e in _hosts()}
    origin = str(h.headers.get("Origin") or "")
    if origin and origin.lower() not in origins: return False
    referer = str(h.headers.get("Referer") or "")
    if referer:
        u = urllib.parse.urlparse(referer)
        if (u.scheme or "").lower() != "http" or (u.hostname or "").lower() not in {"127.0.0.1", "localhost"}: return False
        if (u.port or 80) != PORT: return False
    site = str(h.headers.get("Sec-Fetch-Site") or "").lower()
    if site and site not in ("same-origin", "none"): return False
    return True
def _token_ok(h):
    """Kopfzeile oder Cookie. Der Abfrage-Parameter gilt nicht: der stünde in Referer und Verläufen."""
    got = str(h.headers.get("X-Omaclusive-Token") or "") or _cookie(h, "omaclusive")
    return sitzung.gleich(got, SESSION)
def _zugang(h):
    if _herkunft_ok(h) and _token_ok(h): return True
    h.j({"ok": False}, 403)
    return False
def _sende_config(s):
    if not os.path.isfile(CFG): return s.j({"ok": False}, 404)
    try:
        with open(CFG, "rb") as handle: daten = handle.read()
    except OSError:
        return s.j({"ok": False}, 404)
    return s.roh(daten, "application/json; charset=utf-8")
def _sitzung_uebergeben(s, q):
    """Einmaliger Wechsel: richtiges Geheimnis setzt das Cookie und leitet auf die Seite um, ohne das Geheimnis in der neuen Adresse."""
    if not _herkunft_ok(s, nur_host=True) or not sitzung.gleich((q.get("k") or [""])[0], SESSION):
        return s.j({"ok": False}, 403)
    ziel = sitzung.sichere_seite((q.get("next") or ["/"])[0])
    s.send_response(303)
    s.send_header("Location", ziel)
    s.send_header("Set-Cookie", "omaclusive=%s; HttpOnly; SameSite=Lax; Path=/" % SESSION)
    s.end_headers()
def _autostart_in_config(an):
    """Das Feld "autostart" der Config folgt dem Zustand der Datei. Schreibt nur bei Abweichung und nur, wenn es eine Config gibt."""
    if not os.path.exists(CFG): return
    def setzen(config):
        if config.get("autostart") is an: return False
        config["autostart"] = an
        return True
    _config_aendern(setzen)
def _pfad_antwort():
    import modi
    config = _lade_config()
    w = modi.wirksam(config)
    lang = modi.sprache(config)
    v = modi.vorlage(w["modus"], lang)
    return {"ok": True, "modus": w["modus"], "quelle": w["quelle"], "datei": str(modi.datei(config)),
            "ordner": modi.ordner_info(), "start": w["start"], "plugins": w["plugins"], "maxEbenen": w["maxEbenen"],
            "screens": w["screens"], "vorlage": {"start": v["start"], "plugins": v["plugins"], "screens": v["screens"]},
            "bibliothek": modi.bibliothek(lang), "modi": modi.modus_liste(config), "sprache": lang}
def _plugin_wurzel():
    return os.path.join(os.path.expanduser("~"), ".config", "omaclusive", "plugins")
def _film_starten(name):
    import praxis
    if not shutil.which("mpv"):
        return {"ok": False, "grund": "mpv"}
    pfad = praxis.datei_im_ordner("filme", str(name or ""))
    if pfad is None:
        return {"ok": False, "grund": "datei"}
    back()
    befehl = ["mpv", "--fs", "--really-quiet", "--no-terminal", str(pfad)]
    proc = subprocess.Popen(befehl, start_new_session=True)
    CHILD.append(proc)
    _film["proc"] = proc
    return {"ok": True}
def _tv_starten(nr):
    """Startet Sender Nummer nr aus config.json im Vollbild (mpv). Die Adresse kommt nie von der Oberfläche."""
    import fernsehen
    config = _lade_config()
    liste = fernsehen.sender_liste(config)
    if not isinstance(nr, int) or isinstance(nr, bool) or not 0 <= nr < len(liste):
        return {"ok": False, "grund": "sender"}
    if not fernsehen.bereit():
        return {"ok": False, "grund": "mpv"}
    back()
    try:
        proc = subprocess.Popen(fernsehen.mpv_befehl(liste[nr]["stream"], DIR, config), start_new_session=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return {"ok": False, "grund": "mpv"}
    CHILD.append(proc)
    _tv.update(proc=proc, gestoppt=False)
    return {"ok": True}
def _tv_stand():
    import fernsehen
    proc = _tv.get("proc")
    if not proc:
        return {"ok": True, "laeuft": False, "fehler": ""}
    rc = proc.poll()
    if rc is None:
        return {"ok": True, "laeuft": True, "fehler": ""}
    return {"ok": True, "laeuft": False, "fehler": fernsehen.ergebnis(rc, _tv.get("gestoppt"))}
def _film_stand():
    proc = _film.get("proc")
    return {"ok": True, "laeuft": bool(proc) and proc.poll() is None}
def _ordner_liste(quelle):
    import praxis
    if quelle not in ("bilder", "filme"):
        return None
    try:
        praxis.anlegen(quelle)
        return praxis.karten(quelle)
    except OSError:
        return []
_pflege_lock = threading.Lock()
def _heim(): return os.path.expanduser("~")
def _pflege_aendern(fn):
    """Lädt die Pflege-Daten, ruft fn(daten) auf und speichert, wenn fn True liefert."""
    import pflege
    with _pflege_lock:
        daten = pflege.laden(_heim())
        ergebnis = fn(daten)
        if ergebnis: pflege.speichern(_heim(), daten)
        return daten, ergebnis
def _sende_bereich(s, pfad):
    """Film mit Range-Unterstützung (Spulen im Browser). Nur Dateien, die praxis.datei_im_ordner geliefert hat."""
    typen = {".mp4": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg", ".mkv": "video/x-matroska", ".mov": "video/quicktime"}
    groesse = pfad.stat().st_size
    start, ende, code = 0, groesse - 1, 200
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", s.headers.get("Range") or "")
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            if m.group(2): ende = min(int(m.group(2)), groesse - 1)
        else:
            start = max(0, groesse - int(m.group(2)))
        if start > ende or start >= groesse:
            s.send_response(416); s.send_header("Content-Range", "bytes */%d" % groesse); s.send_header("Content-Length", "0"); s.end_headers(); return
        code = 206
    s.send_response(code)
    s.send_header("Content-Type", typen.get(pfad.suffix.lower(), "application/octet-stream"))
    s.send_header("Accept-Ranges", "bytes")
    s.send_header("Content-Length", str(ende - start + 1))
    if code == 206: s.send_header("Content-Range", "bytes %d-%d/%d" % (start, ende, groesse))
    s.send_header("Cache-Control", "no-store")
    s.end_headers()
    try:
        with open(pfad, "rb") as handle:
            handle.seek(start)
            rest = ende - start + 1
            while rest > 0:
                block = handle.read(min(65536, rest))
                if not block: break
                s.wfile.write(block); rest -= len(block)
    except (BrokenPipeError, ConnectionResetError):
        pass
def _sende_datei(s, pfad):
    typen = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
    }
    daten = pfad.read_bytes()
    s.roh(daten, typen.get(pfad.suffix.lower(), "application/octet-stream"))
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=DIR, **k)
    def translate_path(s, path):
        # Bildsatz: /img/x.svg und /plugins/<id>/x.svg kommen aus dem Ordner glatt/ oder pixel/
        # (config.json "bildstil", Standard glatt). Fehlt die Datei dort, gilt der alte Pfad.
        import praxis, re as _re
        roh = urllib.parse.unquote(urllib.parse.urlparse(path).path)
        m = _re.fullmatch(r"/(img|plugins/[a-z0-9_-]{1,40})/([A-Za-z0-9_.-]+\.svg)", roh)
        if m:
            ziel = praxis.bild_im_stil(os.path.join(DIR, m.group(1)), m.group(2), _lade_config().get("bildstil"))
            if ziel is not None:
                return str(ziel)
        return super().translate_path(path)
    def end_headers(s):
        s.send_header("Cache-Control", "no-store")
        s.send_header("Referrer-Policy", "no-referrer")
        s.send_header("X-Content-Type-Options", "nosniff")
        s.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        s.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()
    def j(s, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        s.send_response(code); s.send_header("Content-Type", "application/json; charset=utf-8")
        s.send_header("Content-Length", str(len(b))); s.end_headers(); s.wfile.write(b)
    def roh(s, daten, typ, code=200):
        s.send_response(code)
        s.send_header("Content-Type", typ)
        s.send_header("Content-Length", str(len(daten)))
        s.end_headers()
        s.wfile.write(daten)
    def body(s):
        n = int(s.headers.get("Content-Length") or 0)
        if not n: return {}
        if n > 1000000: return None
        try: return json.loads(s.rfile.read(n).decode())
        except Exception: return None
    def do_GET(s):
        u = urllib.parse.urlparse(s.path); q = urllib.parse.parse_qs(u.query)
        if u.path == "/api/bereit":
            if not _herkunft_ok(s): return s.j({"ok": False}, 403)
            return s.j({"ok": True})
        if u.path == "/api/sitzung": return _sitzung_uebergeben(s, q)
        if u.path.startswith("/api/") or u.path in ("/config.json", "/config.json.bak"):
            if not _zugang(s): return
        if u.path == "/config.json.bak": return s.j({"ok": False}, 404)
        if u.path == "/config.json": return _sende_config(s)
        # Aktionen nur per POST. GET bleibt lesend, auch mit gültiger Sitzung.
        if u.path in ("/api/open", "/api/back", "/api/pick", "/api/hinweis", "/api/baustein"):
            return s.j({"ok": False}, 405)
        if u.path == "/api/stimmen":
            import stimmen
            config = _lade_config(); aktiv = stimmen.aktive_id(config)
            return s.j({"aktiv": aktiv, "job": stimmen.status(), "stimmen": [
                {"id": v["id"], "sprache": v["sprache"], "name": v["name"], "info": v.get("info", ""), "mb": v.get("mb", 0),
                 "da": stimmen.da(v), "aktiv": v["id"] == aktiv} for v in stimmen.liste()]})
        if u.path == "/api/bausteine":
            import bausteine
            return s.j({"bausteine": bausteine.catalog(), "sprache": bausteine.engine(), "wlan": bausteine.wifi_backend()})
        if u.path == "/api/liste":
            import bausteine
            quelle = q.get("quelle", [""])[0]
            if quelle not in ("wlan.list", "bt.list"):
                return s.j({"ok": False, "liste": []}, 404)
            return s.j({"ok": True, "quelle": quelle, "liste": bausteine.liste(quelle)})
        if u.path == "/api/hilferuf":
            return s.j(_hilferuf_lokal({"art": "zustand"}))
        if u.path == "/api/hilferuf/gesehen":
            return s.j(_gesehen(q.get("since", ["0"])[0]))
        if u.path == "/api/ordner":
            quelle = q.get("quelle", [""])[0]
            liste = _ordner_liste(quelle)
            if liste is None:
                return s.j({"ok": False, "liste": []}, 404)
            return s.j({"ok": True, "quelle": quelle, "liste": liste})
        if u.path == "/api/datei":
            import praxis
            quelle = q.get("quelle", [""])[0]
            name = q.get("name", [""])[0]
            pfad = praxis.datei_im_ordner(quelle, name) if quelle in ("bilder", "filme") else None
            if pfad is None:
                return s.j({"ok": False}, 404)
            return _sende_datei(s, pfad)
        if u.path == "/api/blatt":
            import praxis
            pdf = praxis.blatt_pdf(DIR)
            return s.roh(pdf, "application/pdf")
        if u.path == "/api/plugins":
            import praxis
            return s.j(praxis.plugins_lesen(_plugin_wurzel()))
        if u.path == "/api/plugin-bild":
            import praxis
            pfad = praxis.plugin_datei(_plugin_wurzel(), q.get("id", [""])[0], q.get("datei", [""])[0], _lade_config().get("bildstil"))
            if pfad is None:
                return s.j({"ok": False}, 404)
            return _sende_datei(s, pfad)
        if u.path == "/api/autostart":
            import praxis
            an = praxis.autostart_aktiv(os.path.expanduser("~"))
            _autostart_in_config(an)
            return s.j({"ok": True, "an": an})
        if u.path == "/api/medium":
            import praxis
            pfad = praxis.datei_im_ordner("filme", q.get("name", [""])[0])
            if pfad is None: return s.j({"ok": False}, 404)
            return _sende_bereich(s, pfad)
        if u.path in ("/api/erinnerung", "/api/aufgaben", "/api/pflege"):
            import pflege
            with _pflege_lock: daten = pflege.laden(_heim())
            if u.path == "/api/erinnerung":
                return s.j({"ok": True, "faellig": pflege.faellig(daten, datetime.datetime.now())[:1]})
            if u.path == "/api/aufgaben":
                return s.j({"ok": True, "offen": pflege.offene_aufgaben(daten)})
            return s.j({"ok": True, "erinnerungen": daten["erinnerungen"], "aufgaben": daten["aufgaben"]})
        if u.path == "/api/film":
            return s.j(_film_stand())
        if u.path == "/api/fernsehen":
            return s.j(_tv_stand())
        if u.path == "/api/pfad":
            return s.j(_pfad_antwort())
        if u.path == "/api/modi":
            import modi
            c = _lade_config()
            return s.j({"ok": True, "modus": modi.modus_id(c), "modi": modi.modus_liste(c)})
        return super().do_GET()
    def do_POST(s):
        if not _zugang(s): return
        data = s.body()
        if data is None: return s.j({"ok": False}, 400)
        if not isinstance(data, dict): return s.j({"ok": False}, 400)
        pfad = urllib.parse.urlparse(s.path).path
        if pfad == "/api/back":
            back(); return s.j({"ok": True})
        if pfad == "/api/hinweis":
            import bausteine
            return s.j({"ok": bool(bausteine.hinweis_ton())})
        if pfad == "/api/pick":
            return s.j({"path": pick(data.get("folder") is True)})
        if pfad == "/api/open":
            url = data.get("url")
            if url is not None:
                url = str(url)
                if not re.match(r"https?://", url, re.I): return s.j({"ok": False}, 400)
                launch("url", url); return s.j({"ok": True})
            p = str(data.get("path") or "")
            if p and os.path.exists(p): launch("file", p); return s.j({"ok": True})
            return s.j({"ok": False}, 404)
        if pfad == "/api/hilferuf":
            if not isinstance(data, dict): return s.j({"ok": False}, 400)
            return s.j(_hilferuf_auftrag(data))
        if pfad == "/api/film":
            if not isinstance(data, dict): return s.j({"ok": False}, 400)
            return s.j(_film_starten(data.get("name", "")))
        if pfad == "/api/sprache":
            if not isinstance(data, dict) or not isinstance(data.get("id"), str): return s.j({"ok": False}, 400)
            import stimmen
            ok, grund = stimmen.starten(data["id"], _config_aendern_fn)
            return s.j({"ok": ok, "grund": grund}, 200 if ok else (409 if grund == "laeuft" else 400))
        if pfad == "/api/autostart":
            if not isinstance(data, dict) or not isinstance(data.get("an"), bool): return s.j({"ok": False}, 400)
            import praxis
            an = praxis.autostart_setzen(os.path.expanduser("~"), os.path.join(DIR, "start-talker.sh"), data["an"])
            _autostart_in_config(an)
            return s.j({"ok": True, "an": an})
        if pfad in ("/api/erinnerung/bestaetigen", "/api/aufgaben/abhaken", "/api/pflege"):
            if not isinstance(data, dict): return s.j({"ok": False}, 400)
            import pflege
            if pfad == "/api/pflege":
                sauber, fehler = pflege.bereinige(data)
                if fehler: return s.j({"ok": False, "fehler": fehler}, 400)
                with _pflege_lock:
                    alt = pflege.laden(_heim())
                    sauber["bestaetigt"] = {k: v for k, v in alt["bestaetigt"].items() if k in {e["id"] for e in sauber["erinnerungen"]}}
                    pflege.speichern(_heim(), sauber)
                return s.j({"ok": True})
            eid = data.get("id")
            if not isinstance(eid, str): return s.j({"ok": False}, 400)
            if pfad == "/api/erinnerung/bestaetigen":
                _, ok = _pflege_aendern(lambda d: pflege.bestaetigen(d, eid, datetime.datetime.now()))
            else:
                _, ok = _pflege_aendern(lambda d: pflege.abhaken(d, eid))
            return s.j({"ok": bool(ok)}, 200 if ok else 404)
        if pfad in ("/api/pfad", "/api/pfad/zuruecksetzen", "/api/modus"):
            if not isinstance(data, dict): return s.j({"ok": False}, 400)
            import modi
            if pfad == "/api/modus":
                ergebnis = {}
                def setzen(config):
                    ergebnis["ok"] = modi.modus_setzen(config, str(data.get("modus") or ""))
                    return ergebnis["ok"]
                _config_aendern(setzen)
                return s.j({"ok": bool(ergebnis.get("ok"))}, 200 if ergebnis.get("ok") else 400)
            if pfad == "/api/pfad/zuruecksetzen":
                with _cfg_lock: modi.zuruecksetzen(_lade_config())
                return s.j(_pfad_antwort())
            with _cfg_lock:
                ergebnis = modi.schreibe_pfad(_lade_config(), data)
            if not ergebnis.get("ok"): return s.j(ergebnis, 400)
            ergebnis.update({k: v for k, v in _pfad_antwort().items() if k in ("quelle", "screens", "start", "plugins")})
            return s.j(ergebnis)
        if s.path == "/api/config":
            if not isinstance(data, dict): return s.j({"ok": False}, 400)
            with _cfg_lock:
                _bewahre_kanaele(data, _lade_config())
                import praxis
                data["autostart"] = praxis.autostart_aktiv(os.path.expanduser("~"))
                _schreibe_config(data)
            return s.j({"ok": True})
        if s.path == "/api/baustein":
            # confirm ist nur die Rückfrage auf dem Bildschirm, kein Passwort.
            # Ohne Sitzungsgeheimnis (_zugang) endet der Aufruf vorher mit 403.
            import bausteine
            return s.j(bausteine.execute(data.get("name", ""), bool(data.get("confirm")), data))
        if s.path == "/api/fernsehen":
            return s.j(_tv_starten(data.get("nr")))
        if s.path == "/api/say":
            import bausteine
            texte = data.get("texte")
            nr = data.get("nr") if isinstance(data.get("nr"), int) and not isinstance(data.get("nr"), bool) else None
            if isinstance(texte, list):
                return s.j({"ok": bausteine.speak([str(t) for t in texte], data.get("stimme") or "", nr)})
            return s.j({"ok": bausteine.speak(data.get("text", ""), data.get("stimme") or "", nr)})
        if s.path == "/api/hoeren":
            if _lade_config().get("hoeren") is not True:
                return s.j({"ok": False, "grund": "aus", "text": ""})
            import ohr
            woerter = data.get("woerter") or []
            if not isinstance(woerter, list):
                return s.j({"ok": False, "grund": "fehler", "text": ""})
            return s.j(ohr.hoeren([str(w) for w in woerter[:8]]))
        return s.j({"ok": False}, 404)
    def log_message(s, *a): pass
def _ohr_laden():
    try:
        if _lade_config().get("hoeren") is not True:
            return  # Mikrofon standardmäßig aus: kein Modell laden, nichts aufnehmen
        import ohr
        ohr.laden()
    except Exception:
        pass
def _sprache_vorab():
    try:
        import bausteine
        config = {}
        if os.path.isfile(CFG):
            with open(CFG, encoding="utf-8") as handle:
                config = json.load(handle)
        stimme = config.get("stimme") or "piper"
        bausteine.sprache_vorab(bausteine.texte_aus_config(config), stimme)
    except Exception:
        pass

def _hilferuf_bereit():
    try: _kanaele_sicher()
    except Exception: pass
threading.Thread(target=_ohr_laden, daemon=True).start()
threading.Thread(target=_sprache_vorab, daemon=True).start()
threading.Thread(target=_hilferuf_bereit, daemon=True).start()
SESSION = sitzung.anlegen(PORT)
for _privat in (CFG, CFG + ".bak"):
    try:
        if os.path.isfile(_privat) and not os.path.islink(_privat): os.chmod(_privat, 0o600)
    except OSError:
        pass
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
