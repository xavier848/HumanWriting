"""Tests für Coach v5 (Präzision und Ehrlichkeit nach der vierten Evaluation): ehrliche Diagnose („Grenze des Coaches“, „knapp“,
„Grenze der Einzelkorrekturen“, Selbsthilfe aus dem Text), längenneutrale Varianten statt „Länge halten“, Bündeln (Richtung,
Folgerungen, Modalverben, Nominalstil), Komma-Aufträge mit Teilsatz-Simulation, Nebensatz mit Kopula und projizierter Kette,
Begriffsaufnahme ohne Fachbegriff-Ersatz, Absatzteilung an rhetorischen Bindungen, Gegenfolie, Abkürzungsfamilien,
Floskel-Ersatz ohne neuen Inhalt, Kopfzeile/Wächter, Konnektoren über P90.

Synthetische Texte; als Regressionstests zusätzlich einzelne Sätze aus der v4-Kritik (ssoar-21977 S15/S16, HAW S32/S33,
haw-7747 S36), wie dort zitiert.

python3 -m unittest discover -s tests
"""
import os
import re
import sys
import unittest
import unittest.mock
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
from test_coach import KI_TEXT  # noqa: E402
from test_coach_v4_praezision import ALS_TEXT  # noqa: E402
from test_coach_wirksamkeit import gleichmaessig, mit_metriken  # noqa: E402

B = analyse.lade_baselines()["textsorten"]["hochschule"]
FUELL = gleichmaessig(6, 5)

# Sätze aus der v4-Kritik (Regression)
SSOAR_15 = "Diese werden aufgrund ihrer langwierigen und komplexen Reproduktionszeiten absolut knapp."
SSOAR_16 = ("Mit der Aufnahme des Reproduktionsgedankens verbindet Nachhaltigkeit den gegenwärtigen Produktions- und Konsumprozess mit den "
            "nachfolgenden, wie Abbildung 5 zu verdeutlichen sucht, und führt damit die Dimension Zeit wieder in die wirtschaftliche "
            "Vernunft ein.")
HAW_32 = "Die oberen Anreißer werden noch sehr häufig betrachtet, Dinge die weiter unten rechts stehen, werden weniger häufig beachtet."
HAW_33 = "Bei beiden Arten von Webseiten ergibt sich also ein Betrachtungsmuster, das einem großen F gleicht."
HAW7747_36 = ("Auf gesonderte Nachfrage wurde versichert, dass keine weiteren, die Messung der EDA beeinflussenden, Symptome bestanden, "
              "insbesondere keine Symptome die Haut betreffend.")


def lauf(text):
    L = coach.Lauf(text, None)
    coach._hebel_priorisieren(L)
    coach._waechter(L)
    return L


def satz_nr(text, anfang):
    return next(s["nr"] for s in analyse.analysiere_text(text)["saetze"] if s["text"].startswith(anfang))


