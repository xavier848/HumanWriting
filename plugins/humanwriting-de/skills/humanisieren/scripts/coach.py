#!/usr/bin/env python3
"""Stil-Coach: macht aus der Textanalyse konkrete, satzgenaue Arbeitsaufträge.

Der Coach schreibt nichts um. Er sagt, WAS an WELCHER Stelle zu ändern ist
(„Satz 7 und 8 zu einem Satz ab 30 Wörtern verbinden“), damit der Nutzer selbst formuliert. Danach misst man erneut;
mit --verlauf zeigt der Coach den Fortschritt seit der letzten Messung, meldet Überkorrektur und merkt sich, welche
Hinweise schon genannt wurden.

Grundsätze:
1. Nie über das menschliche Band hinaus: ein Hinweis nur, wenn seine Zielkennzahl auf der KI-Seite außerhalb des grünen
   Bereichs liegt, und nur so viele Aufträge, wie bis zum menschlichen Median nötig sind (Kontingent).
2. Präzision vor Menge: auf echten Texten soll der Coach wenig sagen.
3. Jeder Hinweis nennt eine konkrete, ohne Inhaltsänderung umsetzbare Handlung an einer konkreten Stelle.
4. Inhalt und Quellenzuordnung haben Vorrang: keine Hinweise in wörtlichen Zitaten, keine Bündelung, die eine Aussage
   einer fremden Quelle zuschreibt.
5. Keine fertigen Ersatzsätze für den Nutzertext; Technik-Beispiele nur an neutralen Beispielsätzen.

    python3 coach.py TEXT.md                             # Bericht
    python3 coach.py TEXT.md --verlauf TEXT.coach.json   # mit Fortschritt (Datei wird fortgeschrieben)
    python3 coach.py TEXT.md --format json

Nur Python-Standardbibliothek. Nutzt analyse.py aus dem Skill text-analyse.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter

HIER = os.path.dirname(os.path.abspath(__file__))
for kandidat in (os.path.join(HIER, "..", "..", "text-analyse", "scripts"), HIER):
    if os.path.exists(os.path.join(kandidat, "analyse.py")):
        sys.path.insert(0, os.path.normpath(kandidat))
        break
import analyse  # noqa: E402

DATA = analyse.DATA

# Kennzahl -> Hebel. Ein Hebel bündelt Kennzahlen, die man mit derselben Arbeit verschiebt.
HEBEL_VON = {
    **dict.fromkeys(["satzlaenge_cv", "satzlaenge_sd", "satzlaenge_dispersion", "satzlaenge_schiefe", "anteil_mittlere_saetze",
                     "anteil_lange_saetze", "anteil_sehr_lange_saetze", "anteil_kurze_saetze", "anteil_sehr_kurze_saetze",
                     "rhythmus_r1_log", "satzlaenge_mittel", "satzlaenge_median"], "satzlaenge"),
    **dict.fromkeys(["satzklammer_mittel", "nominalketten_pro_100"], "satzklammer"),
    "konnektoren_pro_1000": "konnektoren",
    "fw_profil_llr_pro_1000": "funktionswoerter",
    **dict.fromkeys(["saetze_pro_absatz_cv", "absatzlaenge_cv", "anteil_einsatz_absaetze", "saetze_pro_absatz", "absatzlaenge_mittel"], "absaetze"),
    **dict.fromkeys(["nachbarsatz_ueberlappung", "anteil_saetze_mit_wortaufnahme", "mattr_100", "mattr_50", "mtld", "inhaltswort_mattr_50",
                     "yule_k", "mattr_klumpung_100"], "begriffe"),
    **dict.fromkeys(["woerter_pro_teilsatz", "kommas_pro_1000", "kommas_pro_satz", "anteil_saetze_mit_nebensatz", "anteil_einfache_saetze",
                     "teilsaetze_pro_satz", "teilsatz_verhaeltnis_21"], "nebensaetze"),
    "semikolon_pro_1000": "semikolon",
    "doppelpunkt_pro_1000": "doppelpunkt",
    **dict.fromkeys(["ki_muster_pro_1000", "sondern_pro_1000", "nicht_nur_sondern_pro_1000", "sowohl_als_auch_pro_1000", "dreierlisten_pro_1000"], "floskeln"),
    **dict.fromkeys(["anteil_funktionswoerter", "anteil_kurze_woerter", "anteil_einsilbig", "wortlaenge_cv", "anteil_lange_woerter",
                     "silben_mittel", "silben_q21", "anteil_mehrsilbig_3plus", "wortlaenge_mittel", "nominalstil_pro_100"], "wortwahl"),
    **dict.fromkeys(["anfuehrungen_pro_1000", "ich_wir_pro_1000", "man_pro_1000", "klammern_pro_1000", "fragen_pro_1000"], "stimme"),
    "abkuerzungen_pro_1000": "abkuerzungen",
}

HEBEL_TEXT = {
    "satzlaenge": ("Satzlängen wie in echten Arbeiten verteilen", "{satzlaenge_daten} KI-Texte bleiben im mittleren Band (14–26 Wörter)."),
    "satzlaenge_bremse": ("Keine weiteren langen Sätze – einzelne teilen", "{satzlaenge_daten} Hier sind es mehr: Weiteres Bündeln würde vom menschlichen Bereich wegführen."),
    "satzklammer": ("Satzklammer füllen", "Bei Menschen stehen zwischen Hilfsverb und Partizip/Infinitiv mehr Wörter (Ø ~7 statt ~5). Claude lagert Angaben in eigene Sätze oder Nebensätze aus."),
    "konnektoren": ("Weniger Konnektoren", "Claude nutzt deutlich mehr Satzverknüpfer (zugleich, zudem, darüber hinaus, hingegen, jedoch …) als Menschen. Streichen, nicht verschieben."),
    "funktionswoerter": ("Funktionswort-Profil", "Das Profil kleiner Wörter ist das stärkste Einzelsignal: Claude schreibt häufiger mit „sich“, „als“, „sie“, „dass“, „diese“, Menschen häufiger mit „es“, „auch“, „durch“, „wie“. Steuerbar über die genannten Konstruktionen, nicht durch Einstreuen."),
    "absaetze": ("Absätze ungleich lang machen", "Menschliche Absätze schwanken stark (mal 2, mal 7 Sätze). KI-Absätze sind fast gleich lang."),
    "begriffe": ("Begriffe halten statt variieren", "Menschen nehmen den Begriff des Vorsatzes öfter wieder auf und bleiben bei einer Bezeichnung. Claude wechselt zwischen Synonymen und knüpft häufiger mit Possessiv an („Ihr …“, „Seine …“)."),
    "nebensaetze": ("Weniger Nebensätze, längere Teilsätze", "Claude hängt häufiger genau einen Nebensatz an (dass, weil, Relativsatz). Menschen packen dieselbe Information öfter in eine Nominalgruppe – die Teilsätze werden länger, der Satz nicht."),
    "semikolon": ("Semikolons ersetzen", "In menschlichen Hochschultexten kommen Semikolons kaum vor (Median 0). Claude setzt sie regelmäßig."),
    "doppelpunkt": ("Doppelpunkte reduzieren", "Doppelpunkte mitten im Satz sind bei Claude häufiger als bei Menschen."),
    "floskeln": ("KI-Floskeln und -Konstruktionen ersetzen", "Diese Wendungen kommen in Claude-Texten mehrfach häufiger vor als in echten Hochschularbeiten. Ziel ist der menschliche Median, nicht null."),
    "wortwahl": ("Wortwahl einfacher und natürlicher", "Menschen nutzen mehr kurze Allerweltswörter und gängige Abkürzungen (z. B., bzw.). Ergibt sich meist aus den übrigen Hebeln."),
    "abkuerzungen": ("Übliche Abkürzungen stehen lassen", "Menschliche Hochschultexte nutzen gängige Abkürzungen (z. B., d. h., bzw., vgl., u. a.). Claude schreibt sie fast immer aus."),
    "stimme": ("Eigene Stimme zeigen", "Menschliche Arbeiten zitieren öfter wörtlich, verwenden Klammern und manchmal „ich/wir“ oder „man“."),
}

# Hinweistyp -> Hebel (Gruppierung, Gewicht, Reihum-Auswahl)
TYP_HEBEL = {
    "buendeln": "satzlaenge", "teilen": "satzlaenge_bremse", "kurz": "satzlaenge", "zickzack": "satzlaenge",
    "klammer": "satzklammer", "klammer_zusatz": "satzklammer",
    "nebensatz": "nebensaetze", "kommas": "nebensaetze",
    "anknuepfung": "begriffe", "kein_bezug": "begriffe", "synonyme": "begriffe",
    "fw_lassen": "funktionswoerter", "fw_zeigt": "funktionswoerter", "fw_dichte": "funktionswoerter",
    "floskel": "floskeln", "gegenfolie": "floskeln", "konnektor": "konnektoren",
    "semikolon": "semikolon", "doppelpunkt": "doppelpunkt", "abkuerzung": "abkuerzungen",
    "absatz_teilen": "absaetze", "absatz_zusammen": "absaetze",
    "gender": "vorgaben", "gedankenstrich": "vorgaben",
}
STRUKTURELL = {"buendeln", "teilen", "kurz", "zickzack", "klammer", "klammer_zusatz", "nebensatz", "kommas"}

# Satzlängen-Klassen wie analyse.py (anteil_kurze/mittlere/lange/sehr_lange_saetze) – keine eigenen Schwellen
KURZ_MAX, MITTEL_VON, MITTEL_BIS, LANG_AB, SEHR_LANG_AB = 10, 14, 26, 30, 40
ZZ_KURZ_MAX, ZZ_LANG_AB = 15, 25  # Zickzack: absolute Klassen
MIN_WOERTER = 4  # kürzere „Sätze“ sind meist Fragmente der Satztrennung: keine Hinweise
VERDICHTUNG = 0.9  # Bündeln: zwei Sätze werden beim Verdichten etwa 10 % kürzer
MAX_TEILEN = 5

PARTIZIP_RE = re.compile(r"\b(Mitarbeitende|Teilnehmende|Studierende|Lehrende|Forschende|Lernende|Beratende|Pflegende|Wählende|Kundinnen und Kunden)[nr]?\b|\b\w+[*:_]innen\b|\b[a-zäöü]+Innen\b")
# wie analyse.py (konnektoren_pro_1000); „darüber hinaus“ läuft als KI-Muster
_KONN = getattr(analyse, "KONNEKTOREN", None)
KONNEKTOREN = [k for k in _KONN if isinstance(k, str)] if isinstance(_KONN, (list, tuple, set, frozenset)) else []
KONNEKTOREN = sorted(KONNEKTOREN, key=len, reverse=True) or ["zudem", "außerdem", "ferner", "des weiteren", "weiterhin", "folglich", "somit", "demnach",
               "infolgedessen", "allerdings", "jedoch", "dennoch", "gleichwohl", "nichtsdestotrotz", "insbesondere", "letztlich",
               "letztendlich", "zugleich", "gleichzeitig", "schließlich", "hingegen", "wiederum"]
KONNEKTOR_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in KONNEKTOREN) + r")\b", re.IGNORECASE)
HILFSVERBEN = set("""ist sind war waren sei seien wäre wären hat haben hatte hatten hätte hätten wird werden wurde wurden würde würden
kann können konnte konnten könnte könnten muss müssen musste mussten müsste müssten soll sollen sollte sollten will wollen wollte
wollten darf dürfen durfte durften dürfte dürften""".split())
KLAMMER_ENDE_HILFS = {"werden", "worden", "sein", "haben", "können", "müssen", "sollen", "dürfen", "wollen", "lassen", "gewesen", "geworden"}
AUSGESCHRIEBEN = {"zum beispiel": "z. B.", "das heißt": "d. h.", "beziehungsweise": "bzw.", "unter anderem": "u. a.",
                  "in der regel": "i. d. R.", "zum teil": "z. T.", "vergleiche": "vgl."}
AUSGESCHRIEBEN_RE = re.compile(r"\b(" + "|".join(AUSGESCHRIEBEN) + r")\b", re.IGNORECASE)

# Anknüpfung: nur, was laut Korpus KI-typisch oder ohne Bezug ist. „Dies“, „Dabei“, „Dadurch“, „Hierbei“ sind bei
# Menschen häufiger als bei Claude (pro 1000 Sätze 15,2 / 12,1 bzw. 16,4 / 9,3) und fehlen deshalb; Possessiv-Anfänge
# sind KI-typisch (4,2 / 8,3), „Sie/Er“ neutral (22,7 / 22,0), „Diese + Nomen“ nur mit abstraktem Sammelwort.
POSSESSIV = ("ihr", "ihre", "ihren", "ihrem", "ihrer", "ihres", "sein", "seine", "seinen", "seinem", "seiner", "seines", "deren", "dessen")
ANKNUEPF_RE = re.compile(r"^(?:(?P<poss>" + "|".join(POSSESSIV) + r")|(?P<pron>sie|er)|(?P<dem>diese[rsmn]?)\s+(?P<nomen>(?-i:[A-ZÄÖÜ])[\w-]*))\b",
                         re.IGNORECASE)
KAPSELWOERTER = ("aspekt", "entwicklung", "perspektive", "einschätzung", "besonderheit", "ansatz", "ansätze", "umstand", "umstände",
                 "sichtweise", "problematik", "herausforderung", "tatsache", "erkenntnis", "befund", "dimension", "facette", "annahme",
                 "auffassung", "überlegung", "konstellation", "tendenz", "verschiebung", "veränderung", "dynamik", "logik", "beobachtung",
                 "lesart", "vorgehensweise", "situation", "zusammenhang", "zusammenhänge", "einordnung", "differenzierung", "ambivalenz",
                 "wechselwirkung", "spannungsfeld", "doppelrolle", "kombination", "argumentation", "position", "feststellung", "sicht")
PERSONEN = ("autor", "autorin", "autoren", "forscher", "befragte", "teilnehmer", "mitarbeiter", "beschäftigte", "führungskräfte",
            "führungskraft", "kunden", "kunde", "konsumenten", "verbraucher", "bewerber", "bewerbende", "studierende", "lehrende",
            "controller", "manager", "experten", "nutzer", "eltern", "kinder", "schüler", "patienten", "arbeitnehmer", "arbeitgeber",
            "gründer", "investoren", "anleger", "probanden", "personen", "menschen", "akteure", "beteiligte", "unternehmer")
LEICHTE_NOMEN = {"jahr", "jahre", "jahren", "jahres", "prozent", "beispiel", "rahmen", "zusammenhang", "hinblick", "bezug", "sinne",
                 "folge", "weise", "teil", "fall", "fälle", "ende", "anfang", "januar", "februar", "märz", "april", "mai", "juni", "juli",
                 "august", "september", "oktober", "november", "dezember", "laufe", "grund", "basis", "hilfe", "form", "art"}
ANAPHER_RE = re.compile(r"^(?:dies|diese[rsmn]?|sie|er|es|dabei|dadurch|damit|daher|hierbei|so|denn|deshalb|" + "|".join(POSSESSIV) + r")\b",
                        re.IGNORECASE)
# Rückverweis in den ersten Wörtern des Folgesatzes („…, hängt daher …“, „dieser Zusammenhang“): inhaltlicher Anschluss
RUECKVERWEIS_RE = re.compile(r"\b(?:da(?:r)?(?:an|auf|aus|bei|durch|für|gegen|hinter|in|mit|nach|neben|über|um|unter|von|vor|zu|zwischen)|"
                             r"daher|deshalb|demnach|dort|hier(?:an|auf|aus|bei|durch|für|in|mit|von|zu)|"
                             r"diese[rsmn]?|solche[rsmn]?)\b", re.IGNORECASE)
AUFZAEHLUNG_RE = re.compile(r"^(?:erstens|zweitens|drittens|viertens|fünftens|zum einen|zum anderen|zum dritten|schließlich|außerdem|"
                            r"hinzu kommt|darüber hinaus|zudem|ferner|weiterhin|auch|ein(?:e[rn]?)? (?:weitere[rsn]?|zweite[rsn]?|dritte[rsn]?))\b",
                            re.IGNORECASE)
# Possessiv, Nomen, finites Verb, dann das Subjekt mit Artikel: der Bezug folgt im selben Satz
KATAPHER_RE = re.compile(r"^\w+\s+[A-ZÄÖÜ][\w-]*\s+[a-zäöüß]\w*\s+(?:ein|eine|einer|der|die|das|dieser|diese|dieses|jede[rs]?)\s+"
                         r"(?:[a-zäöüß]\w*\s+)?[A-ZÄÖÜ]")
AUTORENLISTE_RE = re.compile(r"\b[A-ZÄÖÜ][\w-]+(?:,\s+[A-ZÄÖÜ][\w-]+)+\s+(?:und|&)\s+[A-ZÄÖÜ][\w-]+")
ARTIKEL_NOMEN_RE = re.compile(r"^(?:der|die|das|dieser|diese|dieses|ein|eine)\s+(?:[a-zäöü]\w*\s+)?[A-ZÄÖÜ]")

# Gegenfolie „nicht X, sondern Y“
ADDITIV_RE = re.compile(r"\bnicht\s+(?:nur|allein|bloß|lediglich|mehr\s+nur|einfach\s+nur)\b", re.IGNORECASE)
REDEVERB_RE = re.compile(r"\b(?:zeig\w*|gezeigt|argumentier\w*|beton\w*|weis\w*\s+(?:\S+\s+){0,6}?hin|wies\w*|hingewiesen|hervorheb\w*|"
                         r"hebt\s+(?:\S+\s+){0,4}?hervor|hervorgehoben|kritisier\w*|forder\w*|stell\w*\s+(?:\S+\s+){0,4}?fest|festgestellt|"
                         r"vertritt|vertreten|konstatier\w*|resümier\w*|schlussfolger\w*|folger\w*|schreib\w*|geschrieben|unterstreich\w*)\b",
                         re.IGNORECASE)
NICHT_X_RE = re.compile(r"\b(?:nicht|kein\w*)\s+(?P<x>[^,;]{1,120}?),\s+sondern\b", re.IGNORECASE)
GEGENFOLIE_MUSTER = {"nicht_x_sondern", "nicht_nur_sondern"}

# Funktionswörter: konkrete Konstruktionen (Claude 2,14 / Mensch 0,61 pro 1000 für „lässt/lassen sich“)
LASSEN_SICH_RE = re.compile(r"\b(?:lässt|lassen|ließ|ließen)\s+(?:(?:dabei|daher|so|auch|nicht|kaum|jedoch|somit|damit|hier|nun|also|"
                            r"allerdings|zudem|aber|gut|leicht)\s+)?sich\b|\bsich\s+(?:\S+\s+){0,2}?[a-zäöüß]\w*(?:en|ern|eln)\s+(?:lässt|lassen|ließ|ließen)"
                            r"(?=\s*[,.;:)]|$)")
ZEIGT_SICH_RE = re.compile(r"\b(?:zeigt|zeigen|zeigte|zeigten|ergibt|ergeben|ergab|ergaben)\s+sich\b", re.IGNORECASE)
FW_TECHNIK = {
    "sich": "„sich“-Verb durch ein direktes Verb ersetzen",
    "als": "„als“-Zuschreibung („gilt als“, „dient als“, „erweist sich als“) direkt sagen",
    "sie": "„sie“ durch das Nomen ersetzen",
    "dass": "„dass“-Satz als Nominalgruppe",
    "diese": "„diese“ durch Artikel oder Nomen ersetzen",
}

# Nebensätze mit genau einem Nebensatz, nach Umbaubarkeit sortiert
NEBENSATZ_TYPEN = [
    ("dass", re.compile(r",\s+dass\b"), "den „dass“-Satz als Nominalgruppe fassen (Beispiel: „zeigt, dass die Kosten steigen“ → „zeigt den Anstieg der Kosten“)"),
    ("weil", re.compile(r",\s+(?:weil|da)\b|^(?:Weil|Da)\s"), "den „weil/da“-Satz als Präpositionalgruppe fassen (Beispiel: „da Daten fehlen“ → „wegen fehlender Daten“)"),
    ("relativ", re.compile(r",\s+(?:der|die|das|dem|den|deren|dessen|denen|welche[rsmn]?)\s"),
     "den Relativsatz als vorangestelltes Partizipialattribut fassen (Beispiel: „die Daten, die erhoben wurden“ → „die erhobenen Daten“)"),
    ("sonst", re.compile(r",\s+(?:sodass|so dass|wobei|wodurch|indem|wenn|nachdem|obwohl)\b"),
     "den Nebensatz als Nominal- oder Präpositionalgruppe fassen (Beispiel: „indem Kosten gesenkt werden“ → „durch Kostensenkung“)"),
]
REDEVERB_DASS_RE = re.compile(r"\b(?:zeig\w*|gezeigt|argumentier\w*|beton\w*|hingewiesen|hinweis\w*|weis\w*|wies\w*|feststell\w*|festgestellt|"
                              r"belegt|beleg\w*|nachgewiesen|annehmen|angenommen|vermut\w*|erwart\w*|konstatier\w*|herausgestellt|herausgefunden|"
                              r"schließ\w*|geschlossen|folger\w*|gefolgert|ableit\w*|abgeleitet|"
                              r"darauf|davon|daran|dafür|darüber|dazu|daraus|darin|damit)\b[^.;]*?,\s*(?:dass|ob|wie)\b", re.IGNORECASE)
# nur Adverbialsätze: ein Objektsatz („schließen, dass …“) gehört nicht als Angabe ins Mittelfeld
KLAMMER_QUELLE_RE = re.compile(r",\s+(?P<w>um|indem|ohne|weil|da|wenn|nachdem|bevor|sobald|während|obwohl|sodass|wodurch|womit)\b")
ANGABE_ANFANG = analyse.PRAEPOSITIONEN | {"im", "am", "beim", "vom", "zum", "zur", "ins", "seit", "bis", "während", "dort", "hier", "damals",
                                          "heute", "zuletzt", "zuvor", "anschließend", "danach", "inzwischen", "bereits", "erst"}

# Teilen an einer inhaltlichen Wende: Semikolon, Doppelpunkt vor Großschreibung, Komma vor Konjunktion oder Relativpronomen
_TEIL_KONJ = r"(?:sondern|aber|doch|jedoch|wobei|sodass|so dass|während|weil|da|denn|womit|wodurch|weshalb|wenngleich|obwohl|und|oder|indem|nachdem|wenn)"
TEIL_RE = re.compile(rf";\s+|:\s+(?=[A-ZÄÖÜ])|,\s+(?={_TEIL_KONJ}\b)|,\s+(?=(?:der|die|das|dem|den|deren|dessen|denen|welche[rsmn]?)\s)")
SCHLUSS_RE = re.compile(r"\b(?:daher|deshalb|somit|folglich|also|sodass|so dass|weshalb|insofern)\b", re.IGNORECASE)

# Synonym-Gruppen häufiger Hochschul-Synonyme; „kopf“ = nur als Grundwort eines Kompositums mit gleichem Bestimmungswort
SYNONYM_GRUPPEN = [  # (Wort: Stammformen), nur_kompositum
    ({"Kunde": ("kunde",), "Konsument": ("konsument",), "Verbraucher": ("verbraucher",), "Käufer": ("käufer",)}, False),
    ({"Unternehmen": ("unternehmen",), "Firma": ("firma", "firmen"), "Betrieb": ("betrieb",)}, False),
    ({"Mitarbeiter": ("mitarbeiter",), "Beschäftigte": ("beschäftigte",), "Arbeitnehmer": ("arbeitnehmer",),
      "Angestellte": ("angestellte",)}, False),
    ({"Studie": ("studie",), "Untersuchung": ("untersuchung",), "Erhebung": ("erhebung",)}, False),
    ({"Führungskraft": ("führungskraft", "führungskräfte"), "Vorgesetzte": ("vorgesetzte",), "Manager": ("manager",)}, False),
    ({"Wirkung": ("wirkung",), "Effekt": ("effekt",), "Einfluss": ("einfluss", "einflüsse")}, False),
    ({"Vorteil": ("vorteil",), "Nutzen": ("nutzen",), "Mehrwert": ("mehrwert",)}, False),
    ({"Strategie": ("strategie",), "Konzept": ("konzept",), "Ansatz": ("ansatz", "ansätze")}, False),
    ({"Setzung": ("setzung",), "Gestaltung": ("gestaltung",), "Bildung": ("bildung",), "Findung": ("findung",),
      "Festlegung": ("festlegung",)}, True),  # Preissetzung / Preisgestaltung
]
_FLEXION = ("", "e", "en", "n", "s", "es", "er", "ern", "nen")
# Verbpartikeln/-präfixe sind kein gemeinsames Bestimmungswort: „Ausbildung“ ≠ „Ausgestaltung“, „Fortbildung“ ≠ „Fortsetzung“
_PARTIKEL_PRAEFIX = set("""ab an auf aus bei dar durch ein fest fort frei her heraus hervor hin hinaus hoch mit nach neu nieder vor voraus
vorbei weg weiter wieder zu zurück zusammen um über unter ver be er ent zer ge miss wider hinter gegen entgegen""".split())

MASKE = "▒"
OEFFNER = {"„": "“”", "»": "«", "«": "»", "“": "”", '"': '"'}
QUELLE_KLAMMER_RE = re.compile(r"\((?=[^()]*(?:\bvgl\.|\bebd\.?|\bebenda\b|\bzit\.|\bHrsg\.|\bS\.\s?\d|§|\bAbs\.|\bArt\.\s?\d|\b(?:1[6-9]|20)\d{2}\b))[^()]*\)")
QMARK = "⁣"  # unsichtbarer Platzhalter für entfernte Quellenverweise (Quellen-Zuordnung je Satz)

# Überkorrektur-Wächter: Kennzahl -> {Seite der Verschiebung: Hinweistypen, die ausgesetzt werden}
_VERDICHTEN = {"buendeln", "klammer", "klammer_zusatz", "nebensatz"}
_BEGRIFFE = {"anknuepfung", "kein_bezug", "synonyme"}
WAECHTER = {
    "satzlaenge_mittel": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen", "kurz"}},
    "satzlaenge_median": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen", "kurz"}},
    "anteil_lange_saetze": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen"}},
    "anteil_sehr_lange_saetze": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen"}},
    "anteil_mittlere_saetze": {"gegen": {"buendeln", "kurz", "klammer_zusatz"}, "ki": {"teilen"}},
    "anteil_kurze_saetze": {"gegen": {"buendeln", "klammer", "klammer_zusatz"}, "ki": {"kurz", "teilen"}},
    "satzlaenge_schiefe": {"gegen": {"kurz"}, "ki": {"buendeln"}},
    "rhythmus_r1_log": {"gegen": {"zickzack"}, "ki": {"buendeln"}},
    "lix": {"gegen": _VERDICHTEN, "ki": {"teilen", "kurz"}},
    "wiener_sachtextformel": {"gegen": _VERDICHTEN, "ki": {"teilen", "kurz"}},
    "flesch_amstad": {"gegen": _VERDICHTEN, "ki": {"teilen", "kurz"}},
    "nominalstil_pro_100": {"gegen": _VERDICHTEN},
    "hedging_pro_1000": {"gegen": {"floskel", "konnektor"}},
    "anteil_saetze_mit_wortaufnahme": {"gegen": _BEGRIFFE},
    "nachbarsatz_ueberlappung": {"gegen": _BEGRIFFE},
    "satzanfang_wiederholung": {"gegen": {"anknuepfung", "kein_bezug"}},
    "woerter_pro_teilsatz": {"gegen": {"nebensatz", "kommas", "klammer", "klammer_zusatz"}},
    "teilsatz_verhaeltnis_21": {"gegen": {"nebensatz", "kommas"}, "ki": {"buendeln"}},
    "anteil_saetze_mit_nebensatz": {"gegen": {"nebensatz", "kommas"}, "ki": {"buendeln"}},
    "konnektoren_pro_1000": {"gegen": {"konnektor"}},
    "saetze_pro_absatz": {"gegen": {"absatz_teilen"}, "ki": {"absatz_zusammen"}},
    "absatzlaenge_mittel": {"gegen": {"absatz_teilen"}, "ki": {"absatz_zusammen"}},
    "anteil_einsatz_absaetze": {None: {"absatz_teilen"}, "gegen": {"absatz_teilen"}},
}
TYP_NAME = {"buendeln": "Bündeln", "teilen": "Teilen", "kurz": "kurze Sätze", "zickzack": "Zickzack-Hinweise", "klammer": "Satzklammer",
            "klammer_zusatz": "Angaben aus dem Folgesatz holen", "nebensatz": "Nebensatz → Nominalgruppe", "kommas": "Komma-Hinweise",
            "anknuepfung": "Anknüpfung", "kein_bezug": "Begriffsaufnahme", "synonyme": "Synonym-Hinweise", "floskel": "Floskeln",
            "konnektor": "Konnektoren", "absatz_teilen": "Absatz teilen", "absatz_zusammen": "Absätze zusammenlegen",
            "gegenfolie": "Gegenfolie"}
# „zickzack“ verlangt „Satz X mit X+1 verbinden“ und zählt deshalb wie Bündeln
GEGENTEIL = {"buendeln": {"teilen", "kurz", "kommas"}, "teilen": {"buendeln", "klammer_zusatz", "zickzack"}, "kurz": {"buendeln", "zickzack"},
             "klammer_zusatz": {"teilen"}, "kommas": {"buendeln", "zickzack"}, "zickzack": {"teilen", "kurz", "kommas"},
             "absatz_teilen": {"absatz_zusammen"}, "absatz_zusammen": {"absatz_teilen"}}
ZIEL_TYPEN = {"gender", "gedankenstrich", "semikolon", "floskel"}  # bei „Ziel erreicht“ (Muster nur mit Gewicht ≥ 1,5)
ZIEL_MAX = 5


def anfang(text: str, n: int = 7) -> str:
    w = text.split()
    return " ".join(w[:n]) + (" …" if len(w) > n else "")


def zitat(s: dict) -> str:
    return f"Satz {s['nr']} („{anfang(s['text'])}“)"


def schluessel_anfang(text: str) -> str:
    """Wiedererkennung eines Satzes über Runden: die ersten sechs Token, klein."""
    return " ".join(t.lower() for t in analyse.tokens(text)[:6])


def abstand(z: dict) -> float:
    """Wie weit liegt eine Kennzahl außerhalb des Zielbereichs, in Einheiten des Interquartilsabstands."""
    iqr = z["mensch_p75"] - z["mensch_p25"]
    if iqr <= 0:  # z. B. Semikolons: P25 = P75 = 0 – dann die halbe 10–90-Spanne als Maßstab
        iqr = max(1e-9, (z["mensch_p90"] - z["mensch_p10"]) / 2, 0.25 * abs(z["mensch_p50"]) or 1e-9)
    if z["wert"] < z["mensch_p25"]:
        return min(3.0, (z["mensch_p25"] - z["wert"]) / iqr)
    if z["wert"] > z["mensch_p75"]:
        return min(3.0, (z["wert"] - z["mensch_p75"]) / iqr)
    return 0.0


def band_abstand(wert: float, r: dict) -> float:
    """Abstand zum grünen Bereich P25–P75 in Interquartilsabständen (0 = im Bereich)."""
    m = r["mensch"]
    iqr = (m["p75"] - m["p25"]) or ((m["p90"] - m["p10"]) / 2) or 1e-9
    if wert < m["p25"]:
        return (m["p25"] - wert) / iqr
    if wert > m["p75"]:
        return (wert - m["p75"]) / iqr
    return 0.0


def status_von(wert: float, r: dict) -> str:
    m = r["mensch"]
    if m["p25"] <= wert <= m["p75"]:
        return "gruen"
    if m["p10"] <= wert <= m["p90"]:
        return "gelb"
    return "rot"


def seite_von(wert: float, r: dict) -> str | None:
    """'ki', wenn der Wert vom menschlichen Median aus auf der Seite des KI-Medians liegt, 'gegen' auf der anderen Seite."""
    p50 = r["mensch"]["p50"]
    ki = (r.get("ki") or {}).get("p50")
    if ki is None or ki == p50 or wert == p50:
        return None
    return "ki" if (wert - p50) * (ki - p50) > 0 else "gegen"


def klammer_details(satz_text: str) -> list[tuple[int, str, str]]:
    """(Spanne, Hilfsverb, Klammerende) je Teilsatz: Wörter zwischen finitem Hilfsverb und Partizip/Infinitiv (HW08)."""
    out = []
    for teil in re.split(r"[,;:()–—]", satz_text):
        tw = [t for t in analyse.tokens(teil) if analyse.ist_wort(t)]
        aux = next((i for i, t in enumerate(tw) if t.lower() in HILFSVERBEN), None)
        if aux is None:
            continue
        j = len(tw) - 1
        while j > aux and tw[j].lower() in KLAMMER_ENDE_HILFS:
            j -= 1
        w = tw[j] if tw else ""
        if j - aux >= 2 and w[:1].islower() and len(w) >= 4 and w.lower() not in analyse.FUNKTIONSWOERTER \
                and w.lower() not in HILFSVERBEN and re.search(r"(en|t|iert|ert|elt)$", w):
            out.append((j - aux - 1, tw[aux], w))
    return out


def klammer_spannen(satz_text: str) -> list[int]:
    """Satzklammer-Spannen eines Satzes, wie in analyse.py (HW08)."""
    return [d[0] for d in klammer_details(satz_text)]


def klasse_zz(laenge: int) -> str:
    return "k" if laenge <= ZZ_KURZ_MAX else ("l" if laenge >= ZZ_LANG_AB else "m")


def zickzack(laengen: list[int]) -> list[tuple[int, int]]:
    """Bereiche (von, bis; 0-basiert, einschließlich) mit mindestens 5 Sätzen, die streng zwischen kurz (≤ 15 Wörter)
    und lang (≥ 25 Wörter) wechseln. Ein mittellanger Satz oder zwei gleiche Klassen beenden den Bereich; der nächste
    beginnt erst beim folgenden Satz (keine Überlappung)."""
    bereiche, start = [], None
    for i, l in enumerate(laengen):
        k = klasse_zz(l)
        if k == "m":
            if start is not None and i - start >= 5:
                bereiche.append((start, i - 1))
            start = None
            continue
        if start is None:
            start = i
        elif k == klasse_zz(laengen[i - 1]):
            if i - start >= 5:
                bereiche.append((start, i - 1))
            start = i
    if start is not None and len(laengen) - start >= 5:
        bereiche.append((start, len(laengen) - 1))
    return bereiche


def mechanisch_verlaengert(vorher: dict, jetzt: dict) -> bool:
    """Plausibilitätsregel: Ø-Satzlänge +10 %, aber weder Wörter pro Teilsatz noch Satzklammer-Spanne gestiegen."""
    if not vorher.get("satzlaenge_mittel") or not jetzt.get("satzlaenge_mittel"):
        return False
    if jetzt["satzlaenge_mittel"] <= 1.1 * vorher["satzlaenge_mittel"]:
        return False
    return not any(vorher.get(k) is not None and jetzt.get(k) is not None and jetzt[k] > vorher[k]
                   for k in ("woerter_pro_teilsatz", "satzklammer_mittel"))


# ---------------------------------------------------------------------------
# Zitate und Quellen
# ---------------------------------------------------------------------------

def zitat_masken(saetze: list[dict]) -> dict[int, str]:
    """Satztext mit maskierten wörtlichen Zitaten („…“, "…", »…«) und Klammern mit Quellenangabe (gleiche Länge).

    Zitate dürfen über Satzgrenzen innerhalb eines Absatzes reichen. Ein nie geschlossenes „ bzw. » gilt bis zum
    Satzende; ein nie geschlossenes “ oder " ist vermutlich ein einzelnes Zeichen und wird nicht maskiert."""
    masken: dict[int, str] = {}
    absaetze: dict[int, list[dict]] = {}
    for s in saetze:
        absaetze.setdefault(s["absatz"], []).append(s)
    for liste in absaetze.values():
        text, grenzen, pos = "", [], 0
        for s in liste:
            grenzen.append((pos, pos + len(s["text"])))
            text += s["text"] + "\n"
            pos = len(text)
        spannen, offen, start, art = [], None, 0, ""
        for i, ch in enumerate(text):
            if offen is None:
                if ch in OEFFNER:
                    offen, start, art = OEFFNER[ch], i, ch
            elif ch in offen:
                spannen.append((start, i + 1))
                offen = None
        if offen is not None and art in "„»«":
            ende = next((e for a, e in grenzen if a <= start < e), len(text))
            spannen.append((start, ende))
        zeichen = list(text)
        for a, e in spannen:
            for i in range(a, e):
                if zeichen[i] != "\n":
                    zeichen[i] = MASKE
        maske = "".join(zeichen)
        for s, (a, e) in zip(liste, grenzen):
            m = maske[a:e]
            masken[s["nr"]] = QUELLE_KLAMMER_RE.sub(lambda x: MASKE * len(x.group(0)), m)
    return masken


