"""Tests für Coach v7, Präzisionsrunde aus der v6-Prüfung auf Claude-Texten (C2):

1. Bündeln mit Teilsatz-Simulation (Verhältnis 2:1), Technik nach Nominalstil, Sperre „Attribut + Begründung“, Wächter nennt die
   geschützte Ursache, „vorab geprüft“ nur mit passenden Aufträgen.
2. Gegenfolie: „zwei Hauptsätze“ nur bei Satzklammer ≥ P25 und erstem Hauptsatz ≥ 8 Wörtern, „X, aber auch Y“, Rotation über die
   Runden, keine Anknüpfungs-Rüge für den Folgesatz der eigenen Teilung.
3. Diagnose: Längenblock (max + 0,3 · Rest), „gesperrt“ als eigene Summe außerhalb der Einstufung, Zeilen = Summen, alle Zeilen,
   Aufschub nur bei Deckung, sonst „vorläufig“, Absätze für das Neuformulieren.
4. Keine Sackgasse: „klein, aber sicher“.
5. Kürzende Wort-Aufträge in teilsatz_folge, KUERZUNG und WAECHTER; „rot und weiter verschlechtert“ im Fortschritt.
6. Absatz teilen: Rückbezug, Gegensatz, definites Rückbezugs-Nomen, Themensatz, kein Ein-Satz-Absatz mit „im Folgenden“.
7. Floskel-Ersatz ohne Wiederholung aus der Nähe; Synonyme mit Zielform, nicht bei Quellen-Sätzen.
8. Nebensatz → Präpositionalgruppe gesperrt bei „lassen sich“, Modalverb, „kaum“ und gestapeltem Attribut.

Synthetische Texte und Ausschnitte aus den v6-Prüftexten (dort zitiert). Felder der Messseite werden, wo nötig, gesetzt.

python3 -m unittest discover -s tests
"""
import os
import sys
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
from test_coach import KI_TEXT, THEMEN, absatz, satz  # noqa: E402
from test_coach_wirksamkeit import W, gleichmaessig, mit_metriken  # noqa: E402

TS = analyse.lade_baselines()["textsorten"]["hochschule"]
REF = TS["metriken"]
P75_21, P90_21 = REF["teilsatz_verhaeltnis_21"]["mensch"]["p75"], REF["teilsatz_verhaeltnis_21"]["mensch"]["p90"]


def teil_lauf(teile, werte=None, hinweise=None):
    """Minimaler Lauf für die Teilsatz-Simulation: Sätze mit vorgegebener Teilsatzzahl."""
    fokus = [{"nr": i + 1, "text": "x", "teilsaetze": t, "woerter": 15, "absatz": 1} for i, t in enumerate(teile)]
    werte = werte or {}
    return SimpleNamespace(fokus=fokus, hinweise=list(hinweise or []),
                           p_=lambda k, q: REF[k]["mensch"][q] if k in REF else None,
                           wert=lambda k: werte.get(k))


def diag_ns(beitraege, p, raum=None, messungen=(), hinweise=()):
    return SimpleNamespace(bew={"verfuegbar": True, "p_mensch": p, "modell_beitraege": beitraege}, messungen=list(messungen),
                           ts={"modell": TS["modell"]}, fw_potenzial=0.0, fw_diag=None, hinweise=list(hinweise), _buendel_raum=raum)


# ---------------------------------------------------------------------------------------------------------------------------
# 1. Bündeln mit Teilsatz-Simulation
# ---------------------------------------------------------------------------------------------------------------------------

