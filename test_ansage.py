#!/usr/bin/env python3
"""Prüft die Ansage ohne Ton: mehrere Wörter werden zu einer Aufnahme, neue Ansage ersetzt die alte,
verspätete ältere Anfragen werden verworfen (kein doppeltes Abspielen), Fehler kommen ins Log."""
import os
import tempfile
import wave

import bausteine

tmp = tempfile.mkdtemp()
bausteine.LOGDATEI = os.path.join(tmp, "log.txt")
echt_play = bausteine._play
gespielt = []
gestoppt = []
bausteine._play = lambda wav: (gespielt.append(wav), True)[1]
bausteine.stop_speak = lambda: gestoppt.append(1)


def dauer(pfad):
    with wave.open(pfad) as w:
        return w.getnframes() / float(w.getframerate())


assert bausteine.tempo() == bausteine.AUFNAHME_TEMPO == 1.15

# ein Satz: fertige Aufnahme
assert bausteine.speak("Zurück", "piper", nr=1) is True
assert len(gespielt) == 1 and "audio" in gespielt[0], gespielt
einzeln = dauer(gespielt[0])

# zwei kurze Wörter: eine zusammengesetzte Datei mit Pause, ein Abspielen
assert bausteine.speak(["Zurück", "Nein"], "piper", nr=2) is True
assert len(gespielt) == 2, gespielt
zwei = dauer(gespielt[1])
assert zwei > einzeln + 0.3, (einzeln, zwei)
assert len(gestoppt) == 2, "jede neue Ansage stoppt die alte"

# verspätete ältere Anfrage: nichts wird abgespielt
assert bausteine.speak("Ja", "piper", nr=1) is True
assert len(gespielt) == 2, "verspätete Anfrage darf nicht spielen"

# dieselbe Liste noch einmal: aus dem Zwischenspeicher, wieder genau ein Abspielen
assert bausteine.speak(["Zurück", "Nein"], "piper", nr=3) is True
assert len(gespielt) == 3 and gespielt[2] == gespielt[1]

# kein Player: False und ein Logeintrag, kein Absturz
orig_which = bausteine.which
bausteine.which = lambda name: None
assert echt_play("/x.wav") is False
assert os.path.isfile(bausteine.LOGDATEI), "Fehler muss im Log stehen"
assert "Kein Player" in open(bausteine.LOGDATEI, encoding="utf-8").read()
bausteine.which = orig_which
print("ANSAGE_OK einzeln %.2f s, zwei Wörter %.2f s" % (einzeln, zwei))
