"""Tests für Coach v7 (Einsatzfall: echte Abschnitte knapp unter dem Ziel): Ziel auf dem einseitigen Score, „menschlicher als
typisch“ als Info statt Auftrag, Zitatschutz mit Verschachtelung, Bereinigung verklebter Wörter, Auftragsgrenze nach simulierter
Netto-Wirkung (Messunsicherheit, kleine Lücke, keine netto schädlichen Aufträge), Vorgaben getrennt (Gender-Zielformen,
Gedankenstrich), Sperren (Gegenfolie, Konnektor-Korrelat, „lässt sich“, „um … zu“, Anknüpfung), Semikolon (Komma, Hysterese,
Anzeige) und „erwartet“ im Verlauf.

Synthetische Texte; als Regressionstest der Zitatmaske zusätzlich der erste Absatz eines echten Abschnitts (fhws-1919, mit
verschachteltem Interviewzitat), wie in der v6-Prüfung zitiert. Tests, die an Feldern der Messseite hängen (score_ki,
ziel_score_ki, jenseits_band, info['verklebt']), setzen diese Felder selbst oder prüfen den Rückfall.

python3 -m unittest discover -s tests
"""
import json
import math
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
from test_coach import KI_TEXT, absatz  # noqa: E402
from test_coach_wirksamkeit import gleichmaessig, gleichmaessig_wechsel  # noqa: E402

TS = analyse.lade_baselines()["textsorten"]["hochschule"]
FUELL = gleichmaessig(5, 5)

# erster Absatz von fhws-1919 (echter Abschnitt, v6-Prüfung): verschachteltes Interviewzitat »… »Jawoll …«. Genau (unv.) Ziele.«
# mit Quellenklammer, danach eigener Text, dann ein zweites Interviewzitat über zwei Sätze (S10–S11 in der v6-Messung)
FHWS_ABSATZ = (
    "Weiterhin waren selbst gewählte Ziele Teil von Studienerfolg für die Absolvierenden. »Wie ich Studienerfolg definieren würde? "
    "Na ja erstmal natürlich, dass man es besteht. ((lacht)) (unv.) einfach dann (I: Ja.), dass man erstmal überhaupt dann den "
    "Abschluss hat und dann halt natürlich dementsprechend, dass man den auch natürlich viel bewirkt hat, dass man halt, dann halt "
    "sagen kann: »Jawoll, ich habe meine Ziele erreicht«. Genau (unv.) Ziele.« [2019.01.14_19.01_Absolvent*in, Absatz 12] Dabei "
    "waren die Ziele subjektiv und individuell von der Person abhängig. Die selbst gewählten Ziele konnten zum Beispiel sein, dass "
    "die Person sich einen bestimmten Notendurchschnitt gesetzt hatte, sie Anforderungen bewältigt oder den Studienabschluss "
    "erreicht hatte. Unter Studienerfolg verstanden überwiegend die Lehrenden die Persönlichkeitsentwicklung. So wurde das Studium "
    "nicht nur als reine Wissensvermittlung und als Erwerb von Kompetenzen gesehen, sondern auch als persönliche "
    "Weiterentwicklung. »Und so ist es ganz klar das Ziel des Studiums herauszufinden, wer bin ich, was will ich, was kann ich. Ja "
    "und unsere Angebote sollten den Studierenden ermöglichen, das herauszufinden und dann die entsprechenden Kompetenzen "
    "aufzubauen, das heißt, sie können wirklich Wissen anwenden und aktuelle Probleme lösen.« [2018.06.06_Lehrende, Absatz 8] "
    "Studierende in dem Prozess der Persönlichkeitsentwicklung zu unterstützen, wurde als Aufgabe der Lehrenden beziehungsweise "
    "der Hochschule gesehen.")


ZIEL_P = (analyse.lade_baselines() or {}).get("textsorten", {}).get("hochschule", {}).get("ziel_p_mensch") or 0.86


def bewertung_setzen(**felder):
    """analysiere_und_bewerte mit vorgegebenen Feldern der Bewertung (score, score_ki, ziel_score_ki, p_mensch …)."""
    echt = coach.analyse.analysiere_und_bewerte

    def fake(*a, **k):
        erg, bew = echt(*a, **k)
        return erg, dict(bew, **felder)
    return mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake)


def saetze_von(text):
    return analyse.analysiere_text(text)["saetze"]


