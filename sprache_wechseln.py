#!/usr/bin/env python3
"""Sprache der config.json wechseln (de <-> en) / Switch the language of config.json.

  python3 sprache_wechseln.py en            # config.json auf Englisch
  python3 sprache_wechseln.py de            # config.json auf Deutsch
  python3 sprache_wechseln.py en --out config.example.en.json --quelle config.example.json

Es werden nur Texte uebersetzt, die in locales/de.json und locales/en.json stehen.
Eigene Texte (Namen, eigene Saetze) bleiben, wie sie sind. Vorher wird config.json.bak angelegt.
Danach den Server neu starten.
"""
import argparse
import json
import os
import re
import shutil
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
STANDARD_CODES = {"de": "de-DE", "en": "en-US"}
FELDER = ("wort", "sprechen", "hilfe", "text", "name", "abbruch", "leer", "offen")


def lade(lang):
    with open(os.path.join(DIR, "locales", lang + ".json"), encoding="utf-8") as handle:
        return json.load(handle)


def sprachen():
    """Alle Sprachen mit Tabelle in locales/ (de ist der Schluessel und braucht keine)."""
    namen = {"de"}
    ordner = os.path.join(DIR, "locales")
    if os.path.isdir(ordner):
        namen |= {f[:-5] for f in os.listdir(ordner) if f.endswith(".json") and re.fullmatch(r"[a-z]{2,3}", f[:-5])}
    return sorted(namen)


def richtung(von, nach):
    """Tabelle: Text in Sprache 'von' -> Text in Sprache 'nach'. Schluessel ist Deutsch."""
    if von == nach:
        return {}
    vorwaerts = {} if nach == "de" else lade(nach)
    if von == "de":
        return vorwaerts
    umgekehrt = {}
    for de, fremd in lade(von).items():
        umgekehrt.setdefault(fremd, de)
    if nach == "de":
        return umgekehrt
    return {fremd: vorwaerts[de] for fremd, de in umgekehrt.items() if de in vorwaerts}


def uebersetze(objekt, tabelle):
    if isinstance(objekt, dict):
        for schluessel, wert in list(objekt.items()):
            if schluessel in FELDER and isinstance(wert, str) and wert in tabelle:
                objekt[schluessel] = tabelle[wert]
            else:
                uebersetze(wert, tabelle)
    elif isinstance(objekt, list):
        for eintrag in objekt:
            uebersetze(eintrag, tabelle)
    return objekt


def wechseln(daten, ziel, sprachcode=None):
    """Stellt eine geladene config auf 'ziel' um. Eigene Texte bleiben. Gibt daten zurueck."""
    if ziel not in sprachen():
        raise ValueError("Sprache unbekannt: " + str(ziel))
    von = str(daten.get("language") or "de").split("-")[0].split("_")[0]
    if von not in sprachen():
        von = "de"
    uebersetze(daten, richtung(von, ziel))
    daten["language"] = ziel
    daten["lang"] = sprachcode or STANDARD_CODES.get(ziel, ziel)
    return daten


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sprache", choices=sprachen())
    parser.add_argument("--quelle", default=os.path.join(DIR, "config.json"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    with open(args.quelle, encoding="utf-8") as handle:
        daten = json.load(handle)
    wechseln(daten, args.sprache)
    ziel = args.out or args.quelle
    if os.path.exists(ziel) and not args.out:
        shutil.copy(ziel, ziel + ".bak")
    with open(ziel, "w", encoding="utf-8") as handle:
        json.dump(daten, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("OK", args.sprache, ziel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
