#!/usr/bin/env python3
"""Kontrast, Form und Farbenblindheit der Kacheln. Spielt nichts ab."""
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
ZIEL = 7.0

# Machado 2009, Stärke 1. Simulation auf linearen RGB-Anteilen.
MATS = {
    "protan": [
        [0.152286, 1.052583, -0.204868],
        [0.114503, 0.786281, 0.099216],
        [-0.003882, -0.048116, 1.051998],
    ],
    "deutan": [
        [0.367322, 0.860646, -0.227968],
        [0.280085, 0.672501, 0.047413],
        [-0.011820, 0.042940, 0.968881],
    ],
    "tritan": [
        [1.255528, -0.076749, -0.178779],
        [-0.078411, 0.930809, 0.147602],
        [0.004733, 0.691367, 0.303900],
    ],
}


def kanal(hexwert):
    text = hexwert.lstrip("#")
    if len(text) == 3:
        text = "".join(zeichen * 2 for zeichen in text)
    return [int(text[i:i + 2], 16) for i in (0, 2, 4)]


def lin(wert):
    anteil = wert / 255.0
    if anteil <= 0.04045:
        return anteil / 12.92
    return ((anteil + 0.055) / 1.055) ** 2.4


def helligkeit(hexwert):
    rot, gruen, blau = kanal(hexwert)
    return 0.2126 * lin(rot) + 0.7152 * lin(gruen) + 0.0722 * lin(blau)


def kontrast(a, b):
    hell_a, hell_b = helligkeit(a), helligkeit(b)
    hell, dunkel = max(hell_a, hell_b), min(hell_a, hell_b)
    return (hell + 0.05) / (dunkel + 0.05)


def simuliere(hexwert, name):
    matrix = MATS[name]
    anteile = [wert / 255.0 for wert in kanal(hexwert)]
    werte = []
    for zeile in matrix:
        wert = zeile[0] * anteile[0] + zeile[1] * anteile[1] + zeile[2] * anteile[2]
        werte.append(max(0, min(255, int(round(wert * 255)))))
    return "#{:02x}{:02x}{:02x}".format(*werte)


def farben(text):
    return re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{3,8})"', text)


def norm(hexwert):
    text = hexwert.lower()
    if len(text) == 4:
        return "#" + "".join(zeichen * 2 for zeichen in text[1:])
    return text


def motive(pfad):
    text = open(pfad, encoding="utf-8").read()
    liste = [norm(farbe) for farbe in farben(text)]
    if not liste:
        raise SystemExit(os.path.basename(pfad) + " hat keine Farbe")
    kachel = liste[0]
    reste = []
    for farbe in liste[1:]:
        if farbe != kachel and farbe not in reste:
            reste.append(farbe)
    return text, kachel, reste


def pruefe_pixel(pfad, fehler):
    text = open(pfad, encoding="utf-8").read()
    name = os.path.basename(pfad)
    if 'viewBox="0 0 24 24"' not in text or 'shape-rendering="crispEdges"' not in text:
        fehler.append(name + " ist nicht 24x24 mit harten Kanten")
    if re.search(r"<(path|circle|polygon|ellipse|line)\b", text):
        fehler.append(name + " nutzt keine reinen Rechtecke")
    if text.count("<rect") < 2:
        fehler.append(name + " hat kein Motiv")


def pruefe_glatt(pfad, fehler):
    text = open(pfad, encoding="utf-8").read()
    name = os.path.basename(pfad)
    if 'viewBox="0 0 24 24"' not in text:
        fehler.append(name + " (glatt) ist nicht 24x24")
    if "crispEdges" in text:
        fehler.append(name + " (glatt) hat harte Kanten")
    if len(re.findall(r"<(?:path|circle|ellipse|line|rect)\b", text)) < 2:
        fehler.append(name + " (glatt) hat kein Motiv")