class BuendelnTeilsatz(unittest.TestCase):
    def test_folge_nach_technik(self):
        L = teil_lauf([1, 1, 2, 2])
        L.hinweise = [{"typ": "buendeln", "satz": 1, "weitere_nr": [2], "technik": "nominal"}]
        self.assertEqual(sorted(coach.teilsatz_folge(L)), [1, 2, 2])
        L.hinweise = [{"typ": "buendeln", "satz": 1, "weitere_nr": [2], "technik": "doppelpunkt"}]
        self.assertEqual(sorted(coach.teilsatz_folge(L)), [1, 2, 2])  # der Doppelpunkt trennt keinen Teilsatz ab
        L.hinweise = [{"typ": "buendeln", "satz": 1, "weitere_nr": [2], "technik": "relativ"}]
        self.assertEqual(sorted(coach.teilsatz_folge(L)), [2, 2, 2])  # Relativsatz: Satz b bleibt ein Teilsatz
        L.hinweise = [{"typ": "buendeln", "satz": 3, "weitere_nr": [4], "technik": "nominal"}]
        self.assertEqual(sorted(coach.teilsatz_folge(L)), [1, 1, 3])

    def test_steigend_ueber_p75_verworfen_sinkend_erlaubt(self):
        # Agile R1 (v6-Prüfung): 1,05 → 1,11 über P90 durch eine Bündelung zweier Sätze mit je einem Teilsatz
        L = teil_lauf([1] * 18 + [2] * 19)
        vor = coach.verhaeltnis_21(coach.teilsatz_folge(L))
        self.assertGreater(vor, P75_21)
        self.assertFalse(coach.teilsatz_ok(L, {"typ": "buendeln", "satz": 1, "weitere_nr": [2], "technik": "nominal"}))
        # zwei Sätze mit je einem Nebensatz → einer mit drei Teilsätzen: das Verhältnis sinkt
        self.assertTrue(coach.teilsatz_ok(L, {"typ": "buendeln", "satz": 19, "weitere_nr": [20], "technik": "nominal"}))
        self.assertEqual(L.hinweise, [])  # die Probe wird wieder entfernt
        # unter P75 und danach weiter darunter: erlaubt
        L = teil_lauf([1] * 30 + [2] * 10)
        self.assertTrue(coach.teilsatz_ok(L, {"typ": "buendeln", "satz": 1, "weitere_nr": [2], "technik": "nominal"}))

    def test_kuerzende_wortauftraege_in_der_folge(self):
        L = teil_lauf([3, 1])
        L.hinweise = [{"typ": "fw_ankuendigung", "satz": 1, "fw_weg": {"dass": 1, "sich": 1}}]
        self.assertEqual(sorted(coach.teilsatz_folge(L)), [1, 2])
        L.hinweise = [{"typ": "fw_ankuendigung", "satz": 1, "fw_weg": {"sich": 1}}]  # „folgt, dass …“: der dass-Satz bleibt
        self.assertEqual(sorted(coach.teilsatz_folge(L)), [1, 3])
        # 3 → 2 Teilsätze bei schon hohem Verhältnis: verworfen (Agile S41: 1,11 → 1,17)
        L = teil_lauf([1] * 18 + [2] * 19 + [3])
        self.assertFalse(coach.teilsatz_ok(L, {"typ": "fw_ankuendigung", "satz": 38, "fw_weg": {"dass": 1}}))
        self.assertTrue(coach.teilsatz_ok(L, {"typ": "fw_ankuendigung", "satz": 19, "fw_weg": {"dass": 1}}))  # 2 → 1 senkt

    def test_technik_nach_nominalstil(self):
        p75, p90 = REF["nominalstil_pro_100"]["mensch"]["p75"], REF["nominalstil_pro_100"]["mensch"]["p90"]
        dp50 = REF["doppelpunkt_pro_1000"]["mensch"]["p50"]
        mitte = (p75 + p90) / 2
        self.assertEqual(coach.buendel_technik(teil_lauf([], {"nominalstil_pro_100": p75 - 0.5}), "buendeln"), "nominal")
        self.assertEqual(coach.buendel_technik(teil_lauf([], {"nominalstil_pro_100": mitte, "doppelpunkt_pro_1000": 0.0}), "buendeln"),
                         "doppelpunkt")
        self.assertEqual(coach.buendel_technik(teil_lauf([], {"nominalstil_pro_100": mitte, "doppelpunkt_pro_1000": dp50 + 3}),
                                               "buendeln"), "relativ")
        self.assertIsNone(coach.buendel_technik(teil_lauf([], {"nominalstil_pro_100": mitte}), "aufbau"))
        a = {"nr": 3, "text": "Die Firma plant neue Wege für den Kontakt mit jungen Leuten.", "woerter": 16}
        b = {"nr": 4, "text": "Die Wege betreffen vor allem die Region.", "woerter": 15}
        t = coach._paar_text(a, b, "buendeln", 30, technik="doppelpunkt")
        self.assertIn("Doppelpunkt", t)
        self.assertIn("keine Nominalgruppe", t)
        self.assertNotIn("Nominal- oder Präpositionalgruppe", t)
        self.assertIn("Relativsatz", coach._paar_text(a, b, "buendeln", 30, technik="relativ"))

    def test_attribut_und_begruendung_sperrt(self):
        # ssoar-21977 S14+S15 (v6-Prüfung): als Nominalgruppe entstünde ein gestapeltes Partizipialattribut
        self.assertEqual(coach.attribute_vor_nomen("Diese werden aufgrund ihrer langwierigen und komplexen Reproduktionszeiten "
                                                   "absolut knapp."), 2)
        self.assertEqual(coach.attribute_vor_nomen("da sich die geforderten Datenmengen manuell kaum bewältigen lassen"), 1)
        self.assertEqual(coach.attribute_vor_nomen("Die Firma plant neue Wege."), 1)
        self.assertEqual(coach.attribute_vor_nomen("Die Firma plant Wege."), 0)
        text = ("Haushalten müssen alle wirtschaftenden Einheiten indes mit den finanziellen und auch mit den sozialen und ökologischen "
                "Ressourcen. Diese werden aufgrund ihrer langwierigen und komplexen Reproduktionszeiten absolut knapp.\n\n" + gleichmaessig(4, 5))
        L = coach.Lauf(text, None)
        self.assertEqual(coach.buendel_paar_grund(L, L.nach_nr[1], L.nach_nr[2], laenge=False), "b_attribut_grund")

    def test_buendel_auftraege_heben_das_verhaeltnis_nicht(self):
        # Eigenschaft: auf mehreren Texten hebt kein Bündel-Auftrag das simulierte Verhältnis über P75 (bzw. lässt es über P90)
        from test_coach_v4 import aufbau_text
        for text in (KI_TEXT, aufbau_text(), gleichmaessig(8, 5)):
            c = coach.coache(text, None, 40, roh=True)
            L = coach.Lauf(text, None)
            t = {s["nr"]: [coach._teilsaetze(s)] for s in L.fokus}
            vor = coach.verhaeltnis_21([x for v in t.values() for x in v])
            for h in c["hinweise_roh"]:
                if h["typ"] == "buendeln" and h.get("weitere_nr"):
                    a, b = h["satz"], h["weitere_nr"][0]
                    plus = 0 if h.get("technik") == "relativ" else -1
                    t[a], t[b] = [max(1, t[a][0] + t[b][0] + plus)], []
            nach = coach.verhaeltnis_21([x for v in t.values() for x in v])
            self.assertFalse(nach > vor + 1e-9 and nach > P75_21, text[:40])

    def test_waechter_nennt_geschuetzte_ursache(self):
        # Agile R2 (v6-Prüfung): die eigene Bündelung hob das Verhältnis 2:1 über P90 – Bündeln bleibt erlaubt (lange Sätze unter
        # P25), aber die Ursache steht im Bericht statt „keinem befolgten Auftrag zuzuordnen“
        L0 = coach.Lauf(KI_TEXT, None)
        verbund = next(s for s in L0.fokus if sum(analyse.teilsatz_zerlegung(s["text"])[:2]) >= 2)
        h = {"typ": "buendeln", "anfang": coach.schluessel_anfang(verbund["text"]), "laenge": verbund["woerter"] - 12,
             "weitere": ["gibt es nicht mehr"], "satz": verbund["nr"]}
        verlauf = {"messungen": [{"score": 50, "p_mensch": 0.1, "kennzahlen": {}, "roh": {"teilsatz_verhaeltnis_21": 0.9},
                                  "hinweise": [h]}]}
        with mit_metriken(teilsatz_verhaeltnis_21=1.2, anteil_lange_saetze=0.05, nominalstil_pro_100=6.0):
            c = coach.coache(KI_TEXT, verlauf, 40)
        uk = [u for u in c["fortschritt"]["ueberkorrektur"] if u["id"] == "teilsatz_verhaeltnis_21"]
        self.assertEqual(len(uk), 1)
        self.assertEqual(uk[0]["geschuetzt"], ["buendeln"])
        self.assertNotIn("buendeln", c["fortschritt"]["ausgesetzt"])
        b = coach.bericht(c)
        self.assertIn("Ursache: die Bündelung der Vorrunde", b)
        self.assertNotIn("keinem befolgten Auftrag", b)


