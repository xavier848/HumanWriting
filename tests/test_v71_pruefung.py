"""Regressionstests der adversarialen v7.1-Prüfung (Coach und Inhaltscheck nach A1, A2 und B).

1. Gender-Rückfrage nur bei durchgehendem Gendern: Ein einzelnes Genderzeichen („Rezipient*innen“ einmal) oder drei Partizipien
   in einem Text, der sonst das generische Maskulinum nutzt („die Forscher“, „den Teilnehmern“), hießen „Der Text gendert
   durchgehend“ – die Einzelaufträge entfielen. „Master-“, „Bachelor-“ und „Studierende“ zählten als drei Stämme.
2. Die ausdrückliche Wahl (--vorgaben) gilt mit --verlauf für die weiteren Runden; vorher kam die Rückfrage jede Runde wieder.
3. „Die Aufträge reichen rechnerisch“ gilt nur dem Modell: Fehlen dem Score Punkte, sagt der Bericht das (Claude-Text
   ssoar-38197: „reichen rechnerisch“ bei Score (KI-Seite) 59 von 74).
4. Inhaltscheck: ein “…“-Zitat mit einem nie geschlossenen « darin blieb ganz ungeprüft (kn-47466), vorher erkannt.
5. Claudes Entwürfe misst menschlich-schreiben mit --vorgaben gender,gedankenstrich (sonst Rückfrage statt Stellen).
"""
import os
import re
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coach  # noqa: E402
import inhalt_check  # noqa: E402
from test_coach import KI_TEXT  # noqa: E402
from test_coach_v7 import FUELL, bewertung_setzen  # noqa: E402
from test_coach_v71_bericht import GENDER_TEXT, netto_nur_ein_auftrag, p_fuer_luecke  # noqa: E402

SKILLS = os.path.join(REPO, "plugins", "humanwriting-de", "skills")

# eigener Text im generischen Maskulinum (Studenten, Dozenten, Teilnehmer, Forscher, Experten, Schüler)
MASKULIN = ("Die vorliegende Arbeit untersucht, wie Hochschulen den Übergang in das Studium gestalten. Viele Erstsemester berichten "
            "von Unsicherheiten bei der Wahl der Kurse. Die Studenten nennen vor allem fehlende Informationen über den Ablauf. Die "
            "Dozenten sehen das Problem eher bei der Vorbereitung in der Schule. Die Befragten waren zwischen 19 und 24 Jahre alt. "
            "Die Beschäftigten der Studienberatung bestätigen diesen Eindruck aus ihrer täglichen Arbeit. Auch die Teilnehmer der "
            "Orientierungswoche äußerten ähnliche Sorgen. Es zeigt sich, dass die Informationslage vor Studienbeginn entscheidend "
            "ist. Die Forscher der Studie empfehlen deshalb mehr Beratung vor dem ersten Semester. Die Experten betonen außerdem "
            "die Rolle der Eltern. Viele Schüler wissen wenig über die Anforderungen im Studium.\n\n")
ZUSATZ = "Danach entscheiden sich die meisten für ein Fach und beginnen im Herbst mit dem Studium.\n"


def gender_auftraege(c):
    return [h for h in c["vorgaben"] if h["typ"] == "gender"]


