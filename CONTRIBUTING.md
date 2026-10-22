# Contributing

[Deutsch](CONTRIBUTING.de.md) · **English**

Thank you for wanting to help. Omaclusive stays small and offline on purpose.

## Plugins

A plugin is a folder `plugins/<name>/` with `plugin.json` and pictures.
Without the folder the card disappears. See `plugins/grundbeduerfnisse/` for an example.
For English, add `plugin.en.json` next to it with the same shape (translate the texts only).

## Tests

Please run these before a pull request:

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
node --experimental-websocket test_eingabe.js
node --experimental-websocket test_editor.js
```

The tests need a `config.json`. For a run, `cp config.example.json config.json` is enough,
with `"einrichtung": {"fertig": true}` and `"autostart": false`. The file is listed in `.gitignore`.
`test_modi.py`, `test_sitzung.py`, `test_eingabe.js` and `test_editor.js` create their own temporary `config.json` and delete it again, so remove yours before running them.
`test_modi.py` and `test_editor.js` also write to a throw-away home folder, never to yours.

## Languages

Every visible or spoken text must exist in German and English.

- Python: `from i18n import tr`, then `tr("German text")`. With a placeholder: `tr("Verbunden mit {}").format(name)`.
- JavaScript and HTML: `T("German text")` or `Tf("{} oder {}.", a, b)`.
- Add the German text as the key in `locales/de.json` and the translation in `locales/en.json`
  (same keys, same number of `{}`). `python3 test_i18n.py` reports missing entries.
- English: simple, short sentences that read aloud well. No medical terms.
- New fixed announcements: run `python3 audio_erzeugen.py` afterwards so `audio/de` and `audio/en` grow with them.
- New language: `locales/<code>.json`, `config.example.<code>.json`, an entry in `i18n.py` (`SPRACHEN`) and `sprache.js`.

## Wording

No medical terms, no diagnoses, no therapy language, no donation link.
The call for help is not a replacement for an emergency call. Please keep it that way.

## Privacy in issues

**Please do not post health data or personal details in issues or pull requests**: no diagnoses, no names of users or carers,
no photos of people, no ntfy topic links, no contents of your `config.json`. Describe the problem in general terms.
Screenshots: use the placeholder contacts, not real people.

## Contact

Issues and pull requests here in the repo. Public name: Smeekraft.

## Code of Conduct

Please follow `CODE_OF_CONDUCT.md`.
