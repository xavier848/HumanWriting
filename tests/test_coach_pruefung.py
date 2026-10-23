"""Regressionstests aus der adversarialen Prüfung von Coach v3 (Wirksamkeit + Präzision).

Je Test ein bestätigter Fund: Absatz-Trennstellen vor antwortenden Sätzen, Absatz-Umbau ohne Variationsverlust,
Bindestrich-Regel, Gender-Stämme und Maskulinformen, ehrliche Erreichbarkeit in der Diagnose, einräumendes „wenn auch“,
Possessiv-Bezug. Alle Texte sind synthetisch (keine Korpustexte).

python3 -m unittest discover -s tests
"""
import os
import re
import sys
import unittest
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
from test_coach import THEMEN, _KURZE_WORTE, satz  # noqa: E402

W = _KURZE_WORTE
FUELL = " ".join(satz(THEMEN[1], 17, 3 * i, W) for i in range(4))


def lauf(text):
    return coach.Lauf(text, None)


class AbsatzTrennstellen(unittest.TestCase):
    """Kein neuer Absatz vor einem Satz, der auf den Vorsatz antwortet, und nicht direkt nach einer Aufzählungsankündigung."""

    def _trennbar(self, saetze):
        L = lauf(" ".join(saetze) + "\n\n" + FUELL)
        liste = L.absaetze[1]
        return [coach._absatz_trennbar(L, liste, k) for k in range(1, len(saetze))]

    def test_kein_absatz_vor_antwortendem_konnektor(self):
        for anfang in ("Allerdings", "Dennoch", "Zugleich", "Doch", "Insofern", "Jedoch"):
            s = [satz(THEMEN[0], 17, 0, W), f"{anfang} betrifft die Firma neue Wege für den Kontakt mit jungen Leuten in der Region.",
                 satz(THEMEN[2], 18, 5, W)]
            self.assertEqual(self._trennbar(s)[0], False, anfang)

    def test_kein_absatz_vor_rueckverweis_adjektiv(self):
        s = [satz(THEMEN[0], 17, 0, W), "Die dortige Vernetzung betrifft neue Wege für den Kontakt mit jungen Leuten.",
             "Der beschriebenen Firma fehlt oft die Zeit für neue Wege in der Region und darüber hinaus."]
        self.assertEqual(self._trennbar(s), [False, False])

    def test_kein_absatz_nach_aufzaehlungsankuendigung(self):
        s = ["Aus der Literatur ergeben sich für die eigene Untersuchung zwei Annahmen.",
             "Die erste lautet, dass neue Wege für den Kontakt mit jungen Leuten wirken.",
             satz(THEMEN[2], 18, 5, W)]
        self.assertEqual(self._trennbar(s)[0], False)
        self.assertEqual(self._trennbar(s)[1], True)  # neutraler Satz: Trennung bleibt möglich


class AbsatzVariation(unittest.TestCase):
    def test_zu_lange_absaetze_ohne_variationsverlust(self):
        # Sätze pro Absatz zu hoch, Variation schon über dem Median: früher wurde mittig geteilt und die Variation sank
        # (0,603 → 0,578, im Modell Richtung KI). Jetzt nur Umbauten, die sie nicht senken (hier: keiner).
        L9 = [16, 18, 17, 19, 15, 18, 17, 16, 18, 17, 19, 15]
        teile = []
        for i, n in enumerate([2, 1, 10, 7, 11, 6]):
            saetze = [satz(THEMEN[i % len(THEMEN)], L9[j], 5 * i + 7 * j, W) for j in range(n)]
            for j in range(1, n):
                if j != n // 2:
                    saetze[j] = "Dies " + saetze[j][4:]
            teile.append(" ".join(saetze))
        text = "\n\n".join(teile)
        vorher = analyse.analysiere_text(text)
        S = {s["nr"]: s for s in vorher["saetze"]}
        for h in coach.coache(text, None, 40, roh=True)["hinweise_roh"]:
            if h["typ"] != "absatz_teilen":
                continue
            neu = text
            for nr in map(int, re.findall(r"vor Satz (\d+)", h["text"])):
                i = neu.find(S[nr]["text"])
                neu = neu[:i].rstrip(" ") + "\n\n" + neu[i:]
            self.assertGreaterEqual(analyse.analysiere_text(neu)["metriken"]["saetze_pro_absatz_cv"] + 1e-9,
                                    vorher["metriken"]["saetze_pro_absatz_cv"], h["text"])


