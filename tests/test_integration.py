"""Integration analyse.py ↔ kalibriere.py ↔ baselines.json (Schnittstellen 1–4).

python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import math
import os
import random
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


def muster_mit(gewichte: dict) -> list[dict]:
    """Plugin-Muster mit gesetzten Gewichten (übrige 0)."""
    out = analyse.lade_muster(MUSTER_PFAD)
    for mu in out:
        mu["gewicht"] = gewichte.get(mu["id"], 0.0)
    return out


def zeile_wie_kalibriere(text: str, muster_roh: list[dict], fw_woerter: list[str]) -> dict:
    """Eine Zeile so, wie kalibriere.main sie aus einem gekürzten Abschnitt baut."""
    erg = kalibriere.analysiere_abschnitt(text, muster_roh)
    n_fw, k_fw = kalibriere.fw_zaehlung(erg, text, fw_woerter)
    return {"saetze": erg["info"]["saetze"], **erg["metriken"], "_fw": k_fw, "_n": n_fw, "_token": erg["info"]["token"],
            "_treffer": Counter(t["muster"] for t in erg["muster_treffer"]),
            "_kand": kalibriere.muster_kandidaten(erg["saetze"], muster_roh)}


class EineFormel(unittest.TestCase):
    def test_fw_llr_aus_analyse(self):
        self.assertIs(analyse._fw_llr_zaehlung, analyse.fw_llr_zaehlung)
        profil = {"woerter": ["es", "als"], "rate_mensch": {"es": 0.02, "als": 0.005},
                  "rate_ki": {"es": 0.01, "als": 0.01}, "groesse": {"es": 6.0, "als": 1e6}}
        woerter = ["es"] * 9 + ["als"] * 2 + ["haus"] * 389
        self.assertEqual(kalibriere.fw_llr_zaehlung(Counter(woerter), len(woerter), profil),
                         analyse.fw_llr(woerter, profil))
        self.assertIsNone(kalibriere.fw_llr_zaehlung({}, 0, profil))

    def test_abschnittslaenge_gleich(self):
        self.assertEqual(kalibriere.L_STANDARD, analyse.ABSCHNITT_L)
        self.assertTrue(kalibriere._MIT_KUERZUNG)  # Schnittstelle 1 wird genutzt


class MusterWieLaufzeit(unittest.TestCase):
    """ki_muster_pro_1000 in der Kalibrierung = Laufzeitwert (Überlappung nach Gewicht, Gewicht 0 zählt nicht)."""

    SAETZE = ("Die Digitalisierung trägt maßgeblich dazu bei, dass Prozesse schneller werden. "
              "Insgesamt zeigt sich, dass die Betriebe davon profitieren. "
              "Dies verdeutlicht, wie wichtig eine gute Planung ist. "
              "Darüber hinaus ermöglicht es die Technik, Kosten zu senken.")

    def pruefe(self, gewichte):
        roh = muster_mit({})
        for mu in roh:
            mu["gewicht"] = 1.0
        z = kalibriere.abgeleitet(zeile_wie_kalibriere(self.SAETZE, roh, ["es"]), gewichte, {})
        laufzeit = analyse.analysiere_text(self.SAETZE, muster_mit(gewichte), letzter_absatz_gekuerzt=True)
        self.assertAlmostEqual(z["ki_muster_pro_1000"], laufzeit["metriken"]["ki_muster_pro_1000"], places=4)
        return z

    def test_hoeheres_gewicht_kuerzerer_treffer(self):
        # Kalibrierung zählt mit Gewicht 1 (längster gewinnt: beitrag_leisten), Laufzeit nimmt massgeblich (Gewicht 2)
        gew = {"massgeblich": 2.0, "beitrag_leisten": 0.5, "insgesamt_zeigt": 1.5, "dies_verdeutlicht": 1.2,
               "verdeutlicht": 0.8, "darueber_hinaus": 1.0, "ermoeglicht": 1.4}
        z = self.pruefe(gew)
        alt = 1000 * sum(gew.get(mid, 0) * n for mid, n in z["_treffer"].items()) / z["_token"]
        self.assertNotAlmostEqual(alt, z["ki_muster_pro_1000"], places=3)  # alte Rechnung wich ab

    def test_gewicht_null_verdraengt_nicht(self):
        self.pruefe({"massgeblich": 1.0, "beitrag_leisten": 0.0, "dies_verdeutlicht": 0.0, "verdeutlicht": 1.1})

    def test_kein_doppeltes_gedankenstrich_muster(self):
        ids = {mu["id"] for mu in analyse.lade_muster(MUSTER_PFAD)}
        self.assertNotIn("gedankenstrich", ids)  # misst gedankenstrich_pro_1000 (Review inhalt_und_muster 9)
        e = analyse.analysiere_text("Die Ergebnisse – so die Autoren – sind robust. Sie gelten weiter.",
                                    muster_mit({mid: 1.0 for mid in ids}))
        self.assertEqual(e["saetze"][0]["flags"].count("gedankenstrich"), 1)
        self.assertFalse(any(f.startswith("muster:gedankenstrich") for f in e["saetze"][0]["flags"]))


class Fenster(unittest.TestCase):
    def test_fenster_starts(self):
        self.assertEqual(analyse.fenster_starts(500), [0])
        self.assertEqual(analyse.fenster_starts(800), [0])
        self.assertEqual(analyse.fenster_starts(2000, 800), [0, 600, 1200])
        self.assertEqual(analyse.fenster_starts(801, 800), [0, 1])

    def test_satz_fenster(self):
        w = [20] * 100  # 2000 Wörter
        f = analyse.satz_fenster(w, 800)
        self.assertEqual(len(f), 3)
        self.assertEqual(f[0][0], 0)
        self.assertEqual(f[-1][1], 100)
        self.assertTrue(all(sum(w[a:e]) <= 800 for a, e in f))
        self.assertEqual(analyse.satz_fenster([30] * 10, 800), [(0, 10)])

    def test_kurzer_text_unveraendert(self):
        # Kalibrierabschnitte (≤ 800 Wörter) werden am Stück gemessen: Kalibrierung bleibt gleich
        text = text_erzeugen(random.Random(3), 700, (4, 38), FW_MENSCH)
        e = analyse.analysiere_text(text, [])
        self.assertLessEqual(e["info"]["woerter"], 800)
        self.assertAlmostEqual(e["metriken"]["satzlaenge_schiefe"], round(analyse.schiefe(e["info"]["satzlaengen"]), 4))
        woerter = kalibriere._woerter_low(text)
        self.assertAlmostEqual(e["metriken"]["mattr_klumpung_100"], round(analyse.mattr_klumpung(woerter, 100), 4))

    def test_warnung_langer_text(self):
        kurz = analyse.analysiere_text(text_erzeugen(random.Random(5), 900, (8, 30), FW_MENSCH), [])
        lang = analyse.analysiere_text(text_erzeugen(random.Random(5), 1800, (8, 30), FW_MENSCH), [])
        self.assertFalse(any("Abschnitten à 800" in w for w in kurz["info"]["warnungen"]))
        self.assertTrue(any("Abschnitten à 800" in w for w in lang["info"]["warnungen"]))

    def test_langer_text_fensterweise(self):
        text = text_erzeugen(random.Random(4), 2600, (4, 38), FW_MENSCH)
        e = analyse.analysiere_text(text, [])
        woerter = kalibriere._woerter_low(text)
        n = len(woerter)
        self.assertGreater(n, 1600)
        erwartet = statistics.median(analyse.mattr_klumpung(woerter[a:a + 800], 100) for a in analyse.fenster_starts(n))
        self.assertAlmostEqual(e["metriken"]["mattr_klumpung_100"], round(erwartet, 4))
        self.assertNotAlmostEqual(e["metriken"]["satzlaenge_schiefe"], round(analyse.schiefe(e["info"]["satzlaengen"]), 4))


class BewerteNurModell(unittest.TestCase):
    def test_nur_modell_ohne_ampel_und_score(self):
        ref = {"mensch": {"p10": -2, "p25": 0, "p50": 2, "p75": 4, "p90": 6, "sd": 2.0}, "ki": {"p50": -3, "sd": 2.0},
               "auroc": 0.95, "gewicht": 0.0, "bewertet": False, "nur_modell": True, "se_typ": 2.8}
        b = {"textsorten": {"hochschule": {"metriken": {"fw_profil_llr_pro_1000": ref}}}}
        erg = {"metriken": {"fw_profil_llr_pro_1000": -5.0}, "info": {"saetze": 40}}
        bew = analyse.bewerte(erg, b)
        z = bew["kennzahlen"][0]
        self.assertTrue(z["nur_modell"])
        self.assertIsNone(bew["score"])
        erg.update(saetze=[], muster_treffer=[])
        erg["info"].update(woerter=500, absaetze=3, zitate_entfernt=0, literatur_abgeschnitten=False, warnungen=[],
                           satzlaengen_verteilung={}, satzlaengen=[])
        md = analyse.bericht_markdown(erg, bew)
        self.assertIn("nur Tendenz", md)
        self.assertNotIn("🔴", md)

    def test_grenzfall_nur_ausserhalb_gruen(self):
        def ref(gewicht):
            return {"mensch": {"p10": 0, "p25": 1, "p50": 2, "p75": 3, "p90": 4, "sd": 1.0}, "ki": {"p50": 3, "sd": 1.0},
                    "auroc": 0.8, "gewicht": gewicht, "bewertet": True, "se_typ": 0.5}
        b = {"textsorten": {"hochschule": {"metriken": {"a": ref(0.5), "b": ref(0.5)}}}}
        erg = {"metriken": {"a": 2.9, "b": 3.2}, "info": {"saetze": 40, "woerter": 500, "absaetze": 3, "zitate_entfernt": 0,
               "literatur_abgeschnitten": False, "warnungen": [], "satzlaengen_verteilung": {}, "satzlaengen": []},
               "saetze": [], "muster_treffer": []}
        bew = analyse.bewerte(erg, b)
        z = {r["id"]: r for r in bew["kennzahlen"]}
        self.assertTrue(z["a"]["unsicher"] and z["b"]["unsicher"])  # Flag laut Schnittstelle 4 unverändert
        self.assertEqual(bew["score"], 75)                          # Score unberührt
        zeilen = {l.split("|")[2].strip(): l for l in analyse.bericht_markdown(erg, bew).splitlines() if l.startswith("| 🟢") or l.startswith("| 🟡")}
        self.assertNotIn("Grenzfall", zeilen["a"])
        self.assertIn("Grenzfall", zeilen["b"])


class EndeZuEnde(unittest.TestCase):
    """Synthetischer Korpus → kalibriere.main → baselines.json → analyse.main/bewerte (Schnittstellen 1–4)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        rnd = random.Random(21)
        korpus = os.path.join(cls.tmp, "korpus")
        os.makedirs(os.path.join(korpus, "mensch", "q1"))
        os.makedirs(os.path.join(korpus, "ki", "claude"))
        meta_m, meta_k = [], []
        cls.texte = {}
        for i in range(12):
            mid, kid = f"m{i:02d}", f"k{i:02d}"
            tm = text_erzeugen(rnd, 2800, (4, 38), FW_MENSCH)
            tk = text_erzeugen(rnd, 1000, (15, 19), FW_KI) + "\n\nInsgesamt zeigt sich, dass die Methode maßgeblich wirkt."
            cls.texte[mid], cls.texte[kid] = tm, tk
            with open(os.path.join(korpus, "mensch", "q1", mid + ".txt"), "w", encoding="utf-8") as f:
                f.write(tm)
            with open(os.path.join(korpus, "ki", "claude", kid + ".txt"), "w", encoding="utf-8") as f:
                f.write(tk)
            meta_m.append({"id": mid, "quelle": "q1", "typ": "Bachelorarbeit", "jahr": 2010})
            meta_k.append({"id": kid, "basis_id": mid, "quelle": "claude", "typ": "Bachelorarbeit"})
        with open(os.path.join(korpus, "mensch", "q1", "meta.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(z) for z in meta_m) + "\n")
        with open(os.path.join(korpus, "ki", "claude", "meta.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(z) for z in meta_k) + "\n")
        cls.daten = os.path.join(cls.tmp, "daten")
        os.makedirs(cls.daten)
        shutil.copy(MUSTER_PFAD, os.path.join(cls.daten, "ki_muster.json"))
        cls.baselines_pfad = os.path.join(cls.daten, "baselines.json")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.rc = kalibriere.main(["--korpus", korpus, "--aus", os.path.join(cls.tmp, "aus"), "--baselines", cls.baselines_pfad,
                                      "--muster", os.path.join(cls.daten, "ki_muster.json"), "--cv-wiederholungen", "1",
                                      "--cv-folds", "2", "--bootstrap", "50"])
        with open(cls.baselines_pfad, encoding="utf-8") as f:
            cls.b = json.load(f)
        cls.muster = analyse.lade_muster(os.path.join(cls.daten, "ki_muster.json"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_baselines_felder(self):
        self.assertEqual(self.rc, 0)
        t = self.b["textsorten"]["hochschule"]
        for k in ("fw_profil", "ziel_p_mensch", "score_schwelle", "cluster", "modell"):
            self.assertIn(k, t)
        self.assertEqual(set(t["fw_profil"]), {"woerter", "rate_mensch", "rate_ki", "groesse", "woerter_mensch", "woerter_ki", "methode"})
        met = t["metriken"]
        self.assertTrue(any("se_typ" in v for v in met.values()))
        for v in met.values():
            if v["bewertet"]:
                self.assertIn("cluster", v)
                self.assertIn(v["cluster"], t["cluster"])

    def test_abschnitt_wie_bewerte(self):
        # In-sample-Score und p_mensch aus kalibriere = analyse.bewerte auf demselben gekürzten Abschnitt
        t = self.b["textsorten"]["hochschule"]
        gew = {mu["id"]: mu["gewicht"] for mu in self.muster}
        roh = analyse.lade_muster(os.path.join(self.daten, "ki_muster.json"))
        for mu in roh:
            mu["gewicht"] = 1.0
        mod = t["modell"]
        for doc_id in ("m00", "k00", "k03"):
            ab = kalibriere.zerlege(self.texte[doc_id], max_abschnitte=1)[0]
            kurz = kalibriere.kuerze(ab)
            self.assertIsNotNone(kurz)
            z = kalibriere.abgeleitet(zeile_wie_kalibriere(kurz, roh, t["fw_profil"]["woerter"]), gew, t["fw_profil"])
            e = analyse.analysiere_text(kurz, self.muster, fw_profil=t["fw_profil"], letzter_absatz_gekuerzt=True)
            bew = analyse.bewerte(e, self.b)
            for k in ("ki_muster_pro_1000", "fw_profil_llr_pro_1000"):
                self.assertAlmostEqual(z[k], e["metriken"][k], places=4)
            self.assertEqual(bew["score"], round(kalibriere.score(t["metriken"], z)))
            # S1: z auf ±Z_CLIP begrenzt wie in kalibriere.py (vorher ungeklippt nachgerechnet; nur grün, solange
            # im synthetischen Korpus kein |z| > 3 vorkam)
            kappen = mod.get("kappen") or {}  # v7: einseitige Kappung wie in kalibriere.py und bewerte()
            zz = mod["intercept"] + sum(c * kalibriere.z_wert(z[k], mod["mittel"][k], mod["sd"][k], kappen.get(k))
                                        for k, c in mod["koeffizienten"].items() if z.get(k) is not None)
            self.assertAlmostEqual(bew["p_mensch"], round(1 / (1 + math.exp(-max(-30, min(30, zz)))), 3), places=3)

    def test_analyse_cli_json(self):
        pfad = os.path.join(self.tmp, "eingabe.md")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(self.texte["m05"])
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            rc = analyse.main([pfad, "--baselines", self.baselines_pfad, "--muster", os.path.join(self.daten, "ki_muster.json"),
                               "--format", "json", "--ohne-saetze"])
        self.assertEqual(rc, 0)
        aus = json.loads(puffer.getvalue())
        self.assertIsNotNone(aus["metriken"]["fw_profil_llr_pro_1000"])
        bew = aus["bewertung"]
        self.assertTrue(bew["verfuegbar"])
        self.assertTrue(all(isinstance(z["unsicher"], bool) for z in bew["kennzahlen"]))
        self.assertEqual(bew["ziel_p_mensch"], self.b["textsorten"]["hochschule"]["ziel_p_mensch"])
        self.assertEqual(bew["score_schwelle"], self.b["textsorten"]["hochschule"]["score_schwelle"])
        self.assertTrue(any("cluster" in z for z in bew["kennzahlen"] if z["bewertet"]))
        self.assertNotIn("fw_zaehlung", aus)

    def test_bewerte_rechnet_fw_nach(self):
        # Aufrufer ohne fw_profil (z. B. ältere Skripte): bewerte() ergänzt den Wert aus fw_zaehlung
        t = self.b["textsorten"]["hochschule"]
        e1 = analyse.analysiere_text(self.texte["k02"], self.muster)
        self.assertNotIn("fw_profil_llr_pro_1000", e1["metriken"])
        analyse.bewerte(e1, self.b)
        e2 = analyse.analysiere_text(self.texte["k02"], self.muster, fw_profil=t["fw_profil"])
        self.assertAlmostEqual(e1["metriken"]["fw_profil_llr_pro_1000"], e2["metriken"]["fw_profil_llr_pro_1000"], places=4)
        self.assertLess(e2["metriken"]["fw_profil_llr_pro_1000"], 0)  # KI-Funktionswörter


if __name__ == "__main__":
    unittest.main()
