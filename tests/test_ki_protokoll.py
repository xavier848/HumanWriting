"""Tests für ki_protokoll.py (Dokumentationstabelle der KI-Nutzung aus Coach-Verläufen)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
import ki_protokoll  # noqa: E402

VERLAUF = {
    "datei": "/tmp/kapitel2.md",
    "messungen": [
        {"zeit": "2026-10-21T10:15", "hinweise": [
            {"typ": "buendeln", "anfang": "Viele Unternehmen", "satz": 3},
            {"typ": "konnektor", "anfang": "Zudem zeigen", "satz": 5},
            {"typ": "floskel", "anfang": "Die Kultur spielt", "satz": 7},
            {"typ": "gender", "anfang": "gender:mitarbeiter", "satz": None},
        ]},
        {"zeit": "2026-10-23T09:00", "hinweise": [
            {"typ": "buendeln", "anfang": "Viele Unternehmen", "satz": 3},  # Wiederholung zählt nicht doppelt
            {"typ": "teilen", "anfang": "Trotz der", "satz": 9},
            {"typ": "fw_lassen", "anfang": "Daraus lässt", "satz": 11},
            "kaputt",
        ]},
    ],
}


def ausfuehren(*argv):
    puffer = io.StringIO()
    with contextlib.redirect_stdout(puffer):
        code = ki_protokoll.main(list(argv))
    return code, puffer.getvalue()


class TestAuswertung(unittest.TestCase):
    def test_zaehlt_eindeutige_hinweise_und_bereiche(self):
        a = ki_protokoll.auswerten(VERLAUF)
        self.assertEqual(a["runden"], 2)
        self.assertEqual(a["hinweise"], 6)
        self.assertEqual(a["bereiche"][0], "satzlaenge")  # buendeln + teilen
        self.assertEqual(set(a["bereiche"]), {"satzlaenge", "konnektoren", "floskeln", "form", "satzbau"})
        self.assertEqual([z.day for z in a["zeiten"]], [21, 23])

    def test_bereich_unbekannter_typ(self):
        self.assertEqual(ki_protokoll.bereich("neu_erfunden"), "stil")
        self.assertEqual(ki_protokoll.bereich("nebensatz_relativ"), "satzbau")
        self.assertEqual(ki_protokoll.bereich("absatz_teilen"), "absaetze")

    def test_leerer_verlauf(self):
        a = ki_protokoll.auswerten({})
        self.assertEqual((a["runden"], a["hinweise"], a["bereiche"]), (0, 0, []))


class TestTabelle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pfad = os.path.join(self.tmp.name, "kapitel2.coach.json")
        with open(self.pfad, "w", encoding="utf-8") as f:
            json.dump(VERLAUF, f)

    def tearDown(self):
        self.tmp.cleanup()

    def test_deutsche_zeile_coach(self):
        code, aus = ausfuehren(self.pfad, "--kapitel", "2 Grundlagen | Teil A", "--prompt", "Prüf Kapitel 2")
        self.assertEqual(code, 0)
        zeilen = aus.strip().splitlines()
        self.assertEqual(len(zeilen), 3)
        self.assertTrue(zeilen[0].startswith("| Kapitel/Abschnitt | Werkzeug | Zweck |"))
        zellen = [z.strip() for z in zeilen[2].strip("|").split("|")]
        self.assertEqual(len(zellen), 5)  # Senkrechtstrich im Kapitel darf die Tabelle nicht sprengen
        self.assertEqual(zellen[0], "2 Grundlagen / Teil A")
        self.assertIn("Satzlängen", zellen[2])
        self.assertIn("„Prüf Kapitel 2“", zellen[3])
        self.assertIn("2 Messrunden (21.10.2026–23.10.2026)", zellen[4])
        self.assertIn("6 Hinweise", zellen[4])
        self.assertIn("in eigenen Worten", zellen[4])
        self.assertNotIn("Hinweis: Im Überarbeiten-Modus", aus)

    def test_englisch_und_ueberarbeiten(self):
        code, aus = ausfuehren(self.pfad, "--sprache", "en", "--modus", "ueberarbeiten")
        self.assertEqual(code, 0)
        self.assertIn("| Chapter/Section | Tool(s) used | Purpose | Representative Prompt(s) | Outcome / Integration into Thesis |", aus)
        self.assertIn("kapitel2", aus)  # Standard-Kapitel aus dem Dateinamen
        self.assertIn("Claude rephrased sentences", aus)
        self.assertIn("2026-10-21–2026-10-23", aus)
        self.assertIn("sparingly and selectively", aus)

    def test_ohne_zeitstempel_datum_der_datei(self):
        alt = {"messungen": [{"hinweise": [{"typ": "konnektor", "anfang": "Zudem", "satz": 1}]}]}
        with open(self.pfad, "w", encoding="utf-8") as f:
            json.dump(alt, f)
        os.utime(self.pfad, (1792800000, 1792800000))  # 24.10.2026 (UTC)
        code, aus = ausfuehren(self.pfad)
        self.assertEqual(code, 0)
        self.assertRegex(aus, r"1 Messrunde \((2[34])\.10\.2026\), 1 Hinweis ")

    def test_unlesbare_datei(self):
        kaputt = os.path.join(self.tmp.name, "kaputt.coach.json")
        with open(kaputt, "w", encoding="utf-8") as f:
            f.write("{nicht json")
        fehler = io.StringIO()
        with contextlib.redirect_stderr(fehler):
            code, _ = ausfuehren(kaputt)
        self.assertEqual(code, 1)
        self.assertIn("kein lesbarer Coach-Verlauf", fehler.getvalue())


if __name__ == "__main__":
    unittest.main()
