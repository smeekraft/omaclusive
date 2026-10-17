#!/usr/bin/env python3
"""Prüft den Sprachspeicher. Spielt nichts ab und ändert keine Lautstärke."""
import json
import os

import bausteine

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    datei = os.path.join(ROOT, "config.json")
    if not os.path.exists(datei):
        datei = os.path.join(ROOT, "config.example.json")
    with open(datei, encoding="utf-8") as handle:
        config = json.load(handle)
    texte = bausteine.texte_aus_config(config)
    if "Gleich zurück zum Start." not in texte:
        raise SystemExit("Hinweis fehlt im Sprachspeicher")
    if "Ich will was sagen" not in texte:
        raise SystemExit("Startkarte fehlt im Sprachspeicher")
    roh = "\n".join(texte)
    if "/home/" in roh:
        raise SystemExit("Sprachliste enthält einen Privatpfad")
    gespielt = {"an": False}

    def nicht_spielen(*_args, **_kwargs):
        gespielt["an"] = True
        raise SystemExit("vorab hat abgespielt")

    bausteine._play = nicht_spielen
    anzahl = bausteine.sprache_vorab(["Ja."], "piper")
    if anzahl != 1:
        raise SystemExit("Ja. wurde nicht erzeugt: %s" % anzahl)
    if gespielt["an"]:
        raise SystemExit("vorab hat abgespielt")
    wav = bausteine._phrase_wav.get(bausteine._key("piper", "Ja."))
    if not wav or not os.path.isfile(wav) or os.path.getsize(wav) <= 44:
        raise SystemExit("keine WAV für Ja.")
    bausteine._loesche_temp(wav)  # nie eine mitgelieferte Aufnahme loeschen
    os.environ["OMACLUSIVE_LANG"] = "en"
    try:
        zu_hause = bausteine._vorgefertigt("Yes.", "piper")
        if not zu_hause or "audio" + os.sep + "en" not in zu_hause:
            raise SystemExit("Englische Aufnahme fehlt fuer Yes.")
        if "Going back to the start soon." not in bausteine.texte_aus_config(config):
            raise SystemExit("Englischer Hinweis fehlt im Sprachspeicher")
        if bausteine._key("piper", "Yes.") != "en\0piper@%s\0Yes." % bausteine.tempo():
            raise SystemExit("Englischer Schluessel")
    finally:
        os.environ.pop("OMACLUSIVE_LANG")
    print("SPRACHE_OK", bausteine.engine(), "texte", len(texte))


if __name__ == "__main__":
    main()
