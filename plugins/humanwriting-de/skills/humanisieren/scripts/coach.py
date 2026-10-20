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
   einer fremden Quelle zuschreibt; Aussagestatus (Befund/Vermutung/Fähigkeit) und Kausalität bleiben erhalten.
5. Keine fertigen Ersatzsätze für den Nutzertext; Technik-Beispiele nur an neutralen Beispielsätzen.
6. Keine Aufforderung, einzelne Wörter einzustreuen: Konstruktionen umbauen ja, Funktionswörter „nachfüllen“ nein.
7. Ehrlichkeit: Reichen Einzelkorrekturen für das Modellziel voraussichtlich nicht, sagt der Coach das (Diagnose mit
   den Modellbeiträgen) statt zu verstummen.

Jeder Umbau von Satzlängen und Absätzen wird vor der Ausgabe an den Kennzahlen simuliert; ein Wirksamkeitsgedächtnis
prüft im Verlauf, ob befolgte Aufträge ihre Zielkennzahl bewegt haben, und wechselt sonst die Technik. Je Satz gibt es
höchstens einen Auftrag (Nutzer-Vorgaben ausgenommen): treffen mehrere zu, fasst der Coach sie in fester Reihenfolge zusammen.

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
from typing import NamedTuple

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
    "satzlaenge": ("Satzlängen wie in echten Arbeiten verteilen", "{satzlaenge_daten} KI-Texte bleiben häufiger im mittleren Band."),
    "satzlaenge_bremse": ("Keine weiteren langen Sätze – einzelne teilen", "{satzlaenge_daten} Hier sind es mehr: Weiteres Bündeln würde vom menschlichen Bereich wegführen."),
    "satzklammer": ("Satzklammer füllen", "Bei Menschen stehen zwischen Hilfsverb und Partizip/Infinitiv mehr Wörter; Claude lagert Angaben in eigene Sätze oder Nebensätze aus."),
    "konnektoren": ("Weniger Konnektoren", "Claude nutzt deutlich mehr Satzverknüpfer (zugleich, hingegen, gleichwohl, zudem …) als Menschen. Streichen, nicht verschieben."),
    "funktionswoerter": ("Funktionswort-Profil", "Das Profil kleiner Wörter ist das stärkste Einzelsignal: Claude schreibt häufiger mit „sich“, „als“, „sie“, „dass“, „diese“, Menschen häufiger mit „es“, „auch“, „durch“, „wie“. Steuerbar über die genannten Konstruktionen, nicht durch Einstreuen."),
    "absaetze": ("Absätze ungleich lang machen", "Menschliche Absätze schwanken stark (mal 2, mal 7 Sätze), KI-Absätze sind gleichmäßiger."),
    "begriffe": ("Begriffe halten statt variieren", "Menschen nehmen den Begriff des Vorsatzes öfter wieder auf und bleiben bei einer Bezeichnung. Claude wechselt zwischen Synonymen und knüpft häufiger mit Possessiv an („Ihr …“, „Seine …“)."),
    "nebensaetze": ("Weniger Nebensätze, längere Teilsätze", "Claude hängt häufiger genau einen Nebensatz an (dass, weil, Relativsatz). Menschen packen dieselbe Information öfter in eine Nominalgruppe – die Teilsätze werden länger, der Satz nicht."),
    "semikolon": ("Semikolons ersetzen", "In menschlichen Hochschultexten kommen Semikolons kaum vor, Claude setzt sie regelmäßig."),
    "doppelpunkt": ("Doppelpunkte reduzieren", "Doppelpunkte mitten im Satz sind bei Claude häufiger als bei Menschen."),
    "floskeln": ("KI-Floskeln und -Konstruktionen ersetzen", "Diese Wendungen kommen in Claude-Texten mehrfach häufiger vor als in echten Hochschularbeiten. Ziel ist der menschliche Median, nicht null."),
    "wortwahl": ("Wortwahl einfacher und natürlicher", "Menschen nutzen mehr kurze Allerweltswörter und gängige Abkürzungen (z. B., bzw.). Ergibt sich meist aus den übrigen Hebeln."),
    "abkuerzungen": ("Übliche Abkürzungen stehen lassen", "Menschliche Hochschultexte nutzen gängige Abkürzungen (z. B., d. h., bzw., u. a., usw.). Claude schreibt sie fast immer aus."),
    "stimme": ("Eigene Stimme zeigen", "Menschliche Arbeiten zitieren öfter wörtlich, verwenden Klammern und manchmal „ich/wir“ oder „man“."),
}

# Datenbelege der Hebeltexte: (Kennzahl, erwartete Richtung „mensch“ = bei Menschen höher bzw. „ki“ = bei Claude höher,
# Format). hebel_warum() setzt die Mediane aus den Referenzwerten ein; ein Test prüft, dass jede Richtung den Daten entspricht.
HEBEL_BELEG = {
    "satzlaenge": ("anteil_mittlere_saetze", "ki", "Anteil 14–26 Wörter: Claude ~{k}, Menschen ~{m}", "pz"),
    "satzklammer": ("satzklammer_mittel", "mensch", "Median ~{m} statt ~{k} Wörter bei Claude", "z1"),
    "konnektoren": ("konnektoren_pro_1000", "ki", "je 1000 Wörter Median ~{k} statt ~{m}", "z0"),
    "absaetze": ("saetze_pro_absatz_cv", "mensch", "Variation der Sätze pro Absatz: Menschen ~{m}, Claude ~{k}", "z2"),
    "begriffe": ("anteil_saetze_mit_wortaufnahme", "mensch", "Sätze mit Wortaufnahme: Menschen ~{m}, Claude ~{k}", "pz"),
    "nebensaetze": ("teilsatz_verhaeltnis_21", "ki", "Sätze mit zwei Teilsätzen je Satz mit einem: Claude ~{k}, Menschen ~{m}", "z2"),
    "semikolon": ("semikolon_pro_1000", "ki", "je 1000 Wörter Median {m} bei Menschen, ~{k} bei Claude", "z1"),
    "doppelpunkt": ("doppelpunkt_pro_1000", "ki", "je 1000 Wörter Median ~{k} statt ~{m}", "z1"),
    "floskeln": ("ki_muster_pro_1000", "ki", "Gewicht je 1000 Wörter: Claude ~{k}, Menschen ~{m}", "z1"),
    "wortwahl": ("anteil_kurze_woerter", "mensch", "Anteil kurzer Wörter: Menschen ~{m}, Claude ~{k}", "pz"),
    "abkuerzungen": ("abkuerzungen_pro_1000", "mensch", "je 1000 Wörter Median ~{m} bei Menschen, {k} bei Claude", "z1"),
    "stimme": ("anfuehrungen_pro_1000", "mensch", "Anführungen je 1000 Wörter: Menschen ~{m}, Claude ~{k}", "z1"),
}


def _beleg_fmt(x: float, art: str) -> str:
    if art == "pz":
        return _pz(x)
    return f"{x:.{int(art[1])}f}".replace(".", ",")


def fw_typische(fw_profil: dict | None, n: int = 4) -> tuple[list[str], list[str]]:
    """Funktionswörter mit dem größten Verhältnis der Raten Claude/Mensch bzw. Mensch/Claude (aus dem Funktionswort-Profil)."""
    rm, rk = (fw_profil or {}).get("rate_mensch") or {}, (fw_profil or {}).get("rate_ki") or {}
    woerter = [w for w in (fw_profil or {}).get("woerter") or [] if rm.get(w) and rk.get(w)]
    ki = sorted((w for w in woerter if rk[w] > rm[w]), key=lambda w: -rk[w] / rm[w])
    mensch = sorted((w for w in woerter if rm[w] > rk[w]), key=lambda w: -rm[w] / rk[w])
    return ki[:n], mensch[:n]


def hebel_warum(h: str, ref: dict, daten: str = "", fw_profil: dict | None = None) -> str:
    """Hebeltext mit den Medianen aus den Referenzwerten; ohne Daten der feste Text."""
    text = HEBEL_TEXT[h][1].format(satzlaenge_daten=daten)
    if h == "funktionswoerter" and fw_profil:
        ki, mensch = fw_typische(fw_profil)
        if ki and mensch:
            text = (f"Das Profil kleiner Wörter ist das stärkste Einzelsignal: Claude schreibt häufiger mit {', '.join(f'„{w}“' for w in ki)}, "
                    f"Menschen häufiger mit {', '.join(f'„{w}“' for w in mensch)}. Steuerbar über die genannten Konstruktionen, nicht "
                    "durch Einstreuen.")
    if h == "konnektoren":
        stark = sorted((k for k in KONNEKTOR_KORPUS if (konnektor_verhaeltnis(k) or 0) > KONN_STARK), key=lambda k: -konnektor_verhaeltnis(k))
        # keine „menschlichen“ Konnektoren als Ersatz anpreisen: Austauschen wäre Wort-Einstreuen (Grundsatz 6) und senkt die
        # Konnektor-Dichte nicht
        text = (f"Claude nutzt mehr Satzverknüpfer als Menschen, vor allem {', '.join(f'„{k}“' for k in stark)} (mehr als doppelt so "
                f"häufig). Diese streichen, nicht verschieben und nicht durch einen anderen Konnektor ersetzen.")
    beleg = HEBEL_BELEG.get(h)
    if beleg and beleg[0] in ref and (ref[beleg[0]].get("ki") or {}).get("p50") is not None:
        r = ref[beleg[0]]
        m, k = r["mensch"]["p50"], r["ki"]["p50"]
        if (k > m) == (beleg[1] == "ki") and k != m:
            text += f" ({beleg[2].format(m=_beleg_fmt(m, beleg[3]), k=_beleg_fmt(k, beleg[3]))})"
    return text


# Hinweistyp -> Hebel (Gruppierung, Gewicht, Reihum-Auswahl)
FW_TYPEN = ("fw_ankuendigung", "fw_lassen", "fw_zeigt", "fw_ergibt", "fw_als", "fw_dass", "fw_dichte")
TYP_HEBEL = {
    "buendeln": "satzlaenge", "teilen": "satzlaenge_bremse", "kurz": "satzlaenge", "zickzack": "satzlaenge", "mitte": "satzlaenge",
    "klammer": "satzklammer", "klammer_zusatz": "satzklammer",
    "nebensatz": "nebensaetze", "kommas": "nebensaetze",
    "anknuepfung": "begriffe", "kein_bezug": "begriffe", "synonyme": "begriffe",
    **dict.fromkeys(FW_TYPEN, "funktionswoerter"),
    "floskel": "floskeln", "gegenfolie": "floskeln", "strohmann": "floskeln", "konnektor": "konnektoren",
    "semikolon": "semikolon", "doppelpunkt": "doppelpunkt", "abkuerzung": "abkuerzungen",
    "absatz_teilen": "absaetze", "absatz_zusammen": "absaetze",
    "gender": "vorgaben", "gedankenstrich": "vorgaben", "bindestrich": "vorgaben",
}
STRUKTURELL = {"buendeln", "teilen", "kurz", "zickzack", "mitte", "klammer", "klammer_zusatz", "nebensatz", "kommas"}
# Hinweistypen je Hebel, die einen Hebel tragen: sind sie alle ausgesetzt, zeigt der Bericht den Hebel als ausgesetzt
HEBEL_TYPEN = {"satzlaenge": {"buendeln", "zickzack", "mitte"}, "satzlaenge_bremse": {"teilen"},
               "satzklammer": {"klammer", "klammer_zusatz"}, "nebensaetze": {"nebensatz", "kommas"},
               "begriffe": {"anknuepfung", "kein_bezug", "synonyme"}, "funktionswoerter": set(FW_TYPEN),
               "floskeln": {"floskel", "gegenfolie", "strohmann"}, "konnektoren": {"konnektor"}, "absaetze": {"absatz_teilen", "absatz_zusammen"},
               "abkuerzungen": {"abkuerzung"}, "semikolon": {"semikolon"}, "doppelpunkt": {"doppelpunkt"}}
# erlaubte Alternative, wenn alle Hinweistypen eines Hebels ausgesetzt sind
ALTERNATIVE = {
    "satzlaenge": "Erlaubt bleibt: Satzlängen so lassen; nur dort teilen, wo unten ausdrücklich genannt.",
    "satzlaenge_bremse": "Erlaubt bleibt: keine weiteren Sätze verlängern oder bündeln.",
    "satzklammer": "Erlaubt bleibt: beim Neuformulieren Angaben zwischen Hilfsverb und Partizip stellen, ohne den Satz zu verlängern.",
    "nebensaetze": "Erlaubt bleibt: einen Einschub als eigenen Satz herauslösen (kürzt, statt zu verdichten).",
    "begriffe": "Erlaubt bleibt: bei einer Bezeichnung bleiben, aber keine weiteren Wiederholungen einbauen.",
    "funktionswoerter": "Erlaubt bleibt: einzelne Absätze mit demselben Inhalt in eigenen Worten neu schreiben.",
    "floskeln": "Erlaubt bleibt: die übrigen Wendungen stehen lassen.",
    "konnektoren": "Erlaubt bleibt: die übrigen Konnektoren stehen lassen.",
    "absaetze": "Erlaubt bleibt: die Absätze diese Runde so lassen.",
}

# Satzlängen-Klassen wie analyse.py (anteil_kurze/mittlere/lange/sehr_lange_saetze) – keine eigenen Schwellen
KURZ_MAX, MITTEL_VON, MITTEL_BIS, LANG_AB, SEHR_LANG_AB = 10, 14, 26, 30, 40
ZZ_KURZ_MAX, ZZ_LANG_AB = 15, 25  # Zickzack: absolute Klassen
MIN_WOERTER = 4  # kürzere „Sätze“ sind meist Fragmente der Satztrennung: keine Hinweise
VERDICHTUNG = 0.9  # Bündeln: zwei Sätze werden beim Verdichten etwa 10 % kürzer
MAX_TEILEN = 5
# „Mitte ausdünnen“: Sätze mit 22–26 Wörtern in zwei Sätze mit je ≤ 13 Wörtern teilen (beide verlassen die Klasse 14–26)
MITTE_SATZ_VON, MITTE_SATZ_BIS, MITTE_TEIL_MAX, MAX_MITTE = 22, 26, 13, 4
MODELL_HEBEL = -0.3  # Modellbeitrag, ab dem ein Merkmal auch im grünen/unsicheren Bereich inhaltsneutrale Aufträge bekommt
SCHON_GUT_AB = -0.1  # „Schon gut“ nur, wenn das Merkmal im Modell kaum Richtung KI zieht
ABSATZ_MIN_GEWINN = 0.03  # Absatz-Umbau nur, wenn die Sätze-pro-Absatz-Variation um mindestens so viel steigt
STAGNATION_P = 0.05  # p_mensch über zwei Runden weniger bewegt: ehrliche Diagnose statt weiterer Kleinarbeit

# Gender-Formen (Nutzer-Vorgabe generisches Maskulinum): substantivierte Partizipien auf -ende/-enden („Bewerbende“),
# Genderzeichen (*innen, :innen, _innen, /innen, Binnen-I) und Doppelnennungen („Kundinnen und Kunden“).
GENDER_PARTIZIP_RE = re.compile(r"(?<![\w-])((?:[A-ZÄÖÜ][\wäöüß]*-)*[A-ZÄÖÜ][a-zäöüß]+end)(en|e)(?![\wäöüß*:_/-])")
GENDER_ZEICHEN_RE = re.compile(r"(?<![\w-])([A-ZÄÖÜ][\wäöüß-]*?[a-zäöüß])(?:[*:_]innen|Innen|/-?innen|\(innen\))(?![\wäöüß])")
DOPPEL_RE = re.compile(r"(?<![\w-])([A-ZÄÖÜ][a-zäöüß]+?)innen\s+und\s+([A-ZÄÖÜ][a-zäöüß]+)(?![\wäöüß])"
                       r"|(?<![\w-])([A-ZÄÖÜ][a-zäöüß]+)\s+und\s+([A-ZÄÖÜ][a-zäöüß]+?)innen(?![\wäöüß])")
# Partizipien, die keine Gender-Form sind (übliche Wörter ohne -er-Form, Adjektive, Komposita mit „Ende“, „Spende“, „Wende“)
GENDER_AUSNAHME = {"folgend", "nachfolgend", "entsprechend", "fehlend", "bestehend", "entscheidend", "laufend", "lebend", "anwesend",
                   "abwesend", "sterbend", "heranwachsend", "auszubildend", "außenstehend", "leidtragend", "notleidend", "regierend",
                   "herrschend", "gebärend", "mitwirkend", "höchstbietend", "betreffend", "vorliegend", "zugrundeliegend", "kommend",
                   "bleibend", "wachsend", "zunehmend", "passend", "grundlegend", "weiterführend", "vergleichend", "schützend",
                   "vorhergehend", "übereinstimmend", "legend", "dividend", "gegend", "tugend", "referend", "abend", "spielend",
                   "dringend", "umfassend", "bedeutend", "ausreichend", "zutreffend", "bahnbrechend", "wegweisend", "leitend",
                   "koordinierend", "überzeugend", "zusammenfassend", "abschließend", "einleitend", "anschließend", "ergänzend",
                   "winnend", "andersdenkend", "sitzend", "führend", "nachdenkend", "ablehnend", "annehmend", "verrichtend",
                   "tötend", "hinterfragend", "fragend", "verarbeitend", "arbeitend", "versend"}
GENDER_AUSNAHME_ENDE = ("suchend", "reisend", "vorsitzend", "überlebend", "erziehend", "treibend", "begehrend", "spend", "wend", "tausend",
                        "dutzend", "wochenend", "jahresend", "monatsend", "kriegsend", "lebensend", "projektend", "studienend", "filmend",
                        "tagesend", "quartalsend", "semesterend", "schuljahresend", "qualifizierend", "entziehend", "schreitend",
                        "denkend", "schaffend", "leistend", "tugend", "gegend", "abend", "liegend")
# abgeleitete Maskulinform (Anzeige, Stamm für die Mischform-Suche); sonst Stamm ohne „-end“ + „er“ („Bewerbende“ → „Bewerber“)
GENDER_MASKULIN = {"studierend": ("Studenten", "Student"), "dozierend": ("Dozenten", "Dozent"), "promovierend": ("Doktoranden", "Doktorand"),
                   "absolvierend": ("Absolventen", "Absolvent"), "rezipierend": ("Rezipienten", "Rezipient"),
                   "demonstrierend": ("Demonstranten", "Demonstrant"), "kaufend": ("Käufer", "Käufer"), "pflegend": ("Pfleger", "Pfleger"),
                   "antwortend": ("Befragten", "Befragte"), "beantwortend": ("Befragten", "Befragte"), "lernend": ("Lerner", "Lerner"),
                   "vortragend": ("Referenten", "Referent"), "tragend": ("Träger", "Träger"), "fangend": ("Fänger", "Fänger"),
                   "tanzend": ("Tänzer", "Tänzer"), "singend": ("Sänger", "Sänger")}
# Übliche Personenbezeichnungen auf „-er“, die sich aus einem Partizip ableiten lassen („Teilnehmende“ → „Teilnehmer“). Nur diese
# werden als Ersatz genannt; sonst entstünden erfundene Wörter („Wartende“ → „Warter“, „Alleinstehende“ → „Alleinsteher“). Ein
# Kompositum zählt, wenn das Vorderglied kein Verbpräfix ist („Museumsmitarbeiter“, „Kursleiter“, nicht „Durchführer“).
GENDER_AGENS = set("""teilnehmer mitarbeiter arbeiter arbeitnehmer arbeitgeber auftraggeber geber nehmer lehrer forscher nutzer benutzer
leser helfer betreuer berater aussteller erzähler leiter sprecher zuschauer zuhörer beobachter unterstützer veranstalter gestalter
planer anbieter anwender verwender wähler mitforscher gründer vertreter prüfer raucher fahrer mitfahrer bewerber betrachter schreiber begleiter
besucher zahler bezieher erbringer übersetzer darsteller hersteller steller spender einsteiger aufsteiger umsteiger rückkehrer spieler
mitspieler werber lenker sender designer führer verdiener unterzeichner beisitzer mitstreiter mitwisser befrager bereitsteller sucher
trinker interviewer entwickler händler sammler kenner redner retter trainer leister kläger""".split())
_NEUTRUM_DAVOR = {"das", "im", "am", "vom", "zum", "beim", "ins", "aufs", "etwas", "nichts", "alles", "viel", "wenig", "vieles", "manches"}
# Genderzeichen-Formen starker Substantive: Plural nicht auf „-en“ („Ärzt*innen“ → „Ärzte“, nicht „Ärzten“)
GENDER_ZEICHEN_PLURAL = {"ärzt": "ärzte", "anwält": "anwälte", "köch": "köche", "freund": "freunde", "muslim": "muslime",
                         "bäuer": "bauern", "jüd": "juden", "nachbar": "nachbarn", "zuwander": "zuwanderer", "französ": "franzosen"}


def _agens_bekannt(m: str) -> bool:
    low = m.lower()
    return any(low == w or (low.endswith(w) and len(low) - len(w) >= 3 and low[:-len(w)] not in _PARTIKEL_PRAEFIX)
               for w in GENDER_AGENS)


def _maskulin(wort: str) -> tuple[str | None, str] | None:
    """Generisches Maskulinum zu einer Gender-Form (Anzeige oder None, Schlüssel). Bindestrich-Vorderglieder bleiben.
    None (statt Tupel): keine übliche Personenbezeichnung auf „-er“ ableitbar – dann ist das Partizip keine Gender-Form
    („Wartende“, „Alleinstehende“)."""
    teile = wort.split("-")
    vorne, letzt = teile[:-1], teile[-1]
    low = letzt.lower()
    for k, (anzeige, _st) in sorted(GENDER_MASKULIN.items(), key=lambda x: -len(x[0])):
        if low.endswith(k):
            m = low[:-len(k)] + anzeige.lower()
            break
    else:
        if low.endswith("ierend"):
            return None, low  # „Diskutierende“: keine sichere Ableitung
        m = low[:-3] + "er"
        if not _agens_bekannt(m):
            return None
    m = m[:1].upper() + m[1:]
    return "-".join(vorne + [m]), m.lower()


def _maskulin_zeichen(stamm: str) -> str:
    """Maskulinum zu „…*innen“: „Interviewpartner“, „Klienten/innen“ bleiben, „Autor“ → „Autoren“, „Kund“ → „Kunden“,
    „Ärzt“ → „Ärzte“, „Bibliothekar“ → „Bibliothekare“."""
    low = stamm.lower()
    for k, plural in GENDER_ZEICHEN_PLURAL.items():
        if low.endswith(k):
            vorne = stamm[:len(stamm) - len(k)]
            return vorne + (plural if vorne else plural[:1].upper() + plural[1:])
    if re.search(r"(?:er|ern|en|e)$", stamm):
        return stamm
    if stamm.endswith(("eur", "ar", "är")):
        return stamm + "e"
    return stamm + "en"


def gender_schluessel(maskulin: str) -> str:
    """Gruppenschlüssel einer Maskulinform über Flexionsformen hinweg („Nutzern“ = „Nutzer“, „Studenten“ = „Student“)."""
    low = maskulin.lower().split("-")[-1]
    return re.sub(r"(?<=er)n$|(?<=[^e])en$|(?<=e)n$", "", low)


def gender_funde(text: str) -> list[dict]:
    """Gender-Formen eines (maskierten) Satzes: Fundwort, Maskulinform (oder None) und Gruppenschlüssel."""
    out = []
    for m in GENDER_PARTIZIP_RE.finditer(text):
        wort = m.group(0)
        basis = m.group(1).lower()
        letzt = basis.split("-")[-1]
        inf = letzt[:-1]
        if len(inf) < 5 or not inf.endswith("en") or inf.endswith("een") or letzt in GENDER_AUSNAHME \
                or letzt.endswith(GENDER_AUSNAHME_ENDE):
            continue
        if re.search(r"(?:ngs|ts|rs|ns|[^i]en)$", letzt[:-3]):
            continue  # Kompositum mit „Ende“: „Ausbildungsende“, „Arbeitsende“, „Kursende“, „Lebensende“, „Tabellenende“
        vor = text[:m.start()].split()[-1:] or [""]
        nach = text[m.end():].split()[:1] or [""]
        if vor[0].lower().strip("„\"(") in _NEUTRUM_DAVOR or (nach[0][:1].isupper() and not nach[0][:1] in "„\"("):
            continue  # „das Folgende“, „im Wesentlichen“; attributiv vor einem Nomen („Steigende Preise“)
        abgeleitet = _maskulin(m.group(1))
        if abgeleitet is None:
            continue  # keine übliche Personenbezeichnung auf „-er“: keine Gender-Form („Wartende“, „Alleinstehende“)
        anzeige, schl = abgeleitet
        out.append({"wort": wort, "maskulin": anzeige, "schluessel": gender_schluessel(anzeige) if anzeige else letzt,
                    "start": m.start()})
    for m in GENDER_ZEICHEN_RE.finditer(text):
        stamm = m.group(1)
        mask = _maskulin_zeichen(stamm)
        out.append({"wort": m.group(0), "maskulin": mask, "schluessel": gender_schluessel(mask), "start": m.start()})
    for m in DOPPEL_RE.finditer(text):
        if m.group(1):
            fem, mask = m.group(1), m.group(2)
        else:
            mask, fem = m.group(3), m.group(4)
        if not mask.lower().startswith(fem.lower()[:max(3, len(fem) - 2)]):
            continue  # „Lehrerinnen und Schüler“: zwei verschiedene Gruppen
        out.append({"wort": m.group(0), "maskulin": mask, "schluessel": gender_schluessel(mask), "start": m.start()})
    return out


def ist_genderform(wort: str) -> bool:
    return bool(gender_funde(wort + " ."))


# wie analyse.py (konnektoren_pro_1000); „darüber hinaus“ läuft als KI-Muster
_KONN = getattr(analyse, "KONNEKTOREN", None)
KONNEKTOREN = [k for k in _KONN if isinstance(k, str)] if isinstance(_KONN, (list, tuple, set, frozenset)) else []
KONNEKTOREN = sorted(KONNEKTOREN, key=len, reverse=True) or ["zudem", "außerdem", "ferner", "des weiteren", "weiterhin", "folglich", "somit", "demnach",
               "infolgedessen", "allerdings", "jedoch", "dennoch", "gleichwohl", "nichtsdestotrotz", "insbesondere", "letztlich",
               "letztendlich", "zugleich", "gleichzeitig", "schließlich", "hingegen", "wiederum"]
KONNEKTOR_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in KONNEKTOREN) + r")\b", re.IGNORECASE)
# Konnektoren je 1000 Wörter Mensch / KI (Prosa-Sätze aus 1209 menschlichen und 412 KI-Abschnitten wie kalibriere.py,
# 1,10 Mio. bzw. 0,36 Mio. Wörter; Zählung mit genau KONNEKTOR_RE). Gemeldet wird nur, was bei Claude deutlich häufiger
# ist (Verhältnis > KONN_STARK); Konnektoren mit kleinerem Verhältnis nur bei Häufung im selben Absatz; was bei Menschen
# mindestens so häufig ist (Verhältnis ≤ 1, z. B. „außerdem“ 0,26), nie – Streichen würde ein menschliches Signal entfernen.
KONNEKTOR_KORPUS = {"zugleich": (0.145, 1.015), "gleichwohl": (0.032, 0.077), "hingegen": (0.216, 0.524),
                    "schließlich": (0.212, 0.447), "zudem": (0.620, 1.248), "demnach": (0.225, 0.428), "jedoch": (1.333, 2.380),
                    "insbesondere": (0.559, 0.812), "dennoch": (0.253, 0.340), "allerdings": (0.686, 0.861),
                    "letztlich": (0.099, 0.112), "infolgedessen": (0.015, 0.016), "wiederum": (0.199, 0.208),
                    "somit": (0.814, 0.842), "gleichzeitig": (0.282, 0.230), "folglich": (0.100, 0.082),
                    "weiterhin": (0.299, 0.173), "außerdem": (0.365, 0.093), "ferner": (0.067, 0.011),
                    "letztendlich": (0.076, 0.0), "nichtsdestotrotz": (0.009, 0.0)}
KONN_STARK = 2.0


def konnektor_verhaeltnis(wort: str) -> float | None:
    m, k = KONNEKTOR_KORPUS.get(re.sub(r"\s+", " ", wort.lower()), (0.0, 0.0))
    return k / m if m else None
