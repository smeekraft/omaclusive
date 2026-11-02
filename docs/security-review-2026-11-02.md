# Sicherheitsprüfung Omaclusive, 02.11.2026

Anlass: omacom/omarchy-plugin-marketplace#12234, Kommentar von HANCORE-linux vom 30.10.2026
(Labels `needs-fixes`, `security-review-required`): `sitzung.js:12–14` kopiert das API-Bearer-Secret in ein
per JavaScript lesbares, host-weites Cookie. Cookies sind nicht nach Port getrennt (RFC 6265 §8.5).

- Geprüfter Stand: `main` bei `d5713df` (Version 0.3.1). Geprüft wurde das ganze Repo.
- Fixes: Branch `fix/kein-geheimnis-im-cookie`, Code in Commit `b96e8a9`, Tests in `5d13ff1` (Version 0.3.2).
- „vorher“ = Zeile bei `d5713df`, „Fix“ = Zeile im Branch.

## Weg des Geheimnisses

### Vorher (`d5713df`)

1. **Erzeugung:** `server.py:680–681` bindet `127.0.0.1:8795`, dann `sitzung.anlegen()` (`secrets.token_urlsafe(32)`).
2. **Speicherung:** `sitzung.py:145–149` → Datei `<port>.session`, `0600`, Ordner `0700`, außerhalb der Web-Wurzel. Das war in Ordnung.
3. **Übergabe an den Browser:** `startlib.sh:99–107` → `sitzung.boot_schreiben()` (`sitzung.py:166–183`) schreibt eine `0600`-Startdatei
   mit `location.replace("http://127.0.0.1:8795/<seite>#<GEHEIMNIS>")`. Das Geheimnis stand also in einer **URL** (Fragment).
4. **Im Browser:** `sitzung.js:7–8` liest `location.hash`, `:13` legt es in `sessionStorage`, **`:14` schreibt es in das Cookie
   `omaclusive_session` (Path=/, ohne HttpOnly)**. Das Cookie gilt für den Host `127.0.0.1` auf **allen** Ports.
5. **Prüfung im Server:** `sitzung.py:218–234` (`token_aus`/`zugang_ok`) nahm das Geheimnis aus `X-Omaclusive-Token` **oder dem Cookie**.
   HTTP: `server.py:450–451` (GET) und `:536` (POST). WebSocket: `server.py:340` (`_eingabe_kanal`) hinter derselben Prüfung. Der Browser
   konnte beim WebSocket keinen Kopf setzen, der Handshake lief also nur über das Cookie.

Angriff (aus dem Issue, im Test nachgestellt): Ein anderes lokales Konto liefert eine Seite auf `http://127.0.0.1:8794`. Öffnet die
Person sie im selben Browser, liest `document.cookie` das Geheimnis. Mit `curl -H "X-Omaclusive-Token: …"` (ohne Origin) hat das
fremde Konto dann die private API bis hin zu Ausschalten und Neustart.

### Nachher (Branch)

1. **Erzeugung:** wie vorher. Zusätzlich ein eigenes **Browser-Token** nur im Speicher des Servers (`server.py:825`).
2. **Datei-Geheimnis** (`0600`): bekommen nur lokale Werkzeuge dieses Kontos (Starter, `zurueck.sh`, Knopf-Brücken) im Kopf
   `X-Omaclusive-Token`. Der Browser sieht es nie.
3. **Einmal-Übergabe:** Der Starter holt mit dem Datei-Geheimnis per `POST /api/startcode` einen **Einmal-Code** (60 s, einmal gültig;
   `sitzung.py:208`, `server.py:180–207`). `sitzung.boot_html()` (`sitzung.py:185`) schreibt eine `0600`-Startdatei mit einem
   Formular, das den Code per **POST** an `/api/start` schickt (`server.py:518`). Der Server prüft Host und Origin (`null` von `file://`
   oder die eigene Herkunft), löst den Code ein, **löscht die Startdatei** und antwortet mit einer Seite mit strenger CSP (Nonce), die das
   Browser-Token in `sessionStorage` legt und per `location.replace("/<seite>")` weitergeht (`server.py:208–217`).
