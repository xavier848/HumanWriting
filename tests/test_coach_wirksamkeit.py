"""Tests für Coach v3 (Wirksamkeit): Absatz-Simulation, Wächter, „Mitte ausdünnen“, Rhythmus in der Satzlängen-Simulation,
Funktionswort-Diagnose, ehrliche Stagnationsdiagnose, inhaltsneutrale Modell-Hebel und Wirksamkeitsgedächtnis.

Alle Texte sind synthetisch (keine Korpustexte).

python3 -m unittest discover -s tests
"""
import os
import re
import sys
import unittest
from collections import Counter
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
from test_coach import KI_TEXT, THEMEN, _KURZE_WORTE, absatz, satz  # noqa: E402

W = _KURZE_WORTE


def saetze_von(text):
    return analyse.analysiere_text(text)["saetze"]


def gleichmaessig(n_abs=8, n_saetze=5, start=0):
    """n_abs Absätze mit je n_saetze mittellangen Sätzen (KI-typisch gleichmäßig), je Absatz ein Thema."""
    laengen = [[18, 16, 21, 15, 20, 17], [19, 22, 14, 17, 16, 21], [16, 20, 18, 22, 15, 19]]
    return "\n\n".join(absatz(THEMEN[i % len(THEMEN)], laengen[i % 3][:n_saetze], start + 5 * i, W) for i in range(n_abs))


def mit_metriken(**werte):
    """Ersetzt analysiere_und_bewerte so, dass einzelne Rohmetriken bzw. Kennzahlwerte vorgegeben sind."""
    echt = coach.analyse.analysiere_und_bewerte

    def fake(*a, **k):
        erg, bew = echt(*a, **k)
        for key, v in werte.items():
            erg["metriken"][key] = v
            for z in bew["kennzahlen"]:
                if z["id"] == key:  # Wert und Status passend setzen
                    z["wert"] = v
                    m = {q: z["mensch_" + q] for q in ("p10", "p25", "p75", "p90")}
                    z["status"] = ("gruen" if m["p25"] <= v <= m["p75"] else "gelb" if m["p10"] <= v <= m["p90"] else "rot")
                    z["unsicher"] = False
        return erg, bew
    return mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake)