HILFSVERBEN = set("""ist sind war waren sei seien wäre wären hat haben hatte hatten hätte hätten wird werden wurde wurden würde würden
kann können konnte konnten könnte könnten muss müssen musste mussten müsste müssten soll sollen sollte sollten will wollen wollte
wollten darf dürfen durfte durften dürfte dürften""".split())
KLAMMER_ENDE_HILFS = {"werden", "worden", "sein", "haben", "können", "müssen", "sollen", "dürfen", "wollen", "lassen", "gewesen", "geworden"}
# Ausgeschriebene Abkürzungen (Modellmerkmal abkuerzungen_pro_1000 zählt z. B., d. h., u. a., i. d. R., bzw., ggf., u. U., usw.,
# sog., ca. …; „vgl.“ zählt nicht). Nie am Satzanfang („Z. B. …“ liest sich schlecht), „das heißt“ nur nach Komma (sonst
# oft „das heißt nicht, dass …“), „etwa/rund“ nur vor Zahlen, „vergleiche“ nur in Klammern (sonst das Nomen „Vergleiche“).
ABK_ERSATZ = [
    (re.compile(r"\bzum Beispiel\b"), "z. B.", True), (re.compile(r"\bbeispielsweise\b"), "z. B.", True),
    (re.compile(r"(?<=,\s)das heißt\b"), "d. h.", True), (re.compile(r"\bunter anderem\b"), "u. a.", True),
    (re.compile(r"\bin der Regel\b"), "i. d. R.", True), (re.compile(r"\bbeziehungsweise\b"), "bzw.", True),
    (re.compile(r"\bgegebenenfalls\b"), "ggf.", True), (re.compile(r"\bunter Umständen\b"), "u. U.", True),
    (re.compile(r"\bund so weiter\b"), "usw.", True), (re.compile(r"\bsogenannte[nmrs]?\b"), "sog.", True),
    (re.compile(r"\b(?:circa|etwa|rund)(?=\s+\d)"), "ca.", True), (re.compile(r"(?<=\()vergleiche\b"), "vgl.", False),
]

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
            "gründer", "investoren", "anleger", "probanden", "personen", "menschen", "akteure", "beteiligte", "unternehmer",
            "hebamme", "hebammen", "präsident", "minister", "politiker", "lehrer", "ärzte", "arzt", "pfleger", "student", "studenten",
            "doktorand", "doktoranden", "experte", "befragten", "interviewte", "interviewten", "sprecher", "vertreter", "leiter",
            "inhaber", "eigentümer", "kollege", "kollegen", "mitglied", "mitglieder", "fachkraft", "fachkräfte", "angestellte",
            "angestellten", "beamte", "beamten", "jugendliche", "jugendlichen", "frauen", "männer", "mutter", "vater", "mütter",
            "väter", "bürger", "einwohner", "wähler", "händler", "mediziner", "juristen", "wissenschaftler", "praktiker")
# weibliche Personenbezeichnungen auf -in („Präsidentin“, „Autorin“, „Ärztin“, „Kapitänin“, „Kollegin“)
PERSON_IN_RE = re.compile(r"(?:er|or|ent|ant|ist|eur|är|än|t|g)in(?:nen)?$")


def ist_person(wort: str) -> bool:
    low = wort.lower()
    return any(low == p or low.endswith(p) for p in PERSONEN) or (len(low) > 5 and bool(PERSON_IN_RE.search(low)))
LEICHTE_NOMEN = {"jahr", "jahre", "jahren", "jahres", "prozent", "beispiel", "rahmen", "zusammenhang", "hinblick", "bezug", "sinne",
                 "folge", "weise", "teil", "fall", "fälle", "ende", "anfang", "januar", "februar", "märz", "april", "mai", "juni", "juli",
                 "august", "september", "oktober", "november", "dezember", "laufe", "grund", "basis", "hilfe", "form", "art"}