# ---------------------------------------------------------------------------------------------------------------------------
# 2. Gegenfolie
# ---------------------------------------------------------------------------------------------------------------------------

class Gegenfolie(unittest.TestCase):
    VERB_X = ["strukturierte", "Daten", "auswerten"]

    def test_hauptsaetze_nur_mit_klammer_und_laenge(self):
        for benutzt in (Counter(), Counter({"und_auch_verb": 1, "aber_auch": 1}), Counter({"und_auch_verb": 3, "aber_auch": 3})):
            t, _ = coach.gegenfolie_technik(self.VERB_X, benutzt, klammer_ok=False, erster_hs=12)
            self.assertNotEqual(t, "hauptsaetze")  # Satzklammer unter P25 (Controlling 5,00 → 4,42)
            t, _ = coach.gegenfolie_technik(self.VERB_X, benutzt, klammer_ok=True, erster_hs=6)
            self.assertNotEqual(t, "hauptsaetze")  # erster Hauptsatz zu kurz: Kurzsatz
        t, text = coach.gegenfolie_technik(self.VERB_X, Counter({"und_auch_verb": 1, "aber_auch": 1}), klammer_ok=True, erster_hs=9)
        self.assertEqual(t, "hauptsaetze")
        self.assertIn("kein Pronomen", text)  # sonst rügt die nächste Runde den eigenen Folgesatz (Controlling S32 → S34)
        t, text = coach.gegenfolie_technik(self.VERB_X, Counter({"und_auch_verb": 1}), klammer_ok=False)
        self.assertEqual(t, "aber_auch")
        self.assertIn("„X, aber auch Y“", text)

    def test_rotation_ueber_die_runden(self):
        # v6-Prüfung: „X und … auch Y“ in R1 und R2 – die Technik der Vorrunden zählt mit
        text = ("Solche Systeme können nicht nur strukturierte Daten auswerten, sondern auch Berichtskommentare für die Leitung "
                "entwerfen. Die Firma sucht dabei nicht den schnellen Gewinn, sondern eine langfristige Bindung der Kunden. "
                "Die Leitung plant nicht eine Kürzung der Budgets, sondern einen Ausbau der Teams in der Region. "
                "Die Teams brauchen nicht mehr Regeln, sondern klare Ziele für die gemeinsame Arbeit.\n\n" + gleichmaessig(5, 5))
        with mit_metriken(sondern_pro_1000=6.0, satzklammer_mittel=4.0):
            c1 = coach.coache(text, None, 40, roh=True)
            t1 = next(h["technik"] for h in c1["hinweise_roh"] if h["typ"] == "gegenfolie" and h["satz"] == 1)
            self.assertIn(t1, ("und_auch_verb", "aber_auch"))  # Satzklammer unter P25: keine zwei Hauptsätze
            gf = [h for h in c1["stand"]["hinweise"] if h["typ"] == "gegenfolie" and h.get("satz") == 1]
            if gf:
                self.assertEqual(gf[0].get("technik"), t1)  # im Verlauf gespeichert
            alt = {"typ": "gegenfolie", "anfang": "ein anderer satz aus runde eins", "technik": t1}
            c2 = coach.coache(text, {"messungen": [dict(c1["stand"], hinweise=[alt])]}, 40, roh=True)
        t2 = next(h["technik"] for h in c2["hinweise_roh"] if h["typ"] == "gegenfolie" and h["satz"] == 1)
        self.assertNotEqual(t2, t1)

    def test_folgesatz_der_eigenen_teilung_ohne_anknuepfungs_ruege(self):
        a = "Solche Systeme können strukturierte Daten aus vielen Quellen auswerten und Muster in großen Beständen erkennen."
        b = "Sie können auch Berichtskommentare entwerfen und Abweichungen für die Leitung erklären."
        text = a + " " + b + "\n\n" + gleichmaessig(5, 5)
        h = {"typ": "gegenfolie", "anfang": "solche systeme können nicht nur strukturierte", "laenge": 30, "technik": "hauptsaetze",
             "satz": 1}
        L = coach.Lauf(text, {"messungen": [{"hinweise": [h]}]})
        coach._neu_geteilt(L)
        self.assertEqual(L.neu_geteilt.get(2), "gegenfolie")
        c = coach.coache(text, {"messungen": [{"score": 50, "p_mensch": 0.1, "kennzahlen": {}, "hinweise": [h]}]}, 40, roh=True)
        self.assertFalse([x for x in c["hinweise_roh"] if x["typ"] == "anknuepfung" and x["satz"] == 2])