class AbsatzSimulation(unittest.TestCase):
    def test_kennzahlen_wie_analyse(self):
        text = gleichmaessig(6, 4) + "\n\n" + absatz(THEMEN[7], [17, 19], 3, W)
        erg = analyse.analysiere_text(text)
        anz = Counter(s["absatz"] for s in erg["saetze"])
        wl = Counter()
        for s in erg["saetze"]:
            wl[s["absatz"]] += s["woerter"]
        k = coach.absatz_kennzahlen([anz[n] for n in sorted(anz)], [wl[n] for n in sorted(wl)])
        self.assertAlmostEqual(k["cv"], erg["metriken"]["saetze_pro_absatz_cv"], places=3)
        self.assertAlmostEqual(k["cv_w"], erg["metriken"]["absatzlaenge_cv"], places=3)
        self.assertAlmostEqual(k["mittel"], erg["metriken"]["saetze_pro_absatz"], places=3)

    def test_umbau_erhoeht_die_gemessene_variation(self):
        text = gleichmaessig(8, 5)
        c = coach.coache(text, None, 40, roh=True)
        umbau = [h for h in c["hinweise_roh"] if h["typ"] in ("absatz_teilen", "absatz_zusammen")]
        self.assertEqual(len(umbau), 1)  # höchstens ein Absatz-Umbau je Runde
        h = umbau[0]
        self.assertEqual(h["typ"], "absatz_teilen")  # Zusammenlegen triebe Sätze pro Absatz aus dem grünen Band (5 → 5,7)
        S = {s["nr"]: s for s in saetze_von(text)}
        neu = text
        for nr in map(int, re.findall(r"vor Satz (\d+)", h["text"])):
            i = neu.find(S[nr]["text"])
            neu = neu[:i].rstrip(" ") + "\n\n" + neu[i:]
        vorher = analyse.analysiere_text(text)["metriken"]
        nachher = analyse.analysiere_text(neu)["metriken"]
        self.assertGreaterEqual(nachher["saetze_pro_absatz_cv"] - vorher["saetze_pro_absatz_cv"], coach.ABSATZ_MIN_GEWINN)
        ref = analyse.lade_baselines()["textsorten"]["hochschule"]["metriken"]
        self.assertLessEqual(nachher["saetze_pro_absatz_cv"], ref["saetze_pro_absatz_cv"]["mensch"]["p75"])
        m = ref["saetze_pro_absatz"]["mensch"]
        self.assertTrue(m["p25"] <= nachher["saetze_pro_absatz"] <= m["p75"])  # bleibt im grünen Band
        self.assertIn("Variation", h["text"])

    def test_keine_trennung_in_aufzaehlung_oder_vor_rueckverweis(self):
        # Absatz 1: Einleitung, „Erstens …“, Erläuterung, „Zweitens …“, Schluss; Absatz 2: alle Folgesätze mit Rückverweis
        a1 = " ".join([satz(THEMEN[0], 18, 0, W), "Erstens " + satz(THEMEN[0], 17, 3, W)[0].lower() + satz(THEMEN[0], 17, 3, W)[1:],
                       satz(THEMEN[1], 19, 5, W), "Zweitens " + satz(THEMEN[0], 16, 7, W)[0].lower() + satz(THEMEN[0], 16, 7, W)[1:],
                       satz(THEMEN[2], 18, 9, W)])
        a2 = " ".join([satz(THEMEN[3], 18, 2, W), "Dies " + satz(THEMEN[3], 17, 4, W)[4:], "Dabei " + satz(THEMEN[3], 19, 6, W)[4:],
                       "Daher " + satz(THEMEN[3], 16, 8, W)[4:], "Diese Entwicklung " + satz(THEMEN[3], 18, 1, W)[4:]])
        text = a1 + "\n\n" + a2 + "\n\n" + gleichmaessig(6, 5, 11)
        S = saetze_von(text)
        verboten = {s["nr"] for s in S if s["absatz"] == 1 and s["pos_im_absatz"] in (2, 3, 4)}
        verboten |= {s["nr"] for s in S if s["absatz"] == 2 and s["pos_im_absatz"] > 1}
        c = coach.coache(text, None, 40, roh=True)
        for h in c["hinweise_roh"]:
            if h["typ"] == "absatz_teilen":
                for nr in map(int, re.findall(r"vor Satz (\d+)", h["text"])):
                    self.assertNotIn(nr, verboten, h["text"])

    def test_zusammenlegen_nie_ueber_ueberschrift(self):
        # gleich große kleine Absätze (3 Sätze, unter P25): nur Zusammenlegen zulässig; zwischen allen Paaren außer 3/4 steht
        # eine Überschrift – also darf nur Absatz 3 mit 4 zusammengelegt werden
        teile = []
        for i in range(8):
            if i and i != 3:
                teile.append(f"## Abschnitt {i}")
            teile.append(absatz(THEMEN[i // 2], [17, 19, 21], 4 * i, W))
        text = "\n\n".join(teile)
        c = coach.coache(text, None, 40, roh=True)
        z = [h for h in c["hinweise_roh"] if h["typ"] == "absatz_zusammen"]
        self.assertEqual(len(z), 1)
        self.assertIn("Absatz 3 und 4 ", z[0]["text"])
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "absatz_teilen"])

    def test_zusammenlegen_ohne_siebener_grenze(self):
        # 4 + 4 Sätze: früher wegen der 7er-Grenze gesperrt; jetzt zulässig, wenn die Simulation es trägt
        text = "\n\n".join(absatz(THEMEN[i // 2], [15, 17, 16], 4 * i, W) for i in range(8)) + "\n\n" + \
            "\n\n".join(absatz(THEMEN[5], [17, 18, 16, 19], 3 * i, W) for i in range(2))
        c = coach.coache(text, None, 40, roh=True)
        z = [h for h in c["hinweise_roh"] if h["typ"] == "absatz_zusammen"]
        self.assertTrue(z)
        self.assertTrue(any(re.search(r"\((\d+) \+ (\d+) Sätze\)", h["text"]) and
                            sum(map(int, re.search(r"\((\d+) \+ (\d+) Sätze\)", h["text"]).groups())) >= 6 for h in z))


class Waechter(unittest.TestCase):
    def verlauf(self, hinweise=(), **roh):
        return {"messungen": [{"score": 50, "p_mensch": 0.1, "kennzahlen": {}, "roh": roh, "hinweise": list(hinweise)}]}

    def test_unbewertete_lesbarkeit_sperrt_nur_bei_rot(self):
        with mit_metriken(flesch_amstad=15.0, nominalstil_pro_100=6.0):  # gelb auf der Gegenseite (P10 11,9 – P25 18,4)
            c = coach.coache(KI_TEXT, self.verlauf(flesch_amstad=25.0), 40)
        self.assertFalse([u for u in c["fortschritt"]["ueberkorrektur"] if u["id"] == "flesch_amstad"])
        self.assertNotIn("buendeln", c["fortschritt"]["ausgesetzt"])
        with mit_metriken(flesch_amstad=9.0):  # rot
            c = coach.coache(KI_TEXT, self.verlauf(flesch_amstad=25.0), 40)
        self.assertTrue([u for u in c["fortschritt"]["ueberkorrektur"] if u["id"] == "flesch_amstad"])
        self.assertTrue(coach._VERDICHTEN <= set(c["fortschritt"]["ausgesetzt"]))

    def test_bewertete_gelb_nur_bei_deutlicher_verschiebung(self):
        # anteil_lange_saetze: P75 0,242, IQR ≈ 0,16 – 0,20 → 0,25 ist eine kleine Verschiebung, 0,10 → 0,30 eine große
        with mit_metriken(anteil_lange_saetze=0.25):
            c = coach.coache(KI_TEXT, self.verlauf(anteil_lange_saetze=0.20), 40)
        self.assertNotIn("anteil_lange_saetze", [u["id"] for u in c["fortschritt"]["ueberkorrektur"]])
        with mit_metriken(anteil_lange_saetze=0.30):
            c = coach.coache(KI_TEXT, self.verlauf(anteil_lange_saetze=0.10), 40)
        self.assertIn("anteil_lange_saetze", [u["id"] for u in c["fortschritt"]["ueberkorrektur"]])
        self.assertIn("buendeln", c["fortschritt"]["ausgesetzt"])

    def test_schiefe_sperrt_buendeln_nur_ohne_fehlende_lange_saetze(self):
        befolgt = {"typ": "buendeln", "anfang": "satz der nicht mehr da ist", "laenge": 20, "weitere": ["auch nicht mehr da"]}
        with mit_metriken(satzlaenge_schiefe=0.05, anteil_lange_saetze=0.05, nominalstil_pro_100=6.0):  # rot, kaum lange Sätze
            c = coach.coache(KI_TEXT, self.verlauf(satzlaenge_schiefe=0.6, hinweise=[befolgt]), 40)
        self.assertNotIn("buendeln", c["fortschritt"]["ausgesetzt"])
        with mit_metriken(satzlaenge_schiefe=0.05, anteil_lange_saetze=0.2):
            c = coach.coache(KI_TEXT, self.verlauf(satzlaenge_schiefe=0.6, hinweise=[befolgt]), 40)
        self.assertIn("buendeln", c["fortschritt"]["ausgesetzt"])  # befolgt, ältere Messung ohne Längenfolge: zuordenbar

    def test_nebenwirkung_nur_bei_befolgtem_auftrag(self):
        # ohne befolgten Bündel-Auftrag in der Vorrunde wird die Nebenwirkung gemeldet, aber nichts ausgesetzt
        with mit_metriken(satzlaenge_schiefe=0.05, anteil_lange_saetze=0.2, nominalstil_pro_100=6.0):
            c = coach.coache(KI_TEXT, self.verlauf(satzlaenge_schiefe=0.6), 40)
        uk = [u for u in c["fortschritt"]["ueberkorrektur"] if u["id"] == "satzlaenge_schiefe"]
        self.assertEqual(len(uk), 1)
        self.assertEqual(uk[0]["aussetzen"], [])
        self.assertNotIn("buendeln", c["fortschritt"]["ausgesetzt"])
        self.assertIn("keinem befolgten Auftrag", coach.bericht(c))

    def test_simulierte_wirkung_entscheidet_die_zuordnung(self):
        # Agile R3 (v3-Kritik): Bündeln S1+S2 senkt den Anteil mittellanger Sätze, gestiegen ist er durch eine Kürzung woanders
        alt = [23, 16, 28, 20, 18, 22, 30, 12, 19, 21]
        L = coach.Lauf(KI_TEXT, {"messungen": [{"laengen": alt, "hinweise": []}]})
        h = {"typ": "buendeln", "pos": 0, "laengen_alt": [23, 16], "sim": [36]}
        eff = coach.sim_wirkung(L, [h], "anteil_mittlere_saetze")
        self.assertLess(eff, 0)
        self.assertFalse(coach._verursacht(L, "buendeln", [h], "anteil_mittlere_saetze", +0.01))
        self.assertTrue(coach._verursacht(L, "buendeln", [h], "anteil_mittlere_saetze", -0.05))
        self.assertGreater(coach.sim_wirkung(L, [h], "lix"), 0)  # längere Sätze: LIX steigt

    def test_rhythmus_sperrt_buendeln_nicht_mehr(self):
        self.assertNotIn("ki", coach.WAECHTER["rhythmus_r1_log"])
        with mit_metriken(rhythmus_r1_log=-0.3, nominalstil_pro_100=6.0):
            c = coach.coache(KI_TEXT, self.verlauf(rhythmus_r1_log=0.0), 40)
        self.assertNotIn("buendeln", c["fortschritt"]["ausgesetzt"])
        self.assertIn("vorab so geprüft", coach.bericht(c))  # v5: kein „simuliert“ (interner Jargon) im Nutzertext

    def test_wenig_passiv_keine_relativsatz_umbauten(self):
        # viele Relativsätze, kein Passiv
        rel = [f"Die {t} betrifft die Firma, die oft neue Wege für den Kontakt mit jungen Leuten in der Region nutzt." for t in THEMEN[:10]]
        kurz = [f"Die {t} braucht Zeit und Geld." for t in THEMEN[:10]]
        text = "\n\n".join(" ".join(x for pair in zip(rel[i:i + 2], kurz[i:i + 2]) for x in pair) for i in range(0, 10, 2))
        L = coach.Lauf(text, None)
        coach._hebel_priorisieren(L)
        coach._waechter(L)
        if L.kz["anteil_passiv"]["wert"] < L.kz["anteil_passiv"]["mensch_p25"]:
            self.assertIn("nebensatz_relativ", L.ausgesetzt)
        c = coach.coache(text, None, 40, roh=True)
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "nebensatz" and "Relativsatz" in h["text"]])

    def test_ausgesetzter_hebel_mit_grund_und_alternative(self):
        L = coach.Lauf(gleichmaessig(8, 5), None)
        coach._hebel_priorisieren(L)
        self.assertIn("absaetze", L.hebel)
        L.setze_aus({"absatz_teilen", "absatz_zusammen"}, "Testgrund")
        coach._satzlaengen(L)
        coach._absaetze(L)
        c = coach._ergebnis(L, 15, False)
        h = next(x for x in c["hebel"] if x["id"] == "absaetze")
        self.assertEqual(h["ausgesetzt"], ["Testgrund"])
        self.assertTrue(h["alternative"])
        self.assertIn("diese Runde ausgesetzt, weil Testgrund", coach.bericht(c))


def mitte_text():
    """Genug lange Sätze (≥ 30 W.), aber 65 % mittellange; die mittellangen (24 W.) haben eine Fuge „, die“ nach Wort 12."""
    def mittel(i):
        t = THEMEN[i % len(THEMEN)]
        links = ["Die", t, "betrifft"] + [W[(i + j) % len(W)] for j in range(9)]
        rechts = ["die"] + [W[(i + 13 + j) % len(W)] for j in range(11)]
        return " ".join(links) + ", " + " ".join(rechts) + "."
    folge, absaetze = [], []
    for i in range(40):
        k = i % 40
        if k % 6 == 0:
            folge.append(satz(THEMEN[i % len(THEMEN)], 32, i, W))
        elif k % 6 == 3 and len([x for x in folge if len(x.split()) < 12]) < 7:
            folge.append(satz(THEMEN[i % len(THEMEN)], 8, i, W))
        else:
            folge.append(mittel(i))
    for j in range(0, 40, 5):
        absaetze.append(" ".join(folge[j:j + 5]))
    return "\n\n".join(absaetze)


class MitteAusduennen(unittest.TestCase):
    def test_mitte_modus_konkret_und_simuliert(self):
        text = mitte_text()
        c = coach.coache(text, None, 40, roh=True)
        sl = c["satzlaengen"]
        ref = analyse.lade_baselines()["textsorten"]["hochschule"]["metriken"]
        self.assertGreaterEqual(sl["anteil_lange"], ref["anteil_lange_saetze"]["mensch"]["p50"])
        self.assertGreater(sl["anteil_mittlere"], ref["anteil_mittlere_saetze"]["mensch"]["p75"])
        self.assertEqual(sl["modus"], "mitte")
        mitte = [h for h in c["hinweise_roh"] if h["typ"] == "mitte"]
        self.assertTrue(mitte)
        self.assertLessEqual(len(mitte), min(coach.MAX_MITTE, sl["kontingent"]))
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] in ("buendeln", "zickzack")])
        S = {s["nr"]: s for s in saetze_von(text)}
        for h in mitte:
            self.assertTrue(coach.MITTE_SATZ_VON <= S[h["satz"]]["woerter"] <= coach.MITTE_SATZ_BIS)
            self.assertIn(f"je höchstens {coach.MITTE_TEIL_MAX} Wörtern", h["text"])
            self.assertIn("Bezugswort", h["text"])  # Fuge „, die“: Bezugswort im zweiten Satz wiederholen
        self.assertIn("mittellang", coach.bericht(c))

    def test_teilstelle_beruecksichtigt_zusatzwoerter(self):
        t = "Kleine Betriebe verfügen meist über deutlich weniger finanzielle Mittel als große Konzerne und sind außerhalb ihrer Region oft kaum bekannt."
        st = coach.teilstelle(t, t, 13, coach.MITTE_TEIL_RE)
        self.assertIsNotNone(st)
        self.assertEqual(st[4], "und")
        self.assertIn("Subjekt", coach.fugen_technik(st[4]))
        lang = ("Zugleich haben kleine Firmen Vorteile für eine klare Ansprache neuer Leute, etwa kurze Wege, flache Hierarchien, "
                "eine persönliche Kultur, enge Kontakte zur Region und viel Vertrauen im Ort.")
        st = coach.teilstelle(lang, lang, 13, coach.MITTE_TEIL_RE)
        self.assertTrue(st is None or st[3] + coach.FUGE_ZUSATZ.get(st[4], 0) <= 13)


