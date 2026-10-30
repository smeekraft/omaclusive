# Sicherheitsprüfung Omaclusive, 30.10.2026

Stand der Prüfung: `main` bei `92e31e4`. Fixes auf dem Branch `fix/ws-auth-audit` (Version 0.3.1).
Geprüft wurde das ganze Repo, nicht nur der gemeldete Blocker aus
omacom/omarchy-plugin-marketplace#12234.

Zeilenangaben „vorher“ beziehen sich auf `92e31e4`, „Fix“ auf den Branch.

## Funde

| # | Risiko | Fund | Fix |
|---|--------|------|-----|
| 1 | **Hoch** | Port 8765: Fremde Brücke steuert die UI | Eingabekanal am eigenen Server, mit Sitzungsgeheimnis, Standard aus |
| 2 | **Mittel** | Port 8795: Starter vertraut jedem, der auf dem Port antwortet | Server beweist das Geheimnis (HMAC), erst Port binden, dann Geheimnis |
| 3 | **Mittel** | `server.log` liegt in der Web-Wurzel, 0644, ohne Anmeldung abrufbar | Log im privaten Sitzungsordner (0600), `*.log` nie statisch |
| 4 | **Mittel** | Statische Auslieferung: versteckte Dateien, Zwischenstände, Ordnerlisten, Verweise nach draußen | Statische Auslieferung nur noch für normale Dateien im Programmordner |
| 5 | Niedrig | Installationsordner 0755, `config.json` vom Installer 0644 | `chmod 700` für den Ordner, `chmod 600` für die Config, auch beim Serverstart |
| 6 | Niedrig | `pflege.json` (Erinnerungen, Aufgaben) mit 0644 und festem Zwischennamen | Atomar über `mkstemp` (0600) |
| 7 | Niedrig | Bildstil-Ordner folgt Verweisen aus dem Ordner heraus | `resolve()` und Prüfung, ob die Datei im Ordner bleibt |
| 8 | Info | Test `test_modi.py` liest eine alte Sitzungsdatei (fester Port 8799) | Test wartet auf den Server-Beweis |

### 1. Unauthentifizierter WebSocket auf `ws://localhost:8765` (Blocker)

- **Vorher:** `app.js:1942–1955` verbindet sich bei jedem Start bedingungslos mit `ws://localhost:8765` (Aufruf in `app.js:2259`) und alle 5 s erneut.
  `left`/`right`/`back`/`hold` gehen direkt in `eingabe()`. Der Dienst auf 8765 ist nicht Teil des Repos.
- **Risiko:** Ein anderes Konto auf demselben Rechner belegt den freien Port 8765 und steuert damit die angemeldete Oberfläche, auch die Rückfrage
  bei Ausschalten und Neustart: Erst „Ausschalten“ wählen, dann „Ja“. Die HTTP-API wurde nie berührt, die Steuerung lief über die echte UI.
- **Warum nicht einfach das Token an 8765 schicken:** Der Dienst auf 8765 lässt sich nicht prüfen, also kann ihn auch ein Angreifer betreiben.
  Würde der Browser ihm das Sitzungsgeheimnis schicken, hätte genau dieser Angreifer das Geheimnis der HTTP-API. Cookies trennen außerdem keine Ports:
  Ein Handshake zu `127.0.0.1:<anderer Port>` würde das Cookie `omaclusive_session` mitschicken.
- **Fix:**
  - `server.py:315` `eingabe_an()`: Kanal nur mit `"eingabe": {"websocket": true}` (Standard aus, auch in beiden `config.example*.json`).
  - `server.py:340` `_eingabe_kanal()`, Weg `server.py:527`: WebSocket `/api/eingabe` am eigenen Server (Port 8795). Der Handshake läuft
    durch dieselbe Prüfung wie die HTTP-API (`sitzung.zugang_ok`: Sitzungsgeheimnis aus Kopf oder Cookie, Host, Origin). Ohne gültiges Geheimnis
    gibt es kein `101` und keine Nachricht. Danach werden nur die vier Wörter angenommen, nur ganze, maskierte, kleine Rahmen.
    Die Brücke sendet, die Oberfläche empfängt.
  - `app.js:1945–1965`: Der Client verbindet nur, wenn der Kanal in der Config an ist und ein Sitzungsgeheimnis da ist, und nur zu
    `ws://<eigener Host>/api/eingabe`. Neuverbinden ruft `ws()` erneut auf: dieselbe Prüfung, derselbe Handshake.
