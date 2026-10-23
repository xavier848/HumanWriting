#!/usr/bin/env python3
"""Erzeugt die Referenzdateien der Skills aus den Kalibrierungsergebnissen.

  menschlich-schreiben/references/zielwerte.md  ← baselines.json
  menschlich-schreiben/references/ki-muster.md  ← ki_muster.json + ergebnisse/wortlisten.json (Wortliste geteilt in
                                                   „nicht häufen“ und „nur Diagnose“; Nomen aus der Großschreibung im Korpus)
  text-analyse/references/kennzahlen.md         ← baselines.json (alle Kennzahlen, Korpus, Evaluation)

    python3 referenzen.py                          # schreibt in die Skill-References
    python3 referenzen.py --baselines B --muster M --wortlisten W --aus ORDNER   # Probelauf in einen Arbeitsordner
"""
from __future__ import annotations

import argparse
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
    "rhythmus_r1_log": "Ob lange und kurze Sätze in Phasen kommen (positiv, eher menschlich) oder sich streng abwechseln "
                       "(negativ): Lag-1-Autokorrelation der log-Satzlängen, um 1/n korrigiert (0 = Zufallsreihenfolge). "
                       "Ab 30 Sätzen bewertet.",
    "anteil_gleichfoermige_laeufe": "Anteil der Sätze, die in einer Dreierfolge fast gleich langer Sätze (±20 %) stehen.",
    "mattr_100": "Moving-Average Type-Token-Ratio über 100-Wort-Fenster: Anteil verschiedener Wortformen.",
    "mtld": "Measure of Textual Lexical Diversity (McCarthy & Jarvis 2010).",
    "yule_k": "Yules K: höher = mehr Wortwiederholung.",
    "nachbarsatz_ueberlappung": "Jaccard-Überlappung der Inhaltswortstämme benachbarter Sätze.",
    "anteil_saetze_mit_wortaufnahme": "Anteil der Sätze, die mindestens einen Inhaltswortstamm des Vorsatzes aufnehmen.",
    "menzerath_korrelation": "Korrelation zwischen Teilsatzzahl und Teilsatzlänge; misst vor allem die Gleichförmigkeit der Satzlängen, kein Menzerath-Befund (nicht bewertet).",
    "fw_profil_llr_pro_1000": "Wie menschentypisch die 40 häufigsten Funktionswörter verteilt sind (Menschen: mehr „es“, „wie“, "
                              "„auch“, „durch“; KI: mehr „als“, „sich“, „dass“), als Log-Likelihood-Quotient pro 1000 Wörter; "
                              "> 0 = eher menschlich. Nur im Modell, kein Schreibziel: keine Einzelwörter einstreuen.",
    "satzklammer_mittel": "Mittlere Zahl der Wörter zwischen finitem Hilfs-/Modalverb und Partizip/Infinitiv, also wie weit "
                          "die Satzklammer gespannt ist („wurde in der Befragung erstmals … erhoben“). Bewertet ab 5 Klammern.",
    "teilsatz_verhaeltnis_21": "Sätze mit genau zwei Teilsätzen im Verhältnis zu Sätzen mit einem Teilsatz (geglättet); "
                               "hoch = viele gleich gebaute Zweier-Gefüge (typisch KI).",
    "konnektoren_pro_1000": "Satzverknüpfer wie „zudem“, „somit“, „folglich“, „jedoch“ in allen Satzstellungen pro 1000 Token.",
    "abkuerzungen_pro_1000": "Übliche Stil-Abkürzungen (z. B., bzw., d. h., u. a. …) pro 1000 Token; Verweis-Abkürzungen "
                             "(vgl., S., ebd.) zählen nicht.",
    "nominalketten_pro_100": "Ketten aus mindestens zwei Substantiven, verbunden über Genitiv oder „von“ („die Analyse der "
                             "Daten der Befragung“), pro 100 Wörter.",
    "silben_q21": "Zahl der Zweisilber im Verhältnis zu den Einsilbern (geglättet); höher = mehr Zweisilber.",
    "mattr_klumpung_100": "MATTR-100 geteilt durch die Zufallserwartung (Rarefaktion): < 1 = Begriffe kehren lokal gebündelt "
                          "wieder (eher menschlich), ≈ 1 = Wortwahl gleichmäßig gestreut. Gemessen in 800-Wort-Fenstern.",
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