4. **Im Browser:** `sitzung.js` liest das Token nur aus `sessionStorage` (pro Herkunft, also auch pro Port getrennt) und hält es in
   einer Closure. **Kein Cookie** (ein altes wird gelöscht, `sitzung.js:20`), kein `localStorage`, keine Adresse, kein Fragment.
   `fetch` zu `/api/*` bekommt den Kopf (`credentials: "omit"`). Bilder, Filme und PDF laden über `Sitzung.src()` (`sitzung.js:98`) mit
   einer HMAC-SHA256-Signatur für genau diese Adresse; der WebSocket schickt das Token im Unterprotokoll (`sitzung.js:108`).
5. **Prüfung im Server:** `sitzung.pruefen()` (`sitzung.py:316`): Host genau `127.0.0.1:<port>`, Origin/Referer genau
   `http://127.0.0.1:<port>`, `Sec-Fetch-Site` nur `same-origin`/`none`; sonst **403**. Token nur aus `X-Omaclusive-Token` oder dem
   WebSocket-Unterprotokoll, Vergleich in konstanter Zeit gegen beide Geheimnisse ohne frühen Abbruch (`sitzung.py:307`); sonst **401**.
   Cookies werden nie gelesen. Medien: `server.py:175` `_signiert_ok` (nur 4 Lese-Wege, Herkunft gilt weiter). WebSocket: dieselbe
   Prüfung beim Handshake, Antwort nur mit `Sec-WebSocket-Protocol: omaclusive` (`server.py:422`). Bind nur `127.0.0.1` (`server.py:822`).
   Kein CORS-Kopf, kein `OPTIONS`.

## Funde

| # | Schwere | Fund | Datei:Zeile (vorher) | Fix | Test |
|---|---------|------|----------------------|-----|------|
| 1 | **Hoch** | Bearer-Secret im host-weiten, JS-lesbaren Cookie (Issue-Blocker) | `sitzung.js:14`, `sitzung.py:218–229` | Cookie entfernt, Server liest keine Cookies, Browser-Token in `sessionStorage` | `test_sitzung_browser.js`, `test_kein_cookie.py`, `test_eingabe_kanal.py` |
| 2 | **Mittel** | Secret in einer URL (Fragment der Startseite) | `sitzung.py:179`, `sitzung.js:7–8,17` | Einmal-Code per POST, kein Fragment | `test_kein_cookie.py`, `test_sitzung_browser.js` |
| 3 | **Mittel** | Gespeichertes XSS: Kachelwörter (Dateinamen in `~/Bilder/Omaclusive`, Plugin-Namen) per `innerHTML` | `setup.html:175,252` | `kachelInhalt()` baut DOM-Knoten | `test_sitzung_browser.js`, `test_kein_cookie.py` |
| 4 | **Mittel** | Herkunft zu weit: `localhost` neben `127.0.0.1` | `sitzung.py:190–193,196–199` | Nur `127.0.0.1:<port>` | `test_kein_cookie.py`, `test_eingabe_kanal.py` |
| 5 | Niedrig | Statische Dateien und `HEAD` ohne Host-Prüfung (DNS-Rebinding liest App-Dateien) | `server.py:434–446,533` | Host-Prüfung für jede Anfrage, `HEAD /api/*` 405 | `test_kein_cookie.py` |
| 6 | Niedrig | App einbettbar (kein `X-Frame-Options`/`frame-ancestors`) | `server.py:414–417` | `X-Frame-Options: DENY`, CSP `frame-ancestors 'none'` auf der Startseite | `test_kein_cookie.py`, `test_sitzung_browser.js` |
| 7 | Niedrig | Ausgelieferte Fremdbilder (Plugin-SVG, Fotos) ohne `nosniff`/CSP | `server.py:279–300,378–389` | `nosniff`, `CORP same-origin`, CSP `sandbox` für Medien | `test_kein_cookie.py` |
| 8 | Niedrig | `Referrer-Policy: same-origin` (signierte Adressen) | `server.py:416` | `no-referrer` | `test_kein_cookie.py` |
| 9 | Niedrig | `Content-Length` negativ/ungültig: Lesen bis EOF bzw. Traceback | `server.py:428–433` | `laenge()` prüft Ziffern, sonst 400 | `test_kein_cookie.py` |
| 10 | Niedrig | Unbehandelte Ausnahmen: Verbindungsabbruch, Traceback | `server.py:434,534` | `do_GET`/`do_POST` fangen ab, `500` ohne Details, Traceback nur ins private Log | `test_kein_cookie.py` (In-Prozess) |
| 11 | Niedrig | Verbindungen ohne Zeitlimit (lokale Konten können Fäden binden) | `server.py:390` | `timeout = 30`, WebSocket nach Handshake ohne Limit | `test_kein_cookie.py` (In-Prozess) |
| 12 | Niedrig | Fehler beim Stimmen-Download mit Pfaden/Adressen an die Oberfläche | `stimmen.py:152` | Fester Grund (`netz`/`pruefung`/`fehler`), Typ ins private Log | `test_kein_cookie.py` |
| 13 | Niedrig | Autostart-`Exec` ungequotet (Leerzeichen, `%`, `$` im Pfad) | `praxis.py:218` | `_desktop_exec()` nach Desktop-Entry-Spezifikation | `test_kein_cookie.py`, `test_eingabe.js` |
| 14 | Info | Installer kopiert `pflege.py`/`pflege.html` nicht (`/api/pflege` scheitert in der Installation) | `install.sh:64` | Dateien ergänzt | `test_kein_cookie.py` |

