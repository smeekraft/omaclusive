#!/usr/bin/env python3
"""Offline-Ohr. Hört nur die gezeigten Wörter, auf diesem Rechner, ohne Netz.

Das Modell ist Vosk small-de (Deutsch) oder small-en-us (Englisch, Ordner ohr/model-en). Die Bibliothek ist libvosk. Beides liegt im Ordner ohr.
"""
import ctypes
from i18n import language
import json
import os
import select
import shutil
import signal
import subprocess
import threading
import time

DIR = os.path.dirname(os.path.abspath(__file__))
OHR = os.path.join(DIR, "ohr")
LIB = os.path.join(OHR, "libvosk.so")
MODELL = os.path.join(OHR, "model")  # Deutsch (vosk-model-small-de)
MODELL_EN = os.path.join(OHR, "model-en")  # Englisch (vosk-model-small-en-us), optional


def modell_pfad():
    return MODELL if language() == "de" else MODELL_EN

_lock = threading.Lock()
_lib = None
_model = None
_fehler = ""


def _bibliothek():
    global _lib, _fehler
    if _lib:
        return _lib
    if not os.path.isfile(LIB) or not os.path.isdir(modell_pfad()):
        _fehler = "kein-ohr"
        return None
    try:
        lib = ctypes.CDLL(LIB)
        lib.vosk_set_log_level.argtypes = [ctypes.c_int]
        lib.vosk_set_log_level(-1)
        lib.vosk_model_new.argtypes = [ctypes.c_char_p]
        lib.vosk_model_new.restype = ctypes.c_void_p
        lib.vosk_model_free.argtypes = [ctypes.c_void_p]
        lib.vosk_recognizer_new_grm.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_char_p]
        lib.vosk_recognizer_new_grm.restype = ctypes.c_void_p
        lib.vosk_recognizer_accept_waveform.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        lib.vosk_recognizer_accept_waveform.restype = ctypes.c_int
        lib.vosk_recognizer_result.argtypes = [ctypes.c_void_p]
        lib.vosk_recognizer_result.restype = ctypes.c_char_p
        lib.vosk_recognizer_final_result.argtypes = [ctypes.c_void_p]
        lib.vosk_recognizer_final_result.restype = ctypes.c_char_p
        lib.vosk_recognizer_reset.argtypes = [ctypes.c_void_p]
        lib.vosk_recognizer_free.argtypes = [ctypes.c_void_p]
        _lib = lib
        return lib
    except OSError:
        _fehler = "kein-ohr"
        return None


def laden():
    global _model, _fehler
    with _lock:
        if _model:
            return True
        if _fehler:
            return False
        lib = _bibliothek()
        if not lib:
            return False
        try:
            _model = lib.vosk_model_new(modell_pfad().encode())
        except OSError:
            _model = None
        if not _model:
            _fehler = "kein-ohr"
            return False
        return True


def _quelle():
    if not shutil.which("pactl") or not shutil.which("ffmpeg"):
        return ""
    try:
        lauf = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    name = (lauf.stdout or "").strip()
    if not name or "monitor" in name.lower():
        return ""
    return name


def _satz(roh):
    if not roh:
        return ""
    if isinstance(roh, bytes):
        roh = roh.decode("utf-8", "replace")
    try:
        obj = json.loads(roh)
    except (TypeError, ValueError):
        return ""
    text = str(obj.get("text") or "").strip()
    if not text or text == "[unk]":
        return ""
    return text


def _hoer(woerter, quelle):
    lib = _lib
    grammar = json.dumps(list(woerter) + ["[unk]"], ensure_ascii=False).encode()
    rec = lib.vosk_recognizer_new_grm(_model, 16000.0, grammar)
    if not rec:
        return ""
    proc = subprocess.Popen(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-f", "pulse", "-i", quelle,
            "-ac", "1", "-ar", "16000",
            "-f", "s16le", "-t", "5",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    text = ""
    try:
        ende = time.time() + 4.0
        while time.time() < ende:
            bereit, _, _ = select.select([proc.stdout], [], [], 0.4)
            if not bereit:
                if proc.poll() is not None:
                    break
                continue
            daten = proc.stdout.read(8000)
            if not daten:
                break
            puffer = (ctypes.c_char * len(daten)).from_buffer_copy(daten)
            if lib.vosk_recognizer_accept_waveform(rec, ctypes.cast(puffer, ctypes.c_void_p), len(daten)):
                text = _satz(lib.vosk_recognizer_result(rec))
                if text:
                    break
                lib.vosk_recognizer_reset(rec)
        if not text:
            text = _satz(lib.vosk_recognizer_final_result(rec))
        return text
    finally:
        lib.vosk_recognizer_free(rec)
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                pass
        try:
            proc.stdout.close()
        except OSError:
            pass


def hoeren(woerter):
    """Nimmt kurz das Mikrofon auf und liefert den erkannten Text. Kein Monitor, keine Lautstärke."""
    sauber = []
    for wort in woerter or []:
        text = " ".join(str(wort).split())
        if text and text not in sauber and len(text) <= 80:
            sauber.append(text)
        if len(sauber) >= 8:
            break
    if not sauber:
        return {"ok": False, "grund": "fehler", "text": ""}
    if not laden():
        return {"ok": False, "grund": _fehler or "kein-ohr", "text": ""}
    quelle = _quelle()
    if not quelle:
        return {"ok": False, "grund": "kein-mikro", "text": ""}
    try:
        import bausteine
        bausteine.warte_bis_still()
    except Exception:
        pass
    time.sleep(0.6)
    try:
        with _lock:
            text = _hoer(sauber, quelle)
    except Exception:
        return {"ok": False, "grund": "fehler", "text": ""}
    return {"ok": True, "text": text, "grund": ""}