- **Prüfung:** `test_eingabe_kanal.py` (Handshake ohne, mit falschem und mit fremdem Origin/Host: 403; Kanal aus: 404; Weiterleitung;
  unbekannte Wörter verworfen; Reconnect). `test_eingabe.js` Szenarien „Eingabekanal aus/an“ im echten Chromium: Bei „aus“ gibt es keinen
  einzigen WebSocket. Bei „an“ geht die Verbindung nur zu `/api/eingabe`, eine Brücke ohne Geheimnis wird abgelehnt, mit Geheimnis bewegt „right“ die Kachel.
  Die alten Filter für 8765-Fehler in den Browser-Tests sind entfernt, damit ein Rückfall auffällt.

### 2. Port 8795 von einem fremden Konto belegt

- **Vorher:** `startlib.sh:110–119` prüft nur, ob `GET /api/bereit` mit 200 antwortet, und öffnet dann den Kiosk-Browser auf `127.0.0.1:8795`.
  `server.py:587` schreibt das Geheimnis, *bevor* `server.py:592` den Port bindet.
- **Risiko:** Gleiche Angriffsklasse wie Fund 1, eine Ebene höher. Wer 8795 vorher belegt, liefert der Person vor dem Bildschirm eine eigene
  Oberfläche im Kiosk. Das echte Geheimnis wäre dabei wertlos, weil kein echter Server läuft, aber die Anzeige gehört dem Angreifer.
- **Fix:** `server.py:680` bindet erst den Port, dann wird das Geheimnis geschrieben. `GET /api/bereit?probe=<Zufall>` antwortet mit
  `HMAC-SHA256(Geheimnis, "bereit:" + probe)` (`sitzung.py:240`, `server.py:444`). Das Geheimnis selbst wird nie verraten. Der Starter
  (`startlib.sh:111`, `sitzung.py:247–284`) öffnet den Browser nur, wenn der Beweis stimmt. Sonst meldet er, dass der Port belegt ist.
- **Prüfung:** `test_eingabe_kanal.py` (Attrappe auf dem Port, `omaclusive_server_starten` gibt einen Fehler zurück).

### 3. `server.log` in der Web-Wurzel

- **Vorher:** `startlib.sh:112` schreibt `~/.local/share/omaclusive/server.log`. Das ist die Web-Wurzel der installierten Kopie, Modus 0644.
  `server.py:310–327` sperrt nur `log.txt`/`log.txt.1`, also lieferte `GET /server.log` die Datei ohne Anmeldung aus, auch an andere Konten.
  Das Log enthält Python-Tracebacks mit Pfaden und kann Ausgaben von Hilfsprogrammen enthalten.
- **Fix:** Das Log liegt im privaten Sitzungsordner (`startlib.sh:121–133`, Datei 0600, Ordner 0700). Ein altes `server.log` in der Web-Wurzel
  wird beim Start auf 0600 gesetzt (`server.py:670`) und nie ausgeliefert (Fund 4).

### 4. Statische Auslieferung zu großzügig

- **Vorher:** `server.py:310–327` (`translate_path`) sperrt Config, Sitzungsdatei und Ansagen-Log, sonst liefert `SimpleHTTPRequestHandler` alles aus:
  - `hilferuf.py:321` schreibt die Config über `.config-*.tmp` in der Web-Wurzel. In diesem kurzen Moment war der geheime Hilferuf-Kanal ohne Anmeldung abrufbar.
  - `.git/` (beim Start aus dem Repo), `*.bak`, `*.teil` (Downloads von `install.sh`), Ordnerlisten (`/voices/`, `/img/`).
  - Verweise, die aus dem Programmordner herausführen.
- **Fix:** `server.py:183` `_nicht_ausliefern()`: nur Dateien, deren echter Pfad im Programmordner liegt, kein Pfadteil mit `.` am Anfang, keine
  Endungen `.log .bak .tmp .teil .session`. `server.py:410` schaltet Ordnerlisten ab. Bilder über `/img/…` laufen durch dieselbe Prüfung.
- **Prüfung:** `test_eingabe_kanal.py` (mit und ohne Geheimnis 404, `index.html` und Bilder bleiben 200). `test_sitzung.py` läuft unverändert grün.

### 5. Dateirechte der Installation

- **Vorher:** `install.sh:58` legt `~/.local/share/omaclusive` mit 0755 an. Eine neue `config.json` entsteht über `cp`/`open()` mit 0644. Ältere
  Installationen haben dort den geheimen Hilferuf-Kanal, den andere Konten lesen und damit Rufe fälschen oder mitlesen könnten.
- **Fix:** `install.sh:63` `chmod 700`, `install.sh:153–154` `chmod 600` für Config und Sicherung. `server.py:670` setzt beim Start
  `config.json`/`config.json.bak` auf 0600, auch bei Installationen, die nicht neu installiert werden.

