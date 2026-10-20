#!/usr/bin/env python3
"""Kalibrierung: berechnet Referenzwerte (baselines.json) aus menschlichen und KI-Korpora.

Schritte:
  1. Texte zerlegen (höchstens 3 Abschnitte pro menschlichem Dokument, 1 pro KI-Text) und jeden Abschnitt an
     einer Satzgrenze auf L = 800 bereinigte Wörter kürzen; kürzere Abschnitte (< 0,95·L) verwerfen (HW01)
  2. Für jeden Abschnitt alle Kennzahlen einmal mit analyse.py messen  -> ergebnisse/features.csv
  3. Pro Kennzahl: dokumentgewichtete Perzentile (Mensch/KI), Trennschärfe (AUROC auf allen Abschnitten),
     zusätzliches Gate an themengleichen Paaren (KI-Text ↔ sein menschlicher Auszug) mit Bootstrap nach
     Dokument (HW02), typische Messunsicherheit se_typ (HW18)
  4. Redundante Kennzahlen bündeln: Cluster |r| ≥ 0,7 in den menschlichen Abschnitten, Gewicht gedeckelt (HW14)
  5. Funktionswort-Profil (NegBin-Log-Likelihood-Quotient, HW07) und Gewichte der KI-Muster aus den Häufigkeiten
  6. Logistisches Modell; Merkmalszahl und L2-Stärke per wiederholter gruppierter Kreuzvalidierung (5×5, Thema),
     Evaluation von Modell und Score out-of-fold, finales Modell auf allen Daten; Schwellen score_schwelle und
     ziel_p_mensch
  7. Diagnosen: AUROC je Quelle und Texttyp, Korrelation mit dem Erscheinungsjahr (HW19)
  8. Wort-/Phrasenlisten: was KI über- und was Menschen überdurchschnittlich nutzen
     (log-odds mit informativem Dirichlet-Prior, Monroe et al. 2008)

    python3 kalibriere.py [--korpus ../korpus] [--aus ../ergebnisse] [--baselines PFAD] [--muster PFAD]

Achtung: schreibt baselines.json, ki_muster.json (Gewichte) und wortlisten.json neben baselines.json.
Für Probeläufe --aus, --baselines und --muster auf ein Arbeitsverzeichnis setzen.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import glob
import inspect
import json
import math
import operator
import os
import random
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from itertools import accumulate

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HIER, "..", ".."))
SKILL_DATA = os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "data")
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
import analyse  # noqa: E402

L_STANDARD = analyse.ABSCHNITT_L  # 800 bereinigte Wörter pro Abschnitt (KI bereinigt: P5 ≈ 794, P10 ≈ 824)
L_TOLERANZ = 0.95         # Abschnitte unter 0,95·L werden verworfen
GATE_AUROC = 0.65         # Trennschärfe-Schwelle: AUROC ≥ 0,65 bzw. ≤ 0,35 (alle Abschnitte und Paare)
MIN_PAARE = 10            # weniger Paare: Gate nicht prüfbar (gilt als nicht bestanden)
CLUSTER_R = 0.7           # |r| innerhalb der menschlichen Abschnitte, ab dem Kennzahlen ein Cluster bilden
MODELL_R_MAX = 0.8        # Modellmerkmale untereinander |r| < 0,8 (gepoolt, Kollinearität)
MODELL_K = (6, 9, 12, 15, 20)                 # Merkmalszahlen, zwischen denen die Kreuzvalidierung wählt
MODELL_LAMBDA = (0.1, 0.03, 0.01, 0.003, 0.001)  # L2-Stärke auf dem mittleren Verlust (absteigend: Warmstart)
BOOTSTRAP_N, BOOTSTRAP_SEED = 300, 1
CV_WIEDERHOLUNGEN, CV_FOLDS, CV_SEED = 5, 5, 2024
FW_GLAETTUNG = 0.5        # +0,5 auf die Zählung je Klasse und Wort (HW07)
FW_POISSON = 1e6          # Größenparameter ≥ 1e6 = Poisson-Grenzfall
# Pilotliste HW07 (Fallback, falls analyse.FW_WOERTER fehlt)
FW_PILOT = ["die", "der", "und", "in", "zu", "von", "den", "das", "werden", "auf", "im", "sich", "eine", "ist", "für",
            "mit", "des", "auch", "als", "ein", "es", "wird", "nicht", "dass", "dem", "sind", "oder", "an", "einer",
            "bei", "durch", "wie", "sie", "diese", "um", "aus", "kann", "zur", "einen", "können"]

# Kennzahlen, die nicht in Score/Modell eingehen (Längen-/Format-Artefakte, Korpus-Unterschiede ohne Bezug zur
# Menschlichkeit oder Duplikate anderer Kennzahlen)
NICHT_BEWERTEN = {
    "absaetze", "satzlaenge_max", "markdown_elemente", "listenpunkte", "ueberschriften_pro_1000",
    "zitate_pro_1000", "satzlaenge_median", "satzlaenge_p10", "satzlaenge_p90", "mattr_50",
    "rhythmus_sprung_rel",      # HW11: Duplikat von satzlaenge_cv (r ≈ 0,81), lenkt zum Zickzack
    "menzerath_korrelation",    # HW16: misst vor allem Satzlängen-Gleichförmigkeit (r ≈ 0,78 mit CV)
    "anteil_funktionswoerter",  # HW07: durch fw_profil_llr_pro_1000 ersetzt
}
# Nur ins Logit-Modell und als eigene Anzeige, nicht in den Score (HW07-Korrektur: erst nach Goodhart-Test)
NUR_MODELL = {"fw_profil_llr_pro_1000"}
# Neue Kandidaten: bewertet nur, wenn sie das Gate bestehen (gilt für alle; hier nur zur Kennzeichnung im Bericht)
KANDIDATEN = {"nominalketten_pro_100", "silben_q21", "mattr_klumpung_100", "rhythmus_r1_log"}
META = ("gruppe", "quelle", "quelle_basis", "typ", "jahr", "doc_id", "thema", "abschnitt", "paar", "woerter", "saetze")
HINWEISE = {
    "satzlaenge_cv": "Wie stark die Satzlängen schwanken. Menschen mischen kurze und lange Sätze stärker.",
    "rhythmus_sprung_rel": "Ob Satzlängen eher in Phasen kommen (Mensch) oder streng abwechseln (KI).",
    "rhythmus_r1_log": "Ob Satzlängen eher in Phasen kommen (Mensch) oder streng abwechseln (KI).",
    "anteil_gleichfoermige_laeufe": "Anteil der Sätze in Dreierfolgen fast gleich langer Sätze.",
    "nachbarsatz_ueberlappung": "Menschen greifen Begriffe des Vorsatzes wieder auf, statt ständig Synonyme zu suchen.",
    "mattr_100": "Lexikalische Variation (Informationsfluss). KI-Text wechselt oft zu stark die Wörter (Synonym-Karussell): "
                 "Kernbegriffe wörtlich wiederaufnehmen statt umschreiben.",
    "gedankenstrich_pro_1000": "Gedankenstriche (–, —) für Einschübe; trennt im Hochschulkorpus kaum zwischen Mensch und KI.",
    "ki_muster_pro_1000": "Typische KI-Floskeln und -Konstruktionen, gewichtet nach Korpus-Häufigkeit.",
    "fw_profil_llr_pro_1000": "Gebrauch der häufigsten Funktionswörter (Menschen: mehr es, wie, auch, durch; KI: mehr als, "
                              "sich, dass). Nur als Tendenz lesen, keine Einzelwörter einstreuen.",
    "satzklammer_mittel": "Menschen spannen die Satzklammer weiter (mehr Wörter zwischen Hilfsverb und Partizip/Infinitiv).",
    "konnektoren_pro_1000": "Dichte von Konnektoren (zudem, somit, folglich …) in allen Satzstellungen.",
    "nominalketten_pro_100": "Genitiv- und von-Ketten; in menschlichen Fachtexten eher häufiger als bei KI.",
}


# ---------------------------------------------------------------------------
# Korpus laden, zerlegen, kürzen
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
    if max_abschnitte <= 1:
        return [stuecke[len(stuecke) // 2]]  # mittleres Stück, wie auszuege.py
    # gleichmäßig über das Dokument verteilt auswählen
    idx = sorted({round(i * (len(stuecke) - 1) / (max_abschnitte - 1)) for i in range(max_abschnitte)})
    return [stuecke[i] for i in idx]


def _saetze_mit_woertern(absatz: str) -> list[tuple[str, int]]:
    """Sätze eines Prosa-Absatzes mit Wortzahl, gezählt wie analyse.py (bereinigt, ist_wort)."""
    saetze = analyse.zerlege_saetze(analyse.bereinige_absatz(absatz, Counter()))
    return [(s, sum(1 for t in analyse.tokens(s) if analyse.ist_wort(t))) for s in saetze]


def kuerze(text: str, L: int = L_STANDARD, toleranz: float = L_TOLERANZ) -> str | None:
    """Kürzt einen Abschnitt an einer Satzgrenze auf höchstens L Wörter (HW01).

    Gezählt wird wie in analyse.py: nur Prosa-Absätze (zerlege_bloecke), bereinigt, ist_wort. Ganze Absätze
    bleiben im Wortlaut erhalten und werden mit Leerzeile verbunden; nur der letzte darf gekürzt sein (dann aus
    den bereinigten Sätzen). None, wenn weniger als toleranz·L Wörter zusammenkommen."""
    teile, n = [], 0
    for absatz in analyse.zerlege_bloecke(text)["absaetze"]:
        saetze = _saetze_mit_woertern(absatz)
        w = sum(x for _, x in saetze)
        if not w:
            continue
        if n + w <= L:
            teile.append(absatz)
            n += w
            continue
        rest = []
        for s, x in saetze:
            if n + x > L:
                break
            rest.append(s)
            n += x
        if rest:
            teile.append(" ".join(rest))
        break
    return "\n\n".join(teile) if teile and n >= toleranz * L else None


_MIT_KUERZUNG = "letzter_absatz_gekuerzt" in inspect.signature(analyse.analysiere_text).parameters


def analysiere_abschnitt(text: str, muster: list[dict]) -> dict:
    """analysiere_text mit letzter_absatz_gekuerzt=True (Schnittstelle 1); ältere analyse.py ohne Parameter."""
    if _MIT_KUERZUNG:
        return analyse.analysiere_text(text, muster, letzter_absatz_gekuerzt=True)
    return analyse.analysiere_text(text, muster)


def _woerter_low(text: str) -> list[str]:
    out = []
    for absatz in analyse.zerlege_bloecke(text)["absaetze"]:
        for s in analyse.zerlege_saetze(analyse.bereinige_absatz(absatz, Counter())):
            out.extend(t.lower() for t in analyse.tokens(s) if analyse.ist_wort(t))
    return out


def fw_zaehlung(erg: dict, text: str, woerter: list[str]) -> tuple[int, dict]:
    """(Wortzahl n, Zählungen k_w) der Funktionswörter; aus erg['fw_zaehlung'] oder selbst gezählt."""
    z = erg.get("fw_zaehlung")
    if z and "n" in z:
        return int(z["n"]), {w: int(z.get("k", {}).get(w, 0)) for w in woerter}
    wl = _woerter_low(text)
    c = Counter(wl)
    return len(wl), {w: c[w] for w in woerter}


def jahr_von(x) -> int | None:
    m = re.match(r"\s*(1[89]\d\d|20\d\d)", str(x or ""))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Statistik
# ---------------------------------------------------------------------------

def perz(xs, p):
    return analyse.perzentil(xs, p)


def gewichtetes_perzentil(xs, ws, p):
    """Perzentil mit Beobachtungsgewichten: lineare Interpolation über die Gewichtsmitten.
    Bei gleichen Gewichten identisch mit analyse.perzentil."""
    if not xs:
        return 0.0
    paare = sorted(zip(xs, ws))
    if len(paare) == 1:
        return paare[0][0]
    mitten, s = [], 0.0
    for _, w in paare:
        mitten.append(s + w / 2)
        s += w
    lo, hi = mitten[0], mitten[-1]
    if hi <= lo:
        return paare[0][0]
    ziel = lo + p * (hi - lo)
    j = bisect.bisect_right(mitten, ziel)
    if j <= 0:
        return paare[0][0]
    if j >= len(paare):
        return paare[-1][0]
    a, b = mitten[j - 1], mitten[j]
    t = (ziel - a) / (b - a) if b > a else 0.0
    return paare[j - 1][0] + t * (paare[j][0] - paare[j - 1][0])


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


def raenge(xs):
    """Ränge 1..n, Bindungen gemittelt."""
    order = sorted(range(len(xs)), key=xs.__getitem__)
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for t in range(i, j + 1):
            r[order[t]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(xs, ys):
    return analyse.korrelation(xs, ys)


def pearson_luecken(xs, ys):
    """Pearson über die Positionen, an denen beide Werte vorhanden sind (None = fehlt)."""
    paare = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(paare) < 4:
        return 0.0
    return pearson([a for a, _ in paare], [b for _, b in paare])


def spearman_luecken(xs, ys):
    paare = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(paare) < 4:
        return 0.0
    return pearson(raenge([a for a, _ in paare]), raenge([b for _, b in paare]))


def zusammenfassung(xs, ws=None):
    """Perzentile, Mittel und SD; mit Gewichten ws (z. B. 1/Abschnitte des Dokuments) dokumentgewichtet."""
    if ws is None:
        ws = [1.0] * len(xs)
    s = sum(ws) or 1.0
    m = sum(x * w for x, w in zip(xs, ws)) / s if xs else 0.0
    var = sum(w * (x - m) ** 2 for x, w in zip(xs, ws)) / s if xs else 0.0
    out = {f"p{int(100 * p)}": round(gewichtetes_perzentil(xs, ws, p), 4) for p in (0.10, 0.25, 0.50, 0.75, 0.90)}
    out.update({"mittel": round(m, 4), "sd": round(math.sqrt(var), 4), "n": len(xs)})
    return out


def se_typ(werte_je_dok: dict) -> float | None:
    """HW18: gepoolte SD zwischen Abschnitten desselben Dokuments (nur Dokumente mit ≥ 2 Abschnitten)."""
    ss, df = 0.0, 0
    for xs in werte_je_dok.values():
        xs = [x for x in xs if x is not None]
        if len(xs) < 2:
            continue
        m = sum(xs) / len(xs)
        ss += sum((x - m) ** 2 for x in xs)
        df += len(xs) - 1
    return math.sqrt(ss / df) if df else None


def bootstrap_ziehungen(n: int, anzahl: int = BOOTSTRAP_N, seed: int = BOOTSTRAP_SEED) -> list[list[int]]:
    """Multiplizitäten je Paar (= Dokument) für 'anzahl' Ziehungen mit Zurücklegen, fester Seed."""
    rnd = random.Random(seed)
    out = []
    for _ in range(anzahl):
        c = [0] * n
        for _ in range(n):
            c[rnd.randrange(n)] += 1
        out.append(c)
    return out


def paar_statistik(h: list, k: list, ziehungen: list[list[int]] | None = None) -> dict | None:
    """Themengleiche Paare: h[i], k[i] = Kennzahl von Mensch- und KI-Seite des Paares i (None = fehlt).

    AUROC auf den Paaren (ungepaarter Mann-Whitney über die Paar-Abschnitte) und Vorzeichen-Anteil
    (Mensch > KI, Gleichstand 0,5); mit ziehungen zusätzlich Bootstrap-95-%-Intervalle beider (Resampling der
    Paare, d. h. nach Dokument). Rechnet jede Ziehung in O(n) über einmal sortierte KI-Werte."""
    idx = [i for i in range(len(h)) if h[i] is not None and k[i] is not None]
    if len(idx) < MIN_PAARE:
        return None
    ki_ord = sorted(idx, key=lambda j: k[j])
    ks = [k[j] for j in ki_ord]
    lt = [bisect.bisect_left(ks, h[i]) for i in idx]
    le = [bisect.bisect_right(ks, h[i]) for i in idx]
    zeichen = [1.0 if h[i] > k[i] else 0.5 if h[i] == k[i] else 0.0 for i in idx]

    def werte(c):
        ch = [c[i] for i in idx]
        w = sum(ch)
        if not w:
            return None
        pre = [0] + list(accumulate(c[j] for j in ki_ord))
        u = 0.5 * sum(ci * (pre[a] + pre[b]) for ci, a, b in zip(ch, lt, le))
        return u / (w * w), sum(map(operator.mul, ch, zeichen)) / w

    a, v = werte([1] * len(h))
    out = {"n_paare": len(idx), "auroc": a, "vorzeichen": v}
    if ziehungen:
        boot = [b for b in (werte(c) for c in ziehungen) if b]
        a_s = sorted(b[0] for b in boot)
        v_s = sorted(b[1] for b in boot)
        out["auroc_ci"] = (perz(a_s, 0.025), perz(a_s, 0.975))
        out["vorzeichen_ci"] = (perz(v_s, 0.025), perz(v_s, 0.975))
    return out


def gate_bestanden(a_alle: float, ps: dict | None) -> bool:
    """HW02 (korrigiert): gleiche Richtung wie auf allen Abschnitten, AUROC auf den Paaren ≥ 0,65 bzw. ≤ 0,35,
    Bootstrap-Intervalle von Paar-AUROC und Vorzeichen-Anteil schließen 0,5 aus."""
    if not ps or "auroc_ci" not in ps:
        return False
    oben = a_alle > 0.5
    a = ps["auroc"]
    if (a > 0.5) != oben or abs(a - 0.5) < GATE_AUROC - 0.5:
        return False
    for lo, hi in (ps["auroc_ci"], ps["vorzeichen_ci"]):
        if not ((lo > 0.5) if oben else (hi < 0.5)):
            return False
    return True


def cluster_bilden(keys_sortiert: list[str], spalten: dict, schwelle: float = CLUSTER_R) -> dict:
    """HW14: greedy nach Trennschärfe (keys_sortiert absteigend). Jede Kennzahl kommt zum ersten Clusterkopf mit
    |r| ≥ schwelle (r in den übergebenen Spalten, hier: menschliche Abschnitte), sonst wird sie selbst Kopf.
    Gibt {kennzahl: kopf} zurück."""
    koepfe, zuordnung = [], {}
    for k in keys_sortiert:
        for kopf in koepfe:
            if abs(pearson_luecken(spalten[k], spalten[kopf])) >= schwelle:
                zuordnung[k] = kopf
                break
        else:
            koepfe.append(k)
            zuordnung[k] = k
    return zuordnung


def cluster_gewichte(zuordnung: dict, roh: dict) -> dict:
    """Gewicht je Mitglied g_i·max_g/Σg: ein Cluster wiegt höchstens so viel wie sein stärkstes Mitglied."""
    mitglieder = defaultdict(list)
    for k, kopf in zuordnung.items():
        mitglieder[kopf].append(k)
    out = {}
    for ks in mitglieder.values():
        summe = sum(roh[k] for k in ks)
        gmax = max(roh[k] for k in ks)
        for k in ks:
            out[k] = roh[k] * gmax / summe if summe else 0.0
    return out


# ---------------------------------------------------------------------------
# Logistisches Modell (L2, Klassen balanciert, Newton-Raphson)
# ---------------------------------------------------------------------------

def _loese(A, b):
    """Löst A·x = b (Gauß mit Spaltenpivotsuche); A klein."""
    n = len(b)
    M = [list(r) + [bi] for r, bi in zip(A, b)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        piv = M[i][i] or 1e-12
        for r in range(i + 1, n):
            f = M[r][i] / piv
            if f:
                Mr, Mi = M[r], M[i]
                for c in range(i, n + 1):
                    Mr[c] -= f * Mi[c]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (M[i][n] - sum(M[i][c] * x[c] for c in range(i + 1, n))) / (M[i][i] or 1e-12)
    return x


def _verlust(m):
    """log(1 + e^m), numerisch stabil."""
    return m + math.log1p(math.exp(-m)) if m > 0 else math.log1p(math.exp(m))


def logreg_spalten(spalten, y, lam=0.03, start=None, max_iter=100, tol=1e-7):
    """Ziel: mittlerer klassenbalancierter Log-Loss + lam/2·||w||² (Achsenabschnitt ungestraft).
    Gedämpftes Newton-Verfahren; konvergiert auch bei (fast) trennbaren Daten, weil die Strafe nicht mit n
    verschwindet. spalten = Merkmale spaltenweise (standardisiert). Gibt (w, b) zurück."""
    n, d = len(y), len(spalten)
    n1 = sum(y)
    n0 = n - n1
    if not n1 or not n0:
        return [0.0] * d, 0.0
    gew = [0.5 / n1 if yi else 0.5 / n0 for yi in y]
    Z = [[1.0] * n] + [list(s) for s in spalten]
    beta = list(start) if start and len(start) == d + 1 else [0.0] * (d + 1)

    def eta_von(bt):
        eta = [bt[0]] * n
        for a in range(1, d + 1):
            if bt[a]:
                ba = bt[a]
                eta = [e + ba * x for e, x in zip(eta, Z[a])]
        return eta

    def ziel(eta, bt):
        v = sum(gi * _verlust(-e if yi else e) for e, yi, gi in zip(eta, y, gew))
        return v + 0.5 * lam * sum(b * b for b in bt[1:])

    eta = eta_von(beta)
    f = ziel(eta, beta)
    for _ in range(max_iter):
        p = [1 / (1 + math.exp(-max(-35.0, min(35.0, e)))) for e in eta]
        r = [gi * (pi - yi) for gi, pi, yi in zip(gew, p, y)]
        v = [gi * pi * (1 - pi) for gi, pi in zip(gew, p)]
        g = [sum(map(operator.mul, r, Z[a])) for a in range(d + 1)]
        H = [[0.0] * (d + 1) for _ in range(d + 1)]
        for a in range(d + 1):
            va = list(map(operator.mul, v, Z[a]))
            for c in range(a, d + 1):
                H[a][c] = H[c][a] = sum(map(operator.mul, va, Z[c]))
        for a in range(1, d + 1):
            g[a] += lam * beta[a]
            H[a][a] += lam
        schritt = _loese(H, g)
        t = 1.0
        while True:
            neu = [b - t * s for b, s in zip(beta, schritt)]
            eta_neu = eta_von(neu)
            f_neu = ziel(eta_neu, neu)
            if f_neu <= f + 1e-12 or t < 1e-4:
                break
            t /= 2
        beta, eta, f = neu, eta_neu, f_neu
        if max(abs(t * s) for s in schritt) < tol:
            break
    return beta[1:], beta[0]


def logreg(X, y, lam=0.03, **kw):
    """Wie logreg_spalten, Merkmale zeilenweise."""
    d = len(X[0]) if X else 0
    return logreg_spalten([[x[j] for x in X] for j in range(d)], y, lam, **kw)


def vorhersage(w, b, x):
    z = b + sum(wj * xj for wj, xj in zip(w, x))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


# ---------------------------------------------------------------------------
# Funktionswort-Profil (HW07) und KI-Muster-Gewichte
# ---------------------------------------------------------------------------

def fw_llr_zaehlung(k: dict, n: int, profil: dict | None) -> float | None:
    """1000·LLR/n aus Zählungen (Schnittstelle 2); dieselbe Funktion wie in analyse.py, positiv = menschlicher."""
    return analyse.fw_llr_zaehlung(k, n, profil)


def fw_profil_schaetzen(zeilen: list[dict], woerter: list[str]) -> dict:
    """Raten je Klasse r = (Σk + 0,5)/Σn; ein Größenparameter je Wort per Momentenmethode über alle Abschnitte
    beider Klassen: s = Σ μ_i² / Σ((k_i − μ_i)² − μ_i) mit μ_i = r_Klasse·n_i; Nenner ≤ 0 → 1e6 (Poisson)."""
    n_g = {"mensch": 0, "ki": 0}
    k_g = {"mensch": Counter(), "ki": Counter()}
    for z in zeilen:
        n_g[z["gruppe"]] += z["_n"]
        k_g[z["gruppe"]].update(z["_fw"])
    rate = {g: {w: (k_g[g][w] + FW_GLAETTUNG) / max(1, n_g[g]) for w in woerter} for g in n_g}
    groesse = {}
    for w in woerter:
        zaehler = nenner = 0.0
        for z in zeilen:
            mu = rate[z["gruppe"]][w] * z["_n"]
            kw = z["_fw"].get(w, 0)
            zaehler += mu * mu
            nenner += (kw - mu) ** 2 - mu
        groesse[w] = round(min(FW_POISSON, zaehler / nenner), 3) if nenner > 0 else FW_POISSON
    return {"woerter": list(woerter),
            "rate_mensch": {w: round(rate["mensch"][w], 9) for w in woerter},
            "rate_ki": {w: round(rate["ki"][w], 9) for w in woerter},
            "groesse": groesse,
            "woerter_mensch": n_g["mensch"], "woerter_ki": n_g["ki"],
            "methode": "NegBin-LLR (Mosteller/Wallace): Raten je Klasse mit +0,5-Glättung, Größenparameter per "
                       "Momentenmethode über alle Abschnitte; 1e6 = Poisson"}


def muster_gewichte(zeilen: list[dict], muster_liste: list[dict]) -> tuple[dict, dict]:
    """Gewicht je KI-Muster aus den Raten pro 1000 Token: log2(KI/Mensch), gedeckelt auf 0–3; nur bei
    Verhältnis ≥ 1,25 und Treffern in mindestens 3 KI-Dokumenten."""
    zaehl = {"mensch": Counter(), "ki": Counter()}
    docs = {"mensch": defaultdict(set), "ki": defaultdict(set)}
    tok = {"mensch": 0, "ki": 0}
    for z in zeilen:
        g = z["gruppe"]
        tok[g] += z["_token"]
        for mid, n in z["_treffer"].items():
            zaehl[g][mid] += n
            docs[g][mid].add(z["doc_id"])
    out = {}
    for mu in muster_liste:
        mid = mu["id"]
        r_m = 1000 * zaehl["mensch"][mid] / max(1, tok["mensch"])
        r_k = 1000 * zaehl["ki"][mid] / max(1, tok["ki"])
        verh = (r_k + 0.02) / (r_m + 0.02)
        g = round(max(0.0, min(3.0, math.log2(verh))), 2) if verh >= 1.25 and len(docs["ki"][mid]) >= 3 else 0.0
        out[mid] = {"gewicht": g, "rate_mensch": r_m, "rate_ki": r_k, "verhaeltnis": verh}
    return out, tok


def muster_kandidaten(saetze: list[dict], muster_liste: list[dict]) -> list[list[tuple]]:
    """Alle Roh-Treffer je Satz als (start, ende, muster_id), nur Sätze mit Treffer."""
    out = []
    for s in saetze:
        kand = [(t.start(), t.end(), mu["id"]) for mu in muster_liste for t in mu["_re"].finditer(s["text"])
                if t.end() > t.start()]
        if kand:
            out.append(kand)
    return out


def muster_summe(kandidaten: list[list[tuple]], gew: dict) -> float:
    """Gewichtete Treffersumme wie analyse.analysiere_text: Überlappungen mit den aktuellen Gewichten auflösen
    (analyse.muster_aufloesen), Gewicht 0 zählt nicht."""
    summe = 0.0
    for kand in kandidaten:
        for _a, _e, g, _mu, _f, _v in analyse.muster_aufloesen(
                [(a, e, float(gew.get(mid, 0.0)), {"id": mid}, "") for a, e, mid in kand]):
            if g > 0:
                summe += g
    return summe


def abgeleitet(z: dict, gew: dict, profil: dict) -> dict:
    """Kopie der Zeile mit den von Train-Daten abhängigen Kennzahlen (Muster-Gewichte, Funktionswort-Profil)."""
    neu = dict(z)
    if "_kand" in z:  # wie zur Laufzeit: Überlappungen mit den Fold-Gewichten auflösen
        summe = muster_summe(z["_kand"], gew)
    else:
        summe = sum(gew.get(mid, 0) * n for mid, n in z["_treffer"].items())
    neu["ki_muster_pro_1000"] = round(1000 * summe / max(1, z["_token"]), 4)
    llr = fw_llr_zaehlung(z["_fw"], z["_n"], profil)
    neu["fw_profil_llr_pro_1000"] = round(llr, 4) if llr is not None else None
    return neu


# ---------------------------------------------------------------------------
# Kalibrierung auf einer Datenmenge (in jedem CV-Fold und final auf allen Daten)
# ---------------------------------------------------------------------------

def paare_bilden(daten: list[dict]) -> list[tuple[dict, dict]]:
    """Themengleiche Paare: KI-Abschnitt ↔ mittlerer Abschnitt seines menschlichen basis_id-Dokuments."""
    mensch = {z["thema"]: z for z in daten if z["gruppe"] == "mensch" and z["paar"]}
    return [(mensch[z["thema"]], z) for z in daten if z["gruppe"] == "ki" and z["thema"] in mensch]


def kalibriere_daten(zeilen: list[dict], keys: list[str], muster_liste: list[dict], fw_woerter: list[str],
                     boot_n: int = BOOTSTRAP_N, mit_se: bool = False) -> dict:
    """Schätzt alles, was aus Trainingsdaten kommt: Muster-Gewichte, Funktionswort-Profil, Perzentile,
    Trennschärfe, Paar-Gate, Cluster und Gewichte, Rangliste der Modellmerkmale (samt Standardisierung)."""
    mg, tok = muster_gewichte(zeilen, muster_liste)
    gew = {mid: v["gewicht"] for mid, v in mg.items()}
    profil = fw_profil_schaetzen(zeilen, fw_woerter)
    daten = [abgeleitet(z, gew, profil) for z in zeilen]
    alle_keys = list(keys) + [k for k in ("ki_muster_pro_1000", "fw_profil_llr_pro_1000") if k not in keys]

    pro_dok = Counter(z["doc_id"] for z in daten)
    ist_m = [z["gruppe"] == "mensch" for z in daten]
    dok_w = [1.0 / pro_dok[z["doc_id"]] for z in daten]
    paare = paare_bilden(daten)
    ziehungen = bootstrap_ziehungen(len(paare), boot_n) if boot_n and len(paare) >= MIN_PAARE else None

    metriken = {}
    for k in alle_keys:
        spalte = [z.get(k) for z in daten]
        hm = [(x, w) for x, w, m in zip(spalte, dok_w, ist_m) if m and x is not None]
        hk = [(x, w) for x, w, m in zip(spalte, dok_w, ist_m) if not m and x is not None]
        if len(hm) < 10 or len(hk) < 10:
            continue
        a = auroc([x for x, _ in hm], [x for x, _ in hk])
        trenn = abs(a - 0.5) * 2
        kandidat = k not in NICHT_BEWERTEN and trenn >= 2 * (GATE_AUROC - 0.5)
        ph, pk = [p[0].get(k) for p in paare], [p[1].get(k) for p in paare]
        ps = paar_statistik(ph, pk, ziehungen if kandidat else None)
        gate = gate_bestanden(a, ps) if kandidat else False
        v = {
            "mensch": zusammenfassung([x for x, _ in hm], [w for _, w in hm]),
            "ki": zusammenfassung([x for x, _ in hk], [w for _, w in hk]),
            "auroc": round(a, 3),
            "richtung": "mensch_hoeher" if a > 0.5 else "ki_hoeher",
            "trennschaerfe": round(trenn, 3),
            "gate": bool(gate),
            "bewertet": bool(gate and k not in NUR_MODELL),
            "gewicht": 0.0,
            "hinweis": HINWEISE.get(k, ""),
        }
        v["mensch"]["n_dokumente"] = len({z["doc_id"] for z, m, x in zip(daten, ist_m, spalte) if m and x is not None})
        if ps:
            v["auroc_paare"] = round(ps["auroc"], 3)
            v["vorzeichen_paare"] = round(ps["vorzeichen"], 3)
            v["n_paare"] = ps["n_paare"]
            if "auroc_ci" in ps:
                v["auroc_paare_ci"] = [round(x, 3) for x in ps["auroc_ci"]]
                v["vorzeichen_paare_ci"] = [round(x, 3) for x in ps["vorzeichen_ci"]]
        if k in NUR_MODELL and gate:
            v["nur_modell"] = True
        if mit_se:
            je_dok = defaultdict(list)
            for z, m, x in zip(daten, ist_m, spalte):
                if m:
                    je_dok[z["doc_id"]].append(x)
            se = se_typ(je_dok)
            if se is not None:
                v["se_typ"] = round(se, 4)
        metriken[k] = v

    # Cluster und gedeckelte Gewichte (nur bewertete Kennzahlen, r in den menschlichen Abschnitten)
    bewertet = sorted([k for k, v in metriken.items() if v["bewertet"]], key=lambda k: (-metriken[k]["trennschaerfe"], k))
    spalten_m = {k: [z.get(k) for z, m in zip(daten, ist_m) if m] for k in bewertet}
    zuordnung = cluster_bilden(bewertet, spalten_m)
    gewichte = cluster_gewichte(zuordnung, {k: metriken[k]["trennschaerfe"] for k in bewertet})
    cluster = defaultdict(list)
    for k in bewertet:
        metriken[k]["gewicht_roh"] = metriken[k]["trennschaerfe"]
        metriken[k]["gewicht"] = round(gewichte[k], 3)
        metriken[k]["cluster"] = zuordnung[k]
        cluster[zuordnung[k]].append(k)

    # Rangliste der Modellmerkmale: Gate bestanden, nach Trennschärfe, untereinander |r| < MODELL_R_MAX
    kandidaten = sorted([k for k, v in metriken.items() if v["gate"]], key=lambda k: (-metriken[k]["trennschaerfe"], k))
    rang = []
    for k in kandidaten:
        xs = [z.get(k) for z in daten]
        if all(abs(pearson_luecken(xs, [z.get(g) for z in daten])) < MODELL_R_MAX for g in rang):
            rang.append(k)
        if len(rang) >= max(MODELL_K):
            break
    mu_, sd_ = {}, {}
    for k in rang:
        xs = [z[k] for z in daten if z.get(k) is not None]
        mu_[k] = analyse.mittel(xs)
        sd_[k] = analyse.sd(xs) or 1.0
    return {"metriken": metriken, "cluster": dict(cluster), "rang": rang, "mittel": mu_, "sd": sd_,
            "gew": gew, "muster": mg, "token": tok, "profil": profil, "daten": daten, "n_paare": len(paare)}


def _standardisiert(paket: dict, z: dict, k: str) -> float:
    x = z.get(k)
    return 0.0 if x is None else (x - paket["mittel"][k]) / paket["sd"][k]  # fehlend = Mittelwert (wie bewerte)


def fit_modell(paket: dict, k: int, lam: float, start=None) -> dict:
    merkmale = paket["rang"][:k]
    spalten = [[_standardisiert(paket, z, m) for z in paket["daten"]] for m in merkmale]
    y = [1 if z["gruppe"] == "mensch" else 0 for z in paket["daten"]]
    w, b = logreg_spalten(spalten, y, lam, start=start) if merkmale else ([], 0.0)
    return {"merkmale": merkmale, "w": w, "b": b, "lam": lam}


def p_mensch(modell: dict, paket: dict, z: dict) -> float:
    return vorhersage(modell["w"], modell["b"], [_standardisiert(paket, z, m) for m in modell["merkmale"]])


def score(metriken: dict, z: dict) -> float:
    """Menschlichkeits-Score wie analyse.bewerte: grün 1, gelb 0,5, rot 0, gewichtet mit den gedeckelten Gewichten."""
    gs = gp = 0.0
    for k, v in metriken.items():
        if not v["bewertet"] or z.get(k) is None:
            continue
        if k == "rhythmus_r1_log" and (z.get("saetze") or 0) < 30:
            continue  # wie bewerte(): Reihenfolgemaß bei < 30 Sätzen nicht bewertet
        m, x = v["mensch"], z[k]
        st = 1.0 if m["p25"] <= x <= m["p75"] else 0.5 if m["p10"] <= x <= m["p90"] else 0.0
        gs += v["gewicht"]
        gp += v["gewicht"] * st
    return 100 * gp / gs if gs else 0.0


def score_schwelle_von(gruppen, scores) -> float:
    """Mitte zwischen den Score-Medianen von Mensch und KI."""
    s_m = perz([s for g, s in zip(gruppen, scores) if g == "mensch"], 0.5)
    s_k = perz([s for g, s in zip(gruppen, scores) if g == "ki"], 0.5)
    return (s_m + s_k) / 2


def evaluiere(gruppen, werte, schwelle, wahrscheinlichkeit=False) -> dict:
    pos = [v for g, v in zip(gruppen, werte) if g == "mensch"]
    neg = [v for g, v in zip(gruppen, werte) if g == "ki"]
    rp = sum(v >= schwelle for v in pos)
    rn = sum(v < schwelle for v in neg)
    out = {"auroc": auroc(pos, neg), "genauigkeit": (rp + rn) / max(1, len(pos) + len(neg)),
           "bal_genauigkeit": 0.5 * (rp / max(1, len(pos)) + rn / max(1, len(neg))),
           "n_mensch": len(pos), "n_ki": len(neg), "median_mensch": perz(pos, 0.5), "median_ki": perz(neg, 0.5)}
    if wahrscheinlichkeit and pos and neg:
        out["logloss_bal"] = 0.5 * (analyse.mittel([-math.log(max(p, 1e-6)) for p in pos])
                                    + analyse.mittel([-math.log(max(1 - p, 1e-6)) for p in neg]))
    return out


def mittel_sd(ergebnisse: list[dict]) -> dict:
    out = {}
    for k in ("auroc", "genauigkeit", "bal_genauigkeit", "median_mensch", "median_ki", "logloss_bal"):
        xs = [e[k] for e in ergebnisse if k in e]
        if xs:
            out[k] = round(statistics.fmean(xs), 3)
            out[k + "_sd"] = round(statistics.stdev(xs), 3) if len(xs) > 1 else 0.0
    out["folds"] = len(ergebnisse)
    return out


# ---------------------------------------------------------------------------
# Wiederholte gruppierte Kreuzvalidierung
# ---------------------------------------------------------------------------

def gruppen_folds(themen: list[str], folds: int, rnd: random.Random) -> dict:
    """Ordnet jedes Thema genau einem Fold zu (gemischt, reihum: gleich große Folds)."""
    t = sorted(set(themen))
    rnd.shuffle(t)
    return {th: i % folds for i, th in enumerate(t)}


def kreuzvalidierung(zeilen, keys, muster_liste, fw_woerter, wiederholungen=CV_WIEDERHOLUNGEN, folds=CV_FOLDS,
                     seed=CV_SEED, k_gitter=MODELL_K, lam_gitter=MODELL_LAMBDA, boot_n=BOOTSTRAP_N, log=None) -> dict:
    """Pro Fold die komplette Kalibrierung auf den Train-Themen, Bewertung auf den zurückgehaltenen Themen.
    Gibt Fold-Ergebnisse je Modellkonfiguration (k, λ) und für den Score sowie Out-of-fold-Werte je Zeile zurück."""
    rnd = random.Random(seed)
    gruppen = [z["gruppe"] for z in zeilen]
    erg_modell = {(k, lam): [] for k in k_gitter for lam in lam_gitter}
    oof_modell = {kl: defaultdict(list) for kl in erg_modell}
    erg_score, oof_score = [], defaultdict(list)
    bewertet_zaehl, gate_zaehl = Counter(), Counter()
    for r in range(wiederholungen):
        zuordnung = gruppen_folds([z["thema"] for z in zeilen], folds, rnd)
        for f in range(folds):
            t0 = time.time()
            train = [z for z in zeilen if zuordnung[z["thema"]] != f]
            test_idx = [i for i, z in enumerate(zeilen) if zuordnung[z["thema"]] == f]
            paket = kalibriere_daten(train, keys, muster_liste, fw_woerter, boot_n=boot_n)
            bewertet_zaehl.update(k for k, v in paket["metriken"].items() if v["bewertet"])
            gate_zaehl.update(k for k, v in paket["metriken"].items() if v["gate"])
            test = [abgeleitet(zeilen[i], paket["gew"], paket["profil"]) for i in test_idx]
            g_test = [gruppen[i] for i in test_idx]
            schwelle = score_schwelle_von([z["gruppe"] for z in paket["daten"]],
                                          [score(paket["metriken"], z) for z in paket["daten"]])
            s_test = [score(paket["metriken"], z) for z in test]
            erg_score.append(evaluiere(g_test, s_test, schwelle))
            for i, s in zip(test_idx, s_test):
                oof_score[i].append(s)
            for k in k_gitter:
                start = None
                for lam in lam_gitter:
                    mod = fit_modell(paket, k, lam, start=start)
                    start = [mod["b"]] + list(mod["w"])
                    p = [p_mensch(mod, paket, z) for z in test]
                    erg_modell[(k, lam)].append(evaluiere(g_test, p, 0.5, wahrscheinlichkeit=True))
                    for i, pp in zip(test_idx, p):
                        oof_modell[(k, lam)][i].append(pp)
            if log:
                log(f"  CV {r + 1}.{f + 1}: {len(train)} Train-/{len(test)} Test-Abschnitte, "
                    f"{paket['n_paare']} Paare, {time.time() - t0:.1f} s")
    return {"modell": erg_modell, "oof_modell": oof_modell, "score": erg_score, "oof_score": oof_score,
            "bewertet_haeufigkeit": bewertet_zaehl, "gate_haeufigkeit": gate_zaehl,
            "folds_gesamt": wiederholungen * folds}


def waehle_konfiguration(erg_modell: dict) -> tuple:
    """Ein-Standardfehler-Regel auf dem balancierten Log-Loss out-of-fold: die einfachste Konfiguration (wenige
    Merkmale, dann starke Strafe), deren Mittel höchstens einen Standardfehler über dem besten liegt."""
    werte = {kl: [e["logloss_bal"] for e in v if "logloss_bal" in e] for kl, v in erg_modell.items()}
    mittel = {kl: statistics.fmean(xs) for kl, xs in werte.items() if xs}
    bestes = min(mittel, key=mittel.get)
    xs = werte[bestes]
    se = statistics.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0
    nah = [kl for kl, m in mittel.items() if m <= mittel[bestes] + se]
    return min(nah, key=lambda kl: (kl[0], -kl[1]))


# ---------------------------------------------------------------------------
# Diagnosen (HW19)
# ---------------------------------------------------------------------------

def auroc_je_gruppe(daten: list[dict], werte: list, schluessel: str, min_n: int = 10) -> dict:
    """AUROC je Gruppe (Quelle bzw. Typ): menschliche Abschnitte der Gruppe gegen KI-Abschnitte, deren Basis-
    dokument zur Gruppe gehört. Gruppen mit weniger als min_n KI- oder Mensch-Abschnitten entfallen."""
    pos, neg = defaultdict(list), defaultdict(list)
    for z, x in zip(daten, werte):
        if x is None:
            continue
        (pos if z["gruppe"] == "mensch" else neg)[z[schluessel] or "?"].append(x)
    return {g: auroc(pos[g], neg[g]) for g in sorted(pos) if len(pos[g]) >= min_n and len(neg.get(g, [])) >= min_n}


def typ_gruppe(daten: list[dict], min_ki: int = 20) -> None:
    """Setzt z['typ_gruppe']: Texttyp, seltene Typen (< min_ki KI-Abschnitte) als 'übrige'."""
    n = Counter(z["typ"] for z in daten if z["gruppe"] == "ki")
    for z in daten:
        z["typ_gruppe"] = z["typ"] if n[z["typ"]] >= min_ki else "übrige"


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


def log_odds(c_a: Counter, c_b: Counter, prior: Counter, alpha0: float | None = None):
    """z-Werte nach Monroe et al. (2008), Gl. 16/22. Prior-Stärke alpha0 = Größe des Hintergrundkorpus
    (alpha_w = Hintergrundhäufigkeit), damit die Glättung +0,01 keine Rolle spielt; O(V)."""
    n_a, n_b = sum(c_a.values()), sum(c_b.values())
    p_ges = max(1, sum(prior.values()))  # einmal statt pro N-Gramm
    if alpha0 is None:
        alpha0 = float(p_ges)
    out = {}
    for w in set(c_a) | set(c_b):
        a_w = alpha0 * prior[w] / p_ges + 0.01
        ya, yb = c_a[w], c_b[w]
        la = math.log((ya + a_w) / (n_a + alpha0 - ya - a_w))
        lb = math.log((yb + a_w) / (n_b + alpha0 - yb - a_w))
        out[w] = (la - lb) / math.sqrt(1 / (ya + a_w) + 1 / (yb + a_w))
    return out


# ---------------------------------------------------------------------------
# Bericht
# ---------------------------------------------------------------------------

def _f(x, nk=3):
    return "–" if x is None else f"{x:.{nk}f}"


def _pm(e, k, nk=3):
    return f"{e[k]:.{nk}f} ± {e.get(k + '_sd', 0):.{nk}f}" if k in e else "–"


def bericht(b: dict, diag: dict, muster_bericht: list, wortlisten: dict) -> str:
    t = b["textsorten"]["hochschule"]
    met, ev, kor = t["metriken"], b["evaluation"], b["korpus"]
    z = ["# Kalibrierungsbericht", ""]
    z.append(f"Mensch: {kor['mensch']['dokumente']} Dokumente / {kor['mensch']['abschnitte']} Abschnitte · "
             f"KI: {kor['ki']['dokumente']} Dokumente / {kor['ki']['abschnitte']} Abschnitte · "
             f"Abschnittslänge {kor['abschnittslaenge']} Wörter (verworfen: Mensch {kor['mensch']['verworfen']}, "
             f"KI {kor['ki']['verworfen']}) · themengleiche Paare: {kor['paare']}")
    z += ["", diag["paarpruefung"], ""]
    z += [f"## Kreuzvalidierung ({ev['methode']})", "",
          "Pro Fold komplette Kalibrierung auf den Train-Themen (Muster-Gewichte, Funktionswort-Profil, Perzentile, Gate, "
          "Cluster, Merkmalsauswahl, Modell), Bewertung auf den zurückgehaltenen Themen. Mittelwert ± SD über die Folds.", "",
          "| Verfahren | AUROC | Genauigkeit | bal. Genauigkeit | Median Mensch | Median KI |", "|---|---|---|---|---|---|"]
    for name, key in (("Modell P(menschlich)", "modell_cv"), ("Menschlichkeits-Score", "score_cv")):
        e = ev[key]
        z.append(f"| {name} | {_pm(e, 'auroc')} | {_pm(e, 'genauigkeit')} | {_pm(e, 'bal_genauigkeit')} | "
                 f"{_pm(e, 'median_mensch', 2)} | {_pm(e, 'median_ki', 2)} |")
    hp = ev["hyperparameter"]
    z += ["", f"Gewählte Modellkonfiguration (Ein-Standardfehler-Regel auf dem balancierten Log-Loss out-of-fold): {hp['k']} Merkmale, λ = {hp['lambda']}. "
          f"Out-of-fold gepoolt: Modell-AUROC {ev['modell_oof_auroc']}, Score-AUROC {ev['score_oof_auroc']}. "
          f"In-sample (finales Modell auf allen Daten): Modell-AUROC {ev['modell_alle']['auroc']}, Score-AUROC {ev['score_alle']['auroc']}.",
          "", f"**Schwellen:** score_schwelle = {t['score_schwelle']} (Mitte der Out-of-fold-Score-Mediane), "
          f"ziel_p_mensch = {t['ziel_p_mensch']} (P25 der menschlichen Out-of-fold-Wahrscheinlichkeiten, mindestens 0,5).", "",
          "| k | λ | AUROC | bal. Genauigkeit | Log-Loss (bal.) |", "|---|---|---|---|---|"]
    for zeile in diag["gitter"]:
        z.append(f"| {zeile['k']} | {zeile['lambda']} | {_pm(zeile, 'auroc')} | {_pm(zeile, 'bal_genauigkeit')} | {_pm(zeile, 'logloss_bal')} |")
    z += ["", "## Kennzahlen: Trennschärfe, Paar-Gate, Cluster", "",
          f"Gate: AUROC auf allen Abschnitten und auf den themengleichen Paaren ≥ {GATE_AUROC} bzw. ≤ {1 - GATE_AUROC:.2f} "
          f"(gleiche Richtung), Bootstrap-95-%-Intervalle ({BOOTSTRAP_N} Ziehungen nach Dokument, Seed {BOOTSTRAP_SEED}) von "
          "Paar-AUROC und Vorzeichen-Anteil ohne 0,5. Perzentile dokumentgewichtet. 'CV' = Anteil der Folds, in denen die "
          "Kennzahl bewertet war (bei 'nur Modell': das Gate bestand). ⚠ = |AUROC alle − AUROC Paare| > 0,10 (konfundiert).", "",
          "| Kennzahl | AUROC alle | AUROC Paare [95 %] | Vorzeichen [95 %] | Gate | bewertet | CV | Gewicht | Cluster | se_typ | "
          "Mensch P25–P50–P75 | KI P25–P50–P75 |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in sorted(met.items(), key=lambda kv: -kv[1]["trennschaerfe"]):
        mm, kk = v["mensch"], v["ki"]
        ap = v.get("auroc_paare")
        konf = " ⚠" if ap is not None and abs(ap - v["auroc"]) > 0.10 else ""
        ci = v.get("auroc_paare_ci")
        vci = v.get("vorzeichen_paare_ci")
        ap_txt = "–" if ap is None else f"{ap:.3f}" + (f" [{ci[0]:.2f}; {ci[1]:.2f}]" if ci else "")
        vz_txt = "–" if v.get("vorzeichen_paare") is None else f"{v['vorzeichen_paare']:.2f}" + (f" [{vci[0]:.2f}; {vci[1]:.2f}]" if vci else "")
        name = analyse.NAMEN.get(k, k) + (" (Kandidat)" if k in KANDIDATEN else "") + (" (nur Modell)" if k in NUR_MODELL else "")
        bew = "✔" if v["bewertet"] else ("Modell" if v.get("nur_modell") else "")
        cv_anteil = diag["cv_gate" if k in NUR_MODELL else "cv_bewertet"].get(k, 0)
        cv_txt = f"{cv_anteil:.0%}" if k not in NICHT_BEWERTEN else "–"
        z.append(f"| {name} | {v['auroc']:.3f}{konf} | {ap_txt} | {vz_txt} | {'✔' if v['gate'] else ''} | {bew} | {cv_txt} | "
                 f"{v['gewicht'] if v['bewertet'] else ''} | {v.get('cluster', '')} | {_f(v.get('se_typ'), 4)} | "
                 f"{mm['p25']:.3g} – {mm['p50']:.3g} – {mm['p75']:.3g} | {kk['p25']:.3g} – {kk['p50']:.3g} – {kk['p75']:.3g} |")
    z += ["", "Kandidaten (HW08–HW13, HW22): " + "; ".join(
        f"{k}: {'Gate bestanden' if met[k]['gate'] else 'Gate nicht bestanden'}" + (f" (AUROC {met[k]['auroc']}, Paare {met[k].get('auroc_paare', '–')})")
        for k in sorted(KANDIDATEN) if k in met)]
    z += ["", f"## Cluster redundanter Kennzahlen (|r| ≥ {CLUSTER_R} in den menschlichen Abschnitten)", "",
          "Gewicht je Mitglied = Trennschärfe · max/Σ im Cluster; ein Cluster wiegt höchstens so viel wie sein stärkstes Mitglied.", ""]
    for kopf, mitglieder in sorted(t["cluster"].items(), key=lambda kv: -met[kv[0]]["trennschaerfe"]):
        z.append(f"- **{kopf}**: " + ", ".join(f"{m} ({met[m]['gewicht']})" for m in mitglieder))
    mod = t["modell"]
    z += ["", f"## Modell ({len(mod['koeffizienten'])} Merkmale, λ = {mod.get('lambda')})", "",
          "Logistische Regression auf standardisierten Kennzahlen (positiv = spricht für menschlich):", ""]
    for k, c in sorted(mod["koeffizienten"].items(), key=lambda kv: -abs(kv[1])):
        z.append(f"- {analyse.NAMEN.get(k, k)}: {c:+.3f}")
    fw = t.get("fw_profil")
    if fw:
        verh = sorted(fw["woerter"], key=lambda w: fw["rate_ki"][w] / fw["rate_mensch"][w])
        z += ["", "## Funktionswort-Profil (HW07)", "",
              "Verhältnis KI/Mensch der Raten; KI seltener: " + ", ".join(f"{w} {fw['rate_ki'][w] / fw['rate_mensch'][w]:.2f}" for w in verh[:8])
              + " · KI häufiger: " + ", ".join(f"{w} {fw['rate_ki'][w] / fw['rate_mensch'][w]:.2f}" for w in reversed(verh[-8:]))
              + f" · Poisson-Grenzfall bei {sum(1 for w in fw['woerter'] if fw['groesse'][w] >= FW_POISSON)} von {len(fw['woerter'])} Wörtern."]
    z += ["", "## Diagnose: AUROC je Quelle und Texttyp (HW19)", "",
          "Mensch-Abschnitte einer Quelle bzw. eines Typs gegen KI-Abschnitte, deren Basisdokument dazugehört. "
          "Modell und Score out-of-fold, Kennzahlen mit den finalen Werten. ⚠ = Spannweite > 0,15."]
    for titel, tab in (("Quelle", diag["je_quelle"]), ("Texttyp", diag["je_typ"])):
        gruppen = tab["gruppen"]
        z += ["", f"| {titel}: Kennzahl | " + " | ".join(f"{g} (n={tab['n'][g]})" for g in gruppen) + " | Spannweite |",
              "|---|" + "---|" * (len(gruppen) + 1)]
        for name, werte in tab["zeilen"]:
            vals = [werte.get(g) for g in gruppen]
            da = [x for x in vals if x is not None]
            sp = max(da) - min(da) if len(da) > 1 else 0.0
            z.append(f"| {name} | " + " | ".join(_f(x) for x in vals) + f" | {sp:.3f}{' ⚠' if sp > 0.15 else ''} |")
    z += ["", "## Diagnose: Korrelation mit dem Erscheinungsjahr (menschliche Abschnitte, HW19)", "",
          diag["jahr_zeile"], "", "| Kennzahl | Pearson r | Spearman ρ |", "|---|---|---|"]
    for name, r, rho in diag["jahr"]:
        z.append(f"| {name} | {r:+.3f}{' ⚠' if abs(r) > 0.2 or abs(rho) > 0.2 else ''} | {rho:+.3f} |")
    z += ["", "## KI-Muster (Häufigkeit pro 1000 Token, alle Abschnitte)", "", "| Muster | Mensch | KI | Verhältnis | Gewicht |",
          "|---|---|---|---|---|"]
    for mid, label, r_m, r_k, verh, g in sorted(muster_bericht, key=lambda x: -x[4]):
        z.append(f"| {label} | {r_m:.3f} | {r_k:.3f} | {verh:.2f} | {g} |")
    z += ["", "## Wörter/Phrasen, die KI überdurchschnittlich nutzt (Top 60)", "",
          ", ".join(f"{e['ngramm']} ({e['ki_pro_1000']:.2f} vs {e['mensch_pro_1000']:.2f})" for e in wortlisten["ki_typisch"][:60]),
          "", "## Wörter/Phrasen, die Menschen überdurchschnittlich nutzen (Top 60)", "",
          ", ".join(f"{e['ngramm']} ({e['mensch_pro_1000']:.2f} vs {e['ki_pro_1000']:.2f})" for e in wortlisten["mensch_typisch"][:60]),
          "", f"Laufzeit: {diag['laufzeit']:.0f} s"]
    return "\n".join(z) + "\n"


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    t_start = time.time()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--korpus", default=os.path.join(REPO, "kalibrierung", "korpus"))
    ap.add_argument("--aus", default=os.path.join(REPO, "kalibrierung", "ergebnisse"))
    ap.add_argument("--baselines", default=os.path.join(SKILL_DATA, "baselines.json"))
    ap.add_argument("--muster", default=os.path.join(SKILL_DATA, "ki_muster.json"))
    ap.add_argument("--max-abschnitte", type=int, default=3)
    ap.add_argument("--laenge", type=int, default=L_STANDARD, help="bereinigte Wörter pro Abschnitt (HW01)")
    ap.add_argument("--cv-wiederholungen", type=int, default=CV_WIEDERHOLUNGEN)
    ap.add_argument("--cv-folds", type=int, default=CV_FOLDS)
    ap.add_argument("--bootstrap", type=int, default=BOOTSTRAP_N, help="Bootstrap-Ziehungen für das Paar-Gate")
    args = ap.parse_args(argv)
    if args.max_abschnitte < 1:
        ap.error("--max-abschnitte muss >= 1 sein")
    if args.cv_folds < 2 or args.cv_wiederholungen < 1:
        ap.error("--cv-folds muss >= 2 und --cv-wiederholungen >= 1 sein")
    os.makedirs(args.aus, exist_ok=True)

    def log(s):
        print(s, file=sys.stderr, flush=True)

    mensch = lade_korpus(args.korpus, "mensch")
    ki = lade_korpus(args.korpus, "ki")
    log(f"Dokumente: Mensch {len(mensch)}, KI {len(ki)}")
    if not mensch or not ki:
        log("Beide Korpora werden benötigt.")
        return 1

    # Muster ohne Gewichtung (alle 1.0) laden, damit die Neugewichtung nicht zirkulär ist
    muster_roh = analyse.lade_muster(args.muster)
    for mu in muster_roh:
        mu["gewicht"] = 1.0
    with open(args.muster, encoding="utf-8") as f:
        muster_json = json.load(f)
    fw_woerter = list(getattr(analyse, "FW_WOERTER", None) or FW_PILOT)
    basis = {d["id"]: d for d in mensch}

    zeilen, verworfen = [], Counter()
    satzlaengen = {"mensch": [], "ki": []}
    ngr = {"mensch": Counter(), "ki": Counter()}
    ngr_docs = {"mensch": defaultdict(set), "ki": defaultdict(set)}
    token_summe = {"mensch": 0, "ki": 0}
    for nr, doc in enumerate(mensch + ki):
        g = doc["gruppe"]
        if g == "mensch":
            roh = zerlege(doc["text"], max_abschnitte=args.max_abschnitte)
            stuecke3 = roh if args.max_abschnitte == 3 else zerlege(doc["text"], max_abschnitte=3)
            mitte = stuecke3[len(stuecke3) // 2] if stuecke3 else None  # Auszug für das KI-Gegenstück (auszuege.py)
            thema, b = doc["id"], doc
        else:
            roh = zerlege(doc["text"], max_abschnitte=1) or [doc["text"]]
            mitte = None
            thema = doc.get("basis_id") or doc["id"]
            b = basis.get(thema, {})
        for k, ab in enumerate(roh):
            kurz = kuerze(ab, args.laenge)
            if kurz is None:
                verworfen[g] += 1
                continue
            erg = analysiere_abschnitt(kurz, muster_roh)
            if erg["info"]["saetze"] < 12:
                verworfen[g] += 1
                continue
            n_fw, k_fw = fw_zaehlung(erg, kurz, fw_woerter)
            woerter = [t.lower() for t in analyse.TOKEN_RE.findall(kurz) if analyse.ist_wort(t)]
            zeile = {"gruppe": g, "quelle": doc["quelle"], "quelle_basis": b.get("quelle", doc["quelle"]),
                     "typ": doc.get("typ") or b.get("typ") or "?", "jahr": jahr_von(doc.get("jahr")) if g == "mensch" else None,
                     "doc_id": doc["id"], "thema": thema, "abschnitt": k, "paar": g == "ki" or ab == mitte,
                     "woerter": erg["info"]["woerter"], "saetze": erg["info"]["saetze"], **erg["metriken"],
                     "_fw": k_fw, "_n": n_fw, "_token": erg["info"]["token"],
                     "_treffer": Counter(t["muster"] for t in erg["muster_treffer"]),
                     "_kand": muster_kandidaten(erg["saetze"], muster_roh),
                     "_staemme": {analyse.stamm(w) for w in woerter if w not in analyse.FUNKTIONSWOERTER and len(w) > 3}}
            zeilen.append(zeile)
            satzlaengen[g].extend(erg["info"]["satzlaengen"])
            token_summe[g] += erg["info"]["token"]
            c, _ = ngramme(kurz)
            ngr[g].update(c)
            for w in c:
                ngr_docs[g][w].add(doc["id"])
        if (nr + 1) % 100 == 0:
            log(f"  {nr + 1} Dokumente analysiert ({time.time() - t_start:.0f} s)")
    if not any(z["gruppe"] == "mensch" for z in zeilen) or not any(z["gruppe"] == "ki" for z in zeilen):
        log("Nach dem Kürzen fehlen Abschnitte einer Gruppe.")
        return 1

    # Paarprüfung: hat der gepaarte Auszug die größte Inhaltswort-Überlappung mit dem KI-Text?
    je_doc = defaultdict(list)
    for z in zeilen:
        if z["gruppe"] == "mensch":
            je_doc[z["doc_id"]].append(z)
    n_paare = abweichend = 0
    for z in zeilen:
        if z["gruppe"] != "ki":
            continue
        kand = je_doc.get(z["thema"], [])
        gepaart = [h for h in kand if h["paar"]]
        if not gepaart:
            continue
        n_paare += 1
        jac = {h["abschnitt"]: len(h["_staemme"] & z["_staemme"]) / max(1, len(h["_staemme"] | z["_staemme"])) for h in kand}
        if max(jac, key=jac.get) != gepaart[0]["abschnitt"]:
            abweichend += 1
    for z in zeilen:
        del z["_staemme"]
    paarpruefung = (f"Paarprüfung: Bei {abweichend} von {n_paare} Paaren hat ein anderer Abschnitt des Basisdokuments mehr "
                    "Inhaltswort-Überlappung mit dem KI-Text als der gepaarte mittlere Auszug (Hinweis auf geänderte Extraktion).")
    keys = [k for k in zeilen[0] if k not in META and not k.startswith("_")]
    log(f"Abschnitte: Mensch {sum(z['gruppe'] == 'mensch' for z in zeilen)}, KI {sum(z['gruppe'] == 'ki' for z in zeilen)}, "
        f"verworfen {dict(verworfen)}, Paare {n_paare} ({time.time() - t_start:.0f} s)")

    # --- Kreuzvalidierung -------------------------------------------------------
    cv = kreuzvalidierung(zeilen, keys, muster_json["muster"], fw_woerter, args.cv_wiederholungen, args.cv_folds,
                          boot_n=args.bootstrap, log=log)
    k_best, lam_best = waehle_konfiguration(cv["modell"])
    gruppen = [z["gruppe"] for z in zeilen]
    oof_p = [analyse.mittel(cv["oof_modell"][(k_best, lam_best)][i]) if cv["oof_modell"][(k_best, lam_best)][i] else None
             for i in range(len(zeilen))]
    oof_s = [analyse.mittel(cv["oof_score"][i]) if cv["oof_score"][i] else None for i in range(len(zeilen))]
    ziel_p = round(max(0.5, perz([p for p, g in zip(oof_p, gruppen) if g == "mensch" and p is not None], 0.25)), 2)
    schwelle = round(score_schwelle_von([g for g, s in zip(gruppen, oof_s) if s is not None], [s for s in oof_s if s is not None]), 1)

    # --- Finale Kalibrierung auf allen Daten --------------------------------------
    paket = kalibriere_daten(zeilen, keys, muster_json["muster"], fw_woerter, boot_n=args.bootstrap, mit_se=True)
    modell = fit_modell(paket, k_best, lam_best)
    daten = paket["daten"]
    metriken = paket["metriken"]
    log(f"Final: {sum(v['bewertet'] for v in metriken.values())} Kennzahlen bewertet, {len(paket['cluster'])} Cluster, "
        f"Modell k={k_best}, λ={lam_best} ({time.time() - t_start:.0f} s)")

    # Muster-Gewichte schreiben
    muster_bericht = []
    for mu in muster_json["muster"]:
        mm = paket["muster"][mu["id"]]
        mu["gewicht"] = mm["gewicht"]
        mu["rate_mensch_pro_1000"] = round(mm["rate_mensch"], 3)
        mu["rate_ki_pro_1000"] = round(mm["rate_ki"], 3)
        mu["verhaeltnis_ki_mensch"] = round(mm["verhaeltnis"], 2)
        muster_bericht.append((mu["id"], mu["label"], mm["rate_mensch"], mm["rate_ki"], mm["verhaeltnis"], mm["gewicht"]))
    muster_json["version"] = "kalibriert"
    muster_json["kalibrierung"] = {"token_mensch": paket["token"]["mensch"], "token_ki": paket["token"]["ki"]}
    with open(args.muster, "w", encoding="utf-8") as f:
        json.dump(muster_json, f, ensure_ascii=False, indent=1)

    spalten = list(META) + [k for k in keys] + [k for k in ("fw_profil_llr_pro_1000",) if k not in keys]
    with open(os.path.join(args.aus, "features.csv"), "w", newline="", encoding="utf-8") as f:
        wtr = csv.DictWriter(f, fieldnames=spalten, extrasaction="ignore")
        wtr.writeheader()
        wtr.writerows(daten)

    # --- Evaluation -----------------------------------------------------------------
    p_alle = [p_mensch(modell, paket, z) for z in daten]
    s_alle = [score(metriken, z) for z in daten]
    erg_best = cv["modell"][(k_best, lam_best)]
    gitter = [dict(mittel_sd(v), k=kl[0], **{"lambda": kl[1]}) for kl, v in sorted(cv["modell"].items())]
    ok_p = [(g, p) for g, p in zip(gruppen, oof_p) if p is not None]
    ok_s = [(g, s) for g, s in zip(gruppen, oof_s) if s is not None]
    eval_ = {
        "methode": f"{args.cv_wiederholungen}×{args.cv_folds} gruppierte Kreuzvalidierung (Thema = basis_id bzw. doc_id)",
        "modell_cv": mittel_sd(erg_best),
        "score_cv": mittel_sd(cv["score"]),
        "modell_oof_auroc": round(auroc([p for g, p in ok_p if g == "mensch"], [p for g, p in ok_p if g == "ki"]), 3),
        "score_oof_auroc": round(auroc([s for g, s in ok_s if g == "mensch"], [s for g, s in ok_s if g == "ki"]), 3),
        "modell_alle": {k: round(v, 3) for k, v in evaluiere(gruppen, p_alle, 0.5).items()},
        "score_alle": {k: round(v, 3) for k, v in evaluiere(gruppen, s_alle, schwelle).items()},
        "hyperparameter": {"k": k_best, "lambda": lam_best},
        "score_schwelle": schwelle,
        "ziel_p_mensch": ziel_p,
    }

    n_m = sum(g == "mensch" for g in gruppen)
    baselines = {
        "version": "2",
        "beschreibung": "Referenzwerte für analyse.py, berechnet von kalibrierung/scripts/kalibriere.py. "
                        f"Abschnitte à {args.laenge} bereinigte Wörter; Zielbereich = mittlere 50 % der menschlichen "
                        "Abschnitte (P25–P75, dokumentgewichtet).",
        "korpus": {
            "abschnittslaenge": args.laenge,
            "paare": paket["n_paare"],
            "mensch": {"dokumente": len(mensch), "abschnitte": n_m, "verworfen": verworfen["mensch"],
                       "quellen": dict(Counter(d["quelle"] for d in mensch))},
            "ki": {"dokumente": len(ki), "abschnitte": len(zeilen) - n_m, "verworfen": verworfen["ki"],
                   "quellen": dict(Counter(d["quelle"] for d in ki))},
        },
        "evaluation": eval_,
        "textsorten": {
            "hochschule": {
                "beschreibung": "Formelle Hochschularbeiten: Hausarbeit, Bachelor-/Masterarbeit, Seminar- und Aufgabenbearbeitungen.",
                "abschnittslaenge": args.laenge,
                "metriken": metriken,
                "cluster": paket["cluster"],
                "modell": {"koeffizienten": {k: round(c, 4) for k, c in zip(modell["merkmale"], modell["w"])},
                           "intercept": round(modell["b"], 4),
                           "mittel": {k: round(paket["mittel"][k], 5) for k in modell["merkmale"]},
                           "sd": {k: round(paket["sd"][k], 5) for k in modell["merkmale"]},
                           "lambda": lam_best},
                "fw_profil": paket["profil"],
                "score_schwelle": schwelle,
                "ziel_p_mensch": ziel_p,
                "satzlaengen_verteilung_mensch": analyse.verteilung(satzlaengen["mensch"]),
                "satzlaengen_verteilung_ki": analyse.verteilung(satzlaengen["ki"]),
            }
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.baselines)), exist_ok=True)
    with open(args.baselines, "w", encoding="utf-8") as f:
        json.dump(baselines, f, ensure_ascii=False, indent=1)

    # --- Wortlisten (alle Abschnitte) ---------------------------------------------
    prior = ngr["mensch"] + ngr["ki"]
    z_scores = log_odds(ngr["ki"], ngr["mensch"], prior)
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
                  "methode": "log-odds ratio mit informativem Dirichlet-Prior (Monroe, Colaresi & Quinn 2008; "
                             "Prior-Stärke = Korpusgröße), alle Abschnitte, min. 4 Dokumente"}
    with open(os.path.join(args.aus, "wortlisten.json"), "w", encoding="utf-8") as f:
        json.dump(wortlisten, f, ensure_ascii=False, indent=1)

    # kompakte Fassung fürs Plugin (Coach): nur Inhalts-/Stilwörter, keine reinen Funktionswörter
    def kompakt(eintraege, n=80):
        return [e for e in eintraege if not all(t in analyse.FUNKTIONSWOERTER or len(t) < 3 for t in e["ngramm"].split())][:n]
    kompakt_pfad = os.path.join(os.path.dirname(os.path.abspath(args.baselines)), "wortlisten.json")
    if os.path.abspath(kompakt_pfad) == os.path.abspath(os.path.join(args.aus, "wortlisten.json")):
        kompakt_pfad = kompakt_pfad.replace("wortlisten.json", "wortlisten_kompakt.json")  # Probelauf: nicht überschreiben
    with open(kompakt_pfad, "w", encoding="utf-8") as f:
        json.dump({"methode": wortlisten["methode"], "ki_typisch": kompakt(wortlisten["ki_typisch"]),
                   "mensch_typisch": kompakt(wortlisten["mensch_typisch"])}, f, ensure_ascii=False, indent=1)

    # --- Diagnosen und Bericht ------------------------------------------------------
    typ_gruppe(daten)
    bewertete = [k for k, v in sorted(metriken.items(), key=lambda kv: -kv[1]["trennschaerfe"]) if v["bewertet"] or v.get("nur_modell")]

    def tabelle(schluessel):
        zeilen_t = [("Modell P(menschlich) (OOF)", auroc_je_gruppe(daten, oof_p, schluessel)),
                    ("Score (OOF)", auroc_je_gruppe(daten, oof_s, schluessel))]
        zeilen_t += [(analyse.NAMEN.get(k, k), auroc_je_gruppe(daten, [z.get(k) for z in daten], schluessel)) for k in bewertete]
        gr = sorted({g for _, w in zeilen_t for g in w})
        n = {g: f"{sum(1 for z in daten if z[schluessel] == g and z['gruppe'] == 'mensch')}/"
                f"{sum(1 for z in daten if z[schluessel] == g and z['gruppe'] == 'ki')}" for g in gr}
        return {"gruppen": gr, "zeilen": zeilen_t, "n": n}

    mit_jahr = [z for z in daten if z["gruppe"] == "mensch" and z["jahr"]]
    jahre = [z["jahr"] for z in mit_jahr]
    jahr_keys = bewertete + [k for k in ("satzlaenge_mittel", "satzlaenge_cv", "teilsaetze_pro_satz") if k not in bewertete and k in metriken]
    jahr = sorted([(analyse.NAMEN.get(k, k), pearson_luecken([z.get(k) for z in mit_jahr], jahre),
                    spearman_luecken([z.get(k) for z in mit_jahr], jahre)) for k in jahr_keys], key=lambda t: -abs(t[1]))
    auffaellig = [n for n, r, rho in jahr if abs(r) > 0.2 or abs(rho) > 0.2]
    jahr_zeile = (f"{len(mit_jahr)} Abschnitte mit Jahr ({min(jahre) if jahre else '–'}–{max(jahre) if jahre else '–'}). "
                  + (f"|r| oder |ρ| > 0,2 (nachsehen): {', '.join(auffaellig)}." if auffaellig else "Keine Kennzahl mit |r| oder |ρ| > 0,2."))
    diag = {"paarpruefung": paarpruefung, "gitter": gitter,
            "cv_bewertet": {k: n / cv["folds_gesamt"] for k, n in cv["bewertet_haeufigkeit"].items()},
            "cv_gate": {k: n / cv["folds_gesamt"] for k, n in cv["gate_haeufigkeit"].items()},
            "je_quelle": tabelle("quelle_basis"), "je_typ": tabelle("typ_gruppe"),
            "jahr": jahr, "jahr_zeile": jahr_zeile, "laufzeit": time.time() - t_start}
    with open(os.path.join(args.aus, "bericht.md"), "w", encoding="utf-8") as f:
        f.write(bericht(baselines, diag, muster_bericht, wortlisten))
    print(json.dumps(eval_, ensure_ascii=False, indent=1))
    log(f"Fertig in {time.time() - t_start:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