def null_normal(met: dict) -> list[str]:
    """Bewertete Kennzahlen mit Zielbereich, bei denen der menschliche P10 genau 0 ist: 0 ist dort menschlich normal."""
    return [kk for kk, v in met.items() if v["bewertet"] and abs(v["mensch"].get("p10") or 0) < 1e-9
            and (v["mensch"].get("p10") is not None)]


def _null_satz(kk: str) -> str:
    if kk == "ki_muster_pro_1000":
        return "0 Floskeln ist menschlich normal (P10 = 0)"
    return "0 ist menschlich normal (P10 = 0)"


def zielwerte(b) -> str:
    t = b["textsorten"]["hochschule"]
    met = t["metriken"]
    k = b["korpus"]
    null = set(null_normal(met))
    zeilen = [
        "# Zielwerte für deutsche Hochschultexte",
        "",
        "Automatisch erzeugt aus `text-analyse/data/baselines.json` (kalibrierung/scripts/referenzen.py). Nicht von Hand bearbeiten.",
        "",
        f"Grundlage: {k['mensch']['dokumente']} menschliche Hochschultexte vor 2022 ({k['mensch']['abschnitte']} Abschnitte à "
        f"{k.get('abschnittslaenge', '~600–1300')} Wörter) "
        f"und {k['ki']['dokumente']} KI-Texte zu denselben Themen ({k['ki']['abschnitte']} Abschnitte).",
        "",
        "**Zielbereich** = mittlere 50 % der menschlichen Abschnitte (P25–P75, jedes Dokument zählt gleich). **Band** = P10–P90 "
        "der menschlichen Abschnitte: Auch Werte zwischen Band- und Zielbereichsgrenze sind menschlich. **Trennschärfe** = AUROC, "
        "richtungsunabhängig (0,5 = trennt nicht, 1,0 = trennt perfekt).",
        "",
        "## Bewertete Kennzahlen (nach Trennschärfe)",
        "",
        "| Kennzahl | Zielbereich Mensch | Band Mensch (P10–P90) | Mensch Median | KI Median | Trennschärfe | Tendenz bei KI |",
        "|---|---|---|---|---|---|---|",
    ]
    bew = sorted([(kk, v) for kk, v in met.items() if v["bewertet"]], key=lambda kv: -kv[1]["trennschaerfe"])
    for kk, v in bew:
        m, ki = v["mensch"], v["ki"]
        tendenz = "zu niedrig" if v["richtung"] == "mensch_hoeher" else "zu hoch"
        band = f"{f(kk, m.get('p10'))} – {f(kk, m.get('p90'))}" + (" (0 normal)" if kk in null else "")
        zeilen.append(f"| {analyse.NAMEN.get(kk, kk)} | {f(kk, m['p25'])} – {f(kk, m['p75'])} | {band} | {f(kk, m['p50'])} | "
                      f"{f(kk, ki['p50'])} | {trenn(v)} | {tendenz} |")
    if null:
        zeilen += ["", "## 0 ist menschlich normal", "",
                   "Bei diesen Kennzahlen hat mindestens jeder zehnte menschliche Abschnitt den Wert 0 (P10 = 0). 0 ist dort kein "
                   "Fehler, auch wenn der Wert unter dem Zielbereich liegt und die Analyse ihn gelb färbt: nie Vorkommen "
                   "einbauen, nur um den Zielbereich zu treffen.", ""]
        for kk, v in bew:
            if kk not in null:
                continue
            m = v["mensch"]
            seite = ("weniger ist die menschliche Seite" if v["richtung"] == "ki_hoeher"
                     else "auch KI-Texte liegen oft niedrig, ein einzelner Abschnitt mit 0 ist trotzdem unauffällig")
            zeilen.append(f"- **{analyse.NAMEN.get(kk, kk)}**: {_null_satz(kk)}; Zielbereich {f(kk, m['p25'])}–{f(kk, m['p75'])}, "
                          f"{seite}.")
    kappen = (t.get("modell") or {}).get("kappen") or {}
    if kappen or t.get("ziel_score_ki") is not None:
        zeilen += ["", "## Menschlicher als typisch", "",
                   "Abweichungen vom Zielbereich auf der der KI abgewandten Seite (z. B. weniger Floskeln, mehr Wortaufnahme als "
                   "P75) sind menschlich, solange sie im Band bleiben."
                   + (f" Der einseitige Score (Ziel {_k(t['ziel_score_ki'], 1)}) zählt sie wie grün." if t.get("ziel_score_ki")
                      is not None else "")
                   + (" Über das Band hinaus bringt nichts mehr: Das Modell kappt jedes Merkmal auf dieser Seite am menschlichen "
                      "P10 bzw. P90. Nicht übertreiben, sondern im Band bleiben." if kappen else "")]
    tendenz_k = sorted([(kk, v) for kk, v in met.items() if v.get("nur_modell")], key=lambda kv: -kv[1]["trennschaerfe"])
    if tendenz_k:
        zeilen += ["", "## Nur als Tendenz (Modell, kein Zielbereich)", "",
                   "Diese Kennzahlen gehen nur in die Modell-Einschätzung (P(menschlich)) ein, nicht in den Score, und haben "
                   "deshalb keinen Zielbereich. Gezielt auf sie hinzuschreiben (z. B. bestimmte Funktionswörter einstreuen) "
                   "verfälscht die Messung, statt den Text menschlicher zu machen; sie zeigen nur die Richtung.", "",
                   "| Kennzahl | Mensch Median | KI Median | Trennschärfe | Tendenz bei KI | Bedeutung |", "|---|---|---|---|---|---|"]
        for kk, v in tendenz_k:
            tendenz = "niedriger" if v["richtung"] == "mensch_hoeher" else "höher"
            zeilen.append(f"| {analyse.NAMEN.get(kk, kk)} | {f(kk, v['mensch']['p50'])} | {f(kk, v['ki']['p50'])} | {trenn(v)} | "
                          f"{tendenz} | {ERKLAERUNG.get(kk, '')} |")
    zeilen += ["", "## Was das fürs Schreiben heißt", ""]
    for kk, v in bew[:12]:
        m, ki = v["mensch"], v["ki"]
        richtung = "höher" if v["richtung"] == "mensch_hoeher" else "niedriger"
        zeilen.append(f"- **{analyse.NAMEN.get(kk, kk)}**: Menschen liegen typischerweise bei {f(kk, m['p25'])}–{f(kk, m['p75'])}, "
                      f"KI-Texte bei {f(kk, ki['p25'])}–{f(kk, ki['p75'])}. Beim Schreiben {richtung} ansetzen als der KI-Reflex."
                      + (f" {_null_satz(kk)}." if kk in null else "")
                      + (f" {ERKLAERUNG[kk]}" if kk in ERKLAERUNG else ""))
    vert_m = t.get("satzlaengen_verteilung_mensch")
    if vert_m:
        zeilen += ["", "## Satzlängen-Verteilung (Anteil der Sätze je Klasse)", "", "| Wörter | Mensch | KI |", "|---|---|---|"]
        vert_k = t.get("satzlaengen_verteilung_ki", {})
        for klasse, anteil in vert_m.items():
            zeilen.append(f"| {klasse} | {round(100 * anteil)} % | {round(100 * vert_k.get(klasse, 0))} % |")
    return "\n".join(zeilen) + "\n"


