#!/usr/bin/env python3
"""Inhaltscheck: Hat eine Überarbeitung Inhalte verloren oder neue erfunden?

Vergleicht Original und Überarbeitung deterministisch auf:
  - Zahlen (inkl. Prozent, Prozentpunkte, Vorzeichen, Jahreszahlen, Kennwerte wie N = 849)
  - Quellenverweise ((Müller 2019, S. 12), Müller (2019), vgl. …, ebd.)
  - wörtliche Zitate in Anführungszeichen, abgegrenzt wie im Coach (coach.zitat_masken: verschachtelte
    Zitate zählen zum äußeren, das erste Guillemet im Absatz bestimmt die Richtung, eine Belegklammer
    direkt hinter dem Zitat gehört dazu, ein gerades " kann ein „ schließen)
  - Abkürzungen/Akronyme (KMU, EVP, …): fehlend oder ganz neu; eine schon vorhandene Abkürzung,
    die nur öfter genannt wird (Nomen beim Teilen wiederholt), ist kein neuer Inhalt
  - Fachbegriffe (Inhaltswörter, die im Original mehrfach vorkommen)
  - Überschriften und Fußnotenmarker
  - Umfang (Wörter, Absätze); daneben die Wortzahl, wie der Coach sie zählt (ohne Überschriften,
    Quellenverweise und Fußnoten)

Reine Form gilt nicht als Verlust: Zitierform (Müller (2019) ↔ (Müller 2019), & ↔ und,
et al. ↔ u. a., Reihenfolge im Mehrfachzitat), Schreibweise von Zahlen (1.250 ↔ 1250,
Euro ↔ €, Mio. ↔ Millionen, N = 849 ↔ n = 849, drei ↔ 3) und die Stellung von
Satzzeichen am Zitatende.

Ebenso wenig gilt als Verlust, was der Coach zum Ersetzen empfiehlt: Auslöser-Wörter
der KI-Floskeln (ki_muster.json, z. B. „maßgeblich“, „eine Schlüsselrolle zukommen“)
und kleingeschriebene typische Claude-Wörter (wortlisten.json, z. B. „lässt“,
„häufig“). Fachnomen (großgeschrieben mitten im Satz) bleiben geschützt. Mit
--verlauf werden zusätzlich die Wörter übergangen, die coach.py in einer Messung
unter "ersetzbar" gespeichert hat (samt Flexionsformen, nicht aber Komposita oder
Nomen, die im Original nur als Platzhalter in einer Floskel stehen). Formen, die der
Coach unter "erwartet" speichert (Maskulinform beim Gendern, beim Teilen wiederholtes
Nomen, Abkürzungen), zählen mit --verlauf nicht als „Neuer häufiger Begriff“ bzw. neue
Abkürzung.

Gender-Paare gelten auch ohne Verlauf als derselbe Begriff: Partizip- und Maskulinform
(Bewerbende/Bewerber, Mitarbeitende/Mitarbeiter, Studierende/Studenten, Lehrende/
Lehrkräfte bzw. Dozenten), movierte Formen (Nutzerinnen/Nutzer) und Genderzeichen
(Bewerber*innen). „Lehrer“ für „Lehrende“ bleibt eine Meldung wert.

Bedeutungsgleichheit einzelner Aussagen kann ein Skript nicht prüfen – das
übernimmt das Modell anhand des Inhaltsinventars. Dieses Skript fängt die
harten Fälle ab, bei denen Umschreiben am häufigsten Fehler einbaut.

    python3 inhalt_check.py original.md neu.md [--format json] [--verlauf neu.coach.json]

Exit-Code 0 = keine harten Verluste, 1 = Verluste/Erfindungen gefunden.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter

AKRONYM_RE = re.compile(r"\b[A-ZÄÖÜ]{2,6}(?:-[A-ZÄÖÜ]{1,6})?s?\b")
UEBERSCHRIFT_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$", re.M)
WORT_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+(?:-[A-Za-zÄÖÜäöüß]+)*")
SATZ_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9„\"»(])|\n\s*\n")

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
# Funktionswörter, die beim Umformulieren ohne Inhaltsverlust wegfallen (Präpositionen, Konjunktionen, Konnektoren,
# Pronomen, Hilfs- und Modalverben, Gradpartikeln): nie als „Begriff verschwunden“ oder „Fachwort ersetzt?“ melden
FUNKTIONSWOERTER = set(
    """
    neben trotz gemäß laut wegen außer innerhalb außerhalb oberhalb unterhalb anhand mithilfe aufgrund bezüglich
    hinsichtlich angesichts mittels statt anstatt anstelle entgegen entlang gegenüber zufolge zwecks seitens infolge
    inklusive jenseits diesseits hinter binnen dank samt nebst wider ungeachtet anlässlich zugunsten zulasten mangels
    entsprechend entsprechende entsprechenden entsprechender betreffend ausgenommen inmitten unweit
    sowohl weder entweder falls sofern soweit solange sobald wohingegen wenngleich obgleich obschon zumal seitdem
    weshalb weswegen wieso warum ebenso ebenfalls gleichfalls zugleich gleichzeitig schließlich letztlich
    letztendlich hingegen dagegen wiederum indes indessen vielmehr stattdessen nämlich beziehungsweise respektive
    insbesondere besonders weiterhin weiteren darüber hinaus überdies nichtsdestotrotz gleichwohl dennoch trotzdem
    deswegen darum folglich mithin demnach demzufolge infolgedessen insofern insoweit außerdem ferner jedenfalls
    immerhin zumindest mindestens wenigstens höchstens beispielsweise vielleicht eventuell möglicherweise
    sicherlich tatsächlich eigentlich ziemlich durchaus überhaupt bereits bisher bislang damals danach davor dazu
    darauf daraus darin davon dafür daran darunter hierbei hierzu hierfür hierin hiervon hierdurch hiermit hierauf
    worauf wodurch womit wobei wofür woraus worin wovon wozu zuvor zunächst anschließend später früher heute
    heutzutage inzwischen mittlerweile derzeit zuerst zuletzt erstens zweitens drittens einerseits andererseits
    anderseits immer niemals manchmal stets meist meistens oftmals vielfach teilweise größtenteils weitgehend
    überwiegend nahezu beinahe wieder allein alleine lediglich ausschließlich sogar selbst jeweils insgesamt
    zusammenfassend abschließend ebenfalls genauso gerade
    jener jene jenes jenem jenen welche welcher welches welchem welchen solche solcher solches solchem solchen
    deren dessen derer denen derjenige diejenige dasjenige diejenigen derselbe dieselbe dasselbe denselben
    demselben derselben dieselben keine keiner keines keinem keinen einigen einiger einiges manche mancher manches
    manchen mehrere mehreren sämtliche sämtlichen beide beiden beider andere anderen anderer anderes anderem
    eigene eigenen eigener eigenes unser unsere unseren unserer unserem ihrer ihren ihrem ihres seine seiner
    seinen seinem seines etwas nichts jemand niemand
    worden würde würden wären hätte hätten hatten habe könnte könnten müsste müssten sollten sollen wollen wollte
    wollten dürfen durfte dürfte dürften möchte möchten konnten mussten gewesen seien wäre werde werdet
    alles allem jeden jedem ihnen einander weitere weiterer weiteres weiterem wenige wenigen weniger weniges
    wenigsten vieles vielem vieler meisten meiste beides mehrerer jegliche jeglicher jeglichen jegliches keinerlei
    etliche etlichen zahlreiche zahlreichen zahlreicher gewisse gewissen gewisser jeweilige jeweiligen jeweiliger
    sogenannte sogenannten sogenannter meine meiner meines meinem meinen unseres eurer derjenigen denjenigen
    demjenigen desjenigen jemandem jemanden niemandem niemanden
    zusätzlich daneben desto sonst ansonsten andernfalls diesbezüglich dementsprechend demgegenüber gleichermaßen
    vorher nachher hierüber hieraus womöglich nunmehr circa dahingehend worüber woran worum wogegen inwiefern
    inwieweit ohnehin sowieso keineswegs keinesfalls allenfalls gegebenenfalls seither sodann zumeist zuweilen
    mitunter bisweilen überall folgendermaßen nichtsdestoweniger sozusagen
    einschließlich zuzüglich abzüglich abseits vonseiten unbeschadet vorbehaltlich ausweislich exklusive versus
    könne müsse solle wolle dürfe möge musste mochte geworden
    """.split()
)
STOP |= FUNKTIONSWOERTER
# Funktionswörter, die großgeschrieben mitten im Satz Nomen sind („des Mangels“, „das Selbst“, „des Mittels“):
# dort zählen sie weiter als Begriff, nur kleingeschrieben oder am Satzanfang nicht
NOMEN_HOMOGRAPHE = {"mangels", "selbst", "mittels", "zwecks", "gerade", "nichts", "falls", "trotz"}

# Gender-Paare: Partizip-, Doppel- und Zeichenformen gelten als derselbe Begriff wie die Maskulinform („Bewerbende“ =
# „Bewerber“, „Studierende“ = „Studenten“, „Nutzerinnen“ = „Nutzer“). Die vom Coach verlangte Umstellung auf das
# generische Maskulinum erscheint so weder als „Begriff verschwunden“ noch als „Neuer häufiger Begriff“ – auch ohne Verlauf.
# Unregelmäßige Paare (Wortende, auch im Kompositum: „Bachelorstudierende“ = „Bachelorstudenten“); „Lehrer“ gehört
# bewusst nicht dazu (an Hochschulen eine andere Gruppe als die Lehrenden). „Lehrkräfte“ und „Dozenten“ bleiben verschiedene
# Begriffe (Schule ≠ Hochschule); „Lehrende“ zählt als die der beiden, die im Textpaar vorkommt (LEHRENDE_RE).
GENDER_GRUPPEN = [
    (re.compile(r"studierende[nrms]?$"), "student"),
    (re.compile(r"(?:dozierende[nrms]?|dozent(?:in|innen|en)?)$"), "dozent"),
    (re.compile(r"lehrkr[aä]ft(?:e|en)?$"), "lehrkraft"),
    (re.compile(r"absolvierende[nrms]?$"), "absolvent"),
    (re.compile(r"(?:promovierende[nrms]?|promovend(?:in|innen|en)?|doktorand(?:in|innen|en)?)$"), "doktorand"),
    (re.compile(r"konsumierende[nrms]?$"), "konsument"),
    # „Pfleger“ ist die Maskulinform, die coach.py für „Pflegende“ verlangt (GENDER_MASKULIN)
    (re.compile(r"(?:pflegekr[aä]ft(?:e|en)?|pfleger(?:in|innen|n|s)?)$"), "pflegekraft"),
]
LEHRENDE_RE = re.compile(r"lehrende[nrms]?$")
# nur großgeschrieben (Nomen): „pflegende Angehörige“ (Familie) sind keine Pflegekräfte
GENDER_NOMEN = [(re.compile(r"pflegende[nrms]?$"), "pflegekraft")]
# im Kompositum vorn („Studierendenwerk“ = „Studentenwerk“)
GENDER_INFIX = [(re.compile(r"studierenden(?=[a-zäöüß]{3})"), "studenten"),
                (re.compile(r"dozierenden(?=[a-zäöüß]{3})"), "dozenten"),
                (re.compile(r"lehrenden(?=[a-zäöüß]{3})"), "lehrkraft"),
                (re.compile(r"absolvierenden(?=[a-zäöüß]{3})"), "absolventen")]
# regelmäßig: substantiviertes Partizip „X-ende(n)“ ↔ Nomen auf „X-er“ (Bewerbende/Bewerber, Mitarbeitende/Mitarbeiter,
# Teilnehmende/Teilnehmer). Nur großgeschrieben (Nomen) und nur, wenn die Maskulinform als Nomen in einem der beiden Texte
# vorkommt – Verben und Adjektive („verwenden“, „fehlende“ neben „Fehler“) behalten ihren bisherigen Schlüssel
PARTIZIP_RE = re.compile(r"([a-zäöüß]{4,}?)end(?:e|en|er|em|es)")
# Movierte Formen: Plural „-innen“ (auch Binnen-I), Singular „-in“ nur nach typischen Personen-Endungen; ebenfalls nur
# großgeschrieben und nur, wenn die Grundform („Nutzer“, „Kunden“) in einem der beiden Texte vorkommt
INNEN_RE = re.compile(r"([a-zäöüß]{3,})innen")
INNEN_NICHT = ("beginnen", "gewinnen", "spinnen", "besinnen", "ersinnen", "entrinnen", "zerrinnen")  # Verben
IN_RE = re.compile(r"([a-zäöüß]{2,}(?:er|ent|ant|ist|or|eur|nd|og|eg|ekt|är|ar)|[a-zäöüß]{3,}at)in")
# Endung hinter Genderzeichen („Bewerber*innen“, „Nutzer:innen“, „Absolvent/-innen“) ist kein eigener Begriff
GENDER_ZEICHEN_RE = re.compile(r"[*:_/·]-?$")

# Vom Coach zum Ersetzen empfohlene Wörter (gleiche Daten wie coach.py): KI-Muster mit Gewicht > 0 und die Liste
# typischer Claude-Wörter. Fehlen die Dateien, prüft das Skript wie zuvor.
DATA = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "text-analyse", "data"))
MUSTER_PFAD = os.path.join(DATA, "ki_muster.json")
WORTLISTEN_PFAD = os.path.join(DATA, "wortlisten.json")
PLATZHALTER = "xqxq"        # Ersatzwort für die Kopfwort-Probe, passt auf kein Muster
_CACHE: dict = {}

# --- Quellenverweise ---------------------------------------------------------
JAHR = r"(?:1[5-9]\d{2}|20\d{2})[a-z]?(?![\wäöüß])|o\.\s?J\."
JAHR_RE = re.compile(rf"(?<![\w.,/-])(?:{JAHR})")
NAME = r"[A-ZÄÖÜ][\wÄÖÜäöüß'’-]*"
PARTIKEL = r"(?:von|van|de|der|den|des|du|zu|zur|la|le|di|da|für|of|the)"
ETAL = r"(?:et\s?al\.|u\.\s?a\.)"
# Fundstelle direkt hinter dem Jahr: ", S. 12 f." / ": 12" / ", Kap. 3" / ", 12" (nur am Ende)
FUND_RE = re.compile(
    r"\s*(?:,\s*(?:S\.|p\.|pp\.|Sp\.)\s*|:\s*)(?P<s>\d+(?:\s*[-–]\s*\d+)?(?:\s*ff?\.)?)"
    r"|\s*,\s*(?P<k>(?:Kap|Abs|Rn|Tab|Abb|Anm|Fn)\.\s*\d+(?:\.\d+)*)"
    r"|\s*,\s*(?!(?:1[5-9]\d{2}|20\d{2})[a-z]?(?!\d))(?P<n>\d{1,4}(?:\s*[-–]\s*\d+)?(?:\s*ff?\.)?)(?=\s*(?:[;)]|$))"
)
# führende Hinweiswörter vor dem Autor: vgl., siehe, z. B., zit. n., so auch, u. a. …
PRAEFIX_RE = re.compile(r"^(?:\s*(?:[a-zäöüß][\wäöüß]*\.?(?:\s?[a-zäöüß]\.)*|z\.\s?B\.|Vgl\.|Siehe|Zit\.\s?n\.|Ebenso|So)(?![\wäöüß]))+(?=\s|$)")
AUTOREN_RE = re.compile(rf"^(?:\s|{NAME}(?![\wÄÖÜäöüß'’-])\.?|{PARTIKEL}(?![\wäöüß])|&|/|,|und|and|{ETAL}|\(Hrsg\.\)|Hrsg\.)+$")
NARRATIV_RE = re.compile(
    # Komma zwischen Namen nur in Listen, die mit & / und enden (Reid, Stajduhar & Chappel (2010))
    rf"(?<![\wäöüß'’-])(?P<a>{NAME}(?:(?:\s+|\s*[&/]\s*|\s+und\s+|,\s*(?=[^()]{{0,80}}?(?:&|\bund\b)\s*{NAME}\s*\())"
    rf"(?:{NAME}|{PARTIKEL}(?=\s+[A-ZÄÖÜ]))|\s+{ETAL})*)"
    rf"\s*\(\s*(?P<j>{JAHR})(?P<w>(?:\s*(?:,|;|und|&)\s*(?:{JAHR}|[a-z](?![\wäöüß])))*)(?P<f>[^()]{{0,30}})\)"
)
# Vorangestelltes Nomen samt „von“ gehört zum Fließtext, nicht zum Verweis: „Literaturüberblick von Christensen (2019)“,
# „Laut der Studie von Müller (2020)“ → Verweis = „Christensen (2019)“ bzw. „Müller (2020)“
VON_PRAEFIX_RE = re.compile(rf"{NAME}\s+von\s+(?=[A-ZÄÖÜ]|{PARTIKEL}\s+[A-ZÄÖÜ])")
NICHT_AUTOR = {"prozent", "prozentpunkte", "prozentpunkten", "euro", "dollar", "mio", "mrd", "millionen",
               "milliarden", "tausend", "stand", "jahr", "jahre", "jahren", "punkte", "punkten"}
EBD_RE = re.compile(r"^\s*(?:vgl\.\s*)?(?:ebd\.|ebenda|a\.\s?a\.\s?O\.)", re.I)
KLAMMER_RE = re.compile(r"\(([^()]*)\)")

# --- Zahlen ------------------------------------------------------------------
# Kern ohne Vorzeichen; Vorzeichen, Vergleichszeichen und Einheiten werden drumherum gelesen.
# Tausendergruppen auch mit Leerzeichen (30 000), sonst 1.250 / 0,27 / .45
ZAHL_KERN_RE = re.compile(r"(?<![\w.,])(?:\d{1,3}(?:[ \u00a0\u2009\u202f]\d{3})+(?!\d)|\d+|(?=[.,]\d))(?:[.,]\d+)*")
SKALA = [(r"Mio\.?|Millionen|Million", "Mio"), (r"Mrd\.?|Milliarden|Milliarde", "Mrd"), (r"Tsd\.?|Tausend", "Tsd")]
# längere Formen zuerst: „Prozentpunkte“ darf nicht als „Prozent“ enden
EINHEIT = [(r"Prozentpunkten|Prozentpunkte|Prozentpunkt|Pp\.|pp\.?|PP", "pp"), (r"%|Prozent", "%"),
           (r"‰|Promille", "‰"), (r"Euro|EUR|€", "€"), (r"US-Dollar|Dollar|USD|\$", "$")]
SKALA_RE = re.compile(r"\s?(?:" + "|".join(m for m, _ in SKALA) + r")(?![\wäöüß])")
EINHEIT_RE = re.compile(r"\s?(?:" + "|".join(m for m, _ in EINHEIT) + r")(?![\wäöüß])")
VORWAEHRUNG_RE = re.compile(r"(?:€|EUR|US-Dollar|USD|\$)\s?$")
ZAHLWORT = {"null": "0", "eins": "1", "zwei": "2", "drei": "3", "vier": "4", "fünf": "5", "sechs": "6",
            "sieben": "7", "acht": "8", "neun": "9", "zehn": "10", "elf": "11", "zwölf": "12", "zwanzig": "20",
            "dreißig": "30", "vierzig": "40", "fünfzig": "50", "sechzig": "60", "siebzig": "70", "achtzig": "80",
            "neunzig": "90", "hundert": "100"}
# klein überall; groß nur am Satz-/Zeilenanfang („außer Acht“, „die Elf“ sind keine Zahlen)
ZAHLWORT_RE = re.compile(
    r"(?<![\wäöüß-])(?:" + "|".join(ZAHLWORT) + r"|(?:(?<=^)|(?<=[.!?:]\s)|(?<=\n))(?:"
    + "|".join(w.capitalize() for w in ZAHLWORT) + r"))(?![\wäöüß])", re.M)

# --- Zitate und Fußnoten -----------------------------------------------------
# Wörtliche Zitate erkennt zitat_spannen_absatz wie coach.zitat_masken (Stapel, Belegklammer, „…"). Zusätzlich, nur außerhalb
# dieser Spannen: “…“ (Autokorrektur) und ‚…‘, die der Coach nicht als Zitat führt. Kein Absatzwechsel im Zitat.
_Z = r"(?:(?!\n[ \t\r]*\n)[^{}])+"
ZUSATZ_PAAR_RE = re.compile(
    "“(" + _Z.format("“”„") + ")“"             # “…“ (Autokorrektur; “…” erkennt schon der Stapel)
    "|‚(" + _Z.format("‚‘’") + ")[‘’]"         # ‚…‘
)
# Inhalt einer Klammer direkt hinter dem schließenden Anführungszeichen, der sie als Beleg ausweist (wie coach._beleg_ende)
BELEG_INHALT_RE = re.compile(r"\d|\bebd\b|\bebenda\b|\bvgl\b|\bders\.|\bdies\.|\bHrsg\b|\bzit\b|\bInterview")
FUSSNOTE_RE = re.compile(r"\[\^[^\]\s]+\]|[¹²³⁴⁵⁶⁷⁸⁹⁰]+")
# hochgestellte Einheiten/Kennwerte (m², R², η², χ², 10⁶) sind keine Fußnotenmarker
HOCH_EINHEIT_RE = re.compile(r"(?<![\wäöüß])(?:[kcmdµμ]?m|R|r|s|σ|χ|η|ω|ε|x|y|z|a|b)[²³]|(?<![\d.,])10[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+")


def lesen(pfad: str) -> str:
    with open(pfad, encoding="utf-8", errors="replace") as f:
        t = f.read()
    return unicodedata.normalize("NFC", t).replace("\u00a0", " ")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def grundform(w: str) -> str:
    """Wort ohne Flexionsendung, ungekürzt: „Konsumenten“ = „Konsument“, aber nicht „Konsumentenrente“."""
    w = w.lower()
    for e in ("ungen", "ung", "heiten", "keiten", "heit", "keit", "ern", "en", "er", "es", "em", "e", "n", "s"):
        if len(w) - len(e) >= 4 and w.endswith(e):
            return w[: -len(e)]
    return w


def stamm(w: str) -> str:
    return grundform(w)[:9]


def gender_form(w: str, formen: set | None = None) -> str:
    """Wortform in Kleinschreibung, Gender-Paare auf die Maskulinform gebracht (siehe GENDER_GRUPPEN). formen: Wortformen
    beider Texte (wortformen); die regelmäßigen Regeln greifen nur bei großgeschriebenen Wörtern und nur, wenn die
    Gegenform dort großgeschrieben vorkommt (None = ohne diese Prüfung)."""
    wl = w.lower()
    for rx, ersatz in GENDER_GRUPPEN + GENDER_INFIX:
        neu = rx.sub(ersatz, wl, count=1)
        if neu != wl:
            return neu
    m = LEHRENDE_RE.search(wl)
    if m:   # „Lehrende“ = „Dozenten“, wenn nur diese im Textpaar stehen, sonst = „Lehrkräfte“
        klein = {x.lower() for x in formen} if formen is not None else set()
        dozent = any("dozent" in x or "dozierend" in x for x in klein) and not any("lehrkr" in x for x in klein)
        return wl[:m.start()] + ("dozent" if dozent else "lehrkraft")
    if not w[:1].isupper():
        return wl
    for rx, ersatz in GENDER_NOMEN:
        neu = rx.sub(ersatz, wl, count=1)
        if neu != wl:
            return neu

    def gibt(basis, endungen):
        return formen is None or any(basis[:1].upper() + basis[1:] + e in formen for e in endungen)

    m = INNEN_RE.fullmatch(wl)
    if m and not wl.endswith(INNEN_NICHT) and gibt(m.group(1), ("", "e", "en", "n", "s")):
        return m.group(1)
    m = IN_RE.fullmatch(wl)
    if m and gibt(m.group(1), ("", "e", "en", "n", "s")):
        return m.group(1)
    m = PARTIZIP_RE.fullmatch(wl)
    if m and gibt(m.group(1) + "er", ("", "n", "s")):
        return m.group(1) + "er"
    return wl


def begriff_stamm(w: str, formen: set | None = None) -> str:
    """Schlüssel für den Begriffsvergleich: Stamm nach Angleichung der Gender-Paare („Bewerbende“ = „Bewerber“)."""
    return stamm(gender_form(w, formen))


def wortformen(*texte: str) -> set:
    """Alle Wortformen der Texte (Schreibung wie im Text) – Bezugsmenge für gender_form."""
    return {x for t in texte for x in WORT_RE.findall(t)}


def kontext(t: str, pos, laenge: int = 0, breite: int = 70) -> str:
    """Textausschnitt um Position pos (oder, wie früher, um die erste Fundstelle des Strings pos)."""
    if isinstance(pos, str):
        pos, laenge = t.find(pos), len(pos)
    if pos < 0:
        return ""
    a, b = max(0, pos - breite), min(len(t), pos + laenge + breite)
    return norm(("…" if a else "") + t[a:b] + ("…" if b < len(t) else ""))


# ---------------------------------------------------------------------------
# Quellenverweise
# ---------------------------------------------------------------------------

def _fund(m) -> str:
    if m is None:
        return ""
    if m.group("k"):
        return norm(m.group("k"))
    s = re.sub(r"\s*[-–]\s*", "-", m.group("s") or m.group("n"))
    return "S. " + re.sub(r"\s*(ff?\.)", r" \1", s)


def _autoren(s: str):
    """Autorenteil → (Liste der Nachnamen, et-al.-Flag) oder None, wenn es keine Autorenangabe ist."""
    s = PRAEFIX_RE.sub("", s).strip(" ,")      # „Stand: 2022“ bleibt durch den Doppelpunkt draußen
    if not s or len(s) > 90 or not AUTOREN_RE.match(s) or not re.search(NAME, s):
        return None
    etal = bool(re.search(ETAL, s))
    s = re.sub(rf"{ETAL}|\(?Hrsg\.\)?", " ", s)
    namen = []
    for teil in re.split(r"\s*(?:&|/|,|\bund\b|\band\b)\s*", s):
        w = re.findall(NAME, teil)
        if w:
            namen.append(w[-1].rstrip(".").lower())
    return (namen, etal) if namen and namen[-1] not in NICHT_AUTOR else None


def _autor_beginn(a: str) -> int:
    """Versatz, ab dem der Autorenteil eines narrativen Verweises beginnt. Ein vorangestelltes Nomen samt „von“
    („Literaturüberblick von“, „Laut der Studie von“) und großgeschriebene Funktionswörter am Anfang („Laut“, „Nach“,
    „Gemäß“) bleiben im Fließtext; sonst fehlten sie dem Begriffsvergleich („Fachwort ersetzt?“). Bei einem Vornamen
    vor „von“ („Ludwig von Mises“) bleibt der Vorname im Fließtext – der Schlüssel (Nachname, Jahr) ändert sich nicht."""
    start = 0
    for m in VON_PRAEFIX_RE.finditer(a):
        start = m.end()
    while True:
        m = re.match(rf"({NAME})\s+(?=[A-ZÄÖÜ])", a[start:])
        if not m or m.group(1).lower() not in STOP:
            return start
        start += m.end()


def _jahre(erstes: str, weitere: str) -> list[str]:
    """„2019a“ + „, b, 2021“ → [2019a, 2019b, 2021]"""
    out = [erstes]
    for w in re.findall(rf"{JAHR}|(?<![\wäöüß])[a-z](?![\wäöüß])", weitere):
        out.append(re.sub(r"[a-z]$", "", out[-1]) + w if len(w) == 1 else w)
    return out


def _schluessel(namen, etal, jahr, fund) -> str:
    jahr = re.sub(r"\s", "", jahr).replace("o.J.", "o. J.")
    return " & ".join(namen) + (" et al." if etal else "") + f" {jahr}" + (f", {fund}" if fund else "")


def quellen(t: str):
    """Findet Quellenverweise. Rückgabe: (Liste von Funden, Text ohne die Verweise).

    Fund = {"schluessel", "namen", "jahr", "fund", "roh", "pos"}. Der Schlüssel ist von der
    Zitierform unabhängig (narrativ/Klammer, & / und, et al. / u. a.).
    """
    funde, spannen = [], []

    def neu(namen, etal, jahr, fund, roh, pos):
        funde.append({"schluessel": _schluessel(namen, etal, jahr, fund), "namen": namen, "jahr": jahr,
                      "fund": fund, "roh": norm(roh), "pos": pos})

    # narrativ: Müller (2019), Gagné und Deci (2005, S. 12), Müller et al. (2019a, 2020)
    for m in NARRATIV_RE.finditer(t):
        f = m.group("f")
        fm = FUND_RE.match(f) if f.strip() else None
        if f.strip() and not (fm and not f[fm.end():].strip()):
            continue                        # z. B. „Umsatz (2020: 23 %)“ ist kein Verweis
        au = _autoren(m.group("a"))
        if not au or re.search(r"\d\s*$", t[max(0, m.start() - 3):m.start()]):
            continue                        # „17,1 Prozent (1997)“ ist kein Verweis
        jahre = _jahre(m.group("j"), m.group("w"))
        beginn = m.start() + _autor_beginn(m.group("a"))    # Schlüssel aus dem ganzen Autorenteil, Spanne ab dem Autor
        for i, j in enumerate(jahre):
            neu(au[0], au[1], j, _fund(fm) if i == len(jahre) - 1 else "", t[beginn:m.end()], beginn)
        spannen.append((beginn, m.end()))

    # Klammern: jedes ;-Teilstück einzeln; nur Autor(en) + Jahr bzw. ebd. gelten als Verweis
    for k in KLAMMER_RE.finditer(t):
        if any(a <= k.start() < b for a, b in spannen):
            continue
        off = k.start(1)
        for teil in re.finditer(r"[^;]+", k.group(1)):
            p, p0 = teil.group(0), off + teil.start()
            e = EBD_RE.match(p)
            if e:
                fm = FUND_RE.match(p, e.end())
                ende = fm.end() if fm else e.end()
                funde.append({"schluessel": "ebd." + (f", {_fund(fm)}" if fm else ""), "namen": [], "jahr": "",
                              "fund": _fund(fm), "roh": norm(p[:ende]), "pos": p0})
                spannen.append((p0, p0 + ende))
                continue
            au, ende, letzt = None, 0, 0
            for jm in JAHR_RE.finditer(p):
                if jm.start() < letzt:
                    continue                # Seitenzahl wie „S. 1650“ ist kein zweites Jahr
                zwischen = p[letzt:jm.start()]
                if au and re.fullmatch(r"\s*(?:,|und|&)?\s*", zwischen):
                    pass                    # Müller 2019, 2021 → gleiche Autoren
                else:
                    au2 = _autoren(zwischen)
                    if not au2:
                        break
                    au = au2
                fm = FUND_RE.match(p, jm.end())
                ende = letzt = fm.end() if fm else jm.end()
                bu = None if fm else re.match(r"(?:\s*,\s*[a-z](?![\wäöüß]))+", p[ende:])    # 2019a, b
                for j in _jahre(jm.group(0), bu.group(0) if bu else ""):
                    neu(au[0], au[1], j, _fund(fm), p[:ende], p0)
                if bu:
                    ende = letzt = ende + bu.end()
            if ende:
                spannen.append((p0, p0 + ende))

    rest = list(t)
    for a, b in spannen:
        rest[a:b] = " " * (b - a)
    return funde, "".join(rest)


def zitate(t: str) -> Counter:
    return Counter(f["schluessel"] for f in quellen(t)[0])


# ---------------------------------------------------------------------------
# Zahlen
# ---------------------------------------------------------------------------

def _zahl_norm(kern: str) -> str:
    z = re.sub(r"[ \u00a0\u2009\u202f]", "", kern)
    if "," in z:
        z = z.replace(".", "") if re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d+", z) else z
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", z):
        z = z.replace(".", "")              # Tausenderpunkt
    elif re.fullmatch(r"\d*\.\d+", z):
        z = z.replace(".", ",")             # Dezimalpunkt (0.27, .45)
    if z.startswith(","):
        z = "0" + z
    return z


def _einheit(roh: str, tabelle) -> str:
    roh = roh.strip()
    for muster, kanon in tabelle:
        if re.fullmatch(muster, roh):
            return kanon
    return roh


def zahl_funde(t: str) -> list[dict]:
    """Zahlen mit normalisierter Schreibweise. Fund = {"wert", "weich", "roh", "pos", "laenge"}.

    weich = ausgeschriebenes Zahlwort oder Ziffer vor Bindestrich-Wort (5-stufig): fehlt so eine
    Zahl ohne Ersatz, ist das nur eine Warnung.
    """
    out = []
    for m in ZAHL_KERN_RE.finditer(t):
        a, e = m.start(), m.end()
        wert = _zahl_norm(m.group(0))
        # Vorzeichen: -, − oder – direkt vor der Ziffer, davor Leerraum, =, ( … (nicht COVID-19, 2019–2021)
        if a and t[a - 1] in "-−–" and (a == 1 or t[a - 2] in " \t\n=([:;/"):
            wert, a = "-" + wert, a - 1
        vor = t[max(0, a - 12):a]
        rel = re.search(r"([<>≤≥])\s?$", vor)
        if rel:
            wert = rel.group(1) + wert
        einheit = ""
        sk = SKALA_RE.match(t, e)
        if sk:
            einheit, e = _einheit(sk.group(0), SKALA), sk.end()
        eh = EINHEIT_RE.match(t, e)
        if eh:
            einheit, e = einheit + _einheit(eh.group(0), EINHEIT), eh.end()
        elif VORWAEHRUNG_RE.search(vor):
            einheit += _einheit(VORWAEHRUNG_RE.search(vor).group(0), EINHEIT)
        weich = not einheit and bool(re.match(r"-[a-zäöüß]", t[m.end():m.end() + 2]))
        out.append({"wert": wert + einheit, "weich": weich, "roh": t[a:e], "pos": a, "laenge": e - a, "einheit": einheit})
    # Einheit in Spannen nur einmal geschrieben: „von 45,2 auf 38,7 %“, „3 bis 5 Mrd. Euro“ → beide mit Einheit
    for z, n in reversed(list(zip(out, out[1:]))):
        if not z["einheit"] and not z["weich"] and n["einheit"] and \
                re.fullmatch(r"\s*(?:bis|auf|und|oder|zu|[–/-])\s*", t[z["pos"] + z["laenge"]:n["pos"]]):
            z["einheit"] = n["einheit"]
            z["wert"] += n["einheit"]
    for m in ZAHLWORT_RE.finditer(t):
        wert = ZAHLWORT[m.group(0).lower()]
        eh = EINHEIT_RE.match(t, m.end())
        if eh:
            wert += _einheit(eh.group(0), EINHEIT)
        out.append({"wert": wert, "weich": True, "roh": m.group(0), "pos": m.start(), "laenge": len(m.group(0)), "einheit": ""})
    return sorted(out, key=lambda z: z["pos"])


def zahlen(t: str) -> Counter:
    return Counter(z["wert"] for z in zahl_funde(quellen(t)[1]))


def zahlen_vertauscht(rest_alt: str, rest_neu: str) -> list[dict]:
    """Gleiche Werte derselben Einheit in einem Satz, aber in anderer Reihenfolge (62 %/38 % → 38 %/62 %)."""
    def folgen(t):
        out = []
        for s in SATZ_RE.split(t):
            gruppen: dict = {}
            for z in zahl_funde(s):
                if not z["weich"]:
                    gruppen.setdefault(re.sub(r"^[<>≤≥-]?[\d,.]+", "", z["wert"]), []).append(z["wert"])
            out.extend((s, g) for g in gruppen.values() if len(g) >= 2)
        return out
    neu_folgen = folgen(rest_neu)
    meldungen = []
    for s_alt, f in folgen(rest_alt):
        gleich = [(s, g) for s, g in neu_folgen if Counter(g) == Counter(f)]
        if gleich and not any(g == f for _, g in gleich):
            s_neu, g = gleich[0]
            meldungen.append({"typ": "Zahlen vertauscht?", "wert": f"{' / '.join(f)} → {' / '.join(g)}",
                              "kontext_original": norm(s_alt)[:220], "kontext_neu": norm(s_neu)[:220],
                              "hinweis": "Gleiche Werte in anderer Reihenfolge – prüfen, ob die Zuordnung noch stimmt: "
                                         + norm(s_neu)[:160]})
    return meldungen


# ---------------------------------------------------------------------------
# Zitate, Abkürzungen, Begriffe, Fußnoten
# ---------------------------------------------------------------------------

def _zitat_norm(z: str) -> str:
    z = norm(z.replace("\u00ad", "").replace("...", "…")).replace("*", "").replace("_", " ")
    return norm(z).strip(" .,;:!?…")


def _beleg_ende(text: str, i: int) -> int:
    """Ende einer Quellenklammer direkt hinter einem schließenden Anführungszeichen an Position i (Leerraum dazwischen
    erlaubt): „[2018.06.06_Lehrende, Absatz 8]“, „(ebd., S. 9)“. Gehört zum Zitat, nicht zum Folgesatz; sonst i.
    Gleiches Verhalten wie coach._beleg_ende (Vergleichstest in tests/test_v71_inhalt.py)."""
    j = i
    while j < len(text) and text[j] in " \t\n":
        j += 1
    if j >= len(text) or text[j] not in "[(":
        return i
    auf, zu = text[j], "]" if text[j] == "[" else ")"
    tiefe = 0
    for k in range(j, min(len(text), j + 120)):
        if text[k] == auf:
            tiefe += 1
        elif text[k] == zu:
            tiefe -= 1
            if tiefe == 0:
                return k + 1 if BELEG_INHALT_RE.search(text[j + 1:k]) else i
    return i


def zitat_spannen_absatz(text: str, grenzen: list[tuple[int, int]] | None = None) -> list[tuple[int, int | None, int]]:
    """Wörtliche Zitate in einem Absatz wie coach.zitat_masken: [(Start, Schlusszeichen, Ende)], Start = Position des
    öffnenden Zeichens, Ende hinter dem Schlusszeichen bzw. einer direkt folgenden Belegklammer; Schlusszeichen None bei einem
    nie geschlossenen Zitat (gilt bis zum Satzende laut grenzen, sonst bis zum Absatzende).

    Regeln (identisch mit dem Coach, Vergleichstest in tests/test_v71_inhalt.py): „…“/„…”, “…”, "…", »…« bzw. «…» (das erste
    Guillemet im Absatz bestimmt die Richtung), ebenso ›…‹ bzw. ‹…›; verschachtelte Zitate zählen zum äußeren (Stapel); ein
    gerades " schließt ein „, wenn danach bis zum nächsten „ kein “/” mehr folgt; nie geschlossene Öffner zählen beim erneuten
    Durchlauf nicht mehr mit; nur ein nie geschlossenes „, », «, › bzw. ‹ gilt bis zum Satzende, ein “ oder " nicht."""
    grenzen = grenzen if grenzen is not None else [(0, len(text))]
    erst_g = next((ch for ch in text if ch in "»«"), "»")
    erst_e = next((ch for ch in text if ch in "›‹"), "›")
    oeffner = {"„": "“”", "“": "”", '"': '"', erst_g: "«" if erst_g == "»" else "»", erst_e: "‹" if erst_e == "›" else "›"}
    scan = list(text)
    for i, ch in enumerate(text):
        if ch != "„":
            continue
        j = next((k for k in range(i + 1, len(text)) if text[k] in "“”\"„"), None)
        if j is None or text[j] != '"':
            continue
        k = next((k for k in range(j + 1, len(text)) if text[k] in "“”„"), None)
        if k is None or text[k] == "„":
            scan[j] = "“"

    def durchlauf(ignoriert: set[int]):
        spannen: list[tuple[int, int | None, int]] = []
        stapel: list[tuple[str, str, int]] = []  # (Öffner, Schließer, Start)
        i = 0
        while i < len(text):
            ch = scan[i]
            if i in ignoriert:
                i += 1
                continue
            ebene = next((k for k in range(len(stapel) - 1, -1, -1) if ch in stapel[k][1]), None)
            if ebene is not None:
                start = stapel[ebene][2]
                del stapel[ebene:]
                if not stapel:
                    ende = _beleg_ende(text, i + 1)
                    spannen.append((start, i, ende))
                    i = max(i + 1, ende)
                    continue
            elif ch in oeffner:
                stapel.append((ch, oeffner[ch], i))
            i += 1
        return spannen, stapel

    ignoriert: set[int] = set()
    offene: list[tuple[str, str, int]] = []
    spannen, stapel = durchlauf(ignoriert)
    while stapel:
        offene += stapel
        ignoriert |= {x[2] for x in stapel}
        spannen, stapel = durchlauf(ignoriert)
    for zeichen, _zu, start in offene:
        if zeichen in "„»«›‹":
            spannen.append((start, None, next((e for a, e in grenzen if a <= start < e), len(text))))
    return spannen


