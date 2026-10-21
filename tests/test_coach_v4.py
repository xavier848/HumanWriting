"""Tests für Coach v4 (Wirksamkeit nach der dritten Evaluation): Satzlängen-Simulation am Modell mit harten Grenzen, weites
Bündelfenster und Längenaufbau, Nebensatz-/Klammer-Regeln, Wirkungszuschreibung, Herauslösen, Folgen des Teilens, ehrliche
Diagnose („Grenze des Coaches“ gegen „Grenze des Textes“) und stellenlose Hebel.

Alle Texte sind synthetisch (keine Korpustexte).

python3 -m unittest discover -s tests
"""
import os
import sys
import unittest
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
from test_coach import KI_TEXT, _KURZE_WORTE, satz  # noqa: E402
from test_coach_wirksamkeit import gleichmaessig, mit_metriken  # noqa: E402

W = _KURZE_WORTE
# Themen ohne -ung (sonst liegt der Nominalstil über P90 und der Coach setzt das Verdichten aus)
T = ["Firma", "Region", "Branche", "Messe", "Schule", "Klinik", "Bank", "Kammer"]
B = analyse.lade_baselines()["textsorten"]["hochschule"]
REF = B["metriken"]


def aufbau_text():
    """Keine langen Sätze; je Absatz ein fast langer Satz (26) mit kurzem Folgesatz (6) zum selben Thema, alle übrigen
    Nachbarpaare außerhalb des Bündelfensters (21 + 26 = 47, 6 + 22 = 28, 22 + 25 = 47) – Bündeln findet nichts."""
    teile = []
    for i in range(8):
        teile.append(" ".join([satz(T[(i + 1) % 8], 21, i, W), satz(T[i], 26, i + 3, W), satz(T[i], 6, i + 5, W),
                               satz(T[(i + 3) % 8], 22, i + 7, W), satz(T[(i + 5) % 8], 25, i + 9, W)]))
        teile.append(" ".join([satz(T[(i + 2) % 8], 9, i, W), satz(T[(i + 4) % 8], 10, i + 2, W)]))
    return "\n\n".join(teile)


def lauf_bis_satzlaengen(text, verlauf=None):
    L = coach.Lauf(text, verlauf)
    coach._hebel_priorisieren(L)
    coach._waechter(L)
    coach._wirksamkeit(L)
    coach._satzlaengen(L)
    return L