class ZielEinseitig(unittest.TestCase):
    def ns(self, bew, ts=None):
        return SimpleNamespace(bew=bew, ts=ts if ts is not None else {"ziel_p_mensch": 0.86, "ziel_score": 56.4})

    def test_score_ki_mit_ziel(self):
        z = coach._ziele(self.ns({"score": 50, "score_ki": 70, "ziel_score_ki": 63.0, "p_mensch": 0.9}))
        self.assertTrue(z["einseitig"])
        self.assertEqual((z["score"], z["ziel_score"], z["ziel_score_anzeige"]), (70, 63.0, 63))

    def test_rueckfall_ohne_felder(self):
        z = coach._ziele(self.ns({"score": 56, "p_mensch": 1.0}))
        self.assertFalse(z["einseitig"])
        self.assertEqual((z["score"], z["ziel_score_anzeige"], z["luecke_score"]), (56, 57, 1))
        # score_ki ohne Ziel: ebenfalls Rückfall (kein Vergleich eines einseitigen Werts mit dem zweiseitigen Ziel)
        z = coach._ziele(self.ns({"score": 56, "score_ki": 80, "p_mensch": 1.0}))
        self.assertFalse(z["einseitig"])

    def test_ziel_erreicht_auf_score_ki(self):
        with bewertung_setzen(score=40, score_ki=72, ziel_score_ki=60.0, p_mensch=0.99):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertTrue(c["ziel_erreicht"])
        with bewertung_setzen(score=90, score_ki=55, ziel_score_ki=60.0, p_mensch=0.99):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertFalse(c["ziel_erreicht"])
        self.assertIsNotNone(c["teilziel"])  # die Score-Lücke rechnet auf score_ki
        self.assertEqual(c["teilziel"]["fehlt"], 5)

    def test_anzeige_gerundet(self):
        self.assertEqual(coach._p_anzeige(0.856, 0.86), "85,6 %")
        self.assertEqual(coach._p_anzeige(0.853, 0.86), "85,3 %")  # < 1 Prozentpunkt unter dem Ziel, auch wenn gerundet 85
        self.assertEqual(coach._p_anzeige(0.8649, 0.86), "86,5 %")
        self.assertEqual(coach._p_anzeige(1.0, 0.86), "100 %")
        self.assertEqual(coach._p_anzeige(0.70, 0.86), "70 %")
        with bewertung_setzen(score=40, score_ki=40, p_mensch=0.995):
            c = coach.coache(KI_TEXT, None, 15)
        b = coach.bericht(c)
        self.assertIn(f"Modell 100 % (Ziel ≥ {round(c['ziel_p_mensch'] * 100)} %) erreicht", b)
        self.assertIn(f"bis {math.ceil(c['ziel_score'] - 1e-9)}", b)


class MenschlicherAlsTypisch(unittest.TestCase):
    def lange_text(self):
        return "\n\n".join(absatz(t, [34, 12, 38, 33, 9, 44], 5 * i) for i, t in
                           enumerate(["Arbeitgebermarke", "Personalplanung", "Weiterbildung", "Kommunikation", "Nachwuchsarbeit"]))

    def test_info_statt_teilen_ohne_verlauf(self):
        c = coach.coache(self.lange_text(), None, 40, roh=True)
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "teilen"])
        self.assertIn("anteil_lange_saetze", {z["id"] for z in c["menschlicher_als_typisch"]})
        b = coach.bericht(c)
        self.assertIn("Menschlicher als typisch (kein Auftrag)", b)
        self.assertNotIn("Keine weiteren langen Sätze – einzelne teilen", b)

    def test_info_auch_bei_ziel_erreicht(self):
        with bewertung_setzen(score=95, score_ki=95, p_mensch=0.99):
            c = coach.coache(self.lange_text(), None, 40)
        self.assertTrue(c["ziel_erreicht"])
        self.assertIn("anteil_lange_saetze", {z["id"] for z in c["menschlicher_als_typisch"]})
        self.assertIn("Menschlicher als typisch", coach.bericht(c))

    def test_feld_der_messseite(self):
        echt = coach.analyse.analysiere_und_bewerte

        def fake(*a, **k):
            erg, bew = echt(*a, **k)
            for z in bew["kennzahlen"]:
                z["jenseits_band"] = z["id"] == "konnektoren_pro_1000"
            return erg, bew
        with mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake):
            c = coach.coache(FUELL, None, 15)
        self.assertEqual([z["id"] for z in c["menschlicher_als_typisch"]], ["konnektoren_pro_1000"])

    def test_teilen_bei_ueberkorrektur_aus_coach_auftraegen(self):
        verlauf = {"messungen": [{"score": 40, "p_mensch": 0.01, "kennzahlen": {},
                                  "roh": {"anteil_lange_saetze": 0.05, "satzlaenge_mittel": 18.5, "anteil_mittlere_saetze": 0.62},
                                  "hinweise": [{"typ": "buendeln", "anfang": "satz der nicht mehr da ist", "satz": 2}]}]}
        c = coach.coache(self.lange_text(), verlauf, 40, roh=True)
        self.assertTrue([h for h in c["hinweise_roh"] if h["typ"] == "teilen"])
        # derselbe Verlauf ohne befolgten Coach-Auftrag: die langen Sätze stammen vom Nutzer – kein Gegenauftrag
        verlauf["messungen"][0]["hinweise"] = []
        c = coach.coache(self.lange_text(), verlauf, 40, roh=True)
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "teilen"])

    def test_ueberkorrektur_warnung_am_ziel_erst_jenseits_p90(self):
        r = TS["metriken"]["anteil_lange_saetze"]["mensch"]
        gelb = (r["p75"] + r["p90"]) / 2
        verlauf = {"messungen": [{"score": 60, "p_mensch": 0.95, "kennzahlen": {},
                                  "roh": {"anteil_lange_saetze": r["p50"] - 0.08, "satzlaenge_mittel": 19.0}}]}
        with bewertung_setzen(score=95, score_ki=95, p_mensch=0.99):
            c = coach.coache(KI_TEXT, verlauf, 15)
        L = SimpleNamespace(ref=TS["metriken"])
        self.assertTrue(c["ziel_erreicht"])
        for u in c["fortschritt"]["ueberkorrektur"]:
            self.assertEqual(coach.status_von(u["wert"], L.ref[u["id"]]), "rot", u)
        self.assertLess(gelb, r["p90"])