def _absaetze_mit_saetzen(t: str):
    """(Absatzbeginn, Absatztext) je Absatz: Absätze an Leerzeilen, eine Überschriftzeile ist ein eigener Absatz."""
    for m in re.finditer(r"(?:(?!\n[ \t\r]*\n)[\s\S])+", t):
        start = m.start()
        zeilen, z0 = [], start
        for zeile in m.group(0).split("\n"):
            if re.match(r"[ \t]*#{1,6}[ \t]", zeile):
                if "".join(zeilen).strip():
                    yield z0, "\n".join(zeilen)
                yield start, zeile
                zeilen, z0 = [], start + len(zeile) + 1
            else:
                zeilen.append(zeile)
            start += len(zeile) + 1
        if "".join(zeilen).strip():
            yield z0, "\n".join(zeilen)


def zitat_spannen(t: str) -> list[dict]:
    """Wörtliche Zitate im ganzen Text: [{"start", "ende", "inhalt": (von, bis) oder None, "art"}], nach Position sortiert.
    art "stapel" = wie der Coach (zitat_spannen_absatz je Absatz, Satzgrenzen nach SATZ_RE; "inhalt" None bei nie
    geschlossenem Zitat), "zusatz" = “…“ bzw. ‚…‘ außerhalb davon. "ende" schließt eine Belegklammer direkt dahinter ein."""
    out = []
    for a0, absatz in _absaetze_mit_saetzen(t):
        grenzen, s0 = [], 0
        for m in SATZ_RE.finditer(absatz):
            grenzen.append((s0, m.start()))
            s0 = m.end()
        grenzen.append((s0, len(absatz)))
        for s, schluss, e in zitat_spannen_absatz(absatz, grenzen):
            out.append({"start": a0 + s, "ende": a0 + e, "inhalt": (a0 + s + 1, a0 + schluss) if schluss is not None else None,
                        "art": "stapel"})
    # nur geschlossene Spannen ausblenden: Ein nie geschlossenes « bzw. „ innerhalb eines “…“-Zitats verschluckte sonst dessen
    # Schlusszeichen, und das ganze Zitat bliebe ungeprüft (v7.1-Prüfung, kn-47466: “Ein didaktisch … schaffen« (DRÄGER 2014).“)
    rest = list(t)
    for z in out:
        if z["inhalt"] is not None:
            rest[z["start"]:z["ende"]] = [ch if ch == "\n" else " " for ch in t[z["start"]:z["ende"]]]
    for m in ZUSATZ_PAAR_RE.finditer("".join(rest)):
        i = next(i for i, g in enumerate(m.groups(), 1) if g is not None)
        out.append({"start": m.start(), "ende": m.end(), "inhalt": (m.start(i), m.end(i)), "art": "zusatz"})
    return sorted(out, key=lambda z: z["start"])


