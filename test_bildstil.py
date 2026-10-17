#!/usr/bin/env python3
"""Bildsatz glatt/pixel: Auswahl, Standard, alte Pfade, Plugin-Bilder. Eigener Testserver, eigene Config."""
import http.client, json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path

import praxis

ROOT = Path(__file__).resolve().parent


def holen(port, pfad):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", pfad)
    r = c.getresponse()
    return r.status, r.read()


def main():
    assert praxis.bildstil(None) == "glatt" and praxis.bildstil("") == "glatt"
    assert praxis.bildstil("Pixel") == "pixel" and praxis.bildstil("xyz") == "glatt"
    assert praxis.bild_im_stil(ROOT / "img", "../x.svg", "glatt") is None
    glatt = (ROOT / "img/glatt/ja.svg").read_bytes()
    pixel = (ROOT / "img/pixel/ja.svg").read_bytes()
    assert glatt != pixel
    cfg = ROOT / "config.json"
    sicher = None
    if cfg.exists():
        sicher = tempfile.mktemp(suffix=".json")
        shutil.copy(cfg, sicher)
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0)); port = so.getsockname()[1]
    env = dict(os.environ, PORT=str(port), HOME=tempfile.mkdtemp())
    cfg.write_text("{}", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(ROOT / "server.py")], cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                holen(port, "/img/glatt/ja.svg"); break
            except OSError:
                time.sleep(0.2)
        for stil, erwartet in ((None, glatt), ("glatt", glatt), ("pixel", pixel), ("kaputt", glatt)):
            cfg.write_text(json.dumps({} if stil is None else {"bildstil": stil}), encoding="utf-8")
            code, body = holen(port, "/img/ja.svg")  # alter Pfad
            assert code == 200 and body == erwartet, (stil, "img/ja.svg")
            code, body = holen(port, "/plugins/grundbeduerfnisse/durst.svg")
            soll = (ROOT / "plugins/grundbeduerfnisse" / praxis.bildstil(stil) / "durst.svg").read_bytes()
            assert code == 200 and body == soll, (stil, "plugin")
        cfg.write_text(json.dumps({"bildstil": "pixel"}), encoding="utf-8")
        assert holen(port, "/img/glatt/ja.svg")[1] == glatt  # fester Pfad bleibt fest
        assert holen(port, "/img/pixel/ja.svg")[1] == pixel
        assert holen(port, "/img/gibtsnicht.svg")[0] == 404
    finally:
        proc.terminate(); proc.wait(timeout=10)
        if sicher: shutil.copy(sicher, cfg); os.remove(sicher)
        else: cfg.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        if True:
            # Plugin ohne Stil-Ordner: Datei direkt im Ordner gilt
            plug = Path(tmp) / "plugins" / "demo"
            plug.mkdir(parents=True)
            (plug / "a.svg").write_text("<svg/>", encoding="utf-8")
            assert praxis.plugin_datei(Path(tmp) / "plugins", "demo", "a.svg", "glatt") == (plug / "a.svg").resolve()
            (plug / "pixel").mkdir()
            (plug / "pixel" / "a.svg").write_text("<svg id='p'/>", encoding="utf-8")
            assert praxis.plugin_datei(Path(tmp) / "plugins", "demo", "a.svg", "pixel").parent.name == "pixel"
            assert praxis.plugin_datei(Path(tmp) / "plugins", "demo", "a.svg", "glatt").parent.name == "demo"
    print("BILDSTIL_OK")


if __name__ == "__main__":
    main()