class SatzlaengenAmModell(unittest.TestCase):
    def test_buendelfenster_und_auftragstext(self):
        text = gleichmaessig(8, 5)
        c = coach.coache(text, None, 40, roh=True)
        b = [h for h in c["hinweise_roh"] if h["typ"] == "buendeln"]
        self.assertTrue(b)
        self.assertLessEqual(len(b), min(c["satzlaengen"]["kontingent"], coach.MAX_BUENDELN))
        laenge = {s["nr"]: s["woerter"] for s in analyse.analysiere_text(text)["saetze"]}
        for h in b:
            a_, b_ = laenge[h["satz"]], laenge[h["weitere_nr"][0]]
            self.assertTrue(a_ >= coach.BUENDEL_MIN_TEIL and b_ >= coach.BUENDEL_MIN_TEIL)
            self.assertTrue(coach.BUENDEL_SUMME[0] <= a_ + b_ <= coach.BUENDEL_SUMME[1])
            self.assertIn("höchstens ~40 Wörtern", h["text"])
            self.assertGreater(h["sim_wert"], 0)  # nur Kandidaten mit positivem Wert der Zielfunktion
            self.assertIn(h.get("variante"), (None, "umgedreht"))  # es gibt Bündelpaare: kein Längenaufbau
            if h.get("variante") == "umgedreht":  # v5: kurzer Satz a vor langem Satz b – a wird einleitende Angabe in b
                S = {x["nr"]: x for x in analyse.analysiere_text(text)["saetze"]}
                self.assertTrue(a_ <= coach.UMKEHR_A_MAX and b_ >= coach.UMKEHR_B_MIN or coach.ankuendigung_a(S[h["satz"]]["text"], a_))
                self.assertIn("einleitende Angabe", h["text"])
        self.assertEqual(coach.buendel_laenge(16, 15), coach.LANG_AB)  # verlangt ≥ 30 Wörter
        self.assertEqual(coach.buendel_laenge(23, 23), round(coach.VERDICHTUNG * 46))

    def test_laengenaufbau_ohne_buendelpaar(self):
        c = coach.coache(aufbau_text(), None, 40, roh=True)
        self.assertEqual(c["satzlaengen"]["modus"], "buendeln")
        self.assertLess(c["satzlaengen"]["anteil_lange"], REF["anteil_lange_saetze"]["mensch"]["p25"])
        auf = [h for h in c["hinweise_roh"] if h["typ"] == "buendeln"]
        self.assertTrue(auf)
        self.assertLessEqual(len(auf), min(c["satzlaengen"]["kontingent"], coach.MAX_BUENDELN))
        for h in auf:
            self.assertEqual(h["variante"], "aufbau")
            self.assertIn("ergänzen und Satz", h["text"])
            self.assertIn("auflösen", h["text"])
            self.assertIn("höchstens ~40 Wörtern", h["text"])
            self.assertGreaterEqual(h["sim"][0], coach.LANG_AB)

    def test_harte_grenzen_nach_allen_laengenauftraegen(self):
        # nach allen Satzlängen-Aufträgen einer Runde: keine Längenkennzahl neu rot oder über P75 auf der Gegenseite
        for text in (gleichmaessig(8, 5), aufbau_text(), KI_TEXT):
            L = lauf_bis_satzlaengen(text)
            lm = L.laengen_modell
            start = lm.werte([s["woerter"] for s in L.fokus])
            ende = lm.werte(coach.laengen_folge(L.sim))
            for k in coach.LAENGEN_KENNZAHLEN:
                if k not in REF:
                    continue
                a0, a1 = coach.band_abstand(start[k], REF[k]), coach.band_abstand(ende[k], REF[k])
                if coach.status_von(start[k], REF[k]) != "rot":
                    self.assertNotEqual(coach.status_von(ende[k], REF[k]), "rot", (k, start[k], ende[k]))
                if coach.seite_von(ende[k], REF[k]) == "gegen" and a1 > 0:
                    self.assertLessEqual(a1, a0 + 1e-9, (k, start[k], ende[k]))

    def test_kein_verlaengern_bei_zu_vielen_langen_saetzen(self):
        ueber = "\n\n".join(" ".join(satz(T[i], n, 3 * i, W) for n in (34, 12, 38, 33, 9, 44)) for i in range(6))
        c = coach.coache(ueber, None, 40, roh=True)
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] in ("buendeln", "klammer_zusatz", "zickzack")])