def quellen_flags(text: str, saetze: list[dict]) -> tuple[dict[int, bool], dict[int, bool]]:
    """Je Satz: trägt er einen (für die Messung entfernten) Quellenverweis bzw. beginnt er mit einer Autorenangabe?

    Die Absätze werden wie in analyse.py bereinigt, nur dass Quellenverweise einen unsichtbaren Platzhalter
    hinterlassen. Stimmen die Sätze danach nicht mit der Analyse überein, bleibt der Absatz ohne Markierung."""
    quelle: dict[int, bool] = {}
    autor: dict[int, bool] = {}
    try:
        struktur = analyse.zerlege_bloecke(text)
    except Exception:  # noqa: BLE001 – Zusatzinformation, nie Abbruchgrund
        return quelle, autor
    nach_absatz: dict[int, list[dict]] = {}
    for s in saetze:
        nach_absatz.setdefault(s["absatz"], []).append(s)
    nr_abs = 0
    for roh in struktur["absaetze"]:
        sauber = analyse.zerlege_saetze(analyse.bereinige_absatz(roh, Counter()))
        if not sauber:
            continue
        nr_abs += 1
        markiert = analyse.ZITAT_RE.sub(QMARK, roh)
        markiert = analyse.NUM_BELEG_RE.sub(QMARK, markiert)
        markiert = analyse.FUSSNOTE_RE.sub(QMARK, markiert)
        markiert = re.sub(r"([.!?…])(⁣+)", r"\2\1", markiert)
        m_saetze = analyse.zerlege_saetze(analyse.bereinige_absatz(markiert, Counter()))
        liste = nach_absatz.get(nr_abs, [])
        if len(m_saetze) != len(liste):
            continue
        for s, m in zip(liste, m_saetze):
            if re.sub(r"\s+", " ", m.replace(QMARK, "")).strip() != s["text"]:
                continue
            q = QMARK in m
            quelle[s["nr"]] = q or bool(re.search(r"\bet al\.", s["text"]))
            vorne = m[:m.index(QMARK)] if q else ""
            autor[s["nr"]] = (q and len(analyse.tokens(vorne)) <= 8) or bool(re.search(r"\bet al\.", " ".join(s["text"].split()[:6])))
    return quelle, autor