class RhythmusInDerSimulation(unittest.TestCase):
    def test_rhythmus_wie_analyse(self):
        erg = analyse.analysiere_text(KI_TEXT)
        L = [s["woerter"] for s in erg["saetze"]]
        self.assertAlmostEqual(coach.rhythmus(L), erg["metriken"]["rhythmus_r1_log"], places=3)
        self.assertAlmostEqual(coach.dispersion(L), erg["metriken"]["satzlaenge_dispersion"], places=3)
        self.assertEqual(coach.wechsel([8, 30, 8, 30, 8]), 3)
        self.assertEqual(coach.wechsel([8, 20, 8, 30, 30]), 0)

    def test_laengenmodell_zielfunktion_und_harte_grenzen(self):
        b = analyse.lade_baselines()["textsorten"]["hochschule"]
        ref = b["metriken"]
        lm = coach.LaengenModell(ref, b)
        ki = [12, 18, 22, 15, 25, 19, 14, 21, 17, 24, 16, 20, 23, 13, 26, 18, 27, 11, 19, 22] * 2  # KI-typisch: kaum lange Sätze
        # Bündeln zweier mittellanger Sätze zu einem langen: Modellmerkmale (mittellange Sätze, Dispersion) verbessern sich
        neu = [34] + ki[2:]
        wert, teile = lm.bewerte(ki, neu)
        self.assertIsNotNone(wert)
        self.assertGreater(teile["logit"], 0)
        self.assertGreater(wert, 0)
        # die Werte entsprechen analyse.py
        w = coach.laengen_werte(ki)
        self.assertAlmostEqual(w["satzlaenge_dispersion"], coach.dispersion(ki), places=6)
        # L1 ist nur ein weicher Term: auch wenn L1 schlechter wird, entscheidet das Modell
        self.assertLessEqual(abs(teile["l1"]), coach.L1_GEWICHT * 2)
        # harte Grenze: über P75 auf der Gegenseite (zu viele lange Sätze)
        lang = [34, 36, 31, 33, 38, 18, 20, 32, 35, 19] * 4
        wert2, teile2 = lm.bewerte([18, 20] + lang, [34] + lang)
        self.assertIsNone(wert2)
        self.assertEqual(teile2["grenze"], "anteil_lange_saetze")
        # Rhythmus: Kurz-Lang-Wechsel werden abgewertet
        L0 = [18, 19, 20, 21] * 10
        w_glatt, _ = lm.bewerte(L0, [18, 19, 20, 21, 20] * 8)
        w_zick, t_zick = lm.bewerte(L0, [8, 30, 8, 30, 20] * 8)
        self.assertLess(t_zick["rhythmus"], 0)

    def test_lesbarkeit_nie_rot_auf_der_gegenseite(self):
        b = analyse.lade_baselines()["textsorten"]["hochschule"]
        ref = b["metriken"]
        p90 = ref["lix"]["mensch"]["p90"]
        ki = [12, 18, 22, 15, 25, 19, 14, 21, 17, 24, 16, 20, 23, 13, 26, 18, 27, 11, 19, 22] * 2
        lm = coach.LaengenModell(ref, b, {"lix": p90 - 0.5}, analyse.mittel(ki))  # LIX knapp unter P90
        wert, teile = lm.bewerte(ki, [40] + ki[2:])  # Ø-Satzlänge steigt: LIX ginge über die Puffergrenze
        self.assertIsNone(wert)
        self.assertEqual(teile["grenze"], "lix")


