"""Tests für analyse.py und inhalt_check.py (python3 -m unittest discover -s tests)."""
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
import analyse  # noqa: E402
import inhalt_check  # noqa: E402


def saetze(text):
    return analyse.zerlege_saetze(analyse.bereinige_absatz(text, analyse.Counter()))


class Satztrennung(unittest.TestCase):
    def test_abkuerzungen(self):
        t = ("Viele Unternehmen, z. B. KMU, nutzen das, d. h. sie profitieren. Das gilt u. a. für den Handel, "
             "vgl. S. 12 f. und Abb. 3. Prof. Dr. Müller sieht das anders.")
        self.assertEqual(len(saetze(t)), 3)

    def test_ordinalzahlen(self):
        self.assertEqual(len(saetze("Am 3. Oktober begann die 2. Phase des Projekts im 19. Jahrhundert. Danach folgte nichts.")), 2)

    def test_jahr_am_satzende(self):
        self.assertEqual(len(saetze("Die Studie erschien im Jahr 2019. Danach änderte sich die Lage.")), 2)

    def test_kleine_zahl_am_satzende(self):
        self.assertEqual(len(saetze("Die Zahl der Befragten betrug 12. Die Ergebnisse sind daher vorläufig.")), 2)

    def test_frage_ausruf(self):
        self.assertEqual(len(saetze("Warum ist das so? Das ist unklar! Dennoch gibt es Hinweise.")), 3)

    def test_zitat_mit_punkt(self):
        self.assertEqual(len(saetze("Er schreibt: „Das ist wichtig.“ Danach folgt die Begründung.")), 2)

    def test_quellenverweise_werden_entfernt(self):
        z = analyse.Counter()
        out = analyse.bereinige_absatz("Das zeigt eine Studie (vgl. Müller et al. 2019, S. 12 ff.). Weitere Belege fehlen (ebd.).", z)
        self.assertEqual(z["zitate"], 2)
        self.assertNotIn("2019", out)

    def test_initialen(self):
        self.assertEqual(len(saetze("Laut J. Müller ist das falsch. Andere sehen das anders.")), 2)


class Woerter(unittest.TestCase):
    def test_tokens(self):
        toks = analyse.tokens("Die IT-Strategie der Mitarbeiter*innen kostet 3,5 Mio. Euro.")
        self.assertIn("IT-Strategie", toks)
        self.assertIn("Mitarbeiter*innen", toks)
        self.assertIn("3,5", toks)

    def test_silben(self):
        faelle = {"Haus": 1, "Unternehmen": 4, "Mitarbeiter": 4, "Strategie": 4, "Studie": 3, "Bau": 1,
                  "Arbeit": 2, "Information": 4, "Kommunikation": 5, "beeinflussen": 4}
        richtig = sum(analyse.silben(w) == n for w, n in faelle.items())
        self.assertGreaterEqual(richtig, 8, {w: analyse.silben(w) for w in faelle})


class Struktur(unittest.TestCase):
    def test_ueberschriften_listen_literatur(self):
        text = ("# Titel\n\n## 1. Einleitung\n\nDies ist ein Satz mit genug Wörtern für die Analyse hier. Noch ein Satz folgt.\n\n"
                "- Punkt eins\n- Punkt zwei\n\n"
                "Dies ist nicht der Fall.\n\n"
                "## Literaturverzeichnis\n\nMüller, A. (2019): Buch. Berlin.\n")
        s = analyse.zerlege_bloecke(text)
        self.assertEqual(len(s["listenpunkte"]), 2)
        self.assertTrue(s["literatur_abgeschnitten"])
        self.assertTrue(any("Dies ist nicht der Fall." in a for a in s["absaetze"]), s)
        self.assertFalse(any("Müller, A." in a for a in s["absaetze"]))

    def test_leerer_text(self):
        erg = analyse.analysiere_text("", [])
        self.assertEqual(erg["info"]["saetze"], 0)

    def test_metriken_gleichfoermig(self):
        satz = "Das Unternehmen setzt auf eine klare Strategie für die Zukunft."
        erg = analyse.analysiere_text(" ".join([satz] * 20), [])
        self.assertAlmostEqual(erg["metriken"]["satzlaenge_cv"], 0.0)
        self.assertAlmostEqual(erg["metriken"]["anteil_gleichfoermige_laeufe"], 1.0)


class Statistik(unittest.TestCase):
    def test_mattr_ttr_kurz(self):
        self.assertAlmostEqual(analyse.mattr(["a", "b", "a", "b"], 100), 0.5)

    def test_yule_k(self):
        self.assertAlmostEqual(analyse.yule_k(["a", "b", "c", "d"]), 0.0)

    def test_lesbarkeit(self):
        erg = analyse.analysiere_text("Der Hund bellt laut. Die Katze schläft ruhig. Das Kind spielt draußen.", [])
        m = erg["metriken"]
        self.assertAlmostEqual(m["lix"], m["satzlaenge_mittel"] + 100 * m["anteil_lange_woerter"], places=2)
        self.assertAlmostEqual(m["flesch_amstad"], 180 - m["satzlaenge_mittel"] - 58.5 * m["silben_mittel"], places=2)