def main():
    fehler = []
    ROOT_IMG = os.path.join(ROOT, "img")
    plugin = os.path.join(ROOT, "plugins")
    saetze = {}
    for stil in ("glatt", "pixel"):
        ordner = os.path.join(ROOT_IMG, stil)
        namen = sorted(n for n in os.listdir(ordner) if n.endswith(".svg"))
        saetze[stil] = namen
        dateien = [os.path.join(ordner, n) for n in namen]
        if os.path.isdir(plugin):
            for wurzel, _o, plugnamen in os.walk(plugin):
                if os.path.basename(wurzel) == stil:
                    dateien += [os.path.join(wurzel, n) for n in sorted(plugnamen) if n.endswith(".svg")]
        for pfad in dateien:
            pruefe_pixel(pfad, fehler) if stil == "pixel" else pruefe_glatt(pfad, fehler)
            check_kontrast(pfad, fehler)
        saetze[stil + "+plugin"] = sorted(os.path.basename(p) for p in dateien)
    if saetze["glatt"] != saetze["pixel"]:
        fehler.append("glatt und pixel haben nicht dieselben Dateien")
    if saetze["glatt+plugin"] != saetze["pixel+plugin"]:
        fehler.append("glatt und pixel haben nicht dieselben Plugin-Bilder")
    for stil in ("glatt", "pixel"):
        pruefe_feste(os.path.join(ROOT_IMG, stil), fehler)
    finish(fehler)


def check_kontrast(pfad, fehler):
    if True:
        text, kachel, reste = motive(pfad)
        for farbe in reste:
            if kontrast(farbe, kachel) >= ZIEL:
                continue
            if any(kontrast(farbe, andere) >= ZIEL for andere in [kachel] + reste if andere != farbe):
                continue
            fehler.append("%s %s auf %s nur %.2f" % (os.path.basename(pfad), farbe, kachel, kontrast(farbe, kachel)))



def pruefe_feste(bilder, fehler):
    fest = {
        "ja.svg": ("#ffe14a", "#0c2340", "haken"),
        "nein.svg": ("#0c2340", "#ffe14a", "kreuz"),
        "hilfe.svg": ("#9a3412", "#ffffff", "glocke"),
        "zurueck.svg": ("#0c2340", "#ffe14a", "pfeil"),
    }
    for name, (kachel, motiv, form) in fest.items():
        text, ist_kachel, reste = motive(os.path.join(bilder, name))
        if ist_kachel != kachel:
            fehler.append(name + " Kachel ist " + ist_kachel)
        if motiv not in reste and motiv != ist_kachel:
            fehler.append(name + " Motiv fehlt")
        if 'data-form="%s"' % form not in text:
            fehler.append(name + " hat nicht die Form " + form)
        if re.search(r"#(?:0b7a32|8c1c13|9b2226)\b", text):
            fehler.append(name + " nutzt noch Rot oder Grün als Kachel")

    ja = fest["ja.svg"][0]
    nein = fest["nein.svg"][0]
    if abs(helligkeit(ja) - helligkeit(nein)) < 0.45:
        fehler.append("Ja und Nein sind in Graustufen zu ähnlich")
    print("graustufen Ja %.2f Nein %.2f" % (helligkeit(ja), helligkeit(nein)))
    for name in MATS:
        gesehen_ja = simuliere(ja, name)
        gesehen_nein = simuliere(nein, name)
        abstand = abs(helligkeit(gesehen_ja) - helligkeit(gesehen_nein))
        print(name, gesehen_ja, gesehen_nein, "Ldiff %.2f" % abstand)
        if abstand < 0.35:
            fehler.append("Ja und Nein fallen bei %s zusammen" % name)

    pass


def finish(fehler):
    seite = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    if 'id="setup"' not in seite or "3s linear" not in seite:
        fehler.append("die kleine Einstellungstaste mit Haltebalken fehlt")
    if 'id="hilfe"' in seite or 'id="ja"' in seite or 'id="nein"' in seite or 'id="zurueck"' in seite:
        fehler.append("Ecken-Leiste ist wieder da")
    if "@keyframes" in seite or "blink" in seite:
        fehler.append("die Seite blinkt oder animiert")
    if ".karte.an" not in seite or "border-width: 1.5vh" not in seite:
        fehler.append("die Markierung ist kein dickerer Rand")

    if fehler:
        raise SystemExit("FARBE FAIL " + " | ".join(fehler))
    print("FARBE_OK kacheln kontrast>=7 formen ja/nein/hilfe/zurueck")


if __name__ == "__main__":
    main()