class NebensatzRegeln(unittest.TestCase):
    def auftrag(self, satz_text):
        L = coach.Lauf(satz_text + "\n\n" + KI_TEXT, None)
        coach._hebel_priorisieren(L)
        coach._waechter(L)
        s = L.saetze[0]
        self.assertEqual(s["text"], satz_text)
        return coach.nebensatz_auftrag(L, s, L.masken[s["nr"]])

    def test_passiv_relativsatz_als_praepositionalgruppe(self):
        self.assertTrue(coach.relativsatz_praep("Die Studie nutzt die Daten", "die in der zweiten Welle der Befragung erhoben wurden"))
        self.assertFalse(coach.relativsatz_praep("Die Studie nutzt die Daten", "die erhoben wurden"))  # keine Angabe darin
        self.assertFalse(coach.relativsatz_praep("Die Studie befragt die Mitarbeiter", "die in der Befragung erfasst wurden"))
        self.assertFalse(coach.relativsatz_praep("Die Studie nutzt die Daten", "die in der Befragung erhoben werden können"))

    def test_relativsatz_bis_neun_woerter(self):
        ok = coach.relativsatz_umbaubar
        self.assertTrue(ok("Die Studie nutzt die Daten", "die in der zweiten Welle erhoben wurden")[0])  # Attribut 5 Wörter
        self.assertFalse(ok("Die Studie nutzt die Daten", "die in der zweiten Welle der Befragung erhoben wurden")[0])  # Attribut 7
        self.assertTrue(coach.relativsatz_praep("Die Studie nutzt die Daten", "die in der zweiten Welle der Befragung erhoben wurden"))

    def test_dass_satz_bis_vierzehn_woerter(self):
        a = self.auftrag("Die Daten der Befragung zeigen, dass die Kosten im zweiten Jahr fast überall sehr deutlich und spürbar steigen.")
        self.assertIsNotNone(a)  # 13 Wörter im dass-Satz, Kette „Anstieg der Kosten im zweiten Jahr“ (drei Nomen)
        self.assertIsNone(self.auftrag("Die Daten der Befragung zeigen, dass die Kosten in den letzten drei oder vier Jahren sehr viel "
                                       "stärker als erwartet gestiegen sind."))  # > 14 Wörter
        # v5: projiziertes Ergebnis „den Anstieg der Kosten im zweiten Jahr der Einführung in kleinen Betrieben“ – Kette aus 5 Nomen
        self.assertIsNone(self.auftrag("Die Daten der Befragung zeigen, dass die Kosten im zweiten Jahr der Einführung in kleinen Betrieben "
                                       "steigen."))

    def test_keine_nominalisierung_bei_koordination_kopula_kette_konjunktiv(self):
        for satz_text in ("Die Teams arbeiten schneller, da die Leitung als Partner und nicht als Kontrolle auftritt.",
                          "Die Teams arbeiten schneller, weil sowohl die Leitung als auch die Kunden mitziehen.",
                          "Die Analyse zeigt, dass sich die Instrumente des Controllings weiterentwickeln.",  # Kette aus drei Nomen
                          "Ein einheitlicher Preis führt dazu, dass ein Teil der Kunden mehr bezahlt hätte.",
                          "Ohne die Reform wäre der Bericht teurer, weil die Daten fehlen."):
            self.assertIsNone(self.auftrag(satz_text), satz_text)
        a = self.auftrag("Entscheidend ist, dass die Betriebe ihre Daten pflegen.")
        self.assertTrue(a is None or "Doppelpunkt" in a[1] and "Nominalgruppe" not in a[1].split("–")[0])

    def test_nominalkette(self):
        self.assertEqual(coach.nominal_kette("dass die Kosten im zweiten Jahr steigen"), 2)
        self.assertGreaterEqual(coach.nominal_kette("dass sich die Instrumente des Controllings weiterentwickeln"), 3)
        self.assertEqual(coach.nominal_kette("weil die Führung mehr Spielraum gewährt"), 2 - 1 + 1)  # Akteur wandert in „durch“

    def test_passivschutz_auf_dem_wert_nach_den_auftraegen(self):
        text = "Die Studie nutzt die Daten, die in der zweiten Welle der Befragung erhoben wurden.\n\n" + KI_TEXT
        L = coach.Lauf(text, None)
        coach._hebel_priorisieren(L)
        coach._waechter(L)
        s = L.saetze[0]
        L.ausgesetzt -= {"nebensatz_relativ", "nebensatz_werden"}  # nur den Passiv-Schutz prüfen (nicht den „werden“-Schutz)
        L.passiv_budget = 0
        self.assertIsNone(coach.nebensatz_auftrag(L, s, L.masken[s["nr"]]))  # Passiv fiele unter P25
        L.passiv_budget = 2
        a = coach.nebensatz_auftrag(L, s, L.masken[s["nr"]])
        self.assertIsNotNone(a)
        self.assertEqual(a[2], 1)  # kostet ein Passiv
        self.assertIn("Präpositionalgruppe", a[1])


