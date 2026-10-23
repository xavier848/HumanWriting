"""Regressionstests aus der adversarialen Prüfung von Coach v7 (C1 + C2):

1. Zitatschutz bei gestörten Anführungszeichen: ein verirrtes gerades Zeichen (Zoll-Zeichen, Tippfehler) oder ein gemischt
   geschlossenes Zitat („…") vor einem echten Zitat hielt die Verschachtelungstiefe für den Rest des Absatzes über 0 – spätere
   wörtliche Zitate blieben ungeschützt (fhws: Gender-Vorgabe für „Studierenden“ in S26/S27 des Interviewzitats).
2. Teilziel im Rückfall auf den zweiseitigen Score: deckt die Gegenseite die Score-Lücke, keine Punktesammel-Aufträge auf der
   KI-Seite (fhws p = 1,0, Score 50 / KI-Seite 83: Absatz teilen + Gegenfolie; bt-wd9: zwei Floskel-Aufträge), auch nicht als
   Score-Teil bei kleiner Modell-Lücke (haw-7747: zwei Bündel-Aufträge für 3 Score-Punkte).
3. Artikel der Fugen-Technik („den Gegensatz … behalten“, nicht „die Gegensatz“).

python3 -m unittest discover -s tests
"""
import os
import sys
import unittest
from unittest import mock
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
from test_coach import KI_TEXT  # noqa: E402
from test_coach_v7 import FHWS_ABSATZ, FUELL  # noqa: E402

REF = analyse.lade_baselines()["textsorten"]["hochschule"]["metriken"]


def masken(text):
    s = analyse.analysiere_text(text)["saetze"]
    return s, coach.zitat_masken(s)


def satz_mit(saetze, anf):
    return next(x for x in saetze if x["text"].lstrip("»„\"").startswith(anf))


class ZitatGestoert(unittest.TestCase):
    def test_verirrtes_gerades_zeichen_vor_zitat(self):
        text = ("Die Skala reichte von 1 bis 5\" und wurde vorab getestet. Ein Befragter sagte dazu: „Darüber hinaus ist das nicht nur "
                "gut, sondern auch notwendig für alle Beteiligten.“ Das sehen wir in der Auswertung anders.\n\n" + FUELL)
        s, m = masken(text)
        zitat = satz_mit(s, "Ein Befragter")
        self.assertNotIn("Darüber", m[zitat["nr"]])
        self.assertNotIn("sondern", m[zitat["nr"]])
        self.assertIn("Ein Befragter sagte", m[zitat["nr"]])
        self.assertIn("Das sehen wir", m[satz_mit(s, "Das sehen wir")["nr"]])
        self.assertIn("Die Skala reichte", m[satz_mit(s, "Die Skala")["nr"]])

    def test_verirrtes_englisches_zeichen_vor_zitat(self):
        text = ("Das Wort “Kompetenz bleibt in der Literatur unscharf. Ein Befragter sagte dazu: „Darüber hinaus ist das nicht nur gut, "
                "sondern auch notwendig für alle Beteiligten.“ Das sehen wir in der Auswertung anders.\n\n" + FUELL)
        s, m = masken(text)
        self.assertNotIn("Darüber", m[satz_mit(s, "Ein Befragter")["nr"]])
        self.assertIn("Das sehen wir", m[satz_mit(s, "Das sehen wir")["nr"]])

    def test_gemischt_geschlossen(self):
        # „…" (gerades Schlusszeichen): beide Zitate geschützt, der eigene Text dazwischen nicht
        text = ("Ein Befragter sagte: „Darüber hinaus ist das gut\". Ein anderer meinte zur gleichen Frage: „Das ist nicht nur gut, "
                "sondern auch notwendig.\" Das sehen wir in der Auswertung anders.\n\n" + FUELL)
        s, m = masken(text)
        erster, zweiter = satz_mit(s, "Ein Befragter"), satz_mit(s, "Ein anderer")
        self.assertNotIn("Darüber", m[erster["nr"]])
        self.assertNotIn("sondern", m[zweiter["nr"]])
        self.assertIn("Ein anderer meinte zur gleichen Frage", m[zweiter["nr"]])
        self.assertIn("Das sehen wir", m[satz_mit(s, "Das sehen wir")["nr"]])

    def test_gerade_anfuehrung_innen_bleibt_verschachtelt(self):
        # "…" innerhalb von „…“ ist eine innere Ebene, kein Schluss des äußeren Zitats
        text = ("Die Autorin schreibt: „Wir nennen das \"nicht nur gut, sondern nötig\" und meinen damit alle Beteiligten.“ Danach "
                "folgt in der Arbeit ein eigener Abschnitt zur Methode.\n\n" + FUELL)
        s, m = masken(text)
        zitat = satz_mit(s, "Die Autorin")
        self.assertNotIn("meinen damit", m[zitat["nr"]])
        self.assertNotIn("sondern", m[zitat["nr"]])
        self.assertIn("Die Autorin schreibt", m[zitat["nr"]])
        self.assertIn("folgt in der Arbeit", m[satz_mit(s, "Danach")["nr"]])

    def test_regression_fhws_zoll_zeichen_vor_interviewzitat(self):
        # verirrtes gerades Zeichen im eigenen Text vor dem zweiten Interviewzitat (S10–S11): das Zitat bleibt geschützt, die
        # Gender-Vorgabe nennt die Zitatsätze nicht als zu ändernde Stellen
        text = FHWS_ABSATZ.replace("Die selbst gewählten Ziele konnten", "Die selbst gewählten Ziele (Skala bis 5\") konnten") \
            + "\n\n" + FUELL
        s, m = masken(text)
        zitat_nrn = {satz_mit(s, a)["nr"] for a in ("Und so ist es ganz klar", "Ja und unsere Angebote")}
        for n in zitat_nrn:
            self.assertNotRegex(m[n], r"[A-Za-zÄÖÜäöü]{3}")
        c = coach.coache(text, None, 40, roh=True)
        for h in c["hinweise_roh"] + c["vorgaben"]:
            nrn = set(h.get("saetze") or []) | ({h["satz"]} if h.get("satz") else set())
            self.assertFalse(nrn & zitat_nrn, h["text"])


