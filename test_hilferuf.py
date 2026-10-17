#!/usr/bin/env python3
"""Prüft den Hilferuf ohne Netz und ohne Ton."""
import datetime
import json
import os
import tempfile
import urllib.error

import hilferuf

TAG = datetime.date(2026, 10, 14)


def config_mit(kanal="a" * 32, antwort="b" * 32, name="", tage=30, letzter="2026-10-14"):
    return {
        "hilferuf": {
            "name": name,
            "server": "https://ntfy.sh",
            "kanal": kanal,
            "antwort": antwort,
            "testTage": tage,
            "letzterTest": letzter,
        }
    }


def test_namen():
    if hilferuf.gesehen_satz("") != "Jemand hat deinen Ruf gesehen.":
        raise SystemExit("leerer Name")
    if hilferuf.gesehen_satz("  Testname  ") != "Testname hat deinen Ruf gesehen.":
        raise SystemExit("Name mit Leerzeichen")
    if "\n" in hilferuf.name_speichern("Zeile\nZwei"):
        raise SystemExit("Zeilenumbruch im Namen")
    if hilferuf.name_zeigen("!!!") != "Jemand":
        raise SystemExit("leerer Rest")


def test_frist():
    if hilferuf.test_faellig({"testTage": 30, "letzterTest": "2026-10-14"}, TAG):
        raise SystemExit("heute ist nicht fällig")
    if not hilferuf.test_faellig({"testTage": 30, "letzterTest": "2026-09-14"}, TAG):
        raise SystemExit("nach 30 Tagen fällig")
    if hilferuf.test_faellig({"testTage": 0, "letzterTest": "2020-01-01"}, TAG):
        raise SystemExit("aus bleibt aus")
    if hilferuf.test_faellig({"testTage": "aus", "letzterTest": "2020-01-01"}, TAG):
        raise SystemExit("aus als Wort")
    if hilferuf.test_faellig({"testTage": 30, "letzterTest": ""}, TAG):
        raise SystemExit("ohne Datum noch kein Test")


def test_kanaele():
    erster, zweiter = hilferuf.neue_kanaele()
    if erster == zweiter or len(erster) != 32 or not hilferuf.gueltiger_kanal(erster):
        raise SystemExit("Zufallskanal")
    if hilferuf.server_basis("http://ntfy.sh") or hilferuf.server_basis("https://nutzer:geheim@ntfy.sh"):
        raise SystemExit("unsicherer Server")
    if hilferuf.server_basis("https://ntfy.sh") != "https://ntfy.sh":
        raise SystemExit("Serverbasis")
    roh = {}
    if not hilferuf.sicherstellen(roh, TAG):
        raise SystemExit("Kanäle fehlen")
    if roh["hilferuf"]["letzterTest"] != "2026-10-14":
        raise SystemExit("erste Frist")
    if hilferuf.test_faellig(roh["hilferuf"], TAG):
        raise SystemExit("am Anlegetag kein Test")


def test_senden_und_gesehen():
    cfg = config_mit()
    merker = {}

    def oeffnen(url, daten, kopf):
        merker["url"] = url
        merker["daten"] = daten
        merker["kopf"] = kopf
        if daten is None:
            zeilen = [
                json.dumps({"event": "open"}),
                json.dumps({"event": "message", "message": "gesehen"}),
            ]
            return 200, ("\n".join(zeilen)).encode()
        return 200, b"ok"

    ergebnis = hilferuf.sende(cfg, "ruf", oeffnen)
    if not ergebnis.get("ok") or ergebnis.get("sagen") != hilferuf.RAUS_SATZ:
        raise SystemExit("Versand: " + str(ergebnis))
    if not merker["url"].endswith("/" + "a" * 32):
        raise SystemExit("falscher Kanal")
    aktion = merker["kopf"]["Actions"]
    if not aktion.startswith("http, Gesehen, https://ntfy.sh/" + "b" * 32):
        raise SystemExit("Knopf Gesehen: " + aktion)
    if b"gesehen" not in merker["kopf"]["Actions"].encode():
        raise SystemExit("Antwortwort fehlt")
    if merker["daten"] != "Jemand möchte etwas sagen.".encode():
        raise SystemExit("Nachricht")
    if "Testname" in merker["daten"].decode():
        raise SystemExit("Name steht in der Handy-Nachricht")
    gesehen = hilferuf.frage_gesehen(cfg, ergebnis["seit"], oeffnen)
    if not gesehen.get("gesehen") or gesehen.get("sagen") != "Jemand hat deinen Ruf gesehen.":
        raise SystemExit("Gesehen: " + str(gesehen))
    if not hilferuf.lese_gesehen(json.dumps({"event": "open"}).encode()):
        pass
    if hilferuf.lese_gesehen(json.dumps({"event": "open", "message": "gesehen"}).encode()):
        raise SystemExit("open zählt als Gesehen")


