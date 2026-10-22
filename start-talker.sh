#!/bin/bash
# Startet Omaclusive im Vollbild. Port 8795.
# Beendet vorher alte Omaclusive-Server und -Fenster, damit nichts doppelt läuft oder spielt.
DIR="$(cd "$(dirname "$0")" && pwd)"; PORT=8795
. "$DIR/startlib.sh"
SPRACHE=$(grep -o '"language": *"[a-z]*"' "$DIR/config.json" 2>/dev/null | grep -o '[a-z]*"$' | tr -d '"'); SPRACHE=${SPRACHE:-de}
BR=$(command -v chromium || command -v google-chrome)
omaclusive_alte_beenden "$DIR" "$PORT"
omaclusive_server_starten "$DIR" "$PORT" || exit 1
BOOT="$(omaclusive_boot "$DIR" "$PORT" "${1:-}")" || exit 1
PROFIL="$HOME/.local/share/omaclusive/kiosk"
mkdir -p "$PROFIL"
chmod 700 "$PROFIL"
omaclusive_fokus omaclusive
exec "$BR" --user-data-dir="$PROFIL" --class=omaclusive \
  --app="$BOOT" \
  --start-fullscreen --kiosk --no-first-run --no-default-browser-check \
  --disable-translate --disable-features=Translate,TranslateUI --lang="$SPRACHE" \
  --autoplay-policy=no-user-gesture-required