def zitat_funde(t: str) -> list[dict]:
    """Geschlossene wörtliche Zitate (zitat_spannen) mit normalisiertem Wortlaut. Nie geschlossene zählen hier nicht: Der
    Coach schützt sie (keine Aufträge, _ohne_zitate), verglichen wird aber nur, was eindeutig als Zitat abgegrenzt ist."""
    out = []
    for sp in zitat_spannen(t):
        if sp["inhalt"] is None:
            continue
        z = _zitat_norm(t[sp["inhalt"][0]:sp["inhalt"][1]])
        if z:
            out.append({"wert": z, "lang": len(z) >= 12 and len(z.split()) >= 3, "pos": sp["start"],
                        "laenge": sp["inhalt"][1] + 1 - sp["start"]})
    return out


def woertlich(t: str) -> Counter:
    return Counter(z["wert"] for z in zitat_funde(t) if z["lang"])


def akronyme(t: str) -> Counter:
    return Counter(a.rstrip("s") if len(a) > 2 else a for a in AKRONYM_RE.findall(t))


def _satzanfang(t: str, i: int) -> bool:
    """Steht das Wort an Position i am Text-, Zeilen- oder Satzanfang (ggf. hinter Anführungszeichen/Klammer)?"""
    j = i - 1
    while j >= 0 and t[j] in " \t„“\"»«‚'(*#>-–":
        j -= 1
    return j < 0 or t[j] in ".!?:\n"