FW_TEXT = """## Planung im Betrieb

Der Jahresbericht dient als Grundlage für die Planung der Abteilungen im kommenden Jahr. Die Abteilungen nutzen ihn als zentrale Quelle für ihre Budgets und als Maßstab für die Ziele. Das Controlling fungiert dabei als Schnittstelle zwischen Leitung und Fachbereichen. Viele Daten lassen sich inzwischen automatisch aus den Systemen übernehmen. Die Kosten lassen sich zudem genauer den Projekten zuordnen als früher.

Bei der Planung handelt es sich um einen jährlichen Prozess mit mehreren Stufen. Die Planung bezieht sich auf alle Bereiche und auf alle Standorte des Betriebs. Sie beginnt im Herbst und endet im Januar mit der Freigabe durch die Leitung. Zusammenfassend lässt sich festhalten, dass die Planung heute schneller abläuft als früher. Insgesamt zeigt sich ein deutlicher Wandel in der Arbeit der Abteilungen.

Das Programm versteht sich als Ergänzung zur bisherigen Planung und als Hilfe für kleine Teams. Die Teams sehen das Programm als Entlastung und als Chance für mehr Austausch. Daraus ergibt sich ein klarer Vorteil für die kleinen Standorte und ihre Leitungen. Die Leitung gilt als offen für neue Werkzeuge und als bereit für Veränderungen. Die Abteilungen arbeiten seitdem enger zusammen als vorher und teilen ihre Daten.
"""