# ---------------------------------------------------------------------------
# Begriffe
# ---------------------------------------------------------------------------

def _grund(w: str) -> str:
    w = w.lower()
    for e in ("ungen", "ung", "heiten", "keiten", "heit", "keit", "ern", "en", "er", "es", "em", "e", "n", "s"):
        if len(w) - len(e) >= 4 and w.endswith(e):
            return w[:-len(e)]
    return w


_INITIALEN_FUELL = {"und", "and", "of", "for", "the", "für", "der", "die", "das", "des", "von", "zur", "zum"}


def satz_begriffe(text: str) -> dict:
    """Inhaltsstämme, Kompositum-Grundformen, Akronyme und Initialen eines Satzes (für die Bezugsprüfung)."""
    toks = analyse.tokens(text)
    worte = [w for w in toks if analyse.ist_wort(w) and w.lower() not in analyse.FUNKTIONSWOERTER and len(w) > 2]
    folge = [w for w in toks if analyse.ist_wort(w) and w.lower() not in _INITIALEN_FUELL]
    initialen = set()
    for i in range(len(folge)):
        for j in range(i + 2, min(len(folge), i + 6) + 1):
            initialen.add("".join(x[0] for x in folge[i:j]).upper())
    return {"staemme": analyse.inhaltsstaemme(toks), "grund": {_grund(w) for w in worte if len(w) >= 5},
            "roh": {w.lower() for w in worte if len(w) >= 5},
            "akronyme": {w.rstrip("s") for w in toks if re.fullmatch(r"[A-ZÄÖÜ]{2,6}s?", w)}, "initialen": initialen}


def verbunden(a: dict, b: dict) -> str | None:
    """Teilen zwei Sätze einen Begriff – direkt, als Kompositum (Grundwort ≥ 5 Zeichen als Suffix des anderen oder
    gemeinsames Präfix ≥ 6) oder als Akronym und Langform?"""
    if a["staemme"] & b["staemme"]:
        return "stamm"
    for x in a["grund"]:
        for y in b["grund"]:
            if min(len(x), len(y)) >= 5 and (x.endswith(y) or y.endswith(x)):
                return "kompositum"  # gleiches Grundwort („Berichterstattung“ – „Nachhaltigkeitsberichterstattung“)
            if len(x) >= 6 and len(y) >= 6 and x[:6] == y[:6]:
                return "kompositum"
    for x in a.get("roh", ()):
        for y in b.get("roh", ()):
            if x != y and (x.startswith(y) or y.startswith(x)):
                return "kompositum"  # Bestimmungswort („Preis“ – „Preissetzung“)
    if (b["akronyme"] & a["initialen"]) or (a["akronyme"] & b["initialen"]):
        return "akronym"
    return None


_ADVERB_ANFANG = set("""näher oft häufig meist meistens zuerst zunächst erst insgesamt außerdem schließlich letztlich folglich deshalb
daher damit dabei hierbei zudem ebenso gleichzeitig zugleich allerdings jedoch dennoch trotzdem vielmehr insbesondere besonders
gerade bereits schon auch nur noch weiter ferner ähnlich anders genauer konkret kurz grundsätzlich eigentlich tatsächlich
vermutlich offenbar offensichtlich angesichts aufgrund anhand mithilfe mittels bezüglich hinsichtlich statt anstatt laut gemäß
seit während wegen trotz nämlich somit demnach umgekehrt andererseits einerseits zusätzlich ebenfalls hingegen dagegen""".split())


def kein_nomen_am_anfang(wort: str) -> bool:
    """Großgeschriebenes Satzanfangswort, das sehr wahrscheinlich kein Nomen ist (Adverb, Adjektiv, Präposition)."""
    low = wort.lower()
    return low in _ADVERB_ANFANG or len(low) < 4 or bool(re.search(r"(?:lich|weise|mal|ig|isch|bar|sam|los|end|ens)$", low))


_GROSS_FOLGE_RE = re.compile(r"(?<![\w-])[A-ZÄÖÜ][\w-]*(?: [A-ZÄÖÜ][\w-]*){0,3}")


def bezugsausdruecke(text: str, n: int = 3) -> list[str]:
    """Kandidaten für den Bezugsausdruck eines Satzes in Textreihenfolge (Subjekt bzw. erstes Nomen im Vorfeld zuerst):
    Nomen bzw. direkt aufeinanderfolgende großgeschriebene Wörter (Eigennamen wie „Europäische Union“), ohne
    Funktionswörter, Gender-Partizipien und leichte Nomen („Jahr“, „Rahmen“ …). Nie nach Länge ausgewählt."""
    out: list[str] = []
    beginn = len(text) - len(text.lstrip("„\"(»"))
    for m in _GROSS_FOLGE_RE.finditer(text):
        worte = m.group(0).split()
        while worte and (worte[0].lower() in analyse.FUNKTIONSWOERTER or worte[0].lower() in analyse.STARTWOERTER
                         or (m.start() == beginn and kein_nomen_am_anfang(worte[0]))):
            worte.pop(0)
            beginn = -1
        # Name + Nomen („George Herbert Mead Rollenübernahme“): am ersten typischen Nomen-Ende abschneiden
        for i, w in enumerate(worte[:-1]):
            if re.search(r"(?:ung|heit|keit|schaft|ion|tät|nahme|ismus)(?:en)?$", w.lower()):
                worte = worte[:i + 1]
                break
        worte = [w for w in worte if w.lower() not in LEICHTE_NOMEN and not PARTIZIP_RE.search(w) and len(w) >= 3
                 and w.lower() not in analyse.FUNKTIONSWOERTER and analyse.ist_wort(w)]
        if not worte:
            continue
        phrase = " ".join(worte)
        if phrase not in out:
            out.append(phrase)
        if len(out) >= n:
            break
    return out


_VERGLEICH_VOR_ALS = {"mehr", "weniger", "eher", "anders", "sowohl", "lieber", "früher", "später", "besser", "höher", "niedriger",
                      "größer", "kleiner", "stärker", "schwächer", "länger", "kürzer", "schneller", "geringer", "andere", "anderen"}


def fw_zaehlung(toks: list[str], woerter) -> Counter:
    """KI-seitige Funktionswörter eines Satzes. „als“ nur als Zuschreibung („gilt als“), nicht in „sowohl … als auch“,
    Vergleichen („mehr als“, „höher als“) oder als temporale Konjunktion am Satzanfang."""
    zaehl: Counter = Counter()
    low = [t.lower() for t in toks]
    for i, t in enumerate(low):
        if t not in woerter:
            continue
        if t == "als":
            vor = low[i - 1] if i else ""
            if i == 0 or (i + 1 < len(low) and low[i + 1] == "auch") or vor in _VERGLEICH_VOR_ALS \
                    or (vor.endswith("er") and toks[i - 1][:1].islower()):
                continue
        zaehl[t] += 1
    return zaehl


_PROBE = "xqxq"  # Ersatzwort für die Kopfwort-Probe (wie inhalt_check.PLATZHALTER), passt auf kein Muster
_WORT_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+(?:-[A-Za-zÄÖÜäöüß]+)*")


def floskel_kopfwoerter(satz: str, start: int, ende: int, rx: re.Pattern) -> list[str]:
    """Auslöser-Wörter eines Mustertreffers satz[start:ende]: Wörter, ohne die der Treffer verschwindet
    („maßgeblich“, „zentrale Rolle zukommen“). Platzhalter des Musters („sowohl die Kostenstruktur … als auch“,
    „nicht X, sondern“) bleiben draußen – sie sind Inhalt, kein Ersetzungsvorschlag (Vereinbarung mit inhalt_check)."""
    out = []
    for w in _WORT_RE.finditer(satz, start, ende):
        d = len(_PROBE) - (w.end() - w.start())
        probe = satz[:w.start()] + _PROBE + satz[w.end():]
        if not any(x.start() < ende + d and x.end() > start for x in rx.finditer(probe)):
            out.append(w.group(0))
    return out


