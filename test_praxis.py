#!/usr/bin/env python3
"""Prüft Ordner, Bildblatt und Autostart. Legt nichts im Heimatordner an und ruft kein Netz."""
import json
import os
import tempfile
from pathlib import Path

import praxis

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    pdf = praxis.blatt_pdf(ROOT)
    if not pdf.startswith(b"%PDF"):
        raise SystemExit("Blatt ist kein PDF")
    if b"/home/" in pdf:
        raise SystemExit("Blatt enthält einen Privatpfad")
    erwartet = 0
    for relativ, _name in praxis.KACHELN:
        text = Path(ROOT, relativ).read_text(encoding="utf-8")
        erwartet += len(praxis.svg_rechtecke(text))
    ist = pdf.count(b" re f")
    if ist != erwartet:
        raise SystemExit("Blatt zeichnet %s statt %s Rechtecke" % (ist, erwartet))
    for farbe in (
        b"1.0000 0.8824 0.2902",
        b"0.0471 0.1373 0.2510",
        b"0.6039 0.2039 0.0706",
        b"1.0000 1.0000 1.0000",
    ):
        if farbe not in pdf:
            raise SystemExit("Farbe fehlt: " + farbe.decode("ascii"))
    with tempfile.TemporaryDirectory() as tmp:
        basis = Path(tmp)
        bilder = basis / "Bilder" / "Omaclusive"
        filme = basis / "Videos" / "Omaclusive"
        bilder.mkdir(parents=True)
        filme.mkdir(parents=True)
        (bilder / "probe.jpg").write_bytes(b"jpg")
        (bilder / "weg.txt").write_text("x", encoding="utf-8")
        (filme / "probe.mp4").write_bytes(b"mp4")
        (basis / "geheim.txt").write_text("nein", encoding="utf-8")
        if praxis.datei_im_ordner("bilder", "../geheim.txt", basis) is not None:
            raise SystemExit("Pfad ist aus dem Ordner ausgebrochen")
        if praxis.datei_im_ordner("bilder", "weg.txt", basis) is not None:
            raise SystemExit("Textdatei gilt als Bild")
        foto = praxis.datei_im_ordner("bilder", "probe.jpg", basis)
        if foto is None or foto.name != "probe.jpg":
            raise SystemExit("Bild nicht gefunden")
        karten = praxis.karten("bilder", basis)
        if len(karten) != 1 or karten[0]["aktion"]["typ"] != "schau":
            raise SystemExit("Bildkarte falsch")
        if "/home/" in json.dumps(karten):
            raise SystemExit("Karten enthalten einen Privatpfad")
        film = praxis.karten("filme", basis)
        if film[0]["aktion"]["typ"] != "film" or film[0]["aktion"]["name"] != "probe.mp4":
            raise SystemExit("Filmkarte falsch")
        ziel = praxis.autostart_schreiben(basis / "autostart", "start-talker.sh")
        text = ziel.read_text(encoding="utf-8")
        if "Name=Omaclusive" not in text or "Exec=start-talker.sh" not in text:
            raise SystemExit("Autostart falsch")
        if "/home/" in text:
            raise SystemExit("Autostart enthält einen festen Pfad")
        heim = basis / "heim"
        if praxis.autostart_aktiv(heim):
            raise SystemExit("Autostart ohne Datei als aktiv erkannt")
        if praxis.autostart_setzen(heim, "/x/start-talker.sh", True) is not True or not praxis.autostart_aktiv(heim):
            raise SystemExit("Autostart nicht angelegt")
        if "Exec=/x/start-talker.sh" not in praxis.autostart_datei(heim).read_text(encoding="utf-8"):
            raise SystemExit("Autostart Exec falsch")
        (heim / ".config" / "autostart" / "anderes.desktop").write_text("x", encoding="utf-8")
        if praxis.autostart_setzen(heim, "/x/start-talker.sh", False) is not False or praxis.autostart_aktiv(heim):
            raise SystemExit("Autostart nicht entfernt")
        if not (heim / ".config" / "autostart" / "anderes.desktop").exists():
            raise SystemExit("Entfernen hat fremde Dateien angefasst")
        if praxis.autostart_setzen(heim, "/x/start-talker.sh", False) is not False:
            raise SystemExit("Entfernen ohne Datei muss ruhig bleiben")
        demo = basis / "plugins" / "demo"
        demo.mkdir(parents=True)
        (demo / "a.svg").write_text("<svg></svg>", encoding="utf-8")
        (demo / "plugin.json").write_text(json.dumps({
            "name": "Demo",
            "bild": "a.svg",
            "karten": [{"wort": "A", "bild": "a.svg", "aktion": {"typ": "sprechen", "text": "A."}}],
        }), encoding="utf-8")
        plugins = praxis.plugins_lesen(basis / "plugins")
        if len(plugins) != 1 or plugins[0]["bild"] != "/api/plugin-bild?id=demo&datei=a.svg":
            raise SystemExit("Pluginliste falsch")
        if praxis.plugin_datei(basis / "plugins", "demo", "../a.svg") is not None:
            raise SystemExit("Pluginbild ausgebrochen")
        if praxis.plugin_datei(basis / "plugins", "demo", "a.svg") is None:
            raise SystemExit("Pluginbild fehlt")
        angelegt = praxis.anlegen("bilder", basis / "neu")
        if angelegt is None or not angelegt.is_dir():
            raise SystemExit("Ordner nicht angelegt")
    quelle = Path(praxis.__file__).read_text(encoding="utf-8")
    if "/home/" in quelle:
        raise SystemExit("Privatdaten in praxis")
    print("PRAXIS_OK", erwartet)


if __name__ == "__main__":
    main()
