"""Tests für kalibrierung/scripts/kalibriere.py (python3 -m unittest discover -s tests)."""
import contextlib
import csv
import io
import json
import math
import os
import random
import shutil
import sys
import tempfile
import unittest
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "kalibrierung", "scripts"))
import kalibriere  # noqa: E402
import analyse  # noqa: E402  (Pfad setzt kalibriere)
import referenzen  # noqa: E402

MUSTER_PFAD = os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "data", "ki_muster.json")
INHALT = ["arbeit", "markt", "bildung", "studie", "ergebnis", "prozess", "gruppe", "wandel", "methode", "theorie",
          "praxis", "politik", "wirkung", "rolle", "frage", "grenze", "ebene", "folge", "entwicklung", "schule"]


def satz(rnd, n, fw):
    woerter = [rnd.choice(INHALT) if i % 2 else rnd.choice(fw) for i in range(n)]
    return woerter[0].capitalize() + " " + " ".join(woerter[1:]) + "."


def text_erzeugen(rnd, woerter_ziel, laengen, fw, saetze_pro_absatz=6):
    absaetze, n = [], 0
    while n < woerter_ziel:
        s = [satz(rnd, rnd.randint(*laengen), fw) for _ in range(saetze_pro_absatz)]
        n += sum(len(x.split()) for x in s)
        absaetze.append(" ".join(s))
    return "\n\n".join(absaetze)


FW_MENSCH = ["es", "wie", "auch", "durch", "die", "der", "und", "in", "es", "wie", "auch"]
FW_KI = ["als", "sich", "dass", "die", "der", "und", "in", "als", "sich"]