# ---------------------------------------------------------------------------------------------------------------------------
# 3. Diagnose
# ---------------------------------------------------------------------------------------------------------------------------

BEITRAEGE_8 = [{"id": "fw_profil_llr_pro_1000", "name": "FW", "beitrag": -1.15},
               {"id": "nachbarsatz_ueberlappung", "name": "NS", "beitrag": -0.95},
               {"id": "mattr_100", "name": "MATTR", "beitrag": -0.76}, {"id": "satzklammer_mittel", "name": "Klammer", "beitrag": -0.63},
               {"id": "satzlaenge_dispersion", "name": "Dispersion", "beitrag": -0.61},
               {"id": "anteil_mittlere_saetze", "name": "mittel", "beitrag": -0.60},
               {"id": "anteil_sehr_lange_saetze", "name": "sehr lang", "beitrag": -0.24},
               {"id": "saetze_pro_absatz_cv", "name": "Absatz", "beitrag": -0.09}]


class Diagnose(unittest.TestCase):
    def test_laengenblock_einmal_gezaehlt(self):
        # Agile (v6-Prüfung): Dispersion 0,61 + mittellange 0,60 + sehr lange 0,12 = 1,33 aus demselben Hebel
        d = coach._diagnose(diag_ns(BEITRAEGE_8, 0.15), [], 0.86)
        z = {x["id"]: x for x in d["beitraege"]}
        blk = z["laengenblock"]
        self.assertNotIn("anteil_mittlere_saetze", z)
        pots = sorted([0.61, 0.60, 0.12], reverse=True)
        self.assertAlmostEqual(blk["potenzial_logit"], round(pots[0] + 0.3 * sum(pots[1:]), 2), places=2)
        self.assertIn("Dispersion", blk["name"])

    def test_zeilen_ergeben_die_summen_und_alle_zeilen_stehen_da(self):
        d = coach._diagnose(diag_ns(BEITRAEGE_8, 0.15, raum=0), [], 0.86)
        pot = round(sum(z["potenzial_logit"] for z in d["beitraege"]), 2)
        self.assertAlmostEqual(pot, round(d["erreichbar_logit"] + d["stellenlos_logit"] + d["gesperrt_logit"]
                                          + d["neuformulieren_logit"], 2), places=2)
        txt = "\n".join(coach.diagnose_text(d))
        for z in d["beitraege"]:
            self.assertIn(f"- {z['name']}:", txt)  # keine Zeile abgeschnitten (v6: 7. und 8. Zeile fehlten)
            if z["potenzial_logit"] > 0:
                self.assertIn(f"≈ {coach.fmt(z['potenzial_logit'])}", txt)
        self.assertIn("Summe der Zeilen", txt)
        self.assertIn(f"gesperrt ≈ {coach.fmt(d['gesperrt_logit'])}", txt)

    def test_gesperrt_zaehlt_nicht_fuer_die_einstufung(self):
        # CSRD R3 (v6-Prüfung): 1,12 von 1,48 hieß „knapp“, 0,53 davon gesperrt – ohne sie 40 %
        b = [{"id": "satzklammer_mittel", "name": "Klammer", "beitrag": -0.74},
             {"id": "nachbarsatz_ueberlappung", "name": "NS", "beitrag": -0.44},
             {"id": "satzlaenge_dispersion", "name": "Dispersion", "beitrag": -0.29},
             {"id": "anteil_mittlere_saetze", "name": "mittel", "beitrag": -0.24}]
        p = 1 / (1 + 2.718281828 ** -(coach._logit(0.86) - 1.48))
        d = coach._diagnose(diag_ns(b, p, raum=0), [], 0.86)
        self.assertGreater(d["gesperrt_logit"], 0)
        self.assertLess(d["erreichbar_logit"] + d["stellenlos_logit"], coach.KNAPP_ANTEIL * d["luecke_logit"])
        self.assertEqual(d["grenze"], "einzelkorrekturen")
        self.assertIn("Grenze der Einzelkorrekturen", "\n".join(coach.diagnose_text(d)))

    def test_aufschub_nur_bei_deckung(self):
        # DP R2 (v6-Prüfung): ein Auftrag bei einer Lücke von 3,35 – sofort diagnostizieren, „vorläufig“
        b = [{"id": "satzklammer_mittel", "name": "Klammer", "beitrag": -1.0}, {"id": "nachbarsatz_ueberlappung", "name": "NS", "beitrag": -1.0}]
        auftrag = {"hebel": "absaetze", "typ": "absatz_teilen", "netto_logit": 0.5}
        L = diag_ns(b, 0.11, messungen=[{"p_mensch": 0.003}], hinweise=[auftrag])
        d = coach._diagnose(L, [auftrag], 0.86)
        self.assertIsNotNone(d)
        self.assertTrue(d["vorlaeufig"])
        self.assertIn("(vorläufig)", "\n".join(coach.diagnose_text(d)))
        # kleine Lücke, die offenen Aufträge decken sie vorab gerechnet: Aufschub
        auftrag = dict(auftrag, netto_logit=1.2)
        L = diag_ns(b, 0.70, messungen=[{"p_mensch": 0.40}], hinweise=[auftrag])
        self.assertIsNone(coach._diagnose(L, [auftrag], 0.86))
        self.assertGreaterEqual(L.diagnose_aufgeschoben["sim_offen"] + L.diagnose_aufgeschoben["stellenlos"],
                                coach.KNAPP_ANTEIL * L.diagnose_aufgeschoben["luecke"])
        # ohne offenen Auftrag nie aufschieben, und dann nicht „vorläufig“
        L = diag_ns(b, 0.70, messungen=[{"p_mensch": 0.40}])
        d = coach._diagnose(L, [], 0.86)
        self.assertFalse(d["vorlaeufig"])

    def test_neuformulieren_nennt_absaetze(self):
        L = coach.Lauf(KI_TEXT, None)
        nrn = coach.fw_absaetze(L)
        self.assertTrue(1 <= len(nrn) <= 2)
        self.assertTrue(set(nrn) <= set(L.absaetze))
        d = {"p_mensch": 0.1, "ziel_p_mensch": 0.86, "umsetzbar": 0, "luecke_logit": 3.0, "erreichbar_logit": 0.0, "stellenlos_logit": 0.0,
             "realistisch": False, "grenze": "einzelkorrekturen", "fw_absaetze": nrn,
             "beitraege": [{"id": "fw_profil_llr_pro_1000", "name": "FW", "beitrag": -2.0, "erreichbar": 0.0, "erreichbar_logit": 0.0,
                            "potenzial_logit": 0.0, "rest_logit": 0.0, "wie": "keine_konstruktion"}]}
        self.assertIn(f"am ehesten Absatz {nrn[0]}", "\n".join(coach.diagnose_text(d)))