def gegenseite_bewertung(score, p_mensch):
    """analysiere_und_bewerte mit vorgegebenem Score/p und allen bewerteten Kennzahlen rot auf der der KI abgewandten Seite
    (Rückfall: ohne score_ki/ziel_score_ki)."""
    echt = coach.analyse.analysiere_und_bewerte

    def fake(*a, **k):
        erg, bew = echt(*a, **k)
        zeilen = []
        for z in bew["kennzahlen"]:
            r = REF.get(z["id"])
            z = dict(z)
            if z["bewertet"] and r and r.get("ki", {}).get("p50") is not None:
                m = r["mensch"]
                breite = (m["p90"] - m["p10"]) or 1.0
                ki_oben = r["ki"]["p50"] > m["p50"]
                z["wert"] = m["p10"] - 0.5 * breite if ki_oben else m["p90"] + 0.5 * breite
                z["status"] = "rot"
            z.pop("seite", None)
            z.pop("jenseits_band", None)
            zeilen.append(z)
        bew = dict(bew, kennzahlen=zeilen, score=score, p_mensch=p_mensch)
        bew.pop("score_ki", None)
        bew.pop("ziel_score_ki", None)
        return erg, bew
    return mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake)


class TeilzielGegenseite(unittest.TestCase):
    def test_gegenseite_deckt_keine_auftraege(self):
        with gegenseite_bewertung(score=45, p_mensch=0.99):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertFalse(c["ziel_erreicht"])
        self.assertTrue(c["teilziel"]["gegenseite_deckt"])
        self.assertEqual(c["teilziel"]["hebel"], [])
        self.assertEqual([h for h in c["hinweise"] if h["typ"] != "bereinigung"], [])
        b = coach.bericht(c)
        self.assertIn("kein Handlungsbedarf, keine Aufträge dazu", b)
        self.assertNotIn("Die wichtigsten Hebel", b)
        self.assertNotIn("Deshalb nur Hinweise zu", b)

    def test_ohne_gegenseite_bleiben_teilziel_auftraege(self):
        echt = coach.analyse.analysiere_und_bewerte

        def fake(*a, **k):
            erg, bew = echt(*a, **k)
            return erg, dict(bew, score=40, p_mensch=0.99, score_ki=None, ziel_score_ki=None)
        with mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertIsNotNone(c["teilziel"])
        self.assertFalse(c["teilziel"]["gegenseite_deckt"])
        self.assertTrue(c["hinweise"])

    def test_score_teil_bei_modell_luecke_entfaellt(self):
        # kleine Modell-Lücke plus Score-Lücke, die die Gegenseite deckt: nur die Modell-Aufträge, kein Score-Teil
        with gegenseite_bewertung(score=45, p_mensch=0.85):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertFalse((c.get("teilziel") or {}).get("mit_modell"))
        self.assertLessEqual(len([h for h in c["hinweise"] if h["typ"] != "bereinigung"]), coach.KLEINE_LUECKE_MAX)

    def test_einseitig_zaehlt_gegenseite_nicht(self):
        L = SimpleNamespace(bew={"kennzahlen": []}, kz={})
        self.assertEqual(coach.gegenseite_punkte(L, {"einseitig": True}), 0.0)


class FugenArtikel(unittest.TestCase):
    def test_genus(self):
        self.assertTrue(coach.fugen_technik("aber").startswith("den Gegensatz"))
        self.assertTrue(coach.fugen_technik("wobei").startswith("den Bezug"))
        self.assertTrue(coach.fugen_technik("indem").startswith("das Mittel"))
        self.assertTrue(coach.fugen_technik("während").startswith("den Gegensatz bzw. Zeitbezug"))
        self.assertTrue(coach.fugen_technik("weil").startswith("die Begründung"))


if __name__ == "__main__":
    unittest.main()
