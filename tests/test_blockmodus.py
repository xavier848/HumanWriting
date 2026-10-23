"""Schnittstellen v3 in analyse.py: z-Clipping (S1), Modellbeiträge (S2), unsicher-Regel (S3), Blockmodus (S4).

python3 -m unittest discover -s tests
"""
import contextlib
import copy
import io
import json
import math
import os
import random
import statistics
import sys
import tempfile
import time
import unittest
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
import analyse  # noqa: E402

NOMEN = ["Analyse", "Studie", "Ergebnis", "Methode", "Daten", "Stichprobe", "Hypothese", "Theorie", "Befragung",
         "Unternehmen", "Markt", "Entwicklung", "Forschung", "Praxis", "Bereich", "Ansatz", "Faktor", "Wirkung",
         "Gruppe", "Prozess", "Kommunikation", "Verwaltung", "Bildung", "Gesellschaft"]
VERBEN = ["zeigt", "beschreibt", "untersucht", "erklärt", "verändert", "beeinflusst", "betrifft", "bestätigt",
          "ergänzt", "prägt", "begründet", "erfasst"]
ADJEKTIVE = ["deutliche", "wichtige", "neue", "geringe", "starke", "klare", "aktuelle", "zentrale", "soziale"]
FUNKTION = ["die", "der", "und", "in", "es", "wie", "auch", "durch", "mit", "für", "nicht", "sich", "den", "eine"]


def satz(rnd: random.Random, n: int) -> str:
    """Satz aus genau n Buchstabenwörtern (alle zählen als bereinigte Wörter)."""
    woerter = [rnd.choice(NOMEN)]
    while len(woerter) < n:
        woerter.append(rnd.choice(rnd.choice([NOMEN, VERBEN, ADJEKTIVE, FUNKTION, FUNKTION])))
    return " ".join(woerter) + "."


def satzlaengen(rnd: random.Random, ziel: int, laengen=(5, 32)) -> list[int]:
    out, rest = [], ziel
    while rest > 0:
        n = rnd.randint(*laengen)
        if rest - n < laengen[0]:
            n = rest
        out.append(n)
        rest -= n
    return out


def absaetze(rnd: random.Random, ziel: int, saetze_je_absatz=(2, 7), laengen=(5, 32)) -> list[str]:
    """Absätze mit zusammen genau 'ziel' Wörtern."""
    ls = satzlaengen(rnd, ziel, laengen)
    out, i = [], 0
    while i < len(ls):
        k = rnd.randint(*saetze_je_absatz)
        out.append(" ".join(satz(rnd, n) for n in ls[i:i + k]))
        i += k
    return out


def text(rnd: random.Random, ziel: int, **kw) -> str:
    return "\n\n".join(absaetze(rnd, ziel, **kw))


def baselines_aus(referenz: str) -> dict:
    """Synthetische Referenzwerte um die Kennzahlen eines Referenztexts, mit kleinem Logit-Modell."""
    m = analyse.analysiere_text(referenz, [])["metriken"]
    metriken = {}
    for k, v in m.items():
        if v is None:
            continue
        sd = max(abs(v) * 0.25, 0.05)
        metriken[k] = {"mensch": {"p10": v - 1.28 * sd, "p25": v - 0.67 * sd, "p50": v, "p75": v + 0.67 * sd,
                                  "p90": v + 1.28 * sd, "mittel": v, "sd": sd},
                       "ki": {"p50": v - sd, "sd": sd}, "auroc": 0.8, "gewicht": 0.5, "bewertet": True,
                       "se_typ": 0.8 * sd}
    koef = {"satzlaenge_cv": 1.1, "absatzlaenge_cv": 0.9, "mattr_100": -0.6, "saetze_pro_absatz_cv": 0.8,
            "satzlaenge_mittel": -0.4}
    modell = {"intercept": 0.4, "koeffizienten": koef,
              "mittel": {k: m[k] * 0.9 for k in koef}, "sd": {k: metriken[k]["mensch"]["sd"] for k in koef}}
    return {"textsorten": {"hochschule": {"metriken": metriken, "modell": modell, "score_schwelle": 60,
                                          "ziel_p_mensch": 0.9}}}


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-max(-30, min(30, x))))


