"""Tests für Coach v7.1, Auftrag A1 (Bericht und Verhalten für eigene Texte), nach den beiden Abschlussprüfungen von v7:

1. Bereinigung + Ziel: kein „Kein weiterer Handlungsbedarf“ neben verklebten Wörtern; Ziel vorab auf einer automatisch getrennten
   Kopie; verklebte Tokens vollständig; „erwartet“ mit den getrennten Wörtern.
2. „rot“ im Kopf nur auf der KI-Seite (Gegenseite „menschlicher als typisch“); am Ziel „Normale Streuung, kein Auftrag“.
3. Eine Schwelle: reichen die angezeigten Aufträge simuliert (≥ 1,0 × Lücke), keine Orientierung und nur eine Diagnose-Zeile.
4. Orientierung ohne „Wortwahl“ (außer kurze Wörter auf der KI-Seite) und ohne ausgesetzte Techniken; „Weniger Nebensätze“.
5. Grundcode der Funktionswort-Sperren („gemeint ist eine Möglichkeit: ‚ziemlich einfach‘“ statt „Aussage einer Quelle“);
   „keine umbaubare Konstruktion mehr“ nur ohne gesperrte Konstruktion.
6. Blockmodus: „Hinweise unten“ nur mit Hinweisen; Abschnitte unter dem Ziel ausdrücklich nennen.
7. Vorgaben abschaltbar (--vorgaben, coache(vorgaben=…)), Rückfrage bei durchgehend genderndem Text, „Lehrende“ → „Dozenten“
   bzw. „Hochschullehrer“, Zeile „Vorgaben gelten unabhängig vom Ziel“.
8. „knapp – nach weiteren Änderungen neu messen“.
9. Verlauf: ziel_erreicht, score_beidseitig, score_ziel, auftraege; „score“ unverändert; „beidseitig“ nur als Klammer-Info.

Synthetische Texte; Felder der Messseite werden, wo nötig, per Mock gesetzt (wie test_coach_v7.bewertung_setzen).

python3 -m unittest discover -s tests
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
from test_coach import KI_TEXT  # noqa: E402
from test_coach_v7 import FUELL, ZIEL_P, bewertung_setzen  # noqa: E402
from test_coach_wirksamkeit import gleichmaessig  # noqa: E402

TS = analyse.lade_baselines()["textsorten"]["hochschule"]
ZIEL_KI = TS.get("ziel_score_ki") or 73.2
VERKLEBT_LANG = "Strukturgleichungsmodell,wiesichdieHZB-Note,dieStudienwahlmotive,dieInformiertheitvorStudienbeginn"
VERKLEBT_TEXT = (f"Auf der Grundlage dieses Modells überprüfte die Autorin mittels {VERKLEBT_LANG}, der Leistungsdruck und das "
                 "soziale Klima auf Lernschwierigkeiten auswirken. Die Haltungen wurden ebenfalls erfasst.Merkmale des "
                 "Studienerfolgs sind den drei Phasen des Studiums zugeordnet.\n\n" + FUELL)
GENDER_TEXT = ("Die Studierenden der Hochschule bewerten die Lehre im Durchschnitt gut, wie die Befragung im Frühjahr zeigt. Die "
               "Lehrenden achten in den Seminaren stärker auf aktive Beteiligung und geben häufiger Rückmeldung. Viele Absolvierende "
               "finden schnell eine Stelle in der Region, vor allem in kleineren Betrieben, in Verwaltungen und in Schulen.\n\n"
               + FUELL)


def bewertung_je_text(original: dict, getrennt: dict):
    """analysiere_und_bewerte mit anderen Feldern für den Text mit verklebten Wörtern und für die automatisch getrennte Kopie."""
    echt = coach.analyse.analysiere_und_bewerte

    def fake(text, *a, **k):
        erg, bew = echt(text, *a, **k)
        return erg, dict(bew, **(original if "erfasst.Merkmale" in text else getrennt))
    return mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake)


def p_fuer_luecke(luecke_logit: float) -> float:
    """p_mensch, bei dem die Logit-Lücke zum Modellziel genau luecke_logit beträgt."""
    import math
    return 1 / (1 + math.exp(-(coach._logit(ZIEL_P) - luecke_logit)))


# ---------------------------------------------------------------------------
# 1. Bereinigung + Ziel
# ---------------------------------------------------------------------------

class BereinigungUndZiel(unittest.TestCase):
    def test_trenne_verklebt(self):
        self.assertEqual(coach.trenne_verklebt(VERKLEBT_LANG), "Strukturgleichungsmodell, wie sich die HZB-Note, die "
                         "Studienwahlmotive, die Informiertheit vor Studienbeginn")
        self.assertEqual(coach.trenne_verklebt("erfasst.Merkmale"), "erfasst. Merkmale")
        for bleibt in ("undblöcken", "trotzdem", "Mitarbeiter:innen", "Hintergrund", "z.B"):
            self.assertEqual(coach.trenne_verklebt(bleibt), bleibt)

    def test_token_vollstaendig_und_erwartet_getrennt(self):
        c = coach.coache(VERKLEBT_TEXT, None, 15)
        h = c["hinweise"][0]
        self.assertEqual(h["typ"], "bereinigung")
        self.assertIn(f"„{VERKLEBT_LANG}“", h["text"])  # nicht nach 60 Zeichen abgeschnitten
        self.assertNotIn("…“", h["text"])
        erw = c["stand"]["erwartet"]
        for w in ("informiertheit", "studienbeginn", "studienwahlmotive", "merkmale", "erfasst"):
            self.assertIn(w, erw)
        self.assertFalse([w for w in erw if w.endswith("…") or w in ("studienwahlm", "wiesichdie")], erw)
        b = coach.bericht(c)
        self.assertIn(VERKLEBT_LANG, b.split("### Konkrete Stellen")[0])  # Warnung im Kopf ebenfalls vollständig

    def test_gekuerzte_stelle_der_messseite_wird_vervollstaendigt(self):
        echt = coach.analyse.analysiere_und_bewerte

        def fake(*a, **k):
            erg, bew = echt(*a, **k)
            nr = next(s["nr"] for s in erg["saetze"] if VERKLEBT_LANG in s["text"])
            erg["info"]["verklebt"] = [{"stelle": VERKLEBT_LANG[:59] + "…", "satz": nr}]
            return erg, bew
        with mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake):
            c = coach.coache(VERKLEBT_TEXT, None, 15)
        self.assertIn(f"„{VERKLEBT_LANG}“", c["hinweise"][0]["text"])

    def test_sehr_langes_token_mit_endmarke(self):
        lang = VERKLEBT_LANG + ",derLeistungsdruckunddasSozialeKlimaimStudium"
        anz = coach._verklebt_anzeige({"stelle": lang, "getrennt": coach.trenne_verklebt(lang)})
        self.assertTrue(anz.startswith("„" + lang[:50] + "…“ bis „"), anz)
        self.assertTrue(anz.endswith("Studium“"), anz)

    def test_am_ziel_vorlaeufig_ohne_kein_handlungsbedarf(self):
        with bewertung_setzen(score=95, score_ki=95, p_mensch=0.99):
            c = coach.coache(VERKLEBT_TEXT, None, 15)
        self.assertTrue(c["ziel_erreicht"])
        self.assertTrue(c["ziel_vorlaeufig"])
        self.assertIsNotNone(c["ziel_getrennt"])  # vorab auf der getrennten Kopie gerechnet
        b = coach.bericht(c)
        self.assertIn("Ziel erreicht (vorläufig)", b)
        self.assertIn("vorab gerechnet ebenfalls erreicht", b)
        self.assertNotIn("Kein weiterer Handlungsbedarf", b)
        self.assertIn("übrigen Messwerte unsicher", b)

    def test_ziel_erst_nach_dem_trennen(self):
        # verklebt gemessen unter dem Ziel, getrennt vorab gerechnet am Ziel: zuerst trennen, keine Stil-Aufträge auf verzerrten Werten
        with bewertung_je_text({"score": 60, "score_ki": 60, "p_mensch": 0.5}, {"score": 90, "score_ki": 90, "p_mensch": 0.99}):
            c = coach.coache(VERKLEBT_TEXT, None, 15)
        self.assertFalse(c["ziel_gemessen"])
        self.assertTrue(c["ziel_erreicht"])
        self.assertTrue(c["ziel_getrennt"]["ziel_erreicht"])
        self.assertEqual(c["hinweise"][0]["typ"], "bereinigung")
        for h in c["hinweise"][1:]:
            self.assertIn(h["typ"], coach.ZIEL_TYPEN)
        b = coach.bericht(c)
        self.assertIn("Ziel nach dem Trennen (vorab gerechnet) erreicht", b)
        self.assertNotIn("Kein weiterer Handlungsbedarf", b)

    def test_vorlaeufig_aber_getrennt_darunter(self):
        with bewertung_je_text({"score": 90, "score_ki": 90, "p_mensch": 0.99}, {"score": 60, "score_ki": 60, "p_mensch": 0.5}):
            c = coach.coache(VERKLEBT_TEXT, None, 15)
        self.assertTrue(c["ziel_erreicht"])
        self.assertFalse(c["ziel_getrennt"]["ziel_erreicht"])
        b = coach.bericht(c)
        self.assertIn("Ziel vorläufig erreicht", b)
        self.assertIn("läge es vorab gerechnet darunter", b)
        self.assertNotIn("Kein weiterer Handlungsbedarf", b)

    def test_nicht_trennbar_vorlaeufig(self):
        # „undblöcken“ lässt sich nicht automatisch trennen: keine Vorab-Messung, aber trotzdem vorläufig
        echt = coach.analyse.analysiere_und_bewerte

        def fake(*a, **k):
            erg, bew = echt(*a, **k)
            erg["info"]["verklebt"] = [{"stelle": "undblöcken", "satz": 2}]
            return erg, dict(bew, score=95, score_ki=95, p_mensch=0.99)
        with mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake):
            c = coach.coache(FUELL, None, 15)
        self.assertIsNone(c["ziel_getrennt"])
        b = coach.bericht(c)
        self.assertIn("Ziel erreicht (vorläufig – nach dem Trennen neu messen)", b)
        self.assertNotIn("Kein weiterer Handlungsbedarf", b)

    def test_ohne_verklebte_woerter_unveraendert(self):
        with bewertung_setzen(score=95, score_ki=95, p_mensch=0.99):
            c = coach.coache(FUELL, None, 15)
        self.assertFalse(c["ziel_vorlaeufig"])
        self.assertIsNone(c["ziel_getrennt"])
        self.assertIn("Kein weiterer Handlungsbedarf", coach.bericht(c))


# ---------------------------------------------------------------------------
# 2. Rot-Zählung im Kopf, normale Streuung am Ziel
# ---------------------------------------------------------------------------

class RotNurKiSeite(unittest.TestCase):
    def test_zaehlung_nach_seite(self):
        c = coach.coache(KI_TEXT, None, 15)
        L = coach.Lauf(KI_TEXT, None)
        rot = [z for z in L.bew["kennzahlen"] if z["bewertet"] and z["status"] == "rot"]
        gegen = [z for z in rot if L.kz[z["id"]]["seite"] == "gegen"]
        self.assertEqual(c["rot"], len(rot) - len(gegen))
        self.assertEqual(c["rot_gegen"], len(gegen))
        kopf = coach.bericht(c).split("\n")[2]
        self.assertIn(f"{c['rot']} Kennzahl", kopf)
        self.assertIn("(KI-Seite", kopf)
        if gegen:
            self.assertIn(f"dazu {len(gegen)} menschlicher als typisch", kopf)

    def test_normale_streuung_am_ziel(self):
        with bewertung_setzen(score=95, score_ki=95, p_mensch=0.99):
            c = coach.coache(KI_TEXT, None, 15)
            L = coach.Lauf(KI_TEXT, None)
        ki_rot = {z["id"] for z in L.bew["kennzahlen"] if z["bewertet"] and z["status"] == "rot" and L.kz[z["id"]]["seite"] != "gegen"}
        self.assertTrue(c["normale_streuung"])
        ids = {z["id"] for z in c["normale_streuung"]}
        self.assertLessEqual(ids, ki_rot)
        hebel_mit_auftrag = {h["hebel"] for h in c["hinweise"]}
        self.assertFalse({coach.HEBEL_VON.get(i) for i in ids} & hebel_mit_auftrag)
        self.assertIn("Normale Streuung, kein Auftrag", coach.bericht(c))

    def test_keine_streuungszeile_unter_dem_ziel(self):
        c = coach.coache(KI_TEXT, None, 15)
        self.assertFalse(c["ziel_erreicht"])
        self.assertEqual(c["normale_streuung"], [])
        self.assertNotIn("Normale Streuung", coach.bericht(c))


# ---------------------------------------------------------------------------
# 3. Eine Schwelle
# ---------------------------------------------------------------------------

def netto_nur_ein_auftrag(wert: float):
    """netto_wirkung: der erste bewertete Auftrag bringt `wert`, alle übrigen schaden (fallen weg) – genau ein Auftrag bleibt."""
    erster = {}

    def fake(L, h):
        if not erster or erster["h"] is h:
            erster["h"] = h
            return wert, {"x": wert}
        return -0.5, {}
    return mock.patch.object(coach, "netto_wirkung", fake)


class EineSchwelle(unittest.TestCase):
    def test_reicht_ab_dem_einfachen_der_luecke(self):
        # Lücke 0,25, ein Auftrag mit 0,30: unter dem 1,5-Fachen (keine Auswahl nötig), aber über dem Einfachen → reicht
        with bewertung_setzen(score=95, score_ki=95, p_mensch=round(p_fuer_luecke(0.25), 4)), netto_nur_ein_auftrag(0.30):
            c = coach.coache(KI_TEXT, None, 15)
        stil = [h for h in c["hinweise"] if h["typ"] != "bereinigung"]
        self.assertEqual(len(stil), 1)
        self.assertTrue(c["auftragsgrenze"]["reicht"])
        self.assertIsNone(c["diagnose"])
        b = coach.bericht(c)
        self.assertIn("Der Auftrag reicht rechnerisch", b)
        self.assertIn("danach neu messen", b)
        self.assertNotIn("zur Orientierung", b)
        self.assertNotIn("### Warum das Modellziel", b)

    def test_reicht_nicht_unter_dem_einfachen(self):
        with bewertung_setzen(score=95, score_ki=95, p_mensch=round(p_fuer_luecke(0.6), 4)), netto_nur_ein_auftrag(0.30):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertFalse((c["auftragsgrenze"] or {}).get("reicht"))
        self.assertNotIn("reicht rechnerisch (vorab gerechnet", coach.bericht(c))

    def test_auswahl_behaelt_die_marge(self):
        self.assertEqual(coach.NETTO_FAKTOR, 1.5)
        self.assertEqual(coach.REICHT_FAKTOR, 1.0)


# ---------------------------------------------------------------------------
# 4. Orientierung
# ---------------------------------------------------------------------------

class Orientierung(unittest.TestCase):
    def setUp(self):
        self.L = coach.Lauf(KI_TEXT, None)

    def test_wortwahl_nur_mit_kurzen_woertern_auf_ki_seite(self):
        L = self.L
        L.kz["anteil_kurze_woerter"] = dict(L.kz["anteil_kurze_woerter"], status="gruen", seite="gegen")
        self.assertFalse(coach.orientierung_erlaubt(L, "wortwahl"))
        L.kz["anteil_kurze_woerter"] = dict(L.kz["anteil_kurze_woerter"], status="rot", seite="ki", unsicher=False)
        self.assertTrue(coach.orientierung_erlaubt(L, "wortwahl"))

    def test_ausgesetzte_technik_keine_orientierung(self):
        L = self.L
        self.assertTrue(coach.orientierung_erlaubt(L, "nebensaetze"))
        L.setze_aus({"nebensatz"}, "Nominalstil schon über P90")
        self.assertFalse(coach.orientierung_erlaubt(L, "nebensaetze"))
        L.setze_aus({"buendeln", "klammer"}, "Nominalstil schon über P90")
        self.assertFalse(coach.orientierung_erlaubt(L, "satzlaenge"))
        self.assertFalse(coach.orientierung_erlaubt(L, "satzklammer"))

    def test_titel_weniger_nebensaetze(self):
        L = self.L
        L.kz["woerter_pro_teilsatz"] = dict(L.kz["woerter_pro_teilsatz"], status="gruen")
        self.assertEqual(coach.hebel_name(L, "nebensaetze"), "Weniger Nebensätze")
        L.kz["woerter_pro_teilsatz"] = dict(L.kz["woerter_pro_teilsatz"], status="rot", seite="ki")
        self.assertEqual(coach.hebel_name(L, "nebensaetze"), "Weniger Nebensätze, längere Teilsätze")

    def test_bericht_filtert_orientierung(self):
        def hebel(id_, name, erlaubt):
            return {"id": id_, "name": name, "warum": "…", "stellenlos": True, "orientierung": erlaubt, "selbsthilfe": f"Technik {id_}",
                    "kennzahlen": [{"id": "x", "name": "x", "wert": 1.0, "status": "rot", "bewertet": True}]}
        c = {"bewertung": {"verfuegbar": True, "score": 50, "p_mensch": 0.5}, "info": {"woerter": 800, "saetze": 40, "absaetze": 6,
             "warnungen": []}, "rot": 2, "ziel_erreicht": False, "ziel_p_mensch": 0.85, "ziel_score": 73.2,
             "hebel": [hebel("wortwahl", "Wortwahl einfacher und natürlicher", False),
                       hebel("nebensaetze", "Weniger Nebensätze", False), hebel("absaetze", "Absätze ungleich lang machen", True)],
             "hinweise": [], "anzahl_hinweise_gesamt": 0, "gut": [], "blockmodus": False, "bloecke": []}
        b = coach.bericht(c)
        self.assertIn("Technik absaetze", b)
        self.assertNotIn("Wortwahl einfacher", b)
        self.assertNotIn("Technik nebensaetze", b)

    def test_coache_ohne_widerspruch(self):
        for text in (KI_TEXT, gleichmaessig(8, 5)):
            c = coach.coache(text, None, 15)
            aus = set(c["ausgesetzt"])
            for h in c["hebel"]:
                if h.get("orientierung"):
                    typen = coach.SELBSTHILFE_TYPEN.get(h["id"])
                    self.assertFalse(typen and typen <= aus, h["id"])
                if h["id"] == "wortwahl" and h.get("orientierung"):
                    L = coach.Lauf(text, None)
                    self.assertTrue(L.ki_auffaellig("anteil_kurze_woerter"))


# ---------------------------------------------------------------------------
# 5. Begründungen der Funktionswort-Sperren
# ---------------------------------------------------------------------------

LEICHT_TEXT = ("Für die Auswertung wurden die Seiten heruntergeladen. HTML lässt sich über Pythons Beautiful Soup ziemlich einfach "
               "verarbeiten und die Inhalte lassen sich gut herausziehen. Die Ergebnisse wurden danach in einer Tabelle gesammelt.\n\n"
               + FUELL)


class FunktionswortGruende(unittest.TestCase):
    def setUp(self):
        self.L = coach.Lauf(LEICHT_TEXT, None)
        self.s = next(s for s in self.L.saetze if s["text"].startswith("HTML"))
        self.mk = self.L.masken[self.s["nr"]]
        self.t = coach.LASSEN_SICH_RE.search(self.mk)

    def test_grundcode_leichtigkeitsadverb(self):
        bilanz, grund = coach._fw_bilanz(self.L, "laesst_sich", self.s, self.mk, self.t, mit_grund=True)
        self.assertIsNone(bilanz)
        self.assertEqual(grund, ("leicht_adverb", "ziemlich einfach"))
        self.assertIsNone(coach._fw_bilanz(self.L, "laesst_sich", self.s, self.mk, self.t))  # alte Schnittstelle unverändert
        text = coach.fw_sperrgrund_text(*grund)
        self.assertIn("gemeint ist eine Möglichkeit: „ziemlich einfach“", text)
        self.assertNotIn("Quelle", text)

    def test_stellenliste_nennt_den_richtigen_grund(self):
        self.assertIn("sich", coach.fw_uebernutzt(self.L))
        st = coach.fw_stellen(self.L, ["sich"])["sich"]
        kat = [k for k in st["notwendig"] if k.startswith("„lässt sich“")]
        self.assertTrue(kat, st)
        self.assertIn("gemeint ist eine Möglichkeit", kat[0])
        self.assertNotIn("Aussage einer Quelle", kat[0])

    def test_gilt_als_zuschreibung_und_quelle(self):
        L = coach.Lauf("Ein Unternehmen gilt laut EU als klein, wenn es weniger Beschäftigte hat. Die Beratung gilt als teuer "
                       "und aufwendig für kleine Betriebe.\n\n" + FUELL, None)
        s, s2 = L.saetze[0], L.saetze[1]
        mk, mk2 = L.masken[s["nr"]], L.masken[s2["nr"]]
        self.assertEqual(coach._fw_bilanz(L, "gilt_als", s, mk, coach.GILT_ALS_RE.search(mk), mit_grund=True)[1][0], "zuschreibung")
        L.quelle[s2["nr"]] = True  # Einschätzung einer Quelle
        self.assertEqual(coach._fw_bilanz(L, "gilt_als", s2, mk2, coach.GILT_ALS_RE.search(mk2), mit_grund=True)[1][0], "quelle")
        L.quelle[s2["nr"]] = False
        bilanz, grund = coach._fw_bilanz(L, "gilt_als", s2, mk2, coach.GILT_ALS_RE.search(mk2), mit_grund=True)
        self.assertIsNotNone(bilanz)
        self.assertIsNone(grund)

    def test_gesperrte_statt_keine_konstruktion(self):
        # „lässt sich … ziemlich einfach“ ist nicht umbaubar (Möglichkeit) – keine Sperre dieser Runde, also „keine mehr“ bleibt wahr
        self.assertFalse([g for g in coach.fw_gesperrt(self.L) if g.startswith(f"S{self.s['nr']} ")])
        # eine umbaubare Konstruktion, die nur diese Runde gesperrt ist (Hedging hoch bzw. Typ ausgesetzt): mit Satz und Grund nennen
        L = coach.Lauf("Die Antworten lassen sich in drei Gruppen einteilen. Die Gruppen wurden danach getrennt ausgewertet.\n\n"
                       + FUELL, None)
        s = L.saetze[0]
        self.assertFalse([g for g in coach.fw_gesperrt(L) if g.startswith(f"S{s['nr']} ")])
        L.kz["hedging_pro_1000"] = dict(L.kz["hedging_pro_1000"], wert=L.kz["hedging_pro_1000"]["mensch_p75"] + 5)
        gesp = [g for g in coach.fw_gesperrt(L) if g.startswith(f"S{s['nr']} ")]
        self.assertEqual(gesp, [f"S{s['nr']} „lässt sich“ (Hedging ist schon hoch)"])
        txt = coach.fw_keine_konstruktion(L)
        self.assertNotIn("im Text keine umbaubare Konstruktion mehr", txt)
        self.assertIn(f"gesperrt: S{s['nr']} „lässt sich“ (Hedging ist schon hoch)", txt)
        L.kz["hedging_pro_1000"] = dict(L.kz["hedging_pro_1000"], wert=0.0)
        L.setze_aus({"fw_lassen"}, "test")
        self.assertIn(f"S{s['nr']} „lässt sich“ (diese Runde ausgesetzt)", coach.fw_gesperrt(L))
        # ohne gesperrte Konstruktion bleibt der alte Text
        ohne = coach.Lauf(FUELL, None)
        self.assertEqual(coach.fw_gesperrt(ohne), [])
        self.assertEqual(coach.fw_keine_konstruktion(ohne), coach.FW_KEINE_KONSTRUKTION)

    def test_diagnose_nennt_gesperrte(self):
        d = {"p_mensch": 0.5, "ziel_p_mensch": 0.85, "beitraege": [
            {"id": "fw_profil_llr_pro_1000", "name": "Funktionswort-Profil", "beitrag": -1.2, "erreichbar": 0.0, "erreichbar_logit": 0.0,
             "potenzial_logit": 0.0, "rest_logit": 0.0, "wie": "keine_konstruktion"}],
            "luecke_logit": 1.7, "erreichbar_logit": 0.0, "stellenlos_logit": 0.0, "grenze": "einzelkorrekturen", "realistisch": False,
            "fw_gesperrt": ["S43 „lässt sich“ (gemeint ist eine Möglichkeit: „ziemlich einfach“)"]}
        txt = "\n".join(coach.diagnose_text(d))
        self.assertIn("gesperrt: S43 „lässt sich“", txt)
        self.assertNotIn("im Text keine umbaubare Konstruktion mehr", txt)
        d["fw_gesperrt"] = []
        self.assertIn("im Text keine umbaubare Konstruktion mehr", "\n".join(coach.diagnose_text(d)))


# ---------------------------------------------------------------------------
# 6. Blockmodus
# ---------------------------------------------------------------------------

def block_c(hinweise, unter_ziel=None, ziel=True):
    return {"bewertung": {"verfuegbar": True, "score": 77, "score_ki": 82, "p_mensch": 0.86},
            "info": {"woerter": 2400, "saetze": 120, "absaetze": 30, "warnungen": []}, "rot": 1, "rot_gegen": 0,
            "ziel_erreicht": ziel, "ziel_p_mensch": 0.85, "ziel_score": 73.2, "ziel_score_anzeige": 74, "score_einseitig": True,
            "score_ziel_wert": 82, "hebel": [], "hinweise": hinweise, "anzahl_hinweise_gesamt": len(hinweise), "gut": [],
            "blockmodus": True, "fokus": {"block": 3, "satz_von": 81, "satz_bis": 120},
            "bloecke": [{"nr": 1, "satz_von": 1, "satz_bis": 40, "score": 70, "score_ki": 90, "p_mensch": 1.0},
                        {"nr": 2, "satz_von": 41, "satz_bis": 80, "score": 74, "score_ki": 80, "p_mensch": 0.99},
                        {"nr": 3, "satz_von": 81, "satz_bis": 120, "score": 48, "score_ki": 60, "p_mensch": 0.46}],
            "bloecke_unter_ziel": unter_ziel or []}


class Blockmodus(unittest.TestCase):
    def test_hinweise_unten_nur_mit_hinweisen(self):
        b = coach.bericht(block_c([], [{"nr": 3, "p_mensch": 0.46, "score": 60}]))
        self.assertIn("← am KI-nächsten |", b)
        self.assertNotIn("Hinweise unten", b)
        self.assertNotIn("Die Hinweise betreffen nur Abschnitt", b)
        h = {"typ": "floskel", "hebel": "floskeln", "absatz": 20, "satz": 90, "text": "Satz 90: „x“ ersetzen."}
        b = coach.bericht(block_c([h], ziel=False))
        self.assertIn("← am KI-nächsten, Hinweise unten", b)

    def test_abschnitt_unter_dem_ziel_genannt(self):
        b = coach.bericht(block_c([], [{"nr": 3, "p_mensch": 0.46, "score": 60}]))
        self.assertIn("Der Gesamttext erreicht das Ziel; Abschnitt 3 (Modell 46 %, Score (KI-Seite) 60) liegt allein darunter", b)
        self.assertIn("einzeln coachen", b)
        self.assertIn("| Score (KI-Seite) |", b)

    def test_ergebnis_listet_abschnitte_unter_dem_ziel(self):
        text = gleichmaessig(8, 5)
        n = len(analyse.analysiere_text(text)["saetze"])
        bloecke = [{"nr": 1, "satz_von": 1, "satz_bis": 20, "p_mensch": 0.99, "score": 80, "score_ki": 90, "woerter": 400},
                   {"nr": 2, "satz_von": 21, "satz_bis": n, "p_mensch": 0.46, "score": 50, "score_ki": 60, "woerter": 400}]
        with bewertung_setzen(blockmodus=True, bloecke=bloecke, score=90, score_ki=90, p_mensch=0.9):
            c = coach.coache(text, None, 15)
        self.assertTrue(c["ziel_erreicht"])
        self.assertEqual([x["nr"] for x in c["bloecke_unter_ziel"]], [2])
        b = coach.bericht(c)
        self.assertIn("Abschnitt 2 (Modell 46 %", b)
        self.assertNotIn("Hinweise unten", b)


# ---------------------------------------------------------------------------
# 7. Vorgaben abschaltbar, Rückfrage bei durchgehendem Gendern
# ---------------------------------------------------------------------------

class VorgabenAbschaltbar(unittest.TestCase):
    def test_vorgaben_lesen(self):
        self.assertIsNone(coach.vorgaben_lesen(None))
        self.assertEqual(coach.vorgaben_lesen("keine"), set())
        self.assertEqual(coach.vorgaben_lesen("gender"), {"gender"})
        self.assertEqual(coach.vorgaben_lesen(" gender , gedankenstrich "), {"gender", "gedankenstrich"})
        with self.assertRaises(ValueError):
            coach.vorgaben_lesen("gender,komma")

    def test_rueckfrage_bei_durchgehendem_gendern(self):
        c = coach.coache(GENDER_TEXT, None, 15)
        self.assertTrue(c["gender_durchgehend"])
        self.assertFalse([h for h in c["vorgaben"] if h["typ"] == "gender"])
        b = coach.bericht(c)
        self.assertIn("Der Text gendert durchgehend", b)
        self.assertIn("gilt die Vorgabe generisches Maskulinum für diese Arbeit? Sonst mit `--vorgaben gedankenstrich` messen.", b)
        self.assertIn("Vorgaben gelten unabhängig vom Ziel – umsetzen, wenn sie für diese Arbeit gelten.", b)

    def test_ausdruecklich_gesetzt_einzelauftraege(self):
        c = coach.coache(GENDER_TEXT, None, 15, vorgaben="gender,gedankenstrich")
        self.assertIsNone(c["gender_durchgehend"])
        gender = [h for h in c["vorgaben"] if h["typ"] == "gender"]
        self.assertEqual(len(gender), 3)
        lehr = next(h for h in gender if h["fund"].startswith("Lehrend"))
        self.assertIn("„Dozenten“ bzw. „Hochschullehrer“", lehr["text"])
        self.assertNotIn("„Lehrkräfte“ oder", lehr["text"])
        self.assertIn("hochschullehrer", c["stand"]["erwartet"])
        self.assertNotIn("lehrkräfte", c["stand"]["erwartet"])

    def test_abschalten(self):
        text = GENDER_TEXT.replace("in der Region, vor allem", "in der Region – vor allem")
        c = coach.coache(text, None, 15, vorgaben="keine")
        self.assertFalse([h for h in c["vorgaben"] if h["typ"] in ("gender", "gedankenstrich")])
        self.assertIsNone(c["gender_durchgehend"])
        self.assertEqual(c["vorgaben_aktiv"], [])
        c = coach.coache(text, None, 15, vorgaben="gedankenstrich")
        self.assertFalse([h for h in c["vorgaben"] if h["typ"] == "gender"])
        self.assertTrue([h for h in c["vorgaben"] if h["typ"] == "gedankenstrich"])
        c = coach.coache(text, None, 15, vorgaben={"gender"})
        self.assertFalse([h for h in c["vorgaben"] if h["typ"] == "gedankenstrich"])

    def test_bindestrich_bleibt_eine_korrektur(self):
        text = "Das symbolisch - pragmatische Sportbild prägt die Debatte seit Jahren deutlich.\n\n" + FUELL
        c = coach.coache(text, None, 15, vorgaben="keine")
        self.assertTrue([h for h in c["vorgaben"] if h["typ"] == "bindestrich"])

    def test_mischform_und_wenige_staemme_einzelauftraege(self):
        # Umstellung begonnen: Maskulinformen in mindestens halb so vielen Sätzen wie die gegenderten → Einzelaufträge
        misch = GENDER_TEXT + ("\n\nDie Studenten nutzen die Bibliothek vor allem am Abend und am Wochenende gern. Viele "
                               "Absolventen bleiben nach dem Abschluss in der Stadt und arbeiten dort in kleinen Betrieben.")
        c = coach.coache(misch, None, 15)
        self.assertIsNone(c["gender_durchgehend"])
        self.assertTrue([h for h in c["vorgaben"] if h["typ"] == "gender"])
        # ein einzelner Ausrutscher in einem sonst gendernden Text: weiter die Rückfrage (v7-Prüfung, ash-158: 21× „_innen“, 2× Maskulin)
        rutscher = GENDER_TEXT + "\n\nDie Studenten nutzen die Bibliothek vor allem am Abend und am Wochenende gern."
        self.assertTrue(coach.coache(rutscher, None, 15)["gender_durchgehend"])
        # in einer Vorrunde kamen Gender-Aufträge (Vorgabe bestätigt): die Umstellung läuft, Einzelaufträge auch ohne --vorgaben
        c1 = coach.coache(GENDER_TEXT, None, 15, vorgaben="gender,gedankenstrich")
        c2 = coach.coache(GENDER_TEXT, {"messungen": [c1["stand"]]}, 15)
        self.assertIsNone(c2["gender_durchgehend"])
        self.assertTrue([h for h in c2["vorgaben"] if h["typ"] == "gender"])
        zwei = GENDER_TEXT.replace("Viele Absolvierende finden", "Viele Absolventen finden")
        c = coach.coache(zwei, None, 15)
        self.assertIsNone(c["gender_durchgehend"])
        self.assertEqual(len([h for h in c["vorgaben"] if h["typ"] == "gender"]), 2)

    def test_genderzeichen_reicht(self):
        # Angepasst in der v7.1-Prüfung (Verhalten absichtlich geändert): Ein einzelnes Genderzeichen ist keine durchgehende Haltung
        # (Korpus: ein „Rezipient*innen“ bzw. „Klassenlehrer(innen)“ neben „Teilnehmern“ hieß „gendert durchgehend“) – dann der
        # Einzelauftrag; Genderzeichen mehrfach (≥ 3 Vorkommen bzw. in zwei Stämmen) lösen die Rückfrage weiter aus.
        text = "Die Mitarbeiter*innen der Verwaltung beantworten Fragen zur Anmeldung schnell und freundlich.\n\n" + FUELL
        c = coach.coache(text, None, 15)
        self.assertIsNone(c["gender_durchgehend"])
        self.assertTrue([h for h in c["vorgaben"] if h["typ"] == "gender"])
        text = ("Die Mitarbeiter*innen der Verwaltung beantworten Fragen zur Anmeldung schnell und freundlich. Auch die "
                "Kund*innen der Mensa loben den Service seit dem letzten Semester ausdrücklich.\n\n" + FUELL)
        c = coach.coache(text, None, 15)
        self.assertTrue(c["gender_durchgehend"])
        self.assertEqual(c["gender_durchgehend"]["zeichen"], 2)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(GENDER_TEXT)
            puffer = io.StringIO()
            with redirect_stdout(puffer):
                coach.main([p, "--format", "json", "--vorgaben", "keine"])
            self.assertEqual(json.loads(puffer.getvalue())["vorgaben_aktiv"], [])
            with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
                coach.main([p, "--vorgaben", "gender,unsinn"])


# ---------------------------------------------------------------------------
# 8. Knapp am Ziel
# ---------------------------------------------------------------------------

class KnappAmZiel(unittest.TestCase):
    def test_logit_marge(self):
        p = round(p_fuer_luecke(-0.1), 4)  # 0,1 Logit über dem Ziel
        with bewertung_setzen(score=95, score_ki=95, p_mensch=p):
            c = coach.coache(FUELL, None, 15)
        self.assertTrue(c["ziel_erreicht"])
        self.assertTrue(c["ziel_knapp"])
        self.assertIn("Ziel erreicht (knapp – nach weiteren Änderungen neu messen)", coach.bericht(c))

    def test_score_abstand(self):
        with bewertung_setzen(score=95, score_ki=round(ZIEL_KI + 1.0, 1), p_mensch=0.999):
            c = coach.coache(FUELL, None, 15)
        self.assertTrue(c["ziel_erreicht"])
        self.assertTrue(c["ziel_knapp"])

    def test_deutlich_am_ziel(self):
        with bewertung_setzen(score=95, score_ki=95, p_mensch=0.999):
            c = coach.coache(FUELL, None, 15)
        self.assertFalse(c["ziel_knapp"])
        self.assertNotIn("knapp", coach.bericht(c).split("\n\n✅")[1].split("\n")[0])


# ---------------------------------------------------------------------------
# 9. Verlauf
# ---------------------------------------------------------------------------

class VerlaufFelder(unittest.TestCase):
    def test_stand(self):
        with bewertung_setzen(score=50, score_ki=83, p_mensch=0.99):
            c = coach.coache(VERKLEBT_TEXT, None, 15)
        st = c["stand"]
        self.assertEqual(st["score"], 50)  # unverändert der beidseitige Score (Kompatibilität)
        self.assertEqual(st["score_beidseitig"], 50)
        self.assertEqual(st["score_ziel"], 83)
        self.assertIs(st["ziel_erreicht"], True)
        self.assertEqual(st["auftraege"], len([h for h in c["hinweise"] if not h.get("info")]))
        self.assertGreaterEqual(st["auftraege"], 1)  # die Bereinigung zählt, Vorgaben nicht
        kopf = coach.bericht(c).split("\n")[2]
        self.assertIn("**Score 83/100** (KI-Seite; beidseitig 50 nur zur Info)", kopf)

    def test_auftraege_ohne_vorgaben(self):
        c = coach.coache(GENDER_TEXT.replace("in der Region, vor allem", "in der Region – vor allem"), None, 15,
                         vorgaben="gender,gedankenstrich")
        self.assertTrue(c["vorgaben"])
        self.assertEqual(c["stand"]["auftraege"], len([h for h in c["hinweise"] if not h.get("info")]))

    def test_main_schreibt_felder(self):
        with tempfile.TemporaryDirectory() as d:
            p, v = os.path.join(d, "t.md"), os.path.join(d, "t.coach.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write(KI_TEXT)
            with mock.patch("sys.stdout"):
                coach.main([p, "--verlauf", v])
            with open(v, encoding="utf-8") as f:
                m = json.load(f)["messungen"][-1]
        for k in ("ziel_erreicht", "score_beidseitig", "score_ziel", "auftraege", "score", "score_ki", "p_mensch"):
            self.assertIn(k, m)
        self.assertIsInstance(m["ziel_erreicht"], bool)


if __name__ == "__main__":
    unittest.main()