def _ist_begriff(t: str, m: re.Match) -> bool:
    w = m.group(0)
    if len(w) < 5:
        return False
    if GENDER_ZEICHEN_RE.search(t[max(0, m.start() - 2):m.start()]) and w.lower() in ("innen", "in"):
        return False    # „Bewerber*innen“: die Endung hinter dem Genderzeichen ist kein eigener Begriff
    if w.lower() not in STOP:
        return True
    # „des Mangels“, „das Selbst“: großgeschrieben mitten im Satz ein Nomen, kein Funktionswort
    return w.lower() in NOMEN_HOMOGRAPHE and w[0].isupper() and not _satzanfang(t, m.start())


def begriffe(t: str, ohne: set | None = None, formen: set | None = None) -> Counter:
    """Stämme der Inhaltswörter (Gender-Paare angeglichen, begriff_stamm); ohne = Startpositionen von Wörtern, die nicht
    als Begriff zählen (ersetzbare_stellen); formen = Wortformen beider Texte (wortformen), Standard: dieser Text."""
    formen = wortformen(t) if formen is None else formen
    t = quellen(t)[1]
    return Counter(begriff_stamm(m.group(0), formen) for m in WORT_RE.finditer(t)
                   if _ist_begriff(t, m) and not (ohne and m.start() in ohne))


