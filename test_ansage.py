#!/usr/bin/env python3
"""Prüft die Ansage ohne Ton: mehrere Wörter werden zu einer Aufnahme, neue Ansage ersetzt die alte,
verspätete ältere Anfragen werden verworfen (kein doppeltes Abspielen), Fehler kommen ins Log.
espeak-ng bekommt den Satz nicht als Argument. Das Log nennt den Satz nicht."""
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
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

# Altes Log mit einem Satz: nur die Rechte ändern, der Text bleibt, andere Konten lesen ihn nicht.
with open(bausteine.LOGDATEI, "a", encoding="utf-8") as handle:
    handle.write("alt GEHEIM-historisch\n")
os.chmod(bausteine.LOGDATEI, 0o644)
bausteine.logdateien_abschirmen()
assert stat.S_IMODE(os.stat(bausteine.LOGDATEI).st_mode) == 0o600
assert "GEHEIM-historisch" in open(bausteine.LOGDATEI, encoding="utf-8").read()

# Fehlende Stimme: der gesprochene Satz steht nicht im Log.
phrase_log = "GEHEIM-Nägele-7f29-log"
alt_espeak, alt_piper = bausteine._synth_espeak, bausteine._synth_piper
bausteine._synth_espeak = lambda *a, **k: False
bausteine._synth_piper = lambda *a, **k: False
try:
    assert bausteine.speak(phrase_log, "espeak", nr=30) is False
finally:
    bausteine._synth_espeak, bausteine._synth_piper = alt_espeak, alt_piper
log_inhalt = open(bausteine.LOGDATEI, encoding="utf-8").read()
assert phrase_log not in log_inhalt, log_inhalt
assert "Keine Stimme" in log_inhalt
assert stat.S_IMODE(os.stat(bausteine.LOGDATEI).st_mode) == 0o600


def espeak_attrappe(ordner):
    pfad = os.path.join(ordner, "espeak-ng")
    with open(pfad, "w", encoding="utf-8") as handle:
        handle.write("""#!%s
import json, os, stat, sys, time
argv = sys.argv[1:]
wurzel = os.environ["OMACLUSIVE_ESPEAK_WURZEL"]
with open(os.path.join(wurzel, "argv.log"), "a", encoding="utf-8") as handle:
    handle.write(json.dumps(argv) + "\\n")
pid = os.getpid()
with open(os.path.join(wurzel, "pid"), "w", encoding="ascii") as handle:
    handle.write(str(pid))
ende = time.time() + 5
marker = os.path.join(wurzel, "seen-%%d" %% pid)
while time.time() < ende and not os.path.exists(marker):
    time.sleep(0.01)
if "--stdin" in argv and os.environ.get("OMACLUSIVE_ESPEAK_REJECT") == "1":
    sys.exit(1)
if "--stdin" in argv:
    modus, text = "stdin", sys.stdin.buffer.read().decode("utf-8")
elif "-f" in argv:
    datei = argv[argv.index("-f") + 1]
    modus = "%%o" %% stat.S_IMODE(os.stat(datei).st_mode)
    with open(datei, encoding="utf-8") as handle:
        text = handle.read()
else:
    modus, text = "argv", ""
with open(os.path.join(wurzel, "text"), "w", encoding="utf-8") as handle:
    handle.write(modus + "\\n" + text)
wav = argv[argv.index("-w") + 1]
with open(wav, "wb") as handle:
    handle.write(b"RIFF" + b"\\0" * 80)
""" % sys.executable)
    os.chmod(pfad, 0o755)
    return pfad


def befehl_beobachten(wurzel, fertig, snaps):
    gesehen = set()
    ende = time.time() + 8
    while time.time() < ende and not fertig[0]:
        try:
            pid = int(open(os.path.join(wurzel, "pid"), encoding="ascii").read())
        except (OSError, ValueError):
            time.sleep(0.01)
            continue
        if pid in gesehen:
            time.sleep(0.01)
            continue
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as handle:
                snaps.append(handle.read())
        except OSError:
            time.sleep(0.01)
            continue
        gesehen.add(pid)
        with open(os.path.join(wurzel, "seen-%d" % pid), "w", encoding="ascii") as handle:
            handle.write("1")


def pruefe_espeak(phrase, reject, ueber_speak=False):
    wurzel = tempfile.mkdtemp(prefix="omaclusive-espeak-")
    wav = os.path.join(wurzel, "out.wav")
    espeak_attrappe(wurzel)
    alt_path = os.environ.get("PATH", "")
    alt_reject = os.environ.pop("OMACLUSIVE_ESPEAK_REJECT", None)
    os.environ["PATH"] = wurzel + os.pathsep + alt_path
    os.environ["OMACLUSIVE_ESPEAK_WURZEL"] = wurzel
    if reject:
        os.environ["OMACLUSIVE_ESPEAK_REJECT"] = "1"
    fertig, snaps = [False], []
    thread = threading.Thread(target=befehl_beobachten, args=(wurzel, fertig, snaps))
    thread.start()
    try:
        try:
            if ueber_speak:
                ok = bausteine.speak(phrase, "espeak", nr=31)
            else:
                ok = bausteine._synth_espeak(phrase, wav)
        finally:
            fertig[0] = True
            thread.join(8)
            os.environ["PATH"] = alt_path
            os.environ.pop("OMACLUSIVE_ESPEAK_REJECT", None)
            if alt_reject is not None:
                os.environ["OMACLUSIVE_ESPEAK_REJECT"] = alt_reject
        assert ok is True, phrase
        assert snaps, "Befehlszeile von espeak-ng war nicht sichtbar"
        roh_args = []
        for zeile in open(os.path.join(wurzel, "argv.log"), encoding="utf-8"):
            if zeile.strip():
                roh_args.append(json.loads(zeile))
        assert roh_args, "espeak-ng wurde nicht aufgerufen"
        for roh in snaps:
            assert phrase.encode("utf-8") not in roh, roh
        for args in roh_args:
            assert all(phrase not in teil for teil in args), args
        geliefert = open(os.path.join(wurzel, "text"), encoding="utf-8").read()
        assert phrase in geliefert, geliefert
        datei_modi = []
        for args in roh_args:
            if "-f" in args:
                datei_modi.append(geliefert.split("\n", 1)[0])
                assert not os.path.exists(args[args.index("-f") + 1]), args
        if datei_modi:
            assert datei_modi[-1] == "600", geliefert
        else:
            assert any("--stdin" in args for args in roh_args), roh_args
            assert geliefert.startswith("stdin\n")
    finally:
        shutil.rmtree(wurzel, ignore_errors=True)


# espeak-Fallback über speak(): Satz auf stdin, nicht in /proc/cmdline.
# Ohne --stdin: private Datei 0600, der Satz bleibt aus der Befehlszeile.
pruefe_espeak("GEHEIM-Nägele-7f29-stdin", False, ueber_speak=True)
pruefe_espeak("GEHEIM-Nägele-7f29-datei", True)
print("ANSAGE_OK einzeln %.2f s, zwei Wörter %.2f s" % (einzeln, zwei))
