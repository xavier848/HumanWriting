#!/usr/bin/env python3
"""Extrahiert alle Dokumente einer Korpus-Quelle neu (nach Verbesserungen an extract_text.py).

Liest korpus/mensch/<quelle>/meta.jsonl, extrahiert <pdfs>/<id>.pdf erneut, schreibt den Text zurück,
aktualisiert das Feld "woerter" und meldet Dokumente, die eine manuelle Prüfung brauchen
(zu wenig Text, geringer Anteil behaltener Wörter, auffällige Artefakte).

    python3 neu_extrahieren.py --quelle ssoar --pdfs /pfad/zu/pdfs/ssoar [--min-woerter 1500]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)
import extract_text  # noqa: E402

REPO = os.path.normpath(os.path.join(HIER, "..", ".."))


def artefakte(text: str) -> dict:
    absaetze = [a for a in text.split("\n\n") if a.strip()]
    n = max(1, len(text.split()))
    return {
        "zitat_absaetze": sum(a.startswith(("„", '"', "»")) for a in absaetze) / max(1, len(absaetze)),
        "lose_ziffern_pro_1000": 1000 * len(re.findall(r"[a-zäöü][.!?]\s\d{1,2}\s[A-ZÄÖÜ]", text)) / n,
        "aufzaehlungszeichen": len(re.findall(r"[•▪●■]", text)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quelle", required=True)
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--min-woerter", type=int, default=1500)
    args = ap.parse_args()
    ordner = os.path.join(REPO, "kalibrierung", "korpus", "mensch", args.quelle)
    meta_pfad = os.path.join(ordner, "meta.jsonl")
    zeilen = [json.loads(l) for l in open(meta_pfad, encoding="utf-8") if l.strip()]
    behalten, pruefen, verworfen = [], [], []
    for m in zeilen:
        pdf = os.path.join(args.pdfs, m["id"] + ".pdf")
        if not os.path.exists(pdf):
            pruefen.append((m["id"], "PDF fehlt"))
            behalten.append(m)
            continue
        try:
            text, info = extract_text.extract(pdf)
        except Exception as e:  # noqa: BLE001
            pruefen.append((m["id"], f"Fehler: {e}"))
            behalten.append(m)
            continue
        w = len(text.split())
        if w < args.min_woerter:
            verworfen.append((m["id"], f"nur {w} Wörter nach Neu-Extraktion"))
            txt = os.path.join(ordner, m["id"] + ".txt")
            if os.path.exists(txt):
                os.remove(txt)
            continue
        with open(os.path.join(ordner, m["id"] + ".txt"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
        alt = m.get("woerter")
        m["woerter"] = w
        m["extraktion"] = {"anteil_behalten": info["anteil_behalten"], "start": info["start_found"], "ende": info["end_found"]}
        a = artefakte(text)
        gruende = []
        if info["anteil_behalten"] < 0.15:
            gruende.append(f"nur {info['anteil_behalten']:.0%} behalten")
        if a["zitat_absaetze"] > 0.3:
            gruende.append(f"{a['zitat_absaetze']:.0%} Absätze beginnen mit Zitat")
        if a["lose_ziffern_pro_1000"] > 3:
            gruende.append(f"{a['lose_ziffern_pro_1000']:.1f} lose Ziffern/1000")
        if a["aufzaehlungszeichen"] > 5:
            gruende.append(f"{a['aufzaehlungszeichen']} Aufzählungszeichen")
        if not info["end_found"]:
            gruende.append("Ende (Literaturverzeichnis) nicht erkannt")
        if alt and w > 2.5 * alt:
            gruende.append(f"Wortzahl {alt} → {w}")
        if gruende:
            pruefen.append((m["id"], "; ".join(gruende)))
        behalten.append(m)
    with open(meta_pfad, "w", encoding="utf-8") as f:
        for m in behalten:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(json.dumps({"quelle": args.quelle, "behalten": len(behalten), "verworfen": verworfen, "pruefen": pruefen}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
