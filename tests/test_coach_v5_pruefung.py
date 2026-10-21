"""Regressionstests aus der adversarialen Prüfung von Coach v5: Diagnose zählt den nur durch Neuformulieren erreichbaren
Funktionswort-Rest nicht als Einzelkorrektur, Abkürzungs-Textaufträge halten „ein Auftrag je Satz“ ein, „ermöglicht es“ übernimmt nur
ein Subjekt (keine Objekte, keine falsch gebeugten Formen), Synonyme nur über Wort bzw. Grundwort („Studien“ ≠ „Studiengänge“),
Rückbezug nur auf ein Kapitel im nahen Kontext, kein Bündeln, wenn Satz b einen Gegensatz oder eine Bedingung trägt (ohm-163).

python3 -m unittest discover -s tests
"""
import os
import sys
import unittest
import unittest.mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach  # noqa: E402
from test_coach import KI_TEXT  # noqa: E402
from test_coach_wirksamkeit import gleichmaessig  # noqa: E402

FUELL = gleichmaessig(6, 5)

# Sätze aus der Prüfung (echter Abschnitt opus-fh/ohm-163 der 60/60-Stichprobe)
OHM_41 = "Hierbei gibt es pro User in den Testdatensätzen genau einen Sprung abhängig von dem relativen Rang des relevanten Items."
OHM_42 = "Wird diese beispielsweise genau auf dem Rang 250 empfohlen, ergibt sich ein relativer Rang von 250/500 = 0,5."
OHM_30 = ("Um dies didaktisch aufzuarbeiten wird in diesem Kapitel zunächst beispielhaft eine Simulationsstudie durchgeführt und die "
          "Ergebnisse der Studie kurz erläutert.")
OHM_31 = ("In der vorliegenden Untersuchung steht jedoch die Darstellung des Konzepts einer Simulationsstudie im Vordergrund, die "
          "eigentlichen Ergebnisse werden also nur nachrangig behandelt.")


def lauf(text):
    L = coach.Lauf(text, None)
    coach._hebel_priorisieren(L)
    coach._waechter(L)
    return L


class DiagnoseNeuformulieren(unittest.TestCase):
    def test_nur_neuformulieren_zaehlt_nicht_fuer_die_einstufung(self):
        # DP-Endstand aus Eval4 (p 0,318): Funktionswort-Profil dominiert, keine umbaubare Konstruktion mehr – der Richtwert (0,90) ist
        # nur durch Neuformulieren ganzer Absätze erreichbar und darf aus „Grenze der Einzelkorrekturen“ (45 %) kein „knapp“ machen
        L = lauf(KI_TEXT)
        L.hinweise = []
        L.fw_potenzial = 0.0
        L.fw_diag = dict(L.fw_diag, woerter=[dict(r, zu_viel=False) for r in L.fw_diag["woerter"]])  # nichts Umbaubares übrig
        b = [{"id": "fw_profil_llr_pro_1000", "name": "FW", "beitrag": -3.09}, {"id": "nachbarsatz_ueberlappung", "name": "NS", "beitrag": -0.96},
             {"id": "mattr_100", "name": "MATTR", "beitrag": -0.93}, {"id": "satzklammer_mittel", "name": "Klammer", "beitrag": -0.76},
             {"id": "anteil_sehr_lange_saetze", "name": "sehr lang", "beitrag": -0.25},
             {"id": "satzlaenge_dispersion", "name": "Dispersion", "beitrag": -0.17}]
        L.bew = dict(L.bew, verfuegbar=True, p_mensch=0.318, modell_beitraege=b)
        L.messungen = [{"p_mensch": 0.18}, {"p_mensch": 0.31}]  # Stagnation
        self.assertEqual(coach.fw_offen(L), {})
        d = coach._diagnose(L, [], 0.86)
        self.assertTrue(d["fw_dominant"])
        fw = next(z for z in d["beitraege"] if z["id"] == "fw_profil_llr_pro_1000")
        self.assertEqual(fw["wie"], "nur_neuformulieren")
        self.assertGreater(fw["rest_logit"], 0)
        self.assertEqual(d["grenze"], "einzelkorrekturen")  # vorher „knapp“ (2,06 von 2,58)
        rest_einzel = sum(z["rest_logit"] for z in d["beitraege"] if z is not fw)
        self.assertAlmostEqual(d["stellenlos_logit"], rest_einzel, places=2)
        self.assertAlmostEqual(d.get("neuformulieren_logit", 0.0), fw["rest_logit"], places=2)
        self.assertLess(d["erreichbar_logit"] + d["stellenlos_logit"], coach.KNAPP_ANTEIL * d["luecke_logit"])
        txt = "\n".join(coach.diagnose_text(d))
        self.assertIn("Grenze der Einzelkorrekturen", txt)
        self.assertNotIn("Knapp", txt)
        self.assertIn("nur durch Neuformulieren ganzer Absätze, keine Einzelkorrektur", txt)