def _anzeige(t: str, formen: set) -> dict:
    """Begriffsschlüssel → Stamm der ersten Wortform im Text (für Meldungen: „lehrend“ statt des Schlüssels „lehrkraft“)."""
    t = quellen(t)[1]
    out: dict = {}
    for m in WORT_RE.finditer(t):
        if _ist_begriff(t, m):
            out.setdefault(begriff_stamm(m.group(0), formen), stamm(m.group(0)))
    return out


# ---------------------------------------------------------------------------
# Vom Coach zum Ersetzen empfohlene Wörter
# ---------------------------------------------------------------------------

def _lade_json(pfad: str):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ki_muster(pfad: str | None = None) -> list:
    """KI-Muster, die der Coach nennt (Gewicht > 0), kompiliert wie analyse.lade_muster."""
    pfad = pfad or MUSTER_PFAD
    if ("muster", pfad) not in _CACHE:
        out = []
        for m in (_lade_json(pfad) or {}).get("muster", []):
            if (m.get("gewicht") or 0) <= 0:
                continue
            try:
                out.append(re.compile(m["regex"], 0 if m.get("gross_klein") else re.IGNORECASE))
            except (re.error, KeyError, TypeError):
                continue
        _CACHE[("muster", pfad)] = out
    return _CACHE[("muster", pfad)]


def ki_woerter(pfad: str | None = None) -> set:
    """Wörter der Liste typischer Claude-Wörter (wortlisten.json, ki_typisch), auch aus Mehrwort-Einträgen."""
    pfad = pfad or WORTLISTEN_PFAD
    if ("woerter", pfad) not in _CACHE:
        w = set()
        for e in (_lade_json(pfad) or {}).get("ki_typisch", []):
            w.update(x.lower() for x in WORT_RE.findall(str(e.get("ngramm", ""))))
        _CACHE[("woerter", pfad)] = w
    return _CACHE[("woerter", pfad)]


def _ohne_zitate(t: str) -> str:
    """Wörtliche Zitate (zitat_spannen, auch nie geschlossene und die Belegklammer) durch Leerzeichen ersetzen (gleiche
    Positionen): Zitate sind keine Floskeln."""
    rest = list(t)
    for z in zitat_spannen(t):
        rest[z["start"]:z["ende"]] = [ch if ch == "\n" else " " for ch in t[z["start"]:z["ende"]]]
    return "".join(rest)


def _floskel_spannen(t: str, muster: list | None = None) -> tuple[set, set]:
    """(Auslöser, Platzhalter): Spannen (start, ende) der Wörter in KI-Muster-Treffern außerhalb von Anführungszeichen."""
    muster = ki_muster() if muster is None else muster
    maske = _ohne_zitate(t)
    spannen, platz = set(), set()
    for rx in muster:
        for m in rx.finditer(maske):
            a, b = max(0, m.start() - 300), min(len(maske), m.end() + 300)
            fenster = maske[a:b]
            for w in WORT_RE.finditer(maske, m.start(), m.end()):
                if (w.start(), w.end()) in spannen:
                    continue
                d = len(PLATZHALTER) - (w.end() - w.start())
                probe = fenster[:w.start() - a] + PLATZHALTER + fenster[w.end() - a:]
                if not any(x.start() < m.end() - a + d and x.end() > m.start() - a for x in rx.finditer(probe)):
                    spannen.add((w.start(), w.end()))
                else:
                    platz.add((w.start(), w.end()))
    return spannen, platz - spannen


