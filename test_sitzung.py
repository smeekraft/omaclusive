#!/usr/bin/env python3
"""Sitzungsgeheimnis, Herkunft und keine Aktion per GET.

Startet den echten Server auf 127.0.0.1. systemctl, Chromium und xdg-open sind Attrappen,
damit Ausschalten und Öffnen nichts am Rechner tun.
"""
import http.client
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time

import sitzung

DIR = os.path.dirname(os.path.abspath(__file__))


def ok(bedingung, text):
    if not bedingung:
        print("FEHLER:", text)
        sys.exit(1)


def modus(pfad):
    return stat.S_IMODE(os.lstat(pfad).st_mode)


def gebunden(port):
    nadel = "0100007F:%04X" % port
    with open("/proc/net/tcp", encoding="ascii") as handle:
        for zeile in handle:
            teile = zeile.split()
            if len(teile) > 3 and teile[1].upper() == nadel and teile[3] == "0A":
                return True
    return False


def logtext(pfad):
    if not os.path.exists(pfad):
        return ""
    with open(pfad, encoding="utf-8") as handle:
        return handle.read()


def server_umgebung(prozess):
    """Umgebung, nachdem server.py wirklich ausgeführt wird.

    Popen kehrt zurück, sobald exec beginnt. Bis der Kern die neue
    Prozessumgebung veröffentlicht, ist /proc/<pid>/environ leer oder zeigt
    noch die Umgebung des Elternprozesses. Beides hat den PATH der Attrappen nicht.
    Eine zweite, gleiche Lesung schließt eine zerrissene Zwischensicht aus.
    """
    ende = time.monotonic() + 5
    vorher = None
    while True:
        if prozess.poll() is not None:
            ok(False, "Serverprozess endete vor der Umgebungsprüfung")
        try:
            with open("/proc/%d/cmdline" % prozess.pid, "rb") as handle:
                befehl = handle.read().split(b"\0")
            with open("/proc/%d/environ" % prozess.pid, "rb") as handle:
                roh = handle.read()
        except OSError:
            befehl, roh = [], b""
        # PATH muss als eigener Eintrag dastehen, nicht nur irgendwo im Text.
        if b"server.py" in befehl and b"\0PATH=" in b"\0" + roh:
            if roh == vorher:
                return dict(teil.split(b"=", 1) for teil in roh.split(b"\0") if b"=" in teil)
            vorher = roh
        else:
            vorher = None
        if time.monotonic() >= ende:
            ok(False, "Serverumgebung wurde nicht sichtbar")
        time.sleep(0.005)


def anfrage(port, methode, pfad, body=None, token=None, host=None, origin=None, extra=None):
    con = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    kopf = {"Host": host or ("127.0.0.1:%d" % port)}
    if origin:
        kopf["Origin"] = origin
    if token:
        kopf["X-Omaclusive-Token"] = token
    if extra:
        kopf.update(extra)
    daten = None
    if body is not None:
        daten = json.dumps(body).encode()
        kopf["Content-Type"] = "application/json"
    con.request(methode, pfad, daten, kopf)
    antwort = con.getresponse()
    roh = antwort.read().decode()
    try:
        inhalt = json.loads(roh) if roh[:1] in "{[" else roh
    except json.JSONDecodeError:
        inhalt = roh
    return antwort.status, inhalt


