#!/usr/bin/env python3
"""Kalibrierung: berechnet Referenzwerte (baselines.json) aus menschlichen und KI-Korpora.

Schritte:
  1. Texte in vergleichbare Abschnitte (~600–1200 Wörter) zerlegen
  2. Für jeden Abschnitt alle Kennzahlen mit analyse.py messen  -> ergebnisse/features.csv
  3. Pro Kennzahl: Perzentile (Mensch/KI), Trennschärfe (AUROC), Richtung, Gewicht
  4. Logistisches Modell auf den trennschärfsten, wenig korrelierten Kennzahlen
  5. Prüfung auf zurückgehaltenen Dokumenten (Test-Split nach Dokument)
  6. Wort-/Phrasenlisten: was KI über- und was Menschen überdurchschnittlich nutzen
     (log-odds mit informativem Dirichlet-Prior, Monroe et al. 2008)
  7. Gewichte der KI-Muster aus den tatsächlichen Häufigkeiten

    python3 kalibriere.py [--korpus ../korpus] [--aus ../ergebnisse] [--baselines PFAD]
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HIER, "..", ".."))
SKILL_DATA = os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "data")
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
import analyse  # noqa: E402

# Kennzahlen, die nicht in Score/Modell eingehen (Längen-/Format-Artefakte oder Korpus-Unterschiede, die nichts
# mit Menschlichkeit zu tun haben)
NICHT_BEWERTEN = {
    "absaetze", "satzlaenge_max", "markdown_elemente", "listenpunkte", "ueberschriften_pro_1000",
    "zitate_pro_1000", "satzlaenge_median", "satzlaenge_p10", "satzlaenge_p90", "mattr_50",
    "ki_muster_pro_1000",  # wird nach Neugewichtung der Muster gesondert bewertet
}
HINWEISE = {
    "satzlaenge_cv": "Wie stark die Satzlängen schwanken. Menschen mischen kurze und lange Sätze stärker.",
    "rhythmus_sprung_rel": "Wie stark sich aufeinanderfolgende Sätze in der Länge unterscheiden.",
    "anteil_gleichfoermige_laeufe": "Anteil der Sätze in Dreierfolgen fast gleich langer Sätze.",
    "nachbarsatz_ueberlappung": "Menschen greifen Begriffe des Vorsatzes wieder auf, statt ständig Synonyme zu suchen.",
    "mattr_100": "Wortschatzvielfalt. KI-Text ist oft 'zu abwechslungsreich' (Synonym-Karussell).",
    "gedankenstrich_pro_1000": "Gedankenstriche (–) sind ein starkes KI-Signal.",
    "ki_muster_pro_1000": "Typische KI-Floskeln und -Konstruktionen, gewichtet nach Korpus-Häufigkeit.",
}


# ---------------------------------------------------------------------------
# Korpus laden und zerlegen
# ---------------------------------------------------------------------------

def lade_korpus(wurzel: str, gruppe: str) -> list[dict]:
    docs = []
    for meta_pfad in sorted(glob.glob(os.path.join(wurzel, gruppe, "*", "meta.jsonl"))):
        ordner = os.path.dirname(meta_pfad)
        with open(meta_pfad, encoding="utf-8") as f:
            for zeile in f:
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    meta = json.loads(zeile)
                except json.JSONDecodeError:
                    continue
                pfad = os.path.join(ordner, meta["id"] + ".txt")
                if not os.path.exists(pfad):
                    continue
                with open(pfad, encoding="utf-8") as tf:
                    text = tf.read()
                meta["gruppe"] = gruppe
                meta["quelle"] = meta.get("quelle") or os.path.basename(ordner)
                meta["text"] = text
                docs.append(meta)
    return docs


def zerlege(text: str, ziel=900, minimum=600, maximum=1300, max_abschnitte=3) -> list[str]:
    absaetze = [a.strip() for a in re.split(r"\n\s*\n", text) if a.strip()]
    stuecke, aktuell, n = [], [], 0
    for a in absaetze:
        w = len(a.split())
        if w > maximum:  # Riesenabsatz (Extraktionsfehler) überspringen
            continue
        if n + w > maximum and n >= minimum:
            stuecke.append("\n\n".join(aktuell))
            aktuell, n = [], 0
        aktuell.append(a)
        n += w
        if n >= ziel:
            stuecke.append("\n\n".join(aktuell))
            aktuell, n = [], 0
    if aktuell and n >= minimum:
        stuecke.append("\n\n".join(aktuell))
    if len(stuecke) <= max_abschnitte:
        return stuecke
    # gleichmäßig über das Dokument verteilt auswählen
    idx = sorted({round(i * (len(stuecke) - 1) / (max_abschnitte - 1)) for i in range(max_abschnitte)})
    return [stuecke[i] for i in idx]


def split_von(doc_id: str) -> str:
    h = int(hashlib.sha1(doc_id.encode()).hexdigest(), 16) % 100
    return "test" if h < 25 else "train"


# ---------------------------------------------------------------------------
# Statistik
# ---------------------------------------------------------------------------

def perz(xs, p):
    return analyse.perzentil(xs, p)


def auroc(pos, neg):
    """P(zufälliger Mensch-Wert > zufälliger KI-Wert), Bindungen = 0,5 (Mann-Whitney)."""
    if not pos or not neg:
        return 0.5
    alle = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    raenge = [0.0] * len(alle)
    i = 0
    while i < len(alle):
        j = i
        while j + 1 < len(alle) and alle[j + 1][0] == alle[i][0]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            raenge[k] = r
        i = j + 1
    r_pos = sum(r for r, (_, g) in zip(raenge, alle) if g == 1)
    u = r_pos - len(pos) * (len(pos) + 1) / 2
    return u / (len(pos) * len(neg))


def pearson(xs, ys):
    return analyse.korrelation(xs, ys)


def zusammenfassung(xs):
    return {
        "p10": round(perz(xs, 0.10), 4), "p25": round(perz(xs, 0.25), 4), "p50": round(perz(xs, 0.50), 4),
        "p75": round(perz(xs, 0.75), 4), "p90": round(perz(xs, 0.90), 4),
        "mittel": round(analyse.mittel(xs), 4), "sd": round(analyse.sd(xs), 4), "n": len(xs),
    }


def logreg(X, y, l2=0.5, schritte=4000, lr=0.1):
    """L2-regularisierte logistische Regression (Gradientenabstieg), Klassen balanciert."""
    n, d = len(X), len(X[0])
    w = [0.0] * d
    b = 0.0
    n1 = sum(y)
    n0 = n - n1
    gew = [(n / (2 * n1)) if yi == 1 else (n / (2 * n0)) for yi in y]
    for _ in range(schritte):
        gw = [0.0] * d
        gb = 0.0
        for xi, yi, gi in zip(X, y, gew):
            z = b + sum(wj * xj for wj, xj in zip(w, xi))
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            e = (p - yi) * gi
            gb += e
            for j in range(d):
                gw[j] += e * xi[j]
        for j in range(d):
            w[j] -= lr * (gw[j] / n + l2 * w[j] / n)
        b -= lr * gb / n
    return w, b


def vorhersage(w, b, x):
    z = b + sum(wj * xj for wj, xj in zip(w, x))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


# ---------------------------------------------------------------------------
# Wortlisten (log-odds mit informativem Dirichlet-Prior)
# ---------------------------------------------------------------------------

NGRAM_TOKEN = re.compile(r"[A-Za-zÄÖÜäöüß]+(?:-[A-Za-zÄÖÜäöüß]+)*|[,;:–—]")


def ngramme(text: str, n_max=3) -> tuple[Counter, int]:
    c = Counter()
    gesamt = 0
    for absatz in re.split(r"\n\s*\n", text):
        absatz = analyse.ZITAT_RE.sub("", absatz)
        for satz in analyse.zerlege_saetze(re.sub(r"\s+", " ", absatz)):
            toks = [t.lower() for t in NGRAM_TOKEN.findall(satz)]
            gesamt += sum(1 for t in toks if t[0].isalpha())
            for n in range(1, n_max + 1):
                for i in range(len(toks) - n + 1):
                    g = toks[i : i + n]
                    if n > 1 and (g[0] in ",;:" or g[-1] in ",;:"):
                        continue
                    c[" ".join(g)] += 1
    return c, gesamt


def log_odds(c_a: Counter, c_b: Counter, prior: Counter, alpha0: float, min_gesamt: int = 6):
    n_a, n_b = sum(c_a.values()), sum(c_b.values())
    prior_summe = max(1, sum(prior.values()))
    out = {}
    for w, gesamt in prior.items():
        if gesamt < min_gesamt:
            continue  # seltene N-Gramme können ohnehin nicht die Dokument-Mindestzahl erreichen
        a_w = gesamt * alpha0 / prior_summe + 0.01
        ya, yb = c_a[w], c_b[w]
        la = math.log((ya + a_w) / (n_a + alpha0 - ya - a_w))
        lb = math.log((yb + a_w) / (n_b + alpha0 - yb - a_w))
        var = 1 / (ya + a_w) + 1 / (yb + a_w)
        out[w] = (la - lb) / math.sqrt(var)
    return out


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--korpus", default=os.path.join(REPO, "kalibrierung", "korpus"))
    ap.add_argument("--aus", default=os.path.join(REPO, "kalibrierung", "ergebnisse"))
    ap.add_argument("--baselines", default=os.path.join(SKILL_DATA, "baselines.json"))
    ap.add_argument("--muster", default=os.path.join(SKILL_DATA, "ki_muster.json"))
    ap.add_argument("--max-abschnitte", type=int, default=3)
    args = ap.parse_args()
    os.makedirs(args.aus, exist_ok=True)

    mensch = lade_korpus(args.korpus, "mensch")
    ki = lade_korpus(args.korpus, "ki")
    print(f"Dokumente: Mensch {len(mensch)}, KI {len(ki)}", file=sys.stderr)
    if not mensch or not ki:
        print("Beide Korpora werden benötigt.", file=sys.stderr)
        return 1

    # Muster ohne Gewichtung (alle 1.0) laden, damit die Neugewichtung nicht zirkulär ist
    muster_roh = analyse.lade_muster(args.muster)
    for mu in muster_roh:
        mu["gewicht"] = 1.0

    zeilen = []
    treffer_pro_abschnitt = []
    muster_zaehl = {"mensch": Counter(), "ki": Counter()}
    muster_docs = {"mensch": defaultdict(set), "ki": defaultdict(set)}
    token_summe = {"mensch": 0, "ki": 0}
    satzlaengen = {"mensch": [], "ki": []}
    ngr = {"mensch": Counter(), "ki": Counter()}
    ngr_docs = {"mensch": defaultdict(set), "ki": defaultdict(set)}
    for doc in mensch + ki:
        g = doc["gruppe"]
        # Split nach Thema: das KI-Gegenstück eines menschlichen Dokuments landet im selben Split
        split = split_von(doc.get("basis_id") or doc["id"])
        abschnitte = zerlege(doc["text"], max_abschnitte=args.max_abschnitte) if g == "mensch" else (zerlege(doc["text"], max_abschnitte=1) or [doc["text"]])
        for k, ab in enumerate(abschnitte):
            erg = analyse.analysiere_text(ab, muster_roh)
            if erg["info"]["woerter"] < 300 or erg["info"]["saetze"] < 12:
                continue
            zeile = {"gruppe": g, "quelle": doc["quelle"], "doc_id": doc["id"], "abschnitt": k, "split": split,
                     "woerter": erg["info"]["woerter"], **erg["metriken"]}
            treffer_pro_abschnitt.append((Counter(t["muster"] for t in erg["muster_treffer"]), erg["info"]["token"]))
            zeilen.append(zeile)
            if split == "train":
                satzlaengen[g].extend(erg["info"]["satzlaengen"])
                token_summe[g] += erg["info"]["token"]
                for t in erg["muster_treffer"]:
                    muster_zaehl[g][t["muster"]] += 1
                    muster_docs[g][t["muster"]].add(doc["id"])
                c, _ = ngramme(ab)
                ngr[g].update(c)
                for w in c:
                    ngr_docs[g][w].add(doc["id"])

    train = [z for z in zeilen if z["split"] == "train"]
    test = [z for z in zeilen if z["split"] == "test"]
    print(f"Abschnitte: train {len(train)} (Mensch {sum(z['gruppe']=='mensch' for z in train)}, KI {sum(z['gruppe']=='ki' for z in train)}), "
          f"test {len(test)}", file=sys.stderr)

    # --- Muster neu gewichten -------------------------------------------------
    with open(args.muster, encoding="utf-8") as f:
        muster_json = json.load(f)
    muster_bericht = []
    for mu in muster_json["muster"]:
        r_m = 1000 * muster_zaehl["mensch"][mu["id"]] / max(1, token_summe["mensch"])
        r_k = 1000 * muster_zaehl["ki"][mu["id"]] / max(1, token_summe["ki"])
        verh = (r_k + 0.02) / (r_m + 0.02)
        gewicht = round(max(0.0, min(3.0, math.log2(verh))), 2) if verh >= 1.25 and len(muster_docs["ki"][mu["id"]]) >= 3 else 0.0
        mu["gewicht"] = gewicht
        mu["rate_mensch_pro_1000"] = round(r_m, 3)
        mu["rate_ki_pro_1000"] = round(r_k, 3)
        mu["verhaeltnis_ki_mensch"] = round(verh, 2)
        muster_bericht.append((mu["id"], mu["label"], r_m, r_k, verh, gewicht))
    muster_json["version"] = "kalibriert"
    muster_json["kalibrierung"] = {"token_mensch": token_summe["mensch"], "token_ki": token_summe["ki"]}
    with open(args.muster, "w", encoding="utf-8") as f:
        json.dump(muster_json, f, ensure_ascii=False, indent=1)
    # ki_muster_pro_1000 mit den neuen Gewichten aus den gespeicherten Treffern nachberechnen
    gew = {mu["id"]: mu["gewicht"] for mu in muster_json["muster"]}
    for z, (treffer, tok) in zip(zeilen, treffer_pro_abschnitt):
        z["ki_muster_pro_1000"] = round(1000 * sum(gew.get(mid, 0) * n for mid, n in treffer.items()) / max(1, tok), 4)

    keys = [k for k in zeilen[0] if k not in ("gruppe", "quelle", "doc_id", "abschnitt", "split", "woerter")]
    with open(os.path.join(args.aus, "features.csv"), "w", newline="", encoding="utf-8") as f:
        wtr = csv.DictWriter(f, fieldnames=list(zeilen[0].keys()))
        wtr.writeheader()
        wtr.writerows(zeilen)

    # --- Kennzahlen bewerten --------------------------------------------------
    metriken = {}
    for k in keys:
        hm = [z[k] for z in train if z["gruppe"] == "mensch"]
        hk = [z[k] for z in train if z["gruppe"] == "ki"]
        a = auroc(hm, hk)
        trenn = abs(a - 0.5) * 2
        bewertet = k not in NICHT_BEWERTEN and trenn >= 0.3 or k == "ki_muster_pro_1000" and trenn >= 0.3
        metriken[k] = {
            "mensch": zusammenfassung(hm),
            "ki": zusammenfassung(hk),
            "auroc": round(a, 3),
            "richtung": "mensch_hoeher" if a > 0.5 else "ki_hoeher",
            "trennschaerfe": round(trenn, 3),
            "gewicht": round(trenn, 3) if bewertet else 0.0,
            "bewertet": bool(bewertet),
            "hinweis": HINWEISE.get(k, ""),
        }

    # --- Modell: trennschärfste, wenig korrelierte Kennzahlen ----------------
    kandidaten = sorted([k for k, v in metriken.items() if v["bewertet"]], key=lambda k: -metriken[k]["trennschaerfe"])
    gewaehlt = []
    for k in kandidaten:
        xs = [z[k] for z in train]
        if all(abs(pearson(xs, [z[g] for z in train])) < 0.8 for g in gewaehlt):
            gewaehlt.append(k)
        if len(gewaehlt) >= 12:
            break
    mu_ = {k: analyse.mittel([z[k] for z in train]) for k in gewaehlt}
    sd_ = {k: (analyse.sd([z[k] for z in train]) or 1.0) for k in gewaehlt}
    X = [[(z[k] - mu_[k]) / sd_[k] for k in gewaehlt] for z in train]
    y = [1 if z["gruppe"] == "mensch" else 0 for z in train]
    w, b = logreg(X, y) if gewaehlt else ([], 0.0)

    def p_mensch(z):
        return vorhersage(w, b, [(z[k] - mu_[k]) / sd_[k] for k in gewaehlt])

    def score(z):
        gs = gp = 0.0
        for k, v in metriken.items():
            if not v["bewertet"]:
                continue
            m = v["mensch"]
            st = 1.0 if m["p25"] <= z[k] <= m["p75"] else 0.5 if m["p10"] <= z[k] <= m["p90"] else 0.0
            gs += v["gewicht"]
            gp += v["gewicht"] * st
        return 100 * gp / gs if gs else 0

    def evaluiere(daten, fn, schwelle):
        pos = [fn(z) for z in daten if z["gruppe"] == "mensch"]
        neg = [fn(z) for z in daten if z["gruppe"] == "ki"]
        richtig = sum(v >= schwelle for v in pos) + sum(v < schwelle for v in neg)
        return {"auroc": round(auroc(pos, neg), 3), "genauigkeit": round(richtig / max(1, len(pos) + len(neg)), 3),
                "n_mensch": len(pos), "n_ki": len(neg),
                "median_mensch": round(perz(pos, 0.5), 3), "median_ki": round(perz(neg, 0.5), 3)}

    # Score-Schwelle: Mitte zwischen den Medianen auf train
    s_m = perz([score(z) for z in train if z["gruppe"] == "mensch"], 0.5)
    s_k = perz([score(z) for z in train if z["gruppe"] == "ki"], 0.5)
    schwelle_score = (s_m + s_k) / 2
    eval_ = {
        "modell_train": evaluiere(train, p_mensch, 0.5),
        "modell_test": evaluiere(test, p_mensch, 0.5),
        "score_train": evaluiere(train, score, schwelle_score),
        "score_test": evaluiere(test, score, schwelle_score),
        "score_schwelle": round(schwelle_score, 1),
    }

    baselines = {
        "version": "1",
        "beschreibung": "Referenzwerte für analyse.py, berechnet von kalibrierung/scripts/kalibriere.py. "
                        "Zielbereich = mittlere 50 % der menschlichen Abschnitte (P25–P75).",
        "korpus": {
            "mensch": {"dokumente": len(mensch), "abschnitte": sum(z["gruppe"] == "mensch" for z in zeilen),
                       "quellen": dict(Counter(d["quelle"] for d in mensch))},
            "ki": {"dokumente": len(ki), "abschnitte": sum(z["gruppe"] == "ki" for z in zeilen),
                   "quellen": dict(Counter(d["quelle"] for d in ki))},
        },
        "evaluation": eval_,
        "textsorten": {
            "hochschule": {
                "beschreibung": "Formelle Hochschularbeiten: Hausarbeit, Bachelor-/Masterarbeit, Seminar- und Aufgabenbearbeitungen.",
                "metriken": metriken,
                "modell": {"koeffizienten": {k: round(c, 4) for k, c in zip(gewaehlt, w)}, "intercept": round(b, 4),
                           "mittel": {k: round(v, 5) for k, v in mu_.items()}, "sd": {k: round(v, 5) for k, v in sd_.items()}},
                "score_schwelle": round(schwelle_score, 1),
                "satzlaengen_verteilung_mensch": analyse.verteilung(satzlaengen["mensch"]),
                "satzlaengen_verteilung_ki": analyse.verteilung(satzlaengen["ki"]),
            }
        },
    }
    with open(args.baselines, "w", encoding="utf-8") as f:
        json.dump(baselines, f, ensure_ascii=False, indent=1)

    # --- Wortlisten -------------------------------------------------------------
    prior = ngr["mensch"] + ngr["ki"]
    z_scores = log_odds(ngr["ki"], ngr["mensch"], prior, alpha0=1000.0)
    n_m_tok = max(1, token_summe["mensch"])
    n_k_tok = max(1, token_summe["ki"])

    def liste(richtung, n=150):
        out = []
        for w_, zv in sorted(z_scores.items(), key=lambda kv: -kv[1] if richtung == "ki" else kv[1]):
            g = "ki" if richtung == "ki" else "mensch"
            if len(ngr_docs[g][w_]) < 4 or ngr[g][w_] < 6:
                continue
            if not re.search(r"[a-zäöüß]", w_):
                continue
            out.append({"ngramm": w_, "z": round(zv, 2), "ki_pro_1000": round(1000 * ngr["ki"][w_] / n_k_tok, 3),
                        "mensch_pro_1000": round(1000 * ngr["mensch"][w_] / n_m_tok, 3),
                        "docs_ki": len(ngr_docs["ki"][w_]), "docs_mensch": len(ngr_docs["mensch"][w_])})
            if len(out) >= n:
                break
        return out

    wortlisten = {"ki_typisch": liste("ki"), "mensch_typisch": liste("mensch"),
                  "methode": "log-odds ratio mit informativem Dirichlet-Prior (Monroe, Colaresi & Quinn 2008), nur Train-Split, min. 4 Dokumente"}
    with open(os.path.join(args.aus, "wortlisten.json"), "w", encoding="utf-8") as f:
        json.dump(wortlisten, f, ensure_ascii=False, indent=1)

    # --- Bericht ----------------------------------------------------------------
    zeilen_md = ["# Kalibrierungsbericht", ""]
    zeilen_md.append(f"Mensch: {len(mensch)} Dokumente / {baselines['korpus']['mensch']['abschnitte']} Abschnitte · "
                     f"KI: {len(ki)} Dokumente / {baselines['korpus']['ki']['abschnitte']} Abschnitte")
    zeilen_md.append("")
    zeilen_md.append("## Prüfung auf zurückgehaltenen Dokumenten (Test-Split)")
    zeilen_md.append("")
    zeilen_md.append("| | AUROC | Genauigkeit | Median Mensch | Median KI |")
    zeilen_md.append("|---|---|---|---|---|")
    for name, key in (("Modell P(menschlich)", "modell_test"), ("Menschlichkeits-Score", "score_test")):
        e = eval_[key]
        zeilen_md.append(f"| {name} | {e['auroc']} | {e['genauigkeit']} | {e['median_mensch']} | {e['median_ki']} |")
    zeilen_md.append("")
    zeilen_md.append("## Kennzahlen nach Trennschärfe")
    zeilen_md.append("")
    zeilen_md.append("| Kennzahl | AUROC | Mensch P25–P50–P75 | KI P25–P50–P75 | bewertet |")
    zeilen_md.append("|---|---|---|---|---|")
    for k, v in sorted(metriken.items(), key=lambda kv: -kv[1]["trennschaerfe"]):
        mm, kk = v["mensch"], v["ki"]
        zeilen_md.append(f"| {analyse.NAMEN.get(k, k)} | {v['auroc']} | {mm['p25']:.3g} – {mm['p50']:.3g} – {mm['p75']:.3g} | "
                         f"{kk['p25']:.3g} – {kk['p50']:.3g} – {kk['p75']:.3g} | {'✔' if v['bewertet'] else ''} |")
    zeilen_md.append("")
    zeilen_md.append(f"Modell-Kennzahlen: {', '.join(gewaehlt)}")
    zeilen_md.append("")
    zeilen_md.append("## KI-Muster (Häufigkeit pro 1000 Token)")
    zeilen_md.append("")
    zeilen_md.append("| Muster | Mensch | KI | Verhältnis | Gewicht |")
    zeilen_md.append("|---|---|---|---|---|")
    for mid, label, r_m, r_k, verh, g in sorted(muster_bericht, key=lambda x: -x[4]):
        zeilen_md.append(f"| {label} | {r_m:.3f} | {r_k:.3f} | {verh:.2f} | {g} |")
    zeilen_md.append("")
    zeilen_md.append("## Wörter/Phrasen, die KI überdurchschnittlich nutzt (Top 60)")
    zeilen_md.append("")
    zeilen_md.append(", ".join(f"{e['ngramm']} ({e['ki_pro_1000']:.2f} vs {e['mensch_pro_1000']:.2f})" for e in wortlisten["ki_typisch"][:60]))
    zeilen_md.append("")
    zeilen_md.append("## Wörter/Phrasen, die Menschen überdurchschnittlich nutzen (Top 60)")
    zeilen_md.append("")
    zeilen_md.append(", ".join(f"{e['ngramm']} ({e['mensch_pro_1000']:.2f} vs {e['ki_pro_1000']:.2f})" for e in wortlisten["mensch_typisch"][:60]))
    with open(os.path.join(args.aus, "bericht.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(zeilen_md) + "\n")
    print(json.dumps(eval_, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