class Zitatschutz(unittest.TestCase):
    def masken(self, text):
        s = saetze_von(text)
        return s, coach.zitat_masken(s)

    def test_verschachtelte_guillemets(self):
        text = ("Die Befragte sagte dazu: »Am Ende zählt nur eins, ich sage immer: »Durchhalten«. So ist es eben.« Danach folgte eine "
                "längere Pause im Gespräch mit der Interviewerin.")
        s, m = self.masken(text)
        letzter = s[-1]
        self.assertIn("Danach folgte", m[letzter["nr"]])  # eigener Text nach dem äußeren Schließer bleibt frei
        zitat_satz = next(x for x in s if x["text"].startswith("So ist es"))
        self.assertNotIn("So ist", m[zitat_satz["nr"]])  # Rest des äußeren Zitats bleibt maskiert

    def test_franzoesische_richtung(self):
        text = "Der Autor nennt das «eine stille Revolution in der Verwaltung» und bleibt bei dieser Einschätzung für die Region."
        s, m = self.masken(text)
        self.assertNotIn("stille", m[s[0]["nr"]])
        self.assertIn("bleibt bei dieser", m[s[0]["nr"]])

    def test_quellenklammer_gehoert_zum_zitat(self):
        text = ("Eine Lehrkraft fasste es so: »Wir wollen, dass alle mitkommen.« [Interview 3, Absatz 4] Danach änderte die Schule "
                "ihr Konzept für den Förderunterricht im folgenden Jahr.")
        s, m = self.masken(text)
        folge = s[-1]
        self.assertTrue(m[folge["nr"]].startswith(coach.MASKE))  # Beleg maskiert …
        self.assertGreater(coach.fuehrende_quelle(folge["text"]), 0)
        self.assertTrue(coach.anfang(folge["text"]).startswith("Danach änderte"))  # … und in der Anzeige übersprungen
        L = SimpleNamespace(masken=m)
        self.assertFalse(coach.Lauf.beginnt_im_zitat(L, folge))  # eigener Satzanfang, kein Zitatanfang

    def test_regression_fhws_interviewzitat(self):
        text = FHWS_ABSATZ + "\n\n" + FUELL
        s, m = self.masken(text)
        def satz_mit(anf):
            return next(x for x in s if x["text"].lstrip("»").startswith(anf))
        for anf in ("Und so ist es ganz klar", "Ja und unsere Angebote"):  # S10–S11: Interviewzitat, ganz maskiert
            x = satz_mit(anf)
            self.assertNotRegex(m[x["nr"]], r"[A-Za-zÄÖÜäöü]{3}", anf)
        for anf in ("Unter Studienerfolg verstanden", "So wurde das Studium"):  # eigener Text der Autorin (v6: fälschlich gesperrt)
            x = satz_mit(anf)
            self.assertIn(anf.split()[-1], m[x["nr"]])
        # v7.1: der Absatz gendert durchgehend (3 Stämme) – ohne ausdrückliche Wahl käme eine Rückfrage statt der Einzelaufträge;
        # hier ist die Vorgabe bestätigt, geprüft wird der Zitatschutz der Einzelaufträge
        c = coach.coache(text, None, 40, roh=True, vorgaben="gender,gedankenstrich")
        zitat_nrn = {satz_mit(a)["nr"] for a in ("Und so ist es ganz klar", "Ja und unsere Angebote")}
        for h in c["hinweise_roh"]:
            nrn = set(h.get("saetze") or []) | ({h["satz"]} if h.get("satz") else set())
            self.assertFalse(nrn & zitat_nrn, h["text"])
        # „Lehrenden“ im eigenen Text (S8) bekommt die Vorgabe, nie „Lehrer“
        g = [h for h in c["vorgaben"] if h["typ"] == "gender" and "Lehrend" in h["text"]]
        self.assertTrue(g)
        self.assertNotIn("→ „Lehrer“", g[0]["text"])
        self.assertIn(satz_mit("Unter Studienerfolg verstanden")["nr"], g[0]["saetze"])


