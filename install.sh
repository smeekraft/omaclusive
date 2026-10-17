#!/bin/bash
# Omaclusive installieren, ohne Root. Lädt Piper und die Stimme und prüft die Summe.
# Install Omaclusive without root. Downloads Piper and the voice and checks the checksum.
# Sprache / language:  ./install.sh --lang en   (oder / or  OMACLUSIVE_LANG=en ./install.sh). Standard / default: de
# Fasst den bisher installierten Talker nicht an und ändert keine Tasten.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
LANGUAGE="${OMACLUSIVE_LANG:-de}"
while [ $# -gt 0 ]; do
  case "$1" in
    --lang) LANGUAGE="${2:-de}"; shift 2 ;;
    --lang=*) LANGUAGE="${1#--lang=}"; shift ;;
    *) echo "Unbekannte Option / unknown option: $1"; exit 1 ;;
  esac
done
case "$LANGUAGE" in
  de|en) ;;
  *) echo "Sprache '$LANGUAGE' gibt es nicht, nehme Englisch / language not available, using English"; LANGUAGE=en ;;
esac
DEST="${HOME}/.local/share/omaclusive"
APPS="${HOME}/.local/share/applications"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
PIPER_SHA="a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992"
if [ "$LANGUAGE" = "en" ]; then
  # English: LJ Speech voice (public domain)
  VOICE_NAME="en_US-ljspeech-medium"
  VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/medium/en_US-ljspeech-medium.onnx"
  VOICE_SHA="6f52a751e2349abe7a76735eb09dc1875298c77ea2342ffd2fef79ff81b87f22"
  VOICE_JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/medium/en_US-ljspeech-medium.onnx.json"
  VOICE_JSON_SHA="141d612cc0a95ed7efc1ca936b845c2364967f2e9217c5dbfcf69fc4d6c65860"
  CONFIG_QUELLE="config.example.en.json"
else
  VOICE_NAME="de_DE-thorsten-medium"
  VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/${VOICE_NAME}.onnx"
  VOICE_SHA="7e64762d8e5118bb578f2eea6207e1a35a8e0c30595010b666f983fc87bb7819"
  VOICE_JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/${VOICE_NAME}.onnx.json"
  VOICE_JSON_SHA="974adee790533adb273a1ac88f49027d2a1b8f0f2cf4905954a4791e79264e85"
  CONFIG_QUELLE="config.example.json"
fi

lade() {
  local url="$1" ziel="$2" summe="$3" teil
  teil="${ziel}.teil"
  curl -fsSL -o "$teil" "$url"
  if ! printf '%s  %s\n' "$summe" "$teil" | sha256sum -c -; then
    rm -f "$teil"
    echo "Prüfsumme stimmt nicht."
    exit 1
  fi
  mv "$teil" "$ziel"
}

echo "== Omaclusive wird nach ${DEST} gelegt. Der bisherige Talker bleibt."
mkdir -p "$DEST" "$APPS" "${DEST}/voices"
for f in index.html setup.html editor.html modi.json modi.py app.js pfad.js sprache.js i18n.py sprache_wechseln.py audio_erzeugen.py \
  server.py bausteine.py hilferuf.py praxis.py ohr.py config.example.json config.example.en.json \
  start-talker.sh start-talker-fenster.sh startlib.sh zurueck.sh README.md README.de.md LICENSE CREDITS.md; do
  cp "$SRC/$f" "$DEST/"
done
rm -rf "${DEST}/img" "${DEST}/plugins" "${DEST}/locales" "${DEST}/audio"
cp -a "$SRC/img" "$DEST/img"
cp -a "$SRC/locales" "$DEST/locales"
[ -d "$SRC/audio" ] && cp -a "$SRC/audio" "$DEST/audio"
cp -a "$SRC/plugins" "$DEST/plugins"
if [ -d "$SRC/ohr" ]; then
  rm -rf "${DEST}/ohr"
  cp -a "$SRC/ohr" "$DEST/ohr"
