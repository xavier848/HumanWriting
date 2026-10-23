"""v7 Messseite: Seite der Abweichung, einseitiger Score, einseitige Kappung des Modells (Kalibrierung und Laufzeit),
verklebte Wörter, Anteil wörtlicher Zitate, Transkriptnotation, Belege in eckigen Klammern, Autorenlisten.

python3 -m unittest discover -s tests
"""
import contextlib
import copy
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kalibriere  # noqa: E402
import analyse  # noqa: E402  (Pfad setzt kalibriere)
from test_kalibriere import FW_KI, FW_MENSCH, text_erzeugen  # noqa: E402

MUSTER_PFAD = os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "data", "ki_muster.json")


def ref(p10, p25, p50, p75, p90, ki50, gewicht=1.0, bewertet=True, richtung=None):
    r = {"mensch": {"p10": p10, "p25": p25, "p50": p50, "p75": p75, "p90": p90, "sd": 1.0},
         "ki": {"p50": ki50, "sd": 1.0}, "auroc": 0.8, "gewicht": gewicht, "bewertet": bewertet}
    if richtung:
        r["richtung"] = richtung
    return r


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, x))))


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

class SeiteUndKappe(unittest.TestCase):
    def test_ki_richtung(self):
        self.assertEqual(analyse.ki_richtung(ref(0, 1, 2, 3, 4, ki50=5)), 1)
        self.assertEqual(analyse.ki_richtung(ref(0, 1, 2, 3, 4, ki50=1)), -1)
        # gleiche Mediane (ich/wir: beide 0): AUROC-Richtung der Kalibrierung, ohne sie unbekannt
        self.assertEqual(analyse.ki_richtung(ref(0, 0, 0, 2, 9, ki50=0, richtung="mensch_hoeher")), -1)
        self.assertEqual(analyse.ki_richtung(ref(0, 0, 0, 2, 9, ki50=0, richtung="ki_hoeher")), 1)
        self.assertIsNone(analyse.ki_richtung(ref(0, 0, 0, 2, 9, ki50=0)))
        self.assertIsNone(analyse.ki_richtung({"mensch": {"p50": 1.0}}))

    def test_seite_von(self):
        r = ref(0, 1, 2, 3, 4, ki50=5)  # KI höher
        self.assertEqual(analyse.seite_von(3.5, r), "ki")
        self.assertEqual(analyse.seite_von(0.5, r), "gegen")
        self.assertIsNone(analyse.seite_von(2.0, r))
        self.assertEqual(analyse.seite_von(9.0, ref(0, 0, 0, 2, 9, ki50=0, richtung="mensch_hoeher")), "gegen")
        self.assertIsNone(analyse.seite_von(9.0, ref(0, 0, 0, 2, 9, ki50=0)))

    def test_kappe_von_und_gekappt(self):
        oben = analyse.kappe_von(ref(0, 1, 2, 3, 4, ki50=1))   # KI niedriger → Gegenseite oben, Grenze P90
        unten = analyse.kappe_von(ref(0, 1, 2, 3, 4, ki50=5))  # KI höher → Gegenseite unten, Grenze P10
        self.assertEqual(oben, {"seite": "oben", "wert": 4})
        self.assertEqual(unten, {"seite": "unten", "wert": 0})
        self.assertIsNone(analyse.kappe_von(ref(0, 0, 0, 2, 9, ki50=0)))
        self.assertEqual(analyse.gekappt(7.0, oben), 4)
        self.assertEqual(analyse.gekappt(-7.0, oben), -7.0)   # KI-Seite offen
        self.assertEqual(analyse.gekappt(-7.0, unten), 0)
        self.assertEqual(analyse.gekappt(7.0, unten), 7.0)
        self.assertEqual(analyse.gekappt(3.0, None), 3.0)
        self.assertIsNone(analyse.gekappt(None, oben))

    def test_z_wert_mit_kappe_wie_laufzeit(self):
        rnd = random.Random(8)
        for _ in range(300):
            x, mu, sd = rnd.uniform(-20, 20), rnd.uniform(-3, 3), rnd.uniform(0.1, 4)
            kp = rnd.choice([None, {"seite": "oben", "wert": rnd.uniform(-5, 5)}, {"seite": "unten", "wert": rnd.uniform(-5, 5)}])
            self.assertEqual(kalibriere.z_wert(x, mu, sd, kp), analyse.z_standard(analyse.gekappt(x, kp), mu, sd))
        self.assertEqual(kalibriere.z_wert(None, 0.0, 1.0, {"seite": "oben", "wert": 1.0}), 0.0)