ANAPHER_RE = re.compile(r"^(?:dies|diese[rsmn]?|sie|er|es|ihm|ihn|ihnen|dabei|dadurch|damit|daher|hierbei|so|denn|deshalb|beide[sn]?|"
                        r"letztere[rsn]?|erstere[rsn]?|ähnliches|gleiches|derartige[rsn]?|jene[rsmn]?|" + "|".join(POSSESSIV) + r")\b",
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
ZEIGT_SICH_RE = re.compile(r"\b(?:zeigt|zeigen|zeigte|zeigten)\s+sich\b", re.IGNORECASE)
ERGIBT_SICH_RE = re.compile(r"\b(?:ergibt|ergeben|ergab|ergaben)\s+sich\b", re.IGNORECASE)
# Ankündigung vor einem dass-Satz: ein einziger Auftrag „Ankündigung streichen, Aussage als Hauptsatz“ (kein „kann … werden“,
# kein dass-Satz-Hinweis). „ableiten“ trägt eine Folgerung: sie bleibt mit „daher“/„also“ erkennbar. „schließen“ bleibt draußen.
ANKUENDIGUNG_RE = re.compile(
    r"\b(?:lässt|lassen)\s+sich\s+(?:\w+\s+){0,2}?(?:festhalten|feststellen|sagen|zusammenfassen|konstatieren|resümieren|ableiten)\s*,\s*dass\b"
    r"|\b(?:kann|können)\s+(?:\w+\s+){0,2}?(?:festgehalten|festgestellt|gesagt|zusammengefasst|konstatiert|resümiert|abgeleitet)"
    r"\s+werden\s*,\s*dass\b"
    r"|\b(?:ist|bleibt)\s+(?:\w+\s+){0,2}?(?:festzuhalten|festzustellen|zu\s+konstatieren)\s*,\s*dass\b", re.IGNORECASE)
ANKUENDIGUNG_FOLGERUNG = ("kündigt nur an – streichen und die Aussage als Hauptsatz schreiben; die Folgerung bleibt mit „daher“ oder "
                          "„also“ erkennbar (Beispiel: „Daraus lässt sich ableiten, dass die Kosten steigen.“ → „Die Kosten steigen daher.“)")
_W = r"[^\s,.;:()]+"
DIENT_ALS_RE = re.compile(rf"\b(?:dient|dienen|diente|dienten|fungiert|fungieren|fungierte|fungierten)\b(?:\s+{_W}){{0,6}}?\s+als\b"
                          rf"|\bals\s+(?:{_W}\s+){{1,4}}?(?:dienen|dient|diente|dienten|fungieren|fungiert|fungierte|fungierten)\b", re.IGNORECASE)
VERSTEHT_SICH_ALS_RE = re.compile(rf"\b(?:versteht|verstehen|verstand|verstanden)\s+sich\b(?:\s+{_W}){{0,4}}?\s+als\b", re.IGNORECASE)
GILT_ALS_RE = re.compile(rf"\b(?:gilt|gelten|galt|galten)\b(?:\s+{_W}){{0,4}}?\s+als\b", re.IGNORECASE)
ZUSCHREIBUNG_RE = re.compile(r"\b(?:nach|laut|gemäß|zufolge|im Sinne|Definition|definier\w*)\b|\d", re.IGNORECASE)
REDEVERB_KURZ_RE = re.compile(r"\b(?:zeig(?:t|en|te|ten)|gezeigt|beton\w*|unterstreich\w*|verdeutlich\w*|belegt|belegen|"
                              r"mach(?:t|en)\s+deutlich)\b[^.;,]*?,\s*dass\s+(?P<rest>[^,;]*)", re.IGNORECASE)
# Funktionswort-Konstruktionen, die am Korpus KI-typisch sind: Vorkommen je 1000 Wörter Mensch / KI mit genau diesen Regexen
# (Prosa-Sätze aus 1209 menschlichen und 412 KI-Abschnitten, 1,10 Mio. bzw. 0,36 Mio. Wörter). Aufgenommen nur bei
# Verhältnis ≥ 1,5. Nicht KI-typisch und deshalb ohne Hinweis: „als … bezeichnet“ (0,98), „handelt sich um“ (0,97),
# „bezieht sich auf“ (1,25), „Sie“ (1,33) bzw. „Diese“ (1,05) am Satzanfang. KI-typisch, aber wegen des Aussagestatus
# ausgelassen: „erweist sich als“ (7,9; Befund) und „lässt sich schließen, dass“ (Folgerung). „lässt sich ableiten, dass“
# gehört zur Ankündigung (Verhältnis mit „ableiten“ 1,77), der Auftrag hält die Folgerung mit „daher/also“ fest.
FW_KORPUS = {"ankuendigung": (0.121, 0.214), "laesst_sich": (0.673, 2.380), "zeigt_sich": (0.296, 0.828),
             "ergibt_sich": (0.215, 0.702), "dient_als": (0.154, 0.535), "versteht_sich_als": (0.006, 0.047),
             "gilt_als": (0.085, 0.263), "redeverb_dass": (0.372, 0.856)}
# Wörter, die bei Claude seltener sind als bei Menschen: nie einstreuen lassen, aber Hinweise unterdrücken, die sie entfernen
SCHUTZ_WOERTER = {"werden", "es", "um", "auch", "durch", "wie"}

# „wenn“ als Bedingung; „wenn auch/gleich/überhaupt/schon“ ist einräumend bzw. elliptisch („…, wenn auch nicht immer …“)
WENN_BEDINGUNG = r"wenn(?!\s+(?:auch|gleich|überhaupt|schon|nicht\s+gar)\b)"

# Nebensätze mit genau einem Nebensatz, nach Umbaubarkeit sortiert: (Name, Regex, Technik, Hinweis zum Aussagestatus).
# „sodass“, „so dass“, „wodurch“, „wobei“ fehlen: eine Folge bzw. ein loser Bezug lässt sich kaum ohne Änderung der Kausalität
# in eine Nominalgruppe fassen (v2: „sodass“ → „angesichts“). Relativsätze nur mit Nominativ-Pronomen (nicht dem/den/deren/
# dessen/denen: Objekt- oder Genitiv-Relativsätze ergeben kein Partizipialattribut).
NEBENSATZ_TYPEN = [
    ("dass", re.compile(r",\s+dass\b"), "den „dass“-Satz als Nominalgruppe fassen (Beispiel: „zeigt, dass die Kosten steigen“ → „zeigt "
     "den Anstieg der Kosten“)", "Aussagestatus erhalten: ein Befund bleibt ein Befund, eine Vermutung eine Vermutung"),
    ("weil", re.compile(r",\s+(?:weil|da)\b|^(?:Weil|Da)\s"), "den „weil/da“-Satz als Präpositionalgruppe fassen (Beispiel: „da Daten "
     "fehlen“ → „wegen fehlender Daten“)", "die Begründung bleibt eine Begründung („wegen“, „aufgrund“), nicht „mit“ oder „bei“"),
    ("relativ", re.compile(r",\s+(?:der|die|das|welche[rs]?)\s"), "den Relativsatz als vorangestelltes Partizipialattribut fassen "
     "(Beispiel: „die Daten, die erhoben wurden“ → „die erhobenen Daten“)", ""),
    ("sonst", re.compile(rf",\s+(?P<w>indem|{WENN_BEDINGUNG}|nachdem|obwohl)\b"),
     "den „{w}“-Satz als Präpositionalgruppe fassen (Beispiel: {bsp})",
     "die Verknüpfung ({art}) bleibt erkennbar"),
]
NEBENSATZ_BEISPIEL = {"indem": ("„indem Kosten gesenkt werden“ → „durch Kostensenkung“", "Mittel"),
                      "wenn": ("„wenn Daten fehlen“ → „bei fehlenden Daten“", "Bedingung"),
                      "nachdem": ("„nachdem das Gesetz in Kraft trat“ → „nach Inkrafttreten des Gesetzes“", "Zeitfolge"),
                      "obwohl": ("„obwohl die Kosten steigen“ → „trotz steigender Kosten“", "Einräumung")}
NEBENSATZ_MAX = 12  # dass-/weil-/Adverbialsatz: längere Sätze ergeben beim Nominalisieren Ketten aus vier und mehr Nomen
RELATIV_MAX = 6  # Relativsatz (mit Pronomen): sonst wird das vorangestellte Attribut zu lang
_ARTIKEL_VOR = (r"der|die|das|den|dem|des|ein|eine|einer|eines|einem|einen|diese[rsmn]?|jene[rsmn]?|alle|viele|solche[rsmn]?|"
                r"keine[rsmn]?|zahlreiche[n]?|einige[n]?|mehrere[n]?|beide[n]?|ihre[rsmn]?|seine[rsmn]?|unsere[rsmn]?|jede[rsmn]?|"
                r"manche[rsmn]?|bestimmte[n]?|andere[n]?|weitere[n]?")
# Bezugswort eines Relativsatzes: Gattungsnomen mit Artikel/Begleiter, dazwischen höchstens drei kleingeschriebene Wörter
BEZUG_GATTUNG_RE = re.compile(rf"(?:^|\s)(?i:{_ARTIKEL_VOR})\s+(?:[a-zäöüß][\w-]*\s+){{0,3}}(?P<n>[A-ZÄÖÜ][\w-]*)\s*$")
_AUX_SEIN = {"ist", "sind", "war", "waren", "sei", "seien", "wäre", "wären"}
_AUX_HABEN = {"hat", "haben", "hatte", "hatten", "habe", "hätte", "hätten"}
_ADJ_ENDE = re.compile(r"(?:bar|lich|ig|isch|sam|haft|los|iv|al|ell|är|ent|ant)$")
_PRONOMEN_SUBJ = {"ich", "wir", "er", "sie", "es", "man", "du", "ihr"}
_KONJUNKTIV = {"würde", "würden", "wäre", "wären", "hätte", "hätten"}
# handelnde Subjekte im Nebensatz: beim Nominalisieren den Akteur behalten („durch die Führung“, Genitiv)
AKTEURE = ("unternehmen", "führung", "management", "leitung", "staat", "gesetzgeber", "kommission", "regierung", "organisation",
           "betrieb", "betriebe", "händler", "anbieter", "team", "teams", "verwaltung", "politik", "gericht", "behörde", "behörden",
           "hochschule", "schule", "verband", "verbände", "bank", "banken", "konzern", "konzerne", "firma", "firmen")
REDEVERB_DASS_RE = re.compile(r"\b(?:zeig\w*|gezeigt|argumentier\w*|beton\w*|hingewiesen|hinweis\w*|weis\w*|wies\w*|feststell\w*|festgestellt|"
                              r"belegt|beleg\w*|nachgewiesen|annehmen|angenommen|vermut\w*|erwart\w*|konstatier\w*|herausgestellt|herausgefunden|"
                              r"schließ\w*|geschlossen|folger\w*|gefolgert|ableit\w*|abgeleitet|"
                              r"darauf|davon|daran|dafür|darüber|dazu|daraus|darin|damit)\b[^.;]*?,\s*(?:dass|ob|wie)\b", re.IGNORECASE)
# nur Adverbialsätze, die sich ohne Bedeutungsänderung als Angabe ins Mittelfeld stellen lassen (Zweck, Mittel, Grund,
# Bedingung, Zeit). Nicht: adversatives „während“, konzessives „obwohl“, konsekutives „sodass/wodurch/womit“ – ein Gegensatz
# oder eine Folge in der Klammer der Hauptaussage verfälscht diese. Ein Objektsatz („schließen, dass …“) gehört ohnehin nicht dorthin.
KLAMMER_QUELLE_RE = re.compile(rf",\s+(?P<w>um|indem|ohne|weil|da|{WENN_BEDINGUNG}|nachdem|bevor|sobald)\b")
ANGABE_ANFANG = analyse.PRAEPOSITIONEN | {"im", "am", "beim", "vom", "zum", "zur", "ins", "seit", "bis", "während", "dort", "hier", "damals",
                                          "heute", "zuletzt", "zuvor", "anschließend", "danach", "inzwischen", "bereits", "erst"}

# Teilen an einer inhaltlichen Wende: Semikolon, Doppelpunkt vor Großschreibung, Komma vor Konjunktion oder Relativpronomen
_TEIL_KONJ = r"(?:sondern|aber|doch|jedoch|wobei|sodass|so dass|während|weil|da|denn|womit|wodurch|weshalb|wenngleich|obwohl|und|oder|indem|nachdem|wenn)"
TEIL_RE = re.compile(rf";\s+|:\s+(?=[A-ZÄÖÜ])|,\s+(?={_TEIL_KONJ}\b)|,\s+(?=(?:der|die|das|dem|den|deren|dessen|denen|welche[rsmn]?)\s)")
# „Mitte ausdünnen“ braucht eine Fuge nahe der Mitte: zusätzlich Relativsatz mit „was“ oder Präposition, Erläuterung
# („, etwa …“), Zeit-/Zwecksätze und „und“ vor einem finiten Verb (zweites Prädikat desselben Subjekts)
_FINIT_ALLE = "|".join(sorted(analyse.FINIT | analyse.FINIT_MEHRDEUTIG)) if hasattr(analyse, "FINIT") else "ist|sind|wird|werden|kann|können"
MITTE_TEIL_RE = re.compile(
    TEIL_RE.pattern + r"|,\s+(?=(?:was|womit|wodurch|worauf|woraus|worin|weshalb)\b)"
    r"|,\s+(?=(?:in|an|auf|mit|bei|für|von|zu|aus|nach|über|unter|durch|gegen|um|vor|zwischen)\s+(?:der|dem|den|denen|dessen|deren|welche[rsmn]?)\s)"
    r"|,\s+(?=(?:etwa|nämlich|also|insbesondere|darunter|vor allem)\b)|,\s+(?=(?:bevor|ehe|sobald|solange|seit|seitdem|damit|um)\s)"
    rf"|\s(?=und\s+(?:{_FINIT_ALLE})\b)")
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
# Unbewertete Kennzahlen (Lesbarkeit, Hedging) setzen nur aus, wenn sie rot werden; bewertete auch bei Gelb, sofern sie sich
# um ≥ 0,5 IQR verschoben haben (sonst sperren kleine Ausschläge ganze Hebel). Schiefe auf der KI-Seite sperrt Bündeln nur,
# wenn lange Sätze nicht ohnehin fehlen (anteil_lange_saetze ≥ P50); sonst würde genau ein langer Satz helfen.
WAECHTER = {
    "satzlaenge_mittel": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen", "kurz", "mitte"}},
    "satzlaenge_median": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen", "kurz", "mitte"}},
    "anteil_lange_saetze": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen"}},
    "anteil_sehr_lange_saetze": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen"}},
    "anteil_mittlere_saetze": {"gegen": {"buendeln", "kurz", "klammer_zusatz", "mitte"}, "ki": {"teilen"}},
    "anteil_kurze_saetze": {"gegen": {"buendeln", "klammer", "klammer_zusatz"}, "ki": {"kurz", "teilen", "mitte"}},
    "satzlaenge_schiefe": {"gegen": {"kurz"}, "ki": {"buendeln"}},
    # Rhythmus auf der KI-Seite sperrt das Bündeln nicht mehr nachträglich: laengen_gewinn() wertet Kandidaten ab, die einen
    # Kurz-Lang-Wechsel erzeugen, und verwirft nur solche, die den Rhythmus rot machen
    "rhythmus_r1_log": {"gegen": {"zickzack"}},
    "lix": {"gegen": _VERDICHTEN, "ki": {"teilen", "kurz", "mitte"}},
    "wiener_sachtextformel": {"gegen": _VERDICHTEN, "ki": {"teilen", "kurz", "mitte"}},
    "flesch_amstad": {"gegen": _VERDICHTEN, "ki": {"teilen", "kurz", "mitte"}},
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
            "gegenfolie": "Gegenfolie", "strohmann": "Gegenposition samt Abweisung", "mitte": "Mittellange Sätze teilen",
            "abkuerzung": "Abkürzungen", "bindestrich": "Bindestrich mit Leerzeichen",
            "nebensatz_relativ": "Passiv-Relativsatz → Partizip", "nebensatz_werden": "Nebensatz mit „werden“ → Nominalgruppe",
            "fw_ankuendigung": "Ankündigung streichen", "fw_lassen": "„lässt sich“ umbauen", "fw_zeigt": "„zeigt sich“ umbauen",
            "fw_ergibt": "„ergibt sich“ umbauen", "fw_als": "„als“-Zuschreibung umbauen", "fw_dass": "kurzer „dass“-Satz → Nominalgruppe",
            "fw_dichte": "Funktionswort-Dichte"}
# „zickzack“ verlangt „Satz X mit X+1 verbinden“ und zählt deshalb wie Bündeln
GEGENTEIL = {"buendeln": {"teilen", "kurz", "kommas", "mitte"}, "teilen": {"buendeln", "klammer_zusatz", "zickzack"},
             "kurz": {"buendeln", "zickzack"}, "klammer_zusatz": {"teilen", "mitte"}, "kommas": {"buendeln", "zickzack"},
             "zickzack": {"teilen", "kurz", "kommas", "mitte"}, "mitte": {"buendeln", "zickzack", "klammer_zusatz"},
             "absatz_teilen": {"absatz_zusammen"}, "absatz_zusammen": {"absatz_teilen"}}
# Wirksamkeitsgedächtnis: welche Kennzahl ein Hinweistyp bewegen soll (gemessen wird der Abstand zum menschlichen Median)
ZIEL_KENNZAHL = {"absatz_teilen": "saetze_pro_absatz_cv", "absatz_zusammen": "saetze_pro_absatz_cv",
                 "buendeln": "anteil_mittlere_saetze", "mitte": "anteil_mittlere_saetze", "teilen": "anteil_lange_saetze",
                 "zickzack": "rhythmus_r1_log", "klammer": "satzklammer_mittel", "klammer_zusatz": "satzklammer_mittel",
                 "nebensatz": "teilsatz_verhaeltnis_21", "kommas": "woerter_pro_teilsatz", "abkuerzung": "abkuerzungen_pro_1000",
                 "konnektor": "konnektoren_pro_1000", "anknuepfung": "anteil_saetze_mit_wortaufnahme",
                 "kein_bezug": "anteil_saetze_mit_wortaufnahme", **dict.fromkeys(FW_TYPEN, "fw_profil_llr_pro_1000")}
# Technikwechsel statt bloßem Aussetzen, wenn ein befolgter Auftrag seine Kennzahl nicht bewegt hat
TECHNIK_WECHSEL = {"absatz_teilen": "absatz_zusammen", "absatz_zusammen": "absatz_teilen"}
ZIEL_TYPEN = {"gender", "gedankenstrich", "bindestrich", "semikolon", "floskel"}  # bei „Ziel erreicht“ (Muster nur mit Gewicht ≥ 1,5)
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


def _synonym_gruppen(worte) -> set[int]:
    """Indizes der SYNONYM_GRUPPEN (ohne die Grundwort-Gruppen), deren Wort im Satz vorkommt – allein oder als Teil eines
    Kompositums („Studienlage“ – „Untersuchungen“)."""
    out = set()
    for w in worte:
        low = w.lower()
        for gi, (gruppe, nur_kopf) in enumerate(SYNONYM_GRUPPEN):
            if nur_kopf:
                continue
            if any(low.startswith(g) or any(low.endswith(g + fl) for fl in _FLEXION) for formen in gruppe.values() for g in formen):
                out.add(gi)
    return out


def satz_begriffe(text: str, aliase: list[tuple[set, set]] | None = None) -> dict:
    """Inhaltsstämme, Kompositum-Grundformen (auch Bindestrich-Bestandteile), Akronyme, Initialen, Synonymgruppen und
    Gleichsetzungen „A (B)“ aus dem Text (aliase) eines Satzes – für die Bezugsprüfung."""
    toks = analyse.tokens(text)
    worte = [w for w in toks if analyse.ist_wort(w) and w.lower() not in analyse.FUNKTIONSWOERTER and len(w) > 2]
    teile = [t for w in worte if "-" in w for t in w.split("-") if len(t) >= 4]
    folge = [w for w in toks if analyse.ist_wort(w) and w.lower() not in _INITIALEN_FUELL]
    initialen = set()
    for i in range(len(folge)):
        for j in range(i + 2, min(len(folge), i + 6) + 1):
            initialen.add("".join(x[0] for x in folge[i:j]).upper())
    staemme = analyse.inhaltsstaemme(toks)
    return {"staemme": staemme, "grund": {_grund(w) for w in worte + teile if len(w) >= 5},
            "roh": {w.lower() for w in worte + teile if len(w) >= 5},
            "akronyme": {w.rstrip("s") for w in toks if re.fullmatch(r"[A-ZÄÖÜ]{2,6}s?", w)}, "initialen": initialen,
            "syn": _synonym_gruppen([w for w in worte if w[:1].isupper()]),
            "alias": {i for i, (sa, sb) in enumerate(aliase or []) if staemme & (sa | sb)}}


# Ableitungssuffixe sind kein gemeinsames Grundwort („Wissenschaft“ – „Gesellschaft“, „Planung“ – „Haltung“)
_ABLEITUNG = ("schaft", "ierung", "ation", "ität", "heit", "keit", "ismus", "ung", "lich", "isch", "ion", "ik", "ie", "ur", "ment",
              "nis", "tum")


def gemeinsames_grundwort(x: str, y: str) -> bool:
    """Gemeinsames Suffix ≥ 5 Zeichen zweier Grundformen, das nach Abzug eines Ableitungssuffixes noch ≥ 4 Zeichen hat
    („Autonomieerleben“ – „Kompetenzerleben“)."""
    n = 0
    while n < min(len(x), len(y)) and x[-1 - n] == y[-1 - n]:
        n += 1
    if n < 5:
        return False
    rest = x[-n:]
    for suf in _ABLEITUNG:
        if rest.endswith(suf):
            rest = rest[:-len(suf)]
            break
    return len(rest) >= 4


def verbunden(a: dict, b: dict) -> str | None:
    """Teilen zwei Sätze einen Begriff – direkt, als Kompositum (gleiches Grundwort, gemeinsames Präfix ≥ 6, Bestimmungswort),
    als Akronym und Langform, als Synonym (SYNONYM_GRUPPEN) oder über eine Gleichsetzung „A (B)“ im Text?"""
    if a["staemme"] & b["staemme"]:
        return "stamm"
    for x in a["grund"]:
        for y in b["grund"]:
            if min(len(x), len(y)) >= 5 and (x.endswith(y) or y.endswith(x)):
                return "kompositum"  # gleiches Grundwort („Berichterstattung“ – „Nachhaltigkeitsberichterstattung“)
            if len(x) >= 6 and len(y) >= 6 and x[:6] == y[:6]:
                return "kompositum"
            if gemeinsames_grundwort(x, y):
                return "kompositum"
    for x in a.get("roh", ()):
        for y in b.get("roh", ()):
            if x != y and (x.startswith(y) or y.startswith(x)):
                return "kompositum"  # Bestimmungswort („Preis“ – „Preissetzung“)
    if (b["akronyme"] & a["initialen"]) or (a["akronyme"] & b["initialen"]):
        return "akronym"
    if a.get("syn", set()) & b.get("syn", set()):
        return "synonym"
    if a.get("alias", set()) & b.get("alias", set()):
        return "gleichsetzung"
    return None


DEFINITION_RE = re.compile(r"((?:[\wÄÖÜäöüß-]+\s+){0,2}[A-ZÄÖÜ][\w-]*)\s+\(([^()]{2,60})\)")


def gleichsetzungen(saetze: list[dict]) -> list[tuple[set, set]]:
    """„A (B)“-Gleichsetzungen im Text („dynamische Preissetzung (Dynamic Pricing)“): je Paar die Inhaltsstämme beider
    Seiten. Quellenangaben, Zahlen und „z. B.“-Klammern zählen nicht."""
    out = []
    for s in saetze:
        for m in DEFINITION_RE.finditer(s["text"]):
            b = m.group(2).strip()
            if re.search(r"\d|\b(?:vgl|z\.\s?B|ebd|s\.|S\.|etwa|u\.\s?a)\b", b) or not re.search(r"[A-ZÄÖÜ]", b):
                continue
            sa = analyse.inhaltsstaemme(analyse.tokens(m.group(1)))
            sb = analyse.inhaltsstaemme(analyse.tokens(b))
            if sa and sb and not (sa & sb):
                out.append((sa, sb))
    return out


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


# „-ik“ erst ab fünf Buchstaben („Logik“, „Politik“), sonst Vornamen wie „Erik“
NOMEN_SUFFIX_RE = re.compile(r"(?:ung|heit|keit|schaft|ion|tät|ismus|nahme|(?<=\w{3})ik|ie|enz|anz|ment|nis|tum|ur|ei|isse|ität)(?:en|n|e|s)?$")
FEMININ_RE = re.compile(r"(?:ung|ion|tät|heit|keit|ie|(?<=\w{3})ik|schaft|enz|anz|ur|ei|richtlinie|directive|verordnung|norm|regel)$")
PLURAL_RE = re.compile(r"(?:ungen|ionen|täten|heiten|keiten|schaften|ien|iken|nisse|enzen|anzen|eure|isten|enten|anten|innen|daten|"
                       r"[^suinrtx]s)$")
PLURAL_MOEGLICH_RE = re.compile(r"(?:en|n|e|er)$")  # Plural möglich, aber nicht sicher („Arbeiten“, „Unternehmen“, „Bereiche“)
_DIESE_PP_RE = re.compile(r"\b(?:in|auf|an|aus|mit|zu|nach|von|bei|unter|über|für)\s+diese[rmns]?\s+$", re.IGNORECASE)


def partizip_vorfeld(text: str, wort: str) -> bool:
    """„Begründet wird die Kurve …“: Partizip am Satzanfang, gefolgt vom Hilfsverb – kein Nomen."""
    toks = [t for t in analyse.tokens(text.lstrip("„\"(»")) if analyse.ist_wort(t)]
    return len(toks) > 1 and toks[0] == wort and toks[1].lower() in HILFSVERBEN and _ist_partizip2(wort.lower())


def name_als_subjekt(text: str) -> bool:
    """Beginnt der Satz mit einem einzelnen Eigennamen und einem finiten Verb („Erik spricht …“, „Keller versteht …“)?"""
    toks = [t for t in analyse.tokens(text.lstrip("„\"(»")) if analyse.ist_wort(t)]
    if len(toks) < 2 or not namenartig(toks[0]) or toks[0].lower() in analyse.STARTWOERTER or not toks[1][:1].islower():
        return False
    verb = toks[1].lower()  # Eigennamen sind Singular: „spricht“, „versteht“, „ist“ – nicht „investieren“
    return verb in _SIE_SINGULAR or (verb.endswith("t") and verb not in analyse.FUNKTIONSWOERTER and len(verb) >= 4)


def namenartig(w: str) -> bool:
    """Großgeschriebenes Wort ohne typische Nomen-Endung und kein Personen-/Funktionswort: vermutlich ein Eigenname."""
    low = w.lower()
    return w[:1].isupper() and len(w) >= 3 and low not in analyse.FUNKTIONSWOERTER and not NOMEN_SUFFIX_RE.search(low) \
        and not ist_person(w)


def bezugskandidaten(text: str, n: int = 6) -> list[dict]:
    """Kandidaten für den Bezugsausdruck eines Satzes in Textreihenfolge, mit Merkmalen: koordinierte Namen („Lievens und
    Highhouse“, „Herzberg, Mausner und Snyderman“) als ein Kandidat, Person, Plural, Femininum. Nomen nach „in/auf/an +
    diese(r/m)“ („in diese Richtung“) fallen weg."""
    roh: list[tuple[int, int, list[str]]] = []
    beginn = len(text) - len(text.lstrip("„\"(»"))
    erster = beginn
    for m in _GROSS_FOLGE_RE.finditer(text):
        worte = m.group(0).split()
        start = m.start()
        while worte and (worte[0].lower() in analyse.FUNKTIONSWOERTER or worte[0].lower() in analyse.STARTWOERTER
                         or (start == beginn and (kein_nomen_am_anfang(worte[0]) or partizip_vorfeld(text, worte[0])))):
            start += len(worte[0]) + 1
            worte.pop(0)
            beginn = -1
        # Name + Nomen („George Herbert Mead Rollenübernahme“): am ersten typischen Nomen-Ende abschneiden
        for i, w in enumerate(worte[:-1]):
            if re.search(r"(?:ung|heit|keit|schaft|ion|tät|nahme|ismus)(?:en)?$", w.lower()):
                worte = worte[:i + 1]
                break
        worte = [w for w in worte if w.lower() not in LEICHTE_NOMEN and not ist_genderform(w) and len(w) >= 3
                 and w.lower() not in analyse.FUNKTIONSWOERTER and analyse.ist_wort(w)]
        if not worte or _DIESE_PP_RE.search(text[:start]):
            continue
        roh.append((start, start + len(" ".join(worte)), worte))
    # koordinierte Namen zusammenfassen: „X und Y“, „X, Y und Z“ (alle namenartig, Trenner nur Komma bzw. „und“/„&“)
    out: list[dict] = []
    i = 0
    while i < len(roh):
        j, trenner = i, []
        namen = True
        while j + 1 < len(roh):
            zw = text[roh[j][1]:roh[j + 1][0]]
            alle_namen = all(namenartig(w) for w in roh[j][2] + roh[j + 1][2])
            if re.fullmatch(r"\s*(?:,|und|&|,\s*und)\s*", zw) and alle_namen and namen:
                trenner.append(zw.strip())
                j += 1
            elif j == i and re.fullmatch(r"\s*und\s*", zw):
                trenner.append("und")  # zwei Nomen („Precision und Recall“): gemeinsamer Plural-Kandidat
                namen = False
                j += 1
                break
            else:
                break
        if j > i and trenner and trenner[-1] in ("und", "&", ", und"):
            phrase = text[roh[i][0]:roh[j][1]]
            person = namen or all(ist_person(roh[x][2][-1]) for x in (i, j))
            out.append({"text": phrase, "koordiniert": True, "person": person, "plural": True, "plural_moeglich": True, "feminin": False})
        else:
            j = i
            phrase = " ".join(roh[i][2])
            letzt = roh[i][2][-1].lower()
            person = ist_person(letzt)
            plural = bool(PLURAL_RE.search(letzt))
            if roh[i][0] == erster and len(roh[i][2]) == 1 and namenartig(roh[i][2][0]) and name_als_subjekt(text):
                person = True  # „Erik spricht …“, „Keller versteht …“
            out.append({"text": phrase, "koordiniert": False, "person": person, "plural": plural,
                        "plural_moeglich": plural or bool(PLURAL_MOEGLICH_RE.search(letzt)),
                        "feminin": bool(FEMININ_RE.search(letzt)) and not plural})
        i = j + 1
    gesehen, eindeutig = set(), []
    for k in out:
        if k["text"] not in gesehen:
            gesehen.add(k["text"])
            eindeutig.append(k)
    return eindeutig[:n]


def bezugsausdruecke(text: str, n: int = 3) -> list[str]:
    """Kandidaten für den Bezugsausdruck eines Satzes in Textreihenfolge (Subjekt bzw. erstes Nomen im Vorfeld zuerst):
    Nomen bzw. direkt aufeinanderfolgende großgeschriebene Wörter (Eigennamen wie „Europäische Union“), koordinierte Namen
    als ein Ausdruck, ohne Funktionswörter, Gender-Partizipien und leichte Nomen („Jahr“, „Rahmen“ …). Nie nach Länge
    ausgewählt."""
    return [k["text"] for k in bezugskandidaten(text, n)]


def leitbegriffe(saetze: list[dict]) -> set[str]:
    """Mehrwortbegriffe aus großgeschriebenen Wörtern („Dynamic Pricing“, „Employer Branding“), die mindestens zweimal im
    Text stehen: Fachbegriffe, die kein Hinweis durch ein anderes Wort ersetzen lassen soll."""
    z: Counter = Counter()
    for s in saetze:
        for m in re.finditer(r"(?<![\w-])[A-ZÄÖÜ][\w-]+(?:\s+[A-ZÄÖÜ][\w-]+){1,3}", s["text"]):
            worte = m.group(0).split()
            while worte and (worte[0].lower() in analyse.FUNKTIONSWOERTER or worte[0].lower() in analyse.STARTWOERTER
                             or worte[0].lower() in _ADVERB_ANFANG):
                worte.pop(0)
            if len(worte) >= 2:
                z[" ".join(worte)] += 1
    return {k for k, v in z.items() if v >= 2}


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
    if name_als_subjekt(text) and not kein_nomen_am_anfang(toks[0]):
        return True  # „Erik spricht …“
    for t in toks[:4]:
        low = t.lower()
        if t[:1].isupper() and low not in analyse.FUNKTIONSWOERTER:
            return ist_person(low)
    return False


def synonym_cluster(saetze: list[dict], masken: dict[int, str]) -> list[dict]:
    """Wortgruppen, die im Text für dieselbe Sache wechseln: Synonyme aus SYNONYM_GRUPPEN, allein oder als Grundwort
    eines Kompositums mit gleichem Bestimmungswort (Preissetzung/Preisgestaltung)."""
    funde: dict[tuple, Counter] = {}
    orte: dict[tuple, dict[str, list[int]]] = {}
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
                    orte.setdefault((gi, treffer[0]), {}).setdefault(treffer[1], []).append(s["nr"])
                    break
    cluster = []
    for (gi, praefix), zaehl in funde.items():
        koepfe: dict[str, Counter] = {}
        for (g, form), n in zaehl.items():
            koepfe.setdefault(g, Counter())[form] += n
        if len(koepfe) < 2 or sum(zaehl.values()) < 4:
            continue  # mindestens zwei Varianten und vier Vorkommen
        varianten = sorted(((c.most_common(1)[0][0], sum(c.values())) for c in koepfe.values()), key=lambda v: -v[1])
        saetze_je = {koepfe[g].most_common(1)[0][0]: orte[(gi, praefix)][g] for g in koepfe}
        formen_je = {koepfe[g].most_common(1)[0][0]: sorted({f.lower() for f in koepfe[g]}) for g in koepfe}
        cluster.append({"varianten": varianten, "formen": sorted({form.lower() for (_, form) in zaehl}), "anzahl": sum(zaehl.values()),
                        "saetze": saetze_je, "formen_je": formen_je})
    return sorted(cluster, key=lambda c: -c["anzahl"])


# ---------------------------------------------------------------------------
# Satzlängen
# ---------------------------------------------------------------------------

def _l1(vert: dict, ziel: dict) -> float:
    return sum(abs(vert.get(k, 0.0) - ziel.get(k, 0.0)) for k in ziel)


def rhythmus(laengen: list[int]) -> float:
    """rhythmus_r1_log wie analyse.py: Lag-1-Autokorrelation der log-Satzlängen, um −1/n korrigiert."""
    if len(laengen) < 4:
        return 0.0
    return analyse.autokorrelation([math.log(max(1, x)) for x in laengen], 1) + 1 / len(laengen)


def dispersion(laengen: list[int]) -> float:
    """satzlaenge_dispersion wie analyse.py (Varianz / Mittel)."""
    mu = analyse.mittel(laengen) if laengen else 0.0
    return analyse.sd(laengen) ** 2 / mu if mu else 0.0


def wechsel(laengen: list[int]) -> int:
    """Strenge Kurz-Lang-Wechsel: Dreiergruppen kurz–lang–kurz bzw. lang–kurz–lang (Klassen wie zickzack())."""
    k = [klasse_zz(x) for x in laengen]
    return sum(1 for i in range(1, len(k) - 1) if k[i] != "m" and k[i - 1] != "m" and k[i - 1] == k[i + 1] != k[i])


class Guete(NamedTuple):
    """Abstände einer Satzlängen-Folge zum menschlichen Bereich (L1 der Klassenverteilung, sonst in IQR des grünen Bereichs)
    und die zugehörigen Rohwerte (für die Prüfung, ob ein Umbau eine Kennzahl rot macht)."""
    l1: float
    sch: float
    cv: float
    disp: float
    rh: float
    werte: dict


# Kennzahl je Gütefeld; laengen_gewinn() prüft für jede, ob ein Umbau sie verschlechtert und rot macht
GUETE_KENNZAHL = {"sch": "satzlaenge_schiefe", "cv": "satzlaenge_cv", "disp": "satzlaenge_dispersion", "rh": "rhythmus_r1_log"}


def laengen_guete(laengen: list[int], ref: dict, ziel: dict) -> Guete:
    """L1-Abstand der Klassenverteilung zur menschlichen sowie Abstand von Schiefe, CV, Dispersion und Rhythmus
    (rhythmus_r1_log) zum grünen Bereich."""
    werte = {"sch": analyse.schiefe(laengen), "cv": analyse.cv(laengen), "disp": dispersion(laengen), "rh": rhythmus(laengen)}
    ab = {f: band_abstand(w, ref[GUETE_KENNZAHL[f]]) if GUETE_KENNZAHL[f] in ref else 0.0 for f, w in werte.items()}
    l1 = _l1(analyse.verteilung(laengen), ziel) if ziel else 0.0
    return Guete(l1, ab["sch"], ab["cv"], ab["disp"], ab["rh"], werte)


def wird_rot(alt: Guete, neu: Guete, feld: str, ref: dict) -> bool:
    """Entfernt sich die Kennzahl vom grünen Bereich und liegt danach außerhalb von P10–P90?"""
    k = GUETE_KENNZAHL[feld]
    return getattr(neu, feld) > getattr(alt, feld) + 1e-9 and k in ref and status_von(neu.werte[feld], ref[k]) == "rot"


def laengen_gewinn(alt: Guete, neu: Guete, alt_l: list[int], neu_l: list[int], ref: dict) -> float | None:
    """Wert eines Satzlängen-Umbaus (Bündeln, Mitte ausdünnen); None = nicht zulässig.

    Die Klassenverteilung muss sich der menschlichen nähern. Schiefe, CV, Dispersion und Rhythmus gehen mit ein:
    Verschlechterungen und neue Kurz-Lang-Wechsel werden abgewertet, Verbesserungen aufgewertet, statt das Bündeln danach
    per Wächter ganz zu sperren. Verworfen wird ein Umbau nur, wenn er eine dieser Kennzahlen rot macht bzw. weiter ins
    Rot treibt oder die Abwertung den Gewinn aufzehrt."""
    if not neu.l1 < alt.l1 - 1e-9:
        return None
    wert = alt.l1 - neu.l1
    for feld in GUETE_KENNZAHL:
        a, n = getattr(alt, feld), getattr(neu, feld)
        if wird_rot(alt, neu, feld, ref):
            return None
        wert += -0.5 * (n - a) if n > a else 0.25 * (a - n)
    wert -= 0.03 * max(0, wechsel(neu_l) - wechsel(alt_l))
    return wert if wert > 0 else None


# Art der Verknüpfung an der Trennstelle: sie muss im zweiten Satz erhalten bleiben (Kausalität, Gegensatz …)
FUGE_ART = {"weil": "Begründung", "da": "Begründung", "denn": "Begründung", "sodass": "Folge", "so dass": "Folge", "womit": "Folge",
            "wodurch": "Folge", "weshalb": "Folge", "aber": "Gegensatz", "doch": "Gegensatz", "jedoch": "Gegensatz",
            "sondern": "Gegensatz", "während": "Gegensatz bzw. Zeitbezug", "obwohl": "Einräumung", "wenngleich": "Einräumung",
            "wenn": "Bedingung", "indem": "Mittel", "nachdem": "Zeitfolge", "wobei": "Bezug", "bevor": "Zeitfolge", "ehe": "Zeitfolge",
            "sobald": "Bedingung", "solange": "Bedingung", "seit": "Zeitbezug", "seitdem": "Zeitbezug", "damit": "Zweckangabe",
            "um": "Zweckangabe", "worauf": "Folge", "woraus": "Folge", "worin": "Bezug"}


def fugen_technik(fuge: str) -> str:
    """Wie der zweite Teil nach dem Teilen anschließt, ohne dass die Verknüpfung verloren geht."""
    f = fuge.lower()
    if f in (";", ":"):
        return "das Satzzeichen durch einen Punkt ersetzen"
    if f in analyse.RELATIVPRONOMEN or f == "was":
        return "im zweiten Satz das Bezugswort wiederholen"
    if f in ("und", "oder"):
        return f"nach „{f}“ einen neuen Satz beginnen und das Subjekt wiederholen"
    if f in ("etwa", "nämlich", "also", "insbesondere", "darunter", "vor"):
        return "die Erläuterung als eigenen Satz mit Verb formulieren"
    return f"die {FUGE_ART.get(f, 'Verknüpfung')} im zweiten Satz ausdrücklich behalten"


# Wörter, die der zweite Satz beim Teilen an dieser Fuge voraussichtlich dazubekommt (Subjekt, „Dazu gehören …“)
FUGE_ZUSATZ = {"und": 1, "oder": 1, "etwa": 2, "nämlich": 2, "also": 2, "insbesondere": 2, "darunter": 2, "vor": 2}


def teilstelle(text: str, maske: str, max_teil: int | None = None, rx: re.Pattern = TEIL_RE) -> tuple[int, int, int, str, str] | None:
    """Beste Stelle, um einen Satz an einer inhaltlichen Wende zu teilen: (Position, Wörter links, Wörter rechts,
    Kontext, Fuge). Beide Teile ≥ 8 (und höchstens max_teil, einschließlich der Wörter, die der zweite Satz an dieser Fuge
    voraussichtlich dazubekommt) Wörter, nicht in einem Zitat, möglichst in der Mitte."""
    beste = None
    for m in rx.finditer(maske):
        links, rechts = text[:m.start()], text[m.end():]
        nl, nr = len(analyse.tokens(links)), len(analyse.tokens(rechts))
        zeichen = m.group(0).strip()
        worte = rechts.lower().split()
        if zeichen in (";", ":"):
            fuge = zeichen
        elif rechts.lower().startswith("so dass"):
            fuge = "so dass"
        elif len(worte) > 1 and worte[0] in analyse.PRAEPOSITIONEN and worte[1] in analyse.RELATIVPRONOMEN:
            fuge = worte[1]  # „…, bei dem …“: Relativsatz mit Präposition
        else:
            fuge = worte[0] if worte else ""
        if fuge == "wenn" and len(worte) > 1 and worte[1] in ("auch", "gleich", "überhaupt", "schon"):
            fuge = "wenngleich"  # „…, wenn auch …“: Einräumung, keine Bedingung
        if nl < 8 or nr < 8 or (max_teil and (nl > max_teil or nr + FUGE_ZUSATZ.get(fuge, 0) > max_teil)):
            continue
        guete = abs(nl - nr) - (4 if zeichen == ";" else 0)
        if beste is None or guete < beste[0]:
            vor = " ".join(links.split()[-2:])
            nach = " ".join(rechts.split()[:2])
            beste = (guete, m.start(), nl, nr, f"{vor}{m.group(0).rstrip()} {nach}".replace("  ", " "), fuge)
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
    d["modus"], d["kontingent"], d["gruende"], d["fehlende_mitte"], d["mitte_moeglich"] = None, 0, [], False, False
    p = lambda k, q: ref[k]["mensch"][q] if k in ref else None  # noqa: E731
    if not L or p("anteil_lange_saetze", "p50") is None:
        return d
    lang50, lang75 = p("anteil_lange_saetze", "p50"), p("anteil_lange_saetze", "p75")
    mittl25, mittl50, mittl75 = p("anteil_mittlere_saetze", "p25"), p("anteil_mittlere_saetze", "p50"), p("anteil_mittlere_saetze", "p75")
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
    elif mittl75 is not None and d["anteil_mittlere"] > mittl75:
        # genug lange Sätze, aber die Mitte ist überfüllt: einzelne mittellange Sätze teilen (Modus „mitte“, falls aktiv)
        d["mitte_moeglich"] = True
        d["mitte_kontingent"] = max(1, min(MAX_MITTE, math.ceil((d["mittlere"] - mittl50 * d["n"]) / (1 + mittl50))))
    return d


def _pz(x: float) -> str:
    return f"{round(100 * x)} %"


# ---------------------------------------------------------------------------
# Absätze und Funktionswörter: Hilfsfunktionen
# ---------------------------------------------------------------------------

ORDINAL_RE = re.compile(r"^(?:erstens|zweitens|drittens|viertens|fünftens|zum einen|zum anderen|zum dritten|einerseits|"
                        r"andererseits)\b", re.IGNORECASE)


def absatz_kennzahlen(anz: list[int], woerter: list[int]) -> dict:
    """Absatz-Kennzahlen wie analyse.py: Variation der Sätze bzw. Wörter pro Absatz, Ø Sätze pro Absatz, Ein-Satz-Absätze."""
    return {"cv": analyse.cv(anz) if len(anz) > 1 else 0.0, "cv_w": analyse.cv(woerter) if len(woerter) > 1 else 0.0,
            "mittel": analyse.mittel(anz) if anz else 0.0, "einsatz": sum(x == 1 for x in anz) / len(anz) if anz else 0.0}


def absatz_trenner(text: str) -> set[int]:
    """Absatznummern x (wie in ergebnis['saetze']), nach denen eine Überschrift oder Liste steht: dort nie zusammenlegen."""
    try:
        struktur = analyse.zerlege_bloecke(text)
    except Exception:  # noqa: BLE001 – Zusatzinformation, nie Abbruchgrund
        return set()
    out, nr, einschub = set(), 0, False
    for art, idx in struktur.get("folge", []):
        if art != "absatz":
            einschub = True
            continue
        if not analyse.zerlege_saetze(analyse.bereinige_absatz(struktur["absaetze"][idx], Counter())):
            continue
        if einschub and nr:
            out.add(nr)
        nr += 1
        einschub = False
    return out


def _log_nb(k: int, mu: float, s: float) -> float:
    """Log-Wahrscheinlichkeit der negativen Binomialverteilung wie analyse.py (dort _log_nb)."""
    f = getattr(analyse, "_log_nb", None)
    if f:
        return f(k, mu, s)
    mu = max(mu, 1e-12)
    if s >= 1e6:
        return k * math.log(mu) - mu - math.lgamma(k + 1)
    return (math.lgamma(k + s) - math.lgamma(s) - math.lgamma(k + 1) + s * math.log(s / (s + mu)) + k * math.log(mu / (s + mu)))


def fw_diagnose(saetze: list[dict], profil: dict | None) -> dict | None:
    """Funktionswörter im Fokus: beobachtete gegen erwartete Anzahl (menschliche bzw. KI-Rate · n) und Beitrag je Wort zum
    Funktionswort-LLR pro 1000 Wörter (negativ = zieht Richtung KI), aufsteigend sortiert."""
    woerter = (profil or {}).get("woerter") or []
    toks = [t.lower() for s in saetze for t in analyse.tokens(s["text"]) if analyse.ist_wort(t)]
    n = len(toks)
    if not woerter or not n:
        return None
    menge = set(woerter)
    z = Counter(t for t in toks if t in menge)
    rm, rk, gr = profil.get("rate_mensch", {}), profil.get("rate_ki", {}), profil.get("groesse", {})
    zeilen = []
    for w in woerter:
        if w not in rm or w not in rk:
            continue
        k, s = z.get(w, 0), float(gr.get(w) or 1e6)
        b = 1000.0 * (_log_nb(k, rm[w] * n, s) - _log_nb(k, rk[w] * n, s)) / n
        zeilen.append({"wort": w, "anzahl": k, "mensch": round(rm[w] * n, 1), "ki": round(rk[w] * n, 1), "beitrag": round(b, 3),
                       "zu_viel": k > rm[w] * n})
    zeilen.sort(key=lambda r: r["beitrag"])
    return {"n": n, "zaehlung": dict(z), "woerter": zeilen, "top": [r for r in zeilen if r["beitrag"] < 0][:3],
            "llr": round(sum(r["beitrag"] for r in zeilen), 3)}


def fw_delta(diag: dict, profil: dict, entfernt: Counter, hinzu: Counter) -> float:
    """Änderung des Funktionswort-LLR (pro 1000 Wörter), wenn ein Umbau diese Profilwörter entfernt bzw. hinzufügt."""
    z, n = Counter(diag["zaehlung"]), diag["n"]
    vor = analyse.fw_llr_zaehlung(z, n, profil) or 0.0
    for w, c in entfernt.items():
        z[w] = max(0, z[w] - c)
    for w, c in hinzu.items():
        z[w] += c
    return (analyse.fw_llr_zaehlung(z, max(1, n - sum(entfernt.values()) + sum(hinzu.values())), profil) or 0.0) - vor


def profilwoerter(text: str, profil: dict) -> Counter:
    menge = set(profil.get("woerter") or [])
    return Counter(t.lower() for t in analyse.tokens(text) if t.lower() in menge)


# ---------------------------------------------------------------------------
# Lauf: Messung, Fokus und Zustand eines Coach-Durchgangs
# ---------------------------------------------------------------------------

class Lauf:
    """Zustand eines Coach-Laufs: Messung, Fokus, Zitatmasken, Aussetzungen und die gesammelten Hinweise. Die
    Hinweisfamilien (_satzlaengen, _absaetze, _funktionswoerter …) lesen und schreiben ihn."""

    def __init__(self, text: str, verlauf: dict | None):
        self.text, self.verlauf = text, verlauf
        self.muster = analyse.lade_muster()
        baselines = analyse.lade_baselines()
        self.ts = (baselines or {}).get("textsorten", {}).get("hochschule", {})
        self.ref = self.ts.get("metriken", {})
        if hasattr(analyse, "analysiere_und_bewerte"):
            self.erg, self.bew = analyse.analysiere_und_bewerte(text, self.muster, baselines)
        else:
            fw_profil = self.ts.get("fw_profil")
            self.erg = (analyse.analysiere_text(text, self.muster, fw_profil=fw_profil) if fw_profil
                        else analyse.analysiere_text(text, self.muster))
            self.bew = analyse.bewerte(self.erg, baselines)
        self.saetze, self.m = self.erg["saetze"], self.erg["metriken"]
        self.kz = {z["id"]: dict(z, seite=seite_von(z["wert"], self.ref[z["id"]]) if z["id"] in self.ref else None)
                   for z in self.bew.get("kennzahlen", [])}
        # Fokus: im Blockmodus nur der schwächste Block
        self.bloecke = self.bew.get("bloecke") or []
        self.fokus_block = None
        if self.bew.get("blockmodus") and len(self.bloecke) > 1:
            self.fokus_block = min(self.bloecke, key=lambda b: (b["p_mensch"] if b.get("p_mensch") is not None else 2.0,
                                                                b["score"] if b.get("score") is not None else 101))
            self.von, self.bis = self.fokus_block["satz_von"], self.fokus_block["satz_bis"]
        else:
            self.von, self.bis = 1, len(self.saetze)
        self.fokus = [s for s in self.saetze if self.von <= s["nr"] <= self.bis]
        self.nach_nr = {s["nr"]: s for s in self.saetze}
        self.absaetze: dict[int, list[dict]] = {}
        for s in self.fokus:
            self.absaetze.setdefault(s["absatz"], []).append(s)
        self.masken = zitat_masken(self.saetze)
        self.quelle, self.autor = quellen_flags(text, self.saetze)
        self.aliase = gleichsetzungen(self.saetze)
        self.begriffe_info = {s["nr"]: satz_begriffe(s["text"], self.aliase) for s in self.saetze}
        self.leitbegriffe = leitbegriffe(self.saetze)
        self.tok_fokus = sum(len(analyse.tokens(s["text"])) for s in self.fokus) or 1
        self.anfang_index: dict[str, dict] = {}
        for s in self.saetze:
            self.anfang_index.setdefault(schluessel_anfang(s["text"]), s)
        # Verlauf
        self.messungen = list((verlauf or {}).get("messungen") or [])
        self.vorher = self.messungen[-1] if self.messungen else None
        self.frueher = [(i, {(t, h.get("anfang")) for h in mess.get("hinweise", []) if isinstance(h, dict)
                             for t in (h.get("typen") or [h.get("typ")])})
                        for i, mess in enumerate(self.messungen, 1)]
        self.roh_jetzt = {k: self.m.get(k) for k in set(WAECHTER) | {"satzlaenge_mittel", "woerter_pro_teilsatz", "satzklammer_mittel"}}
        if self.bew.get("blockmodus"):
            for k in self.roh_jetzt:
                if self.kz.get(k):
                    self.roh_jetzt[k] = self.kz[k]["wert"]
        # Zustand der Hinweisfamilien
        self.hebel: dict[str, dict] = {}
        self.hinweise: list[dict] = []
        self.belegt: set[int] = set()  # Sätze mit strukturellem Auftrag (höchstens einer je Satz)
        self.ausgesetzt: set[str] = set()
        self.aussetz_grund: dict[str, list[str]] = {}
        self.ueberkorrektur: list[dict] = []
        self.jenseits: list[dict] = []
        self.wirkung: list[dict] = []
        self.diag: dict = {}
        self.ziel_vert = self.ts.get("satzlaengen_verteilung_mensch") or {}
        self.gebuendelt = 0
        self.gebuendelte_b: set[int] = set()
        self.fw_profil = self.ts.get("fw_profil")
        self.fw_diag = fw_diagnose(self.fokus, self.fw_profil)
        # Wörter, die seltener sind als bei Menschen: nicht einstreuen lassen, aber Hinweise unterdrücken, die sie entfernen
        self.schutz = {r["wort"] for r in (self.fw_diag or {}).get("woerter", [])
                       if r["wort"] in SCHUTZ_WOERTER and not r["zu_viel"] and r["beitrag"] < -0.1}
        self.unterdrueckt: Counter = Counter()  # Hinweise, die der Passiv-/„werden“-/„um“-Schutz verhindert hat
        self.fw_potenzial = 0.0  # Summe der simulierten LLR-Gewinne aller gefundenen Funktionswort-Konstruktionen

    # --- Abfragen -----------------------------------------------------------------
    def p_(self, id_: str, q: str):
        return self.ref[id_]["mensch"][q] if id_ in self.ref else None

    def wert(self, id_: str):
        z = self.kz.get(id_)
        return z["wert"] if z else self.m.get(id_)

    def ki_auffaellig(self, id_: str, nur_rot: bool = False) -> bool:
        """Zielkennzahl auf der KI-Seite außerhalb des grünen Bereichs (gelb an der Grenze der Messunsicherheit zählt nicht)."""
        z = self.kz.get(id_)
        if not z or z["status"] == "gruen" or z["seite"] != "ki":
            return False
        if nur_rot:
            return z["status"] == "rot"
        return not (z["status"] == "gelb" and z.get("unsicher"))

    def modell_hebel(self, id_: str) -> bool:
        """Modellmerkmal zieht deutlich Richtung KI (Beitrag ≤ MODELL_HEBEL), auch wenn die Ampel grün oder unsicher ist."""
        z = self.kz.get(id_)
        return bool(z and z.get("beitrag") is not None and z["beitrag"] <= MODELL_HEBEL and z["seite"] != "gegen")

    def nutzbar(self, s: dict) -> bool:
        """Satz bekommt Hinweise: kein Fragment, nicht ganz im Zitat."""
        return s["woerter"] >= MIN_WOERTER and bool(re.search(r"[A-Za-zÄÖÜäöüß]", self.masken.get(s["nr"], s["text"])))

    def langes_zitat(self, s: dict) -> bool:
        return len(analyse.tokens(s["text"])) - len(analyse.tokens(self.masken.get(s["nr"], s["text"]))) >= 4

    def beginnt_im_zitat(self, s: dict) -> bool:
        """Satzanfang liegt in einem wörtlichen Zitat: Anfangswörter dürfen nicht geändert werden."""
        return self.masken.get(s["nr"], s["text"]).lstrip().startswith(MASKE)

    def pendelt(self, typ: str, *nrn: int) -> bool:
        """Wurde an einem dieser Sätze früher der gegenteilige Auftrag gegeben (erst bündeln, dann teilen …)?"""
        gegen = GEGENTEIL.get(typ, set())
        anf = {schluessel_anfang(self.nach_nr[n]["text"]) for n in nrn if n in self.nach_nr}
        return any(t in gegen and a in anf for _, schl in self.frueher for (t, a) in schl)

    # --- Änderungen ------------------------------------------------------------------
    def setze_aus(self, typen, grund: str) -> None:
        for t in typen:
            self.ausgesetzt.add(t)
            gruende = self.aussetz_grund.setdefault(t, [])
            if grund not in gruende:
                gruende.append(grund)

    def hinweis(self, typ: str, s: dict | None, text_: str, gewicht: float = 1.0, absatz: int | None = None, fund: str | None = None,
                ersetzbar=(), weitere: tuple = (), anfang: str | None = None) -> bool:
        """Hinweis anlegen. anfang = Gedächtnisschlüssel für Hinweise ohne einzelnen Satz („syn:…“, „gender:…“)."""
        if typ in self.ausgesetzt:
            return False
        nrn = ([s["nr"]] if s else []) + list(weitere)
        if typ in STRUKTURELL:
            if any(n in self.belegt for n in nrn) or self.pendelt(typ, *nrn):
                return False
            self.belegt.update(nrn)
        h = TYP_HEBEL.get(typ, typ)
        ziel = ZIEL_KENNZAHL.get(typ)
        ziel_wert = self.wert(ziel) if ziel else None
        self.hinweise.append({"hebel": h, "typ": typ, "absatz": s["absatz"] if s and absatz is None else absatz,
                              "satz": s["nr"] if s else None, "text": text_, "fund": fund,
                              "anfang": anfang or (schluessel_anfang(s["text"]) if s else None), "laenge": s["woerter"] if s else None,
                              "weitere": [schluessel_anfang(self.nach_nr[n]["text"]) for n in weitere if n in self.nach_nr],
                              "weitere_nr": [n for n in weitere if n in self.nach_nr], "stelle": zitat(s) if s else None,
                              "ziel": ziel, "ziel_wert": round(ziel_wert, 4) if isinstance(ziel_wert, float) else ziel_wert,
                              "ersetzbar": sorted({w.lower() for w in ersetzbar if w}),
                              "gewicht": gewicht * (self.hebel.get(h, {}).get("prioritaet", 0.3) + 0.1)})
        return True


# ---------------------------------------------------------------------------
# Hebel, Wächter, Wirksamkeitsgedächtnis
# ---------------------------------------------------------------------------

def _hebel_priorisieren(L: Lauf) -> None:
    """Hebel nach Modellbeitrag (koef · Abstand zum menschlichen Median) und Ampel gewichten. Ein Modellmerkmal mit
    Beitrag ≤ MODELL_HEBEL zählt auch im grünen Bereich (z. B. keine Abkürzungen: grün, weil P25 = 0, im Modell −0,45)."""
    if not L.bew.get("verfuegbar"):
        return
    for z in L.bew["kennzahlen"]:
        b, h = z.get("beitrag"), HEBEL_VON.get(z["id"])
        if not h or b is None or b >= -0.25 or L.kz[z["id"]]["seite"] == "gegen":
            continue
        if z["status"] != "gruen" or z.get("nur_modell") or b <= MODELL_HEBEL:
            eintrag = L.hebel.setdefault(h, {"prioritaet": 0.0, "kennzahlen": []})
            eintrag["prioritaet"] += 0.5 * -b
            eintrag["kennzahlen"].append(z)
    for z in L.bew["kennzahlen"]:
        if not z["bewertet"] or z["status"] == "gruen":
            continue
        if z["status"] == "gelb" and z.get("unsicher"):
            continue  # gelb, aber innerhalb der Messunsicherheit an der Grenze: kein Arbeitsauftrag
        if L.kz[z["id"]]["seite"] != "ki":
            continue  # Abweichungen weg von der KI-Seite sind kein Arbeitsauftrag
        h = HEBEL_VON.get(z["id"])
        if not h:
            continue
        eintrag = L.hebel.setdefault(h, {"prioritaet": 0.0, "kennzahlen": []})
        eintrag["prioritaet"] += (z["gewicht"] or 0.1) * (0.5 + abstand(z))
        if z not in eintrag["kennzahlen"]:
            eintrag["kennzahlen"].append(z)


def _werte_aus(mess: dict) -> dict:
    """Kennzahlwerte einer gespeicherten Messung (werte, bewertete Kennzahlen, Rohwerte der Wächter)."""
    return {**{k: v for k, v in (mess.get("werte") or {}).items() if v is not None},
            **{k: v.get("wert") for k, v in (mess.get("kennzahlen") or {}).items() if isinstance(v, dict)},
            **{k: v for k, v in (mess.get("roh") or {}).items() if v is not None}}


def _grenze_text(v: float, r: dict, rot: bool) -> str:
    if rot:
        return f"über P90 ({fmt(r['p90'])})" if v > r["p90"] else f"unter P10 ({fmt(r['p10'])})"
    return f"über dem Zielbereich (P75 {fmt(r['p75'])})" if v > r["p75"] else f"unter dem Zielbereich (P25 {fmt(r['p25'])})"


def _waechter(L: Lauf) -> None:
    """Überkorrektur- und Nebenwirkungs-Wächter (Verlauf), Zustand jenseits des Bands, Passiv- und „werden“-Schutz."""
    ref = L.ref
    if L.vorher:
        # Vergleich mit der Vorrunde und mit der ersten Messung (das Überschießen kann sich über mehrere Runden aufbauen)
        vergleiche = [(len(L.messungen), _werte_aus(L.vorher))]
        if len(L.messungen) > 1:
            vergleiche.append((1, _werte_aus(L.messungen[0])))
        lang_z = L.kz.get("anteil_lange_saetze")
        lange_fehlen = bool(lang_z) and lang_z["wert"] < lang_z["mensch_p50"]
        for k, zuordnung in WAECHTER.items():
            v1 = L.roh_jetzt.get(k)
            if k not in ref or v1 is None:
                continue
            r = ref[k]["mensch"]
            iqr = (r["p75"] - r["p25"]) or ((r["p90"] - r["p10"]) / 2) or 1e-9
            bewertet = bool(ref[k].get("bewertet"))
            st1, seite1 = status_von(v1, ref[k]), seite_von(v1, ref[k])
            for runde, werte in vergleiche:
                v0 = werte.get(k)
                if v0 is None:
                    continue
                st0, seite0 = status_von(v0, ref[k]), seite_von(v0, ref[k])
                neu_rot = st1 == "rot" and (st0 != "rot" or seite0 != seite1)
                # unbewertete Kennzahlen (Lesbarkeit, Hedging) nur bei Rot; bewertete auch bei Gelb mit deutlicher Verschiebung
                gelb_verschoben = (bewertet and st1 == "gelb" and (st0 == "gruen" or seite0 != seite1)
                                   and abs(v1 - v0) >= 0.5 * iqr)
                if not (neu_rot or gelb_verschoben):
                    continue
                typen = set(zuordnung.get(seite1, set()))
                if k == "satzlaenge_schiefe" and seite1 == "ki" and lange_fehlen:
                    break  # geringe Schiefe bei zu wenigen langen Sätzen: genau ein langer Satz würde helfen, Bündeln bleibt
                grenze = _grenze_text(v1, r, st1 == "rot")
                L.ueberkorrektur.append({"id": k, "name": analyse.NAMEN.get(k, k), "vorher": v0, "messung_vorher": runde, "wert": v1,
                                         "grenze": grenze, "art": "Nebenwirkung" if seite1 == "ki" else "Überkorrektur",
                                         "aussetzen": sorted(typen)})
                L.setze_aus(typen, f"{analyse.NAMEN.get(k, k)} {fmt(v0)} → {fmt(v1)}, jetzt {grenze}")
                break
    # Zustand (auch ohne Verlauf): Lesbarkeit/Nominalstil liegen schon jenseits von P10–P90 auf der der KI gegenüberliegenden
    # Seite. Weiteres Verdichten (Bündeln, Klammer, Nebensatz → Nominalgruppe) würde den Text noch weiter aus dem Band treiben.
    for k in ("lix", "wiener_sachtextformel", "flesch_amstad", "nominalstil_pro_100"):
        v1 = L.roh_jetzt.get(k)
        if k not in ref or v1 is None or status_von(v1, ref[k]) != "rot" or seite_von(v1, ref[k]) != "gegen":
            continue
        r = ref[k]["mensch"]
        grenze = f"über P90 {fmt(r['p90'])}" if v1 > r["p90"] else f"unter P10 {fmt(r['p10'])}"
        L.jenseits.append({"id": k, "name": analyse.NAMEN.get(k, k), "wert": v1, "grenze": grenze})
        L.setze_aus(WAECHTER[k]["gegen"], f"{analyse.NAMEN.get(k, k)} {fmt(v1)} schon {grenze}")
    # Passiv: unter P25 keine Relativsatz-zu-Partizip-Umbauten („die erhoben wurden“ → „die erhobenen“ entfernt Passiv)
    passiv = L.kz.get("anteil_passiv")
    if passiv and passiv["wert"] < passiv["mensch_p25"]:
        L.setze_aus({"nebensatz_relativ"}, f"{passiv['name']} {fmt(passiv['wert'])} unter P25 ({fmt(passiv['mensch_p25'])})")
    if "werden" in L.schutz:
        r_ = next(r for r in L.fw_diag["woerter"] if r["wort"] == "werden")
        L.setze_aus({"nebensatz_werden"}, f"„werden“ {r_['anzahl']}× statt etwa {fmt(r_['mensch'])} bei menschlicher Rate")


def _befolgt(L: Lauf, h: dict) -> bool:
    """Wurde ein Auftrag der Vorrunde umgesetzt? Satz verändert (Anfang nicht mehr da, Länge ±3, Folgesatz aufgelöst) bzw.
    Absatzgrenze gesetzt oder aufgehoben."""
    a = h.get("anfang")
    if not a:
        return False
    s = L.anfang_index.get(a)
    if h.get("typ") == "absatz_teilen":
        return s is None or s.get("pos_im_absatz") == 1
    if h.get("typ") == "absatz_zusammen":
        return s is None or (s.get("pos_im_absatz") or 1) > 1
    if s is None:
        return True
    if h.get("laenge") is not None and abs(s["woerter"] - h["laenge"]) >= 3:
        return True
    return any(w not in L.anfang_index for w in h.get("weitere") or [])


def _wirksamkeit(L: Lauf) -> None:
    """Wirksamkeitsgedächtnis: Hat ein in der Vorrunde befolgter Auftragstyp seine Zielkennzahl dem menschlichen Median
    nicht nähergebracht, wird die Technik gewechselt (Absätze: Zusammenlegen statt Teilen und umgekehrt) bzw. der Typ für
    diese Runde ausgesetzt – mit Begründung im Bericht."""
    if not L.vorher:
        return
    alt_werte = _werte_aus(L.vorher)
    alle = [h for h in L.vorher.get("hinweise") or [] if isinstance(h, dict) and h.get("typ")]
    # Sätze mit mehreren Aufträgen: eine Änderung lässt sich keinem Typ eindeutig zuordnen – dort nichts bewerten
    mehrfach = {a for a, n in Counter(h.get("anfang") for h in alle if h.get("anfang")).items() if n > 1}
    mehrfach |= {h.get("anfang") for h in alle if len(h.get("typen") or []) > 1}  # kombinierter Auftrag
    nach_typ: dict[str, list[dict]] = {}
    for h in alle:
        if h["typ"] in ZIEL_KENNZAHL and h.get("anfang") not in mehrfach:
            nach_typ.setdefault(h["typ"], []).append(h)
    for typ, hs in nach_typ.items():
        ziel = next((h["ziel"] for h in hs if h.get("ziel")), ZIEL_KENNZAHL[typ])
        if ziel not in L.ref:
            continue
        alt = next((h["ziel_wert"] for h in hs if h.get("ziel_wert") is not None), alt_werte.get(ziel))
        neu = L.wert(ziel)
        if alt is None or neu is None or not any(_befolgt(L, h) for h in hs):
            continue
        r = L.ref[ziel]["mensch"]
        iqr = (r["p75"] - r["p25"]) or ((r["p90"] - r["p10"]) / 2) or 1e-9
        if abs(neu - r["p50"]) < abs(alt - r["p50"]) - 0.02 * iqr:
            continue  # wirksam: die Kennzahl ist dem menschlichen Median nähergekommen
        wechsel_zu = TECHNIK_WECHSEL.get(typ)
        grund = (f"{TYP_NAME.get(typ, typ)} wurde nach Messung {len(L.messungen)} umgesetzt, aber {analyse.NAMEN.get(ziel, ziel)} "
                 f"kam dem menschlichen Median nicht näher ({fmt(alt)} → {fmt(neu)}, Median {fmt(r['p50'])})")
        L.setze_aus({typ}, grund)
        L.wirkung.append({"typ": typ, "ziel": ziel, "vorher": alt, "jetzt": neu, "wechsel": wechsel_zu, "grund": grund})


# ---------------------------------------------------------------------------
# Hinweisfamilien
# ---------------------------------------------------------------------------

def _satzlaengen(L: Lauf) -> None:
    """Satzlängen: Modus bestimmen (bündeln / teilen / mitte), dann jeweils simulierte Aufträge bis zum Kontingent."""
    schiefe_fokus = L.m.get("satzlaenge_schiefe") if not L.fokus_block else None
    diag = L.diag = satzlaengen_diagnose(L.fokus, L.ref, L.ziel_vert, schiefe_fokus)
    laengen_aktiv = any(L.ki_auffaellig(k) or L.modell_hebel(k) for k in (
        "anteil_lange_saetze", "anteil_mittlere_saetze", "anteil_sehr_lange_saetze", "satzlaenge_cv", "satzlaenge_sd",
        "satzlaenge_dispersion", "satzlaenge_schiefe"))
    if diag["modus"] == "buendeln" and not laengen_aktiv:
        diag["modus"], diag["kontingent"] = None, 0  # im grünen Bereich und ohne Modellgewicht: kein Auftrag (Grundsatz 1)
    # „Mitte ausdünnen“: genug lange Sätze, aber zu viele mittellange – auch gelb-unsicher, wenn das Modell das Merkmal spürt
    mz = L.kz.get("anteil_mittlere_saetze")
    mitte_aktiv = L.ki_auffaellig("anteil_mittlere_saetze") or bool(
        mz and mz["seite"] == "ki" and mz["status"] != "gruen" and (mz.get("beitrag") or 0) <= MODELL_HEBEL)
    if diag["modus"] is None and diag.get("mitte_moeglich") and mitte_aktiv:
        diag["modus"], diag["kontingent"] = "mitte", diag["mitte_kontingent"]
    _buendeln(L)
    _bremse(L)
    _mitte(L)
    _kurz(L)


def _buendeln(L: Lauf) -> None:
    diag = L.diag
    if diag["modus"] != "buendeln" or diag["kontingent"] <= 0 or "buendeln" in L.ausgesetzt:
        return
    kandidaten = [(a, b) for liste in L.absaetze.values() for a, b in zip(liste, liste[1:]) if buendel_paar_ok(L, a, b)]
    laengen = [s["woerter"] for s in L.fokus]
    idx = {s["nr"]: i for i, s in enumerate(L.fokus)}
    aktuell = list(laengen)
    positionen: list[int | None] = list(range(len(laengen)))  # Index in aktuell je ursprünglichem Fokus-Index (None = verschmolzen)
    guete = laengen_guete(aktuell, L.ref, L.ziel_vert)
    while kandidaten and L.gebuendelt < diag["kontingent"]:
        bester = None
        for a, b in kandidaten:
            ia, ib = positionen[idx[a["nr"]]], positionen[idx[b["nr"]]]
            if ia is None or ib is None:
                continue
            neu = aktuell[:ia] + [round(VERDICHTUNG * (aktuell[ia] + aktuell[ib]))] + aktuell[ib + 1:]
            g = laengen_guete(neu, L.ref, L.ziel_vert)
            wert = laengen_gewinn(guete, g, aktuell, neu, L.ref)
            if wert is not None and (bester is None or wert > bester[0]):
                bester = (wert, a, b, neu, g)
        if bester is None:
            break
        _, a, b, neu, g = bester
        kandidaten = [(x, y) for x, y in kandidaten if x is not a and y is not b and x is not b and y is not a]
        if not L.hinweis("buendeln", a, f"{zitat(a)} und Satz {b['nr']} ({a['woerter']} + {b['woerter']} Wörter) zu einem Satz mit "
                         f"{LANG_AB} bis höchstens ~{BUENDEL_MAX_ZIEL} Wörtern verbinden: den Inhalt von Satz {b['nr']} als Nominal- oder "
                         f"Präpositionalgruppe in Satz {a['nr']} einbauen, kein angehängtes „und“. Aussagestatus erhalten (Befund, "
                         "Vermutung, Fähigkeit); geht das nicht mit einer Nominalgruppe, ist ein Anschluss mit „weshalb“ oder „wobei“ "
                         "erlaubt.", 1.1, weitere=(b["nr"],)):
            continue
        ib = positionen[idx[b["nr"]]]
        positionen = [None if p_i == ib else (p_i - 1 if p_i is not None and p_i > ib else p_i) for p_i in positionen]
        aktuell, guete = neu, g
        L.gebuendelt += 1


BUENDEL_MAX = 42  # a + b vor dem Verdichten; der Auftrag nennt höchstens ~40 Wörter
BUENDEL_MAX_ZIEL = 40
# Satz b trägt einen eigenen Aussagestatus (Vermutung, Befund, Ergänzung) – als Nominalgruppe in Satz a ginge er verloren
BUENDEL_B_ANFANG_RE = re.compile(r"^(?:Es\s+liegt\s+nahe|Zugleich\s+zeigt\s+sich|Hinzu\s+kommt|Dabei\s+zeigt\s+sich|Es\s+zeigt\s+sich|"
                                 r"Gleichzeitig\s+zeigt\s+sich|Es\s+ist\s+(?:davon\s+)?auszugehen|Vermutlich|Möglicherweise|"
                                 r"Wahrscheinlich|Je|Wenn|Falls|Ob|Obwohl|Während|Nachdem|Weil|Da)\b")  # auch: b beginnt mit Nebensatz
_VERMUTUNG_RE = re.compile(r"\b(?:vermutlich|möglicherweise|wahrscheinlich|dürfte[n]?|liegt\s+nahe|anzunehmen|auszuschließen|denkbar|"
                           r"vorstellbar|scheint|scheinen|offenbar|anscheinend|womöglich|eventuell)\b", re.IGNORECASE)


def nomen_staemme(text: str) -> set[str]:
    """Stämme großgeschriebener Nomen eines Satzes (ohne Satzanfangswort, das kein Nomen ist; Adjektive zählen nicht)."""
    toks = [t for t in analyse.tokens(text.lstrip("„\"(»")) if analyse.ist_wort(t)]
    out = set()
    for i, t in enumerate(toks):
        if not t[:1].isupper() or t.lower() in analyse.FUNKTIONSWOERTER or len(t) < 3:
            continue
        if i == 0 and (kein_nomen_am_anfang(t) or t.lower() in analyse.STARTWOERTER):
            continue
        out.add(_grund(t))
    return out


def buendel_paar_ok(L: Lauf, a: dict, b: dict) -> bool:
    """Darf Satz b in Satz a aufgehen? Längen 10–24, zusammen 34–42 Wörter; gleiche Quellenlage; gemeinsames Nomen
    (gleicher Stamm bzw. gleiches Grundwort) oder Anapher am Anfang von b; b trägt keinen eigenen Aussagestatus (Vermutung,
    „Hinzu kommt“, Modal- oder Redeverb in der Hauptaussage)."""
    if not (10 <= a["woerter"] <= 24 and 10 <= b["woerter"] <= 24 and 34 <= a["woerter"] + b["woerter"] <= BUENDEL_MAX):
        return False
    if not (L.nutzbar(a) and L.nutzbar(b)) or L.langes_zitat(a) or L.langes_zitat(b):
        return False
    if ";" in L.masken[a["nr"]] or a["text"].rstrip("\"“”»)").endswith(("?", "!")):
        return False
    if L.quelle.get(a["nr"], False) != L.quelle.get(b["nr"], False):
        return False  # sonst würde eine Aussage der fremden Quelle zugeschrieben
    anf = b["text"].lstrip("„\"(»")
    if BUENDEL_B_ANFANG_RE.match(anf) or _VERMUTUNG_RE.search(L.masken[b["nr"]]) or re.search(r",\s*sondern\b", L.masken[b["nr"]]) \
            or b["text"].rstrip("\"“”»)").endswith(("?", "!")):
        return False  # Vermutung, Gegenüberstellung oder Frage: als Nominalgruppe in Satz a ginge sie verloren
    if AUFZAEHLUNG_RE.match(anf) or any(_AUFZAEHL_WORT_RE.search(" ".join(x["text"].split()[:8])) for x in (a, b)):
        return False  # Aufzählungsglieder („erstens … / Zweitens …“) bleiben eigene Sätze
    haupt = re.split(r",", L.masken[b["nr"]], maxsplit=1)[0]
    if any(w.lower() in analyse.MODALVERBEN for w in analyse.tokens(haupt)) or REDEVERB_RE.search(haupt):
        return False  # Fähigkeit („können“) bzw. Aussage einer Quelle trägt die Hauptaussage
    if re.search(r"[;:]", L.masken[b["nr"]].rstrip(".")) or _BEZUG_IM_KOPF_RE.search(" ".join(anf.split()[:4]).lower()) \
            and re.search(r"\b(?:erste|zweite|dritte|vierte|letzte|weitere)[nrs]?\b", " ".join(anf.split()[:4]).lower()):
        return False  # Semikolon/Doppelpunkt (Liste, zweiter Hauptsatz) oder Aufzählungsglied („Das erste Modell …“)
    a_haupt = re.split(r",", L.masken[a["nr"]], maxsplit=1)[0]
    if re.search(r"\b(?:sei|seien|habe|könne|müsse|werde|solle|stehe|gebe)\b", L.masken[a["nr"]] + " " + L.masken[b["nr"]]):
        return False  # indirekte Rede: der Inhalt gehört einer Quelle
    if ((REDEVERB_RE.search(a_haupt) or SPRECHAKT_RE.search(a_haupt)) and not sachliches_subjekt(a_haupt)) \
            or (re.search(r",\s*dass\b", L.masken[a["nr"]]) and any(ist_person(w) for w in analyse.tokens(a_haupt) if w[:1].isupper())):
        return False  # Satz a gibt eine Person oder Quelle wieder: Satz b würde ihr zugeschrieben
    na, nb = nomen_staemme(a["text"]), nomen_staemme(b["text"])
    gemeinsam = bool(na & nb) or any(min(len(x), len(y)) >= 5 and (x.endswith(y) or y.endswith(x)) for x in na for y in nb)
    erstes = (analyse.tokens(anf) or [""])[0].lower()
    anapher = bool(ANAPHER_RE.match(anf)) or bool(RUECKVERWEIS_RE.fullmatch(erstes))
    return gemeinsam or anapher


def _bremse(L: Lauf) -> None:
    """Teilen-Aufträge nur mit Beleg, dass der Text über das menschliche Band hinaus geraten ist – Überkorrektur im Verlauf,
    Wert über P90 oder fehlende Mitte. Lange Sätze zwischen P75 und P90 sind auch bei Menschen häufig (≈ 15 %) und ziehen im
    Modell eher Richtung menschlich; dort nur kein weiteres Bündeln."""
    diag = L.diag
    laengen = [s["woerter"] for s in L.fokus]
    lang_ids = {"satzlaenge_mittel", "satzlaenge_median", "anteil_lange_saetze", "anteil_sehr_lange_saetze", "anteil_mittlere_saetze"}
    diag["ueberkorrektur"] = any(u["id"] in lang_ids and u["art"] == "Überkorrektur" for u in L.ueberkorrektur)
    diag["ueber_p90"] = bool(laengen) and (diag["anteil_lange"] > (L.p_("anteil_lange_saetze", "p90") or 1)
                                           or diag["mittel"] > (L.p_("satzlaenge_mittel", "p90") or 99))
    min_teilen = LANG_AB
    if diag["modus"] == "teilen" and not diag["ueberkorrektur"]:
        # ohne Verlauf-Beleg: höchstens zwei Aufträge, nur für sehr lange Sätze (≥ 40 Wörter)
        diag["kontingent"] = min(2, diag["kontingent"]) if (diag["ueber_p90"] or diag["fehlende_mitte"]) else 0
        min_teilen = SEHR_LANG_AB
    if diag["modus"] != "teilen" or diag["kontingent"] <= 0 or "teilen" in L.ausgesetzt:
        return
    kandidaten = sorted((s for s in L.fokus if s["woerter"] >= min_teilen and L.nutzbar(s)), key=lambda s: -s["woerter"])
    lange40 = [s for s in kandidaten if s["woerter"] >= SEHR_LANG_AB]
    kandidaten = lange40 + [s for s in kandidaten if s["woerter"] < SEHR_LANG_AB] if lange40 else kandidaten
    aktuell = list(laengen)
    guete = laengen_guete(aktuell, L.ref, L.ziel_vert)
    geteilt, ziel_lange = 0, round(L.p_("anteil_lange_saetze", "p50") * len(laengen))
    for s in kandidaten:
        if geteilt >= diag["kontingent"]:
            break
        stelle = teilstelle(s["text"], L.masken[s["nr"]])
        if stelle is None and L.langes_zitat(s):
            continue  # keine Trennstelle außerhalb des wörtlichen Zitats: „an einer inhaltlichen Wende“ würde das Zitat zerteilen
        nl, nr_ = (stelle[1], stelle[2]) if stelle else (s["woerter"] // 2, s["woerter"] - s["woerter"] // 2)
        i = aktuell.index(s["woerter"]) if s["woerter"] in aktuell else None
        if i is None:
            continue
        neu = aktuell[:i] + [nl, nr_] + aktuell[i + 1:]
        g = laengen_guete(neu, L.ref, L.ziel_vert)
        noch_zu_viele = sum(x >= LANG_AB for x in aktuell) > ziel_lange
        if not (g.l1 < guete.l1 - 1e-9 or noch_zu_viele):
            continue
        if wird_rot(guete, g, "rh", L.ref):
            continue  # würde den Rhythmus (weiter) in den roten Bereich treiben
        wo = f" – an der Stelle „{stelle[3]}“ (nach Wort {nl}); der zweite Teil wird ein eigener Satz" if stelle else \
            " – an einer inhaltlichen Wende"
        if L.hinweis("teilen", s, f"{zitat(s)} ({s['woerter']} Wörter) in zwei Sätze teilen{wo}.", 1.2):
            aktuell, guete = neu, g
            geteilt += 1


def _mitte(L: Lauf) -> None:
    """„Mitte ausdünnen“: konkrete Sätze mit 22–26 Wörtern an einer inhaltlichen Fuge in zwei Sätze mit je ≤ 13 Wörtern
    teilen; jeder Kandidat wird an Klassenverteilung, Dispersion und Rhythmus simuliert (Kontingent bis zum Median)."""
    diag = L.diag
    if diag["modus"] != "mitte" or diag["kontingent"] <= 0 or "mitte" in L.ausgesetzt:
        return
    kand = []
    for s in L.fokus:
        if not (MITTE_SATZ_VON <= s["woerter"] <= MITTE_SATZ_BIS) or not L.nutzbar(s) or L.langes_zitat(s) or s["nr"] in L.belegt:
            continue
        if L.quelle.get(s["nr"]) or L.autor.get(s["nr"]):
            continue  # Quellenzuordnung: die Angabe müsste in beiden Teilen erkennbar bleiben
        st = teilstelle(s["text"], L.masken[s["nr"]], MITTE_TEIL_MAX, MITTE_TEIL_RE)
        if st:
            kand.append((s, st))
    pos = {s["nr"]: i for i, s in enumerate(L.fokus)}
    aktuell = [s["woerter"] for s in L.fokus]
    guete = laengen_guete(aktuell, L.ref, L.ziel_vert)
    n_m = 0
    while kand and n_m < diag["kontingent"]:
        bester = None
        for s, st in kand:
            i = pos[s["nr"]]
            neu = aktuell[:i] + [st[1], st[2]] + aktuell[i + 1:]
            g = laengen_guete(neu, L.ref, L.ziel_vert)
            wert = laengen_gewinn(guete, g, aktuell, neu, L.ref)
            if wert is not None and (bester is None or wert > bester[0]):
                bester = (wert, s, st, neu, g)
        if bester is None:
            break
        _, s, st, neu, g = bester
        kand = [(x, y) for x, y in kand if x is not s]
        if not L.hinweis("mitte", s, f"{zitat(s)} ({s['woerter']} Wörter) in zwei Sätze mit je höchstens {MITTE_TEIL_MAX} Wörtern teilen – "
                         f"an der Stelle „{st[3]}“ (nach Wort {st[1]}); {fugen_technik(st[4])}.", 1.1):
            continue
        i = pos[s["nr"]]
        pos = {nr: (p + 1 if p > i else p) for nr, p in pos.items()}
        aktuell, guete = neu, g
        n_m += 1
    diag["mitte_geteilt"] = n_m


def _kurz(L: Lauf) -> None:
    """Kurze Sätze: nur wenn anteil_kurze_saetze unter P25 liegt UND das die KI-Seite ist (KI-Median unter dem menschlichen).
    In den aktuellen Referenzwerten liegt der KI-Median darüber (0,119 gegen 0,105) – dann gibt es keinen Auftrag."""
    k25 = L.p_("anteil_kurze_saetze", "p25")
    ref = L.ref
    kurz_ki_unten = "anteil_kurze_saetze" in ref and (ref["anteil_kurze_saetze"].get("ki") or {}).get("p50") is not None \
        and ref["anteil_kurze_saetze"]["ki"]["p50"] < ref["anteil_kurze_saetze"]["mensch"]["p50"]
    if k25 is None or not kurz_ki_unten or L.diag["anteil_kurze"] >= k25 or L.diag["n"] < 10:
        return
    for s in sorted(L.fokus, key=lambda s: -s["woerter"]):
        mk = L.masken[s["nr"]]
        if s["woerter"] >= 22 and mk.count(",") >= 2 and SCHLUSS_RE.search(mk) and L.nutzbar(s):
            if L.hinweis("kurz", s, f"{zitat(s)}: Falls darin ein echtes Zwischenergebnis steckt (etwa nach „{SCHLUSS_RE.search(mk).group(0)}“), "
                         "dieses als eigenen kurzen Satz formulieren.", 0.6):
                break


def _zickzack(L: Lauf) -> None:
    """Die Handlung „Satz X mit X+1 verbinden“ verlängert (kurz + lang ≥ 40 Wörter): nicht im TEILEN-Modus."""
    r1 = L.kz.get("rhythmus_r1_log")
    if not (r1 and r1["bewertet"] and r1["wert"] < r1["mensch_p25"] and r1["seite"] == "ki" and not L.gebuendelt
            and "zickzack" not in L.ausgesetzt and L.diag.get("modus") != "teilen"):
        return
    laengen = [s["woerter"] for s in L.fokus]
    n_zz = 0
    for a_i, b_i in zickzack(laengen):
        if n_zz >= 2:
            break
        teil = L.fokus[a_i:b_i + 1]
        folge = " · ".join(str(s["woerter"]) for s in teil)
        x = next((teil[j] for j in range(len(teil) - 1) if klasse_zz(teil[j]["woerter"]) == "k"
                  and teil[j]["absatz"] == teil[j + 1]["absatz"] and L.nutzbar(teil[j]) and L.nutzbar(teil[j + 1])
                  and teil[j]["nr"] not in L.belegt and teil[j + 1]["nr"] not in L.belegt), None)
        if x is None:
            continue
        x2 = L.nach_nr.get(x["nr"] + 2)
        oder = f" oder Satz {x2['nr']} nicht weiter verlängern" if x2 and x2["nr"] <= teil[-1]["nr"] else ""
        ein_absatz = len({s["absatz"] for s in teil}) == 1
        if L.hinweis("zickzack", x, f"Satz {teil[0]['nr']}–{teil[-1]['nr']} wechseln streng zwischen kurz (≤ {ZZ_KURZ_MAX}) und lang "
                     f"(≥ {ZZ_LANG_AB} Wörter) ({folge}). Satz {x['nr']} mit Satz {x['nr'] + 1} verbinden{oder} – zwei ähnlich lange Sätze "
                     "hintereinander brechen das Muster.", 0.8, absatz=teil[0]["absatz"] if ein_absatz else None, weitere=(x["nr"] + 1,)):
            if not ein_absatz:
                L.hinweise[-1]["absatz"] = None  # Spanne über mehrere Absätze: allgemeiner Hinweis, keinem Absatz zugeordnet
            n_zz += 1


def _satzklammer(L: Lauf) -> None:
    def aktiv(k: str) -> bool:  # rot/gelb auf der KI-Seite, auch gelb-unsicher bei deutlichem Modellbeitrag
        z = L.kz.get(k)
        return L.ki_auffaellig(k) or bool(z and z["status"] != "gruen" and L.modell_hebel(k))
    if not (aktiv("satzklammer_mittel") or aktiv("nominalketten_pro_100")):
        return
    n_kl = 0
    for i, s in enumerate(L.fokus):
        if n_kl >= 3:
            break
        if s["woerter"] <= 12 or not L.nutzbar(s) or s["nr"] in L.belegt or L.langes_zitat(s):
            continue
        mk = L.masken[s["nr"]]
        if REDEVERB_DASS_RE.search(mk) or re.search(r",\s+(?:dass|ob)\b", mk):
            continue  # Objektsatz: folgende Nebensätze gehören zu ihm, nicht ins Mittelfeld des Hauptsatzes
        leer = [d for d in klammer_details(mk) if d[0] <= 2]
        if not leer:
            continue
        _, aux, ende = leer[0]
        q = KLAMMER_QUELLE_RE.search(mk)
        if q and (re.search(r"[,;]", mk[q.end():]) or len([w for w in analyse.tokens(mk[q.end():]) if analyse.ist_wort(w)]) > 10):
            q = None  # langer oder verschachtelter Nebensatz: als Angabe im Mittelfeld entstünde ein Satzungetüm
        if q and q.group("w") == "um" and "um" in L.schutz:
            L.unterdrueckt["klammer_um"] += 1
            q = None  # „um … zu“ → Präpositionalgruppe entfernt „um“ und „zu“, die hier ohnehin seltener sind als bei Menschen
        nachbar = L.fokus[i + 1] if i + 1 < len(L.fokus) and L.fokus[i + 1]["absatz"] == s["absatz"] else None
        if q:
            teil = {"um": "„um … zu“-Teil", "ohne": "„ohne … zu“-Teil"}.get(q.group("w"), f"„{q.group('w')}“-Satz")
            if L.hinweis("klammer", s, f"{zitat(s)}: Zwischen „{aux}“ und „{ende}“ steht fast nichts. Den {teil} als Angabe "
                         f"(Präpositionalgruppe, z. B. mit „zur“, „durch“, „wegen“) zwischen „{aux}“ und „{ende}“ holen.", 0.8):
                n_kl += 1
        elif nachbar and L.diag.get("modus") != "teilen" and L.nutzbar(nachbar) and nachbar["woerter"] <= 14 \
                and not L.beginnt_im_zitat(nachbar) and (analyse.tokens(nachbar["text"]) or [""])[0].lower() in ANGABE_ANFANG \
                and verbunden(L.begriffe_info[s["nr"]], L.begriffe_info[nachbar["nr"]]) \
                and L.quelle.get(s["nr"], False) == L.quelle.get(nachbar["nr"], False):
            if L.hinweis("klammer_zusatz", s, f"{zitat(s)}: Zwischen „{aux}“ und „{ende}“ steht fast nichts. Die Angabe vom Anfang von "
                         f"Satz {nachbar['nr']} („{anfang(nachbar['text'], 3)}“) dorthin holen und Satz {nachbar['nr']} damit auflösen.", 0.8,
                         weitere=(nachbar["nr"],)):
                n_kl += 1


def _ist_partizip2(w: str) -> bool:
    return bool(analyse.PARTIZIP_T.fullmatch(w) or analyse.PARTIZIP_GE_EN.fullmatch(w) or analyse.PARTIZIP_EN_ABLAUT.fullmatch(w)) \
        and not _ADJ_ENDE.search(w) and w.lower() not in analyse.KEIN_PARTIZIP


def relativsatz_umbaubar(vorne: str, teil: str) -> tuple[bool, bool]:
    """(umbaubar, Passiv) für einen Relativsatz „…, die erhoben wurden“: höchstens RELATIV_MAX Wörter, Bezugswort ein
    Gattungsnomen mit Artikel (kein Eigenname, keine Autorenliste, kein Name mit Jahr, keine Person), Prädikat ein Partizip
    (werden-Passiv, sein + Partizip II, oder ein Vollverb im Präsens für das Partizip I) – nicht Adjektiv + sein, nicht
    haben-Perfekt, kein Modalverb."""
    worte = [w for w in analyse.tokens(teil) if analyse.ist_wort(w)]
    low = [w.lower() for w in worte]
    if not 2 <= len(worte) <= RELATIV_MAX or any(w in analyse.MODALVERBEN for w in low):
        return False, False
    if re.search(r"[)\d]\s*$", vorne):
        return False, False  # „Ambler und Barrow (1996), die …“
    m = BEZUG_GATTUNG_RE.search(vorne)
    if not m:
        return False, False  # Eigenname, Autorenliste oder Nomen ohne Begleiter
    nomen = m.group("n").lower()
    if ist_person(nomen) or ist_genderform(m.group("n")):
        return False, False  # Personen: „die Mitarbeiter, die …“ bleibt ein Relativsatz
    passiv = any(w in analyse.WERDEN_FORMEN for w in low)
    letzt = low[-1]
    if letzt in analyse.WERDEN_FORMEN or letzt in _AUX_SEIN:
        kern = [w for w in worte[1:-1] if w.lower() not in analyse.WERDEN_FORMEN]
        return bool(kern) and _ist_partizip2(kern[-1]), passiv
    if letzt in _AUX_HABEN or letzt in HILFSVERBEN:
        return False, False  # „die investiert haben“ → kein Partizipialattribut
    # Vollverb im Präsens: Pronomen ist Subjekt nur, wenn kein anderes Subjekt im Satz steht („die Daten, die wir erheben“)
    if any(w in _PRONOMEN_SUBJ for w in low[1:]) or any(w[:1].isupper() for w in worte[1:-1]):
        return False, False
    return worte[-1][:1].islower() and len(worte[-1]) >= 4, False


SPRECHAKT_RE = re.compile(r"\b(?:sag\w*|erklär\w*|mein\w*|glaub\w*|bericht\w*|erzähl\w*|äußer\w*|vernein\w*|bejah\w*|gibt\s+an|"
                         r"geben\s+an|räum\w*\s+(?:\S+\s+){0,3}?ein|mach\w*\s+(?:\S+\s+){0,3}?deutlich|beton\w*|beschreib\w*|"
                         r"schilder\w*|begründ\w*|vermut\w*|hoff\w*|wünsch\w*|befürcht\w*|find\w*|empfind\w*)\b", re.IGNORECASE)


def wiedergegebene_rede(L: Lauf, s: dict, vorne: str) -> bool:
    """Steht vor dem dass-Satz eine Person oder Quelle als Subjekt („Gagné und Deci betonen, dass …“, „Erik betont …“)?"""
    if L.quelle.get(s["nr"]) or L.autor.get(s["nr"]) or personen_anfang(s["text"]) or AUTORENLISTE_RE.search(vorne):
        return True
    if re.match(r"\s*[„\"(»]?(?:Er|Sie|Wir|Ich|Man)\s", vorne):
        return True
    worte = [w for w in analyse.tokens(vorne) if analyse.ist_wort(w)]
    if len(worte) >= 3 and worte[1].lower() in ("und", "&") and worte[0][:1].isupper() and worte[2][:1].isupper() \
            and namenartig(worte[0]) and namenartig(worte[2]):
        return True  # „Hackman und Oldham haben darauf hingewiesen“
    if REDEVERB_RE.search(vorne) and not sachliches_subjekt(vorne):
        return True  # „Erik betont dreimal, dass …“: Redeverb mit (vermutlich) einer Person als Subjekt
    if SPRECHAKT_RE.search(vorne) and re.search(r"\b(?:er|sie|wir|ich)\b", vorne):
        return True  # „Mit der folgenden Aussage macht sie deutlich, dass …“
    if re.search(r"\b(?:sei|seien|habe|könne|müsse|werde|solle|gebe|liege)\b", vorne):
        return True  # Konjunktiv I: indirekte Rede („Entscheidend sei vielmehr, dass …“)
    return any(ist_person(w) for w in worte if w[:1].isupper())


def handelndes_subjekt(teil: str) -> bool:
    """Hat der Nebensatz ein handelndes Subjekt (Person, Organisation)? Dann beim Nominalisieren behalten. Pronomen zählen
    nicht: sie verweisen meist auf das Subjekt des Hauptsatzes, das ohnehin stehen bleibt."""
    worte = [w for w in analyse.tokens(teil) if analyse.ist_wort(w)]
    for w in worte[1:]:
        low = w.lower()
        if w[:1].isupper() and (ist_person(w) or low in AKTEURE or ist_genderform(w)):
            return True
    return False


def nebensatz_auftrag(L: Lauf, s: dict, mk: str) -> tuple[int, str] | None:
    """(Rang, Auftragstext) für einen Satz mit genau einem Nebensatz, oder None. Ankündigungen („lässt sich festhalten, dass“)
    sind ein eigener Auftrag (Ankündigung streichen) und kein Nominalisierungsfall."""
    for rang, (name, rx, technik, status) in enumerate(NEBENSATZ_TYPEN):
        t = rx.search(mk)
        if not t:
            continue
        rest = mk[t.start():].lstrip(", ")
        if name == "relativ" or t.start() == 0:
            teil = re.split(r"[,;]", rest, maxsplit=1)[0]  # eingebetteter Relativsatz bzw. Nebensatz im Vorfeld
        elif re.search(r"[,;]", rest):
            return None  # Nebensatz mit Einschub, Infinitivgruppe oder Aufzählung: nominalisiert entstehen Nomenketten
        else:
            teil = rest
        n_teil = sum(1 for w in analyse.tokens(teil) if analyse.ist_wort(w))
        werden = any(w.lower() in analyse.WERDEN_FORMEN for w in analyse.tokens(teil))
        if name == "relativ":
            ok, passiv = relativsatz_umbaubar(mk[:t.start()], teil)
            if not ok:
                return None
            if passiv and "nebensatz_relativ" in L.ausgesetzt:
                L.unterdrueckt["nebensatz_relativ"] += 1
                return None  # wenig Passiv im Text: den Passiv-Relativsatz nicht zum Partizip machen
        else:
            if n_teil - 1 > NEBENSATZ_MAX or any(w.lower() in analyse.MODALVERBEN | _KONJUNKTIV for w in analyse.tokens(teil)):
                return None  # Modalverb oder Konjunktiv: Möglichkeit bzw. Annahme ginge in der Nominalgruppe verloren
            vorne = mk[:t.start()]
            if name == "dass" and re.search(r"\b(?:so|derart|dermaßen|solcherart)\s+(?:[\w-]+\s+){0,3}?[\w-]+\s*$", vorne):
                return None  # „so gewählt, dass …“: Folge- bzw. Zwecksatz, kein Inhaltssatz
            if name == "dass" and wiedergegebene_rede(L, s, vorne):
                return None  # Paraphrase einer Person oder Quelle bleibt als dass-Satz stehen
            if name != "dass" and (SPRECHAKT_RE.search(vorne) or REDEVERB_RE.search(vorne)) and wiedergegebene_rede(L, s, vorne):
                return None  # „Yara verneint die Frage, da sie …“: wiedergegebene Begründung einer Person
        if werden and "nebensatz_werden" in L.ausgesetzt:
            L.unterdrueckt["nebensatz_werden"] += 1
            return None  # „werden“ ist schon seltener als bei Menschen: den Nebensatz mit „werden“ nicht wegformulieren
        if name == "sonst":
            w = t.group("w").lower()
            bsp, art = NEBENSATZ_BEISPIEL[w]
            technik, status = technik.format(w=w, bsp=bsp), status.format(art=art)
        text_ = technik[0].upper() + technik[1:]
        if name != "relativ" and handelndes_subjekt(teil):
            text_ += "; Handelnde behalten (Akteur als Genitiv oder mit „durch“)"
        if status:
            text_ += f"; {status}"
        return rang, text_ + "."
    return None


def _nebensaetze(L: Lauf) -> None:
    neben_ids = [k for k in ("teilsatz_verhaeltnis_21", "anteil_saetze_mit_nebensatz", "woerter_pro_teilsatz") if L.ki_auffaellig(k)]
    if not neben_ids:
        return
    verteil, mit_neben = Counter(), 0
    for s in L.fokus:
        h_, n_, _ = analyse.teilsatz_zerlegung(s["text"])
        verteil[h_ + n_] += 1
        mit_neben += n_ > 0
    k = 0
    if "teilsatz_verhaeltnis_21" in neben_ids:
        p50 = L.p_("teilsatz_verhaeltnis_21", "p50")
        k = max(k, math.ceil((verteil[2] + 0.5 - p50 * (verteil[1] + 0.5)) / (1 + p50)))
    if "anteil_saetze_mit_nebensatz" in neben_ids:
        k = max(k, math.ceil(mit_neben - L.p_("anteil_saetze_mit_nebensatz", "p50") * len(L.fokus)))
    if "woerter_pro_teilsatz" in neben_ids:
        k = max(k, 2)
    k = min(4, max(0, k))
    kandidaten = []
    for s in L.fokus:
        if s["woerter"] < 8 or not L.nutzbar(s) or s["nr"] in L.belegt or L.langes_zitat(s):
            continue
        h_, n_, _ = analyse.teilsatz_zerlegung(s["text"])
        if h_ != 1 or n_ != 1:
            continue
        mk = L.masken[s["nr"]]
        if ANKUENDIGUNG_RE.search(mk):
            continue  # „lässt sich festhalten, dass …“: ein Auftrag (Ankündigung streichen) in der Funktionswort-Familie
        auftrag = nebensatz_auftrag(L, s, mk)
        if auftrag:
            kandidaten.append((auftrag[0], s["nr"], s, auftrag[1]))
    n_ns = 0
    for _, _, s, text_ in sorted(kandidaten, key=lambda x: (x[0], x[1])):
        if n_ns >= k:
            break
        if L.hinweis("nebensatz", s, f"{zitat(s)}: {text_}", 0.8):
            n_ns += 1
    # Kommas: viele kurze Teilsätze. Teilen nur, wenn lange Sätze nicht fehlen; ist das Verdichten ausgesetzt, nur Herauslösen.
    verdichten_aus = "nebensatz" in L.ausgesetzt or bool(L.jenseits)
    teilen_ok = L.diag.get("modus") == "teilen" or (L.p_("anteil_lange_saetze", "p50") is not None
                                                   and L.diag.get("anteil_lange", 0) >= L.p_("anteil_lange_saetze", "p50"))
    n_ko = 0
    for s in L.fokus:
        if n_ko >= 3:
            break
        mk = analyse._ohne_zahlzeichen(L.masken[s["nr"]]) if hasattr(analyse, "_ohne_zahlzeichen") else L.masken[s["nr"]]
        mk = AUTORENLISTE_RE.sub(lambda x: x.group(0).replace(",", ""), mk)  # „Kahneman, Knetsch und Thaler“
        teile = max(1, s.get("teilsaetze", 1))
        if mk.count(",") < 3 or s["woerter"] / teile >= 10 or not L.nutzbar(s):
            continue
        if (teilen_ok or verdichten_aus) and s["woerter"] < LANG_AB:
            tat = "Einen Einschub als eigenen Satz herauslösen."
        elif verdichten_aus:
            continue
        else:
            tat = "Einen Nebensatz oder Einschub zur Nominalgruppe machen (Länge bleibt, Kommas sinken)."
        if L.hinweis("kommas", s, f"{zitat(s)}: {mk.count(',')} Kommas bei kurzen Teilsätzen. {tat}", 0.7):
            n_ko += 1


def _begriffe(L: Lauf) -> None:
    """Begriffe halten: Anknüpfung (Possessiv, „Sie/Er“, „Diese + Sammelwort“), Begriffsaufnahme und Synonym-Wechsel."""
    aufnahme = L.kz.get("anteil_saetze_mit_wortaufnahme")
    begriffe_lokal = (L.ki_auffaellig("anteil_saetze_mit_wortaufnahme") or L.ki_auffaellig("nachbarsatz_ueberlappung")) \
        and (aufnahme is None or aufnahme["wert"] < aufnahme["mensch_p50"])
    fw = L.kz.get("fw_profil_llr_pro_1000")
    fw_aktiv = bool(fw and fw["wert"] < fw["mensch_p25"])
    if begriffe_lokal and aufnahme:
        teilt = sum(1 for a, b in zip(L.fokus, L.fokus[1:]) if L.begriffe_info[a["nr"]]["staemme"] & L.begriffe_info[b["nr"]]["staemme"])
        k_begriffe = max(0, math.ceil(aufnahme["mensch_p50"] * max(1, len(L.fokus) - 1)) - teilt)
    else:
        k_begriffe = 0
    # Possessiv/„Sie“ zählen auch als Funktionswort-Hebel; „Diese + Sammelwort“ nur über die Begriffs-Kennzahlen
    n_begr = _anknuepfung(L, k_begriffe, min(4, max(k_begriffe, 2 if fw_aktiv else 0)))
    if k_begriffe > n_begr:
        _kein_bezug(L, min(4, k_begriffe - n_begr))
    _synonyme(L)


_SIE_SINGULAR = {"ist", "war", "hat", "hatte", "wird", "wurde", "kann", "konnte", "muss", "musste", "soll", "sollte", "darf", "will",
                 "mag", "bleibt", "gilt", "steht", "liegt", "geht", "lässt", "sei", "wäre", "hätte", "könnte", "müsste", "dürfte"}
_SIE_PLURAL = {"sind", "waren", "haben", "hatten", "werden", "wurden", "können", "konnten", "müssen", "mussten", "sollen", "sollten",
               "dürfen", "wollen", "bleiben", "gelten", "stehen", "liegen", "gehen", "lassen", "seien", "wären", "hätten", "könnten"}


def bezug_vorschlag(L: Lauf, a: dict, b: dict, art: str, wort: str) -> tuple[bool, list[str]]:
    """(Hinweis sinnvoll?, Kandidaten) für den Bezug eines Satzanfangs („Sie“, „Ihr …“, „Seine …“, „Diese …“) in Satz a.
    „Sie/Er“: genau ein Personenkandidat in Satz a (Autoren, Personenwort) ist eindeutig – dann kein Hinweis. Sonst nach
    Numerus und Genus filtern („Ihr“ → Femininum oder Plural, „Sein“ → weder noch); bleibt ein Kandidat, nur diesen nennen."""
    kand = bezugskandidaten(a["text"])
    if L.autor.get(a["nr"]):
        erstes = next((k for k in kand if namenartig(k["text"].split()[0])), None)
        if erstes:
            erstes["person"] = True
    personen = [k for k in kand if k["person"]]
    low = wort.lower()
    # Genus ist nur an typischen Endungen erkennbar („-ung“ feminin); ohne solche Endung ist es unbekannt, nicht „nicht feminin“
    unbekannt = [k for k in kand if not k["feminin"] and not k["plural"] and not k["person"]]
    if art == "pron":
        kette = {"er": r"er|ihm|ihn|seine[mnrs]?", "sie": r"sie|ihre[mnrs]?|ihr"}[low]
        if re.search(rf"\b(?:{kette})\b", L.masken[a["nr"]], re.IGNORECASE):
            return False, []  # Pronomen-Kette: der Bezug steht schon vor Satz a und ist eingeführt
        if len(personen) == 1:
            return False, []  # „Sie“ = die zuvor genannte Person bzw. Autorengruppe
        if len(personen) > 1:
            return True, [k["text"] for k in personen]
        verb = (analyse.tokens(b["text"].lstrip("„\"(»"))[1:2] or [""])[0].lower()
        if low == "er":
            wahl = unbekannt
        elif verb in _SIE_PLURAL or (verb.endswith("en") and verb not in _SIE_SINGULAR):
            wahl = [k for k in kand if k["plural_moeglich"] and not k["feminin"]]
        else:
            wahl = [k for k in kand if k["feminin"]] or unbekannt
    elif art == "poss":
        kette = {"ihr": r"sie|ihre[mnrs]?|ihr|ihnen", "sei": r"er|ihm|ihn|seine[mnrs]?|sein(?=\s+(?-i:[A-ZÄÖÜ]))"}.get(low[:3], "")
        if kette and re.search(rf"\b(?:{kette})\b", L.masken[a["nr"]], re.IGNORECASE):
            return True, []  # Possessiv-Kette („… ihre eigene Kultur. Ihr Stolz …“): Bezug vor Satz a eingeführt – nicht raten
        if low.startswith(("ihr", "deren")):
            wahl = [k for k in kand if k["feminin"] or k["plural"]] or unbekannt
        else:  # sein…, dessen: auch eine (männliche) Person aus Satz a („Ranchard glaubt … / Seine Frau …“)
            wahl = [k for k in kand if not k["feminin"] and not k["plural"]
                    and not (k["person"] and k["text"].split()[-1].lower().endswith("in"))]
    else:
        wahl = [k for k in kand if not k["person"]]
    return True, [k["text"] for k in wahl]


def _bezug_text(kand: list[str], a: dict) -> str:
    if len(kand) == 1:
        return f"vermutlich „{kand[0]}“ aus Satz {a['nr']}"
    if len(kand) == 2:
        return f"vermutlich „{kand[0]}“ oder „{kand[1]}“ aus Satz {a['nr']}"
    return f"das Bezugswort aus Satz {a['nr']} ausdrücklich nennen"


def _anknuepfung(L: Lauf, k_begriffe: int, cap: int) -> int:
    n = 0
    if not cap or "anknuepfung" in L.ausgesetzt:
        return 0
    for liste in L.absaetze.values():
        for a, b in zip(liste, liste[1:]):
            if n >= cap:
                break
            if not (L.nutzbar(a) and L.nutzbar(b)) or b["nr"] in L.gebuendelte_b or L.beginnt_im_zitat(b):
                continue  # „Ihre …“/„Sie …“ als Zitatanfang gehört zum fremden Wortlaut
            mt = ANKNUEPF_RE.match(b["text"].lstrip("„\"(»"))
            if not mt or verbunden(L.begriffe_info[a["nr"]], L.begriffe_info[b["nr"]]):
                continue
            art = "dem" if mt.group("dem") else ("pron" if mt.group("pron") else "poss")
            if art == "dem" and (not k_begriffe or not ist_kapselwort(mt.group("nomen"))):
                continue
            if art == "pron" and personen_anfang(a["text"]):
                continue  # „Sie“ = die zuvor genannten Personen/Autoren
            if art == "poss" and (RUECKVERWEIS_RE.search(" ".join(b["text"].split()[1:8])) or KATAPHER_RE.match(b["text"].lstrip("„\"(»"))):
                continue  # Bezug folgt im selben Satz („Ihren Ursprung hat diese Form …“, „Seine Wirkung entfaltet ein …“)
            wort = mt.group("dem") or mt.group("pron") or mt.group("poss")
            sinnvoll, kand = bezug_vorschlag(L, a, b, art, wort)
            if not sinnvoll:
                continue
            bezug = _bezug_text(kand, a)
            if art == "dem":
                beispiel = f" (z. B. {' oder '.join(f'„{k}“' for k in kand[:2])})" if 0 < len(kand) <= 2 else ""
                t_ = (f"{zitat(b)}: „{mt.group('dem')} {mt.group('nomen')}“ ist ein abstraktes Sammelwort – prüfen, ob ein Begriff aus "
                      f"Satz {a['nr']} präziser ist{beispiel}.")
            elif art == "pron":
                t_ = f"{zitat(b)}: „{wort}“ am Satzanfang durch den Bezugsbegriff ersetzen ({bezug})."
            else:
                t_ = f"{zitat(b)}: „{wort} …“ am Satzanfang durch Artikel + Bezugswort im Genitiv ersetzen ({bezug})."
            if L.hinweis("anknuepfung", b, t_, 1.0):
                L.hinweise[-1]["art"] = art
                n += 1
    return n


_AUFZAEHL_ANKUENDIGUNG_RE = re.compile(r"\b(?:zwei|drei|vier|fünf|sechs|mehrere[n]?|folgende[n]?|verschiedene[n]?)\s+(?:[a-zäöüß][\w-]*\s+)?"
                                       r"[A-ZÄÖÜ]|:\s*$")
_AUFZAEHL_WORT_RE = re.compile(r"\b(?:erstens|zweitens|drittens|viertens|schließlich|zudem|außerdem|ebenso|ebenfalls|ferner|weiterhin|"
                               r"zum einen|zum anderen|darüber hinaus|hinzu kommt|an (?:erster|zweiter|dritter) Stelle|zunächst|"
                               r"zuerst|als (?:erstes|zweites|nächstes))\b", re.IGNORECASE)
_DIES_IRGENDWO_RE = re.compile(r"\b(?:dies|diese[rsmn]?|solche[rsmn]?)\b", re.IGNORECASE)
# Rückbezug in den ersten Wörtern: Personalpronomen („Dennoch ermöglichen sie …“), Beispiel-Anschluss („Ein Museum kann etwa …“),
# Ordnungszahl („Das dritte Merkmal …“)
_BEZUG_IM_KOPF_RE = re.compile(r"\b(?:sie|er|ihm|ihn|ihnen|beide[sn]?|etwa|beispielsweise|zum Beispiel|z\.\s?B\.|insbesondere|"
                               r"erste[nrs]?|zweite[nrs]?|dritte[nrs]?|vierte[nrs]?|letzte[nrs]?|weitere[nrs]?)\b")


def aufzaehlungsglied(liste: list[dict], j: int) -> bool:
    """Ist Satz liste[j] Glied einer Aufzählung? Angekündigt („an allen drei Punkten“, „folgende …“, Doppelpunkt) in einem der
    drei Sätze davor, oder mit Aufzählungswort in den ersten acht Wörtern („…, kann schließlich …“)."""
    b = liste[j]
    if _AUFZAEHL_WORT_RE.search(" ".join(b["text"].split()[:8])):
        return True
    if any(_AUFZAEHL_ANKUENDIGUNG_RE.search(x["text"]) for x in liste[max(0, j - 3):j]):
        return True
    # Erläuterung eines Aufzählungsglieds („Ein weiteres Risiko liegt in der Technik.“ / „Drittens …“ → Beispiele dazu)
    return any(AUFZAEHLUNG_RE.match(x["text"].lstrip("„\"(»")) or _AUFZAEHL_WORT_RE.search(" ".join(x["text"].split()[:8]))
               for x in liste[max(0, j - 2):j])


def fachbegriff_anfang(L: Lauf, b: dict) -> bool:
    """Beginnt der Satz mit einem Fachbegriff oder Eigennamen (Akronym, mehrfach verwendeter Mehrwortbegriff, Teil einer
    Gleichsetzung „A (B)“)? Dann nie zum Ersetzen anregen."""
    anf = b["text"].lstrip("„\"(»")
    toks = [t for t in analyse.tokens(anf)[:4] if analyse.ist_wort(t)]
    if not toks:
        return False
    if re.fullmatch(r"[A-ZÄÖÜ]{2,6}s?", toks[0]):
        return True
    if any(anf.startswith(lb) or anf.split(" ", 1)[-1].startswith(lb) for lb in L.leitbegriffe):
        return True
    st = analyse.inhaltsstaemme(toks[:3])
    return any(st & (sa | sb) for sa, sb in L.aliase)


def _kein_bezug(L: Lauf, k: int) -> None:
    """Begriffsaufnahme: Satz ohne erkennbaren Bezug zum Vorsatz. Nicht bei Aufzählungsgliedern, Rückverweisen („dies“,
    „solche“ irgendwo im Satz), neuen Quellen und Sätzen, die mit einem Fachbegriff beginnen."""
    if "kein_bezug" in L.ausgesetzt or k <= 0:
        return
    hinweis_nrn = {h["satz"] for h in L.hinweise if h["typ"] == "anknuepfung"}
    kand = []
    for liste in L.absaetze.values():
        for j in range(1, len(liste)):
            a, b = liste[j - 1], liste[j]
            if not (L.nutzbar(a) and L.nutzbar(b)) or b["nr"] in hinweis_nrn or b["nr"] in L.gebuendelte_b or b["woerter"] < 8:
                continue
            ia, ib = L.begriffe_info[a["nr"]], L.begriffe_info[b["nr"]]
            if not (ia["staemme"] and ib["staemme"]) or verbunden(ia, ib):
                continue
            if j >= 2 and verbunden(L.begriffe_info[liste[j - 2]["nr"]], ib):
                continue  # Fenster von zwei Sätzen
            if L.beginnt_im_zitat(b):
                continue  # Satzanfang ist fremder Wortlaut
            anf = b["text"].lstrip("„\"(»")
            kopf = " ".join(anf.split()[:7])
            if AUFZAEHLUNG_RE.match(anf) or ANAPHER_RE.match(anf) or RUECKVERWEIS_RE.search(L.masken[b["nr"]]) \
                    or _DIES_IRGENDWO_RE.search(L.masken[b["nr"]]) or _BEZUG_IM_KOPF_RE.search(kopf):
                continue  # Aufzählung oder Rückverweis („Danach …“, „… ist damit denkbar“, „Dennoch ermöglichen sie …“, „etwa“)
            if aufzaehlungsglied(liste, j):
                continue  # paralleles Aufzählungsglied („Selbstorganisierte Teams …“, „Kurze Iterationen …“)
            if L.autor.get(b["nr"]) or personen_anfang(anf) or re.match(r"(?:Laut|Nach|Gemäß)\s+[A-ZÄÖÜ]", anf):
                continue  # neue Quelle: eigener Bezugspunkt
            if fachbegriff_anfang(L, b):
                continue  # „Dynamic Pricing ermöglicht …“: den Fachbegriff nicht ersetzen lassen
            frei = not any(h["satz"] == b["nr"] for h in L.hinweise)
            kand.append((0 if ARTIKEL_NOMEN_RE.match(anf) else 1, 0 if frei else 1, b["nr"], b, a))
    n = 0
    for _, _, _, b, a in sorted(kand, key=lambda x: (x[0], x[1], x[2])):
        if n >= k:
            break
        if L.hinweis("kein_bezug", b, f"{zitat(b)}: beginnt ohne Bezug zu Satz {a['nr']}. Falls dieselbe Sache gemeint ist, das Wort "
                     f"aus Satz {a['nr']} verwenden.", 0.6):
            n += 1


RECHT_RE = re.compile(r"\b(?:Richtlinie|Verordnung|DSGVO|Gesetz\w*|\w+gesetz\w*|Directive|Regulation)\b|§")


def _synonyme(L: Lauf) -> None:
    """Synonym-Wechsel („Kunden“/„Konsumenten“). Nicht, wenn die seltene Form genau einmal vorkommt und dort Rechtsbegriff
    (Richtlinie, Verordnung, §, Gesetz) oder in „A (B)“ gleichgesetzt ist; nicht erneut, wenn die Zählungen seit der Vorrunde
    unverändert sind (dann ist die Wahl bewusst)."""
    if not any(L.ki_auffaellig(k, nur_rot=True) for k in ("mattr_100", "mtld", "inhaltswort_mattr_50")) or "synonyme" in L.ausgesetzt:
        return
    vorher = {h.get("anfang"): h.get("zaehlung") for h in (L.vorher or {}).get("hinweise") or []
              if isinstance(h, dict) and h.get("typ") == "synonyme"}
    n = 0
    for c in synonym_cluster(L.fokus, L.masken):
        if n >= 2:
            break
        # geschützte Einzelform (Rechtsbegriff, Gleichsetzung) fällt aus dem Cluster; die übrigen Formen zählen weiter
        # („Kunden“ 8× / „Konsumenten“ 3× bleibt ein Fund, auch wenn „Verbraucher“ 1× im Satz mit der Richtlinie steht)
        geschuetzt = set()
        for w, k in c["varianten"][1:]:
            if k != 1:
                continue
            nr = c["saetze"].get(w, [None])[0]
            satz_text = L.nach_nr[nr]["text"] if nr in L.nach_nr else ""
            st = analyse.inhaltsstaemme(analyse.tokens(w))
            if RECHT_RE.search(satz_text) or any(st & (sa | sb) for sa, sb in L.aliase):
                geschuetzt.add(w)
        varianten = [(w, k) for w, k in c["varianten"] if w not in geschuetzt]
        if len(varianten) < 2 or sum(k for _, k in varianten) < 4:
            continue
        schl = "syn:" + "|".join(sorted(w.lower() for w, _ in varianten))
        zaehlung = {w.lower(): k for w, k in varianten}
        if vorher.get(schl) == zaehlung and not text_unveraendert(L):
            continue  # überarbeitet, aber diese Wörter nicht angefasst: Wahl offenbar bewusst (nur erneut gemessen: wiederholen)
        formen = sorted({f for w, _ in varianten for f in c.get("formen_je", {}).get(w, [w.lower()])})
        liste_ = ", ".join(f"„{w}“ ({k}×)" for w, k in varianten)
        if L.hinweis("synonyme", None, f"Für dieselbe Sache wechseln die Wörter: {liste_}. Falls dasselbe gemeint ist, eine Form wählen "
                     "und im ganzen Text verwenden.", 0.9, ersetzbar=formen, anfang=schl):
            L.hinweise[-1]["zaehlung"] = zaehlung
            n += 1


# Funktionswort-Konstruktionen: (id, Hinweistyp, übernutztes Wort, Regex, Technik). Technik-Beispiele an neutralen Sätzen.
FW_KONSTRUKTIONEN = [
    ("ankuendigung", "fw_ankuendigung", ("sich", "dass"), ANKUENDIGUNG_RE,
     "kündigt nur an – streichen und die Aussage als Hauptsatz schreiben (Beispiel: „Es lässt sich festhalten, dass die Kosten "
     "steigen.“ → „Die Kosten steigen.“)"),
    ("laesst_sich", "fw_lassen", ("sich",), LASSEN_SICH_RE,
     "→ Passiv ohne Modalverb oder direktes Verb (Beispiel: „Die Abweichung lässt sich auf Lieferengpässe zurückführen.“ → "
     "„Die Abweichung geht auf Lieferengpässe zurück.“); nur wenn wirklich eine Möglichkeit gemeint ist, „kann … werden“"),
    ("zeigt_sich", "fw_zeigt", ("sich",), ZEIGT_SICH_RE,
     "– sagen, wer oder was es zeigt, oder das Ergebnis direkt nennen (Beispiel: „In der Befragung zeigt sich ein Wandel.“ → "
     "„Die Befragung zeigt einen Wandel.“)"),
    ("ergibt_sich", "fw_ergibt", ("sich",), ERGIBT_SICH_RE,
     "→ „folgt“ bzw. „entsteht“, die Richtung bleibt (Beispiel: „Daraus ergibt sich ein Mehraufwand.“ → „Daraus folgt ein "
     "Mehraufwand.“)"),
    ("dient_als", "fw_als", ("als",), DIENT_ALS_RE,
     "→ „ist“ oder „bildet“ (Beispiel: „Der Bericht dient als Grundlage der Planung.“ → „Der Bericht bildet die Grundlage der "
     "Planung.“)"),
    ("versteht_sich_als", "fw_als", ("als", "sich"), VERSTEHT_SICH_ALS_RE,
     "→ „will … sein“ (Beispiel: „Das Programm versteht sich als Ergänzung.“ → „Das Programm will eine Ergänzung sein.“)"),
    ("gilt_als", "fw_als", ("als",), GILT_ALS_RE,
     "→ „wird für … gehalten“, die Einschätzung bleibt eine Einschätzung (Beispiel: „Das Verfahren gilt als zuverlässig.“ → "
     "„Das Verfahren wird für zuverlässig gehalten.“)"),
    ("redeverb_dass", "fw_dass", ("dass",), REDEVERB_KURZ_RE,
     "– den kurzen „dass“-Satz als Nominalgruppe fassen, wer handelt, bleibt genannt (Beispiel: „Die Daten zeigen, dass die "
     "Kosten steigen.“ → „Die Daten zeigen den Anstieg der Kosten.“)"),
]


_SACH_ANFANG = {"dies", "das", "diese", "dieses", "dieser", "die", "der", "den", "ein", "eine", "einer", "insgesamt", "damit",
                "daraus", "daran", "somit", "auch", "beide", "alle", "solche", "solch"}


def sachliches_subjekt(vorne: str) -> bool:
    """Steht vor dem Redeverb ein sachliches Subjekt („Dies“, „Die Daten“, „Das Beispiel“)? Namen, Pronomen und
    Personenwörter („Erik“, „Er“, „Die Autoren“) gelten als wiedergegebene Rede."""
    worte = [w for w in analyse.tokens(vorne) if analyse.ist_wort(w)]
    if not worte or worte[0].lower() not in _SACH_ANFANG:
        return False
    nomen = next((w for w in worte[1:] if w[:1].isupper()), None)
    return nomen is None or not ist_person(nomen)


def _fw_bilanz(L: Lauf, kid: str, s: dict, mk: str, t: re.Match) -> tuple[Counter, Counter] | None:
    """Profilwörter, die die Technik entfernt bzw. hinzufügt; None = an dieser Stelle nicht anwendbar."""
    prof = L.fw_profil
    vor = mk[:t.start()].strip().lower()
    es_davor = vor in ("es", "so es") or (vor.endswith(" es") and len(vor.split()) <= 3)
    weg, dazu = Counter(), Counter()
    if kid == "ankuendigung":
        weg = profilwoerter(t.group(0), prof) + (Counter({"es": 1}) if es_davor else Counter())
    elif kid == "laesst_sich":
        weg["sich"] = 1
        dazu["werden" if re.search(r"\blassen\b|\bließen\b", t.group(0), re.IGNORECASE) else "wird"] = 1
    elif kid in ("zeigt_sich", "ergibt_sich"):
        weg["sich"] = 1
        if es_davor:
            weg["es"] = 1
    elif kid == "dient_als":
        weg["als"] = 1
    elif kid == "versteht_sich_als":
        weg.update({"als": 1, "sich": 1})
    elif kid == "gilt_als":
        if L.quelle.get(s["nr"]) or L.autor.get(s["nr"]) or ZUSCHREIBUNG_RE.search(mk):
            return None  # Definition, Schwellenwert oder Einschätzung einer Quelle: Aussagestatus nicht antasten
        weg["als"] = 1
        dazu.update({"für": 1, ("werden" if re.match(r"(?i)gelten|galten", t.group(0)) else "wird"): 1})
    elif kid == "redeverb_dass":
        rest = t.group("rest").split()
        if len(rest) > 12 or any(w.lower().strip(".") in analyse.MODALVERBEN | _KONJUNKTIV for w in rest) or s["nr"] in L.belegt:
            return None
        if re.search(r"[,;]", mk[t.end("rest"):]):
            return None  # der dass-Satz geht nach dem Komma weiter („weder … noch …“, Einschub): kein kurzer dass-Satz
        if wiedergegebene_rede(L, s, mk[:t.start()]):
            return None
        if L.quelle.get(s["nr"]) or L.autor.get(s["nr"]) or personen_anfang(s["text"]) or AUTORENLISTE_RE.search(mk):
            return None  # wiedergegebene Rede einer Person/Quelle: die Paraphrase bleibt
        if not sachliches_subjekt(mk[:t.start()] or mk):
            return None  # Subjekt ist (vermutlich) eine Person („Erik betont, dass …“, „Er zeigt, dass …“)
        weg["dass"] = 1
    return weg, dazu


FW_MIT_MODALVERB = {"dient_als", "gilt_als", "versteht_sich_als", "ergibt_sich", "zeigt_sich"}


def modalverb_im_teilsatz(maske: str, start: int, ende: int) -> str | None:
    """Modalverb im Teilsatz (zwischen den Kommas) um die Wendung, in Anführungszeichen für den Auftragstext; sonst None."""
    a = maske.rfind(",", 0, start) + 1
    e = maske.find(",", ende)
    teil = maske[a:e if e >= 0 else len(maske)]
    mv = next((w for w in analyse.tokens(teil) if w.lower() in analyse.MODALVERBEN), None)
    return f"„{mv.lower()}“" if mv else None


def _funktionswoerter(L: Lauf) -> None:
    """Funktionswort-Profil: konkrete KI-typische Konstruktionen übernutzter Wörter („lässt sich“, „dient als“, Ankündigung
    vor „dass“ …), je Stelle mit simulierter Wirkung auf den Funktionswort-LLR; nur Umbauten, keine Wörter einstreuen."""
    fw = L.kz.get("fw_profil_llr_pro_1000")
    if not fw or not L.fw_diag or not L.fw_profil:
        return
    unter_p25 = fw["wert"] < fw["mensch_p25"]
    if not (unter_p25 or L.modell_hebel("fw_profil_llr_pro_1000")):
        return
    zu_viel = {r["wort"] for r in L.fw_diag["woerter"] if r["zu_viel"] and r["beitrag"] < 0}
    hz = L.kz.get("hedging_pro_1000")
    hedging_hoch = bool(hz and hz["wert"] > hz["mensch_p75"])
    kand = []
    for s in L.fokus:
        if not L.nutzbar(s) or s["nr"] in L.gebuendelte_b:
            continue
        mk = L.masken[s["nr"]]
        for kid, typ, woerter, rx, technik in FW_KONSTRUKTIONEN:
            if not (set(woerter) & zu_viel) or typ in L.ausgesetzt or (kid == "laesst_sich" and hedging_hoch):
                continue
            t = rx.search(mk)
            if not t or MASKE in t.group(0):
                continue
            if any(h["satz"] == s["nr"] and h.get("spanne") and h["spanne"][0] < t.end() and t.start() < h["spanne"][1]
                   for h in L.hinweise if h["typ"] in ("floskel", "strohmann")):
                break  # dieselbe Wendung hat schon einen Muster-Auftrag („Insgesamt zeigt sich“): ein Auftrag je Stelle
            bilanz = _fw_bilanz(L, kid, s, mk, t)
            if bilanz is None:
                continue
            delta = fw_delta(L.fw_diag, L.fw_profil, *bilanz)
            if delta <= 0:
                continue  # die Technik würde hier menschlich häufigere Wörter („es“, „werden“ …) mit entfernen
            fund = t.group(0) if kid != "redeverb_dass" else t.group(0)[:t.start("rest") - t.start()].strip()
            if kid == "ankuendigung" and re.search(r"ablei|abgeleit", fund, re.IGNORECASE):
                technik = ANKUENDIGUNG_FOLGERUNG
            elif kid in FW_MIT_MODALVERB and modalverb_im_teilsatz(mk, t.start(), t.end()):
                # „kann als Signal fungieren“ → „kann ein Signal sein“: die Möglichkeit bleibt eine Möglichkeit (Aussagestatus)
                technik += f"; {modalverb_im_teilsatz(mk, t.start(), t.end())} bleibt (die Möglichkeit wird keine Tatsache)"
            kand.append((delta, s, typ, fund, technik))
            L.fw_potenzial += delta
            break  # ein Funktionswort-Auftrag je Satz
    n_max = 5 if unter_p25 else 3
    n_fw = 0
    for delta, s, typ, fund, technik in sorted(kand, key=lambda x: (-x[0], x[1]["nr"])):
        if n_fw >= n_max:
            break
        ersetzbar = [w for w in re.findall(r"[A-Za-zÄÖÜäöüß]+", fund) if w.lower() not in analyse.FUNKTIONSWOERTER and len(w) > 3]
        if L.hinweis(typ, s, f"{zitat(s)}: „{fund}“ {technik}.", 0.8, fund=fund, ersetzbar=ersetzbar):
            L.hinweise[-1]["fw_delta"] = round(delta, 3)
            n_fw += 1


# Wertungspaare: „nicht nur Last, sondern auch Instrument“ – der Kontrast selbst ist die Aussage
WERTUNG_NEG = ("last", "belastung", "bürde", "pflicht", "zwang", "risiko", "risiken", "gefahr", "bedrohung", "problem", "hindernis",
               "hürde", "barriere", "bremse", "nachteil", "schwäche", "kosten", "aufwand", "einschränkung", "störfaktor", "defizit",
               "verlust", "schaden", "hemmnis", "zumutung", "formalität", "pflichtübung")
WERTUNG_POS = ("instrument", "chance", "lösung", "treiber", "potenzial", "potential", "vorteil", "nutzen", "gewinn", "stärke", "hebel",
               "werkzeug", "motor", "möglichkeit", "impuls", "mehrwert", "ressource", "katalysator", "investition", "gelegenheit",
               "antrieb", "erfolgsfaktor", "baustein", "schlüssel")
SONDERN_Y_RE = re.compile(r",\s+sondern\s+(?:auch\s+|vor\s+allem\s+|vielmehr\s+)?(?P<y>[^,;.]{1,120})", re.IGNORECASE)
STROHMANN_VOR_RE = re.compile(r"^(?:Auf\s+den\s+ersten\s+Blick)\b|\b(?:könnte|ließe|mag|möchte)\s+man\b|\bließe\s+sich\b", re.IGNORECASE)


def _wertung(text: str, liste: tuple) -> str | None:
    for w in analyse.tokens(text):
        low = w.lower()
        if any(low.startswith(x) or low.endswith(x) for x in liste):
            return w
    return None


def wertungspaar(mk: str) -> tuple[str, str] | None:
    """„nicht (nur) X, sondern (auch) Y“ mit gegensätzlicher Wertung (Last ↔ Instrument, Risiko ↔ Chance)."""
    mx, my = NICHT_X_RE.search(mk), SONDERN_Y_RE.search(mk)
    if not mx or not my:
        return None
    x, y = mx.group("x"), my.group("y")
    for a, b in ((WERTUNG_NEG, WERTUNG_POS), (WERTUNG_POS, WERTUNG_NEG)):
        wx, wy = _wertung(x, a), _wertung(y, b)
        if wx and wy:
            return wx, wy
    return None


def _floskeln(L: Lauf) -> None:
    """KI-Floskeln und -Konstruktionen, dann Konnektoren."""
    _muster(L)
    _konnektoren(L)


def _muster(L: Lauf) -> None:
    """KI-Muster bis zum menschlichen Median (Kontingent), Gegenfolie („nicht X, sondern Y“) und Strohmann-Paar."""
    km = L.kz.get("ki_muster_pro_1000")
    floskel_aktiv = L.ki_auffaellig("ki_muster_pro_1000")
    sondern_aktiv = L.ki_auffaellig("sondern_pro_1000")
    # Kontingent: Gewicht, das bis zum menschlichen Median wegfallen muss (nie bis null jagen)
    noetig = max(0.0, (km["wert"] - km["mensch_p50"]) * L.tok_fokus / 1000) if km else 0.0
    treffer = []
    for s in L.fokus:
        if not L.nutzbar(s):
            continue
        for _a, _e, g, mu, fund, _v in analyse.muster_treffer(L.masken[s["nr"]], L.muster):
            if g > 0 and MASKE not in fund:
                treffer.append((g, s, mu, fund, _a, _e))
    # additive Gegenfolie („nicht nur X, sondern auch Y“) nur, wenn „…, sondern“ auch ohne sie über P75 läge
    n_sondern = sum(len(re.findall(r",\s*sondern\b", L.masken[s["nr"]], re.IGNORECASE)) for s in L.fokus)
    n_additiv = sum(1 for g, s, mu, fund, *_ in treffer if mu["id"] in GEGENFOLIE_MUSTER and ADDITIV_RE.search(fund))
    p75 = L.p_("sondern_pro_1000", "p75")
    additiv_ok = p75 is not None and 1000 * (n_sondern - n_additiv) / L.tok_fokus > p75
    entfernt = 0.0
    strohmann_n: set[int] = set()
    for g, s, mu, fund, _a, _e in sorted(treffer, key=lambda t: (-t[0], t[1]["nr"])):
        gegenfolie = mu["id"] in GEGENFOLIE_MUSTER
        # hochpräzise Muster (Gewicht ≥ 1,5) auch im grünen Bereich, solange der Wert über dem menschlichen Median liegt –
        # nicht die Gegenfolie: echte Kontraste sind auch in menschlichen Texten häufig
        erlaubt = floskel_aktiv or (g >= 1.5 and noetig > 0 and not gegenfolie) or (gegenfolie and sondern_aktiv)
        if not erlaubt or s["nr"] in strohmann_n:
            continue
        if entfernt >= noetig and not (gegenfolie and sondern_aktiv):
            continue
        mk = L.masken[s["nr"]]
        if mu["id"] == "greift_zu_kurz" and _strohmann(L, s, g):
            strohmann_n.add(s["nr"])
            entfernt += g
            continue
        ersatz = mu.get("ersatz", "durch die konkrete Aussage ersetzen")
        typ, info = "floskel", False
        if gegenfolie:
            typ = "gegenfolie"
            paar = wertungspaar(mk)
            mx = NICHT_X_RE.search(mk)
            x_staemme = analyse.inhaltsstaemme(analyse.tokens(ADDITIV_RE.sub(" ", mx.group("x")))) if mx else set()
            vorige = [L.nach_nr[n] for n in range(s["nr"] - 3, s["nr"]) if n in L.nach_nr]
            x_genannt = bool(x_staemme) and any(x_staemme & L.begriffe_info[v["nr"]]["staemme"] for v in vorige)
            x_worte = [w for w in analyse.tokens(ADDITIV_RE.sub(" ", mx.group("x"))) if analyse.ist_wort(w)] if mx else []
            if paar:
                ersatz, info = f"Kontrast ist hier die Aussage („{paar[0]}“ ↔ „{paar[1]}“) – beibehalten.", True
            elif x_worte and len(x_worte) <= 2 and all(w[:1].islower() for w in x_worte) and not ADDITIV_RE.search(fund):
                ersatz, info = "Kontrast zweier Eigenschaften ist hier die Aussage – beibehalten.", True
            elif ADDITIV_RE.search(fund):
                if not additiv_ok:
                    continue
                ersatz = "zu „neben X auch Y“ umstellen; beide Teile und ihre Gewichtung bleiben."
            elif L.quelle.get(s["nr"]) or REDEVERB_RE.search(mk):
                ersatz = "Aussage einer Quelle bzw. Redeverb: nur umformulieren (z. B. zwei Aussagen nacheinander), X behalten."
            elif x_genannt:
                ersatz = "X wird kurz vorher im Text genannt, die Gegenüberstellung ist begründet: nur umformulieren, X behalten."
        # nur Auslöser-Wörter als ersetzbar melden, nie Platzhalter des Musters (die sind Inhalt des Nutzers)
        worte = [w for w in floskel_kopfwoerter(mk, _a, _e, mu["_re"])
                 if w.lower() not in analyse.FUNKTIONSWOERTER and len(w) > 2] if typ == "floskel" else []
        if L.hinweis(typ, s, f"{zitat(s)}: „{fund}“ – {ersatz}", 0.2 if info else 0.6 + 0.3 * g, fund=fund, ersetzbar=worte):
            L.hinweise[-1].update({"muster_gewicht": g, "spanne": (_a, _e), "info": info})
            if not info:
                entfernt += g


def _strohmann(L: Lauf, s: dict, g: float) -> bool:
    """„Auf den ersten Blick könnte man … / Diese Einschätzung greift jedoch zu kurz“: ein Auftrag über beide Sätze statt
    zweier, die sich gegenseitig aufheben. Hinweise an beiden Sätzen entfallen (siehe ein_auftrag_je_satz)."""
    vor = L.nach_nr.get(s["nr"] - 1)
    if not vor or vor["absatz"] != s["absatz"] or not L.nutzbar(vor) or not STROHMANN_VOR_RE.search(L.masken[vor["nr"]]):
        return False
    if not L.hinweis("strohmann", vor, f"Satz {vor['nr']} bis {s['nr']} („{anfang(vor['text'], 5)}“ … „{anfang(s['text'], 5)}“): "
                     "aufgebaute Gegenposition samt Abweisung durch die eigene These ersetzen – die These direkt nennen. Vertritt eine "
                     "Quelle die Gegenposition, die Quelle behalten und sagen, was ihr fehlt.", 0.6 + 0.3 * g, weitere=(s["nr"],),
                     fund="greift … zu kurz"):
        return False
    L.hinweise[-1].update({"muster_gewicht": g, "sperrt": [vor["nr"], s["nr"]]})
    return True


def aufzaehlung_davor(L: Lauf, s: dict, fenster: int = 15) -> bool:
    """Steht in den Sätzen davor ein Aufzählungsglied („erstens“, „an erster Stelle“, „ein weiteres …“, „zum einen“)?"""
    for n in range(max(1, s["nr"] - fenster), s["nr"]):
        x = L.nach_nr.get(n)
        if not x:
            continue
        anf = x["text"].lstrip("„\"(»")
        kopf = " ".join(anf.split()[:8]).lower()
        if (AUFZAEHLUNG_RE.match(anf) and not kopf.startswith(("schließlich", "auch"))) \
                or re.search(r"\b(?:erstens|zweitens|zum einen|an (?:erster|zweiter) stelle|zunächst|zuerst)\b", kopf):
            return True
    return False


def _konnektoren(L: Lauf) -> None:
    """Konnektoren: nur KI-typische (Korpusverhältnis > KONN_STARK) bzw. gehäufte (≥ 2× derselbe im Absatz), Mittelfeld vor
    Satzanfang; Satzanfänge gar nicht, wenn Konnektor-Satzanfänge schon höchstens beim menschlichen Median liegen."""
    if not L.ki_auffaellig("konnektoren_pro_1000"):
        return
    kn = L.kz["konnektoren_pro_1000"]
    k_konn = min(6, max(0, math.ceil((kn["wert"] - kn["mensch_p50"]) * L.tok_fokus / 1000)))
    anf = L.wert("anteil_konnektor_satzanfang")
    anf50 = L.p_("anteil_konnektor_satzanfang", "p50")
    anfang_ok = anf is None or anf50 is None or anf > anf50
    funde = []  # (Absatz, Satz, Wort, im Mittelfeld?)
    for s in L.fokus:
        if not L.nutzbar(s) or s["nr"] in L.gebuendelte_b:
            continue
        mk = L.masken[s["nr"]]
        off = len(mk) - len(mk.lstrip("„\"'(»"))
        for t_ in KONNEKTOR_RE.finditer(mk):
            funde.append((s["absatz"], s, t_.group(1), t_.start() > off))
    haeufung = Counter((a, w.lower()) for a, _s, w, _m in funde)
    kand, gesehen = [], set()
    for a, s, wort, mitte in funde:
        v = konnektor_verhaeltnis(wort)
        if v is None or v <= 1.0 or (not mitte and not anfang_ok) or s["nr"] in gesehen:
            continue
        if wort.lower() == "schließlich" and not mitte and aufzaehlung_davor(L, s):
            continue  # „Schließlich …“ schließt eine Aufzählung ab („An erster Stelle …“, „Ein weiteres Risiko …“)
        stark = v > KONN_STARK
        if not stark and haeufung[(a, wort.lower())] < 2:
            continue  # nur gehäuft: derselbe Konnektor mindestens zweimal im Absatz
        frei = not any(h["satz"] == s["nr"] for h in L.hinweise)
        kand.append((0 if stark else 1, 0 if mitte else 1, 0 if frei else 1, s["nr"], s, wort, v, haeufung[(a, wort.lower())]))
        gesehen.add(s["nr"])
    n_k, gemeldet = 0, set()
    for stark_rang, _m, _f, _nr, s, wort, v, n_abs in sorted(kand):
        if n_k >= k_konn:
            break
        if stark_rang == 1:
            if (s["absatz"], wort.lower()) in gemeldet:
                continue  # bei Häufung eine Stelle je Absatz
            warum = f"steht in Absatz {s['absatz']} {n_abs}×; an dieser Stelle"
        else:
            warum = f"bei Claude etwa {f'{v:.1f}'.replace('.', ',')}× so häufig wie in echten Arbeiten;"
        if L.hinweis("konnektor", s, f"{zitat(s)}: „{wort}“ {warum} streichen, wenn der Bezug klar ist, oder über das wiederholte "
                     "Nomen anschließen (nicht nur verschieben).", 0.9, fund=wort, ersetzbar=[wort]):
            L.hinweise[-1]["konnektor_verhaeltnis"] = round(v, 2)
            gemeldet.add((s["absatz"], wort.lower()))
            n_k += 1


def _zeichen(L: Lauf) -> None:
    for s in L.fokus:
        if not L.nutzbar(s):
            continue
        mk = analyse._ohne_zahlzeichen(L.masken[s["nr"]]) if hasattr(analyse, "_ohne_zahlzeichen") else L.masken[s["nr"]]
        if ";" in mk:
            L.hinweis("semikolon", s, f"{zitat(s)}: Semikolon durch Punkt ersetzen oder mit „und“/„weil“ verbinden.", 1.0, fund=";")
    if "doppelpunkt" in L.hebel:
        for s in L.fokus:
            if L.nutzbar(s) and re.search(r":(?!\d)\s", L.masken[s["nr"]]):
                L.hinweis("doppelpunkt", s, f"{zitat(s)}: Doppelpunkt prüfen – oft ist ein eigener Satz oder ein Nebensatz natürlicher.", 0.7,
                          fund=":")


def _abkuerzungen(L: Lauf) -> None:
    """Inhaltsneutraler Modell-Hebel: 2–3 ausgeschriebene Abkürzungen kürzen, nie über P75 hinaus (grüner Bereich)."""
    if not (L.ki_auffaellig("abkuerzungen_pro_1000") or L.modell_hebel("abkuerzungen_pro_1000")):
        return
    p50, p75 = L.p_("abkuerzungen_pro_1000", "p50"), L.p_("abkuerzungen_pro_1000", "p75")
    if p50 is None or p75 is None:
        return
    stil_re = getattr(analyse, "ABK_STIL_RE", None)
    jetzt = sum(len(stil_re.findall(s["text"])) for s in L.fokus) if stil_re else 0
    obergrenze = math.floor(p75 * L.tok_fokus / 1000) - jetzt
    k = min(3, obergrenze, max(2, math.ceil(p50 * L.tok_fokus / 1000) - jetzt))
    if k <= 0:
        return
    kand = []
    for s in L.fokus:
        if not L.nutzbar(s):
            continue
        mk = L.masken[s["nr"]]
        for rx, kurz, zaehlt in ABK_ERSATZ:
            t = rx.search(mk)
            if t and t.start() > 0 and MASKE not in t.group(0):
                kand.append((0 if zaehlt else 1, s["nr"], s, t.group(0), kurz))
                break
    for _, _, s, fund, kurz in sorted(kand, key=lambda x: (x[0], x[1]))[:k]:
        L.hinweis("abkuerzung", s, f"{zitat(s)}: „{fund}“ als „{kurz}“ schreiben – in Hochschultexten üblich, der Inhalt bleibt gleich.",
                  0.5, fund=fund, ersetzbar=[w for w in fund.split() if len(w) > 3])


# Satzanfang, der auf den Vorsatz antwortet (Gegensatz, Einschränkung, Folgerung, Gleichzeitigkeit): dort beginnt kein neuer
# Absatz („Allerdings ist die dortige Vernetzung …“, „Dennoch wird …“, „Zugleich verpflichtete …“)
ANTWORT_ANFANG_RE = re.compile(r"^(?:allerdings|jedoch|dennoch|trotzdem|doch|aber|gleichzeitig|zugleich|hingegen|dagegen|stattdessen|"
                               r"vielmehr|gleichwohl|indes|insofern|folglich|somit|also|nichtsdestotrotz|umgekehrt|andererseits)\b",
                               re.IGNORECASE)
# Rückverweis-Adjektive („die dortige Vernetzung“, „der beschriebenen Aspekte“) und Ordnungszahl ohne Nomen („Die erste besagt …“)
RUECKVERWEIS_ADJ_RE = re.compile(r"\b(?:dortige|derartige|obige|vorgenannte|genannte|beschriebene|erwähnte|skizzierte)[nmrs]?\b"
                                 r"|^(?:die|der|das)\s+(?:erste|zweite|dritte|vierte|letzte)\s+(?-i:[a-zäöüß])", re.IGNORECASE)
# Vorsatz endet mit einer Aufzählungsankündigung („… ergeben sich zwei Hypothesen.“, „… folgende Gründe:“)
ANKUENDIGUNG_ENDE_RE = re.compile(r"\b(?:zwei|drei|vier|fünf|sechs|mehrere[n]?|folgende[n]?|verschiedene[n]?)\s+(?:[a-zäöüß][\w-]*\s+)?"
                                  r"[A-ZÄÖÜ][\w-]*\s*[.:]?\s*$")


def _absatz_trennbar(L: Lauf, liste: list[dict], k_: int) -> bool:
    """Darf vor liste[k_] ein neuer Absatz beginnen? Nicht im Zitat, nicht vor Aufzählung, Anapher, Rückverweis oder einem
    Satz, der auf den Vorsatz antwortet („Allerdings …“), nicht nach einer Aufzählungsankündigung, nicht mitten in einer
    Aufzählung (erstens … zweitens), nicht nach einem Doppelpunkt."""
    s, vor = liste[k_], liste[k_ - 1]
    if not L.nutzbar(s):
        return False
    if any(s["nr"] in (h.get("weitere_nr") or []) for h in L.hinweise):
        return False  # Satz soll in diesem Durchgang mit dem vorigen verbunden werden (Bündeln, Zickzack, Strohmann-Paar)
    mv, ms = L.masken[vor["nr"]].rstrip(), L.masken[s["nr"]].lstrip()
    if mv[-1:] == MASKE and ms[:1] == MASKE:
        return False  # mitten in einem wörtlichen Zitat
    if vor["text"].rstrip().endswith(":") or ANKUENDIGUNG_ENDE_RE.search(vor["text"]):
        return False
    anf = s["text"].lstrip("„\"(»")
    kopf = " ".join(anf.split()[:6])
    if AUFZAEHLUNG_RE.match(anf) or ANAPHER_RE.match(anf) or RUECKVERWEIS_RE.search(kopf) or ANTWORT_ANFANG_RE.match(anf) \
            or RUECKVERWEIS_ADJ_RE.search(kopf):
        return False
    vorne = any(ORDINAL_RE.match(x["text"].lstrip("„\"(»")) for x in liste[:k_])
    hinten = any(ORDINAL_RE.match(x["text"].lstrip("„\"(»")) for x in liste[k_:])
    return not (vorne and hinten) and not L.pendelt("absatz_teilen", s["nr"])


def _absaetze(L: Lauf) -> None:
    """Absätze ungleich lang machen – jeder Kandidat (alle zulässigen Trennstellen, auch Kopf-/Schlussabsätze mit 1–2 Sätzen,
    und alle Zusammenlegungen benachbarter Absätze mit gemeinsamem Inhaltsstamm) wird an den Absatz-Kennzahlen simuliert.
    Ausgegeben wird höchstens ein Umbau je Runde und nur, wenn er die Sätze-pro-Absatz-Variation um ≥ ABSATZ_MIN_GEWINN
    erhöht, sie nicht über P75 treibt und Sätze pro Absatz nicht aus dem grünen Band schiebt."""
    ids = ("saetze_pro_absatz_cv", "absatzlaenge_cv", "saetze_pro_absatz", "absatzlaenge_mittel")
    if not L.absaetze or not (any(L.ki_auffaellig(k) for k in ids) or L.modell_hebel("saetze_pro_absatz_cv")):
        return
    frei = {t for t in ("absatz_teilen", "absatz_zusammen") if t not in L.ausgesetzt}
    if not frei or any(k not in L.ref for k in ("saetze_pro_absatz_cv", "saetze_pro_absatz", "absatzlaenge_cv")):
        return
    rc, rs, rw = (L.ref[k]["mensch"] for k in ("saetze_pro_absatz_cv", "saetze_pro_absatz", "absatzlaenge_cv"))
    re1 = (L.ref.get("anteil_einsatz_absaetze") or {}).get("mensch") or {"p75": 1.0}
    nrs = sorted(L.absaetze)
    anz = [len(L.absaetze[n]) for n in nrs]
    wl = [sum(s["woerter"] for s in L.absaetze[n]) for n in nrs]
    # simuliert wird auf der Absatzstruktur nach den Satz-Aufträgen dieser Runde (Teilen/Mitte +1, Bündeln −1 Satz)
    plus = Counter(h["absatz"] for h in L.hinweise if h["typ"] in ("teilen", "mitte"))
    minus = Counter(h["absatz"] for h in L.hinweise if h["typ"] in ("buendeln", "klammer_zusatz", "zickzack"))
    sim = [max(1, a + plus[n] - minus[n]) for a, n in zip(anz, nrs)]
    alt = absatz_kennzahlen(sim, wl)
    streuung = alt["cv"] < rc["p50"] and len(nrs) >= 1  # Kontingent bis zum Median der Variation
    zu_lang = L.ki_auffaellig("saetze_pro_absatz") or L.ki_auffaellig("absatzlaenge_mittel")
    if not (streuung or zu_lang):
        return
    band_s = band_abstand(alt["mittel"], L.ref["saetze_pro_absatz"])
    trenner = absatz_trenner(L.text)

    def bewerte(neu_anz: list[int], neu_wl: list[int]) -> tuple[float, dict] | None:
        neu = absatz_kennzahlen(neu_anz, neu_wl)
        nb = band_abstand(neu["mittel"], L.ref["saetze_pro_absatz"])
        if nb > band_s + 1e-9 and nb > 0:
            return None  # Sätze pro Absatz würden das grüne Band verlassen bzw. sich weiter davon entfernen
        if neu["einsatz"] > max(alt["einsatz"], re1["p75"]) + 1e-9:
            return None  # mehr Ein-Satz-Absätze als bei Menschen üblich
        if neu["cv_w"] < min(alt["cv_w"], rw["p50"]) - 1e-9 or neu["cv_w"] > max(alt["cv_w"], rw["p75"]) + 1e-9:
            return None  # die Absatzlängen in Wörtern dürfen nicht gleichmäßiger werden und nicht über P75 streuen
        if streuung:
            if neu["cv"] - alt["cv"] < ABSATZ_MIN_GEWINN or neu["cv"] > rc["p75"]:
                return None
            return abs(alt["cv"] - rc["p50"]) - abs(neu["cv"] - rc["p50"]), neu
        if neu["cv"] < alt["cv"] - 1e-9 or neu["cv"] > max(alt["cv"], rc["p75"]) + 1e-9 or nb >= band_s - 1e-9:
            # nur „zu lange Absätze“: Sätze pro Absatz müssen sinken, die Variation darf nicht leiden (sie ist das stärkere
            # Modellmerkmal; auch oberhalb des Medians würde ein Absinken p_mensch senken) und nicht über P75 steigen
            return None
        return (band_s - nb) * 0.1, neu

    kand = []  # (Wert, Art, i, Grenzen bzw. None, Begriffsgüte, neu)
    if "absatz_teilen" in frei:
        for i, nr in enumerate(nrs):
            liste = L.absaetze[nr]
            stellen = [k_ for k_ in range(1, len(liste)) if _absatz_trennbar(L, liste, k_)]
            ueb = {}
            for k_ in stellen:
                links = set().union(*(L.begriffe_info[s["nr"]]["staemme"] for s in liste[max(0, k_ - 2):k_]))
                rechts = set().union(*(L.begriffe_info[s["nr"]]["staemme"] for s in liste[k_:k_ + 2]))
                ueb[k_] = len(links & rechts) / (len(links | rechts) or 1)
            varianten = [(k_,) for k_ in stellen]
            if wl[i] > 500:  # sehr langer Absatz: auch zwei Trennstellen in einem Umbau (Teile ≥ 3 Sätze)
                varianten += [(a, b) for a in stellen for b in stellen if b - a >= 3 and a >= 3 and len(liste) - b >= 3]
            for grenzen in varianten:
                g = (0,) + grenzen + (len(liste),)
                teile = [liste[x:y] for x, y in zip(g, g[1:])]
                extra = sim[i] - anz[i]  # Satz-Aufträge in diesem Absatz: dem letzten Teil zurechnen (Näherung)
                neu_anz = sim[:i] + [len(t) for t in teile[:-1]] + [max(1, len(teile[-1]) + extra)] + sim[i + 1:]
                neu_wl = wl[:i] + [sum(s["woerter"] for s in t) for t in teile] + wl[i + 1:]
                r = bewerte(neu_anz, neu_wl)
                if r:
                    guete = 1.0 - max(ueb[k_] for k_ in grenzen)
                    kand.append((r[0] + 0.05 * guete, "teilen", i, grenzen, guete, r[1]))
    if "absatz_zusammen" in frei:
        for i in range(len(nrs) - 1):
            x, y = nrs[i], nrs[i + 1]
            if y != x + 1 or x in trenner or L.pendelt("absatz_zusammen", L.absaetze[y][0]["nr"]):
                continue  # nicht über eine Überschrift/Liste hinweg; nicht dort, wo in einer Vorrunde geteilt wurde
            if wl[i] + wl[i + 1] > max(250, max(wl)):
                continue  # kein Riesenabsatz
            sx = set().union(*(L.begriffe_info[s["nr"]]["staemme"] for s in L.absaetze[x]))
            sy = set().union(*(L.begriffe_info[s["nr"]]["staemme"] for s in L.absaetze[y]))
            gemeinsam = sx & sy
            if not gemeinsam:
                continue
            neu_anz = sim[:i] + [sim[i] + sim[i + 1]] + sim[i + 2:]
            neu_wl = wl[:i] + [wl[i] + wl[i + 1]] + wl[i + 2:]
            r = bewerte(neu_anz, neu_wl)
            if r:
                rand_x = set().union(*(L.begriffe_info[s["nr"]]["staemme"] for s in L.absaetze[x][-2:]))
                rand_y = set().union(*(L.begriffe_info[s["nr"]]["staemme"] for s in L.absaetze[y][:2]))
                guete = len(rand_x & rand_y) / (len(rand_x | rand_y) or 1)
                kand.append((r[0] + 0.05 * min(1.0, 3 * guete), "zusammen", i, gemeinsam, guete, r[1]))
    if not kand:
        return
    wert, art, i, info, guete, neu = max(kand, key=lambda k: (k[0], -k[2]))
    folge = " · ".join(str(v) for v in anz)
    if streuung:
        wie = "sehr gleichmäßig" if alt["cv"] < rc["p25"] else "gleichmäßiger als in echten Arbeiten"
        grund = (f" Grund: Sätze pro Absatz {folge} sind {wie}; danach streuen sie stärker (Variation "
                 f"{fmt(round(alt['cv'], 2))} → {fmt(round(neu['cv'], 2))}, Menschen im Median {fmt(rc['p50'])}).")
    else:
        grund = f" Grund: Ø {fmt(round(alt['mittel'], 1))} Sätze pro Absatz (Menschen meist {fmt(rs['p25'])}–{fmt(rs['p75'])})."
    if art == "teilen":
        nr = nrs[i]
        liste = L.absaetze[nr]
        g = (0,) + info + (len(liste),)
        teile = " + ".join(str(y - x) for x, y in zip(g, g[1:]))
        wo = " und ".join(f"vor Satz {liste[k_]['nr']} („{anfang(liste[k_]['text'], 5)}“)" for k_ in info)
        thema = " Dort überschneiden sich die Begriffe davor und danach wenig." if guete >= 0.85 else ""
        L.hinweis("absatz_teilen", liste[info[0]], f"Absatz {nr} ({anz[i]} Sätze): {wo} einen neuen Absatz beginnen – danach {teile} "
                  f"Sätze.{thema}{grund}", 1.0, absatz=nr)
    else:
        x, y = nrs[i], nrs[i + 1]
        wort = next((t for s in L.absaetze[y] for t in analyse.tokens(s["text"]) if analyse.ist_wort(t) and t[:1].isupper()
                     and analyse.stamm(t) in info and t.lower() not in analyse.FUNKTIONSWOERTER), None)
        thema = f" – beide behandeln „{wort}“" if wort else ""
        # erster Satz von Absatz y als Schlüssel: so erkennt das Gedächtnis ein späteres Teilen an derselben Stelle als Pendeln
        L.hinweis("absatz_zusammen", L.absaetze[y][0], f"Absatz {x} und {y} ({anz[i]} + {anz[i + 1]} Sätze) zusammenlegen{thema}.{grund}",
                  0.9, absatz=x)


def _vorgaben(L: Lauf) -> None:
    """Nutzer-Vorgaben (immer, außerhalb von Zitaten): generisches Maskulinum, keine Gedankenstriche."""
    _gender(L)
    _striche(L)


def _gender(L: Lauf) -> None:
    """Ein Hinweis je Wortstamm mit allen Satznummern im ganzen Text und der abgeleiteten Maskulinform; steht die
    Maskulinform schon im Text (Teilumsetzung), wird daraus ein Vereinheitlichungsauftrag."""
    gruppen: dict[str, dict] = {}
    for s in L.saetze:
        if not L.nutzbar(s):
            continue
        for f in gender_funde(L.masken[s["nr"]]):
            g = gruppen.setdefault(f["schluessel"], {"formen": Counter(), "saetze": [], "maskulin": f["maskulin"], "im_fokus": False})
            g["formen"][f["wort"]] += 1
            if s["nr"] not in g["saetze"]:
                g["saetze"].append(s["nr"])
            g["im_fokus"] |= L.von <= s["nr"] <= L.bis
    for schl, g in sorted(gruppen.items(), key=lambda x: x[1]["saetze"][0]):
        if not g["im_fokus"]:
            continue  # gemeldet wird, wenn der Abschnitt mit dieser Form im Fokus ist
        wort = g["formen"].most_common(1)[0][0]
        nrn = g["saetze"]
        wo = f"in Satz {nrn[0]}" if len(nrn) == 1 else f"in Satz {', '.join(map(str, nrn[:-1]))} und {nrn[-1]}"
        weitere_formen = [w for w in g["formen"] if w != wort]
        formen = f"„{wort}“" + (f" (auch {', '.join(f'„{w}“' for w in weitere_formen[:2])})" if weitere_formen else "")
        ziel = f"„{g['maskulin']}“" if g["maskulin"] else "die übliche maskuline Personenbezeichnung"
        misch = ""
        if g["maskulin"]:
            stamm = GENDER_MASKULIN.get(schl, (None, None))[1] or g["maskulin"].split("-")[-1]
            stamm_re = re.compile(r"(?<![\w-])" + re.escape(gender_schluessel(stamm)) + r"(?:e|en|er|ern|n|s)?(?![\wäöüß*:_/-])",
                                  re.IGNORECASE)
            schon = []
            for x in L.saetze:
                mk = L.masken.get(x["nr"], x["text"])
                belegt = [(f["start"], f["start"] + len(f["wort"])) for f in gender_funde(mk)]
                if any(not any(a <= t.start() < e for a, e in belegt) for t in stamm_re.finditer(mk)):
                    schon.append(x["nr"])
            if schon:
                misch = (f" Die Maskulinform steht schon in Satz {', '.join(map(str, schon[:4]))}{' …' if len(schon) > 4 else ''}: "
                         "Mischform, alle Stellen auf eine Form bringen.")
        s0 = L.nach_nr[nrn[0]] if len(nrn) == 1 else None
        if s0:
            text_ = f"{zitat(s0)}: {formen} → {ziel} (Vorgabe generisches Maskulinum).{misch}"
        else:
            text_ = f"{formen} {wo} → {ziel} (Vorgabe generisches Maskulinum), im ganzen Text einheitlich.{misch}"
        L.hinweis("gender", s0, text_, 1.5, absatz=s0["absatz"] if s0 else None, fund=wort, anfang=f"gender:{schl}")
        L.hinweise[-1]["saetze"] = nrn


# Bindestrich mit Leerzeichen zwischen zwei Adjektiven vor einem Nomen („symbolisch - pragmatisches Sportbild“, „der ethisch -
# normative Gehalt“). Zwischen beliebigen kleingeschriebenen Wörtern steht meist ein echter Gedankenstrich („bleiben hingegen -
# zumindest …“, „präsent - gelangen Nachrichten …“): dort wäre „ohne Leerzeichen“ ein Fehler.
_ADJ_SUFFIX = r"(?:isch|lich|ig|al|iv|haft|bar|ell|är|ent|ant|los|sam|ös|ar|deutsch)"
BINDE_VOR_RE = re.compile(rf"[a-zäöüß]+{_ADJ_SUFFIX}(?:e|en|em|er|es)?")
BINDE_NACH_RE = re.compile(rf"[a-zäöüß]+{_ADJ_SUFFIX}(?:e|en|em|er|es)")


def _striche(L: Lauf) -> None:
    """Gedankenstrich-Vorgabe; „ - “ zwischen zwei Adjektiven vor einem Nomen ist ein falsch gesetzter Bindestrich
    („symbolisch - pragmatisches Sportbild“), kein Gedankenstrich – Komma statt Strich wäre dort ein Fehler."""
    for s in L.fokus:
        if not L.nutzbar(s):
            continue
        mk = L.masken[s["nr"]]
        gedanke, binde = False, None
        for m in analyse.GEDANKENSTRICH_RE.finditer(mk):
            vor = re.search(r"(?<![–—-] )(?<![A-Za-zÄÖÜäöüß])([A-Za-zÄÖÜäöüß]+)\s*$", mk[:m.start()])  # nicht „- vermeintlicher - …“
            nach = re.match(r"\s*([A-Za-zÄÖÜäöüß]+)(?=\s+[A-ZÄÖÜ])", mk[m.end():])
            if m.group(0) == "-" and vor and nach and BINDE_VOR_RE.fullmatch(vor.group(1)) and BINDE_NACH_RE.fullmatch(nach.group(1)):
                binde = binde or f"{vor.group(1)} - {nach.group(1)}"
            else:
                gedanke = True
        if binde:
            L.hinweis("bindestrich", s, f"{zitat(s)}: „{binde}“ ist ein Bindestrich mit Leerzeichen – ohne Leerzeichen schreiben "
                      f"(„{binde.replace(' - ', '-')}“), nicht durch Komma ersetzen.", 0.9, fund=binde)
        if gedanke:
            L.hinweis("gedankenstrich", s, f"{zitat(s)}: Gedankenstrich durch Komma, Klammer oder neuen Satz ersetzen.", 0.8, fund="–")


GENANNT = " (schon in Runde {runde} genannt – überspringen, wenn unpassend)"


# Ein Auftrag je Satz: ausgenommen sind Nutzer-Vorgaben sowie Absatz- und Textaufträge (sie ändern keinen Satz)
EINZEL_AUSGENOMMEN = {"gender", "gedankenstrich", "bindestrich", "absatz_teilen", "absatz_zusammen", "synonyme"}
# feste Reihenfolge im kombinierten Auftrag: erst der Umbau des Satzes, dann Wendungen, zuletzt Zeichen und Abkürzungen
AUFTRAG_FOLGE = ["strohmann", "teilen", "mitte", "buendeln", "zickzack", "klammer", "klammer_zusatz", "kurz", "nebensatz", "kommas",
                 "fw_ankuendigung", "floskel", "gegenfolie", "fw_lassen", "fw_zeigt", "fw_ergibt", "fw_als", "fw_dass", "fw_dichte",
                 "anknuepfung", "kein_bezug", "konnektor", "semikolon", "doppelpunkt", "abkuerzung"]


def _teilauftrag(h: dict) -> str:
    """Auftrag eines Hinweises ohne die Stellenangabe („Satz 8 („…“): “) und ohne Gedächtnis-Zusatz."""
    text = h.get("kern") or h["text"]
    stelle = h.get("stelle")
    if stelle and text.startswith(stelle):
        text = text[len(stelle):].lstrip()
        text = text[1:].lstrip() if text.startswith(":") else text
    return text[:1].upper() + text[1:]


def ein_auftrag_je_satz(hinweise: list[dict]) -> list[dict]:
    """Höchstens ein Auftrag je Satz (Vorgaben ausgenommen): Treffen mehrere Hinweise denselben Satz – oder einen Satz, der in
    einem Mehrsatz-Auftrag (Bündeln, Strohmann-Paar) aufgeht –, werden sie zu einem Auftrag in fester Reihenfolge
    zusammengefasst. Ein Strohmann-Paar sperrt alle übrigen Hinweise an seinen beiden Sätzen."""
    rang = {t: i for i, t in enumerate(AUFTRAG_FOLGE)}
    frei = [h for h in hinweise if h["typ"] in EINZEL_AUSGENOMMEN or not h.get("satz")]
    ids_frei = {id(h) for h in frei}
    satzweise = [h for h in hinweise if id(h) not in ids_frei]
    gesperrt = {n for h in satzweise for n in h.get("sperrt") or []}
    satzweise = [h for h in satzweise if h.get("sperrt") or (h["satz"] not in gesperrt
                                                            and not set(h.get("weitere_nr") or []) & gesperrt)]
    besitzer: dict[int, int] = {}
    gruppen: dict[int, list[dict]] = {}
    for h in sorted(satzweise, key=lambda h: (not h.get("weitere_nr"), rang.get(h["typ"], 99), h["satz"])):
        nrn = [h["satz"]] + list(h.get("weitere_nr") or [])
        anker = next((besitzer[n] for n in nrn if n in besitzer), h["satz"])
        gruppen.setdefault(anker, []).append(h)
        for n in nrn:
            besitzer.setdefault(n, anker)
    out = list(frei)
    for anker, teile in gruppen.items():
        if len(teile) == 1:
            out.append(teile[0])
            continue
        teile = sorted(teile, key=lambda h: (rang.get(h["typ"], 99), h["satz"]))
        haupt = teile[0]
        text = haupt.get("kern") or haupt["text"]
        for h in teile[1:]:
            wo = f" in Satz {h['satz']}" if h["satz"] != haupt["satz"] else ""
            text += f" Im selben Durchgang{wo}: {_teilauftrag(h)}"
        genannt = [h.get("schon_genannt") for h in teile]
        neu = dict(haupt, text=text, typen=[h["typ"] for h in teile], gewicht=max(h["gewicht"] for h in teile) + 0.05 * (len(teile) - 1),
                   ersetzbar=sorted({w for h in teile for w in h.get("ersetzbar", [])}), info=all(h.get("info") for h in teile),
                   weitere_nr=sorted({n for h in teile for n in [h["satz"]] + list(h.get("weitere_nr") or [])} - {haupt["satz"]}),
                   teile=[{k: h.get(k) for k in ("typ", "satz", "fund")} for h in teile])
        if all(genannt):
            neu["schon_genannt"] = min(genannt)
            neu["text"] += GENANNT.format(runde=min(genannt))
        else:
            neu.pop("schon_genannt", None)
        out.append(neu)
    return out


def _gedaechtnis(L: Lauf) -> None:
    """Hinweis-Gedächtnis: in der Vorrunde unverändert genannt -> herabstufen."""
    if not L.frueher:
        return
    letzte_runde, letzte = L.frueher[-1]
    for h in L.hinweise:
        k_ = (h["typ"], h["anfang"])
        if h["anfang"] is None or k_ not in letzte:
            continue
        runde = letzte_runde
        for r_, schl in reversed(L.frueher[:-1]):
            if k_ in schl:
                runde = r_
            else:
                break
        h["schon_genannt"] = runde
        h["gewicht"] *= 0.4
        h["kern"] = h["text"]
        h["text"] += GENANNT.format(runde=runde)


# ---------------------------------------------------------------------------
# Ehrliche Diagnose bei Stagnation
# ---------------------------------------------------------------------------

# Welche Modellmerkmale sich mit Einzelkorrekturen ohne Inhaltsänderung bewegen lassen (1 = gut, 0,5 = teilweise, 0 = kaum)
ERREICHBAR = {"saetze_pro_absatz_cv": (1.0, "Absätze teilen oder zusammenlegen"), "abkuerzungen_pro_1000": (1.0, "übliche Abkürzungen"),
              "ki_muster_pro_1000": (1.0, "KI-Wendungen ersetzen"), "semikolon_pro_1000": (1.0, "Semikolons ersetzen"),
              "anteil_mittlere_saetze": (1.0, "Satzlängen verteilen"), "satzlaenge_dispersion": (1.0, "Satzlängen verteilen"),
              "anteil_sehr_lange_saetze": (0.5, "einzelne Sätze bündeln"), "satzklammer_mittel": (0.5, "Satzklammer füllen"),
              "nachbarsatz_ueberlappung": (0.5, "Begriffe halten"), "woerter_pro_teilsatz": (0.5, "Nebensätze verdichten"),
              "fw_profil_llr_pro_1000": (0.0, "nur einzelne Konstruktionen"), "mattr_100": (0.0, "Wortwahl insgesamt")}
# Hinweistypen, mit denen der Coach ein Merkmal bewegt: gibt es diese Runde keinen davon, zählt das Merkmal in der Diagnose nicht
# als erreichbar (sonst hieße es „reicht rechnerisch“, ohne dass eine einzige umsetzbare Stelle genannt ist)
ERREICHBAR_TYPEN = {"saetze_pro_absatz_cv": {"absatz_teilen", "absatz_zusammen"}, "abkuerzungen_pro_1000": {"abkuerzung"},
                    "ki_muster_pro_1000": {"floskel", "gegenfolie", "strohmann"}, "semikolon_pro_1000": {"semikolon"},
                    "anteil_mittlere_saetze": {"buendeln", "mitte", "zickzack"},
                    "satzlaenge_dispersion": {"buendeln", "mitte", "teilen", "zickzack"}, "anteil_sehr_lange_saetze": {"buendeln"},
                    "satzklammer_mittel": {"klammer", "klammer_zusatz"}, "nachbarsatz_ueberlappung": {"anknuepfung", "kein_bezug", "synonyme"},
                    "woerter_pro_teilsatz": {"nebensatz", "kommas"}}
FW_EHRLICH = ("Das Funktionswort-Profil entsteht beim eigenen Formulieren und ändert sich durch Einzelkorrekturen kaum. Wirksam ist, "
              "einzelne Absätze mit demselben Inhalt in eigenen Worten neu zu schreiben, statt Sätze umzubauen.")


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def text_unveraendert(L: Lauf) -> bool:
    """Gleiche Messung wie in der Vorrunde (p_mensch, Score und alle bewerteten Kennzahlen identisch): Text nur erneut
    gemessen, nicht überarbeitet."""
    v = getattr(L, "vorher", None)
    if not v or v.get("p_mensch") != L.bew.get("p_mensch") or v.get("score") != L.bew.get("score"):
        return False
    alt = v.get("kennzahlen") or {}
    jetzt = {z["id"]: z["wert"] for z in L.bew.get("kennzahlen", []) if z["bewertet"]}
    return bool(alt) and set(alt) == set(jetzt) and all(alt[k].get("wert") == w for k, w in jetzt.items())


def _diagnose(L: Lauf, auswahl: list[dict], ziel_p: float) -> dict | None:
    """Liegt p_mensch unter dem Ziel und gibt es < 3 umsetzbare Hinweise (oder hat sich p über zwei Runden um
    < STAGNATION_P bewegt), erklärt der Coach, woran es hängt: negative Modellbeiträge mit Größe, welche davon mit
    Einzelkorrekturen erreichbar sind, und ob das Ziel so realistisch ist."""
    p = L.bew.get("p_mensch")
    if not L.bew.get("verfuegbar") or p is None or p >= ziel_p:
        return None
    if text_unveraendert(L):
        return None  # nur erneut gemessen: die genannten Stellen sind noch offen, das ist keine Stagnation
    umsetzbar = [h for h in auswahl if h["hebel"] != "vorgaben" and not h.get("schon_genannt") and not h.get("info")]
    stagniert, p_alt = False, None
    if len(L.messungen) >= 2 and L.messungen[-2].get("p_mensch") is not None:
        p_alt = L.messungen[-2]["p_mensch"]
        stagniert = abs(p - p_alt) < STAGNATION_P
    if len(umsetzbar) >= 3 and not stagniert:
        return None
    beitraege = [b for b in L.bew.get("modell_beitraege") or [] if b["beitrag"] < -0.05]
    modell = L.ts.get("modell") or {}
    vorhanden = {h["typ"] for h in L.hinweise if not h.get("info")}  # alle Aufträge dieser Runde, auch die nicht angezeigten
    zeilen = []
    for b in beitraege:
        grad, wie = ERREICHBAR.get(b["id"], (0.5, ""))
        logit = -b["beitrag"] * grad
        ohne_stelle = grad > 0 and b["id"] in ERREICHBAR_TYPEN and not (ERREICHBAR_TYPEN[b["id"]] & vorhanden)
        if ohne_stelle:
            logit = 0.0  # grundsätzlich erreichbar, aber diese Runde ohne sichere Stelle: nicht in die Rechnung
        if b["id"] == "fw_profil_llr_pro_1000" and L.fw_potenzial > 0 and modell.get("sd", {}).get(b["id"]):
            # simulierter Gewinn aller gefundenen Konstruktionen (LLR pro 1000) in Logit umgerechnet
            logit = min(-b["beitrag"], modell["koeffizienten"][b["id"]] * L.fw_potenzial / modell["sd"][b["id"]])
            grad = 0.0 if logit < 0.25 * -b["beitrag"] else 0.5
            wie = f"Konstruktionen oben, zusammen etwa +{fmt(round(logit, 2))}"
        zeilen.append({"id": b["id"], "name": b["name"], "beitrag": b["beitrag"], "erreichbar": grad, "erreichbar_logit": round(logit, 3),
                       "wie": wie, "ohne_stelle": ohne_stelle})
    luecke = _logit(ziel_p) - _logit(p)
    erreichbar = sum(z["erreichbar_logit"] for z in zeilen)
    summe = sum(-z["beitrag"] for z in zeilen) or 1e-9
    fw_b = next((-z["beitrag"] for z in zeilen if z["id"] == "fw_profil_llr_pro_1000"), 0.0)
    fw_dominant = fw_b >= 1.0 and (fw_b >= 0.5 * summe or fw_b >= 0.5 * luecke)
    return {"p_mensch": p, "ziel_p_mensch": ziel_p, "stagniert": stagniert, "p_vorvorher": p_alt, "umsetzbar": len(umsetzbar),
            "beitraege": zeilen, "luecke_logit": round(luecke, 2), "erreichbar_logit": round(erreichbar, 2),
            "realistisch": erreichbar >= luecke, "fw_dominant": fw_dominant, "fw_text": FW_EHRLICH if fw_dominant else None,
            "fw_top": (L.fw_diag or {}).get("top", [])}


# ---------------------------------------------------------------------------
# Coach
# ---------------------------------------------------------------------------

def _fw_hebeltext(L: Lauf) -> str | None:
    """Datenbasierter Hebeltext für das Funktionswort-Profil: die 2–3 Wörter mit dem größten Beitrag zum negativen LLR."""
    top = (L.fw_diag or {}).get("top") or []
    if not top:
        return None
    viel = [r for r in top if r["zu_viel"]]
    wenig = [r for r in top if not r["zu_viel"]]
    z1 = lambda x: f"{x:.1f}".replace(".", ",")  # noqa: E731
    teile = []
    if viel:
        teile.append("häufiger als bei Menschen: " + ", ".join(f"„{r['wort']}“ {r['anzahl']}× (Menschen ~{z1(r['mensch'])}, KI ~{z1(r['ki'])})"
                                                          for r in viel))
    if wenig:
        teile.append("seltener: " + ", ".join(f"„{r['wort']}“ {r['anzahl']}× (Menschen ~{z1(r['mensch'])})" for r in wenig))
    text = "Das Profil kleiner Wörter ist das stärkste Einzelsignal. Gezählt: " + "; ".join(teile) + "."
    if viel:
        text += " Übernutzte Wörter nur über die genannten Konstruktionen abbauen."
    if wenig:
        passiv = any(r["wort"] in ("werden", "wird") for r in wenig)
        text += (" Seltene Wörter nicht einstreuen – sie kommen beim eigenen Formulieren von selbst"
                 + (" (Passiv nicht wegformulieren)." if passiv else "."))
    return text


def coache(text: str, verlauf: dict | None = None, max_hinweise: int = 15, roh: bool = False) -> dict:
    """Misst den Text und erzeugt priorisierte, satzgenaue Hinweise. roh=True liefert zusätzlich 'hinweise_roh'
    (alle Hinweise vor der Auswahl und vor dem Filter bei „Ziel erreicht“, für Auswertungen)."""
    L = Lauf(text, verlauf)
    _hebel_priorisieren(L)
    _waechter(L)
    _wirksamkeit(L)
    _satzlaengen(L)
    _zickzack(L)
    _satzklammer(L)
    # Folgesätze einer Bündelung gehen im ersten Satz auf: dort keine weiteren Wort-Hinweise
    L.gebuendelte_b = {h["satz"] + 1 for h in L.hinweise if h["typ"] in ("buendeln", "klammer_zusatz")}
    _nebensaetze(L)
    _begriffe(L)
    _floskeln(L)  # vor den Funktionswörtern: deckt ein Muster dieselbe Wendung ab, entfällt der Funktionswort-Auftrag
    _funktionswoerter(L)
    _zeichen(L)
    _abkuerzungen(L)
    _absaetze(L)
    _vorgaben(L)
    _gedaechtnis(L)
    return _ergebnis(L, max_hinweise, roh)


def _ergebnis(L: Lauf, max_hinweise: int, roh: bool) -> dict:
    """Auswahl (Ziel erreicht / Teilziel / Reihum nach Hebel), Hebelanzeige, Verlaufseintrag und Diagnose."""
    bew, ts, diag, kz = L.bew, L.ts, L.diag, L.kz
    ziel_p = bew.get("ziel_p_mensch") or ts.get("ziel_p_mensch") or 0.5
    ziel_score = ts.get("ziel_score") or bew.get("score_schwelle") or ts.get("score_schwelle") or 60
    ziel_rot = ts.get("ziel_rot_max")
    rot = [z for z in bew.get("kennzahlen", []) if z["bewertet"] and z["status"] == "rot"]
    ziel_erreicht = bool(bew.get("verfuegbar") and (bew.get("score") or 0) >= ziel_score
                         and (bew.get("p_mensch") is None or bew["p_mensch"] >= ziel_p)
                         and (ziel_rot is None or len(rot) <= ziel_rot))
    gesehen, eindeutig = set(), []
    for h in sorted(L.hinweise, key=lambda h: -h["gewicht"]):
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
    eindeutig = ein_auftrag_je_satz(eindeutig)
    stapel: dict[str, list[dict]] = {}
    for h in eindeutig:
        stapel.setdefault(h["hebel"], []).append(h)
    hebel = L.hebel
    hebel_folge = sorted(stapel, key=lambda h: (h != "vorgaben", -hebel.get(h, {}).get("prioritaet", 0)))
    auswahl = []
    while len(auswahl) < max_hinweise and any(stapel.values()):
        for h in hebel_folge:
            if stapel[h] and len(auswahl) < max_hinweise:
                auswahl.append(stapel[h].pop(0))

    # Hebel-Anzeige: im TEILEN-Modus immer die Bremse statt „Lange Sätze ja … KI-Texte bleiben im mittleren Band“ – auch ohne
    # Teilen-Auftrag, sonst lädt der Hebeltext zu weiteren langen Sätzen ein
    if diag["modus"] == "teilen" and ("satzlaenge" in hebel or any(h["typ"] == "teilen" for h in L.hinweise)):
        alt = hebel.pop("satzlaenge", None)
        hebel.setdefault("satzlaenge_bremse", {"prioritaet": max(1.0, alt["prioritaet"] if alt else 0.0),
                                               "kennzahlen": [kz[k] for k in ("anteil_lange_saetze", "satzlaenge_mittel",
                                                                              "anteil_mittlere_saetze") if k in kz]})
    reihenfolge = sorted(hebel, key=lambda h: -hebel[h]["prioritaet"])
    daten = satzlaenge_daten(L.ref, L.ziel_vert)
    fw_text = _fw_hebeltext(L)

    def hebel_eintrag(h: str) -> dict:
        typen = set(HEBEL_TYPEN.get(h, set()))
        if h == "satzlaenge":  # der Typ, der im aktuellen Modus den Hebel trägt
            typen = {"mitte"} if diag.get("modus") == "mitte" else {"buendeln"}
        aus = bool(typen) and typen <= L.ausgesetzt and not any(x["hebel"] == h for x in auswahl)
        gruende = sorted({g for t in typen for g in L.aussetz_grund.get(t, [])}) if aus else []
        warum = fw_text if h == "funktionswoerter" and fw_text else hebel_warum(h, L.ref, daten, L.fw_profil)
        return {"id": h, "name": HEBEL_TEXT[h][0], "warum": warum, "prioritaet": round(hebel[h]["prioritaet"], 2),
                "ausgesetzt": gruende if aus else None, "alternative": ALTERNATIVE.get(h) if aus else None,
                "kennzahlen": [{k: z.get(k) for k in ("id", "name", "wert", "mensch_p25", "mensch_p50", "mensch_p75", "ki_p50", "status",
                                                      "richtung", "nur_modell", "beitrag")} for z in hebel[h]["kennzahlen"]]}

    ersetzbar = sorted({w for h in auswahl for w in h.get("ersetzbar", [])})
    werte = {k: L.wert(k) for k in set(ZIEL_KENNZAHL.values())}
    stand = {"score": bew.get("score"), "p_mensch": bew.get("p_mensch"),
             "kennzahlen": {z["id"]: {"wert": z["wert"], "status": z["status"]} for z in bew.get("kennzahlen", []) if z["bewertet"]},
             "roh": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in L.roh_jetzt.items()},
             "werte": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in werte.items() if v is not None},
             "bloecke": [{k: b.get(k) for k in ("nr", "satz_von", "satz_bis", "p_mensch", "score")} for b in L.bloecke],
             "hinweise": [{k: h.get(k) for k in ("typ", "typen", "anfang", "satz", "ziel", "ziel_wert", "laenge", "weitere", "zaehlung")
                           if k in ("typ", "anfang", "satz") or h.get(k) is not None} for h in auswahl],
             "ersetzbar": ersetzbar, "satzlaengen_modus": diag["modus"]}
    fortschritt = None
    vorher = L.vorher
    if vorher:
        reihen = ["rot", "gelb", "gruen"]
        alt_kz = vorher.get("kennzahlen") or {}
        besser = [k for k, v in stand["kennzahlen"].items() if k in alt_kz and reihen.index(v["status"]) > reihen.index(alt_kz[k]["status"])]
        schlechter = [k for k, v in stand["kennzahlen"].items() if k in alt_kz and reihen.index(v["status"]) < reihen.index(alt_kz[k]["status"])]
        fortschritt = {"score_vorher": vorher.get("score"), "p_mensch_vorher": vorher.get("p_mensch"), "besser": besser, "schlechter": schlechter,
                       "messung_nr": len(L.messungen) + 1,
                       "mechanisch_verlaengert": mechanisch_verlaengert(vorher.get("roh", {}), stand["roh"]),
                       "ueberkorrektur": L.ueberkorrektur, "ausgesetzt": sorted(L.ausgesetzt), "wirkung": L.wirkung,
                       "unveraendert": text_unveraendert(L)}

    # „Schon gut“ nur, was im Modell kaum Richtung KI zieht (sonst stünde z. B. „keine Abkürzungen“ als gut da)
    gruen = sorted([z for z in bew.get("kennzahlen", []) if z["bewertet"] and z["status"] == "gruen"
                    and (z.get("beitrag") is None or z["beitrag"] >= SCHON_GUT_AB)], key=lambda z: -(z["gewicht"] or 0))
    diag_aus = {k: diag.get(k) for k in ("modus", "kontingent", "n", "lange", "mittlere", "kurze", "gruende", "abweichungen",
                                         "ueberkorrektur", "ueber_p90", "fehlende_mitte")}
    diag_aus.update({k: round(diag[k], 3) for k in ("anteil_lange", "anteil_mittlere", "anteil_kurze", "mittel", "schiefe") if diag.get(k) is not None})
    diag_aus["l1"] = round(diag["l1"], 3) if diag.get("l1") is not None else None
    diag_aus["mittlere_p75"] = L.p_("anteil_mittlere_saetze", "p75")
    fw = kz.get("fw_profil_llr_pro_1000")
    ergebnis = {"info": L.erg["info"], "bewertung": {k: bew.get(k) for k in ("score", "p_mensch", "verfuegbar")},
                "hebel": [hebel_eintrag(h) for h in reihenfolge if h in HEBEL_TEXT],
                "hinweise": auswahl, "anzahl_hinweise_gesamt": len(eindeutig),
                "rot": len(rot), "gut": [z["name"] for z in gruen[:4]], "stand": stand, "fortschritt": fortschritt,
                "ziel_p_mensch": ziel_p, "ziel_score": ziel_score, "ziel_rot_max": ziel_rot,
                "bloecke": L.bloecke, "blockmodus": bool(bew.get("blockmodus")),
                "fokus": {"block": L.fokus_block["nr"] if L.fokus_block else None, "satz_von": L.von, "satz_bis": L.bis},
                "satzlaengen": diag_aus, "ersetzbar": ersetzbar, "ziel_erreicht": ziel_erreicht, "teilziel": teilziel,
                "jenseits": L.jenseits, "fw_wert": fw["wert"] if fw else None,
                "funktionswoerter": {k: L.fw_diag[k] for k in ("n", "top", "llr")} if L.fw_diag else None,
                "ausgesetzt": {t: g for t, g in L.aussetz_grund.items()}, "unterdrueckt": dict(L.unterdrueckt),
                "diagnose": None if ziel_erreicht or teilziel else _diagnose(L, auswahl, ziel_p)}
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



