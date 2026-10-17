#!/usr/bin/env python3
"""Prüft nur die leise Hinweis-Datei. Spielt nichts ab und ändert keine Lautstärke."""
import os
import tempfile
import wave

import bausteine


def main():
    fd, path = tempfile.mkstemp(prefix="omaclusive-test-", suffix=".wav")
    os.close(fd)
    try:
        bausteine.write_soft_tone(path)
        with wave.open(path) as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
        dauer = frames / float(rate)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if not 0.15 <= dauer <= 0.4:
        raise SystemExit("Hinweis-Ton hat die falsche Länge: %s" % dauer)
    print("TON_OK", round(dauer, 3))


if __name__ == "__main__":
    main()