# --- Wortliste in ki-muster.md: „nicht häufen“ vs. „nur Diagnose“ -------------------------------------------------------
HAEUFEN_AB = 2.5          # geglättetes Verhältnis KI/Mensch, ab dem eine Wendung unter „nicht häufen“ steht
NOMEN_ANTEIL = 0.6        # Anteil großgeschriebener Vorkommen mitten im Satz, ab dem ein Wort als Nomen gilt
BRUCHSTUECK = 0.9         # Teil-n-Gramm fällt weg, wenn eine längere Wendung mindestens 90 % seiner Treffer hat
PRAEPOSITIONEN = {"in", "im", "vor", "für", "auf", "an", "am", "mit", "nach", "aus", "bei", "zu", "zum", "zur", "von", "vom",
                  "über", "unter", "durch", "gegen", "ohne", "um"}


def nomen_im_korpus(woerter: set, korpus: str | None = None) -> set | None:
    """Wörter, die im Korpus mitten im Satz überwiegend großgeschrieben stehen (Nomen: „befragten“ → „die Befragten“).
    None, wenn kein Korpus vorliegt (dann entscheidet nur das Verhältnis)."""
    korpus = korpus or os.path.join(REPO, "kalibrierung", "korpus")
    pfade = sorted(glob.glob(os.path.join(korpus, "*", "*", "*.txt")))
    if not pfade:
        return None
    gross, klein = {}, {}
    tok_re = re.compile(r"[A-Za-zÄÖÜäöüß]+|[.!?:]|\n\s*\n")
    for pfad in pfade:
        with open(pfad, encoding="utf-8") as fh:
            text = fh.read()
        anfang = True
        for tok in tok_re.findall(text):
            if tok[0] in ".!?:\n":
                anfang = True
                continue
            low = tok.lower()
            if not anfang and low in woerter:
                ziel = gross if tok[0].isupper() else klein
                ziel[low] = ziel.get(low, 0) + 1
            anfang = False
    return {w for w in woerter if gross.get(w, 0) + klein.get(w, 0) >= 5
            and gross.get(w, 0) >= NOMEN_ANTEIL * (gross.get(w, 0) + klein.get(w, 0))}


