#!/usr/bin/env python3
"""Drei Modi (feste Pfade) und der Pfad-Speicher für den Editor. Kein Netz, kein Server.
Three modes (fixed paths) and the path store for the editor. No network, no server.

Modus a = ganz einfach, b = einfach (Standard), c = mehr Auswahl. Die Vorlagen stehen in modi.json.
Der eigene Pfad der Angehörigen liegt in einer festen Datei: ~/.config/omaclusive/pfad-<modus>.json
(oder, wenn config.json "pfadDatei" als schlichten Dateinamen enthält, dort). Nichts außerhalb
dieses Ordners wird gelesen oder geschrieben. Tests übergeben ein eigenes Verzeichnis als "basis".
"""
import copy
import json
import os
import re
import tempfile
from pathlib import Path

DIR = os.path.dirname(os.path.abspath(__file__))
MAX_TIEFE = 3
MAX_SCREENS = 30
MAX_KARTEN = 30
MAX_BYTES = 200 * 1024
_RE_ID = re.compile(r"^[a-z0-9_-]{1,40}$")
_RE_DATEI = re.compile(r"^[A-Za-z0-9_-]{1,40}\.json$")
_RE_BILD = re.compile(r"^(img/[A-Za-z0-9_.-]{1,60}\.svg|plugins/[a-z0-9_-]{1,40}/[A-Za-z0-9_.-]{1,60}\.svg)$")
_RE_STEUER = re.compile(r"[\x00-\x1f\x7f]")
_VERBOTEN_PRAEFIX = ("plugin-", "ordner-", "dyn-")
_AKTIONEN = ("untermenue", "ordner", "hilferuf", "baustein", "sprechen", "dynamisch", "link", "datei", "radio", "aufgaben")
_RE_URL = re.compile(r"^https?://[^\s\x00-\x1f]{1,480}$")
_QUELLEN_ORDNER = ("bilder", "filme")
_QUELLEN_LISTE = ("wlan.list", "bt.list")
_cache = {"mtime": None, "daten": None}


def laden():
    """modi.json lesen (mit kleinem Zwischenspeicher)."""
    pfad = os.path.join(DIR, "modi.json")
    mtime = os.path.getmtime(pfad)
    if _cache["mtime"] != mtime:
        with open(pfad, encoding="utf-8") as handle:
            _cache.update(mtime=mtime, daten=json.load(handle))
    return _cache["daten"]


def sprache(config):
    code = str((config or {}).get("language") or "de").strip().lower().split("-")[0].split("_")[0]
    return code if code in ("de", "en") else "en"


def modus_id(config):
    daten = laden()
    wert = str((config or {}).get("modus") or "").strip().lower()
    return wert if wert in daten["modi"] else daten["standard"]


def modus_liste(config):
    lang = sprache(config)
    return [{"id": k, "name": v["name"][lang], "beschreibung": v["beschreibung"][lang],
             "maxEbenen": v["maxEbenen"], "plugins": v["plugins"],
             "zurueckSekunden": v["zurueckSekunden"], "scanMs": v["scanMs"]}
            for k, v in sorted(laden()["modi"].items())]


def vorlage(modus, lang):
    """Die Vorlage eines Modus in einer Sprache (Kopie, darf verändert werden)."""
    m = laden()["modi"][modus]
    return {"modus": modus, "start": m["start"], "plugins": bool(m["plugins"]),
            "maxEbenen": m["maxEbenen"], "screens": copy.deepcopy(m["screens"][lang])}


def modus_setzen(config, modus):
    """Setzt den Modus in einer Config (Dict) samt Zeiten. Gibt True zurück, wenn der Modus bekannt ist."""
    modi = laden()["modi"]
    if modus not in modi:
        return False
    m = modi[modus]
    config["modus"] = modus
    z = config.get("zurueck")
    if not isinstance(z, dict):
        z = config["zurueck"] = {}
    z["sekunden"] = m["zurueckSekunden"]
    z.setdefault("hinweis", "ansage")
    z["hinweisVorherSekunden"] = 5
    k = config.get("knopf")
    if not isinstance(k, dict):
        k = config["knopf"] = {"modus": "zwei"}
    k["scanMs"] = m["scanMs"]
    return True


# ---- fester Speicherort ----

def wurzel(basis=None):
    return Path(basis) if basis is not None else Path.home()


def ordner(basis=None):
    return wurzel(basis) / ".config" / "omaclusive"


def dateiname(config):
    name = (config or {}).get("pfadDatei")
    if isinstance(name, str) and _RE_DATEI.fullmatch(name):
        return name
    return "pfad-%s.json" % modus_id(config)


def datei(config, basis=None):
    return ordner(basis) / dateiname(config)


# ---- Prüfen und bereinigen ----

def _text(wert, grenze):
    t = re.sub(r"\s+", " ", str(wert if wert is not None else "")).strip()
    if _RE_STEUER.search(t):
        return None
    return t[:grenze]