def ist_kapselwort(nomen: str) -> bool:
    low = nomen.lower()
    for e in ("en", "n", "e", "s", ""):
        stamm = low[:-len(e)] if e and low.endswith(e) else low
        if any(stamm.endswith(k) for k in KAPSELWOERTER):
            return True
    return False


def personen_anfang(text: str) -> bool:
    """Beginnt der Satz mit Personen (Autoren, Befragte …) – dann ist „Sie/Er“ im Folgesatz eindeutig genug."""
    toks = [t for t in analyse.tokens(text)[:5] if analyse.ist_wort(t)]
    if not toks:
        return False
    if re.match(r"(?:Prof|Dr)\.", text.lstrip("„\"(»")):
        return True
    if len(toks) >= 3 and toks[1].lower() in ("und", "&") and toks[0][:1].isupper() and toks[2][:1].isupper() \
            and toks[0].lower() not in analyse.FUNKTIONSWOERTER:
        return True  # „Ambler und Barrow definieren …“
    for t in toks[:4]:
        low = t.lower()
        if t[:1].isupper() and low not in analyse.FUNKTIONSWOERTER:
            return any(low == p or low.endswith(p) for p in PERSONEN)
    return False


def synonym_cluster(saetze: list[dict], masken: dict[int, str]) -> list[dict]:
    """Wortgruppen, die im Text für dieselbe Sache wechseln: Synonyme aus SYNONYM_GRUPPEN, allein oder als Grundwort
    eines Kompositums mit gleichem Bestimmungswort (Preissetzung/Preisgestaltung)."""
    funde: dict[tuple, Counter] = {}
    for s in saetze:
        for t in analyse.tokens(masken.get(s["nr"], s["text"])):
            if not (analyse.ist_wort(t) and t[:1].isupper() and len(t) >= 4):
                continue
            low = t.lower()
            for gi, (gruppe, nur_kopf) in enumerate(SYNONYM_GRUPPEN):
                treffer = None
                for lemma, formen in gruppe.items():
                    for g in formen:
                        for fl in _FLEXION:
                            if low.endswith(g + fl):
                                praefix = low[:len(low) - len(g) - len(fl)]
                                if (praefix and len(praefix) < 3) or (nur_kopf and (not praefix or praefix in _PARTIKEL_PRAEFIX)):
                                    continue
                                treffer = (praefix.rstrip("s-") if praefix.endswith(("s", "-")) and len(praefix) > 4 else praefix, lemma)
                                break
                        if treffer:
                            break
                    if treffer:
                        break
                if treffer:
                    funde.setdefault((gi, treffer[0]), Counter())[(treffer[1], t)] += 1
                    break
    cluster = []
    for (gi, praefix), zaehl in funde.items():
        koepfe: dict[str, Counter] = {}
        for (g, form), n in zaehl.items():
            koepfe.setdefault(g, Counter())[form] += n
        if len(koepfe) < 2 or sum(zaehl.values()) < 4:
            continue  # mindestens zwei Varianten und vier Vorkommen
        varianten = sorted(((c.most_common(1)[0][0], sum(c.values())) for c in koepfe.values()), key=lambda v: -v[1])
        cluster.append({"varianten": varianten, "formen": sorted({form.lower() for (_, form) in zaehl}), "anzahl": sum(zaehl.values())})
    return sorted(cluster, key=lambda c: -c["anzahl"])


# ---------------------------------------------------------------------------
# Satzlängen
# ---------------------------------------------------------------------------

def _l1(vert: dict, ziel: dict) -> float:
    return sum(abs(vert.get(k, 0.0) - ziel.get(k, 0.0)) for k in ziel)


def laengen_guete(laengen: list[int], ref: dict, ziel: dict) -> tuple[float, float, float]:
    """(L1-Abstand der Klassenverteilung zur menschlichen, Abstand Schiefe zum grünen Bereich, Abstand CV)."""
    l1 = _l1(analyse.verteilung(laengen), ziel) if ziel else 0.0
    sch = band_abstand(analyse.schiefe(laengen), ref["satzlaenge_schiefe"]) if "satzlaenge_schiefe" in ref else 0.0
    cvw = band_abstand(analyse.cv(laengen), ref["satzlaenge_cv"]) if "satzlaenge_cv" in ref else 0.0
    return l1, sch, cvw


def teilstelle(text: str, maske: str) -> tuple[int, int, int, str] | None:
    """Beste Stelle, um einen Satz an einer inhaltlichen Wende zu teilen: (Position, Wörter links, Wörter rechts,
    Kontext). Beide Teile ≥ 8 Wörter, nicht in einem Zitat, möglichst in der Mitte."""
    beste = None
    for m in TEIL_RE.finditer(maske):
        links, rechts = text[:m.start()], text[m.end():]
        nl, nr = len(analyse.tokens(links)), len(analyse.tokens(rechts))
        if nl < 8 or nr < 8:
            continue
        guete = abs(nl - nr) - (4 if m.group(0).startswith(";") else 0)
        if beste is None or guete < beste[0]:
            vor = " ".join(links.split()[-2:])
            nach = " ".join(rechts.split()[:2])
            beste = (guete, m.start(), nl, nr, f"{vor}{m.group(0).rstrip()} {nach}")
    return beste[1:] if beste else None


def satzlaengen_diagnose(fokus: list[dict], ref: dict, ziel: dict, schiefe_wert: float | None) -> dict:
    """Klassenverteilung, Anteile und Modus (bündeln / teilen / –) der Satzlängen im Fokus."""
    L = [s["woerter"] for s in fokus]
    n = len(L) or 1
    d = {"n": len(L), "lange": sum(x >= LANG_AB for x in L), "sehr_lange": sum(x >= SEHR_LANG_AB for x in L),
         "mittlere": sum(MITTEL_VON <= x <= MITTEL_BIS for x in L), "kurze": sum(x <= KURZ_MAX for x in L),
         "woerter": sum(L), "mittel": (sum(L) / n) if L else 0.0}
    d["anteil_lange"], d["anteil_mittlere"], d["anteil_kurze"] = d["lange"] / n, d["mittlere"] / n, d["kurze"] / n
    d["schiefe"] = schiefe_wert if schiefe_wert is not None else analyse.schiefe(L)
    d["verteilung"] = analyse.verteilung(L)
    d["l1"] = _l1(d["verteilung"], ziel) if ziel else None
    d["abweichungen"] = sorted(((k, d["verteilung"].get(k, 0.0), v) for k, v in ziel.items()), key=lambda x: -abs(x[1] - x[2]))[:2] if ziel else []
    d["modus"], d["kontingent"], d["gruende"], d["fehlende_mitte"] = None, 0, [], False
    p = lambda k, q: ref[k]["mensch"][q] if k in ref else None  # noqa: E731
    if not L or p("anteil_lange_saetze", "p50") is None:
        return d
    lang50, lang75 = p("anteil_lange_saetze", "p50"), p("anteil_lange_saetze", "p75")
    mittl25, mittl50 = p("anteil_mittlere_saetze", "p25"), p("anteil_mittlere_saetze", "p50")
    sl50, sl75 = p("satzlaenge_mittel", "p50"), p("satzlaenge_mittel", "p75")
    if d["anteil_lange"] > lang75:
        d["gruende"].append(f"{d['lange']} von {d['n']} Sätzen haben ≥ {LANG_AB} Wörter ({_pz(d['anteil_lange'])}, Menschen meist {_pz(lang50)}–{_pz(lang75)})")
    if sl75 is not None and d["mittel"] > sl75:
        d["gruende"].append(f"Ø {fmt(round(d['mittel'], 1))} Wörter pro Satz (Menschen meist {fmt(round(p('satzlaenge_mittel', 'p25'), 1))}–{fmt(round(sl75, 1))})")
    fehlende_mitte = d["anteil_mittlere"] < mittl25 and d["anteil_lange"] >= lang50
    d["fehlende_mitte"] = fehlende_mitte
    if fehlende_mitte:
        d["gruende"].append(f"nur {_pz(d['anteil_mittlere'])} mittellange Sätze ({MITTEL_VON}–{MITTEL_BIS} Wörter; Menschen meist ≥ {_pz(mittl25)})")
    if d["gruende"]:
        d["modus"] = "teilen"
        k = 0
        if d["anteil_lange"] > lang75:
            k = max(k, d["lange"] - round(lang50 * d["n"]))
        if sl75 is not None and d["mittel"] > sl75:
            k = max(k, math.ceil(d["woerter"] / sl50 - d["n"]))
        if fehlende_mitte:
            k = max(k, math.ceil((mittl50 * d["n"] - d["mittlere"]) / 2))
        d["kontingent"] = max(1, min(MAX_TEILEN, k))
    elif d["anteil_lange"] < lang50 and d["anteil_mittlere"] > mittl50:
        d["modus"] = "buendeln"
        d["kontingent"] = max(0, round(lang50 * d["n"]) - d["lange"])
    return d


def _pz(x: float) -> str:
    return f"{round(100 * x)} %"


# ---------------------------------------------------------------------------
# Coach
# ---------------------------------------------------------------------------