def clip(z: float) -> float:
    return max(-3.0, min(3.0, z))


REF = baselines_aus(text(random.Random(99), 800))


def intern(t: str) -> tuple[dict, list[list[dict]], list[dict]]:
    """Gesamtergebnis, Blockplan und Messung je Block (wie analysiere_und_bewerte intern: aus der Blockstruktur,
    ohne den Blocktext erneut zu zerlegen)."""
    erg, zw = analyse._analysiere(t, [], None, False)
    plan = analyse._bloecke_planen(analyse._block_einheiten(zw))
    neu = [analyse._analysiere("", [], None, b[-1]["teil"] and not b[-1]["letzter_teil"],
                               struktur=analyse._blockstruktur(b))[0] for b in plan]
    return erg, plan, neu


# ---------------------------------------------------------------------------
# S1–S3
# ---------------------------------------------------------------------------

class Konstanten(unittest.TestCase):
    def test_werte(self):
        self.assertEqual(analyse.Z_CLIP, 3.0)
        self.assertEqual(analyse.UNSICHER_FAKTOR, 0.5)
        self.assertEqual(analyse.BLOCK_AB, 1200)
        self.assertEqual(analyse.BLOCK_AB, 1.5 * analyse.ABSCHNITT_L)


class ZClipping(unittest.TestCase):
    def baselines(self):
        ref = {"mensch": {"p10": -2, "p25": -1, "p50": 0.5, "p75": 1, "p90": 2, "sd": 1.0}, "ki": {"p50": -1, "sd": 1.0},
               "auroc": 0.8, "gewicht": 0.5, "bewertet": True}
        return {"textsorten": {"hochschule": {"metriken": {"a": ref, "b": copy.deepcopy(ref)}, "modell": {
            "intercept": 0.2, "koeffizienten": {"a": 1.5, "b": -0.7}, "mittel": {"a": 0.0, "b": 0.0},
            "sd": {"a": 1.0, "b": 0.0}}}}}

    def bew(self, a, b):
        return analyse.bewerte({"metriken": {"a": a, "b": b}, "info": {"saetze": 40}}, self.baselines())

    def test_extreme_werte_auf_drei_begrenzt(self):
        self.assertEqual(self.bew(10.0, 0.0)["p_mensch"], self.bew(3.0, 0.0)["p_mensch"])
        self.assertEqual(self.bew(10.0, 0.0)["p_mensch"], round(sigmoid(0.2 + 1.5 * 3), 3))
        self.assertEqual(self.bew(-50.0, 0.0)["p_mensch"], round(sigmoid(0.2 - 1.5 * 3), 3))
        self.assertEqual(self.bew(2.0, 0.0)["p_mensch"], round(sigmoid(0.2 + 1.5 * 2), 3))  # innerhalb: linear
        # sd = 0 zählt als 1 (wie bisher), Clipping auch dort
        self.assertEqual(self.bew(0.0, 7.0)["p_mensch"], round(sigmoid(0.2 - 0.7 * 3), 3))

    def test_beitrag_mit_clipping(self):
        z = {r["id"]: r for r in self.bew(10.0, -0.25)["kennzahlen"]}
        self.assertAlmostEqual(z["a"]["beitrag"], 1.5 * (3 - 0.5), places=4)       # z(10) = 3, z(p50) = 0,5
        self.assertAlmostEqual(z["b"]["beitrag"], -0.7 * (-0.25 - 0.5), places=4)

    def test_z_standard(self):
        self.assertEqual(analyse.z_standard(9.0, 1.0, 2.0), 3.0)
        self.assertEqual(analyse.z_standard(-9.0, 1.0, 2.0), -3.0)
        self.assertEqual(analyse.z_standard(2.0, 1.0, 2.0), 0.5)
        self.assertEqual(analyse.z_standard(2.0, 1.0, 0.0), 1.0)


