# shellcheck shell=bash
# Gemeinsame Hilfen für start-talker.sh und start-talker-fenster.sh (wird mit "source" geladen).
# Beendet nur eigene, alte Omaclusive-Instanzen, nie fremde Programme.

omaclusive_alte_beenden() {
  local dir="$1" port="$2" pid cmd
  # 1) Server dieses Ordners
  for pid in $(pgrep -f "python3? .*${dir}/server.py" 2>/dev/null); do
    kill "$pid" 2>/dev/null
  done
  # 2) Wer auf dem Omaclusive-Port lauscht und ein server.py ist (z. B. aus einem alten Ordner)
  if command -v ss >/dev/null 2>&1; then
    for pid in $(ss -ltnpH "sport = :${port}" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u); do
      cmd=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null)
      case "$cmd" in
        *python*server.py*) kill "$pid" 2>/dev/null ;;
      esac
    done
  fi
  # 3) Alte Omaclusive-Fenster (eigenes Profil), damit nicht zwei Fenster Ton und Tasten teilen
  pkill -f -- "--user-data-dir=${HOME}/.local/share/omaclusive/kiosk" 2>/dev/null
  pkill -f -- "--user-data-dir=${HOME}/.local/share/omaclusive/fenster" 2>/dev/null
  # kurz warten, bis der Port frei ist
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    curl -s -o /dev/null --max-time 1 "http://127.0.0.1:${port}/" || break
    sleep 0.3
  done
}

# Ordner von server.py. Absichtlich beim Laden: BASH_SOURCE zeigt hier auf diese Datei,
# und die Subshell wechselt nicht das Verzeichnis des Aufrufers.
_omaclusive_programm="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# Rückgabe 0, wenn ziel die Wurzel selbst ist oder darunter liegt.
omaclusive_liegt_in() {
  local ziel="$1" wurzel="$2" z w
  [ -n "$ziel" ] && [ -n "$wurzel" ] || return 1
  z=$(realpath -m -- "$ziel") || return 1
  w=$(realpath -m -- "$wurzel") || return 1
  [ -n "$z" ] && [ -n "$w" ] || return 1
  [ "$z" = "$w" ] && return 0
  case "$z" in
    "$w"/*) return 0 ;;
  esac
  return 1
}

# Der Sitzungsordner darf weder in der Web-Wurzel liegen noch sie enthalten.
omaclusive_sitzung_ungeeignet() {
  local ziel="$1" home="$2" programm="$3" install
  install="${home}/.local/share/omaclusive"
  omaclusive_liegt_in "$ziel" "$programm" && return 0
  omaclusive_liegt_in "$programm" "$ziel" && return 0
  omaclusive_liegt_in "$ziel" "$install" && return 0
  omaclusive_liegt_in "$install" "$ziel" && return 0
  return 1
}

# Gleicher Ordner wie sitzung.py: privates Laufzeitverzeichnis, sonst ein privater
# Ordner außerhalb der Web-Wurzel (nie ~/.local/share/omaclusive/run).
omaclusive_sitzung_ordner() {
  local runtime="${XDG_RUNTIME_DIR:-}" mode owner last home programm ziel
  home="${HOME}"
  programm="${_omaclusive_programm}"
  [ -n "$programm" ] || return 1
  if [ -n "$runtime" ] && [ -d "$runtime" ] && [ ! -L "$runtime" ]; then
    mode="$(stat -c '%a' "$runtime" 2>/dev/null || true)"
    owner="$(stat -c '%u' "$runtime" 2>/dev/null || true)"
    case "$mode" in
      *[!0-9]*) mode="" ;;
    esac
    if [ "$owner" = "$(id -u)" ] && [ -n "$mode" ]; then
      last="${mode: -2}"
      if [ "$last" = "00" ]; then
        ziel="${runtime}/omaclusive"
        if ! omaclusive_sitzung_ungeeignet "$ziel" "$home" "$programm"; then
          printf '%s' "$ziel"
          return 0
        fi
      fi
    fi
  fi
  ziel="${home}/.local/state/omaclusive/run"
  if omaclusive_sitzung_ungeeignet "$ziel" "$home" "$programm"; then
    ziel="${home}/.omaclusive-private/run"
  fi
  if omaclusive_sitzung_ungeeignet "$ziel" "$home" "$programm"; then
    ziel="/tmp/omaclusive-$(id -u)/run"
  fi
  if omaclusive_sitzung_ungeeignet "$ziel" "$home" "$programm"; then
    echo "kein privater Sitzungsordner außerhalb der Web-Wurzel" >&2
    return 1
  fi
  printf '%s' "$ziel"
}

# Schreibt die Startseite (Modus 0600) und gibt ihre file-Adresse aus. Das Geheimnis steht nicht in der Befehlszeile.
omaclusive_boot() {
  local dir="$1" port="$2" seite="$3"
  DIR="$dir" PORT="$port" SEITE="$seite" python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["DIR"])
import sitzung
print(sitzung.boot_url(int(os.environ["PORT"]), os.environ.get("SEITE") or ""), end="")
PY
}

omaclusive_server_starten() {
  local dir="$1" port="$2" i
  mkdir -p "${HOME}/.local/share/omaclusive"
  PORT="$port" nohup python3 "${dir}/server.py" >>"${HOME}/.local/share/omaclusive/server.log" 2>&1 &
  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    curl -sf -o /dev/null --max-time 1 "http://127.0.0.1:${port}/api/bereit" && return 0
    sleep 0.25
  done
  echo "Omaclusive-Server startet nicht. Siehe ~/.local/share/omaclusive/server.log" >&2
  return 1
}

# Fenster nach vorn und Tastatur dorthin (Hyprland/Omarchy), damit Pfeiltasten und Maus gleich ankommen.
# Prüft bis zu 20 Sekunden lang, ob das Fenster der Klasse wirklich den Fokus hat, und holt es sonst nach vorn.
omaclusive_fokus() {
  local klasse="$1"
  command -v hyprctl >/dev/null 2>&1 || return 0
  (
    local i aktiv
    for i in $(seq 1 20); do
      sleep 1
      aktiv=$(hyprctl activewindow -j 2>/dev/null | tr -d ' \n' | grep -o '"class":"[^"]*"' | head -1)
      if [ "$aktiv" = "\"class\":\"${klasse}\"" ]; then
        [ "$i" -ge 3 ] && break
        continue
      fi
      hyprctl dispatch focuswindow "class:${klasse}" >/dev/null 2>&1
    done
  ) &
}