class Funktionswoerter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = coach.coache(FW_TEXT, None, 40, roh=True)
        cls.fw = [h for h in cls.c["hinweise_roh"] if h["typ"].startswith("fw_")]
        cls.S = {s["nr"]: s for s in saetze_von(FW_TEXT)}

    def nr(self, anfang):
        return next(n for n, s in self.S.items() if s["text"].startswith(anfang))

    def test_diagnose_summe_wie_kennzahl(self):
        profil = analyse.lade_baselines()["textsorten"]["hochschule"]["fw_profil"]
        erg = analyse.analysiere_text(FW_TEXT, fw_profil=profil)
        d = coach.fw_diagnose(erg["saetze"], profil)
        self.assertAlmostEqual(d["llr"], erg["metriken"]["fw_profil_llr_pro_1000"], places=1)
        self.assertEqual([r["beitrag"] for r in d["woerter"]], sorted(r["beitrag"] for r in d["woerter"]))
        als = next(r for r in d["woerter"] if r["wort"] == "als")
        self.assertEqual(als["anzahl"], d["zaehlung"].get("als", 0))
        self.assertAlmostEqual(als["mensch"], round(profil["rate_mensch"]["als"] * d["n"], 1))
        self.assertLessEqual(len(d["top"]), 3)

    def test_ki_typische_konstruktionen_mit_technik(self):
        typen = {h["satz"]: h for h in self.fw}
        self.assertGreaterEqual(len(self.fw), 4)
        self.assertLessEqual(len(self.fw), 5)  # Kontingent je Runde
        self.assertEqual(typen[self.nr("Zusammenfassend lässt sich")]["typ"], "fw_ankuendigung")
        self.assertIn("streichen", typen[self.nr("Zusammenfassend lässt sich")]["text"])
        technik = {"fw_als": ("bildet", "will … sein", "für … gehalten"), "fw_lassen": ("Passiv ohne Modalverb",),
                   "fw_zeigt": ("direkt nennen",), "fw_ergibt": ("„folgt“",), "fw_ankuendigung": ("streichen",)}
        for h in self.fw:
            self.assertTrue(any(t in h["text"] for t in technik[h["typ"]]), h["text"])
            self.assertGreater(h.get("fw_delta", 1), 0)
        # nicht KI-typisch (Korpusverhältnis < 1,5): keine Hinweise
        for anfang in ("Bei der Planung handelt", "Die Planung bezieht sich", "Sie beginnt im Herbst"):
            self.assertNotIn(self.nr(anfang), typen, anfang)

    def test_dient_als_bildet(self):
        text = ("## Planung\n\nDer Jahresbericht dient als Grundlage für die Planung der Abteilungen im kommenden Jahr. "
                "Das Controlling fungiert dabei als Schnittstelle zwischen Leitung und Fachbereichen im ganzen Betrieb. "
                "Die Abteilungen nutzen die Zahlen als Maßstab für ihre Ziele und als Quelle für die Budgets. "
                "Die Leitung sieht den Bericht als Werkzeug und als Hilfe für die Teams und ihre Arbeit.\n")
        c = coach.coache(text, None, 40, roh=True)
        als = [h for h in c["hinweise_roh"] if h["typ"] == "fw_als"]
        self.assertEqual({h["satz"] for h in als}, {1, 2})
        self.assertTrue(all("„ist“ oder „bildet“" in h["text"] for h in als))

    def test_ein_auftrag_fuer_die_ankuendigung(self):
        nr = self.nr("Zusammenfassend lässt sich")
        am_satz = [h for h in self.c["hinweise_roh"] if h["satz"] == nr]
        self.assertEqual([h["typ"] for h in am_satz if h["typ"] in ("nebensatz", "fw_lassen", "fw_ankuendigung")], ["fw_ankuendigung"])

    def test_gilt_als_nur_ohne_zuschreibung(self):
        self.assertIn(self.nr("Die Leitung gilt als"), {h["satz"] for h in self.fw if h["typ"] == "fw_als"})
        text = FW_TEXT.replace("Die Leitung gilt als offen", "Nach der Definition der Kommission gilt die Leitung als offen")
        c = coach.coache(text, None, 40, roh=True)
        nr = next(s["nr"] for s in saetze_von(text) if s["text"].startswith("Nach der Definition"))
        self.assertFalse([h for h in c["hinweise_roh"] if h["satz"] == nr and h["typ"] == "fw_als"])

    def test_wiedergegebene_rede_bleibt(self):
        self.assertTrue(coach.sachliches_subjekt("Die Ergebnisse zeigen"))
        self.assertTrue(coach.sachliches_subjekt("Dies verdeutlicht"))
        for vorne in ("Erik betont dreimal", "Er zeigt", "Die Autoren betonen", "Sie unterstreichen"):
            self.assertFalse(coach.sachliches_subjekt(vorne), vorne)
        text = ("## Befragung\n\nDie Ergebnisse zeigen, dass die Kosten im zweiten Jahr deutlich steigen. Erik betont dreimal, dass er so "
                "etwas nie machen würde. Die Daten belegen, dass die Teams heute schneller arbeiten. Die Autoren betonen, dass die "
                "Planung wichtig bleibt. Dies verdeutlicht, dass kleine Betriebe von der Planung profitieren. Viele hoffen, dass "
                "die Lage besser wird und dass die Teams bleiben.\n")
        c = coach.coache(text, None, 40, roh=True)
        S = {s["nr"]: s["text"] for s in saetze_von(text)}
        for h in c["hinweise_roh"]:
            if h["typ"] == "fw_dass":
                self.assertFalse(S[h["satz"]].startswith(("Erik", "Die Autoren")), h["text"])

    def test_lassen_nicht_bei_hohem_hedging(self):
        with mit_metriken(hedging_pro_1000=20.0):
            c = coach.coache(FW_TEXT, None, 40, roh=True)
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "fw_lassen"])

    def test_keine_einstreu_aufforderung(self):
        for h in self.c["hinweise_roh"]:
            self.assertNotRegex(h["text"], r"(?i)(einstreuen|einfügen|ergänzen)\W+„?(es|werden|auch|durch|wie|um)\b")
        warum = next((h["warum"] for h in self.c["hebel"] if h["id"] == "funktionswoerter"), "")
        if "seltener" in warum:
            self.assertIn("nicht einstreuen", warum)

    def test_korpusverhaeltnis_jeder_konstruktion(self):
        for kid, *_ in coach.FW_KONSTRUKTIONEN:
            m, k = coach.FW_KORPUS[kid]
            self.assertGreaterEqual(k / m, 1.5, kid)

    def test_werden_schutz(self):
        # kein „werden“ im Text, aber Nebensätze mit „wurden“: die Nebensatz-Hinweise dürfen sie nicht wegformulieren lassen
        text = KI_TEXT.replace("die in den letzten Jahren stark gewachsen sind", "die in den letzten Jahren stark ausgebaut wurden")
        L = coach.Lauf(text, None)
        if "werden" in L.schutz:
            coach._hebel_priorisieren(L)
            coach._waechter(L)
            self.assertIn("nebensatz_werden", L.ausgesetzt)
        c = coach.coache(text, None, 40, roh=True)
        S = {s["nr"]: s for s in saetze_von(text)}
        for h in c["hinweise_roh"]:
            if h["typ"] == "nebensatz" and "werden" in L.schutz:
                self.assertFalse(re.search(r",.*\b(wurden|wurde|werden|wird)\b", S[h["satz"]]["text"]), h["text"])