def _verh(e: dict) -> float:
    return (e["ki_pro_1000"] + 0.02) / (e["mensch_pro_1000"] + 0.02)


def wortliste_teilen(eintraege: list[dict], nomen: set | None) -> tuple[list[dict], list[dict]]:
    """KI-typische Wörter/Wendungen → (nicht häufen, nur Diagnose).

    - nicht häufen: Verhältnis ≥ HAEUFEN_AB ohne Themen-/Personenwort (zugleich, lässt sich, auf diese Weise, hinzu
      kommt, sodass, ergibt sich); Wendungen mit Präposition vorn („in der Regel“) zählen als Wendung, auch mit Nomen
    - nur Diagnose: Funktionswörter mit kleinerem Verhältnis (als, sich, die, ein) und alles mit Nomen (befragten,
      Befund, „vgl. Abb.“)
    Bruchstücke längerer Wendungen mit fast gleicher Häufigkeit („diese weise“ neben „auf diese weise“) fallen weg."""
    def toks(e):
        return [x for x in e["ngramm"].split() if re.match(r"[a-zäöüß]", x)]

    behalten = []
    for e in eintraege:
        t = toks(e)
        teil = any(len(toks(g)) > len(t) and g["ki_pro_1000"] >= BRUCHSTUECK * e["ki_pro_1000"]
                   and any(toks(g)[i:i + len(t)] == t for i in range(len(toks(g)) - len(t) + 1)) for g in eintraege)
        if not teil:
            behalten.append(e)
    haeufen, diagnose = [], []
    for e in behalten:
        t = toks(e)
        inhalt = [x for x in t if x not in analyse.FUNKTIONSWOERTER]
        wendung = len(t) > 1 and t[0] in PRAEPOSITIONEN
        thema = bool(nomen) and not wendung and any(x in nomen for x in inhalt)
        # gerundet wie angezeigt („2,5×“), damit Liste und Schwelle zusammenpassen
        (diagnose if thema or round(_verh(e), 1) < HAEUFEN_AB else haeufen).append(e)
    return haeufen, diagnose


def _wl_eintrag(e: dict) -> str:
    return f"*{e['ngramm']}* ({e['ki_pro_1000']:.2f} vs {e['mensch_pro_1000']:.2f}, {_verh(e):.1f}×)"


