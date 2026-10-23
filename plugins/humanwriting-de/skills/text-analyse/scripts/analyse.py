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

Eingabeformate: .txt, .md (UTF-8, UTF-16, Windows-1252), .docx und .odt (ohne Zusatzpakete),
.pdf (falls pdftotext installiert). .doc, .rtf und .pages werden mit Meldung abgelehnt.
Nur Python-Standardbibliothek, Python >= 3.8.

Messkonventionen (ausführlich: references/kennzahlen-methodik.md):
- Satzlänge = Token nach TOKEN_RE (Wörter und Zahlen; eine Ziffernfolge zählt als 1 Token).
- Wortlängen- und Silbenmaße nur über Buchstabenwörter, ohne Ein-Buchstaben-Token, vokallose
  Abkürzungen (bzw, vgl) und Akronyme (KMU, USA); Abkürzungen zählt abkuerzungen_pro_1000.
- Silbe = Vokal oder Diphthong (Best); i/u vor Vokal sind eigene Kerne (In-for-ma-ti-on, Stu-di-en).
- Teilsatz = Segment mit finitem Verb (Stufe 1: Kommas, Subjunktionen, Relativpronomen, Verbletztstellung);
  Infinitivgruppen (um … zu, erweiterter Infinitiv) zählen nicht als Teilsatz.
- Typen = kleingeschriebene Wortformen, keine Lemmata (Homographen verschmelzen).
- satzlaenge_dispersion = Var/Ø (Ords I), satzlaenge_schiefe = g1, autokorrelation normiert mit 1/N.
- Längenabhängige Kennzahlen (satzlaenge_schiefe, mattr_klumpung_100) = Median über Fenster à 800 Wörter
  (Länge der Kalibrierabschnitte); kürzere Texte werden am Stück gemessen.
- Blockmodus (analysiere_und_bewerte): Texte über 1200 Wörtern werden in Blöcke von etwa 800 Wörtern zerlegt und
  blockweise bewertet; die Gesamtbewertung nutzt je Kennzahl den Median über die Blöcke.
- v7: Transkriptnotation ((lacht), (unv.), (I: …)) und Belege in eckigen Klammern mit Jahr fallen vor der Satztrennung
  weg; info meldet verklebte Wörter aus der PDF-Extraktion ('verklebt', mit Warnung), den Anteil der Wörter in
  wörtlichen Zitaten ('zitat_anteil') und die entfernte Transkriptnotation ('transkript_notation'). Autorenlisten vor
  einer Jahresangabe zählen nicht als Dreierliste.
- v7: bewerte() gibt je Kennzahl die Seite der Abweichung ('ki'/'gegen') und 'jenseits_band' aus, dazu den einseitigen
  Score 'score_ki' (Abweichungen auf der Gegenseite der KI zählen wie grün). Das Modell kappt jedes Merkmal vorher
  einseitig am menschlichen Band (modell['kappen']): Übertreibung jenseits P10/P90 zählt nicht als „noch menschlicher“.
"""
from __future__ import annotations

import argparse
import codecs
import json
import math
import os
import re
import statistics
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from functools import lru_cache

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
    abb abs abschn abt adj adv akad allg anh anm aufl ausg bd bde bearb beil bes betr bez bspw bsp
    bzgl bzw ca chr co corp dipl dgl dr dt durchschn ebd eig einschl engl entspr erg erw etc ev evtl exkl
    f ff fa fam frz geb gegr gem ges gest ggf ggü hg hrsg hl i inkl insb int jh jhd jg jr kap kath kfz kl
    lfd lt ltd max min mio mod mrd mt nachf nr no o od orig pkt pl prof proz rd red resp s sen sog sp st std
    str stud tab tel teilw tsd u ua ug usf usw v verf vgl vol vs wg wiss z zb zt zit zzgl zw zus et al
    inc e d h m vlt ggfs feb mär apr jun jul aug sep sept okt nov ders diess hgg
    mind ziff rn rdnr fn anl mill diss univ sc pp hs inst verl nachdr hervorh herv darst ugs var sek mitarb lit kfm
    """.split()
)
# Echte Wörter, die auch als Abkürzung vorkommen: nur vor Zahl/Verweis keine Satzgrenze ("Art. 5 GG")
MEHRDEUTIG = {"art", "alt", "dies", "jan", "dez"}
# Abkürzungen, die zugleich Satzende sein können ("… usw. Die …")
SATZENDE_FAEHIG = {"usw", "usf", "etc", "ebd"}
SEITEN_FOLGE = {"f", "ff"}  # nur klein und nach Zahl: "S. 12 ff."

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

# Großgeschriebenes Folgewort nach Zahl/Abkürzung mit Punkt, das einen neuen Satz anzeigt
STARTWOERTER = (SATZSTARTER | FUNKTIONSWOERTER | SUBJUNKTIONEN | NEBENORDNER | PRAEPOSITIONEN
                | {k.split()[0] for k in KONNEKTOR_ANFAENGE}
                | set("weiterhin ferner zusätzlich deutlich zuvor auffällig keiner keine folglich dennoch trotzdem vielmehr anhand mittels".split())
                ) - {"bzw", "usw", "etc", "ca"}

# Konnektoren in allen Stellungen (HW15); "darüber hinaus" fehlt bewusst (eigenes KI-Muster)
KONNEKTOREN = [
    "zudem", "außerdem", "ferner", "des weiteren", "weiterhin", "folglich", "somit", "demnach", "infolgedessen",
    "allerdings", "jedoch", "dennoch", "gleichwohl", "nichtsdestotrotz", "insbesondere", "letztlich", "letztendlich",
    "zugleich", "gleichzeitig", "schließlich", "hingegen", "wiederum",
]
KONNEKTOR_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k).replace(" ", r"\s+") for k in KONNEKTOREN if k != "des weiteren")
    + r"|des\s+weiteren\b(?!\s+(?-i:[A-ZÄÖÜ])[\wäöüß-]*(?:e?s|en)\b))\b",  # nicht Genitiv "des weiteren Vorgehens"
    re.IGNORECASE,
)

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

# Funktionswort-Profil (HW07): Pilotliste der 40 häufigsten Funktionswörter ohne Konnektoren
FW_WOERTER = [
    "die", "der", "und", "in", "zu", "von", "den", "das", "werden", "auf", "im", "sich", "eine", "ist", "für", "mit",
    "des", "auch", "als", "ein", "es", "wird", "nicht", "dass", "dem", "sind", "oder", "an", "einer", "bei", "durch",
    "wie", "sie", "diese", "um", "aus", "kann", "zur", "einen", "können",
]

# Satzklammer (HW08): finite Hilfs- und Modalverben; Infinitiv-Hilfsverben am Klammerende
HILFSVERBEN = set(
    """
    ist sind war waren sei seien wäre wären bin bist seid hat haben hatte hatten hätte hätten habe hast habt
    wird werden wurde wurden würde würden werde wirst werdet kann können konnte konnten könnte könnten muss
    müssen musste mussten müsste müssten soll sollen sollte sollten will wollen wollte wollten darf dürfen
    durfte durften dürfte dürften mag mögen mochte möchte möchten lässt lassen ließ ließen
    """.split()
)
KLAMMER_INF_ENDE = {"werden", "worden", "sein", "haben", "können", "müssen", "sollen", "dürfen", "wollen", "lassen", "gewesen", "geworden"}

# Teilsätze (HW03 Stufe 1)
NUR_NACH_KOMMA = {"bis", "ehe", "seitdem", "soweit"}  # sonst meist Präposition/Adverb ("bis 2020", "Seitdem hat …")
SUBJ_UEBERALL = SUBJUNKTIONEN - NUR_NACH_KOMMA
SATZANFANG_SUBJ = {"bis", "ehe", "soweit", "da", "während", "wie"}  # "Da die Stichprobe klein war, …"
BIS_PRAEP_FOLGE = {"zu", "zum", "zur", "auf", "heute", "dato", "hin", "in", "ins", "an", "nach", "ende", "mitte", "anfang",
                   "etwa", "ca", "circa", "spätestens", "einschließlich", "inklusive", "maximal", "mindestens", "kurz",
                   "vor", "zuletzt", "jetzt", "dahin"}
ARTIKEL_KONJ = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "eines", "und", "oder", "sowie"}
FINIT = set(
    """
    ist sind war waren wird wurde wurden hat hatte hatten kann konnte konnten muss musste mussten soll sollte
    sollten will wollte darf durfte mag möchte würde würden wäre wären hätte hätten sei seien gibt gab gilt galt
    lässt bin bist seid habe hast habt
    """.split()
)
FINIT_MEHRDEUTIG = {"werden", "haben", "können", "müssen", "sollen", "wollen", "dürfen", "sein"}

# Passiv
_PRAEFIX = r"(?:be|er|ver|ent|zer|emp|miss|wider|hinter|über|unter|durch|um)"
_PARTIKEL = (r"(?:ab|an|auf|aus|bei|dar|durch|ein|fest|fort|her|hin|mit|nach|vor|weg|weiter|wieder|zu|zurück|zusammen|wahr|"
             r"statt|frei|bereit|hervor|heraus|heran|herbei|herunter|hinzu|hinein|voran|voraus|um|vorbei|offen|klar|"
             r"gegenüber|entgegen|nieder|los|kennen)")
_P2 = rf"(?:{_PARTIKEL})?(?:(?!zu(?!rück|sammen)){_PARTIKEL})?"  # bis zu 2 Partikeln ("miteinbezogen"), kein zu-Infix
PARTIZIP_T = re.compile(rf"\w*ge\w{{2,}}t|{_P2}{_PRAEFIX}\w{{2,}}t|\w{{3,}}iert|getan")
PARTIZIP_GE_EN = re.compile(rf"{_P2}ge\w{{2,}}en")
PARTIZIP_EN_ABLAUT = re.compile(
    rf"{_P2}{_PRAEFIX}\w*(?:[^e]ieben|[^e]ichen|[^e]iffen|itten|[^e]ieden|[^e]iesen|ogen|oben|ossen|ochen|ommen|ohlen|"
    rf"olfen|onnen|orben|orfen|offen|oren|unden|ungen|anden)"
)
PARTIZIP_EN_OHNE_GE = re.compile(rf"{_P2}{_PRAEFIX}\w{{2,}}en")  # = Infinitivform, nur in eindeutigem Kontext
GE_INFINITIVE = {"gehören", "gelingen", "geschehen", "gewinnen", "genießen", "gestalten", "gewähren", "gewährleisten",
                 "gelten", "gebrauchen", "gefährden", "gestehen", "gewöhnen", "genügen"}
WERDEN_PRAET = {"wurde", "wurden", "wurdest", "wurdet", "worden"}
MODALVERBEN = {"kann", "können", "könnte", "könnten", "konnte", "konnten", "muss", "müssen", "musste", "mussten", "müsste",
               "müssten", "soll", "sollen", "sollte", "sollten", "darf", "dürfen", "durfte", "durften", "dürfte", "dürften",
               "will", "wollen", "wollte", "wollten", "mag", "mögen", "möchte", "möchten"}
KEIN_PARTIZIP = {"überhaupt", "bereit", "gesamt", "insgesamt", "gerecht", "unbedingt", "vielleicht", "erneut", "bekannt",
                 "bewusst", "gezielt"}
TRANSPARENT = set("„“”\"»«‚‘'()[]")

# Abkürzungen (HW05): Stil-Abkürzungen als Kennzahl, Verweis-Abkürzungen nur als Info
ABK_STIL_RE = re.compile(
    r"(?<![\wÄÖÜäöüß])(?:z\.\s?B\.|d\.\s?h\.|u\.\s?a\.|i\.\s?d\.\s?R\.|u\.\s?U\.|bzw\.|ggf\.|bspw\.|usw\.|etc\.|ca\.|"
    r"sog\.|insb\.|evtl\.)", re.IGNORECASE)
ABK_VERWEIS_RE = re.compile(r"(?<![\wÄÖÜäöüß])(?:vgl\.|S\.(?=\s?\d)|ff?\.(?=\s|$)|ebd\.|Hrsg\.|Abb\.|Kap\.)")
AKRONYM_RE = re.compile(r"[A-ZÄÖÜ]{2,5}s?")

# Nominalketten (HW13)
GENVERB = {"des", "der", "eines", "einer", "dieses", "dieser", "seines", "seiner", "ihres", "ihrer", "von", "vom"}
ROH_TOKEN_RE = re.compile(r"[\wÄÖÜäöüß-]+|[,;:()\[\]–—„“\"]")

LITERATUR_UEBERSCHRIFT = re.compile(
    r"^\s*(?:#+\s*)?[*_]{0,2}\s*"
    r"(?:\d+(?:\.\d+)*\.?\s*|(?-i:[IVXLC]+)(?:\.\s*|\s+))?"  # '7.', '7 ', '7.Lit…', 'VII.' – römisch nur groß
    r"(?:(?:(?:Quellen|Literatur)-?\s*und\s*)?(?:Literaturverzeichnis|Quellenverzeichnis)"
    r"|Verwendete\s+(?:Literatur|Quellen)|Literatur(?:liste|angaben)?|Quellen(?:angaben)?|Internetquellen"
    r"|Bibliogra(?:ph|f)ie|Bibliography|Referenzen|References"
    r"|Anhang|Anlagen?|(?:Eidesstattliche|Ehrenwörtliche)\s+(?:Erklärung|Versicherung)|Selbst(?:st)?ändigkeitserklärung)"
    r"(?:\s+\([^)]*\))?\s*[*_]{0,2}\s*:?\s*$",
    re.IGNORECASE,
)
INHALTSVERZEICHNIS_UEBERSCHRIFT = re.compile(
    r"^\s*(?:#+\s*)?[*_]{0,2}\s*(?:Inhaltsverzeichnis|Inhalt|Gliederung|Abbildungsverzeichnis|Tabellenverzeichnis|"
    r"Abkürzungsverzeichnis)\s*[*_]{0,2}\s*:?\s*$", re.IGNORECASE)
TOC_ZEILE_RE = re.compile(r"^.{1,160}?(?:\.{3,}|…+|\s)\s*\d{1,3}$")
UNTERKAPITEL_NR = re.compile(r"^\s*(?:#+\s*)?[*_]{0,2}\s*\d+\.\d+")
EINSTIEG_UEBERSCHRIFT = re.compile(
    r"^\s*(?:#+\s*)?(?:\d+\.?\s*|[IVX]+\.\s*|Kapitel\s+1:?\s*)?(?:Einleitung|Einführung|Problemstellung|Hinführung|Vorbemerkung(?:en)?)\b",
    re.IGNORECASE)
FOLGEKAPITEL_UEBERSCHRIFT = re.compile(
    r"^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?\s*)?(?:Hauptteil|Fazit|Schluss\w*|Zusammenfassung|Ausblick|Diskussion|Ergebnisse)\b",
    re.IGNORECASE)

BUCHST = "A-Za-zÀ-ÖØ-öø-ɏ"
WORT = (rf"(?:\d+[{BUCHST}]+|[{BUCHST}]+\d*[{BUCHST}]*)"
        rf"(?:[-'’](?:[{BUCHST}0-9]+(?:\.\d+)?))*"
        rf"(?:/-?inn(?:en|e/n|/en)|(?<=[{BUCHST}]{{4}})/-?in\b|[*_:]innen|[*_:]in\b|[*_:/][rnem]\b)?"
        rf"(?:-[{BUCHST}0-9]+)*")
ZAHL = r"\d+(?:[.,]\d+)*"
TOKEN_RE = re.compile(rf"{WORT}|{ZAHL}")
BUCHSTABENWORT_RE = re.compile(rf"^{WORT}$")
_TOK_SATZZEICHEN_RE = re.compile(rf"{WORT}|{ZAHL}|[^\w\s]")

ZITAT_RE = re.compile(
    r"\s?\((?:[^()]{0,160}?\b(?:1[6-9]\d{2}|20\d{2})[a-z]?\b[^()]{0,80}?"
    r"|[^()]{0,120}?\b(?:o\.\s?J\.|n\.\s?d\.)[^()]{0,60}"
    r"|[^()]{0,120}?\b[eE]bd\.[^()]{0,40}"
    r"|(?:[vV]gl\.\s*)?(?:Anhang|Anh\.|Transkript(?:ion)?|Interview|I\s?\d+|B\s?\d+|IP\s?\d+)[^()]{0,40}?"
    r"(?:§\s?\d+|\b[AZ]\.\s?\d+|Z\.\s?\d+|Pos\.\s?\d+)[^()]{0,20})\)"
)
# numerische Belege (IEEE/Vancouver) mit mehreren Nummern oder Seitenangabe; Intervalle wie [0, 1] ausgenommen
NUM_BELEG_RE = re.compile(r"\s?\[(?!0\b)\d+(?:[,–-]\s?\d+)*(?:,\s?S\.\s?\d+[^\]]{0,10})?\]")
# Belege in eckigen Klammern mit Jahreszahl (v7): „[Wolfram 2009]“, „[Mergner et al. (2015), S. 9)]“,
# Interviewbelege „[2018.06.06_Lehrende, Absatz 8]“; vor ZITAT_RE, damit eine innere „(2015)“ den Beleg nicht zerreißt
KLAMMER_BELEG_RE = re.compile(r"\s?\[[^\[\]]{0,160}?\b(?:1[6-9]\d{2}|20\d{2})[a-z]?\b[^\[\]]{0,80}?\]")
# Transkriptnotation in Interviewzitaten (v7), vor der Satztrennung entfernt: ((lacht)), ((unv.)), ((…)), (unv.),
# (lacht), (I: Ja.), (B: …), [unverständlich]; „(…)“ nur, wenn der Absatz weitere Transkriptnotation enthält
TRANSKRIPT_DOPPEL_RE = re.compile(r"\s?\(\([^()]{0,60}\)\)")
TRANSKRIPT_RE = re.compile(
    r"\s?(?:\((?:[Uu]nv(?:erst)?\.?|[Uu]nverständlich|[Ll]acht|[Ll]achen|[Ll]achend|[Ss]eufzt|[Rr]äuspert sich|[Hh]ustet|"
    r"[Pp]ause(?: \d+(?:,\d)? ?(?:s|Sek\.?|Sekunden))?|"
    r"(?:I|B|IP|IV|I\d{1,2}|B\d{1,2}|Interviewer(?:in)?|Befragte[rn]?)\s?:\s?[^()]{0,120})\)"
    r"|\[(?:[Uu]nv(?:erst)?\.?|[Uu]nverständlich|[Ll]acht|[Pp]ause)\])")