# ---------------------------------------------------------------------------
# bewerte(): seite, jenseits_band, score_ki, Kappung im Modell
# ---------------------------------------------------------------------------

def baselines_klein(mit_kappen=True):
    metriken = {
        "a": ref(0, 1, 2, 3, 4, ki50=5, gewicht=0.5),        # KI höher
        "b": ref(10, 20, 30, 40, 50, ki50=15, gewicht=0.3),  # KI niedriger
        "c": ref(0, 0, 0, 2, 9, ki50=0, gewicht=0.2, richtung="mensch_hoeher"),  # Mediane gleich
        "d": ref(0, 1, 2, 3, 4, ki50=2, gewicht=0.4),        # KI-Richtung unbekannt
        "e": ref(0, 1, 2, 3, 4, ki50=5, gewicht=0.0, bewertet=False),
    }
    modell = {"koeffizienten": {"a": -1.0, "b": 0.8}, "intercept": 0.3, "mittel": {"a": 2.5, "b": 28.0},
              "sd": {"a": 1.5, "b": 12.0}, "lambda": 0.01, "z_clip": 3.0}
    if mit_kappen:
        modell["kappen"] = {"a": analyse.kappe_von(metriken["a"]), "b": analyse.kappe_von(metriken["b"])}
    return {"textsorten": {"hochschule": {"metriken": metriken, "modell": modell, "ziel_p_mensch": 0.86,
                                          "ziel_score": 56.4, "ziel_score_ki": 70.0, "score_schwelle": 63.4}}}


def ergebnis(**werte):
    return {"metriken": dict(werte), "info": {"saetze": 40, "woerter": 800}}