class GenderRueckfrageNurDurchgehend(unittest.TestCase):
    def test_einzelnes_genderzeichen_neben_maskulinum(self):
        for form in ("Mitarbeiter*innen", "MitarbeiterInnen", "Mitarbeiter:innen", "Mitarbeiter(innen)"):
            text = MASKULIN + f"Die {form} der Beratung führen jedes Jahr etwa 300 Gespräche mit Interessenten durch. " + ZUSATZ
            c = coach.coache(text, None, 15)
            self.assertIsNone(c["gender_durchgehend"], form)
            self.assertEqual(len(gender_auftraege(c)), 1, form)  # die eine Form als Einzelauftrag
            self.assertNotIn("gendert durchgehend", coach.bericht(c))

    def test_drei_partizipien_in_gemischtem_text(self):
        text = (MASKULIN.replace("Die Studenten", "Die Studierenden").replace("Die Dozenten", "Die Lehrenden")
                .replace("die Teilnehmer", "die Teilnehmenden"))
        c = coach.coache(text, None, 15)
        self.assertIsNone(c["gender_durchgehend"])  # Forscher, Experten, Schüler: der Text mischt
        self.assertEqual(len(gender_auftraege(c)), 3)

    def test_studierende_komposita_sind_ein_stamm(self):
        text = ("Die Bachelorstudierenden wählen ihre Kurse meist in der ersten Woche des Semesters aus. Die Masterstudierenden "
                "haben dagegen feste Module und kaum Wahlfreiheit im ersten Jahr. Alle Studierenden können die Beratung der "
                "Fakultät nutzen, wenn sie unsicher sind.\n\n" + FUELL)
        c = coach.coache(text, None, 15)
        self.assertIsNone(c["gender_durchgehend"])
        self.assertTrue(gender_auftraege(c))
        self.assertEqual(coach.gender_basis("bachelorstudent"), "student")
        self.assertEqual(coach.gender_basis("diskussionsteilnehmer"), "teilnehmer")
        self.assertEqual(coach.gender_basis("xyzabc"), "xyzabc")

    def test_beschaeftigte_und_befragte_zaehlen_nicht(self):
        text = ("Die Studierenden und die Lehrenden der Fakultät wurden im Frühjahr getrennt befragt. Die Befragten nannten vor "
                "allem die Raumplanung. Die Beschäftigten der Verwaltung und die Angestellten der Bibliothek sahen das ähnlich, "
                "die Vorgesetzten eher nicht.\n\n" + FUELL)
        c = coach.coache(text, None, 15)
        self.assertIsNone(c["gender_durchgehend"])  # nur zwei gendergerechte Stämme
        self.assertEqual({h["fund"] for h in gender_auftraege(c)}, {"Studierenden", "Lehrenden"})

    def test_durchgehend_gendernd_bleibt_rueckfrage(self):
        self.assertTrue(coach.coache(GENDER_TEXT, None, 15)["gender_durchgehend"])
        text = ("Die Mitarbeiter*innen der Verwaltung beantworten Fragen zur Anmeldung schnell. Auch die Kund*innen der Mensa "
                "loben den Service seit dem letzten Semester ausdrücklich. Die Student*innen nutzen die Bibliothek vor allem am "
                "Abend.\n\n" + FUELL)
        c = coach.coache(text, None, 15)
        self.assertTrue(c["gender_durchgehend"])
        self.assertEqual(c["gender_durchgehend"]["zeichen"], 3)

    def test_genderzeichen_nur_im_zitat(self):
        text = (MASKULIN + "Eine Beraterin sagt: „Die Mitarbeiter*innen und Student*innen brauchen mehr Zeit für die Gespräche“ "
                "(Müller 2020, S. 4). " + ZUSATZ)
        c = coach.coache(text, None, 15)
        self.assertIsNone(c["gender_durchgehend"])
        self.assertFalse(gender_auftraege(c))

    def test_maskulin_erkennung(self):
        def treffer(t):
            return [m.group(0) for m in coach.MASKULIN_PERSON_RE.finditer(t)]
        self.assertEqual(treffer("Die Forscher der Studie"), ["Die Forscher"])
        self.assertEqual(treffer("viele junge Lehrer"), ["viele junge Lehrer"])
        self.assertEqual(treffer("mit den Teilnehmern"), ["Teilnehmern"])
        self.assertEqual(treffer("die Bachelorstudenten"), ["Bachelorstudenten"])
        for t in ("der Lehrer", "Lehrer*innen", "Studenten/-innen", "Lehrer(innen)", "die Lehrerin", "Lehrerzimmer",
                  "Expertenwissen", "die Autoren der Studie"):
            self.assertEqual(treffer(t), [], t)


class VorgabenImVerlauf(unittest.TestCase):
    def test_wahl_gilt_fuer_weitere_runden(self):
        c1 = coach.coache(GENDER_TEXT, None, 15, vorgaben="gedankenstrich")
        self.assertEqual(c1["stand"]["vorgaben"], ["gedankenstrich"])
        c2 = coach.coache(GENDER_TEXT, {"messungen": [c1["stand"]]}, 15)
        self.assertIsNone(c2["gender_durchgehend"])  # keine erneute Rückfrage
        self.assertFalse(gender_auftraege(c2))
        self.assertEqual(c2["vorgaben_aktiv"], ["gedankenstrich"])
        self.assertEqual(c2["stand"]["vorgaben"], ["gedankenstrich"])  # weitergetragen
        c3 = coach.coache(GENDER_TEXT, {"messungen": [c1["stand"], c2["stand"]]}, 15, vorgaben="gender,gedankenstrich")
        self.assertEqual(len(gender_auftraege(c3)), 3)  # ausdrücklich neu gewählt: gilt sofort

    def test_keine_vorgaben_bleibt_gespeichert(self):
        c1 = coach.coache(GENDER_TEXT, None, 15, vorgaben="keine")
        self.assertEqual(c1["stand"]["vorgaben"], [])
        c2 = coach.coache(GENDER_TEXT, {"messungen": [c1["stand"]]}, 15)
        self.assertEqual(c2["vorgaben_aktiv"], [])
        self.assertIsNone(c2["gender_durchgehend"])

    def test_standard_speichert_keine_wahl(self):
        c1 = coach.coache(GENDER_TEXT, None, 15)
        self.assertIsNone(c1["stand"]["vorgaben"])
        self.assertTrue(coach.coache(GENDER_TEXT, {"messungen": [c1["stand"]]}, 15)["gender_durchgehend"])
        self.assertIn("Mit `--verlauf` gilt die Wahl auch für die weiteren Messungen.", coach.bericht(c1))

    def test_unbrauchbarer_eintrag(self):
        c1 = coach.coache(GENDER_TEXT, None, 15)
        stand = dict(c1["stand"], vorgaben=["unsinn"])
        c2 = coach.coache(GENDER_TEXT, {"messungen": [stand]}, 15)
        self.assertTrue(c2["gender_durchgehend"])  # Standard mit Rückfrage, kein Absturz