class AbkuerzungEinAuftragJeSatz(unittest.TestCase):
    TEXT = (FUELL + "\n\nDie Firma hat rund 500 Beschäftigte in der Region und plant dazu mehr Zeit und Geld ein.\n\n"
            "Im Ausland arbeiten etwa 120 weitere Beschäftigte für die Firma an zwei neuen Standorten.")

    def abk(self, belegen):
        L = coach.Lauf(self.TEXT, None)
        coach._hebel_priorisieren(L)
        r = L.ref["abkuerzungen_pro_1000"]
        L.ref = dict(L.ref, abkuerzungen_pro_1000=dict(r, mensch=dict(r["mensch"], p50=2.0, p75=4.0)))
        if belegen:
            s = next(x for x in L.saetze if x["text"].startswith("Im Ausland"))
            L.hinweis("floskel", s, "Satz: anderer Auftrag", 0.6)
        with unittest.mock.patch.object(coach.Lauf, "modell_hebel", lambda self, k: True):
            coach._abkuerzungen(L)
        return L, [h for h in L.hinweise if h["typ"] == "abkuerzung"]

    def test_textauftrag_nicht_an_einem_belegten_satz(self):
        _L, frei = self.abk(False)
        self.assertEqual(len(frei), 1)  # Kontrolle: ohne anderen Auftrag ein Textauftrag über beide Sätze
        L, belegt = self.abk(True)
        self.assertEqual(belegt, [])  # sonst zwei Aufträge an „Im Ausland …“ (Floskel + Abkürzung), an der Zusammenfassung vorbei
        self.assertEqual(L.unterdrueckt.get("abk_familie_belegt"), 1)
        je_satz = {}
        for h in coach.ein_auftrag_je_satz(L.hinweise):
            for n in {h.get("satz")} | set(h.get("saetze") or []) - {None}:
                je_satz[n] = je_satz.get(n, 0) + 1
        self.assertTrue(all(v == 1 for v in je_satz.values()))


