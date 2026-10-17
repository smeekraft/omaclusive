#!/bin/bash
# Testfenster: kein Kiosk. ?test=1 öffnet keine Links und keine Dateien.
# Port 8795, eigenes Fensterprofil. Beendet vorher alte Omaclusive-Server und -Fenster.
DIR="$(cd "$(dirname "$0")" && pwd)"; PORT=8795
. "$DIR/startlib.sh"
SPRACHE=$(grep -o '"language": *"[a-z]*"' "$DIR/config.json" 2>/dev/null | grep -o '[a-z]*"$' | tr -d '"'); SPRACHE=${SPRACHE:-de}
BR=$(command -v chromium || command -v google-chrome)
omaclusive_alte_beenden "$DIR" "$PORT"
omaclusive_server_starten "$DIR" "$PORT" || exit 1
omaclusive_fokus omaclusive-test
exec "$BR" --user-data-dir="$HOME/.local/share/omaclusive/fenster" --class=omaclusive-test \
  --app="http://127.0.0.1:$PORT/?test=1" \
  --window-size=1480,780 --no-first-run --no-default-browser-check \
  --disable-translate --disable-features=Translate,TranslateUI --lang="$SPRACHE" \
  --autoplay-policy=no-user-gesture-required
