#!/usr/bin/env python3
"""Eingebaute Aktionen der Bild-Fernbedienung.

Nur feste Befehle, keine Shell. Netzwerk: NetworkManager (nmcli) oder iwd (iwctl).
Vorlesen: Piper mit der Stimme Thorsten, sonst espeak-ng. Beides offline.
"""
from i18n import tr, language
import json, math, os, re, shutil, signal, struct, subprocess, tempfile, threading, time, wave

DIR = os.path.dirname(os.path.abspath(__file__))
SINK = "@DEFAULT_AUDIO_SINK@"
_lock = threading.Lock()
_player = None
_out_flag = None
_letzte_nr = 0  # neueste Ansage-Nummer vom Browser: verspätete ältere Anfragen werden verworfen
AUFNAHME_TEMPO = 1.15  # so langsam sind die mitgelieferten Aufnahmen in audio/ (siehe audio_erzeugen.py)
LOGDATEI = os.path.expanduser("~/.local/share/omaclusive/log.txt")


def log(text):
    """Schreibt Fehler der Ansage in ~/.local/share/omaclusive/log.txt (klein gehalten)."""
    try:
        os.makedirs(os.path.dirname(LOGDATEI), exist_ok=True)
        if os.path.isfile(LOGDATEI) and os.path.getsize(LOGDATEI) > 200000:
            os.replace(LOGDATEI, LOGDATEI + ".1")
        with open(LOGDATEI, "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(text)[:300] + "\n")
    except OSError:
        pass


def which(name):
    return shutil.which(name)


def service_active(name):
    try:
        r = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.stdout.strip() == "active"


def wifi_backend():
    """NetworkManager hat Vorrang, wenn der Dienst läuft. Sonst iwd."""
    if which("nmcli") and service_active("NetworkManager"):
        return "networkmanager"
    if which("iwctl") and service_active("iwd"):
        return "iwd"
    if which("nmcli"):
        return "networkmanager"
    if which("iwctl"):
        return "iwd"
    return None


def run(cmd, timeout=8):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def clean_text(text):
    text = re.sub(r"[\x00-\x1f]+", " ", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]


def piper_bin():
    local = os.path.join(DIR, "piper", "piper")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    found = which("piper-tts")
    return found or None


VOICES = {
    "de": ("de_DE-thorsten-medium.onnx", "de_DE-thorsten-high.onnx", "de_DE-thorsten-low.onnx"),
    "en": ("en_US-ljspeech-medium.onnx", "en_US-ljspeech-high.onnx", "en_US-kristin-medium.onnx"),
}


def voice_model(lang=None):
    lang = lang or language()
    for name in VOICES.get(lang, VOICES["en"]):
        path = os.path.join(DIR, "voices", name)
        if os.path.isfile(path):
            return path
    root = "/usr/share/piper-voices"
    if os.path.isdir(root):
        for dirpath, _, files in os.walk(root):
            for fname in files:
                if fname.endswith(".onnx") and (
                    ("thorsten" in fname) if lang == "de" else fname.startswith("en_")
                ):
                    return os.path.join(dirpath, fname)
    return None


def engine():
    if piper_bin() and voice_model():
        return "piper"
    if which("espeak-ng"):
        return "espeak-ng"
    return "keine"


def stop_speak():
    global _player
    if _player and _player.poll() is None:
        try:
            os.killpg(_player.pid, signal.SIGTERM)
        except OSError:
            pass
    _player = None


_tempo_cache = {"mtime": None, "wert": AUFNAHME_TEMPO}


def tempo():
    """Piper-Tempo (length_scale) aus config.json, Schluessel "stimmeTempo".
    Standard 1.15 (etwas langsamer als Piper-Original), groesser = langsamer. Erlaubt 0.5 bis 2.0.
    Fehlt er oder ist er ungueltig: 1.15."""
    pfad = os.path.join(DIR, "config.json")
    try:
        mtime = os.path.getmtime(pfad)
    except OSError:
        return AUFNAHME_TEMPO
    if _tempo_cache["mtime"] != mtime:
        wert = AUFNAHME_TEMPO
        try:
            with open(pfad, encoding="utf-8") as handle:
                daten = json.load(handle)
            roh = daten.get("stimmeTempo") if isinstance(daten, dict) else None
            if roh is not None and not isinstance(roh, bool):
                zahl = float(roh)
                if zahl == zahl and 0.5 <= zahl <= 2.0:
                    wert = round(zahl, 2)
        except (OSError, ValueError, TypeError):
            pass
        _tempo_cache.update(mtime=mtime, wert=wert)
    return _tempo_cache["wert"]


def _synth_piper(text, wav):
    binary = piper_bin()
    model = voice_model()
    if not binary or not model:
        return False
    env = os.environ.copy()
    folder = os.path.dirname(binary)
    env["LD_LIBRARY_PATH"] = folder + ((":" + env["LD_LIBRARY_PATH"]) if env.get("LD_LIBRARY_PATH") else "")
    global _out_flag
    if not _out_flag:
        _out_flag = "--output_file"
        try:
            help_run = subprocess.run([binary, "--help"], capture_output=True, text=True, timeout=5, env=env)
            help_text = (help_run.stdout or "") + (help_run.stderr or "")
            if "--output_file" not in help_text and "-f" in help_text:
                _out_flag = "-f"
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        cmd = [binary, "--model", model, "--espeak_data", os.path.join(folder, "espeak-ng-data"), _out_flag, wav]
        if tempo() != 1.0:
            cmd += ["--length_scale", str(tempo())]
        r = subprocess.run(cmd, input=text + "\n", text=True, capture_output=True, env=env, cwd=folder, timeout=40)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and os.path.isfile(wav) and os.path.getsize(wav) > 44


def _synth_espeak(text, wav):
    binary = which("espeak-ng")
    if not binary:
        return False
    try:
        r = subprocess.run([binary, "-v", language(), "-w", wav, text], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and os.path.isfile(wav) and os.path.getsize(wav) > 44


_phrase_wav = {}
_phrase_order = []
_PHRASE_MAX = 48


def _play(wav):
    """Startet den Player. Gibt True zurück, wenn er läuft. Fehler kommen ins Log."""
    global _player
    kandidaten = []
    if which("pw-play"):
        kandidaten.append(["pw-play", wav])
    if which("paplay"):
        kandidaten.append(["paplay", wav])
    if which("mpv"):
        kandidaten.append(["mpv", "--no-video", "--really-quiet", wav])
    if not kandidaten:
        log("Kein Player gefunden (pw-play, paplay oder mpv fehlt)")
        return False
    for cmd in kandidaten:
        try:
            _player = subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError as fehler:
            log("Player %s startet nicht: %s" % (cmd[0], fehler))
    _player = None
    return False


def _ist_wegwerf(pfad):
    """True nur fuer Dateien im Temp-Ordner, nie fuer mitgelieferte Aufnahmen in audio/
    (auch wenn das Repo selbst unter /tmp liegt)."""
    if not pfad:
        return False
    echt = os.path.realpath(pfad)
    temp = os.path.realpath(tempfile.gettempdir()) + os.sep
    audio = os.path.realpath(os.path.join(DIR, "audio")) + os.sep
    return echt.startswith(temp) and not echt.startswith(audio)


def _loesche_temp(pfad):
    """Loescht nur Wegwerf-Dateien im Temp-Ordner, nie mitgelieferte Aufnahmen."""
    if _ist_wegwerf(pfad):
        try:
            os.remove(pfad)
        except OSError:
            pass


def _remember_phrase(key, wav):
    if key not in _phrase_wav:
        _phrase_order.append(key)
    _phrase_wav[key] = wav
    while len(_phrase_order) > _PHRASE_MAX:
        old = _phrase_order.pop(0)
        path = _phrase_wav.pop(old, None)
        if path and path != wav and _ist_wegwerf(path):
            try:
                os.remove(path)
            except OSError:
                pass


def _key(stimme, text):
    lang = language()
    if tempo() != 1.0:
        stimme = stimme + "@" + str(tempo())
    return (stimme + "\0" + text) if lang == "de" else (lang + "\0" + stimme + "\0" + text)


_audio_index = {}


def _vorgefertigt(text, stimme):
    """Fertige Aufnahme aus audio/<sprache>/ (Piper-Stimme). Sonst None.
    Nur fuer die Standardstimme; wer espeak waehlt, bekommt espeak."""
    if stimme == "espeak" or tempo() != AUFNAHME_TEMPO:
        return None
    lang = language()
    if lang not in _audio_index:
        try:
            with open(os.path.join(DIR, "audio", lang, "index.json"), encoding="utf-8") as handle:
                daten = json.load(handle)
        except (OSError, ValueError):
            daten = {}
        _audio_index[lang] = daten if isinstance(daten, dict) else {}
    name = _audio_index[lang].get(text)
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
        return None
    path = os.path.join(DIR, "audio", lang, name)
    if os.path.isfile(path) and os.path.getsize(path) > 44:
        return path
    return None


def _synthese(text, stimme):
    """Erzeugt eine WAV, spielt sie nicht ab."""
    fd, wav = tempfile.mkstemp(prefix="omaclusive-sprache-", suffix=".wav")
    os.close(fd)
    if stimme == "espeak":
        ok = _synth_espeak(text, wav)
    else:
        ok = _synth_piper(text, wav) or _synth_espeak(text, wav)
    if not ok:
        try:
            os.remove(wav)
        except OSError:
            pass
        return None
    return wav


def _wav_da(key):
    wav = _phrase_wav.get(key)
    if wav and os.path.isfile(wav) and os.path.getsize(wav) > 44:
        return wav
    return None


def sprache_vorab(texte, stimme="piper"):
    """Legt Ansagen vorher in den Zwischenspeicher. Spielt nichts ab."""
    if stimme not in ("piper", "espeak"):
        stimme = ""
    gemacht = 0
    gesehen = set()
    for roh in texte or []:
        text = clean_text(roh)
        if not text or text in gesehen:
            continue
        gesehen.add(text)
        key = _key(stimme, text)
        with _lock:
            if _wav_da(key):
                gemacht += 1
                continue
        wav = _vorgefertigt(text, stimme) or _synthese(text, stimme)
        if not wav:
            continue
        with _lock:
            if _wav_da(key):
                _loesche_temp(wav)
            else:
                _remember_phrase(key, wav)
        gemacht += 1
    return gemacht


def _texte_plugins(texte):
    wurzel = os.path.join(DIR, "plugins")
    try:
        with open(os.path.join(wurzel, "index.json"), encoding="utf-8") as handle:
            ids = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(ids, list):
        return
    for pid in ids:
        if not isinstance(pid, str) or not re.fullmatch(r"[a-z0-9_-]{1,40}", pid):
            continue
        try:
            daten = None
            lang = language()
            namen = ["plugin.json"] if lang == "de" else ["plugin." + lang + ".json", "plugin.json"]
            for datei in namen:
                try:
                    with open(os.path.join(wurzel, pid, datei), encoding="utf-8") as handle:
                        daten = json.load(handle)
                    break
                except (OSError, json.JSONDecodeError):
                    continue
        except OSError:
            continue
        if daten is None:
            continue
        if not isinstance(daten, dict):
            continue
        for feld in ("name", "sprechen"):
            if daten.get(feld):
                texte.append(str(daten[feld]))
        for karte in daten.get("karten") or []:
            if not isinstance(karte, dict):
                continue
            for feld in ("wort", "sprechen"):
                if karte.get(feld):
                    texte.append(str(karte[feld]))
            aktion = karte.get("aktion") or {}
            if isinstance(aktion, dict) and aktion.get("text"):
                texte.append(str(aktion["text"]))


def texte_aus_config(config):
    """Sammelt die festen Ansagen, damit sie vor dem ersten Antippen da sind."""
    texte = [
        tr("Gleich zurück zum Start."),
        tr("Du bist am Start."),
        tr("Nicht gemacht."),
        tr("Nein."),
        tr("Ja."),
        tr("Zurück."),
        tr("Andere."),
        tr("Wirklich?"),
        tr("Der Ruf ist nicht rausgegangen."),
        tr("Der Ruf ist raus."),
        tr("Ich rufe."),
        tr("Das ist ein Test."),
        tr("Der Test ist nicht rausgegangen."),
        tr("Jemand hat deinen Ruf gesehen."),
        tr("Hier ist noch nichts."),
        tr("Das geht hier nicht."),
        tr("Es startet mit dem Rechner."),
        tr("Noch leer"),
    ]
    _texte_plugins(texte)
    if not isinstance(config, dict):
        return texte
    feste = config.get("feste") or {}
    if isinstance(feste, dict):
        for eintrag in feste.values():
            if isinstance(eintrag, dict) and eintrag.get("wort"):
                texte.append(str(eintrag["wort"]))
    screens = config.get("screens") or {}
    if isinstance(screens, dict):
        for screen in screens.values():
            if not isinstance(screen, dict):
                continue
            if screen.get("name"):
                texte.append(str(screen["name"]))
            liste = list(screen.get("liste") or [])
            for seite in ("left", "right"):
                if screen.get(seite):
                    liste.append(screen.get(seite))
            for card in liste:
                if not isinstance(card, dict):
                    continue
                for feld in ("wort", "sprechen", "label"):
                    if card.get(feld):
                        texte.append(str(card[feld]))
                aktion = card.get("aktion") or {}
                if isinstance(aktion, dict):
                    for feld in ("text", "leer", "offen"):
                        if aktion.get(feld):
                            texte.append(str(aktion[feld]))
                if card.get("abbruch"):
                    texte.append(str(card["abbruch"]))
    import hilferuf
    eintrag = config.get("hilferuf") if isinstance(config.get("hilferuf"), dict) else {}
    texte.append(hilferuf.gesehen_satz(eintrag.get("name")))
    fertig = []
    gesehen = set()
    for text in texte:
        text = clean_text(text)
        if text and text not in gesehen:
            gesehen.add(text)
            fertig.append(text)
    return fertig


def _wav_fuer(text, stimme):
    """Gibt den Pfad zur WAV für einen Satz zurück (fertige Aufnahme, Zwischenspeicher oder neu erzeugt)."""
    key = _key(stimme, text)
    with _lock:
        vorhanden = _wav_da(key)
    if not vorhanden:
        vorhanden = _vorgefertigt(text, stimme) or _synthese(text, stimme)
        if not vorhanden:
            log("Keine Stimme für: " + text)
            return None
        with _lock:
            andere = _wav_da(key)
            if andere:
                _loesche_temp(vorhanden)
                vorhanden = andere
            else:
                _remember_phrase(key, vorhanden)
    return vorhanden


def _pause_wav(dauer_s, rate, kanaele, breite):
    return b"\x00" * (int(rate * dauer_s) * kanaele * breite)


def _verbinde(wavs, pause_s=0.35):
    """Hängt kurze Aufnahmen mit einer Pause zu einer Datei zusammen. None, wenn die Formate nicht passen."""
    fd, ziel = tempfile.mkstemp(prefix="omaclusive-sprache-", suffix=".wav")
    os.close(fd)
    try:
        params = None
        with wave.open(ziel, "wb") as aus:
            for i, pfad in enumerate(wavs):
                with wave.open(pfad, "rb") as ein:
                    p = (ein.getnchannels(), ein.getsampwidth(), ein.getframerate())
                    if params is None:
                        params = p
                        aus.setnchannels(p[0]); aus.setsampwidth(p[1]); aus.setframerate(p[2])
                    elif p != params:
                        raise ValueError("Formate verschieden")
                    if i:
                        aus.writeframes(_pause_wav(pause_s, p[2], p[0], p[1]))
                    aus.writeframes(ein.readframes(ein.getnframes()))
        return ziel
    except (OSError, ValueError, wave.Error, EOFError):
        _loesche_temp(ziel)
        return None


def speak(text, stimme="", nr=None):
    """Spricht einen kurzen Satz oder eine Liste kurzer Wörter ("Filme", "Bilder") nacheinander.
    Gleiche Sätze werden wiederverwendet. Piper zuerst, sonst espeak-ng.
    Eine neue Ansage stoppt die laufende. nr: Nummer vom Browser, ältere Anfragen werden verworfen,
    damit nichts doppelt oder in falscher Reihenfolge spielt."""
    global _letzte_nr
    teile = text if isinstance(text, (list, tuple)) else [text]
    teile = [t for t in (clean_text(x) for x in teile[:6]) if t]
    if not teile:
        return False
    if stimme not in ("piper", "espeak"):
        stimme = ""
    if nr is not None:
        with _lock:
            if nr < _letzte_nr:
                return True  # veraltet: die neuere Ansage spielt schon
            _letzte_nr = nr
    if len(teile) == 1:
        vorhanden = _wav_fuer(teile[0], stimme)
    else:
        gesamt = " ".join(teile)
        key = _key(stimme, "\x01" + gesamt)
        with _lock:
            vorhanden = _wav_da(key)
        if not vorhanden:
            einzeln = [_wav_fuer(t, stimme) for t in teile]
            if all(einzeln):
                vorhanden = _verbinde(einzeln)
            if not vorhanden:
                vorhanden = _wav_fuer(". ".join(teile) + ".", stimme)
            elif vorhanden:
                with _lock:
                    _remember_phrase(key, vorhanden)
    if not vorhanden:
        return False
    with _lock:
        if nr is not None and nr < _letzte_nr:
            return True
        stop_speak()
        return _play(vorhanden)


def warte_bis_still(grenze=12):
    """Wartet, bis das Vorlesen zu Ende ist. Ändert die Lautstärke nicht."""
    ende = time.time() + grenze
    while time.time() < ende:
        with _lock:
            laeuft = _player is not None and _player.poll() is None
        if not laeuft:
            return
        time.sleep(0.05)


def volume_state():
    r = run(["wpctl", "get-volume", SINK])
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", r.stdout)
    level = float(match.group(1)) if match else 0.0
    muted = "MUTED" in r.stdout.upper()
    return int(round(level * 100)), muted


def phrase_volume():
    percent, muted = volume_state()
    if muted or percent == 0:
        return tr("Ton ist aus")
    return tr("Lautstärke {} Prozent").format(percent)


def volume_up():
    run(["wpctl", "set-mute", SINK, "0"])
    run(["wpctl", "set-volume", "-l", "1.0", SINK, "5%+"])
    return phrase_volume()


def volume_down():
    run(["wpctl", "set-volume", SINK, "5%-"])
    return phrase_volume()


def volume_mute():
    run(["wpctl", "set-mute", SINK, "toggle"])
    return phrase_volume()


def phrase_media():
    if not which("playerctl"):
        return ""
    status = run(["playerctl", "status"])
    if status.returncode != 0:
        return ""
    state = status.stdout.strip()
    if state == "Playing":
        return tr("Es läuft")
    if state == "Paused":
        return tr("Pause")
    return ""


def media_playpause():
    if not which("playerctl"):
        return tr("Pause geht nicht")
    result = run(["playerctl", "play-pause"])
    if result.returncode != 0:
        return tr("Es läuft nichts")
    state = phrase_media()
    if state == tr("Es läuft"):
        return tr("Weiter")
    if state == tr("Pause"):
        return tr("Pause")
    return tr("Es läuft nichts")


def _nm_ssid():
    result = run(["nmcli", "-t", "-f", "TYPE,NAME", "connection", "show", "--active"])
    for line in result.stdout.splitlines():
        if line.startswith("802-11-wireless:"):
            name = line.split(":", 1)[1]
            return name.replace(r"\:", ":").replace(r"\\", "\\").strip()
    return ""


def _wlan_nm():
    radio = run(["nmcli", "radio", "wifi"])
    if radio.returncode != 0:
        return tr("WLAN ist nicht erreichbar")
    if radio.stdout.strip().lower() != "enabled":
        return tr("WLAN ist aus")
    name = _nm_ssid()
    if name:
        return tr("WLAN ist an, {}").format(clean_text(name))
    return tr("WLAN ist an")


def _wlan_iwd():
    listed = run(["iwctl", "station", "list"])
    names = []
    for line in listed.stdout.splitlines():
        match = re.match(r"\s*(wlan\S+)", line)
        if match:
            names.append(match.group(1))
    if not names:
        return tr("WLAN ist nicht erreichbar")
    show = run(["iwctl", "station", names[0], "show"])
    text = show.stdout
    if re.search(r"Powered\s+no", text, re.I):
        return tr("WLAN ist aus")
    match = re.search(r"Connected network\s+(.+)", text)
    if match:
        name = match.group(1).strip()
        if name and name != "-":
            return tr("WLAN ist an, {}").format(clean_text(name))
    return tr("WLAN ist an")


def status_wlan():
    backend = wifi_backend()
    if backend == "networkmanager":
        return _wlan_nm()
    if backend == "iwd":
        return _wlan_iwd()
    return tr("WLAN ist nicht erreichbar")


def status_kurz():
    parts = [status_wlan(), phrase_volume()]
    media = phrase_media()
    if media:
        parts.append(media)
    return ". ".join(parts)


def screen_lock():
    result = run(["loginctl", "lock-session"])
    if result.returncode != 0:
        return tr("Sperren geht nicht")
    return tr("Bildschirm ist gesperrt")


def poweroff():
    run(["systemctl", "poweroff"])
    return tr("Der Rechner geht aus")


def reboot():
    run(["systemctl", "reboot"])
    return tr("Der Rechner startet neu")


_MAC = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
_last_ssids = set()
_last_saved = set()
_last_security = {}
_last_macs = set()


def split_nmcli(line):
    parts, buf, esc = [], [], False
    for ch in line:
        if esc:
            buf.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def _short(name, n=14):
    name = clean_text(name)
    if len(name) <= n:
        return name
    return name[: n - 1] + "…"


def wifi_device_nm():
    result = run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"])
    for line in result.stdout.splitlines():
        parts = split_nmcli(line)
        if len(parts) >= 2 and parts[1].strip() == "wifi" and parts[0].strip():
            return parts[0].strip()
    return ""


def wifi_is_on():
    backend = wifi_backend()
    if backend == "networkmanager":
        result = run(["nmcli", "radio", "wifi"])
        return result.stdout.strip().lower() == "enabled"
    if backend == "iwd":
        device = iwd_device()
        if not device:
            return False
        show = run(["iwctl", "device", device, "show"])
        return not re.search(r"Powered\s+no", show.stdout, re.I)
    return False


def iwd_device():
    listed = run(["iwctl", "device", "list"])
    for line in listed.stdout.splitlines():
        match = re.match(r"\s*(wlan\S+)", line)
        if match:
            return match.group(1)
    return ""


def iwd_station():
    listed = run(["iwctl", "station", "list"])
    for line in listed.stdout.splitlines():
        match = re.match(r"\s*(wlan\S+)", line)
        if match:
            return match.group(1)
    return iwd_device()


def saved_ssids_nm():
    result = run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    names = set()
    for line in result.stdout.splitlines():
        parts = split_nmcli(line)
        if len(parts) >= 2 and "wireless" in parts[1]:
            names.add(parts[0])
    return names


def is_open(security):
    return str(security or "").strip().lower() in ("", "--", "none", "open", "owe")


def parse_iwd_networks(text):
    nets = []
    for line in text.splitlines():
        if "Network" in line or not line.strip() or set(line.strip()) <= {"-"}:
            continue
        match = re.match(r"\s*(.+?)\s{2,}(\S+)\s+(\S+)\s*$", line)
        if not match:
            continue
        name = match.group(1).strip().lstrip(">* ").strip()
        if not name:
            continue
        nets.append({"ssid": name, "security": match.group(2), "signal": match.group(3)})
    return nets


_wifi_cache = None
_bt_cache = None
_SCAN_TTL = 25


def _fresh(cache):
    if cache and time.time() - cache[0] < _SCAN_TTL:
        return cache[1]
    return None


def _forget_wifi():
    global _wifi_cache
    _wifi_cache = None


def _forget_bt():
    global _bt_cache
    _bt_cache = None


def scan_wifi():
    global _wifi_cache
    cached = _fresh(_wifi_cache)
    if cached is not None:
        return cached
    rows = _scan_wifi_now()
    _wifi_cache = (time.time(), rows)
    return rows


def _scan_wifi_now():
    backend = wifi_backend()
    if backend == "networkmanager":
        if not wifi_device_nm():
            return []
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "dev", "wifi", "list", "--rescan", "yes"],
            capture_output=True, text=True, timeout=25,
        )
        saved = saved_ssids_nm()
        best = {}
        for line in result.stdout.splitlines():
            parts = split_nmcli(line)
            if len(parts) < 3:
                continue
            ssid = parts[0].strip()
            if not ssid:
                continue
            try:
                signal = int(parts[1] or 0)
            except ValueError:
                signal = 0
            security = parts[2]
            used = len(parts) > 3 and parts[3].strip() == "*"
            prev = best.get(ssid)
            if not prev or signal > prev["signal"]:
                best[ssid] = {"ssid": ssid, "signal": signal, "security": security, "used": used, "saved": ssid in saved}
        rows = list(best.values())
        rows.sort(key=lambda n: (not n["used"], not n["saved"], -n["signal"]))
        return rows[:12]
    if backend == "iwd":
        station = iwd_station()
        if not station:
            return []
        subprocess.run(["iwctl", "station", station, "scan"], capture_output=True, text=True, timeout=15)
        result = run(["iwctl", "station", station, "get-networks"], timeout=10)
        rows = []
        for net in parse_iwd_networks(result.stdout)[:12]:
            rows.append({"ssid": net["ssid"], "signal": 0, "security": net["security"], "used": False, "saved": net["security"] == "open"})
        return rows
    return []