class Bereinigung(unittest.TestCase):
    TEXT = ("Auf der Grundlage dieses Modells überprüfte die Autorin mittels Strukturgleichungsmodell,wiesichdieHZB-Note,"
            "dieStudienwahlmotive und das soziale Klima auf Lernschwierigkeiten auswirken. Die Haltungen wurden ebenfalls "
            "erfasst.Merkmale des Studienerfolgs sind den drei Phasen des Studiums zugeordnet.\n\n" + FUELL)

    def test_erster_auftrag_und_hinweis(self):
        c = coach.coache(self.TEXT, None, 15)
        self.assertEqual(c["hinweise"][0]["typ"], "bereinigung")
        self.assertIn("Verklebte Wörter trennen (verzerrt die Messung)", c["hinweise"][0]["text"])
        self.assertIn("erfasst.Merkmale", c["hinweise"][0]["text"])
        b = coach.bericht(c)
        self.assertIn("übrigen Messwerte unsicher", b)
        self.assertLess(b.index("Verklebte Wörter trennen"), b.index("Formuliere die Stellen"))

    def test_zweite_runde_bleibt_vorn(self):
        c1 = coach.coache(self.TEXT, None, 15)
        c2 = coach.coache(self.TEXT, {"messungen": [c1["stand"]]}, 15)
        self.assertEqual(c2["hinweise"][0]["typ"], "bereinigung")
        self.assertIn("noch offen", c2["hinweise"][0]["text"])
        self.assertNotIn("überspringen", c2["hinweise"][0]["text"])

    def test_rueckfall_gleiche_regel(self):
        s = [{"nr": 1, "text": "Die Daten wurden erfasst.Merkmale und z.B. die Note bzw.Lage, www.beispiel.de sowie 14:30Uhr."}]
        stellen = [x["stelle"] for x in coach.verklebte_stellen(s)]
        self.assertEqual(stellen, ["erfasst.Merkmale"])

    def test_feld_der_messseite(self):
        echt = coach.analyse.analysiere_und_bewerte

        def fake(*a, **k):
            erg, bew = echt(*a, **k)
            erg["info"]["verklebt"] = [{"stelle": "undblöcken", "satz": 2}]
            return erg, bew
        with mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake):
            c = coach.coache(FUELL, None, 15)
        self.assertIn("„undblöcken“ (S2)", c["hinweise"][0]["text"])

    def test_hoher_zitatanteil(self):
        zitat = ("Die Befragte sagte: „Wir haben die Arbeit in kleinen Gruppen geteilt, weil die Zeit knapp war und jeder etwas "
                 "beitragen wollte, und am Ende hat jeder seinen Teil gut gemacht, so dass das Projekt pünktlich fertig wurde und "
                 "alle zufrieden waren, auch die Leitung der Schule und die Eltern der Kinder in der Klasse.“")
        text = "\n\n".join([zitat] * 3 + [gleichmaessig(2, 5)])
        c = coach.coache(text, None, 15)
        self.assertGreaterEqual(c["zitat_anteil"], coach.ZITAT_ANTEIL_HOCH)
        self.assertIn("% wörtliche Zitate – Messung nur bedingt aussagekräftig", coach.bericht(c))