TRANSKRIPT_AUSLASSUNG_RE = re.compile(r"\s?\((?:\.{2,3}|…)\)")
FUSSNOTE_RE = re.compile(r"\[\^[^\]\s]+\]|\[\d+\]|[¹²³⁴⁵⁶⁷⁸⁹⁰]+")
# Nicht hochgestellte Fußnotenziffern (pdftotext, Copy-Paste): "grundlegend.12 Weiter", "veröffentlicht3. Sie"
FUSSNOTE_ZIFFER_RE = re.compile(
    r"(?<![A-Za-zÄÖÜäöüß])(?P<wort>[A-Za-zÄÖÜäöüß]{2,})(?P<zeichen>[.,;!?)\"“”»«]?)(?P<nr>\d{1,3})"
    r"(?=[\s,;:!?]|\.(?=\s|$)|$)"
)
FUSSNOTEN_DEF_RE = re.compile(r"^\s{0,3}\[\^[^\]\s]+\]:")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
MD_FETT_RE = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")
MD_KURSIV_RE = re.compile(r"(?<![*\w])\*[^*\n]+\*(?![*\w])|(?<![_\w])_[^_\n]+_(?![_\w])")
MD_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!<>|~\"'])")
HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>\n]*>")
URL_RE = re.compile(r"(?:https?://|www\.)\S+?(?=[.,;:!?)\]]?(?:\s|$))")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LISTE_RE = re.compile(r"^\s*([-*•–·▪◦‣➢]|o(?=\t)|\d{1,2}[.)]|[a-z][.)])\s+")
ABK_ZEILENSTART_RE = re.compile(r"^(?:[^\W\d_]\.\s?){2,}")  # z. B., d. h., u. a., i. d. R. am Zeilenanfang
FETTZEILE_RE = re.compile(r"^(\*\*|__)[^*_]+\1:?$")
NUM_KAPITEL_RE = re.compile(r"^\d{1,2}[.)]\s+[A-ZÄÖÜ]")
GEDANKENSTRICH_RE = re.compile(r"(?<=\s)[–—-](?=\s)(?!(?<=\d\s[–—-])\s\d)|(?<=\w)—(?=\w)")

# Dreier-Aufzählungen (Komma vor Nebensatz, Infinitiv oder Apposition ausgeschlossen)
_DL_W = r"[\wÄÖÜäöüß]+(?:-[\wÄÖÜäöüß]+)*-?"
_DL_KEIN_GLIED = (r"(?:dass|weil|ob|wenn|als|da|obwohl|während|nachdem|bevor|damit|sodass|indem|wie|wo|was|wobei|"
                  r"deren|dessen|welche[rnms]?|um|ohne|statt|anstatt|also|beispielsweise|etwa|insbesondere|nämlich|es|"
                  r"sondern|aber|doch|denn|jedoch|bis|zu)\b")
_DL_GLIED = rf"(?!{_DL_KEIN_GLIED}){_DL_W}(?:\s(?!(?:und|oder|sowie)\b){_DL_W})?"
DREIERLISTE_RE = re.compile(
    rf"(?<![\w-])(?P<g1>{_DL_W}(?:\s{_DL_W})?),\s(?P<g2>{_DL_GLIED})(?:,\s{_DL_GLIED})*,?\s(?:und|sowie|oder)\s{_DL_W}",
    re.IGNORECASE,
)
# Autorenliste direkt vor einer Jahresangabe (v7): Namen mit Partikeln (von, van, de …), Reihe mit „und“/„&“/„sowie“,
# optional „et al.“, danach „(1986)“, „(1986, S. 5)“, „[2004]“, „(Hrsg.) (2010)“-artig oder „(o. J.)“
_AUTOR = r"(?:(?:von|vom|van|de|der|den|du|da|di|le|la|del|ten|zu|op)\s)*[A-ZÄÖÜ][\w'’-]*[^\W\d_]"
AUTORENLISTE_RE = re.compile(
    rf"(?<![\w-])(?P<liste>{_AUTOR}(?:,\s{_AUTOR})+,?\s(?:und|&|sowie|and)\s{_AUTOR}(?:\set\sal\.?)?)"
    r"\s?[(\[]\s?(?:(?:Hrsg\.|Hg\.|Eds?\.)[,;)]?\s?\(?)?(?:(?:1[6-9]\d{2}|20\d{2})[a-z]?\b|o\.\s?J\.)")
_NP_REIHE = re.compile(r"(?:der|die|das|den|dem|des)\s+(?:[a-zäöüß]\w*\s+)?[A-ZÄÖÜ][\w-]*\s+(?:und|oder|sowie|bzw\.)\s+"
                       r"(?:der|die|das|den|dem|des|ein\w*|deren|dessen|ihr\w*|sein\w*|unser\w*)\s")
ARTIKEL_POSS = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "eines", "deren", "dessen",
                "ihre", "ihren", "ihrem", "ihrer", "ihres", "seine", "seinen", "seinem", "seiner", "seines"}
_INF_RE = re.compile(r"(?:\bzu\s+[a-zäöüß]\w*(?:en|ln|rn)|\b[a-zäöüß]\w*zu\w+(?:en|ln|rn))[.!?]?$")

# Silben (HW04): Kern = Vokal oder Diphthong
SILBENKERN_RE = re.compile(r"aa|ee|oo|ei|ai|ey|ay|oy|au|äu|eu|ie|ou|[aeiouyäöüéèàáâêôû]")
_AUSNAHMEN_BEE = {"beere", "beeren", "beet", "beete", "beeten"}
_HIAT_EXTRA_RE = re.compile(r"museum|ideen|tourneen|alleen|armeen")
_IEN_KOMPOSITUM_RE = re.compile(
    r"(?:stud|med|kriter|ser|fer|mater|famil|lin|theor|strateg|kategor|ökonom|technolog|industr|akadem|histor|kolon|"
    r"demokrat|energ|bakter|präm)ien(?=[a-zäöüß])")  # Stu-di-en-gang, Me-di-en-kom-pe-tenz
# Anglizismen: Schreibung auf Lautkerne abbilden (Team = 1 Kern, Software = 2)
_ENGLISCH = [(re.compile(p), r) for p, r in (
    (r"team", "tem"), (r"coach", "coch"), (r"lead", "led"), (r"learn", "lern"), (r"search", "serch"),
    (r"stream", "strem"), (r"speak", "spek"), (r"leas(?=ing)", "les"), (r"featur", "fetur"), (r"reach", "rech"),
    (r"clean", "clen"), (r"dream", "drem"), (r"health", "helth"), (r"head", "hed"), (r"break", "brek"),
    (r"board", "bord"), (r"load", "lod"), (r"road", "rod"), (r"build", "bild"), (r"recruit", "recrut"),
    (r"(on|off|dead|time|guide|pipe)line", r"\1lin"), (r"(soft|hard|mal|middle)ware", r"\1war"),
    (r"website", "websit"), (r"service$", "servis"), (r"update", "updat"), (r"manage(?=ment)", "manag"),
    (r"homeoffice", "homofis"), (r"youtube", "jutub"), (r"social", "socal"),
)]
_ENGLISCH_TEST = re.compile(r"team|coach|lead|learn|search|stream|speak|leas|featur|reach|clean|dream|health|head|break|"
                            r"board|load|road|build|recruit|line|ware|website|service|update|manage|homeoffice|youtube|social")


# ---------------------------------------------------------------------------
# Einlesen
# ---------------------------------------------------------------------------

def lies_datei(pfad: str) -> str:
    if pfad == "-":
        return sys.stdin.read()
    if not os.path.isfile(pfad):
        raise SystemExit(f"Datei nicht gefunden: {pfad}")
    endung = os.path.splitext(pfad)[1].lower()
    with open(pfad, "rb") as f:
        kopf = f.read(4096)
    if endung == ".docx":
        return lies_docx(pfad)
    if endung == ".odt":
        return lies_odt(pfad)
    if endung == ".pdf":
        try:
            out = subprocess.run(["pdftotext", "-enc", "UTF-8", pfad, "-"], check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as e:
            raise SystemExit(f"PDF konnte nicht gelesen werden (pdftotext nötig): {e}")
        return out.stdout.decode("utf-8", errors="replace")
    if (endung in (".doc", ".rtf", ".pages", ".docm")
            or kopf.startswith((b"{\\rtf", b"\xd0\xcf\x11\xe0", b"PK\x03\x04"))
            or (b"\x00" in kopf and not kopf.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)))):
        raise SystemExit(f"Format von {pfad} wird nicht unterstützt – bitte als .docx, .odt, .txt oder .md speichern.")
    return lies_textdatei(pfad)


def lies_textdatei(pfad: str) -> str:
    """UTF-8 (auch mit BOM), UTF-16 mit BOM, sonst Windows-1252 – mit Warnung statt stiller Verfälschung."""
    with open(pfad, "rb") as f:
        roh = f.read()
    if roh.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return roh.decode("utf-16")
    try:
        return roh.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    u = roh.decode("utf-8-sig", errors="replace")
    fehler = u.count("�")
    gueltig = sum(1 for ch in u if ord(ch) > 127 and ch != "�")
    if gueltig > fehler:  # überwiegend UTF-8 mit einzelnen kaputten Bytes: nicht alles umdeuten
        print(f"Warnung: {fehler} ungültige Byte(s) in UTF-8-Datei ersetzt.", file=sys.stderr)
        return u
    print("Warnung: Datei ist nicht UTF-8 – lese als Windows-1252.", file=sys.stderr)
    return roh.decode("cp1252", errors="replace")


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
UEBERSCHRIFT_STIL = re.compile(r"(?i)^(heading|berschrift|überschrift|title|titel)")
VERZEICHNIS_STIL = re.compile(r"(?i)^(toc|verzeichnis|inhaltsverz)")
# nur ohne styles.xml; ListParagraph/Listenabsatz bewusst nicht (ohne numPr keine Liste)
LISTEN_STIL_OHNE_STYLES = re.compile(r"(?i)^(listbullet|listnumber|aufzhlungszeichen|aufzählungszeichen|listennummer)")
_DOCX_UEBERSPRINGEN = {_MC + "Fallback", _W + "txbxContent", _W + "delText", _W + "instrText", _W + "tbl"}


def _docx_absatz_text(p) -> str:
    teile = []

    def lauf(el):
        for k in el:
            if k.tag in _DOCX_UEBERSPRINGEN:
                continue
            if k.tag == _W + "t":
                teile.append(k.text or "")
            elif k.tag in (_W + "tab", _W + "br", _W + "cr"):
                teile.append(" ")
            elif k.tag == _W + "noBreakHyphen":
                teile.append("-")
            else:
                lauf(k)
    lauf(p)
    return "".join(teile)


def _docx_num_an(numpr):
    """None = keine Angabe, True/False = Nummerierung an/aus (numId 0 schaltet aus)."""
    if numpr is None:
        return None
    nid = numpr.find(_W + "numId")
    return nid is None or nid.get(_W + "val") != "0"


def _docx_stile(z):
    """styleId -> (Stilname klein, Nummerierung über Formatvorlage samt basedOn-Kette an?)."""
    try:
        wurzel = ET.fromstring(z.read("word/styles.xml"))
    except (KeyError, ET.ParseError):
        return None
    roh = {}
    for st in wurzel.iter(_W + "style"):
        if st.get(_W + "type") != "paragraph":
            continue
        sid = st.get(_W + "styleId") or ""
        name, basis = st.find(_W + "name"), st.find(_W + "basedOn")
        roh[sid] = ((name.get(_W + "val") if name is not None else sid).lower(),
                    basis.get(_W + "val") if basis is not None else None,
                    _docx_num_an(st.find(f"{_W}pPr/{_W}numPr")))

    def num(sid, tiefe=0):
        if sid not in roh or tiefe > 20:
            return False
        _, basis, n = roh[sid]
        return n if n is not None else (num(basis, tiefe + 1) if basis else False)
    return {sid: (v[0], num(sid)) for sid, v in roh.items()}


def lies_docx(pfad: str) -> str:
    """Absätze aus word/document.xml; Tabellen als Tabellenzeile, Textfelder/Inhaltsverzeichnis übersprungen."""
    try:
        with zipfile.ZipFile(pfad) as z:
            wurzel = ET.fromstring(z.read("word/document.xml"))
            stile = _docx_stile(z)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise SystemExit(f"{pfad} ist keine gültige .docx-Datei (alte .doc? bitte als .docx speichern): {e}")
    absaetze: list[str] = []

    def bloecke(container):
        for el in container:
            if el.tag == _W + "tbl":
                absaetze.append("| Tabelle |")  # zählt in zerlege_bloecke als Tabellenzeile
                continue
            if el.tag in (_W + "sdt", _W + "customXml"):
                inhalt = el.find(_W + "sdtContent")
                bloecke(inhalt if inhalt is not None else el)
                continue
            if el.tag != _W + "p":
                continue
            st = el.find(f"{_W}pPr/{_W}pStyle")
            sid = st.get(_W + "val") if st is not None else ""
            if stile is not None:
                name, stil_num = stile.get(sid, (sid.lower(), False))
            else:
                name, stil_num = sid.lower(), bool(LISTEN_STIL_OHNE_STYLES.match(sid))
            text = _docx_absatz_text(el)
            if not text.strip() or VERZEICHNIS_STIL.match(name) or VERZEICHNIS_STIL.match(sid):
                continue
            eigen = _docx_num_an(el.find(f"{_W}pPr/{_W}numPr"))
            if UEBERSCHRIFT_STIL.match(name) or UEBERSCHRIFT_STIL.match(sid):
                text = "# " + text
            elif eigen if eigen is not None else stil_num:
                text = "- " + text
            absaetze.append(text)
    body = wurzel.find(_W + "body")
    bloecke(body if body is not None else wurzel)
    return "\n\n".join(absaetze)


_ODT_T = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_ODT_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"


def _odt_text(el) -> str:
    teile = [el.text or ""]
    for k in el:
        if k.tag in (_ODT_T + "note", _ODT_OFFICE + "annotation"):
            pass  # Fußnoten/Kommentare weglassen (wie bei .docx)
        elif k.tag == _ODT_T + "s":
            teile.append(" " * int(k.get(_ODT_T + "c", "1")))
        elif k.tag in (_ODT_T + "tab", _ODT_T + "line-break"):
            teile.append(" ")
        else:
            teile.append(_odt_text(k))
        teile.append(k.tail or "")
    return "".join(teile)


