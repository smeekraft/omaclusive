#!/bin/bash
# Sagt dem lokalen Omaclusive auf Port 8795, einen Film zu beenden. Startet nichts.
# Das Sitzungsgeheimnis bleibt in der Datei und kommt nicht in die Befehlszeile.
DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=8795
DIR="$DIR" PORT="$PORT" python3 - <<'PY'
import os, sys, urllib.request
sys.path.insert(0, os.environ["DIR"])
import sitzung
port = int(os.environ["PORT"])
try:
    token = sitzung.lesen(port)
except OSError:
    sys.exit(0)
url = "http://127.0.0.1:%d/api/back" % port
req = urllib.request.Request(url, data=b"{}", method="POST", headers={
    "Content-Type": "application/json",
    "Host": "127.0.0.1:%d" % port,
    "X-Omaclusive-Token": token,
})
try:
    urllib.request.urlopen(req, timeout=2).read()
except Exception:
    pass
PY
