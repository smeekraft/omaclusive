import datetime
import tempfile
import unittest
from pathlib import Path

import pflege

D = datetime.datetime


class PflegeTest(unittest.TestCase):
    def daten(self, **kw):
        roh = {"erinnerungen": [], "aufgaben": [], "bestaetigt": {}}
        roh.update(kw)
        return pflege.bereinige(roh)[0]

    def test_bereinigen_lehnt_falsches_ab(self):
        sauber, fehler = pflege.bereinige({"erinnerungen": [{"zeit": "25:00", "text": "x"}, {"zeit": "08:00", "text": ""}, "x"],
                                           "aufgaben": [{"text": ""}]})
        self.assertEqual(sauber["erinnerungen"], [])
        self.assertTrue(fehler)
        self.assertEqual(pflege.bereinige("kaputt")[0], pflege.leer())

    def test_text_wird_gekuerzt_und_gesaeubert(self):
        d = self.daten(erinnerungen=[{"zeit": "08:00", "text": "a\x00b\n" + "x" * 300}])
        t = d["erinnerungen"][0]["text"]
        self.assertEqual(len(t), pflege.MAX_TEXT)
        self.assertNotIn("\x00", t)

    def test_grenzen(self):
        d = self.daten(erinnerungen=[{"zeit": "08:00", "text": "t%d" % i} for i in range(60)],
                       aufgaben=[{"text": "a%d" % i} for i in range(80)])
        self.assertEqual(len(d["erinnerungen"]), pflege.MAX_ERINNERUNGEN)
        self.assertEqual(len(d["aufgaben"]), pflege.MAX_AUFGABEN)
        self.assertEqual(len({e["id"] for e in d["erinnerungen"]}), pflege.MAX_ERINNERUNGEN)

    def test_taeglich_faellig_und_bestaetigt(self):
        d = self.daten(erinnerungen=[{"id": "e1", "zeit": "08:00", "text": "Tablette", "wiederholen": "taeglich"}])
        self.assertEqual(pflege.faellig(d, D(2026, 10, 16, 7, 59)), [])
        f = pflege.faellig(d, D(2026, 10, 16, 8, 0))
        self.assertEqual([x["text"] for x in f], ["Tablette"])
        self.assertTrue(pflege.bestaetigen(d, "e1", D(2026, 10, 16, 8, 1)))
        self.assertEqual(pflege.faellig(d, D(2026, 10, 16, 20, 0)), [])
        self.assertEqual(len(pflege.faellig(d, D(2026, 10, 17, 8, 0))), 1)  # morgen wieder
        self.assertFalse(pflege.bestaetigen(d, "gibtsnicht", D(2026, 10, 16)))

    def test_werktags_wochenende_tage(self):
        w = self.daten(erinnerungen=[{"id": "w", "zeit": "08:00", "text": "w", "wiederholen": "werktags"},
                                     {"id": "e", "zeit": "08:00", "text": "e", "wiederholen": "wochenende"},
                                     {"id": "t", "zeit": "08:00", "text": "t", "wiederholen": "tage", "tage": [2]}])
        ids = lambda dt: [x["id"] for x in pflege.faellig(w, dt)]
        self.assertEqual(ids(D(2026, 10, 14, 9, 0)), ["t", "w"])  # Mittwoch
        self.assertEqual(ids(D(2026, 10, 17, 9, 0)), ["e"])  # Samstag
        self.assertEqual(ids(D(2026, 10, 16, 9, 0)), ["w"])  # Freitag

    def test_einmal_braucht_datum_und_bleibt_bis_bestaetigt(self):
        d = self.daten(erinnerungen=[{"id": "x", "zeit": "10:00", "text": "Arzt", "wiederholen": "einmal", "datum": "2026-10-16"},
                                     {"id": "y", "zeit": "10:00", "text": "kaputt", "wiederholen": "einmal"}])
        self.assertEqual([e["id"] for e in d["erinnerungen"]], ["x"])
        self.assertEqual(pflege.faellig(d, D(2026, 10, 15, 12, 0)), [])
        self.assertEqual(len(pflege.faellig(d, D(2026, 10, 17, 9, 0))), 1)  # verpasst, bleibt
        pflege.bestaetigen(d, "x", D(2026, 10, 17, 9, 1))
        self.assertEqual(pflege.faellig(d, D(2026, 10, 18, 9, 0)), [])

    def test_inaktiv(self):
        d = self.daten(erinnerungen=[{"id": "e1", "zeit": "00:00", "text": "t", "aktiv": False}])
        self.assertEqual(pflege.faellig(d, D(2026, 10, 16, 12, 0)), [])

    def test_aufgaben_abhaken(self):
        d = self.daten(aufgaben=[{"id": "a1", "text": "Eins"}, {"id": "a2", "text": "Zwei"}])
        self.assertEqual([a["text"] for a in pflege.offene_aufgaben(d)], ["Eins", "Zwei"])
        self.assertTrue(pflege.abhaken(d, "a1"))
        self.assertFalse(pflege.abhaken(d, "a1"))
        self.assertEqual([a["text"] for a in pflege.offene_aufgaben(d)], ["Zwei"])

    def test_speichern_laden_und_kaputte_datei(self):
        with tempfile.TemporaryDirectory() as heim:
            self.assertEqual(pflege.laden(heim), pflege.leer())
            d = self.daten(aufgaben=[{"id": "a1", "text": "Eins"}])
            pflege.speichern(heim, d)
            self.assertEqual(pflege.laden(heim)["aufgaben"][0]["text"], "Eins")
            Path(pflege.datei(heim)).write_text("{kaputt", encoding="utf-8")
            self.assertEqual(pflege.laden(heim), pflege.leer())


if __name__ == "__main__":
    unittest.main()