class DiagnoseEhrlich(unittest.TestCase):
    def ns(self, beitraege, p, raum=None, messungen=(), hinweise=()):
        return SimpleNamespace(bew={"verfuegbar": True, "p_mensch": p, "modell_beitraege": beitraege}, messungen=list(messungen),
                               ts={"modell": B["modell"]}, fw_potenzial=0.0, fw_diag=None, hinweise=list(hinweise), _buendel_raum=raum)

    def test_kein_raum_zaehlt_als_ohne_auftrag(self):
        # Controlling-Endstand aus v4 (p 0,639): Dispersion, sehr lange und mittellange Sätze ohne Spielraum im Bündelfenster.
        # v7 (v6-Prüfung): der gesperrte Rest steht als eigene Summe („gesperrt“), zählt nicht für die Einstufung, und die drei
        # Längenmerkmale bilden einen Block (größtes Potenzial + 0,3 · übrige)
        b = [{"id": "fw_profil_llr_pro_1000", "name": "FW", "beitrag": -1.15}, {"id": "nachbarsatz_ueberlappung", "name": "NS", "beitrag": -0.95},
             {"id": "mattr_100", "name": "MATTR", "beitrag": -0.76}, {"id": "satzklammer_mittel", "name": "Klammer", "beitrag": -0.63},
             {"id": "satzlaenge_dispersion", "name": "Dispersion", "beitrag": -0.45},
             {"id": "anteil_sehr_lange_saetze", "name": "sehr lang", "beitrag": -0.25},
             {"id": "anteil_mittlere_saetze", "name": "mittel", "beitrag": -0.17}, {"id": "saetze_pro_absatz_cv", "name": "Absatz", "beitrag": -0.09}]
        d = coach._diagnose(self.ns(b, 0.639, raum=0), [], 0.86)
        z = {x["id"]: x for x in d["beitraege"]}
        self.assertNotIn("satzlaenge_dispersion", z)
        blk = z["laengenblock"]
        self.assertEqual(sorted(blk["glieder"]), ["anteil_mittlere_saetze", "anteil_sehr_lange_saetze", "satzlaenge_dispersion"])
        self.assertEqual(blk["wie"], "kein_raum")
        self.assertAlmostEqual(blk["potenzial_logit"], round(0.45 + 0.3 * (0.125 + 0.17), 2), places=2)
        self.assertIsNone(blk["selbsthilfe"])  # keine Selbsthilfe „bündeln“ gegen die Satzlängen-Vorgabe
        self.assertAlmostEqual(d["gesperrt_logit"], blk["rest_logit"], places=2)
        # Einstufung ohne den gesperrten Teil: ohne Auftrag 1,22 von 1,24 → knapp (v6 zählte die gesperrten 0,54 mit: „Grenze
        # des Coaches“)
        self.assertEqual(d["grenze"], "knapp")
        self.assertAlmostEqual(d["stellenlos_logit"], 1.22, places=2)
        txt = "\n".join(coach.diagnose_text(d))
        self.assertIn("gesperrt ≈", txt)
        self.assertIn("eine Grenze des Coaches, zählt nicht mit", txt)
        self.assertNotIn("Grenze des Textes", txt)
        self.assertNotIn("zwei zusammengehörige mittellange Sätze", txt)

    def test_knapp_und_grenze_der_einzelkorrekturen(self):
        b = [{"id": "satzklammer_mittel", "name": "Klammer", "beitrag": -1.0}, {"id": "nachbarsatz_ueberlappung", "name": "NS", "beitrag": -1.0}]
        luecke = coach._logit(0.86) - coach._logit(0.45)  # ≈ 2,02; erreichbar ohne Auftrag 0,5 + 0,5 = 1,0
        d = coach._diagnose(self.ns(b, 0.45), [], 0.86)
        self.assertLess(d["stellenlos_logit"], coach.KNAPP_ANTEIL * luecke)
        self.assertEqual(d["grenze"], "einzelkorrekturen")
        txt = "\n".join(coach.diagnose_text(d))
        self.assertIn("Grenze der Einzelkorrekturen", txt)
        self.assertNotIn("Grenze des Textes", txt)
        d = coach._diagnose(self.ns(b, 0.62), [], 0.86)  # Lücke ≈ 1,33: 1,0 liegt bei 75 %
        self.assertEqual(d["grenze"], "knapp")
        self.assertIn("Knapp – Schätzung unsicher", "\n".join(coach.diagnose_text(d)))
        self.assertIn("Grenze der Einzelkorrekturen", coach.GRENZE_NAME["text"])  # alte Verläufe

    def test_keine_diagnose_direkt_nach_runde_1_mit_anstieg(self):
        echt = coach.analyse.analysiere_und_bewerte

        def fake(*a, **k):
            erg, bew = echt(*a, **k)
            return erg, dict(bew, p_mensch=0.40)
        c0 = coach.coache(KI_TEXT, None, 2)
        text = KI_TEXT.replace("die Ressourcen fehlen oft", "die Ressourcen fehlen häufig")
        with unittest.mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake):
            # v7 (v6-Prüfung): Aufschub nur, wenn die offenen Aufträge (simuliert) samt den Potenzialen ohne Auftrag ≥ 0,7 der
            # Lücke decken – bei p 0,40 (Lücke ≈ 2,2) reichen zwei kleine Aufträge nicht: Diagnose sofort, „vorläufig“
            c = coach.coache(text, {"messungen": [dict(c0["stand"], p_mensch=0.25)]}, 2)  # +0,15 in dieser Runde
            self.assertIsNotNone(c["diagnose"])
            self.assertTrue(c["diagnose"]["vorlaeufig"])
            self.assertIn("(vorläufig)", coach.bericht(c))
            c = coach.coache(text, {"messungen": [dict(c0["stand"], p_mensch=0.36)]}, 2)  # kaum gestiegen: Diagnose
            self.assertIsNotNone(c["diagnose"])
            c = coach.coache(text, {"messungen": [dict(c0["stand"], p_mensch=0.25), dict(c0["stand"], p_mensch=0.25)]}, 2)
            self.assertIsNotNone(c["diagnose"])  # nur direkt nach Runde 1

        # der Aufschub selbst (offene Aufträge decken die Lücke) ist in test_coach_v7_praezision.DiagnoseAufschub geprüft

    def test_funktionswort_selbsthilfe_aus_der_stellenliste(self):
        L = lauf(ALS_TEXT)
        offen = coach.fw_offen(L)
        self.assertIn("S7", coach.fw_selbsthilfe(offen))  # „dient als“ in Satz 7 steht im Text
        ohne = lauf(ALS_TEXT.replace("Der Bericht dient als Grundlage", "Der Bericht ist die Grundlage").replace(
            "Die Beratung gilt als teuer", "Die Beratung kostet viel Geld"))
        self.assertEqual(coach.fw_offen(ohne), {})
        self.assertEqual(coach.fw_selbsthilfe({}), coach.FW_KEINE_KONSTRUKTION)
        # Orientierung und Diagnose widersprechen sich nicht: beide aus derselben Stellenliste
        self.assertIn("keine umbaubare Konstruktion mehr", coach._fw_hebeltext(ohne, False))
        self.assertNotIn("„lässt sich“", coach.fw_selbsthilfe(coach.fw_offen(ohne)))

    def test_funktionswort_richtwert_nur_bei_dominanz_ohne_konstruktion(self):
        L = lauf(KI_TEXT)
        L.hinweise = []
        L.fw_potenzial = 0.0
        L.messungen = [{"p_mensch": 0.0}, {"p_mensch": L.bew["p_mensch"]}]  # Stagnation
        L.fw_diag = dict(L.fw_diag, woerter=[dict(r, zu_viel=False) for r in L.fw_diag["woerter"]])  # nichts übernutzt
        self.assertEqual(coach.fw_offen(L), {})
        d = coach._diagnose(L, [], 0.86)
        fw = next((z for z in d["beitraege"] if z["id"] == "fw_profil_llr_pro_1000"), None)
        if fw and not d["fw_dominant"]:
            self.assertEqual(fw["wie"], "keine_konstruktion")
            self.assertEqual(fw["rest_logit"], 0.0)
        elif fw:
            self.assertEqual(fw["selbsthilfe"] or coach.FW_KEINE_KONSTRUKTION, coach.FW_KEINE_KONSTRUKTION)

    def test_abkuerzungen_nur_mit_langform(self):
        L = lauf(FUELL)  # keine einzige ausgeschriebene Abkürzung
        self.assertEqual(coach.abk_plan(L)[0], [])
        self.assertIsNone(coach.abk_selbsthilfe(L))
        self.assertEqual(coach.abkuerzung_potenzial(L) or 0.0, 0.0)
        mit = lauf(gleichmaessig(10, 5) + "\n\nDie Firma nutzt beispielsweise neue Wege für den Kontakt mit jungen Leuten in der "
                   "ganzen Region.")  # ~900 Wörter: bis zum Median fehlt eine Abkürzung
        self.assertIn("„beispielsweise“", coach.abk_selbsthilfe(mit) or "")
        self.assertNotIn("verwenden", coach.SELBSTHILFE["abkuerzungen_pro_1000"])  # nie zum Einstreuen auffordern
        self.assertNotIn("verwenden", coach.SELBSTHILFE_HEBEL["abkuerzungen"])

    def test_ki_muster_im_gruenen_band_mit_stelle(self):
        text = FUELL + "\n\nFür den Kontakt mit jungen Leuten in der ganzen Region kommt der Firma dabei eine zentrale Rolle zu."
        with mit_metriken(ki_muster_pro_1000=2.6):  # grün, aber über dem menschlichen Median
            L = lauf(text)
        rest, pot = coach.muster_rest(L)
        self.assertTrue(rest)
        self.assertGreater(pot, 0)
        self.assertIn("S", coach.muster_selbsthilfe(rest))
        self.assertTrue(any("Rolle" in f for _n, f, _g in rest))