class BewerteV7(unittest.TestCase):
    def test_seite_und_jenseits_band(self):
        b = analyse.bewerte(ergebnis(a=-1.0, b=60.0, c=9.5, d=3.5, e=9.0), baselines_klein())
        z = {x["id"]: x for x in b["kennzahlen"]}
        self.assertEqual((z["a"]["status"], z["a"]["seite"], z["a"]["jenseits_band"]), ("rot", "gegen", True))
        self.assertEqual((z["b"]["status"], z["b"]["seite"], z["b"]["jenseits_band"]), ("rot", "gegen", True))
        self.assertEqual((z["c"]["status"], z["c"]["seite"], z["c"]["jenseits_band"]), ("rot", "gegen", True))
        self.assertEqual((z["d"]["status"], z["d"]["seite"], z["d"]["jenseits_band"]), ("gelb", None, False))
        b2 = analyse.bewerte(ergebnis(a=3.5, b=25.0, c=1.0, d=2.0), baselines_klein())
        z2 = {x["id"]: x for x in b2["kennzahlen"]}
        self.assertEqual((z2["a"]["status"], z2["a"]["seite"], z2["a"]["jenseits_band"]), ("gelb", "ki", False))
        self.assertEqual((z2["b"]["status"], z2["b"]["seite"]), ("gruen", None))  # grün: keine Seite
        self.assertEqual((z2["c"]["status"], z2["c"]["seite"]), ("gruen", None))
        b3 = analyse.bewerte(ergebnis(a=0.5, b=12.0), baselines_klein())
        z3 = {x["id"]: x for x in b3["kennzahlen"]}
        self.assertEqual((z3["a"]["status"], z3["a"]["seite"], z3["a"]["jenseits_band"]), ("gelb", "gegen", False))
        self.assertEqual((z3["b"]["status"], z3["b"]["seite"], z3["b"]["jenseits_band"]), ("gelb", "ki", False))

    def test_score_ki_einseitig(self):
        bl = baselines_klein()
        e = ergebnis(a=-1.0, b=12.0, c=9.5, d=3.5, e=9.0)
        b = analyse.bewerte(copy.deepcopy(e), bl)
        # Gewichte a 0,5 b 0,3 c 0,2 d 0,4 (e unbewertet); zweiseitig: rot 0, gelb 0,5, rot 0, gelb 0,5
        self.assertEqual(b["score"], round(100 * (0.3 * 0.5 + 0.4 * 0.5) / 1.4))
        # einseitig: a und c Gegenseite → wie grün; b KI-Seite gelb; d ohne Richtung zweiseitig
        self.assertEqual(b["score_ki"], round(100 * (0.5 + 0.3 * 0.5 + 0.2 + 0.4 * 0.5) / 1.4))
        self.assertEqual(b["ziel_score_ki"], 70.0)
        self.assertEqual(b["ziel_score"], 56.4)
        met = bl["textsorten"]["hochschule"]["metriken"]
        z = dict(e["metriken"], saetze=40)
        self.assertEqual(b["score"], round(kalibriere.score(met, z)))
        self.assertEqual(b["score_ki"], round(kalibriere.score_ki(met, z)))
        self.assertGreaterEqual(kalibriere.score_ki(met, z), kalibriere.score(met, z))

    def test_score_ki_gleich_score_ohne_gegenseite(self):
        b = analyse.bewerte(ergebnis(a=9.0, b=0.0, c=0.0, d=2.0), baselines_klein())
        self.assertEqual(b["score"], b["score_ki"])
        self.assertIsNone(analyse.bewerte(ergebnis(a=1.0), {})["score_ki"])

    def test_kappung_im_modell(self):
        bl = baselines_klein()
        mod = bl["textsorten"]["hochschule"]["modell"]

        def p(a, b):
            return analyse.bewerte(ergebnis(a=a, b=b), bl)["p_mensch"]
        # a: KI höher → unter P10 = 0 gekappt; b: KI niedriger → über P90 = 50 gekappt
        self.assertEqual(p(-5.0, 30.0), p(0.0, 30.0))
        self.assertEqual(p(2.0, 90.0), p(2.0, 50.0))
        self.assertLess(p(7.0, 30.0), p(4.0, 30.0))          # KI-Seite offen (bis z-Clipping)
        self.assertLess(p(2.0, 0.0), p(2.0, 15.0))
        erwartet = sigmoid(0.3 - 1.0 * (0.0 - 2.5) / 1.5 + 0.8 * (50.0 - 28.0) / 12.0)
        self.assertAlmostEqual(p(-5.0, 90.0), round(erwartet, 3))
        # ohne Kappung (baselines vor v7): Übertreibung zählt weiter
        alt = baselines_klein(mit_kappen=False)
        self.assertGreater(analyse.bewerte(ergebnis(a=2.0, b=90.0), alt)["p_mensch"],
                           analyse.bewerte(ergebnis(a=2.0, b=50.0), alt)["p_mensch"])
        # Beitrag aus dem gekappten Wert; Summe + Intercept-Term am Median = Logit
        b = analyse.bewerte(ergebnis(a=-5.0, b=90.0), bl)
        bt = {x["id"]: x["beitrag"] for x in b["modell_beitraege"]}
        self.assertAlmostEqual(bt["b"], 0.8 * (50.0 - 30.0) / 12.0, places=4)
        self.assertAlmostEqual(bt["a"], -1.0 * (0.0 - 2.0) / 1.5, places=4)
        am_median = mod["intercept"] - 1.0 * (2.0 - 2.5) / 1.5 + 0.8 * (30.0 - 28.0) / 12.0
        self.assertAlmostEqual(sigmoid(am_median + sum(bt.values())), b["p_mensch"], delta=0.0006)

    def test_bericht_nennt_einseitigen_score_und_gegenseite(self):
        bl = baselines_klein()
        e = {"metriken": {"a": -1.0, "b": 60.0, "c": 1.0, "d": 2.0}, "info": {
            "woerter": 800, "saetze": 40, "absaetze": 6, "zitate_entfernt": 0, "literatur_abgeschnitten": False,
            "warnungen": [], "satzlaengen_verteilung": analyse.verteilung([20] * 40), "satzlaengen": [20] * 40,
            "kernbegriffe": []}, "saetze": [], "muster_treffer": []}
        md = analyse.bericht_markdown(e, analyse.bewerte(copy.deepcopy(e), bl))
        self.assertIn("nur KI-Seite:", md)
        self.assertIn("Gegenseite, kein KI-Signal", md)


