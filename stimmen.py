#!/usr/bin/env python3
"""Sprache und Stimme waehlen / Choose language and voice.

Die Liste steht in voices.json (Name, Modell, SHA256). Neue Sprache: locales/xx.json
und ein Eintrag in voices.json. Geladen wird nur von der festen Quelle QUELLE,
mit Pruefsumme, ohne Root, nach voices/.
"""
import hashlib
import json
import os
import threading
import urllib.request

import sprache_wechseln

DIR = os.path.dirname(os.path.abspath(__file__))
QUELLE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
_job = {"id": None, "status": "leer", "fehler": ""}
_sperre = threading.Lock()


def liste():
    try:
        with open(os.path.join(DIR, "voices.json"), encoding="utf-8") as handle:
            roh = json.load(handle).get("stimmen", [])
    except (OSError, ValueError, AttributeError):
        return []
    erlaubt = set(sprache_wechseln.sprachen())
    ergebnis = []
    for v in roh if isinstance(roh, list) else []:
        if not isinstance(v, dict):
            continue
        felder = ("id", "sprache", "name", "modell", "pfad", "sha256", "json_sha256")
        if not all(isinstance(v.get(k), str) and v.get(k) for k in felder):
            continue
        if v["sprache"] not in erlaubt or not _sauber(v["modell"]) or not _sauber(v["id"]):
            continue
        if ".." in v["pfad"] or v["pfad"].startswith("/"):
            continue
        ergebnis.append(v)
    return ergebnis


def _sauber(text):
    return bool(text) and all(c.isalnum() or c in "_.-" for c in text)


def finde(stimme_id):
    for v in liste():
        if v["id"] == stimme_id:
            return v
    return None


def standard(sprache):
    eintraege = [v for v in liste() if v["sprache"] == sprache]
    for v in eintraege:
        if v.get("standard"):
            return v
    return eintraege[0] if eintraege else None


def datei(v, endung=".onnx"):
    return os.path.join(DIR, "voices", v["modell"] + endung)


def _summe(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def da(v):
    try:
        return (os.path.isfile(datei(v)) and _summe(datei(v)) == v["sha256"]
                and os.path.isfile(datei(v, ".onnx.json")) and _summe(datei(v, ".onnx.json")) == v["json_sha256"])
    except OSError:
        return False


def aktive_id(config):
    """Gewaehlte Stimme aus der config, sonst die Standardstimme der Sprache."""
    sprache = str((config or {}).get("language") or "de").split("-")[0]
    v = finde((config or {}).get("stimmeId"))
    if v and v["sprache"] == sprache:
        return v["id"]
    s = standard(sprache)
    return s["id"] if s else None


def _lade(url, ziel, summe):
    if not url.startswith(QUELLE):
        raise ValueError("Quelle nicht erlaubt")
    teil = ziel + ".teil"
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=60) as antwort, open(teil, "wb") as aus:
            for block in iter(lambda: antwort.read(1 << 20), b""):
                h.update(block)
                aus.write(block)
        if h.hexdigest() != summe:
            raise ValueError("Pruefsumme stimmt nicht")
        os.replace(teil, ziel)
    finally:
        if os.path.exists(teil):
            os.remove(teil)


def herunterladen(v):
    """Laedt Modell und Stimmdaten, falls sie fehlen oder falsch sind. Wirft bei Fehlern."""
    for endung, summe in ((".onnx", v["sha256"]), (".onnx.json", v["json_sha256"])):
        ziel = datei(v, endung)
        if os.path.isfile(ziel) and _summe(ziel) == summe:
            continue
        _lade(QUELLE + v["pfad"] + endung, ziel, summe)


def anwenden(config, v):
    """Stellt die geladene config auf Sprache und Stimme von v um. Gibt True zurueck."""
    sprache_wechseln.wechseln(config, v["sprache"], v.get("sprachcode"))
    config["stimmeId"] = v["id"]
    config["stimmeModell"] = v["modell"]
    config["stimme"] = "piper"
    return True


def status():
    with _sperre:
        return dict(_job)


def starten(stimme_id, config_aendern):
    """Startet das Wechseln im Hintergrund. config_aendern(fn) wendet fn auf die config an und speichert."""
    v = finde(stimme_id)
    if not v:
        return False, "unbekannt"
    with _sperre:
        if _job["status"] == "laeuft":
            return False, "laeuft"
        _job.update(id=v["id"], status="laeuft", fehler="")

    def arbeit():
        try:
            if not da(v):
                herunterladen(v)
            config_aendern(lambda c: anwenden(c, v))
            ende = ("fertig", "")
        except Exception as fehler:
            ende = ("fehler", str(fehler)[:120])
        with _sperre:
            _job.update(status=ende[0], fehler=ende[1])

    threading.Thread(target=arbeit, daemon=True).start()
    return True, ""