class Modellbeitraege(unittest.TestCase):
    def nachrechnen(self, bew: dict, metriken: dict, baselines: dict):
        """Unabhängig: Logit aus den Koeffizienten = Intercept-Term am menschlichen Median + Σ Beiträge. Merkmale mit
        Kappung (v4-Baselines) werden auf der der KI abgewandten Seite am Bandrand begrenzt, bevor sie standardisiert werden."""
        ts = baselines["textsorten"]["hochschule"]
        mod = ts["modell"]
        logit = mod["intercept"]
        am_median = mod["intercept"]
        mit_wert = []

        def gekappt(k, x):
            kappe = (mod.get("kappen") or {}).get(k)
            if not kappe:
                return x
            return min(x, kappe["wert"]) if kappe["seite"] == "oben" else max(x, kappe["wert"])

        for k, c in mod["koeffizienten"].items():
            if metriken.get(k) is None:
                continue
            sd = mod["sd"][k] or 1.0
            logit += c * clip((gekappt(k, metriken[k]) - mod["mittel"][k]) / sd)
            p50 = ts["metriken"][k]["mensch"]["p50"] if k in ts["metriken"] else mod["mittel"][k]
            am_median += c * clip((p50 - mod["mittel"][k]) / sd)
            mit_wert.append(k)
        summe = sum(b["beitrag"] for b in bew["modell_beitraege"])
        self.assertAlmostEqual(am_median + summe, logit, delta=1e-3)
        self.assertEqual(bew["p_mensch"], round(sigmoid(logit), 3))
        self.assertEqual(sorted(b["id"] for b in bew["modell_beitraege"]), sorted(mit_wert))
        werte = [b["beitrag"] for b in bew["modell_beitraege"]]
        self.assertEqual(werte, sorted(werte))  # am stärksten KI-ziehend zuerst
        zeilen = {z["id"]: z for z in bew["kennzahlen"]}
        for b in bew["modell_beitraege"]:
            self.assertEqual(b["name"], analyse.NAMEN.get(b["id"], b["id"]))
            if b["id"] in zeilen:
                self.assertEqual(zeilen[b["id"]]["beitrag"], b["beitrag"])
        for k, z in zeilen.items():
            if k not in mod["koeffizienten"]:
                self.assertIsNone(z["beitrag"])

    def test_synthetisch(self):
        for seed in (1, 2, 3):
            e = analyse.analysiere_text(text(random.Random(seed), 700, laengen=(3, 45)), [])
            self.nachrechnen(analyse.bewerte(e, REF), e["metriken"], REF)

    def test_plugin_baselines(self):
        b = analyse.lade_baselines()
        if not b or "modell" not in b.get("textsorten", {}).get("hochschule", {}):
            self.skipTest("Plugin-baselines.json ohne Modell")
        e = analyse.analysiere_text(text(random.Random(4), 800), analyse.lade_muster())
        bew = analyse.bewerte(e, b)
        self.nachrechnen(bew, e["metriken"], b)

    def test_fehlender_wert_ohne_beitrag(self):
        e = analyse.analysiere_text(text(random.Random(5), 600), [])
        e["metriken"]["mattr_100"] = None
        bew = analyse.bewerte(e, REF)
        self.assertNotIn("mattr_100", [b["id"] for b in bew["modell_beitraege"]])
        self.assertNotIn("mattr_100", [z["id"] for z in bew["kennzahlen"]])
        self.nachrechnen(bew, e["metriken"], REF)

    def test_kein_negatives_null(self):
        # Regression: negativer Koeffizient · (z(Wert) − z(p50)) = −0.0, wenn der Wert genau am Median liegt
        # (häufig bei Zählmaßen mit Median 0, z. B. Semikolons) – im JSON stand dann "beitrag": -0.0.
        b = copy.deepcopy(REF)
        mod = b["textsorten"]["hochschule"]["modell"]
        e = analyse.analysiere_text(text(random.Random(7), 700), [])
        e["metriken"]["mattr_100"] = b["textsorten"]["hochschule"]["metriken"]["mattr_100"]["mensch"]["p50"]
        self.assertLess(mod["koeffizienten"]["mattr_100"], 0)
        bew = analyse.bewerte(e, b)
        eintrag = next(x for x in bew["modell_beitraege"] if x["id"] == "mattr_100")
        self.assertEqual(math.copysign(1.0, eintrag["beitrag"]), 1.0)
        self.assertNotIn("-0.0", json.dumps(bew["modell_beitraege"]))

    def test_ohne_modell_leere_liste(self):
        b = copy.deepcopy(REF)
        del b["textsorten"]["hochschule"]["modell"]
        bew = analyse.bewerte(analyse.analysiere_text(text(random.Random(6), 500), []), b)
        self.assertEqual(bew["modell_beitraege"], [])
        self.assertTrue(all(z["beitrag"] is None for z in bew["kennzahlen"]))