class Auftragsgrenze(unittest.TestCase):
    def test_messunsicherheit_hoechstens_ein_auftrag(self):
        with bewertung_setzen(score=80, score_ki=80, p_mensch=round(ZIEL_P - 0.005, 3)):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertIsNotNone(c["messunsicherheit"])
        self.assertLessEqual(len([h for h in c["hinweise"] if h["typ"] != "bereinigung"]), 1)
        self.assertIn("im Bereich der Messunsicherheit", coach.bericht(c))
        self.assertIsNone(c["diagnose"])
        # Score bis 1 Punkt unter dem Ziel zählt ebenso
        with bewertung_setzen(score=56, score_ki=56, ziel_score_ki=56.4, p_mensch=0.99):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertIsNotNone(c["messunsicherheit"])

    def test_kleine_luecke_hoechstens_zwei(self):
        # p knapp unter dem Ziel (Lücke < 0,02), Score deutlich darunter: höchstens zwei Modell-Aufträge plus Score-Hebel
        with bewertung_setzen(score=40, score_ki=40, p_mensch=round(ZIEL_P - 0.01, 3)):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertIsNone(c["messunsicherheit"])
        grenze = c["auftragsgrenze"]
        self.assertIsNotNone(grenze)
        self.assertLessEqual(grenze["gewaehlt"], coach.KLEINE_LUECKE_MAX)

    def test_netto_reihenfolge_und_summe(self):
        # nur Modell-Lücke (Score erreicht): Aufträge nach Netto-Wirkung bis zum 1,5-Fachen der Lücke
        with bewertung_setzen(p_mensch=0.80, score=90, score_ki=90):
            c = coach.coache(KI_TEXT, None, 15, roh=True)
        luecke = coach._logit(ZIEL_P) - coach._logit(0.80)
        auftr = [h for h in c["hinweise"] if h["typ"] != "bereinigung"]
        self.assertTrue(auftr)
        if c["auftragsgrenze"]:
            # abgebrochen, sobald das 1,5-Fache der Lücke erreicht ist: ohne den kleinsten Auftrag läge die Summe darunter
            netto = sorted(h["netto_logit"] for h in auftr)
            self.assertLess(sum(netto[1:]), coach.NETTO_FAKTOR * luecke + 1e-9)
        for h in auftr:
            self.assertGreaterEqual(h["netto_logit"], -coach.NETTO_TOLERANZ)

    def test_netto_schaedliche_nie(self):
        with bewertung_setzen(p_mensch=0.30):
            c = coach.coache(KI_TEXT, None, 40, roh=True)
        for h in c["hinweise"]:
            if h.get("netto_logit") is not None and h["typ"] != "teilen":
                self.assertGreaterEqual(h["netto_logit"], -coach.NETTO_TOLERANZ, h["text"])

    def test_nebeneffekte_in_der_simulation(self):
        c = coach.coache(KI_TEXT, None, 40, roh=True)
        L = SimpleNamespace(ts=TS, wert=lambda k: TS["metriken"][k]["mensch"]["p50"] if k in TS["metriken"] else None)
        # „um … zu“ → Präpositionalgruppe: „um“ und „zu“ (bei Menschen häufiger) gehen verloren – negativer Funktionswort-Anteil
        d = coach.fw_delta(c_diag(KI_TEXT), TS["fw_profil"], coach.Counter({"um": 1, "zu": 1}), coach.Counter())
        self.assertLess(d, 0)
        # neue kurze Satzklammer senkt das Mittel der Spannen: negativ im Modell
        self.assertLess(coach.modell_delta(L, {"satzklammer_mittel": -0.4}), 0)
        self.assertTrue(any("mattr_100" in (h.get("netto_teile") or {}) for h in c["hinweise_roh"]
                            if h.get("fw_weg") or h.get("fw_dazu")))

    def test_absatz_simulation_trifft_messung(self):
        # gleichmäßige Absätze: die simulierte Netto-Wirkung des Absatz-Auftrags liegt nahe an der gemessenen (Summe der
        # Modellbeiträge nach dem Umsetzen minus vorher)
        text = gleichmaessig_wechsel(8, 5)  # Themenwechsel im Absatz: dort darf geteilt werden (v7-C2)
        c = coach.coache(text, None, 40, roh=True)
        h = next(x for x in c["hinweise_roh"] if x["typ"] in ("absatz_teilen", "absatz_zusammen"))
        self.assertGreater(h["netto_logit"], 0)
        absaetze = {}
        for x in saetze_von(text):
            absaetze.setdefault(x["absatz"], []).append(x)
        neu = []
        for nr in sorted(absaetze):
            liste = absaetze[nr]
            if h["typ"] == "absatz_teilen" and nr == h["absatz"]:
                k = next(i for i, x in enumerate(liste) if x["nr"] == h["satz"])
                neu += [liste[:k], liste[k:]]
            elif h["typ"] == "absatz_zusammen" and nr == h["absatz"] + 1:
                neu[-1] = neu[-1] + liste
            else:
                neu.append(liste)
        text_neu = "\n\n".join(" ".join(x["text"] for x in p) for p in neu)

        def summe(t):
            _e, bew = analyse.analysiere_und_bewerte(t, analyse.lade_muster(), analyse.lade_baselines())
            return sum(b["beitrag"] for b in bew["modell_beitraege"])
        gemessen = summe(text_neu) - summe(text)
        self.assertAlmostEqual(h["netto_logit"], gemessen, delta=max(0.3, 0.35 * abs(gemessen)))