class SatzklammerVorfeld(unittest.TestCase):
    def test_vorfeld_angabe(self):
        vf = coach.vorfeld_angabe("In der neueren Literatur wurde dies früh beschrieben.")
        self.assertIsNotNone(vf)
        self.assertEqual(vf[0], "In der neueren Literatur")
        self.assertGreaterEqual(vf[2], 2)
        self.assertIsNone(coach.vorfeld_angabe("Bereits Hackman und Oldham haben darauf hingewiesen."))  # Gradpartikel + Subjekt
        # Klammer schon voll und langes Subjekt: die Umstellung würde sie verkürzen
        self.assertIsNone(coach.vorfeld_angabe("Bereits vor der aktuellen Welle wurde in der Literatur die Entwicklung des Controllers "
                                               "vom reinen Zahlenlieferanten hin zum Partner des Managements beschrieben."))
        self.assertIsNone(coach.vorfeld_angabe("Die Analyse hat gezeigt, dass es sich um einen Wandel handelt."))  # Subjekt vorn

    def test_klammer_auftrag_nur_umstellen(self):
        text = KI_TEXT + "\n\nIn der neueren Literatur wurde dies früh beschrieben und kritisch diskutiert."
        c = coach.coache(text, None, 60, roh=True)
        kl = [h for h in c["hinweise_roh"] if h["typ"] == "klammer" and "vom Satzanfang" in h["text"]]
        for h in kl:
            self.assertIn("nur umstellen, der Inhalt bleibt gleich", h["text"])
            self.assertGreater(h["klammer_zuwachs"], 0)


class Wirkungszuschreibung(unittest.TestCase):
    def test_lokal_wirksames_buendeln_wird_nicht_ausgesetzt(self):
        text = gleichmaessig(8, 5) + "\n\n" + satz(T[0], 34, 1, W)
        lang = analyse.analysiere_text(text)["saetze"][-1]
        h = {"typ": "buendeln", "anfang": coach.schluessel_anfang(lang["text"]), "laenge": 18, "weitere": ["nicht mehr da"],
             "ziel": "anteil_mittlere_saetze", "ziel_wert": 0.10}  # Kennzahl ist „schlechter“ geworden
        L = coach.Lauf(text, {"messungen": [{"hinweise": [h]}]})
        self.assertTrue(coach.lokal_wirksam(L, h))
        coach._wirksamkeit(L)
        self.assertNotIn("buendeln", L.ausgesetzt)

    def test_buendeln_nie_aussetzen_unter_p25(self):
        # befolgter Bündel-Auftrag, dessen Verbundsatz tatsächlich zwei Teilsätze hat; Teilsatz-Verhältnis ist rot geworden
        verbund = next(s for s in analyse.analysiere_text(KI_TEXT)["saetze"] if s["text"].startswith("Darüber hinaus verdeutlicht"))
        befolgt = {"typ": "buendeln", "anfang": coach.schluessel_anfang(verbund["text"]), "laenge": 9, "weitere": ["auch weg"]}
        verlauf = {"messungen": [{"score": 50, "p_mensch": 0.1, "kennzahlen": {}, "roh": {"teilsatz_verhaeltnis_21": 0.6},
                                  "hinweise": [befolgt]}]}
        with mit_metriken(teilsatz_verhaeltnis_21=1.3, anteil_lange_saetze=0.03, nominalstil_pro_100=6.0):
            c = coach.coache(KI_TEXT, verlauf, 40)
        self.assertNotIn("buendeln", c["fortschritt"]["ausgesetzt"])  # lange Sätze unter P25: Bündeln bleibt
        with mit_metriken(teilsatz_verhaeltnis_21=1.3, anteil_lange_saetze=0.12, nominalstil_pro_100=6.0):
            c = coach.coache(KI_TEXT, verlauf, 40)
        self.assertIn("buendeln", c["fortschritt"]["ausgesetzt"])  # befolgt und als Ursache plausibel
        befolgt_unbekannt = dict(befolgt, anfang="satz der nicht mehr da ist")
        verlauf["messungen"][0]["hinweise"] = [befolgt_unbekannt]
        with mit_metriken(teilsatz_verhaeltnis_21=1.3, anteil_lange_saetze=0.12, nominalstil_pro_100=6.0):
            c = coach.coache(KI_TEXT, verlauf, 40)
        self.assertNotIn("buendeln", c["fortschritt"]["ausgesetzt"])  # Verbundsatz nicht nachprüfbar: keine Zuschreibung


