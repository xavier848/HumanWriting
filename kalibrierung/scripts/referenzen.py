#!/usr/bin/env python3
"""Erzeugt die Referenzdateien der Skills aus den Kalibrierungsergebnissen.

  menschlich-schreiben/references/zielwerte.md  ← baselines.json
  menschlich-schreiben/references/ki-muster.md  ← ki_muster.json + ergebnisse/wortlisten.json
  text-analyse/references/kennzahlen.md         ← baselines.json (alle Kennzahlen, Korpus, Evaluation)

    python3 referenzen.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HIER, "..", ".."))
SKILLS = os.path.join(REPO, "plugins", "humanwriting-de", "skills")
sys.path.insert(0, os.path.join(SKILLS, "text-analyse", "scripts"))
import analyse  # noqa: E402

PROZENT = {k for k in analyse.NAMEN if k.startswith("anteil_")} | {"satzanfang_wiederholung", "satzanfang_top3_anteil"}

ERKLAERUNG = {
    "satzlaenge_mittel": "Durchschnittliche Zahl der Wörter pro Satz.",
    "satzlaenge_sd": "Standardabweichung der Satzlängen in Wörtern.",
    "satzlaenge_cv": "Standardabweichung geteilt durch Mittelwert – die längenunabhängige „Varianz“ der Satzlängen.",
    "satzlaenge_schiefe": "Asymmetrie der Satzlängen-Verteilung (positiv = langer Schwanz zu langen Sätzen).",
    "satzlaenge_dispersion": "Varianz geteilt durch Mittelwert (Dispersionsindex der Satzlängen).",
    "rhythmus_sprung_rel": "Mittlerer Längenunterschied zwischen aufeinanderfolgenden Sätzen, relativ zur Ø-Satzlänge.",
    "rhythmus_autokorrelation": "Korrelation der Länge eines Satzes mit der des nächsten (Lag 1).",
    "anteil_gleichfoermige_laeufe": "Anteil der Sätze, die in einer Dreierfolge fast gleich langer Sätze (±20 %) stehen.",
    "mattr_100": "Moving-Average Type-Token-Ratio über 100-Wort-Fenster: Anteil verschiedener Wortformen.",
    "mtld": "Measure of Textual Lexical Diversity (McCarthy & Jarvis 2010).",
    "yule_k": "Yules K: höher = mehr Wortwiederholung.",
    "nachbarsatz_ueberlappung": "Jaccard-Überlappung der Inhaltswortstämme benachbarter Sätze.",
    "anteil_saetze_mit_wortaufnahme": "Anteil der Sätze, die mindestens einen Inhaltswortstamm des Vorsatzes aufnehmen.",
    "menzerath_korrelation": "Korrelation zwischen Satzlänge (in Teilsätzen) und Teilsatzlänge (in Wörtern); Menzerath-Altmann-Gesetz: negativ.",
    "lix": "Lesbarkeitsindex nach Björnsson: Ø-Satzlänge + Prozent Wörter mit mehr als 6 Buchstaben.",
    "flesch_amstad": "Flesch-Reading-Ease, deutsche Anpassung nach Amstad: 180 − ASL − 58,5·ASW.",
    "wiener_sachtextformel": "1. Wiener Sachtextformel (Bamberger & Vanecek): Schulstufe, höher = schwerer.",
    "ki_muster_pro_1000": "Treffer der KI-Muster pro 1000 Token, gewichtet nach log2(KI-Rate / Mensch-Rate).",
}


def f(k, x):
    if x is None:
        return "–"
    if k in PROZENT:
        return f"{100 * x:.0f} %"
    if abs(x) >= 100:
        return f"{x:.0f}"
    if abs(x) >= 10:
        return f"{x:.1f}".replace(".", ",")
    return f"{x:.2f}".replace(".", ",")


def trenn(v):
    """AUROC richtungsunabhängig: 0,5 = trennt nicht, 1,0 = trennt perfekt."""
    return f"{max(v['auroc'], 1 - v['auroc']):.2f}".replace(".", ",")


def lade(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def zielwerte(b) -> str:
    t = b["textsorten"]["hochschule"]
    met = t["metriken"]
    k = b["korpus"]
    zeilen = [
        "# Zielwerte für deutsche Hochschultexte",
        "",
        "Automatisch erzeugt aus `text-analyse/data/baselines.json` (kalibrierung/scripts/referenzen.py). Nicht von Hand bearbeiten.",
        "",
        f"Grundlage: {k['mensch']['dokumente']} menschliche Hochschultexte vor 2022 ({k['mensch']['abschnitte']} Abschnitte à ~600–1300 Wörter) "
        f"und {k['ki']['dokumente']} KI-Texte zu denselben Themen ({k['ki']['abschnitte']} Abschnitte).",
        "",
        "**Zielbereich** = mittlere 50 % der menschlichen Abschnitte (P25–P75). **Trennschärfe** = AUROC, richtungsunabhängig (0,5 = trennt nicht, 1,0 = trennt perfekt).",
        "",
        "## Bewertete Kennzahlen (nach Trennschärfe)",
        "",
        "| Kennzahl | Zielbereich Mensch | Mensch Median | KI Median | Trennschärfe | Tendenz bei KI |",
        "|---|---|---|---|---|---|",
    ]
    bew = sorted([(kk, v) for kk, v in met.items() if v["bewertet"]], key=lambda kv: -kv[1]["trennschaerfe"])
    for kk, v in bew:
        m, ki = v["mensch"], v["ki"]
        tendenz = "zu niedrig" if v["richtung"] == "mensch_hoeher" else "zu hoch"
        zeilen.append(f"| {analyse.NAMEN.get(kk, kk)} | {f(kk, m['p25'])} – {f(kk, m['p75'])} | {f(kk, m['p50'])} | {f(kk, ki['p50'])} | "
                      f"{trenn(v)} | {tendenz} |")
    zeilen += ["", "## Was das fürs Schreiben heißt", ""]
    for kk, v in bew[:12]:
        m, ki = v["mensch"], v["ki"]
        richtung = "höher" if v["richtung"] == "mensch_hoeher" else "niedriger"
        zeilen.append(f"- **{analyse.NAMEN.get(kk, kk)}**: Menschen liegen typischerweise bei {f(kk, m['p25'])}–{f(kk, m['p75'])}, "
                      f"KI-Texte bei {f(kk, ki['p25'])}–{f(kk, ki['p75'])}. Beim Schreiben {richtung} ansetzen als der KI-Reflex."
                      + (f" {ERKLAERUNG[kk]}" if kk in ERKLAERUNG else ""))
    vert_m = t.get("satzlaengen_verteilung_mensch")
    if vert_m:
        zeilen += ["", "## Satzlängen-Verteilung (Anteil der Sätze je Klasse)", "", "| Wörter | Mensch | KI |", "|---|---|---|"]
        vert_k = t.get("satzlaengen_verteilung_ki", {})
        for klasse, anteil in vert_m.items():
            zeilen.append(f"| {klasse} | {round(100 * anteil)} % | {round(100 * vert_k.get(klasse, 0))} % |")
    return "\n".join(zeilen) + "\n"


def kimuster(mu, wl) -> str:
    zeilen = [
        "# KI-Muster: vermeiden und ersetzen",
        "",
        "Automatisch erzeugt aus `text-analyse/data/ki_muster.json` und `kalibrierung/ergebnisse/wortlisten.json`. Nicht von Hand bearbeiten.",
        "",
        "Raten = Treffer pro 1000 Token im menschlichen bzw. KI-Korpus. **Verhältnis** = wie viel häufiger KI das Muster nutzt. "
        "Muster mit Gewicht 0 sind in menschlichen Texten genauso häufig und werden nicht bestraft.",
        "",
        "Ein Muster nie durch ein Synonym des Musters ersetzen (aus „spielt eine zentrale Rolle“ wird nicht „nimmt eine Schlüsselposition ein“), sondern durch die konkrete Aussage.",
        "",
        "| Muster | Mensch | KI | Verhältnis | Gewicht | Stattdessen |",
        "|---|---|---|---|---|---|",
    ]
    for m in sorted(mu["muster"], key=lambda m: -m.get("verhaeltnis_ki_mensch", 1)):
        zeilen.append(f"| {m['label']} | {m.get('rate_mensch_pro_1000', '–')} | {m.get('rate_ki_pro_1000', '–')} | "
                      f"{m.get('verhaeltnis_ki_mensch', '–')} | {m.get('gewicht', '–')} | {m.get('ersatz', '')} |")
    if wl:
        zeilen += ["", "## Datenbasierte Wortliste: von KI überdurchschnittlich genutzt", "",
                   "Aus dem themengleichen Korpusvergleich (log-odds mit Dirichlet-Prior). Pro 1000 Wörter: KI vs. Mensch. "
                   "Themenwörter fallen durch das themengleiche Design weitgehend heraus; was bleibt, ist Stil.", ""]
        zeilen.append(", ".join(f"*{e['ngramm']}* ({e['ki_pro_1000']:.2f} vs {e['mensch_pro_1000']:.2f})" for e in wl["ki_typisch"][:120]))
        zeilen += ["", "## Datenbasierte Wortliste: von Menschen überdurchschnittlich genutzt", "",
                   "Diese Wörter und Wendungen sind in echten Hochschultexten häufiger als in KI-Texten. Sie dürfen (natürlich und passend) verwendet werden.", ""]
        zeilen.append(", ".join(f"*{e['ngramm']}* ({e['mensch_pro_1000']:.2f} vs {e['ki_pro_1000']:.2f})" for e in wl["mensch_typisch"][:120]))
    return "\n".join(zeilen) + "\n"


def kennzahlen(b) -> str:
    t = b["textsorten"]["hochschule"]
    met = t["metriken"]
    k = b["korpus"]
    ev = b.get("evaluation", {})
    zeilen = [
        "# Kennzahlen, Referenzkorpus und Güte",
        "",
        "Automatisch erzeugt aus `data/baselines.json` (kalibrierung/scripts/referenzen.py).",
        "",
        "## Referenzkorpus",
        "",
        f"- **Mensch:** {k['mensch']['dokumente']} Dokumente, {k['mensch']['abschnitte']} Abschnitte. Quellen: "
        + ", ".join(f"{q} ({n})" for q, n in k["mensch"]["quellen"].items())
        + ". Nur Texte bis einschließlich 2021 (sicher vor ChatGPT).",
        f"- **KI:** {k['ki']['dokumente']} Dokumente, {k['ki']['abschnitte']} Abschnitte. Quellen: "
        + ", ".join(f"{q} ({n})" for q, n in k["ki"]["quellen"].items())
        + ". Themengleich: Jeder KI-Text wurde aus einer inhaltlichen Gliederung eines menschlichen Auszugs geschrieben.",
        "",
        "## Güte auf zurückgehaltenen Dokumenten (Test-Split, 25 %)",
        "",
        "| Verfahren | AUROC | Genauigkeit | Median Mensch | Median KI |",
        "|---|---|---|---|---|",
    ]
    for name, key in (("Modell P(menschlich)", "modell_test"), ("Menschlichkeits-Score", "score_test")):
        if key in ev:
            e = ev[key]
            zeilen.append(f"| {name} | {e['auroc']} | {e['genauigkeit']} | {e['median_mensch']} | {e['median_ki']} |")
    zeilen += ["", f"Score-Schwelle (Mitte zwischen den Medianen): {t.get('score_schwelle', '–')}.",
               "", "## Alle Kennzahlen", "",
               "| Kennzahl | Mensch P10 / P25 / P50 / P75 / P90 | KI P25 / P50 / P75 | Trennschärfe | bewertet | Bedeutung |",
               "|---|---|---|---|---|---|"]
    for kk, v in sorted(met.items(), key=lambda kv: -kv[1]["trennschaerfe"]):
        m, ki = v["mensch"], v["ki"]
        zeilen.append(f"| {analyse.NAMEN.get(kk, kk)} | {f(kk, m['p10'])} / {f(kk, m['p25'])} / {f(kk, m['p50'])} / {f(kk, m['p75'])} / {f(kk, m['p90'])} | "
                      f"{f(kk, ki['p25'])} / {f(kk, ki['p50'])} / {f(kk, ki['p75'])} | {trenn(v)} | {'✔' if v['bewertet'] else ''} | {ERKLAERUNG.get(kk, '')} |")
    modell = t.get("modell", {})
    if modell.get("koeffizienten"):
        zeilen += ["", "## Modell", "", "Logistische Regression auf standardisierten Kennzahlen (positiv = spricht für menschlich):", ""]
        for kk, c in sorted(modell["koeffizienten"].items(), key=lambda kv: -abs(kv[1])):
            zeilen.append(f"- {analyse.NAMEN.get(kk, kk)}: {c:+.2f}")
    return "\n".join(zeilen) + "\n"


def _formen(eintrag: str) -> list[str]:
    """Suchformen eines Listeneintrags: Wendungen exakt, Wörter mit typischen Flexionsendungen."""
    kern = re.sub(r"\(.*?\)\s*", "", eintrag).replace("sich ", "").strip().lower()
    if " " in kern:
        return [kern]
    if kern.endswith("en") and len(kern) > 5:  # Verb: Infinitiv, Präsens, Partizip
        st = kern[:-2]
        return [kern, st + "t", st + "e", st + "st", st + "te", st + "ten", "ge" + st + "t", kern + "d"]
    return [kern, kern + "e", kern + "en", kern + "n", kern + "er", kern + "es", kern + "s", kern + "em"]


def persoenlicher_wortschatz(liste: dict) -> str | None:
    korpus = os.path.join(REPO, "kalibrierung", "korpus")
    texte = {g: [] for g in ("mensch", "ki")}
    for g in texte:
        for pfad in glob.glob(os.path.join(korpus, g, "*", "*.txt")):
            with open(pfad, encoding="utf-8") as fh:
                texte[g].append(fh.read().lower())
    if not texte["mensch"] or not texte["ki"]:
        return None
    gross = {g: " ".join(t) for g, t in texte.items()}
    n = {g: max(1, len(re.findall(r"[a-zäöüß]+", gross[g]))) for g in gross}
    zeilen = [
        "# Persönlicher Wortschatz",
        "",
        "Automatisch erzeugt aus `kalibrierung/persoenlich/wortschatz.json` (kalibrierung/scripts/referenzen.py). Nicht von Hand bearbeiten.",
        "",
        "Wörter und Wendungen aus Xaviers eigenen Nachrichten, die auch in Hausarbeiten passen. Verwende sie, **wo sie inhaltlich passen** – nie als Pflichtvokabel. "
        "Jedes Wort ist mit den Kalibrierungskorpora abgeglichen (Treffer pro 1000 Wörter, menschliche Hochschultexte vs. Claude-Texte):",
        "",
        "- ✅ **menschentypisch** (Menschen nutzen es mindestens 1,5× so oft wie Claude): bevorzugen",
        "- ⚪ **neutral**: normal verwenden",
        "- ⚠️ **eher KI-typisch** (Claude nutzt es mindestens 1,5× so oft): erlaubt, aber nicht häufen",
        "",
        "Seltene Wörter (unter 0,05 pro 1000 in beiden Korpora) sind statistisch unsicher und als neutral markiert.",
        "",
    ]
    for gruppe, woerter in liste["gruppen"].items():
        zeilen += [f"## {gruppe}", "", "| | Wort | Mensch | Claude |", "|---|---|---|---|"]
        for w in woerter:
            formen = _formen(w)
            muster = re.compile(r"\b(" + "|".join(re.escape(f) for f in formen) + r")\b")
            r = {g: 1000 * len(muster.findall(gross[g])) / n[g] for g in gross}
            verh = (r["ki"] + 0.02) / (r["mensch"] + 0.02)
            if max(r.values()) < 0.05:
                symbol = "⚪"
            elif verh >= 1.5:
                symbol = "⚠️"
            elif verh <= 1 / 1.5:
                symbol = "✅"
            else:
                symbol = "⚪"
            zeilen.append(f"| {symbol} | {w} | {r['mensch']:.2f} | {r['ki']:.2f} |".replace(".", ","))
        zeilen.append("")
    return "\n".join(zeilen) + "\n"


def main() -> int:
    b = lade(os.path.join(SKILLS, "text-analyse", "data", "baselines.json"))
    mu = lade(os.path.join(SKILLS, "text-analyse", "data", "ki_muster.json"))
    wl_pfad = os.path.join(REPO, "kalibrierung", "ergebnisse", "wortlisten.json")
    wl = lade(wl_pfad) if os.path.exists(wl_pfad) else None
    ausgaben = {
        os.path.join(SKILLS, "menschlich-schreiben", "references", "zielwerte.md"): zielwerte(b),
        os.path.join(SKILLS, "menschlich-schreiben", "references", "ki-muster.md"): kimuster(mu, wl),
        os.path.join(SKILLS, "text-analyse", "references", "kennzahlen.md"): kennzahlen(b),
    }
    wortschatz_pfad = os.path.join(REPO, "kalibrierung", "persoenlich", "wortschatz.json")
    if os.path.exists(wortschatz_pfad):
        inhalt = persoenlicher_wortschatz(lade(wortschatz_pfad))
        if inhalt:
            ausgaben[os.path.join(SKILLS, "menschlich-schreiben", "references", "persoenlicher-wortschatz.md")] = inhalt
    for pfad, inhalt in ausgaben.items():
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "w", encoding="utf-8") as fh:
            fh.write(inhalt)
        print("geschrieben:", os.path.relpath(pfad, REPO))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
