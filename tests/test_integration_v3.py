"""Integration v3: kalibriere.py ↔ analyse.py nach den Schnittstellen S1–S4, Ende zu Ende über einen kleinen
synthetischen Korpus (kalibriere.main → baselines.json/ki_muster.json → analyse.bewerte/analysiere_und_bewerte/main).

S1 z-Clipping identisch in Kalibrierung und Laufzeit, S2 Modellbeiträge (Intercept-Term am menschlichen Median
+ Σ Beiträge = Logit; Median der KI-Beiträge = Goodhart-Analyse der Kalibrierung), S3 unsicher-Regel mit der
Wortzahl (auch im Blockmodus), S4 Blockmodus mit den kalibrierten Dateien.

python3 -m unittest discover -s tests
"""
import contextlib
import copy
import io
import json
import math
import os
import random
import re
import shutil
import statistics
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


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, x))))


def logit_kalibriere(mod: dict, werte: dict) -> float:
    """Logit wie kalibriere.p_mensch (z_wert mit Kappung und Clipping, fehlend = 0), aus dem Modell in baselines.json.
    v7: einseitige Kappung am menschlichen Band (modell['kappen']) wie in Fit und bewerte()."""
    kappen = mod.get("kappen") or {}
    return mod["intercept"] + sum(c * kalibriere.z_wert(werte.get(k), mod["mittel"][k], mod["sd"][k], kappen.get(k))
                                  for k, c in mod["koeffizienten"].items())


def logit_am_median(ts: dict, werte: dict) -> float:
    """Intercept-Term am menschlichen Median: Intercept + Σ koef · z(mensch_p50) über die Merkmale mit Wert."""
    mod = ts["modell"]
    kappen = mod.get("kappen") or {}
    out = mod["intercept"]
    for k, c in mod["koeffizienten"].items():
        if werte.get(k) is None:
            continue
        p50 = ((ts["metriken"].get(k) or {}).get("mensch") or {}).get("p50")
        out += c * (kalibriere.z_wert(p50, mod["mittel"][k], mod["sd"][k], kappen.get(k)) if p50 is not None else 0.0)
    return out


def unsicher_erwartet(zeile: dict, se: float | None, n_woerter: int) -> bool:
    """S3 unabhängig nachgerechnet."""
    if not se:
        return False
    grenze = min(abs(zeile["wert"] - zeile["mensch_p25"]), abs(zeile["wert"] - zeile["mensch_p75"]))
    return grenze < 0.5 * se * math.sqrt(800 / max(800, n_woerter))