def diagnose_text(d: dict) -> list[str]:
    """Bericht-Abschnitt der ehrlichen Diagnose: Modellbeiträge, Erreichbarkeit, Funktionswort-Hinweis."""
    out = ["\n### Warum das Modellziel noch fehlt\n"]
    kopf = f"Modell {round(100 * d['p_mensch'])} % menschlich, Ziel {round(100 * d['ziel_p_mensch'])} %."
    if d.get("stagniert") and d.get("p_vorvorher") is not None:
        kopf += f" Seit zwei Messungen kaum Bewegung ({round(100 * d['p_vorvorher'])} % → {round(100 * d['p_mensch'])} %)."
    elif d.get("umsetzbar", 0) < 3:
        n = d.get("umsetzbar", 0)
        kopf += f" Neue sichere Einzelstellen gibt es nur {n}." if n else " Neue sichere Einzelstellen gibt es keine mehr."
    out.append(kopf + " Was den Text im Modell Richtung KI zieht (Beitrag, je negativer, desto stärker):\n")
    grade = {1.0: "mit Einzelkorrekturen erreichbar", 0.5: "teilweise erreichbar", 0.0: "mit Einzelkorrekturen kaum erreichbar"}
    for z in d["beitraege"][:6]:
        wie = f" ({z['wie']})" if z.get("wie") and (z["erreichbar"] > 0 or z.get("erreichbar_logit", 0) > 0) else ""
        stufe = grade.get(z["erreichbar"], "teilweise erreichbar")
        if z.get("ohne_stelle"):
            stufe = "grundsätzlich erreichbar, diese Runde aber ohne sichere Stelle – zählt nicht mit"
        # „Beitrag“ ausdrücklich nennen: der Name trägt oft die Einheit der Kennzahl (LLR, pro 1000), der Wert ist aber Logit
        out.append(f"- {z['name']}: Beitrag {fmt(round(z['beitrag'], 2))} – {stufe}{wie}")
    if d["realistisch"]:
        out.append(f"\nDie erreichbaren Beiträge (≈ {fmt(d['erreichbar_logit'])}) reichen rechnerisch für die Lücke zum Ziel "
                   f"(≈ {fmt(d['luecke_logit'])}): die als erreichbar markierten Hebel zuerst umsetzen.")
    else:
        out.append(f"\n**Ehrlich gesagt:** Mit Einzelkorrekturen ist das Modellziel voraussichtlich nicht erreichbar – die erreichbaren "
                   f"Beiträge (≈ {fmt(d['erreichbar_logit'])}) sind kleiner als die Lücke zum Ziel (≈ {fmt(d['luecke_logit'])}).")
    if d.get("fw_text"):
        out.append(f"\n{d['fw_text']}")
    return out