def floskel_kopfwoerter(t: str, muster: list | None = None) -> set:
    """Spannen (start, ende) der Auslöser-Wörter von KI-Muster-Treffern außerhalb von Anführungszeichen.

    Auslöser ist ein Wort, ohne das der Treffer verschwindet („maßgeblich“, „Schlüsselrolle“, „spielt … zentrale
    Rolle“). Platzhalter des Musters, etwa der Inhalt in „nicht X, sondern“ oder das Nomen in „Dieses Ergebnis
    zeigt, dass“, bleiben Begriffe: Ersetzt man sie probeweise, trifft das Muster weiter."""
    return _floskel_spannen(t, muster)[0]


def ersetzbare_stellen(t: str, ersetzbar=(), muster: list | None = None, woerter: set | None = None) -> set:
    """Startpositionen der Wörter in t, die der Coach zum Ersetzen empfiehlt; sie zählen nicht als Begriff.

    - Wörter aus ersetzbar (vom Coach im Verlauf gespeichert, auch flektiert: gleiche Grundform, Komposita nicht), auch
      großgeschrieben – außer Nomen, die im Original nur als Platzhalter in einer Floskel stehen (die „Kostenstruktur“
      in „sowohl die Kostenstruktur … als auch“): Die hat der Coach aus dem Fund übernommen, nicht zum Ersetzen empfohlen
    - typische Claude-Wörter (wortlisten.json), außer als Nomen (großgeschrieben mitten im Satz; am Satzanfang nur,
      wenn das Wort auch mitten im Satz großgeschrieben vorkommt)
    - Auslöser-Wörter von KI-Floskeln; als Nomen nur bei einmaligem Vorkommen im Text (eine „Schlüsselrolle“
      als Floskel), wiederholt gilt das Nomen als Fachwort des Textes und bleibt geschützt"""
    r = quellen(t)[1]
    woerter = ki_woerter() if woerter is None else woerter
    kopf, platz = _floskel_spannen(t, muster)
    funde = list(WORT_RE.finditer(r))
    anzahl = Counter(stamm(m.group(0)) for m in funde if _ist_begriff(r, m))
    nomen_im_text = {m.group(0).lower() for m in funde if m.group(0)[0].isupper() and not _satzanfang(r, m.start())}
    platz_nomen = {grundform(t[a:b]) for a, b in platz if t[a].isupper() and t[a:b].lower() in nomen_im_text}
    frei = {grundform(x) for e in ersetzbar for x in WORT_RE.findall(str(e))} - platz_nomen
    out = set()
    for m in funde:
        w = m.group(0)
        wl = w.lower()
        nomen = w[0].isupper() and wl in nomen_im_text
        if grundform(w) in frei:
            out.add(m.start())
        elif not nomen and wl in woerter:
            out.add(m.start())
        elif (m.start(), m.end()) in kopf and (not nomen or anzahl[stamm(w)] <= 1):
            out.add(m.start())
    return out


def ersetzbar_aus_verlauf(daten) -> set:
    """Vereinigung aller "ersetzbar"-Listen eines Coach-Verlaufs ({"messungen": [{..., "ersetzbar": [...]}, …]})."""
    listen = []
    if isinstance(daten, dict):
        listen.append(daten.get("ersetzbar") or [])
        messungen = daten.get("messungen") or []
    else:
        messungen = daten if isinstance(daten, list) else []
    listen += [m.get("ersetzbar") or [] for m in messungen if isinstance(m, dict)]
    return {x.lower() for liste in listen if isinstance(liste, list) for e in liste for x in WORT_RE.findall(str(e))}


def erwartet_aus_verlauf(daten) -> set:
    """Vereinigung aller "erwartet"-Listen eines Coach-Verlaufs (ab v7): Wortformen, die durch die Aufträge des Coaches
    neu entstehen dürfen (Maskulinform beim Gendern, wiederholtes Nomen beim Teilen, ausgeschriebene Abkürzungen).
    Ältere Verläufe ohne das Feld ergeben eine leere Menge."""
    listen = []
    if isinstance(daten, dict):
        listen.append(daten.get("erwartet") or [])
        messungen = daten.get("messungen") or []
    else:
        messungen = daten if isinstance(daten, list) else []
    listen += [m.get("erwartet") or [] for m in messungen if isinstance(m, dict)]
    return {x.lower() for liste in listen if isinstance(liste, list) for e in liste for x in WORT_RE.findall(str(e))}


def _erwartet_schluessel(erwartet, formen: set | None = None) -> set:
    """Schlüssel, unter denen erwartete Formen im Begriffsvergleich auftauchen: Stamm und begriff_stamm (wie begriffe()).
    Die bloße Wortform gehört nicht dazu: Als Schlüssel stünde sie sonst für jedes Kompositum mit demselben Anfang
    („befragung“ deckte „Befragungsergebnisse“, Schlüssel „befragung“, als neuen Begriff ab)."""
    out = set()
    for e in erwartet:
        for x in WORT_RE.findall(str(e)):
            out |= {stamm(x), begriff_stamm(x, formen)}
    return out


def _unerwartete_begriffe(t: str, erwartet, formen: set) -> Counter:
    """Wie begriffe(), aber ohne Vorkommen, deren ungekürzte Grundform eine erwartete Form ist. Der Begriffsschlüssel
    (9-Zeichen-Stamm) allein reicht nicht: „unternehmer“ deckte sonst neue „Unternehmensberatung“ mit ab."""
    erw_grund = {grundform(g) for e in erwartet for x in WORT_RE.findall(str(e)) for g in (x, gender_form(x, formen))}
    t = quellen(t)[1]
    return Counter(begriff_stamm(m.group(0), formen) for m in WORT_RE.finditer(t)
                   if _ist_begriff(t, m) and grundform(gender_form(m.group(0), formen)) not in erw_grund
                   and grundform(m.group(0)) not in erw_grund)


def _erwartet_abkuerzungen(erwartet) -> set:
    """Erwartete Formen in der Schreibung von akronyme(), kleingeschrieben: Plural-s ab (Coach: „kmus“ = „KMU“), Teile von
    Bindestrich-Wörtern einzeln (Bereinigung verklebter Wörter: „hzb-note“ = „HZB“)."""
    out = set()
    for e in erwartet:
        for x in WORT_RE.findall(str(e)):
            for t in {x.lower()} | set(x.lower().split("-")):
                out |= {t, t[:-1] if len(t) > 3 and t.endswith("s") else t}
    return out


def fussnoten(t: str) -> list[tuple[str, int]]:
    t = HOCH_EINHEIT_RE.sub(lambda m: " " * len(m.group(0)), t)
    return [(m.group(0), m.start()) for m in FUSSNOTE_RE.finditer(t)]


def absaetze(t: str) -> int:
    return len([b for b in re.split(r"\n\s*\n", t) if b.strip() and not b.strip().startswith("#")])


def _analyse_modul():
    """analyse.py aus text-analyse/scripts (wie coach.py es lädt) oder None, wenn es fehlt. Wird erst bei Bedarf geladen."""
    if "analyse" not in _CACHE:
        modul = None
        pfad = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "text-analyse", "scripts"))
        if os.path.exists(os.path.join(pfad, "analyse.py")):
            if pfad not in sys.path:
                sys.path.insert(0, pfad)
            try:
                import analyse as modul  # noqa: PLC0415
            except Exception:  # noqa: BLE001 – die Zählung wie im Coach ist eine Zusatzangabe
                modul = None
        _CACHE["analyse"] = modul
    return _CACHE["analyse"]


def woerter_wie_coach(t: str) -> int | None:
    """Wortzahl so, wie coach.py sie im Kopf nennt (analyse.py, info['woerter']): ohne Überschriften, Quellenverweise,
    Belegklammern, Fußnoten und Transkript-Notation, Zahlen nicht als Wort. None, wenn analyse.py nicht verfügbar ist."""
    a = _analyse_modul()
    if a is None:
        return None
    try:
        struktur = a.zerlege_bloecke(t)
        schon = set(struktur.get("bereinigt", ()))
        zaehler: Counter = Counter()
        return sum(1 for i, roh in enumerate(struktur["absaetze"])
                   for s in a.zerlege_saetze(roh if i in schon else a.bereinige_absatz(roh, zaehler))
                   for tok in a.tokens(s) if a.ist_wort(tok))
    except Exception:  # noqa: BLE001
        return None


def differenz(alt: Counter, neu: Counter):
    fehlt = alt - neu
    neu_dazu = neu - alt
    return sorted(fehlt.elements()), sorted(neu_dazu.elements())


# ---------------------------------------------------------------------------
# Vergleich
# ---------------------------------------------------------------------------

def _erster(funde, schl, wert):
    return next(f for f in funde if f[schl] == wert)


