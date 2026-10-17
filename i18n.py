#!/usr/bin/env python3
"""Zweisprachigkeit (de/en). Two languages (de/en).

Schluessel ist der deutsche Originaltext. Die Tabellen liegen in locales/de.json und
locales/en.json. Sprache: Umgebung OMACLUSIVE_LANG, sonst "language" in config.json,
sonst "de". Unbekannte Sprache faellt auf Englisch zurueck. Fehlt ein Eintrag, bleibt
der Originaltext stehen.
"""
import json
import os

DIR = os.path.dirname(os.path.abspath(__file__))
SPRACHEN = ("de", "en")
STANDARD = "de"
_tabellen = {}
_cfg = {"mtime": None, "lang": STANDARD}


def normalisiere(code):
    code = str(code or "").strip().lower().replace("_", "-").split("-")[0]
    if not code:
        return STANDARD
    return code if code in SPRACHEN else "en"


def _aus_config():
    pfad = os.path.join(DIR, "config.json")
    try:
        mtime = os.path.getmtime(pfad)
    except OSError:
        _cfg.update(mtime=None, lang=STANDARD)
        return STANDARD
    if _cfg["mtime"] != mtime:
        lang = STANDARD
        try:
            with open(pfad, encoding="utf-8") as handle:
                daten = json.load(handle)
            if isinstance(daten, dict) and daten.get("language"):
                lang = normalisiere(daten["language"])
        except (OSError, ValueError):
            pass
        _cfg.update(mtime=mtime, lang=lang)
    return _cfg["lang"]


def language():
    env = os.environ.get("OMACLUSIVE_LANG")
    if env:
        return normalisiere(env)
    return _aus_config()


def tabelle(lang):
    if lang not in _tabellen:
        try:
            with open(os.path.join(DIR, "locales", lang + ".json"), encoding="utf-8") as handle:
                daten = json.load(handle)
        except (OSError, ValueError):
            daten = {}
        _tabellen[lang] = daten if isinstance(daten, dict) else {}
    return _tabellen[lang]


def tr(text):
    """Uebersetzt einen deutschen Originaltext in die gewaehlte Sprache."""
    text = str(text)
    lang = language()
    if lang == "de":
        return text
    return tabelle(lang).get(text, text)


def trf(text, *args):
    """Wie tr, mit {}-Platzhaltern."""
    return tr(text).format(*args)


def speech_lang():
    return {"de": "de-DE", "en": "en-US"}.get(language(), "en-US")