# ---------------------------------------------------------------------------------------------------------------------------
# 4. Keine Sackgasse
# ---------------------------------------------------------------------------------------------------------------------------

class KleinAberSicher(unittest.TestCase):
    def test_ohne_auftrag_kommen_sichere_kleine_stellen(self):
        L = coach.Lauf(KI_TEXT, None)
        treffer = [(s["nr"], fund, g) for s in L.fokus for _a, _e, g, mu, fund, _v in analyse.muster_treffer(L.masken[s["nr"]], L.muster)
                   if g >= coach.KLEIN_SICHER_GEWICHT and mu["id"] not in coach.GEGENFOLIE_MUSTER]
        self.assertTrue(treffer)
        # alle normalen Aufträge fallen weg (wie in den Schlussrunden der v6-Prüfung): dann „klein, aber sicher“. v7.1: alle Treffer –
        # einzeln bringt eine Wendung weit über der Kappung (KI_TEXT: 22,5 je 1000) simuliert nichts, die Familie zusammen schon
        with mock.patch.object(coach, "ein_auftrag_je_satz", lambda hs, texte=None: []), \
                mock.patch.object(coach, "muster_rest", lambda L_: (treffer, 0.3)):
            c = coach.coache(KI_TEXT, None, 15)
        klein = [h for h in c["hinweise"] if h.get("klein_sicher")]
        self.assertTrue(klein)
        self.assertTrue(all(h["text"].startswith(coach.KLEIN_SICHER) for h in klein))
        self.assertIn("nur noch kleine, aber sichere", coach.bericht(c))

    def test_diagnose_zeile_klein_sicher(self):
        # Controlling R3 (v6-Prüfung): die Muster-Zeile nennt die Aufträge „klein, aber sicher“ statt „im grünen Bereich, ohne Auftrag“
        b = [{"id": "ki_muster_pro_1000", "name": "KI-Muster", "beitrag": -0.34}]
        L = diag_ns(b, 0.44, hinweise=[{"typ": "floskel", "hebel": "floskeln", "klein_sicher": True}])
        L.fokus, L._klein_muster_pot = [], 0.3
        # v7.1: „mit Aufträgen“ = Summe der netto_teile der angezeigten Aufträge
        d = coach._diagnose(L, [{"typ": "floskel", "hebel": "floskeln", "klein_sicher": True, "netto_logit": 0.3,
                                 "netto_teile": {"ki_muster_pro_1000": 0.3}}], 0.86)
        z = d["beitraege"][0]
        self.assertEqual(z["wie"], "klein_sicher")
        self.assertAlmostEqual(z["erreichbar_logit"], 0.3, places=2)
        self.assertFalse(d["vorlaeufig"])  # nur kleine Aufträge offen: die Einschätzung gilt
        txt = "\n".join(coach.diagnose_text(d))
        self.assertIn("„klein, aber sicher“", txt)
        self.assertNotIn("im grünen Bereich", txt)

    def test_nicht_wenn_es_auftraege_gibt(self):
        c = coach.coache(KI_TEXT, None, 15)
        self.assertTrue(c["hinweise"])
        self.assertFalse([h for h in c["hinweise"] if h.get("klein_sicher")])