def c_diag(text):
    s = saetze_von(text)
    return coach.fw_diagnose(s, TS["fw_profil"])


class Vorgaben(unittest.TestCase):
    TEXT = ("Die Studierenden der Hochschule bewerten die Lehre im Durchschnitt gut, wie die Befragung im Frühjahr zeigt. Die "
            "Lehrenden achten in den Seminaren stärker auf aktive Beteiligung und geben häufiger Rückmeldung. Viele Absolvierende "
            "finden schnell eine Stelle in der Region – vor allem in kleineren Betrieben, in Verwaltungen und in Schulen. Die "
            "Diskutierenden im Plenum stimmten den Ergebnissen weitgehend zu und forderten mehr Zeit für Projekte.\n\n" + FUELL)

    # v7.1: TEXT gendert durchgehend (4 Stämme) – die Tests der Einzelaufträge setzen die Vorgaben ausdrücklich (bestätigt); die
    # Rückfrage ohne ausdrückliche Wahl prüft test_coach_v71_bericht.VorgabenAbschaltbar
    def test_eigener_abschnitt_nicht_im_limit(self):
        c = coach.coache(self.TEXT, None, 1, vorgaben="gender,gedankenstrich")
        typen = {h["typ"] for h in c["vorgaben"]}
        self.assertTrue({"gender", "gedankenstrich"} <= typen)
        self.assertFalse([h for h in c["hinweise"] if h["typ"] in coach.VORGABE_TYPEN])
        self.assertLessEqual(len([h for h in c["hinweise"] if h["typ"] != "bereinigung"]), 1)
        b = coach.bericht(c)
        self.assertIn("### Vorgaben (ändern den Score nicht)", b)

    def test_zielformen_hochschule(self):
        c = coach.coache(self.TEXT, None, 15, vorgaben="gender,gedankenstrich")
        texte = {h["fund"]: h["text"] for h in c["vorgaben"] if h["typ"] == "gender"}
        self.assertIn("„Studenten“", next(t for f, t in texte.items() if f.startswith("Studierend")))
        self.assertIn("„Absolventen“", next(t for f, t in texte.items() if f.startswith("Absolvierend")))
        lehr = next(t for f, t in texte.items() if f.startswith("Lehrend"))
        # v7.1 (v7-Prüfung, fhws): „Lehrkräfte“ ist kein generisches Maskulinum und klingt nach Schule – nur Dozenten/Hochschullehrer
        self.assertIn("„Dozenten“ bzw. „Hochschullehrer“", lehr)
        self.assertNotIn("→ „Lehrer“", lehr)
        self.assertNotIn("„Lehrkräfte“ oder", lehr)
        disk = next(t for f, t in texte.items() if f.startswith("Diskutierend"))
        self.assertIn("eine passende maskuline Bezeichnung", disk)

    def test_rest_nur_in_zitaten(self):
        text = ("Die Studenten der Hochschule bewerten die Lehre gut. Eine Dozentin sagte dazu: „Unsere Studierenden "
                "arbeiten sehr selbstständig und fragen viel nach.“ Die Studenten nutzen die Bibliothek vor allem am "
                "Abend.\n\n" + FUELL)
        c = coach.coache(text, None, 15)
        self.assertFalse([h for h in c["vorgaben"] if h["typ"] == "gender"])
        self.assertTrue(any("Rest steht in wörtlichen Zitaten" in g for g in c["gender_info"]))
        self.assertIn("so lassen", coach.bericht(c))

    def test_gedankenstrich_nach_funktion(self):
        self.assertIn("Klammern oder zwischen Kommas", coach.strich_technik("Die Lage hat – wie oben angeführt – sich verändert."))
        self.assertIn("Doppelpunkt", coach.strich_technik(
            "Dafür wurden zwei Städte ausgewählt – einerseits Amsterdam, in der Konsum erlaubt ist, sowie San Francisco."))
        self.assertIn("Komma oder einen neuen Satz", coach.strich_technik("Die Kosten steigen – das belastet die Betriebe stark."))

    def test_diagnose_zaehlt_vorgaben_nicht(self):
        with bewertung_setzen(p_mensch=0.2):
            c = coach.coache(self.TEXT, None, 15)
        if c["diagnose"]:
            self.assertEqual(c["diagnose"]["umsetzbar"], len([h for h in c["hinweise"] if not h.get("schon_genannt")
                                                              and h["hebel"] != "vorgaben" and h["typ"] != "bereinigung"]))