def test_ohne_netz():
    def oeffnen(url, daten, kopf):
        raise urllib.error.URLError("offline")

    ergebnis = hilferuf.sende(config_mit(), "ruf", oeffnen)
    if ergebnis.get("ok") or ergebnis.get("sagen") != hilferuf.AUS_SATZ:
        raise SystemExit("offline Ruf")
    if ergebnis.get("bild") != "img/ruf-aus.svg":
        raise SystemExit("offline Bild")
    test = hilferuf.sende(config_mit(), "test", oeffnen)
    if test.get("sagen") != hilferuf.TEST_AUS_SATZ:
        raise SystemExit("offline Test")


def test_auftrag_test_nur_wenn_faellig():
    cfg = config_mit(letzter="2026-10-14")
    aufgerufen = {"an": False}

    def oeffnen(url, daten, kopf):
        aufgerufen["an"] = True
        return 200, b"ok"

    speichern, ergebnis = hilferuf.auftrag(
        cfg, {"art": "test", "nurWennFaellig": True}, oeffnen, TAG
    )
    if aufgerufen["an"] or ergebnis.get("faellig") is not False:
        raise SystemExit("Test zu früh: " + str(ergebnis))
    if speichern:
        raise SystemExit("nichts zu speichern")
    cfg["hilferuf"]["letzterTest"] = "2026-09-01"
    speichern, ergebnis = hilferuf.auftrag(
        cfg, {"art": "test", "nurWennFaellig": True}, oeffnen, TAG
    )
    if not ergebnis.get("ok") or not speichern:
        raise SystemExit("fälliger Test")
    if cfg["hilferuf"]["letzterTest"] != "2026-10-14":
        raise SystemExit("Datum nicht gesetzt")
    if ergebnis.get("sagen") != hilferuf.TEST_SATZ:
        raise SystemExit("Testsatz")


def test_datei():
    fd, pfad = tempfile.mkstemp(prefix="omaclusive-hilferuf-", suffix=".json")
    os.close(fd)
    try:
        hilferuf.schreibe_atomar(pfad, {"hilferuf": {"name": ""}})
        with open(pfad, encoding="utf-8") as handle:
            roh = handle.read()
        if "/home/" in roh:
            raise SystemExit("Privatpfad in der Datei")
        if json.loads(roh)["hilferuf"]["name"] != "":
            raise SystemExit("nicht lesbar")
    finally:
        os.remove(pfad)


def test_warnung():
    text = hilferuf.zustand(config_mit())["warnung"]
    if "keinen Notruf" not in text or "weiter" not in text:
        raise SystemExit("Warnung fehlt")


def main():
    test_namen()
    test_frist()
    test_kanaele()
    test_senden_und_gesehen()
    test_ohne_netz()
    test_auftrag_test_nur_wenn_faellig()
    test_datei()
    test_warnung()
    modul = open(hilferuf.__file__, encoding="utf-8").read()
    if "/home/" in modul:
        raise SystemExit("Privatpfad im Hilferuf")
    print("HILFERUF_OK")


if __name__ == "__main__":
    main()