class Stagnation(unittest.TestCase):
    def test_diagnose_bei_stagnation(self):
        c0 = coach.coache(KI_TEXT)
        p = c0["bewertung"]["p_mensch"]
        verlauf = {"messungen": [dict(c0["stand"], p_mensch=p), dict(c0["stand"], p_mensch=p)]}
        # überarbeitet, aber p bewegt sich kaum (ein bloß erneut gemessener Text ist keine Stagnation, siehe test_coach_integration)
        text = KI_TEXT.replace("die Ressourcen fehlen oft", "die Ressourcen fehlen häufig")
        c = coach.coache(text, verlauf)
        d = c["diagnose"]
        self.assertIsNotNone(d)
        self.assertTrue(d["stagniert"])
        b = [z["beitrag"] for z in d["beitraege"]]
        self.assertEqual(b, sorted(b))
        self.assertTrue(all(x < 0 for x in b))
        txt = coach.bericht(c)
        self.assertIn("Warum das Modellziel noch fehlt", txt)
        self.assertEqual(bool(d["fw_text"]), d["fw_dominant"])
        if d["fw_dominant"]:
            self.assertIn("in eigenen Worten neu zu schreiben", txt)
        # v5: „Grenze der Einzelkorrekturen“ erst unter 70 % der Lücke, dazwischen „knapp, Schätzung unsicher“
        if d["grenze"] == "einzelkorrekturen":
            self.assertIn("Grenze der Einzelkorrekturen", txt)
        elif d["grenze"] == "knapp":
            self.assertIn("Knapp – Schätzung unsicher", txt)
        self.assertNotIn("Grenze des Textes", txt)

    def test_diagnose_bei_wenigen_hinweisen_statt_schweigen(self):
        c = coach.coache(KI_TEXT, None, 2)
        self.assertIsNotNone(c["diagnose"])
        self.assertNotIn("Keine sicheren Einzelstellen", coach.bericht(c))

    def test_keine_diagnose_am_ziel(self):
        echt = coach.analyse.analysiere_und_bewerte

        def fake(*a, **k):
            erg, bew = echt(*a, **k)
            return erg, dict(bew, score=95, score_ki=95, p_mensch=0.99)
        with mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake):
            c = coach.coache(KI_TEXT, None, 2)
        self.assertIsNone(c["diagnose"])


