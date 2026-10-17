#!/usr/bin/env python3
"""Prueft die Zweisprachigkeit: Tabellen, Platzhalter, Beispiel-Configs, Umschalten."""
import json
import os
import re

import i18n

ROOT = os.path.dirname(os.path.abspath(__file__))


def laden(pfad):
    with open(os.path.join(ROOT, pfad), encoding="utf-8") as handle:
        return json.load(handle)


def struktur(objekt):
    """Schluessel und Formen, ohne die Texte."""
    if isinstance(objekt, dict):
        return {k: struktur(v) for k, v in objekt.items() if k not in ("language", "lang")}
    if isinstance(objekt, list):
        return [struktur(v) for v in objekt]
    return type(objekt).__name__


def texte_im_quelltext():
    funde = set()
    for name in ("bausteine.py", "hilferuf.py", "praxis.py", "server.py", "app.js", "pfad.js", "setup.html"):
        with open(os.path.join(ROOT, name), encoding="utf-8") as handle:
            roh = handle.read()
        for m in re.finditer(r"\btr\(\"((?:[^\"\\]|\\.)*)\"\)", roh):
            funde.add(m.group(1))
        for m in re.finditer(r"\bTf?\(([^()]*)\)", roh):
            for q in re.finditer(r"\"((?:[^\"\\]|\\.)+)\"|'((?:[^'\\]|\\.)+)'", m.group(1)):
                funde.add((q.group(1) or q.group(2)).replace("\\'", "'"))
    return funde


def main():
    de, en = laden("locales/de.json"), laden("locales/en.json")
    if set(de) != set(en):
        raise SystemExit("de.json und en.json haben verschiedene Schluessel: %s" % sorted(set(de) ^ set(en))[:5])
    for schluessel, wert in en.items():
        if not str(wert).strip():
            raise SystemExit("leere Uebersetzung: " + schluessel)
        if schluessel.count("{}") != wert.count("{}"):
            raise SystemExit("Platzhalter passen nicht: " + schluessel)
    fehlt = sorted(t for t in texte_im_quelltext() if t not in en)
    if fehlt:
        raise SystemExit("Ohne Uebersetzung: %s" % fehlt[:5])
    if struktur(laden("config.example.json")) != struktur(laden("config.example.en.json")):
        raise SystemExit("config.example.en.json hat eine andere Form als config.example.json")
    if struktur(laden("plugins/grundbeduerfnisse/plugin.json")) != struktur(laden("plugins/grundbeduerfnisse/plugin.en.json")):
        raise SystemExit("plugin.en.json hat eine andere Form als plugin.json")
    if laden("config.example.json").get("language") != "de" or laden("config.example.en.json").get("language") != "en":
        raise SystemExit("language fehlt in den Beispiel-Configs")
    os.environ["OMACLUSIVE_LANG"] = "de"
    if i18n.tr("Gleich zurück zum Start.") != "Gleich zurück zum Start.":
        raise SystemExit("Deutsch hat sich veraendert")
    os.environ["OMACLUSIVE_LANG"] = "en"
    if i18n.tr("Gleich zurück zum Start.") != "Going back to the start soon.":
        raise SystemExit("Englisch fehlt")
    if i18n.trf("Verbunden mit {}", "Netz") != "Connected to Netz":
        raise SystemExit("Platzhalter")
    os.environ["OMACLUSIVE_LANG"] = "fr"
    if i18n.language() != "en":
        raise SystemExit("Unbekannte Sprache muss auf Englisch fallen")
    if i18n.tr("Nicht uebersetzt") != "Nicht uebersetzt":
        raise SystemExit("Fehlender Eintrag muss das Original bleiben")
    os.environ.pop("OMACLUSIVE_LANG")
    for lang in ("de", "en"):
        ordner = os.path.join(ROOT, "audio", lang)
        if os.path.isdir(ordner):
            index = laden("audio/%s/index.json" % lang)
            for text, datei in index.items():
                if not os.path.isfile(os.path.join(ordner, datei)):
                    raise SystemExit("Aufnahme fehlt: %s/%s" % (lang, datei))
    print("I18N_OK", len(en), "Texte")


if __name__ == "__main__":
    main()
