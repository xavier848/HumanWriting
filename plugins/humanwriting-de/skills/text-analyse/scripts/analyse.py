#!/usr/bin/env python3
"""Textanalyse für deutsche Hochschultexte: misst, wie "menschlich" ein Text statistisch ist.

Berechnet Kennzahlen zu Satzlänge, Satzrhythmus, Wortlänge, Silben, Wortschatz,
Satzbau, Zeichensetzung, Absätzen, Lesbarkeit und typischen KI-Mustern und
vergleicht sie mit Referenzwerten aus menschlichen und KI-generierten Texten
(data/baselines.json).

Aufruf:
    python3 analyse.py TEXT.md                 # Bericht (Markdown)
    python3 analyse.py TEXT.md --format json   # maschinenlesbar (für die Umschreib-Schleife)
    python3 analyse.py TEXT.md --stellen 30    # mehr auffällige Stellen zeigen
    cat text.txt | python3 analyse.py -        # von stdin

Eingabeformate: .txt, .md, .docx (ohne Zusatzpakete), .pdf (falls pdftotext installiert).
Nur Python-Standardbibliothek, Python >= 3.8.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import subprocess
import sys
import unicodedata
import zipfile
from collections import Counter

HIER = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HIER, "..", "data"))
STANDARD_BASELINES = os.path.join(DATA, "baselines.json")
STANDARD_MUSTER = os.path.join(DATA, "ki_muster.json")

# ---------------------------------------------------------------------------
# Sprachdaten
# ---------------------------------------------------------------------------

# Abkürzungen (klein, ohne Schlusspunkt). Ein Punkt nach diesen Token beendet keinen Satz.
ABKUERZUNGEN = set(
    """
    abb abs abschn abt adj adv akad allg alt anh anm art aufl ausg bd bde bearb beil bes betr bez bspw bsp
    bzgl bzw ca chr co corp dipl dgl dr dt durchschn ebd eig einschl engl entspr erg erw etc ev evtl exkl
    f ff fa fam frz geb gegr gem ges gest ggf ggü hg hrsg hl i inkl insb int jh jhd jg jr kap kath kfz kl
    lfd lt ltd max min mio mod mrd mt nachf nr no o od orig pkt pl prof proz rd red resp s sen sog sp st std
    str stud tab tel teilw tsd u ua ug usf usw v verf vgl vol vs wg wiss z zb zt zit zzgl zw zus et al
    inc bzgl e d h m vlt ggfs evtl dez jan feb mär apr jun jul aug sep sept okt nov ders dies diess hgg
    """.split()
)

# Wörter, mit denen nach "3." typischerweise ein neuer Satz beginnt (sonst Ordinalzahl: "die 3. Phase")
SATZSTARTER = set(
    """
    die der das dies diese dieser dieses es er sie wir ich man im in auch so zudem daher somit allerdings
    jedoch damit hier dabei danach außerdem ein eine einer zunächst anschließend schließlich insgesamt
    """.split()
)

FUNKTIONSWOERTER = set(
    """
    der die das den dem des ein eine einer eines einem einen und oder aber doch sondern denn sowie bzw als
    wie wenn dass daß ob weil da obwohl während nachdem bevor damit sodass indem falls sofern soweit zu zum
    zur im in ins an am auf aus bei beim mit nach seit von vom vor über unter um durch für gegen ohne bis
    zwischen hinter neben wegen trotz innerhalb außerhalb gemäß laut ich du er sie es wir ihr man sich
    mich mir dich dir uns euch ihn ihm ihnen ihr ihre ihrem ihren ihrer ihres sein seine seinem seinen
    seiner seines mein meine unser unsere dieser diese dieses diesem diesen jener jene welche welcher
    welches welchem welchen kein keine keinem keinen keiner nicht auch noch schon nur sehr so dann dort
    hier da ist sind war waren wird werden wurde wurden worden sein bin bist seid gewesen hat haben hatte
    hatten habe kann können konnte konnten muss müssen musste mussten soll sollen sollte sollten will
    wollen darf dürfen mag möchte würde würden wäre wären hätte hätten etwa eher bereits jedoch zudem
    somit also daher deshalb dabei dadurch damit davon dazu darauf darin darüber hierbei hierzu wobei
    alle allen aller alles andere anderen anderer anderes viel viele vielen mehr meist meisten einige
    einigen jede jeder jedes jedem jeden selbst sowohl weder noch immer wieder bzw usw etc ca
    """.split()
)

SUBJUNKTIONEN = set(
    """
    dass daß weil obwohl obgleich obschon wenn falls sofern soweit sobald solange sodass indem nachdem
    bevor ehe seitdem bis ob wobei wodurch womit worauf woraus worin wovon wozu weshalb weswegen inwiefern
    inwieweit wohingegen
    """.split()
)
# Nur nach Komma als Nebensatz-Einleitung gewertet
SUBJUNKTIONEN_NACH_KOMMA = {"als", "da", "damit", "während", "wie", "wo", "was", "wer", "warum", "wann"}
RELATIVPRONOMEN = {"der", "die", "das", "dem", "den", "deren", "dessen", "denen", "welche", "welcher", "welches", "welchem", "welchen"}
PRAEPOSITIONEN = {"in", "mit", "von", "bei", "auf", "für", "durch", "über", "unter", "zu", "nach", "aus", "an", "um", "gegen", "ohne", "vor", "hinter", "zwischen", "neben", "seit", "trotz", "wegen"}
NEBENORDNER = {"aber", "doch", "denn", "sondern", "jedoch"}

KONNEKTOR_ANFAENGE = [
    "darüber hinaus", "des weiteren", "zudem", "außerdem", "ferner", "weiterhin", "zusätzlich", "insgesamt",
    "somit", "folglich", "daher", "deshalb", "dadurch", "allerdings", "jedoch", "dennoch", "gleichzeitig",
    "zugleich", "letztlich", "letztendlich", "schließlich", "abschließend", "zusammenfassend", "insbesondere",
    "vor allem", "hierbei", "dabei", "damit", "demnach", "infolgedessen", "nichtsdestotrotz", "ebenso",
    "gleichermaßen", "darauf aufbauend", "vor diesem hintergrund", "in diesem zusammenhang", "im gegensatz dazu",
    "andererseits", "einerseits", "hinzu kommt", "nicht zuletzt", "konkret", "kurz gesagt", "mit anderen worten",
]

HEDGING = set(
    """
    kann können könnte könnten dürfte dürften möglicherweise vermutlich wahrscheinlich eher tendenziell
    scheint scheinen erscheint erscheinen vermeintlich gegebenenfalls ggf unter umständen teilweise
    weitgehend mitunter offenbar anscheinend
    """.split()
)

PERSONAL = {"ich", "wir", "mein", "meine", "meiner", "meinem", "meinen", "unser", "unsere", "unseren", "unserem", "unserer", "mich", "mir", "uns"}

NOMINAL_ENDUNGEN = ("ung", "ungen", "heit", "heiten", "keit", "keiten", "ion", "ionen", "ität", "itäten", "ismus", "schaft", "schaften", "nis", "nisse", "ierung", "ierungen")

WERDEN_FORMEN = {"werden", "wird", "wurde", "wurden", "worden", "werde", "würde", "würden", "wirst", "werdet"}

LITERATUR_UEBERSCHRIFT = re.compile(
    r"^\s*(#+\s*)?(\d+(\.\d+)*\.?\s*)?(Literaturverzeichnis|Literatur|Quellenverzeichnis|Quellen|Bibliographie|"
    r"Bibliografie|Referenzen|References|Anhang|Eidesstattliche Erklärung|Selbstständigkeitserklärung)\s*:?\s*$",
    re.IGNORECASE,
)

WORT = r"[A-Za-zÄÖÜäöüßéèàáâêôûçñ]+(?:[-'’][A-Za-zÄÖÜäöüßéèàáâêôûçñ0-9]+)*(?:[*_:/]?innen|[*_:]in)?"
ZAHL = r"\d+(?:[.,]\d+)*"
TOKEN_RE = re.compile(rf"{ZAHL}|{WORT}")
BUCHSTABENWORT_RE = re.compile(rf"^{WORT}$")

ZITAT_RE = re.compile(
    r"\s?\((?:[^()]{0,160}?\b(?:1[6-9]\d{2}|20\d{2})[a-z]?\b[^()]{0,80}?|(?:vgl\.|Vgl\.)?\s*ebd\.[^()]{0,40}|o\.\s?J\.[^()]{0,40})\)"
)
FUSSNOTE_RE = re.compile(r"\[\^?\d+\]|[¹²³⁴⁵⁶⁷⁸⁹⁰]+")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
MD_FETT_RE = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")
MD_KURSIV_RE = re.compile(r"(?<![*\w])\*[^*\n]+\*(?![*\w])|(?<![_\w])_[^_\n]+_(?![_\w])")
LISTE_RE = re.compile(r"^\s*([-*•–·▪]|\d{1,2}[.)]|[a-z][.)])\s+")
GEDANKENSTRICH_RE = re.compile(r"(?<=\s)[–—](?=\s)|(?<=\w)—(?=\w)|(?<=\s)-(?=\s)")
DREIERLISTE_RE = re.compile(
    r"\b[\wÄÖÜäöüß-]+(?:\s[\wÄÖÜäöüß-]+)?,\s[\wÄÖÜäöüß-]+(?:\s[\wÄÖÜäöüß-]+)?(?:,\s[\wÄÖÜäöüß-]+(?:\s[\wÄÖÜäöüß-]+)?)*,?\s(?:und|sowie|oder)\s[\wÄÖÜäöüß-]+"
)

VOKALGRUPPE_RE = re.compile(r"[aeiouyäöü]+")


# ---------------------------------------------------------------------------
# Einlesen
# ---------------------------------------------------------------------------

def lies_datei(pfad: str) -> str:
    if pfad == "-":
        return sys.stdin.read()
    endung = os.path.splitext(pfad)[1].lower()
    if endung == ".docx":
        return lies_docx(pfad)
    if endung == ".pdf":
        try:
            out = subprocess.run(["pdftotext", "-enc", "UTF-8", pfad, "-"], check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as e:
            raise SystemExit(f"PDF konnte nicht gelesen werden (pdftotext nötig): {e}")
        return out.stdout.decode("utf-8", errors="replace")
    with open(pfad, encoding="utf-8", errors="replace") as f:
        return f.read()


def lies_docx(pfad: str) -> str:
    with zipfile.ZipFile(pfad) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    absaetze = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
        stil = re.search(r'<w:pStyle w:val="([^"]+)"', p)
        text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")
        if not text.strip():
            continue
        if stil and re.match(r"(?i)(heading|berschrift|title|titel)", stil.group(1)):
            text = "# " + text
        elif "<w:numPr>" in p:
            text = "- " + text
        absaetze.append(text)
    return "\n\n".join(absaetze)


# ---------------------------------------------------------------------------
# Struktur: Absätze, Überschriften, Listen
# ---------------------------------------------------------------------------

def normalisiere(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ").replace(" ", " ")
    text = text.replace("­", "")  # weiches Trennzeichen
    return text


def ist_ueberschrift(zeile: str) -> bool:
    s = zeile.strip()
    if re.match(r"^#{1,6}\s", s):
        return True
    if re.match(r"^\*\*[^*]+\*\*:?$", s):  # ganze Zeile fett = Zwischenüberschrift
        return True
    woerter = s.split()
    if len(woerter) <= 12 and not re.search(r"[.!?:;…\"“”»)]$", s):
        return True
    return False


def zerlege_bloecke(text: str) -> dict:
    """Teilt in Prosa-Absätze, Überschriften, Listenpunkte; schneidet ab Literaturverzeichnis ab."""
    text = normalisiere(text)
    roh_bloecke = re.split(r"\n\s*\n", text)
    absaetze, ueberschriften, listenpunkte = [], [], []
    tabellenzeilen = 0
    code = False
    abgeschnitten = False
    for block in roh_bloecke:
        zeilen = [z for z in block.split("\n") if z.strip()]
        if not zeilen:
            continue
        if zeilen[0].strip().startswith("```"):
            code = not code if zeilen[-1].strip() == zeilen[0].strip() and len(zeilen) == 1 else False
            continue
        if code:
            continue
        if LITERATUR_UEBERSCHRIFT.match(zeilen[0]) and (absaetze or ueberschriften):
            abgeschnitten = True
            break
        prosa: list[str] = []
        for z in zeilen:
            s = z.strip()
            if s.startswith("|") or s.count("|") >= 2:
                tabellenzeilen += 1
                continue
            if LISTE_RE.match(s):
                if prosa:
                    absaetze.append(" ".join(prosa))
                    prosa = []
                listenpunkte.append(LISTE_RE.sub("", s, count=1))
                continue
            if not prosa and ist_ueberschrift(s) and (len(zeilen) == 1 or re.match(r"^#{1,6}\s", s)):
                ueberschriften.append(re.sub(r"^#+\s*", "", s))
                continue
            prosa.append(s)
        if prosa:
            absaetze.append(" ".join(prosa))
    return {
        "absaetze": absaetze,
        "ueberschriften": ueberschriften,
        "listenpunkte": listenpunkte,
        "tabellenzeilen": tabellenzeilen,
        "literatur_abgeschnitten": abgeschnitten,
    }


def bereinige_absatz(absatz: str, zaehler: Counter) -> str:
    zaehler["markdown_fett"] += len(MD_FETT_RE.findall(absatz))
    zaehler["markdown_kursiv"] += len(MD_KURSIV_RE.findall(absatz))
    absatz = MD_LINK_RE.sub(r"\1", absatz)
    absatz = re.sub(r"\*\*|__", "", absatz)
    absatz = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"\1", absatz)
    zaehler["fussnoten"] += len(FUSSNOTE_RE.findall(absatz))
    absatz = FUSSNOTE_RE.sub("", absatz)
    zaehler["zitate"] += len(ZITAT_RE.findall(absatz))
    absatz = ZITAT_RE.sub("", absatz)
    absatz = re.sub(r"`[^`]*`", "", absatz)
    absatz = re.sub(r"\s+([.,;:!?])", r"\1", absatz)
    return re.sub(r"\s+", " ", absatz).strip()


# ---------------------------------------------------------------------------
# Satzsegmentierung
# ---------------------------------------------------------------------------

def _kern(token: str) -> str:
    return token.strip("\"'„“”»«‚‘’()[]{}").rstrip(".!?…").lower()


VERWEIS_VOR_ZAHL = {"abb", "abbildung", "tab", "tabelle", "s", "seite", "kap", "kapitel", "abschnitt", "nr", "anhang", "anlage", "abs", "art", "fn", "fußnote", "bd", "band", "heft", "jg", "vol", "no"}


def ist_satzgrenze(token: str, naechstes: str, vorher: str = "") -> bool:
    t = token.rstrip("\"'“”»«’)]")
    if not t:
        return False
    if not re.search(r"[.!?…]$", t):
        return False
    n = naechstes.lstrip("\"'„“»«‚‘([")
    if not n:
        return False
    if not (n[0].isupper() or n[0].isdigit()):
        return False
    if t.endswith(("!", "?", "…", "...")):
        return True
    kern = _kern(t)
    if kern in ABKUERZUNGEN:
        return False
    if "." in kern and all(len(teil) <= 3 for teil in kern.split(".") if teil):  # z.B. u.a. d.h. i.d.R.
        return False
    if len(kern) == 1 and kern.isalpha():  # Initiale / "z." "B."
        return False
    if re.fullmatch(r"\d{1,2}", kern):  # Ordinalzahl: "die 3. Phase" – außer nach Verweis: "Abb. 3. Danach"
        return _kern(n) in SATZSTARTER or _kern(vorher) in VERWEIS_VOR_ZAHL
    if re.fullmatch(r"[ivxlc]+", kern) and len(kern) <= 4 and token[:1].isupper():
        return False
    return True


def zerlege_saetze(absatz: str) -> list[str]:
    tokens = absatz.split()
    saetze, aktuell = [], []
    for i, tok in enumerate(tokens):
        aktuell.append(tok)
        naechstes = tokens[i + 1] if i + 1 < len(tokens) else ""
        if naechstes and ist_satzgrenze(tok, naechstes, tokens[i - 1] if i else ""):
            saetze.append(" ".join(aktuell))
            aktuell = []
    if aktuell:
        saetze.append(" ".join(aktuell))
    return [s for s in saetze if TOKEN_RE.search(s)]


# ---------------------------------------------------------------------------
# Wort-Ebene
# ---------------------------------------------------------------------------

def tokens(satz: str) -> list[str]:
    return TOKEN_RE.findall(satz)


def ist_wort(t: str) -> bool:
    return bool(BUCHSTABENWORT_RE.match(t))


def buchstaben(t: str) -> int:
    return sum(ch.isalpha() for ch in t)


def silben(wort: str) -> int:
    w = wort.lower()
    w = re.sub(r"[^a-zäöüßéèàáâêôûy]", "", w)
    if not w:
        return 1
    n = len(VOKALGRUPPE_RE.findall(w))
    # "ie" am Wortende nach Konsonant in Fremdwörtern zweisilbig (Studie, Familie, Linie)
    if re.search(r"[^aeiouäöü]ie(n)?$", w) and re.search(r"(stud|famil|lin|ser|ini?tiat|kateg|strateg|technolog|ökonom|ener|theor|demokrat|bürokrat|histor|kolon|ferien|lilie|kastan|mumie|prämie|arie)", w):
        n += 1
    return max(1, n)


def stamm(wort: str) -> str:
    w = wort.lower()
    for endung in ("ungen", "ung", "heiten", "keiten", "heit", "keit", "ern", "en", "er", "es", "em", "e", "n", "s"):
        if len(w) - len(endung) >= 4 and w.endswith(endung):
            w = w[: -len(endung)]
            break
    return w[:8]


def inhaltsstaemme(satz_tokens: list[str]) -> set:
    return {stamm(t) for t in satz_tokens if ist_wort(t) and t.lower() not in FUNKTIONSWOERTER and len(t) > 2}


# ---------------------------------------------------------------------------
# Statistik-Helfer
# ---------------------------------------------------------------------------

def mittel(xs):
    return statistics.fmean(xs) if xs else 0.0


def sd(xs):
    return statistics.pstdev(xs) if len(xs) > 1 else 0.0


def cv(xs):
    m = mittel(xs)
    return sd(xs) / m if m else 0.0


def perzentil(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


def schiefe(xs):
    if len(xs) < 3:
        return 0.0
    m, s = mittel(xs), sd(xs)
    return sum(((x - m) / s) ** 3 for x in xs) / len(xs) if s else 0.0


def autokorrelation(xs, lag=1):
    if len(xs) <= lag + 2:
        return 0.0
    m = mittel(xs)
    nenner = sum((x - m) ** 2 for x in xs)
    if not nenner:
        return 0.0
    return sum((xs[i] - m) * (xs[i + lag] - m) for i in range(len(xs) - lag)) / nenner


def korrelation(xs, ys):
    if len(xs) < 4:
        return 0.0
    mx, my = mittel(xs), mittel(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if not sx or not sy:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def mattr(woerter, fenster=100):
    if not woerter:
        return 0.0
    if len(woerter) < fenster:
        return len(set(woerter)) / len(woerter)
    zaehl = Counter(woerter[:fenster])
    werte = [len(zaehl) / fenster]
    for i in range(fenster, len(woerter)):
        alt = woerter[i - fenster]
        zaehl[alt] -= 1
        if zaehl[alt] == 0:
            del zaehl[alt]
        zaehl[woerter[i]] += 1
        werte.append(len(zaehl) / fenster)
    return mittel(werte)


def _mtld_richtung(woerter, schwelle):
    faktoren, typen, n = 0.0, set(), 0
    for w in woerter:
        typen.add(w)
        n += 1
        if len(typen) / n <= schwelle:
            faktoren += 1
            typen, n = set(), 0
    if n:
        ttr = len(typen) / n
        faktoren += (1 - ttr) / (1 - schwelle) if ttr < 1 else 0
    return len(woerter) / faktoren if faktoren else float(len(woerter))


def mtld(woerter, schwelle=0.72):
    if len(woerter) < 50:
        return 0.0
    return (_mtld_richtung(woerter, schwelle) + _mtld_richtung(list(reversed(woerter)), schwelle)) / 2


def yule_k(woerter):
    n = len(woerter)
    if n < 2:
        return 0.0
    freq_der_freq = Counter(Counter(woerter).values())
    s2 = sum(i * i * v for i, v in freq_der_freq.items())
    return 10000 * (s2 - n) / (n * n)


# ---------------------------------------------------------------------------
# KI-Muster
# ---------------------------------------------------------------------------

def lade_muster(pfad: str | None = None) -> list[dict]:
    pfad = pfad or STANDARD_MUSTER
    if not os.path.exists(pfad):
        return []
    with open(pfad, encoding="utf-8") as f:
        daten = json.load(f)
    muster = []
    for m in daten.get("muster", []):
        flags = 0 if m.get("gross_klein") else re.IGNORECASE
        try:
            m = dict(m)
            m["_re"] = re.compile(m["regex"], flags)
            muster.append(m)
        except re.error as e:
            print(f"Warnung: Muster {m.get('id')} ungültig: {e}", file=sys.stderr)
    return muster


# ---------------------------------------------------------------------------
# Hauptanalyse
# ---------------------------------------------------------------------------

def teilsatz_info(satz: str, satz_tokens: list[str]) -> tuple[int, bool]:
    """Schätzt die Zahl der Teilsätze (Haupt- + Nebensätze) und ob ein Nebensatz vorkommt."""
    low = satz.lower()
    neben = 0
    for t in satz_tokens:
        if t.lower() in SUBJUNKTIONEN:
            neben += 1
    teile = re.split(r"[,;]\s*", low)
    for teil in teile[1:]:
        w = teil.split()
        if not w:
            continue
        w0 = w[0].strip("„\"(")
        if w0 in SUBJUNKTIONEN:
            continue  # schon gezählt
        if w0 in SUBJUNKTIONEN_NACH_KOMMA or w0 in RELATIVPRONOMEN:
            neben += 1
        elif w0 in PRAEPOSITIONEN and len(w) > 1 and w[1] in RELATIVPRONOMEN:
            neben += 1
        elif w0 in ("um", "ohne", "anstatt", "statt") and re.search(r"\bzu\b|\w+zu\w+en\b", teil):
            neben += 1
    haupt = 1 + sum(1 for teil in teile[1:] if teil.split() and teil.split()[0] in NEBENORDNER)
    haupt += low.count(";")
    return haupt + neben, neben > 0


def analysiere_text(text: str, muster: list[dict] | None = None) -> dict:
    """Berechnet alle Rohmetriken. Gibt dict mit 'metriken', 'saetze', 'absaetze', 'info' zurück."""
    if muster is None:
        muster = lade_muster()
    struktur = zerlege_bloecke(text)
    zaehler: Counter = Counter()
    absatz_saetze: list[list[str]] = []
    for a in struktur["absaetze"]:
        sauber = bereinige_absatz(a, zaehler)
        s = zerlege_saetze(sauber)
        if s:
            absatz_saetze.append(s)

    saetze = []  # dicts
    for ai, liste in enumerate(absatz_saetze):
        for si, s in enumerate(liste):
            toks = tokens(s)
            saetze.append({"nr": len(saetze) + 1, "absatz": ai + 1, "pos_im_absatz": si + 1, "text": s, "tokens": toks})

    alle_tokens = [t for s in saetze for t in s["tokens"]]
    woerter = [t for t in alle_tokens if ist_wort(t)]
    woerter_low = [w.lower() for w in woerter]
    n_tok = len(alle_tokens)
    n_w = len(woerter)
    n_s = len(saetze)
    pro1000 = (lambda x: 1000.0 * x / n_tok) if n_tok else (lambda x: 0.0)
    m: dict[str, float] = {}

    # --- Satzlänge -----------------------------------------------------------
    laengen = [len(s["tokens"]) for s in saetze]
    m["satzlaenge_mittel"] = mittel(laengen)
    m["satzlaenge_median"] = statistics.median(laengen) if laengen else 0.0
    m["satzlaenge_sd"] = sd(laengen)
    m["satzlaenge_cv"] = cv(laengen)
    m["satzlaenge_p10"] = perzentil(laengen, 0.10)
    m["satzlaenge_p90"] = perzentil(laengen, 0.90)
    m["satzlaenge_max"] = float(max(laengen)) if laengen else 0.0
    m["satzlaenge_schiefe"] = schiefe(laengen)
    m["satzlaenge_dispersion"] = (sd(laengen) ** 2 / mittel(laengen)) if laengen and mittel(laengen) else 0.0
    m["anteil_kurze_saetze"] = sum(l <= 10 for l in laengen) / n_s if n_s else 0.0
    m["anteil_sehr_kurze_saetze"] = sum(l <= 6 for l in laengen) / n_s if n_s else 0.0
    m["anteil_lange_saetze"] = sum(l >= 30 for l in laengen) / n_s if n_s else 0.0
    m["anteil_sehr_lange_saetze"] = sum(l >= 40 for l in laengen) / n_s if n_s else 0.0
    m["anteil_mittlere_saetze"] = sum(14 <= l <= 26 for l in laengen) / n_s if n_s else 0.0

    # --- Satzrhythmus --------------------------------------------------------
    diffs = [abs(laengen[i + 1] - laengen[i]) for i in range(len(laengen) - 1)]
    m["rhythmus_sprung_rel"] = (mittel(diffs) / mittel(laengen)) if diffs and mittel(laengen) else 0.0
    m["rhythmus_autokorrelation"] = autokorrelation(laengen, 1)
    in_lauf = [False] * len(laengen)
    for i in range(len(laengen) - 2):
        fenster = laengen[i : i + 3]
        mf = mittel(fenster)
        if mf and all(abs(x - mf) <= 0.2 * mf for x in fenster):
            in_lauf[i] = in_lauf[i + 1] = in_lauf[i + 2] = True
    m["anteil_gleichfoermige_laeufe"] = sum(in_lauf) / n_s if n_s else 0.0

    # --- Wortlänge / Silben -------------------------------------------------
    wl = [buchstaben(w) for w in woerter]
    sil = [silben(w) for w in woerter]
    m["wortlaenge_mittel"] = mittel(wl)
    m["wortlaenge_sd"] = sd(wl)
    m["wortlaenge_cv"] = cv(wl)
    m["anteil_lange_woerter"] = sum(x > 6 for x in wl) / n_w if n_w else 0.0
    m["anteil_sehr_lange_woerter"] = sum(x >= 13 for x in wl) / n_w if n_w else 0.0
    m["anteil_kurze_woerter"] = sum(x <= 3 for x in wl) / n_w if n_w else 0.0
    m["silben_mittel"] = mittel(sil)
    m["silben_sd"] = sd(sil)
    m["anteil_einsilbig"] = sum(x == 1 for x in sil) / n_w if n_w else 0.0
    m["anteil_mehrsilbig_3plus"] = sum(x >= 3 for x in sil) / n_w if n_w else 0.0
    m["anteil_mehrsilbig_5plus"] = sum(x >= 5 for x in sil) / n_w if n_w else 0.0

    # --- Wortschatz ------------------------------------------------------------
    m["mattr_100"] = mattr(woerter_low, 100)
    m["mattr_50"] = mattr(woerter_low, 50)
    m["mtld"] = mtld(woerter_low)
    m["yule_k"] = yule_k(woerter_low)
    m["anteil_funktionswoerter"] = sum(w in FUNKTIONSWOERTER for w in woerter_low) / n_w if n_w else 0.0
    inhalt = [stamm(w) for w in woerter_low if w not in FUNKTIONSWOERTER and len(w) > 2]
    m["inhaltswort_mattr_50"] = mattr(inhalt, 50)
    staemme = [inhaltsstaemme(s["tokens"]) for s in saetze]
    overlaps, teilt = [], 0
    for i in range(1, len(staemme)):
        a, b = staemme[i - 1], staemme[i]
        if a and b:
            overlaps.append(len(a & b) / len(a | b))
            if a & b:
                teilt += 1
    m["nachbarsatz_ueberlappung"] = mittel(overlaps)
    m["anteil_saetze_mit_wortaufnahme"] = teilt / (len(staemme) - 1) if len(staemme) > 1 else 0.0
    m["nominalstil_pro_100"] = 100.0 * sum(w.endswith(NOMINAL_ENDUNGEN) and len(w) > 5 for w in woerter_low) / n_w if n_w else 0.0
    m["hedging_pro_1000"] = pro1000(sum(w in HEDGING for w in woerter_low))
    m["ich_wir_pro_1000"] = pro1000(sum(w in PERSONAL for w in woerter_low))
    m["man_pro_1000"] = pro1000(woerter_low.count("man"))

    # --- Satzbau -------------------------------------------------------------
    teilsaetze, mit_neben, passiv = [], 0, 0
    menz_x, menz_y = [], []
    for s in saetze:
        n_teil, hat_neben = teilsatz_info(s["text"], s["tokens"])
        s["teilsaetze"] = n_teil
        teilsaetze.append(n_teil)
        mit_neben += hat_neben
        menz_x.append(n_teil)
        menz_y.append(len(s["tokens"]) / n_teil)
        low = [t.lower() for t in s["tokens"]]
        if any(t in WERDEN_FORMEN for t in low) and any(
            re.fullmatch(r"ge\w{2,}(t|en)|\w{3,}iert|(be|er|ver|ent|zer|ge|über|unter|vor|an|auf|aus|ein|ab|zu|durch)\w{2,}(t|en)", t)
            for t in low
            if t not in WERDEN_FORMEN
        ):
            passiv += 1
    m["teilsaetze_pro_satz"] = mittel(teilsaetze)
    m["anteil_saetze_mit_nebensatz"] = mit_neben / n_s if n_s else 0.0
    m["anteil_einfache_saetze"] = sum(1 for s in saetze if "," not in s["text"] and ";" not in s["text"]) / n_s if n_s else 0.0
    m["woerter_pro_teilsatz"] = (n_tok / sum(teilsaetze)) if teilsaetze else 0.0
    m["menzerath_korrelation"] = korrelation(menz_x, menz_y)
    m["anteil_passiv"] = passiv / n_s if n_s else 0.0

    # Satzanfänge
    erste = []
    konnektor_start = 0
    dies_start = 0
    for s in saetze:
        low = s["text"].lower().lstrip("„\"'(»")
        w = low.split()
        erste.append(w[0].strip(",.:;") if w else "")
        if any(low.startswith(k + " ") or low.startswith(k + ",") for k in KONNEKTOR_ANFAENGE):
            konnektor_start += 1
            s["konnektor_start"] = True
        if re.match(r"(dies|das|diese[rs]?)\s+(zeigt|verdeutlicht|unterstreicht|belegt|macht|bedeutet|führt|ermöglicht|trägt|stellt|ist)\b", low):
            dies_start += 1
            s["dies_start"] = True
    m["anteil_konnektor_satzanfang"] = konnektor_start / n_s if n_s else 0.0
    m["anteil_dies_satzanfang"] = dies_start / n_s if n_s else 0.0
    m["anteil_artikel_satzanfang"] = sum(e in ("der", "die", "das") for e in erste) / n_s if n_s else 0.0
    gleich = sum(1 for i in range(1, len(erste)) if erste[i] and erste[i] == erste[i - 1])
    m["satzanfang_wiederholung"] = gleich / (len(erste) - 1) if len(erste) > 1 else 0.0
    top3 = sum(c for _, c in Counter(erste).most_common(3))
    m["satzanfang_top3_anteil"] = top3 / n_s if n_s else 0.0

    # --- Zeichensetzung (pro 1000 Token) -----------------------------------
    roh = " ".join(s["text"] for s in saetze)
    m["kommas_pro_1000"] = pro1000(roh.count(","))
    m["semikolon_pro_1000"] = pro1000(roh.count(";"))
    m["doppelpunkt_pro_1000"] = pro1000(len(re.findall(r":(?!\d)", roh)))
    m["gedankenstrich_pro_1000"] = pro1000(len(GEDANKENSTRICH_RE.findall(roh)))
    m["klammern_pro_1000"] = pro1000(roh.count("("))
    m["anfuehrungen_pro_1000"] = pro1000(len(re.findall(r"[„“”\"»«]", roh)) / 2)
    m["fragen_pro_1000"] = pro1000(sum(s["text"].rstrip("\"“”»)").endswith("?") for s in saetze))
    m["ausrufe_pro_1000"] = pro1000(sum(s["text"].rstrip("\"“”»)").endswith("!") for s in saetze))
    m["kommas_pro_satz"] = roh.count(",") / n_s if n_s else 0.0

    # --- Absätze -------------------------------------------------------------
    abs_w = [sum(len(tokens(s)) for s in liste) for liste in absatz_saetze]
    abs_s = [len(liste) for liste in absatz_saetze]
    m["absaetze"] = float(len(absatz_saetze))
    m["absatzlaenge_mittel"] = mittel(abs_w)
    m["absatzlaenge_cv"] = cv(abs_w) if len(abs_w) > 1 else 0.0
    m["saetze_pro_absatz"] = mittel(abs_s)
    m["saetze_pro_absatz_cv"] = cv(abs_s) if len(abs_s) > 1 else 0.0
    m["anteil_einsatz_absaetze"] = sum(x == 1 for x in abs_s) / len(abs_s) if abs_s else 0.0

    # --- KI-Muster und Struktur ---------------------------------------------
    treffer_gesamt = 0.0
    treffer_liste = []
    for mu in muster:
        for s in saetze:
            for t in mu["_re"].finditer(s["text"]):
                g = float(mu.get("gewicht", 1.0))
                treffer_gesamt += g
                treffer_liste.append({"satz": s["nr"], "muster": mu["id"], "label": mu.get("label", mu["id"]), "kategorie": mu.get("kategorie", ""), "fund": t.group(0), "gewicht": g})
                s.setdefault("muster", []).append(mu["id"])
    m["ki_muster_pro_1000"] = pro1000(treffer_gesamt)
    m["dreierlisten_pro_1000"] = pro1000(sum(len(DREIERLISTE_RE.findall(s["text"])) for s in saetze))
    m["sowohl_als_auch_pro_1000"] = pro1000(len(re.findall(r"\bsowohl\b[^.!?]{1,150}?\bals auch\b", roh, re.I)))
    m["nicht_nur_sondern_pro_1000"] = pro1000(len(re.findall(r"\bnicht nur\b[^.!?]{1,150}?\bsondern\b", roh, re.I)))
    m["sondern_pro_1000"] = pro1000(len(re.findall(r",\s*sondern\b", roh, re.I)))
    m["markdown_elemente"] = float(zaehler["markdown_fett"] + zaehler["markdown_kursiv"] + len(struktur["listenpunkte"]))
    m["listenpunkte"] = float(len(struktur["listenpunkte"]))
    m["ueberschriften_pro_1000"] = pro1000(len(struktur["ueberschriften"]))
    m["zitate_pro_1000"] = pro1000(zaehler["zitate"])

    # --- Lesbarkeit ------------------------------------------------------------
    asl = m["satzlaenge_mittel"]
    asw = m["silben_mittel"]
    m["lix"] = asl + 100.0 * m["anteil_lange_woerter"]
    m["flesch_amstad"] = 180.0 - asl - 58.5 * asw
    m["wiener_sachtextformel"] = 0.1935 * 100 * m["anteil_mehrsilbig_3plus"] + 0.1672 * asl + 0.1297 * 100 * m["anteil_lange_woerter"] - 0.0327 * 100 * m["anteil_einsilbig"] - 0.875

    # --- Satz-Flags für die Umschreib-Schleife -------------------------------
    for i, s in enumerate(saetze):
        flags = []
        l = len(s["tokens"])
        if in_lauf[i]:
            flags.append("gleichfoermig")
        if l >= 40:
            flags.append("sehr_lang")
        if s.get("konnektor_start"):
            flags.append("konnektor_anfang")
        if s.get("dies_start"):
            flags.append("dies_anfang")
        if i > 0 and erste[i] and erste[i] == erste[i - 1]:
            flags.append("gleicher_satzanfang")
        if GEDANKENSTRICH_RE.search(s["text"]):
            flags.append("gedankenstrich")
        if DREIERLISTE_RE.search(s["text"]):
            flags.append("dreierliste")
        for mid in s.get("muster", []):
            flags.append("muster:" + mid)
        s["flags"] = flags
        s["woerter"] = l

    info = {
        "woerter": n_w,
        "token": n_tok,
        "saetze": n_s,
        "absaetze": len(absatz_saetze),
        "ueberschriften": len(struktur["ueberschriften"]),
        "listenpunkte": len(struktur["listenpunkte"]),
        "tabellenzeilen": struktur["tabellenzeilen"],
        "literatur_abgeschnitten": struktur["literatur_abgeschnitten"],
        "zitate_entfernt": zaehler["zitate"],
        "satzlaengen": laengen,
        "satzlaengen_verteilung": verteilung(laengen),
        "warnungen": [],
    }
    if n_w < 300:
        info["warnungen"].append(f"Nur {n_w} Wörter – unter ~300 Wörtern sind die Kennzahlen unzuverlässig.")
    if n_s < 15:
        info["warnungen"].append(f"Nur {n_s} Sätze – Verteilungsmaße (Varianz, Rhythmus) sind wenig aussagekräftig.")
    for s in saetze:
        s.pop("tokens", None)
        s.pop("konnektor_start", None)
        s.pop("dies_start", None)
    return {"metriken": {k: round(v, 4) for k, v in m.items()}, "saetze": saetze, "muster_treffer": treffer_liste, "info": info}


def verteilung(laengen):
    klassen = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 40), (41, 10_000)]
    n = len(laengen) or 1
    out = {}
    for a, b in klassen:
        name = f"{a}-{b}" if b < 10_000 else f"{a}+"
        out[name] = round(sum(a <= l <= b for l in laengen) / n, 3)
    return out


# ---------------------------------------------------------------------------
# Bewertung gegen Referenzwerte
# ---------------------------------------------------------------------------

NAMEN = {
    "satzlaenge_mittel": "Satzlänge Ø (Wörter)",
    "satzlaenge_median": "Satzlänge Median",
    "satzlaenge_sd": "Satzlänge Standardabweichung",
    "satzlaenge_cv": "Satzlängen-Variation (CV = SD/Ø)",
    "satzlaenge_p10": "Satzlänge 10 %-Perzentil",
    "satzlaenge_p90": "Satzlänge 90 %-Perzentil",
    "satzlaenge_max": "Längster Satz",
    "satzlaenge_schiefe": "Satzlängen-Schiefe",
    "satzlaenge_dispersion": "Satzlängen-Dispersion (Var/Ø)",
    "anteil_kurze_saetze": "Anteil kurzer Sätze (≤10 W.)",
    "anteil_sehr_kurze_saetze": "Anteil sehr kurzer Sätze (≤6 W.)",
    "anteil_lange_saetze": "Anteil langer Sätze (≥30 W.)",
    "anteil_sehr_lange_saetze": "Anteil sehr langer Sätze (≥40 W.)",
    "anteil_mittlere_saetze": "Anteil mittellanger Sätze (14–26 W.)",
    "rhythmus_sprung_rel": "Rhythmus: Längensprung zw. Nachbarsätzen",
    "rhythmus_autokorrelation": "Rhythmus: Autokorrelation (Lag 1)",
    "anteil_gleichfoermige_laeufe": "Anteil Sätze in gleichförmigen Läufen",
    "wortlaenge_mittel": "Wortlänge Ø (Buchstaben)",
    "wortlaenge_sd": "Wortlänge Standardabweichung",
    "wortlaenge_cv": "Wortlängen-Variation (CV)",
    "anteil_lange_woerter": "Anteil langer Wörter (>6 Buchst.)",
    "anteil_sehr_lange_woerter": "Anteil sehr langer Wörter (≥13 Buchst.)",
    "anteil_kurze_woerter": "Anteil kurzer Wörter (≤3 Buchst.)",
    "silben_mittel": "Silben pro Wort Ø",
    "silben_sd": "Silben pro Wort SD",
    "anteil_einsilbig": "Anteil einsilbiger Wörter",
    "anteil_mehrsilbig_3plus": "Anteil Wörter ≥3 Silben",
    "anteil_mehrsilbig_5plus": "Anteil Wörter ≥5 Silben",
    "mattr_100": "Wortschatzvielfalt (MATTR-100)",
    "mattr_50": "Wortschatzvielfalt (MATTR-50)",
    "mtld": "Wortschatzvielfalt (MTLD)",
    "yule_k": "Yules K (Wortwiederholung)",
    "anteil_funktionswoerter": "Anteil Funktionswörter",
    "inhaltswort_mattr_50": "Vielfalt der Inhaltswörter",
    "nachbarsatz_ueberlappung": "Begriffsaufnahme zw. Nachbarsätzen",
    "anteil_saetze_mit_wortaufnahme": "Sätze, die einen Begriff des Vorsatzes aufnehmen",
    "nominalstil_pro_100": "Nominalstil (-ung/-heit/-keit … pro 100 W.)",
    "hedging_pro_1000": "Abschwächungen/Modalität pro 1000",
    "ich_wir_pro_1000": "ich/wir pro 1000",
    "man_pro_1000": "„man“ pro 1000",
    "teilsaetze_pro_satz": "Teilsätze pro Satz",
    "anteil_saetze_mit_nebensatz": "Anteil Sätze mit Nebensatz",
    "anteil_einfache_saetze": "Anteil Sätze ohne Komma",
    "woerter_pro_teilsatz": "Wörter pro Teilsatz",
    "menzerath_korrelation": "Menzerath-Korrelation",
    "anteil_passiv": "Anteil Passivsätze",
    "anteil_konnektor_satzanfang": "Satzanfang mit Konnektor (Zudem, Darüber hinaus …)",
    "anteil_dies_satzanfang": "Satzanfang „Dies zeigt/verdeutlicht …“",
    "anteil_artikel_satzanfang": "Satzanfang mit Der/Die/Das",
    "satzanfang_wiederholung": "Gleicher Satzanfang wie Vorsatz",
    "satzanfang_top3_anteil": "Anteil der 3 häufigsten Satzanfänge",
    "kommas_pro_1000": "Kommas pro 1000",
    "kommas_pro_satz": "Kommas pro Satz",
    "semikolon_pro_1000": "Semikolons pro 1000",
    "doppelpunkt_pro_1000": "Doppelpunkte pro 1000",
    "gedankenstrich_pro_1000": "Gedankenstriche pro 1000",
    "klammern_pro_1000": "Klammern pro 1000",
    "anfuehrungen_pro_1000": "Anführungen pro 1000",
    "fragen_pro_1000": "Fragesätze pro 1000",
    "ausrufe_pro_1000": "Ausrufesätze pro 1000",
    "absaetze": "Absätze",
    "absatzlaenge_mittel": "Absatzlänge Ø (Wörter)",
    "absatzlaenge_cv": "Absatzlängen-Variation (CV)",
    "saetze_pro_absatz": "Sätze pro Absatz Ø",
    "saetze_pro_absatz_cv": "Sätze-pro-Absatz-Variation (CV)",
    "anteil_einsatz_absaetze": "Anteil Ein-Satz-Absätze",
    "ki_muster_pro_1000": "KI-Floskeln & -Muster pro 1000",
    "dreierlisten_pro_1000": "Dreier-Aufzählungen pro 1000",
    "sowohl_als_auch_pro_1000": "„sowohl … als auch“ pro 1000",
    "nicht_nur_sondern_pro_1000": "„nicht nur … sondern“ pro 1000",
    "sondern_pro_1000": "„…, sondern“ pro 1000",
    "markdown_elemente": "Markdown-Elemente (Fett, Listen)",
    "listenpunkte": "Listenpunkte",
    "ueberschriften_pro_1000": "Überschriften pro 1000",
    "zitate_pro_1000": "Quellenverweise pro 1000",
    "lix": "LIX (Lesbarkeitsindex)",
    "flesch_amstad": "Flesch-Amstad (Lesbarkeit)",
    "wiener_sachtextformel": "Wiener Sachtextformel",
}


def lade_baselines(pfad: str | None = None) -> dict | None:
    pfad = pfad or STANDARD_BASELINES
    if not os.path.exists(pfad):
        return None
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


def bewerte(ergebnis: dict, baselines: dict | None, textsorte: str = "hochschule") -> dict:
    """Ordnet jede Kennzahl gegen die menschliche Referenzverteilung ein (grün/gelb/rot)."""
    m = ergebnis["metriken"]
    if not baselines or textsorte not in baselines.get("textsorten", {}):
        return {"verfuegbar": False, "kennzahlen": [], "score": None}
    ref = baselines["textsorten"][textsorte]["metriken"]
    zeilen = []
    gew_summe = gew_punkte = 0.0
    for key, r in ref.items():
        if key not in m:
            continue
        wert = m[key]
        mensch, ki = r["mensch"], r.get("ki", {})
        if mensch["p25"] <= wert <= mensch["p75"]:
            status = "gruen"
        elif mensch["p10"] <= wert <= mensch["p90"]:
            status = "gelb"
        else:
            status = "rot"
        ki_naeher = None
        if ki:
            ki_naeher = abs(wert - ki["p50"]) < abs(wert - mensch["p50"])
        richtung = None
        if status != "gruen":
            richtung = "erhoehen" if wert < mensch["p25"] else "senken"
        zeile = {
            "id": key,
            "name": NAMEN.get(key, key),
            "wert": wert,
            "mensch_p10": mensch["p10"], "mensch_p25": mensch["p25"], "mensch_p50": mensch["p50"],
            "mensch_p75": mensch["p75"], "mensch_p90": mensch["p90"],
            "ki_p50": ki.get("p50"),
            "trennschaerfe": r.get("auroc"),
            "gewicht": r.get("gewicht", 0.0),
            "bewertet": r.get("bewertet", False),
            "status": status,
            "ki_naeher": ki_naeher,
            "richtung": richtung,
            "hinweis": r.get("hinweis", ""),
        }
        zeilen.append(zeile)
        if zeile["bewertet"]:
            g = max(0.0, float(zeile["gewicht"]))
            gew_summe += g
            gew_punkte += g * {"gruen": 1.0, "gelb": 0.5, "rot": 0.0}[status]
    score = round(100 * gew_punkte / gew_summe) if gew_summe else None
    modell = baselines["textsorten"][textsorte].get("modell")
    p_mensch = None
    if modell:
        z = modell["intercept"]
        for key, coef in modell["koeffizienten"].items():
            if key in m:
                mu, sigma = modell["mittel"][key], modell["sd"][key] or 1.0
                z += coef * ((m[key] - mu) / sigma)
        p_mensch = round(1 / (1 + math.exp(-max(-30, min(30, z)))), 3)
    zeilen.sort(key=lambda z: (not z["bewertet"], {"rot": 0, "gelb": 1, "gruen": 2}[z["status"]], -(z["gewicht"] or 0)))
    return {"verfuegbar": True, "kennzahlen": zeilen, "score": score, "p_mensch": p_mensch, "korpus": baselines.get("korpus", {})}


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

STATUS_SYMBOL = {"gruen": "🟢", "gelb": "🟡", "rot": "🔴"}


def fmt(x):
    if x is None:
        return "–"
    if isinstance(x, float):
        if abs(x) >= 100:
            return f"{x:.0f}"
        if abs(x) >= 10:
            return f"{x:.1f}"
        return f"{x:.2f}"
    return str(x)


def bericht_markdown(ergebnis: dict, bewertung: dict, max_stellen: int = 15, alle: bool = False) -> str:
    info, m = ergebnis["info"], ergebnis["metriken"]
    out = []
    out.append(f"## Textanalyse\n")
    out.append(f"{info['woerter']} Wörter · {info['saetze']} Sätze · {info['absaetze']} Absätze"
               + (f" · {info['zitate_entfernt']} Quellenverweise (für die Messung ausgeblendet)" if info["zitate_entfernt"] else "")
               + (" · Literaturverzeichnis ignoriert" if info["literatur_abgeschnitten"] else ""))
    for w in info["warnungen"]:
        out.append(f"\n> ⚠️ {w}")
    if bewertung.get("verfuegbar"):
        out.append("")
        teile = []
        if bewertung["score"] is not None:
            teile.append(f"**Menschlichkeits-Score: {bewertung['score']}/100**")
        if bewertung.get("p_mensch") is not None:
            teile.append(f"Modell-Einschätzung: {round(100 * bewertung['p_mensch'])} % menschlich")
        out.append(" · ".join(teile))
        out.append("")
        out.append("| | Kennzahl | Wert | Mensch (Zielbereich P25–P75) | Mensch Median | KI Median | Aufgabe |")
        out.append("|---|---|---|---|---|---|---|")
        for z in bewertung["kennzahlen"]:
            if not z["bewertet"] and not alle:
                continue
            aufgabe = ""
            if z["richtung"] == "erhoehen":
                aufgabe = "↑ erhöhen"
            elif z["richtung"] == "senken":
                aufgabe = "↓ senken"
            if z["status"] != "gruen" and z["ki_naeher"]:
                aufgabe += " (KI-typisch)"
            out.append(
                f"| {STATUS_SYMBOL[z['status']]} | {z['name']} | {fmt(z['wert'])} | {fmt(z['mensch_p25'])}–{fmt(z['mensch_p75'])} | "
                f"{fmt(z['mensch_p50'])} | {fmt(z['ki_p50'])} | {aufgabe} |"
            )
        if not alle:
            out.append("\n_Nur trennscharfe Kennzahlen gezeigt; alle mit `--alle`._")
    else:
        out.append("\n_Keine Referenzwerte gefunden (data/baselines.json) – zeige Rohwerte._\n")
        out.append("| Kennzahl | Wert |\n|---|---|")
        for k, v in m.items():
            out.append(f"| {NAMEN.get(k, k)} | {fmt(v)} |")

    # Verteilung
    out.append("\n**Satzlängen-Verteilung** (Anteil der Sätze je Längenklasse in Wörtern)\n")
    vert = info["satzlaengen_verteilung"]
    for k, v in vert.items():
        balken = "█" * round(v * 40)
        out.append(f"`{k:>6}` {balken} {round(100 * v)} %")
    out.append("\n**Satzlängen im Verlauf:** " + " ".join(str(x) for x in info["satzlaengen"][:120]) + (" …" if len(info["satzlaengen"]) > 120 else ""))

    # Auffällige Stellen
    auff = [s for s in ergebnis["saetze"] if s["flags"]]
    if auff:
        out.append(f"\n**Auffällige Stellen** ({len(auff)} Sätze, zeige {min(max_stellen, len(auff))})\n")
        prio = lambda s: -sum(2 if f.startswith("muster:") else 1 for f in s["flags"])
        for s in sorted(auff, key=prio)[:max_stellen]:
            text = s["text"] if len(s["text"]) <= 160 else s["text"][:157] + "…"
            out.append(f"- Satz {s['nr']} (Abs. {s['absatz']}, {s['woerter']} W.): „{text}“ → {', '.join(s['flags'])}")
    if ergebnis["muster_treffer"]:
        c = Counter(t["label"] for t in ergebnis["muster_treffer"])
        out.append("\n**Gefundene KI-Muster:** " + ", ".join(f"{k} ({v}×)" for k, v in c.most_common(20)))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datei", help="Textdatei (.txt/.md/.docx/.pdf) oder - für stdin")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--textsorte", default="hochschule")
    ap.add_argument("--baselines", help="Pfad zu baselines.json")
    ap.add_argument("--muster", help="Pfad zu ki_muster.json")
    ap.add_argument("--stellen", type=int, default=15, help="max. Zahl auffälliger Sätze im Bericht")
    ap.add_argument("--alle", action="store_true", help="auch nicht bewertete Kennzahlen zeigen")
    ap.add_argument("--ohne-saetze", action="store_true", help="JSON ohne Satzliste")
    args = ap.parse_args(argv)

    text = lies_datei(args.datei)
    ergebnis = analysiere_text(text, lade_muster(args.muster))
    bewertung = bewerte(ergebnis, lade_baselines(args.baselines), args.textsorte)
    if args.format == "json":
        ausgabe = {"info": ergebnis["info"], "metriken": ergebnis["metriken"], "bewertung": bewertung, "muster_treffer": ergebnis["muster_treffer"]}
        if not args.ohne_saetze:
            ausgabe["saetze"] = ergebnis["saetze"]
        json.dump(ausgabe, sys.stdout, ensure_ascii=False, indent=1)
        sys.stdout.write("\n")
    else:
        print(bericht_markdown(ergebnis, bewertung, args.stellen, args.alle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