class HerausloesenUndTeilen(unittest.TestCase):
    KOMMA = ("Die Firma plant, wie üblich, mit Puffer, mit Reserve, mit Zeit und mit Geld für junge Leute.")

    def test_herausloesen_nur_mit_genug_langen_saetzen(self):
        wenig_lange = gleichmaessig(6, 5) + "\n\n" + " ".join([self.KOMMA] * 3)
        c = coach.coache(wenig_lange, None, 60, roh=True)
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "kommas" and "herauslösen" in h["text"]])
        for h in c["hinweise_roh"]:
            if h["typ"] == "kommas" and "herauslösen" in h["text"]:
                self.assertIn("Bezugsnomen", h["text"])
        self.assertIn("kommas", coach.WAECHTER["anteil_lange_saetze"]["ki"])
        self.assertIn("kommas", coach.WAECHTER["satzlaenge_mittel"]["ki"])
        self.assertIn("kommas", coach.WAECHTER["satzlaenge_dispersion"]["ki"])

    def test_teilen_wiederholt_das_subjekt_als_nomen(self):
        for fuge in ("und", "oder"):
            t = coach.fugen_technik(fuge)
            self.assertIn("als Nomen", t)
            self.assertIn("kein Pronomen", t)
        self.assertIn("kein Pronomen", coach.fugen_technik("die"))

    def test_neu_geteilter_satz_ohne_anknuepfung_und_begriffsaufnahme(self):
        erster = "Die Firma plant neue Wege für junge Leute in der Region."
        zweiter = "Sie braucht dafür mehr Zeit und mehr Geld als bisher geplant."
        text = gleichmaessig(6, 5) + "\n\n" + erster + " " + zweiter + " " + satz(T[2], 18, 3, W)
        h = {"typ": "mitte", "anfang": coach.schluessel_anfang(erster), "laenge": 24}
        c = coach.coache(text, {"messungen": [{"hinweise": [h], "kennzahlen": {}, "roh": {}}]}, 60, roh=True)
        nr = next(s["nr"] for s in analyse.analysiere_text(text)["saetze"] if s["text"] == zweiter)
        am = [x for x in c["hinweise_roh"] if x["satz"] == nr and x["typ"] in ("anknuepfung", "kein_bezug")]
        self.assertFalse([x for x in am if x["typ"] == "kein_bezug"])
        for x in am:
            self.assertIn("Folge des Teilens", x["text"])


class DiagnoseGrenzen(unittest.TestCase):
    def lauf(self, beitraege, hinweise=(), fw_potenzial=0.0, p=0.3):
        return SimpleNamespace(bew={"verfuegbar": True, "p_mensch": p, "modell_beitraege": beitraege}, messungen=[],
                               ts={"modell": B["modell"]}, fw_potenzial=fw_potenzial, fw_diag=None, hinweise=list(hinweise))

    def test_grenze_des_coaches_mit_selbsthilfe(self):
        L = self.lauf([{"id": "satzklammer_mittel", "name": "Satzklammer", "beitrag": -1.1},
                       {"id": "satzlaenge_dispersion", "name": "Dispersion", "beitrag": -0.9},
                       {"id": "anteil_mittlere_saetze", "name": "mittellange Sätze", "beitrag": -0.8}], p=0.6)
        d = coach._diagnose(L, [], 0.86)
        self.assertEqual(d["grenze"], "coach")
        self.assertEqual(d["erreichbar_logit"], 0.0)
        self.assertGreater(d["stellenlos_logit"], d["luecke_logit"])
        txt = "\n".join(coach.diagnose_text(d))
        self.assertIn("Mit den Aufträgen dieser Runde reicht es nicht", txt)
        self.assertIn("Grenze des Coaches", txt)
        self.assertIn("zwischen Hilfsverb und Partizip", txt)  # Selbsthilfe-Technik
        self.assertNotIn("in eigenen Worten neu zu schreiben", txt)

    def test_funktionswort_dominant_nur_wenn_es_wirklich_blockiert(self):
        dominant = self.lauf([{"id": "fw_profil_llr_pro_1000", "name": "FW", "beitrag": -6.1},
                              {"id": "satzklammer_mittel", "name": "Satzklammer", "beitrag": -0.3}], p=0.1)
        d = coach._diagnose(dominant, [], 0.86)
        self.assertTrue(d["fw_dominant"])
        self.assertEqual(d["grenze"], "einzelkorrekturen")  # v5: „Grenze der Einzelkorrekturen“ (früher „Grenze des Textes“)
        fw = next(z for z in d["beitraege"] if z["id"] == "fw_profil_llr_pro_1000")
        self.assertGreater(fw["potenzial_logit"], 0)  # Erfahrungswert statt fest 0
        self.assertLessEqual(fw["potenzial_logit"], coach.FW_RICHTWERT_LOGIT + 1e-9)
        self.assertIn("in eigenen Worten neu zu schreiben", "\n".join(coach.diagnose_text(d)))
        # FW groß, aber die übrigen (auch stellenlosen) Merkmale decken die Lücke: kein „Absätze neu schreiben“
        gedeckt = self.lauf([{"id": "fw_profil_llr_pro_1000", "name": "FW", "beitrag": -2.9},
                             {"id": "anteil_mittlere_saetze", "name": "mittellange Sätze", "beitrag": -1.0},
                             {"id": "satzlaenge_dispersion", "name": "Dispersion", "beitrag": -1.0}], p=0.5)
        d = coach._diagnose(gedeckt, [], 0.86)
        self.assertFalse(d["fw_dominant"])
        self.assertIsNone(d["fw_text"])


