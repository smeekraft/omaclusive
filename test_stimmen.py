#!/usr/bin/env python3
"""Prueft Sprach- und Stimmwahl: voices.json, Umstellen der config, Download-Schutz. Kein Netz."""
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import time

import bausteine
import sprache_wechseln
import stimmen

ROOT = os.path.dirname(os.path.abspath(__file__))


def laden(pfad):
    with open(os.path.join(ROOT, pfad), encoding="utf-8") as handle:
        return json.load(handle)


def pruefe(bedingung, text):
    if not bedingung:
        raise SystemExit("FEHLER: " + text)


def texte(objekt, aus):
    if isinstance(objekt, dict):
        for k, v in objekt.items():
            if k in sprache_wechseln.FELDER and isinstance(v, str):
                aus.append(v)
            texte(v, aus)
    elif isinstance(objekt, list):
        for v in objekt:
            texte(v, aus)
    return aus


def main():
    # voices.json
    roh = laden("voices.json")
    pruefe(roh["quelle"] == stimmen.QUELLE, "Quelle in voices.json weicht von der festen Quelle ab")
    liste = stimmen.liste()
    pruefe(len(liste) == len(roh["stimmen"]), "voices.json hat ungueltige Eintraege")
    ids = [v["id"] for v in liste]
    pruefe(len(set(ids)) == len(ids), "doppelte Stimmen-IDs")
    for v in liste:
        pruefe(re.fullmatch(r"[0-9a-f]{64}", v["sha256"]) and re.fullmatch(r"[0-9a-f]{64}", v["json_sha256"]), "Summe " + v["id"])
        pruefe(os.path.isfile(os.path.join(ROOT, "locales", v["sprache"] + ".json")) or v["sprache"] == "de", "keine Tabelle fuer " + v["sprache"])
    for sprache in ("de", "en"):
        pruefe(stimmen.standard(sprache), "keine Standardstimme " + sprache)
    pruefe(len([v for v in liste if v["sprache"] == "en"]) >= 2, "mindestens zwei englische Stimmen")
    # ungueltige Eintraege fliegen raus
    pruefe(stimmen.finde("gibt-es-nicht") is None, "unbekannte Stimme")

    # Umstellen: de -> en -> de bringt dieselben Texte zurueck
    de = laden("config.example.json")
    en = sprache_wechseln.wechseln(copy.deepcopy(de), "en")
    pruefe(en["language"] == "en" and en["lang"] == "en-US", "language/lang nach en")
    pruefe(texte(en, []) == texte(laden("config.example.en.json"), []), "Umstellen ergibt nicht config.example.en.json")
    zurueck = sprache_wechseln.wechseln(copy.deepcopy(en), "de")
    pruefe(texte(zurueck, []) == texte(de, []), "en -> de bringt nicht das Original")
    pruefe(zurueck["language"] == "de" and zurueck["lang"] == "de-DE", "language/lang nach de")
    eigen = copy.deepcopy(de)
    eigen["name"] = "Meine eigene Karte"
    pruefe(sprache_wechseln.wechseln(eigen, "en")["name"] == "Meine eigene Karte", "eigener Text bleibt")
    try:
        sprache_wechseln.wechseln({}, "xx")
        pruefe(False, "unbekannte Sprache muss abgelehnt werden")
    except ValueError:
        pass

    # anwenden
    config = copy.deepcopy(de)
    cori = stimmen.finde("en-gb")
    pruefe(stimmen.anwenden(config, cori), "anwenden")
    pruefe(config["stimmeId"] == "en-gb" and config["stimmeModell"] == "en_GB-cori-high" and config["language"] == "en", "config nach Stimmwahl")
    pruefe(stimmen.aktive_id(config) == "en-gb", "aktive Stimme")
    pruefe(stimmen.aktive_id({"language": "en", "stimmeId": "de"}) == stimmen.standard("en")["id"], "Stimme einer anderen Sprache zaehlt nicht")

    # Download-Schutz
    tmp = tempfile.mkdtemp()
    try:
        try:
            stimmen._lade("https://example.com/x.onnx", os.path.join(tmp, "x.onnx"), "0" * 64)
            pruefe(False, "fremde Quelle muss abgelehnt werden")
        except ValueError:
            pass
        pruefe(not os.listdir(tmp), "nach Ablehnung liegt nichts da")

        # starten mit falscher/richtiger Datei, ohne Netz (herunterladen wird ersetzt)
        alt_dir, alt_dl = stimmen.DIR, stimmen.herunterladen
        stimmen.DIR = tmp
        os.makedirs(os.path.join(tmp, "voices"))
        inhalt = b"stimme"
        probe = {"id": "t-en", "sprache": "en", "name": "T", "modell": "en_US-test-low", "pfad": "en/en_US/test/low/en_US-test-low",
                 "sha256": hashlib.sha256(inhalt).hexdigest(), "json_sha256": hashlib.sha256(b"{}").hexdigest(), "sprachcode": "en-US"}
        with open(os.path.join(tmp, "voices.json"), "w", encoding="utf-8") as handle:
            std = dict(probe, id="t-std", modell="en_US-std-low", standard=True)
            json.dump({"quelle": stimmen.QUELLE, "stimmen": [std, probe]}, handle)
        pruefe(not stimmen.da(probe), "Stimme darf noch nicht da sein")
        geladen = []

        def falsch(v):
            geladen.append(v["id"])
            raise ValueError("Pruefsumme stimmt nicht")

        def richtig(v):
            geladen.append(v["id"])
            for endung, daten in ((".onnx", inhalt), (".onnx.json", b"{}")):
                with open(stimmen.datei(v, endung), "wb") as handle:
                    handle.write(daten)

        def warte():
            for _ in range(100):
                if stimmen.status()["status"] != "laeuft":
                    return stimmen.status()
                time.sleep(0.05)
            pruefe(False, "Job haengt")

        gespeichert = []

        def aendern(fn):
            c = {"language": "de"}
            fn(c)
            gespeichert.append(c)

        stimmen.herunterladen = falsch
        ok, grund = stimmen.starten("t-en", aendern)
        pruefe(ok, "starten")
        pruefe(warte()["status"] == "fehler" and not gespeichert, "bei falscher Summe darf die config nicht wechseln")
        stimmen.herunterladen = richtig
        ok, grund = stimmen.starten("t-en", aendern)
        pruefe(warte()["status"] == "fertig" and len(gespeichert) == 1, "Wechsel nach Download")
        pruefe(gespeichert[0]["language"] == "en" and gespeichert[0]["stimmeModell"] == "en_US-test-low", "config nach Wechsel")
        pruefe(stimmen.da(probe), "Stimme muss jetzt da sein")
        stimmen.herunterladen = falsch
        n = len(geladen)
        stimmen.starten("t-en", aendern)
        pruefe(warte()["status"] == "fertig" and len(geladen) == n, "schon geladene Stimme wird nicht erneut geladen")
        pruefe(stimmen.starten("gibt-es-nicht", aendern) == (False, "unbekannt"), "unbekannte ID")

        # bausteine nimmt die gewaehlte Stimme, nur passend zur Sprache; fertige Aufnahmen nur mit der Standardstimme
        alt_b = bausteine.DIR
        bausteine.DIR = tmp
        os.environ["OMACLUSIVE_LANG"] = "en"
        with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as handle:
            json.dump({"language": "en", "stimmeModell": "en_US-test-low"}, handle)
        pruefe(bausteine.voice_model("en").endswith("en_US-test-low.onnx"), "gewaehlte Stimme wird benutzt")
        pruefe(bausteine.voice_model("de") is None or "test-low" not in bausteine.voice_model("de"), "Stimme einer anderen Sprache wird nicht benutzt")
        pruefe(not bausteine._ist_standardstimme(), "Fremdstimme ist nicht die Standardstimme")
        with open(os.path.join(tmp, "config.json"), "w", encoding="utf-8") as handle:
            json.dump({"language": "en", "stimmeModell": "../../etc/passwd"}, handle)
        pruefe(bausteine._gewaehlt("en") is None, "unsauberer Modellname wird abgelehnt")
        bausteine.DIR = alt_b
        os.environ.pop("OMACLUSIVE_LANG")
        stimmen.DIR, stimmen.herunterladen = alt_dir, alt_dl
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("STIMMEN_OK", len(liste), "Stimmen")


if __name__ == "__main__":
    main()