class Bindestrich(unittest.TestCase):
    def typen(self, satz_text):
        c = coach.coache(satz_text + " " + FUELL, None, 40, roh=True)
        return {h["typ"] for h in c["hinweise_roh"] if h.get("satz") == 1}

    def test_gedankenstrich_zwischen_kleinwoertern_bleibt_gedankenstrich(self):
        t = self.typen("Die Preise bleiben hingegen - zumindest innerhalb eines Quartals - weitgehend stabil und gut planbar.")
        self.assertIn("gedankenstrich", t)
        self.assertNotIn("bindestrich", t)

    def test_bindestrich_zwischen_adjektiven_vor_nomen(self):
        t = self.typen("Ein einheitliches und technisch - organisatorisches Konzept wurde im Projekt entwickelt und erprobt.")
        self.assertIn("bindestrich", t)

    def test_strichpaar_ist_kein_bindestrich(self):
        t = self.typen("Das Vorhaben soll zum Abbau - vermeintlicher - fachlicher Barrieren in der Praxis beitragen.")
        self.assertNotIn("bindestrich", t)


class GenderStaemme(unittest.TestCase):
    def funde(self, text):
        return [(f["wort"], f["maskulin"]) for f in coach.gender_funde(text)]

    def test_keine_gender_form(self):
        for kein in ("Nach dem Ausbildungsende wechseln viele.", "Vor Arbeitsende kam der Anruf.", "Bis Kursende blieb Zeit.",
                     "Durch Ausblenden sinkt der Fehler.", "Die Vampirlegende lebt.", "Die Wartenden wurden ungeduldig.",
                     "Alleinstehende leben oft in kleinen Wohnungen.", "Die Vorzugsdividenden stiegen.", "Bis Tabellenende fehlt viel."):
            self.assertEqual(self.funde(kein), [], kein)

    def test_maskulinformen(self):
        self.assertEqual(self.funde("Beantwortende sagen wenig."), [("Beantwortende", "Befragten")])
        self.assertEqual(self.funde("Mittragende sind wichtig."), [("Mittragende", "Mitträger")])
        self.assertEqual(self.funde("Die Pflegenden und Teilnehmenden reden."), [("Pflegenden", "Pfleger"), ("Teilnehmenden", "Teilnehmer")])
        self.assertEqual(self.funde("Die Geringverdienenden zahlen."), [("Geringverdienenden", "Geringverdiener")])
        self.assertEqual(self.funde("Ärzt*innen, Freund_innen, BibliothekarInnen und NachbarInnen."),
                         [("Ärzt*innen", "Ärzte"), ("Freund_innen", "Freunde"), ("BibliothekarInnen", "Bibliothekare"),
                          ("NachbarInnen", "Nachbarn")])
        self.assertEqual(self.funde("Die Hausärzt*innen."), [("Hausärzt*innen", "Hausärzte")])


