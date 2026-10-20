"""Tests für die PDF-Extraktion der Kalibrierung (Text-Hilfsfunktionen, ohne PDF)."""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "kalibrierung", "scripts"))
import extract_text as e  # noqa: E402


class Zeilen(unittest.TestCase):
    def test_silbentrennung(self):
        self.assertEqual(e.join_lines(["Das Unter-", "nehmen wächst."]), "Das Unternehmen wächst.")
        self.assertEqual(e.join_lines(["Das Unter‐", "nehmen wächst."]), "Das Unternehmen wächst.")

    def test_kompositum_und_ellipse(self):
        self.assertEqual(e.join_lines(["die Marketing-", "Strategie"]), "die Marketing-Strategie")
        self.assertEqual(e.join_lines(["Ein-", "und Ausgang"]), "Ein- und Ausgang")
        self.assertEqual(e.join_lines(["mittel-", "bis langfristig"]), "mittel- bis langfristig")
        self.assertEqual(e.join_lines(["Flaschen so-", "wie Dosen"]), "Flaschen sowie Dosen")


class Fussnoten(unittest.TestCase):
    def test_marker_weg_zahlen_bleiben(self):
        t = "Das Unternehmen12 wächst.3 Der Wert liegt bei 0,67 und 9.000 Euro, Web 2.0 und CO2 am 30.10.2019."
        out = e.INLINE_FOOTNOTE.sub("", t)
        self.assertIn("Unternehmen wächst.", out)
        for z in ("0,67", "9.000", "Web 2.0", "CO2", "30.10.2019"):
            self.assertIn(z, out)


class Prosa(unittest.TestCase):
    SATZ = ("Die Untersuchung zeigt, dass kleine und mittlere Unternehmen ihre Arbeitgebermarke seltener "
            "systematisch entwickeln als große Konzerne, obwohl sie davon besonders profitieren könnten. "
            "Gründe dafür sind fehlende Ressourcen und eine geringe Bekanntheit in der Region.")

    def test_prosa_ok(self):
        self.assertIsNone(e.prose_problem(self.SATZ))

    def test_literatur(self):
        self.assertEqual(e.prose_problem("Müller, A. & Schmidt, B. (2019). Employer Branding in KMU. Wiesbaden: Springer Gabler, "
                                         "S. 12–45, hier insbesondere das Kapitel zur Arbeitgebermarke und den Fallstudien zu den Unternehmen aus dem Mittelstand."), "literatur")
        self.assertEqual(e.prose_problem("[9] F. J. Robertz und R. Wickenhäuser, Der Riss in der Tafel. Amoklauf und schwere Gewalt "
                                         "in der Schule. Heidelberg: Springer, 2007, mit weiteren Angaben zu den Fallbeispielen."), "literatur")

    def test_vorspann(self):
        self.assertEqual(e.prose_problem("Ich bedanke mich bei all meinen Kolleginnen und Kollegen, die durch ihre aktive und "
                                         "kreative Teilnahme diese Studie erst möglich gemacht haben und mich unterstützt haben."), "vorspann")

    def test_liste_und_formel(self):
        self.assertEqual(e.prose_problem("Die Termine: - Weltmeisterschaft im Einzel - Weltmeisterschaft im Team - Europameisterschaft "
                                         "- Weltcup in Berlin und weitere Wettbewerbe, die für die Saison von Bedeutung sind."), "liste")


if __name__ == "__main__":
    unittest.main()
