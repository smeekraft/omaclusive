"""Ordner, Bildblatt und Autostart. Kein Netz und kein Start des Servers.

Tests übergeben ein eigenes Verzeichnis. Nichts hier schreibt in ein Heimatverzeichnis,
solange der Aufrufer keines übergibt.
"""
import json
from i18n import tr
import os
import re
from pathlib import Path

BILDER = ("Bilder", "Omaclusive")
VIDEOS = ("Videos", "Omaclusive")
BILD_ENDEN = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
FILM_ENDEN = {".mp4", ".webm", ".mkv", ".ogv", ".mov"}
PLUGIN_BILD = {".svg", ".png", ".jpg", ".jpeg", ".webp"}
_RE_RECHTECK = re.compile(r"<rect\b([^>]*)/?>", re.I)
_RE_ATTR = re.compile(r"""\b([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*"([^"]*)\"""")

KACHELN = (
    ("img/pixel/zurueck.svg", "Zurück"),
    ("img/pixel/nein.svg", "Nein"),
    ("img/pixel/ja.svg", "Ja"),
    ("img/pixel/sagen.svg", "Sagen"),
    ("img/pixel/fotos.svg", "Bilder"),
    ("img/pixel/fernsehen.svg", "Filme"),
    ("img/pixel/system.svg", "Steuern"),
    ("img/pixel/hilfe.svg", "Hilferuf"),
    ("img/pixel/ton.svg", "Klingel"),
    ("img/pixel/zwei.svg", "Zwei Knöpfe"),
    ("img/pixel/andere.svg", "Andere"),
)


def ordner_pfad(quelle, basis=None):
    if quelle == "bilder":
        teile = BILDER
    elif quelle == "filme":
        teile = VIDEOS
    else:
        return None
    wurzel = Path(basis) if basis is not None else Path.home()
    return wurzel.joinpath(*teile)


def anlegen(quelle, basis=None):
    pfad = ordner_pfad(quelle, basis)
    if pfad is None:
        return None
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def _im_ordner(basis, name):
    if not name or not isinstance(name, str):
        return None
    if name != os.path.basename(name) or name in (".", ".."):
        return None
    if "/" in name or "\\" in name or name.startswith("."):
        return None
    wurzel = Path(basis).resolve()
    ziel = (wurzel / name).resolve()
    try:
        ziel.relative_to(wurzel)
    except ValueError:
        return None
    return ziel


def datei_im_ordner(quelle, name, basis=None):
    pfad = ordner_pfad(quelle, basis)
    if pfad is None:
        return None
    ziel = _im_ordner(pfad, name)
    if ziel is None or not ziel.is_file():
        return None
    enden = BILD_ENDEN if quelle == "bilder" else FILM_ENDEN
    if ziel.suffix.lower() not in enden:
        return None
    return ziel


def liste(quelle, basis=None):
    pfad = ordner_pfad(quelle, basis)
    if pfad is None or not pfad.is_dir():
        return []
    enden = BILD_ENDEN if quelle == "bilder" else FILM_ENDEN
    namen = []
    for eintrag in pfad.iterdir():
        if not eintrag.is_file() or eintrag.name.startswith("."):
            continue
        if eintrag.suffix.lower() not in enden:
            continue
        if _im_ordner(pfad, eintrag.name) is None:
            continue
        namen.append(eintrag.name)
    namen.sort()
    return namen


def karten(quelle, basis=None):
    aus = []
    for name in liste(quelle, basis):
        stamm = Path(name).stem or name
        if quelle == "bilder":
            aus.append({
                "wort": stamm,
                "sprechen": stamm,
                "bild": "/api/datei?quelle=bilder&name=" + _quote(name),
                "aktion": {"typ": "schau", "name": name},
            })
        else:
            aus.append({
                "wort": stamm,
                "sprechen": stamm,
                "bild": "img/fernsehen.svg",
                "aktion": {"typ": "film", "name": name},
            })
    return aus


def _quote(name):
    from urllib.parse import quote
    return quote(name, safe="")


BILDSTILE = ("glatt", "pixel")