def kimuster(mu, wl, nomen: set | None = None) -> str:
    """nomen: Nomen der Wortliste (nomen_im_korpus); None = nur nach Verhältnis teilen."""
    zeilen = [
        "# KI-Muster: vermeiden und ersetzen",
        "",
        "Automatisch erzeugt aus `text-analyse/data/ki_muster.json` und `kalibrierung/ergebnisse/wortlisten.json`. Nicht von Hand bearbeiten.",
        "",
        "Raten = Treffer pro 1000 Token im menschlichen bzw. KI-Korpus. **Verhältnis** = wie viel häufiger KI das Muster nutzt. "
        "Muster mit Gewicht 0 sind in menschlichen Texten genauso häufig und werden nicht bestraft. Null Treffer ist menschlich "
        "normal: nie Floskeln einbauen, um eine Kennzahl zu treffen.",
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
        haeufen, diagnose = wortliste_teilen(wl["ki_typisch"][:150], nomen)
        zeilen += ["", "## Datenbasierte Wortliste: von KI überdurchschnittlich genutzt", "",
                   "Aus dem themengleichen Korpusvergleich (log-odds mit Dirichlet-Prior). Pro 1000 Wörter: KI vs. Mensch, dazu "
                   "das Verhältnis. Die Liste ist zweigeteilt: Nur die erste Gruppe betrifft das Schreiben.", "",
                   "### Phrasen, die man nicht häufen sollte", "",
                   f"Wendungen, die KI mindestens {str(HAEUFEN_AB).replace('.', ',')}-mal so oft nutzt wie Menschen (nach "
                   "Verhältnis). Einzeln erlaubt, aber nicht mehrfach im selben Abschnitt; nicht durch ein Synonym ersetzen, "
                   "sondern den Satz anders bauen.", ""]
        zeilen.append(", ".join(_wl_eintrag(e) for e in sorted(haeufen, key=lambda e: -_verh(e))))
        zeilen += ["", "### Nur Diagnose, nicht meiden", "",
                   "Funktionswörter, die KI nur etwas häufiger nutzt (als, sich, die, ein), sowie Themen- und Personenwörter "
                   "(z. B. „Befragte“). Sie zeigen, worin sich KI-Text statistisch unterscheidet. Sie gezielt zu meiden oder zu "
                   "ersetzen, macht einen Text nicht menschlicher, sondern verzerrt ihn.", ""]
        zeilen.append(", ".join(_wl_eintrag(e) for e in diagnose))
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
    ]
    if "modell_cv" in ev:  # ab Version 2: wiederholte gruppierte Kreuzvalidierung
        zeilen += [f"## Güte out-of-fold ({ev.get('methode', 'Kreuzvalidierung')})", "",
                   "Mittelwert ± SD über die Folds; pro Fold wurde alles (Perzentile, Gewichte, Funktionswort-Profil, Modell) nur aus den Train-Themen geschätzt.", "",
                   "| Verfahren | AUROC | Genauigkeit | bal. Genauigkeit | Median Mensch | Median KI |", "|---|---|---|---|---|---|"]
        for name, key in (("Modell P(menschlich)", "modell_cv"), ("Menschlichkeits-Score", "score_cv"),
                          ("Einseitiger Score", "score_ki_cv")):
            if key not in ev:
                continue
            e = ev[key]
            pm = lambda x, n=3: f"{e[x]:.{n}f} ± {e.get(x + '_sd', 0):.{n}f}".replace(".", ",") if x in e else "–"  # noqa: E731
            zeilen.append(f"| {name} | {pm('auroc')} | {pm('genauigkeit')} | {pm('bal_genauigkeit')} | {pm('median_mensch', 2)} | {pm('median_ki', 2)} |")
    else:
        zeilen += ["## Güte auf zurückgehaltenen Dokumenten (Test-Split, 25 %)", "",
                   "| Verfahren | AUROC | Genauigkeit | Median Mensch | Median KI |", "|---|---|---|---|---|"]
        for name, key in (("Modell P(menschlich)", "modell_test"), ("Menschlichkeits-Score", "score_test")):
            if key in ev:
                e = ev[key]
                zeilen.append(f"| {name} | {e['auroc']} | {e['genauigkeit']} | {e['median_mensch']} | {e['median_ki']} |")
    zeilen += schwellen_und_kalibrierung(t, ev)
    zeilen += einseitig_und_kappung(t, ev)
    zeilen += goodhart_tabelle(t)
    zeilen += ["", "## Alle Kennzahlen", "",
               "| Kennzahl | Mensch P10 / P25 / P50 / P75 / P90 | KI P25 / P50 / P75 | Trennschärfe | bewertet | Gewicht | Messunsicherheit | Bedeutung |",
               "|---|---|---|---|---|---|---|---|"]
    for kk, v in sorted(met.items(), key=lambda kv: -kv[1]["trennschaerfe"]):
        m, ki = v["mensch"], v["ki"]
        bew = "✔" if v["bewertet"] else ("nur Modell" if v.get("nur_modell") else "")
        zeilen.append(f"| {analyse.NAMEN.get(kk, kk)} | {f(kk, m['p10'])} / {f(kk, m['p25'])} / {f(kk, m['p50'])} / {f(kk, m['p75'])} / {f(kk, m['p90'])} | "
                      f"{f(kk, ki['p25'])} / {f(kk, ki['p50'])} / {f(kk, ki['p75'])} | {trenn(v)} | {bew} | "
                      f"{f(None, v['gewicht']) if v['bewertet'] else ''} | {f(kk, v.get('se_typ'))} | {ERKLAERUNG.get(kk, '')} |")
    if t.get("cluster"):
        zeilen += ["", "## Gebündelte Kennzahlen (Cluster)", "",
                   "Kennzahlen, die in menschlichen Texten stark korrelieren (|r| ≥ 0,7), zählen im Score zusammen höchstens so viel wie ihr stärkstes Mitglied:", ""]
        for kopf, mitglieder in t["cluster"].items():
            if len(mitglieder) > 1:
                zeilen.append("- " + ", ".join(analyse.NAMEN.get(m_, m_) for m_ in mitglieder))
    modell = t.get("modell", {})
    if modell.get("koeffizienten"):
        zeilen += ["", "## Modell", "", "Logistische Regression auf standardisierten Kennzahlen (positiv = spricht für menschlich)"
                   + ("; jedes Merkmal vor der Standardisierung einseitig am menschlichen Band gekappt (siehe Kappung)"
                      if modell.get("kappen") else "") + ":", ""]
        for kk, c in sorted(modell["koeffizienten"].items(), key=lambda kv: -abs(kv[1])):
            zeilen.append(f"- {analyse.NAMEN.get(kk, kk)}: {c:+.2f}")
    return "\n".join(zeilen) + "\n"


