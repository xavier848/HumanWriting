#!/usr/bin/env python3
"""PDF -> sauberer Fließtext für die Kalibrierung.

Wandelt eine wissenschaftliche Arbeit (Hausarbeit, Bachelorarbeit, Artikel) in
Text um und behält nur Fließtext-Prosa. Nutzt `pdftotext -bbox-layout`, um über
Position und Zeilenhöhe (≈ Schriftgröße) zu erkennen, was Kopf-/Fußzeile,
Fußnote, Überschrift oder normaler Absatz ist.

Entfernt: Kopf-/Fußzeilen, Seitenzahlen, Inhaltsverzeichnis, Überschriften,
Abbildungs-/Tabellenbeschriftungen, Fußnoten, Lizenzseiten, alles vor der
Einleitung und ab Literaturverzeichnis/Anhang/Erklärung.

Ausgabe: Absätze, getrennt durch eine Leerzeile.

    python3 extract_text.py arbeit.pdf -o arbeit.txt [--json meta.json]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field

NS = "{http://www.w3.org/1999/xhtml}"

END_HEADINGS = re.compile(
    r"^\s*(?:[0-9IVX]+\.?\s*)?(Literaturverzeichnis|Literatur-?\s*und\s*Quellenverzeichnis|"
    r"Quellenverzeichnis|Literatur|Bibliographie|Bibliografie|Referenzen|References|"
    r"Anhang|Anhangsverzeichnis|Anlagen?|Eidesstattliche\s+(Erklärung|Versicherung)|"
    r"Ehrenwörtliche\s+Erklärung|Selbst(st)?ändigkeitserklärung|Erklärung|"
    r"Versicherung\s+über\s+.*)\s*:?\s*$",
    re.IGNORECASE,
)
START_HEADINGS = re.compile(
    r"^\s*(?:[0-9]+\.?|[IVX]+\.?|Kapitel\s+1:?)?\s*(Einleitung|Einführung|Problemstellung|"
    r"Ausgangslage|Hinführung(\s+zum\s+Thema)?|Motivation|Problemstellung\s+und\s+Zielsetzung)\b",
    re.IGNORECASE,
)
CAPTION = re.compile(
    r"^\s*(Abbildung|Abb\.|Tabelle|Tab\.|Grafik|Quelle\s*:|Darstellung|Figure|Table|Anmerkung\s*:)\s*\d*",
    re.IGNORECASE,
)
TOC_LINE = re.compile(r"(\.\s?){4,}\s*\d+\s*$|…+\s*\d+\s*$|\s\.{3,}\s?\d+")
LICENSE = re.compile(
    r"Nutzungsbedingungen|Terms of use|Deposit-Lizenz|Deposit Licen[cs]e|Creative Commons|"
    r"creativecommons\.org|Empfohlene Zitierung|Suggested Citation|Dieser Beitrag ist mit Zustimmung|"
    r"www\.ssoar\.info|urn:nbn:de|Diese Version ist zitierbar",
    re.IGNORECASE,
)
URL = re.compile(r"https?://\S+|www\.\S+")
INLINE_FOOTNOTE = re.compile(r"(?<=[A-Za-zÄÖÜäöüß.,;:!?\)\"“”])(\d{1,3})(?=[\s,.;:]|$)")
HYPHEN_KEEP_NEXT = {"und", "oder", "bzw.", "sowie", "als", "bis", "noch", "wie", "u.", "&"}
TERMINAL = re.compile(r"[.!?:\"“”»«)]$")


@dataclass
class Line:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@dataclass
class Block:
    page: int
    page_h: float
    lines: list[Line] = field(default_factory=list)

    @property
    def x0(self) -> float:
        return min(l.x0 for l in self.lines)

    @property
    def x1(self) -> float:
        return max(l.x1 for l in self.lines)

    @property
    def y0(self) -> float:
        return min(l.y0 for l in self.lines)

    @property
    def y1(self) -> float:
        return max(l.y1 for l in self.lines)

    @property
    def med_h(self) -> float:
        return statistics.median(l.h for l in self.lines)

    @property
    def n_words(self) -> int:
        return sum(len(l.text.split()) for l in self.lines)


def parse_bbox(path: str) -> list[Block]:
    out = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", "-bbox-layout", path, "-"],
        check=True,
        capture_output=True,
    )
    xml = out.stdout.decode("utf-8", errors="replace")
    xml = re.sub(r"<!DOCTYPE[^>]*>", "", xml, count=1)
    xml = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]", "", xml)
    xml = re.sub(r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", xml)
    root = ET.fromstring(xml)
    blocks: list[Block] = []
    for pno, page in enumerate(root.iter(NS + "page")):
        ph = float(page.get("height", "842"))
        for blk in page.iter(NS + "block"):
            b = Block(page=pno, page_h=ph)
            for ln in blk.iter(NS + "line"):
                words = [w.text or "" for w in ln.iter(NS + "word")]
                text = " ".join(w for w in words if w)
                if not text.strip():
                    continue
                b.lines.append(
                    Line(float(ln.get("xMin")), float(ln.get("yMin")), float(ln.get("xMax")), float(ln.get("yMax")), text)
                )
            if b.lines:
                blocks.append(b)
    return blocks


def join_lines(texts: list[str]) -> str:
    """Fügt Zeilen zusammen und hebt Silbentrennungen am Zeilenende auf."""
    out = ""
    for raw in texts:
        line = raw.strip()
        if not line:
            continue
        if not out:
            out = line
            continue
        if out.endswith("-") and not out.endswith(" -") and not out.endswith("--"):
            nxt = line.split(" ", 1)[0]
            prev_word = out.rsplit(" ", 1)[-1]
            if nxt and nxt[0].islower() and nxt not in HYPHEN_KEEP_NEXT and len(prev_word) > 2:
                out = out[:-1] + line  # Silbentrennung: "Unter-" + "nehmen"
            elif nxt[:1].isupper() and len(prev_word) > 2:
                out = out + line  # Bindestrich-Kompositum: "Marketing-" + "Strategie"
            else:
                out = out + " " + line  # "Ein-" + "und Ausgang"
        else:
            out = out + " " + line
    return re.sub(r"\s+", " ", out).strip()


def body_line_height(blocks: list[Block]) -> float:
    c: Counter[float] = Counter()
    for b in blocks:
        for l in b.lines:
            c[round(l.h * 2) / 2] += len(l.text.split())
    return c.most_common(1)[0][0] if c else 10.0


def split_paragraphs(b: Block) -> list[list[Line]]:
    """Teilt einen Block an Absatzgrenzen (Leerraum, Einzug, kurze Endzeile)."""
    lines = sorted(b.lines, key=lambda l: (round(l.y0, 0), l.x0))
    if len(lines) == 1:
        return [lines]
    gaps = [lines[i + 1].y0 - lines[i].y1 for i in range(len(lines) - 1)]
    pos_gaps = [g for g in gaps if g > -2]
    med_gap = statistics.median(pos_gaps) if pos_gaps else 2.0
    width = b.x1 - b.x0
    paras: list[list[Line]] = [[lines[0]]]
    for i in range(1, len(lines)):
        prev, cur = lines[i - 1], lines[i]
        gap = cur.y0 - prev.y1
        new = False
        if gap > med_gap + 0.6 * prev.h:
            new = True
        elif TERMINAL.search(prev.text) and prev.x1 < b.x1 - 0.12 * width:
            new = True  # kurze Endzeile mit Satzende
        elif TERMINAL.search(prev.text) and cur.x0 > b.x0 + 8 and cur.x0 < b.x0 + 40:
            new = True  # Erstzeileneinzug
        if new:
            paras.append([cur])
        else:
            paras[-1].append(cur)
    return paras


def is_footnote_text(par: str) -> bool:
    if re.match(r"^\d{1,3}\s?[A-ZÄÖÜa-zäöü(„\"]", par) and not re.match(r"^\d{4}", par):
        if len(par.split()) < 70 or re.search(r"\b(vgl\.|Vgl\.|ebd\.|Ebd\.|S\.\s?\d|a\.a\.O\.|zit\. n\.)", par):
            return True
    if re.match(r"^(Vgl\.|vgl\.|Ebd\.|ebd\.|Siehe|siehe|Zit\.)", par) and len(par.split()) < 70:
        return True
    return False


def prose_ok(par: str) -> bool:
    words = par.split()
    if len(words) < 25:
        return False
    if not TERMINAL.search(par):
        return False
    if par[0].islower():
        return False
    letters = sum(c.isalpha() for c in par)
    if letters / max(1, len(par)) < 0.72:
        return False
    digits = sum(c.isdigit() for c in par)
    if digits / max(1, len(par)) > 0.08:
        return False
    if len(URL.findall(par)) > 2:
        return False
    if LICENSE.search(par):
        return False
    # Literaturangaben: viele "(Jahr):" bzw. "Verlag" bei kurzer Länge
    if len(re.findall(r"\(\d{4}[a-z]?\)\s*[:.]", par)) >= 2:
        return False
    # Englischer Absatz (Abstract)
    en = len(re.findall(r"\b(the|and|of|to|in|is|that|for|with)\b", par))
    de = len(re.findall(r"\b(der|die|das|und|ist|nicht|mit|von|zu|den|sich)\b", par))
    if en > de:
        return False
    return True


def extract(path: str) -> tuple[str, dict]:
    blocks = parse_bbox(path)
    body_h = body_line_height(blocks)
    n_pages = max((b.page for b in blocks), default=-1) + 1

    # Wiederkehrende Kopf-/Fußzeilen (normalisiert, Ziffern -> #)
    edge = Counter()
    for b in blocks:
        if b.y1 < 0.1 * b.page_h or b.y0 > 0.9 * b.page_h:
            edge[re.sub(r"\d+", "#", " ".join(l.text for l in b.lines).lower())] += 1
    repeated = {k for k, v in edge.items() if v >= max(3, int(0.25 * n_pages))}

    items: list[tuple[str, str]] = []  # ("H", text) | ("P", text)
    dropped = Counter()
    for b in blocks:
        text_all = " ".join(l.text for l in b.lines)
        norm = re.sub(r"\d+", "#", text_all.lower())
        rel_top, rel_bot = b.y0 / b.page_h, b.y1 / b.page_h
        if norm in repeated or ((rel_bot < 0.08 or rel_top > 0.93) and b.n_words < 20):
            dropped["kopf_fuss"] += 1
            continue
        if re.fullmatch(r"(Seite\s*)?[-–]?\s*[0-9IVXivx]{1,5}\s*[-–]?", text_all.strip()):
            dropped["seitenzahl"] += 1
            continue
        if b.med_h < 0.86 * body_h and rel_top > 0.45:
            dropped["fussnote"] += 1
            continue
        if b.med_h > 1.12 * body_h and len(b.lines) <= 3:
            items.append(("H", join_lines([l.text for l in b.lines])))
            continue
        for para_lines in split_paragraphs(b):
            par = join_lines([l.text for l in para_lines])
            if not par:
                continue
            words = par.split()
            if TOC_LINE.search(par):
                dropped["inhaltsverzeichnis"] += 1
                continue
            if len(words) <= 14 and not TERMINAL.search(par):
                items.append(("H", par))
                continue
            if re.match(r"^\d+(\.\d+)*\.?\s+\S", par) and len(words) <= 16 and not par.endswith("."):
                items.append(("H", par))
                continue
            items.append(("P", par))

    # Start: erste "Einleitung"-Überschrift, auf die Fließtext folgt
    start = 0
    for i, (kind, t) in enumerate(items):
        if kind == "H" and START_HEADINGS.match(t) and len(t.split()) <= 8:
            if any(k == "P" and len(x.split()) > 25 for k, x in items[i + 1 : i + 6]):
                start = i + 1
                break
    # Ende: erste End-Überschrift nach 40 % des Dokuments
    end = len(items)
    for i in range(int(len(items) * 0.4), len(items)):
        kind, t = items[i]
        if kind == "H" and END_HEADINGS.match(t):
            end = i
            break
    body = items[start:end]

    # Über Seiten-/Fußnotengrenzen gerissene Absätze wieder verbinden
    paras: list[str] = []
    for kind, t in body:
        if kind == "H":
            paras.append("\x00H")  # Überschrift trennt Absätze
            continue
        unbalanced = paras and paras[-1].count("(") > paras[-1].count(")")
        if paras and paras[-1] != "\x00H" and ((not TERMINAL.search(paras[-1]) and t[:1].islower()) or unbalanced):
            paras[-1] = join_lines([paras[-1], t])
        else:
            paras.append(t)

    if start == 0 and paras and paras[0] != "\x00H":
        paras = paras[1:]  # ohne erkannte Einleitung: erster Absatz ist oft ein Fragment
    kept: list[str] = []
    for p in paras:
        if p == "\x00H":
            continue
        # Literaturverzeichnis, das mit dem letzten Absatz verklebt ist
        m = re.search(r"\s(Literaturverzeichnis|Literatur|Quellenverzeichnis)\s+[A-ZÄÖÜ][a-zäöü]+,\s", p)
        if m:
            p = p[: m.start()]
        if CAPTION.match(p):
            dropped["beschriftung"] += 1
            continue
        if re.match(r"^\d+(\.\d+)*\.?\s+[A-ZÄÖÜ]", p):
            # Abschnittsnummer + Überschrift ohne Abstand mit dem Absatz verklebt
            dropped["ueberschrift_verklebt"] += 1
            continue
        first = re.split(r"(?<=[.!?])\s", p, maxsplit=1)[0]
        if ")" in first and ("(" not in first or first.index(")") < first.index("(")):
            dropped["fragment"] += 1  # beginnt mitten in einer Klammer
            continue
        if is_footnote_text(p):
            dropped["fussnote"] += 1
            continue
        p = INLINE_FOOTNOTE.sub("", p)
        p = re.sub(r"\s+([.,;:!?])", r"\1", p)
        if not prose_ok(p):
            dropped["keine_prosa"] += 1
            continue
        kept.append(p)

    text = "\n\n".join(kept)
    meta = {
        "source_pdf": path,
        "pages": n_pages,
        "body_line_height": body_h,
        "paragraphs_kept": len(kept),
        "words_kept": len(text.split()),
        "dropped": dict(dropped),
        "start_found": start > 0,
        "end_found": end < len(items),
    }
    return text, meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("-o", "--output", help="Zieldatei (Standard: stdout)")
    ap.add_argument("--json", help="Metadaten als JSON hierhin schreiben")
    args = ap.parse_args()
    text, meta = extract(args.pdf)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
