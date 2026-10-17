#!/usr/bin/env python3
"""Hilferuf über ntfy. Kein Notruf. Netz nur für den Versand und die Rückmeldung."""
import datetime
from i18n import tr
import json
import os
import re
import secrets
import tempfile
import urllib.error
import urllib.request

WARNUNG = "Der Hilferuf leitet Rufe an ein Handy weiter. Er ersetzt keinen Notruf."
AUS_SATZ = "Der Ruf ist nicht rausgegangen."
RAUS_SATZ = "Der Ruf ist raus."
RUFE_SATZ = "Ich rufe."
TEST_SATZ = "Das ist ein Test."
TEST_AUS_SATZ = "Der Test ist nicht rausgegangen."
STANDARD_SERVER = "https://ntfy.sh"
_KANAL = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


class _OhneUmleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OEFFNER = urllib.request.build_opener(_OhneUmleitung)


def heute():
    return datetime.date.today()


def name_speichern(name):
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    text = "".join(zeichen for zeichen in text if zeichen.isalnum() or zeichen in " .-'" )
    return text[:40]


def name_zeigen(name):
    return name_speichern(name) or tr("Jemand")


def gesehen_satz(name):
    return tr("{} hat deinen Ruf gesehen.").format(name_zeigen(name))


def test_tage(wert):
    if wert is None or wert == "":
        return 30
    if wert in ("aus", "off", False):
        return 0
    try:
        zahl = int(wert)
    except (TypeError, ValueError):
        return 30
    if zahl <= 0:
        return 0
    return min(365, zahl)


def gueltiger_kanal(text):
    return bool(_KANAL.fullmatch(str(text or "")))


def neue_kanaele():
    erster = secrets.token_hex(16)
    zweiter = secrets.token_hex(16)
    while zweiter == erster:
        zweiter = secrets.token_hex(16)
    return erster, zweiter


def server_basis(url):
    text = str(url or "").strip()
    if not text:
        return None
    teile = urllib.parse.urlsplit(text)
    if teile.scheme != "https" or not teile.hostname:
        return None
    if teile.username or teile.password or teile.query or teile.fragment:
        return None
    if teile.path not in ("", "/"):
        return None
    return urllib.parse.urlunsplit(("https", teile.netloc, "", "", ""))


def test_faellig(eintrag, tag):
    eintrag = eintrag or {}
    tage = test_tage(eintrag.get("testTage"))
    if tage <= 0:
        return False
    letzter = str(eintrag.get("letzterTest") or "").strip()
    if not letzter:
        return False
    try:
        start = datetime.date.fromisoformat(letzter[:10])
    except ValueError:
        return False
    return tag >= start + datetime.timedelta(days=tage)


def sicherstellen(config, tag):
    """Legt fehlende Zufallskanäle an. Der erste Test wartet dann eine Frist."""
    if not isinstance(config, dict):
        return False
    eintrag = dict(config.get("hilferuf") or {})
    geaendert = not isinstance(config.get("hilferuf"), dict)
    if not server_basis(eintrag.get("server")):
        eintrag["server"] = STANDARD_SERVER
        geaendert = True
    if "name" not in eintrag:
        eintrag["name"] = ""
        geaendert = True
    else:
        eintrag["name"] = name_speichern(eintrag.get("name"))
    if "testTage" not in eintrag:
        eintrag["testTage"] = 30
        geaendert = True
    else:
        eintrag["testTage"] = test_tage(eintrag.get("testTage"))
    kanal = str(eintrag.get("kanal") or "")
    antwort = str(eintrag.get("antwort") or "")
    if not gueltiger_kanal(kanal) or not gueltiger_kanal(antwort) or kanal == antwort:
        kanal, antwort = neue_kanaele()
        eintrag["kanal"] = kanal
        eintrag["antwort"] = antwort
        if not str(eintrag.get("letzterTest") or "").strip():
            eintrag["letzterTest"] = tag.isoformat()
        geaendert = True
    config["hilferuf"] = eintrag
    return geaendert


def kanaele_neu(eintrag, tag):
    neu = dict(eintrag or {})
    kanal, antwort = neue_kanaele()
    neu["kanal"] = kanal
    neu["antwort"] = antwort
    neu["letzterTest"] = tag.isoformat()
    if not server_basis(neu.get("server")):
        neu["server"] = STANDARD_SERVER
    neu["name"] = name_speichern(neu.get("name"))
    neu["testTage"] = test_tage(neu.get("testTage"))
    return neu


def einstellen(eintrag, name, tage, server):
    neu = dict(eintrag or {})
    neu["name"] = name_speichern(name)
    neu["testTage"] = test_tage(tage)
    basis = server_basis(server) if str(server or "").strip() else server_basis(neu.get("server"))
    neu["server"] = basis or STANDARD_SERVER
    return neu


def zustand(config):
    eintrag = (config or {}).get("hilferuf") or {}
    basis = server_basis(eintrag.get("server")) or STANDARD_SERVER
    kanal = str(eintrag.get("kanal") or "")
    return {
        "ok": True,
        "name": name_speichern(eintrag.get("name")),
        "anzeigeName": name_zeigen(eintrag.get("name")),
        "testTage": test_tage(eintrag.get("testTage")),
        "letzterTest": str(eintrag.get("letzterTest") or ""),
        "abo": (basis + "/" + kanal) if gueltiger_kanal(kanal) else "",
        "server": basis,
        "warnung": tr(WARNUNG),
    }


