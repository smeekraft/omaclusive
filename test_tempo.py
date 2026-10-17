#!/usr/bin/env python3
"""Prueft stimmeTempo (Piper length_scale): Standard, gueltige und ungueltige Werte."""
import json, os, tempfile
import bausteine

tmp = tempfile.mkdtemp()
bausteine.DIR = tmp
cfg = os.path.join(tmp, "config.json")


def setze(wert, fehlt=False):
    daten = {} if fehlt else {"stimmeTempo": wert}
    with open(cfg, "w", encoding="utf-8") as handle:
        json.dump(daten, handle)
    os.utime(cfg, (os.path.getmtime(cfg) + 1, os.path.getmtime(cfg) + 1 + len(str(wert))))
    bausteine._tempo_cache["mtime"] = None


S = bausteine.AUFNAHME_TEMPO
assert S == 1.15
assert bausteine.tempo() == S  # keine config: Standard 1.15
setze(None, fehlt=True); assert bausteine.tempo() == S
for roh, soll in ((1.0, 1.0), (1.2, 1.2), ("1.5", 1.5), (0.5, 0.5), (2.0, 2.0),
                  (0.4, S), (2.5, S), ("x", S), (None, S), (True, S)):
    setze(roh)
    assert bausteine.tempo() == soll, (roh, bausteine.tempo())

befehle = []


class Lauf:
    returncode = 0


bausteine.piper_bin = lambda: "/x/piper"
bausteine.voice_model = lambda lang=None: "/x/m.onnx"
bausteine._out_flag = "--output_file"
bausteine.subprocess.run = lambda cmd, **kw: (befehle.append(cmd), Lauf())[1]
setze(1.0); bausteine._synth_piper("a", "/tmp/omaclusive-test.wav")
setze(1.4); bausteine._synth_piper("a", "/tmp/omaclusive-test.wav")
assert "--length_scale" not in befehle[0]
assert befehle[1][-2:] == ["--length_scale", "1.4"]
setze(1.4); assert bausteine._vorgefertigt("Start", "piper") is None  # anderes Tempo: keine fertigen Aufnahmen
import audio_erzeugen
assert audio_erzeugen.AUFNAHME_TEMPO == S, "Aufnahme-Tempo und Standard-Tempo gleich"
assert bausteine._key("piper", "a") != (lambda: (setze(1.0), bausteine._key("piper", "a"))[1])()
print("TEMPO_OK")