def bildstil(wert):
    """Bildsatz aus config.json ("bildstil"): glatt (Standard) oder pixel."""
    text = str(wert or "").strip().lower()
    return "pixel" if text in ("pixel", "pixelart", "pixelstil") else "glatt"


def bild_im_stil(ordner, name, stil):
    """Bild im Stil-Unterordner, sonst None (dann gilt die Datei direkt im Ordner)."""
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name) or name.startswith("."):
        return None
    ziel = Path(ordner) / bildstil(stil) / name
    return ziel if ziel.is_file() else None


def plugin_datei(wurzel, pid, datei, stil=None):
    if not isinstance(pid, str) or not re.fullmatch(r"[a-z0-9_-]{1,40}", pid):
        return None
    if not isinstance(datei, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", datei):
        return None
    if Path(datei).suffix.lower() not in PLUGIN_BILD:
        return None
    basis = (Path(wurzel) / pid).resolve()
    if stil is not None:
        im_stil = bild_im_stil(basis, datei, stil)
        if im_stil is not None:
            return im_stil
    ziel = _im_ordner(basis, datei)
    if ziel is None or not ziel.is_file():
        return None
    return ziel


def _bild_url(pid, datei):
    if not isinstance(datei, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", datei):
        return ""
    if Path(datei).suffix.lower() not in PLUGIN_BILD:
        return ""
    return "/api/plugin-bild?id=" + pid + "&datei=" + datei


def plugins_lesen(wurzel):
    wurzel = Path(wurzel)
    if not wurzel.is_dir():
        return []
    aus = []
    for eintrag in sorted(wurzel.iterdir(), key=lambda pfad: pfad.name):
        if not eintrag.is_dir() or not re.fullmatch(r"[a-z0-9_-]{1,40}", eintrag.name):
            continue
        datei = eintrag / "plugin.json"
        if not datei.is_file():
            continue
        try:
            daten = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
        if isinstance(daten, dict):
            aus.append(_plugin_fuer_client(eintrag.name, daten))
    return aus


def _plugin_fuer_client(pid, daten):
    karten_liste = []
    for karte in daten.get("karten") or []:
        if not isinstance(karte, dict):
            continue
        neu = dict(karte)
        neu["bild"] = _bild_url(pid, karte.get("bild"))
        karten_liste.append(neu)
    return {
        "id": pid,
        "name": str(daten.get("name") or pid),
        "sprechen": str(daten.get("sprechen") or daten.get("name") or pid),
        "bild": _bild_url(pid, daten.get("bild")),
        "karten": karten_liste,
    }


def autostart_text(exec_pfad):
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Omaclusive\n"
        "Exec=" + str(exec_pfad) + "\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def autostart_schreiben(ziel_ordner, exec_pfad):
    ordner = Path(ziel_ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    pfad = ordner / "omaclusive.desktop"
    temporaer = ordner / "omaclusive.desktop.tmp"
    temporaer.write_text(autostart_text(exec_pfad), encoding="utf-8")
    os.replace(temporaer, pfad)
    return pfad


def autostart_datei(heim):
    """Fester Pfad: <heim>/.config/autostart/omaclusive.desktop. Kein Pfad kommt von außen."""
    return Path(heim) / ".config" / "autostart" / "omaclusive.desktop"


def autostart_aktiv(heim):
    return autostart_datei(heim).is_file()


def autostart_setzen(heim, exec_pfad, an):
    """an=True legt den Eintrag an, an=False entfernt genau diese eine Datei. Gibt den neuen Zustand zurück."""
    datei = autostart_datei(heim)
    if an:
        autostart_schreiben(datei.parent, exec_pfad)
    else:
        try:
            datei.unlink()
        except FileNotFoundError:
            pass
    return autostart_aktiv(heim)


def start_skript(verzeichnis):
    return str(Path(verzeichnis) / "start-talker.sh")


def svg_rechtecke(text):
    rechtecke = []
    for treffer in _RE_RECHTECK.finditer(text or ""):
        attr = dict(_RE_ATTR.findall(treffer.group(1)))
        try:
            x = float(attr.get("x") or 0)
            y = float(attr.get("y") or 0)
            breite = float(attr.get("width") or 0)
            hoehe = float(attr.get("height") or 0)
        except ValueError:
            continue
        if breite <= 0 or hoehe <= 0:
            continue
        rechtecke.append((x, y, breite, hoehe, attr.get("fill") or "#0c2340"))
    return rechtecke


def _rgb(wert):
    text = str(wert or "").strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
        return (12 / 255.0, 35 / 255.0, 64 / 255.0)
    return (int(text[1:3], 16) / 255.0, int(text[3:5], 16) / 255.0, int(text[5:7], 16) / 255.0)


def _pdf_text(satz):
    roh = satz.encode("cp1252", errors="replace")
    aus = bytearray(b"(")
    for byte in roh:
        if byte in b"\\()":
            aus.extend(b"\\" + bytes([byte]))
        elif byte < 32 or byte > 126:
            aus.extend(("\\%03o" % byte).encode("ascii"))
        else:
            aus.append(byte)
    aus.append(ord(")"))
    return bytes(aus)


def _kachel(svg, beschriftung, links, unten, groesse):
    zeilen = []
    for x, y, breite, hoehe, fuellung in svg_rechtecke(svg):
        rot, gruen, blau = _rgb(fuellung)
        px = links + (x / 24.0) * groesse
        py = unten + groesse - ((y + hoehe) / 24.0) * groesse
        pw = (breite / 24.0) * groesse
        ph = (hoehe / 24.0) * groesse
        zeilen.append("%.4f %.4f %.4f rg" % (rot, gruen, blau))
        zeilen.append("%.2f %.2f %.2f %.2f re f" % (px, py, pw, ph))
    zeilen.append("BT")
    zeilen.append("/F1 11 Tf")
    zeilen.append("0.0471 0.1373 0.2510 rg")
    zeilen.append("1 0 0 1 %.2f %.2f Tm" % (links, unten - 14))
    zeilen.append(_pdf_text(beschriftung).decode("ascii") + " Tj")
    zeilen.append("ET")
    return "\n".join(zeilen)


def blatt_pdf(verzeichnis):
    wurzel = Path(verzeichnis)
    groesse = 90.0
    zeilen = []
    for nummer, (relativ, beschriftung) in enumerate(KACHELN):
        beschriftung = tr(beschriftung)
        spalte = nummer % 6
        reihe = nummer // 6
        links = 36.0 + spalte * 128.0
        unten = 470.0 - reihe * 150.0
        svg = (wurzel / relativ).read_text(encoding="utf-8")
        zeilen.append(_kachel(svg, beschriftung, links, unten, groesse))
    zeilen.append("BT")
    zeilen.append("/F1 16 Tf")
    zeilen.append("0.0471 0.1373 0.2510 rg")
    texte = (
        tr("Pfeil links ist die linke Kachel."),
        tr("Pfeil rechts ist die rechte Kachel."),
        tr("Linksklick und Rechtsklick gehen auch."),
        tr("Im Ein-Knopf-Modus wählt jede Taste die markierte Kachel."),
    )
    for nummer, satz in enumerate(texte):
        zeilen.append("1 0 0 1 36.00 %.2f Tm" % (150.0 - nummer * 24.0))
        zeilen.append(_pdf_text(satz).decode("ascii") + " Tj")
    zeilen.append("ET")
    inhalt = ("\n".join(zeilen) + "\n").encode("ascii")
    return _pdf(inhalt)


def _pdf(inhalt):
    objekte = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [4 0 R] >>\nendobj\n",
        b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n",
        b"4 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] "
        b"/Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        (b"<< /Length %d >>\nstream\n" % len(inhalt)) + inhalt + b"endstream\nendobj\n",
    ]
    aus = bytearray(b"%PDF-1.4\n")
    offsets = []
    for objekt in objekte:
        if objekt.startswith(b"<<"):
            objekt = b"5 0 obj\n" + objekt
        offsets.append(len(aus))
        aus.extend(objekt)
    xref = len(aus)
    aus.extend(b"xref\n0 6\n")
    aus.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        aus.extend(("%010d 00000 n \n" % offset).encode("ascii"))
    aus.extend(("trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref).encode("ascii"))
    return bytes(aus)