def _vergleiche_zahlen(alt, neu, z_alt, z_neu, res, gut_alt=(), gut_neu=()):
    """gut_alt/gut_neu: Jahre aufgelöster Verweise; sie heben nur bestehende Differenzen auf."""
    t_a, t_n = Counter(z["wert"] for z in z_alt), Counter(z["wert"] for z in z_neu)
    h_a = Counter(z["wert"] for z in z_alt if not z["weich"])
    h_n = Counter(z["wert"] for z in z_neu if not z["weich"])
    hart, weich = [], []
    for w in t_a:
        if t_a[w] > t_n[w]:
            n_hart = max(0, h_a[w] - t_n[w])      # Ziffern zuerst gegen die Überarbeitung abgleichen
            hart += [("fehlt", w)] * min(n_hart, t_a[w] - t_n[w])
            weich += [("fehlt", w)] * (t_a[w] - t_n[w] - min(n_hart, t_a[w] - t_n[w]))
    for w in t_n:
        if t_n[w] > t_a[w]:
            n_hart = max(0, h_n[w] - t_a[w])
            hart += [("neu", w)] * min(n_hart, t_n[w] - t_a[w])
            weich += [("neu", w)] * (t_n[w] - t_a[w] - min(n_hart, t_n[w] - t_a[w]))
    for richtung, jahre in (("neu", gut_alt), ("fehlt", gut_neu)):
        for j in jahre:
            if (richtung, j) in hart:
                hart.remove((richtung, j))
    # Zahlwort ersetzt (drei → vier) ist hart; Zahlwort ohne Gegenstück (zwei → beide) nur Warnung
    if {r for r, _ in weich} == {"fehlt", "neu"}:
        hart, weich = hart + weich, []
    for richtung, w in dict.fromkeys(hart):
        if richtung == "fehlt":
            z = _erster(z_alt, "wert", w)
            res["harte_verluste"].append({"typ": "Zahl", "wert": w, "fund": norm(z["roh"]),
                                          "kontext_original": kontext(alt, z["pos"], z["laenge"])})
        else:
            z = _erster(z_neu, "wert", w)
            res["erfindungen"].append({"typ": "Zahl", "wert": w, "fund": norm(z["roh"]),
                                       "kontext_neu": kontext(neu, z["pos"], z["laenge"])})
    for richtung, w in dict.fromkeys(weich):
        quelle, text = (z_alt, alt) if richtung == "fehlt" else (z_neu, neu)
        z = _erster(quelle, "wert", w)
        res["warnungen"].append({"typ": "Zahlwort " + ("fehlt" if richtung == "fehlt" else "neu"), "wert": w,
                                 "hinweis": f"„{norm(z['roh'])}“ – " + kontext(text, z["pos"], z["laenge"], 50)})


def _nstamm(n: str) -> str:
    return n[:-1] if n.endswith("s") and len(n) > 4 else n      # Müllers → Müller


def _naehe(text: str, namen, jahr: str, breite: int = 80) -> bool:
    """Stehen Nachname und Jahr in der Nähe (Verweis in Fließtext aufgelöst: „Müller zeigte 2019 …“)?"""
    if not namen or not jahr:
        return False
    j = re.escape(re.sub(r"[a-z]$", "", jahr))
    for m in re.finditer(rf"(?<!\d){j}(?!\d)", text):
        umfeld = text[max(0, m.start() - breite):m.end() + breite].lower()
        if any(re.search(rf"(?<![\wäöüß]){re.escape(_nstamm(n))}", umfeld) for n in namen):
            return True
    return False


def _vergleiche_quellen(alt, neu, q_alt, q_neu, rest_alt, rest_neu, res):
    """Meldet Quellenverluste/-erfindungen. Rückgabe: Jahre aufgelöster Verweise (alt, neu), die auf der
    Gegenseite jetzt als Zahl im Fließtext stehen und beim Zahlenvergleich gutgeschrieben werden."""
    gut_alt, gut_neu = [], []
    c_alt, c_neu = Counter(q["schluessel"] for q in q_alt), Counter(q["schluessel"] for q in q_neu)
    fehlt, dazu = list(c_alt - c_neu), list(c_neu - c_alt)
    # gleiche Jahr/Fundstelle und gemeinsamer Autor → Angabe verändert (Koautor, et al.), keine Erfindung
    def passt(qa, qn):
        return qa["jahr"] == qn["jahr"] and qa["fund"] == qn["fund"] and \
            {_nstamm(n) for n in qa["namen"]} & {_nstamm(n) for n in qn["namen"]}

    fehlt0, dazu0 = list(fehlt), list(dazu)
    for f in fehlt0:
        qa = _erster(q_alt, "schluessel", f)
        qn = next((_erster(q_neu, "schluessel", d) for d in dazu0 if passt(qa, _erster(q_neu, "schluessel", d))), None)
        if qn:
            res["warnungen"].append({"typ": "Quellenangabe verändert", "wert": f"{qa['roh']} → {qn['roh']}",
                                     "hinweis": "Autorenangabe weicht ab (Koautor, et al.) – prüfen."})
            fehlt.remove(f)
    dazu = [d for d in dazu0 if not any(passt(_erster(q_alt, "schluessel", f), _erster(q_neu, "schluessel", d)) for f in fehlt0)]
    # aufgelöst gilt ein Verweis nur, wenn sein Jahr auf der Gegenseite als zusätzliche Zahl im Fließtext steht
    j_alt = Counter(m.group(0) for m in re.finditer(r"(?<![\d.,])(?:1[5-9]|20)\d{2}(?![\d.,]\d)", rest_alt))
    j_neu = Counter(m.group(0) for m in re.finditer(r"(?<![\d.,])(?:1[5-9]|20)\d{2}(?![\d.,]\d)", rest_neu))
    for f in fehlt:
        q = _erster(q_alt, "schluessel", f)
        j = re.sub(r"[a-z]$", "", q["jahr"])
        if not q["fund"] and j_neu[j] > j_alt[j] and _naehe(rest_neu, q["namen"], q["jahr"]):
            j_neu[j] -= 1
            res["warnungen"].append({"typ": "Quellenverweis umformuliert", "wert": q["roh"],
                                     "hinweis": "Autor und Jahr stehen noch im Text, aber nicht mehr als Verweis – prüfen."})
            gut_alt.append(j)
            continue
        res["harte_verluste"].append({"typ": "Quellenverweis", "wert": q["roh"], "schluessel": f,
                                      "kontext_original": kontext(alt, q["pos"], len(q["roh"]))})
    for d in dazu:
        q = _erster(q_neu, "schluessel", d)
        j = re.sub(r"[a-z]$", "", q["jahr"])
        if not q["fund"] and j_alt[j] > j_neu[j] and _naehe(rest_alt, q["namen"], q["jahr"]):
            j_alt[j] -= 1
            res["warnungen"].append({"typ": "Quellenverweis umformuliert", "wert": q["roh"],
                                     "hinweis": "Autor und Jahr standen im Original im Fließtext – prüfen."})
            gut_neu.append(j)
            continue
        res["erfindungen"].append({"typ": "Quellenverweis", "wert": q["roh"], "schluessel": d,
                                   "kontext_neu": kontext(neu, q["pos"], len(q["roh"]))})
    return gut_alt, gut_neu


def _vergleiche_zitate(alt, neu, res):
    z_alt, z_neu = zitat_funde(alt), zitat_funde(neu)
    fehlt, dazu = differenz(Counter(z["wert"] for z in z_alt), Counter(z["wert"] for z in z_neu))
    for f in dict.fromkeys(fehlt):
        z = _erster(z_alt, "wert", f)
        if z["lang"]:
            res["harte_verluste"].append({"typ": "Wörtliches Zitat", "wert": f, "kontext_original": kontext(alt, z["pos"], z["laenge"])})
        elif not re.search(rf"(?<![\wäöüß]){re.escape(f)}(?![\wäöüß])", neu, re.I):
            res["warnungen"].append({"typ": "Kurzes Zitat/Begriff fehlt", "wert": f,
                                     "hinweis": "In Anführungszeichen zitierter Begriff fehlt in der Überarbeitung – " + kontext(alt, z["pos"], z["laenge"], 50)})
    for d in dict.fromkeys(dazu):
        z = _erster(z_neu, "wert", d)
        if z["lang"]:
            res["erfindungen"].append({"typ": "Wörtliches Zitat", "wert": d, "kontext_neu": kontext(neu, z["pos"], z["laenge"])})
        elif not re.search(rf"(?<![\wäöüß]){re.escape(d)}(?![\wäöüß])", alt, re.I):
            res["warnungen"].append({"typ": "Kurzes Zitat/Begriff neu", "wert": d,
                                     "hinweis": "Neuer Begriff in Anführungszeichen – " + kontext(neu, z["pos"], z["laenge"], 50)})


