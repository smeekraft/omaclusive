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


def ordner_wie_shell(env, cwd):
    py = subprocess.check_output(
        [sys.executable, "-c", "import sitzung; print(sitzung.ordner(), end='')"],
        cwd=cwd, env=env, text=True)
    sh = subprocess.check_output(
        ["bash", "-c", "source startlib.sh; omaclusive_sitzung_ordner"],
        cwd=cwd, env=env, text=True).strip()
    return py, sh


def server_log(pfad):
    try:
        with open(pfad, encoding="utf-8", errors="replace") as handle:
            return handle.read()[-2000:]
    except OSError:
        return ""


def warte_bereit(port):
    for _ in range(60):
        try:
            st, bereit = anfrage(port, "GET", "/api/bereit")
            if st == 200 and isinstance(bereit, dict) and bereit.get("ok") is True:
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.1)
    return False


def sitzung_vom_server(env, cwd):
    roh = subprocess.check_output(
        [sys.executable, "-c",
         "import os, sitzung\n"
         "p = int(os.environ['PORT'])\n"
         "print(sitzung.datei(p))\n"
         "print(sitzung.lesen(p))"],
        cwd=cwd, env=env, text=True)
    zeilen = roh.splitlines()
    ok(len(zeilen) == 2 and zeilen[1], "Sitzungsdatei lesbar: %r" % roh)
    return zeilen[0], zeilen[1]


def kein_geheimnis(port, url, geheim, text):
    st, inhalt = anfrage(port, "GET", url)
    ok(st == 404 and geheim not in str(inhalt), "%s: %s %s" % (text, st, url))


def log_pflanzen(wurzel, phrase, mit_hallo=False):
    """log.txt mit einem gesprochenen Satz, wie eine alte Datei im Installationsordner."""
    pfade = []
    for name in ("log.txt", "log.txt.1"):
        pfad = os.path.join(wurzel, name)
        with open(pfad, "w", encoding="utf-8") as handle:
            handle.write("Keine Stimme für: %s\n" % phrase)
        os.chmod(pfad, 0o644)
        pfade.append(pfad)
    link = os.path.join(wurzel, "log-leak.txt")
    os.symlink(os.path.join(wurzel, "log.txt"), link)
    pfade.append(link)
    if mit_hallo:
        hallo = os.path.join(wurzel, "hallo.txt")
        with open(hallo, "w", encoding="utf-8") as handle:
            handle.write("hallo-static")
        pfade.append(hallo)
    return pfade


def log_anfragen(port, phrase, geheim, beschreibung):
    """GET ohne und mit Sitzungsgeheimnis liefert den gesprochenen Satz nicht."""
    urls = ("/log.txt", "/log.txt.1", "/log-leak.txt", "/a/../log.txt", "/log%2etxt", "/log.txt?x=1")
    for url in urls:
        kein_geheimnis(port, url, phrase, beschreibung + " " + url)
        st, inhalt = anfrage(port, "GET", url, token=geheim)
        ok(st == 404 and phrase not in str(inhalt), "%s mit Geheimnis: %s %s" % (beschreibung, st, url))
    st, inhalt = anfrage(port, "HEAD", "/log.txt")
    ok(st == 404 and phrase not in str(inhalt), beschreibung + " HEAD /log.txt: %s" % st)


def kopiere_installation(home):
    ziel = os.path.join(home, ".local", "share", "omaclusive")
    os.makedirs(ziel)
    os.chmod(ziel, 0o755)
    for name in ("server.py", "sitzung.py", "hilferuf.py", "i18n.py", "praxis.py"):
        shutil.copy(os.path.join(DIR, name), os.path.join(ziel, name))
    return ziel