ABK_ANHANG = gleichmaessig(5, 5, 30)
ABK_ANHANG2 = gleichmaessig(5, 5, 60)
ABK_TEXT = """## Arbeitszeit im Betrieb

Viele Betriebe bieten heute flexible Modelle an, zum Beispiel Gleitzeit oder Teilzeit für junge Eltern. Zum Beispiel nutzt die Firma ein Konto für Überstunden und plant die Schichten neu. Die Teams wählen ihre Zeiten in der Regel selbst und stimmen sich dabei kurz ab. Die Vergleiche mit anderen Firmen zeigen deutliche Unterschiede bei den Modellen. Die Leitung prüft unter anderem die Kosten und die Wirkung auf die Stimmung im Team.

Die Firma hat rund 500 Beschäftigte an drei Standorten in der Region und im Ausland. Das heißt nicht, dass alle Standorte gleich arbeiten oder gleich planen. Die Leitung plant die Schichten neu, das heißt mit kürzeren Wegen und mehr Pausen. Die Teams nutzen die freie Zeit beispielsweise für Weiterbildung oder Familie. Die Beschäftigten bewerten die Modelle insgesamt gut und wünschen sich mehr davon.
"""


class ModellHebel(unittest.TestCase):
    def test_abkuerzungen_inhaltsneutral_und_begrenzt(self):
        text = ABK_TEXT + "\n" + ABK_ANHANG + "\n\n" + ABK_ANHANG2
        c = coach.coache(text, None, 40, roh=True)
        abk = [h for h in c["hinweise_roh"] if h["typ"] == "abkuerzung"]
        self.assertTrue(abk)
        S = {s["nr"]: s for s in saetze_von(text)}
        for h in abk:
            texte = [S[n]["text"] for n in h["saetze"]]  # v5: eine Familie kann mehrere Sätze umfassen (Auftrag ohne Einzelsatz)
            for f in h["funde"]:
                self.assertFalse(any(t.startswith(f[:1].upper() + f[1:]) for t in texte), h["text"])  # nie am Satzanfang
                self.assertNotIn("Vergleiche", f)
                if f == "das heißt":
                    self.assertTrue(any(", das heißt" in t for t in texte))
            self.assertNotIn("in der Regel", h["text"])  # „i. d. R.“ wirkt im Fließtext gestelzt
        self.assertNotIn("Abkürzungen pro 1000 (z. B., bzw., d. h. …)", c["gut"])  # Modellbeitrag −0,45: nicht „schon gut“
        ref = analyse.lade_baselines()["textsorten"]["hochschule"]["metriken"]["abkuerzungen_pro_1000"]["mensch"]
        tok = sum(len(analyse.tokens(s["text"])) for s in S.values())
        treffer = sum(len(h["funde"]) for h in abk)
        # v5: begonnen wird nur unter dem Median; eine Familie wird ganz genannt, solange das Ergebnis höchstens bei P75 liegt
        self.assertLessEqual(treffer, int(ref["p75"] * tok / 1000))
        kurz = coach.coache(ABK_TEXT, None, 40, roh=True)  # ~130 Wörter: schon eine Abkürzung läge über dem Median
        self.assertFalse([h for h in kurz["hinweise_roh"] if h["typ"] == "abkuerzung"])

    def test_alle_treffer_im_satz_einheitlich(self):
        satz = "Die Firma hat rund 500 Beschäftigte in der Region und etwa 120 weitere im Ausland an zwei Standorten."
        text = satz + "\n\n" + ABK_ANHANG + "\n\n" + ABK_ANHANG2
        # ~910 Wörter: Kontingent 1, die Familie „ca.“ hat 2 Treffer – v5: ganz genannt, weil das Ergebnis unter P75 bleibt
        c = coach.coache(text, None, 40, roh=True)
        abk = [h for h in c["hinweise_roh"] if h["typ"] == "abkuerzung"]
        self.assertEqual(len(abk), 1, [h["text"] for h in abk])
        self.assertEqual(abk[0]["funde"], ["rund", "etwa"])
        self.assertIn("„rund“ und „etwa“ als „ca.“", abk[0]["text"])
        self.assertIn("einheitlich", abk[0]["text"])
        L = coach.Lauf(text, None)  # P75 künstlich gesenkt: die ganze Familie läge darüber → keiner (keine Mischform)
        coach._hebel_priorisieren(L)
        r = L.ref["abkuerzungen_pro_1000"]
        L.ref = dict(L.ref, abkuerzungen_pro_1000=dict(r, mensch=dict(r["mensch"], p75=1.5)))
        coach._abkuerzungen(L)
        self.assertFalse([h for h in L.hinweise if h["typ"] == "abkuerzung"])

    def test_hebel_auch_im_gruenen_bereich(self):
        c = coach.coache(ABK_TEXT + "\n" + ABK_ANHANG + "\n\n" + ABK_ANHANG2, None, 40)
        h = next((x for x in c["hebel"] if x["id"] == "abkuerzungen"), None)
        self.assertIsNotNone(h)
        z = h["kennzahlen"][0]
        self.assertEqual(z["status"], "gruen")
        self.assertLessEqual(z["beitrag"], coach.MODELL_HEBEL)
        c["hebel"] = [h] + [x for x in c["hebel"] if x is not h]
        self.assertIn("im Zielbereich, aber weit vom menschlichen Median", coach.bericht(c))