class UnsicherRegel(unittest.TestCase):
    def bew(self, wert, woerter=None):
        ref = {"mensch": {"p10": 15, "p25": 18, "p50": 20, "p75": 23, "p90": 26, "sd": 4.0}, "ki": {"p50": 18.5, "sd": 1.0},
               "auroc": 0.8, "gewicht": 0.6, "bewertet": True, "se_typ": 1.0}
        b = {"textsorten": {"hochschule": {"metriken": {"satzlaenge_mittel": ref}}}}
        info = {"saetze": 40}
        if woerter is not None:
            info["woerter"] = woerter
        return analyse.bewerte({"metriken": {"satzlaenge_mittel": wert}, "info": info}, b)["kennzahlen"][0]

    def test_schwelle_halbe_se_bis_800_woerter(self):
        self.assertTrue(self.bew(17.6, 500)["unsicher"])    # 0,4 < 0,5 · 1,0
        self.assertFalse(self.bew(17.4, 500)["unsicher"])   # 0,6 ≥ 0,5
        self.assertTrue(self.bew(23.45, 800)["unsicher"])   # obere Grenze P75
        self.assertTrue(self.bew(17.6)["unsicher"])          # ohne Wortzahl wie ein Abschnitt
        self.assertEqual(self.bew(17.6, 500)["status"], "gelb")

    def test_schwelle_schrumpft_mit_der_laenge(self):
        # 3200 Wörter: 0,5 · 1,0 · √(800/3200) = 0,25
        self.assertFalse(self.bew(17.6, 3200)["unsicher"])
        self.assertTrue(self.bew(17.8, 3200)["unsicher"])
        self.assertEqual(self.bew(17.6, 3200)["status"], self.bew(17.6, 500)["status"])  # Status unberührt


# ---------------------------------------------------------------------------
# S4 Blockmodus
# ---------------------------------------------------------------------------