def lies_odt(pfad: str) -> str:
    try:
        with zipfile.ZipFile(pfad) as z:
            wurzel = ET.fromstring(z.read("content.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise SystemExit(f"{pfad} ist keine gültige .odt-Datei.")
    absaetze: list[str] = []
    tabelle = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table"

    def gehe(el, in_liste=False):
        for k in el:
            if k.tag in (_ODT_T + "note", _ODT_T + "tracked-changes", _ODT_T + "table-of-content"):
                continue
            if k.tag == tabelle:
                absaetze.append("| Tabelle |")
                continue
            if k.tag in (_ODT_T + "h", _ODT_T + "p"):
                txt = _odt_text(k).strip()
                if txt:
                    absaetze.append(("# " if k.tag == _ODT_T + "h" else "- " if in_liste else "") + txt)
            else:
                gehe(k, in_liste or k.tag == _ODT_T + "list")
    gehe(wurzel)
    return "\n\n".join(absaetze)


# ---------------------------------------------------------------------------
# Struktur: Absätze, Überschriften, Listen
# ---------------------------------------------------------------------------

_ZEILENTRENNUNG_RE = re.compile("([A-Za-zÄÖÜäöüßéè]+)([-‐­])\n[ \t]*(?=([A-Za-zÄÖÜäöüßéè]+))")
_ERGAENZUNG_DANACH = {"und", "oder", "bzw", "sowie", "als", "bis", "noch", "wie", "u", "beziehungsweise"}
_ZUSAMMEN_TROTZDEM = {("so", "wie"), ("den", "noch")}  # sowie, dennoch


def _zeilentrennung(m: re.Match) -> str:
    vor, strich, nach = m.group(1), m.group(2), m.group(3)
    if strich == "­":
        return vor  # weiches Trennzeichen: immer Silbentrennung
    if nach[0].isupper():
        return vor + "-"  # Corona-|Pandemie, E-|Mail
    if nach.lower() in _ERGAENZUNG_DANACH and (vor.lower(), nach.lower()) not in _ZUSAMMEN_TROTZDEM:
        return vor + "- "  # Profi-|und, Lehr-|noch
    if vor[-1].isupper():
        return vor + "-"  # IT-|basierte
    return vor  # Unter-|nehmen, so-|wie


def normalisiere(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = _ZEILENTRENNUNG_RE.sub(_zeilentrennung, text)  # vor dem Entfernen von U+00AD
    for ch in "    ":
        text = text.replace(ch, " ")
    text = text.translate(dict.fromkeys(map(ord, "­​‌‍⁠﻿"), None))  # unsichtbare Zeichen
    return text.replace("‐", "-").replace("‑", "-")


SCHLUSS_ANHANG_RE = re.compile(
    r"(?:\[\^[^\]\s]+\]|\[\d+\]|[¹²³⁴⁵⁶⁷⁸⁹⁰]+|(?<=[a-zäöüß][.!?])\d{1,3}|[*_\"“”»«‘’'\)\]\s])+$")


def ist_ueberschrift(zeile: str) -> bool:
    s = zeile.strip()
    if re.match(r"^#{1,6}\s", s):
        return True
    if re.match(r"^\*\*[^*]+\*\*:?$", s) and not re.search(r"[.!?]\*\*$", s):  # ganze Zeile fett = Zwischenüberschrift
        return True
    kern = SCHLUSS_ANHANG_RE.sub("", s)  # Fußnotenzeichen, Hervorhebung, schließende Anführungszeichen/Klammern
    return len(s.split()) <= 12 and not re.search(r"[.!?:;…]$", kern)


def _entferne_front_matter(text: str) -> str:
    m = re.match(r"\A---[ \t]*\n((?:.*\n)*?)(?:---|\.\.\.)[ \t]*(?:\n|\Z)", text)
    if m and re.match(r"^[\w-]+\s*:", m.group(1)):
        return text[m.end():]
    return text


def _entferne_code(text: str) -> str:
    """Code-Blöcke (``` und ~~~) zeilenweise entfernen, auch mit Leerzeilen; offener Block bleibt Text."""
    zeilen, out, fence, start = text.split("\n"), [], None, 0
    for i, z in enumerate(zeilen):
        m = re.match(r"^\s{0,3}(`{3,}|~{3,})", z)
        if m:
            if fence is None:
                fence, start = m.group(1)[0], i
                continue
            if m.group(1)[0] == fence:
                fence = None
                continue
        if fence is None:
            out.append(z)
    if fence is not None:
        out.extend(zeilen[start + 1:])
    return "\n".join(out)


STRICH_RE = re.compile(r"^ {0,3}-{3,}\s*$")
SPALTEN_RE = re.compile(r"^ {0,3}-{3,}(?: +-{3,})+\s*$")
SETEXT_RE = re.compile(r"^ {0,3}(?:={2,}|-{2,})\s*$")
TRENNLINIE_RE = re.compile(r"^ {0,3}([*_])(?:\s*\1){2,}\s*$")


def entferne_md_tabellen(text: str) -> tuple[str, int]:
    """Pandoc-Tabellen ohne '|' entfernen, Setext-Überschriften in ATX umwandeln, Trennlinien streichen."""
    zeilen, out, n_tab, i = text.split("\n"), [], 0, 0
    while i < len(zeilen):
        z = zeilen[i]
        vorher = out[-1] if out else ""
        folgend = zeilen[i + 1] if i + 1 < len(zeilen) else ""
        rahmen = STRICH_RE.match(z) and not vorher.strip() and folgend.strip() and folgend.startswith("  ")
        if SPALTEN_RE.match(z) or rahmen:
            if SPALTEN_RE.match(z) and vorher.strip():
                out.pop()
                n_tab += 1  # Kopfzeile
            i += 1
            while i < len(zeilen):
                s = zeilen[i]
                if not s.strip():
                    j = i + 1
                    while j < len(zeilen) and not zeilen[j].strip():
                        j += 1
                    if j >= len(zeilen) or not zeilen[j].startswith("  "):
                        break  # Tabellenende
                elif not (STRICH_RE.match(s) or SPALTEN_RE.match(s)):
                    n_tab += 1
                i += 1
            out.append("")  # Blockgrenze erhalten
            continue
        if SETEXT_RE.match(z) and vorher.strip() and not vorher.startswith(" ") and not LISTE_RE.match(vorher.strip()):
            out[-1] = "## " + vorher.strip()
            out.append("")
            i += 1
            continue
        if (STRICH_RE.match(z) or TRENNLINIE_RE.match(z)) and not vorher.strip():  # horizontale Linie
            i += 1
            continue
        out.append(z)
        i += 1
    return "\n".join(out), n_tab


SATZENDE_ZEILE_RE = re.compile(r"[.!?…:\"“”»«)]$")
NUM_UEBERSCHRIFT = re.compile(r"^(\d+(\.\d+)*\.?|[IVX]+\.|[A-H]\.?)\s+[A-ZÄÖÜ]")


def _zeilen_ueberschrift(s: str, breite: float) -> bool:
    """Überschrift innerhalb eines Blocks nur mit starken Signalen (Fließtextzeilen haben auch ≤ 12 Wörter)."""
    if s.startswith(("-", "*", "•", ">", "|")) or LISTE_RE.match(s) and not NUM_UEBERSCHRIFT.match(s):
        return bool(FETTZEILE_RE.match(s))
    if re.match(r"^#{1,6}\s", s) or LITERATUR_UEBERSCHRIFT.match(s) or INHALTSVERZEICHNIS_UEBERSCHRIFT.match(s):
        return True
    if not ist_ueberschrift(s) or re.search(r"[,;–—-]$", s):
        return False
    if s[:1] in "([" or s[:1].islower() or s.count(")") > s.count("("):  # Belegrest '(Interview 4)', 'S. 141)'
        return False
    letztes = s.split()[-1].strip("*_")
    if not (letztes[:1].isupper() or letztes[:1].isdigit()):  # Umbruchzeilen enden meist auf Artikel/Verb/Adjektiv
        return False
    woerter = len(s.split())
    if NUM_UEBERSCHRIFT.match(s):  # '2.1 Begriffsbestimmung'
        return woerter <= 12 and len(s) < 0.8 * breite
    return woerter <= 6 and len(s) < 0.5 * breite


def _in_absaetze(zeilen: list[str]) -> list[list[str]]:
    """Block mit einfachen Zeilenumbrüchen in Absätze teilen (Word-Kopie: lange Zeilen; PDF: kurze letzte Absatzzeile)."""
    if len(zeilen) < 2:
        return [zeilen]
    laengen = sorted(len(z.strip()) for z in zeilen)
    # robust gegen einzelne von pdftotext (Silbentrennung) zusammengezogene Überlängen
    breite = (laengen[-1] if len(laengen) < 8 else laengen[int(0.9 * (len(laengen) - 1))]) or 1
    word_kopie = breite > 140
    gruppen, akt = [], []
    for i, z in enumerate(zeilen):
        s = z.strip()
        vor = zeilen[i - 1].strip() if i else ""
        nach = zeilen[i + 1].strip() if i + 1 < len(zeilen) else ""
        if ((not vor or SATZENDE_ZEILE_RE.search(vor)) and _zeilen_ueberschrift(s, breite)
                and (not nach or nach[:1].isupper() or nach[:1].isdigit() or nach[:1] in "-*•")):
            if akt:
                gruppen.append(akt)
            gruppen.append([z])
            akt = []
            continue
        akt.append(z)
        if (nach and SATZENDE_ZEILE_RE.search(s) and (nach[:1].isupper() or nach[:1] in "„\"»«")
                and not LISTE_RE.match(s) and (word_kopie or len(s) < 0.7 * breite)):
            gruppen.append(akt)
            akt = []
    if akt:
        gruppen.append(akt)
    return gruppen


def _listenart(s: str):
    m = LISTE_RE.match(s)
    if not m or ABK_ZEILENSTART_RE.match(s):
        return None
    marke = m.group(1)
    return "zahl" if marke[0].isdigit() else ("buchstabe" if marke[0].isalpha() else marke)


def ist_listenzeile(zeilen: list[str], zi: int, in_liste: bool, vorige_art: str | None = None) -> bool:
    """Listenmarker nur bei passendem Kontext als Liste werten; sonst harter Umbruch mitten im Satz (PDF)."""
    s = zeilen[zi].strip()
    art = _listenart(s)
    if art is None:
        return False
    if zi == 0 or in_liste or vorige_art in ("ueberschrift", "zitat"):
        return True
    vorher = zeilen[zi - 1].strip()
    # Satzende/Doppelpunkt davor – nicht bei Beleg 'Hartmann 1999:' oder Abkürzungsrest 'o.' (harter Umbruch)
    satzende = re.search(r"[.!?:;]$", vorher) and not re.search(r"(?:\b\d{4}[a-z]?:|(?<![\w.])[^\W\d_]\.)$", vorher)
    if satzende or re.match(r"^#{1,6}\s", vorher) or FETTZEILE_RE.match(vorher):
        return True
    naechste = zeilen[zi + 1].strip() if zi + 1 < len(zeilen) else None
    return naechste is not None and _listenart(naechste) == art  # mehrere gleichartige Marker in Folge


def _toc_schluessel(z: str) -> str:
    z = re.sub(r"^#+\s*|[*_]", "", z.strip())
    z = re.sub(r"(?:\.{3,}|…+|\s)\s*\d{1,3}$", "", z)
    return re.sub(r"\s+", " ", z).strip(" .").lower()


def _erste_zeilen(bloecke):
    """Erste Zeilen der folgenden Blöcke, soweit Überschrift; stoppt am nächsten Verzeichnis/Anhang."""
    for zeilen in bloecke:
        z = zeilen[0].strip()
        if z and ist_ueberschrift(z):
            if LITERATUR_UEBERSCHRIFT.match(z):
                return
            yield z


def _starke_kapitelzeile(z: str, muster: re.Pattern) -> bool:
    if not muster.match(z):
        return False
    return bool(re.match(r"^\s*(#|\d|[IVX]+\.|Kapitel)", z)) or len(z.split()) <= 3


def zerlege_bloecke(text: str) -> dict:
    """Teilt in Prosa-Absätze, Überschriften, Listenpunkte; schneidet ab Literaturverzeichnis ab."""
    text = normalisiere(text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = _entferne_front_matter(text)
    text = _entferne_code(text)
    text, tabellenzeilen = entferne_md_tabellen(text)
    absaetze, ueberschriften, listenpunkte = [], [], []
    folge: list[tuple[str, int]] = []  # Textreihenfolge für den Blockmodus: (Art, Index in der jeweiligen Liste)
    abgeschnitten = False
    fussnoten_text = zitatbloecke = 0

    def neu(liste: list, art: str, inhalt: str) -> None:
        folge.append((art, len(liste)))
        liste.append(inhalt)

    # 1) Blöcke an Leerzeilen, Fußnotendefinitionen entfernen, Blöcke mit einfachen Umbrüchen teilen
    bloecke: list[list[str]] = []
    in_fn = False  # gilt über Blockgrenzen (mehrabsätzige Fußnoten)
    for block in re.split(r"\n\s*\n", text):
        zeilen = [z for z in block.split("\n") if z.strip()]
        if not zeilen:
            continue
        if in_fn and all(z.startswith(("    ", "\t")) for z in zeilen):
            continue
        gefiltert, in_fn = [], False
        for z in zeilen:
            if FUSSNOTEN_DEF_RE.match(z):
                in_fn = True
                fussnoten_text += 1
                continue
            if in_fn and z[:1].isspace():
                continue
            in_fn = False
            gefiltert.append(z)
        if gefiltert:
            bloecke.extend(_in_absaetze(gefiltert))

    # 2) Blöcke auswerten
    ueberspringen = im_inhaltsverzeichnis = False
    toc_eintraege: set[str] = set()
    vorher_liste = False
    for bi, zeilen in enumerate(bloecke):
        erste = zeilen[0].strip()
        if ueberspringen:  # Vorspann (Erklärung) bis zur nächsten Überschrift überspringen
            if len(zeilen) == 1 and ist_ueberschrift(erste) and not LITERATUR_UEBERSCHRIFT.match(erste):
                ueberspringen = False
            else:
                continue
        if INHALTSVERZEICHNIS_UEBERSCHRIFT.match(erste) and len(zeilen) == 1:
            im_inhaltsverzeichnis, toc_eintraege = True, set()
            continue
        if im_inhaltsverzeichnis:
            nur_eintraege = all(ist_ueberschrift(z) or TOC_ZEILE_RE.match(z.strip()) for z in zeilen)
            if nur_eintraege and not (len(zeilen) == 1 and _toc_schluessel(erste) in toc_eintraege):
                toc_eintraege.update(_toc_schluessel(z) for z in zeilen)
                continue
            im_inhaltsverzeichnis = False
        if LITERATUR_UEBERSCHRIFT.match(erste):
            folgende = list(_erste_zeilen(bloecke[bi + 1:]))
            # früh im Text (< 10 % und < 1000 Wörter gelesen): Vorspann oder Verzeichniseintrag, nie abschneiden
            bisher = sum(len(a.split()) for a in absaetze)
            rest = sum(len(z.split()) for folge_zeilen in bloecke[bi + 1:] for z in folge_zeilen)
            frueh = bisher < 1000 and bisher < 0.1 * (bisher + rest)
            if frueh and any(_starke_kapitelzeile(z, EINSTIEG_UEBERSCHRIFT) for z in folgende):
                ueberspringen = True  # Erklärung/Verzeichnis vor der Einleitung
                continue
            if not frueh and not (
                    UNTERKAPITEL_NR.match(erste) or any(_starke_kapitelzeile(z, FOLGEKAPITEL_UEBERSCHRIFT) for z in folgende)):
                abgeschnitten = True  # Unterkapitel '1.3 Quellen' oder Kapitel davor ('3 Quellen' … '4 Fazit') bleiben
                break
        prosa: list[str] = []
        in_liste = False
        vorige_art = None  # None | "liste" | "ueberschrift" | "prosa" | "zitat"
        for zi, z in enumerate(zeilen):
            s = z.strip()
            if s.startswith("|") or s.count("|") >= 2:
                tabellenzeilen += 1
                continue
            if s.startswith(">"):  # Blockzitat: fremder Wortlaut
                zitatbloecke += 1
                if prosa:
                    neu(absaetze, "absatz", " ".join(prosa))
                    prosa = []
                in_liste, vorige_art = False, "zitat"
                continue
            if re.match(r"^#{1,6}\s", s) and zi > 0:  # Überschrift ohne Leerzeile davor
                if prosa:
                    neu(absaetze, "absatz", " ".join(prosa))
                    prosa = []
                neu(ueberschriften, "ueberschrift", re.sub(r"^#+\s*", "", s))
                in_liste, vorige_art = False, "ueberschrift"
                continue
            if in_liste and not LISTE_RE.match(s) and (
                    z[:1].isspace() or (s[:1].islower() and not re.search(r"[.!?:]$", listenpunkte[-1]))):
                listenpunkte[-1] += " " + s  # eingerückte oder angehängte Fortsetzung des Listenpunkts
                continue
            if (len(zeilen) == 1 and not vorher_liste and NUM_KAPITEL_RE.match(s)
                    and ist_ueberschrift(LISTE_RE.sub("", s, count=1))
                    and not (bi + 1 < len(bloecke) and _listenart(bloecke[bi + 1][0].strip()) == "zahl")):
                neu(ueberschriften, "ueberschrift", s)  # '1. Einleitung' als eigene Zeile
                vorige_art = "ueberschrift"
                continue
            if ist_listenzeile(zeilen, zi, in_liste, vorige_art):
                if prosa:
                    neu(absaetze, "absatz", " ".join(prosa))
                    prosa = []
                neu(listenpunkte, "liste", LISTE_RE.sub("", s, count=1))
                in_liste, vorige_art = True, "liste"
                continue
            in_liste = False
            if not prosa and ist_ueberschrift(s) and (len(zeilen) == 1 or re.match(r"^#{1,6}\s", s) or FETTZEILE_RE.match(s)):
                neu(ueberschriften, "ueberschrift", re.sub(r"^#+\s*|^\*\*|\*\*:?$", "", s))
                vorige_art = "ueberschrift"
                continue
            prosa.append(s)
            vorige_art = "prosa"
        if prosa:
            neu(absaetze, "absatz", " ".join(prosa))
        vorher_liste = vorige_art == "liste"
    return {
        "absaetze": absaetze,
        "ueberschriften": ueberschriften,
        "listenpunkte": listenpunkte,
        "tabellenzeilen": tabellenzeilen,
        "literatur_abgeschnitten": abgeschnitten,
        "fussnoten_text": fussnoten_text,
        "zitatbloecke": zitatbloecke,
        "folge": folge,
    }


def _fussnote_ziffer(m: re.Match, zaehler: Counter) -> str:
    wort, zeichen = m["wort"], m["zeichen"]
    if not zeichen and not wort[-1].islower():  # CO2, CH4, DAX40, SDG13, FY23 bleiben
        return m.group(0)
    if zeichen == "." and (wort.lower() in ABKUERZUNGEN or re.fullmatch(r"[IVXLC]+", wort)):  # Abb.3, Kap.4, II.1
        return m.group(0)
    zaehler["fussnoten"] += 1
    return wort + zeichen


def entferne_transkript(absatz: str, zaehler: Counter) -> str:
    """Transkriptnotation aus Interviewzitaten entfernen (v7), gezählt in zaehler['transkript'].

    ((…))-Kommentare, (unv.), (lacht), Sprecherrückmeldungen wie (I: Ja.) und [unverständlich] zerlegen sonst Zitate in
    Fragmente bzw. zählen als Wörter; eine Auslassung (…) gilt nur bei weiterer Notation im Absatz als Transkriptpause."""
    n = len(TRANSKRIPT_DOPPEL_RE.findall(absatz))
    absatz = TRANSKRIPT_DOPPEL_RE.sub("", absatz)
    n += len(TRANSKRIPT_RE.findall(absatz))
    absatz = TRANSKRIPT_RE.sub("", absatz)
    if n:
        n += len(TRANSKRIPT_AUSLASSUNG_RE.findall(absatz))
        absatz = TRANSKRIPT_AUSLASSUNG_RE.sub("", absatz)
        zaehler["transkript"] += n
    return absatz


def bereinige_absatz(absatz: str, zaehler: Counter) -> str:
    absatz = re.sub(r"<br\s*/?>", " ", absatz, flags=re.I)
    absatz = HTML_TAG_RE.sub("", absatz)
    absatz = re.sub(r"(?<=\s)---(?=\s)|(?<=\w)---(?=\w)", "—", absatz)  # Pandoc: --- = Geviertstrich
    absatz = re.sub(r"(?<=\s)--(?=\s)|(?<=\d)--(?=\d)", "–", absatz)  # Pandoc: -- = Halbgeviertstrich
    absatz = MD_ESCAPE_RE.sub(r"\1", absatz)  # Markdown-Escapes: Mitarbeiter\*innen, \[sic\]
    zaehler["markdown_fett"] += len(MD_FETT_RE.findall(absatz))
    zaehler["markdown_kursiv"] += len(MD_KURSIV_RE.findall(absatz))
    absatz = MD_LINK_RE.sub(r"\1", absatz)
    absatz = URL_RE.sub("URL", absatz)
    absatz = EMAIL_RE.sub("EMAIL", absatz)
    absatz = re.sub(r"\*\*|__", "", absatz)
    absatz = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"\1", absatz)
    absatz = entferne_transkript(absatz, zaehler)
    zaehler["fussnoten"] += len(FUSSNOTE_RE.findall(absatz))
    absatz = FUSSNOTE_RE.sub("", absatz)
    absatz = FUSSNOTE_ZIFFER_RE.sub(lambda m: _fussnote_ziffer(m, zaehler), absatz)
    zaehler["zitate"] += len(KLAMMER_BELEG_RE.findall(absatz))
    absatz = KLAMMER_BELEG_RE.sub("", absatz)
    zaehler["zitate"] += len(ZITAT_RE.findall(absatz))
    absatz = ZITAT_RE.sub("", absatz)
    zaehler["zitate"] += len(NUM_BELEG_RE.findall(absatz))
    absatz = NUM_BELEG_RE.sub("", absatz)
    absatz = re.sub(r"`[^`]*`", "", absatz)
    absatz = re.sub(r"\s+([.,;:!?])(?!\d)", r"\1", absatz)
    return re.sub(r"\s+", " ", absatz).strip()


# ---------------------------------------------------------------------------
# Satzsegmentierung
# ---------------------------------------------------------------------------

def _kern(token: str) -> str:
    return token.strip("\"'„“”»«‚‘’()[]{}").rstrip(".!?…").lower()


def _folgewort(n: str) -> str:
    return n.strip("\"'„“”»«‚‘’()[]{}").rstrip(".,;:!?…").lower()


VERWEIS_VOR_ZAHL = {"abb", "abbildung", "tab", "tabelle", "s", "seite", "kap", "kapitel", "abschnitt", "nr", "anhang", "anlage", "abs", "art", "fn", "fußnote", "bd", "band", "heft", "jg", "vol", "no"}
AUSLASSUNG_RE = re.compile(r"^([„\"»‚]?)[\[(](?:\.\.\.|…)[\])]([.!?]?)$")
_VERWEIS_NACH_ART = re.compile(r"(abs|nr|s|hs|lit|satz|uabs|var|alt)(\.|\d|$)")
_ROEMISCH = re.compile(r"[IVXLC]+(?![^\W\d_])")


def ist_satzgrenze(token: str, naechstes: str, vorher: str = "") -> bool:
    m = AUSLASSUNG_RE.match(token)
    if m:  # Auslassung im Zitat: […] / [...] / (…) / „[…] / […].
        n = naechstes.lstrip("\"'„“»«‚‘([")
        if not n or not (n[0].isupper() or n[0].isdigit()):
            return False
        if m.group(2):
            return True
        if vorher.rstrip("\"'“”»«‚‘’)]").endswith((".", "!", "?")):  # Satz endete schon vor der Auslassung
            return True
        if m.group(1):  # „[…] = Zitatanfang mitten im Satz
            return False
        return _folgewort(n) in STARTWOERTER  # großes Funktionswort => Satzanfang, Nomen => Satzmitte
    t = token.rstrip("\"'“”»«’‘)]}")
    if not t or not re.search(r"[.!?…]$", t):
        return False
    n = naechstes.lstrip("\"'„“»«‚‘([")
    if not n or not (n[0].isupper() or n[0].isdigit() or n[0] == "§"):
        return False
    if re.search(r"[(\[][^()\[\]]*[!?][)\]]$", token):  # (sic!), (!), (?)
        return False
    if t.endswith(("!", "?", "…", "...")):
        return True
    if re.search(r"[)\]}“”\"»«’‘]\.$|\.\.$", t):  # Punkt hinter Klammer/Anführung bzw. Abkürzungs- + Satzpunkt
        return True
    kern = _kern(t)
    folge = _folgewort(n)
    if kern in MEHRDEUTIG:
        if n[0].isdigit() or _ROEMISCH.match(n):  # Art. 5 GG, Alt. 2, 15. Jan. 2020, Art. XX GATT
            return False
        if _VERWEIS_NACH_ART.match(_kern(n) + ("." if n.endswith(".") else "")):  # "Art. Abs. …" (Ziffern verloren)
            return False
        return True  # "dieser Art. Sie", "Jahre alt. Daher", "bestätigen dies. Weitere"
    if kern in SATZENDE_FAEHIG or (kern in SEITEN_FOLGE and t[:1] == "f" and re.search(r"\d$", vorher)):
        if token.endswith(")"):  # "(… etc.) Kontext"
            return False
        return folge in STARTWOERTER  # "etc. Diese" trennt, "etc. Konsumenten", "ff. SGB" nicht
    if len(kern) == 1 and kern.isalpha():  # Initiale / "z. B." / "Gruppe A. Die"
        return t[-2:-1].isupper() and folge in STARTWOERTER and not vorher.endswith(".")
    if kern in ABKUERZUNGEN:
        return False
    zkern = kern.lstrip("<>=≤≥~±")
    if re.fullmatch(r"\d{1,2}", zkern):  # Ordinalzahl "die 3. Phase" – außer vor Satzanfang oder nach Verweis
        return folge in STARTWOERTER or _kern(vorher) in VERWEIS_VOR_ZAHL
    teile = [p for p in re.split(r"[.\-]", zkern) if p]
    if "." in zkern and teile and all(p.isdigit() and len(p) <= 3 for p in teile):  # 31.12. / 4.2. / .05 / 1.234
        return folge in STARTWOERTER
    if "." in kern and all(len(teil) <= 3 for teil in kern.split(".") if teil):  # z.B. u.a. d.h. i.d.R.
        return False
    if re.fullmatch(r"[a-zäöü]{1,6}\.-[a-zäöü]{1,7}", kern):  # Dipl.-Ing. Univ.-Prof. Priv.-Doz.
        return False
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


@lru_cache(maxsize=65536)
def silben(wort: str) -> int:
    """Silbenkerne nach Best (Vokal oder Diphthong); 0 bei vokallosen Token (bzw, Std)."""
    w = re.sub(r"[^a-zäöüßéèàáâêôûy]", "", wort.lower()).replace("qu", "qv")  # u nach q ist kein Kern
    if not w:
        return 0
    if _ENGLISCH_TEST.search(w):
        for muster, ersatz in _ENGLISCH:
            w = muster.sub(ersatz, w)
    n = len(SILBENKERN_RE.findall(w))
    if not n:
        return 0
    if len(w) > 5 and re.search(r"[^aeiouäöü]ien$", w) and not re.search(r"(schien|spien|wien)$", w):
        n += 1  # Stu-di-en, Me-di-en
    n += len(_IEN_KOMPOSITUM_RE.findall(w))
    if _HIAT_EXTRA_RE.search(w):
        n += 1  # Mu-se-um, I-de-en
    if w.startswith("koo"):
        n += 1  # Ko-o-pe-ra-ti-on
    if re.match(r"(be|ge)e[nhrd]", w) and w not in _AUSNAHMEN_BEE:
        n += 1  # be-en-den, ge-ehrt
    n += len(re.findall(r"(?<!d)i(?=en[tz])", w))  # Pa-ti-ent, Ef-fi-zi-enz (nicht: dient)
    return n


@lru_cache(maxsize=65536)
def stamm(wort: str) -> str:
    w = wort.lower()
    for endung in ("ungen", "ung", "heiten", "keiten", "heit", "keit", "ern", "en", "er", "es", "em", "e", "n", "s"):
        if len(w) - len(endung) >= 4 and w.endswith(endung):
            w = w[: -len(endung)]
            break
    return w[:8]


def inhaltsstaemme(satz_tokens: list[str]) -> set:
    return {stamm(t) for t in satz_tokens if ist_wort(t) and t.lower() not in FUNKTIONSWOERTER and len(t) > 2}


def fuer_wortlaenge(w: str) -> bool:
    """Wortlängen-/Silbenmaße ohne Ein-Buchstaben-Token, vokallose Abkürzungen, Akronyme und Ziffernwörter (HW05)."""
    return len(w) > 1 and not AKRONYM_RE.fullmatch(w) and not any(ch.isdigit() for ch in w) and silben(w) > 0


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


ABSCHNITT_L = 800  # Wörter je Kalibrierabschnitt (kalibriere.L_STANDARD); Fensterlänge längenabhängiger Kennzahlen
BLOCK_AB = 1200  # = 1,5·ABSCHNITT_L: darüber bewertet analysiere_und_bewerte im Blockmodus (Schnittstelle S4)


def fenster_starts(n: int, L: int = ABSCHNITT_L) -> list[int]:
    """Startpositionen von k = ceil(n/L) Fenstern der Länge L, gleichmäßig zwischen 0 und n − L (HW01)."""
    if n <= L:
        return [0]
    k = math.ceil(n / L)
    return [round(i * (n - L) / (k - 1)) for i in range(k)]


def satz_fenster(woerter_je_satz: list[int], L: int = ABSCHNITT_L) -> list[tuple[int, int]]:
    """Fenster aus ganzen Sätzen mit höchstens L Wörtern (Satzindizes von, bis); ≤ L Wörter: ein Fenster."""
    n = sum(woerter_je_satz)
    if n <= L or not woerter_je_satz:
        return [(0, len(woerter_je_satz))]
    kum = [0]
    for x in woerter_je_satz:
        kum.append(kum[-1] + x)
    out = []
    for st in fenster_starts(n, L):
        a = min(next(i for i, c in enumerate(kum) if c >= st), len(woerter_je_satz) - 1)
        e = a
        while e < len(woerter_je_satz) and kum[e + 1] - kum[a] <= L:
            e += 1
        out.append((a, max(e, a + 1)))
    return out


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


def mattr_klumpung(woerter, fenster=100):
    """MATTR geteilt durch die Zufallserwartung der Typen je Fenster (Rarefaktion, hypergeometrisch)."""
    n = len(woerter)
    if not n:
        return 0.0
    w = min(fenster, n)
    log_nenner = math.lgamma(n + 1) - math.lgamma(n - w + 1)
    ev = 0.0
    for f in Counter(woerter).values():
        if n - f < w:
            ev += 1.0
        else:
            ev += 1.0 - math.exp(math.lgamma(n - f + 1) - math.lgamma(n - f - w + 1) - log_nenner)
    return mattr(woerter, fenster) / (ev / w) if ev else 0.0


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


def _log_nb(k: int, mu: float, s: float) -> float:
    mu = max(mu, 1e-12)
    if s >= 1e6:  # Poisson-Grenzfall
        return k * math.log(mu) - mu - math.lgamma(k + 1)
    return (math.lgamma(k + s) - math.lgamma(s) - math.lgamma(k + 1)
            + s * math.log(s / (s + mu)) + k * math.log(mu / (s + mu)))


def fw_llr_zaehlung(zaehlung, n: int, profil: dict | None) -> float | None:
    """fw_llr aus Zählungen {Wort: k} und Wortzahl n (bewerte(), kalibriere.py)."""
    woerter = (profil or {}).get("woerter") or []
    if not n or not woerter:
        return None
    rm, rk, gr = profil.get("rate_mensch", {}), profil.get("rate_ki", {}), profil.get("groesse", {})
    llr = 0.0
    for w in woerter:
        if w not in rm or w not in rk:
            continue
        k = int(zaehlung.get(w, 0))
        s = float(gr.get(w) or 1e6)
        llr += _log_nb(k, rm[w] * n, s) - _log_nb(k, rk[w] * n, s)
    return 1000.0 * llr / n


_fw_llr_zaehlung = fw_llr_zaehlung  # alter Name


def fw_llr(woerter_low: list[str], profil: dict | None) -> float | None:
    """Funktionswort-Profil (HW07): 1000·LLR/n, NegBin je Wort; positiv = menschlicher."""
    if not profil or not woerter_low:
        return None
    return fw_llr_zaehlung(Counter(woerter_low), len(woerter_low), profil)


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


def muster_treffer(satz: str, muster: list[dict]) -> list[tuple]:
    """Treffer eines Satzes; bei Überlappung zählt nur der Treffer mit höchstem Gewicht (dann der längste).
    Rückgabe: (start, ende, gewicht, muster, fund, verdrängte Muster-IDs)."""
    return muster_aufloesen([(t.start(), t.end(), float(mu.get("gewicht", 1.0)), mu, t.group(0))
                             for mu in muster for t in mu["_re"].finditer(satz) if t.end() > t.start()])


def muster_aufloesen(kand: list[tuple]) -> list[tuple]:
    """Überlappende Kandidaten (start, ende, gewicht, muster, fund) eines Satzes auflösen: höchstes Gewicht, dann
    längster, dann frühester Treffer gewinnt. Auch von kalibriere.py genutzt (gleiche Regel mit Fold-Gewichten)."""
    behalten = []
    for k in sorted(kand, key=lambda k: (-k[2], -(k[1] - k[0]), k[0])):
        konflikt = next((b for b in behalten if not (k[1] <= b[0] or k[0] >= b[1])), None)
        if konflikt is None:
            behalten.append(k + ([],))
        elif k[3]["id"] != konflikt[3]["id"]:
            konflikt[5].append(k[3]["id"])
    return sorted(behalten, key=lambda k: k[0])


# ---------------------------------------------------------------------------
# Satzbau
# ---------------------------------------------------------------------------

def _ohne_zahlzeichen(t: str) -> str:
    """Dezimalkommas ('3,45') und Semikolon in Kennwertreihen ('3,45; SD = 1') nicht als Satzzeichen zählen."""
    return re.sub(r"(?<=\d)[,;](?=\s?[A-Za-z]{1,3}\s?=|\d)", " ", t)


def _verbfinal(segment: str, folge: str = "") -> bool:
    """Segment endet auf (kleingeschriebenes) Verb – Nebensatz; Aufzählung/Apposition endet auf ein Nomen."""
    segment = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", segment)
    segment = re.split(r"[(\[]", segment)[0]  # am Komma zerschnittenen Beleg abtrennen
    ws = re.findall(r"[A-Za-zÄÖÜäöüß]+|\d+", segment)
    alpha = [w for w in ws if w[0].isalpha()]
    if alpha and not alpha[-1].islower() and re.search(r"\s(?:als|wie)\s", segment):
        segment = re.split(r"\s(?:als|wie)\s", segment)[0]  # Nachfeld: 'der höher lag als bei Männern'
        ws = re.findall(r"[A-Za-zÄÖÜäöüß]+|\d+", segment)
        alpha = [w for w in ws if w[0].isalpha()]
    if len(alpha) < 2 or not alpha[-1].islower():
        return False
    if len(ws) >= 3:
        return True
    f = folge.split()  # 'die zeigen, dass …' / 'die rauchen, haben …'
    return bool(f) and (f[0].lower() in SUBJUNKTIONEN | SUBJUNKTIONEN_NACH_KOMMA or (f[0].islower() and f[0] not in ARTIKEL_KONJ))


def _hat_verbkandidat(segment: str) -> bool:
    """Finites Verb möglich: Wort aus FINIT oder kleingeschriebenes Nicht-Funktionswort auf -t/-te/-ten/-en/-st,
    dem kein großgeschriebenes Wort folgt."""
    toks = tokens(segment)
    for i, t in enumerate(toks):
        low = t.lower()
        if low in FINIT or (low in FINIT_MEHRDEUTIG and (i == 0 or toks[i - 1].lower() != "zu")):
            return True
        if (t.islower() and low not in FUNKTIONSWOERTER and buchstaben(t) >= 4 and re.search(r"(?:t|te|ten|en|st)$", low)
                and not re.search(r"(?:ant|[^i]ent|ekt|akt|ukt|ikt)$", low)
                and not (i + 1 < len(toks) and toks[i + 1][:1].isupper())):
            return True
    return False


def teilsatz_zerlegung(satz: str) -> tuple[int, int, int]:
    """(Hauptsätze, Nebensätze, Infinitivgruppen) – Stufe 1 der Definition 'ein Teilsatz pro finitem Verb'."""
    satz = _ohne_zahlzeichen(satz)
    low = satz.lower()
    neben = sum(1 for t in tokens(satz) if t.lower() in SUBJ_UEBERALL)
    infinitiv = 0
    teile_mit = re.split(r"([,;])\s*", satz)
    teile = teile_mit[0::2]
    trenner = [""] + teile_mit[1::2]
    erster = teile[0].lower().split()
    w0 = erster[0].strip("„\"(") if erster else ""
    if w0 in ("um", "ohne", "statt", "anstatt") and re.search(r"\bzu\b|\w+zu\w+(?:en|ln|rn)\b", teile[0].lower()):
        infinitiv += 1  # 'Um … zu prüfen, …' – kein Teilsatz
    elif w0 == "je" and re.search(r"\b(desto|umso|um so)\b", low):
        neben += 1
    elif (w0 in SATZANFANG_SUBJ and len(teile) > 1 and (len(erster) < 2 or erster[1] not in BIS_PRAEP_FOLGE)
          and _verbfinal(teile[0], teile[1])):
        neben += 1
    haupt = 1
    for i, roh in enumerate(teile[1:], 1):
        w = roh.lower().split()
        if not w:
            continue
        if trenner[i] == ";":
            haupt += _hat_verbkandidat(roh)  # Semikolon verbindet Hauptsätze
            continue
        if w[0] in NEBENORDNER and _hat_verbkandidat(roh):
            haupt += 1  # ', sondern die Folgen' ohne Verb zählt nicht
        folge = teile[i + 1] if i + 1 < len(teile) else ""
        w0 = w[0].strip("„\"(")
        if w0 in SUBJ_UEBERALL:
            continue  # schon gezählt
        if _INF_RE.search(roh.strip()) and not re.search(r"\b(ist|sind|war|waren|bleibt|bleiben)\b", roh.lower()):
            infinitiv += 1  # ', die Ursachen zu untersuchen' / ', frühzeitig zu handeln'
        elif w0 in NUR_NACH_KOMMA:
            if (len(w) < 2 or (w[1] not in BIS_PRAEP_FOLGE and not w[1][0].isdigit())) and _verbfinal(roh, folge):
                neben += 1
        elif w0 in RELATIVPRONOMEN or w0 in SUBJUNKTIONEN_NACH_KOMMA:
            if _verbfinal(roh, folge) and not _NP_REIHE.match(roh):  # 'das Alter, das Geschlecht und das Einkommen'
                neben += 1
        elif w0 in PRAEPOSITIONEN and len(w) > 1 and w[1] in RELATIVPRONOMEN:
            neben += 1
        elif w0 in ("um", "ohne", "anstatt", "statt") and re.search(r"\bzu\b|\w+zu\w+(?:en|ln|rn)\b", roh.lower()):
            infinitiv += 1
    return haupt, neben, infinitiv


def teilsatz_info(satz: str, satz_tokens: list[str] | None = None) -> tuple[int, bool]:
    """Zahl der Teilsätze (Haupt- + Nebensätze mit finitem Verb) und ob ein Nebensatz vorkommt."""
    haupt, neben, _ = teilsatz_zerlegung(satz)
    return haupt + neben, neben > 0


def _teilsatz_info_komma(satz: str, satz_tokens: list[str]) -> int:
    """Alter Komma-Zähler, nur für den Vergleich in einem Kalibrierlauf (info['teilsatz_alt'])."""
    low = satz.lower()
    neben = sum(1 for t in satz_tokens if t.lower() in SUBJUNKTIONEN)
    teile = re.split(r"[,;]\s*", low)
    for teil in teile[1:]:
        w = teil.split()
        if not w:
            continue
        w0 = w[0].strip("„\"(")
        if w0 in SUBJUNKTIONEN:
            continue
        if w0 in SUBJUNKTIONEN_NACH_KOMMA or w0 in RELATIVPRONOMEN:
            neben += 1
        elif w0 in PRAEPOSITIONEN and len(w) > 1 and w[1] in RELATIVPRONOMEN:
            neben += 1
        elif w0 in ("um", "ohne", "anstatt", "statt") and re.search(r"\bzu\b|\w+zu\w+en\b", teil):
            neben += 1
    haupt = 1 + sum(1 for teil in teile[1:] if teil.split() and teil.split()[0] in NEBENORDNER) + low.count(";")
    return haupt + neben


def ist_passiv(satz: str) -> bool:
    """werden-Passiv: Partizip II in Satzklammer mit werden; Futur, würde + Infinitiv und Kopula ausgenommen."""
    toks = _TOK_SATZZEICHEN_RE.findall(satz)
    low = [t.lower() for t in toks]
    pos_w = [i for i, t in enumerate(low) if t in WERDEN_FORMEN]
    if not pos_w:
        return False
    praet = any(low[i] in WERDEN_PRAET for i in pos_w)
    modal = any(t in MODALVERBEN for t in low)

    def naechstes(i):
        j = i + 1
        while j < len(toks) and toks[j] in TRANSPARENT:
            j += 1
        return j
    for i, t in enumerate(toks):
        w = low[i]
        if w in WERDEN_FORMEN or w in KEIN_PARTIZIP or not t[:1].isalpha():
            continue
        if w.startswith("un") and not w.startswith("unter"):  # 'ungenutzt'
            continue
        j = naechstes(i)
        if j < len(toks) and low[j] == "zu":
            j = naechstes(j)
        direkt_davor = j < len(toks) and low[j] in WERDEN_FORMEN  # überspringt „“ ( )
        if not (t.islower() or (i == 0 and direkt_davor)):  # Nomen sind groß; 'Beschrieben wird …'
            continue
        if not (i > pos_w[0] or direkt_davor):
            continue
        if i + 1 < len(toks) and toks[i + 1][:1].isupper():  # attributiv: 'begrenzten Zeitraum'
            continue
        if PARTIZIP_T.fullmatch(w) or (PARTIZIP_GE_EN.fullmatch(w) and w not in GE_INFINITIVE):
            return True
        if PARTIZIP_EN_ABLAUT.fullmatch(w):
            return True
        if PARTIZIP_EN_OHNE_GE.fullmatch(w) and (
                praet or (direkt_davor and (low[j] == "worden" or (low[j] == "werden" and (modal or low[i + 1] == "zu"))))):
            return True  # infinitivgleiches Partizip nur nach Präteritum, vor 'worden' oder mit Modalverb
    return False


def satzklammern(satz: str) -> list[int]:
    """Spannen (Wörter) zwischen finitem Hilfs-/Modalverb und Partizip/Infinitiv am Teilsatzende (HW08)."""
    spannen = []
    for teil in re.split(r"[,;:()–—]", satz):
        tw = tokens(teil)
        aux = next((i for i, t in enumerate(tw) if t.lower() in HILFSVERBEN), None)
        if aux is None:
            continue
        j = len(tw) - 1
        while j > aux and tw[j].lower() in KLAMMER_INF_ENDE:  # 'müssen … erhoben werden'
            j -= 1
        w = tw[j]
        if (j - aux >= 2 and w.islower() and buchstaben(w) >= 4 and w not in FUNKTIONSWOERTER and w not in HILFSVERBEN
                and re.search(r"(?:en|t|iert|ert|elt)$", w)):
            spannen.append(j - aux - 1)
    return spannen


def autorenlisten(text: str) -> list[str]:
    """Autorenlisten vor einer Jahresangabe (v7): „Kahneman, Knetsch und Thaler (1986)“, „Xia, Monroe und Cox et al.
    [2004]“. Gibt die Namensreihe ohne Jahr zurück; der Beleg selbst fällt in bereinige_absatz weg, deshalb wird auf dem
    Rohabsatz gesucht und das Ergebnis an dreierlisten weitergereicht."""
    return [m.group("liste") for m in AUTORENLISTE_RE.finditer(text)]


def dreierlisten(satz: str, autoren: list[str] | set[str] | None = None) -> list[str]:
    """Echte Aufzählungen mit ≥ 3 Gliedern; Komma vor Nebensatz/Relativsatz/Infinitiv zählt nicht.

    Keine Dreierliste (v7): Autorenlisten vor einer Jahresangabe („Kahneman, Knetsch und Thaler (1986)“). Weil der
    Beleg im bereinigten Satz fehlt, übergibt _analysiere die im Rohabsatz gefundenen Listen als autoren; ein Satz mit
    noch vorhandenem Beleg wird zusätzlich selbst geprüft."""
    ausnahmen = set(autoren or ()) | set(autorenlisten(satz))
    out, pos = [], 0
    while True:
        m = DREIERLISTE_RE.search(satz, pos)
        if not m:
            return out
        k1, k2 = m.group("g1").split()[-1], m.group("g2").split()[-1]
        satzanfang = m.start("g1") == 0 and len(m.group("g1").split()) == 1
        # Köpfe von Glied 1 und 2 gleich geschrieben (Nomen-Nomen bzw. Adj./Verb-Adj./Verb); '-verwaltung' passt immer
        ok = satzanfang or k1[:1].isupper() == k2[:1].isupper() or k2[:1] == "-" or k1.endswith("-")
        if ok and ausnahmen:
            rest = satz[m.start("g2"):m.end()]  # ab dem 2. Glied: liegt die Reihe ganz in einer Autorenliste?
            ok = not any(rest in au for au in ausnahmen)
        if ok and m.group("g2").split()[0].lower() in RELATIVPRONOMEN and m.group(0).split()[-1].lower() not in ARTIKEL_POSS:
            segment = re.split(r"[,;]", satz[m.start("g2"):])[0]  # Relativsatz: verbfinal, keine Artikelreihe
            ok = not (_verbfinal(segment) and not _NP_REIHE.match(segment))
        if ok:
            out.append(m.group(0))
            pos = m.end()
        else:
            pos = m.start() + 1


def substantiv_maske(satz_tokens: list[list[str]]) -> list[list[bool]]:
    """Substantiv = großgeschrieben, nicht am Satzanfang; am Satzanfang nur, wenn die Form im Text auch im
    Satzinneren groß vorkommt. Akronyme und Funktionswörter ausgeschlossen."""
    innen = {t for toks in satz_tokens for t in toks[1:] if t[:1].isupper()}
    maske = []
    for toks in satz_tokens:
        zeile = []
        for i, t in enumerate(toks):
            ist = (t[:1].isupper() and t[:1].isalpha() and not AKRONYM_RE.fullmatch(t)
                   and t.lower() not in FUNKTIONSWOERTER and (i > 0 or t in innen))
            zeile.append(ist)
        maske.append(zeile)
    return maske


def nominalketten(saetze_text: list[str]) -> list[int]:
    """Längen (Substantive) maximaler Genitiv-/von-Ketten mit ≥ 2 Substantiven; Satzzeichen brechen die Kette (HW13)."""
    roh = [[t for t in ROH_TOKEN_RE.findall(s)] for s in saetze_text]
    maske = substantiv_maske([[t for t in toks if t[:1].isalnum()] for toks in roh])
    laengen = []
    for toks, m_woerter in zip(roh, maske):
        ist_subst, k = [], 0
        for t in toks:  # Maske (nur Wörter) auf Roh-Token mit Satzzeichen übertragen
            if t[:1].isalnum():
                ist_subst.append(m_woerter[k])
                k += 1
            else:
                ist_subst.append(False)
        i = 0
        while i < len(toks):
            if not ist_subst[i]:
                i += 1
                continue
            n_subst, j = 1, i
            while True:
                p = j + 1
                if p >= len(toks) or toks[p].lower() not in GENVERB or toks[p][:1].isupper():
                    break
                q, adj = p + 1, 0
                while (q < len(toks) and adj < 3 and toks[q][:1].islower() and toks[q][:1].isalpha()
                       and toks[q] not in FUNKTIONSWOERTER):
                    q, adj = q + 1, adj + 1
                if q < len(toks) and ist_subst[q]:
                    n_subst, j = n_subst + 1, q
                else:
                    break
            if n_subst >= 2:
                laengen.append(n_subst)
            i = j + 1
    return laengen


# ---------------------------------------------------------------------------
# Eingabeprüfung (v7): verklebte Wörter, Anteil wörtlicher Zitate
# ---------------------------------------------------------------------------

VERKLEBT_RE = re.compile(r"(?<=\w)([.,;:!?])([A-Za-zÄÖÜäöüß]{2,})")
VERKLEBT_LANG = 25  # Token über 25 Zeichen mit innerem Komma oder Klein-Groß-Wechsel
_VERKLEBT_URL_RE = re.compile(r"://|^www\.|@|[A-Za-z0-9-]\.(?:de|com|org|net|eu|at|ch|edu|gov|info|io|uk|fr|it|nl)(?:/|$)")
_VERKLEBT_DATEI_RE = re.compile(r"\.(?:pdf|docx?|xlsx?|csv|txt|py|md|json|html?|jpe?g|png|gif|zip|pptx?|odt|xml|sav|dta|tex|"
                                r"bib|js|r)$", re.IGNORECASE)
_KLEIN_GROSS_RE = re.compile(r"[a-zäöüß](?!I(?:nnen|n\b))[A-ZÄÖÜ]")  # Binnen-I (StudentInnen) ausgenommen


def _verklebt(kern: str) -> bool:
    """True, wenn ein Token (ohne umgebende Anführungen/Klammern) verklebte Wörter enthält (PDF-Extraktion)."""
    if _VERKLEBT_URL_RE.search(kern) or _VERKLEBT_DATEI_RE.search(kern):
        return False
    for m in VERKLEBT_RE.finditer(kern):
        zeichen, rechts = m.group(1), m.group(2)
        links = kern[:m.start(1)]
        if links[-1:].isdigit():
            continue  # Zahlen: „14:30Uhr“, „§2.BGB“
        lw = re.search(r"[A-Za-zÄÖÜäöüß]+$", links)
        if not lw or len(lw.group(0)) == 1 or lw.group(0).lower() in ABKUERZUNGEN | MEHRDEUTIG:
            continue  # Initialen und Abkürzungen: „M.Sc“, „J.Smith“, „Dr.Müller“, „vgl.Abb“
        if zeichen in ".!?" and not rechts[0].isupper():
            continue  # Code, Domains, Dateinamen; ein Satzanfang wäre großgeschrieben
        if zeichen == "." and (rechts.isupper() or (lw.group(0)[0].isupper() and len(rechts) <= 4
                                                    and rechts.lower() not in STARTWOERTER)):
            continue  # Marken- und Domainnamen: „Plan.Net“, „Group.IE“, „DATA.GOV“ (aber „Ziel.Die“ zählt)
        if zeichen == ":" and re.match(r"in(?:nen)?$", rechts):
            continue  # Gender-Doppelpunkt „Mitarbeiter:innen“
        return True
    if len(kern) > VERKLEBT_LANG:
        if re.search(r"[^\W\d_],[^\W\d_]", kern):
            return True
        if any(len(teil) > 12 and _KLEIN_GROSS_RE.search(teil) for teil in kern.split("-")):
            return True  # „wiesichdieHZB“; Markennamen in Komposita („YouTube-Trendlisten-Analyse“) bleiben
    return False


def verklebte_stellen(saetze: list[dict]) -> list[dict]:
    """Verklebte Wörter in den gemessenen Sätzen: [{'stelle': Ausschnitt, 'satz': Satznummer}] (v7).

    Regeln: Satzzeichen direkt vor ≥ 2 Buchstaben („erfasst.Merkmale“, „Note,wie“; nach . ! ? nur vor Großbuchstaben)
    oder ein Token über 25 Zeichen mit innerem Komma bzw. Klein-Groß-Wechsel. Ausgenommen: Abkürzungen und Initialen,
    URLs, E-Mail-Adressen, Dateinamen, Zahlen, Gender-Doppelpunkt, Binnen-I."""
    out = []
    for s in saetze:
        for tok in s["text"].split():
            kern = tok.strip("\"'„“”»«‚‘’()[]{}").rstrip(".,;:!?").rstrip("\"'“”»«’‘)]}")
            if kern and _verklebt(kern):
                out.append({"stelle": kern if len(kern) <= 60 else kern[:59] + "…", "satz": s.get("nr")})
    return out


def zitat_spannen(text: str) -> list[tuple[int, int]]:
    """Zeichenbereiche wörtlicher Zitate in einem Absatz: „…“ (auch „…”), »…« bzw. «…» (das erste Guillemet bestimmt die
    Richtung), “…” und "…"; verschachtelte Zitate zählen zum äußeren. Nicht geschlossene Zitate zählen nicht."""
    erstes = re.search(r"[»«]", text)
    g_auf, g_zu = ("«", "»") if erstes and erstes.group(0) == "«" else ("»", "«")
    stapel: list[tuple[str, int]] = []
    out = []
    for i, ch in enumerate(text):
        if stapel:
            zu = stapel[-1][0]
            if ch == zu or (zu == "“" and ch == "”"):
                _, start = stapel.pop()
                if not stapel:
                    out.append((start, i + 1))
                continue
        if ch == "„":
            stapel.append(("“", i))
        elif ch == g_auf:
            stapel.append((g_zu, i))
        elif ch == "“":
            stapel.append(("”", i))
        elif ch == '"':
            stapel.append(('"', i))
    return out


ZITAT_MIN_WOERTER = 4  # kürzere Anführungen gelten als hervorgehobene Begriffe, nicht als wörtliches Zitat


def zitat_woerter(text: str) -> int:
    """Wörter (ist_wort) in wörtlichen Zitaten mit mindestens ZITAT_MIN_WOERTER Wörtern."""
    n = 0
    for a, e in zitat_spannen(text):
        k = sum(1 for t in TOKEN_RE.findall(text[a:e]) if ist_wort(t))
        if k >= ZITAT_MIN_WOERTER:
            n += k
    return n


# ---------------------------------------------------------------------------
# Hauptanalyse
# ---------------------------------------------------------------------------

def hinweis_langer_text(n_w: int) -> str:
    """Hinweis für Texte über BLOCK_AB Wörter, wenn analysiere_text sie am Stück misst."""
    return (f"{n_w} Wörter – die Referenzwerte stammen aus Abschnitten à {ABSCHNITT_L} Wörtern. Bewertet wird ein so "
            f"langer Text deshalb im Blockmodus (Blöcke von etwa {ABSCHNITT_L} Wörtern, je Kennzahl der Median); am Stück "
            "gemessen liegen Absatz- und Streuungsmaße (CV) höher.")


def analysiere_text(text: str, muster: list[dict] | None = None, fw_profil: dict | None = None,
                    letzter_absatz_gekuerzt: bool = False) -> dict:
    """Berechnet alle Rohmetriken. Gibt dict mit 'metriken', 'saetze', 'muster_treffer', 'info' zurück.

    fw_profil: Funktionswort-Profil aus baselines.json (setzt fw_profil_llr_pro_1000).
    letzter_absatz_gekuerzt: letzter Absatz zählt nicht in die Absatz-Kennzahlen (gekürzter Abschnitt)."""
    return _analysiere(text, muster, fw_profil, letzter_absatz_gekuerzt)[0]


def _analysiere(text: str, muster: list[dict] | None, fw_profil: dict | None,
                letzter_absatz_gekuerzt: bool, struktur: dict | None = None) -> tuple[dict, dict]:
    """analysiere_text plus Zwischenstände für den Blockmodus: Struktur (mit Textreihenfolge), Sätze je
    Roh-Absatz (auch leere) und Wörter je Satz.

    struktur: bereits zerlegte Struktur (wie zerlege_bloecke); dann wird text nicht erneut zerlegt (Blockmodus).
    Absätze, deren Index in struktur['bereinigt'] steht, bestehen schon aus bereinigten Sätzen (Teilstück eines
    Riesenabsatzes) und werden nicht ein zweites Mal bereinigt (bereinige_absatz ist nicht idempotent)."""
    if muster is None:
        muster = lade_muster()
    if struktur is None:
        struktur = zerlege_bloecke(text)
    zaehler: Counter = Counter()
    absatz_saetze: list[list[str]] = []
    roh_saetze: list[list[str]] = []  # je Eintrag von struktur["absaetze"], auch ohne Satz
    schon_bereinigt = set(struktur.get("bereinigt", ()))
    absatz_autoren: list[list[str]] = []  # Autorenlisten vor Jahresangaben im Rohabsatz (v7, für dreierlisten)
    for ai, a in enumerate(struktur["absaetze"]):
        sauber = a if ai in schon_bereinigt else bereinige_absatz(a, zaehler)
        s = zerlege_saetze(sauber)
        roh_saetze.append(s)
        if s:
            absatz_saetze.append(s)
            absatz_autoren.append(autorenlisten(a))

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
    anteil = lambda x, n: x / n if n else 0.0  # noqa: E731
    m: dict[str, float | None] = {}

    # --- Satzlänge -----------------------------------------------------------
    laengen = [len(s["tokens"]) for s in saetze]
    m["satzlaenge_mittel"] = mittel(laengen)
    m["satzlaenge_median"] = statistics.median(laengen) if laengen else 0.0
    m["satzlaenge_sd"] = sd(laengen)
    m["satzlaenge_cv"] = cv(laengen)
    m["satzlaenge_p10"] = perzentil(laengen, 0.10)
    m["satzlaenge_p90"] = perzentil(laengen, 0.90)
    m["satzlaenge_max"] = float(max(laengen)) if laengen else 0.0
    # längenabhängig (HW01: +0,36 SD zwischen 600 und 1300 Wörtern): Median über Satzfenster à ABSCHNITT_L Wörter
    w_je_satz = [sum(1 for t in s["tokens"] if ist_wort(t)) for s in saetze]
    m["satzlaenge_schiefe"] = statistics.median(schiefe(laengen[a:e]) for a, e in satz_fenster(w_je_satz)) if laengen else 0.0
    m["satzlaenge_dispersion"] = (sd(laengen) ** 2 / mittel(laengen)) if laengen and mittel(laengen) else 0.0
    m["anteil_kurze_saetze"] = anteil(sum(l <= 10 for l in laengen), n_s)
    m["anteil_sehr_kurze_saetze"] = anteil(sum(l <= 6 for l in laengen), n_s)
    m["anteil_lange_saetze"] = anteil(sum(l >= 30 for l in laengen), n_s)
    m["anteil_sehr_lange_saetze"] = anteil(sum(l >= 40 for l in laengen), n_s)
    m["anteil_mittlere_saetze"] = anteil(sum(14 <= l <= 26 for l in laengen), n_s)

    # --- Satzrhythmus --------------------------------------------------------
    diffs = [abs(laengen[i + 1] - laengen[i]) for i in range(len(laengen) - 1)]
    m["rhythmus_sprung_rel"] = (mittel(diffs) / mittel(laengen)) if diffs and mittel(laengen) else 0.0
    log_l = [math.log(l) for l in laengen]
    # Lag-1-Autokorrelation der log-Längen, um den Erwartungswert -1/n unter Zufallsreihenfolge korrigiert (HW10)
    m["rhythmus_r1_log"] = autokorrelation(log_l, 1) + 1 / n_s if n_s >= 4 else 0.0
    r1_absatz = None
    if n_s >= 4:
        mu_l = mittel(log_l)
        paare = [(log_l[i], log_l[i + 1]) for i in range(n_s - 1) if saetze[i]["absatz"] == saetze[i + 1]["absatz"]]
        nenner = sum((x - mu_l) ** 2 for x in log_l) / n_s
        if paare and nenner:
            r1_absatz = sum((a - mu_l) * (b - mu_l) for a, b in paare) / len(paare) / nenner + 1 / n_s
    in_lauf = [False] * len(laengen)
    for i in range(len(laengen) - 2):
        fenster = laengen[i : i + 3]
        mf = mittel(fenster)
        if mf and all(abs(x - mf) <= 0.2 * mf for x in fenster):
            in_lauf[i] = in_lauf[i + 1] = in_lauf[i + 2] = True
    m["anteil_gleichfoermige_laeufe"] = anteil(sum(in_lauf), n_s)

    # --- Wortlänge / Silben (ohne Abkürzungen, Akronyme, Ein-Buchstaben-Token; HW05) -------
    wl_woerter = [w for w in woerter if fuer_wortlaenge(w)]
    wl = [buchstaben(w) for w in wl_woerter]
    sil = [silben(w) for w in wl_woerter]
    n_wl = len(wl)
    m["wortlaenge_mittel"] = mittel(wl)
    m["wortlaenge_sd"] = sd(wl)
    m["wortlaenge_cv"] = cv(wl)
    m["anteil_lange_woerter"] = anteil(sum(x > 6 for x in wl), n_wl)
    m["anteil_sehr_lange_woerter"] = anteil(sum(x >= 13 for x in wl), n_wl)
    m["anteil_kurze_woerter"] = anteil(sum(x <= 3 for x in wl), n_wl)
    m["silben_mittel"] = mittel(sil)
    m["silben_sd"] = sd(sil)
    m["anteil_einsilbig"] = anteil(sum(x == 1 for x in sil), n_wl)
    m["anteil_mehrsilbig_3plus"] = anteil(sum(x >= 3 for x in sil), n_wl)
    m["anteil_mehrsilbig_5plus"] = anteil(sum(x >= 5 for x in sil), n_wl)
    c_sil = Counter(sil)
    m["silben_q21"] = (c_sil[2] + 0.5) / (c_sil[1] + 0.5)  # HW22, Kandidat

    # --- Wortschatz ------------------------------------------------------------
    m["mattr_100"] = mattr(woerter_low, 100)
    m["mattr_50"] = mattr(woerter_low, 50)
    # HW12: nur auf festen Fenstern gültig (−0,49 SD zwischen 600 und 1300 Wörtern) – Median über Fenster à ABSCHNITT_L
    m["mattr_klumpung_100"] = statistics.median(mattr_klumpung(woerter_low[a:a + ABSCHNITT_L], 100)
                                                for a in fenster_starts(n_w))
    m["mtld"] = mtld(woerter_low)
    m["yule_k"] = yule_k(woerter_low)
    m["anteil_funktionswoerter"] = anteil(sum(w in FUNKTIONSWOERTER for w in woerter_low), n_w)
    if fw_profil:
        m["fw_profil_llr_pro_1000"] = fw_llr(woerter_low, fw_profil)
    inhalt = [stamm(w) for w in woerter_low if w not in FUNKTIONSWOERTER and len(w) > 2]
    m["inhaltswort_mattr_50"] = mattr(inhalt, 50)
    formen: dict[str, Counter] = defaultdict(Counter)
    for w in woerter:
        if w.lower() not in FUNKTIONSWOERTER and len(w) > 2:
            formen[stamm(w)][w] += 1
    kern = sorted(formen.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))[:5]
    kernbegriffe = [{"stamm": st, "form": c.most_common(1)[0][0], "anzahl": sum(c.values())} for st, c in kern]
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
    m["nominalstil_pro_100"] = 100.0 * anteil(sum(w.endswith(NOMINAL_ENDUNGEN) and len(w) > 5 for w in woerter_low), n_w)
    ketten = nominalketten([s["text"] for s in saetze])
    m["nominalketten_pro_100"] = 100.0 * anteil(len(ketten), n_w)  # HW13, Kandidat
    m["hedging_pro_1000"] = pro1000(sum(w in HEDGING for w in woerter_low))
    m["ich_wir_pro_1000"] = pro1000(sum(w in PERSONAL for w in woerter_low))
    m["man_pro_1000"] = pro1000(woerter_low.count("man"))

    # --- Satzbau -------------------------------------------------------------
    teilsaetze, teilsaetze_alt, mit_neben, passiv, infinitive = [], [], 0, 0, 0
    menz_x, menz_y = [], []
    spannen = []
    for s in saetze:
        haupt, neben, inf = teilsatz_zerlegung(s["text"])
        n_teil = haupt + neben
        s["teilsaetze"] = n_teil
        teilsaetze.append(n_teil)
        teilsaetze_alt.append(_teilsatz_info_komma(_ohne_zahlzeichen(s["text"]), s["tokens"]))
        mit_neben += neben > 0
        infinitive += inf
        menz_x.append(n_teil)
        menz_y.append(len(s["tokens"]) / n_teil)
        passiv += ist_passiv(s["text"])
        spannen.extend(satzklammern(s["text"]))
    ct = Counter(teilsaetze)
    m["teilsaetze_pro_satz"] = mittel(teilsaetze)
    m["teilsatz_verhaeltnis_21"] = (ct[2] + 0.5) / (ct[1] + 0.5)  # HW09
    m["anteil_saetze_mit_nebensatz"] = anteil(mit_neben, n_s)
    m["anteil_einfache_saetze"] = anteil(sum(1 for s in saetze if not re.search(r"[,;]", _ohne_zahlzeichen(s["text"]))), n_s)
    m["woerter_pro_teilsatz"] = (n_tok / sum(teilsaetze)) if teilsaetze else 0.0
    m["menzerath_korrelation"] = korrelation(menz_x, menz_y)
    m["anteil_passiv"] = anteil(passiv, n_s)
    m["satzklammer_mittel"] = mittel(spannen) if len(spannen) >= 5 else None  # HW08; None bei < 5 Klammern

    # Satzanfänge und Konnektoren
    erste = []
    konnektor_start = 0
    dies_start = 0
    konn_gesamt = konn_mitte = 0
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
        offset = len(s["text"]) - len(s["text"].lstrip("„\"'(»"))
        for t in KONNEKTOR_RE.finditer(s["text"]):
            konn_gesamt += 1
            if t.start() > offset:
                konn_mitte += 1
                s["konnektor_mitte"] = True
    m["anteil_konnektor_satzanfang"] = anteil(konnektor_start, n_s)
    m["konnektoren_pro_1000"] = pro1000(konn_gesamt)  # HW15
    m["anteil_dies_satzanfang"] = anteil(dies_start, n_s)
    m["anteil_artikel_satzanfang"] = anteil(sum(e in ("der", "die", "das") for e in erste), n_s)
    gleich = sum(1 for i in range(1, len(erste)) if erste[i] and erste[i] == erste[i - 1])
    m["satzanfang_wiederholung"] = gleich / (len(erste) - 1) if len(erste) > 1 else 0.0
    top3 = sum(c for _, c in Counter(erste).most_common(3))
    m["satzanfang_top3_anteil"] = anteil(top3, n_s)

    # --- Zeichensetzung (pro 1000 Token) -----------------------------------
    roh = " ".join(s["text"] for s in saetze)
    roh_z = _ohne_zahlzeichen(roh)
    m["kommas_pro_1000"] = pro1000(roh_z.count(","))
    m["semikolon_pro_1000"] = pro1000(roh_z.count(";"))
    # nur Doppelpunkt vor Leerraum, Ende, Anführung, Klammer, Strich – nicht Mitarbeiter:innen, 14:30, https://
    m["doppelpunkt_pro_1000"] = pro1000(len(re.findall(r":(?=\s|$|[\"„“”»«‚‘’)\]–—])", roh)))
    m["gedankenstrich_pro_1000"] = pro1000(len(GEDANKENSTRICH_RE.findall(roh)))
    m["klammern_pro_1000"] = pro1000(roh.count("("))
    m["anfuehrungen_pro_1000"] = pro1000(len(re.findall(r"[„“”\"»«]", roh)) / 2)
    m["fragen_pro_1000"] = pro1000(sum(s["text"].rstrip("\"“”»)").endswith("?") for s in saetze))
    m["ausrufe_pro_1000"] = pro1000(sum(s["text"].rstrip("\"“”»)").endswith("!") for s in saetze))
    m["kommas_pro_satz"] = anteil(roh_z.count(","), n_s)
    m["abkuerzungen_pro_1000"] = pro1000(len(ABK_STIL_RE.findall(roh)))  # HW05

    # --- Absätze (gekürzter letzter Absatz zählt nicht) ---------------------
    abs_liste = absatz_saetze[:-1] if letzter_absatz_gekuerzt else absatz_saetze
    abs_w = [sum(len(tokens(s)) for s in liste) for liste in abs_liste]
    abs_s = [len(liste) for liste in abs_liste]
    m["absaetze"] = float(len(abs_liste))
    m["absatzlaenge_mittel"] = mittel(abs_w)
    m["absatzlaenge_cv"] = cv(abs_w) if len(abs_w) > 1 else 0.0
    m["saetze_pro_absatz"] = mittel(abs_s)
    m["saetze_pro_absatz_cv"] = cv(abs_s) if len(abs_s) > 1 else 0.0
    m["anteil_einsatz_absaetze"] = anteil(sum(x == 1 for x in abs_s), len(abs_s))

    # --- KI-Muster und Struktur ---------------------------------------------
    treffer_gesamt = 0.0
    treffer_liste = []
    for s in saetze:
        for _a, _e, g, mu, fund, verdraengt in muster_treffer(s["text"], muster):
            if g <= 0:
                continue  # Gewicht 0 = laut Kalibrierung kein KI-Signal: weder Fund noch Flag
            treffer_gesamt += g
            eintrag = {"satz": s["nr"], "muster": mu["id"], "label": mu.get("label", mu["id"]),
                       "kategorie": mu.get("kategorie", ""), "fund": fund, "gewicht": g}
            if verdraengt:
                eintrag["ueberlagert"] = sorted(set(verdraengt))
            treffer_liste.append(eintrag)
            if mu["id"] not in s.setdefault("muster", []):
                s["muster"].append(mu["id"])
    m["ki_muster_pro_1000"] = pro1000(treffer_gesamt)
    dreier = [dreierlisten(s["text"], absatz_autoren[s["absatz"] - 1]) for s in saetze]
    m["dreierlisten_pro_1000"] = pro1000(sum(len(d) for d in dreier))
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
        if s.get("konnektor_mitte"):
            flags.append("konnektor_mitte")
        if s.get("dies_start"):
            flags.append("dies_anfang")
        if i > 0 and erste[i] and erste[i] == erste[i - 1]:
            flags.append("gleicher_satzanfang")
        if GEDANKENSTRICH_RE.search(s["text"]):
            flags.append("gedankenstrich")
        if dreier[i]:
            flags.append("dreierliste")
        for mid in s.get("muster", []):
            flags.append("muster:" + mid)
        s["flags"] = flags
        s["woerter"] = l

    roh_verweis = len(ABK_VERWEIS_RE.findall(roh))
    verklebt = verklebte_stellen(saetze)
    n_zitat = sum(zitat_woerter(" ".join(liste)) for liste in absatz_saetze)
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
        "fussnoten_entfernt": zaehler["fussnoten"],
        "fussnoten_text_entfernt": struktur["fussnoten_text"],
        "zitatbloecke": struktur["zitatbloecke"],
        "satzlaengen": laengen,
        "satzlaengen_verteilung": verteilung(laengen),
        "kernbegriffe": kernbegriffe,
        "verweis_abk": roh_verweis,
        "teilsatz_verteilung": {str(k) if k < 4 else "4+": round(anteil(sum(v for kk, v in ct.items() if (kk == k if k < 4 else kk >= 4)), n_s), 3)
                                for k in (1, 2, 3, 4)},
        "infinitivgruppen": infinitive,
        "teilsatz_alt": {"teilsaetze_pro_satz": round(mittel(teilsaetze_alt), 4),
                         "woerter_pro_teilsatz": round(n_tok / sum(teilsaetze_alt), 4) if teilsaetze_alt else 0.0},
        "satzklammern": len(spannen),
        "anteil_klammer_ab_8": round(anteil(sum(x >= 8 for x in spannen), len(spannen)), 4),
        "anteil_konnektor_mittelstellung": round(konn_mitte / konn_gesamt, 4) if konn_gesamt else None,
        "rhythmus_r1_log_absatz": round(r1_absatz, 4) if r1_absatz is not None else None,
        "nominalketten_laenge_mittel": round(mittel(ketten), 4) if ketten else None,
        "verklebt": verklebt,
        "zitat_anteil": round(anteil(n_zitat, n_w), 4),
        "transkript_notation": zaehler["transkript"],
        "warnungen": [],
    }
    if verklebt:
        bsp = verklebt[0]
        info["warnungen"].append(
            f"{len(verklebt)} verklebte Stelle{'n' if len(verklebt) > 1 else ''} ohne Leerzeichen (z. B. „{bsp['stelle']}“ in "
            f"Satz {bsp['satz']}) – typisch für PDF-Extraktion. Das verfälscht Satzgrenzen, Satz- und Wortlängen; vor der "
            "Bewertung die fehlenden Leerzeichen einfügen.")
    if n_w < 300:
        info["warnungen"].append(f"Nur {n_w} Wörter – unter ~300 Wörtern sind die Kennzahlen unzuverlässig.")
    if n_s < 15:
        info["warnungen"].append(f"Nur {n_s} Sätze – Verteilungsmaße (Varianz, Rhythmus) sind wenig aussagekräftig.")
    elif n_s < 30:
        info["warnungen"].append(f"Nur {n_s} Sätze – Rhythmuswert unsicher (SE ≈ 1/√n), wird nicht bewertet.")
    if n_w > BLOCK_AB:  # Referenz = Abschnitte à ABSCHNITT_L Wörter (HW01); analysiere_und_bewerte ersetzt den Hinweis
        info["warnungen"].append(hinweis_langer_text(n_w))
    for s in saetze:
        s.pop("tokens", None)
        s.pop("konnektor_start", None)
        s.pop("konnektor_mitte", None)
        s.pop("dies_start", None)
    fw_zaehlung = Counter(w for w in woerter_low if w in FW_SET)
    return {
        "metriken": {k: (round(v, 4) if v is not None else None) for k, v in m.items()},
        "saetze": saetze,
        "muster_treffer": treffer_liste,
        "info": info,
        "fw_zaehlung": {"n": n_w, "k": dict(fw_zaehlung)},
    }, {"struktur": struktur, "roh_saetze": roh_saetze, "woerter_je_satz": w_je_satz}


FW_SET = set(FW_WOERTER) | FUNKTIONSWOERTER


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
    "satzlaenge_mittel": "Satzlänge Ø (Token inkl. Zahlen)",
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
    "rhythmus_r1_log": "Rhythmus: Autokorrelation log-Satzlängen (Lag 1, biaskorrigiert)",
    "anteil_gleichfoermige_laeufe": "Anteil Sätze in gleichförmigen Läufen",
    "wortlaenge_mittel": "Wortlänge Ø (Buchstaben)",
    "wortlaenge_sd": "Wortlänge Standardabweichung",
    "wortlaenge_cv": "Wortlängen-Variation (CV)",
    "anteil_lange_woerter": "Anteil langer Wörter (>6 Buchst.)",
    "anteil_sehr_lange_woerter": "Anteil sehr langer Wörter (≥13 Buchst.)",
    "anteil_kurze_woerter": "Anteil kurzer Wörter (≤3 Buchst.)",
    "silben_mittel": "Silben pro Wort Ø",
    "silben_sd": "Silben pro Wort SD",
    "silben_q21": "Verhältnis Zwei- zu Einsilbern",
    "anteil_einsilbig": "Anteil einsilbiger Wörter",
    "anteil_mehrsilbig_3plus": "Anteil Wörter ≥3 Silben",
    "anteil_mehrsilbig_5plus": "Anteil Wörter ≥5 Silben",
    "mattr_100": "Lexikalische Variation (MATTR-100)",
    "mattr_50": "Lexikalische Variation (MATTR-50)",
    "mattr_klumpung_100": "Lokale Begriffswiederholung (MATTR ÷ Zufallserwartung)",
    "mtld": "Lexikalische Variation (MTLD)",
    "yule_k": "Yules K (Wiederholungsrate)",
    "anteil_funktionswoerter": "Anteil Funktionswörter",
    "fw_profil_llr_pro_1000": "Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich)",
    "inhaltswort_mattr_50": "Vielfalt der Inhaltswörter",
    "nachbarsatz_ueberlappung": "Begriffsaufnahme zw. Nachbarsätzen",
    "anteil_saetze_mit_wortaufnahme": "Sätze, die einen Begriff des Vorsatzes aufnehmen",
    "nominalstil_pro_100": "Nominalstil (-ung/-heit/-keit … pro 100 W.)",
    "nominalketten_pro_100": "Nominalketten (Genitiv-/von-Ketten) pro 100 W.",
    "hedging_pro_1000": "Abschwächungen/Modalität pro 1000",
    "ich_wir_pro_1000": "ich/wir pro 1000",
    "man_pro_1000": "„man“ pro 1000",
    "teilsaetze_pro_satz": "Teilsätze pro Satz",
    "teilsatz_verhaeltnis_21": "Verhältnis Sätze mit 2 zu 1 Teilsatz",
    "anteil_saetze_mit_nebensatz": "Anteil Sätze mit Nebensatz",
    "anteil_einfache_saetze": "Anteil Sätze ohne Komma",
    "woerter_pro_teilsatz": "Wörter pro Teilsatz",
    "menzerath_korrelation": "Kopplung Teilsatzzahl–Teilsatzlänge",
    "anteil_passiv": "Anteil Passivsätze",
    "satzklammer_mittel": "Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv",
    "anteil_konnektor_satzanfang": "Satzanfang mit Konnektor (Zudem, Darüber hinaus …)",
    "konnektoren_pro_1000": "Konnektoren pro 1000 (alle Stellungen)",
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
    "abkuerzungen_pro_1000": "Abkürzungen pro 1000 (z. B., bzw., d. h. …)",
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


def _abstand(wert, ziel, streu):
    return abs(wert - ziel) / streu if streu else abs(wert - ziel)


Z_CLIP = 3.0  # Logit-Modell: standardisierte Merkmale auf ±Z_CLIP begrenzt (S1; kalibriere.py importiert den Wert)
UNSICHER_FAKTOR = 0.5  # 'unsicher': Abstand zur Grenze < UNSICHER_FAKTOR · se_typ · √(ABSCHNITT_L / n) (S3)


def z_standard(x: float, mu: float, sigma: float | None) -> float:
    """z-Wert eines Modellmerkmals mit Clipping auf ±Z_CLIP (S1); sd 0/None zählt als 1."""
    return max(-Z_CLIP, min(Z_CLIP, (x - mu) / (sigma or 1.0)))


def ki_richtung(r: dict) -> int | None:
    """Richtung, in der der KI-Median vom menschlichen Median abweicht (v7): +1 = KI höher, −1 = KI niedriger.
    Bei gleichen Medianen (z. B. beide 0 bei ich/wir) entscheidet die AUROC-Richtung der Kalibrierung ('richtung');
    ohne beides None."""
    m50 = (r.get("mensch") or {}).get("p50")
    k50 = (r.get("ki") or {}).get("p50")
    if m50 is not None and k50 is not None and k50 != m50:
        return 1 if k50 > m50 else -1
    return {"ki_hoeher": 1, "mensch_hoeher": -1}.get(r.get("richtung"))


def seite_von(wert: float, r: dict) -> str | None:
    """'ki', wenn der Wert vom menschlichen Median aus in Richtung des KI-Medians abweicht, 'gegen' auf der anderen
    Seite (v7); None ohne bekannte KI-Richtung oder genau am Median."""
    richtung = ki_richtung(r)
    p50 = (r.get("mensch") or {}).get("p50")
    if richtung is None or p50 is None or wert == p50:
        return None
    return "ki" if (wert - p50) * richtung > 0 else "gegen"


def kappe_von(r: dict) -> dict | None:
    """Einseitige Kappung eines Modellmerkmals am menschlichen Band (v7): auf der der KI abgewandten Seite höchstens bis
    P90 (KI niedriger → {'seite': 'oben', 'wert': P90}) bzw. P10 (KI höher → {'seite': 'unten', 'wert': P10}); die
    KI-Seite bleibt offen (dort begrenzt nur Z_CLIP). Werte jenseits des Bands sind dann für das Modell so menschlich wie
    der Bandrand: Übertreibung wird nicht weiter belohnt. kalibriere.py schreibt das Ergebnis nach modell['kappen']."""
    richtung = ki_richtung(r)
    mensch = r.get("mensch") or {}
    if richtung is None or mensch.get("p10") is None or mensch.get("p90") is None:
        return None
    return {"seite": "oben", "wert": mensch["p90"]} if richtung < 0 else {"seite": "unten", "wert": mensch["p10"]}


def gekappt(x: float | None, kappe: dict | None) -> float | None:
    """Wert nach der einseitigen Kappung (v7); ohne Kappe unverändert, None bleibt None."""
    if x is None or not kappe:
        return x
    return min(x, kappe["wert"]) if kappe["seite"] == "oben" else max(x, kappe["wert"])


def bewerte(ergebnis: dict, baselines: dict | None, textsorte: str = "hochschule") -> dict:
    """Ordnet jede Kennzahl gegen die menschliche Referenzverteilung ein (grün/gelb/rot).

    'unsicher' (S3) = |Wert − nächste Grenze P25/P75| < UNSICHER_FAKTOR · se_typ · √(ABSCHNITT_L / max(ABSCHNITT_L, n)),
    n = ergebnis['info']['woerter'] (fehlt die Angabe: ABSCHNITT_L); Status und Score bleiben unverändert.
    Logit-Modell mit z-Clipping (S1) auf den einseitig gekappten Werten (v7, modell['kappen'], siehe kappe_von);
    'beitrag' je Modellmerkmal = koef · (z(gekappter Wert) − z(Mensch-Median)), negativ = zieht Richtung KI, dazu
    'modell_beitraege' aufsteigend sortiert (S2).
    Je Kennzahl (v7): 'seite' = 'ki' | 'gegen' | None (Abweichung vom menschlichen Median in Richtung des KI-Medians bzw.
    davon weg; None bei grün oder unbekannter KI-Richtung), 'jenseits_band' = Wert jenseits P10/P90 auf der Gegenseite.
    'score_ki' = einseitiger Score: Abweichungen auf der Gegenseite zählen wie grün (Gewichte wie beim Score); 'score'
    bleibt der zweiseitige Score.
    Fehlt fw_profil_llr_pro_1000 und enthält die Textsorte ein fw_profil, wird es aus ergebnis['fw_zaehlung']
    nachberechnet und in ergebnis['metriken'] eingetragen."""
    m = ergebnis["metriken"]
    if not baselines or textsorte not in baselines.get("textsorten", {}):
        return {"verfuegbar": False, "kennzahlen": [], "score": None, "score_ki": None}
    ts = baselines["textsorten"][textsorte]
    fw = ts.get("fw_profil")
    if fw and "fw_profil_llr_pro_1000" not in m and ergebnis.get("fw_zaehlung"):
        z = ergebnis["fw_zaehlung"]
        wert = fw_llr_zaehlung(z.get("k", {}), z.get("n", 0), fw)
        m["fw_profil_llr_pro_1000"] = round(wert, 4) if wert is not None else None
    n_s = ergebnis.get("info", {}).get("saetze")
    n_woerter = ergebnis.get("info", {}).get("woerter") or 0
    unsicher_skala = UNSICHER_FAKTOR * math.sqrt(ABSCHNITT_L / max(ABSCHNITT_L, n_woerter))
    ref = ts.get("metriken", {})

    # Logit-Modell (S1) und Beiträge (S2): Referenzpunkt ist der menschliche Median, ohne Referenzwert das Modellmittel
    modell = ts.get("modell")
    p_mensch, beitraege = None, {}
    if modell:
        kappen = modell.get("kappen") or {}  # v7; ältere baselines.json ohne Kappung
        logit = modell["intercept"]
        for key, coef in modell["koeffizienten"].items():
            if m.get(key) is None:
                continue  # fehlend = Mittelwert (z = 0), wie in kalibriere.py
            mu, sigma = modell["mittel"][key], modell["sd"][key]
            z_wert = z_standard(gekappt(m[key], kappen.get(key)), mu, sigma)
            logit += coef * z_wert
            p50 = gekappt(((ref.get(key) or {}).get("mensch") or {}).get("p50"), kappen.get(key))
            # gerundet; + 0.0 macht aus −0.0 (negativer Koeffizient · 0, z. B. Semikolons am Median 0) eine 0.0
            beitraege[key] = round(coef * (z_wert - (z_standard(p50, mu, sigma) if p50 is not None else 0.0)), 4) + 0.0
        p_mensch = round(1 / (1 + math.exp(-max(-30, min(30, logit)))), 3)
    zeilen = []
    gew_summe = gew_punkte = gew_punkte_ki = 0.0
    for key, r in ref.items():
        if m.get(key) is None:
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
        if ki and ki.get("p50") is not None:
            ki_naeher = _abstand(wert, ki["p50"], ki.get("sd")) < _abstand(wert, mensch["p50"], mensch.get("sd"))
        richtung = None
        if status != "gruen":
            richtung = "erhoehen" if wert < mensch["p25"] else "senken"
        seite = seite_von(wert, r) if status != "gruen" else None
        se = r.get("se_typ")
        unsicher = bool(se) and min(abs(wert - mensch["p25"]), abs(wert - mensch["p75"])) < unsicher_skala * se
        bewertet = r.get("bewertet", False)
        if key == "rhythmus_r1_log" and n_s is not None and n_s < 30:
            bewertet = False  # Reihenfolgemaß bei < 30 Sätzen zu unsicher
        zeile = {
            "id": key,
            "name": NAMEN.get(key, key),
            "wert": wert,
            "mensch_p10": mensch["p10"], "mensch_p25": mensch["p25"], "mensch_p50": mensch["p50"],
            "mensch_p75": mensch["p75"], "mensch_p90": mensch["p90"],
            "ki_p50": ki.get("p50"),
            "trennschaerfe": r.get("auroc"),
            "gewicht": r.get("gewicht", 0.0),
            "bewertet": bewertet,
            "nur_modell": bool(r.get("nur_modell")),  # nur im Modell p_mensch, nie Rot-Ziel (HW07)
            "status": status,
            "unsicher": unsicher,
            "ki_naeher": ki_naeher,
            "richtung": richtung,
            "seite": seite,
            "jenseits_band": seite == "gegen" and status == "rot",
            "beitrag": round(beitraege[key], 4) if key in beitraege else None,
            "hinweis": r.get("hinweis", ""),
        }
        if r.get("cluster") is not None:
            zeile["cluster"] = r["cluster"]
        zeilen.append(zeile)
        if zeile["bewertet"]:
            g = max(0.0, float(zeile["gewicht"] or 0.0))
            punkte = {"gruen": 1.0, "gelb": 0.5, "rot": 0.0}[status]
            gew_summe += g
            gew_punkte += g * punkte
            gew_punkte_ki += g * (1.0 if seite == "gegen" else punkte)
    score = round(100 * gew_punkte / gew_summe) if gew_summe else None
    score_ki = round(100 * gew_punkte_ki / gew_summe) if gew_summe else None
    zeilen.sort(key=lambda z: (not z["bewertet"], {"rot": 0, "gelb": 1, "gruen": 2}[z["status"]], -(z["gewicht"] or 0)))
    modell_beitraege = sorted(({"id": k, "name": NAMEN.get(k, k), "beitrag": round(b, 4)} for k, b in beitraege.items()),
                              key=lambda e: (e["beitrag"], e["id"]))
    return {"verfuegbar": True, "kennzahlen": zeilen, "score": score, "score_ki": score_ki, "p_mensch": p_mensch,
            "modell_beitraege": modell_beitraege,
            "score_schwelle": ts.get("score_schwelle"), "ziel_p_mensch": ts.get("ziel_p_mensch"),
            "ziel_score": ts.get("ziel_score"), "ziel_score_ki": ts.get("ziel_score_ki"),
            "korpus": baselines.get("korpus", {})}


# ---------------------------------------------------------------------------
# Blockmodus (S4): lange Texte in Blöcken à etwa ABSCHNITT_L Wörtern bewerten
# ---------------------------------------------------------------------------

ABSATZ_KENNZAHLEN = ("absaetze", "absatzlaenge_mittel", "absatzlaenge_cv", "saetze_pro_absatz", "saetze_pro_absatz_cv",
                     "anteil_einsatz_absaetze")
BLOCK_HINWEIS = "Blockmodus:"  # Anfang des Hinweises in info['warnungen'] (Bericht zeigt ihn als Info, nicht als Warnung)


def _block_einheiten(intern: dict) -> list[dict]:
    """Prosa-Einheiten in Textreihenfolge mit Wortzahl und globalen Satzindizes (0-basiert, wie ergebnis['saetze']).

    Ein Absatz über 1,5·ABSCHNITT_L Wörtern zerfällt in Einzelsätze ('teil'), damit er an einer Satzgrenze geteilt
    werden kann. Überschriften hängen vor der folgenden Einheit, Listenpunkte hinter der vorigen (außer nach einer
    Überschrift). Verzeichnis-/Literatur-Überschriften werden weggelassen, damit auch _blocktext neu gemessen nichts
    abschneidet; Tabellen und Blockzitate zählen ohnehin nur in info."""
    struktur, roh_saetze, w_je_satz = intern["struktur"], intern["roh_saetze"], intern["woerter_je_satz"]
    einheiten: list[dict] = []
    offen: list[str] = []  # Überschriften/Listen vor der nächsten Einheit
    gi = 0
    for art, idx in struktur.get("folge", []):
        if art == "absatz":
            saetze = roh_saetze[idx]
            if not saetze:
                continue  # Absatz ohne Satz (z. B. nur Belege): auch am Stück nicht gemessen
            nrn = list(range(gi, gi + len(saetze)))
            gi += len(saetze)
            w = sum(w_je_satz[i] for i in nrn)
            if w > 1.5 * ABSCHNITT_L and len(saetze) > 1:
                for j, (satz, nr) in enumerate(zip(saetze, nrn)):
                    einheiten.append({"vor": offen, "nach": [], "text": satz, "absatz": idx, "teil": True,
                                      "letzter_teil": j == len(saetze) - 1, "saetze": [nr], "woerter": w_je_satz[nr]})
                    offen = []
            else:
                einheiten.append({"vor": offen, "nach": [], "text": struktur["absaetze"][idx], "absatz": idx,
                                  "teil": False, "letzter_teil": True, "saetze": nrn, "woerter": w})
                offen = []
        elif art == "ueberschrift":
            u = struktur["ueberschriften"][idx]
            if not (LITERATUR_UEBERSCHRIFT.match(u) or INHALTSVERZEICHNIS_UEBERSCHRIFT.match(u)):
                offen.append("# " + u)
        elif art == "liste":
            zeile = "- " + struktur["listenpunkte"][idx]
            if einheiten and not offen:
                einheiten[-1]["nach"].append(zeile)
            else:
                offen.append(zeile)
    if offen and einheiten:
        einheiten[-1]["nach"].extend(offen)
    return einheiten


def _bloecke_planen(einheiten: list[dict], L: int = ABSCHNITT_L) -> list[list[dict]]:
    """Gierig an Absatzgrenzen: Ein Block schließt, sobald er ≥ 0,75·L Wörter hat und die nächste Einheit ihn weiter
    von L entfernen würde. Ein Rest unter 0,75·L kommt zum vorigen Block."""
    bloecke: list[list[dict]] = []
    akt: list[dict] = []
    akt_w = 0
    for e in einheiten:
        if akt and akt_w >= 0.75 * L and abs(akt_w + e["woerter"] - L) > abs(akt_w - L):
            bloecke.append(akt)
            akt, akt_w = [], 0
        akt.append(e)
        akt_w += e["woerter"]
    if akt:
        if bloecke and akt_w < 0.75 * L:
            bloecke[-1].extend(akt)
        else:
            bloecke.append(akt)
    return bloecke


def _blockstruktur(block: list[dict]) -> dict:
    """Struktur eines Blocks wie zerlege_bloecke, direkt aus den Einheiten des Gesamttexts: Roh-Absätze (Bereinigung wie
    am Stück), Teilsätze eines geteilten Absatzes als ein Absatz, Überschriften und Listenpunkte in Textreihenfolge.

    Der Block wird bewusst nicht erneut aus Text zerlegt: Ein Teilstück eines Riesenabsatzes, das mit '2. …' oder
    'a) …' beginnt, würde sonst als ein einziger Listenpunkt gelesen (Block ohne Wörter), ein aus Zeilen mit je einem
    '|' zusammengefügter Absatz als Tabellenzeile."""
    st = {"absaetze": [], "ueberschriften": [], "listenpunkte": [], "tabellenzeilen": 0,
          "literatur_abgeschnitten": False, "fussnoten_text": 0, "zitatbloecke": 0, "folge": [], "bereinigt": []}
    listen = {"absatz": st["absaetze"], "ueberschrift": st["ueberschriften"], "liste": st["listenpunkte"]}

    def neu(art: str, inhalt: str) -> None:
        st["folge"].append((art, len(listen[art])))
        listen[art].append(inhalt)

    def zusatz(zeilen: list[str]) -> None:  # aus _block_einheiten: '# Überschrift' bzw. '- Listenpunkt'
        for z in zeilen:
            neu("ueberschrift" if z.startswith("# ") else "liste", z[2:])

    offener_absatz = None
    for e in block:
        if e["vor"]:
            zusatz(e["vor"])
            offener_absatz = None
        if e["teil"] and offener_absatz == e["absatz"]:
            st["absaetze"][-1] += " " + e["text"]
        else:
            neu("absatz", e["text"])
            if e["teil"]:  # aus bereinigten Sätzen: in _analysiere nicht erneut bereinigen
                st["bereinigt"].append(len(st["absaetze"]) - 1)
        offener_absatz = e["absatz"] if e["teil"] else None
        if e["nach"]:
            zusatz(e["nach"])
            offener_absatz = None
    return st


def _blocktext(block: list[dict]) -> str:
    """Text eines Blocks (Anzeige/Tests); gemessen wird über _blockstruktur, nicht über diesen Text."""
    st = _blockstruktur(block)
    praefix = {"absatz": ("", st["absaetze"]), "ueberschrift": ("# ", st["ueberschriften"]),
               "liste": ("- ", st["listenpunkte"])}
    return "\n\n".join(praefix[art][0] + praefix[art][1][i] for art, i in st["folge"])


def _satzbereiche(plan: list[list[dict]], block_erg: list[dict], saetze: list[dict]) -> list[tuple[int, int]]:
    """Globale Satznummern (von, bis) je Block. Stimmen die neu gemessenen Satzzahlen mit dem Gesamttext überein,
    ergeben sie sich fortlaufend; sonst über Textabgleich (Rückfall: Satzindizes der Einheiten)."""
    gemessen = [e["info"]["saetze"] for e in block_erg]
    erwartet = [sum(len(u["saetze"]) for u in block) for block in plan]
    if gemessen == erwartet and sum(gemessen) == len(saetze):
        out, start = [], 1
        for n in gemessen:
            out.append((start, start + n - 1))
            start += n
        return out
    texte = [s["text"] for s in saetze]
    out, zeiger = [], 0
    for block, e in zip(plan, block_erg):
        nrn = [i for u in block for i in u["saetze"]]
        von, bis = nrn[0], nrn[-1]  # Rückfall
        bt = [s["text"] for s in e["saetze"]]
        if bt:
            treffer = [i for i in range(zeiger, len(texte)) if texte[i] == bt[0]]
            if treffer:
                von = min(treffer, key=lambda i: abs(i - nrn[0]))
                ende = [i for i in range(von, len(texte)) if texte[i] == bt[-1]]
                if ende:
                    bis = min(ende, key=lambda i: abs(i - (von + len(bt) - 1)))
        out.append((von + 1, bis + 1))
        zeiger = bis + 1
    return out


def analysiere_und_bewerte(text: str, muster: list[dict] | None = None, baselines: dict | None = None,
                           textsorte: str = "hochschule") -> tuple[dict, dict]:
    """Analyse und Bewertung in einem Schritt (S4), mit Blockmodus für lange Texte.

    ergebnis = analysiere_text(text) wie bisher (alle Sätze mit globaler Nummer, Flags, info). Über BLOCK_AB bereinigten
    Wörtern wird der Text in Blöcke von etwa ABSCHNITT_L Wörtern zerlegt (Länge der Referenzabschnitte), jeder Block
    gemessen und bewertet; die Gesamtbewertung nutzt je Kennzahl den Median über die Blöcke (nur Kennzahlen, die in
    mindestens der Hälfte der Blöcke vorhanden sind), p_mensch = Median der Block-p_mensch. Zusätzliche Felder:
    'blockmodus', 'n_woerter', 'bloecke'. muster/baselines None = Standarddateien; {} = ohne Referenzwerte."""
    if muster is None:
        muster = lade_muster()
    if baselines is None:
        baselines = lade_baselines()
    fw_profil = ((baselines or {}).get("textsorten", {}).get(textsorte) or {}).get("fw_profil")
    ergebnis, intern = _analysiere(text, muster, fw_profil, False)
    n = ergebnis["info"]["woerter"]
    verfuegbar = bool(baselines) and textsorte in baselines.get("textsorten", {})
    plan = _bloecke_planen(_block_einheiten(intern)) if n > BLOCK_AB and verfuegbar else []
    if not plan:
        bewertung = bewerte(ergebnis, baselines, textsorte)
        bewertung.update(blockmodus=False, n_woerter=n, bloecke=[])
        return ergebnis, bewertung

    block_erg, block_bew = [], []
    for block in plan:
        gekuerzt = block[-1]["teil"] and not block[-1]["letzter_teil"]
        e = _analysiere("", muster, fw_profil, gekuerzt, struktur=_blockstruktur(block))[0]
        if not e["metriken"].get("absaetze"):  # kein vollständiger Absatz (Stück eines Riesenabsatzes)
            for k in ABSATZ_KENNZAHLEN:
                e["metriken"][k] = None
        block_erg.append(e)
        block_bew.append(bewerte(e, baselines, textsorte))

    schluessel = list(dict.fromkeys(k for e in block_erg for k in e["metriken"]))
    median_m = {}
    for k in schluessel:
        werte = [e["metriken"][k] for e in block_erg if e["metriken"].get(k) is not None]
        median_m[k] = round(statistics.median(werte), 4) if werte and 2 * len(werte) >= len(block_erg) else None
    n_s_typisch = statistics.median(e["info"]["saetze"] for e in block_erg)  # für die Rhythmus-Regel (< 30 Sätze)
    bewertung = bewerte({"metriken": median_m, "info": {"saetze": n_s_typisch, "woerter": n}}, baselines, textsorte)
    ps = [b["p_mensch"] for b in block_bew if b.get("p_mensch") is not None]
    bewertung["p_mensch"] = round(statistics.median(ps), 3) if ps else None

    bloecke = []
    for nr, (e, b, (von, bis)) in enumerate(zip(block_erg, block_bew, _satzbereiche(plan, block_erg, ergebnis["saetze"])), 1):
        rot = sum(1 for z in b["kennzahlen"] if z["bewertet"] and not z["nur_modell"] and z["status"] == "rot")
        bloecke.append({"nr": nr, "woerter": e["info"]["woerter"], "satz_von": von, "satz_bis": bis,
                        "score": b["score"], "score_ki": b.get("score_ki"), "p_mensch": b.get("p_mensch"), "rot": rot})
    bewertung.update(blockmodus=True, n_woerter=n, bloecke=bloecke)

    k = len(bloecke)
    hinweis = (f"{BLOCK_HINWEIS} {n} Wörter, bewertet in {k} Blöcken von etwa {ABSCHNITT_L} Wörtern" if k > 1 else
               f"{BLOCK_HINWEIS} {n} Wörter, bewertet als ein Block (ein Rest unter {round(0.75 * ABSCHNITT_L)} Wörtern "
               "wird nicht abgetrennt)")
    hinweis += (f" – die Referenzwerte stammen aus Abschnitten à {ABSCHNITT_L} Wörtern. "
                + ("Kennzahlen und Score beruhen auf dem Median über die Blöcke, die Modell-Einschätzung ist der Median "
                   "der Blöcke." if k > 1 else "Kennzahlen, Score und Modell-Einschätzung stammen aus diesem Block."))
    warn = ergebnis["info"]["warnungen"]
    alt = hinweis_langer_text(n)
    ergebnis["info"]["warnungen"] = [hinweis if w == alt else w for w in warn] if alt in warn else [hinweis] + warn
    return ergebnis, bewertung


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
    out.append("## Textanalyse\n")
    out.append(f"{info['woerter']} Wörter · {info['saetze']} Sätze · {info['absaetze']} Absätze"
               + (f" · {info['zitate_entfernt']} Quellenverweise (für die Messung ausgeblendet)" if info["zitate_entfernt"] else "")
               + (" · Literaturverzeichnis ignoriert" if info["literatur_abgeschnitten"] else ""))
    for w in info["warnungen"]:
        out.append(f"\n> {'ℹ️' if w.startswith(BLOCK_HINWEIS) else '⚠️'} {w}")
    bloecke = (bewertung.get("bloecke") or []) if bewertung.get("blockmodus") else []
    if bewertung.get("verfuegbar"):
        out.append("")
        teile = []
        median = " (Median der Blöcke)" if len(bloecke) > 1 else ""
        if bewertung["score"] is not None:
            teile.append(f"**Menschlichkeits-Score: {bewertung['score']}/100**")
        if bewertung.get("score_ki") is not None and bewertung["score_ki"] != bewertung["score"]:
            teile.append(f"nur KI-Seite: {bewertung['score_ki']}/100")
        if bewertung.get("p_mensch") is not None:
            teile.append(f"Modell-Einschätzung: {round(100 * bewertung['p_mensch'])} % menschlich{median}")
        out.append(" · ".join(teile))
        ki_ziehend = [b for b in bewertung.get("modell_beitraege") or [] if b["beitrag"] < 0][:3]
        if ki_ziehend:
            out.append("\nStärkste KI-Signale im Modell (Beitrag zum Logit gegenüber einem typischen menschlichen Text): "
                       + ", ".join(f"{b['name']} ({fmt(b['beitrag'])})" for b in ki_ziehend))
        if len(bloecke) > 1:
            out.append(f"\n_Blockmodus: Werte in der Tabelle = Median über {len(bloecke)} Blöcke._")
        out.append("")
        out.append("| | Kennzahl | Wert | Mensch (Zielbereich P25–P75) | Mensch Median | KI Median | Aufgabe |")
        out.append("|---|---|---|---|---|---|---|")
        for z in bewertung["kennzahlen"]:
            if not (z["bewertet"] or z.get("nur_modell")) and not alle:
                continue
            if z.get("nur_modell"):  # eigene Anzeige ohne Ampel: nur Tendenz (HW07)
                out.append(f"| ℹ️ | {z['name']} | {fmt(z['wert'])} | {fmt(z['mensch_p25'])}–{fmt(z['mensch_p75'])} | "
                           f"{fmt(z['mensch_p50'])} | {fmt(z['ki_p50'])} | nur Tendenz (fließt ins Modell) |")
                continue
            aufgabe = ""
            if z.get("seite") == "gegen":  # v7: menschlicher als typisch – nicht in Richtung KI zurückschieben
                aufgabe = "kein Auftrag (Gegenseite, kein KI-Signal)"
            elif z["richtung"] == "erhoehen":
                aufgabe = "↑ erhöhen"
            elif z["richtung"] == "senken":
                aufgabe = "↓ senken"
            if z["status"] != "gruen" and z["ki_naeher"] and z.get("seite") != "gegen":
                aufgabe += " (KI-typisch)"
            if z.get("unsicher") and z["status"] != "gruen":
                aufgabe += " (Grenzfall)"
            out.append(
                f"| {STATUS_SYMBOL[z['status']]} | {z['name']} | {fmt(z['wert'])} | {fmt(z['mensch_p25'])}–{fmt(z['mensch_p75'])} | "
                f"{fmt(z['mensch_p50'])} | {fmt(z['ki_p50'])} | {aufgabe.strip()} |"
            )
        if not alle:
            out.append("\n_Nur trennscharfe Kennzahlen gezeigt; alle mit `--alle`._")
        if bloecke:
            out.append(f"\n**Blöcke** (je etwa {ABSCHNITT_L} Wörter, wie die Referenzabschnitte)\n")
            out.append("| Block | Sätze | Wörter | Score | % menschlich |")
            out.append("|---|---|---|---|---|")
            ki_naechster = None
            if len(bloecke) > 1:
                ki_naechster = min(bloecke, key=lambda b: (b["p_mensch"] if b["p_mensch"] is not None else 2.0,
                                                           b["score"] if b["score"] is not None else 101))["nr"]
            for b in bloecke:
                p = f"{round(100 * b['p_mensch'])} %" if b["p_mensch"] is not None else "–"
                marke = " ← am KI-nächsten" if b["nr"] == ki_naechster else ""
                out.append(f"| {b['nr']} | {b['satz_von']}–{b['satz_bis']} | {b['woerter']} | {fmt(b['score'])} | {p}{marke} |")
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
        prio = lambda s: -sum(2 if f.startswith("muster:") else 1 for f in s["flags"])  # noqa: E731
        for s in sorted(auff, key=prio)[:max_stellen]:
            text = s["text"] if len(s["text"]) <= 160 else s["text"][:157] + "…"
            out.append(f"- Satz {s['nr']} (Abs. {s['absatz']}, {s['woerter']} W.): „{text}“ → {', '.join(s['flags'])}")
    if ergebnis["muster_treffer"]:
        c = Counter(t["label"] for t in ergebnis["muster_treffer"])
        out.append("\n**Gefundene KI-Muster:** " + ", ".join(f"{k} ({v}×)" for k, v in c.most_common(20)))
    if info.get("kernbegriffe"):
        out.append("\n**Kernbegriffe:** " + ", ".join(f"{k['form']} ({k['anzahl']}×)" for k in info["kernbegriffe"]))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datei", help="Textdatei (.txt/.md/.docx/.odt/.pdf) oder - für stdin")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--textsorte", default="hochschule")
    ap.add_argument("--baselines", help="Pfad zu baselines.json")
    ap.add_argument("--muster", help="Pfad zu ki_muster.json")
    ap.add_argument("--stellen", type=int, default=15, help="max. Zahl auffälliger Sätze im Bericht")
    ap.add_argument("--alle", action="store_true", help="auch nicht bewertete Kennzahlen zeigen")
    ap.add_argument("--ohne-saetze", action="store_true", help="JSON ohne Satzliste")
    args = ap.parse_args(argv)

    text = lies_datei(args.datei)
    baselines = lade_baselines(args.baselines)
    ergebnis, bewertung = analysiere_und_bewerte(text, lade_muster(args.muster), baselines or {}, args.textsorte)
    if args.datei.lower().endswith(".pdf"):
        ergebnis["info"]["warnungen"].append("PDF-Eingabe: Absätze sind aus dem Seitenlayout rekonstruiert – "
                                             "Absatzkennzahlen nur eingeschränkt verlässlich.")
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