def wlan_on():
    _forget_wifi()
    backend = wifi_backend()
    if backend == "networkmanager":
        run(["nmcli", "radio", "wifi", "on"], timeout=10)
    elif backend == "iwd":
        device = iwd_device()
        if device:
            run(["iwctl", "device", device, "set-property", "Powered", "on"], timeout=10)
    return status_wlan()


def wlan_off():
    _forget_wifi()
    backend = wifi_backend()
    if backend == "networkmanager":
        run(["nmcli", "radio", "wifi", "off"], timeout=10)
    elif backend == "iwd":
        device = iwd_device()
        if device:
            run(["iwctl", "device", device, "set-property", "Powered", "off"], timeout=10)
    return status_wlan()


def wlan_connect(ssid):
    ssid = clean_text(ssid)[:64]
    if not ssid or ssid not in _last_ssids:
        return tr("Das Netz gibt es nicht")
    security = _last_security.get(ssid, "")
    if security and not is_open(security) and ssid not in _last_saved:
        return tr("Dafür fehlt das Passwort")
    if not wifi_is_on():
        wlan_on()
    _forget_wifi()
    backend = wifi_backend()
    if backend == "networkmanager":
        result = subprocess.run(
            ["nmcli", "-w", "20", "dev", "wifi", "connect", ssid],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=25,
        )
        if result.returncode == 0:
            return tr("Verbunden mit {}").format(ssid)
        return tr("Verbinden hat nicht geklappt")
    if backend == "iwd":
        station = iwd_station()
        if not station:
            return tr("Kein WLAN-Gerät")
        result = subprocess.run(
            ["iwctl", "station", station, "connect", ssid],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=25,
        )
        if result.returncode == 0:
            return tr("Verbunden mit {}").format(ssid)
        return tr("Verbinden hat nicht geklappt")
    return tr("WLAN ist nicht erreichbar")