class Sperren(unittest.TestCase):
    def typen_an(self, text, satz_anfang, roh=True):
        c = coach.coache(text, None, 40, roh=roh)
        s = next(x for x in saetze_von(text) if x["text"].startswith(satz_anfang))
        return {h["typ"] for h in c["hinweise_roh"] if h.get("satz") == s["nr"]}, c, s

    def test_gegenfolie_quelle_und_konjunktiv_stehen_lassen(self):
        text = ("Auch gäbe es keinen Beweis für einen Anstieg der Konsumraten durch die Gesetzesänderung im Jahr 1976. Zwar hätte es "
                "einen Anstieg der Lebenszeitprävalenz gegeben, allerdings sehen Experten den Grund für den Anstieg nicht in der "
                "Gesetzesänderung von 1976, sondern in der Ausweitung der kommerziellen Werbung in den Coffeeshops.\n\n" + FUELL)
        typen, c, s = self.typen_an(text, "Zwar hätte es")
        self.assertNotIn("gegenfolie", typen)
        self.assertIn(s["nr"], [x["satz"] for x in c["stehen_lassen"]])

    def test_konnektor_im_korrelat(self):
        self.assertTrue(coach.KORRELAT_VOR_RE.search("Der Abbau hat jedoch nicht nur die Entwicklung beeinflusst, er hat "))
        self.assertTrue(coach.KORRELAT_VOR_RE.search("Zwar steigen die Kosten, "))
        self.assertFalse(coach.KORRELAT_VOR_RE.search("Die Kosten steigen, "))

    def test_konnektor_hebeltext_nur_vorhandene(self):
        t = coach.hebel_warum("konnektoren", TS["metriken"], vorhanden={"zudem"})
        self.assertIn("„zudem“", t)
        self.assertNotIn("„zugleich“", t)
        self.assertNotIn("„hingegen“", t)

    def test_laesst_sich_leicht_und_koordiniert(self):
        def gesperrt(satz):
            t = coach.LASSEN_SICH_RE.search(satz)
            return coach.lassen_gesperrt(satz, t)
        self.assertTrue(gesperrt("HTML lässt sich über Beautiful Soup ziemlich einfach verarbeiten."))
        self.assertTrue(gesperrt("Die Daten lassen sich sammeln und anschließend auswerten."))
        self.assertTrue(gesperrt("Das Verfahren lässt sich kaum übertragen."))
        self.assertFalse(gesperrt("Die Abweichung lässt sich auf Lieferengpässe zurückführen."))

    def test_um_zu_nur_mit_ung_form(self):
        self.assertFalse(coach.um_zu_nominalisierbar(" den Platz zu entsprechen."))
        self.assertFalse(coach.um_zu_nominalisierbar(" dem Anspruch gerecht zu werden."))
        self.assertTrue(coach.um_zu_nominalisierbar(" die Qualität der Lehre zu verbessern."))
        self.assertTrue(coach.um_zu_nominalisierbar(" die Abläufe sicherzustellen."))
        self.assertTrue(coach.um_zu_nominalisierbar(" die Prozesse zu optimieren."))

    def test_anknuepfung_subjekt_am_satzanfang(self):
        text = ("Die Hypothesen stammen überwiegend aus eigener Überlegung und aus der Literatur. Sie beschäftigen sich mit den "
                "Metadaten der Videos und mit ihrer Platzierung in der Trendliste.\n\n" + FUELL)
        typen, c, _s = self.typen_an(text, "Sie beschäftigen")
        self.assertNotIn("anknuepfung", typen)
        self.assertTrue(coach.vorfeld("Die Hypothesen stammen überwiegend aus eigener Überlegung."))
        self.assertIsNone(coach.vorfeld("Und"))

    def test_vorfeld_mit_attributsatz(self):
        self.assertIsNone(coach.vorfeld_angabe("Neben den eigentlichen Fragestellungen für die Auswertung wird die Grundlage "
                                               "aufgestellt, wie auf die Hypothesen geschlossen wurde."))