# ---------------------------------------------------------------------------------------------------------------------------
# 5. Kürzende Wort-Aufträge, Wächter, Fortschritt
# ---------------------------------------------------------------------------------------------------------------------------

class KuerzendeAuftraege(unittest.TestCase):
    def test_tabellen(self):
        self.assertEqual(coach.KUERZUNG["fw_ergibt"], 1)
        self.assertTrue({"fw_ankuendigung", "fw_dass"} <= coach.WAECHTER["teilsatz_verhaeltnis_21"]["ki"])
        self.assertEqual(coach.WAECHTER["satzklammer_mittel"]["ki"], {"konnektor", "floskel", "fw_ankuendigung", "gegenfolie", "mitte"})

    def test_rot_und_weiter_verschlechtert(self):
        c0 = coach.coache(KI_TEXT, None, 15)
        alt = dict(c0["stand"])
        kz = dict(alt["kennzahlen"])
        k = next((k for k, v in kz.items() if v["status"] == "rot" and coach.seite_von(v["wert"], REF[k]) == "ki"), None)
        if k is None:
            self.skipTest("keine rote Kennzahl auf der KI-Seite")
        r = REF[k]["mensch"]
        iqr = r["p75"] - r["p25"]
        richtung = 1 if kz[k]["wert"] > r["p50"] else -1
        kz[k] = {"wert": kz[k]["wert"] - richtung * 0.5 * iqr, "status": "rot"}  # früher näher am Median, auch schon rot
        c = coach.coache(KI_TEXT, {"messungen": [dict(alt, kennzahlen=kz)]}, 15)
        self.assertIn(k, c["fortschritt"]["weiter_rot"])
        self.assertIn("rot und weiter verschlechtert", coach.bericht(c))


