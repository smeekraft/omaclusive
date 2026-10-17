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
import shutil
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
FELDER = ("wort", "sprechen", "hilfe", "text", "name", "abbruch", "leer", "offen")


def lade(lang):
    with open(os.path.join(DIR, "locales", lang + ".json"), encoding="utf-8") as handle:
        return json.load(handle)


def richtung(ziel):
    de_en = lade("en")
    if ziel == "en":
        return de_en
    umgekehrt = {}
    for de, en in de_en.items():
        umgekehrt.setdefault(en, de)
    return umgekehrt


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sprache", choices=("de", "en"))
    parser.add_argument("--quelle", default=os.path.join(DIR, "config.json"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    with open(args.quelle, encoding="utf-8") as handle:
        daten = json.load(handle)
    tabelle = richtung(args.sprache)
    uebersetze(daten, tabelle)
    daten["language"] = args.sprache
    daten["lang"] = "de-DE" if args.sprache == "de" else "en-US"
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