def wlan_cards():
    global _last_ssids, _last_saved, _last_security
    cards = []
    if wifi_is_on():
        cards.append({
            "wort": tr("Aus"), "sprechen": tr("WLAN aus"), "bild": "img/wlan-aus.svg",
            "bestaetigen": True, "aktion": {"typ": "baustein", "name": "wlan.off"},
        })
    else:
        cards.append({
            "wort": tr("An"), "sprechen": tr("WLAN an"), "bild": "img/wlan.svg",
            "aktion": {"typ": "baustein", "name": "wlan.on"},
        })
    nets = scan_wifi()
    _last_ssids = {n["ssid"] for n in nets}
    _last_saved = {n["ssid"] for n in nets if n.get("saved")}
    _last_security = {n["ssid"]: n.get("security", "") for n in nets}
    if not nets and wifi_backend() == "networkmanager" and not wifi_device_nm():
        cards.append({
            "wort": tr("Kein Gerät"), "sprechen": tr("Kein WLAN-Gerät"), "bild": "img/wlan-aus.svg",
            "aktion": {"typ": "baustein", "name": "wlan.none"},
        })
    elif not nets:
        cards.append({
            "wort": tr("Keine"), "sprechen": tr("Kein Netz gefunden"), "bild": "img/wlan-aus.svg",
            "aktion": {"typ": "baustein", "name": "wlan.empty"},
        })
    else:
        for net in nets:
            cards.append({
                "wort": _short(net["ssid"]), "sprechen": net["ssid"], "bild": "img/wlan.svg",
                "aktion": {"typ": "baustein", "name": "wlan.connect", "ssid": net["ssid"]},
            })
    return cards