class DiagnoseErreichbarkeit(unittest.TestCase):
    def test_merkmal_ohne_auftrag_zaehlt_nicht(self):
        L = SimpleNamespace(
            bew={"verfuegbar": True, "p_mensch": 0.2,
                 "modell_beitraege": [{"id": "saetze_pro_absatz_cv", "name": "Absatz-Variation", "beitrag": -1.6},
                                      {"id": "anteil_mittlere_saetze", "name": "mittellange Sätze", "beitrag": -0.4},
                                      {"id": "satzklammer_mittel", "name": "Satzklammer", "beitrag": -0.5}]},
            messungen=[], ts={"modell": {}}, fw_potenzial=0.0, fw_diag=None, hinweise=[{"typ": "absatz_teilen"}])
        # v7.1: „mit Aufträgen“ zählt nur, was die angezeigten Aufträge simuliert bringen (netto_teile) – hier der Absatz-Auftrag
        auftrag = {"typ": "absatz_teilen", "hebel": "absaetze", "netto_logit": 1.6, "netto_teile": {"saetze_pro_absatz_cv": 1.6}}
        d = coach._diagnose(L, [auftrag], 0.86)
        z = {x["id"]: x for x in d["beitraege"]}
        self.assertAlmostEqual(z["saetze_pro_absatz_cv"]["erreichbar_logit"], 1.6)
        self.assertEqual(z["anteil_mittlere_saetze"]["erreichbar_logit"], 0.0)
        self.assertTrue(z["anteil_mittlere_saetze"]["ohne_stelle"])
        self.assertEqual(z["satzklammer_mittel"]["erreichbar_logit"], 0.0)
        self.assertAlmostEqual(d["erreichbar_logit"], 1.6)
        self.assertIn("ohne sichere Stelle", "\n".join(coach.diagnose_text(d)))


class WennAuch(unittest.TestCase):
    def test_einraeumendes_wenn_ist_keine_bedingung(self):
        saetze = ["Alle Filialen verfügen über einen Betriebsrat, wenn auch nicht immer mit einer festen Freistellung.",
                  "Die Werte bilden die Grundlage der Marke, wenn gleich ein einzelner Wert nicht entscheidet.",
                  "Die Kosten sinken deutlich, wenn die Produktion automatisiert wird."]
        L = lauf(" ".join(saetze) + " " + FUELL)
        auftraege = [coach.nebensatz_auftrag(L, s, L.masken[s["nr"]]) for s in L.saetze[:3]]
        self.assertIsNone(auftraege[0])
        self.assertIsNone(auftraege[1])
        self.assertIn("Bedingung", auftraege[2][1])
        self.assertIsNone(coach.KLAMMER_QUELLE_RE.search(saetze[0]))
        t = ("Die Reform brachte in vielen Regionen deutliche Verbesserungen für die Beschäftigten, wenn auch nicht in allen "
             "Bereichen und nicht für alle Gruppen gleichermaßen.")
        self.assertEqual(coach.teilstelle(t, t)[4], "wenngleich")
        self.assertIn("Einräumung", coach.fugen_technik("wenngleich"))


class PossessivBezug(unittest.TestCase):
    def vorschlag(self, a, b):
        L = lauf(a + " " + b + " " + FUELL)
        A, B = L.saetze[0], L.saetze[1]
        mt = coach.ANKNUEPF_RE.match(B["text"])
        return coach.bezug_vorschlag(L, A, B, "poss", mt.group("poss"))

    def test_sein_schliesst_person_nicht_aus(self):
        _, kand = self.vorschlag("Hallström glaubt, der letzte ehrliche Händler der Stadt zu sein.",
                                 "Seine Frau und sein Sohn führen inzwischen den Laden.")
        self.assertIn("Hallström", kand)

    def test_possessiv_kette_ohne_raten(self):
        self.assertEqual(self.vorschlag("Außerdem sind die Weber darauf bedacht, ihre eigene Tradition zu bewahren.",
                                        "Ihr Stolz ist groß und so geben sie ihr Wissen gerne weiter."), (True, []))

    def test_sachbezug_bleibt(self):
        self.assertEqual(self.vorschlag("Der Ansatz verbindet Theorie und Praxis in einem gemeinsamen Rahmen.",
                                        "Seine Stärke liegt in der klaren Struktur der einzelnen Schritte."), (True, ["Ansatz"]))


if __name__ == "__main__":
    unittest.main()