def _k(x, n=3) -> str:
    """Zahl mit deutschem Dezimalkomma."""
    return "–" if x is None else f"{x:.{n}f}".replace(".", ",")


def _prozent(x) -> str:
    return "–" if x is None else f"{100 * x:.1f} %".replace(".", ",")


def einseitig_und_kappung(t: dict, ev: dict) -> list[str]:
    """v7: einseitiger Score (Abweichungen auf der Gegenseite der KI zählen wie grün) und die einseitige Kappung der
    Modellmerkmale am menschlichen Band (textsorten.hochschule.modell.kappen)."""
    zeilen = []
    if t.get("ziel_score_ki") is not None or "score_ki_cv" in ev or "score_ki_alle" in ev:
        e = ev.get("score_ki_alle") or {}
        zeilen += ["", "## Einseitiger Score", "",
                   "Wie der Menschlichkeits-Score (gewichteter Anteil grün/gelb/rot über die bewerteten Kennzahlen), aber nur "
                   "Abweichungen in Richtung KI zählen: Liegt eine Kennzahl auf der der KI abgewandten Seite des menschlichen "
                   "Medians („menschlicher als typisch“), zählt sie wie grün. Der zweiseitige Score bleibt als „score“ erhalten."
                   + (f" Auf allen Abschnitten: AUROC {_k(e.get('auroc'), 3)}, Median Mensch {_k(e.get('median_mensch'), 1)}, "
                      f"Median KI {_k(e.get('median_ki'), 1)}." if e else "")
                   + (f" Ziel {_k(t['ziel_score_ki'], 1)} (siehe Schwellen)." if t.get("ziel_score_ki") is not None else "")]
    kappen = (t.get("modell") or {}).get("kappen") or {}
    if kappen:
        met, koef = t.get("metriken", {}), (t.get("modell") or {}).get("koeffizienten", {})
        zeilen += ["", "## Kappung der Modellmerkmale", "",
                   "Jedes Modellmerkmal wird vor der Standardisierung einseitig am menschlichen Band gekappt: auf der der KI "
                   "abgewandten Seite höchstens bis zum menschlichen P90 bzw. P10, auf der KI-Seite unverändert (dort gilt das "
                   "z-Clipping). Ein Wert „menschlicher als 90 % der Menschen“ zählt so nicht noch menschlicher; Übertreiben "
                   "bringt keine Wahrscheinlichkeit.", "",
                   "| Merkmal | gekappt | Grenze | Mensch Median | KI Median | Koeffizient |", "|---|---|---|---|---|---|"]
        for kk, kp in sorted(kappen.items(), key=lambda kv: -abs(koef.get(kv[0], 0))):
            v = met.get(kk, {})
            seite = "nach oben (P90)" if kp.get("seite") == "oben" else "nach unten (P10)"
            zeilen.append(f"| {analyse.NAMEN.get(kk, kk)} | {seite} | {f(kk, kp.get('wert'))} | "
                          f"{f(kk, (v.get('mensch') or {}).get('p50'))} | {f(kk, (v.get('ki') or {}).get('p50'))} | "
                          + (f"{koef[kk]:+.2f}".replace(".", ",") if kk in koef else "–") + " |")
    return zeilen


