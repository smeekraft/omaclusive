# Mitmachen

**Deutsch** · [English](CONTRIBUTING.md)

Danke, dass du mitdenken willst. Omaclusive bleibt bewusst klein und offline.

## Plugins

Ein Plugin ist ein Ordner unter `plugins/<name>/` mit `plugin.json` und Bildern.
Ohne den Ordner verschwindet die Karte. Schau dir `plugins/grundbeduerfnisse/` als Beispiel an.
Für Englisch legst du daneben `plugin.en.json` mit gleicher Form an (nur die Texte übersetzen).

## Tests

Vor einem Pull Request bitte laufen lassen:

```bash
node test_pfad.js
node --check app.js
python3 test_ton.py
python3 test_farbe.py
python3 test_sprache.py
python3 test_hilferuf.py
python3 test_praxis.py
python3 test_i18n.py
python3 test_bildstil.py
python3 test_tempo.py
python3 test_ansage.py
python3 test_audio.py
node test_i18n.js
python3 test_modi.py
python3 test_sitzung.py
python3 test_eingabe_kanal.py
node --experimental-websocket test_eingabe.js
node --experimental-websocket test_editor.js
```

Die Tests brauchen eine `config.json`. Für einen Lauf reicht `cp config.example.json config.json`
mit `"einrichtung": {"fertig": true}` und `"autostart": false`. Die Datei steht in `.gitignore`.
`test_modi.py`, `test_eingabe.js` und `test_editor.js` legen selbst eine vorübergehende `config.json` an und löschen sie wieder. Lösche deine vorher.
`test_modi.py` und `test_editor.js` schreiben außerdem in ein Wegwerf-Heimverzeichnis, nie in deines.

## Sprachen

Jeder sichtbare oder gesprochene Text muss auf Deutsch und Englisch da sein.

- Python: `from i18n import tr`, dann `tr("Deutscher Text")`. Mit Platzhalter: `tr("Verbunden mit {}").format(name)`.
- JavaScript und HTML: `T("Deutscher Text")` oder `Tf("{} oder {}.", a, b)`.
- Den deutschen Text als Schlüssel in `locales/de.json` und die Übersetzung in `locales/en.json` eintragen
  (gleiche Schlüssel, gleiche Anzahl `{}`). `python3 test_i18n.py` meldet fehlende Einträge.
- Englisch: einfache, kurze Sätze, gut vorlesbar. Keine medizinischen Begriffe.
- Neue feste Ansagen: danach `python3 audio_erzeugen.py` laufen lassen, damit `audio/de` und `audio/en` mitwachsen.
- Neue Sprache: `locales/<code>.json`, `config.example.<code>.json`, Eintrag in `i18n.py` (`SPRACHEN`) und `sprache.js`.

## Wortwahl

Keine medizinischen Begriffe, keine Diagnosen, keine Therapie-Sprache, kein Spenden-Link.
Der Hilferuf ist kein Notruf-Ersatz. Das bitte so lassen.

## Datenschutz in Issues

**Bitte keine Gesundheitsdaten und keine persönlichen Angaben in Issues oder Pull Requests**: keine Diagnosen, keine Namen von Nutzenden oder Betreuenden,
keine Fotos von Personen, keine ntfy-Topic-Links, keinen Inhalt deiner `config.json`. Beschreibe das Problem allgemein.
Bei Screenshots: die Platzhalter-Kontakte nehmen, keine echten Personen.

## Kontakt

Issues und Pull Requests hier im Repo. Öffentlicher Name: Smeekraft.

## Verhaltenskodex

Bitte `CODE_OF_CONDUCT.de.md` beachten.