### 1. Secret im host-weiten Cookie (Hoch)

- **Vorher:** `sitzung.js:14` `document.cookie = "omaclusive_session=" + token + "; Path=/; SameSite=Strict"`. Kein `HttpOnly`, kein Port-Bezug.
  `SameSite=Strict` hilft nicht: `127.0.0.1:8794` und `127.0.0.1:8795` sind *same-site*. `sitzung.py:222–228` nahm das Cookie als Zugang.
- **Fix:** Cookie weg, ohne Rückwärtskompatibilität. `sitzung.token_aus()` liest nur `X-Omaclusive-Token` und das WebSocket-Unterprotokoll.
  `sitzung.js` löscht ein altes `omaclusive_session`. Der Browser bekommt nie das Datei-Geheimnis, sondern ein eigenes Token in
  `sessionStorage` (Herkunft inklusive Port).
- **Test:** `test_sitzung_browser.js` öffnet im selben Chromium eine Seite auf `127.0.0.1:<port+1>`: `document.cookie` leer, `localStorage`
  und `sessionStorage` leer, `fetch` (CORS und no-cors) bekommt 401/403, WebSocket abgelehnt (401/403, kein 101), App nicht einbettbar.
  Gegenprobe: mit der alten Zeile 14 wieder eingebaut liest die fremde Seite das Token (3 Fehler im Test). `test_kein_cookie.py`: nur mit
  Cookie (Datei-Geheimnis oder Browser-Token) 401, nie `Set-Cookie` in einer Antwort. `test_eingabe_kanal.py`: WebSocket mit Keks 401.

### 2. Secret in einer URL (Mittel)

- **Vorher:** Startseite mit `location.replace(".../<seite>#<geheimnis>")` (`sitzung.py:179`). Fragmente gehen nicht an den Server, stehen aber
  in Verlauf/Sitzungswiederherstellung, in `/json/list` eines Debug-Ports und in der Startdatei.
- **Fix:** Startdatei mit POST-Formular und Einmal-Code (`sitzung.py:185`), Einlösen in `server.py:518`, Startdatei wird gelöscht, Code
  gilt einmal und 60 s. Ziele nur `name.html?abfrage` (`sitzung.ziel_ok`), nie `//fremd`.
- **Test:** `test_kein_cookie.py` (Code nicht das Geheimnis, kein Fragment, einmal gültig, abgelaufen ungültig, fremde Herkunft 403,
  `//evil.example` 400, Startdatei gelöscht, Browser-Token holt keine Codes). `test_sitzung_browser.js` (Adresse und Verlauf ohne Token,
  Geheimnis oder Code).

### 3. Gespeichertes XSS in den Einstellungen (Mittel)

- **Vorher:** `setup.html:175,252` `b.innerHTML = \`<img src="${p.bild}" alt="">${p.wort}\``. Das Wort kommt u. a. aus Dateinamen im
  Ordner `~/Bilder/Omaclusive` (`praxis.py:106–110`) und aus Plugin-Dateien. Ein Foto namens `<img src=x onerror=…>.png` lief als
  Skript in der App-Herkunft und hätte Token und API (Ausschalten) gehabt.
- **Fix:** `kachelInhalt()` (`setup.html:175`) setzt `img.src` und einen Textknoten. Keine HTML-Vorlagen mit Daten mehr.
- **Test:** `test_sitzung_browser.js` (Wort `<img src=x onerror="window.__xss=1">` bleibt Text, kein Skript), `test_kein_cookie.py`
  (keine `innerHTML`-Vorlage mit `${…}` in `setup.html`).