class LaengeNeutral(unittest.TestCase):
    ANK = ("Zusammenfassend lässt sich festhalten, dass die Firma mit diesem Vorgehen neue Wege für den Kontakt mit jungen Leuten "
           "in der ganzen Region und im Ausland findet und dafür auch klar und offen plant.")
    SOWOHL = ("Unternehmen, die diesen Wandel aktiv gestalten, investieren sowohl in ihre Datenqualität und die Systeme als auch in die "
              "Kompetenzen ihrer Beschäftigten und in neue Formen der guten Zusammenarbeit im ganzen Team.")

    def test_einziger_langer_satz_im_absatz_kein_kuerzender_auftrag(self):
        c = coach.coache(gleichmaessig(8, 5) + "\n\n" + self.ANK, None, 80, roh=True)
        self.assertFalse([h for h in c["hinweise_roh"] if "Länge halten" in h["text"]])
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "fw_ankuendigung"])
        self.assertEqual(c["unterdrueckt"].get("kuerzung_einziger_langer"), 1)
        with mit_metriken(ki_muster_pro_1000=8.0):
            c = coach.coache(gleichmaessig(8, 5) + "\n\nDie Firma plant neue Wege für den Kontakt mit jungen Leuten. " + self.SOWOHL,
                             None, 80, roh=True)
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "floskel" and "sowohl" in h["text"]])

    def test_rueckbezug_auf_vorhandenes(self):
        vor = "Die Ergebnisse der Befragung in Kapitel 3 zeigen deutliche Unterschiede zwischen den Standorten der Firma."
        c = coach.coache(gleichmaessig(8, 5) + "\n\n" + vor + " " + self.ANK, None, 80, roh=True)
        h = next(x for x in c["hinweise_roh"] if x["typ"] == "fw_ankuendigung")
        self.assertEqual(h["variante"], "rueckbezug")
        self.assertIn("„Kapitel 3“", h["text"])
        self.assertIn("längenneutral", h["text"])
        self.assertNotIn("Länge halten", h["text"])
        self.assertEqual(h["sim"], h["laengen_alt"])  # längenneutral: keine Kürzung

    def test_zweiter_langer_satz_simulation_entscheidet(self):
        lang2 = ("Die Firma plant dazu neue Wege für den Kontakt mit jungen Leuten in der ganzen Region und im Ausland und nutzt dafür "
                 "auch mehr Zeit und Geld als früher in der Planung.")
        with mit_metriken(ki_muster_pro_1000=8.0):
            c = coach.coache(gleichmaessig(8, 5) + "\n\n" + lang2 + " " + self.SOWOHL, None, 80, roh=True)
        h = [x for x in c["hinweise_roh"] if x["typ"] == "floskel" and "sowohl" in x["text"]]
        for x in h:
            self.assertNotIn("Länge halten", x["text"])
            self.assertLess(x["sim"][0], x["laengen_alt"][0])
            self.assertGreaterEqual(coach.auftrag_logit(coach.Lauf(KI_TEXT, None), dict(x, muster_gewicht=0.8)), 0)

    def test_widerspruch_kuerzen_und_laenge_halten(self):
        a = {"typ": "fw_ankuendigung", "satz": 4, "laenge": 30, "laengen_alt": [30], "sim": [26], "hebel": "funktionswoerter",
             "text": "Satz 4 („…“): Ankündigung streichen. Länge halten (mindestens 30 Wörter): nur die Wendung umbauen.",
             "stelle": "Satz 4 („…“)", "gewicht": 1.0, "laenge_halten": 30}
        b = {"typ": "konnektor", "satz": 4, "laenge": 30, "streicht": ["zudem"], "hebel": "konnektoren",
             "text": "Satz 4 („…“): „zudem“ streichen.", "stelle": "Satz 4 („…“)", "gewicht": 1.0}
        teile, notiz = coach.widersprueche_aufloesen([a, b])
        self.assertTrue(notiz)
        self.assertFalse([t for t in teile if "Länge halten" in t["text"]])
        einzel, notiz = coach.widersprueche_aufloesen([a])
        self.assertNotIn("Länge halten", einzel[0]["text"])