### 6. `pflege.json` lesbar für andere

- **Vorher:** `pflege.py:110–115` schreibt über einen festen Zwischennamen `pflege.json.tmp` mit der umask (meist 0644).
  Erinnerungen wie „Tabletten nehmen“ sind private Daten.
- **Fix:** `pflege.py:111` schreibt atomar über `mkstemp` (0600), wie `modi.py` es schon tut. Prüfung in `test_eingabe_kanal.py`.

### 7. Bildstil folgt Verweisen

- **Vorher:** `praxis.py:136–141` `bild_im_stil()` gibt `<ordner>/<stil>/<name>` zurück, auch wenn das ein Verweis nach draußen ist.
  Das gilt für die statischen Bilder und für `/api/plugin-bild`.
- **Fix:** `praxis.py:140–147` prüft, dass der echte Pfad im Ordner bleibt.

### 8. Fehler im Test `test_modi.py`

- **Vorher:** `test_modi.py:143–150` liest die Sitzungsdatei, bevor der Server sie neu geschrieben hat. Bei festem Port 8799 schlug der zweite
  Lauf hintereinander auch auf `main` fehl: Das alte Geheimnis ergab 403.
- **Fix:** Der Test wartet mit `sitzung.warte_auf_server()` auf den Beweis des Servers.

## Ohne Befund geprüft

- **Ports und Sockets:** Es gibt nur einen Listener, den HTTP-Server auf `127.0.0.1:8795` (`server.py:680`). Es gibt keine weiteren Sockets:
  mpv läuft ohne IPC-Socket, `ohr.py` liest ffmpeg über eine Pipe. Jeder Weg unter `/api/` und `/config.json` prüft Geheimnis, Host und Origin
  (`sitzung.py:190–234`), jetzt auch der WebSocket. Aktionen gehen nur über POST, Ausschalten, Neustart und Sperren nur mit der einmaligen
  Freigabe des Servers.
- **Shell-Aufrufe:** Kein `shell=True` und kein `os.system`. Alle Befehle sind feste argv-Listen. Gesprochene Sätze gehen über stdin oder eine
  0600-Datei (seit #8). SSID und MAC kommen nur aus der letzten eigenen Suche. TV-Adressen stehen hinter `--`. `BarWidget.qml` setzt Pfade in Anführungszeichen.
- **Temp-Dateien:** Überall `mkstemp` (0600). Gelöscht wird nur im Temp-Ordner (`bausteine.py:_ist_wegwerf`).
- **Pfad-Traversal:** Bilder und Filme über `praxis._im_ordner` (keine `/`, kein `.` am Anfang, `resolve()`). Plugin-Bilder per Regex,
  `_pfad_normal` für `..`. `/api/open` mit Pfad öffnet nur mit Geheimnis.
- **Installer:** Kein `sudo` und kein Root. Er schreibt nur in `~/.local/share/omaclusive` und in die drei eigenen `.desktop`-Dateien. Downloads
  laufen mit sha256-Prüfung und Abbruch. Ein Deinstallationsskript gibt es im Repo nicht, also gab es hier nichts zu prüfen.
- **„Komplett offline“:** Netzaufrufe zur Laufzeit gibt es nur, wenn jemand sie auslöst, und alle stehen im README unter „Datenschutz“:
  der Hilferuf (ntfy, der automatische Test erst nach dem ersten Test einer betreuenden Person), Fernsehen und Radio beim Wählen eines Senders
  und der Download einer Stimme beim ersten Wählen. Die Oberfläche lädt keine externen Skripte, Schriften oder Bilder. Ohne Netz geht alles andere weiter.
  Wichtig: Der alte WebSocket war zwar lokal, aber gerade kein Netzaufruf nach außen. Daran hat sich nichts geändert.

## Prüfungen nach den Fixes

- Alle Python-Tests, `test_i18n.js`, `test_pfad.js`, `test_editor.js` (48 Prüfungen) und `test_eingabe.js` (Eingabe im Browser, alle Szenarien) sind grün.
- `omarchy plugin validate` ist ohne Fehler (Exit 0).
- Die App wurde einmal über die echte Start-Kette (`omaclusive_server_starten` und Startdatei) mit headless Chromium gestartet. Geprüft:
  Kacheln blättern und öffnen, Ansagen über `pw-play`, Ausschalten-Rückfrage (Nein: bleibt an, Ja: `systemctl poweroff` als Attrappe).
  Kein Geheimnis in einer Befehlszeile, kein WebSocket, `GET /server.log` gibt 404.
