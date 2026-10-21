"""Regressionstests aus der Integration von Coach v5 (CLI-Ende-zu-Ende über drei Runden, eval-employer-branding):
Die Orientierungszeile zum Funktionswort-Profil ordnet „als“ richtig ein – „weniger als 250“ ist eine Mengenangabe und wird
nicht von „gelten … als“ verschluckt, „geringere … Ressourcen als Großkonzerne“ ist ein Vergleich, keine Rolle. Aus der
60/60-Stichprobe (ssoar-66043 S13): kein neuer Absatz vor einem Satz, dessen Beleg auf die Quelle davor verweist („(ders.)“).

python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach  # noqa: E402
from test_coach_v4_praezision import ALS_TEXT  # noqa: E402

# Sätze aus eval-employer-branding (Satz 1 und 2 wie im Original, Satz 3 als Gegenprobe: Definition trotz Komparativ)
KMU = ("Nach der Empfehlung der Europäischen Kommission (2003) gelten Unternehmen mit weniger als 250 Beschäftigten und einem "
       "Jahresumsatz von höchstens 50 Mio. Euro als kleine und mittlere Unternehmen.")
RESSOURCEN = "Mittelständische Unternehmen verfügen meist über geringere finanzielle und personelle Ressourcen als Großkonzerne."
DEFINITION = "Größere Unternehmen sehen die Marke als Werkzeug der Personalgewinnung."


def stellen(text):
    """„als“-Stellen und die Satznummern der Sätze nach ihrem Anfang."""
    L = coach.Lauf(text, None)
    coach._hebel_priorisieren(L)
    nr = {s["text"][:12]: s["nr"] for s in L.fokus}
    return coach.fw_stellen(L, ["als"])["als"], nr


class AlsEinordnung(unittest.TestCase):
    def test_mengenangabe_wird_nicht_zur_konstruktion(self):
        self.assertIsNone(coach.GILT_ALS_RE.search("gelten Unternehmen mit weniger als 250 Beschäftigten"))
        self.assertIsNotNone(coach.GILT_ALS_RE.search("Das Verfahren gilt als zuverlässig."))
        # „weniger als“ vor einem Nomen gehört zur Konstruktion (Korpusbeispiele) und bleibt erkannt
        self.assertIsNotNone(coach.DIENT_ALS_RE.search("Soziale Netzwerke fungieren damit weniger als Instrument der Pflege."))
        self.assertIsNotNone(coach.VERSTEHT_SICH_ALS_RE.search("Er versteht sich dabei mehr als Konsument denn als Produzent."))

    def test_vergleich_und_definition_im_text(self):
        text = ALS_TEXT + " " + KMU + " " + RESSOURCEN + " " + DEFINITION
        st, nr = stellen(text)
        kmu, res, defi = nr[KMU[:12]], nr[RESSOURCEN[:12]], nr[DEFINITION[:12]]
        self.assertIn(kmu, st["notwendig"]["Vergleich/Mengenangabe"])  # „weniger als 250“
        self.assertIn(kmu, st["notwendig"]["Definition/Einordnung"])  # „gelten … als kleine und mittlere Unternehmen“
        self.assertIn(res, st["notwendig"]["Vergleich/Mengenangabe"])
        self.assertNotIn(res, st["notwendig"].get("Rolle/Funktion", []))
        self.assertIn(defi, st["notwendig"]["Definition/Einordnung"])
        self.assertNotIn(defi, st["notwendig"]["Vergleich/Mengenangabe"])
        self.assertFalse([k for k in st["notwendig"] if k.startswith("„gilt als“")])


# nach ssoar-66043 S12–S14 (gekürzt): S3 ist ein Zitat derselben Person wie in S2, belegt mit „(ders.)“
DERS_TEXT = ("Der Europäische Betriebsrat tagt zweimal im Jahr in wechselnden Städten. "
             "Die Fluktuation bei den Standortvertretern führt dazu, dass „solche Dinge in Vergessenheit geraten“ (IGM_B). "
             "„Die Unterscheidung von Rahmenvereinbarung und Kodex verschwimmt in der Wahrnehmung“ (ders.). "
             "Gefährlich sei dies, weil ein Kodex vom guten Willen des Arbeitgebers abhängt. "
             "Auf Managementseite wurde eine anonyme Beschwerdehotline eingerichtet. "
             "Die Hotline ist in der Compliance-Abteilung angesiedelt.")


class AbsatzNichtVorQuelleWieVorher(unittest.TestCase):
    def test_kein_absatz_vor_ders_oder_ebd(self):
        L = coach.Lauf(DERS_TEXT, None)
        liste = [s for s in L.fokus if s["absatz"] == L.fokus[0]["absatz"]]
        self.assertFalse(coach._absatz_trennbar(L, liste, 2))  # vor „… (ders.).“
        self.assertTrue(coach._absatz_trennbar(L, liste, 4))  # Themenwechsel zur Hotline bleibt möglich
        for beleg in ("(ebd., S. 12)", "(vgl. ebd. 14)", "(ebenda)", "(a. a. O., S. 3)", "(dies., S. 7)"):
            self.assertTrue(coach.QUELLE_WIE_VORHER_RE.search("Das gilt auch hier " + beleg + "."), beleg)
        for kein in ("Die Studie zeigt dies.", "Wir prüfen das (dies gilt auch für Kleinbetriebe).", "(Müller 2019, S. 4)"):
            self.assertIsNone(coach.QUELLE_WIE_VORHER_RE.search(kein), kein)


if __name__ == "__main__":
    unittest.main()