class Semikolon(unittest.TestCase):
    def test_komma_bei_aufzaehlung(self):
        self.assertIn("Komma", coach.semikolon_technik(
            "Sie behandeln die Trends, sowie einen Einfluss auf Videos; der Zusammensetzung der Kommentare und wie Schreiber "
            "die Videos bewerten."))
        self.assertIn("Punkt", coach.semikolon_technik("Die Zahl ist niedrig; der Anteil der Personen sei einer der niedrigsten."))

    def text(self, n):
        saetze = [f"Die Firma plant neue Wege für die Arbeit im Team; die Leitung prüft die Kosten Nummer {i} genau." for i in range(n)]
        return " ".join(saetze) + "\n\n" + FUELL

    def test_hysterese_nur_wortzahl(self):
        text = self.text(2)
        c1 = coach.coache(text, None, 15)
        alt = dict(c1["stand"], kennzahlen=dict(c1["stand"]["kennzahlen"]))
        alt["kennzahlen"]["semikolon_pro_1000"] = {"wert": 0.1, "status": "gruen"}  # Status-Kipp ohne neues Semikolon
        c2 = coach.coache(text, {"messungen": [alt]}, 15)
        self.assertNotIn("semikolon_pro_1000", c2["fortschritt"]["schlechter"])

    def test_am_ziel_nur_bei_anstieg(self):
        text = self.text(3)
        with bewertung_setzen(score=95, score_ki=95, p_mensch=0.99):
            c = coach.coache(text, None, 15)
            self.assertFalse([h for h in c["hinweise"] if h["typ"] == "semikolon"])
            v = {"messungen": [dict(c["stand"], zaehler={"semikolon": 1})]}
            c2 = coach.coache(text, v, 15)
        self.assertTrue([h for h in c2["hinweise"] if h["typ"] == "semikolon"])
        self.assertLessEqual(len([h for h in c2["hinweise"] if h["typ"] == "semikolon"]), 2)

    def test_anzeige(self):
        self.assertIn("höchstens 1–2 je 800 Wörter", coach.SELBSTHILFE_HEBEL["semikolon"])
        c = {"bewertung": {"verfuegbar": True, "score": 50, "p_mensch": 0.5}, "info": {"woerter": 800, "saetze": 40, "absaetze": 6,
             "warnungen": []}, "rot": 1, "ziel_erreicht": False, "ziel_p_mensch": 0.86, "ziel_score": 56.4,
             "hebel": [{"id": "semikolon", "name": "Semikolons ersetzen", "warum": "…", "stellenlos": False,
                        "kennzahlen": [{"id": "semikolon_pro_1000", "name": "Semikolons pro 1000", "wert": 4.2, "bewertet": True,
                                        "status": "rot", "mensch_p25": 0.0, "mensch_p75": 0.0}]}],
             "hinweise": [], "anzahl_hinweise_gesamt": 0, "gut": [], "blockmodus": False, "bloecke": []}
        self.assertIn("Ziel: höchstens 1–2 je 800 Wörter", coach.bericht(c))


class Erwartet(unittest.TestCase):
    def test_verlauf_enthaelt_erwartete_formen(self):
        text = Vorgaben.TEXT
        c = coach.coache(text, None, 15, vorgaben="gender,gedankenstrich")  # v7.1: Vorgabe bestätigt (Text gendert durchgehend)
        self.assertIn("studenten", c["stand"]["erwartet"])
        self.assertIn("absolventen", c["stand"]["erwartet"])
        self.assertIn("dozenten", c["stand"]["erwartet"])
        self.assertNotIn("lehrer", c["stand"]["erwartet"])

    def test_main_schreibt_erwartet(self):
        with tempfile.TemporaryDirectory() as d:
            p, v = os.path.join(d, "t.md"), os.path.join(d, "t.coach.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write(Vorgaben.TEXT)
            with mock.patch("sys.stdout"):
                coach.main([p, "--verlauf", v, "--vorgaben", "gender,gedankenstrich"])  # v7.1: Vorgabe bestätigt
            with open(v, encoding="utf-8") as f:
                verlauf = json.load(f)
        m = verlauf["messungen"][-1]
        self.assertIn("erwartet", m)
        self.assertIn("studenten", m["erwartet"])
        self.assertIn("zaehler", m)


if __name__ == "__main__":
    unittest.main()