def coache(text: str, verlauf: dict | None = None, max_hinweise: int = 15, roh: bool = False) -> dict:
    """Misst den Text und erzeugt priorisierte, satzgenaue Hinweise. roh=True liefert zusätzlich 'hinweise_roh'
    (alle Hinweise vor der Auswahl und vor dem Filter bei „Ziel erreicht“, für Auswertungen)."""
    muster = analyse.lade_muster()
    baselines = analyse.lade_baselines()
    ts = (baselines or {}).get("textsorten", {}).get("hochschule", {})
    ref = ts.get("metriken", {})
    if hasattr(analyse, "analysiere_und_bewerte"):
        erg, bew = analyse.analysiere_und_bewerte(text, muster, baselines)
    else:
        fw_profil = ts.get("fw_profil")
        erg = analyse.analysiere_text(text, muster, fw_profil=fw_profil) if fw_profil else analyse.analysiere_text(text, muster)
        bew = analyse.bewerte(erg, baselines)
    saetze = erg["saetze"]
    m = erg["metriken"]
    kz = {z["id"]: dict(z, seite=seite_von(z["wert"], ref[z["id"]]) if z["id"] in ref else None) for z in bew.get("kennzahlen", [])}

    def ki_auffaellig(id_: str, nur_rot: bool = False) -> bool:
        """Zielkennzahl auf der KI-Seite außerhalb des grünen Bereichs (gelb an der Grenze der Messunsicherheit zählt nicht)."""
        z = kz.get(id_)
        if not z or z["status"] == "gruen" or z["seite"] != "ki":
            return False
        if nur_rot:
            return z["status"] == "rot"
        return not (z["status"] == "gelb" and z.get("unsicher"))

    def p_(id_: str, q: str):
        return ref[id_]["mensch"][q] if id_ in ref else None

    # --- Hebel priorisieren (Medianvektor) --------------------------------
    hebel: dict[str, dict] = {}
    if bew.get("verfuegbar"):
        # Modellbeitrag (koef · Abstand zum menschlichen Median, negativ = zieht Richtung KI)
        for z in bew["kennzahlen"]:
            b = z.get("beitrag")
            h = HEBEL_VON.get(z["id"])
            if h and b is not None and b < -0.25 and (z["status"] != "gruen" or z.get("nur_modell")) and kz[z["id"]]["seite"] != "gegen":
                eintrag = hebel.setdefault(h, {"prioritaet": 0.0, "kennzahlen": []})
                eintrag["prioritaet"] += 0.5 * -b
                eintrag["kennzahlen"].append(z)
        for z in bew["kennzahlen"]:
            if not z["bewertet"] or z["status"] == "gruen":
                continue
            if z["status"] == "gelb" and z.get("unsicher"):
                continue  # gelb, aber innerhalb der Messunsicherheit an der Grenze: kein Arbeitsauftrag
            if kz[z["id"]]["seite"] != "ki":
                continue  # Abweichungen weg von der KI-Seite sind kein Arbeitsauftrag
            h = HEBEL_VON.get(z["id"])
            if not h:
                continue
            eintrag = hebel.setdefault(h, {"prioritaet": 0.0, "kennzahlen": []})
            eintrag["prioritaet"] += (z["gewicht"] or 0.1) * (0.5 + abstand(z))
            if z not in eintrag["kennzahlen"]:
                eintrag["kennzahlen"].append(z)

    # --- Fokus: im Blockmodus nur der schwächste Block ---------------------
    bloecke = bew.get("bloecke") or []
    fokus_block = None
    if bew.get("blockmodus") and len(bloecke) > 1:
        fokus_block = min(bloecke, key=lambda b: (b["p_mensch"] if b.get("p_mensch") is not None else 2.0,
                                                  b["score"] if b.get("score") is not None else 101))
        von, bis = fokus_block["satz_von"], fokus_block["satz_bis"]
    else:
        von, bis = 1, len(saetze)
    fokus = [s for s in saetze if von <= s["nr"] <= bis]
    nach_nr = {s["nr"]: s for s in saetze}
    absaetze: dict[int, list[dict]] = {}
    for s in fokus:
        absaetze.setdefault(s["absatz"], []).append(s)
    masken = zitat_masken(saetze)
    quelle, autor = quellen_flags(text, saetze)
    begriffe_info = {s["nr"]: satz_begriffe(s["text"]) for s in saetze}
    tok_fokus = sum(len(analyse.tokens(s["text"])) for s in fokus) or 1

    def nutzbar(s: dict) -> bool:
        """Satz bekommt Hinweise: kein Fragment, nicht ganz im Zitat."""
        return s["woerter"] >= MIN_WOERTER and bool(re.search(r"[A-Za-zÄÖÜäöüß]", masken.get(s["nr"], s["text"])))

    def langes_zitat(s: dict) -> bool:
        return len(analyse.tokens(s["text"])) - len(analyse.tokens(masken.get(s["nr"], s["text"]))) >= 4

    def beginnt_im_zitat(s: dict) -> bool:
        """Satzanfang liegt in einem wörtlichen Zitat: Anfangswörter dürfen nicht geändert werden."""
        return masken.get(s["nr"], s["text"]).lstrip().startswith(MASKE)

    # --- Verlauf: Überkorrektur-Wächter und Hinweis-Gedächtnis ----------------
    vorher = (verlauf or {}).get("messungen", [])[-1] if verlauf and verlauf.get("messungen") else None
    roh_jetzt = {k: m.get(k) for k in set(WAECHTER) | {"satzlaenge_mittel", "woerter_pro_teilsatz", "satzklammer_mittel"}}
    if bew.get("blockmodus"):
        for k in roh_jetzt:
            if kz.get(k):
                roh_jetzt[k] = kz[k]["wert"]
    ueberkorrektur, ausgesetzt = [], set()
    if vorher:
        def werte_aus(mess: dict) -> dict:
            return {**{k: v.get("wert") for k, v in (mess.get("kennzahlen") or {}).items() if isinstance(v, dict)},
                    **{k: v for k, v in (mess.get("roh") or {}).items() if v is not None}}
        # Vergleich mit der Vorrunde und mit der ersten Messung (das Überschießen kann sich über mehrere Runden aufbauen)
        vergleiche = [(len(verlauf["messungen"]), werte_aus(vorher))]
        if len(verlauf["messungen"]) > 1:
            vergleiche.append((1, werte_aus(verlauf["messungen"][0])))
        for k, zuordnung in WAECHTER.items():
            v1 = roh_jetzt.get(k)
            if k not in ref or v1 is None:
                continue
            st1, seite1 = status_von(v1, ref[k]), seite_von(v1, ref[k])
            for runde, werte in vergleiche:
                v0 = werte.get(k)
                if v0 is None:
                    continue
                st0, seite0 = status_von(v0, ref[k]), seite_von(v0, ref[k])
                band_verlassen = st1 == "rot" and seite1 in ("gegen", None) and (st0 != "rot" or seite0 != seite1)
                gruen_verlassen = st0 == "gruen" and st1 != "gruen"
                ueber_median = seite0 == "ki" and seite1 == "gegen" and st1 != "gruen"  # über das Ziel hinaus auf die andere Seite
                if not (band_verlassen or gruen_verlassen or ueber_median):
                    continue
                typen = zuordnung.get(seite1, set())
                r = ref[k]["mensch"]
                grenze = (f"über P90 ({fmt(r['p90'])})" if v1 > r["p90"] else f"unter P10 ({fmt(r['p10'])})") if st1 == "rot" else \
                    (f"über dem Zielbereich (P75 {fmt(r['p75'])})" if v1 > r["p75"] else f"unter dem Zielbereich (P25 {fmt(r['p25'])})")
                ueberkorrektur.append({"id": k, "name": analyse.NAMEN.get(k, k), "vorher": v0, "messung_vorher": runde, "wert": v1,
                                       "grenze": grenze, "art": "Nebenwirkung" if seite1 == "ki" else "Überkorrektur",
                                       "aussetzen": sorted(typen)})
                ausgesetzt |= typen
                break
    # Zustand (auch ohne Verlauf): Lesbarkeit/Nominalstil liegen schon jenseits von P10–P90 auf der der KI gegenüberliegenden
    # Seite. Weiteres Verdichten (Bündeln, Klammer, Nebensatz → Nominalgruppe) würde den Text noch weiter aus dem Band treiben.
    jenseits = []
    for k in ("lix", "wiener_sachtextformel", "flesch_amstad", "nominalstil_pro_100"):
        v1 = roh_jetzt.get(k)
        if k not in ref or v1 is None or status_von(v1, ref[k]) != "rot" or seite_von(v1, ref[k]) != "gegen":
            continue
        r = ref[k]["mensch"]
        jenseits.append({"id": k, "name": analyse.NAMEN.get(k, k), "wert": v1,
                         "grenze": f"über P90 {fmt(r['p90'])}" if v1 > r["p90"] else f"unter P10 {fmt(r['p10'])}"})
        ausgesetzt |= WAECHTER[k]["gegen"]
    frueher: list[tuple[int, set]] = []  # (Runde, {(typ, anfang)}) aller bisherigen Messungen
    for i, mess in enumerate((verlauf or {}).get("messungen", []), 1):
        frueher.append((i, {(h.get("typ"), h.get("anfang")) for h in mess.get("hinweise", []) if isinstance(h, dict)}))

    hinweise: list[dict] = []
    belegt: set[int] = set()  # Sätze mit strukturellem Auftrag (höchstens einer je Satz)

    def pendelt(typ: str, *nrn: int) -> bool:
        """Wurde an einem dieser Sätze früher der gegenteilige Auftrag gegeben (erst bündeln, dann teilen …)?"""
        gegen = GEGENTEIL.get(typ, set())
        anf = {schluessel_anfang(nach_nr[n]["text"]) for n in nrn if n in nach_nr}
        return any(t in gegen and a in anf for _, schl in frueher for (t, a) in schl)

    def hinweis(typ: str, s: dict | None, text_: str, gewicht: float = 1.0, absatz: int | None = None, fund: str | None = None,
                ersetzbar=(), weitere: tuple = ()):
        if typ in ausgesetzt:
            return False
        nrn = ([s["nr"]] if s else []) + list(weitere)
        if typ in STRUKTURELL:
            if any(n in belegt for n in nrn) or pendelt(typ, *nrn):
                return False
            belegt.update(nrn)
        h = TYP_HEBEL.get(typ, typ)
        hinweise.append({"hebel": h, "typ": typ, "absatz": s["absatz"] if s and absatz is None else absatz,
                         "satz": s["nr"] if s else None, "text": text_, "fund": fund,
                         "anfang": schluessel_anfang(s["text"]) if s else None,
                         "ersetzbar": sorted({w.lower() for w in ersetzbar if w}),
                         "gewicht": gewicht * (hebel.get(h, {}).get("prioritaet", 0.3) + 0.1)})
        return True

    # --- 1. Satzlängen --------------------------------------------------------
    ziel_vert = ts.get("satzlaengen_verteilung_mensch") or {}
    schiefe_fokus = m.get("satzlaenge_schiefe") if not fokus_block else None
    diag = satzlaengen_diagnose(fokus, ref, ziel_vert, schiefe_fokus)
    laengen_aktiv = any(ki_auffaellig(k) for k in ("anteil_lange_saetze", "anteil_mittlere_saetze", "anteil_sehr_lange_saetze",
                                                   "satzlaenge_cv", "satzlaenge_sd", "satzlaenge_dispersion", "satzlaenge_schiefe"))
    if diag["modus"] == "buendeln" and not laengen_aktiv:
        diag["modus"], diag["kontingent"] = None, 0  # im grünen Bereich: kein Auftrag (Grundsatz 1)
    L = [s["woerter"] for s in fokus]
    idx = {s["nr"]: i for i, s in enumerate(fokus)}
    gebuendelt = 0
    if diag["modus"] == "buendeln" and diag["kontingent"] > 0 and "buendeln" not in ausgesetzt:
        kandidaten = []
        for liste in absaetze.values():
            for a, b in zip(liste, liste[1:]):
                if not (10 <= a["woerter"] <= 24 and 10 <= b["woerter"] <= 24 and a["woerter"] + b["woerter"] >= 34):
                    continue
                if not (nutzbar(a) and nutzbar(b)) or langes_zitat(a) or langes_zitat(b):
                    continue
                if ";" in masken[a["nr"]] or a["text"].rstrip("\"“”»)").endswith(("?", "!")):
                    continue
                if quelle.get(a["nr"], False) != quelle.get(b["nr"], False):
                    continue  # sonst würde eine Aussage der fremden Quelle zugeschrieben
                if not (verbunden(begriffe_info[a["nr"]], begriffe_info[b["nr"]]) or ANAPHER_RE.match(b["text"].lstrip("„\"(»"))
                        or RUECKVERWEIS_RE.search(" ".join(b["text"].split()[:6]))):
                    continue
                kandidaten.append((a, b))
        aktuell = list(L)
        positionen = list(range(len(L)))  # Index in aktuell je ursprünglichem Fokus-Index (None = verschmolzen)
        guete = laengen_guete(aktuell, ref, ziel_vert)
        while kandidaten and gebuendelt < diag["kontingent"]:
            bester = None
            for a, b in kandidaten:
                ia, ib = positionen[idx[a["nr"]]], positionen[idx[b["nr"]]]
                if ia is None or ib is None:
                    continue
                neu = aktuell[:ia] + [round(VERDICHTUNG * (aktuell[ia] + aktuell[ib]))] + aktuell[ib + 1:]
                g = laengen_guete(neu, ref, ziel_vert)
                if g[0] < guete[0] - 1e-9 and g[1] <= guete[1] + 1e-9 and g[2] <= guete[2] + 1e-9:
                    if bester is None or guete[0] - g[0] > bester[0]:
                        bester = (guete[0] - g[0], a, b, neu, g)
            if bester is None:
                break
            _, a, b, neu, g = bester
            kandidaten = [(x, y) for x, y in kandidaten if x is not a and y is not b and x is not b and y is not a]
            if not hinweis("buendeln", a, f"{zitat(a)} und Satz {b['nr']} ({a['woerter']} + {b['woerter']} Wörter) zu einem Satz ab {LANG_AB} Wörtern "
                           f"verbinden: den Inhalt von Satz {b['nr']} als Nominal- oder Präpositionalgruppe in Satz {a['nr']} einbauen, kein "
                           "angehängtes „und“.", 1.1, weitere=(b["nr"],)):
                continue
            ia, ib = positionen[idx[a["nr"]]], positionen[idx[b["nr"]]]
            positionen = [None if p_i == ib else (p_i - 1 if p_i is not None and p_i > ib else p_i) for p_i in positionen]
            aktuell, guete = neu, g
            gebuendelt += 1
    # Bremse: Teilen-Aufträge nur mit Beleg, dass der Text über das menschliche Band hinaus geraten ist – Überkorrektur im
    # Verlauf, Wert über P90 oder fehlende Mitte. Lange Sätze zwischen P75 und P90 sind auch bei Menschen häufig (≈ 15 %)
    # und ziehen im Modell eher Richtung menschlich; dort nur kein weiteres Bündeln.
    lang_ids = {"satzlaenge_mittel", "satzlaenge_median", "anteil_lange_saetze", "anteil_sehr_lange_saetze", "anteil_mittlere_saetze"}
    diag["ueberkorrektur"] = any(u["id"] in lang_ids and u["art"] == "Überkorrektur" for u in ueberkorrektur)
    diag["ueber_p90"] = bool(L) and (diag["anteil_lange"] > (p_("anteil_lange_saetze", "p90") or 1)
                                     or diag["mittel"] > (p_("satzlaenge_mittel", "p90") or 99))
    min_teilen = LANG_AB
    if diag["modus"] == "teilen" and not diag["ueberkorrektur"]:
        # ohne Verlauf-Beleg: höchstens zwei Aufträge, nur für sehr lange Sätze (≥ 40 Wörter)
        diag["kontingent"] = min(2, diag["kontingent"]) if (diag["ueber_p90"] or diag["fehlende_mitte"]) else 0
        min_teilen = SEHR_LANG_AB
    if diag["modus"] == "teilen" and diag["kontingent"] > 0 and "teilen" not in ausgesetzt:
        kandidaten = sorted((s for s in fokus if s["woerter"] >= min_teilen and nutzbar(s)), key=lambda s: -s["woerter"])
        lange40 = [s for s in kandidaten if s["woerter"] >= SEHR_LANG_AB]
        kandidaten = lange40 + [s for s in kandidaten if s["woerter"] < SEHR_LANG_AB] if lange40 else kandidaten
        aktuell = list(L)
        guete = laengen_guete(aktuell, ref, ziel_vert)
        geteilt, ziel_lange = 0, round(p_("anteil_lange_saetze", "p50") * len(L))
        for s in kandidaten:
            if geteilt >= diag["kontingent"]:
                break
            stelle = teilstelle(s["text"], masken[s["nr"]])
            if stelle is None and langes_zitat(s):
                continue  # keine Trennstelle außerhalb des wörtlichen Zitats: „an einer inhaltlichen Wende“ würde das Zitat zerteilen
            nl, nr_ = (stelle[1], stelle[2]) if stelle else (s["woerter"] // 2, s["woerter"] - s["woerter"] // 2)
            i = aktuell.index(s["woerter"]) if s["woerter"] in aktuell else None
            if i is None:
                continue
            neu = aktuell[:i] + [nl, nr_] + aktuell[i + 1:]
            g = laengen_guete(neu, ref, ziel_vert)
            noch_zu_viele = sum(x >= LANG_AB for x in aktuell) > ziel_lange
            if not (g[0] < guete[0] - 1e-9 or noch_zu_viele):
                continue
            wo = f" – an der Stelle „{stelle[3]}“ (nach Wort {nl}); der zweite Teil wird ein eigener Satz" if stelle else \
                " – an einer inhaltlichen Wende"
            if hinweis("teilen", s, f"{zitat(s)} ({s['woerter']} Wörter) in zwei Sätze teilen{wo}.", 1.2):
                aktuell, guete = neu, g
                geteilt += 1
    # d) kurze Sätze: nur wenn anteil_kurze_saetze unter P25 liegt UND das die KI-Seite ist (KI-Median unter dem menschlichen).
    #    In den aktuellen Referenzwerten liegt der KI-Median darüber (0,119 gegen 0,105) – dann gibt es keinen Auftrag.
    k25 = p_("anteil_kurze_saetze", "p25")
    kurz_ki_unten = "anteil_kurze_saetze" in ref and (ref["anteil_kurze_saetze"].get("ki") or {}).get("p50") is not None \
        and ref["anteil_kurze_saetze"]["ki"]["p50"] < ref["anteil_kurze_saetze"]["mensch"]["p50"]
    if k25 is not None and kurz_ki_unten and diag["anteil_kurze"] < k25 and diag["n"] >= 10:
        for s in sorted(fokus, key=lambda s: -s["woerter"]):
            if s["woerter"] >= 22 and masken[s["nr"]].count(",") >= 2 and SCHLUSS_RE.search(masken[s["nr"]]) and nutzbar(s):
                if hinweis("kurz", s, f"{zitat(s)}: Falls darin ein echtes Zwischenergebnis steckt (etwa nach „{SCHLUSS_RE.search(masken[s['nr']]).group(0)}“), "
                           "dieses als eigenen kurzen Satz formulieren.", 0.6):
                    break

    # --- 2. Zickzack ------------------------------------------------------------
    # Die Handlung „Satz X mit X+1 verbinden“ verlängert (kurz + lang ≥ 40 Wörter): nicht im TEILEN-Modus.
    r1 = kz.get("rhythmus_r1_log")
    if r1 and r1["bewertet"] and r1["wert"] < r1["mensch_p25"] and r1["seite"] == "ki" and not gebuendelt and "zickzack" not in ausgesetzt \
            and diag["modus"] != "teilen":
        n_zz = 0
        for a_i, b_i in zickzack(L):
            if n_zz >= 2:
                break
            teil = fokus[a_i:b_i + 1]
            folge = " · ".join(str(s["woerter"]) for s in teil)
            x = next((teil[j] for j in range(len(teil) - 1) if klasse_zz(teil[j]["woerter"]) == "k"
                      and teil[j]["absatz"] == teil[j + 1]["absatz"] and nutzbar(teil[j]) and nutzbar(teil[j + 1])
                      and teil[j]["nr"] not in belegt and teil[j + 1]["nr"] not in belegt), None)
            if x is None:
                continue
            x2 = nach_nr.get(x["nr"] + 2)
            oder = f" oder Satz {x2['nr']} nicht weiter verlängern" if x2 and x2["nr"] <= teil[-1]["nr"] else ""
            ein_absatz = len({s["absatz"] for s in teil}) == 1
            if hinweis("zickzack", x, f"Satz {teil[0]['nr']}–{teil[-1]['nr']} wechseln streng zwischen kurz (≤ {ZZ_KURZ_MAX}) und lang "
                       f"(≥ {ZZ_LANG_AB} Wörter) ({folge}). Satz {x['nr']} mit Satz {x['nr'] + 1} verbinden{oder} – zwei ähnlich lange Sätze "
                       "hintereinander brechen das Muster.", 0.8, absatz=teil[0]["absatz"] if ein_absatz else None, weitere=(x["nr"] + 1,)):
                if not ein_absatz:
                    hinweise[-1]["absatz"] = None  # Spanne über mehrere Absätze: allgemeiner Hinweis, keinem Absatz zugeordnet
                n_zz += 1

    # --- 3. Satzklammer ---------------------------------------------------------
    if ki_auffaellig("satzklammer_mittel") or ki_auffaellig("nominalketten_pro_100"):
        n_kl = 0
        for i, s in enumerate(fokus):
            if n_kl >= 3:
                break
            if s["woerter"] <= 12 or not nutzbar(s) or s["nr"] in belegt or langes_zitat(s):
                continue
            mk = masken[s["nr"]]
            if REDEVERB_DASS_RE.search(mk) or re.search(r",\s+(?:dass|ob)\b", mk):
                continue  # Objektsatz: folgende Nebensätze gehören zu ihm, nicht ins Mittelfeld des Hauptsatzes
            leer = [d for d in klammer_details(mk) if d[0] <= 2]
            if not leer:
                continue
            _, aux, ende = leer[0]
            q = KLAMMER_QUELLE_RE.search(mk)
            nachbar = fokus[i + 1] if i + 1 < len(fokus) and fokus[i + 1]["absatz"] == s["absatz"] else None
            if q:
                teil = {"um": "„um … zu“-Teil", "ohne": "„ohne … zu“-Teil"}.get(q.group("w"), f"„{q.group('w')}“-Satz")
                if hinweis("klammer", s, f"{zitat(s)}: Zwischen „{aux}“ und „{ende}“ steht fast nichts. Den {teil} als Angabe "
                           f"(Präpositionalgruppe, z. B. mit „zur“, „durch“, „wegen“) zwischen „{aux}“ und „{ende}“ holen.", 0.8):
                    n_kl += 1
            elif nachbar and diag["modus"] != "teilen" and nutzbar(nachbar) and nachbar["woerter"] <= 14 and not beginnt_im_zitat(nachbar) \
                    and (analyse.tokens(nachbar["text"]) or [""])[0].lower() in ANGABE_ANFANG \
                    and verbunden(begriffe_info[s["nr"]], begriffe_info[nachbar["nr"]]) \
                    and quelle.get(s["nr"], False) == quelle.get(nachbar["nr"], False):
                if hinweis("klammer_zusatz", s, f"{zitat(s)}: Zwischen „{aux}“ und „{ende}“ steht fast nichts. Die Angabe vom Anfang von "
                           f"Satz {nachbar['nr']} („{anfang(nachbar['text'], 3)}“) dorthin holen und Satz {nachbar['nr']} damit auflösen.", 0.8,
                           weitere=(nachbar["nr"],)):
                    n_kl += 1

    # Folgesätze einer Bündelung gehen im ersten Satz auf: dort keine weiteren Wort-Hinweise
    gebuendelte_b = {h["satz"] + 1 for h in hinweise if h["typ"] in ("buendeln", "klammer_zusatz")}

    # --- 4. Nebensätze und Kommas -----------------------------------------------
    neben_ids = [k for k in ("teilsatz_verhaeltnis_21", "anteil_saetze_mit_nebensatz", "woerter_pro_teilsatz") if ki_auffaellig(k)]
    if neben_ids:
        verteil = Counter()
        mit_neben = 0
        for s in fokus:
            h_, n_, _ = analyse.teilsatz_zerlegung(s["text"])
            verteil[h_ + n_] += 1
            mit_neben += n_ > 0
        k = 0
        if "teilsatz_verhaeltnis_21" in neben_ids:
            p50 = p_("teilsatz_verhaeltnis_21", "p50")
            k = max(k, math.ceil((verteil[2] + 0.5 - p50 * (verteil[1] + 0.5)) / (1 + p50)))
        if "anteil_saetze_mit_nebensatz" in neben_ids:
            k = max(k, math.ceil(mit_neben - p_("anteil_saetze_mit_nebensatz", "p50") * len(fokus)))
        if "woerter_pro_teilsatz" in neben_ids:
            k = max(k, 2)
        k = min(4, max(0, k))
        kandidaten = []
        for s in fokus:
            if s["woerter"] < 8 or not nutzbar(s) or s["nr"] in belegt or langes_zitat(s):
                continue
            h_, n_, _ = analyse.teilsatz_zerlegung(s["text"])
            if h_ != 1 or n_ != 1:
                continue
            mk = masken[s["nr"]]
            for rang, (name, rx, technik) in enumerate(NEBENSATZ_TYPEN):
                if rx.search(mk):
                    kandidaten.append((rang, s["nr"], s, technik))
                    break
        n_ns = 0
        for _, _, s, technik in sorted(kandidaten, key=lambda x: (x[0], x[1])):
            if n_ns >= k:
                break
            if hinweis("nebensatz", s, f"{zitat(s)}: {technik[0].upper() + technik[1:]}.", 0.8):
                n_ns += 1
        # Kommas: viele kurze Teilsätze. Teilen nur, wenn lange Sätze nicht fehlen.
        teilen_ok = diag["modus"] == "teilen" or (p_("anteil_lange_saetze", "p50") is not None
                                                 and diag["anteil_lange"] >= p_("anteil_lange_saetze", "p50"))
        n_ko = 0
        for s in fokus:
            if n_ko >= 3:
                break
            mk = analyse._ohne_zahlzeichen(masken[s["nr"]]) if hasattr(analyse, "_ohne_zahlzeichen") else masken[s["nr"]]
            mk = AUTORENLISTE_RE.sub(lambda x: x.group(0).replace(",", ""), mk)  # „Kahneman, Knetsch und Thaler“
            teile = max(1, s.get("teilsaetze", 1))
            if mk.count(",") < 3 or s["woerter"] / teile >= 10 or not nutzbar(s):
                continue
            if teilen_ok and s["woerter"] < LANG_AB:
                tat = "Einen Einschub als eigenen Satz herauslösen."
            else:
                tat = "Einen Nebensatz oder Einschub zur Nominalgruppe machen (Länge bleibt, Kommas sinken)."
            if hinweis("kommas", s, f"{zitat(s)}: {mk.count(',')} Kommas bei kurzen Teilsätzen. {tat}", 0.7):
                n_ko += 1

    # --- 5. Begriffe ------------------------------------------------------------------
    aufnahme = kz.get("anteil_saetze_mit_wortaufnahme")
    begriffe_lokal = (ki_auffaellig("anteil_saetze_mit_wortaufnahme") or ki_auffaellig("nachbarsatz_ueberlappung")) \
        and (aufnahme is None or aufnahme["wert"] < aufnahme["mensch_p50"])
    fw = kz.get("fw_profil_llr_pro_1000")
    fw_aktiv = bool(fw and fw["wert"] < fw["mensch_p25"])
    if begriffe_lokal and aufnahme:
        teilt = sum(1 for a, b in zip(fokus, fokus[1:]) if begriffe_info[a["nr"]]["staemme"] & begriffe_info[b["nr"]]["staemme"])
        k_begriffe = max(0, math.ceil(aufnahme["mensch_p50"] * max(1, len(fokus) - 1)) - teilt)
    else:
        k_begriffe = 0
    n_begr = 0
    # Possessiv/„Sie“ zählen auch als Funktionswort-Hebel; „Diese + Sammelwort“ nur über die Begriffs-Kennzahlen
    cap_anknuepf = min(4, max(k_begriffe, 2 if fw_aktiv else 0))
    if cap_anknuepf and "anknuepfung" not in ausgesetzt:
        for liste in absaetze.values():
            for a, b in zip(liste, liste[1:]):
                if n_begr >= cap_anknuepf:
                    break
                if not (nutzbar(a) and nutzbar(b)) or b["nr"] in gebuendelte_b or beginnt_im_zitat(b):
                    continue  # „Ihre …“/„Sie …“ als Zitatanfang gehört zum fremden Wortlaut
                mt = ANKNUEPF_RE.match(b["text"].lstrip("„\"(»"))
                if not mt or verbunden(begriffe_info[a["nr"]], begriffe_info[b["nr"]]):
                    continue
                kand = bezugsausdruecke(a["text"])
                if not kand:
                    continue
                vorschlag = " oder ".join(f"„{k_}“" for k_ in kand[:3])
                if mt.group("dem"):
                    if not k_begriffe or not ist_kapselwort(mt.group("nomen")):
                        continue
                    t_ = (f"{zitat(b)} beginnt mit „{mt.group('dem')} {mt.group('nomen')}“ (abstraktes Sammelwort). Prüfen, ob ein Begriff "
                          f"aus Satz {a['nr']} präziser ist, z. B. {vorschlag}.")
                elif mt.group("pron"):
                    if personen_anfang(a["text"]) or autor.get(a["nr"]):
                        continue  # „Sie“ = die zuvor genannten Personen/Autoren
                    t_ = (f"{zitat(b)} beginnt mit „{mt.group('pron')}“: das Pronomen durch den Bezugsbegriff ersetzen (vermutlich "
                          f"{vorschlag} aus Satz {a['nr']}).")
                else:
                    if RUECKVERWEIS_RE.search(" ".join(b["text"].split()[1:8])) or KATAPHER_RE.match(b["text"].lstrip("„\"(»")):
                        continue  # Bezug folgt im selben Satz („Ihren Ursprung hat diese Form …“, „Seine Wirkung entfaltet ein …“)
                    t_ = (f"{zitat(b)} beginnt mit „{mt.group('poss')} …“: Artikel + Bezugswort im Genitiv statt Possessiv (Bezug "
                          f"vermutlich {vorschlag} aus Satz {a['nr']}).")
                if hinweis("anknuepfung", b, t_, 1.0):
                    hinweise[-1]["art"] = "dem" if mt.group("dem") else ("pron" if mt.group("pron") else "poss")
                    n_begr += 1
    if k_begriffe > n_begr and "kein_bezug" not in ausgesetzt:
        hinweis_nrn = {h["satz"] for h in hinweise if h["typ"] == "anknuepfung"}
        kand = []
        for liste in absaetze.values():
            for j in range(1, len(liste)):
                a, b = liste[j - 1], liste[j]
                if not (nutzbar(a) and nutzbar(b)) or b["nr"] in hinweis_nrn or b["nr"] in gebuendelte_b or b["woerter"] < 8:
                    continue
                ia, ib = begriffe_info[a["nr"]], begriffe_info[b["nr"]]
                if not (ia["staemme"] and ib["staemme"]) or verbunden(ia, ib):
                    continue
                if j >= 2 and verbunden(begriffe_info[liste[j - 2]["nr"]], ib):
                    continue  # Fenster von zwei Sätzen
                if beginnt_im_zitat(b):
                    continue  # Satzanfang ist fremder Wortlaut
                anf = b["text"].lstrip("„\"(»")
                if AUFZAEHLUNG_RE.match(anf) or ANAPHER_RE.match(anf) or RUECKVERWEIS_RE.search(" ".join(anf.split()[:6])):
                    continue  # Aufzählung oder ausdrücklicher Rückverweis („Danach …“, „Die dort …“)
                if autor.get(b["nr"]) or personen_anfang(anf) or re.match(r"(?:Laut|Nach|Gemäß)\s+[A-ZÄÖÜ]", anf):
                    continue  # neue Quelle: eigener Bezugspunkt
                kand.append((0 if ARTIKEL_NOMEN_RE.match(anf) else 1, b["nr"], b, a))
        n_kb = 0
        for _, _, b, a in sorted(kand, key=lambda x: (x[0], x[1])):
            if n_kb >= min(4, k_begriffe - n_begr):
                break
            if hinweis("kein_bezug", b, f"Satz {b['nr']} („{anfang(b['text'])}“) beginnt ohne Bezug zu Satz {a['nr']}. Falls dieselbe Sache gemeint "
                       f"ist, das Wort aus Satz {a['nr']} verwenden.", 0.6):
                n_kb += 1
    if any(ki_auffaellig(k, nur_rot=True) for k in ("mattr_100", "mtld", "inhaltswort_mattr_50")) and "synonyme" not in ausgesetzt:
        for c in synonym_cluster(fokus, masken)[:2]:
            liste_ = ", ".join(f"„{w}“ ({n}×)" for w, n in c["varianten"])
            hinweis("synonyme", None, f"Für dieselbe Sache wechseln die Wörter: {liste_}. Falls dasselbe gemeint ist, eine Form wählen und im "
                    "ganzen Text verwenden.", 0.9, ersetzbar=c["formen"])

    # --- 6. Funktionswörter konkret ------------------------------------------------------
    if fw_aktiv:
        n_fw = 0
        for s in fokus:
            if n_fw >= 5:
                break
            if not nutzbar(s) or s["nr"] in gebuendelte_b:
                continue
            mk = masken[s["nr"]]
            t_l = LASSEN_SICH_RE.search(mk)
            t_z = ZEIGT_SICH_RE.search(mk)
            if t_l and sum(h["typ"] == "fw_lassen" for h in hinweise) < 2:
                if hinweis("fw_lassen", s, f"{zitat(s)}: „{t_l.group(0)}“ → Technik „kann … werden“ (Beispiel: „Das lässt sich messen.“ → "
                           "„Das kann gemessen werden.“).", 0.8, fund=t_l.group(0), ersetzbar=re.findall(r"lässt|lassen|ließ|ließen", t_l.group(0), re.I)):
                    n_fw += 1
            elif t_z and sum(h["typ"] == "fw_zeigt" for h in hinweise) < 1:
                if hinweis("fw_zeigt", s, f"{zitat(s)}: „{t_z.group(0)}“ – das Ergebnis direkt nennen (Beispiel: „Es zeigt sich, dass die Kosten "
                           "steigen.“ → „Die Kosten steigen.“).", 0.8, fund=t_z.group(0), ersetzbar=[t_z.group(0).split()[0]]):
                    n_fw += 1
        profil = ts.get("fw_profil") or {}
        rm, rk = profil.get("rate_mensch") or {}, profil.get("rate_ki") or {}
        gewichte = {w: math.log(rk[w] / rm[w]) for w in FW_TECHNIK if rm.get(w) and rk.get(w) and rk[w] > rm[w]}
        if gewichte:
            dichte = []
            schon = {h["satz"] for h in hinweise if h["typ"].startswith("fw_")}
            for s in fokus:
                if s["woerter"] < 12 or not nutzbar(s) or s["nr"] in schon or s["nr"] in gebuendelte_b:
                    continue
                zaehl = fw_zaehlung(analyse.tokens(masken[s["nr"]]), gewichte)
                if len(zaehl) < 2 or sum(zaehl.values()) < 3:
                    continue
                dichte.append((sum(gewichte[w] * min(2, n) for w, n in zaehl.items()) / s["woerter"], s, zaehl))
            for _, s, zaehl in sorted(dichte, key=lambda x: -x[0])[:max(0, min(3, 5 - n_fw))]:
                woerter = ", ".join(f"„{w}“" + (f" {n}×" if n > 1 else "") for w, n in zaehl.most_common())
                technik = "; ".join(FW_TECHNIK[w] for w, _ in zaehl.most_common(3))
                hinweis("fw_dichte", s, f"{zitat(s)}: viele KI-typische Funktionswörter ({woerter}). Konstruktionen prüfen: {technik}.", 0.6)

    # --- 7. Floskeln, Gegenfolie, Konnektoren ---------------------------------------------
    muster_info = {mu["id"]: mu for mu in muster}
    km = kz.get("ki_muster_pro_1000")
    floskel_aktiv = ki_auffaellig("ki_muster_pro_1000")
    sondern_aktiv = ki_auffaellig("sondern_pro_1000")
    # Kontingent: Gewicht, das bis zum menschlichen Median wegfallen muss (nie bis null jagen)
    noetig = max(0.0, (km["wert"] - km["mensch_p50"]) * tok_fokus / 1000) if km else 0.0
    treffer = []
    for s in fokus:
        if not nutzbar(s):
            continue
        for _a, _e, g, mu, fund, _v in analyse.muster_treffer(masken[s["nr"]], muster):
            if g > 0 and MASKE not in fund:
                treffer.append((g, s, mu, fund, _a, _e))
    entfernt = 0.0
    for g, s, mu, fund, _a, _e in sorted(treffer, key=lambda t: (-t[0], t[1]["nr"])):
        gegenfolie = mu["id"] in GEGENFOLIE_MUSTER
        # hochpräzise Muster (Gewicht ≥ 1,5) auch im grünen Bereich, solange der Wert über dem menschlichen Median liegt –
        # nicht die Gegenfolie: echte Kontraste sind auch in menschlichen Texten häufig
        erlaubt = floskel_aktiv or (g >= 1.5 and noetig > 0 and not gegenfolie) or (gegenfolie and sondern_aktiv)
        if not erlaubt:
            continue
        if entfernt >= noetig and not (gegenfolie and sondern_aktiv):
            continue
        ersatz = mu.get("ersatz", "durch die konkrete Aussage ersetzen")
        typ = "floskel"
        if gegenfolie:
            typ = "gegenfolie"
            mk = masken[s["nr"]]
            mx = NICHT_X_RE.search(mk)
            x_staemme = analyse.inhaltsstaemme(analyse.tokens(ADDITIV_RE.sub(" ", mx.group("x")))) if mx else set()
            vorige = [nach_nr[n] for n in range(s["nr"] - 3, s["nr"]) if n in nach_nr]
            x_genannt = bool(x_staemme) and any(x_staemme & begriffe_info[v["nr"]]["staemme"] for v in vorige)
            if ADDITIV_RE.search(fund):
                ersatz = "zu „X und auch Y“ bzw. „neben X auch Y“ umstellen."
            elif quelle.get(s["nr"]) or REDEVERB_RE.search(mk):
                ersatz = "Aussage einer Quelle bzw. Redeverb: nur umformulieren (z. B. zwei Aussagen nacheinander), X behalten."
            elif x_genannt:
                ersatz = "X wird kurz vorher im Text genannt, die Gegenüberstellung ist begründet: nur umformulieren, X behalten."
        # nur Auslöser-Wörter als ersetzbar melden, nie Platzhalter des Musters (die sind Inhalt des Nutzers)
        worte = [w for w in floskel_kopfwoerter(masken[s["nr"]], _a, _e, mu["_re"])
                 if w.lower() not in analyse.FUNKTIONSWOERTER and len(w) > 2] if typ == "floskel" else []
        if hinweis(typ, s, f"{zitat(s)}: „{fund}“ – {ersatz}", 0.6 + 0.3 * g, fund=fund, ersetzbar=worte):
            hinweise[-1]["muster_gewicht"] = g
            entfernt += g
    if ki_auffaellig("konnektoren_pro_1000"):
        kn = kz["konnektoren_pro_1000"]
        k_konn = min(6, max(0, math.ceil((kn["wert"] - kn["mensch_p50"]) * tok_fokus / 1000)))
        kand = []
        for s in fokus:
            if not nutzbar(s) or s["nr"] in gebuendelte_b:
                continue
            t_ = KONNEKTOR_RE.search(masken[s["nr"]])
            if t_:
                kand.append((0 if t_.start() <= 2 else 1, s["nr"], s, t_.group(1)))
        n_k = 0
        for _, _, s, wort in sorted(kand, key=lambda x: (x[0], x[1])):
            if n_k >= k_konn:
                break
            if hinweis("konnektor", s, f"{zitat(s)}: „{wort}“ streichen, wenn der Bezug klar ist, oder über das wiederholte Nomen anschließen "
                       "(nicht nur verschieben).", 0.9, fund=wort, ersetzbar=[wort]):
                n_k += 1

    # --- 8. Semikolon, Doppelpunkt, Abkürzungen -----------------------------------------
    for s in fokus:
        if not nutzbar(s):
            continue
        mk = analyse._ohne_zahlzeichen(masken[s["nr"]]) if hasattr(analyse, "_ohne_zahlzeichen") else masken[s["nr"]]
        if ";" in mk:
            hinweis("semikolon", s, f"{zitat(s)}: Semikolon durch Punkt ersetzen oder mit „und“/„weil“ verbinden.", 1.0, fund=";")
    if "doppelpunkt" in hebel:
        for s in fokus:
            if nutzbar(s) and re.search(r":(?!\d)\s", masken[s["nr"]]):
                hinweis("doppelpunkt", s, f"{zitat(s)}: Doppelpunkt prüfen – oft ist ein eigener Satz oder ein Nebensatz natürlicher.", 0.7, fund=":")
    if "abkuerzungen" in hebel:
        n_ab = 0
        for s in fokus:
            t_ = AUSGESCHRIEBEN_RE.search(masken[s["nr"]]) if nutzbar(s) else None
            if t_ and n_ab < 3:
                kurz = AUSGESCHRIEBEN[t_.group(1).lower()]
                hinweis("abkuerzung", s, f"{zitat(s)}: „{t_.group(1)}“ darf als „{kurz}“ stehen – in Hochschultexten üblich.", 0.5, fund=t_.group(1))
                n_ab += 1

    # --- 9. Absätze (höchstens ein Umbau je Runde) --------------------------------------------
    abs_ids = ("saetze_pro_absatz_cv", "absatzlaenge_cv", "saetze_pro_absatz", "absatzlaenge_mittel")
    if any(ki_auffaellig(k) for k in abs_ids) and absaetze:
        anz = {nr: len(l) for nr, l in absaetze.items()}
        woerter_abs = {nr: sum(s["woerter"] for s in l) for nr, l in absaetze.items()}
        gleichmaessig = (ki_auffaellig("saetze_pro_absatz_cv") or ki_auffaellig("absatzlaenge_cv")) and len(anz) >= 3
        grund = f" Grund: Sätze pro Absatz {' · '.join(str(v) for v in anz.values())} sind sehr gleichmäßig." if gleichmaessig else ""

        def tiling(liste: list[dict]) -> list[int]:
            """Trennstellen-Kandidaten (Index im Absatz, vor dem geteilt wird), geringste Begriffsüberlappung zuerst."""
            werte = []
            for k_ in range(2, len(liste) - 1):
                vor, nach = masken[liste[k_ - 1]["nr"]].rstrip(), masken[liste[k_]["nr"]].lstrip()
                if not nutzbar(liste[k_]) or (vor[-1:] == MASKE and nach[:1] == MASKE):
                    continue  # nicht mitten in einem wörtlichen Zitat teilen
                links = set().union(*(begriffe_info[s["nr"]]["staemme"] for s in liste[max(0, k_ - 2):k_]))
                rechts = set().union(*(begriffe_info[s["nr"]]["staemme"] for s in liste[k_:k_ + 2]))
                ueb = len(links & rechts) / (len(links | rechts) or 1)
                werte.append((ueb, abs(k_ - len(liste) / 2), k_))
            return [k_ for _, _, k_ in sorted(werte)]

        spa = kz.get("saetze_pro_absatz")
        riesig = [nr for nr, w in woerter_abs.items() if w > 250 and anz[nr] >= 4]
        nur_gleichmaessig = not (riesig or len(anz) == 1 or (spa and spa["wert"] >= spa["mensch_p50"]))
        if not nur_gleichmaessig or (gleichmaessig and max(anz.values()) >= 5):
            nr = max(riesig or anz, key=lambda n: (woerter_abs[n] if riesig else anz[n]))
            liste = absaetze[nr]
            # kein Pendeln: nicht dort teilen, wo in einer Vorrunde zusammengelegt wurde
            stellen = [k_ for k_ in tiling(liste) if not pendelt("absatz_teilen", liste[k_]["nr"])]
            if stellen and len(liste) >= 4:
                k_, k2 = stellen[0], None
                zweite = ""
                if woerter_abs[nr] > 500:
                    rest = [x for x in stellen[1:] if abs(x - k_) >= 4 and x >= 4 and len(liste) - x >= 4]
                    if rest:
                        k_, k2 = sorted((k_, rest[0]))
                        zweite = f" und vor Satz {liste[k2]['nr']}"
                grenzen = [0, k_] + ([k2] if k2 else []) + [len(liste)]
                neu_anz = [v for n_, v in anz.items() if n_ != nr] + [b - a for a, b in zip(grenzen, grenzen[1:])]
                # nur „zu gleichmäßig“ als Anlass: Teilen muss die Streuung erhöhen und darf die Sätze pro Absatz nicht unter
                # P25 drücken (sonst geht der Auftrag gegen seine eigene Kennzahl bzw. über das menschliche Band hinaus)
                wirkt = not nur_gleichmaessig or (analyse.cv(neu_anz) > analyse.cv(list(anz.values()))
                                                  and (not spa or sum(neu_anz) / len(neu_anz) >= spa["mensch_p25"]))
                if wirkt:
                    hinweis("absatz_teilen", liste[k_], f"Absatz {nr} ({woerter_abs[nr]} Wörter, {anz[nr]} Sätze) vor Satz {liste[k_]['nr']}{zweite} "
                            f"teilen – dort überschneiden sich die Begriffe davor und danach am wenigsten.{grund}", 1.0, absatz=nr)
        elif gleichmaessig and len(anz) >= 2:
            nrs = list(anz)
            paare = []
            for x, y in zip(nrs, nrs[1:]):
                if anz[x] + anz[y] > 7 or pendelt("absatz_zusammen", absaetze[y][0]["nr"]):
                    continue  # zu groß oder Pendeln (genau hier wurde in einer Vorrunde geteilt)
                gemeinsam = set().union(*(begriffe_info[s["nr"]]["staemme"] for s in absaetze[x])) & \
                    set().union(*(begriffe_info[s["nr"]]["staemme"] for s in absaetze[y]))
                if gemeinsam:
                    paare.append((anz[x] + anz[y], -len(gemeinsam), x, y, gemeinsam))
            if paare:
                _, _, x, y, gemeinsam = min(paare)
                wort = next((t for s in absaetze[y] for t in analyse.tokens(s["text"]) if analyse.ist_wort(t) and t[:1].isupper()
                             and analyse.stamm(t) in gemeinsam and t.lower() not in analyse.FUNKTIONSWOERTER), None)
                thema = f" – beide behandeln „{wort}“" if wort else ""
                # erster Satz von Absatz y als Schlüssel: so erkennt das Gedächtnis ein späteres Teilen an derselben Stelle als Pendeln
                hinweis("absatz_zusammen", absaetze[y][0], f"Absatz {x} und {y} ({anz[x]} + {anz[y]} Sätze) zusammenlegen{thema}.{grund}", 0.9,
                        absatz=x)

    # --- 10. Nutzer-Vorgaben (immer, außerhalb von Zitaten) -----------------------------------------
    for s in fokus:
        if not nutzbar(s):
            continue
        mk = masken[s["nr"]]
        for f in PARTIZIP_RE.findall(mk) or []:
            wort = f if isinstance(f, str) else next((x for x in f if x), "")
            if not wort:
                g_ = PARTIZIP_RE.search(mk)
                wort = g_.group(0) if g_ else ""
            if wort:
                hinweis("gender", s, f"{zitat(s)}: „{wort}“ → generisches Maskulinum (z. B. „Mitarbeiter“, „Teilnehmer“).", 1.5, fund=wort)
                break
        if analyse.GEDANKENSTRICH_RE.search(mk):
            hinweis("gedankenstrich", s, f"{zitat(s)}: Gedankenstrich durch Komma, Klammer oder neuen Satz ersetzen.", 0.8, fund="–")

    # --- Hinweis-Gedächtnis: in der Vorrunde unverändert genannt -> herabstufen ------------------
    if frueher:
        letzte_runde, letzte = frueher[-1]
        for h in hinweise:
            k_ = (h["typ"], h["anfang"])
            if h["anfang"] is None or k_ not in letzte:
                continue
            runde = letzte_runde
            for r_, schl in reversed(frueher[:-1]):
                if k_ in schl:
                    runde = r_
                else:
                    break
            h["schon_genannt"] = runde
            h["gewicht"] *= 0.4
            h["text"] += f" (schon in Runde {runde} genannt – überspringen, wenn unpassend)"

    # --- Auswahl ------------------------------------------------------------------------------
    ziel_p = bew.get("ziel_p_mensch") or ts.get("ziel_p_mensch") or 0.5
    ziel_score = ts.get("ziel_score") or bew.get("score_schwelle") or ts.get("score_schwelle") or 60
    ziel_rot = ts.get("ziel_rot_max")
    rot = [z for z in bew.get("kennzahlen", []) if z["bewertet"] and z["status"] == "rot"]
    ziel_erreicht = bool(bew.get("verfuegbar") and (bew.get("score") or 0) >= ziel_score
                         and (bew.get("p_mensch") is None or bew["p_mensch"] >= ziel_p)
                         and (ziel_rot is None or len(rot) <= ziel_rot))
    gesehen, eindeutig = set(), []
    for h in sorted(hinweise, key=lambda h: -h["gewicht"]):
        schluessel = (h["typ"], h["satz"], h["absatz"], h["text"] if h["satz"] is None else h["text"][:40])
        if schluessel not in gesehen:
            gesehen.add(schluessel)
            eindeutig.append(h)
    alle_roh = list(eindeutig)
    if ziel_erreicht:
        # nur Nutzer-Vorgaben und hochpräzise Hinweise (Semikolon, KI-Muster mit Gewicht ≥ 1,5); dazu die Satzlängen-Bremse,
        # wenn der Verlauf zeigt, dass der Text über das menschliche Band hinaus getrieben wurde
        bremse = diag["ueberkorrektur"]  # nur mit Beleg aus dem Verlauf: ohne ihn ist ein Text am Ziel auch mit langen Sätzen unauffällig
        teilen_h = [h for h in eindeutig if h["typ"] == "teilen"][:2] if bremse else []
        eindeutig = [h for h in eindeutig if h["typ"] in ZIEL_TYPEN
                     and (h["typ"] != "floskel" or h.get("muster_gewicht", 0) >= 1.5)] + teilen_h
        max_hinweise = min(max_hinweise, ZIEL_MAX)
    teilziel = None
    if bew.get("verfuegbar") and not ziel_erreicht and bew.get("p_mensch") is not None and bew["p_mensch"] >= ziel_p \
            and (bew.get("score") or 0) < ziel_score:
        # Modell-Ziel erreicht, nur der Score fehlt: nur die Hebel der gewichtigsten Kennzahlen, die die Lücke schließen
        fehlt = ziel_score - (bew.get("score") or 0)
        gsum = sum(max(0.0, float(z["gewicht"] or 0)) for z in bew["kennzahlen"] if z["bewertet"]) or 1.0
        offen = sorted((z for z in kz.values() if z["bewertet"] and z["status"] != "gruen" and z["seite"] == "ki"
                        and not (z["status"] == "gelb" and z.get("unsicher"))), key=lambda z: -(z["gewicht"] or 0))
        familien, punkte = [], 0.0
        for z in offen:
            punkte += 50.0 * max(0.0, float(z["gewicht"] or 0)) / gsum
            h = HEBEL_VON.get(z["id"])
            if h == "satzlaenge" and diag["modus"] == "teilen":
                h = "satzlaenge_bremse"
            if h and h not in familien:
                familien.append(h)
            if punkte >= fehlt:
                break
        teilziel = {"fehlt": round(fehlt, 1), "hebel": familien}
        eindeutig = [h for h in eindeutig if h["hebel"] in familien or h["hebel"] == "vorgaben"
                     or (h["typ"] == "teilen" and diag["ueberkorrektur"])]
        max_hinweise = min(max_hinweise, 8)
    stapel: dict[str, list[dict]] = {}
    for h in eindeutig:
        stapel.setdefault(h["hebel"], []).append(h)
    hebel_folge = sorted(stapel, key=lambda h: (h != "vorgaben", -hebel.get(h, {}).get("prioritaet", 0)))
    auswahl = []
    while len(auswahl) < max_hinweise and any(stapel.values()):
        for h in hebel_folge:
            if stapel[h] and len(auswahl) < max_hinweise:
                auswahl.append(stapel[h].pop(0))

    # Hebel-Anzeige: im TEILEN-Modus immer die Bremse statt „Lange Sätze ja … KI-Texte bleiben im mittleren Band“ – auch ohne
    # Teilen-Auftrag, sonst lädt der Hebeltext zu weiteren langen Sätzen ein
    if diag["modus"] == "teilen" and ("satzlaenge" in hebel or any(h["typ"] == "teilen" for h in hinweise)):
        alt = hebel.pop("satzlaenge", None)
        hebel.setdefault("satzlaenge_bremse", {"prioritaet": max(1.0, alt["prioritaet"] if alt else 0.0),
                                               "kennzahlen": [kz[k] for k in ("anteil_lange_saetze", "satzlaenge_mittel",
                                                                              "anteil_mittlere_saetze") if k in kz]})
    reihenfolge = sorted(hebel, key=lambda h: -hebel[h]["prioritaet"])
    daten = satzlaenge_daten(ref, ziel_vert)

    ersetzbar = sorted({w for h in auswahl for w in h.get("ersetzbar", [])})
    stand = {"score": bew.get("score"), "p_mensch": bew.get("p_mensch"),
             "kennzahlen": {z["id"]: {"wert": z["wert"], "status": z["status"]} for z in bew.get("kennzahlen", []) if z["bewertet"]},
             "roh": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in roh_jetzt.items()},
             "bloecke": [{k: b.get(k) for k in ("nr", "satz_von", "satz_bis", "p_mensch", "score")} for b in bloecke],
             "hinweise": [{"typ": h["typ"], "anfang": h["anfang"], "satz": h["satz"]} for h in auswahl],
             "ersetzbar": ersetzbar, "satzlaengen_modus": diag["modus"]}
    fortschritt = None
    if vorher:
        reihen = ["rot", "gelb", "gruen"]
        besser = [k for k, v in stand["kennzahlen"].items() if k in (vorher.get("kennzahlen") or {})
                  and reihen.index(v["status"]) > reihen.index(vorher["kennzahlen"][k]["status"])]
        schlechter = [k for k, v in stand["kennzahlen"].items() if k in (vorher.get("kennzahlen") or {})
                      and reihen.index(v["status"]) < reihen.index(vorher["kennzahlen"][k]["status"])]
        fortschritt = {"score_vorher": vorher.get("score"), "p_mensch_vorher": vorher.get("p_mensch"), "besser": besser, "schlechter": schlechter,
                       "messung_nr": len(verlauf["messungen"]) + 1,
                       "mechanisch_verlaengert": mechanisch_verlaengert(vorher.get("roh", {}), stand["roh"]),
                       "ueberkorrektur": ueberkorrektur, "ausgesetzt": sorted(ausgesetzt)}

    gruen = sorted([z for z in bew.get("kennzahlen", []) if z["bewertet"] and z["status"] == "gruen"], key=lambda z: -(z["gewicht"] or 0))
    diag_aus = {k: diag.get(k) for k in ("modus", "kontingent", "n", "lange", "mittlere", "kurze", "gruende", "abweichungen",
                                         "ueberkorrektur", "ueber_p90", "fehlende_mitte")}
    diag_aus.update({k: round(diag[k], 3) for k in ("anteil_lange", "anteil_mittlere", "anteil_kurze", "mittel", "schiefe") if diag.get(k) is not None})
    diag_aus["l1"] = round(diag["l1"], 3) if diag.get("l1") is not None else None
    ergebnis = {"info": erg["info"], "bewertung": {k: bew.get(k) for k in ("score", "p_mensch", "verfuegbar")},
                "hebel": [{"id": h, "name": HEBEL_TEXT[h][0], "warum": HEBEL_TEXT[h][1].format(satzlaenge_daten=daten),
                           "prioritaet": round(hebel[h]["prioritaet"], 2),
                           "kennzahlen": [{k: z.get(k) for k in ("id", "name", "wert", "mensch_p25", "mensch_p75", "ki_p50", "status", "richtung",
                                                                 "nur_modell", "beitrag")} for z in hebel[h]["kennzahlen"]]}
                          for h in reihenfolge if h in HEBEL_TEXT],
                "hinweise": auswahl, "anzahl_hinweise_gesamt": len(eindeutig),
                "rot": len(rot), "gut": [z["name"] for z in gruen[:4]], "stand": stand, "fortschritt": fortschritt,
                "ziel_p_mensch": ziel_p, "ziel_score": ziel_score, "ziel_rot_max": ziel_rot,
                "bloecke": bloecke, "blockmodus": bool(bew.get("blockmodus")),
                "fokus": {"block": fokus_block["nr"] if fokus_block else None, "satz_von": von, "satz_bis": bis},
                "satzlaengen": diag_aus, "ersetzbar": ersetzbar, "ziel_erreicht": ziel_erreicht, "teilziel": teilziel,
                "jenseits": jenseits,
                "fw_wert": fw["wert"] if fw else None}
    if roh:
        ergebnis["hinweise_roh"] = alle_roh
        ergebnis["hinweise_gefiltert"] = eindeutig
    return ergebnis


