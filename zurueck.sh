#!/bin/bash
# Sagt dem lokalen Omaclusive auf Port 8795, einen Film zu beenden. Startet nichts.
# Das Sitzungsgeheimnis geht über die Standardeingabe an curl, nicht über die Befehlszeile.
DIR="$(cd "$(dirname "$0")" && pwd)"; PORT=8795
TOKEN=$(python3 "$DIR/sitzung.py" lesen "$PORT" 2>/dev/null) || true
if [ -z "${TOKEN:-}" ]; then
  exit 0
fi
curl --silent --output /dev/null --max-time 2 --config - <<EOF || true
request = "POST"
url = "http://127.0.0.1:${PORT}/api/back"
header = "Content-Type: application/json"
header = "X-Omaclusive-Token: ${TOKEN}"
EOF
