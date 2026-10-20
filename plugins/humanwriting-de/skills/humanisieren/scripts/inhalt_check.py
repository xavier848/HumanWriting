#!/usr/bin/env python3
"""Inhaltscheck: Hat eine Überarbeitung Inhalte verloren oder neue erfunden?

Vergleicht Original und Überarbeitung deterministisch auf:
  - Zahlen (inkl. Prozent, Jahreszahlen, Kennwerte wie N=849)
  - Quellenverweise ((Müller 2019, S. 12), Müller (2019), vgl. …)
  - wörtliche Zitate in Anführungszeichen
  - Abkürzungen/Akronyme (KMU, EVP, …)
  - Fachbegriffe (Inhaltswörter, die im Original mehrfach vorkommen)
  - Überschriften und Fußnotenmarker
  - Umfang (Wörter, Absätze)

Bedeutungsgleichheit einzelner Aussagen kann ein Skript nicht prüfen – das
übernimmt das Modell anhand des Inhaltsinventars. Dieses Skript fängt die
harten Fälle ab, bei denen Umschreiben am häufigsten Fehler einbaut.

    python3 inhalt_check.py original.md neu.md [--format json]

Exit-Code 0 = keine harten Verluste, 1 = Verluste/Erfindungen gefunden.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter

ZAHL_RE = re.compile(r"(?<![\w,.])(?:[A-Za-z]{1,2}\s?=\s?)?\d+(?:[.,]\d+)*(?:\s?(?:%|Prozent|Prozentpunkte|Mio\.|Mrd\.|Euro|EUR|€|\$|USD))?")
ZITAT_KLAMMER_RE = re.compile(r"\((?:[^()]{0,160}?\b(?:1[6-9]\d{2}|20\d{2})[a-z]?\b[^()]{0,80}?|(?:vgl\.|Vgl\.)?\s*ebd\.[^()]{0,40})\)")
ZITAT_NARRATIV_RE = re.compile(r"\b[A-ZÄÖÜ][\wäöüß'-]+(?:\s(?:et al\.|und|&|/)\s?[A-ZÄÖÜ]?[\wäöüß'-]*)?\s\((?:1[6-9]\d{2}|20\d{2})[a-z]?(?:[,:]\s?S\.\s?\d+[f.]*)?\)")
WOERTLICH_RE = re.compile(r"[„\"»“]([^„“\"»«”]{12,}?)[“\"«”]")
AKRONYM_RE = re.compile(r"\b[A-ZÄÖÜ]{2,6}(?:-[A-ZÄÖÜ]{1,6})?s?\b")
FUSSNOTE_RE = re.compile(r"\[\^\d+\]|[¹²³⁴⁵⁶⁷⁸⁹⁰]+")
UEBERSCHRIFT_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$", re.M)
WORT_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+(?:-[A-Za-zÄÖÜäöüß]+)*")

STOP = set(
    """
    der die das den dem des ein eine einer eines einem einen und oder aber doch sondern denn sowie als wie
    wenn dass ob weil da obwohl während nachdem bevor damit sodass indem zu zum zur im in an am auf aus bei
    mit nach seit von vom vor über unter um durch für gegen ohne bis zwischen sich sie es er wir ich man ist
    sind war waren wird werden wurde wurden worden sein hat haben hatte kann können konnte muss müssen soll
    sollte nicht auch noch schon nur sehr so dann dabei dadurch dies diese dieser dieses diesem diesen
    jedoch zudem somit daher deshalb allerdings mehr viele vielen einige jede jeder jedes alle allen
    """.split()
)


def lesen(pfad: str) -> str:
    with open(pfad, encoding="utf-8", errors="replace") as f:
        t = f.read()
    return unicodedata.normalize("NFC", t).replace(" ", " ")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def stamm(w: str) -> str:
    w = w.lower()
    for e in ("ungen", "ung", "heiten", "keiten", "heit", "keit", "ern", "en", "er", "es", "em", "e", "n", "s"):
        if len(w) - len(e) >= 4 and w.endswith(e):
            return w[: -len(e)][:9]
    return w[:9]


def zahlen(t: str) -> Counter:
    ohne_zitate = ZITAT_KLAMMER_RE.sub(" ", t)
    out = Counter()
    for z in ZAHL_RE.findall(ohne_zitate):
        z = norm(z).replace("Prozent", "%").replace(" %", "%")
        out[z] += 1
    return out


def zitate(t: str) -> Counter:
    c = Counter(norm(z) for z in ZITAT_KLAMMER_RE.findall(t))
    c.update(norm(z) for z in ZITAT_NARRATIV_RE.findall(t))
    return c


def woertlich(t: str) -> Counter:
    return Counter(norm(z) for z in WOERTLICH_RE.findall(t) if len(z.split()) >= 3)


def akronyme(t: str) -> Counter:
    return Counter(a.rstrip("s") if len(a) > 2 else a for a in AKRONYM_RE.findall(t))


def begriffe(t: str) -> Counter:
    t = ZITAT_KLAMMER_RE.sub(" ", t)
    return Counter(stamm(w) for w in WORT_RE.findall(t) if w.lower() not in STOP and len(w) >= 5)


def absaetze(t: str) -> int:
    return len([b for b in re.split(r"\n\s*\n", t) if b.strip() and not b.strip().startswith("#")])


def differenz(alt: Counter, neu: Counter):
    fehlt = alt - neu
    neu_dazu = neu - alt
    return sorted(fehlt.elements()), sorted(neu_dazu.elements())


def kontext(t: str, fund: str, breite: int = 70) -> str:
    i = t.find(fund)
    if i < 0:
        return ""
    a, b = max(0, i - breite), min(len(t), i + len(fund) + breite)
    return norm(("…" if a else "") + t[a:b] + ("…" if b < len(t) else ""))


def pruefe(alt: str, neu: str) -> dict:
    res: dict = {"harte_verluste": [], "erfindungen": [], "warnungen": [], "kennzahlen": {}}

    for name, fn, hart in (
        ("Zahl", zahlen, True),
        ("Quellenverweis", zitate, True),
        ("Wörtliches Zitat", woertlich, True),
        ("Abkürzung", akronyme, False),
    ):
        fehlt, dazu = differenz(fn(alt), fn(neu))
        for f in dict.fromkeys(fehlt):
            eintrag = {"typ": name, "wert": f, "kontext_original": kontext(alt, f)}
            (res["harte_verluste"] if hart else res["warnungen"]).append(eintrag)
        for d in dict.fromkeys(dazu):
            eintrag = {"typ": name, "wert": d, "kontext_neu": kontext(neu, d)}
            (res["erfindungen"] if hart else res["warnungen"]).append(eintrag)

    # Fachbegriffe: mehrfach im Original, ganz verschwunden in der Überarbeitung
    b_alt, b_neu = begriffe(alt), begriffe(neu)
    verschwunden = [s for s, n in b_alt.most_common() if n >= 2 and b_neu[s] == 0]
    if verschwunden:
        res["warnungen"].append({"typ": "Begriff verschwunden", "wert": ", ".join(verschwunden[:25]),
                                 "hinweis": "Kommt im Original mehrfach vor, in der Überarbeitung gar nicht mehr. Synonym-Ersatz bei Fachbegriffen vermeiden."})
    neu_haeufig = [s for s, n in b_neu.most_common() if n >= 3 and b_alt[s] == 0]
    if neu_haeufig:
        res["warnungen"].append({"typ": "Neuer häufiger Begriff", "wert": ", ".join(neu_haeufig[:15]),
                                 "hinweis": "Taucht neu und mehrfach auf – prüfen, ob dadurch Inhalt hinzugekommen ist."})

    h_alt, h_neu = UEBERSCHRIFT_RE.findall(alt), UEBERSCHRIFT_RE.findall(neu)
    if [norm(h) for h in h_alt] != [norm(h) for h in h_neu]:
        res["warnungen"].append({"typ": "Überschriften geändert", "wert": f"{len(h_alt)} → {len(h_neu)}",
                                 "hinweis": "Überschriften sollten beim Umschreiben unverändert bleiben."})
    f_alt, f_neu = len(FUSSNOTE_RE.findall(alt)), len(FUSSNOTE_RE.findall(neu))
    if f_alt != f_neu:
        res["harte_verluste"].append({"typ": "Fußnotenmarker", "wert": f"{f_alt} → {f_neu}", "kontext_original": ""})

    w_alt, w_neu = len(WORT_RE.findall(alt)), len(WORT_RE.findall(neu))
    verh = w_neu / w_alt if w_alt else 0
    res["kennzahlen"] = {"woerter_original": w_alt, "woerter_neu": w_neu, "verhaeltnis": round(verh, 3),
                         "absaetze_original": absaetze(alt), "absaetze_neu": absaetze(neu)}
    if verh < 0.85 or verh > 1.2:
        res["warnungen"].append({"typ": "Umfang", "wert": f"{round(100 * verh)} % der Originallänge",
                                 "hinweis": "Starke Längenänderung deutet auf weggelassene oder hinzugefügte Inhalte hin."})
    res["ok"] = not res["harte_verluste"] and not res["erfindungen"]
    return res


def bericht(res: dict) -> str:
    out = ["## Inhaltscheck", ""]
    k = res["kennzahlen"]
    out.append(f"Wörter: {k['woerter_original']} → {k['woerter_neu']} ({round(100 * k['verhaeltnis'])} %) · Absätze: {k['absaetze_original']} → {k['absaetze_neu']}")
    out.append("")
    out.append("✅ **Keine harten Verluste oder Erfindungen.**" if res["ok"] else "❌ **Inhalt verändert – vor dem Weitermachen korrigieren:**")
    for e in res["harte_verluste"]:
        out.append(f"- FEHLT ({e['typ']}): `{e['wert']}` – Original: {e.get('kontext_original', '')}")
    for e in res["erfindungen"]:
        out.append(f"- NEU ({e['typ']}): `{e['wert']}` – Überarbeitung: {e.get('kontext_neu', '')}")
    if res["warnungen"]:
        out.append("\n**Prüfen:**")
        for e in res["warnungen"]:
            out.append(f"- {e['typ']}: {e['wert']}" + (f" – {e['hinweis']}" if e.get("hinweis") else ""))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("original")
    ap.add_argument("neu")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    args = ap.parse_args(argv)
    res = pruefe(lesen(args.original), lesen(args.neu))
    if args.format == "json":
        json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print(bericht(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