def _anfrage(config, art):
    eintrag = (config or {}).get("hilferuf") or {}
    basis = server_basis(eintrag.get("server"))
    kanal = str(eintrag.get("kanal") or "")
    antwort = str(eintrag.get("antwort") or "")
    if not basis or not gueltiger_kanal(kanal) or not gueltiger_kanal(antwort):
        return None
    if art == "test":
        titel = tr("Test, kein Hilferuf")
        text = tr("Das ist ein Test. Es ist kein Hilferuf.")
        prioritaet = "3"
    else:
        titel = tr("Hilferuf")
        text = tr("Jemand möchte etwas sagen.")
        prioritaet = "5"
    ziel = basis + "/" + antwort
    kopf = {
        "User-Agent": "Omaclusive",
        "Title": titel,
        "Priority": prioritaet,
        "Content-Type": "text/plain; charset=utf-8",
        "Actions": "http, Gesehen, " + ziel + ", method=POST, body=gesehen",
    }
    return {
        "url": basis + "/" + kanal,
        "body": text.encode("utf-8"),
        "headers": kopf,
        "seit": int(datetime.datetime.now().timestamp()) - 2,
    }


def standard_oeffnen(url, daten, kopf):
    if daten is not None and not isinstance(daten, bytes):
        daten = str(daten).encode("utf-8")
    methode = "POST" if daten is not None else "GET"
    anfrage = urllib.request.Request(url, data=daten, headers=kopf or {}, method=methode)
    try:
        with _OEFFNER.open(anfrage, timeout=8) as antwort:
            return antwort.status, antwort.read(65536)
    except urllib.error.HTTPError as fehler:
        try:
            roh = fehler.read(4096)
        except Exception:
            roh = b""
        return fehler.code, roh


def sende(config, art, oeffnen=None):
    art = "test" if art == "test" else "ruf"
    oeffnen = oeffnen or standard_oeffnen
    anfrage = _anfrage(config, art)
    aus = tr(TEST_AUS_SATZ if art == "test" else AUS_SATZ)
    if not anfrage:
        return {"ok": False, "sagen": aus, "bild": "img/ruf-aus.svg"}
    try:
        status, _roh = oeffnen(anfrage["url"], anfrage["body"], anfrage["headers"])
    except Exception:
        return {"ok": False, "sagen": aus, "bild": "img/ruf-aus.svg"}
    if status != 200:
        return {"ok": False, "sagen": aus, "bild": "img/ruf-aus.svg"}
    if art == "test":
        return {"ok": True, "sagen": tr(TEST_SATZ), "bild": "img/ruf-test.svg", "seit": anfrage["seit"]}
    return {"ok": True, "sagen": tr(RAUS_SATZ), "bild": "img/hilfe.svg", "seit": anfrage["seit"]}


def lese_gesehen(roh):
    if not roh:
        return False
    text = roh.decode("utf-8", "replace")
    for zeile in text.splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            eintrag = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        if not isinstance(eintrag, dict):
            continue
        if eintrag.get("event") not in (None, "message"):
            continue
        if str(eintrag.get("message") or "").strip().lower() == "gesehen":
            return True
    return False


def frage_gesehen(config, seit, oeffnen=None):
    oeffnen = oeffnen or standard_oeffnen
    eintrag = (config or {}).get("hilferuf") or {}
    basis = server_basis(eintrag.get("server"))
    antwort = str(eintrag.get("antwort") or "")
    if not basis or not gueltiger_kanal(antwort):
        return {"ok": False, "gesehen": False}
    try:
        seit_zahl = int(float(seit))
    except (TypeError, ValueError):
        seit_zahl = 0
    url = basis + "/" + antwort + "/json?poll=1&since=" + str(seit_zahl)
    try:
        status, roh = oeffnen(url, None, {"User-Agent": "Omaclusive"})
    except Exception:
        return {"ok": False, "gesehen": False}
    if status != 200 or not lese_gesehen(roh):
        return {"ok": status == 200, "gesehen": False}
    name = name_zeigen(eintrag.get("name"))
    return {
        "ok": True,
        "gesehen": True,
        "name": name,
        "sagen": gesehen_satz(name),
        "bild": "img/ruf-gesehen.svg",
    }


def auftrag(config, daten, oeffnen=None, tag=None):
    """Führt einen Auftrag aus. Gibt zurück, ob die Konfiguration zu speichern ist."""
    if not isinstance(config, dict):
        config = {}
    daten = daten or {}
    tag = tag or heute()
    geaendert = sicherstellen(config, tag)
    art = str(daten.get("art") or "zustand")
    if art == "zustand":
        return geaendert, zustand(config)
    if art == "speichern":
        config["hilferuf"] = einstellen(
            config.get("hilferuf"), daten.get("name"), daten.get("testTage"), daten.get("server")
        )
        return True, zustand(config)
    if art == "neu":
        config["hilferuf"] = kanaele_neu(config.get("hilferuf"), tag)
        return True, zustand(config)
    if art == "test" and daten.get("nurWennFaellig") and not test_faellig(config.get("hilferuf"), tag):
        return geaendert, {"ok": True, "faellig": False}
    if art == "test":
        ergebnis = sende(config, "test", oeffnen)
        ergebnis["faellig"] = True
        if ergebnis.get("ok"):
            config["hilferuf"]["letzterTest"] = tag.isoformat()
            return True, ergebnis
        return geaendert, ergebnis
    ergebnis = sende(config, "ruf", oeffnen)
    return geaendert, ergebnis


def schreibe_atomar(pfad, daten):
    ordner = os.path.dirname(os.path.abspath(pfad)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=ordner)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(daten, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, pfad)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