# ---------------------------------------------------------------------------
# kalibriere.py: Kappung in Paket, Fit und Goodhart
# ---------------------------------------------------------------------------

class KalibriereKappung(unittest.TestCase):
    def test_fit_auf_gekappten_werten(self):
        rnd = random.Random(4)
        daten = [{"gruppe": "mensch" if i % 2 else "ki", "a": rnd.gauss(1 if i % 2 else -1, 1)} for i in range(160)]
        for z in daten[:12]:
            if z["gruppe"] == "mensch":
                z["a"] = 6.0  # Übertreibung auf der Gegenseite
        kp = {"seite": "oben", "wert": 1.8}
        paket = {"rang": ["a"], "mittel": {"a": 0.2}, "sd": {"a": 1.1}, "kappen": {"a": kp}, "daten": daten}
        mod = kalibriere.fit_modell(paket, 1, 0.01)
        spalte = [max(-3.0, min(3.0, (min(z["a"], 1.8) - 0.2) / 1.1)) for z in daten]
        w, b = kalibriere.logreg_spalten([spalte], [1 if z["gruppe"] == "mensch" else 0 for z in daten], 0.01)
        self.assertAlmostEqual(mod["w"][0], w[0], places=6)
        self.assertAlmostEqual(mod["b"], b, places=6)
        hoch = kalibriere.p_mensch(mod, paket, {"a": 50.0})
        self.assertAlmostEqual(hoch, kalibriere.p_mensch(mod, paket, {"a": 1.8}))
        self.assertLess(kalibriere.p_mensch(mod, paket, {"a": -50.0}), kalibriere.p_mensch(mod, paket, {"a": -2.0}))

    def test_goodhart_median_im_band_unberuehrt(self):
        daten = [{"gruppe": "ki", "a": -2.0 + 0.1 * i} for i in range(5)] + [{"gruppe": "mensch", "a": 2.0}]
        paket = {"daten": daten, "metriken": {"a": {"mensch": {"p50": 1.0}}}, "mittel": {"a": 0.0}, "sd": {"a": 1.0},
                 "kappen": {"a": {"seite": "oben", "wert": 1.5}}}
        modell = {"merkmale": ["a"], "w": [2.0], "b": 0.0}
        gh = kalibriere.goodhart_analyse(modell, paket, ziel_p=0.5)
        self.assertAlmostEqual(gh["merkmale"][0]["median_beitrag_ki"], 2.0 * (-1.8 - 1.0))