def schwellen_und_kalibrierung(t: dict, ev: dict) -> list[str]:
    """Schwellen (score_schwelle, ziel_p_mensch), Wahl von k/λ und Kalibrierung der Modell-Wahrscheinlichkeit."""
    hp = ev.get("hyperparameter", {})
    zeilen = ["", "## Schwellen", "",
              f"- **Score-Schwelle {_k(t.get('score_schwelle'), 1)}**: " + ev.get("score_schwelle_methode", "Mitte zwischen den "
              "Medianen der Out-of-fold-Scores von Mensch und KI") + "."]
    if "ziel_p_mensch" in t:
        zeilen.append(f"- **Ziel für P(menschlich) {_k(t['ziel_p_mensch'], 2)}**: "
                      + ev.get("ziel_p_mensch_methode", "aus den menschlichen Out-of-fold-Wahrscheinlichkeiten")
                      + ", auf 2 Stellen gerundet. Zusammen mit der Score-Schwelle ist das das Ziel des Coachs.")
    if t.get("ziel_score") is not None:
        zeilen.append(f"- **Ziel für den Score {_k(t['ziel_score'], 1)}**: "
                      + ev.get("ziel_score_methode", "P10 der menschlichen Out-of-fold-Scores") + ".")
    if t.get("ziel_score_ki") is not None:
        zeilen.append(f"- **Ziel für den einseitigen Score {_k(t['ziel_score_ki'], 1)}**: "
                      + ev.get("ziel_score_ki_methode", "P10 der menschlichen Out-of-fold-Werte des einseitigen Scores") + ".")
    za = ev.get("ziel_erreicht_anteil_oof")
    if za:
        zeilen.append(f"- **Anteil „Ziel erreicht“ (out-of-fold)**: Mensch {_prozent(za.get('mensch'))}, KI {_prozent(za.get('ki'))}"
                      + (f" – {ev['ziel_erreicht_methode']}" if ev.get("ziel_erreicht_methode") else "") + "."
                      + (f" Mit dem zweiseitigen Score statt des einseitigen: Mensch "
                         f"{_prozent(ev['ziel_erreicht_anteil_oof_zweiseitig'].get('mensch'))}, KI "
                         f"{_prozent(ev['ziel_erreicht_anteil_oof_zweiseitig'].get('ki'))}."
                         if ev.get("ziel_erreicht_anteil_oof_zweiseitig") else "")
                      + " Auch ein Teil echter menschlicher Abschnitte verfehlt das Ziel; es ist eine Orientierung, kein Beweis.")
    if hp:
        lam = hp.get("lambda")
        zeilen.append(f"- **Modell**: {hp.get('k')} Merkmale, L2-Strafe λ = {f'{lam:g}'.replace('.', ',') if lam is not None else '–'}"
                      + (f", standardisierte Merkmale auf ±{hp['z_clip']:g} begrenzt" if hp.get("z_clip") else "")
                      + "; k und λ nach der Ein-Standardfehler-Regel (erst wenige Merkmale, dann die stärkste Strafe, "
                        "deren Log-Loss höchstens einen Standardfehler über dem besten liegt).")
    kg = ev.get("modell_oof_kalibrierung")
    if kg:
        zeilen += ["", "## Kalibrierung der Modell-Wahrscheinlichkeit (out-of-fold)", "",
                   f"Brier-Score {_k(kg['brier'], 3)} (klassenbalanciert {_k(kg['brier_bal'], 3)}), "
                   f"ECE über {kg.get('klassen', 10)} Klassen {_k(kg['ece'], 3)} (klassenbalanciert {_k(kg['ece_bal'], 3)}). "
                   "Klein = gut kalibriert; „klassenbalanciert“ gewichtet Mensch und KI gleich, wie das Modell geschätzt ist.", "",
                   "| Gruppe | P5 | P10 | P25 | P50 | P75 | P90 |", "|---|---|---|---|---|---|---|"]
        for g, name in (("mensch", "Mensch"), ("ki", "KI")):
            pz = kg.get("perzentile", {}).get(g)
            if pz:
                zeilen.append(f"| {name} | " + " | ".join(_k(pz.get(q), 2) for q in ("p5", "p10", "p25", "p50", "p75", "p90")) + " |")
        rel = [r for r in kg.get("reliabilitaet", []) if r.get("p_mittel") is not None]
        if rel:
            zeilen += ["", "| P(menschlich) | Abschnitte Mensch | Abschnitte KI | Ø Vorhersage | Anteil Mensch (balanciert) |",
                       "|---|---|---|---|---|"]
            for r in rel:
                zeilen.append(f"| {_k(r['von'], 1)}–{_k(r['bis'], 1)} | {r['n_mensch']} | {r['n_ki']} | {_k(r['p_mittel_bal'], 2)} | "
                              f"{_k(r['anteil_mensch_bal'], 2)} |")
    return zeilen


