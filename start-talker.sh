#!/bin/bash
# Startet Omaclusive im Vollbild. Port 8795.
# Beendet vorher alte Omaclusive-Server und -Fenster, damit nichts doppelt läuft oder spielt.
DIR="$(cd "$(dirname "$0")" && pwd)"; PORT=8795
. "$DIR/startlib.sh"
SPRACHE=$(grep -o '"language": *"[a-z]*"' "$DIR/config.json" 2>/dev/null | grep -o '[a-z]*"$' | tr -d '"'); SPRACHE=${SPRACHE:-de}
BR=$(command -v chromium || command -v google-chrome)
omaclusive_alte_beenden "$DIR" "$PORT"
omaclusive_server_starten "$DIR" "$PORT" || exit 1
omaclusive_fokus omaclusive
exec "$BR" --user-data-dir="$HOME/.local/share/omaclusive/kiosk" --class=omaclusive \
  --app="http://127.0.0.1:$PORT/${1:-}" \
  --start-fullscreen --kiosk --no-first-run --no-default-browser-check \
  --disable-translate --disable-features=Translate,TranslateUI --lang="$SPRACHE" \
  --autoplay-policy=no-user-gesture-required
