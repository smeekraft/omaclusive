#!/usr/bin/env python3
"""Fernsehen: die Lieblingssender als Kacheln, ein Druck startet den Stream im Vollbild (mpv).
TV: the favourite channels as tiles, one press starts the stream full screen (mpv).

Die Sender stehen in config.json unter "fernsehen": {"sender": [{"name", "bild", "stream"}]}.
Die Oberfläche schickt nur die Nummer des Senders, die Adresse kommt immer aus config.json.
YouTube-Live-Links spielt mpv mit yt-dlp (falls installiert). Kein Konto, keine Telemetrie.

Ruhig und sicher (Fotosensibilität, WCAG 2.3.1): mpv startet ohne Bedienleiste, ohne
Bildschirmtexte und ohne Startbild, schwarz, bis das Bild kommt. Nichts blinkt.
"""
import os
import re
import shutil

MAX_SENDER = 6
STANDARD_BILD = "img/fernsehen.svg"
_RE_URL = re.compile(r"^https?://[^\s\x00-\x1f\"'<>]{1,480}$")
_RE_BILD = re.compile(r"^img/[A-Za-z0-9_.-]{1,60}\.svg$")
_RE_STEUER = re.compile(r"[\x00-\x1f\x7f]")

# Exit-Codes: 0 = zurück (Knopf, Esc oder Sendung zu Ende). Alles andere ist ein Fehler:
# 3 = kein Bild in der Wartezeit (mpv/omaclusive_tv.lua), 2 = Stream ging nicht auf, 1 = mpv selbst.

# Omaclusive-Tastennamen (wie im Browser) -> mpv-Tastennamen
_MPV_TASTE = {
    "ArrowLeft": "LEFT", "ArrowRight": "RIGHT", "ArrowUp": "UP", "ArrowDown": "DOWN",
    " ": "SPACE", "Spacebar": "SPACE", "Enter": "ENTER", "Tab": "TAB", "Backspace": "BS",
    "PageUp": "PGUP", "PageDown": "PGDWN", "Home": "HOME", "End": "END",
}


def _text(wert, grenze):
    t = re.sub(r"\s+", " ", str(wert if wert is not None else "")).strip()
    if not t or _RE_STEUER.search(t):
        return ""
    return t[:grenze]


def sender_liste(config):
    """Die gültigen Sender aus config.json, höchstens MAX_SENDER. Ungültige fallen still weg."""
    tv = (config or {}).get("fernsehen")
    roh = tv.get("sender") if isinstance(tv, dict) else None
    if not isinstance(roh, list):
        return []
    liste = []
    for s in roh:
        if not isinstance(s, dict) or s.get("aus") is True:
            continue
        name = _text(s.get("name"), 40)
        stream = str(s.get("stream") or "").strip()
        if not name or not _RE_URL.fullmatch(stream):
            continue
        bild = str(s.get("bild") or "").strip()
        if not _RE_BILD.fullmatch(bild):
            bild = STANDARD_BILD
        liste.append({"name": name, "bild": bild, "stream": stream})
        if len(liste) >= MAX_SENDER:
            break
    return liste


def mpv_taste(taste):
    """'ArrowLeft' -> 'LEFT'. Unbekannte oder unsichere Namen -> ''."""
    t = str(taste or "")
    if t in _MPV_TASTE:
        return _MPV_TASTE[t]
    if re.fullmatch(r"[A-Za-z0-9]", t):
        return t.lower()
    if re.fullmatch(r"F([1-9]|1[0-2])", t):
        return t
    return ""


def _tasten(config, art):
    roh = ((config or {}).get("keys") or {}).get(art)
    if isinstance(roh, str):
        roh = [roh]
    if not isinstance(roh, list):
        roh = {"links": ["ArrowLeft"], "rechts": ["ArrowRight"], "waehlen": ["ArrowUp", " ", "Enter"]}.get(art, [])
    out = []
    for t in roh:
        m = mpv_taste(t)
        if m and m not in out:
            out.append(m)
    return out


def _zahl(wert, standard, klein, gross):
    try:
        n = int(round(float(wert)))
    except (TypeError, ValueError):
        return standard
    return max(klein, min(gross, n))


def knopf_einstellungen(config):
    """Was die Knöpfe in mpv tun. Zwei Knöpfe: links = Zurück, rechts = Pause/Weiter,
    beide 3 s halten = Zurück. Ein Knopf: kurz = Pause/Weiter, 3 s halten = Zurück."""
    c = config or {}
    knopf = c.get("knopf") if isinstance(c.get("knopf"), dict) else {}
    modus = knopf.get("modus")
    ein = modus in ("ein", "einknopf", 1, "1")
    links, rechts, waehlen = _tasten(c, "links"), _tasten(c, "rechts"), _tasten(c, "waehlen")
    if ein:
        einzeln = []
        for t in links + rechts + waehlen:
            if t not in einzeln:
                einzeln.append(t)
        links, rechts = einzeln, []
    else:
        rechts = [t for t in rechts if t not in links]
    return {
        "ein": ein,
        "links": links + ["MBTN_LEFT"] if not ein else links + ["MBTN_LEFT", "MBTN_RIGHT"],
        "rechts": (rechts + ["MBTN_RIGHT"]) if not ein else [],
        "halten": _zahl(c.get("setupHoldMs"), 3000, 1000, 10000),
        "entprell": _zahl(c.get("debounceMs"), 300, 100, 2000),
        "warten": _zahl(((c.get("fernsehen") or {}) if isinstance(c.get("fernsehen"), dict) else {}).get("wartenSekunden"), 30, 10, 120),
    }


def mpv_befehl(stream, dir_, config):
    """Der mpv-Aufruf: Vollbild, schwarz, ohne Bedienleiste, ohne Bildschirmtexte, eigene Knöpfe."""
    k = knopf_einstellungen(config)
    opts = ",".join([
        "omaclusive_tv-links=" + "/".join(k["links"]),
        "omaclusive_tv-rechts=" + "/".join(k["rechts"]),
        "omaclusive_tv-ein=" + ("ja" if k["ein"] else "nein"),
        "omaclusive_tv-halten=%d" % k["halten"],
        "omaclusive_tv-entprell=%d" % k["entprell"],
        "omaclusive_tv-warten=%d" % k["warten"],
    ])
    return [
        "mpv", "--no-config", "--load-scripts=no",
        "--fs", "--force-window=immediate",
        "--osc=no", "--osd-level=0", "--no-osd-bar", "--osd-on-seek=no", "--term-osd=no",
        "--sid=no", "--sub-auto=no", "--audio-display=no", "--cursor-autohide=always",
        "--input-default-bindings=no", "--keep-open=no", "--idle=no",
        "--really-quiet", "--no-terminal", "--ytdl=yes", "--network-timeout=20",
        "--hwdec=auto-safe", "--title=Omaclusive",
        "--script=" + os.path.join(dir_, "mpv", "omaclusive_tv.lua"),
        "--script-opts=" + opts,
        "--", stream,
    ]


def bereit():
    """mpv ist da? (yt-dlp nur für YouTube-Links nötig.)"""
    return bool(shutil.which("mpv"))


def ergebnis(returncode, gestoppt):
    """Aus dem Ende von mpv: 'fehler' (Stream kam nicht oder brach ab) oder ''."""
    if gestoppt or returncode is None:
        return ""
    return "" if returncode == 0 else "fehler"