class Buendeln(unittest.TestCase):
    def paar(self, a, b, laenge=False):
        L = coach.Lauf(a + " " + b + "\n\n" + FUELL, None)
        return L, coach.buendel_paar_grund(L, L.saetze[0], L.saetze[1], laenge=laenge)

    def test_regression_ssoar_und_haw(self):
        L, grund = self.paar(SSOAR_15, SSOAR_16)
        self.assertEqual(grund, "kein_bezug")  # nur das Bestimmungswort „Reproduktion“ verbindet die Sätze
        self.assertFalse(coach.buendel_laengen_ok(L, L.saetze[0]["woerter"], L.saetze[1]["woerter"]))  # b hat 33 Wörter
        self.assertEqual(self.paar(HAW_32, HAW_33)[1], "b_status")  # Folgerung „Bei beiden … ergibt sich also“
        for text in (SSOAR_15 + " " + SSOAR_16, HAW_32 + " " + HAW_33):
            c = coach.coache(text + "\n\n" + FUELL, None, 40, roh=True)
            self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "buendeln" and h["satz"] == 1])

    def test_folgerung_wertung_und_modalverben_in_b(self):
        a = "Die Firma nutzt seit dem Frühjahr neue Wege für den Kontakt mit jungen Leuten in der Region."
        for b, grund in (("Insgesamt plant die Firma dazu auch mehr Zeit und Geld für die Werbung ein.", "b_status"),
                         ("Die Firma plant dafür also mehr Zeit und Geld für die Werbung in der Region ein.", "b_status"),
                         ("Die Werbung für den Kontakt mit jungen Leuten ist leider sehr teuer geworden.", "b_status"),
                         ("Die Wege für den Kontakt mit jungen Leuten lassen sich gut mit dem Budget planen.", "b_modal_rede"),
                         ("Die Wege für den Kontakt sind ein Thema, an dem die Firma weiter arbeiten sollte.", "b_modal_neben")):
            self.assertEqual(self.paar(a, b)[1], grund, b)

    def test_umgedrehte_richtung_und_auftragstext(self):
        a = "Ein erstes Ergebnis betrifft die Werbung der Firma."
        b = ("Die Firma nutzt für den Kontakt mit jungen Leuten in der Region seit dem Frühjahr neue Wege und plant dazu auch mehr Zeit "
             "und Geld ein.")
        L = coach.Lauf(a + " " + b + "\n\n" + FUELL, None)
        self.assertTrue(coach.umkehr(L, L.saetze[0], L.saetze[1]))
        txt = coach._paar_text(L.saetze[0], L.saetze[1], "umgedreht", 32, False, True)
        self.assertIn("einleitende Angabe an den Anfang von Satz 2", txt)
        self.assertIn("mit Doppelpunkt", txt)
        for t in (txt, coach._paar_text(L.saetze[0], L.saetze[1], "buendeln", 32, False, True)):
            self.assertIn("Fachbegriffe beider Sätze behalten", t)
            self.assertIn("höchstens zwei Nomen hintereinander", t)
            self.assertIn("Doppelpunkt oder „denn“ (ein Hauptsatz) statt Nominalgruppe", t)
            self.assertNotIn("„weshalb“ oder „wobei“ erlaubt", t)
        viele = coach._paar_text(L.saetze[0], L.saetze[1], "buendeln", 32, True, False)
        self.assertIn("überspringen", viele)
        self.assertNotIn("Doppelpunkt", viele)

    def test_kein_buendeln_bei_hohem_nominalstil(self):
        # Sperre erst über P90 (9,42): zwischen P75 und P90 bleibt Bündeln erlaubt (v5 sperrte dort wirksame Bündelungen)
        with mit_metriken(nominalstil_pro_100=8.8):  # über P75 (8,25), unter P90
            c = coach.coache(gleichmaessig(8, 5), None, 40, roh=True)
        self.assertNotIn("buendeln", c["ausgesetzt"])
        with mit_metriken(nominalstil_pro_100=9.8):  # über P90
            c = coach.coache(gleichmaessig(8, 5), None, 40, roh=True)
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "buendeln"])
        self.assertIn("buendeln", c["ausgesetzt"])
        self.assertIn("über P90", c["ausgesetzt"]["buendeln"][0])
        self.assertEqual(c["satzlaengen"]["selbst_buendeln"], 0)  # keine Selbsthilfe „bündeln“ gegen die Aussetzung

    def test_keine_abkuerzung_an_satz_b(self):
        text = gleichmaessig(8, 5).replace("in der Region und plant dazu auch mehr.", "unter anderem in der Region und plant dazu auch mehr.")
        c = coach.coache(text, None, 60, roh=True)
        eingebettet = {n for h in c["hinweise_roh"] if h["typ"] == "buendeln" for n in h.get("eingebettet") or []}
        for h in c["hinweise_roh"]:
            if h["typ"] == "abkuerzung":
                self.assertFalse(set(h.get("saetze") or [h["satz"]]) & eingebettet, h["text"])