def pruefe_nicht_per_http(env, install, beschreibung, prefix):
    """Server aus der Installationskopie: GET holt die Sitzungsdatei nicht."""
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        port = so.getsockname()[1]
    env = dict(env)
    env["PORT"] = str(port)
    env["PYTHONUNBUFFERED"] = "1"
    logpfad = os.path.join(env["HOME"], "server-%s.err" % port)
    log = open(logpfad, "w", encoding="utf-8")
    phrase = "GEHEIM-ansage-" + beschreibung.replace(" ", "-")
    lecks = log_pflanzen(install, phrase, mit_hallo=True)
    srv = subprocess.Popen([sys.executable, "server.py"], cwd=install, env=env, stdout=log, stderr=subprocess.STDOUT)
    fehler = None
    try:
        ok(warte_bereit(port), "Server (%s) antwortet nicht: %s" % (beschreibung, server_log(logpfad)))
        ok(modus(os.path.join(install, "log.txt")) == 0o600, beschreibung + ": alte log.txt ist 0600")
        ok(modus(os.path.join(install, "log.txt.1")) == 0o600, beschreibung + ": alte log.txt.1 ist 0600")
        with open(os.path.join(install, "log.txt"), encoding="utf-8") as handle:
            ok(phrase in handle.read(), beschreibung + ": Loginhalt bleibt erhalten")
        datei, geheim = sitzung_vom_server(env, install)
        log_anfragen(port, phrase, geheim, beschreibung + " Log")
        st, inhalt = anfrage(port, "GET", "/hallo.txt")
        ok(st == 200 and inhalt == "hallo-static", beschreibung + ": normale Datei bleibt erreichbar: %s" % st)
        with open(datei, encoding="ascii") as handle:
            ok(geheim in handle.read(), beschreibung + ": Datei enthält das Geheimnis")
        ok(modus(datei) == 0o600, beschreibung + ": Datei ist 0600")
        ok(modus(os.path.dirname(datei)) == 0o700, beschreibung + ": Ordner ist 0700")
        ok(not sitzung.liegt_in(datei, install), beschreibung + ": Datei liegt in der Web-Wurzel: " + datei)
        ok(not sitzung.liegt_in(os.path.dirname(datei), install), beschreibung + ": Ordner liegt in der Web-Wurzel")
        ok(os.path.realpath(datei).startswith(os.path.realpath(prefix) + os.sep), beschreibung + ": unerwarteter Ort " + datei)
        for url in (
            "/run/%d.session" % port,
            "/%d.session" % port,
            "/run/%d.boot.html" % port,
            "/%d.boot.html" % port,
            "/run/%d%%2esession" % port,
        ):
            kein_geheimnis(port, url, geheim, beschreibung)
        alt = os.path.join(install, "run")
        os.makedirs(alt, exist_ok=True)
        pflanze = os.path.join(alt, "%d.session" % port)
        with open(pflanze, "w", encoding="ascii") as handle:
            handle.write(geheim + "\n")
        lecks.append(pflanze)
        kein_geheimnis(port, "/run/%d.session" % port, geheim, beschreibung + ", gepflanzte Datei")
        link = os.path.join(install, "sitzung-leak.txt")
        os.symlink(datei, link)
        lecks.append(link)
        kein_geheimnis(port, "/sitzung-leak.txt", geheim, beschreibung + ", Verweis")
        boot = subprocess.check_output(
            [sys.executable, "-c",
             "import os, sitzung; print(sitzung.boot_schreiben(int(os.environ['PORT']), ''), end='')"],
            cwd=install, env=env, text=True)
        with open(boot, encoding="utf-8") as handle:
            ok(geheim in handle.read(), beschreibung + ": Startdatei lokal")
        ok(not sitzung.liegt_in(boot, install), beschreibung + ": Startdatei in der Web-Wurzel: " + boot)
        bootlink = os.path.join(install, "boot-leak.txt")
        os.symlink(boot, bootlink)
        lecks.append(bootlink)
        kein_geheimnis(port, "/boot-leak.txt", geheim, beschreibung + ", Startdatei-Verweis")
        kein_geheimnis(port, "/%d.boot.html" % port, geheim, beschreibung + ", boot.html")
    except BaseException as exc:
        fehler = exc
        raise
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()
        if fehler is not None:
            sys.stderr.write(server_log(logpfad))
        for pfad in lecks:
            try:
                os.remove(pfad)
            except OSError:
                pass