def bekannte_bausteine():
    namen = set()
    for m in laden()["modi"].values():
        for screens in m["screens"].values():
            for s in screens.values():
                for k in s.get("liste", []):
                    a = k.get("aktion") or {}
                    if a.get("typ") == "baustein":
                        namen.add(a.get("name"))
    return namen


def _aktion(a, fehler, wo, bausteine):
    if not isinstance(a, dict) or a.get("typ") not in _AKTIONEN:
        fehler.append("%s: Aktion nicht erlaubt" % wo)
        return None
    typ = a["typ"]
    if typ == "untermenue":
        ziel = a.get("ziel")
        if not isinstance(ziel, str) or not _RE_ID.fullmatch(ziel) or ziel.startswith(_VERBOTEN_PRAEFIX):
            fehler.append("%s: Ziel ungültig" % wo)
            return None
        return {"typ": typ, "ziel": ziel}
    if typ == "ordner":
        q = a.get("quelle")
        if q not in _QUELLEN_ORDNER:
            fehler.append("%s: Ordner ungültig" % wo)
            return None
        return {"typ": typ, "quelle": q, "ziel": q}
    if typ in ("hilferuf", "radio", "aufgaben"):
        return {"typ": typ}
    if typ == "baustein":
        if a.get("name") not in bausteine:
            fehler.append("%s: Baustein nicht erlaubt" % wo)
            return None
        return {"typ": typ, "name": a["name"]}
    if typ == "sprechen":
        t = _text(a.get("text"), 200)
        if not t:
            fehler.append("%s: Text fehlt" % wo)
            return None
        return {"typ": typ, "text": t}
    if typ == "link":
        url = a.get("url")
        if not isinstance(url, str) or not _RE_URL.fullmatch(url):
            fehler.append("%s: Link ungültig" % wo)
            return None
        return {"typ": typ, "url": url}
    if typ == "datei":
        pf = a.get("pfad")
        if (not isinstance(pf, str) or not pf.startswith("/") or len(pf) > 500 or _RE_STEUER.search(pf)
                or ".." in pf.split("/")):
            fehler.append("%s: Datei ungültig" % wo)
            return None
        return {"typ": typ, "pfad": pf}
    q = a.get("quelle")
    if q not in _QUELLEN_LISTE:
        fehler.append("%s: Liste ungültig" % wo)
        return None
    return {"typ": typ, "quelle": q, "ziel": q}


def pruefe(daten, bausteine=None, max_ebenen=None):
    """Prüft einen Pfad. Gibt (sauberer_pfad_oder_None, fehler, warnungen) zurück.
    Es werden nur bekannte Felder übernommen. Unerreichbare Ebenen fallen weg."""
    fehler, warnungen = [], []
    bausteine = bekannte_bausteine() if bausteine is None else bausteine
    if not isinstance(daten, dict):
        return None, ["Kein Pfad"], warnungen
    screens = daten.get("screens")
    start = daten.get("start", "start")
    if not isinstance(screens, dict) or not screens:
        return None, ["Keine Ebenen"], warnungen
    if not isinstance(start, str) or start not in screens:
        return None, ["Start fehlt"], warnungen
    if len(screens) > MAX_SCREENS:
        return None, ["Zu viele Ebenen"], warnungen
    sauber = {}
    for sid, s in screens.items():
        if not isinstance(sid, str) or not _RE_ID.fullmatch(sid) or sid.startswith(_VERBOTEN_PRAEFIX):
            fehler.append("Ebenen-Name ungültig")
            continue
        if not isinstance(s, dict) or not isinstance(s.get("liste"), list):
            fehler.append("%s: Liste fehlt" % sid)
            continue
        if len(s["liste"]) > MAX_KARTEN:
            fehler.append("%s: zu viele Karten" % sid)
            continue
        name = _text(s.get("name"), 60)
        if not name:
            fehler.append("%s: Name fehlt" % sid)
            continue
        karten = []
        for i, k in enumerate(s["liste"]):
            wo = "%s/%d" % (sid, i + 1)
            if not isinstance(k, dict):
                fehler.append("%s: keine Karte" % wo)
                continue
            wort = _text(k.get("wort"), 60)
            if not wort:
                fehler.append("%s: Wort fehlt" % wo)
                continue
            sprechen = _text(k.get("sprechen") if k.get("sprechen") is not None else wort, 120) or wort
            bild = k.get("bild")
            if not isinstance(bild, str) or not _RE_BILD.fullmatch(bild):
                fehler.append("%s: Bild ungültig" % wo)
                continue
            a = _aktion(k.get("aktion"), fehler, wo, bausteine)
            if a is None:
                continue
            karte = {"wort": wort, "sprechen": sprechen, "bild": bild, "aktion": a}
            if k.get("bestaetigen") is True:
                karte["bestaetigen"] = True
                ab = _text(k.get("abbruch"), 120)
                if ab:
                    karte["abbruch"] = ab
            if k.get("aus") is True:
                karte["aus"] = True
            karten.append(karte)
        sauber[sid] = {"name": name, "liste": karten}
    if fehler:
        return None, fehler, warnungen
    # Erreichbarkeit, Kreise, Tiefe
    tiefe = {}
    def besuche(sid, d, pfad):
        if sid in pfad:
            fehler.append("Kreis bei %s" % sid)
            return
        if sid not in sauber:
            fehler.append("Ebene fehlt: %s" % sid)
            return
        if d > MAX_TIEFE:
            fehler.append("Zu tief: %s" % sid)
            return
        if tiefe.get(sid, 0) >= d:
            return
        tiefe[sid] = d
        for k in sauber[sid]["liste"]:
            if k["aktion"]["typ"] == "untermenue":
                besuche(k["aktion"]["ziel"], d + 1, pfad + [sid])
    besuche(start, 1, [])
    if fehler:
        return None, sorted(set(fehler)), warnungen
    sauber = {sid: s for sid, s in sauber.items() if sid in tiefe}
    if not any(not k.get("aus") for k in sauber[start]["liste"]):
        return None, ["Am Start muss mindestens eine Karte sichtbar sein"], warnungen
    for sid, s in sauber.items():
        if not any(not k.get("aus") for k in s["liste"]):
            warnungen.append("%s: keine sichtbare Karte" % s["name"])
    grenze = max_ebenen
    if grenze and max(tiefe.values()) > grenze:
        warnungen.append("Mehr Ebenen als im gewählten Modus gedacht (%d)" % grenze)
    return {"version": 1, "start": start, "plugins": daten.get("plugins") is True,
            "screens": sauber}, [], warnungen


