#!/usr/bin/env python3
"""Fasst die Metadaten der generierten KI-Texte (eine JSON-Datei pro Text) zu korpus/ki/<quelle>/meta.jsonl zusammen.

    python3 ki_meta_sammeln.py --meta-dir /pfad/ki_gen/meta [--quelle claude]
"""
import argparse
import glob
import json
import os

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HIER, "..", ".."))

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--meta-dir", required=True)
ap.add_argument("--quelle", default="claude")
args = ap.parse_args()
ordner = os.path.join(REPO, "kalibrierung", "korpus", "ki", args.quelle)
zeilen = []
for pfad in sorted(glob.glob(os.path.join(args.meta_dir, "*.json"))):
    with open(pfad, encoding="utf-8") as f:
        m = json.load(f)
    if os.path.exists(os.path.join(ordner, m["id"] + ".txt")):
        zeilen.append(m)
with open(os.path.join(ordner, "meta.jsonl"), "w", encoding="utf-8") as f:
    for m in zeilen:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print(f"{len(zeilen)} Einträge in {os.path.relpath(ordner, REPO)}/meta.jsonl")