class BerichtUndVerlauf(unittest.TestCase):
    def test_stellenlose_hebel_nur_zur_orientierung(self):
        c = coach.coache(KI_TEXT, None, 40)
        stellenlos = [h for h in c["hebel"] if h.get("stellenlos")]
        txt = coach.bericht(c)
        if any(h in c["hebel"][:6] for h in stellenlos):
            self.assertIn("Keine sichere Stelle – zur Orientierung", txt)
        mit = {h["hebel"] for h in c["hinweise"]}
        for h in c["hebel"]:
            if h.get("stellenlos"):
                self.assertNotIn(h["id"], mit)
                self.assertTrue(h.get("selbsthilfe") or h["id"] not in coach.SELBSTHILFE_HEBEL)

    def test_json_modus_ausgesetzt(self):
        L = coach.Lauf(gleichmaessig(8, 5), None)
        coach._hebel_priorisieren(L)
        L.setze_aus({"buendeln"}, "Test")
        coach._satzlaengen(L)
        c = coach._ergebnis(L, 15, False)
        self.assertEqual(c["satzlaengen"]["modus"], "buendeln")
        self.assertEqual(c["stand"]["satzlaengen_modus"], "ausgesetzt")
        self.assertEqual(len(c["stand"]["laengen"]), len(L.fokus))  # Längenfolge für die Wirkungsprüfung der Folgerunde

    def test_diagnose_kurz_bei_unveraendertem_text(self):
        c1 = coach.coache(KI_TEXT, None, 2)
        self.assertIsNotNone(c1["diagnose"])
        self.assertEqual(c1["stand"]["diagnose_kurz"]["grenze"], c1["diagnose"]["grenze"])
        c2 = coach.coache(KI_TEXT, {"messungen": [c1["stand"]]}, 2)
        self.assertIsNone(c2["diagnose"])
        txt = coach.bericht(c2)
        self.assertIn("Diagnose wie in Messung 1", txt)
        self.assertNotIn("Warum das Modellziel noch fehlt", txt)

    def test_kein_laenge_halten_bei_kuerzung_ins_mittelband(self):
        # v5: kein „Länge halten“ mehr (nach der Kürzung nur durch Auffüllen erfüllbar); ohne Rückbezug im Text entscheidet die
        # Simulation – bleibt der Auftrag, steht die geschätzte Kürzung für die Wirkungsprüfung im Hinweis
        ank = ("Zusammenfassend lässt sich festhalten, dass die Firma mit diesem Vorgehen neue Wege für den Kontakt mit jungen Leuten "
               "in der ganzen Region findet und dafür auch klar plant.")
        self.assertTrue(coach.MITTEL_BIS < len(ank.split()) < coach.LANG_AB)
        c = coach.coache(gleichmaessig(8, 5) + "\n\n" + ank, None, 80, roh=True)
        self.assertFalse([x for x in c["hinweise_roh"] if "Länge halten" in x["text"]])
        h = next((x for x in c["hinweise_roh"] if x["typ"] == "fw_ankuendigung"), None)
        if h is not None:
            self.assertLessEqual(h["sim"][0], coach.MITTEL_BIS)


if __name__ == "__main__":
    unittest.main()