class EndeZuEndeKappung(unittest.TestCase):
    """Synthetischer Korpus, kalibriert mit und ohne Kappung (eigene Ausgabepfade, Plugin-Daten bleiben unberührt)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        rnd = random.Random(77)
        korpus = os.path.join(cls.tmp, "korpus")
        os.makedirs(os.path.join(korpus, "mensch", "q1"))
        os.makedirs(os.path.join(korpus, "ki", "claude"))
        meta_m, meta_k = [], []
        cls.texte = {}
        for i in range(12):
            mid, kid = f"m{i:02d}", f"k{i:02d}"
            cls.texte[mid] = text_erzeugen(rnd, 2600, (4, 38), FW_MENSCH)
            cls.texte[kid] = text_erzeugen(rnd, 1000, (15, 19), FW_KI) + "\n\nInsgesamt zeigt sich, dass es maßgeblich wirkt."
            for ordner, tid in (("mensch/q1", mid), ("ki/claude", kid)):
                with open(os.path.join(korpus, ordner, tid + ".txt"), "w", encoding="utf-8") as f:
                    f.write(cls.texte[tid])
            meta_m.append({"id": mid, "quelle": "q1", "typ": "Bachelorarbeit", "jahr": 2010 + i})
            meta_k.append({"id": kid, "basis_id": mid, "quelle": "claude", "typ": "Bachelorarbeit"})
        for ordner, zeilen in (("mensch/q1", meta_m), ("ki/claude", meta_k)):
            with open(os.path.join(korpus, ordner, "meta.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(z) for z in zeilen) + "\n")
        cls.ergebnisse = {}
        for name, extra in (("mit", []), ("ohne", ["--ohne-kappung"])):
            daten = os.path.join(cls.tmp, name)
            os.makedirs(daten)
            shutil.copy(MUSTER_PFAD, os.path.join(daten, "ki_muster.json"))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = kalibriere.main(["--korpus", korpus, "--aus", daten, "--baselines", os.path.join(daten, "baselines.json"),
                                      "--muster", os.path.join(daten, "ki_muster.json"), "--cv-wiederholungen", "1",
                                      "--cv-folds", "2", "--bootstrap", "40"] + extra)
            with open(os.path.join(daten, "baselines.json"), encoding="utf-8") as f:
                cls.ergebnisse[name] = (rc, json.load(f), daten)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_baselines_v7_felder(self):
        rc, b, _ = self.ergebnisse["mit"]
        self.assertEqual(rc, 0)
        self.assertEqual(b["version"], "4")
        ts = b["textsorten"]["hochschule"]
        mod = ts["modell"]
        self.assertEqual(set(mod["kappen"]), set(mod["koeffizienten"]))
        for k, kp in mod["kappen"].items():
            self.assertEqual(kp, analyse.kappe_von(ts["metriken"][k]), k)  # Seite und Grenze aus den finalen Perzentilen
        self.assertIn("ziel_score_ki", ts)
        ev = b["evaluation"]
        self.assertEqual(ev["ziel_score_ki"], ts["ziel_score_ki"])
        self.assertTrue(ev["hyperparameter"]["kappung"])
        for k in ("ziel_erreicht_anteil_oof", "ziel_erreicht_anteil_oof_zweiseitig"):
            self.assertEqual(set(ev[k]), {"mensch", "ki"})
        self.assertIn("score_ki_cv", ev)
        self.assertGreaterEqual(ts["ziel_score_ki"], ts["ziel_score"])  # einseitig nie strenger

    def test_ohne_kappung(self):
        rc, b, daten = self.ergebnisse["ohne"]
        self.assertEqual(rc, 0)
        self.assertEqual(b["textsorten"]["hochschule"]["modell"]["kappen"], {})
        self.assertFalse(b["evaluation"]["hyperparameter"]["kappung"])
        with open(os.path.join(daten, "bericht.md"), encoding="utf-8") as f:
            self.assertIn("Ohne einseitige Kappung", f.read())

    def test_bericht_und_features(self):
        _, b, daten = self.ergebnisse["mit"]
        with open(os.path.join(daten, "bericht.md"), encoding="utf-8") as f:
            bericht = f.read()
        for teil in ("Einseitige Kappung (v7)", "ziel_score_ki = ", "score_ki ≥ ziel_score_ki", "Regel bis v6", "gekappt "):
            self.assertIn(teil, bericht)
        with open(os.path.join(daten, "features.csv"), encoding="utf-8") as f:
            kopf = f.readline().strip().split(",")
        self.assertTrue({"final_p_mensch", "final_score", "final_score_ki"} <= set(kopf))

    def test_laufzeit_wie_kalibrierung(self):
        """p_mensch, score und score_ki aus kalibriere (Modell aus baselines.json) = analyse.bewerte."""
        _, b, daten = self.ergebnisse["mit"]
        ts = b["textsorten"]["hochschule"]
        mod = ts["modell"]
        muster = analyse.lade_muster(os.path.join(daten, "ki_muster.json"))
        roh = analyse.lade_muster(os.path.join(daten, "ki_muster.json"))
        for mu in roh:
            mu["gewicht"] = 1.0
        gew = {mu["id"]: mu["gewicht"] for mu in muster}
        merkmale = list(mod["koeffizienten"])
        modell = {"merkmale": merkmale, "w": [mod["koeffizienten"][k] for k in merkmale], "b": mod["intercept"]}
        paket = {"mittel": mod["mittel"], "sd": mod["sd"], "kappen": mod["kappen"]}
        n = gekappt_n = 0
        for doc_id, t in sorted(self.texte.items()):
            for ab in kalibriere.zerlege(t, max_abschnitte=3 if doc_id.startswith("m") else 1) or [t]:
                kurz = kalibriere.kuerze(ab)
                if kurz is None:
                    continue
                e = kalibriere.analysiere_abschnitt(kurz, roh)
                if e["info"]["saetze"] < 12:
                    continue
                n_fw, k_fw = kalibriere.fw_zaehlung(e, kurz, ts["fw_profil"]["woerter"])
                zeile = kalibriere.abgeleitet({"saetze": e["info"]["saetze"], **e["metriken"], "_fw": k_fw, "_n": n_fw,
                                               "_token": e["info"]["token"], "_treffer": Counter(),
                                               "_kand": kalibriere.muster_kandidaten(e["saetze"], roh)}, gew, ts["fw_profil"])
                erg = analyse.analysiere_text(kurz, muster, fw_profil=ts["fw_profil"], letzter_absatz_gekuerzt=True)
                bew = analyse.bewerte(erg, b)
                self.assertEqual(bew["p_mensch"], round(kalibriere.p_mensch(modell, paket, zeile), 3))
                self.assertEqual(bew["score"], round(kalibriere.score(ts["metriken"], zeile)))
                self.assertEqual(bew["score_ki"], round(kalibriere.score_ki(ts["metriken"], zeile)))
                n += 1
                gekappt_n += any(analyse.gekappt(zeile.get(k), kp) != zeile.get(k) for k, kp in mod["kappen"].items())
        self.assertGreaterEqual(n, 20)
        self.assertGreater(gekappt_n, 0)  # die Kappung greift tatsächlich in einigen Abschnitten


# ---------------------------------------------------------------------------
# analysiere_text(): verklebte Wörter, Zitatanteil, Transkriptnotation, Belege, Autorenlisten
# ---------------------------------------------------------------------------

FUELL = ("Die Untersuchung beschreibt den Ablauf der Befragung genauer. Danach folgen die Ergebnisse der Auswertung. "
         "Sie zeigen ein gemischtes Bild für die einzelnen Gruppen. ")


class Verklebt(unittest.TestCase):
    def test_positiv(self):
        for t in ("erfasst.Merkmale", "Note,wie", "Strukturgleichungsmodell,wiesichdieHZB-Note", "Fazit:Die", "Warum?Weil",
                  "dieInformiertheitvorStudienbeginnUnd", "Müller,Meier"):
            self.assertTrue(analyse._verklebt(t), t)

    def test_negativ(self):
        for t in ("z.B", "z.B.Unternehmen", "M.Sc", "Dr.Müller", "vgl.Abb", "www.statista.com", "https://x.de/a.B", "Amazon.com",
                  "bericht.pdf", "Daten.XLSX", "14:30Uhr", "§2.BGB", "Mitarbeiter:innen", "Student:in", "1,5", "3.Kapitel",
                  "YouTube-Trendlisten-Analyse", "BachelorstudentInnenbefragung", "pandas.read_csv", "max@mustermann.de",
                  "Hochschulzugangsberechtigungsnote", "PowerPoint-Präsentationsvorlagen", "u.a", "e.V", "sog.Bachelor"):
            self.assertFalse(analyse._verklebt(t), t)

    def test_info_und_warnung(self):
        text = (FUELL + "Blüthmann prüfte mittels Strukturgleichungsmodell,wiesichdieHZB-Note auswirkt. Die Befragung wurde "
                "anhand von Haltungen erfasst.Merkmale des Studiums kamen hinzu. " + FUELL)
        e = analyse.analysiere_text(text, [])
        v = e["info"]["verklebt"]
        self.assertEqual([x["stelle"] for x in v], ["Strukturgleichungsmodell,wiesichdieHZB-Note", "erfasst.Merkmale"])
        self.assertEqual([x["satz"] for x in v], [4, 5])
        self.assertTrue(any("verklebte Stellen" in w for w in e["info"]["warnungen"]))
        sauber = analyse.analysiere_text(FUELL * 3, [])
        self.assertEqual(sauber["info"]["verklebt"], [])
        self.assertFalse(any("verklebt" in w for w in sauber["info"]["warnungen"]))

    def test_langer_ausschnitt_gekuerzt(self):
        e = analyse.analysiere_text("Das " + "Wort,und" * 12 + " endet hier. " + FUELL, [])
        self.assertLessEqual(len(e["info"]["verklebt"][0]["stelle"]), 60)


class Zitatanteil(unittest.TestCase):
    def test_spannen(self):
        t = "Er sagt »Wie ich das sehe: »Jawoll, erreicht«. Genau so.« Danach „kurz“ und \"noch eins hier\" offen „ohne Ende"
        sp = analyse.zitat_spannen(t)
        self.assertEqual([t[a:e] for a, e in sp],
                         ["»Wie ich das sehe: »Jawoll, erreicht«. Genau so.«", "„kurz“", "\"noch eins hier\""])
        schweiz = "Er sagt «Das ist ein Zitat mit fünf Wörtern» und geht."
        self.assertEqual([schweiz[a:e] for a, e in analyse.zitat_spannen(schweiz)], ["«Das ist ein Zitat mit fünf Wörtern»"])
        englisch = "Er sagt “so ist es eben” und geht."
        self.assertEqual(len(analyse.zitat_spannen(englisch)), 1)

    def test_anteil(self):
        zitat = "„Die Lehrenden sollten den Studierenden ermöglichen, das selbst herauszufinden.“"
        text = FUELL + "Eine Dozentin sagt dazu: " + zitat + " Der „Begriff“ bleibt offen. " + FUELL
        e = analyse.analysiere_text(text, [])
        n_zitat = 9  # Wörter im Zitat; der kurze „Begriff“ zählt nicht
        self.assertAlmostEqual(e["info"]["zitat_anteil"], round(n_zitat / e["info"]["woerter"], 4))
        self.assertEqual(analyse.analysiere_text(FUELL * 3, [])["info"]["zitat_anteil"], 0.0)


class Transkript(unittest.TestCase):
    def test_entfernt_und_gezaehlt(self):
        z = Counter()
        aus = analyse.bereinige_absatz("»Na ja ((lacht)) (unv.) einfach dann (I: Ja.), dass (…) man es schafft. Genau "
                                       "(unv.) Ziele.« Dabei (B2: genau) [unverständlich] (Pause 3 Sek.) bleibt es.", z)
        self.assertEqual(aus, "»Na ja einfach dann, dass man es schafft. Genau Ziele.« Dabei bleibt es.")
        self.assertEqual(z["transkript"], 8)

    def test_auslassung_nur_im_interviewkontext(self):
        z = Counter()
        self.assertEqual(analyse.bereinige_absatz("Er schreibt (…) weiter, und (...) so fort.", z),
                         "Er schreibt (…) weiter, und (...) so fort.")
        self.assertEqual(z["transkript"], 0)
        self.assertEqual(analyse.bereinige_absatz("Die Lösung (1) und (2) sowie (Pause) sind gut.", Counter()),
                         "Die Lösung (1) und (2) sowie sind gut.")

    def test_info_und_saetze(self):
        text = (FUELL + "Eine Absolventin sagt: »Na ja ((lacht)) erstmal natürlich, dass man es besteht (I: Ja.), und dann "
                "halt den Abschluss hat.« " + FUELL)
        e = analyse.analysiere_text(text, [])
        self.assertEqual(e["info"]["transkript_notation"], 2)
        alle = " ".join(s["text"] for s in e["saetze"])
        for rest in ("lacht", "(I:", "Ja.)"):
            self.assertNotIn(rest, alle)


class KlammerBelege(unittest.TestCase):
    def test_eckige_klammern_mit_jahr(self):
        z = Counter()
        aus = analyse.bereinige_absatz("So [Wolfram 2009] und ein Zitat.« [2018.06.06_Lehrende, Absatz 8] Dann [Mergner et "
                                       "al. (2015), S. 9)] und [0, 1] sowie [sic] und [Hervorh. d. Verf.] am Ende.", z)
        self.assertEqual(aus, "So und ein Zitat.« Dann und [0, 1] sowie [sic] und [Hervorh. d. Verf.] am Ende.")
        self.assertEqual(z["zitate"], 3)

    def test_interviewbeleg_trennt_saetze(self):
        text = (FUELL + "»Das ist das Ziel des Studiums, wer bin ich.« [2018.06.06_Lehrende, Absatz 8] Studierende darin zu "
                "unterstützen, wurde als Aufgabe gesehen. " + FUELL)
        e = analyse.analysiere_text(text, [])
        self.assertTrue(any(s["text"].startswith("Studierende darin") for s in e["saetze"]))


class Autorenlisten(unittest.TestCase):
    def test_keine_dreierliste(self):
        for s in ("Kahneman, Knetsch und Thaler (1986) haben gezeigt, dass Kunden fair urteilen.",
                  "Nach Xia, Monroe und Cox (2004) beurteilen Kunden die Fairness.",
                  "Die Studien von Kahneman, Knetsch und Thaler [1986] zeigen es.",
                  "Calvano, Calzolari, Denicolò und Pastorello (2020, S. 3) zeigen es.",
                  "Xia, Monroe und Cox et al. (2004) zeigen es.",
                  "van Dick, Wagner und Stellmacher (2004) zeigen es."):
            self.assertEqual(analyse.dreierlisten(s), [], s)  # Beleg noch im Satz
            e = analyse.analysiere_text(s, [])  # Beleg in bereinige_absatz entfernt, Liste aus dem Rohabsatz
            self.assertEqual(e["metriken"]["dreierlisten_pro_1000"], 0.0, s)
            self.assertNotIn("dreierliste", e["saetze"][0]["flags"], s)

    def test_echte_listen_bleiben(self):
        for s in ("Bekanntheit, Reputation und Image sind wichtig (Cable & Turban, 2001).",
                  "Die Länder Deutschland, Frankreich und Italien (Eurostat 2019) wachsen.",
                  "Meyer, Allen und Smith zeigen 1993, dass es gilt."):
            self.assertEqual(len(analyse.dreierlisten(analyse.bereinige_absatz(s, Counter()))), 1, s)
            self.assertGreater(analyse.analysiere_text(s, [])["metriken"]["dreierlisten_pro_1000"], 0.0, s)

    def test_autorenlisten(self):
        self.assertEqual(analyse.autorenlisten("Laut Kahneman, Knetsch und Thaler (1986) und Ezrachi und Stucke (2016) gilt."),
                         ["Kahneman, Knetsch und Thaler"])
        self.assertEqual(analyse.autorenlisten("Bekanntheit, Reputation und Image (Cable & Turban, 2001)"), [])


class BlockmodusV7(unittest.TestCase):
    def test_score_ki_je_block(self):
        rnd = random.Random(9)
        text = text_erzeugen(rnd, 2600, (4, 34), FW_MENSCH)
        bl = baselines_klein()
        bl["textsorten"]["hochschule"]["metriken"] = {
            "satzlaenge_cv": ref(0.35, 0.38, 0.43, 0.48, 0.53, ki50=0.37, gewicht=0.5),
            "anteil_lange_saetze": ref(0.04, 0.08, 0.15, 0.24, 0.35, ki50=0.07, gewicht=0.4)}
        bl["textsorten"]["hochschule"]["modell"] = None
        erg, bew = analyse.analysiere_und_bewerte(text, [], bl)
        self.assertTrue(bew["blockmodus"])
        self.assertIn("score_ki", bew)
        self.assertTrue(all("score_ki" in b and b["score_ki"] >= b["score"] for b in bew["bloecke"]))


if __name__ == "__main__":
    unittest.main()