class KommaUndNebensatz(unittest.TestCase):
    def test_regression_haw7747_berichtete_rede(self):
        L = lauf(HAW7747_36 + "\n\n" + FUELL)
        s = L.saetze[0]
        self.assertTrue(coach.wiedergegebene_rede(L, s, L.masken[s["nr"]].split(",")[0]))
        c = coach.coache(HAW7747_36 + "\n\n" + FUELL, None, 40, roh=True)
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] in ("kommas", "nebensatz") and h["satz"] == 1])
        for verb in ("versichert", "angegeben", "mitgeteilt", "bestätigt", "berichtet"):
            self.assertTrue(coach.REDEVERB_RE.search(f"Auf Nachfrage wurde {verb}"), verb)
        self.assertTrue(coach.REDEVERB_RE.search("Die Befragten gaben häufig an"))

    def test_teilsatz_simulation(self):
        self.assertEqual(coach.verhaeltnis_21([1, 1, 2, 3]), (1 + 0.5) / (2 + 0.5))
        self.assertEqual(coach.teilsatz_wirkung(3), 1)
        self.assertEqual(coach.teilsatz_wirkung(2), -1)
        self.assertIn("kommas", coach.WAECHTER["teilsatz_verhaeltnis_21"]["ki"])
        self.assertIn("nebensatz", coach.WAECHTER["teilsatz_verhaeltnis_21"]["ki"])
        # ein befolgter Komma-Auftrag an einem Satz mit drei Teilsätzen erklärt einen Anstieg, einer mit zwei nicht
        L = coach.Lauf(KI_TEXT, None)
        h3 = {"typ": "kommas", "anfang": "satz der nicht mehr da ist", "teilsaetze": 3}
        h2 = dict(h3, teilsaetze=2)
        self.assertTrue(coach._verursacht(L, "kommas", [h3], "teilsatz_verhaeltnis_21", 0.2))
        self.assertFalse(coach._verursacht(L, "kommas", [h2], "teilsatz_verhaeltnis_21", 0.2))
        self.assertFalse(coach._verursacht(L, "nebensatz", [h2], "teilsatz_verhaeltnis_21", 0.2))

    def test_komma_nur_ohne_anstieg_ueber_p75(self):
        drei = ("Die Firma plant, wenn die Region wächst, mehr Stellen, die sie mit jungen Leuten aus dem Umland, aus der Stadt "
                "und aus dem Ausland besetzt.")
        L = lauf(drei + "\n\n" + FUELL)
        self.assertGreaterEqual(coach._teilsaetze(L.saetze[0]), 3)
        with mit_metriken(woerter_pro_teilsatz=6.0, teilsatz_verhaeltnis_21=1.2):
            c = coach.coache(drei + "\n\n" + FUELL, None, 40, roh=True)
        for h in c["hinweise_roh"]:
            if h["typ"] == "kommas" and h["satz"] == 1:
                L2 = coach.Lauf(drei + "\n\n" + FUELL, None)
                L2.hinweise = [dict(h)]
                self.assertLessEqual(coach.verhaeltnis_21(coach.teilsatz_folge(L2)), B["metriken"]["teilsatz_verhaeltnis_21"]["mensch"]["p75"])

    def test_kopula_dass_und_projizierte_kette(self):
        self.assertTrue(coach.kopula_praedikativ("dass mehr Autonomie für alle Mitarbeitenden gleichermaßen motivierend ist"))
        self.assertTrue(coach.kopula_praedikativ("dass die Daten verfügbar sind"))
        self.assertFalse(coach.kopula_praedikativ("dass die Kosten gestiegen sind"))
        self.assertFalse(coach.kopula_praedikativ("dass die Kosten gesenkt werden"))
        self.assertGreaterEqual(coach.projizierte_kette("dass die Kosten im zweiten Jahr der Einführung in kleinen Betrieben steigen"),
                                coach.PROJ_KETTE_MAX)
        self.assertLess(coach.projizierte_kette("dass die Kosten steigen"), coach.PROJ_KETTE_MAX)
        satz = "Ein zweiter kritischer Punkt betrifft die Annahme, dass mehr Autonomie für alle gleichermaßen motivierend ist."
        L = lauf(satz + "\n\n" + KI_TEXT)
        self.assertIsNone(coach.nebensatz_auftrag(L, L.saetze[0], L.masken[1]))


