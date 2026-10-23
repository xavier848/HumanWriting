"""Tests für Coach v3 (Integration): Funde aus dem Zusammenführen von Wirksamkeit, Präzision und Prüfung.

- Synonym-Cluster: Eine geschützte Einzelform (Rechtsbegriff) fällt aus dem Cluster, die übrigen Formen bleiben ein Fund.
- Erneute Messung eines unveränderten Texts ist keine Stagnation: keine Diagnose „nicht erreichbar“, sondern der Hinweis,
  dass die genannten Stellen noch offen sind.
- Diagnosezeilen nennen den Modellbeitrag ausdrücklich als „Beitrag“ (nicht mit dem Kennzahlwert verwechselbar).

Alle Texte sind synthetisch (keine Korpustexte).

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
from test_coach import KI_TEXT  # noqa: E402
from test_coach_wirksamkeit import gleichmaessig, mit_metriken  # noqa: E402
from unittest import mock  # noqa: E402


def synonyme_wirksam():
    """v7.1 (Mindestwirkung): Unter dem Modellziel erscheinen nur Aufträge mit simuliertem Netto-Gewinn > NETTO_TOLERANZ. Der
    Synonym-Auftrag dieser Kunsttexte bringt simuliert nichts (MATTR ist gemockt) und würde nicht mehr angezeigt – für die Prüfung von
    Gedächtnis und Teilschutz gilt er hier als wirksam."""
    echt = coach.netto_wirkung

    def fake(L, h):
        n, t = echt(L, h)
        return (max(n, 0.05), t) if h["typ"] == "synonyme" else (n, t)
    return mock.patch.object(coach, "netto_wirkung", fake)


class SynonymTeilschutz(unittest.TestCase):
    TEXT = ("Die Kunden vergleichen Preise im Netz. Viele Kunden kaufen heute online ein. Die Konsumenten reagieren schnell auf "
            "Rabatte. Seit der Richtlinie (EU) 2019/2161 müssen Händler Verbraucher über personalisierte Preise informieren. "
            "Die Kunden achten auf Bewertungen. Die Konsumenten wechseln oft den Anbieter. Die Kunden lesen Testberichte.")

    def syn(self, text):
        with mit_metriken(mattr_100=0.9):
            c = coach.coache(text + "\n\n" + gleichmaessig(3, 5), None, 40, roh=True)
        return [x for x in c["hinweise_roh"] if x["typ"] == "synonyme"]

    def test_geschuetzte_form_faellt_nur_aus_dem_cluster(self):
        syn = self.syn(self.TEXT)
        self.assertEqual(len(syn), 1)
        h = syn[0]
        self.assertIn("Konsumenten", h["text"])
        self.assertNotIn("Verbraucher", h["text"])
        self.assertEqual(h["zaehlung"], {"kunden": 4, "konsumenten": 2})
        self.assertEqual(h["anfang"], "syn:konsumenten|kunden")
        self.assertNotIn("verbraucher", h["ersetzbar"])
        self.assertIn("konsumenten", h["ersetzbar"])

    def test_unveraenderter_text_wiederholt_den_hinweis(self):
        text = self.TEXT + "\n\n" + gleichmaessig(3, 5)
        with mit_metriken(mattr_100=0.9), synonyme_wirksam():
            c1 = coach.coache(text, None, 40, roh=True)
            c2 = coach.coache(text, {"messungen": [c1["stand"]]}, 40, roh=True)  # nur erneut gemessen
            umgebaut = text.replace("Die Kunden lesen Testberichte.", "Die Kunden lesen oft Testberichte.")
            c3 = coach.coache(umgebaut, {"messungen": [c1["stand"]]}, 40, roh=True)  # überarbeitet, Synonyme nicht angefasst
        syn = lambda c: [x for x in c["hinweise_roh"] if x["typ"] == "synonyme"]  # noqa: E731
        self.assertTrue(syn(c1))
        self.assertTrue(syn(c2))
        self.assertTrue(all(x.get("schon_genannt") for x in syn(c2)))
        self.assertFalse(syn(c3))

    def test_nur_eine_form_uebrig_kein_hinweis(self):
        text = self.TEXT.replace("Die Konsumenten reagieren", "Die Kunden reagieren").replace("Die Konsumenten wechseln", "Die Kunden wechseln")
        self.assertEqual(self.syn(text), [])


class UnveraenderterText(unittest.TestCase):
    def test_erneute_messung_ist_keine_stagnation(self):
        c1 = coach.coache(KI_TEXT, None, 2)
        self.assertIsNotNone(c1["diagnose"])  # wenige Hinweise: Diagnose (Stagnationsregel)
        c2 = coach.coache(KI_TEXT, {"messungen": [c1["stand"]]}, 2)
        self.assertIsNone(c2["diagnose"])
        self.assertTrue(c2["fortschritt"]["unveraendert"])
        txt = coach.bericht(c2)
        self.assertIn("unverändert", txt)
        self.assertNotIn("Warum das Modellziel noch fehlt", txt)
        c3 = coach.coache(KI_TEXT, {"messungen": [c1["stand"], c2["stand"]]}, 2)
        self.assertIsNone(c3["diagnose"])  # auch zweimal unverändert nicht

    def test_ueberarbeiteter_text_ist_nicht_unveraendert(self):
        c1 = coach.coache(KI_TEXT, None, 2)
        c2 = coach.coache(KI_TEXT.replace("die Ressourcen fehlen oft", "die Ressourcen fehlen häufig"), {"messungen": [c1["stand"]]}, 2)
        self.assertFalse(c2["fortschritt"]["unveraendert"])
        self.assertIsNotNone(c2["diagnose"])


class FunktionswortModalverb(unittest.TestCase):
    TEXT = ("## Planung\n\nDer Jahresbericht kann im kommenden Jahr als Planungsgrundlage für alle Abteilungen dienen. "
            "Das Controlling fungiert dabei als Schnittstelle zwischen Leitung und Fachbereichen im ganzen Betrieb. "
            "Die Abteilungen nutzen die Zahlen als Maßstab für ihre Ziele und als Quelle für die Budgets. "
            "Die Leitung sieht den Bericht als Werkzeug und als Hilfe für die Teams und ihre Arbeit.\n")

    def test_modalverb_bleibt(self):
        c = coach.coache(self.TEXT, None, 40, roh=True)
        als = {h["satz"]: h["text"] for h in c["hinweise_roh"] if h["typ"] == "fw_als"}
        self.assertIn(1, als)
        self.assertIn("„kann“ bleibt", als[1])
        if 2 in als:
            self.assertNotIn("bleibt (die Möglichkeit", als[2])  # ohne Modalverb kein Zusatz

    def test_modalverb_im_teilsatz(self):
        m = "Die Marke kann, wie Studien zeigen, als Signal dienen."
        self.assertIsNone(coach.modalverb_im_teilsatz(m, m.index("als"), m.index("dienen") + 6))  # „kann“ steht vor dem Einschub
        m2 = "Die Marke kann als Signal dienen, wenn sie glaubwürdig ist."
        self.assertEqual(coach.modalverb_im_teilsatz(m2, m2.index("als"), m2.index("dienen") + 6), "„kann“")


class DiagnoseText(unittest.TestCase):
    def test_beitrag_ausdruecklich(self):
        c = coach.coache(KI_TEXT, None, 2)
        zeilen = [z for z in coach.diagnose_text(c["diagnose"]) if z.startswith("- ")]
        self.assertTrue(zeilen)
        self.assertTrue(all(": Beitrag -" in z or ": Beitrag −" in z for z in zeilen), zeilen)


if __name__ == "__main__":
    unittest.main()
