#!/usr/bin/env python3
"""Wählt pro menschlichem Dokument einen Auszug als Vorlage für das themengleiche KI-Gegenstück.

Für jedes Dokument wird derselbe Zerlegungsalgorithmus wie in kalibriere.py benutzt und der mittlere
Abschnitt gewählt. Ausgabe: <aus>/<id>.txt pro Auszug und <aus>/auftraege.json mit Metadaten.
Die KI-Texte werden später nur aus einer inhaltlichen Gliederung dieses Auszugs geschrieben, nie aus
dem Wortlaut (siehe kalibrierung/README.md).

    python3 auszuege.py --aus /tmp/ki_gen/auszug
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)
import kalibriere  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--korpus", default=os.path.join(kalibriere.REPO, "kalibrierung", "korpus"))
    ap.add_argument("--aus", required=True)
    args = ap.parse_args()
    os.makedirs(args.aus, exist_ok=True)
    auftraege = []
    for doc in kalibriere.lade_korpus(args.korpus, "mensch"):
        stuecke = kalibriere.zerlege(doc["text"], max_abschnitte=3)
        if not stuecke:
            continue
        auszug = stuecke[len(stuecke) // 2]
        pfad = os.path.join(args.aus, doc["id"] + ".txt")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(auszug + "\n")
        auftraege.append({k: doc.get(k) for k in ("id", "quelle", "titel", "typ", "fach", "jahr")}
                         | {"woerter": len(auszug.split()), "auszug": pfad})
    with open(os.path.join(args.aus, "auftraege.json"), "w", encoding="utf-8") as f:
        json.dump(auftraege, f, ensure_ascii=False, indent=1)
    print(f"{len(auftraege)} Auszüge geschrieben nach {args.aus}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
