# Credits / Beteiligte Programme

**English** · [Deutsch below](#beteiligte-programme)

Omaclusive itself is licensed under the GPL-3.0. The full text is in `LICENSE`.

## Piper

Speech is produced by Piper, developed by Michael Hansen in the Rhasspy project.
The version `install.sh` downloads is release **2023.11.14-2**, file `piper_linux_x86_64.tar.gz`.
The original project is at https://github.com/rhasspy/piper under the MIT licence.
Development continues at https://github.com/OHF-Voice/piper1-gpl.

Piper is not shipped with the source. `install.sh` downloads it on the first run and aborts if the checksum does not match.
A local copy of Piper (for example from an older install) does not belong in a published package.

## Voice Thorsten (German)

File `de_DE-thorsten-medium`. The voice is by Thorsten Müller, licence CC0 per the Piper voice package.
Source: https://huggingface.co/rhasspy/piper-voices under `de/de_DE/thorsten/medium/`.
Checked 15.10.2026 against the model card there: dataset Thorsten-Voice, licence CC0. The same card says the model was finetuned from the
US English "lessac" voice. Omaclusive ships no voice file, `install.sh` downloads it, and the recordings in `audio/` are generated audio of this voice.

## Voice John (English, default)

File `en_US-john-medium`. US English male voice, one speaker, from recordings of LibriVox (https://librivox.org), licence public domain. Finetuned from the voice Kristin; dataset compiled by the voice author, see https://brycebeattie.com/files/tts/.
Source: https://huggingface.co/rhasspy/piper-voices under `en/en_US/john/medium/`.
Checked 17.10.2026 against the model card there: licence public domain.
The recordings in `audio/en/` and `audio/de/` were made with these two voices.

## Optional English voices (choose in the app)

Downloaded only when picked, from https://huggingface.co/rhasspy/piper-voices, checksums in `voices.json`. Checked 17.10.2026 against the model cards:
`en_US-ljspeech-medium` and `en_US-ljspeech-high` (LJ Speech by Keith Ito, public domain, `en/en_US/ljspeech/`) and `en_GB-cori-high` (British English, recordings from LibriVox, public domain, dataset compiled by the voice author, see https://brycebeattie.com/files/tts/, `en/en_GB/cori/high/`).

## Vosk (optional voice listening)

German model `vosk-model-small-de`, English model `vosk-model-small-en-us` (optional, folder `ohr/model-en`), both Apache-2.0.
https://alphacephei.com/vosk/

## espeak-ng

Fallback voice if Piper is missing. espeak-ng is licensed under the GPL-3.0.
https://github.com/espeak-ng/espeak-ng

---

# Beteiligte Programme

Omaclusive selbst steht unter der GPL-3.0. Der Wortlaut liegt in `LICENSE`.

## Piper

Die Stimme spricht Piper, entwickelt von Michael Hansen im Projekt Rhasspy.
Die Fassung, die `install.sh` lädt, ist die Veröffentlichung **2023.11.14-2**,
Datei `piper_linux_x86_64.tar.gz`.
Das ursprüngliche Projekt liegt unter https://github.com/rhasspy/piper und steht unter der MIT-Lizenz.
Die Weiterentwicklung läuft unter https://github.com/OHF-Voice/piper1-gpl.

Piper wird nicht mit dem Quelltext mitgeliefert. `install.sh` lädt es beim ersten Lauf
und bricht ab, wenn die Prüfsumme nicht stimmt. Eine lokale Kopie von Piper
(etwa von einer früheren Installation) gehört nicht in ein veröffentlichtes Paket.

## Stimme Thorsten

Datei `de_DE-thorsten-medium`. Im Stimm-Paket heißt das Feld `dataset` `thorsten`.
Die Stimme stammt von Thorsten Müller und wird im Piper-Stimm-Paket als gemeinfrei geführt.
Quelle: https://huggingface.co/rhasspy/piper-voices unter `de/de_DE/thorsten/medium/`.
Am 15.10.2026 an der dortigen Modellkarte geprüft: Datensatz Thorsten-Voice, Lizenz CC0. Dieselbe Karte nennt, dass das Modell
von der US-englischen Stimme „lessac“ weitertrainiert wurde. Omaclusive liefert keine Stimmdatei mit, `install.sh` lädt sie,
und die Aufnahmen in `audio/` sind erzeugtes Audio dieser Stimme.

## Stimme John (Englisch, Standard)

Datei `en_US-john-medium`. US-englische männliche Stimme, ein Sprecher, aus Aufnahmen von LibriVox (https://librivox.org), gemeinfrei. Von der Stimme Kristin weitertrainiert; Datensatz vom Stimm-Autor zusammengestellt, siehe https://brycebeattie.com/files/tts/.
Quelle: https://huggingface.co/rhasspy/piper-voices unter `en/en_US/john/medium/`.
Am 17.10.2026 an der dortigen Modellkarte geprüft: gemeinfrei.
Die Aufnahmen in `audio/de/` und `audio/en/` sind mit diesen beiden Stimmen entstanden.

## Wählbare englische Stimmen (in der App)

Werden nur geladen, wenn man sie wählt, von https://huggingface.co/rhasspy/piper-voices, Prüfsummen in `voices.json`. Am 17.10.2026 an den Modellkarten geprüft:
`en_US-ljspeech-medium` und `en_US-ljspeech-high` (LJ Speech von Keith Ito, gemeinfrei, `en/en_US/ljspeech/`) und `en_GB-cori-high` (britisches Englisch, Aufnahmen von LibriVox, gemeinfrei, Datensatz vom Stimm-Autor zusammengestellt, siehe https://brycebeattie.com/files/tts/, `en/en_GB/cori/high/`).

## Vosk (Sprecherkennung, optional)

Deutsches Modell `vosk-model-small-de`, englisches Modell `vosk-model-small-en-us` (optional, Ordner `ohr/model-en`), beide Apache-2.0.
https://alphacephei.com/vosk/

## espeak-ng

Ersatzstimme, wenn Piper fehlt. espeak-ng steht unter der GPL-3.0.
https://github.com/espeak-ng/espeak-ng