def satzlaenge_daten(ref: dict, ziel: dict) -> str:
    """Hebel-Text aus den Referenzdaten: Anteil langer/sehr langer Sätze und häufigste Klasse(n)."""
    try:
        lang = ref["anteil_lange_saetze"]["mensch"]["p50"]
        sehr = ref["anteil_sehr_lange_saetze"]["mensch"]["p50"]
    except KeyError:
        return "Menschen schreiben auch lange Sätze, aber nur etwa jeden sechsten."
    ordinal = {4: "vierte", 5: "fünfte", 6: "sechste", 7: "siebte", 8: "achte", 9: "neunte", 10: "zehnte"}.get(int(1 / lang) if lang else 6, "sechste")
    teil = f"Lange Sätze ja, aber nur etwa jeder {ordinal} (Menschen: ~{_pz(lang)} ≥ {LANG_AB} Wörter, ~{_pz(sehr)} ≥ {SEHR_LANG_AB}"
    if ziel:
        top = max(ziel.values())
        klassen = [k.replace("-", "–") for k, v in ziel.items() if abs(v - top) < 0.005]
        teil += f"; häufigste Klasse{'n' if len(klassen) > 1 else ''} {' und '.join(klassen)} Wörter"
    return teil + ")."


def fmt(x):
    return analyse.fmt(x).replace(".", ",") if isinstance(x, float) else str(x)