class Begriffsaufnahme(unittest.TestCase):
    def test_bestimmungswort_nur_mit_synonymem_grundwort(self):
        r = coach.begriffs_relation
        self.assertIsNone(r("Datenqualität", "Datenbasis", {"daten"}))
        self.assertEqual(r("Preissetzung", "Preisgestaltung", set())[0], "bestimmungswort")
        self.assertIsNone(r("Systemqualität", "Systembasis", set()))
        self.assertEqual(r("Marktstudie", "Markterhebung", set())[0], "synonym")  # Grundwörter Studie/Erhebung: Synonyme

    def test_wiederkehrender_fachbegriff_wird_nicht_ersetzt(self):
        text = ("Die Preissetzung im Einzelhandel folgt heute oft festen Regeln und Tabellen der Zentrale. "
                "Viele Anbieter passen die Preisgestaltung inzwischen mehrmals täglich an die aktuelle Nachfrage an. "
                "Algorithmen werten dafür Wetterdaten, Lagerbestände und Konkurrenzangebote in Echtzeit aus.\n\n"
                "Die Preisgestaltung gilt in vielen Branchen als heikles Thema mit hohem Risiko für das Image.")
        with mit_metriken(anteil_saetze_mit_wortaufnahme=0.2):
            c = coach.coache(text + "\n\n" + FUELL, None, 40, roh=True)
        kb = [x for x in c["hinweise_roh"] if x["typ"] == "kein_bezug" and x["satz"] == 2]
        for x in kb:
            self.assertNotIn("„Preisgestaltung“ → „Preissetzung“", x["text"])
            self.assertIn("kommt im Text mehrfach vor und bleibt", x["text"])
            self.assertEqual(x["art"], "wiederaufnahme")
            self.assertIsNone(x["fund"])


class AbsatzTeilen(unittest.TestCase):
    def trennbar(self, saetze):
        text = " ".join(saetze) + "\n\n" + FUELL
        L = coach.Lauf(text, None)
        liste = L.absaetze[1]
        return [coach._absatz_trennbar(L, liste, k) for k in range(1, len(saetze))]

    def test_rhetorische_bindungen(self):
        basis = ["Die Firma nutzt neue Wege für den Kontakt mit jungen Leuten in der Region und plant dazu mehr Geld ein.",
                 "Viele Betriebe im Umland folgen diesem Vorbild inzwischen mit eigenen Angeboten für Schulen."]
        # nach kurzem Ankündigungssatz (Employer S17)
        self.assertFalse(self.trennbar(basis + ["Von zentraler Bedeutung ist die Signaltheorie nach Spence.",
                                                "Auf dem Arbeitsmarkt fehlen Bewerbern verlässliche Informationen über Betriebe."])[2])
        # vor der Kontrast-Antwort auf einen „nicht“-Satz (CSRD S3/S4)
        self.assertFalse(self.trennbar(basis + ["Dieser Gedanke ist in der Forschung nicht neu und wird seit Jahren diskutiert.",
                                                "Neu ist jedoch die Verbindlichkeit der Berichte für alle großen Firmen."])[2])
        # vor einem Beispiel (DP S33/S34)
        self.assertFalse(self.trennbar(basis + ["Personalisierte Preise können das Vertrauen der Kunden stark beschädigen.",
                                                "Bekannt geworden ist ein Fall aus dem Jahr 2011 bei einem großen Versandhändler."])[2])
        self.assertTrue(self.trennbar(basis + ["Die Schulen in der Region melden steigende Zahlen bei den Anmeldungen.",
                                               "Die Kammer bietet ab dem Herbst neue Kurse für Ausbilder in den Betrieben an."])[2])