class Blockmodus(unittest.TestCase):
    def pruefe_bloecke(self, t: str, baselines=REF):
        """Gemeinsame Invarianten: Satz- und Wortsummen, lückenlose globale Satznummern, Block-Sätze = Gesamtsätze."""
        erg, bew = analyse.analysiere_und_bewerte(t, [], baselines)
        self.assertTrue(bew["blockmodus"])
        self.assertEqual(bew["n_woerter"], erg["info"]["woerter"])
        bl = bew["bloecke"]
        self.assertEqual([b["nr"] for b in bl], list(range(1, len(bl) + 1)))
        self.assertEqual(bl[0]["satz_von"], 1)
        self.assertEqual(bl[-1]["satz_bis"], erg["info"]["saetze"])
        for a, b in zip(bl, bl[1:]):
            self.assertEqual(a["satz_bis"] + 1, b["satz_von"])
        self.assertEqual(sum(b["woerter"] for b in bl), erg["info"]["woerter"])
        # unabhängig neu gemessen: Satzsumme und Satztexte je Block = globale Sätze satz_von..satz_bis
        e2, plan, neu = intern(t)
        self.assertEqual(len(plan), len(bl))
        self.assertEqual(sum(n["info"]["saetze"] for n in neu), erg["info"]["saetze"])
        for b, n in zip(bl, neu):
            self.assertEqual([s["text"] for s in erg["saetze"][b["satz_von"] - 1:b["satz_bis"]]],
                             [s["text"] for s in n["saetze"]])
            self.assertEqual(b["woerter"], n["info"]["woerter"])
            self.assertTrue(all(s["nr"] == i for i, s in enumerate(erg["saetze"], 1)))
        if len(bl) > 1:
            self.assertTrue(all(b["woerter"] >= 0.75 * analyse.ABSCHNITT_L for b in bl))
        return erg, bew, plan, neu

    def test_1199_und_1201_woerter(self):
        t1199 = text(random.Random(11), 1199)
        t1201 = text(random.Random(11), 1201)
        e1, b1 = analyse.analysiere_und_bewerte(t1199, [], REF)
        self.assertEqual(e1["info"]["woerter"], 1199)
        self.assertFalse(b1["blockmodus"])
        self.assertEqual(b1["bloecke"], [])
        self.assertEqual(b1["n_woerter"], 1199)
        e2, b2, plan, _ = self.pruefe_bloecke(t1201)
        self.assertEqual(e2["info"]["woerter"], 1201)
        self.assertGreaterEqual(len(plan), 1)

    def test_kurzer_text_identisch(self):
        for seed, n in ((12, 400), (13, 1000), (14, 1199)):
            t = text(random.Random(seed), n)
            erg, bew = analyse.analysiere_und_bewerte(t, [], REF)
            erwartet_erg = analyse.analysiere_text(t, [])
            erwartet = analyse.bewerte(erwartet_erg, REF)
            erwartet.update(blockmodus=False, n_woerter=erwartet_erg["info"]["woerter"], bloecke=[])
            self.assertEqual(erg, erwartet_erg)
            self.assertEqual(bew, erwartet)

    def test_nur_ueberschriften_und_kurze_absaetze(self):
        rnd = random.Random(15)
        teile = []
        for i in range(60):
            teile.append(f"## Abschnitt {i + 1} über die Daten")
            teile.append(" ".join(satz(rnd, n) for n in (12, 14, 14)))  # 40 Wörter
        erg, bew, plan, neu = self.pruefe_bloecke("\n\n".join(teile))
        self.assertEqual(erg["info"]["woerter"], 2400)
        self.assertEqual(erg["info"]["ueberschriften"], 60)
        self.assertEqual(len(plan), 3)
        for block in plan:  # jeder Block beginnt mit seiner Überschrift
            self.assertTrue(block[0]["vor"] and block[0]["vor"][0].startswith("# Abschnitt"))
        self.assertEqual(sum(n["info"]["ueberschriften"] for n in neu), 60)

    def test_riesenabsatz_ohne_leerzeilen(self):
        rnd = random.Random(16)
        riese = " ".join(satz(rnd, n) for n in satzlaengen(rnd, 3000))
        erg, bew, plan, neu = self.pruefe_bloecke(riese)
        self.assertEqual(erg["info"]["absaetze"], 1)
        self.assertIn(len(plan), (3, 4))
        self.assertTrue(all(u["teil"] for block in plan for u in block))
        # alle Blöcke bis auf den letzten enden mitten im Absatz: letzter_absatz_gekuerzt
        self.assertEqual([b[-1]["teil"] and not b[-1]["letzter_teil"] for b in plan],
                         [True] * (len(plan) - 1) + [False])
        self.assertTrue(all(n["metriken"]["absaetze"] == 0 for n in neu[:-1]))
        # Absatz-Kennzahlen nur im letzten Block vorhanden (< Hälfte): nicht bewertet
        ids = {z["id"] for z in bew["kennzahlen"]}
        self.assertFalse(ids & set(analyse.ABSATZ_KENNZAHLEN))
        self.assertIn("satzlaenge_cv", ids)

    def test_riesenabsatz_mit_zeilenumbruechen(self):
        rnd = random.Random(17)
        woerter = " ".join(satz(rnd, n) for n in satzlaengen(rnd, 3000)).split()
        zeilen = [" ".join(woerter[i:i + 11]) for i in range(0, len(woerter), 11)]
        self.pruefe_bloecke("\n".join(zeilen))

    def test_riesenabsatz_mit_aufzaehlungsziffern(self):
        # Regression: Ein Block, der mitten im Riesenabsatz mit '2. …' oder 'a) …' beginnt, wurde beim erneuten
        # Zerlegen des Blocktexts als ein einziger Listenpunkt gelesen (0 Wörter, Bewertung leerer Metriken).
        rnd = random.Random(3)
        s = [satz(rnd, n) for n in satzlaengen(rnd, 3000, (10, 20))]
        riese = " ".join(x if i == 0 else ("a) " if i % 2 else "2. ") + x for i, x in enumerate(s))
        erg, bew, plan, neu = self.pruefe_bloecke(riese)  # Satztexte und Wortsummen je Block = Gesamttext
        self.assertGreaterEqual(len(plan), 3)
        self.assertTrue(all(b["woerter"] >= 0.75 * analyse.ABSCHNITT_L for b in bew["bloecke"]))

    def test_zusammengefuegte_zeilen_mit_senkrechtstrich(self):
        # Regression: Absatz aus zwei Zeilen mit je einem '|' wurde im Blocktext (eine Zeile) zur Tabellenzeile.
        rnd = random.Random(4)
        mitte = ("Die bedingte Wahrscheinlichkeit P(A | B) ist hier gering und\nwird mit P(B | A) verglichen, "
                 "wie die Daten zeigen.")
        t = "\n\n".join([text(rnd, 700), mitte, text(rnd, 900)])
        erg, bew = analyse.analysiere_und_bewerte(t, [], REF)
        self.assertTrue(bew["blockmodus"])
        self.assertEqual(sum(b["woerter"] for b in bew["bloecke"]), erg["info"]["woerter"])
        self.assertEqual(bew["bloecke"][-1]["satz_bis"], erg["info"]["saetze"])

    def test_teilstuecke_nicht_doppelt_bereinigt(self):
        # Regression: Teilstücke eines Riesenabsatzes bestehen aus schon bereinigten Sätzen; ein zweites
        # bereinige_absatz entfernte weitere Klammern ('(1989; 2003; Happé, Frith)' blieb beim ersten Mal stehen).
        roh = "Die Theorie von Uta Frith (1989; 2003; Happé, Frith (2006)) wird hier geprüft."  # verschachtelt
        sauber = analyse.bereinige_absatz(roh, Counter())
        if analyse.bereinige_absatz(sauber, Counter()) == sauber:
            self.skipTest("bereinige_absatz ist für dieses Beispiel inzwischen idempotent")
        rnd = random.Random(26)
        saetze = [satz(rnd, n) for n in satzlaengen(rnd, 3000, (10, 20))]
        for i in range(0, len(saetze), 7):
            saetze[i] = roh
        riese = " ".join(saetze)
        erg, bew, plan, neu = self.pruefe_bloecke(riese)  # Satztexte und Wortsummen je Block = Gesamttext
        self.assertIn("(1989; 2003; Happé, Frith)", " ".join(x["text"] for x in erg["saetze"]))  # am Stück so belassen

    def test_listen_und_tabellen_zwischen_absaetzen(self):
        rnd = random.Random(18)
        teile = []
        for i, a in enumerate(absaetze(rnd, 2600)):
            teile.append(a)
            if i % 3 == 0:
                teile.append("- Erster Punkt der Aufzählung\n- Zweiter Punkt mit mehr Wörtern\n- Dritter Punkt")
            if i % 4 == 1:
                teile.append("| Merkmal | Wert |\n|---|---|\n| Alter | 34 |\n| Dauer | 12 |")
            if i % 5 == 2:
                teile.append("> Ein Blockzitat aus der Literatur, das nicht mitgezählt wird.")
        erg, bew, plan, neu = self.pruefe_bloecke("\n\n".join(teile))
        self.assertEqual(erg["info"]["woerter"], 2600)
        self.assertEqual(sum(n["info"]["listenpunkte"] for n in neu), erg["info"]["listenpunkte"])
        self.assertGreater(erg["info"]["tabellenzeilen"], 0)
        self.assertTrue(all(n["info"]["tabellenzeilen"] == 0 for n in neu))

    def test_literaturverzeichnis_am_ende(self):
        rnd = random.Random(19)
        rumpf = text(rnd, 2500)
        lit = "\n\n".join(f"Müller, A{i}. (20{i % 20:02d}): Ein sehr langer Titel über Forschung und Praxis. Berlin: Verlag."
                          for i in range(60))
        t = rumpf + "\n\n## Literaturverzeichnis\n\n" + lit
        erg, bew, plan, neu = self.pruefe_bloecke(t)
        self.assertTrue(erg["info"]["literatur_abgeschnitten"])
        self.assertEqual(erg["info"]["woerter"], 2500)
        self.assertFalse(any("Verlag" in analyse._blocktext(b) or "Literaturverzeichnis" in analyse._blocktext(b)
                             for b in plan))

    def test_median_score_und_p_mensch(self):
        t = text(random.Random(20), 4000, laengen=(3, 40))
        erg, bew = analyse.analysiere_und_bewerte(t, [], REF)
        _, plan, neu = intern(t)
        ps = [b["p_mensch"] for b in bew["bloecke"]]
        self.assertEqual(bew["p_mensch"], round(statistics.median(ps), 3))
        median = {}
        for k in neu[0]["metriken"]:
            werte = [n["metriken"][k] for n in neu if n["metriken"].get(k) is not None]
            median[k] = round(statistics.median(werte), 4) if 2 * len(werte) >= len(neu) else None
        for z in bew["kennzahlen"]:
            self.assertAlmostEqual(z["wert"], median[z["id"]], places=4)
        erwartet = analyse.bewerte({"metriken": median, "info": {"woerter": erg["info"]["woerter"],
                                    "saetze": statistics.median(n["info"]["saetze"] for n in neu)}}, REF)
        self.assertEqual(bew["score"], erwartet["score"])
        self.assertEqual(bew["modell_beitraege"], erwartet["modell_beitraege"])
        for b, n in zip(bew["bloecke"], neu):
            eb = analyse.bewerte(n, REF)
            self.assertEqual((b["score"], b["p_mensch"]), (eb["score"], eb["p_mensch"]))
            self.assertEqual(b["rot"], sum(1 for z in eb["kennzahlen"] if z["bewertet"] and z["status"] == "rot"))
        # unsicher mit der Gesamtwortzahl (S3)
        self.assertEqual([z["unsicher"] for z in bew["kennzahlen"]], [z["unsicher"] for z in erwartet["kennzahlen"]])

    def test_hinweis_statt_warnung(self):
        t = text(random.Random(21), 2000)
        roh = analyse.analysiere_text(t, [])
        self.assertIn(analyse.hinweis_langer_text(roh["info"]["woerter"]), roh["info"]["warnungen"])
        erg, bew = analyse.analysiere_und_bewerte(t, [], REF)
        w = erg["info"]["warnungen"]
        self.assertNotIn(analyse.hinweis_langer_text(erg["info"]["woerter"]), w)
        self.assertEqual(sum(x.startswith(analyse.BLOCK_HINWEIS) for x in w), 1)

    def test_ohne_baselines_kein_blockmodus(self):
        t = text(random.Random(22), 2000)
        erg, bew = analyse.analysiere_und_bewerte(t, [], {})
        self.assertFalse(bew["verfuegbar"])
        self.assertFalse(bew["blockmodus"])
        self.assertEqual(bew["bloecke"], [])
        self.assertIn(analyse.hinweis_langer_text(erg["info"]["woerter"]), erg["info"]["warnungen"])

    def test_textabgleich_bei_abweichender_satzzahl(self):
        def einheit(nrn):
            return {"saetze": nrn}
        saetze = [{"text": t} for t in ("Aa bb.", "Cc dd.", "Ee ff.", "Gg hh.", "Ii jj.")]
        plan = [[einheit([0, 1])], [einheit([2, 3, 4])]]
        # Block 1 neu gemessen als ein Satz (verschmolzen), Block 2 korrekt
        neu = [{"info": {"saetze": 1}, "saetze": [{"text": "Aa bb. Cc dd."}]},
               {"info": {"saetze": 3}, "saetze": [{"text": "Ee ff."}, {"text": "Gg hh."}, {"text": "Ii jj."}]}]
        self.assertEqual(analyse._satzbereiche(plan, neu, saetze), [(1, 2), (3, 5)])
        # Block 2 neu gemessen mit einem zusätzlich geteilten Satz am Ende
        neu[1] = {"info": {"saetze": 4}, "saetze": [{"text": "Ee ff."}, {"text": "Gg hh."}, {"text": "Ii"}, {"text": "jj."}]}
        self.assertEqual(analyse._satzbereiche(plan, neu, saetze), [(1, 2), (3, 5)])
        # übereinstimmend: fortlaufend
        neu = [{"info": {"saetze": 2}, "saetze": saetze[:2]}, {"info": {"saetze": 3}, "saetze": saetze[2:]}]
        self.assertEqual(analyse._satzbereiche(plan, neu, saetze), [(1, 2), (3, 5)])

    def test_bericht_und_main(self):
        t = text(random.Random(23), 3300, laengen=(3, 40))
        erg, bew = analyse.analysiere_und_bewerte(t, [], REF)
        md = analyse.bericht_markdown(erg, bew)
        self.assertIn("**Blöcke**", md)
        zeilen = [z for z in md.splitlines() if z.startswith("| ") and z.split("|")[1].strip().isdigit()]
        self.assertEqual(len(zeilen), len(bew["bloecke"]))
        markiert = [z for z in zeilen if "am KI-nächsten" in z]
        self.assertEqual(len(markiert), 1)
        tiefster = min(bew["bloecke"], key=lambda b: (b["p_mensch"], b["score"]))
        self.assertEqual(int(markiert[0].split("|")[1]), tiefster["nr"])
        self.assertIn(f"| {tiefster['satz_von']}–{tiefster['satz_bis']} |", markiert[0])
        self.assertIn("ℹ️ " + analyse.BLOCK_HINWEIS, md)
        with tempfile.TemporaryDirectory() as d:
            tp, bp = os.path.join(d, "t.md"), os.path.join(d, "b.json")
            with open(tp, "w", encoding="utf-8") as f:
                f.write(t)
            with open(bp, "w", encoding="utf-8") as f:
                json.dump(REF, f)
            mp = os.path.join(d, "m.json")  # main() soll wie oben ohne KI-Muster messen (sonst hängt der Test an ki_muster.json)
            with open(mp, "w", encoding="utf-8") as f:
                json.dump({"muster": []}, f)
            puffer = io.StringIO()
            with contextlib.redirect_stdout(puffer):
                analyse.main([tp, "--baselines", bp, "--muster", mp, "--format", "json", "--ohne-saetze"])
            aus = json.loads(puffer.getvalue())
            self.assertTrue(aus["bewertung"]["blockmodus"])
            self.assertEqual(aus["bewertung"]["bloecke"], bew["bloecke"])
            self.assertEqual(aus["bewertung"]["n_woerter"], erg["info"]["woerter"])
            self.assertIn("modell_beitraege", aus["bewertung"])
            puffer = io.StringIO()
            with contextlib.redirect_stdout(puffer):
                analyse.main([tp, "--baselines", bp])
            self.assertIn("am KI-nächsten", puffer.getvalue())
            # Kurzer Text: kein Blockabschnitt im Bericht
            with open(tp, "w", encoding="utf-8") as f:
                f.write(text(random.Random(24), 600))
            puffer = io.StringIO()
            with contextlib.redirect_stdout(puffer):
                analyse.main([tp, "--baselines", bp])
            self.assertNotIn("**Blöcke**", puffer.getvalue())

    def test_laufzeit_10000_woerter(self):
        t = text(random.Random(25), 10000)
        muster, baselines = analyse.lade_muster(), analyse.lade_baselines()
        start = time.perf_counter()
        erg, bew = analyse.analysiere_und_bewerte(t, muster, baselines)
        dauer = time.perf_counter() - start
        self.assertEqual(erg["info"]["woerter"], 10000)
        if baselines:
            self.assertTrue(bew["blockmodus"])
            self.assertGreaterEqual(len(bew["bloecke"]), 11)
        self.assertLess(dauer, 2.0)


if __name__ == "__main__":
    unittest.main()