### 4.–14.

Siehe Tabelle; jede Zeile hat eine benannte Prüfung in `test_kein_cookie.py` (Host/Origin/Referer/`Sec-Fetch-Site` je Weg und Token,
DNS-Rebinding statisch und `HEAD`, Sicherheitsköpfe, Medien-Signaturen, `Content-Length`, `500` ohne Interna, Zeitlimit, Stimmenfehler,
`Exec`-Quoting, Installer-Liste). `test_eingabe_kanal.py` deckt den WebSocket ab (anderer Port, `localhost`, `null`, fremder Host, Host mit
anderem Port: 403; ohne/falsches Token/Keks: 401; Antwort ohne Token).

## Ohne Befund oder bewusst so gelassen (Info)

- **Shell/Subprozesse:** weiterhin kein `shell=True`, nur argv-Listen. SSIDs und MACs nur aus der eigenen Suche. Eine SSID, die mit `-`
  beginnt, kann `nmcli`/`iwctl` höchstens als unbekannte Option scheitern lassen; keine Ausführung. Nicht geändert.
- **`/api/open` mit Pfad:** öffnet jede vorhandene Datei per `xdg-open`, aber nur mit gültigem Token und eigener Herkunft. Das ist die
  gewollte Funktion „Datei-Kachel“. Nicht geändert.
- **Pfad-Traversal:** `praxis._im_ordner` (kein `/`, kein `.` am Anfang, `resolve()`), `plugin_datei` per Regex, statisch `_nicht_ausliefern`.
  `test_eingabe.js` (Pfadtricks 404) und `test_eingabe_kanal.py` grün.
- **Datei- und Socket-Rechte:** Sitzungsdatei, Startdatei, `server.log` `0600` in `0700`; `config.json` `0600`; nur TCP auf `127.0.0.1`,
  keine Unix-Sockets. Unverändert in Ordnung.
- **CSRF:** Jede Aktion ist POST mit Kopf-Token, das eine fremde Seite weder kennt noch (ohne CORS) setzen darf. Kein Cookie mehr, also
  auch keine „ambient credentials“. `/api/start` nimmt `Origin: null`, braucht aber einen unbekannten Einmal-Code.
- **`/api/bereit?probe=`** ist ohne Token erreichbar und gibt `HMAC(Geheimnis, "bereit:"+probe)`. Das verrät das Geheimnis nicht und ist
  sonst nirgends ein Zugang.
- **`sessionStorage`** kann Chromium bei der Sitzungswiederherstellung im Profil speichern. Die Profile `~/.local/share/omaclusive/kiosk`
  und `fenster` sind `0700` (`start-talker.sh`); das Token gilt nur bis zum nächsten Serverstart.
- **Abhängigkeiten:** Python nur Standardbibliothek, keine npm-Pakete zur Laufzeit. Piper `2023.11.14-2` und die Stimmen werden mit
  sha256 geprüft (`install.sh`, `stimmen.py`). Externe Programme (Chromium, mpv, yt-dlp, espeak-ng, nmcli/iwctl, bluetoothctl) kommen vom
  System und werden mit dessen Updates aktuell gehalten. Kein Fund mit bekannter Lücke im Repo.
- **Logs:** Der Server protokolliert keine Anfragezeilen (`log_message` aus). `test_kein_cookie.py` und `test_sitzung_browser.js` prüfen,
  dass Datei-Geheimnis, Browser-Token, Startcode und Signatur nicht im Server-Log stehen.

## Prüfungen nach den Fixes

Alle 23 Testdateien grün (Python 3.14.8, Node 26.8.1, Chromium headless):

```
test_ansage.py test_audio.py test_bildstil.py test_eingabe_kanal.py test_farbe.py test_fernsehen.py
test_hilferuf.py test_i18n.py test_kein_cookie.py (511 Prüfungen) test_modi.py test_pflege.py test_praxis.py
test_sitzung.py test_sprache.py test_stimmen.py test_tempo.py test_ton.py
test_i18n.js test_pfad.js test_bild.js (SELFTEST PASS) test_editor.js (48)
test_sitzung_browser.js (25) test_eingabe.js (521)
```

`omarchy plugin validate ./` ohne Fehler. Die Shell-Startkette (`omaclusive_server_starten`, `omaclusive_boot`) liefert eine `0600`-Startdatei
ohne das Geheimnis.