class Gegenfolie(unittest.TestCase):
    def test_technik_nach_art_von_x(self):
        t, txt = coach.gegenfolie_technik(["ersetzen"], coach.Counter())
        self.assertIn("„X und … auch Y“", txt)
        self.assertNotIn("„neben X auch Y“", txt)
        t, txt = coach.gegenfolie_technik(["allein", "von", "technischen", "Entwicklungen"], coach.Counter())
        self.assertIn("„von“ steht in beiden Gliedern", txt)
        t, txt = coach.gegenfolie_technik(["die", "Rekrutierung"], coach.Counter())
        self.assertEqual(t, "neben")
        t2, txt2 = coach.gegenfolie_technik(["die", "Bindung"], coach.Counter({"neben": 1}))
        self.assertNotEqual(t2, "neben")  # wechselnde Technik

    def test_hoechstens_zwei_je_text(self):
        saetze = [f"Die {x} ist nicht nur für die Rekrutierung der Firma wichtig, sondern auch für die Bindung im Betrieb."
                  for x in ("Marke", "Kultur", "Werbung", "Schulung")]
        text = "\n\n".join(" ".join([s, "Die Firma plant dazu mehr Zeit und Geld für den Kontakt mit jungen Leuten ein."])
                           for s in saetze) + "\n\n" + FUELL
        with mit_metriken(sondern_pro_1000=6.0, ki_muster_pro_1000=8.0):
            c = coach.coache(text, None, 60, roh=True)
        g = [h for h in c["hinweise_roh"] if h["typ"] == "gegenfolie"]
        self.assertLessEqual(len(g), coach.GEGENFOLIE_MAX)
        stand = {"messungen": [dict(c["stand"], hinweise=[{"typ": "gegenfolie", "anfang": f"a{i}"} for i in range(2)])]}
        with mit_metriken(sondern_pro_1000=6.0, ki_muster_pro_1000=8.0):
            c2 = coach.coache(text, stand, 60, roh=True)
        self.assertFalse([h for h in c2["hinweise_roh"] if h["typ"] == "gegenfolie"])  # je Text, über alle Runden


class Abkuerzungsfamilie(unittest.TestCase):
    def test_alle_langformen_in_einem_auftrag(self):
        text = (FUELL + "\n\nDie Firma hat rund 500 Beschäftigte in der Region und plant dazu mehr Zeit und Geld ein.\n\n"
                "Im Ausland arbeiten etwa 120 weitere Beschäftigte für die Firma an zwei neuen Standorten.")
        L = coach.Lauf(text, None)
        coach._hebel_priorisieren(L)
        r = L.ref["abkuerzungen_pro_1000"]
        L.ref = dict(L.ref, abkuerzungen_pro_1000=dict(r, mensch=dict(r["mensch"], p50=2.0, p75=4.0)))
        with unittest.mock.patch.object(coach.Lauf, "modell_hebel", lambda self, k: True):
            coach._abkuerzungen(L)
        abk = [h for h in L.hinweise if h["typ"] == "abkuerzung"]
        self.assertEqual(len(abk), 1)
        self.assertIsNone(abk[0]["satz"])  # mehrere Sätze: ein Auftrag mit allen Satznummern
        self.assertEqual(abk[0]["funde"], ["rund", "etwa"])
        self.assertIn("alle Stellen in einem Durchgang", abk[0]["text"])
        self.assertTrue(abk[0]["anfang"].startswith("abk:"))