class Wirksamkeitsgedaechtnis(unittest.TestCase):
    def test_stand_speichert_ziel_und_wert(self):
        c = coach.coache(gleichmaessig(8, 5), None, 15)
        hs = [h for h in c["stand"]["hinweise"] if h["typ"] in coach.ZIEL_KENNZAHL]
        self.assertTrue(hs)
        for h in hs:
            self.assertEqual(h["ziel"], coach.ZIEL_KENNZAHL[h["typ"]])
            self.assertIsNotNone(h["ziel_wert"])
            self.assertIsNotNone(h["laenge"])
        self.assertIn("saetze_pro_absatz_cv", c["stand"]["werte"])

    def test_wirkungsloser_auftrag_wechselt_technik(self):
        text = gleichmaessig(8, 5)
        S = saetze_von(text)
        erster_abs3 = next(s for s in S if s["absatz"] == 3)  # beginnt schon einen Absatz: „befolgt“
        cv = analyse.analysiere_text(text)["metriken"]["saetze_pro_absatz_cv"]
        verlauf = {"messungen": [{"score": 40, "p_mensch": 0.05, "kennzahlen": {}, "roh": {},
                                  "hinweise": [{"typ": "absatz_teilen", "anfang": coach.schluessel_anfang(erster_abs3["text"]),
                                                "satz": erster_abs3["nr"], "ziel": "saetze_pro_absatz_cv", "ziel_wert": cv}]}]}
        c = coach.coache(text, verlauf, 40, roh=True)
        w = c["fortschritt"]["wirkung"]
        self.assertEqual([x["typ"] for x in w], ["absatz_teilen"])
        self.assertEqual(w[0]["wechsel"], "absatz_zusammen")
        self.assertIn("absatz_teilen", c["fortschritt"]["ausgesetzt"])
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "absatz_teilen"])
        self.assertIn("Wirkung geprüft", coach.bericht(c))

    def test_wirksamer_auftrag_bleibt(self):
        text = gleichmaessig(8, 5)
        S = saetze_von(text)
        erster_abs3 = next(s for s in S if s["absatz"] == 3)
        verlauf = {"messungen": [{"score": 40, "p_mensch": 0.05, "kennzahlen": {}, "roh": {},
                                  "hinweise": [{"typ": "absatz_teilen", "anfang": coach.schluessel_anfang(erster_abs3["text"]),
                                                "satz": erster_abs3["nr"], "ziel": "saetze_pro_absatz_cv", "ziel_wert": -0.5}]}]}
        c = coach.coache(text, verlauf, 40)
        self.assertFalse(c["fortschritt"]["wirkung"])  # Abstand zum Median kleiner geworden (−0,5 → 0): wirksam

    def test_unbefolgter_auftrag_wird_nicht_bewertet(self):
        text = gleichmaessig(8, 5)
        S = saetze_von(text)
        mitten = next(s for s in S if s["absatz"] == 3 and s["pos_im_absatz"] == 3)  # Absatzgrenze nicht gesetzt
        cv = analyse.analysiere_text(text)["metriken"]["saetze_pro_absatz_cv"]
        verlauf = {"messungen": [{"score": 40, "p_mensch": 0.05, "kennzahlen": {}, "roh": {},
                                  "hinweise": [{"typ": "absatz_teilen", "anfang": coach.schluessel_anfang(mitten["text"]),
                                                "satz": mitten["nr"], "ziel": "saetze_pro_absatz_cv", "ziel_wert": cv}]}]}
        c = coach.coache(text, verlauf, 40)
        self.assertFalse(c["fortschritt"]["wirkung"])


if __name__ == "__main__":
    unittest.main()