# ---------------------------------------------------------------------------------------------------------------------------
# 6. Absatz teilen
# ---------------------------------------------------------------------------------------------------------------------------

class AbsatzSperren(unittest.TestCase):
    def trennbar(self, saetze):
        L = coach.Lauf(" ".join(saetze) + "\n\n" + gleichmaessig(4, 5), None)
        liste = L.absaetze[1]
        return [coach._absatz_trennbar(L, liste, k) for k in range(1, len(saetze))]

    A = satz(THEMEN[0], 17, 0, W)

    def test_rueckbezug_und_gegensatz_in_den_ersten_sieben_woertern(self):
        # Controlling vor S8 (v6-Prüfung): „Für das Controlling bedeutet dies allerdings …“
        for b in ("Für das Controlling bedeutet dies allerdings neue Wege für den Kontakt mit jungen Leuten in der Region.",
                  "Beide Wege betreffen den Kontakt mit jungen Leuten in der Region und planen dazu mehr.",
                  "In der Region betrifft der Kontakt jedoch neue Wege für die jungen Leute und die Firma."):
            self.assertEqual(self.trennbar([self.A, b, satz(THEMEN[2], 18, 5, W)])[0], False, b)

    def test_definites_rueckbezugs_nomen(self):
        b = "Der Ansatz betrifft neue Wege für den Kontakt mit jungen Leuten in der Region und plant dazu mehr."  # Kapselwort
        self.assertEqual(self.trennbar([self.A, b, satz(THEMEN[2], 18, 5, W)])[0], False)
        b = satz(THEMEN[0], 18, 4, W)  # „Die Arbeitgebermarke …“ nach „Die Arbeitgebermarke …“
        self.assertEqual(self.trennbar([self.A, b, satz(THEMEN[2], 18, 5, W)])[0], False)
        self.assertEqual(self.trennbar([self.A, satz(THEMEN[2], 18, 5, W), satz(THEMEN[3], 18, 6, W)]), [True, True])

    def test_themensatz(self):
        # DP vor S14 (v6-Prüfung): der kurze Themensatz „Eine weitere Chance besteht …“ und seine Begründung bleiben zusammen
        t = "Eine weitere Chance besteht in der Reaktion gegenüber dem Wettbewerb."
        s = [t, satz(THEMEN[2], 18, 5, W), satz(THEMEN[3], 18, 6, W), satz(THEMEN[4], 17, 2, W)]
        self.assertEqual(self.trennbar(s), [False, False, False])

    def test_kein_ein_satz_absatz_mit_im_folgenden(self):
        abs1 = absatz(THEMEN[0], [18, 16, 21, 15, 20], 0, W) + " Im Folgenden betrifft die Personalplanung neue Wege der Firma."
        text = abs1 + "\n\n" + absatz(THEMEN[1], [19, 22, 14, 17, 16], 5, W) + "\n\n" + gleichmaessig(5, 5, 11)
        c = coach.coache(text, None, 40, roh=True)
        S = {s["nr"]: s for s in analyse.analysiere_text(text)["saetze"]}
        for h in c["hinweise_roh"]:
            if h["typ"] == "absatz_teilen":
                self.assertFalse(coach.IM_FOLGENDEN_RE.search(S[h["satz"]]["text"]) and h["absatz"] == 1
                                 and h["satz"] == max(n for n, s in S.items() if s["absatz"] == 1))


# ---------------------------------------------------------------------------------------------------------------------------
# 7. Floskel-Ersatz und Synonyme
# ---------------------------------------------------------------------------------------------------------------------------