def kennzahl_lage(k: dict) -> str:
    """Lage einer Modellkennzahl ohne Ampel: „KI-nah“ nur bei negativem Wert (Log-Likelihood-Verhältnis, 0 = neutral),
    sonst die Lage zum menschlichen Median."""
    w, m50 = k.get("wert"), k.get("mensch_p50")
    if w is None:
        return "ohne Wert"
    if w < 0:
        return "KI-nah"
    if m50 is None or w == m50:
        return "beim menschlichen Median"
    return f"{'unter' if w < m50 else 'über'} dem menschlichen Median {fmt(m50)}"


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
                   + (f" · schlechter: {', '.join(analyse.NAMEN.get(k, k) for k in f['schlechter'])}" if f["schlechter"] else "")
                   + (" · Text seit der letzten Messung unverändert – die genannten Stellen sind noch offen." if f.get("unveraendert") else ""))
        for u in f.get("ueberkorrektur") or []:
            aus = ", ".join(TYP_NAME.get(t, t) for t in u["aussetzen"])
            seit = f" (Messung {u['messung_vorher']})" if u.get("messung_vorher") else ""
            folge = (f" Diese Runde ausgesetzt: {aus}." if aus else
                     " Satzlängen-Aufträge unten sind daraufhin simuliert und verschlechtern ihn nicht weiter." if u["id"] == "rhythmus_r1_log" else "")
            out.append(f"\n> ⚠️ **{u['art']}:** {u['name']} {fmt(u['vorher'])}{seit} → {fmt(u['wert'])}, jetzt {u['grenze']}.{folge}")
        if f.get("mechanisch_verlaengert"):
            out.append("\n> ⚠️ **Mechanisch verlängert:** Die Sätze sind länger geworden, aber Teilsätze und Satzklammern nicht – vermutlich angehängte Teilsätze. Das zählt nicht als Fortschritt; stattdessen nominal verdichten.")
        for w in f.get("wirkung") or []:
            folge = (f" Diese Runde stattdessen: {TYP_NAME.get(w['wechsel'], w['wechsel'])}." if w.get("wechsel")
                     and w["wechsel"] not in (f.get("ausgesetzt") or []) else " Diese Runde ausgesetzt.")
            out.append(f"\n> ↺ **Wirkung geprüft:** {w['grund']}.{folge}")
    teil_aus = {t: g for t, g in (c.get("ausgesetzt") or {}).items()
                if t in ("nebensatz_relativ", "nebensatz_werden") and (c.get("unterdrueckt") or {}).get(t)}
    if teil_aus and not c["ziel_erreicht"]:
        out.append("\n> ℹ️ **Geschützt:** " + "; ".join(f"keine Hinweise „{TYP_NAME.get(t, t)}“ ({', '.join(g)})" for t, g in teil_aus.items())
                   + " – sonst ginge Passiv verloren, das hier schon seltener ist als in echten Arbeiten.")
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
    elif sl.get("modus") == "mitte" and any(h["typ"] == "mitte" for h in c["hinweise"]):
        out.append(f"\n**Satzlängen:** {sl['mittlere']} von {sl['n']} Sätzen sind mittellang ({MITTEL_VON}–{MITTEL_BIS} Wörter, "
                   f"{_pz(sl.get('anteil_mittlere') or 0)}; Menschen meist ≤ {_pz(sl.get('mittlere_p75') or 0)}), lange Sätze gibt es genug. Nur die unten "
                   f"genannten Sätze mit {MITTE_SATZ_VON}–{MITTE_SATZ_BIS} Wörtern teilen – nicht mehr, nichts bündeln.")
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
                    teile.append(f"{k['name']}: {fmt(k['wert'])} ({kennzahl_lage(k)}, fließt ins Modell)")
                elif k.get("status") == "gruen" and (k.get("beitrag") or 0) <= MODELL_HEBEL:
                    teile.append(f"{k['name']}: {fmt(k['wert'])} (im Zielbereich, aber weit vom menschlichen Median "
                                 f"{fmt(k.get('mensch_p50'))} – fließt ins Modell)")
                else:
                    teile.append(f"{k['name']}: {fmt(k['wert'])} (Ziel {fmt(k['mensch_p25'])}–{fmt(k['mensch_p75'])})")
            if h.get("ausgesetzt"):
                out.append(f"{i}. **{h['name']}** – _diese Runde ausgesetzt, weil {'; '.join(h['ausgesetzt'])}._ {h.get('alternative') or ''}"
                           f"  \n   _{'; '.join(teile)}_")
            else:
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
    elif not c["ziel_erreicht"] and c["bewertung"].get("verfuegbar") and not c.get("diagnose"):
        out.append("\n_Keine sicheren Einzelstellen gefunden – die Hebel oben beim eigenen Formulieren im Blick behalten._")
    if c.get("diagnose"):
        out.extend(diagnose_text(c["diagnose"]))
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