def pruefe(alt: str, neu: str, ersetzbar=(), erwartet=()) -> dict:
    """ersetzbar: Wörter, die der Coach zum Ersetzen empfohlen hat (z. B. aus ersetzbar_aus_verlauf).
    erwartet: Wortformen, die durch die Aufträge des Coaches neu entstehen dürfen (erwartet_aus_verlauf); sie zählen
    nicht als „Neuer häufiger Begriff“ und ihre Abkürzungen nicht als neu. Harte Funde (Zahlen, Quellen, Zitate,
    Fußnoten) bleiben davon unberührt."""
    alt = unicodedata.normalize("NFC", alt)
    neu = unicodedata.normalize("NFC", neu)
    res: dict = {"harte_verluste": [], "erfindungen": [], "warnungen": [], "kennzahlen": {}}
    formen = wortformen(alt, neu)      # Bezugsmenge für die Gender-Paare: Gegenform in einem der beiden Texte
    erw = _erwartet_schluessel(erwartet, formen)
    erw_abk = _erwartet_abkuerzungen(erwartet)

    q_alt, rest_alt = quellen(alt)
    q_neu, rest_neu = quellen(neu)
    gut_alt, gut_neu = _vergleiche_quellen(alt, neu, q_alt, q_neu, rest_alt, rest_neu, res)
    # Positionen im Rest-Text entsprechen denen im Original (Verweise sind nur ausgeblendet)
    _vergleiche_zahlen(alt, neu, zahl_funde(rest_alt), zahl_funde(rest_neu), res, gut_alt, gut_neu)
    _vergleiche_zitate(alt, neu, res)
    res["warnungen"].extend(zahlen_vertauscht(rest_alt, rest_neu))

    a_alt, a_neu = akronyme(alt), akronyme(neu)
    fehlt, dazu = differenz(a_alt, a_neu)
    for f in dict.fromkeys(fehlt):
        res["warnungen"].append({"typ": "Abkürzung", "wert": f, "kontext_original": kontext(alt, alt.find(f), len(f)),
                                 "hinweis": ("fehlt in der Überarbeitung ganz" if not a_neu[f]
                                             else f"im Original {a_alt[f]}×, jetzt {a_neu[f]}×")
                                 + " – prüfen, ob eine Aussage weggefallen ist."})
    for d in dict.fromkeys(dazu):
        if d.lower() in erw_abk:
            continue    # vom Coach verlangt (z. B. Nomen beim Teilen wiederholt: „Die ESRS wurden …“)
        if a_alt[d]:
            continue    # steht schon im Original: nur öfter genannt (Nomen beim Teilen wiederholt), kein neuer Inhalt
        res["warnungen"].append({"typ": "Abkürzung", "wert": d, "kontext_neu": kontext(neu, neu.find(d), len(d)),
                                 "hinweis": "neu, im Original nicht enthalten – prüfen, ob Inhalt hinzugekommen ist."})

    # Fachbegriffe: mehrfach im Original, ganz verschwunden in der Überarbeitung. Wörter, die der Coach zum Ersetzen
    # empfiehlt (Floskel-Auslöser, typische Claude-Wörter, Verlauf), zählen im Original nicht als Begriff. Schlüssel ist
    # begriff_stamm: Gender-Paare („Bewerbende“/„Bewerber“) gelten als derselbe Begriff.
    ohne = ersetzbare_stellen(alt, ersetzbar)
    b_roh, b_neu = begriffe(alt, formen=formen), begriffe(neu, formen=formen)
    b_alt = begriffe(alt, ohne, formen)
    zeig_alt, zeig_neu = _anzeige(alt, formen), _anzeige(neu, formen)
    verschwunden = [s for s, n in b_alt.most_common() if n >= 2 and b_neu[s] == 0]
    if verschwunden:
        res["warnungen"].append({"typ": "Begriff verschwunden", "wert": ", ".join(zeig_alt.get(s, s) for s in verschwunden[:25]),
                                 "hinweis": "Kommt im Original mehrfach vor, in der Überarbeitung gar nicht mehr. Synonym-Ersatz bei Fachbegriffen vermeiden."})
    # lange Fachwörter (Nomen, nicht am Satzanfang) schon bei einmaligem Verschwinden melden
    r_alt, r_neu = quellen(alt)[1], quellen(neu)[1]
    lang = [m.group(0) for m in re.finditer(r"(?<=[\wäöüß,;:)\]] )[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜa-zäöüß]+)*", r_alt)
            if len(m.group(0)) >= 13 and b_alt[begriff_stamm(m.group(0), formen)] < 2 and m.group(0).lower() not in NICHT_AUTOR
            and m.group(0).lower() not in STOP and m.start() not in ohne]
    staemme_neu = {begriff_stamm(x, formen) for x in WORT_RE.findall(r_neu)}
    ersetzt = [w for w in dict.fromkeys(lang) if begriff_stamm(w, formen) not in staemme_neu]
    if ersetzt:
        res["warnungen"].append({"typ": "Fachwort ersetzt?", "wert": ", ".join(ersetzt[:15]),
                                 "hinweis": "Langes Fachwort aus dem Original fehlt in der Überarbeitung – Synonym oder gestrichene Aussage?"})
    # zur Nachvollziehbarkeit: was ohne die Coach-Ausnahmen gemeldet worden wäre
    gemeldet = set(verschwunden) | {begriff_stamm(w, formen) for w in ersetzt}
    res["nicht_gemeldet"] = sorted({m.group(0).lower() for m in WORT_RE.finditer(r_alt)
                                    if m.start() in ohne and _ist_begriff(r_alt, m)
                                    and b_neu[begriff_stamm(m.group(0), formen)] == 0
                                    and begriff_stamm(m.group(0), formen) not in gemeldet
                                    and (b_roh[begriff_stamm(m.group(0), formen)] >= 2
                                         or (len(m.group(0)) >= 13 and m.group(0)[0].isupper()))})
    # neue häufige Begriffe; vom Coach erwartete Formen (Verlauf "erwartet") zählen nicht
    b_unerw = _unerwartete_begriffe(neu, erwartet, formen) if erw else b_neu
    neu_haeufig = [s for s, n in b_neu.most_common() if n >= 3 and b_roh[s] == 0 and (s not in erw or b_unerw[s] >= 3)]
    if neu_haeufig:
        res["warnungen"].append({"typ": "Neuer häufiger Begriff", "wert": ", ".join(zeig_neu.get(s, s) for s in neu_haeufig[:15]),
                                 "hinweis": "Taucht neu und mehrfach auf – prüfen, ob dadurch Inhalt hinzugekommen ist."})
    erw_neu = sorted({zeig_neu.get(s, s) for s, n in b_neu.items() if n >= 3 and b_roh[s] == 0 and s in erw and b_unerw[s] < 3})
    if erw_neu:
        res["erwartet_neu"] = erw_neu

    h_alt, h_neu = UEBERSCHRIFT_RE.findall(alt), UEBERSCHRIFT_RE.findall(neu)
    if [norm(h) for h in h_alt] != [norm(h) for h in h_neu]:
        res["warnungen"].append({"typ": "Überschriften geändert", "wert": f"{len(h_alt)} → {len(h_neu)}",
                                 "hinweis": "Überschriften sollten beim Umschreiben unverändert bleiben."})

    # Fußnotenmarker nach Identität vergleichen (gelöscht, getauscht), nicht nur nach Anzahl
    f_alt, f_neu = fussnoten(alt), fussnoten(neu)
    fehlt, dazu = differenz(Counter(f for f, _ in f_alt), Counter(f for f, _ in f_neu))
    for f in dict.fromkeys(fehlt):
        pos = next(p for x, p in f_alt if x == f)
        res["harte_verluste"].append({"typ": "Fußnotenmarker", "wert": f, "kontext_original": kontext(alt, pos, len(f))})
    for d in dict.fromkeys(dazu):
        pos = next(p for x, p in f_neu if x == d)
        res["erfindungen"].append({"typ": "Fußnotenmarker", "wert": d, "kontext_neu": kontext(neu, pos, len(d))})

    w_alt, w_neu = len(WORT_RE.findall(alt)), len(WORT_RE.findall(neu))
    verh = w_neu / w_alt if w_alt else 0
    # Zusatzangabe: Wortzahl wie im Kopf des Coaches (ohne Quellenverweise usw.), damit die Zahlen nicht verwirren
    res["kennzahlen"] = {"woerter_original": w_alt, "woerter_neu": w_neu, "verhaeltnis": round(verh, 3),
                         "woerter_coach_original": woerter_wie_coach(alt), "woerter_coach_neu": woerter_wie_coach(neu),
                         "absaetze_original": absaetze(alt), "absaetze_neu": absaetze(neu)}
    if verh < 0.85 or verh > 1.2:
        res["warnungen"].append({"typ": "Umfang", "wert": f"{round(100 * verh)} % der Originallänge",
                                 "hinweis": "Starke Längenänderung deutet auf weggelassene oder hinzugefügte Inhalte hin."})
    # Umfang je Absatz (nur bei gleicher Absatzzahl): ein gelöschter Satz fällt im Gesamttext kaum auf
    a_abs = [b for b in re.split(r"\n\s*\n", alt) if b.strip() and not b.strip().startswith(("#", "[^", "¹"))]
    n_abs = [b for b in re.split(r"\n\s*\n", neu) if b.strip() and not b.strip().startswith(("#", "[^", "¹"))]
    if len(a_abs) == len(n_abs) > 1:
        for i, (x, y) in enumerate(zip(a_abs, n_abs), 1):
            wx = len(WORT_RE.findall(x))
            v = len(WORT_RE.findall(y)) / wx if wx else 1.0
            if wx >= 30 and v < 0.75:
                res["warnungen"].append({"typ": "Absatz gekürzt", "wert": f"Absatz {i}: {round(100 * v)} %",
                                         "hinweis": "Deutlich kürzer als im Original – möglicherweise ist eine Aussage weggefallen."})
    res["ok"] = not res["harte_verluste"] and not res["erfindungen"]
    return res


def bericht(res: dict) -> str:
    out = ["## Inhaltscheck", ""]
    k = res["kennzahlen"]
    coach_zahl = ""
    if k.get("woerter_coach_original") is not None and k.get("woerter_coach_neu") is not None:
        coach_zahl = (f" · wie im Coach gezählt (ohne Überschriften, Quellenverweise und Fußnoten): "
                      f"{k['woerter_coach_original']} → {k['woerter_coach_neu']}")
    out.append(f"Wörter: {k['woerter_original']} → {k['woerter_neu']} ({round(100 * k['verhaeltnis'])} %){coach_zahl}"
               f" · Absätze: {k['absaetze_original']} → {k['absaetze_neu']}")
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
    if res.get("nicht_gemeldet"):
        out.append("\n_Nicht als Verlust gewertet (vom Coach zum Ersetzen empfohlen): " + ", ".join(res["nicht_gemeldet"][:20]) + "._")
    if res.get("erwartet_neu"):
        out.append("\n_Nicht als neuer Begriff gewertet (vom Coach verlangte Form): " + ", ".join(res["erwartet_neu"][:20]) + "._")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("original")
    ap.add_argument("neu")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--verlauf", help="Verlaufsdatei von coach.py (TEXT.coach.json): dort unter \"ersetzbar\" "
                                      "gespeicherte Wörter gelten nicht als verschwundene Begriffe, unter \"erwartet\" "
                                      "gespeicherte nicht als neue Begriffe")
    args = ap.parse_args(argv)
    ersetzbar, erwartet = set(), set()
    if args.verlauf:
        daten = _lade_json(args.verlauf)
        if not daten and not os.path.exists(args.verlauf):
            print(f"Hinweis: Verlaufsdatei {args.verlauf} nicht gefunden – geprüft wird ohne Coach-Liste.", file=sys.stderr)
        ersetzbar = ersetzbar_aus_verlauf(daten)
        erwartet = erwartet_aus_verlauf(daten)
    res = pruefe(lesen(args.original), lesen(args.neu), ersetzbar, erwartet)
    if args.format == "json":
        json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print(bericht(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