class ErsatzUndSynonyme(unittest.TestCase):
    def lauf(self, saetze):
        return coach.Lauf(" ".join(saetze) + "\n\n" + gleichmaessig(3, 5), None)

    def test_variante_aus_der_naehe_entfaellt(self):
        # Employer S17 (v6-Prüfung): „steht im Mittelpunkt“ wiederholte S3 „Im Mittelpunkt steht …“
        L = self.lauf(["Im Mittelpunkt steht die Frage nach neuen Wegen für junge Leute.",
                       "Von zentraler Bedeutung ist dabei der Kontakt mit jungen Leuten in der Region."])
        s = L.nach_nr[2]
        neu = coach.ersatz_ohne_nahe(L, s, coach.FLOSKEL_NEUTRAL["von_bedeutung"])
        self.assertNotIn("„steht im Mittelpunkt“", neu)
        self.assertIn("„ist besonders wichtig für …“", neu)
        # ohne die Wendung in der Nähe bleibt der Text
        L = self.lauf(["Die Frage nach neuen Wegen für junge Leute ist offen.",
                       "Von zentraler Bedeutung ist dabei der Kontakt mit jungen Leuten in der Region."])
        self.assertEqual(coach.ersatz_ohne_nahe(L, L.nach_nr[2], coach.FLOSKEL_NEUTRAL["von_bedeutung"]),
                         coach.FLOSKEL_NEUTRAL["von_bedeutung"])

    def test_einzige_variante_aus_der_naehe(self):
        L = self.lauf(["Wichtig ist der Kontakt mit jungen Leuten in der Region.",
                       "Von zentraler Bedeutung ist dabei der Kontakt mit jungen Leuten in der Region."])
        neu = coach.ersatz_ohne_nahe(L, L.nach_nr[2], "„ist wichtig für …“ mit Begründung.")
        self.assertIn("steht schon in Satz 1", neu)

    def test_synonym_zielform(self):
        L = SimpleNamespace(wert=lambda k: 6.0, p_=lambda k, q: REF[k]["mensch"][q])
        self.assertEqual(coach.synonym_ziel(L, [("Kunden", 8), ("Konsumenten", 3)])[0], "Kunden")
        L = SimpleNamespace(wert=lambda k: 9.0, p_=lambda k, q: REF[k]["mensch"][q])  # Nominalstil über P75
        self.assertEqual(coach.synonym_ziel(L, [("Wirkung", 5), ("Effekt", 3)])[0], "Effekt")

    def test_synonym_nicht_bei_quellen_satz(self):
        # DP (v6-Prüfung): „Konsumenten“ im Kahneman-Satz meint Verbraucher allgemein – nicht vereinheitlichen
        basis = ["Die Kunden der Firma kaufen oft online ein und vergleichen dabei die Preise genau.",
                 "Viele Kunden reagieren auf hohe Preise mit dem Wechsel zu anderen Anbietern in der Region.",
                 "Die Kunden erwarten faire Preise und klare Regeln für alle Angebote der Firma.",
                 "Auch treue Kunden achten auf Preise und wechseln bei Ärger schnell den Anbieter."]
        quelle = "Konsumenten empfinden Preiserhöhungen als unfair, wenn sie keinen Grund erkennen (Kahneman et al., 1986)."
        eigen = "Konsumenten empfinden Preiserhöhungen als unfair, wenn sie keinen Grund erkennen."
        with mit_metriken(mattr_100=0.9):
            c_q = coach.coache(" ".join(basis + [quelle]) + "\n\n" + gleichmaessig(3, 5), None, 40, roh=True)
            c_e = coach.coache(" ".join(basis + [eigen]) + "\n\n" + gleichmaessig(3, 5), None, 40, roh=True)
        syn_e = [h for h in c_e["hinweise_roh"] if h["typ"] == "synonyme" and "konsumenten" in h["anfang"]]
        if not syn_e:
            self.skipTest("Synonym-Hinweis hier nicht aktiv")
        self.assertIn("durchgehend „Kunden“", syn_e[0]["text"])
        self.assertEqual(syn_e[0]["ersetzbar"], ["konsumenten"])  # nur die zu ersetzende Form
        self.assertFalse([h for h in c_q["hinweise_roh"] if h["typ"] == "synonyme" and "konsumenten" in h["anfang"]])


# ---------------------------------------------------------------------------------------------------------------------------
# 8. Nebensatz → Präpositionalgruppe
# ---------------------------------------------------------------------------------------------------------------------------

class NebensatzSperren(unittest.TestCase):
    def test_modal_und_attribute(self):
        L = coach.Lauf(KI_TEXT, None)
        s = L.fokus[0]
        for teil in ("da sich die geforderten Datenmengen manuell kaum bewältigen lassen", "weil die Daten nur schwer zu erheben sind",
                     "weil die Firma die Daten erheben muss", "da sie kaum Daten erhebt"):
            self.assertEqual(coach.nominal_sperre(L, s, "x", teil), "modal", teil)
        self.assertEqual(coach.nominal_sperre(L, s, "x", "weil die langwierigen komplexen Verfahren fehlen"), "attribute")
        self.assertIsNone(coach.nominal_sperre(L, s, "x", "weil Daten fehlen"))

    def test_controlling_s42_kein_auftrag(self):
        # Controlling S42 (v6-Prüfung): „…, da sich die geforderten Datenmengen manuell kaum bewältigen lassen“ ergab „wegen der
        # geforderten, manuell kaum zu bewältigenden Datenmengen“
        satz42 = ("Automatisierte Prüfungen gewinnen im Controlling an Gewicht, da sich die geforderten Datenmengen manuell kaum "
                  "bewältigen lassen.")
        text = satz42 + " " + absatz(THEMEN[1], [18, 16, 21, 15], 2, W) + "\n\n" + gleichmaessig(5, 5)
        L = coach.Lauf(text, None)
        self.assertIsNone(coach.nebensatz_auftrag(L, L.nach_nr[1], L.masken[1]))


if __name__ == "__main__":
    unittest.main()