class FloskelOhneNeuenInhalt(unittest.TestCase):
    def ersatz(self, text, nr, mid):
        L = coach.Lauf(text + "\n\n" + FUELL, None)
        mu = next(m for m in L.muster if m.get("id") == mid)
        return coach.floskel_ersatz(mu, L, L.nach_nr[nr])

    def test_begruendung_nur_mit_begruendung_im_kontext(self):
        ohne = self.ersatz("Von zentraler Bedeutung ist die Signaltheorie nach Spence. Auf dem Arbeitsmarkt fehlen oft Informationen, "
                           "da Bewerber die Betriebe kaum kennen.", 1, "von_bedeutung")
        self.assertNotIn("Begründung", ohne)
        self.assertNotIn("Fakten", ohne)
        self.assertIn("gleich stark, ohne neuen Inhalt", ohne)
        mit = self.ersatz("Von zentraler Bedeutung ist die Signaltheorie nach Spence. Denn sie erklärt, warum Bewerber auf Signale "
                          "achten.", 1, "von_bedeutung")
        self.assertIn("Begründung", mit)

    def test_ermoeglicht_es_mit_subjekt_aus_dem_kontext(self):
        dativ = self.ersatz("Das Verfahren ermöglicht es den Händlern, Preise schnell anzupassen.", 1, "ermoeglicht")
        self.assertIn("„den Händlern“", dativ)  # Prüfung: keine selbst gebeugte Form („Händlern können so …“ war falsch)
        self.assertNotIn("Händlern können", dativ)
        absatz = self.ersatz("Viele Händler nutzen neue Verfahren. Das Verfahren ermöglicht es, Preise schnell anzupassen.", 2,
                             "ermoeglicht")
        self.assertIn("„Händler“", absatz)
        ohne = self.ersatz("Das Verfahren ermöglicht es, Preise schnell anzupassen.", 1, "ermoeglicht")
        self.assertIn("Passiv", ohne)
        self.assertIn("kein neues Subjekt erfinden", ohne)


class KopfzeileUndWaechter(unittest.TestCase):
    def test_kein_jargon_im_bericht(self):
        with open(coach.__file__, encoding="utf-8") as f:
            quelle = f.read()
        self.assertNotIn("Satzlängen-Aufträge unten sind simuliert", quelle)
        self.assertNotIn("daraufhin simuliert", quelle)
        self.assertIn("Optional, kein Auftrag:", quelle)
        self.assertNotIn("Logit", coach.FW_EHRLICH)


class KonnektorenUeberP90(unittest.TestCase):
    TEXT = ("Die Firma nutzt neue Wege für den Kontakt mit jungen Leuten. Sie plant zudem mehr Zeit und Geld für die Werbung ein.\n\n"
            "Die Kammer bietet neue Kurse für Ausbilder an. Die Schulen melden zudem steigende Zahlen bei den Anmeldungen.\n\n"
            "Die Region wächst seit Jahren deutlich. Die Betriebe suchen zudem dringend junge Leute für ihre offenen Stellen.\n\n"
            "Die Leitung prüft jedoch die Kosten. Die Teams arbeiten jedoch gern im Büro. Die Zahlen steigen jedoch langsam.")

    def konnektoren(self, wert):
        with mit_metriken(konnektoren_pro_1000=wert, anteil_konnektor_satzanfang=0.2):
            c = coach.coache(self.TEXT + "\n\n" + gleichmaessig(3, 5), None, 60, roh=True)
        return [h for h in c["hinweise_roh"] if h["typ"] == "konnektor"]

    def test_textweite_haeufung_nur_ueber_p90(self):
        k = self.konnektoren(14.0)  # über P90 (11,4)
        zudem = [h for h in k if h["fund"].lower() == "zudem"]
        self.assertEqual(len(zudem), 2)  # 3× im Text, je Absatz eine Stelle, eine bleibt stehen
        self.assertTrue(all("steht im Text 3×" in h["text"] for h in zudem))
        self.assertLessEqual(len({h["absatz"] for h in zudem}), 2)
        self.assertFalse([h for h in k if h["fund"].lower() == "jedoch" and "im Text" in h["text"]])  # jedoch: nicht textweit
        k = self.konnektoren(10.0)  # zwischen P75 und P90: Regel wie v4
        self.assertFalse([h for h in k if h["fund"].lower() == "zudem"])
        self.assertLessEqual(len(k), coach.MAX_KONNEKTOR)

    def test_rote_kennzahl_ohne_auftrag_in_der_orientierung(self):
        c = coach.coache(KI_TEXT, None, 40)
        h = {"id": "konnektoren", "name": "Weniger Konnektoren", "warum": "…", "stellenlos": True, "selbsthilfe": "Selbst prüfen",
             "kennzahlen": [{"id": "konnektoren_pro_1000", "name": "Konnektoren", "wert": 14.0, "status": "rot", "bewertet": True}]}
        # sechs andere stellenlose Hebel davor: ohne die Regel fiele der rote Konnektor-Hebel aus der Orientierung (höchstens drei)
        andere = [{"id": f"x{i}", "name": f"X{i}", "warum": "", "stellenlos": True, "selbsthilfe": "s", "kennzahlen": []} for i in range(6)]
        c["hebel"] = [x for x in c["hebel"] if x["id"] != "konnektoren"] + andere + [h]
        txt = coach.bericht(c)
        self.assertIn("Weniger Konnektoren: Selbst prüfen", txt)


if __name__ == "__main__":
    unittest.main()