class ErmoeglichtSubjekt(unittest.TestCase):
    def ersatz(self, text, nr):
        L = coach.Lauf(text + "\n\n" + FUELL, None)
        return coach.ermoeglicht_ersatz(L, L.nach_nr[nr])

    def test_dativ_ohne_falsch_gebeugte_form(self):
        t = self.ersatz("Das Verfahren ermöglicht es den Händlern, Preise schnell anzupassen.", 1)
        self.assertNotIn("Händlern können", t)
        self.assertIn("„den Händlern“", t)
        self.assertIn("Nominativ", t)

    def test_akteur_nur_als_subjekt_am_satzanfang(self):
        # Objekt bzw. Genitiv („Merkmale zu den Unternehmen“, ssoar-19287) ist nicht der Handelnde: Passiv, kein neues Subjekt
        t = self.ersatz("Der Datensatz enthält Merkmale zu den Unternehmen. Die Kombination beider Quellen ermöglicht es, die Vergabe "
                        "genauer zu untersuchen.", 2)
        self.assertNotIn("„Unternehmen", t)
        self.assertIn("Passiv", t)
        # Subjekt im Nebensatz („Bevor sich eine Organisation …“, hsmw-3538) zählt ebenfalls nicht
        t = self.ersatz("Bevor sich eine Organisation entscheidet, prüft sie die Kosten. Die Ermittlung der Daten ermöglicht es, die "
                        "Maschinen zu vergleichen.", 2)
        self.assertIn("Passiv", t)
        # Subjekt am Satzanfang: übernehmen, Verb passend zur Zahl
        t = self.ersatz("Das Unternehmen erhält dabei viele Daten. Die erweiterte Suche ermöglicht es, die Treffer zu filtern.", 2)
        self.assertIn("„Das Unternehmen kann so …“", t)
        t = self.ersatz("Händler, die ihre Preise selbst pflegen, verlieren Zeit. Das Verfahren ermöglicht es, Preise anzupassen.", 2)
        self.assertIn("„Händler können so …“", t)


class SynonymNurUeberGrundwort(unittest.TestCase):
    def test_bestimmungswort_ist_kein_synonym(self):
        self.assertIsNone(coach.begriffs_relation("Studien", "Studiengänge", set()))  # hm-103 S3/S4
        self.assertEqual(coach.begriffs_relation("Kunden", "Konsumenten", set())[0], "synonym")
        self.assertEqual(coach.begriffs_relation("Endkunden", "Verbraucher", set())[0], "synonym")  # Grundwort zählt weiter


class RueckbezugNurNah(unittest.TestCase):
    ANK = ("Zusammenfassend lässt sich festhalten, dass die Firma mit diesem Vorgehen neue Wege für den Kontakt mit jungen Leuten "
           "in der ganzen Region und im Ausland findet und dafür auch klar und offen plant.")
    VOR = "Die Leitung der Firma spricht seit dem letzten Jahr offen mit allen Leuten aus der Region über neue Pläne."

    def test_kapitel_aus_der_einleitung_traegt_keine_folgerung(self):
        intro = "In Kapitel 2 werden die rechtlichen Grundlagen der Ausbildung in kleinen Betrieben kurz dargestellt.\n\n"
        c = coach.coache(intro + gleichmaessig(8, 5) + "\n\n" + self.VOR + " " + self.ANK, None, 80, roh=True)
        ank = [h for h in c["hinweise_roh"] if h["typ"] == "fw_ankuendigung"]
        self.assertFalse([h for h in ank if h.get("variante") == "rueckbezug" or "Kapitel 2" in h["text"]])


class BuendelnGegensatzBedingung(unittest.TestCase):
    def test_bedingung_und_gegensatz_in_satz_b(self):
        self.assertTrue(coach.b_eigener_status(OHM_42, OHM_42))  # uneingeleiteter Bedingungssatz mit Beispiel
        self.assertTrue(coach.b_eigener_status(OHM_31, OHM_31))  # „steht jedoch …“: Gegensatz zum Vorsatz
        self.assertTrue(coach.bedingung_verberst("Herrscht dagegen Misstrauen, führt dies eher zu Rückzug."))
        self.assertFalse(coach.bedingung_verberst("Bleibt festzuhalten, dass die Kosten steigen."))
        self.assertFalse(coach.b_eigener_status(OHM_41, OHM_41))  # gewöhnlicher Aussagesatz bleibt bündelbar

    def test_paar_wird_nicht_gebuendelt(self):
        for a, b in ((OHM_41, OHM_42), (OHM_30, OHM_31)):
            L = coach.Lauf(FUELL + "\n\n" + a + " " + b, None)
            sa = next(x for x in L.saetze if x["text"] == a)
            sb = next(x for x in L.saetze if x["text"] == b)
            self.assertEqual(coach.buendel_paar_grund(L, sa, sb, laenge=False), "b_status")


if __name__ == "__main__":
    unittest.main()