def parse_bt_devices(text):
    found = []
    for line in text.splitlines():
        match = re.match(r"^Device\s+([0-9A-Fa-f:]{17})\s+(.*)$", line.strip())
        if match:
            found.append((match.group(1).upper(), match.group(2).strip() or match.group(1)))
    return found


def bt_is_on():
    if not which("bluetoothctl"):
        return False
    result = run(["bluetoothctl", "show"])
    return bool(re.search(r"Powered:\s+yes", result.stdout, re.I))


def bt_on():
    _forget_bt()
    run(["bluetoothctl", "power", "on"], timeout=10)
    return tr("Bluetooth ist an")


def bt_off():
    _forget_bt()
    run(["bluetoothctl", "power", "off"], timeout=10)
    return tr("Bluetooth ist aus")


def scan_bt():
    global _bt_cache
    cached = _fresh(_bt_cache)
    if cached is not None:
        return cached
    rows = _scan_bt_now()
    _bt_cache = (time.time(), rows)
    return rows


def _scan_bt_now():
    subprocess.run(["bluetoothctl", "--timeout", "4", "scan", "on"], capture_output=True, text=True, timeout=8)
    paired = parse_bt_devices(run(["bluetoothctl", "devices", "Paired"]).stdout)
    discovered = parse_bt_devices(run(["bluetoothctl", "devices"]).stdout)
    seen, out = set(), []
    for mac, name in paired + discovered:
        if mac in seen:
            continue
        seen.add(mac)
        out.append({"mac": mac, "name": name})
        if len(out) >= 12:
            break
    return out