class Inhaltscheck(unittest.TestCase):
    ORIG = ("## Ergebnisse\n\nIn der Befragung (n = 849) gaben 42 % der Mitarbeitenden an, Technostress zu erleben "
            "(Müller 2019, S. 12). Laut Schmidt (2020) steigt die Belastung „besonders bei ständiger Erreichbarkeit“. "
            "Die KMU im Sample waren stärker betroffen.\n")

    def test_stilaenderung_ok(self):
        neu = ("## Ergebnisse\n\n42 % der Mitarbeitenden gaben in der Befragung (n = 849) an, Technostress zu erleben "
               "(Müller 2019, S. 12). Die Belastung steigt laut Schmidt (2020) „besonders bei ständiger Erreichbarkeit“. "
               "Stärker betroffen waren die KMU im Sample.\n")
        self.assertTrue(inhalt_check.pruefe(self.ORIG, neu)["ok"])

    def test_zahl_geaendert(self):
        neu = self.ORIG.replace("42 %", "45 %")
        res = inhalt_check.pruefe(self.ORIG, neu)
        self.assertFalse(res["ok"])

    def test_quelle_geloescht(self):
        neu = self.ORIG.replace(" (Müller 2019, S. 12)", "")
        self.assertFalse(inhalt_check.pruefe(self.ORIG, neu)["ok"])


class Cli(unittest.TestCase):
    def test_json_ausgabe(self):
        import io
        import json
        from contextlib import redirect_stdout
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("Das ist ein Test. " * 30)
            pfad = f.name
        buf = io.StringIO()
        with redirect_stdout(buf):
            analyse.main([pfad, "--format", "json"])
        daten = json.loads(buf.getvalue())
        self.assertIn("metriken", daten)
        os.unlink(pfad)


if __name__ == "__main__":
    unittest.main()


class Coach(unittest.TestCase):
    def test_coach_laeuft_und_schreibt_verlauf(self):
        import coach
        text = ("## Einleitung\n\nDie Arbeitgebermarke ist für kleine Unternehmen wichtig. Darüber hinaus verdeutlicht dies, dass "
                "die Mitarbeitenden profitieren; die Bindung steigt. Insgesamt zeigt sich ein klarer Effekt für die Unternehmen.\n\n"
                "Die Studie untersucht drei Fälle aus dem Mittelstand. Sie nutzt Interviews mit Führungskräften und Beschäftigten.\n")
        c = coach.coache(text * 3, None, 10)
        self.assertIn("hinweise", c)
        texte = " ".join(h["text"] for h in c["hinweise"])
        self.assertIn("Mitarbeitende", texte)  # Nutzer-Vorgabe generisches Maskulinum wird immer gemeldet
        self.assertIn("Semikolon", texte)

    def test_zickzack_und_klammer(self):
        import coach
        # streng abwechselnd kurz/lang über mindestens vier Wechsel
        self.assertTrue(coach.zickzack([6, 24, 7, 25, 6, 23, 8]))
        # ähnlich lange Sätze hintereinander sind kein Zickzack
        self.assertFalse(coach.zickzack([18, 19, 21, 17, 20, 18]))
        self.assertEqual(coach.klammer_spannen("Die Daten wurden im Frühjahr 2019 online erhoben."), [3])  # Zahlen zählen nicht als Wort
        self.assertEqual(coach.klammer_spannen("Die Befragung wurde durchgeführt."), [])

    def test_mechanisch_verlaengert(self):
        import coach
        vorher = {"satzlaenge_mittel": 16.0, "woerter_pro_teilsatz": 8.0, "satzklammer_mittel": 5.0}
        angehaengt = {"satzlaenge_mittel": 20.0, "woerter_pro_teilsatz": 7.5, "satzklammer_mittel": 5.0}
        verdichtet = {"satzlaenge_mittel": 20.0, "woerter_pro_teilsatz": 9.0, "satzklammer_mittel": 5.0}
        self.assertTrue(coach.mechanisch_verlaengert(vorher, angehaengt))
        self.assertFalse(coach.mechanisch_verlaengert(vorher, verdichtet))
        self.assertFalse(coach.mechanisch_verlaengert(vorher, {**angehaengt, "satzlaenge_mittel": 17.0}))
        self.assertFalse(coach.mechanisch_verlaengert({}, angehaengt))
        c = coach.coache("Die Unternehmen investieren in die Ausbildung. Sie wollen Fachkräfte binden.\n\n" * 8,
                         {"messungen": [{"score": 50, "p_mensch": 0.5, "kennzahlen": {}, "roh": {"satzlaenge_mittel": 2.0,
                                                                                               "woerter_pro_teilsatz": 99.0}}]}, 5)
        self.assertTrue(c["fortschritt"]["mechanisch_verlaengert"])
        self.assertIn("Mechanisch verlängert", coach.bericht(c))
