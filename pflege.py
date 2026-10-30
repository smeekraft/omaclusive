"""Erinnerungen und Aufgaben (To-do). Kein Netz, kein Server-Start.

Gespeichert wird in <heim>/.config/omaclusive/pflege.json (fester Pfad). Tests übergeben ein eigenes
Heimverzeichnis und eine feste Uhrzeit.
"""
import datetime
import json
import os
import re
import tempfile
from pathlib import Path

MAX_ERINNERUNGEN = 30
MAX_AUFGABEN = 50
MAX_TEXT = 120
WIEDERHOLEN = ("einmal", "taeglich", "werktags", "wochenende", "tage")
_RE_ZEIT = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_RE_DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_ID = re.compile(r"^[a-z0-9_-]{1,40}$")
_STEUER = re.compile(r"[\x00-\x1f\x7f]")


def datei(heim):
    return Path(heim) / ".config" / "omaclusive" / "pflege.json"


def leer():
    return {"erinnerungen": [], "aufgaben": [], "bestaetigt": {}}


def _text(wert):
    t = _STEUER.sub(" ", str(wert or "")).strip()
    t = re.sub(r"\s+", " ", t)
    return t[:MAX_TEXT]


def _neue_id(vorhanden, vorsilbe):
    n = 1
    while "%s%d" % (vorsilbe, n) in vorhanden:
        n += 1
    return "%s%d" % (vorsilbe, n)


def bereinige(daten):
    """Prüft und säubert Daten von außen. Gibt (sauber, fehler) zurück."""
    fehler = []
    sauber = leer()
    if not isinstance(daten, dict):
        return sauber, ["Daten ungültig"]
    ids = set()
    for roh in (daten.get("erinnerungen") or [])[:MAX_ERINNERUNGEN]:
        if not isinstance(roh, dict):
            fehler.append("Erinnerung ungültig")
            continue
        zeit = str(roh.get("zeit") or "")
        text = _text(roh.get("text"))
        if not _RE_ZEIT.fullmatch(zeit) or not text:
            fehler.append("Erinnerung braucht Uhrzeit HH:MM und Text")
            continue
        wiederholen = roh.get("wiederholen") if roh.get("wiederholen") in WIEDERHOLEN else "taeglich"
        tage = sorted({t for t in (roh.get("tage") or []) if isinstance(t, int) and not isinstance(t, bool) and 0 <= t <= 6})
        if wiederholen == "tage" and not tage:
            wiederholen = "taeglich"
        datum = str(roh.get("datum") or "")
        if wiederholen == "einmal":
            try:
                datetime.date.fromisoformat(datum)
            except ValueError:
                fehler.append("Einmalige Erinnerung braucht ein Datum")
                continue
        else:
            datum = ""
        eid = str(roh.get("id") or "")
        if not _RE_ID.fullmatch(eid) or eid in ids:
            eid = _neue_id(ids, "e")
        ids.add(eid)
        sauber["erinnerungen"].append({"id": eid, "zeit": zeit, "text": text, "wiederholen": wiederholen,
                                       "tage": tage if wiederholen == "tage" else [], "datum": datum,
                                       "aktiv": roh.get("aktiv") is not False})
    ids = set()
    for roh in (daten.get("aufgaben") or [])[:MAX_AUFGABEN]:
        if not isinstance(roh, dict):
            fehler.append("Aufgabe ungültig")
            continue
        text = _text(roh.get("text"))
        if not text:
            fehler.append("Aufgabe braucht Text")
            continue
        aid = str(roh.get("id") or "")
        if not _RE_ID.fullmatch(aid) or aid in ids:
            aid = _neue_id(ids, "a")
        ids.add(aid)
        sauber["aufgaben"].append({"id": aid, "text": text, "erledigt": roh.get("erledigt") is True})
    best = daten.get("bestaetigt")
    if isinstance(best, dict):
        for k, v in best.items():
            if k in {e["id"] for e in sauber["erinnerungen"]} and isinstance(v, str) and _RE_DATUM.fullmatch(v):
                sauber["bestaetigt"][k] = v
    return sauber, fehler


def laden(heim):
    try:
        with open(datei(heim), encoding="utf-8") as handle:
            daten = json.load(handle)
    except (OSError, ValueError):
        return leer()
    return bereinige(daten)[0]


def speichern(heim, daten):
    """Schreibt atomar mit Modus 0600: Erinnerungen und Aufgaben gehen andere Konten nichts an."""
    ziel = datei(heim)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pflege-", suffix=".tmp", dir=str(ziel.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(daten, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, ziel)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def passt_tag(e, tag):
    """Gilt die Erinnerung an diesem Kalendertag? (Montag = 0)"""
    w = e["wiederholen"]
    if w == "einmal":
        return e["datum"] <= tag.isoformat()  # verpasste einmalige bleiben, bis sie bestätigt sind
    if w == "taeglich":
        return True
    if w == "werktags":
        return tag.weekday() < 5
    if w == "wochenende":
        return tag.weekday() >= 5
    return tag.weekday() in e["tage"]


def faellig(daten, jetzt):
    """Fällige, noch nicht bestätigte Erinnerungen (nach Uhrzeit sortiert). Eine tägliche Erinnerung gilt nur heute."""
    tag = jetzt.date()
    uhr = jetzt.strftime("%H:%M")
    aus = []
    for e in daten["erinnerungen"]:
        if not e["aktiv"] or not passt_tag(e, tag):
            continue
        if e["zeit"] > uhr and not (e["wiederholen"] == "einmal" and e["datum"] < tag.isoformat()):
            continue
        b = daten["bestaetigt"].get(e["id"])
        if e["wiederholen"] == "einmal":
            if b:
                continue
        elif b == tag.isoformat():
            continue
        aus.append({"id": e["id"], "zeit": e["zeit"], "text": e["text"], "tag": tag.isoformat()})
    return sorted(aus, key=lambda x: (x["zeit"], x["id"]))


def bestaetigen(daten, eid, jetzt):
    if eid not in {e["id"] for e in daten["erinnerungen"]}:
        return False
    daten["bestaetigt"][eid] = jetzt.date().isoformat()
    return True


def offene_aufgaben(daten):
    return [{"id": a["id"], "text": a["text"]} for a in daten["aufgaben"] if not a["erledigt"]]


def abhaken(daten, aid):
    for a in daten["aufgaben"]:
        if a["id"] == aid and not a["erledigt"]:
            a["erledigt"] = True
            return True
    return False