def bt_connect(mac):
    mac = str(mac or "").upper().strip()
    if not _MAC.match(mac) or mac not in _last_macs:
        return tr("Das Gerät gibt es nicht")
    info = run(["bluetoothctl", "info", mac])
    name = ""
    connected = False
    for line in info.stdout.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("name:"):
            name = stripped.split(":", 1)[1].strip()
        if stripped.lower().startswith("connected:") and "yes" in stripped.lower():
            connected = True
    if connected:
        return tr("Schon verbunden, {}").format(name) if name else tr("Schon verbunden")
    _forget_bt()
    result = subprocess.run(
        ["bluetoothctl", "connect", mac],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20,
    )
    text = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0 or "Connection successful" in text:
        return tr("Verbunden, {}").format(name) if name else tr("Verbunden")
    return tr("Verbinden hat nicht geklappt")


def bt_cards():
    global _last_macs
    if not which("bluetoothctl"):
        return [{
            "wort": tr("Geht nicht"), "sprechen": tr("Bluetooth geht nicht"), "bild": "img/bluetooth.svg",
            "aktion": {"typ": "baustein", "name": "bt.missing"},
        }]
    cards = []
    if bt_is_on():
        cards.append({
            "wort": tr("Aus"), "sprechen": tr("Bluetooth aus"), "bild": "img/bluetooth-aus.svg",
            "bestaetigen": True, "aktion": {"typ": "baustein", "name": "bt.off"},
        })
        devices = scan_bt()
    else:
        cards.append({
            "wort": tr("An"), "sprechen": tr("Bluetooth an"), "bild": "img/bluetooth.svg",
            "aktion": {"typ": "baustein", "name": "bt.on"},
        })
        devices = []
    _last_macs = {d["mac"] for d in devices}
    if bt_is_on() and not devices:
        cards.append({
            "wort": tr("Keine"), "sprechen": tr("Kein Gerät gefunden"), "bild": "img/bluetooth-aus.svg",
            "aktion": {"typ": "baustein", "name": "bt.empty"},
        })
    for dev in devices:
        cards.append({
            "wort": _short(dev["name"]), "sprechen": dev["name"], "bild": "img/bluetooth.svg",
            "aktion": {"typ": "baustein", "name": "bt.connect", "mac": dev["mac"]},
        })
    return cards