def goodhart_tabelle(t: dict) -> list[str]:
    """Kontrafaktische Goodhart-Sensitivität aus baselines.json (textsorten.hochschule.goodhart)."""
    gh = t.get("goodhart")
    if not gh or not gh.get("merkmale"):
        return []
    zeilen = ["", "## Goodhart-Sensitivität des Modells", "",
              f"Was passiert, wenn ein KI-Text nur eine Kennzahl auf den menschlichen Median bringt? Je Modellmerkmal wurde in "
              f"allen {gh['n_ki']} KI-Abschnitten nur dieses Merkmal auf den Median der menschlichen Abschnitte gesetzt "
              f"(finales Modell). Median P(menschlich) der KI-Abschnitte vorher: {_k(gh['median_p_ki'], 3)}; "
              f"Ziel: {_k(gh['ziel_p_mensch'], 2)}. ⚠ = das Merkmal allein hebt den mittleren KI-Abschnitt auf das Ziel; "
              "dann könnte man das Urteil mit einer einzigen Stellschraube kippen.", "",
              "| Merkmal | Median P nachher | Median-Änderung | KI-Abschnitte ≥ Ziel | allein über Ziel |", "|---|---|---|---|---|"]
    for r in gh["merkmale"]:
        zeilen.append(f"| {analyse.NAMEN.get(r['id'], r['id'])} | {_k(r['median_p'], 3)} | {'+' if r['median_delta'] >= 0 else ''}"
                      f"{_k(r['median_delta'], 3)} | {round(100 * r['anteil_ueber_ziel'])} % | {'⚠ ja' if r['ueber_ziel'] else 'nein'} |")
    tp = gh.get("top")
    if tp and tp.get("ids"):
        zeilen += ["", f"Die {len(tp['ids'])} Merkmale mit dem stärksten Zug Richtung KI gemeinsam ("
                   + ", ".join(analyse.NAMEN.get(m, m) for m in tp["ids"])
                   + f"): Median P nachher {_k(tp['median_p'], 3)}, {round(100 * tp['anteil_ueber_ziel'])} % der KI-Abschnitte "
                   "erreichen das Ziel" + (" – ⚠ der mittlere KI-Abschnitt erreicht es damit." if tp["ueber_ziel"] else
                                           "; der mittlere KI-Abschnitt bleibt darunter.")]
    return zeilen


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baselines", default=os.path.join(SKILLS, "text-analyse", "data", "baselines.json"))
    ap.add_argument("--muster", default=os.path.join(SKILLS, "text-analyse", "data", "ki_muster.json"))
    ap.add_argument("--wortlisten", default=os.path.join(REPO, "kalibrierung", "ergebnisse", "wortlisten.json"))
    ap.add_argument("--aus", default=None, help="Ordner für alle erzeugten Dateien (Probelauf); Standard: Skill-References")
    args = ap.parse_args(argv)
    b = lade(args.baselines)
    mu = lade(args.muster)
    wl = lade(args.wortlisten) if os.path.exists(args.wortlisten) else None

    # Nomen der KI-Wortliste (Themen- und Personenwörter → „nur Diagnose“), aus der Großschreibung im Korpus
    nomen = nomen_im_korpus({x for e in wl["ki_typisch"] for x in e["ngramm"].split()}) if wl else None

    def ziel(skill, name):
        return os.path.join(args.aus, name) if args.aus else os.path.join(SKILLS, skill, "references", name)

    ausgaben = {
        ziel("menschlich-schreiben", "zielwerte.md"): zielwerte(b),
        ziel("menschlich-schreiben", "ki-muster.md"): kimuster(mu, wl, nomen),
        ziel("text-analyse", "kennzahlen.md"): kennzahlen(b),
    }
    wortschatz_pfad = os.path.join(REPO, "kalibrierung", "persoenlich", "wortschatz.json")
    if os.path.exists(wortschatz_pfad):
        inhalt = persoenlicher_wortschatz(lade(wortschatz_pfad))
        if inhalt:
            ausgaben[ziel("menschlich-schreiben", "persoenlicher-wortschatz.md")] = inhalt
    for pfad, inhalt in ausgaben.items():
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "w", encoding="utf-8") as fh:
            fh.write(inhalt)
        print("geschrieben:", pfad if args.aus else os.path.relpath(pfad, REPO))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