def bericht(c: dict) -> str:
    out = ["## Stil-Coach", ""]
    b, info = c["bewertung"], c["info"]
    kopf = f"{info['woerter']} Wörter · {info['saetze']} Sätze · {info['absaetze']} Absätze"
    if b.get("verfuegbar"):
        kopf += f" · **Score {b['score']}/100** · Modell: {round(100 * (b['p_mensch'] or 0))} % menschlich · {c['rot']} Kennzahlen rot"
    out.append(kopf)
    block_hinweis = getattr(analyse, "BLOCK_HINWEIS", None)
    for w in info["warnungen"]:
        out.append(f"\n> {'ℹ️' if block_hinweis and w.startswith(block_hinweis) else '⚠️'} {w}")
    f = c.get("fortschritt")
    if f:
        d = (b["score"] or 0) - (f["score_vorher"] or 0)
        out.append(f"\n**Fortschritt (Messung {f['messung_nr']}):** Score {f['score_vorher']} → {b['score']} ({'+' if d >= 0 else ''}{d})"
                   + (f" · besser: {', '.join(analyse.NAMEN.get(k, k) for k in f['besser'])}" if f["besser"] else "")
                   + (f" · schlechter: {', '.join(analyse.NAMEN.get(k, k) for k in f['schlechter'])}" if f["schlechter"] else ""))
        for u in f.get("ueberkorrektur") or []:
            aus = ", ".join(TYP_NAME.get(t, t) for t in u["aussetzen"])
            seit = f" (Messung {u['messung_vorher']})" if u.get("messung_vorher") else ""
            out.append(f"\n> ⚠️ **{u['art']}:** {u['name']} {fmt(u['vorher'])}{seit} → {fmt(u['wert'])}, jetzt {u['grenze']}."
                       + (f" Diese Runde ausgesetzt: {aus}." if aus else ""))
        if f.get("mechanisch_verlaengert"):
            out.append("\n> ⚠️ **Mechanisch verlängert:** Die Sätze sind länger geworden, aber Teilsätze und Satzklammern nicht – vermutlich angehängte Teilsätze. Das zählt nicht als Fortschritt; stattdessen nominal verdichten.")
    schon = {u["id"] for u in (f or {}).get("ueberkorrektur") or []}
    jenseits = [j for j in c.get("jenseits") or [] if j["id"] not in schon]
    if jenseits and not c["ziel_erreicht"]:
        out.append("\n> ⚠️ **Schon jenseits des menschlichen Bereichs:** "
                   + ", ".join(f"{j['name']} {fmt(j['wert'])} ({j['grenze']})" for j in jenseits)
                   + ". Diese Runde keine Verdichtungs-Hinweise (Bündeln, Satzklammer, Nebensatz → Nominalgruppe).")
    if c["blockmodus"] and c["bloecke"]:
        out.append("\n**Abschnitte** (lange Texte werden in Abschnitten zu ~800 Wörtern gemessen, wie die Referenz):\n")
        out.append("| Abschnitt | Sätze | Score | Modell |\n|---|---|---|---|")
        fokus_nr = (c.get("fokus") or {}).get("block")
        for bl in c["bloecke"]:
            marke = " ← am KI-nächsten, Hinweise unten" if bl["nr"] == fokus_nr else ""
            p = bl.get("p_mensch")
            out.append(f"| {bl['nr']} | {bl['satz_von']}–{bl['satz_bis']} | {bl.get('score')} | {round(100 * p) if p is not None else '–'} %{marke} |")
        if fokus_nr:
            fo = c["fokus"]
            out.append(f"\n_Die Hinweise betreffen nur Abschnitt {fokus_nr} (Satz {fo['satz_von']}–{fo['satz_bis']}). Danach erneut messen._")
    if c["ziel_erreicht"]:
        rot_teil = f", höchstens {c['ziel_rot_max']} Kennzahlen rot" if c.get("ziel_rot_max") is not None else ""
        out.append(f"\n✅ **Ziel erreicht:** Modell ≥ {round(100 * c['ziel_p_mensch'])} % menschlich, Score ≥ {round(c['ziel_score'])}{rot_teil} – so "
                   "unauffällig wie die meisten echten Hochschularbeiten. **Kein weiterer Handlungsbedarf.**"
                   + (" Ausnahme: Die Satzlängen sind über den menschlichen Bereich hinaus gewachsen – die Teilen-Hinweise unten nehmen "
                      "das zurück." if any(h["typ"] == "teilen" for h in c["hinweise"]) else "")
                   + (" Unten nur noch Vorgaben und sehr sichere Einzelstellen." if c["hinweise"] else ""))
    elif c.get("teilziel"):
        namen = ", ".join(HEBEL_TEXT[h][0] for h in c["teilziel"]["hebel"] if h in HEBEL_TEXT)
        out.append(f"\n_Modell-Ziel erreicht ({round(100 * c['ziel_p_mensch'])} % menschlich); dem Score fehlen noch {fmt(c['teilziel']['fehlt'])} "
                   f"Punkte bis {round(c['ziel_score'])}. Deshalb nur Hinweise zu: {namen or '–'}._")
    elif c["bewertung"].get("verfuegbar"):
        out.append(f"\n_Ziel: Modell ≥ {round(100 * c['ziel_p_mensch'])} % menschlich und Score ≥ {round(c['ziel_score'])}. Einzelne rote Kennzahlen sind normal – auch echte Arbeiten haben im Mittel mehrere._")
    sl = c.get("satzlaengen") or {}
    if sl.get("modus") == "teilen" and (sl.get("ueber_p90") or sl.get("fehlende_mitte")) \
            and not any(h["typ"] == "teilen" for h in c["hinweise"]):
        out.append(f"\n**Satzlängen:** {'; '.join(sl['gruende'])}. Keine weiteren Sätze verlängern oder bündeln.")
    elif sl.get("modus") and any(h["typ"] in ("buendeln", "teilen") for h in c["hinweise"]):
        abw = ", ".join(f"{k.replace('-', '–')} W.: {_pz(t)} statt {_pz(mz)}" for k, t, mz in sl.get("abweichungen", []))
        if sl["modus"] == "teilen":
            out.append(f"\n**Satzlängen:** {'; '.join(sl['gruende'])}. Keine weiteren Bündelungen; stattdessen einzelne lange Sätze teilen"
                       + (f" ({abw})." if abw else "."))
        else:
            out.append(f"\n**Satzlängen:** {sl['lange']} von {sl['n']} Sätzen haben ≥ {LANG_AB} Wörter; bis zum menschlichen Median (~15 %) fehlen "
                       f"{sl['kontingent']} lange Sätze – nicht mehr bündeln als unten genannt" + (f" ({abw})." if abw else "."))
    if c["hebel"] and not c["ziel_erreicht"]:
        out.append("\n### Die wichtigsten Hebel\n")
        for i, h in enumerate(c["hebel"][:4], 1):
            teile = []
            for k in h["kennzahlen"][:3]:
                if k.get("nur_modell"):
                    lage = "KI-nah, fließt ins Modell" if (k.get("wert") or 0) < 0 else "unter dem menschlichen Mittel, fließt ins Modell"
                    teile.append(f"{k['name']}: {fmt(k['wert'])} ({lage})")
                else:
                    teile.append(f"{k['name']}: {fmt(k['wert'])} (Ziel {fmt(k['mensch_p25'])}–{fmt(k['mensch_p75'])})")
            out.append(f"{i}. **{h['name']}** – {h['warum']}  \n   _{'; '.join(teile)}_")
    if c["hinweise"]:
        out.append("\n### Konkrete Stellen\n")
        allgemein = [h for h in c["hinweise"] if h["absatz"] is None]
        for h in allgemein:
            out.append(f"- {h['text']}")
        nach_absatz: dict[int, list[dict]] = {}
        for h in c["hinweise"]:
            if h["absatz"] is not None:
                nach_absatz.setdefault(h["absatz"], []).append(h)
        for nr in sorted(nach_absatz):
            out.append(f"\n**Absatz {nr}**")
            for h in sorted(nach_absatz[nr], key=lambda h: h["satz"] or 0):
                out.append(f"- {h['text']}")
        rest = c["anzahl_hinweise_gesamt"] - len(c["hinweise"])
        if rest > 0:
            out.append(f"\n_{rest} weitere Hinweise nach der nächsten Messung._")
    elif not c["ziel_erreicht"] and c["bewertung"].get("verfuegbar"):
        out.append("\n_Keine sicheren Einzelstellen gefunden – die Hebel oben beim eigenen Formulieren im Blick behalten._")
    if c["gut"]:
        out.append("\n**Schon gut:** " + ", ".join(c["gut"]) + ".")
    out.append("\n_Formuliere die Stellen selbst um und miss danach erneut (mit `--verlauf`, um den Fortschritt zu sehen)._")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datei")
    ap.add_argument("--verlauf", help="JSON-Datei für den Fortschritt (wird angelegt/fortgeschrieben)")
    ap.add_argument("--format", choices=["md", "json"], default="md")
    ap.add_argument("--max-hinweise", type=int, default=15)
    args = ap.parse_args(argv)
    verlauf = None
    if args.verlauf and os.path.exists(args.verlauf):
        with open(args.verlauf, encoding="utf-8") as f:
            verlauf = json.load(f)
    c = coache(analyse.lies_datei(args.datei), verlauf, args.max_hinweise)
    if args.verlauf:
        verlauf = verlauf or {"datei": os.path.abspath(args.datei), "messungen": []}
        verlauf["messungen"].append(c["stand"])
        with open(args.verlauf, "w", encoding="utf-8") as f:
            json.dump(verlauf, f, ensure_ascii=False, indent=1)
    if args.format == "json":
        json.dump(c, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print(bericht(c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