# ---- Lesen, Schreiben, Zurücksetzen ----

def lese_pfad(config, basis=None):
    """Der gespeicherte, geprüfte Pfad oder None."""
    p = datei(config, basis)
    try:
        if p.stat().st_size > MAX_BYTES:
            return None
        with open(p, encoding="utf-8") as handle:
            roh = json.load(handle)
    except (OSError, ValueError):
        return None
    m = laden()["modi"][modus_id(config)]
    sauber, fehler, _ = pruefe(roh, max_ebenen=m["maxEbenen"])
    return sauber if not fehler else None


def schreibe_pfad(config, daten, basis=None):
    """Prüft und schreibt. Gibt {"ok", "fehler", "warnungen", "datei"} zurück."""
    m = laden()["modi"][modus_id(config)]
    sauber, fehler, warnungen = pruefe(daten, max_ebenen=m["maxEbenen"])
    if fehler:
        return {"ok": False, "fehler": fehler, "warnungen": warnungen}
    text = json.dumps(sauber, indent=2, ensure_ascii=False) + "\n"
    if len(text.encode("utf-8")) > MAX_BYTES:
        return {"ok": False, "fehler": ["Zu groß"], "warnungen": warnungen}
    ziel = datei(config, basis)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pfad-", suffix=".tmp", dir=str(ziel.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, ziel)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return {"ok": True, "fehler": [], "warnungen": warnungen, "datei": str(ziel)}


def zuruecksetzen(config, basis=None):
    """Löscht den eigenen Pfad dieses Modus. Danach gilt wieder die Vorlage."""
    try:
        datei(config, basis).unlink()
        return True
    except FileNotFoundError:
        return False


def wirksam(config, basis=None):
    """Der Pfad, den die App benutzt: eigener Pfad, sonst Vorlage des Modus."""
    lang = sprache(config)
    mid = modus_id(config)
    v = vorlage(mid, lang)
    eigen = lese_pfad(config, basis)
    if eigen:
        return {"modus": mid, "quelle": "datei", "start": eigen["start"], "plugins": eigen["plugins"],
                "maxEbenen": v["maxEbenen"], "screens": eigen["screens"]}
    return {"modus": mid, "quelle": "vorlage", "start": v["start"], "plugins": v["plugins"],
            "maxEbenen": v["maxEbenen"], "screens": v["screens"]}


def bibliothek(lang):
    """Alle Karten, die der Editor anbieten darf (aus allen drei Vorlagen, ohne Doppelte)."""
    gesehen, liste = set(), []
    for k, m in sorted(laden()["modi"].items(), reverse=True):
        for s in m["screens"][lang].values():
            for karte in s["liste"]:
                if karte["aktion"]["typ"] == "untermenue":
                    continue
                c = {x: karte[x] for x in karte if x != "aus"}
                schluessel = json.dumps(c, sort_keys=True, ensure_ascii=False)
                if schluessel not in gesehen:
                    gesehen.add(schluessel)
                    liste.append(c)
    return liste


def ordner_info(basis=None):
    import praxis
    return {"bilder": str(praxis.ordner_pfad("bilder", basis)), "filme": str(praxis.ordner_pfad("filme", basis))}