def write_beep(path):
    rate = 22050
    with wave.open(path, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * 0.9)):
            t = i / rate
            on = (t % 0.45) < 0.22
            sample = int(24000 * math.sin(2 * math.pi * 880 * t)) if on else 0
            frames += struct.pack("<h", sample)
        handle.writeframes(frames)


def help_local():
    fd, wav = tempfile.mkstemp(prefix="omaclusive-hilfe-", suffix=".wav")
    os.close(fd)
    try:
        write_beep(wav)
        if which("pw-play"):
            cmd = ["pw-play", wav]
        elif which("paplay"):
            cmd = ["paplay", wav]
        else:
            cmd = ["mpv", "--no-video", "--really-quiet", wav]
        subprocess.run(cmd, timeout=5)
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass
    return tr("Hilfe")


def help_later():
    return tr("Das kommt noch")


def write_soft_tone(path):
    """Kurzer, leiser Ton als Hinweis vor der Rückkehr zum Start."""
    rate = 22050
    with wave.open(path, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        dur = int(rate * 0.22)
        for i in range(dur):
            t = i / float(rate)
            attack = min(1.0, i / (rate * 0.02))
            release = min(1.0, (dur - i) / (rate * 0.05))
            env = attack if attack < release else release
            sample = int(4500 * env * math.sin(2 * math.pi * 523.25 * t))
            frames += struct.pack("<h", max(-32767, min(32767, sample)))
        handle.writeframes(frames)


def hinweis_ton():
    fd, wav = tempfile.mkstemp(prefix="omaclusive-hinweis-", suffix=".wav")
    os.close(fd)
    try:
        write_soft_tone(wav)
        if which("pw-play"):
            cmd = ["pw-play", wav]
        elif which("paplay"):
            cmd = ["paplay", wav]
        elif which("mpv"):
            cmd = ["mpv", "--no-video", "--really-quiet", wav]
        else:
            return False
        subprocess.run(cmd, timeout=3)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass


def _brightness_percent():
    if not which("brightnessctl"):
        return None
    try:
        result = run(["brightnessctl", "-m"])
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in (result.stdout or "").splitlines():
        for part in line.split(","):
            if part.endswith("%") and part[:-1].isdigit():
                return part
    return None


def _brightness_step(up):
    if _brightness_percent() is None:
        return tr("Helligkeit geht hier nicht")
    try:
        run(["brightnessctl", "set", "5%+" if up else "5%-"])
    except (OSError, subprocess.TimeoutExpired):
        return tr("Helligkeit geht hier nicht")
    percent = _brightness_percent()
    if not percent:
        return tr("Heller") if up else tr("Dunkler")
    return tr("Helligkeit {}").format(percent)


def brightness_up():
    return _brightness_step(True)


def brightness_down():
    return _brightness_step(False)


def _user_dir(kind, names):
    home = os.path.abspath(os.path.expanduser("~"))
    if which("xdg-user-dir"):
        try:
            result = run(["xdg-user-dir", kind])
        except (OSError, subprocess.TimeoutExpired):
            result = None
        path = (result.stdout or "").strip() if result else ""
        if path and os.path.isdir(path) and os.path.abspath(path) != home:
            return path
    for name in names:
        path = os.path.join(home, name)
        if os.path.isdir(path):
            return path
    return None


def _open_folder(kind, names, fehlt, offen):
    path = _user_dir(kind, names)
    if not path:
        return fehlt
    if not which("xdg-open"):
        return tr("Öffnen geht nicht")
    subprocess.Popen(
        ["xdg-open", path],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return offen


def files_pictures():
    return _open_folder("PICTURES", ("Bilder", "Pictures", "Fotos"), tr("Der Fotos-Ordner fehlt."), tr("Fotos sind offen."))


def files_documents():
    return _open_folder("DOCUMENTS", ("Dokumente", "Documents"), tr("Der Dateien-Ordner fehlt."), tr("Dateien sind offen."))


def liste(quelle):
    if quelle == "wlan.list":
        return wlan_cards()
    if quelle == "bt.list":
        return bt_cards()
    return []


def _done(phrase):
    speak(phrase)
    return {"ok": True, "sagen": phrase}


def _ask():
    return {"ok": False, "bestaetigen": True, "sagen": tr("Wirklich?")}


# name -> Anzeige und Funktion. betreuer: nur nach Ja, nicht in der normalen Liste als Vorschlag ohne Hinweis.
_ITEMS = [
    ("volume.up", "Lauter", "img/lauter.svg", volume_up, False),
    ("volume.down", "Leiser", "img/leiser.svg", volume_down, False),
    ("volume.mute", "Stumm", "img/stumm.svg", volume_mute, False),
    ("media.playpause", "Pause", "img/pause.svg", media_playpause, False),
    ("status.kurz", "Sagen", "img/sagen.svg", status_kurz, False),
    ("status.wlan", "WLAN", "img/wlan.svg", status_wlan, False),
    ("status.volume", "Wie laut", "img/lauter.svg", phrase_volume, False),
    ("wlan.on", "An", "img/wlan.svg", wlan_on, False),
    ("bt.on", "An", "img/bluetooth.svg", bt_on, False),
    ("help.local", "Hilfe", "img/hilfe.svg", help_local, False),
    ("help.later", "Später", "img/spaeter.svg", help_later, False),
    ("brightness.up", "Heller", "img/sonne.svg", brightness_up, False),
    ("brightness.down", "Dunkler", "img/mond.svg", brightness_down, False),
    ("files.pictures", "Fotos", "img/fotos.svg", files_pictures, False),
    ("files.documents", "Dateien", "img/dateien.svg", files_documents, False),
    ("screen.lock", "Sperren", "img/sperren.svg", screen_lock, True),
    ("system.poweroff", "Aus", "img/aus.svg", poweroff, True),
    ("system.reboot", "Neu starten", "img/neu.svg", reboot, True),
]
_BY_NAME = {item[0]: item for item in _ITEMS}


def catalog():
    out = []
    for name, wort, bild, _fn, betreuer in _ITEMS:
        item = {"name": name, "wort": tr(wort), "bild": bild, "betreuer": betreuer}
        out.append(item)
    out.append({"name": "wlan.off", "wort": tr("WLAN aus"), "bild": "img/wlan-aus.svg", "betreuer": False, "bestaetigen": True})
    out.append({"name": "bt.off", "wort": tr("Bluetooth aus"), "bild": "img/bluetooth-aus.svg", "betreuer": False, "bestaetigen": True})
    out.append({"name": "wlan.list", "wort": tr("Netze"), "bild": "img/wlan.svg", "betreuer": False, "dynamisch": "wlan.list"})
    out.append({"name": "bt.list", "wort": tr("Geräte"), "bild": "img/bluetooth.svg", "betreuer": False, "dynamisch": "bt.list"})
    return out


def execute(name, confirm=False, extra=None):
    extra = extra or {}
    name = str(name or "")
    try:
        if name == "wlan.off":
            if not wifi_is_on():
                return _done(tr("WLAN ist aus"))
            if not confirm:
                return _ask()
            return _done(wlan_off())
        if name == "bt.off":
            if not bt_is_on():
                return _done(tr("Bluetooth ist aus"))
            if not confirm:
                return _ask()
            return _done(bt_off())
        if name == "wlan.connect":
            return _done(wlan_connect(extra.get("ssid", "")))
        if name == "bt.connect":
            return _done(bt_connect(extra.get("mac", "")))
        if name in ("wlan.none", "wlan.empty", "bt.empty", "bt.missing"):
            phrases = {
                "wlan.none": tr("Kein WLAN-Gerät"),
                "wlan.empty": tr("Kein Netz gefunden"),
                "bt.empty": tr("Kein Gerät gefunden"),
                "bt.missing": tr("Bluetooth geht nicht"),
            }
            return _done(phrases[name])
    except (OSError, subprocess.TimeoutExpired):
        return _done(tr("Das hat nicht geklappt"))
    item = _BY_NAME.get(name)
    if not item:
        return {"ok": False, "sagen": tr("Das gibt es nicht")}
    _name, _wort, _bild, fn, betreuer = item
    if betreuer and not confirm:
        return {"ok": False, "bestaetigen": True, "sagen": tr("Wirklich?"), "betreuer": True}
    try:
        phrase = fn()
    except (OSError, subprocess.TimeoutExpired):
        phrase = tr("Das hat nicht geklappt")
    speak(phrase)
    return {"ok": True, "sagen": phrase, "betreuer": betreuer}
