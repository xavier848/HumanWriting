#!/usr/bin/env python3
"""PDF -> sauberer Fließtext für die Kalibrierung.

Wandelt eine wissenschaftliche Arbeit (Hausarbeit, Bachelorarbeit, Artikel) in
Text um und behält nur Fließtext-Prosa. Nutzt `pdftotext -bbox-layout` und
arbeitet zeilenbasiert: Absätze werden aus Zeilenabständen, Einzügen,
Zeilenhöhe (≈ Schriftgröße) und kurzen Endzeilen rekonstruiert. Das funktioniert
auch bei 1,5-zeiligem Satz, bei dem pdftotext jede Zeile als eigenen Block
liefert (typisch für Word-Abschlussarbeiten).

Entfernt: Kopf-/Fußzeilen, Seitenzahlen, Inhaltsverzeichnis, Überschriften,
Abbildungs-/Tabellenbeschriftungen, Fußnoten (auch hochgestellte Fußnotenziffern
im Text), Aufzählungen, Blockzitate, Interview-Transkripte, Literaturangaben,
Lizenzseiten, alles vor der Einleitung und ab Literaturverzeichnis/Anhang.
Repariert: Silbentrennung (auch U+2010/U+00AD), Ligaturen (ﬀ, ﬁ, ﬂ …),
durch Sperrsatz zerrissene Wörter.

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
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field

NS = "{http://www.w3.org/1999/xhtml}"

END_WOERTER = (
    r"Literaturverzeichnis|Literatur-?\s*und\s*Quellenverzeichnis|Quellen-?\s*und\s*Literaturverzeichnis|"
    r"Quellenverzeichnis|Quellen|Literatur|Bibliographie|Bibliografie|Referenzen|References|Bibliography|"
    r"Anhang|Anhänge|Anhangsverzeichnis|Anlagen?|Appendix|Eidesstattliche\s+(Erklärung|Versicherung)|"
    r"Ehrenwörtliche\s+Erklärung|Selbst(st)?ändigkeitserklärung|Erklärung(\s+zur\s+\w+)?|Versicherung\s+über\s+.*|"
    r"Abkürzungsverzeichnis|Abkürzungen|Glossar|Danksagung|Über\s+die\s+Autor(in|en|innen)?|Zu\s+den\s+Autor(in|en|innen)?"
)
END_HEADINGS = re.compile(
    rf"^\s*(?:[0-9IVX]+(\.\d+)*\.?\s*)?(?:{END_WOERTER}|(?:Anhang|Anlagen?|Appendix)\s*(?:[A-Z0-9]{{1,3}}\b)?\s*[:–-]?.*)\s*:?\s*$",
    re.IGNORECASE,
)
END_IM_ABSATZ = re.compile(
    r"^\s*(?:[0-9IVX]+\.?\s*)?(Literaturverzeichnis|Quellenverzeichnis|Literatur|Quellen|Bibliographie|Bibliografie|References)\s+"
    r"[A-ZÄÖÜ][\wäöüß'-]+,\s",
    re.IGNORECASE,
)
START_HEADINGS = re.compile(
    r"^\s*(?:[0-9]+\.?|[IVX]+\.?|Kapitel\s+1:?)?\s*(Einleitung|Einführung|Problemstellung|"
    r"Ausgangslage|Hinführung(\s+zum\s+Thema)?|Motivation|Problemstellung\s+und\s+Zielsetzung|Vorbemerkung(en)?)\b",
    re.IGNORECASE,
)
CAPTION = re.compile(
    r"^\s*(Abbildung|Abb\.|Tabelle|Tab\.|Grafik|Quelle\s*:|Darstellung|Figure|Table|Anmerkung\s*:|Anm\.\s*:)\s*\d*",
    re.IGNORECASE,
)
TOC_LINE = re.compile(r"(\.\s?){4,}\s*\d+\s*$|…+\s*\d+\s*$|\s\.{3,}\s?\d+|(\s\.){3,}")
LICENSE = re.compile(
    r"Nutzungsbedingungen|Terms of use|Deposit-Lizenz|Deposit Licen[cs]e|Creative Commons|"
    r"creativecommons\.org|Empfohlene Zitierung|Suggested Citation|Dieser Beitrag ist mit Zustimmung|"
    r"www\.ssoar\.info|urn:nbn:de|Diese Version ist zitierbar|Alle Rechte vorbehalten|ISSN\s?\d|ISBN\s?\d|"
    r"[\w.+-]+@[\w-]+\.[\w.]+|\bTel\.?\s*:|\bFax\s*:|Download unter|Die vertretene Auffassung|"
    r"Gewährt wird ein nicht exklusives|Urheberrechtshinweise|nicht-kommerziellen Gebrauch bestimmt",
    re.IGNORECASE,
)
URL = re.compile(r"https?://\S+|www\.\S+")
# Fußnotenziffer direkt am Wort ("Unternehmen12", "Unternehmen.12"), aber nicht in Zahlen ("0,67", "Web 2.0", "CO2")
INLINE_FOOTNOTE = re.compile(r"(?:(?<=[a-zäöüß)][.,;:!?])|(?<=[a-zäöüß)\"“”»]))(\d{1,3})(?=[\s,.;:]|$)")
HYPHEN_KEEP_NEXT = {"und", "oder", "bzw.", "sowie", "als", "bis", "noch", "wie", "u.", "&"}
TERMINAL = re.compile(r"[.!?:\"“”»«)]$")
BULLET = re.compile(r"^\s*([•·▪■□◦○●➢➤►✓✔\-–—*]|\d{1,2}[.)]\s|[a-z]\)\s)\s*")
LIGATUREN = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
TRENNSTRICHE = "-‐­"
LITERATUR_EINTRAG = re.compile(
    r"^[A-ZÄÖÜ][\wäöüß'-]+,\s?(?:[A-ZÄÖÜ]\.|[A-ZÄÖÜ][a-zäöü]+).{0,150}?(?:\(?\b(?:1[89]|20)\d{2}[a-z]?\b\)?)"
)
# Beginn eines Literaturverzeichnisses mitten im Absatz: "… Satzende. Birkel, P. & Birkel, C. (2002)."
LITERATUR_START = re.compile(r"(?<=[.!?])\s+[A-ZÄÖÜ][\wäöüß'-]+,\s(?:[A-ZÄÖÜ]\.\s?){1,3}(?:[&/,;]|\(\d{4}|u\.|und\b)")
TRANSKRIPT = re.compile(r"^\s*(?:[A-Z]{1,3}\d?|Interviewer(?:in)?|Befragte[r]?)\s?:\s|#\d{2}:\d{2}")


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
class Page:
    w: float
    h: float
    lines: list[Line] = field(default_factory=list)


@dataclass
class Gruppe:
    page: int
    page_h: float
    lines: list[Line] = field(default_factory=list)

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


def normalisiere_text(t: str) -> str:
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"\u00ad(?=\w)", "-", t)  # weiches Trennzeichen mitten im Wort ist ein echter Bindestrich ("BSD­Unix")
    for a, b in LIGATUREN.items():
        t = t.replace(a, b)
    return re.sub(r"[-]", "", t)  # Private-Use-Zeichen (Wingdings-Aufzählungszeichen)


def parse_bbox(path: str) -> list[Page]:
    out = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", "-bbox-layout", path, "-"],
        check=True,
        capture_output=True,
    )
    xml = out.stdout.decode("utf-8", errors="replace")
    xml = re.sub(r"<!DOCTYPE[^>]*>", "", xml, count=1)
    xml = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]", "", xml)
    xml = re.sub(r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", xml)
    root = ET.fromstring(xml)
    pages: list[Page] = []
    for page in root.iter(NS + "page"):
        p = Page(float(page.get("width", "595")), float(page.get("height", "842")))
        for ln in page.iter(NS + "line"):
            woerter = []
            for w in ln.iter(NS + "word"):
                t = normalisiere_text(w.text or "")
                if not t.strip():
                    continue
                woerter.append((float(w.get("xMin")), float(w.get("yMin")), float(w.get("xMax")), float(w.get("yMax")), t))
            if not woerter:
                continue
            hoehen = sorted(w[3] - w[1] for w in woerter)
            med_h = hoehen[len(hoehen) // 2]
            ly1 = statistics.median(w[3] for w in woerter)
            teile: list[list] = []
            for wx0, wy0, wx1, wy1, t in woerter:
                wh = wy1 - wy0
                # hochgestellte Fußnotenziffer als eigenes Wort: kleiner und angehoben
                if re.fullmatch(r"\d{1,3}[,)]?", t) and len(woerter) > 1 and (wh < 0.8 * med_h or wy1 < ly1 - 0.25 * med_h):
                    continue
                if teile and 0 <= wx0 - teile[-1][2] < 0.12 * med_h:  # Sperrsatz-/Ligatur-Lücke: zusammenziehen
                    teile[-1][2] = wx1
                    teile[-1][4] += t
                else:
                    teile.append([wx0, wy0, wx1, wy1, t])
            if not teile:
                continue
            text = " ".join(t[4] for t in teile)
            p.lines.append(Line(min(t[0] for t in teile), float(ln.get("yMin")), max(t[2] for t in teile), float(ln.get("yMax")), text))
        pages.append(p)
    return pages


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
        if out[-1] in TRENNSTRICHE and not out.endswith((" -", "--")):
            stamm = out.rstrip(TRENNSTRICHE)
            nxt = line.split(" ", 1)[0]
            prev_word = stamm.rsplit(" ", 1)[-1]
            silbe = prev_word.islower() and len(prev_word) <= 3  # "so- wie", "den- noch"
            if nxt and nxt[0].islower() and (nxt not in HYPHEN_KEEP_NEXT or silbe) and len(prev_word) > 1:
                out = stamm + line  # Silbentrennung: "Unter-" + "nehmen"
            elif nxt[:1].isupper() and len(prev_word) > 1:
                out = stamm + "-" + line  # Bindestrich-Kompositum: "Marketing-" + "Strategie"
            else:
                out = stamm + "- " + line  # "Ein-" + "und Ausgang"
        else:
            out = out + " " + line
    out = out.replace("­", "")
    return re.sub(r"\s+", " ", out).strip()


def gewichteter_modus(werte: list[tuple[float, int]]) -> float:
    c: Counter[float] = Counter()
    for h, n in werte:
        c[round(h * 2) / 2] += n
    return c.most_common(1)[0][0] if c else 10.0


def gruppiere(pages: list[Page], body_h: float, zeilenabstand: float) -> list[Gruppe]:
    """Fasst Zeilen zu Absätzen, Überschriften und Fußnoten zusammen."""
    gruppen: list[Gruppe] = []
    absatz_luecke = zeilenabstand + max(0.45 * body_h, 2.5)
    for pno, page in enumerate(pages):
        body = [l for l in page.lines if abs(l.h - body_h) <= 0.15 * body_h]
        if body:
            xs0 = sorted(l.x0 for l in body)
            xs1 = sorted(l.x1 for l in body)
            links = xs0[len(xs0) // 10]
            rechts = xs1[int(len(xs1) * 0.9)]
        else:
            links, rechts = 0.1 * page.w, 0.9 * page.w
        breite = max(1.0, rechts - links)
        aktuell: Gruppe | None = None
        for ln in page.lines:
            neu = aktuell is None
            if not neu:
                prev = aktuell.lines[-1]
                luecke = ln.y0 - prev.y1
                if abs(ln.h - prev.h) > 0.15 * max(ln.h, prev.h):
                    neu = True  # andere Schriftgröße
                elif ln.y0 < prev.y0 - 1 or abs(ln.x0 - prev.x0) > 0.35 * page.w:
                    neu = True  # Spalten- oder Blocksprung
                elif luecke > absatz_luecke * (prev.h / body_h if body_h else 1):
                    neu = True  # Absatzabstand
                elif TERMINAL.search(prev.text) and prev.x1 < rechts - 0.12 * breite:
                    neu = True  # kurze Endzeile mit Satzende
                elif TERMINAL.search(prev.text) and links + 0.012 * page.w < ln.x0 < links + 0.1 * page.w and ln.x0 > prev.x0 + 3:
                    neu = True  # Erstzeileneinzug
                elif BULLET.match(ln.text) and not BULLET.match(prev.text):
                    neu = True
            if neu:
                aktuell = Gruppe(page=pno, page_h=page.h)
                gruppen.append(aktuell)
            aktuell.lines.append(ln)
    return gruppen


def ueberschrift_norm(t: str) -> str:
    # Kapitälchen: "1 E INLEITUNG" -> "1 EINLEITUNG"
    return re.sub(r"\b([A-ZÄÖÜ]) ([A-ZÄÖÜ]{2,})\b", r"\1\2", t)


def is_footnote_text(par: str) -> bool:
    if re.match(r"^\d{1,3}\s?[A-ZÄÖÜa-zäöü(„\"]", par) and not re.match(r"^\d{4}", par):
        if len(par.split()) < 70 or re.search(r"\b(vgl\.|Vgl\.|ebd\.|Ebd\.|S\.\s?\d|a\.a\.O\.|zit\. n\.)", par):
            return True
    if re.match(r"^(Vgl\.|vgl\.|Ebd\.|ebd\.|Siehe|siehe|Zit\.)", par) and len(par.split()) < 70:
        return True
    return False


def prose_problem(par: str) -> str | None:
    """Gibt den Grund zurück, warum ein Absatz keine Fließtext-Prosa ist (oder None)."""
    words = par.split()
    if len(words) < 25:
        return "zu_kurz"
    if not TERMINAL.search(par):
        return "kein_satzende"
    if par[0].islower():
        return "fragment"
    letters = sum(c.isalpha() for c in par)
    if letters / max(1, len(par)) < 0.72:
        return "zeichen"
    digits = sum(c.isdigit() for c in par)
    if digits / max(1, len(par)) > 0.08:
        return "zahlen"
    if len(URL.findall(par)) > 2:
        return "urls"
    if LICENSE.search(par):
        return "lizenz"
    if LITERATUR_EINTRAG.match(par) or len(re.findall(r"\(\d{4}[a-z]?\)\s*[:.,]", par)) >= 2:
        return "literatur"
    if re.match(r"^\[\d{1,3}\]\s", par) or re.match(r"^[A-ZÄÖÜ][\w .&/-]{1,90}\(\d{4}[a-z]?\)\.\s", par):
        return "literatur"
    if re.search(r"(Abgerufen|Zugriff|Zugegriffen|Stand)\s+(am|:)\s*\d", par) and URL.search(par):
        return "literatur"
    if len(re.findall(r"\b(ebenda|ebd\.|a\.\s?a\.\s?O\.)", par)) >= 3:
        return "fussnotentext"
    if re.search(r"[\U0001D400-\U0001D7FF]", par) or len(re.findall(r"[∑∈≤≥→∏√∫≈≠±×÷]", par)) >= 3:
        return "formel"
    if len(re.findall(r"\s-\s", par)) >= 3 or len(re.findall(r"\b(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+\d{4}\s*:", par)) >= 3:
        return "liste"
    einzelne = re.findall(r"(?<![\w.])[b-hj-np-tv-zäöü](?![\w.])", par)
    if len(einzelne) >= 3:
        return "artefakte"  # Kerning-/Doppelschicht-Reste: "un d", "mit t d dem"
    if re.match(r"^(Mein(e)?\s+(herzlich\w*|besonder\w*|groß\w*)?\s*Dank|Ich\s+möchte\s+mich\b.*\bbedanken|Ich\s+(bedanke\s+mich|danke)\b|Vielen\s+Dank|An\s+dieser\s+Stelle\s+(möchte|danke)|Danken\s+möchte|Ich\s+versichere|Hiermit\s+(erkläre|versichere)|Hinweis\s+im\s+Sinne\s+des\s+Gleichbehandlungs|Aus\s+Gründen\s+der\s+(besseren\s+)?Lesbarkeit)", par):
        return "vorspann"
    if TRANSKRIPT.match(par) or re.search(r"#\d{2}:\d{2}", par):
        return "transkript"
    if re.match(r"^[„\"»]", par) and re.search(r"[“\"«]\s*(\([^)]*\))?\s*[.]?$", par[-80:]):
        return "blockzitat"
    if BULLET.match(par):
        return "liste"
    funktion = len(re.findall(r"\b(der|die|das|den|dem|des|ein|eine|einer|und|oder|ist|sind|wird|werden|nicht|mit|von|zu|in|im|auf|für|sich|dass|es|wie|als|auch)\b", par))
    if funktion / len(words) < 0.12:
        return "keine_saetze"  # Abkürzungs-/Namenslisten, Tabellenreste
    en = len(re.findall(r"\b(the|and|of|to|in|is|that|for|with)\b", par))
    de = len(re.findall(r"\b(der|die|das|und|ist|nicht|mit|von|zu|den|sich)\b", par))
    if en > de:
        return "englisch"
    return None


def extract(path: str) -> tuple[str, dict]:
    pages = parse_bbox(path)
    n_pages = len(pages)
    roh_woerter = sum(len(l.text.split()) for p in pages for l in p.lines)
    # Schriftgröße des Fließtexts aus dem vorderen Teil (Anhänge mit verkleinerten Seiten ignorieren)
    vorne = pages[: max(3, int(0.7 * n_pages))]
    body_h = gewichteter_modus([(l.h, len(l.text.split())) for p in vorne for l in p.lines])
    luecken = []
    for p in vorne:
        for a, b in zip(p.lines, p.lines[1:]):
            if abs(a.h - body_h) <= 0.1 * body_h and abs(b.h - body_h) <= 0.1 * body_h and abs(a.x0 - b.x0) < 30 and b.y0 > a.y0:
                g = b.y0 - a.y1
                if -2 < g < 3 * body_h:
                    luecken.append(g)
    zeilenabstand = statistics.median(luecken) if luecken else 0.3 * body_h
    gruppen = gruppiere(pages, body_h, zeilenabstand)

    # Wiederkehrende Kopf-/Fußzeilen (normalisiert, Ziffern -> #)
    rand = Counter()
    for g in gruppen:
        if g.y1 < 0.12 * g.page_h or g.y0 > 0.88 * g.page_h:
            rand[re.sub(r"\d+", "#", " ".join(l.text for l in g.lines).lower())] += 1
    wiederholt = {k for k, v in rand.items() if v >= max(3, int(0.2 * n_pages))}

    items: list[tuple[str, str]] = []  # ("H", text) | ("P", text) | ("L", text)
    dropped = Counter()
    for g in gruppen:
        text_all = " ".join(l.text for l in g.lines)
        norm = re.sub(r"\d+", "#", text_all.lower())
        rel_top, rel_bot = g.y0 / g.page_h, g.y1 / g.page_h
        if norm in wiederholt or ((rel_bot < 0.08 or rel_top > 0.93) and g.n_words < 20):
            dropped["kopf_fuss"] += 1
            continue
        if re.fullmatch(r"(Seite\s*)?[-–]?\s*[0-9IVXivx]{1,5}\s*[-–]?(\s*(von|/)\s*\d+)?", text_all.strip()):
            dropped["seitenzahl"] += 1
            continue
        if g.med_h < 0.86 * body_h and rel_top > 0.45:
            dropped["fussnote"] += 1
            continue
        par = join_lines([l.text for l in g.lines])
        if not par:
            continue
        if TOC_LINE.search(par):
            dropped["inhaltsverzeichnis"] += 1
            continue
        n_w = len(par.split())
        if BULLET.match(par) and not re.match(r"^\d{1,2}\.\s+[A-ZÄÖÜ]", par):
            items.append(("L", par))
            continue
        if g.med_h > 1.12 * body_h and len(g.lines) <= 3:
            items.append(("H", ueberschrift_norm(par)))
            continue
        if len(g.lines) <= 2 and n_w <= 14 and not TERMINAL.search(par):
            items.append(("H", ueberschrift_norm(par)))
            continue
        if re.match(r"^\d+(\.\d+)*\.?\s+\S", par) and n_w <= 16 and not par.endswith("."):
            items.append(("H", ueberschrift_norm(par)))
            continue
        items.append(("P", par))

    # Start: erste "Einleitung"-Überschrift in der vorderen Hälfte, auf die Fließtext folgt
    start = 0
    grenze = max(10, int(len(items) * 0.5))
    for i, (kind, t) in enumerate(items[:grenze]):
        if kind == "H" and START_HEADINGS.match(t) and len(t.split()) <= 8:
            if any(k == "P" and prose_problem(x) is None for k, x in items[i + 1 : i + 8]):
                start = i + 1
                break
    # Ende: erste End-Überschrift nach dem Start (das Inhaltsverzeichnis liegt davor); ohne Start nach 15 %
    end = len(items)
    prosa_bisher = 0
    for i in range(start if start else int(len(items) * 0.15), len(items)):
        kind, t = items[i]
        if kind == "P":
            if END_IM_ABSATZ.match(t) and prosa_bisher > 3:
                end = i
                break
            if prose_problem(t) is None:
                prosa_bisher += 1
        if kind == "H" and END_HEADINGS.match(t) and prosa_bisher > 3:
            end = i
            break
    body = items[start:end]

    # Über Seiten-/Fußnotengrenzen gerissene Absätze wieder verbinden
    paras: list[str] = []
    for kind, t in body:
        if kind != "P":
            paras.append("\x00" + kind)
            continue
        letzte = paras[-1] if paras else "\x00H"
        if not letzte.startswith("\x00"):
            offen = not TERMINAL.search(letzte)
            unbalanciert = letzte.count("(") > letzte.count(")")
            if (offen and (t[:1].islower() or len(letzte.split()) >= 12)) or unbalanciert:
                paras[-1] = join_lines([letzte, t])
                continue
        paras.append(t)

    if start == 0 and paras and not paras[0].startswith("\x00"):
        paras = paras[1:]  # ohne erkannte Einleitung: erster Absatz ist oft ein Fragment
    kept: list[str] = []
    for p in paras:
        if p.startswith("\x00"):
            continue
        lit = LITERATUR_START.search(p)
        if lit:
            p = p[: lit.start()]  # ab hier Literaturverzeichnis ohne erkannte Überschrift
            dropped["literatur_abgeschnitten"] += 1
        if CAPTION.match(p):
            dropped["beschriftung"] += 1
            continue
        if re.match(r"^\d+(\.\d+)*\.?\s+[A-ZÄÖÜ]", p):
            dropped["ueberschrift_verklebt"] += 1  # Abschnittsnummer + Überschrift mit dem Absatz verklebt
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
        p = re.sub(r"\b([A-ZÄÖÜ]) ([A-ZÄÖÜ]{3,})\b", r"\1\2", p)  # Kapitälchen im Fließtext
        p = re.sub(r"(?<=[a-zäöüß]),(?=[A-Za-zÄÖÜäöüß])", ", ", p)  # fehlendes Leerzeichen nach Komma (enger Blocksatz)
        p = re.sub(r"^(Abstract|Zusammenfassung|Kurzfassung|Einleitung|Einführung|Vorwort|Fazit|Ausblick|Danksagung)\s+(?=[A-ZÄÖÜ][a-zäöü])", "", p)
        grund = prose_problem(p)
        if grund:
            dropped[grund] += 1
            continue
        kept.append(p)
        if lit:
            break

    text = "\n\n".join(kept)
    woerter = len(text.split())
    meta = {
        "source_pdf": path,
        "pages": n_pages,
        "body_line_height": body_h,
        "zeilenabstand": round(zeilenabstand, 2),
        "roh_woerter": roh_woerter,
        "paragraphs_kept": len(kept),
        "words_kept": woerter,
        "anteil_behalten": round(woerter / roh_woerter, 3) if roh_woerter else 0.0,
        "dropped": dict(dropped),
        "start_found": start > 0,
        "end_found": end < len(items),
    }
    if roh_woerter and woerter / roh_woerter < 0.15:
        meta["warnung"] = "Weniger als 15 % des PDF-Textes behalten – Extraktion manuell prüfen."
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
