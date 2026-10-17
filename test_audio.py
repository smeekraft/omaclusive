#!/usr/bin/env python3
"""Prüft die fertigen Aufnahmen in audio/de und audio/en: Format, Länge, kein Clipping,
nicht abgeschnitten (am Ende ist es still), und dass jede Datei im Index vorkommt.
Spielt nichts ab."""
import array
import json
import os
import sys
import wave

ROOT = os.path.dirname(os.path.abspath(__file__))


def pruefe(lang):
    ordner = os.path.join(ROOT, "audio", lang)
    with open(os.path.join(ordner, "index.json"), encoding="utf-8") as handle:
        index = json.load(handle)
    fehler, laengen = [], []
    for text, name in index.items():
        pfad = os.path.join(ordner, name)
        if not os.path.isfile(pfad):
            fehler.append("fehlt: " + name)
            continue
        with wave.open(pfad, "rb") as w:
            kanaele, breite, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            roh = w.readframes(n)
        if (kanaele, breite) != (1, 2) or rate < 16000:
            fehler.append("Format %s: %s/%s/%s" % (name, kanaele, breite, rate))
            continue
        daten = array.array("h")
        daten.frombytes(roh)
        dauer = n / float(rate)
        laengen.append(dauer)
        if dauer < 0.15:
            fehler.append("zu kurz %s %.2f s (%s)" % (name, dauer, text[:30]))
        if dauer > 12:
            fehler.append("zu lang %s %.1f s" % (name, dauer))
        spitze = max(max(daten), -min(daten)) if daten else 0
        if spitze == 0:
            fehler.append("stumm: " + name)
            continue
        zu_laut = sum(1 for x in daten if abs(x) >= 32760)
        if zu_laut > 3:
            fehler.append("Clipping %s: %d Werte am Anschlag" % (name, zu_laut))
        ende = daten[-int(rate * 0.03):]
        rms = (sum(x * x for x in ende) / float(len(ende))) ** 0.5 if ende else 0
        if rms > spitze * 0.06:
            fehler.append("am Ende nicht still (abgeschnitten?) %s rms %.0f von %d (%s)" % (name, rms, spitze, text[:30]))
    mittel = sum(laengen) / len(laengen) if laengen else 0
    print("AUDIO %s: %d Dateien, mittel %.2f s, längste %.2f s" % (lang, len(laengen), mittel, max(laengen or [0])))
    return fehler


def main():
    alle = []
    for lang in ("de", "en"):
        alle += ["%s: %s" % (lang, f) for f in pruefe(lang)]
    if alle:
        print("\n".join(alle[:20]))
        sys.exit("AUDIO FAIL %d Probleme" % len(alle))
    print("AUDIO_OK")


if __name__ == "__main__":
    main()
