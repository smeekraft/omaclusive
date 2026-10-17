#!/usr/bin/env python3
"""Erzeugt die Sprachaufnahmen audio/de und audio/en mit Piper (offline).
Generates the voice recordings audio/de and audio/en with Piper (offline).

  python3 audio_erzeugen.py                # beide Sprachen / both languages
  python3 audio_erzeugen.py en             # nur Englisch / English only
  python3 audio_erzeugen.py --liste        # nur die Satzliste zeigen, nichts erzeugen

Voraussetzung: Piper und die Stimmen. Standard: ~/.local/share/omaclusive/piper/piper und
~/.local/share/omaclusive/voices/ (das legt install.sh an). Mit --piper und --stimmen anders.
Geschrieben werden audio/<sprache>/*.wav und audio/<sprache>/index.json (Satz -> Datei).
Saetze mit Platzhaltern ({}) und Namen werden zur Laufzeit gesprochen, nicht vorab.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
STIMMEN = {"de": "de_DE-thorsten-medium.onnx", "en": "en_US-ljspeech-medium.onnx"}
CONFIGS = {"de": ("config.example.json", "plugins/grundbeduerfnisse/plugin.json"),
           "en": ("config.example.en.json", "plugins/grundbeduerfnisse/plugin.en.json")}
AUFNAHME_TEMPO = 1.15  # Piper length_scale: etwas langsamer. Muss zu bausteine.AUFNAHME_TEMPO passen.
# Wörter, die nur über sonderKarte() in pfad.js laufen und deshalb nicht als T("...") im Quelltext stehen
EXTRA = ("Weiter blättern", "Zurück", "Nein", "Ja", "Pause", "Weiter", "Okay")
FELDER = ("wort", "sprechen", "text", "name", "abbruch", "leer", "offen")


def lese(name):
    with open(os.path.join(DIR, name), encoding="utf-8") as handle:
        return handle.read()


def config_texte(obj, aus):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FELDER and isinstance(v, str) and not re.fullmatch(r"[a-z]+\.[a-z]+", v):
                aus.append(v)
            config_texte(v, aus)
    elif isinstance(obj, list):
        for v in obj:
            config_texte(v, aus)


def saetze(lang):
    """Alle Saetze, die ohne Platzhalter gesprochen werden koennen (deutsche Schluessel -> Sprache)."""
    with open(os.path.join(DIR, "locales", "en.json"), encoding="utf-8") as handle:
        en = json.load(handle)
    schluessel = []
    for name in ("bausteine.py", "hilferuf.py"):
        roh = lese(name)
        schluessel += re.findall(r"\btr\(\"((?:[^\"\\]|\\.)*)\"\)", roh)
        schluessel += [m[1] for m in re.findall(r"^(WARNUNG|AUS_SATZ|RAUS_SATZ|RUFE_SATZ|TEST_SATZ|TEST_AUS_SATZ) = \"([^\"]*)\"", roh, re.M)]
    for name in ("app.js", "pfad.js"):
        schluessel += re.findall(r"\bT\(\"((?:[^\"\\]|\\.)*)\"\)", lese(name))
    schluessel += list(EXTRA)
    ergebnis = []
    for s in schluessel:
        if "{}" in s:
            continue
        ergebnis.append(s if lang == "de" else en.get(s, ""))
    for datei in CONFIGS[lang]:
        texte = []
        config_texte(json.loads(lese(datei)), texte)
        ergebnis += texte
    # Die drei Modi (modi.json): Wörter und Ebenennamen der Vorlagen in dieser Sprache
    modi = json.loads(lese("modi.json"))
    for m in modi["modi"].values():
        texte = []
        config_texte(m["screens"][lang], texte)
        ergebnis += texte
    fertig, gesehen = [], set()
    for text in ergebnis:
        text = re.sub(r"\s+", " ", text).strip()
        if text and text not in gesehen and "{}" not in text:
            gesehen.add(text)
            fertig.append(text)
    return fertig


def dateiname(text):
    ascii_text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        ascii_text = ascii_text.replace(a, b)
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:40] or "satz"
    roh = ("%s|%s" % (AUFNAHME_TEMPO, text)).encode("utf-8")  # Tempo im Namen: neues Tempo = neue Dateien
    return slug + "-" + hashlib.sha1(roh).hexdigest()[:6] + ".wav"


def erzeuge(lang, piper, stimmen):
    modell = os.path.join(stimmen, STIMMEN[lang])
    if not os.path.isfile(modell):
        sys.exit("Stimme fehlt / voice missing: " + modell)
    ordner = os.path.join(DIR, "audio", lang)
    os.makedirs(ordner, exist_ok=True)
    index = {}
    for text in saetze(lang):
        name = dateiname(text)
        ziel = os.path.join(ordner, name)
        if not os.path.isfile(ziel) or os.path.getsize(ziel) <= 44:
            r = subprocess.run([piper, "--model", modell, "--output_file", ziel, "--length_scale", str(AUFNAHME_TEMPO)],
                               input=text + "\n",
                               text=True, capture_output=True, timeout=60)
            if r.returncode != 0 or not os.path.isfile(ziel):
                sys.exit("Piper-Fehler bei: %s\n%s" % (text, r.stderr[-300:]))
        index[text] = name
    with open(os.path.join(ordner, "index.json"), "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    benutzt = set(index.values()) | {"index.json"}
    for name in os.listdir(ordner):
        if name not in benutzt:
            os.remove(os.path.join(ordner, name))
    print("OK", lang, len(index), "Dateien")


def main():
    home = os.path.expanduser("~/.local/share/omaclusive")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sprachen", nargs="*", choices=("de", "en"), help="Standard: de en")
    p.add_argument("--piper", default=os.path.join(home, "piper", "piper"))
    p.add_argument("--stimmen", default=os.path.join(home, "voices"))
    p.add_argument("--liste", action="store_true")
    a = p.parse_args()
    for lang in a.sprachen or ("de", "en"):
        if a.liste:
            print("\n".join("%s\t%s" % (lang, t) for t in saetze(lang)))
        else:
            erzeuge(lang, a.piper, a.stimmen)


if __name__ == "__main__":
    main()