def main():
    # Ordnerwahl stimmt mit der Shell überein (privat oder der eigene run-Ordner).
    home_probe = tempfile.mkdtemp(prefix="omaclusive-ordner-")
    try:
        env = dict(os.environ, HOME=home_probe)
        env.pop("XDG_RUNTIME_DIR", None)
        py = subprocess.check_output(
            [sys.executable, "-c", "import sitzung; print(sitzung.ordner(), end='')"],
            cwd=DIR, env=env, text=True)
        sh = subprocess.check_output(
            ["bash", "-c", "source startlib.sh; omaclusive_sitzung_ordner"],
            cwd=DIR, env=env, text=True).strip()
        ok(py == sh == os.path.join(home_probe, ".local", "share", "omaclusive", "run"), "Ordner ohne Laufzeitverzeichnis: " + py)
        privat = tempfile.mkdtemp(prefix="omaclusive-runtime-")
        os.chmod(privat, 0o700)
        env["XDG_RUNTIME_DIR"] = privat
        py = subprocess.check_output(
            [sys.executable, "-c", "import sitzung; print(sitzung.ordner(), end='')"],
            cwd=DIR, env=env, text=True)
        sh = subprocess.check_output(
            ["bash", "-c", "source startlib.sh; omaclusive_sitzung_ordner"],
            cwd=DIR, env=env, text=True).strip()
        ok(py == sh == os.path.join(privat, "omaclusive"), "privates Laufzeitverzeichnis: " + py)
        offen = tempfile.mkdtemp(prefix="omaclusive-offen-")
        os.chmod(offen, 0o755)
        env["XDG_RUNTIME_DIR"] = offen
        py = subprocess.check_output(
            [sys.executable, "-c", "import sitzung; print(sitzung.ordner(), end='')"],
            cwd=DIR, env=env, text=True)
        ok(py.startswith(home_probe), "offenes Laufzeitverzeichnis wird nicht benutzt")
    finally:
        shutil.rmtree(home_probe, ignore_errors=True)

    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        port = so.getsockname()[1]
    home = tempfile.mkdtemp(prefix="omaclusive-sitzung-")
    protokoll = os.path.join(home, "befehle.log")
    bin_dir = os.path.join(home, "bin")
    os.makedirs(bin_dir)
    attrappe = "#!/bin/sh\nprintf '%s %s\\n' \"$(basename \"$0\")\" \"$*\" >> \"$OMACLUSIVE_CMDLOG\"\nexit 0\n"
    for name in ("systemctl", "loginctl", "chromium", "google-chrome", "xdg-open"):
        pfad = os.path.join(bin_dir, name)
        with open(pfad, "w", encoding="utf-8") as handle:
            handle.write(attrappe)
        os.chmod(pfad, 0o755)
    cfg = os.path.join(DIR, "config.json")
    sicher = None
    if os.path.exists(cfg):
        sicher = os.path.join(home, "config.original")
        shutil.copy(cfg, sicher)
    shutil.copy(os.path.join(DIR, "config.example.json"), cfg)
    env = dict(os.environ)
    env.pop("XDG_RUNTIME_DIR", None)
    env.update(PORT=str(port), HOME=home, PATH=bin_dir + os.pathsep + env.get("PATH", ""), OMACLUSIVE_CMDLOG=protokoll)
    srv = subprocess.Popen([sys.executable, "server.py"], cwd=DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        kinder = server_umgebung(srv)
        ok(kinder.get(b"PATH", b"").split(b":")[0] == bin_dir.encode(), "Server benutzt die Attrappen")
        alt_xdg = os.environ.pop("XDG_RUNTIME_DIR", None)
        geheim = None
        for _ in range(60):
            try:
                st, bereit = anfrage(port, "GET", "/api/bereit")
                if st == 200 and isinstance(bereit, dict) and bereit.get("ok") is True:
                    geheim = sitzung.lesen(port, home)
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.1)
        ok(bool(geheim), "Server und Sitzungsdatei sind da")
        datei = sitzung.datei(port, home)
        ok(modus(datei) == 0o600, "Sitzungsdatei ist 0600: %o" % modus(datei))
        ok(modus(os.path.dirname(datei)) == 0o700, "Sitzungsordner ist 0700")
        ok(gebunden(port), "Server hört auf 127.0.0.1")
        ok("00000000:%04X" % port not in open("/proc/net/tcp", encoding="ascii").read().upper(), "nicht auf allen Schnittstellen")

        st, seite = anfrage(port, "GET", "/index.html")
        ok(st == 200 and "sitzung.js" in seite and geheim not in seite, "Seite ohne Geheimnis")
        st, skript = anfrage(port, "GET", "/sitzung.js")
        ok(st == 200 and geheim not in skript, "Skript ohne Geheimnis")
        st, _ = anfrage(port, "GET", "/config.json")
        ok(st == 403, "config.json ohne Geheimnis: 403")
        st, cfg_text = anfrage(port, "GET", "/config.json", token=geheim)
        ok(st == 200 and isinstance(cfg_text, dict) and cfg_text.get("language") == "de", "config.json mit Geheimnis")
        st, _ = anfrage(port, "GET", "/foo/../config.json")
        ok(st == 403, "config.json über .. ohne Geheimnis: 403")

        st, katalog = anfrage(port, "GET", "/api/bausteine", token=geheim)
        ok(st == 200 and any(e.get("name") == "system.poweroff" for e in katalog.get("bausteine", [])), "Bausteine mit Geheimnis")
        st, pfad = anfrage(port, "GET", "/api/pfad", token=geheim)
        ok(st == 200 and pfad.get("ok") is True and pfad.get("modus") == "b", "Pfad mit Geheimnis")
        vorher = logtext(protokoll)
        ok("poweroff" not in vorher and "reboot" not in vorher, "Lesen löst kein Ausschalten aus")

        st, _ = anfrage(port, "GET", "/api/open?url=http://example.com/", token=geheim)
        ok(st == 405 and "chromium" not in logtext(protokoll), "GET /api/open tut nichts")
        st, _ = anfrage(port, "GET", "/api/back", token=geheim)
        ok(st == 405, "GET /api/back: 405")
        st, _ = anfrage(port, "GET", "/api/pick?folder=1", token=geheim)
        ok(st == 405, "GET /api/pick: 405")
        st, _ = anfrage(port, "GET", "/api/hinweis", token=geheim)
        ok(st == 405, "GET /api/hinweis: 405")
        st, _ = anfrage(port, "POST", "/api/open", {"url": "http://example.com/"}, token=None)
        ok(st == 403 and "chromium" not in logtext(protokoll), "POST /api/open ohne Geheimnis: 403")
        st, _ = anfrage(port, "POST", "/api/open", {"url": "http://example.com/"}, token=geheim, origin="http://evil.example")
        ok(st == 403 and "chromium" not in logtext(protokoll), "POST /api/open fremde Herkunft: 403")
        st, _ = anfrage(port, "POST", "/api/open", {"url": "http://example.com/"}, token=geheim, host="evil.example:%d" % port)
        ok(st == 403 and "chromium" not in logtext(protokoll), "POST /api/open fremder Host: 403")
        st, _ = anfrage(port, "POST", "/api/open", {"url": "http://example.com/"}, token="falsch")
        ok(st == 403 and "chromium" not in logtext(protokoll), "POST /api/open falsches Geheimnis: 403")
        st, offen = anfrage(port, "POST", "/api/open", {"url": "http://example.com/a"}, token=geheim)
        for _ in range(30):
            if "chromium" in logtext(protokoll):
                break
            time.sleep(0.05)
        ok(st == 200 and isinstance(offen, dict) and offen.get("ok") is True and "chromium" in logtext(protokoll),
           "POST /api/open mit Geheimnis öffnet: %s %s" % (st, offen))

        st, _ = anfrage(port, "POST", "/api/baustein", {"name": "system.poweroff", "confirm": True})
        ok(st == 403 and "poweroff" not in logtext(protokoll), "Ausschalten ohne Geheimnis: 403")
        st, _ = anfrage(port, "POST", "/api/baustein", {"name": "system.reboot", "confirm": True}, token=geheim, origin="http://evil.example")
        ok(st == 403 and "reboot" not in logtext(protokoll), "Neustart fremde Herkunft: 403")
        st, frage = anfrage(port, "POST", "/api/baustein", {"name": "system.poweroff", "confirm": True}, token=geheim)
        ok(st == 200 and frage.get("bestaetigen") is True and frage.get("ok") is not True and frage.get("bestaetigung"), "confirm allein schaltet nicht aus")
        ok("poweroff" not in logtext(protokoll), "kein systemctl poweroff nach confirm")
        st, _ = anfrage(port, "POST", "/api/baustein", {"name": "system.poweroff", "confirm": True, "bestaetigung": frage["bestaetigung"]}, token=geheim, origin="null")
        ok(st == 403 and "poweroff" not in logtext(protokoll), "Freigabe mit fremder Herkunft reicht nicht")
        st, aus = anfrage(port, "POST", "/api/baustein", {"name": "system.poweroff", "bestaetigung": frage["bestaetigung"]}, token=geheim)
        ok(st == 200 and aus.get("ok") is True and logtext(protokoll).count("systemctl poweroff") == 1, "Ja mit Freigabe schaltet aus (Attrappe)")
        st, nochmal = anfrage(port, "POST", "/api/baustein", {"name": "system.poweroff", "confirm": True, "bestaetigung": frage["bestaetigung"]}, token=geheim)
        ok(nochmal.get("ok") is not True and logtext(protokoll).count("systemctl poweroff") == 1, "dieselbe Freigabe gilt nur einmal")
        st, neu = anfrage(port, "POST", "/api/baustein", {"name": "system.reboot", "confirm": True}, token=geheim)
        ok(neu.get("bestaetigen") is True and "reboot" not in logtext(protokoll), "Neustart wartet auf die Freigabe")
        st, start = anfrage(port, "POST", "/api/baustein", {"name": "system.reboot", "bestaetigung": neu["bestaetigung"]}, token=geheim)
        ok(start.get("ok") is True and "systemctl reboot" in logtext(protokoll), "Neustart mit Freigabe (Attrappe)")

        boot = sitzung.boot_schreiben(port, "", home)
        ok(modus(boot) == 0o600, "Startdatei ist 0600")
        with open(boot, encoding="utf-8") as handle:
            html = handle.read()
        ok(geheim in html and html.startswith("<!doctype html>"), "Startdatei trägt das Geheimnis nur lokal")
        url = sitzung.boot_url(port, "setup.html", home)
        ok(url.startswith("file://") and geheim not in url, "Befehlszeile enthält das Geheimnis nicht")
    finally:
        if "alt_xdg" in locals() and alt_xdg is not None:
            os.environ["XDG_RUNTIME_DIR"] = alt_xdg
        srv.terminate()
        try:
            srv.wait(5)
        except subprocess.TimeoutExpired:
            srv.kill()
        if sicher:
            shutil.copy(sicher, cfg)
        else:
            try:
                os.remove(cfg)
            except OSError:
                pass
        bak = cfg + ".bak"
        if os.path.exists(bak) and not sicher:
            try:
                os.remove(bak)
            except OSError:
                pass
        shutil.rmtree(home, ignore_errors=True)
    print("SITZUNG_OK")


if __name__ == "__main__":
    main()