class ReichtNurFuersModell(unittest.TestCase):
    def test_score_luecke_wird_genannt(self):
        with bewertung_setzen(score=60, score_ki=60, p_mensch=round(p_fuer_luecke(0.25), 4)), netto_nur_ein_auftrag(0.30):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertTrue(c["auftragsgrenze"]["reicht"])
        b = coach.bericht(c)
        zeile = next(z for z in b.splitlines() if "rechnerisch" in z)
        self.assertIn("Der Auftrag reicht rechnerisch für das Modellziel", zeile)
        self.assertRegex(zeile, r"Dem Score \(KI-Seite\) fehlen noch \d+ Punkte bis \d+")
        self.assertIn("nicht vorab gerechnet", zeile)

    def test_ohne_score_luecke_unveraendert(self):
        with bewertung_setzen(score=95, score_ki=95, p_mensch=round(p_fuer_luecke(0.25), 4)), netto_nur_ein_auftrag(0.30):
            c = coach.coache(KI_TEXT, None, 15)
        zeile = next(z for z in coach.bericht(c).splitlines() if "rechnerisch" in z)
        self.assertIn("Der Auftrag reicht rechnerisch (vorab gerechnet", zeile)
        self.assertIn("; danach neu messen. Falls dann noch etwas fehlt, folgt die Diagnose.", zeile)
        self.assertNotIn("fehlen noch", zeile)


class KonnektorOhneWirkungGrund(unittest.TestCase):
    # „die Dichte bliebe auffällig“ nur, wenn die verworfenen Streichungen die Dichte nicht unter P90 brächten
    def lauf(self, wert, n):
        from collections import Counter
        from types import SimpleNamespace
        return SimpleNamespace(kz={"konnektoren_pro_1000": {"wert": wert, "mensch_p90": 11.39}}, tok_fokus=800,
                               ohne_wirkung_typen=Counter({"konnektor": n}))

    def test_dichte_bliebe_auffaellig(self):
        self.assertEqual(coach.konnektor_ohne_wirkung_grund(self.lauf(17.05, 3)), "die Dichte bliebe auffällig")  # hslb3: 13,3

    def test_dichte_saenke_ins_band(self):
        grund = coach.konnektor_ohne_wirkung_grund(self.lauf(12.0, 1))  # 12,0 → 10,75
        self.assertNotIn("auffällig", grund)
        self.assertIn("Konnektoren zählen im Modell nicht", grund)


class InhaltZitatMitOffenemGuillemet(unittest.TestCase):
    # kn-47466 (Korpus): “…“ (Autokorrektur) mit einem nie geschlossenen « darin – das offene « verschluckte das Schlusszeichen,
    # das ganze Zitat blieb ungeprüft (vor v7.1 erkannt)
    ALT = ("Der Autor fasst zusammen: “Ein didaktisch gut konzipierter Vorkurs als Online-Kurs ist ein sinnvolles Angebot, ein "
           "digitales Kolloquium eher nicht. Denn natürlich wird Technik niemals die persönliche Bindung ersetzen, sie kann aber "
           "durchaus Entlastung schaffen« (Dräger 2014).“\n\nDanach folgt ein eigener Absatz über die Lehre an der Hochschule.")

    def test_zitat_erkannt_und_verfaelschung_gemeldet(self):
        self.assertTrue(any("sinnvolles Angebot" in z["wert"] for z in inhalt_check.zitat_funde(self.ALT)))
        res = inhalt_check.pruefe(self.ALT, self.ALT.replace("sinnvolles Angebot", "gutes Angebot"))
        self.assertEqual([x["typ"] for x in res["harte_verluste"]], ["Wörtliches Zitat"])

    def test_eigener_text_kein_fund(self):
        res = inhalt_check.pruefe(self.ALT, self.ALT.replace("Danach folgt ein eigener Absatz", "Es folgt ein eigener Absatz"))
        self.assertEqual(res["harte_verluste"], [])
        self.assertEqual(res["erfindungen"], [])


class SkillsMitVorgaben(unittest.TestCase):
    def lies(self, name):
        with open(os.path.join(SKILLS, name, "SKILL.md"), encoding="utf-8") as f:
            return f.read()

    def test_menschlich_schreiben_misst_mit_vorgaben(self):
        aufrufe = [z for z in self.lies("menschlich-schreiben").splitlines() if re.search(r"coach\.py\"? DATEI", z)]
        self.assertTrue(aufrufe)
        self.assertTrue(all("--vorgaben gender,gedankenstrich" in z for z in aufrufe))

    def test_humanisieren_ueberarbeiten_und_rueckfrage(self):
        text = self.lies("humanisieren")
        self.assertIn("coach.py <name>.md --verlauf <name>.coach.json --vorgaben gender,gedankenstrich", text)
        self.assertIn("Gendert der Text durchgehend, fragt der Coach einmal nach", text)


if __name__ == "__main__":
    unittest.main()
