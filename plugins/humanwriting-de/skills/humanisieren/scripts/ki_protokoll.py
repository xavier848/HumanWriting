#!/usr/bin/env python3
"""KI-Nutzungsprotokoll aus Coach-Verläufen (*.coach.json).

Erzeugt Zeilen für die Dokumentationstabelle der KI-Nutzung, die Hochschulen verlangen, z. B. die MBS Research
Guidelines 2026, Anhang 3: Kapitel/Abschnitt, Werkzeug, Zweck, repräsentative Prompts, Ergebnis/Einbindung.
Je Verlauf eine Zeile. Gezählt wird, was der Coach festgehalten hat (Messrunden, Hinweise je Bereich, Datum);
Werkzeug und Prompts sind Angaben des Nutzers und vor der Abgabe zu prüfen.

Aufruf:
  python3 ki_protokoll.py kapitel2.coach.json --kapitel "2 Theoretische Grundlagen" --prompt "Prüf meinen Abschnitt"
  python3 ki_protokoll.py k2.coach.json k3.coach.json --kapitel "2 Grundlagen" --kapitel "3 Methodik" --sprache en
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

# Hinweistyp des Coaches -> Bereich (Reihenfolge = Ausgabe bei Gleichstand)
BEREICHE = [
    ("satzlaenge", ("Satzlängen", "sentence length"), ("buendeln", "teilen", "kurz", "zickzack", "mitte")),
    ("satzbau", ("Satzbau", "sentence structure"), ("klammer", "nebensatz", "kommas", "fw_")),
    ("konnektoren", ("Konnektoren", "connectives"), ("konnektor",)),
    ("floskeln", ("Floskeln", "stock phrases"), ("floskel", "gegenfolie", "strohmann")),
    ("begriffe", ("Begriffswahl und Anschluss", "terminology and cohesion"), ("anknuepfung", "kein_bezug", "synonyme")),
    ("absaetze", ("Absätze", "paragraphing"), ("absatz",)),
    ("form", ("Zeichensetzung und Form", "punctuation and formal conventions"),
     ("abkuerzung", "bindestrich", "gender", "semikolon", "gedankenstrich", "doppelpunkt")),
]
STIL = ("Stil", "style")

TEXTE = {
    "de": {
        "kopf": ("Kapitel/Abschnitt", "Werkzeug", "Zweck", "Repräsentative Prompts", "Ergebnis/Einbindung"),
        "werkzeug": "Claude (Anthropic) in Claude Code mit Plugin humanwriting-de (Stil-Coach)",
        "prompt": "Prüf meinen Abschnitt mit dem Stil-Coach und nenn mir die Stellen, die ich überarbeiten soll.",
        "zweck": {"coach": "Stil-Feedback zum eigenen Entwurf ({b})",
                  "ueberarbeiten": "Stilistische Überarbeitung des eigenen Entwurfs ({b})"},
        "runden": lambda n: f"{n} Messrunde" + ("" if n == 1 else "n"),
        "hinweise": lambda n: f"{n} Hinweis" + ("" if n == 1 else "e"),
        "ergebnis": {"coach": "{runden}{daten}, {hinweise} auf Satzebene ohne ausformulierte Textpassagen; "
                              "Hinweise selbst geprüft und in eigenen Worten umgesetzt oder verworfen",
                     "ueberarbeiten": "{runden}{daten}, {hinweise}; Sätze von Claude stilistisch umformuliert, "
                                      "Inhalt mit inhalt_check.py geprüft und selbst durchgesehen"},
        "bis": "–",
        "hinweis_ueberarbeiten": ("Hinweis: Im Überarbeiten-Modus stammen die Formulierungen von Claude. Nach den MBS "
                                  "Research Guidelines 2026 (Teil C, 4.2) dürfen KI-Formulierungen auch dokumentiert nur "
                                  "sparsam und ausgewählt in die Arbeit."),
        "datum": "%d.%m.%Y",
    },
    "en": {
        "kopf": ("Chapter/Section", "Tool(s) used", "Purpose", "Representative Prompt(s)", "Outcome / Integration into Thesis"),
        "werkzeug": "Claude (Anthropic) in Claude Code with the humanwriting-de plugin (style coach)",
        "prompt": "Check my section with the style coach and point out the passages I should revise.",
        "zweck": {"coach": "Style feedback on my own draft ({b})",
                  "ueberarbeiten": "Stylistic revision of my own draft ({b})"},
        "runden": lambda n: f"{n} measurement round" + ("" if n == 1 else "s"),
        "hinweise": lambda n: f"{n} sentence-level note" + ("" if n == 1 else "s"),
        "ergebnis": {"coach": "{runden}{daten}, {hinweise} without any drafted text passages; "
                              "I checked each note and revised the text in my own words or kept it",
                     "ueberarbeiten": "{runden}{daten}, {hinweise}; Claude rephrased sentences stylistically, "
                                      "content checked with inhalt_check.py and reviewed by me"},
        "bis": "–",
        "hinweis_ueberarbeiten": ("Note: in revision mode the wording comes from Claude. Under the MBS Research Guidelines "
                                  "2026 (Part C, 4.2), AI-generated formulations may only be used sparingly and selectively, "
                                  "even when documented."),
        "datum": "%Y-%m-%d",
    },
}


def bereich(typ: str) -> str:
    for name, _, praefixe in BEREICHE:
        if any(typ.startswith(p) for p in praefixe):
            return name
    return "stil"


def bereich_name(name: str, sprache: str) -> str:
    i = 0 if sprache == "de" else 1
    for n, namen, _ in BEREICHE:
        if n == name:
            return namen[i]
    return STIL[i]


def auswerten(verlauf: dict) -> dict:
    """Messrunden, eindeutige Hinweise je Bereich und Zeitpunkte aus einem Verlauf."""
    messungen = [m for m in verlauf.get("messungen") or [] if isinstance(m, dict)]
    gesehen: set = set()
    je_bereich: dict[str, int] = {}
    for m in messungen:
        for h in m.get("hinweise") or []:
            if not isinstance(h, dict) or not h.get("typ"):
                continue
            schluessel = (h["typ"], h.get("anfang"), h.get("satz"))
            if schluessel in gesehen:  # derselbe Hinweis in einer späteren Runde zählt einmal
                continue
            gesehen.add(schluessel)
            b = bereich(h["typ"])
            je_bereich[b] = je_bereich.get(b, 0) + 1
    zeiten = []
    for m in messungen:
        try:
            zeiten.append(dt.datetime.fromisoformat(str(m.get("zeit"))))
        except ValueError:
            pass
    reihenfolge = [n for n, _, _ in BEREICHE] + ["stil"]
    bereiche = sorted(je_bereich, key=lambda b: (-je_bereich[b], reihenfolge.index(b)))
    return {"runden": len(messungen), "hinweise": len(gesehen), "bereiche": bereiche, "zeiten": sorted(zeiten)}


def zelle(text: str) -> str:
    return " ".join(str(text).replace("|", "/").split())


def zeile(auswertung: dict, kapitel: str, werkzeug: str, prompts: list[str], modus: str, sprache: str,
          ersatz_datum: dt.date | None = None) -> list[str]:
    t = TEXTE[sprache]
    namen = [bereich_name(b, sprache) for b in auswertung["bereiche"][:3]]
    zweck = t["zweck"][modus].format(b=", ".join(namen) if namen else STIL[0 if sprache == "de" else 1])
    tage = sorted({z.date() for z in auswertung["zeiten"]}) or ([ersatz_datum] if ersatz_datum else [])
    daten = ""
    if tage:
        erst, letzt = tage[0].strftime(t["datum"]), tage[-1].strftime(t["datum"])
        daten = f" ({erst})" if erst == letzt else f" ({erst}{t['bis']}{letzt})"
    ergebnis = t["ergebnis"][modus].format(runden=t["runden"](auswertung["runden"]), daten=daten,
                                           hinweise=t["hinweise"](auswertung["hinweise"]))
    prompt_text = " · ".join(f"„{p}“" if sprache == "de" else f"“{p}”" for p in prompts)
    return [zelle(kapitel), zelle(werkzeug), zelle(zweck), zelle(prompt_text), zelle(ergebnis)]


def tabelle(zeilen: list[list[str]], sprache: str) -> str:
    kopf = TEXTE[sprache]["kopf"]
    aus = ["| " + " | ".join(kopf) + " |", "|" + "---|" * len(kopf)]
    aus += ["| " + " | ".join(z) + " |" for z in zeilen]
    return "\n".join(aus)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Zeilen für die Dokumentationstabelle der KI-Nutzung aus Coach-Verläufen.")
    ap.add_argument("verlaeufe", nargs="+", help="Coach-Verläufe (*.coach.json)")
    ap.add_argument("--kapitel", action="append", default=[],
                    help="Kapitel/Abschnitt je Verlauf in derselben Reihenfolge (Standard: Dateiname)")
    ap.add_argument("--werkzeug", help="Werkzeug inkl. Modellversion, falls bekannt")
    ap.add_argument("--prompt", action="append", default=[], help="repräsentativer Prompt (mehrfach möglich)")
    ap.add_argument("--modus", choices=("coach", "ueberarbeiten"), default="coach",
                    help="coach = Nutzer formuliert selbst (Standard), ueberarbeiten = Claude hat umformuliert")
    ap.add_argument("--sprache", choices=("de", "en"), default="de", help="Sprache der Tabelle (Standard: de)")
    args = ap.parse_args(argv)
    t = TEXTE[args.sprache]
    zeilen = []
    for i, pfad in enumerate(args.verlaeufe):
        try:
            with open(pfad, encoding="utf-8") as f:
                verlauf = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"{pfad}: kein lesbarer Coach-Verlauf ({e})", file=sys.stderr)
            return 1
        if i < len(args.kapitel):
            kapitel = args.kapitel[i]
        else:
            name = os.path.basename(str(verlauf.get("datei") or pfad))
            kapitel = name.split(".")[0]
        ersatz = dt.date.fromtimestamp(os.path.getmtime(pfad))  # ältere Verläufe ohne Zeitstempel: letzte Änderung
        zeilen.append(zeile(auswerten(verlauf), kapitel, args.werkzeug or t["werkzeug"], args.prompt or [t["prompt"]],
                            args.modus, args.sprache, ersatz))
    print(tabelle(zeilen, args.sprache))
    if args.modus == "ueberarbeiten":
        print("\n" + t["hinweis_ueberarbeiten"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