def main():
    # Ordnerwahl stimmt mit der Shell überein und liegt nie unter der Web-Wurzel.
    home_probe = tempfile.mkdtemp(prefix="omaclusive-ordner-")
    reste = [home_probe]
    fallback = os.path.join(home_probe, ".local", "state", "omaclusive", "run")
    try:
        env = dict(os.environ, HOME=home_probe)
        env.pop("XDG_RUNTIME_DIR", None)
        py, sh = ordner_wie_shell(env, DIR)
        ok(py == sh == fallback, "Ordner ohne Laufzeitverzeichnis: " + py)
        ok(sitzung.liegt_in(os.path.join(home_probe, "a", "b"), home_probe), "liegt_in erkennt Unterordner")
        ok(not sitzung.liegt_in(home_probe + "-x", home_probe), "liegt_in verwechselt keine Nachbarn")
        privat = tempfile.mkdtemp(prefix="omaclusive-runtime-")
        reste.append(privat)
        os.chmod(privat, 0o700)
        env["XDG_RUNTIME_DIR"] = privat
        py, sh = ordner_wie_shell(env, DIR)
        ok(py == sh == os.path.join(privat, "omaclusive"), "privates Laufzeitverzeichnis: " + py)
        offen = tempfile.mkdtemp(prefix="omaclusive-offen-")
        reste.append(offen)
        os.chmod(offen, 0o755)
        env["XDG_RUNTIME_DIR"] = offen
        py, sh = ordner_wie_shell(env, DIR)
        ok(py == sh == fallback, "offenes Laufzeitverzeichnis wird nicht benutzt: " + py)
        innen = tempfile.mkdtemp(prefix=".omaclusive-runtime-", dir=DIR)
        reste.append(innen)
        os.chmod(innen, 0o700)
        env["XDG_RUNTIME_DIR"] = innen
        py, sh = ordner_wie_shell(env, DIR)
        ok(py == sh == fallback, "Laufzeitverzeichnis in der Web-Wurzel wird nicht benutzt: " + py)
        install_runtime = os.path.join(home_probe, ".local", "share", "omaclusive", "runtime")
        os.makedirs(install_runtime)
        os.chmod(install_runtime, 0o700)
        env["XDG_RUNTIME_DIR"] = install_runtime
        py, sh = ordner_wie_shell(env, DIR)
        ok(py == sh == fallback, "Laufzeitverzeichnis im Installationsordner wird nicht benutzt: " + py)
        state_link = os.path.join(home_probe, ".local", "state")
        os.symlink(os.path.join(home_probe, ".local", "share", "omaclusive"), state_link)
        env.pop("XDG_RUNTIME_DIR", None)
        py, sh = ordner_wie_shell(env, DIR)
        privat_fallback = os.path.join(home_probe, ".omaclusive-private", "run")
        ok(py == sh == privat_fallback, "state-Verweis in die Web-Wurzel wird nicht benutzt: " + py)
        ok(not sitzung.liegt_in(py, os.path.join(home_probe, ".local", "share", "omaclusive")), "Fallback bleibt außerhalb")
    finally:
        for pfad in reste:
            shutil.rmtree(pfad, ignore_errors=True)

    # HOME ist selbst die Web-Wurzel: weder state noch der private Ordner daneben sind sicher.
    baum = tempfile.mkdtemp(prefix="omaclusive-heim-")
    try:
        shutil.copy(os.path.join(DIR, "sitzung.py"), baum)
        shutil.copy(os.path.join(DIR, "startlib.sh"), baum)
        env = dict(os.environ, HOME=baum)
        env.pop("XDG_RUNTIME_DIR", None)
        py, sh = ordner_wie_shell(env, baum)
        tmp_ordner = "/tmp/omaclusive-%d/run" % os.getuid()
        ok(py == sh == tmp_ordner, "Home in der Web-Wurzel weicht nach /tmp aus: " + py)
        with socket.socket() as so:
            so.bind(("127.0.0.1", 0))
            port = so.getsockname()[1]
        env["PORT"] = str(port)
        subprocess.check_call(
            [sys.executable, "-c", "import os, sitzung; sitzung.anlegen(int(os.environ['PORT']))"],
            cwd=baum, env=env)
        datei = os.path.join(tmp_ordner, "%d.session" % port)
        ok(modus(datei) == 0o600, "Ausweichdatei ist 0600")
        ok(modus(tmp_ordner) == 0o700, "Ausweichordner ist 0700")
        ok(not sitzung.liegt_in(datei, baum), "Ausweichdatei liegt in der Web-Wurzel")
        os.remove(datei)
        try:
            os.rmdir(tmp_ordner)
            os.rmdir(os.path.dirname(tmp_ordner))
        except OSError:
            pass
    finally:
        shutil.rmtree(baum, ignore_errors=True)

    # Installiertes Layout: Web-Wurzel ist ~/.local/share/omaclusive. GET /run/<port>.session bleibt leer.
    home_install = tempfile.mkdtemp(prefix="omaclusive-install-")
    privat_http = None
    try:
        install = kopiere_installation(home_install)
        basis = dict(os.environ, HOME=home_install)
        basis.pop("XDG_RUNTIME_DIR", None)
        basis.pop("PYTHONPATH", None)
        pruefe_nicht_per_http(basis, install, "Fallback", os.path.join(home_install, ".local", "state", "omaclusive", "run"))
        privat_http = tempfile.mkdtemp(prefix="omaclusive-xdg-")
        os.chmod(privat_http, 0o700)
        env = dict(basis)
        env["XDG_RUNTIME_DIR"] = privat_http
        pruefe_nicht_per_http(env, install, "Laufzeitverzeichnis", os.path.join(privat_http, "omaclusive"))
        innen_http = os.path.join(install, "runtime")
        os.makedirs(innen_http)
        os.chmod(innen_http, 0o700)
        env = dict(basis)
        env["XDG_RUNTIME_DIR"] = innen_http
        pruefe_nicht_per_http(env, install, "abgelehntes Laufzeitverzeichnis", os.path.join(home_install, ".local", "state", "omaclusive", "run"))
        ok(not os.path.exists(os.path.join(innen_http, "omaclusive")), "abgelehntes Laufzeitverzeichnis bleibt ohne Sitzungsordner")
    finally:
        if privat_http:
            shutil.rmtree(privat_http, ignore_errors=True)
        shutil.rmtree(home_install, ignore_errors=True)

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
    lecks = []
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
        ok(not sitzung.liegt_in(datei, DIR), "Sitzungsdatei liegt in der Web-Wurzel: " + datei)
        ok(not sitzung.liegt_in(datei, os.path.join(home, ".local", "share", "omaclusive")), "Sitzungsdatei liegt im Installationsordner: " + datei)
        ok(os.path.realpath(os.path.dirname(datei)) == os.path.realpath(os.path.join(home, ".local", "state", "omaclusive", "run")),
           "Fallback ist der private state-Ordner: " + datei)
        kein_geheimnis(port, "/run/%d.session" % port, geheim, "GET Fallback-Pfad")
        kein_geheimnis(port, "/%d.session" % port, geheim, "GET Sitzungsname")
        leck = os.path.join(DIR, "sitzung-leak.txt")
        os.symlink(datei, leck)
        lecks.append(leck)
        kein_geheimnis(port, "/sitzung-leak.txt", geheim, "GET Verweis auf die Sitzungsdatei")
        phrase = "GEHEIM-repo-log-7f29"
        for pfad in log_pflanzen(DIR, phrase):
            lecks.append(pfad)
        log_anfragen(port, phrase, geheim, "Web-Wurzel")
        ok(modus(os.path.join(DIR, "log.txt")) == 0o644, "eine später angelegte log.txt bleibt lesbar für den Test, wird aber nicht ausgeliefert")
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
        ok(not sitzung.liegt_in(boot, DIR), "Startdatei liegt in der Web-Wurzel")
        bootlink = os.path.join(DIR, "boot-leak.txt")
        os.symlink(boot, bootlink)
        lecks.append(bootlink)
        kein_geheimnis(port, "/boot-leak.txt", geheim, "GET Verweis auf die Startdatei")
        kein_geheimnis(port, "/%d.boot.html" % port, geheim, "GET boot.html")
    finally:
        for pfad in lecks:
            try:
                os.remove(pfad)
            except OSError:
                pass
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