class Zerlegen(unittest.TestCase):
    def text(self, absaetze, woerter=500):
        return "\n\n".join(" ".join(f"wort{i}x" for _ in range(woerter)) for i in range(absaetze))

    def test_max_ein_abschnitt_nimmt_mittleren(self):
        t = self.text(6)
        alle = kalibriere.zerlege(t, max_abschnitte=100)
        self.assertGreaterEqual(len(alle), 2)
        eins = kalibriere.zerlege(t, max_abschnitte=1)  # früher ZeroDivisionError
        self.assertEqual(eins, [alle[len(alle) // 2]])

    def test_drei_abschnitte_unveraendert(self):
        t = self.text(12)
        alle = kalibriere.zerlege(t, max_abschnitte=100)
        idx = sorted({round(i * (len(alle) - 1) / 2) for i in range(3)})
        self.assertEqual(kalibriere.zerlege(t, max_abschnitte=3), [alle[i] for i in idx])

    def test_cli_lehnt_null_ab(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            kalibriere.main(["--max-abschnitte", "0"])


class Kuerzen(unittest.TestCase):
    def setUp(self):
        rnd = random.Random(3)
        self.text = "## Kapitelüberschrift\n\n" + text_erzeugen(rnd, 400, (8, 14), FW_MENSCH)

    def woerter(self, t):
        return sum(x for a in analyse.zerlege_bloecke(t)["absaetze"] for _, x in kalibriere._saetze_mit_woertern(a))

    def test_kuerzt_an_satzgrenze(self):
        k = kalibriere.kuerze(self.text, L=200)
        n = self.woerter(k)
        self.assertLessEqual(n, 200)
        self.assertGreaterEqual(n, 190)
        self.assertTrue(k.rstrip().endswith("."))
        self.assertNotIn("Kapitelüberschrift", k)  # Überschriften zählen nicht und fallen weg
        absaetze = k.split("\n\n")
        self.assertTrue(all(a in self.text for a in absaetze[:-1]))  # ganze Absätze im Wortlaut
        erg = analyse.analysiere_text(k, [])
        self.assertEqual(erg["info"]["woerter"], n)

    def test_zu_kurz_wird_verworfen(self):
        self.assertIsNone(kalibriere.kuerze(self.text, L=2000))
        self.assertIsNotNone(kalibriere.kuerze(self.text, L=self.woerter(self.text) + 5))  # ≥ 0,95·L reicht

    def test_letzter_absatz_zaehlt_nicht(self):
        if not kalibriere._MIT_KUERZUNG:
            self.skipTest("analyse.py ohne letzter_absatz_gekuerzt")
        k = kalibriere.kuerze(self.text, L=200)
        voll = analyse.analysiere_text(k, [])
        gek = kalibriere.analysiere_abschnitt(k, [])
        self.assertEqual(gek["metriken"]["absaetze"], voll["metriken"]["absaetze"] - 1)
        self.assertEqual(gek["metriken"]["satzlaenge_mittel"], voll["metriken"]["satzlaenge_mittel"])


class LogOdds(unittest.TestCase):
    def test_monoton_in_gegenzaehlung(self):
        base_a, base_b = Counter({"_rest": 153_000}), Counter({"_rest": 1_680_000})
        zs = []
        for yb in (0, 1, 2, 5, 20):
            a = base_a + Counter({"x": 40})
            b = base_b + (Counter({"x": yb}) if yb else Counter())
            zs.append(kalibriere.log_odds(a, b, a + b)["x"])
        self.assertTrue(all(z1 > z2 for z1, z2 in zip(zs, zs[1:])), zs)

    def test_gleiche_relative_haeufigkeit_neutral(self):
        a = Counter({"x": 100, "_rest": 100_000})
        b = Counter({"x": 300, "_rest": 300_000})
        self.assertLess(abs(kalibriere.log_odds(a, b, a + b)["x"]), 0.05)


class Statistik(unittest.TestCase):
    def test_gewichtetes_perzentil_gleiche_gewichte(self):
        rnd = random.Random(1)
        xs = [rnd.gauss(0, 1) for _ in range(37)]
        for p in (0.1, 0.25, 0.5, 0.75, 0.9):
            self.assertAlmostEqual(kalibriere.gewichtetes_perzentil(xs, [1.0] * len(xs), p), analyse.perzentil(xs, p))

    def test_dokumentgewicht(self):
        xs = [0, 0, 0, 1, 2, 3]  # Dokument A mit drei Abschnitten, B/C/D mit je einem
        ws = [1 / 3] * 3 + [1, 1, 1]
        self.assertAlmostEqual(analyse.perzentil(xs, 0.5), 0.5)
        self.assertAlmostEqual(kalibriere.gewichtetes_perzentil(xs, ws, 0.5), 4 / 3)
        z = kalibriere.zusammenfassung(xs, ws)
        self.assertAlmostEqual(z["mittel"], 1.5)  # = Mittel der Dokumentmittel
        self.assertEqual(z["n"], 6)

    def test_se_typ(self):
        se = kalibriere.se_typ({"A": [1, 3], "B": [2, 2, 5], "C": [7], "D": [None, 4]})
        self.assertAlmostEqual(se, math.sqrt(8 / 3))
        self.assertIsNone(kalibriere.se_typ({"A": [1], "B": [2]}))

    def test_auroc(self):
        self.assertEqual(kalibriere.auroc([3, 4], [1, 2]), 1.0)
        self.assertEqual(kalibriere.auroc([1, 1], [1, 1]), 0.5)


class PaarGate(unittest.TestCase):
    def test_trennbare_paare(self):
        h, k = [100 + i for i in range(20)], list(range(20))
        ps = kalibriere.paar_statistik(h, k, kalibriere.bootstrap_ziehungen(20, 200))
        self.assertEqual(ps["auroc"], 1.0)
        self.assertEqual(ps["vorzeichen"], 1.0)
        self.assertTrue(kalibriere.gate_bestanden(0.9, ps))
        self.assertFalse(kalibriere.gate_bestanden(0.2, ps))  # Richtung widerspricht

    def test_zufall_besteht_nicht(self):
        rnd = random.Random(5)
        h = [rnd.gauss(0, 1) for _ in range(60)]
        k = [rnd.gauss(0, 1) for _ in range(60)]
        ps = kalibriere.paar_statistik(h, k, kalibriere.bootstrap_ziehungen(60, 200))
        self.assertFalse(kalibriere.gate_bestanden(0.7, ps))

    def test_zu_wenige_paare(self):
        self.assertIsNone(kalibriere.paar_statistik([1, 2, None], [0, 1, 2]))

    def test_bootstrap_wie_explizite_ziehung(self):
        rnd = random.Random(2)
        h = [rnd.randint(0, 3) for _ in range(15)]  # mit Bindungen
        k = [rnd.randint(0, 3) for _ in range(15)]
        c = kalibriere.bootstrap_ziehungen(15, 1, seed=9)[0]
        hx = [v for v, n in zip(h, c) for _ in range(n)]
        kx = [v for v, n in zip(k, c) for _ in range(n)]
        ps = kalibriere.paar_statistik(h, k, [c])
        self.assertAlmostEqual(ps["auroc_ci"][0], kalibriere.auroc(hx, kx))
        self.assertAlmostEqual(kalibriere.paar_statistik(h, k)["auroc"], kalibriere.auroc(h, k))


class Cluster(unittest.TestCase):
    def test_greedy_und_deckel(self):
        rnd = random.Random(4)
        x = [rnd.gauss(0, 1) for _ in range(200)]
        spalten = {"a": x, "b": [v + rnd.gauss(0, 0.1) for v in x], "c": [rnd.gauss(0, 1) for _ in range(200)]}
        spalten["b"][3] = None  # Lücken werden paarweise übergangen
        z = kalibriere.cluster_bilden(["a", "c", "b"], spalten)
        self.assertEqual(z, {"a": "a", "c": "c", "b": "a"})
        g = kalibriere.cluster_gewichte(z, {"a": 0.6, "b": 0.4, "c": 0.5})
        self.assertAlmostEqual(g["a"] + g["b"], 0.6)
        self.assertAlmostEqual(g["a"], 0.36)
        self.assertAlmostEqual(g["c"], 0.5)


class Funktionswoerter(unittest.TestCase):
    def zeile(self, g, n, k):
        return {"gruppe": g, "_n": n, "_fw": k}

    def test_raten_und_groesse(self):
        zeilen = [self.zeile("mensch", 1000, {"es": 5}), self.zeile("mensch", 1000, {"es": 15}),
                  self.zeile("ki", 1000, {"es": 2}), self.zeile("ki", 1000, {"es": 4})]
        p = kalibriere.fw_profil_schaetzen(zeilen, ["es"])
        r_m, r_k = 20.5 / 2000, 6.5 / 2000
        self.assertAlmostEqual(p["rate_mensch"]["es"], r_m)
        self.assertAlmostEqual(p["rate_ki"]["es"], r_k)
        mu = [r_m * 1000, r_m * 1000, r_k * 1000, r_k * 1000]
        k = [5, 15, 2, 4]
        s = sum(m * m for m in mu) / sum((kk - m) ** 2 - m for kk, m in zip(k, mu))
        self.assertAlmostEqual(p["groesse"]["es"], round(s, 3))

    def test_unterdispers_poisson(self):
        zeilen = [self.zeile("mensch", 1000, {"es": 10}), self.zeile("mensch", 1000, {"es": 10}),
                  self.zeile("ki", 1000, {"es": 5}), self.zeile("ki", 1000, {"es": 5})]
        self.assertEqual(kalibriere.fw_profil_schaetzen(zeilen, ["es"])["groesse"]["es"], kalibriere.FW_POISSON)

    def test_llr_wie_analyse(self):
        rnd = random.Random(8)
        text = text_erzeugen(rnd, 300, (8, 14), FW_MENSCH)
        profil = {"woerter": ["es", "wie", "als", "sich", "und"],
                  "rate_mensch": {"es": 0.02, "wie": 0.02, "als": 0.005, "sich": 0.005, "und": 0.03},
                  "rate_ki": {"es": 0.01, "wie": 0.01, "als": 0.01, "sich": 0.01, "und": 0.03},
                  "groesse": {"es": 8.0, "wie": 1e6, "als": 3.5, "sich": 20.0, "und": 50.0}}
        erg = analyse.analysiere_text(text, [])
        n, k = kalibriere.fw_zaehlung(erg, text, profil["woerter"])
        eigen = kalibriere.fw_llr_zaehlung(k, n, profil)
        self.assertGreater(eigen, 0)  # Text nutzt es/wie häufig: menschlicher
        n2, k2 = kalibriere.fw_zaehlung({}, text, profil["woerter"])  # Fallback ohne erg['fw_zaehlung']
        self.assertEqual((n, k), (n2, k2))
        if not hasattr(analyse, "fw_llr"):
            self.skipTest("analyse.fw_llr fehlt")
        self.assertAlmostEqual(eigen, analyse.fw_llr(kalibriere._woerter_low(text), profil))
        mit = analyse.analysiere_text(text, [], fw_profil=profil)
        self.assertAlmostEqual(mit["metriken"]["fw_profil_llr_pro_1000"], round(eigen, 4))


class Modell(unittest.TestCase):
    def test_konvergiert_bei_trennbaren_daten(self):
        X = [[1.0]] * 10 + [[-1.0]] * 100  # trennbar, unbalanciert, symmetrisch
        y = [1] * 10 + [0] * 100
        w, b = kalibriere.logreg(X, y, lam=0.03)
        self.assertTrue(0 < w[0] < 100)
        self.assertAlmostEqual(b, 0.0, places=6)  # Klassen balanciert
        # Gradient des Ziels ≈ 0
        gew = [0.5 / 10 if yi else 0.5 / 100 for yi in y]
        g = sum(gi * (kalibriere.vorhersage(w, b, x) - yi) * x[0] for x, yi, gi in zip(X, y, gew)) + 0.03 * w[0]
        self.assertLess(abs(g), 1e-6)

    def test_mehr_strafe_kleinere_gewichte(self):
        rnd = random.Random(6)
        X = [[rnd.gauss(1 if i % 2 else -1, 1), rnd.gauss(0, 1)] for i in range(200)]
        y = [i % 2 for i in range(200)]
        w1, _ = kalibriere.logreg(X, y, lam=0.001)
        w2, _ = kalibriere.logreg(X, y, lam=0.3)
        self.assertGreater(abs(w1[0]), abs(w2[0]))
        self.assertGreater(w1[0], 0)

    def test_gruppen_folds(self):
        themen = [f"t{i}" for i in range(23)] * 2
        z = kalibriere.gruppen_folds(themen, 5, random.Random(1))
        self.assertEqual(set(z), set(themen))
        groessen = Counter(z.values())
        self.assertLessEqual(max(groessen.values()) - min(groessen.values()), 1)

    def test_konfiguration_ein_standardfehler(self):
        erg = {(6, 0.1): [{"logloss_bal": v} for v in (0.30, 0.31, 0.29)],
               (9, 0.01): [{"logloss_bal": v} for v in (0.10, 0.12, 0.08)],
               (15, 0.001): [{"logloss_bal": v} for v in (0.09, 0.11, 0.07)]}
        self.assertEqual(kalibriere.waehle_konfiguration(erg), (9, 0.01))


class ZClipping(unittest.TestCase):
    """S1: z = max(−Z_CLIP, min(Z_CLIP, (x − mittel)/sd)) in Fit, OOF-Vorhersage und Goodhart-Analyse."""

    def paket(self):
        return {"mittel": {"a": 0.0, "b": 10.0}, "sd": {"a": 1.0, "b": 2.0}}

    def test_konstante_wie_analyse(self):
        self.assertEqual(kalibriere.Z_CLIP, getattr(analyse, "Z_CLIP", 3.0))

    def test_z_wert(self):
        self.assertEqual(kalibriere.z_wert(100.0, 0.0, 1.0), kalibriere.Z_CLIP)
        self.assertEqual(kalibriere.z_wert(-100.0, 0.0, 1.0), -kalibriere.Z_CLIP)
        self.assertAlmostEqual(kalibriere.z_wert(13.0, 10.0, 2.0), 1.5)
        self.assertEqual(kalibriere.z_wert(None, 10.0, 2.0), 0.0)  # fehlend = Mittelwert, wie bewerte()
        self.assertEqual(kalibriere.z_wert(5.0, 4.0, 0.0), 1.0)    # SD 0 → 1

    def test_p_mensch_begrenzt(self):
        modell = {"merkmale": ["a", "b"], "w": [1.5, -0.5], "b": 0.2}
        p_rand = kalibriere.p_mensch(modell, self.paket(), {"a": 3.0, "b": 10.0})
        self.assertAlmostEqual(kalibriere.p_mensch(modell, self.paket(), {"a": 40.0, "b": 10.0}), p_rand)
        self.assertLess(kalibriere.p_mensch(modell, self.paket(), {"a": 2.0, "b": 10.0}), p_rand)
        z = 0.2 + 1.5 * 3.0 - 0.5 * (-3.0)
        self.assertAlmostEqual(kalibriere.p_mensch(modell, self.paket(), {"a": 9.0, "b": -50.0}), 1 / (1 + math.exp(-z)))

    def test_fit_auf_begrenzten_werten(self):
        rnd = random.Random(7)
        daten = [{"gruppe": "mensch" if i % 2 else "ki", "a": rnd.gauss(1 if i % 2 else -1, 1)} for i in range(120)]
        daten[0]["a"] = 60.0  # Ausreißer
        paket = {"rang": ["a"], "mittel": {"a": 0.0}, "sd": {"a": 1.0}, "daten": daten}
        mod = kalibriere.fit_modell(paket, 1, 0.01)
        spalte = [max(-3.0, min(3.0, z["a"])) for z in daten]
        w, b = kalibriere.logreg_spalten([spalte], [1 if z["gruppe"] == "mensch" else 0 for z in daten], 0.01)
        self.assertAlmostEqual(mod["w"][0], w[0], places=6)
        self.assertAlmostEqual(mod["b"], b, places=6)


class Auswahl(unittest.TestCase):
    def test_lambda_gitter(self):
        g = kalibriere.MODELL_LAMBDA
        self.assertGreaterEqual(len(g), 10)
        self.assertLessEqual(min(g), 0.001)
        self.assertGreaterEqual(max(g), 30)
        self.assertEqual(list(g), sorted(g, reverse=True))  # absteigend: Warmstart von der starken Strafe aus
        schritte = [math.log10(a / b) for a, b in zip(g, g[1:])]
        self.assertLess(max(schritte) - min(schritte), 0.01)  # log-gleichabständig (bis auf Rundung)

    def test_lambda_richtung_staerkere_regularisierung(self):
        erg = {(6, lam): [{"logloss_bal": v + d} for d in (-0.02, 0.0, 0.02)]
               for lam, v in ((10.0, 0.40), (1.0, 0.21), (0.1, 0.205), (0.01, 0.20), (0.001, 0.20))}
        erg.update({(9, lam): [{"logloss_bal": v + d} for d in (-0.02, 0.0, 0.02)]
                    for lam, v in ((1.0, 0.30), (0.1, 0.25), (0.01, 0.19), (0.001, 0.19))})
        details = {}
        # bestes 0,19 ± SE 0,0115 → k = 6 (0,20 ≤ 0,2015); für k = 6: Minimum 0,20 + SE → größtes λ mit ≤ 0,2115 ist 1,0
        self.assertEqual(kalibriere.waehle_konfiguration(erg, details), (6, 1.0))
        self.assertEqual(details["k"], 6)
        self.assertEqual(details["lambda"], 1.0)
        self.assertAlmostEqual(details["grenze_lambda"], 0.20 + 0.02 / math.sqrt(3))
        self.assertFalse(details["lambda_am_rand"])

    def test_auswahl_json_behaelt_gitterwerte(self):
        # Prüfer-Fund: round(λ, 5) machte aus 0,003162 den Nicht-Gitterwert 0,00316 (aus 0,0003162 → 0,00032)
        erg = {(6, lam): [{"logloss_bal": 0.2 + d + (0.0 if lam < 0.001 else 0.05)} for d in (-0.01, 0.0, 0.01)]
               for lam in kalibriere.MODELL_LAMBDA}
        details = {}
        k, lam = kalibriere.waehle_konfiguration(erg, details)
        j = kalibriere.auswahl_json(details)
        self.assertEqual(j["lambda"], lam)
        self.assertIn(j["bestes"]["lambda"], kalibriere.MODELL_LAMBDA)
        self.assertEqual(j["lambda_gitter"], sorted(kalibriere.MODELL_LAMBDA))
        self.assertEqual(kalibriere.auswahl_json({"lambda": 0.003162, "x": {"se": 0.0041934}})["x"]["se"], 0.004193)


class KalibrierungsGuete(unittest.TestCase):
    def test_brier(self):
        self.assertEqual(kalibriere.brier([1.0, 0.0], [1, 0]), 0.0)
        self.assertAlmostEqual(kalibriere.brier([0.5] * 4, [1, 1, 1, 0]), 0.25)
        # balanciert: jede Klasse zählt halb, unabhängig von ihrer Größe
        self.assertAlmostEqual(kalibriere.brier([0.9, 0.9, 0.9, 0.4], [1, 1, 1, 0], balanciert=True), 0.5 * 0.01 + 0.5 * 0.16)

    def test_ece(self):
        ps = [0.2] * 5 + [0.8] * 5
        ys = [1, 0, 0, 0, 0] + [1, 1, 1, 1, 0]
        self.assertAlmostEqual(kalibriere.ece(ps, ys), 0.0)
        self.assertAlmostEqual(kalibriere.ece([0.95] * 4, [1, 0, 1, 0]), 0.45)
        rel = kalibriere.reliabilitaet([1.0, 0.0, 0.05], [1, 0, 0])
        self.assertEqual(len(rel), kalibriere.ECE_KLASSEN)
        self.assertEqual((rel[-1]["n_mensch"], rel[0]["n_ki"]), (1, 2))  # p = 1 fällt in die letzte Klasse
        self.assertIsNone(rel[5]["p_mittel"])

    def test_kalibrierungs_guete(self):
        g = kalibriere.kalibrierungs_guete([0.9, 0.8, 0.95, 0.1, 0.3], [1, 1, 1, 0, 0])
        self.assertEqual(set(g["perzentile"]), {"mensch", "ki"})
        self.assertEqual(set(g["perzentile"]["mensch"]), {"p5", "p10", "p25", "p50", "p75", "p90", "p95"})
        self.assertAlmostEqual(g["perzentile"]["mensch"]["p50"], 0.9)
        for k in ("brier", "brier_bal", "ece", "ece_bal", "reliabilitaet"):
            self.assertIn(k, g)

    def test_ziel_p_mensch(self):
        self.assertEqual(kalibriere.ziel_p_mensch_von([0.999] * 50), 0.95)   # Deckel
        self.assertEqual(kalibriere.ziel_p_mensch_von([0.2] * 50), 0.5)      # Boden
        ps = [0.5 + i / 200 for i in range(100)]
        self.assertEqual(kalibriere.ziel_p_mensch_von(ps), round(analyse.perzentil(ps, 0.10), 2))
        self.assertEqual(kalibriere.ziel_p_mensch_von(ps), 0.55)


class Goodhart(unittest.TestCase):
    def setUp(self):
        daten = [{"gruppe": "ki", "a": -2.0 + 0.1 * i, "b": 1.0, "c": None if i == 4 else -1.0} for i in range(5)]
        daten += [{"gruppe": "mensch", "a": 2.0, "b": 0.0, "c": 1.0}]
        metriken = {k: {"mensch": {"p50": p}} for k, p in (("a", 2.0), ("b", 0.0), ("c", 1.0))}
        self.paket = {"daten": daten, "metriken": metriken, "mittel": {"a": 0.0, "b": 0.0, "c": 0.0},
                      "sd": {"a": 1.0, "b": 1.0, "c": 1.0}}
        self.modell = {"merkmale": ["a", "b", "c"], "w": [2.0, -1.0, 0.5], "b": 0.0}

    def test_kontrafaktisch(self):
        gh = kalibriere.goodhart_analyse(self.modell, self.paket, ziel_p=0.5, top_n=2)
        self.assertEqual(gh["n_ki"], 5)
        zeilen = {r["id"]: r for r in gh["merkmale"]}
        # Logits −5,5 −5,3 −5,1 −4,9 −4,2 (i = 4 ohne c); Median i = 2: 2·(−1,8) − 1 − 0,5 = −5,1.
        # Nur a auf den Mensch-Median 2: Logit + 2·(2 − a) → 2,5 2,5 2,5 2,5 3,0, Median 2,5
        self.assertAlmostEqual(gh["median_p_ki"], round(1 / (1 + math.exp(5.1)), 4))
        self.assertAlmostEqual(zeilen["a"]["median_p"], round(1 / (1 + math.exp(-2.5)), 4))
        self.assertTrue(zeilen["a"]["ueber_ziel"])
        self.assertFalse(zeilen["b"]["ueber_ziel"])
        self.assertAlmostEqual(zeilen["a"]["median_beitrag_ki"], 2.0 * (-1.8 - 2.0))
        self.assertAlmostEqual(zeilen["c"]["median_beitrag_ki"], 0.5 * (-1.0 - 1.0))  # nur Abschnitte mit Wert
        self.assertEqual(gh["merkmale"][0]["id"], "a")  # nach Median-Änderung sortiert
        self.assertEqual(gh["top"]["ids"], ["a", "b"])  # stärkster KI-Zug zuerst
        self.assertTrue(gh["top"]["ueber_ziel"])

    def test_begrenzt(self):
        self.paket["daten"][2]["a"] = -50.0  # Ausreißer: Beitrag höchstens koef · (−3 − z(Median))
        gh = kalibriere.goodhart_analyse(self.modell, self.paket, ziel_p=0.5)
        self.assertGreaterEqual(min(r["median_beitrag_ki"] for r in gh["merkmale"]), 2.0 * (-3.0 - 2.0))


class ScoreWieBewerte(unittest.TestCase):
    def test_score_stimmt_mit_analyse_ueberein(self):
        def ref(p10, p25, p50, p75, p90, gewicht, bewertet=True):
            return {"mensch": {"p10": p10, "p25": p25, "p50": p50, "p75": p75, "p90": p90, "sd": 1.0},
                    "ki": {"p50": p50 + 1, "sd": 1.0}, "auroc": 0.8, "gewicht": gewicht, "bewertet": bewertet}
        metriken = {"a": ref(0, 1, 2, 3, 4, 0.5), "b": ref(0, 1, 2, 3, 4, 0.3), "c": ref(0, 1, 2, 3, 4, 0.2),
                    "rhythmus_r1_log": ref(0, 1, 2, 3, 4, 0.4), "d": ref(0, 1, 2, 3, 4, 0.0, bewertet=False),
                    "e": ref(0, 1, 2, 3, 4, 0.7)}
        z = {"a": 2.0, "b": 0.5, "c": 9.0, "rhythmus_r1_log": 9.0, "d": 9.0, "e": None, "saetze": 25}
        baselines = {"textsorten": {"hochschule": {"metriken": metriken}}}
        ergebnis = {"metriken": {k: v for k, v in z.items() if k != "saetze"}, "info": {"saetze": 25}}
        s = kalibriere.score(metriken, z)
        self.assertAlmostEqual(s, 100 * (0.5 + 0.15) / 1.0)
        self.assertEqual(analyse.bewerte(ergebnis, baselines)["score"], round(s))


class EndeZuEnde(unittest.TestCase):
    """Kleiner synthetischer Korpus: Lauf mit eigenen Ausgabepfaden, Plugin-Daten bleiben unberührt."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        rnd = random.Random(11)
        korpus = os.path.join(cls.tmp, "korpus")
        for q in ("q1", "q2"):
            os.makedirs(os.path.join(korpus, "mensch", q))
        os.makedirs(os.path.join(korpus, "ki", "claude"))
        meta_m = {"q1": [], "q2": []}
        meta_k = []
        for i in range(14):
            q = "q1" if i % 2 else "q2"
            mid, kid = f"m{i:02d}", f"k{i:02d}"
            with open(os.path.join(korpus, "mensch", q, mid + ".txt"), "w", encoding="utf-8") as f:
                f.write(text_erzeugen(rnd, 2800, (4, 38), FW_MENSCH))
            with open(os.path.join(korpus, "ki", "claude", kid + ".txt"), "w", encoding="utf-8") as f:
                f.write(text_erzeugen(rnd, 1000, (15, 19), FW_KI))
            meta_m[q].append({"id": mid, "quelle": q, "typ": "Bachelorarbeit", "jahr": 2005 + i})
            meta_k.append({"id": kid, "basis_id": mid, "quelle": "claude", "typ": "Bachelorarbeit"})
        for q, zeilen in meta_m.items():
            with open(os.path.join(korpus, "mensch", q, "meta.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(z) for z in zeilen) + "\n")
        with open(os.path.join(korpus, "ki", "claude", "meta.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(z) for z in meta_k) + "\n")
        cls.aus = os.path.join(cls.tmp, "aus")
        cls.daten = os.path.join(cls.tmp, "daten")
        os.makedirs(cls.daten)
        shutil.copy(MUSTER_PFAD, os.path.join(cls.daten, "ki_muster.json"))
        cls.plugin_vorher = os.path.getmtime(MUSTER_PFAD)
        stderr = sys.stderr
        stdout = sys.stdout
        sys.stderr = sys.stdout = open(os.devnull, "w")
        try:
            cls.rc = kalibriere.main(["--korpus", korpus, "--aus", cls.aus, "--baselines", os.path.join(cls.daten, "baselines.json"),
                                      "--muster", os.path.join(cls.daten, "ki_muster.json"), "--cv-wiederholungen", "2",
                                      "--cv-folds", "2", "--bootstrap", "100"])
        finally:
            sys.stderr.close()
            sys.stderr, sys.stdout = stderr, stdout
        with open(os.path.join(cls.daten, "baselines.json"), encoding="utf-8") as f:
            cls.b = json.load(f)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_dateien(self):
        self.assertEqual(self.rc, 0)
        for pfad in (os.path.join(self.aus, "features.csv"), os.path.join(self.aus, "bericht.md"),
                     os.path.join(self.aus, "wortlisten.json"), os.path.join(self.daten, "wortlisten.json")):
            self.assertTrue(os.path.exists(pfad), pfad)
        self.assertEqual(os.path.getmtime(MUSTER_PFAD), self.plugin_vorher)
        with open(os.path.join(self.aus, "features.csv"), encoding="utf-8") as f:
            zeilen = list(csv.DictReader(f))
        self.assertEqual(sum(z["gruppe"] == "ki" for z in zeilen), 14)
        self.assertTrue(all(760 <= int(z["woerter"]) <= 800 for z in zeilen))
        self.assertIn("fw_profil_llr_pro_1000", zeilen[0])
        with open(os.path.join(self.aus, "bericht.md"), encoding="utf-8") as f:
            bericht = f.read()
        for teil in ("Kreuzvalidierung", "Cluster redundanter Kennzahlen", "AUROC je Quelle", "Erscheinungsjahr",
                     "Wahl von k und λ", "Brier-Score", "ECE", "Reliabilitätstabelle", "score_schwelle = ", "ziel_p_mensch = ",
                     "Goodhart-Sensitivität"):
            self.assertIn(teil, bericht)

    def test_baselines_struktur(self):
        t = self.b["textsorten"]["hochschule"]
        self.assertEqual(t["fw_profil"]["woerter"], list(getattr(analyse, "FW_WOERTER", kalibriere.FW_PILOT)))
        self.assertEqual(set(t["fw_profil"]["rate_mensch"]), set(t["fw_profil"]["woerter"]))
        self.assertGreaterEqual(t["ziel_p_mensch"], 0.5)
        self.assertLessEqual(t["ziel_p_mensch"], 0.95)
        self.assertIn("score_schwelle", t)
        self.assertEqual(self.b["version"], "4")  # v4: einseitige Kappung (v7)
        self.assertEqual(t["modell"]["z_clip"], kalibriere.Z_CLIP)
        self.assertIn(t["modell"]["lambda"], kalibriere.MODELL_LAMBDA)
        gh = t["goodhart"]
        self.assertEqual({r["id"] for r in gh["merkmale"]}, set(t["modell"]["koeffizienten"]))
        self.assertLessEqual(len(gh["top"]["ids"]), kalibriere.GOODHART_TOP)
        kg = self.b["evaluation"]["modell_oof_kalibrierung"]
        self.assertEqual(len(kg["reliabilitaet"]), kalibriere.ECE_KLASSEN)
        self.assertTrue(0 <= kg["brier"] <= 1 and 0 <= kg["ece"] <= 1)
        self.assertIn("auswahl", self.b["evaluation"]["hyperparameter"])
        self.assertEqual(self.b["evaluation"]["hyperparameter"]["auswahl"]["lambda"], t["modell"]["lambda"])
        self.assertEqual(self.b["korpus"]["paare"], 14)
        ev = self.b["evaluation"]
        self.assertIn("auroc_sd", ev["modell_cv"])
        self.assertEqual(ev["modell_cv"]["folds"], 4)
        met = t["metriken"]
        self.assertIn("fw_profil_llr_pro_1000", met)
        self.assertGreater(met["fw_profil_llr_pro_1000"]["auroc"], 0.9)
        self.assertFalse(met["fw_profil_llr_pro_1000"]["bewertet"])  # nur Modell
        for k in ("rhythmus_sprung_rel", "menzerath_korrelation", "anteil_funktionswoerter"):
            if k in met:
                self.assertFalse(met[k]["bewertet"], k)
        self.assertTrue(any("se_typ" in v for v in met.values()))
        bew = [k for k, v in met.items() if v["bewertet"]]
        self.assertTrue(bew)
        for k in bew:
            self.assertIn(met[k]["cluster"], t["cluster"])
            self.assertTrue(met[k]["gate"])
        for kopf, mitglieder in t["cluster"].items():
            self.assertLessEqual(sum(met[m]["gewicht"] for m in mitglieder), max(met[m]["trennschaerfe"] for m in mitglieder) + 0.002)

    def test_bewerte_mit_neuen_baselines(self):
        rnd = random.Random(12)
        text = text_erzeugen(rnd, 800, (4, 38), FW_MENSCH)
        t = self.b["textsorten"]["hochschule"]
        erg = analyse.analysiere_text(text, [], fw_profil=t["fw_profil"])
        bew = analyse.bewerte(erg, self.b)
        self.assertTrue(bew["verfuegbar"])
        self.assertIsNotNone(bew["p_mensch"])
        self.assertEqual(bew["ziel_p_mensch"], t["ziel_p_mensch"])
        if not hasattr(analyse, "Z_CLIP"):
            self.skipTest("analyse.bewerte ohne z-Clipping (S1)")
        # S1: dieselbe Wahrscheinlichkeit wie das Modell in kalibriere.py, auch für Werte jenseits von ±3 SD
        mod = t["modell"]
        werte = dict(erg["metriken"])
        k0 = next(iter(mod["koeffizienten"]))
        werte[k0] = mod["mittel"][k0] + 10 * mod["sd"][k0]
        erg["metriken"][k0] = werte[k0]
        kappen = mod.get("kappen") or {}  # v7: einseitige Kappung vor der Standardisierung, wie bewerte()
        logit = mod["intercept"] + sum(c * kalibriere.z_wert(werte.get(k), mod["mittel"][k], mod["sd"][k], kappen.get(k))
                                       for k, c in mod["koeffizienten"].items())
        self.assertAlmostEqual(analyse.bewerte(erg, self.b)["p_mensch"], 1 / (1 + math.exp(-logit)), delta=0.0006)

    def test_referenzen_aus_neuen_baselines(self):
        t = self.b["textsorten"]["hochschule"]
        ziel = referenzen.zielwerte(self.b)
        kenn = referenzen.kennzahlen(self.b)
        for teil in ("## Schwellen", "Brier-Score", "ECE", "## Goodhart-Sensitivität des Modells", "P10 der menschlichen"):
            self.assertIn(teil, kenn)
        nur_modell = [k for k, v in t["metriken"].items() if v.get("nur_modell")]
        if nur_modell:
            self.assertIn("## Nur als Tendenz", ziel)
            tabelle = ziel.split("## Bewertete Kennzahlen")[1].split("\n## ")[0]
            for k in nur_modell:
                self.assertNotIn(analyse.NAMEN.get(k, k), tabelle)  # kein Zielbereich
                self.assertIn(analyse.NAMEN.get(k, k), ziel.split("## Nur als Tendenz")[1])
        for k in ("fw_profil_llr_pro_1000", "satzklammer_mittel", "teilsatz_verhaeltnis_21", "rhythmus_r1_log",
                  "konnektoren_pro_1000", "abkuerzungen_pro_1000", "nominalketten_pro_100", "silben_q21", "mattr_klumpung_100"):
            self.assertGreater(len(referenzen.ERKLAERUNG.get(k, "")), 40, k)
        self.assertNotIn("rhythmus_autokorrelation", referenzen.ERKLAERUNG)


if __name__ == "__main__":
    unittest.main()