class V3EndeZuEnde(unittest.TestCase):
    """Synthetischer Korpus → kalibriere.main (eigene Ausgabepfade) → Laufzeit mit denselben Dateien."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        rnd = random.Random(31)
        korpus = os.path.join(cls.tmp, "korpus")
        for q in ("q1", "q2"):
            os.makedirs(os.path.join(korpus, "mensch", q))
        os.makedirs(os.path.join(korpus, "ki", "claude"))
        meta_m = {"q1": [], "q2": []}
        meta_k = []
        cls.texte = {}
        for i in range(14):
            q = "q1" if i % 2 else "q2"
            mid, kid = f"m{i:02d}", f"k{i:02d}"
            tm = text_erzeugen(rnd, 2800, (4, 38), FW_MENSCH)
            tk = text_erzeugen(rnd, 1000, (15, 19), FW_KI) + "\n\nInsgesamt zeigt sich, dass die Methode maßgeblich wirkt."
            cls.texte[mid], cls.texte[kid] = tm, tk
            with open(os.path.join(korpus, "mensch", q, mid + ".txt"), "w", encoding="utf-8") as f:
                f.write(tm)
            with open(os.path.join(korpus, "ki", "claude", kid + ".txt"), "w", encoding="utf-8") as f:
                f.write(tk)
            meta_m[q].append({"id": mid, "quelle": q, "typ": "Bachelorarbeit", "jahr": 2008 + i})
            meta_k.append({"id": kid, "basis_id": mid, "quelle": "claude", "typ": "Bachelorarbeit"})
        for q, zeilen in meta_m.items():
            with open(os.path.join(korpus, "mensch", q, "meta.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(z) for z in zeilen) + "\n")
        with open(os.path.join(korpus, "ki", "claude", "meta.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(z) for z in meta_k) + "\n")
        cls.daten = os.path.join(cls.tmp, "daten")
        os.makedirs(cls.daten)
        cls.muster_pfad = os.path.join(cls.daten, "ki_muster.json")
        shutil.copy(MUSTER_PFAD, cls.muster_pfad)
        cls.baselines_pfad = os.path.join(cls.daten, "baselines.json")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.rc = kalibriere.main(["--korpus", korpus, "--aus", os.path.join(cls.tmp, "aus"),
                                      "--baselines", cls.baselines_pfad, "--muster", cls.muster_pfad,
                                      "--cv-wiederholungen", "1", "--cv-folds", "2", "--bootstrap", "50"])
        with open(cls.baselines_pfad, encoding="utf-8") as f:
            cls.b = json.load(f)
        cls.ts = cls.b["textsorten"]["hochschule"]
        cls.mod = cls.ts["modell"]
        cls.muster = analyse.lade_muster(cls.muster_pfad)
        cls.muster_roh = analyse.lade_muster(cls.muster_pfad)
        for mu in cls.muster_roh:
            mu["gewicht"] = 1.0
        cls.gew = {mu["id"]: mu["gewicht"] for mu in cls.muster}
        cls.abschnitte = cls._abschnitte()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def _abschnitte(cls) -> list[dict]:
        """Alle Abschnitte wie kalibriere.main (zerlegen, kürzen, ≥ 12 Sätze) mit beiden Messwegen:
        'zeile' = kalibriere (Rohmuster, abgeleitet mit den finalen Gewichten und dem Profil), 'erg' = analyse.py."""
        profil = cls.ts["fw_profil"]
        out = []
        for doc_id, t in sorted(cls.texte.items()):
            mensch = doc_id.startswith("m")
            roh = kalibriere.zerlege(t, max_abschnitte=3 if mensch else 1) or [t]
            for ab in roh:
                kurz = kalibriere.kuerze(ab)
                if kurz is None:
                    continue
                e = kalibriere.analysiere_abschnitt(kurz, cls.muster_roh)
                if e["info"]["saetze"] < 12:
                    continue
                n_fw, k_fw = kalibriere.fw_zaehlung(e, kurz, profil["woerter"])
                zeile = {"saetze": e["info"]["saetze"], **e["metriken"], "_fw": k_fw, "_n": n_fw,
                         "_token": e["info"]["token"], "_treffer": Counter(x["muster"] for x in e["muster_treffer"]),
                         "_kand": kalibriere.muster_kandidaten(e["saetze"], cls.muster_roh)}
                zeile = kalibriere.abgeleitet(zeile, cls.gew, profil)
                erg = analyse.analysiere_text(kurz, cls.muster, fw_profil=profil, letzter_absatz_gekuerzt=True)
                out.append({"doc_id": doc_id, "gruppe": "mensch" if mensch else "ki", "text": kurz, "zeile": zeile,
                            "erg": erg})
        return out

    def langer_text(self, ids: list[str]) -> str:
        return "\n\n".join(f"# Kapitel {i}\n\n{self.texte[d]}" for i, d in enumerate(ids, 1))

    # ------------------------------------------------------------------ Grundlagen
    def test_lauf_und_dateien(self):
        self.assertEqual(self.rc, 0)
        self.assertEqual(self.b["version"], "4")  # v4: einseitige Kappung (v7)
        self.assertTrue(self.mod["kappen"])
        self.assertEqual(self.mod["z_clip"], analyse.Z_CLIP)
        self.assertEqual(self.b["evaluation"]["hyperparameter"]["z_clip"], analyse.Z_CLIP)
        self.assertTrue(self.mod["koeffizienten"])
        self.assertTrue(any(z["gruppe"] == "ki" for z in self.abschnitte))
        self.assertGreaterEqual(sum(z["gruppe"] == "mensch" for z in self.abschnitte), 20)

    # ------------------------------------------------------------------ S1
    def test_s1_eine_konstante_eine_formel(self):
        self.assertEqual(kalibriere.Z_CLIP, analyse.Z_CLIP)
        self.assertEqual(analyse.Z_CLIP, 3.0)
        rnd = random.Random(5)
        for _ in range(500):
            x, mu = rnd.uniform(-50, 50), rnd.uniform(-5, 5)
            sd = rnd.choice([0.0, None, rnd.uniform(0.01, 4)])
            self.assertEqual(kalibriere.z_wert(x, mu, sd), analyse.z_standard(x, mu, sd))
            self.assertLessEqual(abs(analyse.z_standard(x, mu, sd)), analyse.Z_CLIP)
        self.assertEqual(kalibriere.z_wert(None, 1.0, 2.0), 0.0)  # fehlend = Mittelwert; bewerte() überspringt ihn

    def test_s1_p_mensch_wie_kalibriere(self):
        """kalibriere.p_mensch (Modell aus baselines.json) = analyse.bewerte auf denselben Abschnitten."""
        merkmale = list(self.mod["koeffizienten"])
        modell = {"merkmale": merkmale, "w": [self.mod["koeffizienten"][k] for k in merkmale], "b": self.mod["intercept"]}
        paket = {"mittel": self.mod["mittel"], "sd": self.mod["sd"], "kappen": self.mod["kappen"]}  # v7
        for a in self.abschnitte:
            p_kal = kalibriere.p_mensch(modell, paket, a["zeile"])
            bew = analyse.bewerte(copy.deepcopy(a["erg"]), self.b)
            self.assertAlmostEqual(bew["p_mensch"], p_kal, delta=0.0005 + 1e-9)
            self.assertEqual(bew["score"], round(kalibriere.score(self.ts["metriken"], a["zeile"])))

    def test_s1_ausreisser_begrenzt(self):
        """Jedes Modellmerkmal einzeln auf ±10 SD gesetzt: beide Seiten begrenzen auf ±3 (die Gegenseite schon vorher am
        menschlichen Band, v7), also gleiche p wie bei ±3 SD."""
        merkmale = list(self.mod["koeffizienten"])
        modell = {"merkmale": merkmale, "w": [self.mod["koeffizienten"][k] for k in merkmale], "b": self.mod["intercept"]}
        paket = {"mittel": self.mod["mittel"], "sd": self.mod["sd"], "kappen": self.mod["kappen"]}
        a = next(x for x in self.abschnitte if x["gruppe"] == "mensch")
        for k in merkmale:
            for faktor in (10.0, -10.0):
                zeile = dict(a["zeile"])
                erg = copy.deepcopy(a["erg"])
                wert = self.mod["mittel"][k] + faktor * (self.mod["sd"][k] or 1.0)
                zeile[k] = erg["metriken"][k] = wert
                p_kal = kalibriere.p_mensch(modell, paket, zeile)
                p_lauf = analyse.bewerte(erg, self.b)["p_mensch"]
                self.assertAlmostEqual(p_lauf, p_kal, delta=0.0005 + 1e-9, msg=k)
                erg3 = copy.deepcopy(a["erg"])
                erg3["metriken"][k] = self.mod["mittel"][k] + math.copysign(3.0, faktor) * (self.mod["sd"][k] or 1.0)
                self.assertAlmostEqual(analyse.bewerte(erg3, self.b)["p_mensch"], p_lauf, delta=0.0011, msg=k)

    # ------------------------------------------------------------------ S2
    def test_s2_beitraege_und_intercept_term_gleich_logit(self):
        for a in self.abschnitte:
            erg = copy.deepcopy(a["erg"])
            bew = analyse.bewerte(erg, self.b)
            m = erg["metriken"]
            logit = logit_kalibriere(self.mod, m)
            summe = sum(x["beitrag"] for x in bew["modell_beitraege"])
            self.assertAlmostEqual(logit_am_median(self.ts, m) + summe, logit, delta=1e-3)
            self.assertAlmostEqual(bew["p_mensch"], sigmoid(logit), delta=0.0005 + 1e-9)
            werte = [x["beitrag"] for x in bew["modell_beitraege"]]
            self.assertEqual(werte, sorted(werte))
            self.assertEqual({x["id"] for x in bew["modell_beitraege"]},
                             {k for k in self.mod["koeffizienten"] if m.get(k) is not None})
            zeilen = {z["id"]: z for z in bew["kennzahlen"]}
            for x in bew["modell_beitraege"]:
                self.assertEqual(zeilen[x["id"]]["beitrag"], x["beitrag"])
            for k, z in zeilen.items():
                if k not in self.mod["koeffizienten"]:
                    self.assertIsNone(z["beitrag"], k)

    def test_s2_median_der_ki_beitraege_wie_goodhart(self):
        """Goodhart-Analyse der Kalibrierung (S2-Definition, finales Modell) = Median der Laufzeit-Beiträge der KI-Abschnitte."""
        gh = self.ts["goodhart"]
        ki = [a for a in self.abschnitte if a["gruppe"] == "ki"]
        self.assertEqual(gh["n_ki"], len(ki))
        je_merkmal = {k: [] for k in self.mod["koeffizienten"]}
        for a in ki:
            bew = analyse.bewerte(copy.deepcopy(a["erg"]), self.b)
            for x in bew["modell_beitraege"]:
                je_merkmal[x["id"]].append(x["beitrag"])
        for r in gh["merkmale"]:
            xs = je_merkmal[r["id"]]
            erwartet = statistics.median(xs) if xs else 0.0
            # kalibriere rechnet mit ungerundeten Koeffizienten/Mittelwerten, baselines.json speichert gerundete
            self.assertAlmostEqual(r["median_beitrag_ki"], erwartet, delta=2e-3, msg=r["id"])

    # ------------------------------------------------------------------ S3
    def test_s3_unsicher_mit_kalibrierten_se(self):
        se = {k: v.get("se_typ") for k, v in self.ts["metriken"].items()}
        self.assertTrue(any(se.values()))
        n_unsicher = 0
        for a in self.abschnitte:
            erg = copy.deepcopy(a["erg"])
            bew = analyse.bewerte(erg, self.b)
            for z in bew["kennzahlen"]:
                self.assertEqual(z["unsicher"], unsicher_erwartet(z, se.get(z["id"]), erg["info"]["woerter"]), z["id"])
                n_unsicher += z["unsicher"]
        self.assertGreater(n_unsicher, 0)

    def test_s3_status_score_p_unberuehrt(self):
        a = next(x for x in self.abschnitte if x["gruppe"] == "ki")
        ohne_se = copy.deepcopy(self.b)
        for v in ohne_se["textsorten"]["hochschule"]["metriken"].values():
            v.pop("se_typ", None)
        breit = copy.deepcopy(self.b)
        for v in breit["textsorten"]["hochschule"]["metriken"].values():
            v["se_typ"] = 1e6
        b1 = analyse.bewerte(copy.deepcopy(a["erg"]), ohne_se)
        b2 = analyse.bewerte(copy.deepcopy(a["erg"]), breit)
        self.assertFalse(any(z["unsicher"] for z in b1["kennzahlen"]))
        self.assertTrue(all(z["unsicher"] for z in b2["kennzahlen"]))
        for feld in ("score", "p_mensch", "modell_beitraege"):
            self.assertEqual(b1[feld], b2[feld], feld)
        self.assertEqual([(z["id"], z["status"]) for z in b1["kennzahlen"]], [(z["id"], z["status"]) for z in b2["kennzahlen"]])

    # ------------------------------------------------------------------ S4
    def test_s4_abschnitt_kein_blockmodus(self):
        """Kalibrierabschnitte (≈ 800 Wörter): analysiere_und_bewerte = bewerte(analysiere_text) + drei Felder."""
        for a in self.abschnitte[::4]:
            erg, bew = analyse.analysiere_und_bewerte(a["text"], self.muster, self.b)
            e2 = analyse.analysiere_text(a["text"], self.muster, fw_profil=self.ts["fw_profil"])
            erwartet = analyse.bewerte(e2, self.b)
            erwartet.update(blockmodus=False, n_woerter=e2["info"]["woerter"], bloecke=[])
            self.assertEqual(erg, e2)
            self.assertEqual(bew, erwartet)

    def pruefe_blockbewertung(self, erg: dict, bew: dict):
        bl = bew["bloecke"]
        self.assertTrue(bew["blockmodus"])
        self.assertGreater(bew["n_woerter"], analyse.BLOCK_AB)
        self.assertEqual(bew["n_woerter"], erg["info"]["woerter"])
        self.assertEqual(sum(b["woerter"] for b in bl), bew["n_woerter"])
        self.assertEqual(bl[0]["satz_von"], 1)
        self.assertEqual(bl[-1]["satz_bis"], erg["info"]["saetze"])
        for x, y in zip(bl, bl[1:]):
            self.assertEqual(x["satz_bis"] + 1, y["satz_von"])
        if len(bl) > 1:
            self.assertTrue(all(b["woerter"] >= 0.75 * analyse.ABSCHNITT_L for b in bl))
        # p_mensch = Median der Blöcke; Score, Beiträge und unsicher aus dem Medianvektor (S2/S3 auch hier)
        self.assertEqual(bew["p_mensch"], round(statistics.median(b["p_mensch"] for b in bl), 3))
        werte = {z["id"]: z["wert"] for z in bew["kennzahlen"]}
        werte["saetze"] = statistics.median(b["satz_bis"] - b["satz_von"] + 1 for b in bl)
        self.assertEqual(bew["score"], round(kalibriere.score(self.ts["metriken"], werte)))
        summe = sum(x["beitrag"] for x in bew["modell_beitraege"])
        self.assertAlmostEqual(logit_am_median(self.ts, werte) + summe, logit_kalibriere(self.mod, werte), delta=1e-3)
        for z in bew["kennzahlen"]:
            se = self.ts["metriken"][z["id"]].get("se_typ")
            self.assertEqual(z["unsicher"], unsicher_erwartet(z, se, bew["n_woerter"]), z["id"])

    def test_s4_lange_texte_mit_kalibrierten_dateien(self):
        erg_m, bew_m = analyse.analysiere_und_bewerte(self.langer_text(["m00", "m03"]), self.muster, self.b)
        erg_k, bew_k = analyse.analysiere_und_bewerte(self.langer_text(["k01", "k02", "k05", "k06"]), self.muster, self.b)
        self.pruefe_blockbewertung(erg_m, bew_m)
        self.pruefe_blockbewertung(erg_k, bew_k)
        self.assertGreaterEqual(len(bew_m["bloecke"]), 5)
        self.assertGreaterEqual(len(bew_k["bloecke"]), 4)
        self.assertGreater(bew_m["p_mensch"], bew_k["p_mensch"])
        self.assertTrue(any(w.startswith(analyse.BLOCK_HINWEIS) for w in erg_m["info"]["warnungen"]))

    def test_s4_cli_json_und_bericht(self):
        pfad = os.path.join(self.tmp, "lang.md")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(self.langer_text(["m02", "m05"]))
        argv = [pfad, "--baselines", self.baselines_pfad, "--muster", self.muster_pfad]
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            self.assertEqual(analyse.main(argv + ["--format", "json"]), 0)
        aus = json.loads(puffer.getvalue())
        bew = aus["bewertung"]
        self.assertTrue(bew["blockmodus"])
        self.assertEqual(bew["ziel_p_mensch"], self.ts["ziel_p_mensch"])
        self.assertEqual(len(aus["saetze"]), bew["bloecke"][-1]["satz_bis"])
        self.assertFalse(any(x["beitrag"] == 0 and math.copysign(1.0, x["beitrag"]) < 0 for x in bew["modell_beitraege"]))
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            self.assertEqual(analyse.main(argv), 0)
        md = puffer.getvalue()
        self.assertIn("**Blöcke**", md)
        self.assertIn("← am KI-nächsten", md)
        self.assertIn("(Median der Blöcke)", md)
        zeilen = [z for z in md.splitlines() if re.match(r"^\| \d+ \| \d+–\d+ \|", z)]
        self.assertEqual(len(zeilen), len(bew["bloecke"]))


if __name__ == "__main__":
    unittest.main()