fi
chmod +x "$DEST"/*.sh "$DEST/server.py"

if [ -x "${DEST}/piper/piper" ] && [ "$(cat "${DEST}/piper/.summe" 2>/dev/null || true)" = "$PIPER_SHA" ]; then
  echo "== Piper ist schon geprüft."
else
  echo "== Piper wird geladen."
  tmp="$(mktemp -d)"
  lade "$PIPER_URL" "$tmp/piper.tar.gz" "$PIPER_SHA"
  mkdir -p "$tmp/aus"
  tar -xzf "$tmp/piper.tar.gz" -C "$tmp/aus"
  bin="$(find "$tmp/aus" -type f -name piper -print -quit)"
  if [ -z "$bin" ]; then
    echo "Das Piper-Archiv enthält das Programm nicht."
    rm -rf "$tmp"
    exit 1
  fi
  rm -rf "${DEST}/piper"
  mkdir -p "${DEST}/piper"
  cp -a "$(dirname "$bin")/." "${DEST}/piper/"
  printf '%s\n' "$PIPER_SHA" > "${DEST}/piper/.summe"
  rm -rf "$tmp"
fi

if [ -f "${DEST}/voices/${VOICE_NAME}.onnx" ] && printf '%s  %s\n' "$VOICE_SHA" "${DEST}/voices/${VOICE_NAME}.onnx" | sha256sum -c - >/dev/null; then
  echo "== Stimme ist schon geprüft."
else
  echo "== Stimme wird geladen."
  lade "$VOICE_URL" "${DEST}/voices/${VOICE_NAME}.onnx" "$VOICE_SHA"
fi
if [ -f "${DEST}/voices/${VOICE_NAME}.onnx.json" ] && printf '%s  %s\n' "$VOICE_JSON_SHA" "${DEST}/voices/${VOICE_NAME}.onnx.json" | sha256sum -c - >/dev/null; then
  echo "== Stimmdaten sind schon geprüft."
else
  lade "$VOICE_JSON_URL" "${DEST}/voices/${VOICE_NAME}.onnx.json" "$VOICE_JSON_SHA"
fi

if [ -f "${DEST}/config.json" ]; then
  echo "== Vorhandene config.json bleibt."
else
  if [ -f "$SRC/config.json" ]; then
    cp "$SRC/config.json" "${DEST}/config.json"
  else
    cp "$SRC/$CONFIG_QUELLE" "${DEST}/config.json"
  fi
  DEST="$DEST" python3 - <<'PY'
import json, os
pfad = os.path.join(os.environ["DEST"], "config.json")
with open(pfad, encoding="utf-8") as handle:
    daten = json.load(handle)
daten.setdefault("einrichtung", {})["fertig"] = False
with open(pfad, "w", encoding="utf-8") as handle:
    json.dump(daten, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY
  echo "== Neue Kopie stellt die erste Frage."
fi

cat > "$APPS/omaclusive.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Omaclusive
Comment=Offene Bild-Fernbedienung
Exec=${DEST}/start-talker.sh
Icon=${DEST}/img/sagen.svg
Categories=Utility;Accessibility;
EOF
cat > "$APPS/omaclusive-einrichten.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Omaclusive einrichten
Exec=${DEST}/start-talker.sh setup.html
Icon=${DEST}/img/anpassen.svg
Categories=Utility;Accessibility;
EOF
cat > "$APPS/omaclusive-testen.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Omaclusive testen
Comment=Fenster zum Ausprobieren
Exec=${DEST}/start-talker-fenster.sh
Icon=${DEST}/img/sagen.svg
Categories=Utility;Accessibility;
EOF
update-desktop-database "$APPS" >/dev/null 2>&1 || true

fehlend=""
command -v python3 >/dev/null || fehlend="${fehlend} python3"
command -v chromium >/dev/null || fehlend="${fehlend} chromium"
command -v curl >/dev/null || fehlend="${fehlend} curl"
command -v mpv >/dev/null || echo "== mpv fehlt. Filme sagen dann, dass es hier nicht geht."
command -v espeak-ng >/dev/null || echo "== espeak-ng fehlt. Ohne Piper gibt es dann keine Ersatzstimme."
if [ -n "$fehlend" ]; then
  echo "== Es fehlt noch:${fehlend}"
  echo "   Bitte nachinstallieren. Dieses Skript ruft dafür kein Root auf."
else
  echo "== Die Grundprogramme sind da."
fi
echo
echo "Fertig. Im App-Menü nach Omaclusive suchen. Es startet nicht von selbst."
echo "Der bisherige Talker bleibt, wo er ist."
