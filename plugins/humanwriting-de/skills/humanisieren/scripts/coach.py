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

Jeder Umbau von Satzlängen wird vor der Ausgabe am Modell simuliert (Δ-Logit der längenabhängigen Modellmerkmale plus
Score-Anteil, mit harten Grenzen gegen Überkorrektur), Absätze und Satzklammern an ihren Kennzahlen. Ein Wirksamkeits-
gedächtnis prüft im Verlauf, ob befolgte Aufträge gewirkt haben (Satzlängen lokal: Verbundsatz da? Satz geteilt?), und
schreibt Nebenwirkungen nur Aufträgen zu, deren simulierte Wirkung in die beobachtete Richtung zeigt. Je Satz gibt es
höchstens einen Auftrag (Nutzer-Vorgaben ausgenommen): treffen mehrere zu, fasst der Coach sie in fester Reihenfolge zusammen.
Hebel ohne sichere Stelle erscheinen nur zur Orientierung (mit Technik zum Selbermachen, aus dem Text erzeugt: vorhandene
Konstruktionen, vorhandene Langformen, verbliebene Wendungen mit Satznummer – nie eine Aufforderung zum Einstreuen). Die Diagnose
trennt „Grenze des Coaches“ (rechnerisch erreichbar, aber diese Runde ohne Auftrag – auch, wenn das Bündelfenster keinen Spielraum
lässt) von „knapp, Schätzung unsicher“ (70–100 % der Lücke) und „Grenze der Einzelkorrekturen“ (unter 70 %); direkt nach einer
ersten Runde mit deutlichem Anstieg gibt es noch keine Diagnose. Was kein Auftrag ist (eine Gegenfolie, deren Kontrast die
Aussage ist), steht nicht in der Aufgabenliste, sondern einmal als Info-Zeile; Angebote heißen „Optional, kein Auftrag“.
Kombinierte Aufträge werden auf innere Widersprüche geprüft (auch „kürzen“ gegen eine nur durch Auffüllen erreichbare Länge),
und kein Auftrag widerspricht einem im selben Bericht ausgesetzten Typ oder genannten Hebel.

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
import statistics
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
    "abkuerzungen": ("Übliche Abkürzungen stehen lassen", "Menschliche Hochschultexte nutzen gängige Abkürzungen (z. B., d. h., bzw., u. a.). Claude schreibt sie fast immer aus."),
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


def alternative_text(L, h: str) -> str | None:
    """Erlaubte Alternative eines ausgesetzten Hebels – nie eine Technik, die im selben Bericht selbst ausgesetzt ist
    („nur dort teilen, wo genannt“ nur, wenn Teilen erlaubt ist und unten Teilen-Aufträge stehen)."""
    if h == "satzlaenge":
        teilen_da = any(x["typ"] in ("teilen", "mitte") or {"teilen", "mitte"} & set(x.get("typen") or []) for x in L.hinweise)
        if "teilen" in L.ausgesetzt or not teilen_da:
            return "Erlaubt bleibt: Satzlängen diese Runde so lassen."
    if h == "funktionswoerter":
        return ALTERNATIVE[h].rstrip(".") + fw_absatz_zusatz(L) + "."
    return ALTERNATIVE.get(h)


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


def hebel_warum(h: str, ref: dict, daten: str = "", fw_profil: dict | None = None, vorhanden: set[str] | None = None) -> str:
    """Hebeltext mit den Medianen aus den Referenzwerten; ohne Daten der feste Text. vorhanden: Konnektoren, die im Text
    tatsächlich stehen (der Konnektor-Hebel nennt nur diese, nie „zugleich“ in einem Text ohne „zugleich“)."""
    text = HEBEL_TEXT[h][1].format(satzlaenge_daten=daten)
    if h == "funktionswoerter" and fw_profil:
        ki, mensch = fw_typische(fw_profil)
        if ki and mensch:
            text = (f"Das Profil kleiner Wörter ist das stärkste Einzelsignal: Claude schreibt häufiger mit {', '.join(f'„{w}“' for w in ki)}, "
                    f"Menschen häufiger mit {', '.join(f'„{w}“' for w in mensch)}. Steuerbar über die genannten Konstruktionen, nicht "
                    "durch Einstreuen.")
    if h == "konnektoren":
        stark = sorted((k for k in KONNEKTOR_KORPUS if (konnektor_verhaeltnis(k) or 0) > KONN_STARK), key=lambda k: -konnektor_verhaeltnis(k))
        if vorhanden is not None:
            stark = [k for k in stark if k in vorhanden]
        allein = [k for k in stark if konnektor_verhaeltnis(k) > KONN_ALLEIN]
        rest = [k for k in stark if k not in allein]
        # keine „menschlichen“ Konnektoren als Ersatz anpreisen: Austauschen wäre Wort-Einstreuen (Grundsatz 6) und senkt die
        # Konnektor-Dichte nicht. Gestrichen wird nur an den genannten Stellen (einzeln nur, was mehr als 4× so häufig ist)
        teile = []
        if allein:
            teile.append(f"{', '.join(f'„{k}“' for k in allein)} (bei Claude mehr als viermal so häufig)")
        if rest:
            teile.append(f"{', '.join(f'„{k}“' for k in rest)} (gut doppelt so häufig)")
        text = ("Claude nutzt mehr Satzverknüpfer als Menschen" + (f"; in diesem Text vor allem {' und '.join(teile)}" if teile else "")
                + ". Nur an den genannten Stellen streichen, nicht verschieben und nicht durch einen anderen Konnektor ersetzen.")
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
    "gender": "vorgaben", "gedankenstrich": "vorgaben", "bindestrich": "vorgaben", "konsistenz": "vorgaben",
    "bereinigung": "bereinigung",
}
STRUKTURELL = {"buendeln", "teilen", "kurz", "zickzack", "mitte", "klammer", "klammer_zusatz", "nebensatz", "kommas"}
# Hinweistypen je Hebel, die einen Hebel tragen: sind sie alle ausgesetzt, zeigt der Bericht den Hebel als ausgesetzt
HEBEL_TYPEN = {"satzlaenge": {"buendeln", "zickzack", "mitte"}, "satzlaenge_bremse": {"teilen"},
               "satzklammer": {"klammer", "klammer_zusatz"}, "nebensaetze": {"nebensatz", "kommas"},
               "begriffe": {"anknuepfung", "kein_bezug", "synonyme"}, "funktionswoerter": set(FW_TYPEN),
               "floskeln": {"floskel", "gegenfolie", "strohmann"}, "konnektoren": {"konnektor"}, "absaetze": {"absatz_teilen", "absatz_zusammen"},
               "abkuerzungen": {"abkuerzung"}, "semikolon": {"semikolon"}, "doppelpunkt": {"doppelpunkt"}}
# Technik zum Selbermachen, wenn ein Hebel in dieser Runde keine sichere Stelle hat (Bericht: „zur Orientierung“)
SELBSTHILFE_HEBEL = {
    "satzlaenge": "zwei zusammengehörige mittellange Sätze derselben Quelle zu einem Satz mit 30–40 Wörtern verbinden (den zweiten als "
                  "Nominal- oder Präpositionalgruppe), bis etwa jeder sechste Satz lang ist",
    "satzlaenge_bremse": "einzelne Sätze über 40 Wörter an einer inhaltlichen Wende teilen",
    "satzklammer": "Angaben vom Satzanfang zwischen Hilfsverb und Partizip stellen und das Subjekt nach vorn holen (Beispiel: „In der "
                   "Literatur wurde dies beschrieben.“ → „Dies wurde in der Literatur beschrieben.“)",
    "nebensaetze": "kurze „weil“-, „wenn“- oder „dass“-Sätze als Nominalgruppe fassen, wenn höchstens zwei Nomen hintereinander entstehen",
    "funktionswoerter": "Konstruktionen wie „lässt sich“, „zeigt sich“, „dient als“ beim Überarbeiten auflösen; nichts einstreuen",
    "begriffe": "den Schlüsselbegriff des Vorsatzes wieder aufnehmen, statt ihn zu umschreiben oder mit „Ihr …“ anzuknüpfen",
    "absaetze": "an einem thematischen Einschnitt einen neuen Absatz beginnen oder zwei kurze Absätze zum selben Thema zusammenlegen",
    "floskeln": "Wendungen wie „spielt eine zentrale Rolle“ durch die konkrete Aussage ersetzen",
    "konnektoren": "„zugleich“ streichen, wo der Bezug klar ist; andere Satzverknüpfer nur, wenn derselbe im Absatz gehäuft steht",
    "abkuerzungen": "nur vorhandene Langformen kürzen („beispielsweise“ → „z. B.“), nichts einstreuen",
    "semikolon": "Semikolons durch Punkt ersetzen (in Aufzählungen durch Komma) – höchstens 1–2 je 800 Wörter",
    "doppelpunkt": "Doppelpunkte mitten im Satz durch einen eigenen Satz ersetzen",
    "wortwahl": "ergibt sich meist aus den übrigen Hebeln",
    "stimme": "wörtliche Zitate, Klammern oder „wir“ verwenden, wo es passt",
}
# erlaubte Alternative, wenn alle Hinweistypen eines Hebels ausgesetzt sind
ALTERNATIVE = {
    "satzlaenge": "Erlaubt bleibt: Satzlängen so lassen; nur dort teilen, wo unten ausdrücklich genannt.",
    "satzlaenge_bremse": "Erlaubt bleibt: keine weiteren Sätze verlängern oder bündeln.",
    "satzklammer": "Erlaubt bleibt: beim Neuformulieren Angaben zwischen Hilfsverb und Partizip stellen, ohne den Satz zu verlängern.",
    # Herauslösen ist ein Komma-Auftrag („kommas“) – ist der Hebel ausgesetzt, ist es das auch
    "nebensaetze": "Erlaubt bleibt: die Nebensätze diese Runde so lassen.",
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
                   "tanzend": ("Tänzer", "Tänzer"), "singend": ("Sänger", "Sänger"), "hochschullehrend": ("Hochschullehrer", "Hochschullehrer")}
# Zielformen im Hochschulkontext, die kein einzelnes Wort sind: „Lehrende“ sind Lehrkräfte bzw. Dozenten – „Lehrer“ meint die
# Schule und verschiebt die Zuordnung (v6-Prüfung, fhws: „Aufgabe der Lehrer beziehungsweise der Hochschule“)
GENDER_ZIELTEXT = {"lehrend": "„Lehrkräfte“ oder „Dozenten“ (im Hochschulkontext nicht „Lehrer“)"}
GENDER_UNBEKANNT = "eine passende maskuline Bezeichnung"
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
    if low in GENDER_ZIELTEXT:
        return None, low  # feste Zielformen im Hochschulkontext (GENDER_ZIELTEXT), keine Einzelform
    if low.endswith("lehrend") and low != "hochschullehrend":
        return None, low  # „Fachlehrende“ o. Ä.: keine sichere Ableitung, nie „…lehrer“ raten
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
KONN_STARK = 2.0  # Hebeltext: „mehr als doppelt so häufig“
KONN_ALLEIN = 4.0  # ein einzelnes Vorkommen wird nur gemeldet, wenn der Konnektor bei Claude mehr als 4× so häufig ist
KONN_HAEUFUNG = {"jedoch": 3}  # Häufung im selben Absatz (sonst 2): „jedoch“ ist auch bei Menschen häufig (1,33 je 1000 Wörter)
MAX_KONNEKTOR = 2  # Konnektor-Aufträge je Runde
MAX_KONNEKTOR_P90 = 5  # über P90: Kontingent bis zum Median, höchstens so viele
KONN_TEXTWEIT = 3  # über P90: derselbe Konnektor so oft im Fokus gilt als Häufung (je Absatz höchstens eine Stelle)
# Erster Teil einer Korrelatkonstruktion im selben Satz vor dem Konnektor: „nicht nur … zudem“, „zwar … jedoch“, „einerseits …“
KORRELAT_VOR_RE = re.compile(r"\b(?:nicht\s+nur|nicht\s+allein|zwar|einerseits|zum\s+einen|sowohl)\b", re.IGNORECASE)


def konnektor_verhaeltnis(wort: str) -> float | None:
    m, k = KONNEKTOR_KORPUS.get(re.sub(r"\s+", " ", wort.lower()), (0.0, 0.0))
    return k / m if m else None
HILFSVERBEN = set("""ist sind war waren sei seien wäre wären hat haben hatte hatten hätte hätten wird werden wurde wurden würde würden
kann können konnte konnten könnte könnten muss müssen musste mussten müsste müssten soll sollen sollte sollten will wollen wollte
wollten darf dürfen durfte durften dürfte dürften""".split())
KLAMMER_ENDE_HILFS = {"werden", "worden", "sein", "haben", "können", "müssen", "sollen", "dürfen", "wollen", "lassen", "gewesen", "geworden"}
# Ausgeschriebene Abkürzungen (Modellmerkmal abkuerzungen_pro_1000 zählt z. B., d. h., u. a., bzw., ca. …; „vgl.“ zählt nicht).
# Nur die im Fließtext gängigen (z. B., d. h., bzw., u. a., vgl., ca.) – nicht „i. d. R.“, „z. T.“, „ggf.“, „sog.“, „usw.“, die im
# Fließtext gestelzt wirken. Nie am Satzanfang („Z. B. …“ liest sich schlecht), „das heißt“ nur nach Komma (sonst oft „das heißt
# nicht, dass …“), „etwa/rund“ nur vor Zahlen, „vergleiche“ nur in Klammern (sonst das Nomen „Vergleiche“).
ABK_ERSATZ = [
    (re.compile(r"\bzum Beispiel\b"), "z. B.", True), (re.compile(r"\bbeispielsweise\b"), "z. B.", True),
    (re.compile(r"(?<=,\s)das heißt\b"), "d. h.", True), (re.compile(r"\bunter anderem\b"), "u. a.", True),
    (re.compile(r"\bbeziehungsweise\b"), "bzw.", True),
    (re.compile(r"\b(?:circa|etwa|rund)(?=\s+\d)"), "ca.", True), (re.compile(r"(?<=\()vergleiche\b"), "vgl.", False),
]
# Kurz- und Langform derselben Abkürzung (Konsistenz nach Ersetzungen): „ca.“ neben „etwa 15.000“, „z. B.“ neben „beispielsweise“
ABK_FAMILIEN = {"ca.": (re.compile(r"\bca\.(?=\s*\d)"), re.compile(r"\b(?:circa|etwa|rund)(?=\s+\d)", re.IGNORECASE)),
                "z. B.": (re.compile(r"\bz\.\s?B\."), re.compile(r"\b(?:zum Beispiel|beispielsweise)\b", re.IGNORECASE)),
                "d. h.": (re.compile(r"\bd\.\s?h\."), re.compile(r"(?<=,\s)das heißt\b")),
                "u. a.": (re.compile(r"\bu\.\s?a\."), re.compile(r"\bunter anderem\b", re.IGNORECASE)),
                "bzw.": (re.compile(r"\bbzw\."), re.compile(r"\bbeziehungsweise\b", re.IGNORECASE))}

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
                         r"vertritt|vertreten|konstatier\w*|resümier\w*|schlussfolger\w*|folger\w*|schreib\w*|geschrieben|unterstreich\w*|"
                         # passive bzw. unpersönliche Berichtsverben („Auf Nachfrage wurde versichert, dass …“, „gaben an“)
                         r"versicher\w*|angegeben|gab\w*\s+(?:\S+\s+){0,3}?an|mitgeteilt|bestätigt|berichtet)\b",
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
# kein dass-Satz-Hinweis). Folgerungsverben („ableiten“, „folgern“, „schließen“): siehe FOLGERUNG_RE.
ANKUENDIGUNG_RE = re.compile(
    r"\b(?:lässt|lassen)\s+sich\s+(?:\w+\s+){0,2}?(?:festhalten|feststellen|sagen|zusammenfassen|konstatieren|resümieren|ableiten|"
    r"folgern|schließen)\s*,\s*dass\b"
    r"|\b(?:kann|können)\s+(?:\w+\s+){0,2}?(?:festgehalten|festgestellt|gesagt|zusammengefasst|konstatiert|resümiert|abgeleitet|"
    r"gefolgert|geschlossen)"
    r"\s+werden\s*,\s*dass\b"
    r"|\b(?:ist|bleibt)\s+(?:\w+\s+){0,2}?(?:festzuhalten|festzustellen|zu\s+konstatieren)\s*,\s*dass\b", re.IGNORECASE)
# Folgerungsverben (ableiten, folgern, schließen) tragen eine Folgerung des Autors: nicht streichen (sonst wird daraus eine
# Tatsachenbehauptung), sondern die Folgerung über „folgt“ erhalten – mit Doppelpunkt, solange Doppelpunkte nicht schon über dem
# menschlichen Median liegen (Doppelpunkte sind bei Claude häufiger), sonst „folgt, dass“. Nie „daher/also“: das kollidiert mit
# konzessiven Adverbien („lässt sich dennoch ableiten“ → „ist dennoch …“ machte in v3 aus der Folgerung eine Tatsache).
FOLGERUNG_RE = re.compile(r"ableit|abgeleit|folger|gefolgert|schließ|geschlossen", re.IGNORECASE)
KONZESSIV_RE = re.compile(r"\b(?:dennoch|trotzdem|gleichwohl|nichtsdestotrotz)\b", re.IGNORECASE)
ANKUENDIGUNG_FOLGERUNG = ("trägt eine Folgerung – nicht streichen: die Ankündigung zu „… folgt daraus: …“ verkürzen, der Inhalt des "
                          "„dass“-Satzes wird Hauptsatz (Beispiel: „Für die Praxis lässt sich ableiten, dass Schulungen nötig sind.“ → "
                          "„Für die Praxis folgt daraus: Schulungen sind nötig.“); die Folgerung bleibt eine Folgerung")
ANKUENDIGUNG_FOLGERUNG_VERB = ("trägt eine Folgerung – nicht streichen: die Folgerung über das Verb erhalten, nur die Ankündigung "
                               "kürzen (Beispiel: „Daraus lässt sich ableiten, dass die Kosten steigen.“ → „Daraus folgt, dass die "
                               "Kosten steigen.“)")
_W = r"[^\s,.;:()]+"
# „als“ vor einer Zahl ist eine Mengenangabe („gelten Unternehmen mit weniger als 250 Beschäftigten als …“), nie das „als“
# der Konstruktion: Der träge Treffer springt dann zum nächsten „als“ im Fenster (am Korpus ändert das keinen Treffer).
_ALS_NICHT_ZAHL = r"\s+als\b(?!\s*\d)"
DIENT_ALS_RE = re.compile(rf"\b(?:dient|dienen|diente|dienten|fungiert|fungieren|fungierte|fungierten)\b(?:\s+{_W}){{0,6}}?{_ALS_NICHT_ZAHL}"
                          rf"|\bals\s+(?:{_W}\s+){{1,4}}?(?:dienen|dient|diente|dienten|fungieren|fungiert|fungierte|fungierten)\b", re.IGNORECASE)
VERSTEHT_SICH_ALS_RE = re.compile(rf"\b(?:versteht|verstehen|verstand|verstanden)\s+sich\b(?:\s+{_W}){{0,4}}?{_ALS_NICHT_ZAHL}", re.IGNORECASE)
GILT_ALS_RE = re.compile(rf"\b(?:gilt|gelten|galt|galten)\b(?:\s+{_W}){{0,4}}?{_ALS_NICHT_ZAHL}", re.IGNORECASE)
ZUSCHREIBUNG_RE = re.compile(r"\b(?:nach|laut|gemäß|zufolge|im Sinne|Definition|definier\w*)\b|\d", re.IGNORECASE)
REDEVERB_KURZ_RE = re.compile(r"\b(?:zeig(?:t|en|te|ten)|gezeigt|beton\w*|unterstreich\w*|verdeutlich\w*|belegt|belegen|"
                              r"mach(?:t|en)\s+deutlich)\b[^.;,]*?,\s*dass\s+(?P<rest>[^,;]*)", re.IGNORECASE)
# Funktionswort-Konstruktionen, die am Korpus KI-typisch sind: Vorkommen je 1000 Wörter Mensch / KI mit genau diesen Regexen
# (Prosa-Sätze aus 1209 menschlichen und 412 KI-Abschnitten, 1,10 Mio. bzw. 0,36 Mio. Wörter). Aufgenommen nur bei
# Verhältnis ≥ 1,5. Nicht KI-typisch und deshalb ohne Hinweis: „als … bezeichnet“ (0,98), „handelt sich um“ (0,97),
# „bezieht sich auf“ (1,25), „Sie“ (1,33) bzw. „Diese“ (1,05) am Satzanfang. KI-typisch, aber wegen des Aussagestatus
# ausgelassen: „erweist sich als“ (7,9; Befund). „lässt sich ableiten/folgern/schließen, dass“ gehört zur Ankündigung
# (Verhältnis mit „ableiten“ 1,77); der Auftrag streicht die Folgerung nicht, sondern hält sie über „folgt“ fest.
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
NEBENSATZ_MAX = 12  # weil-/Adverbialsatz: längere Sätze ergeben beim Nominalisieren Ketten aus vier und mehr Nomen
NEBENSATZ_MAX_DASS = 14  # dass-Satz: der Inhalt wird Objekt des Hauptverbs („zeigt den Anstieg …“), etwas mehr Spielraum
RELATIV_MAX = 9  # Relativsatz an einem Gattungsnomen: höchstens so viele Wörter …
ATTRIBUT_MAX = 5  # … und als vorangestelltes Partizip höchstens so viele Wörter vor dem Nomen (sonst Präpositionalgruppe oder nichts)
RELATIV_PRAEP_MAX = 9  # Passiv-Relativsatz mit Angabe („die in der Befragung erhoben wurden“) als Präpositionalgruppe am Nomen
KETTE_MAX = 2  # Nomen, die beim Nominalisieren hintereinander stünden (Verbalnomen + Genitive); ab 3 wird es eine Nominalkette
# Koordination im Nebensatz: nominalisiert entstehen Ketten wie „des … unterstützenden und nicht kontrollierenden Selbstverständnisses“
KOORDINATION_RE = re.compile(r"\b(?:und|oder)\s+nicht\b|\bsowohl\b|\bweder\b|\bnicht\s+nur\b|\bals\s+auch\b", re.IGNORECASE)
# „Entscheidend/Wichtig ist, dass …“: Kopula + Bewertung vor dem dass-Satz – nominalisiert wird daraus „Entscheidend sind die Kenntnis …“
KOPULA_DASS_RE = re.compile(r"^\s*[„\"(»]?(?:Entscheidend|Wichtig|Zentral|Maßgeblich|Ausschlaggebend|Problematisch|Klar|Fraglich|Unstrittig|"
                            r"Offen|Bedeutsam|Wesentlich|Notwendig|Erforderlich|Sicher|Denkbar|Auffällig|Bemerkenswert)\s+"
                            r"(?:ist|bleibt|war|erscheint|scheint)\b(?:\s+\w+){0,3}\s*$", re.IGNORECASE)
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
# Präposition je Subjunktion: die Beziehung bleibt (Bedingung → „bei“, nicht „wegen“; Zweck → „zur“; Mittel → „durch“)
KLAMMER_PRAEP = {"um": "„zur“ oder „für“ – der Zweck bleibt ein Zweck", "indem": "„durch“ – das Mittel bleibt ein Mittel",
                 "ohne": "„ohne“", "weil": "„wegen“ oder „aufgrund“ – die Begründung bleibt eine Begründung",
                 "da": "„wegen“ oder „aufgrund“ – die Begründung bleibt eine Begründung",
                 "wenn": "„bei“ – die Bedingung bleibt eine Bedingung, keine Begründung", "nachdem": "„nach“", "bevor": "„vor“",
                 "sobald": "„mit“ oder „nach“ – die zeitliche Folge bleibt"}
# Korrelat im Teilsatz vor dem Nebensatz („darauf hinweisen, wenn …“, „dadurch, dass …“): der Nebensatz ist Inhalt, keine Angabe
KORRELAT_RE = re.compile(r"\bdar?(?:auf|an|für|von|zu|mit|über|um|nach|aus|in|bei|gegen|durch|unter)\b", re.IGNORECASE)
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
    # „kommas“ (Herauslösen) kürzt Sätze wie „teilen“: es zählt auf der KI-Seite (zu kurz, zu wenig lange Sätze, zu gleichmäßig) mit
    "satzlaenge_mittel": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen", "kurz", "mitte", "kommas"}},
    "satzlaenge_median": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen", "kurz", "mitte"}},
    "anteil_lange_saetze": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen", "kommas"}},
    "satzlaenge_dispersion": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen", "kommas"}},
    "anteil_sehr_lange_saetze": {"gegen": {"buendeln", "klammer_zusatz", "zickzack"}, "ki": {"teilen"}},
    "anteil_mittlere_saetze": {"gegen": {"buendeln", "kurz", "klammer_zusatz", "mitte"}, "ki": {"teilen"}},
    "anteil_kurze_saetze": {"gegen": {"buendeln", "klammer", "klammer_zusatz"}, "ki": {"kurz", "teilen", "mitte"}},
    "satzlaenge_schiefe": {"gegen": {"kurz"}, "ki": {"buendeln"}},
    # Rhythmus auf der KI-Seite sperrt das Bündeln nicht nachträglich: das Längenmodell wertet Kandidaten ab, die einen
    # Kurz-Lang-Wechsel erzeugen, und verwirft solche, die den Rhythmus rot machen
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
    # Komma- und Nebensatz-Aufträge zählen auf der KI-Seite mit ihrer simulierten Teilsatz-Wirkung (3 → 2 Teilsätze hebt das
    # Verhältnis, 2 → 1 senkt es; _verursacht)
    "teilsatz_verhaeltnis_21": {"gegen": {"nebensatz", "kommas"}, "ki": {"buendeln", "kommas", "nebensatz", "fw_ankuendigung", "fw_dass"}},
    # kürzende Wort-Aufträge, Gegenfolie und Mitte-Teilung kürzen Satzklammern („können nicht nur … auswerten“ → zwei kurze
    # Klammern; v6-Prüfung: Controlling 5,00 → 4,42, rot)
    "satzklammer_mittel": {"gegen": {"klammer", "klammer_zusatz"}, "ki": {"konnektor", "floskel", "fw_ankuendigung", "gegenfolie", "mitte"}},
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
            "fw_dichte": "Funktionswort-Dichte", "konsistenz": "Vereinheitlichen"}
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
# Aufträge, die einen Teilsatz in eine Nominal- bzw. Präpositionalgruppe überführen (lokale Wirkungsprüfung: Teilsätze des Satzes)
VERDICHTUNG_TYPEN = {"nebensatz", "kommas", "fw_dass"}
# Technikwechsel statt bloßem Aussetzen, wenn ein befolgter Auftrag seine Kennzahl nicht bewegt hat
TECHNIK_WECHSEL = {"absatz_teilen": "absatz_zusammen", "absatz_zusammen": "absatz_teilen"}
ZIEL_TYPEN = {"gender", "gedankenstrich", "bindestrich", "semikolon", "floskel", "konsistenz"}  # bei „Ziel erreicht“ (Muster nur mit Gewicht ≥ 1,5)
ZIEL_MAX = 5


def anfang(text: str, n: int = 7) -> str:
    """Satzanfang für die Anzeige; eine führende Quellenklammer (Beleg des vorigen Zitats) wird übersprungen."""
    w = text[fuehrende_quelle(text):].split()
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

def _beleg_ende(text: str, i: int) -> int:
    """Ende einer Quellenklammer direkt hinter einem schließenden Anführungszeichen (Position i; Leerzeichen und Satzgrenze
    dazwischen erlaubt): „[2018.06.06_Lehrende, Absatz 8]“, „(ebd., S. 9)“, „[Mergner et al. (2015), S. 9)]“. Gehört zum
    Zitat (Beleg des wörtlichen Wortlauts), nicht zum Folgesatz. Sonst i."""
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
                inhalt = text[j + 1:k]
                if re.search(r"\d|\bebd\b|\bebenda\b|\bvgl\b|\bders\.|\bdies\.|\bHrsg\b|\bzit\b|\bInterview", inhalt):
                    return k + 1
                return i
    return i


QUELLE_VORN_RE = re.compile(r"^\s*(?:\[[^\[\]]{1,100}\]|\((?=[^()]*\d)[^()]{1,80}\))\s*")


def fuehrende_quelle(text: str) -> int:
    """Länge einer Quellenklammer am Satzanfang („[2018.06.06_Lehrende, Absatz 8] Studierende …“): der Beleg des vorigen
    Zitats, den die Satztrennung dem Folgesatz zuschlägt. Anzeige und Satzanfangs-Prüfungen überspringen ihn."""
    m = QUELLE_VORN_RE.match(text)
    if not m or not re.search(r"[A-Za-zÄÖÜäöüß]", text[m.end():]):
        return 0
    inhalt = m.group(0)
    return m.end() if re.search(r"\d|\bebd\b|\bvgl\b|\bders\.|\bHrsg\b", inhalt) else 0


def zitat_masken(saetze: list[dict]) -> dict[int, str]:
    """Satztext mit maskierten wörtlichen Zitaten („…“, "…", »…«, ›…‹) und Klammern mit Quellenangabe (gleiche Länge).

    Zitate dürfen über Satzgrenzen innerhalb eines Absatzes reichen und verschachtelt sein (»Wie … sagen kann: »Jawoll …«.
    Genau.«): ein Stapel führt die Verschachtelungstiefe, das Zitat endet erst bei Tiefe 0. Ist das erste Guillemet im Absatz
    ein », gilt « nur als Schließer (deutsche Form), sonst umgekehrt (»…« bzw. «…»); ebenso › und ‹. Eine Quellenklammer direkt
    hinter dem schließenden Zeichen gehört zum Zitat. Ein nie geschlossenes „, », «, › bzw. ‹ gilt bis zum Satzende; ein nie
    geschlossenes “ oder " ist vermutlich ein einzelnes Zeichen und wird nicht maskiert. Nie geschlossene Öffner zählen danach
    nicht mehr mit (erneuter Durchlauf ohne sie): ein verirrtes oder falsch geschlossenes Zeichen („…", Zoll-Zeichen) hielte die
    Tiefe sonst für den Rest des Absatzes über 0, und spätere echte Zitate blieben ungeschützt (v7-Prüfung, fhws S26/S27)."""
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
        erst_g = next((ch for ch in text if ch in "»«"), "»")
        erst_e = next((ch for ch in text if ch in "›‹"), "›")
        oeffner = {"„": "“”", "“": "”", '"': '"', erst_g: "«" if erst_g == "»" else "»", erst_e: "‹" if erst_e == "›" else "›"}
        # gemischt geschlossen („…"): das nächste Anführungszeichen nach „ ist ein gerades und bis zum nächsten „ (bzw. Absatzende)
        # folgt kein “/” mehr – dann schließt dieses " das „ (sonst bliebe „ offen und das " öffnete eine neue Ebene)
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

        def durchlauf(ignoriert: set[int]) -> tuple[list[tuple[int, int]], list[tuple[str, str, int]]]:
            spannen_: list[tuple[int, int]] = []
            stapel: list[tuple[str, str, int]] = []  # (Öffner, Schließer, Start)
            i = 0
            while i < len(text):
                ch = scan[i]
                if i in ignoriert:
                    i += 1
                    continue
                # schließt das Zeichen eine offene Ebene? (die innerste zuerst; nicht geschlossene innere Ebenen fallen mit weg)
                ebene = next((k for k in range(len(stapel) - 1, -1, -1) if ch in stapel[k][1]), None)
                if ebene is not None:
                    start = stapel[ebene][2]
                    del stapel[ebene:]
                    if not stapel:
                        ende = _beleg_ende(text, i + 1)
                        spannen_.append((start, ende))
                        i = max(i + 1, ende)
                        continue
                elif ch in oeffner:
                    stapel.append((ch, oeffner[ch], i))
                i += 1
            return spannen_, stapel

        ignoriert: set[int] = set()
        offene: list[tuple[str, str, int]] = []
        spannen, stapel = durchlauf(ignoriert)
        while stapel:
            offene += stapel
            ignoriert |= {x[2] for x in stapel}
            spannen, stapel = durchlauf(ignoriert)
        for zeichen_, _zu, start in offene:
            if zeichen_ in "„»«›‹":
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


def _synonym_kopf(w: str) -> set[int]:
    """Wie _synonym_gruppen, aber nur, wenn das Wort selbst oder sein Grundwort zur Gruppe gehört („Konsumenten“,
    „Endkunden“) – nicht über ein Bestimmungswort („Studiengänge“ ist keine „Studie“)."""
    low = w.lower().replace("-", "")
    out = set()
    for gi, (gruppe, nur_kopf) in enumerate(SYNONYM_GRUPPEN):
        if nur_kopf:
            continue
        if any(low.endswith(g + fl) for formen in gruppe.values() for g in formen for fl in _FLEXION):
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


# Satzlängen-Kennzahlen, die sich aus einer Längenfolge berechnen lassen (Definitionen wie analyse.py)
LAENGEN_KENNZAHLEN = ("anteil_lange_saetze", "anteil_mittlere_saetze", "anteil_sehr_lange_saetze", "anteil_kurze_saetze",
                      "satzlaenge_mittel", "satzlaenge_median", "satzlaenge_sd", "satzlaenge_cv", "satzlaenge_dispersion",
                      "satzlaenge_schiefe", "rhythmus_r1_log")
# Lesbarkeitsformeln (analyse.py) hängen linear von der Ø-Satzlänge ab: LIX = ASL + …, Wiener = 0,1672·ASL + …, Flesch = 180 − ASL − …
LESBARKEIT_ASL = {"lix": 1.0, "wiener_sachtextformel": 0.1672, "flesch_amstad": -1.0}
ABSATZ_CV = "saetze_pro_absatz_cv"  # Modellmerkmal, das Bündeln/Teilen über die Sätze je Absatz mitbewegen
L1_GEWICHT = 0.5  # L1-Abstand zur menschlichen Klassenverteilung: kein Modellmerkmal, nur weicher Term
RHYTHMUS_ABWERTUNG = 0.5  # je IQR, um den sich der Rhythmus vom grünen Bereich entfernt
WECHSEL_ABWERTUNG = 0.03  # je neuem strengem Kurz-Lang-Wechsel
ROT_TOLERANZ = 0.25  # IQR, um die eine schon rote Kennzahl auf der KI-Seite weiter abrutschen darf (sonst harte Grenze)
AMPEL_PUNKTE = {"gruen": 1.0, "gelb": 0.5, "rot": 0.0}


def laengen_werte(laengen: list[int]) -> dict:
    """Satzlängen-Kennzahlen wie analyse.py aus einer Längenfolge (Schiefe als Median über Fenster à 800 Wörter)."""
    n = len(laengen)
    if not n:
        return {}
    mu, sd_ = analyse.mittel(laengen), analyse.sd(laengen)
    try:
        fenster = analyse.satz_fenster(laengen)
    except Exception:  # noqa: BLE001 – ältere analyse.py: ein Fenster
        fenster = [(0, n)]
    return {"anteil_lange_saetze": sum(x >= LANG_AB for x in laengen) / n,
            "anteil_mittlere_saetze": sum(MITTEL_VON <= x <= MITTEL_BIS for x in laengen) / n,
            "anteil_sehr_lange_saetze": sum(x >= SEHR_LANG_AB for x in laengen) / n,
            "anteil_kurze_saetze": sum(x <= KURZ_MAX for x in laengen) / n,
            "satzlaenge_mittel": mu, "satzlaenge_median": float(statistics.median(laengen)), "satzlaenge_sd": sd_,
            "satzlaenge_cv": sd_ / mu if mu else 0.0, "satzlaenge_dispersion": sd_ ** 2 / mu if mu else 0.0,
            "satzlaenge_schiefe": statistics.median(analyse.schiefe(laengen[a:e]) for a, e in fenster),
            "rhythmus_r1_log": rhythmus(laengen)}


class LaengenModell:
    """Bewertet Satzlängen-Umbauten (Bündeln, Längenaufbau, Mitte ausdünnen, Teilen, Herauslösen) vor der Ausgabe.

    Zielfunktion = Δ-Logit der längenabhängigen Modellmerkmale (Koeffizienten, Mittel, SD und z-Clipping aus baselines;
    mit Absatzangaben auch saetze_pro_absatz_cv, das Bündeln/Teilen über die Sätze je Absatz mitbewegen)
    + Score-Anteil der bewerteten Längen-Kennzahlen (Gewicht · Ampelpunkte) − L1_GEWICHT · ΔL1 der Klassenverteilung
    (weicher Term) − Rhythmus-Abwertung. Harte Grenzen: kein Umbau, der eine Längen- oder Lesbarkeitskennzahl rot macht
    (bzw. weiter ins Rot treibt) oder über P75/unter P25 auf die der KI gegenüberliegende Seite schiebt."""

    def __init__(self, ref: dict, ts: dict, lesbar: dict | None = None, asl0: float | None = None):
        modell = ts.get("modell") or {}
        koef = modell.get("koeffizienten") or {}
        self.ref = ref
        self.koef = {k: koef[k] for k in LAENGEN_KENNZAHLEN if k in koef and k in (modell.get("mittel") or {})}
        # Bündeln/Teilen ändern auch die Zahl der Sätze je Absatz: Modellmerkmal saetze_pro_absatz_cv (nur, wenn die Absätze
        # bekannt sind; geht in Zielfunktion und harte Grenzen ein, nicht in die Längen-Diagnose)
        self.koef_absatz = koef.get(ABSATZ_CV) if ABSATZ_CV in (modell.get("mittel") or {}) else None
        self.mu, self.sd = modell.get("mittel") or {}, modell.get("sd") or {}
        self.clip = modell.get("z_clip") or getattr(analyse, "Z_CLIP", 3.0)
        self.kappen = modell.get("kappen") or {}  # v7: einseitige Kappung am menschlichen Band (wie analyse.bewerte)
        self.ziel = ts.get("satzlaengen_verteilung_mensch") or {}
        self.gewicht = {k: float(ref[k].get("gewicht") or 0.0) for k in LAENGEN_KENNZAHLEN if k in ref and ref[k].get("bewertet")}
        self.lesbar = {k: v for k, v in (lesbar or {}).items() if v is not None and k in ref}
        self.asl0 = asl0

    def _z(self, k: str, v: float) -> float:
        kappe = self.kappen.get(k)
        if kappe:
            v = min(v, kappe["wert"]) if kappe.get("seite") == "oben" else max(v, kappe["wert"])
        return max(-self.clip, min(self.clip, (v - self.mu[k]) / (self.sd.get(k) or 1.0)))

    def werte(self, laengen: list[int], absatz_anz: list[int] | None = None) -> dict:
        w = laengen_werte(laengen)
        if w and self.asl0 is not None:
            for k, wert0 in self.lesbar.items():
                w[k] = wert0 + LESBARKEIT_ASL[k] * (w["satzlaenge_mittel"] - self.asl0)
        if w and absatz_anz is not None and len(absatz_anz) > 1 and self.koef_absatz is not None:
            w[ABSATZ_CV] = analyse.cv(absatz_anz)  # wie analyse.py: CV der Sätze je Absatz
        return w

    def logit(self, w: dict) -> float:
        out = sum(c * self._z(k, w[k]) for k, c in self.koef.items() if k in w)
        if ABSATZ_CV in w and self.koef_absatz is not None:
            out += self.koef_absatz * self._z(ABSATZ_CV, w[ABSATZ_CV])
        return out

    def score(self, w: dict, n: int) -> float:
        return sum(g * AMPEL_PUNKTE[status_von(w[k], self.ref[k])] for k, g in self.gewicht.items()
                   if k in w and (k != "rhythmus_r1_log" or n >= 30))

    def verletzt(self, alt: dict, neu: dict) -> str | None:
        """Harte Grenze (None = eingehalten), nur für Kennzahlen, die der Umbau vom grünen Bereich wegbewegt:
        - Längen-Kennzahl auf der der KI gegenüberliegenden Seite über P75 bzw. unter P25 (Überkorrektur, v1: 31 % lange Sätze);
        - Lesbarkeit (LIX, Wiener, Flesch) auf der Gegenseite im letzten Viertel vor P90 bzw. P10 oder darüber hinaus
          (Puffer für die Schätzung der Verdichtung);
        - jede Kennzahl, die neu rot wird oder im Rot um mehr als ROT_TOLERANZ IQR weiter abrutscht."""
        for k, v in neu.items():
            if k not in self.ref or k not in alt:
                continue
            r = self.ref[k]
            a_alt, a_neu = band_abstand(alt[k], r), band_abstand(v, r)
            if a_neu <= a_alt + 1e-9:
                continue
            m = r["mensch"]
            gegen = seite_von(v, r) == "gegen"
            if k in LESBARKEIT_ASL:
                oben = v > m["p75"]
                linie = m["p75"] + 0.75 * (m["p90"] - m["p75"]) if oben else m["p25"] - 0.75 * (m["p25"] - m["p10"])
                if gegen and (v > linie if oben else v < linie):
                    return k
            elif gegen and a_neu > 0:
                return k
            st_alt, st_neu = status_von(alt[k], r), status_von(v, r)
            if st_neu == "rot" and (st_alt != "rot" or a_neu - a_alt > ROT_TOLERANZ):
                return k
        return None

    def bewerte(self, alt_l: list[int], neu_l: list[int], alt_abs: list[int] | None = None,
                neu_abs: list[int] | None = None) -> tuple[float | None, dict]:
        """(Wert der Zielfunktion oder None bei verletzter harter Grenze, Einzelteile). alt_abs/neu_abs: Sätze je Absatz
        vorher/nachher (dann zählt die Sätze-pro-Absatz-Variation mit)."""
        alt, neu = self.werte(alt_l, alt_abs), self.werte(neu_l, neu_abs)
        grenze = self.verletzt(alt, neu)
        teile = {"logit": self.logit(neu) - self.logit(alt), "score": self.score(neu, len(neu_l)) - self.score(alt, len(alt_l)),
                 "l1": 0.0, "rhythmus": 0.0, "grenze": grenze, "werte": neu}
        if ABSATZ_CV in alt and ABSATZ_CV in neu:
            teile["absatz"] = self.koef_absatz * (self._z(ABSATZ_CV, neu[ABSATZ_CV]) - self._z(ABSATZ_CV, alt[ABSATZ_CV]))
        if self.ziel:
            teile["l1"] = -L1_GEWICHT * (_l1(analyse.verteilung(neu_l), self.ziel) - _l1(analyse.verteilung(alt_l), self.ziel))
        if "rhythmus_r1_log" in self.ref:
            r = self.ref["rhythmus_r1_log"]
            teile["rhythmus"] = -RHYTHMUS_ABWERTUNG * max(0.0, band_abstand(neu["rhythmus_r1_log"], r) - band_abstand(alt["rhythmus_r1_log"], r))
        teile["rhythmus"] -= WECHSEL_ABWERTUNG * max(0, wechsel(neu_l) - wechsel(alt_l))
        if grenze:
            return None, teile
        return teile["logit"] + teile["score"] + teile["l1"] + teile["rhythmus"], teile


def laengen_folge(sim: list[list[int]]) -> list[int]:
    """Längenfolge aus dem Simulationszustand (je Fokussatz die Liste der Längen, die nach den Aufträgen daraus werden)."""
    return [x for teil in sim for x in teil]


def mit_ersetzung(sim: list[list[int]], ersatz: dict[int, list[int]]) -> list[list[int]]:
    return [ersatz.get(i, teil) for i, teil in enumerate(sim)]


def buendel_laenge(a: int, b: int) -> int:
    """Voraussichtliche Länge des Verbundsatzes: etwa 10 % kürzer, aber mindestens LANG_AB (der Auftrag verlangt ≥ 30 Wörter)."""
    s = a + b
    return max(min(s, LANG_AB), round(VERDICHTUNG * s))


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
        return "im zweiten Satz das Bezugswort als Nomen wiederholen, kein Pronomen"
    if f in ("und", "oder"):
        # „Subjekt wiederholen“ allein erfüllt auch „Sie …“ – dann bemängelt die nächste Runde genau diesen Satzanfang
        return (f"nach „{f}“ einen neuen Satz beginnen und das Subjekt als Nomen wiederholen (etwa „Mittelständische Unternehmen …“ "
                "statt „Sie …“), kein Pronomen")
    if f in ("etwa", "nämlich", "also", "insbesondere", "darunter", "vor"):
        return "die Erläuterung als eigenen Satz mit Verb formulieren"
    art = FUGE_ART.get(f, "Verknüpfung")
    # Artikel nach dem Genus („den Gegensatz“, „den Bezug“, „das Mittel“ – nicht „die Gegensatz“; v7-Prüfung)
    artikel = "den" if art.split()[0] in ("Gegensatz", "Bezug", "Zeitbezug") else "das" if art == "Mittel" else "die"
    return f"{artikel} {art} im zweiten Satz ausdrücklich behalten"


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
    elif d["anteil_lange"] < lang50 and (d["anteil_mittlere"] > mittl50
                                         or (p("satzlaenge_dispersion", "p50") is not None and dispersion(L) < p("satzlaenge_dispersion", "p50"))):
        # zu wenig lange Sätze und eine überfüllte Mitte bzw. zu gleichmäßige Längen (Dispersion unter dem Median); dass die
        # Mitte dabei nicht unter P25 fällt, sichert die harte Grenze der Simulation
        d["modus"] = "buendeln"
        # jede Bündelung macht aus zwei Sätzen einen: k Bündelungen ergeben (lange + k) / (n − k) – Kontingent so, dass der
        # Anteil am nächsten beim menschlichen Median landet (nicht round(p50 · n) − lange: das schießt bis ~0,6 Sätze darüber)
        d["kontingent"] = max(0, round((lang50 * d["n"] - d["lange"]) / (1 + lang50)))
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
        # Satzlängen-Simulation: je Fokussatz die Längen, die nach den Aufträgen dieser Runde voraussichtlich daraus werden
        self.fokus_index = {s["nr"]: i for i, s in enumerate(self.fokus)}
        self.sim: list[list[int]] = [[s["woerter"]] for s in self.fokus]
        self.laengen_modell = LaengenModell(self.ref, self.ts, {k: self.wert(k) for k in LESBARKEIT_ASL},
                                            analyse.mittel([s["woerter"] for s in self.fokus]) if self.fokus else None)
        self.sim_gewinn: dict[str, float] = {}  # simulierter Gewinn der Zielfunktion je Hinweistyp (Bericht, Diagnose)
        self.passiv_budget: int | None = None  # Passiv-Relativsätze, die umgebaut werden dürfen, ohne unter P25 zu fallen
        self.neu_geteilt: dict[int, str] = {}  # Sätze, die erst durch einen befolgten Teilen-/Herauslöse-Auftrag entstanden sind
        self.klammer_sim: dict | None = None  # Satzklammer-Simulation (Spannen, Summe, Ziel)
        # Gegenfolie, deren Kontrast die Aussage ist: kein Auftrag, nur einmal als Info-Zeile „Bewusst stehen lassen“
        self.stehen_lassen: list[dict] = []
        self.stehen_lassen_frueher: set[str] = {a for mess in self.messungen for a in (mess.get("stehen_lassen") or [])} \
            | {a for _, schl in self.frueher for (t, a) in schl if t == "gegenfolie" and a}
        # Nominalketten je Satz (Genitiv-/von-Ketten wie analyse.py): kein Nominalisierungsauftrag in Sätze mit ≥ 3 Nomen in
        # Folge, wenn der Bericht ohnehin „Wortwahl einfacher“ als Hebel führt
        self.kette_max: dict[int, int] = {}
        self.gender_info: list[str] = []  # Gender-Restformen nur in wörtlichen Zitaten: Info statt Auftrag
        self.fw_teilsatz_gesperrt: set[tuple[int, str]] = set()  # (Satz, Typ): Funktionswort-Umbau höbe das Verhältnis 2:1

    def absatz_anzahl(self, sim: list[list[int]]) -> list[int]:
        """Sätze je Absatz im Fokus für einen Simulationszustand (Bündeln −1, Teilen +1 im Absatz des Satzes)."""
        anz: dict[int, int] = {}
        for s, teil in zip(self.fokus, sim):
            anz[s["absatz"]] = anz.get(s["absatz"], 0) + len(teil)
        return [anz[a] for a in sorted(anz)]

    def laengen_umbau(self, ersatz: dict[int, list[int]]) -> tuple[float | None, dict]:
        """Bewertet einen Satzlängen-Umbau auf dem aktuellen Simulationszustand (Index im Fokus → neue Längen), einschließlich
        der Wirkung auf die Sätze-pro-Absatz-Variation (Modellmerkmal; ein Bündel-Auftrag in einem langen Absatz macht die
        Absätze gleichmäßiger und kann so mehr kosten, als die Satzlängen bringen)."""
        neu = mit_ersetzung(self.sim, ersatz)
        return self.laengen_modell.bewerte(laengen_folge(self.sim), laengen_folge(neu), self.absatz_anzahl(self.sim),
                                           self.absatz_anzahl(neu))

    def uebernimm(self, typ: str, ersatz: dict[int, list[int]], wert: float | None) -> None:
        self.sim = mit_ersetzung(self.sim, ersatz)
        if wert is not None:
            self.sim_gewinn[typ] = self.sim_gewinn.get(typ, 0.0) + wert

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
        mk = self.masken.get(s["nr"], s["text"])
        return mk[fuehrende_quelle(s["text"]):].lstrip().startswith(MASKE)

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
                              "ersetzbar": sorted({w.lower() for w in ersetzbar if w}), "pos": self.fokus_index.get(s["nr"]) if s else None,
                              "teilsaetze": sum(analyse.teilsatz_zerlegung(s["text"])[:2]) if s and typ in VERDICHTUNG_TYPEN else None,
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
        if z["id"] == "semikolon_pro_1000" and semikolon_zahl(L) <= semikolon_erlaubt(L):
            continue  # höchstens 1–2 je 800 Wörter: unauffällig (das Modellgewicht zählt oben weiter)
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
        lange_sehr_wenig = bool(lang_z) and lang_z["wert"] < lang_z["mensch_p25"]
        befolgt = vorrunde_befolgt(L)
        for k, zuordnung in WAECHTER.items():
            v1 = L.roh_jetzt.get(k)
            if k not in ref or v1 is None:
                continue
            r = ref[k]["mensch"]
            iqr = (r["p75"] - r["p25"]) or ((r["p90"] - r["p10"]) / 2) or 1e-9
            # Satzanfangs-Wiederholung ist unbewertet, zählt aber wie eine bewertete Kennzahl: eine Anknüpfung, die den Anfang des
            # Vorsatzes wiederholt, soll schon bei Gelb mit deutlicher Verschiebung auffallen (v6-Prüfung, haw 0,024 → 0,071)
            bewertet = bool(ref[k].get("bewertet")) or k == "satzanfang_wiederholung"
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
                if k == "satzlaenge_schiefe" and seite1 == "ki" and lange_fehlen:
                    break  # geringe Schiefe bei zu wenigen langen Sätzen: genau ein langer Satz würde helfen, Bündeln bleibt
                if seite1 == "ki":
                    if runde != len(L.messungen):
                        continue  # Nebenwirkung nur gegenüber der Vorrunde einem Auftrag zuordnen
                    # nur Typen, die in der Vorrunde befolgt wurden und deren simulierte Wirkung in die beobachtete Richtung zeigt
                    typen = {t for t in zuordnung.get(seite1, set()) if t in befolgt and _verursacht(L, t, befolgt[t], k, v1 - v0)}
                else:
                    typen = set(zuordnung.get(seite1, set()))  # Überkorrektur: harte Grenze, unabhängig von der Zuordnung
                geschuetzt = []
                if lange_sehr_wenig and "buendeln" in typen:
                    # nie aussetzen, solange lange Sätze unter P25 liegen – die Ursache aber nennen (v6-Prüfung: „keinem Auftrag
                    # zuzuordnen“, obwohl die eigene Bündelung das Verhältnis 2:1 über P90 hob)
                    typen.discard("buendeln")
                    geschuetzt.append("buendeln")
                grenze = _grenze_text(v1, r, st1 == "rot")
                L.ueberkorrektur.append({"id": k, "name": analyse.NAMEN.get(k, k), "vorher": v0, "messung_vorher": runde, "wert": v1,
                                         "grenze": grenze, "art": "Nebenwirkung" if seite1 == "ki" else "Überkorrektur",
                                         "aussetzen": sorted(typen), "geschuetzt": geschuetzt})
                if typen:
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
    # Passiv-Schutz auf dem Wert NACH den Aufträgen: so viele Sätze dürfen ihr einziges Passiv verlieren, bis P25 erreicht ist
    p25 = L.p_("anteil_passiv", "p25")
    if p25 is not None and L.fokus:
        n_passiv = sum(1 for s in L.fokus if analyse.ist_passiv(s["text"]))
        L.passiv_budget = max(0, n_passiv - math.ceil(p25 * len(L.fokus)))
        if "nebensatz_relativ" in L.ausgesetzt:
            L.passiv_budget = 0
    if "werden" in L.schutz:
        r_ = next(r for r in L.fw_diag["woerter"] if r["wort"] == "werden")
        L.setze_aus({"nebensatz_werden"}, f"„werden“ {r_['anzahl']}× statt etwa {fmt(r_['mensch'])} bei menschlicher Rate")


def _befolgt(L: Lauf, h: dict) -> bool:
    """Wurde ein Auftrag der Vorrunde umgesetzt? Satz verändert (Anfang nicht mehr da, Länge ±3, Folgesatz aufgelöst) bzw.
    Absatzgrenze gesetzt oder aufgehoben."""
    a = h.get("anfang")
    if not a:
        return False
    if a.startswith("abk:"):
        return any(w not in L.anfang_index for w in h.get("weitere") or [])  # Auftrag über mehrere Sätze: einer davon verändert
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


def vorrunde_befolgt(L: Lauf) -> dict[str, list[dict]]:
    """Befolgte Aufträge der Vorrunde je Hinweistyp (Teile kombinierter Aufträge zählen bei jedem ihrer Typen)."""
    out: dict[str, list[dict]] = {}
    for h in (L.vorher or {}).get("hinweise") or []:
        if not isinstance(h, dict) or not h.get("typ") or not _befolgt(L, h):
            continue
        for t in h.get("typen") or [h["typ"]]:
            out.setdefault(t, []).append(h)
    return out


def sim_wirkung(L: Lauf, hs: list[dict], k: str) -> float | None:
    """Simulierte Wirkung befolgter Aufträge auf eine Längen- bzw. Lesbarkeitskennzahl: Kennzahl auf der gespeicherten
    Längenfolge der Vorrunde, in der nur diese Umbauten ausgeführt sind, minus ohne. None = nicht simulierbar."""
    alt = (L.vorher or {}).get("laengen")
    if not alt or (k not in LAENGEN_KENNZAHLEN and k not in LESBARKEIT_ASL):
        return None
    sim = [[x] for x in alt]
    geaendert = False
    for h in hs:
        pos, neu, alt_l = h.get("pos"), h.get("sim"), h.get("laengen_alt")
        if pos is None or neu is None or not alt_l or pos + len(alt_l) > len(sim) or sim[pos] != [alt_l[0]]:
            continue
        sim[pos] = list(neu)
        for j in range(1, len(alt_l)):
            sim[pos + j] = []
        geaendert = True
    if not geaendert:
        return None
    w0, w1 = laengen_werte(alt), laengen_werte(laengen_folge(sim))
    if k in LESBARKEIT_ASL:
        return LESBARKEIT_ASL[k] * (w1["satzlaenge_mittel"] - w0["satzlaenge_mittel"])
    return w1[k] - w0[k]


def _verursacht(L: Lauf, typ: str, hs: list[dict], k: str, delta: float) -> bool:
    """Ist die beobachtete Änderung delta der Kennzahl k plausibel diesem (befolgten) Auftragstyp zuzuschreiben? Längen- und
    Lesbarkeitskennzahlen: die simulierte Wirkung zeigt in dieselbe Richtung und macht mindestens ein Viertel der Änderung
    aus. Teilsatz-Kennzahlen beim Bündeln: der Verbundsatz hat tatsächlich zwei Teilsätze bekommen. Sonst: befolgt genügt."""
    eff = sim_wirkung(L, hs, k)
    if eff is not None:
        return eff * delta > 0 and abs(eff) >= 0.25 * abs(delta)
    if typ in ("kommas", "nebensatz", "fw_ankuendigung", "fw_dass") and k == "teilsatz_verhaeltnis_21":
        # simulierte Teilsatz-Wirkung: nur Aufträge an Sätzen, aus deren drei Teilsätzen zwei werden sollten, heben das Verhältnis
        # (und nur, wenn der Satz tatsächlich einen Teilsatz verloren hat)
        return any(teilsatz_wirkung(h.get("teilsaetze") or 0, h.get("variante")) * delta > 0 and lokal_wirksam(L, h) is not False
                   for h in hs)
    if typ == "buendeln" and k in ("teilsatz_verhaeltnis_21", "anteil_saetze_mit_nebensatz"):
        verbund = [L.anfang_index.get(h.get("anfang")) for h in hs]
        return any(v and sum(analyse.teilsatz_zerlegung(v["text"])[:2]) >= 2 for v in verbund)
    if k in LAENGEN_KENNZAHLEN and (L.vorher or {}).get("laengen") and typ not in STRUKTURELL:
        return False  # die Längenfolge ist bekannt, der Typ ändert Längen aber nicht gezielt
    return True


def lokal_wirksam(L: Lauf, h: dict) -> bool | None:
    """Lokale Prüfung eines befolgten Satzlängen-Auftrags: Bündeln – existiert der Verbundsatz mit ≥ 27 Wörtern (und ist der
    Folgesatz aufgegangen)? Teilen, Mitte, Herauslösen – ist der Satz um mindestens 5 Wörter kürzer geworden? Nebensatz bzw.
    Komma → Nominalgruppe – hat der Satz einen Teilsatz weniger? None = nicht prüfbar (Satzanfang umformuliert, alter Verlauf)."""
    if h.get("typ") in VERDICHTUNG_TYPEN and h.get("teilsaetze"):
        # Nebensatz/Komma → Nominalgruppe: hat der Satz selbst einen Teilsatz verloren? (Die globale Kennzahl bewegen auch
        # andere Aufträge derselben Runde, z. B. ein Komma-Auftrag, der aus drei Teilsätzen zwei macht.)
        s = _satz_ungefaehr(L, h.get("anfang"))
        return None if s is None else sum(analyse.teilsatz_zerlegung(s["text"])[:2]) < h["teilsaetze"]
    s = L.anfang_index.get(h.get("anfang"))
    if s is None:
        return None
    if h.get("typ") == "buendeln":
        if any(w in L.anfang_index for w in h.get("weitere") or []):
            return None
        return s["woerter"] >= LANG_AB - 3
    if h.get("typ") in ("mitte", "teilen") or (h.get("typ") == "kommas" and h.get("variante") == "herausloesen"):
        return s["woerter"] <= (h.get("laenge") or 999) - 5
    return None


def _satz_ungefaehr(L: Lauf, a: str | None) -> dict | None:
    """Satz zu einem Gedächtnisschlüssel, auch wenn der Umbau weiter vorn eingegriffen hat: exakt, sonst der einzige Satz mit
    denselben ersten vier Wörtern."""
    if not a:
        return None
    s = L.anfang_index.get(a)
    if s is not None:
        return s
    kopf = " ".join(a.split()[:4])
    treffer = [x for k, x in L.anfang_index.items() if len(kopf.split()) == 4 and " ".join(k.split()[:4]) == kopf]
    return treffer[0] if len(treffer) == 1 else None


def _wirksamkeit(L: Lauf) -> None:
    """Wirksamkeitsgedächtnis: Hat ein in der Vorrunde befolgter Auftragstyp seine Zielkennzahl dem menschlichen Median
    nicht nähergebracht, wird die Technik gewechselt (Absätze: Zusammenlegen statt Teilen und umgekehrt) bzw. der Typ für
    diese Runde ausgesetzt – mit Begründung im Bericht. Satzlängen-Aufträge werden lokal geprüft (Verbundsatz da? Satz
    geteilt?), nicht an der globalen Kennzahl, die auch andere Aufträge bewegen; Bündeln wird nie ausgesetzt, solange lange
    Sätze unter P25 liegen."""
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
    lang_z = L.kz.get("anteil_lange_saetze")
    lange_sehr_wenig = bool(lang_z) and lang_z["wert"] < lang_z["mensch_p25"]
    for typ, hs in nach_typ.items():
        if typ == "buendeln" and lange_sehr_wenig:
            continue
        ziel = next((h["ziel"] for h in hs if h.get("ziel")), ZIEL_KENNZAHL[typ])
        if ziel not in L.ref:
            continue
        lokal = [x for x in (lokal_wirksam(L, h) for h in hs if _befolgt(L, h)) if x is not None]
        if lokal:
            if any(lokal):
                continue  # mindestens ein Auftrag hat lokal gewirkt: globale Schwankungen stammen von anderen Änderungen
            grund = (f"{TYP_NAME.get(typ, typ)} wurde nach Messung {len(L.messungen)} umgesetzt, aber ohne die verlangte Länge "
                     + (f"(kein Verbundsatz mit ≥ {LANG_AB - 3} Wörtern)" if typ == "buendeln" else "(der Satz ist nicht geteilt)"))
            L.setze_aus({typ}, grund)
            L.wirkung.append({"typ": typ, "ziel": ziel, "vorher": None, "jetzt": None, "wechsel": TECHNIK_WECHSEL.get(typ), "grund": grund})
            continue
        alt = next((h["ziel_wert"] for h in hs if h.get("ziel_wert") is not None), alt_werte.get(ziel))
        neu = L.wert(ziel)
        if alt is None or neu is None or not any(_befolgt(L, h) for h in hs):
            continue
        r = L.ref[ziel]["mensch"]
        iqr = (r["p75"] - r["p25"]) or ((r["p90"] - r["p10"]) / 2) or 1e-9
        if abs(neu - r["p50"]) < abs(alt - r["p50"]) - 0.02 * iqr:
            continue  # wirksam: die Kennzahl ist dem menschlichen Median nähergekommen
        eff = sim_wirkung(L, [h for h in hs if _befolgt(L, h)], ziel)
        if eff is not None and abs(alt + eff - r["p50"]) < abs(alt - r["p50"]):
            continue  # simuliert hätte der Auftrag allein geholfen: die Gegenbewegung stammt von anderen Änderungen
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
    # auch, wenn die längenabhängigen Modellmerkmale zusammen deutlich Richtung KI ziehen (einzeln je > MODELL_HEBEL)
    laengen_aktiv = laengen_aktiv or sum(min(0.0, (L.kz.get(k) or {}).get("beitrag") or 0.0) for k in L.laengen_modell.koef) <= MODELL_HEBEL
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
    if diag["modus"] == "mitte":
        _mitte(L, diag["kontingent"])
    elif diag["modus"] == "buendeln" and mitte_aktiv:
        # zu wenig lange Sätze und eine überfüllte Mitte: was das Bündeln nicht schafft, dürfen einzelne mittellange Sätze
        # übernehmen – Kontingent bis zum menschlichen Median, simuliert auf dem Stand nach dem Bündeln
        folge = laengen_folge(L.sim)
        m50 = L.p_("anteil_mittlere_saetze", "p50") or 0.5
        ueber = sum(MITTEL_VON <= x <= MITTEL_BIS for x in folge) - m50 * len(folge)
        _mitte(L, min(MAX_MITTE, math.ceil(ueber / (1 + m50))) if ueber > 0 else 0)
    _kurz(L)


def _buendeln(L: Lauf) -> None:
    """Bündeln bis zum Kontingent (lange Sätze bis zum menschlichen Median, höchstens MAX_BUENDELN je Runde): jedes zulässige
    Nachbarpaar wird an der Zielfunktion des Längenmodells simuliert, der beste Kandidat zuerst. Findet sich kein Paar und
    fehlen lange Sätze deutlich (unter P25), folgt der Längenaufbau: ein fast langer Satz nimmt die kurze Angabe des
    Folgesatzes auf."""
    diag = L.diag
    if diag["modus"] != "buendeln" or diag["kontingent"] <= 0 or "buendeln" in L.ausgesetzt:
        return
    ns, ns90 = L.wert("nominalstil_pro_100"), L.p_("nominalstil_pro_100", "p90")
    if ns is not None and ns90 is not None and ns > ns90:
        # Bündeln fasst einen Satz als Nominal- bzw. Präpositionalgruppe: bei schon sehr hohem Nominalstil entstehen Nominalketten
        # (v4: Ketten mit 4–7 Nomen). Grenze P90 wie beim Wächter für unbewertete Kennzahlen – P75 sperrte in v5 wirksame
        # Bündelungen schon knapp über der Grenze (Controlling +0,006); gegen Ketten wirkt zusätzlich der Auftragstext.
        a, b = fmt_paar(ns, ns90)
        L.setze_aus({"buendeln"}, f"{analyse.NAMEN.get('nominalstil_pro_100', 'Nominalstil')} {a} schon über P90 ({b}) – "
                                  "Bündeln würde weitere Nominalgruppen erzeugen")
        return
    paare = buendel_kandidaten(L)
    grenze = min(diag["kontingent"], MAX_BUENDELN)
    n = _laengen_paare(L, [p_ for p_ in paare if p_[2] != "aufbau"], grenze)
    lang25 = L.p_("anteil_lange_saetze", "p25")
    if n == 0 and lang25 is not None and diag["anteil_lange"] < lang25:
        _laengen_paare(L, [p_ for p_ in paare if p_[2] == "aufbau"], grenze)


def buendel_kandidaten(L: Lauf) -> list[tuple[dict, dict, str]]:
    """Nachbarpaare im selben Absatz: Bündeln (beide ≥ BUENDEL_MIN_TEIL, zusammen BUENDEL_SUMME Wörter; Variante „beispiel“,
    wenn Satz b ein Beispiel anschließt) und Längenaufbau (Satz a mit AUFBAU_A, Satz b mit AUFBAU_B Wörtern, zusammen ≥ 30)."""
    out = []
    for liste in L.absaetze.values():
        for a, b in zip(liste, liste[1:]):
            wa, wb = a["woerter"], b["woerter"]
            if wa >= BUENDEL_MIN_TEIL and wb >= BUENDEL_MIN_TEIL and BUENDEL_SUMME[0] <= wa + wb <= BUENDEL_SUMME[1]:
                if not buendel_laengen_ok(L, wa, wb):
                    continue  # ein Satz ist schon lang: das Paar brächte keinen zusätzlichen langen Satz
                art = "beispiel" if BEISPIEL_ANFANG_RE.match(b["text"].lstrip("„\"(»")) else "buendeln"
                if art == "buendeln" and umkehr(L, a, b):
                    art = "umgedreht"  # kurzer Satz a bzw. Ankündigung: a wird einleitende Angabe in b
            elif (AUFBAU_A[0] <= wa <= AUFBAU_A[1] and AUFBAU_B[0] <= wb <= AUFBAU_B[1]
                  or AUFBAU_A[0] <= wb <= AUFBAU_A[1] and AUFBAU_B[0] <= wa <= AUFBAU_B[1]) and wa + wb >= LANG_AB:
                art = "aufbau"  # der fast lange Satz nimmt die kurze Aussage des Nachbarsatzes auf (beide Reihenfolgen)
            else:
                continue
            if art in ("aufbau", "umgedreht") and wa < wb and eingebettet_status(L, a):
                continue  # kurzer Satz vorn: er geht im langen auf – sein Aussagestatus wird geprüft wie sonst der von Satz b
            if buendel_paar_ok(L, a, b, laenge=False):
                out.append((a, b, art))
    return out


def ohne_verb(text: str) -> bool:
    """Kein finites Verb und kein kleingeschriebenes Inhaltswort mit Verbendung: ein Satzfragment (z. B. die Fortsetzung einer
    Aufzählung über einen Punkt hinweg) – kein Bündelpartner."""
    for t in analyse.tokens(text):
        low = t.lower()
        if low in analyse.FINIT or low in analyse.FINIT_MEHRDEUTIG:
            return False
        if t.islower() and low not in analyse.FUNKTIONSWOERTER and len(low) >= 4 and re.search(r"(?:t|te|ten|en|st|ern|eln)$", low):
            return False
    return True


def buendel_laengen_ok(L: Lauf, wa: int, wb: int) -> bool:
    """Ein Bündelpaar mit einem Satz ab LANG_AB Wörtern bringt keinen zusätzlichen langen Satz, nur einen längeren (v4: ssoar-21977
    S15+16 mit 10 + 33 Wörtern) – zulässig nur, wenn sehr lange Sätze fehlen (unter dem menschlichen Median) und der Verbundsatz
    voraussichtlich sehr lang wird."""
    if max(wa, wb) < LANG_AB:
        return True
    p50 = L.p_("anteil_sehr_lange_saetze", "p50")
    w = L.wert("anteil_sehr_lange_saetze")
    return p50 is not None and w is not None and w < p50 and buendel_laenge(wa, wb) >= SEHR_LANG_AB


def umkehr(L: Lauf, a: dict, b: dict) -> bool:
    """Bündelrichtung umdrehen: Satz a ist kurz (≤ UMKEHR_A_MAX) und Satz b lang (≥ UMKEHR_B_MIN), oder Satz a kündigt nur an
    („Ein erstes Ergebnis betrifft …“). Dann geht a als einleitende Angabe in b auf – nicht der lange Satz als Nominalgruppe in den
    kurzen (v4: Controlling S3+S4 → Satz mit 35 Wörtern und Nominalkette)."""
    return (a["woerter"] <= UMKEHR_A_MAX and b["woerter"] >= UMKEHR_B_MIN) or ankuendigung_a(L.masken[a["nr"]], a["woerter"])


def ankuendigung_a(mk: str, woerter: int) -> bool:
    """Kündigt Satz a nur an? Ein kurzer Satz (≤ ANKUENDIGUNG_A_MAX Wörter) mit „betrifft“/„geht es um“/„folgende“ in den ersten
    sieben Wörtern oder mit Doppelpunkt am Ende."""
    if woerter > ANKUENDIGUNG_A_MAX:
        return False
    return bool(re.search(r":\s*$", mk.rstrip(".")) or ANKUENDIGUNG_A_RE.search(" ".join(mk.split()[:7])))


NEBENSATZ_ANFANG = analyse.SUBJ_UEBERALL | analyse.SUBJUNKTIONEN_NACH_KOMMA | analyse.NUR_NACH_KOMMA


def _haupt_neben(mk: str) -> tuple[str, str]:
    """(Hauptsatz, Neben- und Infinitivsätze) eines Satzes: Kommas einer Aufzählung („die Datensammlung, die Erstellung …
    können …“) trennen keinen Nebensatz – das finite Modalverb steht oft erst hinter ihnen."""
    ohne_klammer = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", mk)  # Belege und Zahlen in Klammern („(−0,22)“) trennen nichts
    teile = re.split(r",", AUTORENLISTE_RE.sub(lambda x: x.group(0).replace(",", ""), ohne_klammer))
    out, neben = [teile[0]], []
    for t in teile[1:]:
        w = [x for x in analyse.tokens(t) if analyse.ist_wort(x)]
        if not w:
            continue
        w0 = w[0].lower()
        if w0 in NEBENSATZ_ANFANG or w0 in ("um", "ohne", "statt", "anstatt") \
                or (w0 in analyse.PRAEPOSITIONEN and len(w) > 1 and w[1].lower() in analyse.RELATIVPRONOMEN) \
                or (w0 in analyse.RELATIVPRONOMEN and not (len(w) > 1 and w[1][:1].isupper())) \
                or re.search(r"\bzu\s+\w+\W*$|\w+zu\w+en\W*$", t.strip()):
            neben.append(t)  # Nebensatz, Relativsatz (Pronomen ohne folgendes Nomen) oder Infinitivgruppe
            continue
        out.append(t)
    return ",".join(out), ",".join(neben)


def hauptsatz_teile(mk: str) -> str:
    """Hauptsatz eines Satzes ohne Neben- und Infinitivsätze (siehe _haupt_neben)."""
    return _haupt_neben(mk)[0]


def modal_im_nebensatz(mk: str) -> str | None:
    """Modalverb in einem Neben- oder Relativsatz („…, an dem … arbeiten sollte“): als Nominalgruppe ginge die Möglichkeit bzw.
    Pflicht verloren – Satz b eines Bündelpaars darf dann nicht aufgehen (v4: Controlling S24+25)."""
    return next((w for w in analyse.tokens(_haupt_neben(mk)[1]) if w.lower() in analyse.MODALVERBEN), None)


def eingebettet_status(L: Lauf, s: dict) -> str | None:
    """Eigener Aussagestatus eines Satzes, der als Nominal- oder Präpositionalgruppe im Nachbarsatz aufgehen soll (wie die
    Prüfung von Satz b in buendel_paar_grund): Vermutung, Gegenüberstellung, Frage, Konjunktiv II/Kontrafaktum, Modal- oder
    Redeverb in der Hauptaussage – nominalisiert ginge er verloren."""
    mk = L.masken[s["nr"]]
    if b_eigener_status(s["text"], mk):
        return "b_status"
    if nominal_sperre(L, s, mk) == "konjunktiv":
        return "b_konjunktiv"
    haupt = hauptsatz_teile(mk)
    if any(w.lower() in analyse.MODALVERBEN for w in analyse.tokens(haupt)) or REDEVERB_RE.search(haupt) or LASSEN_SICH_RE.search(haupt):
        return "b_modal_rede"
    if modal_im_nebensatz(mk):
        return "b_modal_neben"
    return None


def b_eigener_status(text: str, mk: str) -> bool:
    """Trägt ein Satz einen eigenen Aussagestatus, der als Nominalgruppe im Nachbarsatz verloren ginge? Vermutung, Gegenüberstellung,
    Frage, Nebensatz-Anfang, Folgerung bzw. Verallgemeinerung („Also …“, „Insgesamt …“, „Bei beiden … ergibt sich also …“) oder
    Wertung („leider“)."""
    anf = text.lstrip("„\"(»")
    return bool(BUENDEL_B_ANFANG_RE.match(anf) or _VERMUTUNG_RE.search(mk) or re.search(r",\s*sondern\b", mk)
                or text.rstrip("\"“”»)").endswith(("?", "!")) or FOLGERUNG_B_RE.search(anf)
                or FOLGERUNG_KOPF_RE.search(" ".join(anf.split()[:6])) or WERTUNG_ADV_RE.search(mk)
                or KONTRAST_B_RE.search(" ".join(anf.split()[:6])) or bedingung_verberst(text))


# Satz b stellt dem Vorsatz etwas gegenüber („In großen Gruppen bedarf es hingegen …“, „Diesem Nutzen steht jedoch gegenüber …“)
# oder ist ein uneingeleiteter Bedingungssatz („Wird diese … empfohlen, ergibt sich …“, „Herrscht dagegen Misstrauen, führt dies …“):
# als Nominalgruppe in Satz a gingen Gegensatz bzw. Bedingung verloren (v5-Prüfung: ohm-163 S41+42 neu, S30+31)
KONTRAST_B_RE = re.compile(r"\b(?:jedoch|allerdings|hingegen|dagegen|demgegenüber)\b", re.IGNORECASE)
_VERB_KOPF = {"herrscht", "herrschen", "fehlt", "fehlen", "kommt", "kommen", "steigt", "steigen", "sinkt", "sinken", "fällt", "fallen",
              "liegt", "liegen", "folgt", "folgen", "geht", "gehen", "nimmt", "nehmen", "betrachtet", "betrachten", "zeigt", "zeigen",
              "bleibt", "bleiben", "besteht", "bestehen", "überwiegt", "überwiegen", "gelingt", "gelingen", "ändert", "ändern"}
_VERBERST_B_RE = re.compile(r"^(?P<v>[A-ZÄÖÜ][a-zäöüß]+)\s+(?P<w2>\S+)[^.;:?!]*?,\s+(?:so\s+|dann\s+)?(?P<v2>[a-zäöüß]+)\b")
_VERBERST_W2 = {"man", "es", "sich", "dies", "diese", "dieser", "dieses", "der", "die", "das", "ein", "eine", "er", "sie"}


def bedingung_verberst(text: str) -> bool:
    """Uneingeleiteter Bedingungssatz am Satzanfang: finites Verb zuerst, nach dem Komma wieder ein finites Verb („Wird diese …
    empfohlen, ergibt sich …“, „Betrachtet man …, zeigt sich …“). Fragen zählen nicht."""
    anf = text.lstrip("„\"(»")
    m = _VERBERST_B_RE.match(anf)
    if not m or text.rstrip("\"“”»)").endswith("?"):
        return False
    v, v2 = m.group("v").lower(), m.group("v2")
    verb_vorn = v in analyse.FINIT or v in analyse.FINIT_MEHRDEUTIG or v in _VERB_KOPF or (v.endswith("t") and m.group("w2").lower() in _VERBERST_W2)
    verb_nach = v2 in analyse.FINIT or v2 in analyse.FINIT_MEHRDEUTIG or v2 in _VERB_KOPF or bool(re.search(r"(?:t|en)$", v2))
    return verb_vorn and verb_nach and v2 not in analyse.FUNKTIONSWOERTER


def _paar_text(a: dict, b: dict, art: str, neu: int, viele_nebensaetze: bool = False, doppelpunkt: bool = True,
               technik: str = "nominal") -> str:
    # Nominalgruppe nur ohne Nominalkette; als Ausweg ein Doppelpunkt (zählt nicht als Teilsatz) oder „denn“ mit einem Hauptsatz –
    # „denn“ nicht, wenn der Text schon viele Sätze mit zwei Teilsätzen hat (v4: Controlling S24+25, Agile S39+40)
    if technik in ("doppelpunkt", "relativ"):
        # Nominalstil schon über P75: keine weitere Nominalgruppe, nur Doppelpunkt bzw. Relativsatz
        rest = ("Aussagestatus erhalten (Befund, Vermutung, Fähigkeit); Fachbegriffe beider Sätze behalten; keine Nominalgruppe – der "
                "Nominalstil liegt schon über dem Zielbereich.")
        kopf = (f"{zitat(a)} und Satz {b['nr']} ({a['woerter']} + {b['woerter']} Wörter) zu einem Satz mit {LANG_AB} bis höchstens "
                f"~{BUENDEL_MAX_ZIEL} Wörtern verbinden: ")
        if technik == "doppelpunkt":
            wie = (f"Satz {a['nr']} mit Doppelpunkt vor Satz {b['nr']} setzen (Satz {b['nr']} bleibt ein vollständiger Satz)"
                   if art == "umgedreht" else
                   f"Satz {b['nr']} mit Doppelpunkt an Satz {a['nr']} anschließen (Satz {b['nr']} bleibt ein vollständiger Satz)")
        else:
            wie = f"Satz {b['nr']} als Relativsatz an das Bezugsnomen in Satz {a['nr']} anschließen"
        return f"{kopf}{wie}, kein angehängtes „und“. {rest}"
    status = "Aussagestatus erhalten (Befund, Vermutung, Fähigkeit); Fachbegriffe beider Sätze behalten; höchstens zwei Nomen hintereinander"
    if viele_nebensaetze:
        status += ("; geht das nicht, ein Doppelpunkt statt Nominalgruppe – kein „denn“, „weshalb“ oder „wobei“ (der Text hat schon viele "
                   "Nebensätze); sonst das Paar überspringen." if doppelpunkt else
                   "; geht das nicht, das Paar überspringen – kein „denn“, „weshalb“ oder „wobei“ (der Text hat schon viele Nebensätze).")
    else:
        status += ("; geht das nicht, Doppelpunkt oder „denn“ (ein Hauptsatz) statt Nominalgruppe." if doppelpunkt else
                   "; geht das nicht, „denn“ (ein Hauptsatz) statt Nominalgruppe, sofern der zweite Inhalt eine Begründung ist – sonst das "
                   "Paar überspringen.")
    if art == "umgedreht":
        dp = f" oder Satz {a['nr']} mit Doppelpunkt vor Satz {b['nr']} setzen" if doppelpunkt else ""
        return (f"{zitat(a)} und Satz {b['nr']} ({a['woerter']} + {b['woerter']} Wörter) zu einem Satz mit {LANG_AB} bis höchstens "
                f"~{BUENDEL_MAX_ZIEL} Wörtern verbinden: Satz {a['nr']} ist kurz bzw. kündigt nur an – seinen Inhalt als einleitende "
                f"Angabe an den Anfang von Satz {b['nr']} stellen{dp}, nicht Satz {b['nr']} als Nominalgruppe in Satz {a['nr']}; kein "
                f"angehängtes „und“. {status}")
    if art == "aufbau":
        x, y = (a, b) if a["woerter"] >= b["woerter"] else (b, a)  # x = fast langer Satz, y = kurzer Nachbarsatz
        return (f"Satz {x['nr']} („{anfang(x['text'])}“, {x['woerter']} Wörter) um die Aussage aus Satz {y['nr']} („{anfang(y['text'], 4)}“) "
                f"ergänzen und Satz {y['nr']} damit auflösen – ein Satz mit etwa {neu}, höchstens ~{BUENDEL_MAX_ZIEL} Wörtern: die "
                f"Aussage als Nominal- oder Präpositionalgruppe einbauen, kein angehängtes „und“. {status}")
    if art == "beispiel":
        return (f"{zitat(a)} und Satz {b['nr']} ({a['woerter']} + {b['woerter']} Wörter) zu einem Satz mit {LANG_AB} bis höchstens "
                f"~{BUENDEL_MAX_ZIEL} Wörtern verbinden: das Beispiel aus Satz {b['nr']} mit „etwa“ oder „z. B.“ an Satz {a['nr']} "
                f"anschließen, kein angehängtes „und“. {status}")
    return (f"{zitat(a)} und Satz {b['nr']} ({a['woerter']} + {b['woerter']} Wörter) zu einem Satz mit {LANG_AB} bis höchstens "
            f"~{BUENDEL_MAX_ZIEL} Wörtern verbinden: den Inhalt von Satz {b['nr']} als Nominal- oder Präpositionalgruppe in Satz "
            f"{a['nr']} einbauen, kein angehängtes „und“. {status}")


def buendel_technik(L: Lauf, art: str) -> str | None:
    """Technik eines Bündel-Auftrags: bis Nominalstil-P75 die Nominal- bzw. Präpositionalgruppe (Ausweg Doppelpunkt oder „denn“);
    zwischen P75 und P90 nur der Doppelpunkt (solange Doppelpunkte höchstens beim Median liegen) oder ein Relativsatz – keine
    weitere Nominalgruppe, dort drohen Nominalketten (v6-Prüfung: ssoar-21977 S14+15, gestapeltes Partizipialattribut). Der
    Längenaufbau ist eine Nominalgruppe und entfällt dort. None = an dieser Stelle keine Technik."""
    ns, p75 = L.wert("nominalstil_pro_100"), L.p_("nominalstil_pro_100", "p75")
    if ns is None or p75 is None or ns <= p75:
        return "nominal"
    if art == "aufbau":
        return None
    if doppelpunkt_ok(L):
        return "doppelpunkt"
    return "relativ" if art in ("buendeln", "beispiel") else None


def _laengen_paare(L: Lauf, paare: list[tuple[dict, dict, str]], grenze: int) -> int:
    """Gierige Auswahl: je Schritt das Paar mit dem größten positiven Wert der Zielfunktion (harte Grenzen eingehalten). Jeder
    Kandidat wird zusätzlich am Verhältnis der Sätze mit zwei zu einem Teilsatz simuliert (teilsatz_ok wie beim Komma-Auftrag)."""
    n, teilsatz_weg = 0, set()
    while paare and n < grenze:
        bester = None
        for a, b, art in paare:
            ia, ib = L.fokus_index[a["nr"]], L.fokus_index[b["nr"]]
            if L.sim[ia] != [a["woerter"]] or L.sim[ib] != [b["woerter"]] or a["nr"] in L.belegt or b["nr"] in L.belegt:
                continue
            technik = buendel_technik(L, art)
            if technik is None:
                continue
            laenge = max(LANG_AB, a["woerter"] + b["woerter"] - 1) if art == "aufbau" else buendel_laenge(a["woerter"], b["woerter"])
            wert, teile = L.laengen_umbau({ia: [laenge], ib: []})
            if wert is None or wert <= 1e-6 or (bester is not None and wert <= bester[0]):
                continue
            if not teilsatz_ok(L, {"typ": "buendeln", "satz": a["nr"], "weitere_nr": [b["nr"]], "technik": technik}):
                teilsatz_weg.add((a["nr"], b["nr"]))
                continue  # das Verhältnis 2:1 läge danach über P75 und stiege (bzw. bliebe über P90)
            bester = (wert, a, b, art, laenge, teile, technik)
        if bester is None:
            break
        wert, a, b, art, laenge, teile, technik = bester
        paare = [(x, y, z) for x, y, z in paare if not {x["nr"], y["nr"]} & {a["nr"], b["nr"]}]
        viele = any(L.kz.get(k) and L.kz[k]["seite"] == "ki" and L.kz[k]["wert"] > L.kz[k]["mensch_p75"]
                    for k in ("anteil_saetze_mit_nebensatz", "teilsatz_verhaeltnis_21"))
        if not L.hinweis("buendeln", a, _paar_text(a, b, art, laenge, viele, doppelpunkt_ok(L), technik), 1.1, weitere=(b["nr"],)):
            continue
        # eingebettet: der Satz, der als Angabe bzw. Nominalgruppe im anderen aufgeht (keine Wort-Teilaufträge dort, z. B. Abkürzungen)
        eingebettet = [a["nr"]] if art == "umgedreht" or (art == "aufbau" and a["woerter"] < b["woerter"]) else [b["nr"]]
        L.hinweise[-1].update({"variante": art if art != "buendeln" else None, "laengen_alt": [a["woerter"], b["woerter"]],
                               "sim": [laenge], "sim_wert": round(wert, 3), "sim_logit": round(teile["logit"], 3),
                               "eingebettet": eingebettet, "technik": technik})
        L.uebernimm("buendeln", {L.fokus_index[a["nr"]]: [laenge], L.fokus_index[b["nr"]]: []}, wert)
        L.gebuendelt += 1
        n += 1
    if teilsatz_weg:
        L.unterdrueckt["buendeln_teilsatz"] += len(teilsatz_weg)
    return n


BUENDEL_MIN_TEIL = 8  # Bündeln: beide Sätze mindestens so lang …
BUENDEL_SUMME = (30, 46)  # … und zusammen so lang (vor dem Verdichten); der Auftrag nennt höchstens ~40 Wörter
BUENDEL_MAX = BUENDEL_SUMME[1]
BUENDEL_MAX_ZIEL = 40
MAX_BUENDELN = 4  # Bündel- und Aufbau-Aufträge je Runde (der Rest des Kontingents nach der nächsten Messung)
AUFBAU_A, AUFBAU_B = (24, 29), (4, 7)  # Längenaufbau: fast langer Satz a, kurzer Folgesatz b (zu kurz für ein Bündelpaar)
# Satz b schließt ein Beispiel an: „…, etwa …“ statt Nominalgruppe („So“ allein ist mehrdeutig und zählt nicht)
BEISPIEL_ANFANG_RE = re.compile(r"^(?:Beispielsweise|Zum\s+Beispiel|Ein\s+(?:\w+\s+)?Beispiel|Etwa|Exemplarisch|"
                                r"So\s+\w+\s+(?:etwa|beispielsweise))\b")
# Satz b trägt einen eigenen Aussagestatus (Vermutung, Befund, Ergänzung) – als Nominalgruppe in Satz a ginge er verloren
BUENDEL_B_ANFANG_RE = re.compile(r"^(?:Es\s+liegt\s+nahe|Zugleich\s+zeigt\s+sich|Hinzu\s+kommt|Dabei\s+zeigt\s+sich|Es\s+zeigt\s+sich|"
                                 r"Gleichzeitig\s+zeigt\s+sich|Es\s+ist\s+(?:davon\s+)?auszugehen|Vermutlich|Möglicherweise|"
                                 r"Wahrscheinlich|Je|Wenn|Falls|Ob|Obwohl|Während|Nachdem|Weil|Da)\b")  # auch: b beginnt mit Nebensatz
_VERMUTUNG_RE = re.compile(r"\b(?:vermutlich|möglicherweise|wahrscheinlich|dürfte[n]?|liegt\s+nahe|anzunehmen|auszuschließen|denkbar|"
                           r"vorstellbar|scheint|scheinen|offenbar|anscheinend|womöglich|eventuell)\b", re.IGNORECASE)
# Satz b zieht eine Folgerung oder verallgemeinert über das Vorige („Also …“, „Insgesamt …“, „Bei beiden Arten … ergibt sich also …“):
# als Nominalgruppe in Satz a verlöre sie ihren Geltungsbereich (v4-Kritik: ssoar-21977 S15+16, HAW S32+33)
FOLGERUNG_B_RE = re.compile(r"^(?:Also|Somit|Folglich|Daher|Damit|Insgesamt|Demnach|Deshalb|Mithin|Bei\s+(?:beiden|allen)\b)\b"
                            r"|\b(?:ergibt|ergeben|zeigt|zeigen)\s+sich\s+(?:also|somit|folglich|daher|demnach|insgesamt)\b")
FOLGERUNG_KOPF_RE = re.compile(r"\b(?:also|somit|folglich|demnach|mithin)\b", re.IGNORECASE)  # in den ersten sechs Wörtern
# Wertungsadverb in Satz b: nominalisiert ginge die Wertung verloren (ssoar-21977 S30 „leider“)
WERTUNG_ADV_RE = re.compile(r"\b(?:leider|erfreulicherweise|bedauerlicherweise|glücklicherweise|überraschenderweise|"
                            r"bemerkenswerterweise|unglücklicherweise)\b", re.IGNORECASE)
# Satz a kündigt nur an („Ein erstes Ergebnis betrifft die Automatisierung.“): dann geht a in b auf, nicht umgekehrt
ANKUENDIGUNG_A_RE = re.compile(r"\b(?:betrifft|betreffen|betraf|betrafen)\b|\bist\s+Folgendes\b|\bfolgende[nrs]?\b|:\s*$|"
                               r"\bgeht\s+es\s+(?:dabei\s+)?um\b", re.IGNORECASE)
UMKEHR_A_MAX, UMKEHR_B_MIN = 12, 20  # kurzer Satz a vor langem Satz b: a wird einleitende Angabe in b
# Satz a zieht ein Fazit: ein angehängter Inhalt aus Satz b fiele unter dessen Geltungsbereich
ZUSAMMENFASSUNG_A_RE = re.compile(r"^(?:Insgesamt|Zusammenfassend|Abschließend|Alles\s+in\s+allem|Im\s+Ergebnis|Somit|Folglich|Damit)\b")
ANKUENDIGUNG_A_MAX = 16  # Ankündigungssatz („Ein erstes Ergebnis betrifft …“): höchstens so viele Wörter


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


def nomen_bezug(L: Lauf, a: dict, b: dict) -> bool:
    """Begriffsbezug zweier Sätze über ein Nomen: gemeinsamer Inhaltsstamm, der in mindestens einem der Sätze als Nomen steht
    („automatisiert“ – „Automatisierung“, nicht „großen“ – „Große“), oder Kompositum, Akronym, Synonym bzw. Gleichsetzung."""
    ia, ib = L.begriffe_info[a["nr"]], L.begriffe_info[b["nr"]]
    art = verbunden(ia, ib)
    if art is None:
        return False
    if art == "kompositum":
        # ein gemeinsames Bestimmungswort allein („Reproduktionszeiten“ – „Reproduktionsgedanke“) ist kein Bezug: nur mit gleichem
        # bzw. verwandtem Grundwort oder wenn ein Wort das Bestimmungswort des anderen ist („Preis“ – „Preissetzung“)
        return any(min(len(x), len(y)) >= 5 and (x.endswith(y) or y.endswith(x)) or gemeinsames_grundwort(x, y)
                   for x in ia["grund"] for y in ib["grund"]) \
            or any(x != y and (x.startswith(y) or y.startswith(x)) for x in ia.get("roh", ()) for y in ib.get("roh", ())) \
            or bool((ib["akronyme"] & ia["initialen"]) or (ia["akronyme"] & ib["initialen"]) or (ia.get("syn", set()) & ib.get("syn", set()))
                    or (ia.get("alias", set()) & ib.get("alias", set())))
    if art != "stamm":
        return True
    nomen = set()
    for x in (a, b):
        toks = [t for t in analyse.tokens(x["text"].lstrip("„\"(»")) if analyse.ist_wort(t)]
        nomen |= analyse.inhaltsstaemme([t for t in toks[1:] if t[:1].isupper() and t.lower() not in analyse.FUNKTIONSWOERTER])
    wa, wb = _woerter_je_stamm(a["text"]), _woerter_je_stamm(b["text"])
    for st in ia["staemme"] & ib["staemme"] & nomen:
        if st in PARTIKEL_STAEMME:
            continue
        # der Stamm (auf acht Buchstaben gekürzt) kann nur ein gemeinsames Bestimmungswort sein („Reproduktionszeiten“ –
        # „Reproduktionsgedanke“): zählt nur, wenn die Wörter sich lediglich in der Endung unterscheiden oder das Grundwort teilen
        for x in wa.get(st, ()):
            for y in wb.get(st, ()):
                gx, gy = _grund(x), _grund(y)
                if gx.startswith(gy) or gy.startswith(gx) or gemeinsames_grundwort(gx, gy):
                    return True
    return False


def _woerter_je_stamm(text: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for t in analyse.tokens(text):
        if analyse.ist_wort(t) and t.lower() not in analyse.FUNKTIONSWOERTER:
            out.setdefault(analyse.stamm(t), set()).add(t.lower())
    return out


# Partikeln und Adverbien, die analyse.stamm (Kürzung auf 8 Buchstaben) zum „Stamm“ langer Wörter macht: „Zusammenhänge“ und
# „zusammenarbeiten“ teilen „zusammen“, aber keinen Begriff (Komposita wie „Therapiebeginn“ – „Therapieeinrichtungen“ zählen)
PARTIKEL_STAEMME = {"zusammen", "entgegen", "gegenübe", "auseinan", "miteinan", "nebenein", "unterein", "voneinan", "aufeinan",
                    "durchein", "hinterei", "zueinand", "beieinan", "füreinan", "ineinand", "nacheina"}


def buendel_paar_ok(L: Lauf, a: dict, b: dict, laenge: bool = True) -> bool:
    """Darf Satz b in Satz a aufgehen? (laenge=True: beide ≥ BUENDEL_MIN_TEIL, zusammen BUENDEL_SUMME Wörter.)"""
    return buendel_paar_grund(L, a, b, laenge) is None


def buendel_paar_grund(L: Lauf, a: dict, b: dict, laenge: bool = True) -> str | None:
    """Grund, warum Satz b nicht in Satz a aufgehen darf (None = zulässig): gleiche Quellenlage; gemeinsames Nomen (gleicher
    Stamm bzw. gleiches Grundwort) oder Anapher am Anfang von b; b trägt keinen eigenen Aussagestatus (Vermutung, „Hinzu
    kommt“, Modal- oder Redeverb in der Hauptaussage)."""
    if laenge and not (a["woerter"] >= BUENDEL_MIN_TEIL and b["woerter"] >= BUENDEL_MIN_TEIL
                       and BUENDEL_SUMME[0] <= a["woerter"] + b["woerter"] <= BUENDEL_SUMME[1]):
        return "laenge"
    if not (L.nutzbar(a) and L.nutzbar(b)) or L.langes_zitat(a) or L.langes_zitat(b):
        return "zitat"
    if ";" in L.masken[a["nr"]] or a["text"].rstrip("\"“”»)").endswith(("?", "!")):
        return "semikolon_frage"
    if ohne_verb(L.masken[a["nr"]]) or ohne_verb(L.masken[b["nr"]]):
        return "fragment"  # Satz ohne finites Verb (Aufzählungsrest wie „Die Ergebnisliste …, eine Nachrichtenseite und …“)
    if L.quelle.get(a["nr"], False) != L.quelle.get(b["nr"], False):
        return "quelle"  # sonst würde eine Aussage der fremden Quelle zugeschrieben
    anf = b["text"].lstrip("„\"(»")
    if b_eigener_status(b["text"], L.masken[b["nr"]]):
        return "b_status"  # Vermutung, Gegenüberstellung, Frage, Folgerung oder Wertung: als Nominalgruppe in Satz a ginge sie verloren
    if nominal_sperre(L, b, L.masken[b["nr"]]) == "konjunktiv":
        return "b_konjunktiv"  # Annahme/Kontrafaktum („wäre“, „hätte“, „würde“): nominalisiert wird daraus eine Tatsache
    if AUFZAEHLUNG_RE.match(anf) or _AUFZAEHL_WORT_RE.search(" ".join(b["text"].split()[:8])):
        return "aufzaehlung"  # Aufzählungsglied („Zweitens …“, „… zudem …“) bleibt ein eigener Satz; eine Erläuterung darf in ihr Glied
    liste = L.absaetze.get(b["absatz"]) or []
    j = next((i for i, x in enumerate(liste) if x["nr"] == b["nr"]), None)
    if j is not None and any(_AUFZAEHL_ZAHL_RE.search(x["text"]) for x in liste[max(0, j - 3):j]) \
            and not ANAPHER_RE.match(anf) and not RUECKVERWEIS_RE.search(" ".join(anf.split()[:6])):
        return "aufzaehlung"  # paralleles Glied einer gezählten Aufzählung („an allen drei Punkten“ – „Kurze Iterationen …“)
    haupt = re.split(r",", AUTORENLISTE_RE.sub(lambda x: x.group(0).replace(",", ""), L.masken[b["nr"]]), maxsplit=1)[0]
    if L.autor.get(b["nr"]) or AUTORENLISTE_RE.search(" ".join(anf.split()[:6])) \
            or (personen_anfang(b["text"]) and (REDEVERB_RE.search(haupt) or SPRECHAKT_RE.search(haupt))):
        return "b_rede"  # Satz b gibt eine Person oder Quelle wieder („Goretzki, Strauss und Weber zeigen …“)
    haupt_ganz = hauptsatz_teile(L.masken[b["nr"]])  # auch hinter Aufzählungskommas („…, die Erstellung … können …“)
    if any(w.lower() in analyse.MODALVERBEN for w in analyse.tokens(haupt_ganz)) or REDEVERB_RE.search(haupt) \
            or LASSEN_SICH_RE.search(haupt_ganz):
        return "b_modal_rede"  # Fähigkeit („können“, „lässt sich + Infinitiv“) bzw. Aussage einer Quelle trägt die Hauptaussage
    if modal_im_nebensatz(L.masken[b["nr"]]):
        return "b_modal_neben"  # Modalverb im Neben- bzw. Relativsatz von b: nominalisiert ginge die Möglichkeit/Pflicht verloren
    if BEGRUENDUNG_PRAEP_RE.search(L.masken[b["nr"]]) and attribute_vor_nomen(L.masken[b["nr"]]) >= 1:
        # Partizip- bzw. Adjektivattribut plus Begründung („aufgrund ihrer langwierigen und komplexen …“): in Satz a eingebaut
        # entstünde ein gestapeltes Attribut (v6-Prüfung: ssoar-21977 S14+15)
        return "b_attribut_grund"
    if re.search(r"[;:]", L.masken[b["nr"]].rstrip(".")) or _BEZUG_IM_KOPF_RE.search(" ".join(anf.split()[:4]).lower()) \
            and re.search(r"\b(?:erste|zweite|dritte|vierte|letzte|weitere)[nrs]?\b", " ".join(anf.split()[:4]).lower()):
        return "b_liste"  # Semikolon/Doppelpunkt (Liste, zweiter Hauptsatz) oder Aufzählungsglied („Das erste Modell …“)
    ha, na_, _ = analyse.teilsatz_zerlegung(a["text"])
    hb, nb_, _ = analyse.teilsatz_zerlegung(b["text"])
    # Teilsätze des Verbundsatzes: als Nominalgruppe bzw. mit Doppelpunkt t_a + t_b − 1, als Relativsatz t_a + t_b. Zwei Sätze mit
    # je einem Nebensatz ergeben so drei Teilsätze – die einzige Bündelung, die das Verhältnis 2:1 senkt (v6-Prüfung)
    t_neu = ha + na_ + hb + nb_ - (0 if buendel_technik(L, "buendeln") == "relativ" else 1)
    if hb + nb_ >= 3 or t_neu >= 4:
        return "verschachtelt"  # zusammen entstünde ein Satz mit vier und mehr Teilsätzen
    if t_neu >= 3 and not teilsatz_hoch(L):
        return "verschachtelt"  # drei Teilsätze nur, wo sie das (zu hohe) Verhältnis 2:1 senken – sonst wie bisher höchstens zwei
    if t_neu >= 3 and (re.search(r",\s*sondern\b", L.masken[a["nr"]]) or ZUSAMMENFASSUNG_A_RE.match(a["text"].lstrip("„\"(»"))):
        return "verschachtelt"  # drei Teilsätze um eine Gegenüberstellung bzw. ein Fazit („Insgesamt …“): der Bezug verschwimmt
    if KOPULA_DASS_RE.match(b["text"]) or (re.search(r"(?:^|,)\s*dass\b", L.masken[a["nr"]], re.IGNORECASE)
                                           and re.search(r"(?:^|,)\s*dass\b", L.masken[b["nr"]], re.IGNORECASE)):
        # „Entscheidend ist, dass …“ trägt eine eigene Gewichtung; zwei „dass“-Sätze ergäben „…, dass …, und dass …“
        return "b_status"
    a_haupt = re.split(r",", L.masken[a["nr"]], maxsplit=1)[0]
    if re.search(r"\b(?:sei|seien|habe|könne|müsse|werde|solle|stehe|gebe)\b", L.masken[a["nr"]] + " " + L.masken[b["nr"]]):
        return "indirekte_rede"  # indirekte Rede: der Inhalt gehört einer Quelle
    if ((REDEVERB_RE.search(a_haupt) or SPRECHAKT_RE.search(a_haupt)) and not sachliches_subjekt(a_haupt)) \
            or (re.search(r",\s*dass\b", L.masken[a["nr"]]) and any(ist_person(w) for w in analyse.tokens(a_haupt) if w[:1].isupper())):
        return "a_rede"  # Satz a gibt eine Person oder Quelle wieder: Satz b würde ihr zugeschrieben
    na, nb = nomen_staemme(a["text"]), nomen_staemme(b["text"])
    gemeinsam = bool(na & nb) or any(min(len(x), len(y)) >= 5 and (x.endswith(y) or y.endswith(x)) for x in na for y in nb) \
        or nomen_bezug(L, a, b)
    # Rückverweis am Anfang oder in den ersten Wörtern von b („Dies …“, „… wird damit …“, „bei einer solchen …“)
    anapher = bool(ANAPHER_RE.match(anf)) or bool(RUECKVERWEIS_RE.search(" ".join(L.masken[b["nr"]].lstrip("„\"(»").split()[:6])))
    return None if gemeinsam or anapher else "kein_bezug"


# Modellmerkmale, deren Selbsthilfe-Technik Bündeln ist (Bericht: „so geht es selbst“) – nur mit Spielraum (buendel_raum)
LAENGEN_SELBST = {"anteil_mittlere_saetze", "satzlaenge_dispersion", "anteil_sehr_lange_saetze"}


def buendel_raum(L: Lauf) -> int | None:
    """Wie viele lange Sätze der Nutzer über die Aufträge hinaus noch selbst bilden darf (0 = keine): nur im Modus „bündeln“,
    Bündeln nicht ausgesetzt, höchstens der Rest des Kontingents (bis zum menschlichen Median) und nur so viele beliebige
    Nachbarpaare ohne Auftrag (gleicher Absatz, je ≥ BUENDEL_MIN_TEIL, zusammen BUENDEL_SUMME Wörter, unverdichtet), wie
    nacheinander auf dem simulierten Stand nach allen Aufträgen die harten Grenzen einhalten und die Zielfunktion heben. Sonst
    widerspräche „so geht es selbst“ dem Satzlängen-Hinweis bzw. den Grenzen gegen Überkorrektur. None = keine
    Längen-Simulation (unbekannt, keine Sperre)."""
    if getattr(L, "_buendel_raum", None) is not None:
        return L._buendel_raum
    if not getattr(L, "diag", None) or not hasattr(L, "sim"):
        return None
    diag, raum = L.diag, 0
    rest = (diag.get("kontingent") or 0) - L.gebuendelt
    if diag.get("modus") != "buendeln" or "buendeln" in L.ausgesetzt or rest <= 0:
        L._buendel_raum = 0
        return 0
    # gierig auf einer Kopie des Simulationsstands: je Schritt irgendein freies Paar, ohne Verdichtung (Nutzer bündeln selten so
    # knapp wie simuliert; höchstens BUENDEL_MAX_ZIEL Wörter), das die harten Grenzen einhält und die Zielfunktion hebt
    sim_alt, frei, proben = L.sim, set(), []
    try:
        while raum < rest:
            gefunden = None
            for liste in L.absaetze.values():
                for a, b in zip(liste, liste[1:]):
                    ia, ib = L.fokus_index[a["nr"]], L.fokus_index[b["nr"]]
                    wa, wb = a["woerter"], b["woerter"]
                    if {a["nr"], b["nr"]} & (L.belegt | frei) or L.sim[ia] != [wa] or L.sim[ib] != [wb] \
                            or not (wa >= BUENDEL_MIN_TEIL and wb >= BUENDEL_MIN_TEIL and BUENDEL_SUMME[0] <= wa + wb <= BUENDEL_SUMME[1]) \
                            or not buendel_laengen_ok(L, wa, wb):
                        continue
                    ersatz = {ia: [min(wa + wb, BUENDEL_MAX_ZIEL)], ib: []}
                    wert, _ = L.laengen_umbau(ersatz)
                    probe = {"typ": "buendeln", "satz": a["nr"], "weitere_nr": [b["nr"]], "technik": buendel_technik(L, "buendeln")}
                    if wert is not None and wert > 1e-6 and probe["technik"] and teilsatz_ok(L, probe):
                        gefunden = (a["nr"], b["nr"], ersatz, probe)
                        break
                if gefunden:
                    break
            if not gefunden:
                break
            frei |= {gefunden[0], gefunden[1]}
            L.sim = mit_ersetzung(L.sim, gefunden[2])
            L.hinweise.append(gefunden[3])  # vorübergehend: die nächste Teilsatz-Simulation rechnet dieses Paar mit
            proben.append(gefunden[3])
            raum += 1
    finally:
        L.sim = sim_alt
        L.hinweise[:] = [h for h in L.hinweise if not any(h is p_ for p_ in proben)]
    L._buendel_raum = raum
    return raum


def _bremse(L: Lauf) -> None:
    """Teilen-Aufträge nur mit Beleg, dass der Text über das menschliche Band hinaus geraten ist – Überkorrektur im Verlauf,
    Wert über P90 oder fehlende Mitte. Lange Sätze zwischen P75 und P90 sind auch bei Menschen häufig (≈ 15 %) und ziehen im
    Modell eher Richtung menschlich; dort nur kein weiteres Bündeln."""
    diag = L.diag
    laengen = [s["woerter"] for s in L.fokus]
    lang_ids = {"satzlaenge_mittel", "satzlaenge_median", "anteil_lange_saetze", "anteil_sehr_lange_saetze", "anteil_mittlere_saetze"}
    # Überkorrektur nur, wenn der Verlauf zeigt, dass befolgte Coach-Aufträge (Bündeln, Angabe holen, Zickzack) die Satzlängen über
    # das menschliche Band getrieben haben – dann wie bisher Teilen-Aufträge
    verlaengert = any(isinstance(h, dict) and h.get("typ") and set(h.get("typen") or [h["typ"]]) & {"buendeln", "klammer_zusatz", "zickzack"}
                      and _befolgt(L, h) for mess in L.messungen for h in mess.get("hinweise") or [])
    # alter Verlauf (v1) ohne gespeicherte Aufträge: die Überkorrektur im Verlauf gilt wie bisher als Folge der Coach-Aufträge
    verlaengert = verlaengert or (bool(L.messungen) and not any("hinweise" in mess for mess in L.messungen))
    diag["ueberkorrektur"] = verlaengert and any(u["id"] in lang_ids and u["art"] == "Überkorrektur" for u in L.ueberkorrektur)
    diag["ueber_p90"] = bool(laengen) and (diag["anteil_lange"] > (L.p_("anteil_lange_saetze", "p90") or 1)
                                           or diag["mittel"] > (L.p_("satzlaenge_mittel", "p90") or 99))
    min_teilen = LANG_AB
    if diag["modus"] == "teilen" and not diag["ueberkorrektur"]:
        # ohne Verlauf-Beleg kein Teilen-Auftrag: Satzlängen jenseits des menschlichen Bands auf der der KI abgewandten Seite sind
        # auf echten Texten Eigenart (Info „Menschlicher als typisch“, kein Auftrag); zwischen P75 und P90 ohnehin unauffällig
        diag["kontingent"] = 0
        min_teilen = SEHR_LANG_AB
    if diag["modus"] != "teilen" or diag["kontingent"] <= 0 or "teilen" in L.ausgesetzt:
        return
    kandidaten = sorted((s for s in L.fokus if s["woerter"] >= min_teilen and L.nutzbar(s)), key=lambda s: -s["woerter"])
    lange40 = [s for s in kandidaten if s["woerter"] >= SEHR_LANG_AB]
    kandidaten = lange40 + [s for s in kandidaten if s["woerter"] < SEHR_LANG_AB] if lange40 else kandidaten
    geteilt, ziel_lange = 0, round(L.p_("anteil_lange_saetze", "p50") * len(laengen))
    for s in kandidaten:
        if geteilt >= diag["kontingent"]:
            break
        stelle = teilstelle(s["text"], L.masken[s["nr"]])
        if stelle is None and L.langes_zitat(s):
            continue  # keine Trennstelle außerhalb des wörtlichen Zitats: „an einer inhaltlichen Wende“ würde das Zitat zerteilen
        nl, nr_ = (stelle[1], stelle[2] + FUGE_ZUSATZ.get(stelle[4], 0)) if stelle else (s["woerter"] // 2, s["woerter"] - s["woerter"] // 2)
        i = L.fokus_index[s["nr"]]
        if L.sim[i] != [s["woerter"]]:
            continue
        noch_zu_viele = sum(x >= LANG_AB for x in laengen_folge(L.sim)) > ziel_lange
        wert, _ = L.laengen_umbau({i: [nl, nr_]})
        if wert is None or not (wert > 1e-6 or noch_zu_viele):
            continue  # harte Grenze (z. B. Rhythmus würde rot) oder kein Gewinn, obwohl lange Sätze nicht mehr zu viele sind
        wo = (f" – an der Stelle „{stelle[3]}“ (nach Wort {nl}); {fugen_technik(stelle[4])}" if stelle else
              " – an einer inhaltlichen Wende; der zweite Satz nennt sein Subjekt als Nomen, kein Pronomen")
        if nominal_sperre(L, s, L.masken[s["nr"]]):
            wo += "; Konjunktiv bzw. Annahme in beiden Sätzen beibehalten"
        if L.hinweis("teilen", s, f"{zitat(s)} ({s['woerter']} Wörter) in zwei Sätze teilen{wo}.", 1.2):
            L.hinweise[-1].update({"laengen_alt": [s["woerter"]], "sim": [nl, nr_], "sim_wert": round(wert, 3)})
            L.uebernimm("teilen", {i: [nl, nr_]}, wert)
            geteilt += 1


def _mitte(L: Lauf, kontingent: int) -> None:
    """„Mitte ausdünnen“: konkrete Sätze mit 22–26 Wörtern an einer inhaltlichen Fuge in zwei Sätze mit je ≤ 13 Wörtern
    teilen; jeder Kandidat wird an der Zielfunktion des Längenmodells simuliert (Kontingent bis zum Median)."""
    diag = L.diag
    if kontingent <= 0 or "mitte" in L.ausgesetzt:
        return
    kand = []
    for s in L.fokus:
        if not (MITTE_SATZ_VON <= s["woerter"] <= MITTE_SATZ_BIS) or not L.nutzbar(s) or L.langes_zitat(s) or s["nr"] in L.belegt:
            continue
        if L.quelle.get(s["nr"]) or L.autor.get(s["nr"]):
            continue  # Quellenzuordnung: die Angabe müsste in beiden Teilen erkennbar bleiben
        if nominal_sperre(L, s, L.masken[s["nr"]]):
            continue  # Konjunktiv/Kontrafaktum: geteilt verliert der zweite Satz den Bezug auf die Annahme
        st = teilstelle(s["text"], L.masken[s["nr"]], MITTE_TEIL_MAX, MITTE_TEIL_RE)
        if st:
            kand.append((s, st))
    n_m = 0
    while kand and n_m < kontingent:
        bester = None
        for s, st in kand:
            i = L.fokus_index[s["nr"]]
            if L.sim[i] != [s["woerter"]]:
                continue
            teile_ = [st[1], st[2] + FUGE_ZUSATZ.get(st[4], 0)]
            wert, _ = L.laengen_umbau({i: teile_})
            if wert is not None and wert > 1e-6 and (bester is None or wert > bester[0]):
                bester = (wert, s, st, teile_)
        if bester is None:
            break
        wert, s, st, teile_ = bester
        kand = [(x, y) for x, y in kand if x is not s]
        if not L.hinweis("mitte", s, f"{zitat(s)} ({s['woerter']} Wörter) in zwei Sätze mit je höchstens {MITTE_TEIL_MAX} Wörtern teilen – "
                         f"an der Stelle „{st[3]}“ (nach Wort {st[1]}); {fugen_technik(st[4])}.", 1.1):
            continue
        L.hinweise[-1].update({"laengen_alt": [s["woerter"]], "sim": teile_, "sim_wert": round(wert, 3)})
        L.uebernimm("mitte", {L.fokus_index[s["nr"]]: teile_}, wert)
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


# Funktionswörter, die ein Adverbialsatz → Präpositionalgruppe entfernt bzw. hinzufügt (Netto-Simulation: Funktionswort-Profil, MATTR)
KLAMMER_FW = {"um": ({"um": 1, "zu": 1}, {"zur": 1}), "ohne": ({"zu": 1}, {}), "indem": ({"indem": 1}, {"durch": 1}),
              "weil": ({"weil": 1}, {"wegen": 1}), "da": ({"da": 1}, {"wegen": 1}), "wenn": ({"wenn": 1}, {"bei": 1}),
              "nachdem": ({"nachdem": 1}, {"nach": 1}), "bevor": ({"bevor": 1}, {"vor": 1}), "sobald": ({"sobald": 1}, {"mit": 1})}
KLAMMER_LEER_MAX = 3  # Satzklammer gilt bis zu so vielen Wörtern zwischen Hilfsverb und Partizip als (fast) leer
KLAMMER_MAX = 4  # Klammer-Aufträge je Runde
VORFELD_MIN, VORFELD_MAX = 3, 9  # Angabe im Vorfeld, die ins Mittelfeld wandern kann („Bereits vor der Digitalisierung …“)


def vorfeld_angabe(mk: str) -> tuple[str, int, int, str, str, bool] | None:
    """(Angabe, Wörter der Angabe, Zuwachs, Hilfsverb, Klammerende, Klammer leer?), wenn ein Hauptsatz mit einer Angabe beginnt (Präposition
    bzw. Zeitadverb, kein Nebensatz), danach das finite Hilfsverb steht und die Satzklammer fast leer ist („In der Literatur
    wurde dies früh beschrieben.“). Die Angabe zwischen Hilfsverb und Partizip, das Subjekt nach vorn: die Klammer wächst um
    mindestens Angabe − alte Spanne Wörter (das Subjekt stand vorher in der Klammer), der Inhalt bleibt gleich."""
    erster = re.split(r"[,;:()–—]", mk, maxsplit=1)[0]
    tw = [t for t in analyse.tokens(erster) if analyse.ist_wort(t)]
    aux = next((i for i, t in enumerate(tw) if t.lower() in HILFSVERBEN), None)
    if aux is None or not VORFELD_MIN <= aux <= VORFELD_MAX or tw[0].lower() not in ANGABE_ANFANG:
        return None
    if re.match(r"\s*,\s*(?:(?:in|an|auf|mit|bei|für|von|zu|aus|nach|über|unter|durch)\s+)?(?:der|die|das|dem|den|deren|dessen|denen|"
                r"welche[rsmn]?)\s", mk[len(erster):]):
        return None  # Relativsatz hinter dem Partizip gehört zum Subjekt: nach vorn geholt, verlöre er seinen Bezug
    if re.match(r"\s*,\s*(?:wie|ob|was|warum|wo|wann|dass|inwiefern|inwieweit|welche[rsmn]?)\b", mk[len(erster):], re.IGNORECASE):
        return None  # Attribut- bzw. Subjektsatz („…, wie auf die Hypothesen geschlossen wurde“): mit nach vorn geholt, schwerfällig
    praep = analyse.PRAEPOSITIONEN | {"im", "am", "beim", "vom", "zum", "zur", "ins"}
    if tw[0].lower() not in praep and tw[1].lower() not in praep:
        return None  # „Bereits Hackman und Oldham haben …“: Gradpartikel vor dem Subjekt, keine Angabe
    if any(t.lower() in analyse.SUBJUNKTIONEN or t.lower() in analyse.RELATIVPRONOMEN and i > 0 and tw[i - 1] in (",",)
           for i, t in enumerate(tw[:aux])):
        return None  # Nebensatz im Vorfeld
    d = klammer_details(erster)
    if not d or d[0][1] != tw[aux]:
        return None
    spanne, hv, ende = d[0]
    pronomen_subjekt = aux + 1 < len(tw) and tw[aux + 1].lower() in {"es", "sie", "er", "dies", "das", "man", "diese", "dieser", "dieses"} \
        and aux + 2 < len(tw) and not tw[aux + 2][:1].isupper()  # „wurde dies …“, nicht „wurde diese Entwicklung …“
    if pronomen_subjekt and aux >= 3:
        # Subjekt ist ein Wort: die Klammer wächst um Angabe − 1, auch wenn sie schon gefüllt ist
        return " ".join(tw[:aux]), aux, aux - 1, hv, ende, spanne <= KLAMMER_LEER_MAX
    if spanne > KLAMMER_LEER_MAX or aux < spanne + 2:
        return None  # die Klammer würde kaum wachsen (oder schrumpfen, wenn das Subjekt länger ist als die Angabe)
    return " ".join(tw[:aux]), aux, aux - spanne, hv, ende, True


def klammer_simulation(L: Lauf) -> dict | None:
    """Satzklammer-Spannen im Fokus wie analyse.py (satzklammer_mittel = Mittel aller Spannen, ab 5 Klammern) und die Summe an
    zusätzlichen Wörtern, die bis zum menschlichen Median fehlt (Kontingent)."""
    spannen = [x for s in L.fokus for x in analyse.satzklammern(s["text"])]
    p50 = L.p_("satzklammer_mittel", "p50")
    if len(spannen) < 5 or p50 is None:
        return None
    mu = sum(spannen) / len(spannen)
    return {"n": len(spannen), "summe": float(sum(spannen)), "mittel": mu, "noetig": max(0.0, (p50 - mu) * len(spannen)), "gewinn": 0.0}


def klammer_logit(L: Lauf, sim: dict, plus: float) -> float:
    """Δ-Logit des Modellmerkmals satzklammer_mittel, wenn die Spannen zusammen um plus Wörter wachsen."""
    modell = L.ts.get("modell") or {}
    k = "satzklammer_mittel"
    if k not in (modell.get("koeffizienten") or {}):
        return 0.0
    z = lambda v: modell_z(L.ts, k, v)  # noqa: E731
    alt = (sim["summe"] + sim["gewinn"]) / sim["n"]
    return modell["koeffizienten"][k] * (z(alt + plus / sim["n"]) - z(alt))


# „um … zu“ als Präpositionalgruppe („zur Verbesserung …“) nur mit gebräuchlicher -ung-Form: Verben mit üblichem Verbalnomen auf -ung
# (dazu alle auf -ieren → -ierung) – nicht bei Dativverben bzw. Dativobjekt („um dem Anspruch zu entsprechen“)
UM_ZU_UNG = set("""verbessern sichern sicherstellen erhöhen steigern senken unterstützen fördern vermeiden erreichen gewährleisten
überprüfen prüfen bewerten messen erfassen ermitteln beschreiben darstellen klären lösen umsetzen entwickeln gestalten planen steuern
beantworten vorbereiten stärken begrenzen herstellen erstellen einführen ergänzen erweitern vertiefen verringern gewinnen erhalten
bewältigen beurteilen untersuchen erklären begründen verdeutlichen veranschaulichen überwinden ordnen einordnen bündeln vereinfachen
beschleunigen verkürzen entlasten absichern festigen erleichtern auswerten befragen abgrenzen eingrenzen herleiten
ableiten verknüpfen vernetzen bestimmen festlegen abbilden aufbereiten bereitstellen versorgen erzeugen anpassen sammeln beobachten
dokumentieren vermitteln""".split()) - {"ermöglichen"}
DATIV_VERBEN = {"entsprechen", "helfen", "dienen", "folgen", "begegnen", "widersprechen", "zustimmen", "schaden", "nützen",
                "gerecht", "genügen", "vertrauen", "gehorchen", "zuvorkommen", "ausweichen", "entgegenwirken", "vorbeugen", "zuhören"}
_DATIV_RE = re.compile(r"\b(?:dem|einem|diesem|jedem|keinem|ihm|ihnen|ihrem|seinem|unserem)\b", re.IGNORECASE)


def um_zu_nominalisierbar(rest: str) -> bool:
    """Lässt sich der „um … zu“-Teil (Text nach „um“) als Präpositionalgruppe mit gebräuchlicher -ung-Form fassen?"""
    teil = re.split(r"[,;:.]", rest, maxsplit=1)[0]
    w = [x for x in analyse.tokens(teil) if analyse.ist_wort(x)]
    if not w:
        return False
    verb = None
    for i, x in enumerate(w):
        low = x.lower()
        if low == "zu" and i + 1 < len(w):
            verb = w[i + 1].lower()
        elif re.fullmatch(r"[a-zäöüß]{2,}zu[a-zäöüß]{3,}en", low) and not low.startswith(("zu", "dazu", "hinzu")):
            verb = re.sub(r"^([a-zäöüß]+?)zu([a-zäöüß]+en)$", r"\1\2", low)  # „sicherzustellen“ → „sicherstellen“
    if not verb or verb in DATIV_VERBEN or _DATIV_RE.search(teil):
        return False
    return verb in UM_ZU_UNG or verb.endswith("ieren")


def _satzklammer(L: Lauf) -> None:
    """Satzklammer füllen, simuliert am Mittel der Klammerspannen (Kontingent bis zum menschlichen Median, höchstens
    KLAMMER_MAX je Runde). Techniken, je Satz die mit dem größten Zuwachs: Angabe aus dem Vorfeld ins Mittelfeld (Subjekt
    nach vorn), kurzen Adverbialsatz als Präpositionalgruppe in die Klammer, Angabe vom Anfang des Folgesatzes holen."""
    def aktiv(k: str) -> bool:  # rot/gelb auf der KI-Seite oder deutlicher Modellbeitrag (inhaltsneutrale Umstellung)
        return L.ki_auffaellig(k) or L.modell_hebel(k)
    if not (aktiv("satzklammer_mittel") or aktiv("nominalketten_pro_100")):
        return
    sim = L.klammer_sim = klammer_simulation(L)
    kand = []  # (Zuwachs, Satz, Typ, Text, weitere)
    for i, s in enumerate(L.fokus):
        if s["woerter"] < 8 or not L.nutzbar(s) or s["nr"] in L.belegt or L.langes_zitat(s):
            continue
        mk = L.masken[s["nr"]]
        vf = vorfeld_angabe(mk)
        if vf:
            angabe, n_vf, zuwachs, hv, ende, leer_ = vf
            kopf = f"Zwischen „{hv}“ und „{ende}“ steht fast nichts. " if leer_ else ""
            kand.append((zuwachs, s, "klammer", f"{zitat(s)}: {kopf}Die Angabe „{angabe}“ vom Satzanfang zwischen „{hv}“ und „{ende}“ "
                         "stellen und das Subjekt an den Satzanfang holen – nur umstellen, der Inhalt bleibt gleich.", (), {}))
            continue
        if s["woerter"] <= 12 or REDEVERB_DASS_RE.search(mk) or re.search(r",\s+(?:dass|ob)\b", mk):
            continue  # Objektsatz: folgende Nebensätze gehören zu ihm, nicht ins Mittelfeld des Hauptsatzes
        leer = [d for d in klammer_details(mk) if d[0] <= KLAMMER_LEER_MAX]
        if not leer:
            continue
        _, aux, ende = leer[0]
        q = KLAMMER_QUELLE_RE.search(mk)
        n_q = len([w for w in analyse.tokens(mk[q.end():]) if analyse.ist_wort(w)]) if q else 0
        if q and (re.search(r"[,;]", mk[q.end():]) or n_q > 10 or nominal_sperre(L, s, mk, mk[q.start():].lstrip(", "))):
            q = None  # langer, verschachtelter oder koordinierter Nebensatz bzw. Konjunktiv: als Angabe entstünde ein Satzungetüm
        if q:
            # der Nebensatz gehört zum Teilsatz direkt davor: nur dessen Klammer (nicht ein vorangestellter „Sind … erfüllt“-Satz,
            # ein Relativsatz oder ein Satzteil vor einem Doppelpunkt); Korrelat („darauf hinweisen, wenn …“) = Inhaltssatz;
            # Modalverb im Nebensatz („…, da sie sprechen sollten“) ginge als Präpositionalgruppe verloren
            vor = re.split(r"[,;:()–—]", mk[:q.start()])[-1]
            dq = [d for d in klammer_details(vor) if d[0] <= KLAMMER_LEER_MAX]
            vw = [w for w in analyse.tokens(vor) if analyse.ist_wort(w)]
            # Korrelat direkt vor dem Klammerende („… darauf hinweisen, wenn …“): der Nebensatz ist dessen Inhalt – Präposition
            # aus dem Korrelat („auf“), das Korrelat entfällt; steht ein „da(r)…“-Wort anderswo, ist es mehrdeutig: kein Auftrag
            korrelat = vw[-2] if len(vw) >= 2 and dq and vw[-1] == dq[0][2] and KORRELAT_RE.fullmatch(vw[-2]) else None
            if not dq or (KORRELAT_RE.search(vor) and not korrelat) \
                    or any(w.lower() in analyse.MODALVERBEN for w in analyse.tokens(mk[q.end():])):
                q = None
            else:
                _, aux, ende = dq[0]
        if q and q.group("w") == "um" and "um" in L.schutz:
            L.unterdrueckt["klammer_um"] += 1
            q = None  # „um … zu“ → Präpositionalgruppe entfernt „um“ und „zu“, die hier ohnehin seltener sind als bei Menschen
        if q and q.group("w") == "um" and not um_zu_nominalisierbar(mk[q.end():]):
            L.unterdrueckt["klammer_um_ung"] += 1
            q = None  # keine gebräuchliche -ung-Form bzw. Dativobjekt: „um den Platz zu entsprechen“ → „zur Entsprechung des Platzes“
        nachbar = L.fokus[i + 1] if i + 1 < len(L.fokus) and L.fokus[i + 1]["absatz"] == s["absatz"] else None
        if q:
            teil = {"um": "„um … zu“-Teil", "ohne": "„ohne … zu“-Teil"}.get(q.group("w"), f"„{q.group('w')}“-Satz")
            praep = KLAMMER_PRAEP.get(q.group("w"), "passender Präposition")
            if korrelat:
                p_ = re.sub(r"^dar?", "", korrelat.lower())
                praep = f"„{p_}“ – „{korrelat}“ entfällt, der Inhalt bleibt"
            kand.append((max(1, n_q - 2), s, "klammer", f"{zitat(s)}: Zwischen „{aux}“ und „{ende}“ steht fast nichts. Den {teil} als "
                         f"Angabe (Präpositionalgruppe mit {praep}) zwischen „{aux}“ und „{ende}“ holen.", (),
                         {"fw_weg": dict(KLAMMER_FW.get(q.group("w"), ({q.group("w"): 1}, {}))[0]),
                          "fw_dazu": dict(KLAMMER_FW.get(q.group("w"), ({}, {}))[1]), "subjunktion": q.group("w")}))
        elif nachbar and L.diag.get("modus") != "teilen" and L.nutzbar(nachbar) and nachbar["woerter"] <= 14 \
                and not L.beginnt_im_zitat(nachbar) and (analyse.tokens(nachbar["text"]) or [""])[0].lower() in ANGABE_ANFANG \
                and verbunden(L.begriffe_info[s["nr"]], L.begriffe_info[nachbar["nr"]]) \
                and L.quelle.get(s["nr"], False) == L.quelle.get(nachbar["nr"], False):
            kand.append((3, s, "klammer_zusatz", f"{zitat(s)}: Zwischen „{aux}“ und „{ende}“ steht fast nichts. Die Angabe vom Anfang von "
                         f"Satz {nachbar['nr']} („{anfang(nachbar['text'], 3)}“) dorthin holen und Satz {nachbar['nr']} damit auflösen.",
                         (nachbar["nr"],), {}))
    n_kl = 0
    for zuwachs, s, typ, text_, weitere, extra in sorted(kand, key=lambda k: (-k[0], k[1]["nr"])):
        if n_kl >= KLAMMER_MAX or (sim and sim["gewinn"] >= sim["noetig"] and n_kl > 0):
            break  # Kontingent: bis zum menschlichen Median (mindestens ein Auftrag, wenn das Merkmal aktiv ist)
        if L.hinweis(typ, s, text_, 0.8, weitere=weitere):
            d_logit = klammer_logit(L, sim, zuwachs) if sim else 0.0
            L.hinweise[-1].update({"klammer_zuwachs": zuwachs, "sim_logit": round(d_logit, 3), **extra})
            L.sim_gewinn[typ] = L.sim_gewinn.get(typ, 0.0) + d_logit
            if sim:
                sim["gewinn"] += zuwachs
            n_kl += 1


def _ist_partizip2(w: str) -> bool:
    return bool(analyse.PARTIZIP_T.fullmatch(w) or analyse.PARTIZIP_GE_EN.fullmatch(w) or analyse.PARTIZIP_EN_ABLAUT.fullmatch(w)) \
        and not _ADJ_ENDE.search(w) and w.lower() not in analyse.KEIN_PARTIZIP


def relativsatz_umbaubar(vorne: str, teil: str) -> tuple[bool, bool]:
    """(umbaubar, Passiv) für einen Relativsatz „…, die erhoben wurden“: höchstens RELATIV_MAX Wörter und ein vorangestelltes
    Attribut mit höchstens ATTRIBUT_MAX Wörtern, Bezugswort ein
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
    if len(worte) - 1 - (1 if letzt in analyse.WERDEN_FORMEN or letzt in _AUX_SEIN else 0) > ATTRIBUT_MAX:
        return False, passiv  # das vorangestellte Attribut würde zu lang („die in der zweiten Welle der Befragung erhobenen Daten“)
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


def nominal_kette(teil: str) -> int:
    """Geschätzte Länge der Nomenkette, die beim Nominalisieren des Nebensatzes entsteht: Verbalnomen + jedes Nomen des
    Nebensatzes mit Begleiter oder ohne Präposition davor (wird Genitivattribut); Nomen nach einer Präposition bleiben eine
    eigene Angabe („im zweiten Jahr“), ein handelndes Subjekt wandert in „durch …“."""
    toks = [t for t in analyse.tokens(teil) if analyse.ist_wort(t)]
    n, in_angabe = 0, False
    for i, t in enumerate(toks[1:], 1):
        if not t[:1].isupper() or t.lower() in analyse.FUNKTIONSWOERTER:
            continue
        vor = ""
        for j in range(i - 1, max(-1, i - 4), -1):
            if toks[j][:1].islower() and toks[j].lower() not in analyse.FUNKTIONSWOERTER:
                continue  # Adjektiv oder Partizip zwischen Begleiter und Nomen („der zweiten Welle“)
            vor = toks[j].lower()
            break
        if vor in analyse.PRAEPOSITIONEN or vor in ("im", "am", "zum", "zur", "beim", "vom", "ins", "aufs"):
            in_angabe = True  # Präpositionalgruppe: eigene Angabe, keine Kette
            continue
        if in_angabe and vor in ("des", "der", "eines", "einer"):
            continue  # Genitiv innerhalb der Präpositionalgruppe („im zweiten Jahr der Einführung“)
        in_angabe = False
        n += 1
    return 1 + n - (1 if handelndes_subjekt(teil) else 0)


BEGRUENDUNG_PRAEP_RE = re.compile(r"\b(?:aufgrund|wegen|infolge|angesichts)\b", re.IGNORECASE)
# Möglichkeit bzw. Schwierigkeit im Nebensatz: „…, da sich die Datenmengen manuell kaum bewältigen lassen“ – als Präpositionalgruppe
# entstünde ein gestapeltes Attribut („wegen der manuell kaum zu bewältigenden Datenmengen“, v6-Prüfung: Controlling S42)
SICH_LASSEN_RE = re.compile(r"\bsich\b[^,;]*\b(?:lässt|lassen|ließ|ließen)\b|\b(?:lässt|lassen|ließ|ließen)\s+sich\b", re.IGNORECASE)
SCHWER_RE = re.compile(r"\b(?:kaum|nur\s+schwer|schwerlich|nur\s+bedingt|nur\s+mit\s+Mühe)\b", re.IGNORECASE)
_KEIN_ATTRIBUT = {"einen", "einem", "einer", "eines", "keinen", "keinem", "keiner", "keines", "diesen", "diesem", "dieser", "dieses",
                  "jeden", "jedem", "jeder", "jedes", "allen", "alle", "aller", "vielen", "viele", "vieler", "einigen", "einige",
                  "mehreren", "mehrere", "wenigen", "wenige", "beiden", "beide", "solchen", "solche", "manchen", "manche", "ihren",
                  "ihrem", "ihrer", "ihres", "seinen", "seinem", "seiner", "seines", "unseren", "unserem", "unserer", "deren",
                  "dessen", "welche", "welchen", "welcher", "sowie", "sich", "werden", "worden", "haben", "sein"}
_ATTRIBUT_RE = re.compile(r"[a-zäöüß][\wäöüß-]{2,}(?:e|en|em|er|es)$")


def attribute_vor_nomen(text: str) -> int:
    """Größte Zahl vorangestellter Adjektiv- bzw. Partizipattribute vor einem Nomen („ihrer langwierigen und komplexen
    Reproduktionszeiten“ = 2, „die geforderten Datenmengen“ = 1); „und“, „oder“ und Kommas zwischen den Attributen zählen nicht."""
    toks = re.findall(r"[A-Za-zÄÖÜäöüß][\wÄÖÜäöüß-]*|,", text)
    best = 0
    for i, t in enumerate(toks):
        if i == 0 or not t[:1].isupper() or t.lower() in analyse.FUNKTIONSWOERTER:
            continue
        n, j = 0, i - 1
        while j >= 0:
            w = toks[j]
            low = w.lower()
            if w in (",",) or low in ("und", "oder"):
                if n == 0:
                    break
                j -= 1
                continue
            if w[:1].islower() and low not in analyse.FUNKTIONSWOERTER and low not in _KEIN_ATTRIBUT and _ATTRIBUT_RE.search(w):
                n += 1
                j -= 1
                continue
            break
        best = max(best, n)
    return best


def nominal_sperre(L: Lauf, s: dict, mk: str, teil: str | None = None) -> str | None:
    """Grund, warum ein Satz (bzw. sein Nebensatz teil) nicht nominalisiert werden darf: Konjunktiv/Kontrafaktum im ganzen
    Satz („hätte“, „wäre“, „würde“), Koordination im Nebensatz („und nicht“, „sowohl“, Aufzählung), Möglichkeit bzw. Schwierigkeit
    im Nebensatz („lassen sich“, Modalverb, „kaum“, „nur schwer“), Nomenkette ≥ 3 (Genitive) bzw. projiziertes Ergebnis mit
    Kopfnomen und Genitiv-/Präpositionalkette ≥ PROJ_KETTE_MAX, oder ab zwei Attributen vor dem Kopfnomen (gestapeltes Attribut)."""
    if any(w.lower() in _KONJUNKTIV for w in analyse.tokens(mk)):
        return "konjunktiv"  # Annahme bzw. Kontrafaktum: nominalisiert kippt oder verschwimmt die Bedeutung
    if teil is not None:
        if KOORDINATION_RE.search(teil) or len(re.findall(r"\b(?:und|oder)\b", teil)) >= 2 or koordinierte_teilsaetze(teil):
            return "koordination"
        if SICH_LASSEN_RE.search(teil) or SCHWER_RE.search(teil) \
                or any(w.lower() in analyse.MODALVERBEN for w in analyse.tokens(teil)):
            return "modal"
        if nominal_kette(teil) > KETTE_MAX or projizierte_kette(teil) >= PROJ_KETTE_MAX:
            return "kette"
        if attribute_vor_nomen(teil) + (1 if kopula_praedikativ(teil) else 0) >= 2:
            return "attribute"
    return None


PROJ_KETTE_MAX = 4  # Kopfnomen + Genitiv-/Präpositionalkette im nominalisierten Ergebnis: ab so vielen Nomen sperren
KOPULA_SEIN = {"ist", "sind", "war", "waren", "sei", "seien", "wäre", "wären"}
KOPULA_ANDERE = {"bleibt", "bleiben", "blieb", "blieben", "wird", "werden", "wurde", "wurden", "erscheint", "erscheinen", "scheint",
                 "scheinen"}


def kopula_praedikativ(teil: str) -> bool:
    """Endet der Nebensatz auf Kopula + prädikatives Adjektiv bzw. Partizip I („dass mehr Autonomie … motivierend ist“, „da die
    Daten knapp sind“)? Nominalisiert braucht er ein neues Kopfnomen („die … motivierende Wirkung von …“) – die Kette wird länger
    als geprüft (v4: Agile S23). Partizip II mit „werden“/„sein“ (Passiv, Perfekt) zählt nicht."""
    w = [t for t in analyse.tokens(teil) if analyse.ist_wort(t)]
    if len(w) < 3 or w[-1].lower() not in KOPULA_SEIN | KOPULA_ANDERE:
        return False
    prae = w[-2]
    low = prae.lower()
    if not prae[:1].islower() or low in analyse.FUNKTIONSWOERTER or low in HILFSVERBEN:
        return False
    if re.search(r"end(?:e[nmrs]?)?$", low):
        return True  # Partizip I
    return not _ist_partizip2(low)


def projizierte_kette(teil: str) -> int:
    """Nomen im nominalisierten Ergebnis eines Nebensatzes: das neue Kopfnomen (Verbalnomen; bei Kopula + Adjektiv ein weiteres)
    plus jedes Nomen des Nebensatzes – Genitivattribute, handelnde Subjekte („durch …“) und Präpositionalgruppen hängen dann alle
    am Kopf („die Wirkung von mehr Autonomie auf alle Mitarbeiter“)."""
    toks = [t for t in analyse.tokens(teil) if analyse.ist_wort(t)]
    nomen = sum(1 for t in toks[1:] if t[:1].isupper() and t.lower() not in analyse.FUNKTIONSWOERTER)
    return 1 + nomen + (1 if kopula_praedikativ(teil) else 0)


def koordinierte_teilsaetze(teil: str) -> bool:
    """Verbindet ein „und“/„oder“ im Nebensatz zwei Teilsätze („dass es täglich Neuigkeiten gibt und man mit vielen in Kontakt
    steht“)? Links steht dann ein Teilsatz mit Subjekt (Nomen oder Pronomen), der auf ein Verb endet, rechts ein Verb.
    Nominalisiert entstünden zwei Nominalgruppen mit eigenen Handelnden; „die Kosten und die Preise steigen“ bleibt erlaubt."""
    teile = re.split(r"\s+(?:und|oder)\s+", re.sub(r"\([^()]*\)", " ", teil))
    if len(teile) < 2:
        return False
    links = [w for w in analyse.tokens(teile[0]) if analyse.ist_wort(w)][1:]  # ohne die Subjunktion
    if len(links) < 2:
        return False
    letzt = links[-1]
    low = letzt.lower()
    verb = low in analyse.FINIT or low in analyse.FINIT_MEHRDEUTIG or (
        letzt.islower() and low not in analyse.FUNKTIONSWOERTER and len(low) >= 4 and bool(re.search(r"(?:t|ten|en|st|ern|eln)$", low)))
    subjekt = any(w[:1].isupper() or w.lower() in _PRONOMEN_SUBJ for w in links[:-1])
    return verb and subjekt and analyse._hat_verbkandidat(teile[-1])


def nominal_gesperrt(L: Lauf, s: dict) -> bool:
    """Kein Nominalisierungsauftrag (Nebensatz, Komma → Nominalgruppe, kurzer „dass“-Satz), wenn derselbe Bericht „Wortwahl
    einfacher“ als Hebel führt und der Satz schon eine Kette aus ≥ 3 Nomen in Folge hat (Genitiv-/von-Kette wie analyse.py) –
    sonst widerspräche der Auftrag dem Hebel."""
    if "wortwahl" not in L.hebel:
        return False
    if s["nr"] not in L.kette_max:
        L.kette_max[s["nr"]] = max(analyse.nominalketten([s["text"]]) or [0])
    return L.kette_max[s["nr"]] >= 3


def relativsatz_praep(vorne: str, teil: str) -> bool:
    """Passiv-Relativsatz mit eigener Angabe (Präpositionalgruppe), höchstens RELATIV_PRAEP_MAX Wörter, Bezugswort ein
    Gattungsnomen ohne Personenbezug, kein Modalverb: „die Daten, die in der Befragung erhoben wurden“ → „die Daten aus der
    Befragung“."""
    worte = [w for w in analyse.tokens(teil) if analyse.ist_wort(w)]
    low = [w.lower() for w in worte]
    if not 3 <= len(worte) <= RELATIV_PRAEP_MAX or any(w in analyse.MODALVERBEN for w in low) or re.search(r"[)\d]\s*$", vorne):
        return False
    m = BEZUG_GATTUNG_RE.search(vorne)
    if not m or ist_person(m.group("n").lower()) or ist_genderform(m.group("n")):
        return False
    if low[-1] not in analyse.WERDEN_FORMEN and low[-1] not in ("worden",):
        return False
    kern = [w for w in worte[1:-1] if w.lower() not in analyse.WERDEN_FORMEN]
    return bool(kern) and _ist_partizip2(kern[-1]) and any(w in analyse.PRAEPOSITIONEN for w in low[1:-2])


def nebensatz_auftrag(L: Lauf, s: dict, mk: str) -> tuple[int, str, int] | None:
    """(Rang, Auftragstext, Passiv-Kosten) für einen Satz mit genau einem Nebensatz, oder None. Ankündigungen („lässt sich
    festhalten, dass“) sind ein eigener Auftrag (Ankündigung streichen) und kein Nominalisierungsfall. Passiv-Kosten = 1, wenn
    der Umbau dem Satz sein einziges Passiv nimmt (der Passiv-Schutz rechnet mit dem Wert nach den Aufträgen)."""
    if nominal_sperre(L, s, mk) or nominal_gesperrt(L, s):
        return None
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
        passiv_weg = 0
        if werden and analyse.ist_passiv(s["text"]) and not analyse.ist_passiv(s["text"].replace(teil, " ")):
            passiv_weg = 1  # das einzige Passiv des Satzes steht im Nebensatz
        if name == "relativ":
            ok, passiv = relativsatz_umbaubar(mk[:t.start()], teil)
            praep = not ok and relativsatz_praep(mk[:t.start()], teil)
            if not (ok or praep):
                return None
            if KOORDINATION_RE.search(teil):
                return None
            if SICH_LASSEN_RE.search(teil) or SCHWER_RE.search(teil):
                return None  # „die sich kaum bewältigen lassen“: als Partizip „die kaum zu bewältigenden …“ (gestapelt)
            kopf = BEZUG_GATTUNG_RE.search(mk[:t.start()])
            if ok and not praep and kopf and attribute_vor_nomen(kopf.group(0)) >= 1:
                return None  # das Bezugsnomen hat schon ein Attribut: mit dem Partizip stünden zwei davor (gestapelt)
            if (passiv or praep) and passiv_weg and ("nebensatz_relativ" in L.ausgesetzt or (L.passiv_budget is not None and L.passiv_budget <= 0)):
                L.unterdrueckt["nebensatz_relativ"] += 1
                return None  # wenig Passiv im Text: den Passiv-Relativsatz nicht wegformulieren
            if praep or passiv:
                # Passiv-Relativsatz: als Präpositionalgruppe am Nomen statt als vorangestelltes Partizip (keine Attributkette)
                technik = ("den Relativsatz als Präpositionalgruppe am Nomen fassen, wenn die Angabe darin das Wesentliche trägt (Beispiel: "
                           "„die Daten, die in der Befragung erhoben wurden“ → „die Daten aus der Befragung“); sonst als vorangestelltes "
                           "Partizip (Beispiel: „die Daten, die erhoben wurden“ → „die erhobenen Daten“)") if praep or n_teil > 3 else technik
        else:
            grenze = NEBENSATZ_MAX_DASS if name == "dass" else NEBENSATZ_MAX
            if n_teil - 1 > grenze or any(w.lower() in analyse.MODALVERBEN | _KONJUNKTIV for w in analyse.tokens(teil)):
                return None  # Modalverb oder Konjunktiv: Möglichkeit bzw. Annahme ginge in der Nominalgruppe verloren
            vorne = mk[:t.start()]
            if name == "dass" and re.search(r"\b(?:so|derart|dermaßen|solcherart)\s+(?:[\w-]+\s+){0,3}?[\w-]+\s*$", vorne):
                return None  # „so gewählt, dass …“: Folge- bzw. Zwecksatz, kein Inhaltssatz
            if name == "dass" and wiedergegebene_rede(L, s, vorne):
                return None  # Paraphrase einer Person oder Quelle bleibt als dass-Satz stehen
            if name == "dass" and kopula_praedikativ(teil):
                return None  # „dass X motivierend ist“: nominalisiert entstünde ein neues Kopfnomen samt Nominalkette
            if name != "dass" and (SPRECHAKT_RE.search(vorne) or REDEVERB_RE.search(vorne)) and wiedergegebene_rede(L, s, vorne):
                return None  # „Yara verneint die Frage, da sie …“: wiedergegebene Begründung einer Person
            if name == "dass" and KOPULA_DASS_RE.match(vorne):
                # „Entscheidend ist, dass …“: keine Nominalisierung; nur wenn Doppelpunkte nicht schon häufig sind, die Ankündigung
                # mit Doppelpunkt („Entscheidend ist: …“), der Inhalt des dass-Satzes wird Hauptsatz
                dp, dp50 = L.wert("doppelpunkt_pro_1000"), L.p_("doppelpunkt_pro_1000", "p50")
                if dp is None or dp50 is None or dp > dp50:
                    return None
                kopf = vorne.strip(" ,„\"(»")
                return rang, (f"„{kopf}, dass …“ als Ankündigung mit Doppelpunkt schreiben („{kopf}: …“), der Inhalt des „dass“-Satzes "
                              "wird Hauptsatz – keine Nominalgruppe; Aussagestatus erhalten: eine Forderung bleibt eine Forderung "
                              "(„Unternehmen müssen …“), keine Tatsachenbehauptung."), 0
            sperre = nominal_sperre(L, s, mk, teil)
            if sperre:
                return None
        if werden and "nebensatz_werden" in L.ausgesetzt:
            L.unterdrueckt["nebensatz_werden"] += 1
            return None  # „werden“ ist schon seltener als bei Menschen: den Nebensatz mit „werden“ nicht wegformulieren
        if name != "relativ" and passiv_weg and L.passiv_budget is not None and L.passiv_budget <= 0:
            L.unterdrueckt["nebensatz_passiv"] += 1
            return None  # Passiv läge nach dem Umbau unter P25
        if name == "sonst":
            w = t.group("w").lower()
            bsp, art = NEBENSATZ_BEISPIEL[w]
            technik, status = technik.format(w=w, bsp=bsp), status.format(art=art)
        text_ = technik[0].upper() + technik[1:]
        if name != "relativ" and handelndes_subjekt(teil):
            text_ += "; Handelnde behalten (Akteur als Genitiv oder mit „durch“)"
        if status:
            text_ += f"; {status}"
        return rang, text_ + ".", passiv_weg
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
            kandidaten.append((auftrag[0], s["nr"], s, auftrag[1], auftrag[2]))
    n_ns = 0
    for _, _, s, text_, passiv_weg in sorted(kandidaten, key=lambda x: (x[0], x[1])):
        if n_ns >= k:
            break
        if passiv_weg and L.passiv_budget is not None and L.passiv_budget <= 0:
            L.unterdrueckt["nebensatz_passiv"] += 1
            continue  # das Passiv-Budget ist durch frühere Aufträge dieser Runde aufgebraucht
        if L.hinweis("nebensatz", s, f"{zitat(s)}: {text_}", 0.8):
            n_ns += 1
            if passiv_weg and L.passiv_budget is not None:
                L.passiv_budget -= 1
    _kommas(L)


def _teilsaetze(s: dict) -> int:
    return max(1, s.get("teilsaetze") or sum(analyse.teilsatz_zerlegung(s["text"])[:2]))


def teilsatz_folge(L: Lauf) -> list[int]:
    """Teilsätze je Satz im Fokus nach den Aufträgen dieser Runde (Simulation): Bündeln fasst Satz b als Nominalgruppe
    (t_a + t_b − 1), Teilen/Mitte trennt an einer Teilsatzgrenze (t → t − 1 und 1), Nebensatz bzw. Komma → Nominalgruppe nimmt
    einen Teilsatz (t → t − 1), Herauslösen macht aus einem Einschub einen eigenen Satz (t → t − 1 und 1)."""
    t = {s["nr"]: [_teilsaetze(s)] for s in L.fokus}
    for h in L.hinweise:
        n = h.get("satz")
        if n not in t or not t[n]:
            continue
        x = t[n][0]
        if h["typ"] == "buendeln" and h.get("weitere_nr"):
            b = h["weitere_nr"][0]
            if b in t and t[b]:
                # Nominalgruppe bzw. Doppelpunkt: t_a + t_b − 1 (der Doppelpunkt trennt in analyse.py keinen Teilsatz ab);
                # Relativsatz: Satz b bleibt ein eigener Teilsatz (t_a + t_b)
                t[n], t[b] = [max(1, x + t[b][0] - (0 if h.get("technik") == "relativ" else 1))], []
        elif h["typ"] in ("teilen", "mitte") or (h["typ"] == "kommas" and h.get("variante") == "herausloesen"):
            t[n] = [max(1, x - 1), 1]
        elif h["typ"] in ("nebensatz", "kommas", "fw_dass"):
            t[n] = [max(1, x - 1)]
        elif h["typ"] == "fw_ankuendigung" and (h.get("fw_weg") or {}).get("dass"):
            t[n] = [max(1, x - 1)]  # Ankündigung gestrichen bzw. „folgt daraus: …“: der „dass“-Satz wird Hauptsatz
    return [x for v in t.values() for x in v]


NUR_NEBENSATZ_PAARE = (" – nur zwei Sätze, die beide schon einen Nebensatz haben (sonst steigt das Verhältnis der Sätze mit zwei zu "
                       "einem Teilsatz weiter)")


def teilsatz_hoch(L) -> bool:
    """Liegt das Verhältnis der Sätze mit zwei zu einem Teilsatz (nach den Aufträgen dieser Runde) über P75? Dann senkt nur eine
    Bündelung zweier Sätze mit je einem Nebensatz es – Selbsthilfe „bündeln“ nur mit diesem Zusatz."""
    p75 = L.p_("teilsatz_verhaeltnis_21", "p75") if hasattr(L, "p_") else None
    if p75 is None or not hasattr(L, "fokus"):
        return False
    return verhaeltnis_21(teilsatz_folge(L)) > p75


def teilsatz_ok(L: Lauf, probe: dict) -> bool:
    """Darf ein Auftrag das Verhältnis der Sätze mit zwei zu einem Teilsatz so verschieben? Simuliert auf dem Stand nach den
    Aufträgen dieser Runde (teilsatz_folge): verworfen, wenn das Verhältnis danach über P75 liegt und steigt, oder über P90 liegt
    und nicht sinkt. Eine Bündelung zweier Sätze mit Nebensatz senkt es (zwei Sätze mit zwei Teilsätzen werden einer mit drei) und
    bleibt erlaubt (v6-Prüfung, Agile S39+40: 1,05 → 1,11, über P90)."""
    p75, p90 = L.p_("teilsatz_verhaeltnis_21", "p75"), L.p_("teilsatz_verhaeltnis_21", "p90")
    if p75 is None:
        return True
    vor = verhaeltnis_21(teilsatz_folge(L))
    L.hinweise.append(probe)
    try:
        nach = verhaeltnis_21(teilsatz_folge(L))
    finally:
        L.hinweise.pop()
    if nach > vor + 1e-9:
        return nach <= p75
    if nach >= vor - 1e-9:
        return p90 is None or nach <= p90
    return True


def verhaeltnis_21(folge: list[int]) -> float:
    """teilsatz_verhaeltnis_21 wie analyse.py: (Sätze mit 2 Teilsätzen + 0,5) / (Sätze mit 1 Teilsatz + 0,5)."""
    c = Counter(folge)
    return (c[2] + 0.5) / (c[1] + 0.5)


def teilsatz_wirkung(t: int, variante: str | None = None) -> int:
    """Richtung, in die ein Verdichtungsauftrag an einem Satz mit t Teilsätzen das Verhältnis 2:1 verschiebt (+1 steigt, −1 sinkt):
    aus 3 Teilsätzen werden 2 (steigt), aus 2 wird 1 (sinkt); Herauslösen erzeugt zusätzlich einen Satz mit einem Teilsatz."""
    if t == 3:
        return 1
    if t == 2 or (variante == "herausloesen" and t >= 4):
        return -1
    return 0


def _kommas(L: Lauf) -> None:
    """Viele kurze Teilsätze (≥ 3 Kommas, < 10 Wörter je Teilsatz). Herauslösen nur, wenn Teilen nicht ausgesetzt ist und lange
    Sätze nicht fehlen (anteil_lange ≥ P50) – simuliert wie „Mitte ausdünnen“; sonst Nominalgruppe (mit den Schutzregeln des
    Nebensatz-Auftrags) oder, wenn das Verdichten ausgesetzt ist, gar kein Komma-Auftrag. Jeder Komma-Auftrag nur, wenn der Satz
    danach einen einzigen Teilsatz hat oder das simulierte Verhältnis der Sätze mit zwei zu einem Teilsatz höchstens bei P75 bleibt
    (v4: Controlling 1,00 → 1,15, weil aus Sätzen mit drei Teilsätzen solche mit zwei wurden)."""
    p75_21 = L.p_("teilsatz_verhaeltnis_21", "p75")

    def teilsatz_ok(s: dict, herausloesen: bool) -> bool:
        if _teilsaetze(s) - 1 <= 1:
            return True  # danach nur noch Sätze mit einem Teilsatz
        if p75_21 is None:
            return True
        probe = {"typ": "kommas", "satz": s["nr"], "variante": "herausloesen" if herausloesen else "nominal"}
        L.hinweise.append(probe)
        try:
            return verhaeltnis_21(teilsatz_folge(L)) <= p75_21
        finally:
            L.hinweise.remove(probe)

    verdichten_aus = "nebensatz" in L.ausgesetzt or "kommas" in L.ausgesetzt or bool(L.jenseits)
    lang50 = L.p_("anteil_lange_saetze", "p50")
    folge = laengen_folge(L.sim)
    # gemessener UND simulierter Stand (nach den Bündelungen dieser Runde): wer das Bündeln überspringt, bekommt kein Herauslösen
    lange_jetzt = min(L.diag.get("anteil_lange", 0.0), sum(x >= LANG_AB for x in folge) / (len(folge) or 1))
    herausloesen_ok = "teilen" not in L.ausgesetzt and "kommas" not in L.ausgesetzt and lang50 is not None and lange_jetzt >= lang50
    n_ko = 0
    for s in L.fokus:
        if n_ko >= 3:
            break
        mk = analyse._ohne_zahlzeichen(L.masken[s["nr"]]) if hasattr(analyse, "_ohne_zahlzeichen") else L.masken[s["nr"]]
        mk = AUTORENLISTE_RE.sub(lambda x: x.group(0).replace(",", ""), mk)  # „Kahneman, Knetsch und Thaler“
        teile = max(1, s.get("teilsaetze", 1))
        if mk.count(",") < 3 or s["woerter"] / teile >= 10 or not L.nutzbar(s) or s["nr"] in L.belegt:
            continue
        if nominal_sperre(L, s, mk) or (re.search(r",\s*(?:dass|ob)\b", mk) and wiedergegebene_rede(L, s, mk.split(",")[0])):
            continue  # Konjunktiv/Kontrafaktum oder wiedergegebene Rede: weder herauslösen noch nominalisieren (DP S8, haw-7747 S36)
        if herausloesen_ok and s["woerter"] < LANG_AB:
            i = L.fokus_index[s["nr"]]
            st = teilstelle(s["text"], L.masken[s["nr"]], None, MITTE_TEIL_RE)
            teile_ = [st[1], st[2] + FUGE_ZUSATZ.get(st[4], 0)] if st else [s["woerter"] // 2, s["woerter"] - s["woerter"] // 2 + 1]
            if L.sim[i] != [s["woerter"]]:
                continue
            wert, _ = L.laengen_umbau({i: teile_})
            if wert is None or wert < 0:
                continue  # das Herauslösen würde die Satzlängen verschlechtern bzw. eine harte Grenze verletzen
            if not teilsatz_ok(s, True):
                L.unterdrueckt["kommas_teilsatz"] += 1
                continue  # das Verhältnis der Sätze mit zwei zu einem Teilsatz läge danach über P75
            tat = ("Einen Einschub als eigenen Satz herauslösen; der neue Satz beginnt mit dem Bezugsnomen (kein „sie“, „er“, „dies“).")
            if L.hinweis("kommas", s, f"{zitat(s)}: {mk.count(',')} Kommas bei kurzen Teilsätzen. {tat}", 0.7):
                L.hinweise[-1].update({"variante": "herausloesen", "laengen_alt": [s["woerter"]], "sim": teile_, "sim_wert": round(wert, 3)})
                L.uebernimm("kommas", {i: teile_}, wert)
                n_ko += 1
            continue
        if verdichten_aus:
            continue  # kein Herauslösen erlaubt und Verdichten ausgesetzt: kein Komma-Auftrag
        if nominal_sperre(L, s, mk) or (re.search(r",\s*(?:dass|ob)\b", mk) and wiedergegebene_rede(L, s, mk.split(",")[0])) \
                or KOORDINATION_RE.search(mk) or (re.search(r",\s*dass\b", mk) and KOPULA_DASS_RE.match(mk.split(",")[0])) \
                or nominal_gesperrt(L, s) or ANKUENDIGUNG_RE.search(mk):
            # … oder Ankündigung vor „dass“: die baut der Funktionswort-Auftrag um (zwei Umbauten desselben „dass“-Satzes
            # widersprächen sich)
            continue  # Konjunktiv/Kontrafaktum, wiedergegebene Rede, Koordination oder „Entscheidend ist, dass“: nicht nominalisieren
        neben = _haupt_neben(mk)[1]
        if SICH_LASSEN_RE.search(neben) or SCHWER_RE.search(neben) or modal_im_nebensatz(mk):
            continue  # Möglichkeit bzw. Schwierigkeit im Nebensatz: als Nominalgruppe entstünde ein gestapeltes Attribut
        if not teilsatz_ok(s, False):
            L.unterdrueckt["kommas_teilsatz"] += 1
            continue  # aus drei Teilsätzen würden zwei: das Verhältnis 2:1 läge danach über P75
        tat = "Einen Nebensatz oder Einschub zur Nominalgruppe machen (Länge bleibt, Kommas sinken); keine Kette aus drei und mehr Nomen."
        if L.hinweis("kommas", s, f"{zitat(s)}: {mk.count(',')} Kommas bei kurzen Teilsätzen. {tat}", 0.7):
            L.hinweise[-1]["variante"] = "nominal"
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


def vorfeld(text: str) -> list[str] | None:
    """Wörter vor dem finiten Verb (Vorfeld eines Hauptsatzes), höchstens sieben; None, wenn kein Verb erkennbar ist."""
    toks = [t for t in analyse.tokens(text.lstrip("„\"(»")) if analyse.ist_wort(t)]
    for i in range(1, min(8, len(toks))):
        low = toks[i].lower()
        if low in analyse.FINIT or low in analyse.FINIT_MEHRDEUTIG:
            return toks[:i]
        if toks[i].islower() and low not in analyse.FUNKTIONSWOERTER and len(low) >= 4 and re.search(r"(?:t|te|ten|en|st)$", low) \
                and toks[i - 1].lower() not in _KEIN_VERB_DAVOR and not (i + 1 < len(toks) and toks[i + 1][:1].isupper()):
            return toks[:i]
    return None


def bezug_am_satzanfang(L: Lauf, a: dict, kand: list[str]) -> bool:
    """Ist der Bezug eines Pronomens bzw. Possessivs in Satz b das Subjekt am Anfang von Satz a? Das Vorfeld von a ist eine
    Nominalgruppe (Artikel bzw. Nomen, keine Präposition) und enthält einen der Kandidaten – oder es gibt keinen Kandidaten außer ihr.
    Die Ersetzung wiederholte dann nur den Satzanfang von a."""
    vf = vorfeld(L.masken.get(a["nr"], a["text"]))
    if not vf:
        return False
    erstes = vf[0].lower()
    if erstes in analyse.PRAEPOSITIONEN | {"im", "am", "zum", "zur", "beim", "vom", "ins"}:
        return False  # Angabe im Vorfeld („Zum Schluss der Studie geht …“): das Subjekt steht nicht vorn
    nomen = {w.lower() for w in vf[1:] if w[:1].isupper()}
    if erstes not in _AKTEUR_DET | {"der", "die", "das"}:
        if erstes in analyse.FUNKTIONSWOERTER or erstes in _ADVERB_ANFANG or len(vf) > 3:
            return False  # „Dabei …“, „So …“: kein Subjekt am Satzanfang
        nomen.add(erstes)  # Name bzw. Nomen ohne Artikel („Hypothesen stammen …“, „Stiehler sieht …“)
    if not nomen:
        return False
    if not kand:
        return True
    return any(w.lower() in nomen for k in kand for w in k.split() if w[:1].isupper())


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
            if b["nr"] in L.neu_geteilt:
                # Satz entstand erst durch einen befolgten Teilen-/Herauslöse-Auftrag: nur die Folge des Teilens benennen; nach der
                # Gegenfolie als zwei Hauptsätze gar nicht (der Auftrag selbst verlangte schon den Neuanfang ohne Pronomen)
                if art == "dem" or L.neu_geteilt[b["nr"]] == "gegenfolie":
                    continue
                wort = mt.group("pron") or mt.group("poss")
                _, kand = bezug_vorschlag(L, a, b, art, wort)
                if L.hinweis("anknuepfung", b, f"{zitat(b)}: Folge des Teilens – am Satzanfang das Bezugsnomen statt „{wort}“ nennen "
                             f"({_bezug_text(kand, a)}).", 1.0):
                    L.hinweise[-1]["art"] = "folge_teilen"
                    n += 1
                continue
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
            if art in ("pron", "poss") and bezug_am_satzanfang(L, a, kand):
                # der Bezug ist das Subjekt am Anfang des Vorsatzes: das Pronomen ist eindeutig, die Ersetzung wiederholte nur den
                # Satzanfang (v6-Prüfung, haw S3/S4: „Die Hypothesen … Die Hypothesen …“, Score 80 → 78)
                L.unterdrueckt["anknuepfung_subjekt_vorn"] += 1
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
                kopf = (kand[0].split()[-1] if kand else "")
                L.hinweise[-1].update({"art": art, "bezug": kopf,
                                       "fw_weg": {wort.lower(): 1} if art != "dem" else {},
                                       "fw_dazu": ({"die": 1} if art == "pron" else {"die": 1, "der": 1}) if art != "dem" else {}})
                n += 1
    return n


_AUFZAEHL_ANKUENDIGUNG_RE = re.compile(r"\b(?:zwei|drei|vier|fünf|sechs|mehrere[n]?|folgende[n]?|verschiedene[n]?)\s+(?:[a-zäöüß][\w-]*\s+)?"
                                       r"[A-ZÄÖÜ]|:\s*$")
_AUFZAEHL_WORT_RE = re.compile(r"\b(?:erstens|zweitens|drittens|viertens|schließlich|zudem|außerdem|ebenso|ebenfalls|ferner|weiterhin|"
                               r"zum einen|zum anderen|darüber hinaus|hinzu kommt|an (?:erster|zweiter|dritter) Stelle|zunächst|"
                               r"zuerst|als (?:erstes|zweites|nächstes))\b", re.IGNORECASE)
# gezählte Aufzählung („an allen drei Punkten“, „zwei Hypothesen“, „folgende Gründe“, Doppelpunkt am Satzende)
_AUFZAEHL_ZAHL_RE = re.compile(r"\b(?:zwei|drei|vier|fünf|sechs|folgende[n]?)\s+(?:[a-zäöüß][\w-]*\s+)?[A-ZÄÖÜ]|:\s*$")
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


def satz_nomen(L: Lauf, s: dict) -> list[str]:
    """Nomen eines Satzes außerhalb wörtlicher Zitate (großgeschrieben, ≥ 4 Buchstaben, kein Funktionswort, kein Akronym, keine
    Gender-Form, kein leichtes Nomen; am Satzanfang nur, wenn das Wort wahrscheinlich ein Nomen ist)."""
    toks = [t for t in analyse.tokens(L.masken.get(s["nr"], s["text"]).lstrip("„\"(»")) if analyse.ist_wort(t)]
    out = []
    for i, t in enumerate(toks):
        low = t.lower()
        if not t[:1].isupper() or len(t) < 4 or low in analyse.FUNKTIONSWOERTER or low in analyse.STARTWOERTER \
                or low in LEICHTE_NOMEN or ist_genderform(t) or re.fullmatch(r"[A-ZÄÖÜ]{2,}s?", t):
            continue
        if i == 0 and (kein_nomen_am_anfang(t) or partizip_vorfeld(s["text"], t)):
            continue
        out.append(t)
    return out


def _gemeinsam_vorne(x: str, y: str) -> int:
    n = 0
    while n < min(len(x), len(y)) and x[n] == y[n]:
        n += 1
    return n


def begriffs_relation(x: str, y: str, vokabular: set[str]) -> tuple[str, int] | None:
    """Mögliche Bezeichnung derselben Sache durch zwei verschiedene Nomen: gleiche Synonymgruppe („Kunden“ – „Konsumenten“),
    gleiches Grundwort („Systemlandschaft“ – „IT-Landschaft“, „Bericht“ – „Nachhaltigkeitsbericht“) oder gleiches
    Bestimmungswort mit ≥ 5 Zeichen nur zusammen mit synonymem Grundwort („Preissetzung“ – „Preisgestaltung“, nicht
    „Datenqualität“ – „Datenbasis“). Ein Bestimmungswort zählt nur, wenn es kein Verbpräfix ist.
    (Art, Länge des gemeinsamen Teils) oder None."""
    rx, ry = x.lower().replace("-", ""), y.lower().replace("-", "")
    if analyse.stamm(x) == analyse.stamm(y) or rx == ry:
        return None
    # Synonymgruppe nur über das Wort selbst bzw. sein Grundwort: ein Synonym als bloßes Bestimmungswort („Studien“ – „Studiengänge“)
    # bezeichnet etwas anderes (v5-Prüfung hm-103 S3/S4: „Studiengänge“ als Ergänzung zu „Studien“ angeboten)
    sx, sy = _synonym_kopf(x), _synonym_kopf(y)
    if sx & sy:
        return "synonym", 99
    gx, gy = _grund(rx), _grund(ry)
    n = 0
    while n < min(len(gx), len(gy)) and gx[-1 - n] == gy[-1 - n]:
        n += 1
    if n >= 5 and ((min(len(gx), len(gy)) >= 5 and (gx.endswith(gy) or gy.endswith(gx))) or gemeinsames_grundwort(gx, gy)):
        return "grundwort", n
    p = _gemeinsam_vorne(rx, ry)
    # gleiches Bestimmungswort: beide Wörter sind Komposita (nach Bestimmungswort und Fugenelement bleiben je ≥ 4 Zeichen) –
    # das bloße Bestimmungswort („Führung“ neben „Führungskonzept“) bezeichnet etwas anderes
    for n_ in range(p, 4, -1):
        pre = rx[:n_]
        if pre in _PARTIKEL_PRAEFIX:
            continue
        rest_x, rest_y = rx[n_:], ry[n_:]
        if len(re.sub(r"^(?:es|en|s|n)(?=[a-zäöüß]{4})", "", rest_x)) < 4 or len(re.sub(r"^(?:es|en|s|n)(?=[a-zäöüß]{4})", "", rest_y)) < 4:
            continue
        # das Bestimmungswort steht als eigenes Wort im Text, ist lang genug, oder die Grundwörter sind Synonyme
        # („Preissetzung“ – „Preisgestaltung“; Fugen-s wahlweise abgetrennt)

        def kopf_in(rest: str, gruppe: dict) -> bool:
            varianten = {rest, re.sub(r"^(?:es|en|s|n)", "", rest)}
            return any(v.startswith(g) for v in varianten for f in gruppe.values() for g in f)
        # nur mit synonymem Grundwort: das gemeinsame Bestimmungswort allein bezeichnet nicht dieselbe Sache – die Bedeutung trägt
        # das Grundwort (v4: „Datenqualität“ → „Datenbasis“ hätte einen Fachbegriff geändert)
        koepfe = any(kopf_in(rest_x, gr) and kopf_in(rest_y, gr) for gr, _nur_kopf in SYNONYM_GRUPPEN)
        if koepfe:
            return "bestimmungswort", n_
    return None


def begriffs_paar(L: Lauf, a: dict, b: dict) -> tuple[str, str, str] | None:
    """(Nomen in b, Nomen in a, Art) für die Begriffsaufnahme: das Paar mit der stärksten Beziehung (Synonym vor gemeinsamem
    Wortteil, längerer Teil vor kürzerem); None = kein Kandidat (Themenwechsel – dann schweigt der Coach)."""
    vokabular = {w.lower().replace("-", "") for s in L.fokus for w in satz_nomen(L, s)}
    vokabular |= {_grund(w) for w in vokabular}
    beste = None
    for y in satz_nomen(L, b):
        for x in satz_nomen(L, a):
            rel = begriffs_relation(x, y, vokabular)
            if rel and (beste is None or rel[1] > beste[0]):
                beste = (rel[1], y, x, rel[0])
    return (beste[1], beste[2], beste[3]) if beste else None


def _kein_bezug(L: Lauf, k: int) -> None:
    """Begriffsaufnahme: Satz ohne Wortaufnahme aus dem Vorsatz, in dem aber ein Nomen dieselbe Sache bezeichnen könnte wie
    ein Nomen des Vorsatzes (Synonymgruppe, gleiches Grund- oder Bestimmungswort) – dann nennt der Auftrag beide. Ohne
    solches Paar schweigt der Coach (Themenwechsel). Nicht bei Aufzählungsgliedern, Rückverweisen („dies“, „solche“
    irgendwo im Satz), neuen Quellen und Sätzen, die mit einem Fachbegriff beginnen; nach einer Nennung nie wieder."""
    if "kein_bezug" in L.ausgesetzt or k <= 0:
        return
    hinweis_nrn = {h["satz"] for h in L.hinweise if h["typ"] == "anknuepfung"}
    # nach einer Nennung endgültig gestrichen – außer der Text wurde nur erneut gemessen: dann bleiben die Stellen der letzten
    # Runde offen, früher gestrichene kommen aber nicht wieder
    genannt = [{a for (t, a) in schl if t == "kein_bezug" and a} for _, schl in L.frueher]
    if genannt and text_unveraendert(L):
        schon = set().union(*genannt[:-1]) - genannt[-1]
    else:
        schon = set().union(*genannt)
    kand = []
    for liste in L.absaetze.values():
        for j in range(1, len(liste)):
            a, b = liste[j - 1], liste[j]
            if not (L.nutzbar(a) and L.nutzbar(b)) or b["nr"] in hinweis_nrn or b["nr"] in L.gebuendelte_b or b["woerter"] < 8 \
                    or b["nr"] in L.neu_geteilt or schluessel_anfang(b["text"]) in schon:
                continue  # … Satz, der erst durch einen befolgten Teilen-Auftrag entstand, oder schon einmal genannt (endgültig)
            ia, ib = L.begriffe_info[a["nr"]], L.begriffe_info[b["nr"]]
            if not (ia["staemme"] and ib["staemme"]) or (ia["staemme"] & ib["staemme"]) \
                    or verbunden(ia, ib) in ("akronym", "gleichsetzung"):
                continue  # schon Wortaufnahme bzw. Bezug über Akronym oder Gleichsetzung „A (B)“
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
            paar = begriffs_paar(L, a, b)
            if not paar:
                continue  # kein Nomen, das dieselbe Sache bezeichnen könnte: Themenwechsel, kein Auftrag
            if paar[0] in L.leitbegriffe or any(paar[0] in lb.split() for lb in L.leitbegriffe):
                continue  # Teil eines mehrfach verwendeten Fachbegriffs: nicht ersetzen lassen
            frei = not any(h["satz"] == b["nr"] for h in L.hinweise)
            kand.append((0 if paar[2] == "synonym" else 1, 0 if frei else 1, b["nr"], b, a, paar))
    n = 0
    for _, _, _, b, a, (y, x, art) in sorted(kand, key=lambda x: (x[0], x[1], x[2])):
        if n >= k:
            break
        if wiederkehrend(L, y, b["nr"]):
            # „y“ steht im Text mehrfach: ein Fachbegriff wird nie zum Ersetzen vorgeschlagen – stattdessen die Wiederaufnahme anbieten
            t_ = (f"{zitat(b)}: nimmt kein Wort aus Satz {a['nr']} wieder auf. „{y}“ kommt im Text mehrfach vor und bleibt; wo es passt, "
                  f"„{x}“ aus Satz {a['nr']} in Satz {b['nr']} wieder aufnehmen (etwa als Ergänzung zu „{y}“), sonst stehen lassen "
                  "(Themenwechsel).")
            ok = L.hinweis("kein_bezug", b, t_, 0.6)
            art_auftrag = "wiederaufnahme"
        else:
            ok = L.hinweis("kein_bezug", b, f"{zitat(b)}: nimmt kein Wort aus Satz {a['nr']} wieder auf – „{y}“ → „{x}“? Nur wenn dieselbe "
                           f"Sache gemeint ist, das Wort aus Satz {a['nr']} übernehmen; sonst stehen lassen (Themenwechsel).", 0.6, fund=y)
            art_auftrag = "ersetzen"
        if ok:
            L.hinweise[-1].update({"paar": [y, x], "paar_art": art, "art": art_auftrag})
            n += 1


def wiederkehrend(L: Lauf, wort: str, ausser: int) -> bool:
    """Steht das Nomen (gleiche Grundform) noch in einem anderen Satz des Textes? Dann ist es ein wiederkehrender Fachbegriff."""
    g = _grund(wort.lower().replace("-", ""))
    for s in L.saetze:
        if s["nr"] == ausser:
            continue
        if any(t[:1].isupper() and _grund(t.lower().replace("-", "")) == g for t in analyse.tokens(L.masken.get(s["nr"], s["text"]))):
            return True
    return False


RECHT_RE = re.compile(r"\b(?:Richtlinie|Verordnung|DSGVO|Gesetz\w*|\w+gesetz\w*|Directive|Regulation)\b|§")


def synonym_varianten(L: Lauf, c: dict) -> list[tuple[str, int]]:
    """Varianten eines Synonym-Clusters ohne geschützte Einzelformen: eine Form, die genau einmal vorkommt und dort
    Rechtsbegriff (Richtlinie, Verordnung, §, Gesetz) oder in „A (B)“ gleichgesetzt ist, fällt heraus; die übrigen Formen
    zählen weiter („Kunden“ 8× / „Konsumenten“ 3× bleibt ein Fund, auch wenn „Verbraucher“ 1× im Satz mit der Richtlinie steht)."""
    geschuetzt = set()
    for w, k in c["varianten"][1:]:
        if k != 1:
            continue
        nr = c["saetze"].get(w, [None])[0]
        satz_text = L.nach_nr[nr]["text"] if nr in L.nach_nr else ""
        st = analyse.inhaltsstaemme(analyse.tokens(w))
        if RECHT_RE.search(satz_text) or any(st & (sa | sb) for sa, sb in L.aliase):
            geschuetzt.add(w)
    return [(w, k) for w, k in c["varianten"] if w not in geschuetzt]


def synonym_ziel(L: Lauf, varianten: list[tuple[str, int]]) -> tuple[str, str]:
    """(Zielform, Begründung) eines Synonym-Clusters: die häufigere Form; liegt der Nominalstil über P75, die Form ohne -ung
    (v6-Prüfung, Agile: „Effekt/Wirkung“ ohne Zielform, gewählt wurde „Wirkung“ – Nominalstil 8,53 → 8,99)."""
    ns, p75 = L.wert("nominalstil_pro_100"), L.p_("nominalstil_pro_100", "p75")
    if ns is not None and p75 is not None and ns > p75:
        ohne_ung = [(w, k) for w, k in varianten if not re.search(r"ung(?:en)?$", w.lower())]
        if ohne_ung and len(ohne_ung) < len(varianten):
            return max(ohne_ung, key=lambda v: v[1])[0], "die Form ohne -ung, der Nominalstil ist schon hoch"
    return max(varianten, key=lambda v: v[1])[0], "die häufigere Form"


def _synonyme(L: Lauf) -> None:
    """Synonym-Wechsel („Kunden“/„Konsumenten“). Nicht, wenn die seltene Form genau einmal vorkommt und dort Rechtsbegriff
    (Richtlinie, Verordnung, §, Gesetz) oder in „A (B)“ gleichgesetzt ist; nicht erneut, wenn die Zählungen seit der Vorrunde
    unverändert sind (dann ist die Wahl bewusst)."""
    if not any(L.ki_auffaellig(k, nur_rot=True) for k in ("mattr_100", "mtld", "inhaltswort_mattr_50")) or "synonyme" in L.ausgesetzt:
        return
    vorher = {h.get("anfang"): h.get("zaehlung") for h in (L.vorher or {}).get("hinweise") or []
              if isinstance(h, dict) and h.get("typ") == "synonyme"}
    # alle früheren Runden: nach einer Überarbeitung, die diese Wörter nicht angefasst hat, nicht in der übernächsten Runde
    # wieder auftauchen (sonst pendelt der Hinweis: genannt – still – genannt)
    frueher: dict[str, list] = {}
    for mess in L.messungen:
        for h in mess.get("hinweise") or []:
            if isinstance(h, dict) and h.get("typ") == "synonyme":
                frueher.setdefault(h.get("anfang"), []).append(h.get("zaehlung"))
    n = 0
    for c in synonym_cluster(L.fokus, L.masken):
        if n >= 2:
            break
        varianten = synonym_varianten(L, c)
        if len(varianten) < 2 or sum(k for _, k in varianten) < 4:
            continue
        schl = "syn:" + "|".join(sorted(w.lower() for w, _ in varianten))
        zaehlung = {w.lower(): k for w, k in varianten}
        if zaehlung in frueher.get(schl, []) and not (text_unveraendert(L) and vorher.get(schl) == zaehlung):
            continue  # überarbeitet, aber diese Wörter nicht angefasst: Wahl offenbar bewusst (nur erneut gemessen: wiederholen)
        ziel, grund = synonym_ziel(L, varianten)
        andere = [w for w, _ in varianten if w != ziel]
        # eine zu ersetzende Form steht in einem Satz mit Quellenangabe: dort gehört die Wortwahl zur Quelle (v6-Prüfung, DP:
        # „Konsumenten“ im Kahneman-Satz meint Verbraucher allgemein, nicht die Kunden eines Händlers)
        if any(L.quelle.get(nr) for w in andere for nr in c.get("saetze", {}).get(w, [])):
            L.unterdrueckt["synonyme_quelle"] += 1
            continue
        formen = sorted({f for w in andere for f in c.get("formen_je", {}).get(w, [w.lower()])})
        liste_ = ", ".join(f"„{w}“ ({k}×)" for w, k in varianten)
        if L.hinweis("synonyme", None, f"Für dieselbe Sache wechseln die Wörter: {liste_}. Falls dasselbe gemeint ist, durchgehend „{ziel}“ "
                     f"verwenden ({grund}); wo eine andere Form etwas anderes meint, sie stehen lassen.", 0.9, ersetzbar=formen, anfang=schl):
            L.hinweise[-1].update({"zaehlung": zaehlung, "zielform": ziel})
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
        if FOLGERUNG_RE.search(t.group(0)) and not doppelpunkt_ok(L):
            weg.pop("dass", None)  # Folgerung über „folgt, dass“: der „dass“-Satz bleibt
    elif kid == "laesst_sich":
        if lassen_gesperrt(mk, t):
            L.unterdrueckt["fw_lassen_leicht"] += 1
            return None  # „lässt sich leicht/einfach …“ bzw. „… verarbeiten und … herausziehen“: nur „kann … werden“ ginge, länger
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
        if nominal_sperre(L, s, mk, "dass " + t.group("rest")) or kopula_praedikativ("dass " + t.group("rest")):
            return None  # dieselbe Nominalisierung wie beim Nebensatz-Auftrag, dieselben Sperren (Konjunktiv, Koordination, Kette, Kopula)
        weg["dass"] = 1
    return weg, dazu


# „lässt sich“ mit Adverb der Leichtigkeit bzw. Schwierigkeit oder mit koordinierten Infinitiven: gemeint ist eine Möglichkeit, es
# bliebe nur „kann … werden“ – länger, doppeltes Passiv, neue kurze Satzklammer (v6-Prüfung, haw S43: Score 80 → 77)
LEICHT_ADV_RE = re.compile(r"\b(?:einfach|leicht|gut|schwer|kaum|problemlos|mühelos|ohne\s+weiteres)\b", re.IGNORECASE)
KOORD_INF_RE = re.compile(r"\b[a-zäöüß]\w*(?:en|ern|eln)\s+(?:und|oder|sowie)\s+(?:[^,;:.]*\s)?[a-zäöüß]\w*(?:en|ern|eln)\s*$")


def lassen_gesperrt(mk: str, t: re.Match) -> bool:
    """„lässt sich“ nicht umbauen: Leichtigkeitsadverb in der Wendung bzw. im Teilsatz oder koordinierte Infinitive am Teilsatzende."""
    a = max(mk.rfind(",", 0, t.start()), mk.rfind(";", 0, t.start())) + 1
    e = len(mk)
    for z in ",;:":
        k = mk.find(z, t.end())
        if k >= 0:
            e = min(e, k)
    teil = mk[a:e].rstrip(" .!?“”\"»«)")
    return bool(LEICHT_ADV_RE.search(teil) or KOORD_INF_RE.search(teil))


def neue_klammer(kid: str, mk: str, t: re.Match) -> int | None:
    """Spanne der Satzklammer, die ein Funktionswort-Umbau voraussichtlich neu erzeugt („lässt sich X Y verarbeiten“ → „wird X Y
    verarbeitet“, „gilt als zuverlässig“ → „wird für zuverlässig gehalten“): die Wörter zwischen der Wendung und dem Verb am
    Teilsatzende. None = keine neue Klammer (Nebensatz mit Verb am Ende, direktes Verb)."""
    if kid not in ("laesst_sich", "gilt_als") or not re.match(r"(?i)lässt|lassen|ließ|ließen|gilt|gelten|galt|galten", t.group(0)):
        return None
    rest = re.split(r"[,;:()–—]", mk[t.end():], maxsplit=1)[0]
    w = [x for x in analyse.tokens(rest) if analyse.ist_wort(x)]
    if kid == "gilt_als":
        return len(w) + 1 if w else None  # „wird für (…) gehalten“: „für“ plus die Einschätzung
    if len(w) < 2 or not re.search(r"(?:en|ern|eln)$", w[-1]) or not w[-1].islower():
        return None
    return len(w) - 1


FW_MIT_MODALVERB = {"dient_als", "gilt_als", "versteht_sich_als", "ergibt_sich", "zeigt_sich"}
# Ersatzverben der „als“-Zuschreibungen: steht ein Ersatzverb schon im Satz, wird nur die andere Variante angeboten
_IST_RE = re.compile(r"\b(?:ist|sind|war|waren)\b", re.IGNORECASE)
_BILDET_RE = re.compile(r"\bbild(?:et|en|ete|eten|e)\b", re.IGNORECASE)
_HALTEN_RE = re.compile(r"\b(?:hält|halten|hielt|hielten|gehalten)\b", re.IGNORECASE)
_WOLLEN_RE = re.compile(r"\b(?:will|wollen|wollte|wollten)\b", re.IGNORECASE)


def doppelpunkt_ok(L: Lauf) -> bool:
    """Darf ein Auftrag einen Doppelpunkt vorschlagen? Nur, solange Doppelpunkte höchstens beim menschlichen Median liegen."""
    dp, dp50 = L.wert("doppelpunkt_pro_1000"), L.p_("doppelpunkt_pro_1000", "p50")
    return dp is None or dp50 is None or dp <= dp50


def modalverb_im_teilsatz(maske: str, start: int, ende: int) -> str | None:
    """Modalverb im Teilsatz (zwischen den Kommas) um die Wendung, in Anführungszeichen für den Auftragstext; sonst None."""
    a = maske.rfind(",", 0, start) + 1
    e = maske.find(",", ende)
    teil = maske[a:e if e >= 0 else len(maske)]
    mv = next((w for w in analyse.tokens(teil) if w.lower() in analyse.MODALVERBEN), None)
    return f"„{mv.lower()}“" if mv else None


FW_VERBEN = {"ergibt_sich": ["folgt", "entsteht"], "gilt_als": ["gehalten"], "versteht_sich_als": ["will"]}


def fw_technik(L: Lauf, kid: str, technik: str, mk: str, t: re.Match) -> tuple[str, list[str], list[str]] | None:
    """(Auftragstext, vorgeschlagene Verben, Wörter, die bleiben müssen) einer Funktionswort-Konstruktion an dieser Stelle;
    None = an dieser Stelle kein Auftrag (das einzige Ersatzverb steht schon im Satz). Folgerungsverben: Folgerung über
    „folgt“ erhalten (Doppelpunkt nur, solange Doppelpunkte nicht häufig sind), konzessive Adverbien bleiben beim Verb – nie
    „daher/also“. Verben und Bleibewörter prüft ein_auftrag_je_satz gegen die übrigen Teile eines kombinierten Auftrags."""
    rest = mk[:t.start()] + " " + mk[t.end():]  # Satz ohne die Wendung selbst
    verben, behalten = list(FW_VERBEN.get(kid, [])), []
    if kid == "ankuendigung" and FOLGERUNG_RE.search(t.group(0)):
        technik = ANKUENDIGUNG_FOLGERUNG if doppelpunkt_ok(L) else ANKUENDIGUNG_FOLGERUNG_VERB
        verben = ["folgt"]
        konz = KONZESSIV_RE.search(mk)
        if konz:
            adv = konz.group(0).lower()
            behalten.append(adv)
            technik += f"; „{adv}“ bleibt beim Verb („folgt {adv} …“), nicht „daher“ oder „also“"
        return technik, verben, behalten
    if kid == "dient_als":
        ist, bildet = bool(_IST_RE.search(rest)), bool(_BILDET_RE.search(rest))
        verben = [v for v, da in (("ist", ist), ("bildet", bildet)) if not da]
        if not verben:
            return None
        if bildet:
            technik = ("→ „ist“ („bildet“ steht schon im Satz; Beispiel: „Der Bericht dient als Grundlage der Planung.“ → „Der "
                       "Bericht ist die Grundlage der Planung.“)")
        elif ist:
            technik = ("→ „bildet“ („ist“ steht schon im Satz; Beispiel: „Der Bericht dient als Grundlage der Planung.“ → „Der "
                       "Bericht bildet die Grundlage der Planung.“)")
    elif kid == "gilt_als" and _HALTEN_RE.search(rest):
        return None
    elif kid == "versteht_sich_als" and _WOLLEN_RE.search(rest):
        return None
    if kid in FW_MIT_MODALVERB and modalverb_im_teilsatz(mk, t.start(), t.end()):
        # „kann als Signal fungieren“ → „kann ein Signal sein“: die Möglichkeit bleibt eine Möglichkeit (Aussagestatus)
        mv = modalverb_im_teilsatz(mk, t.start(), t.end())
        technik += f"; {mv} bleibt (die Möglichkeit wird keine Tatsache)"
        behalten.append(mv.strip("„“"))
    return technik, verben, behalten


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
            ft = fw_technik(L, kid, technik, mk, t)
            if ft is None:
                continue  # das einzige Ersatzverb steht schon im Satz (kein doppeltes Verb)
            technik, verben, behalten = ft
            if typ == "fw_dass" and (nominal_gesperrt(L, s) or "nebensatz" in L.ausgesetzt or L.jenseits):
                # „dass“-Satz → Nominalgruppe ist eine Nominalisierung: nicht, wenn „Wortwahl einfacher“ Hebel ist und der Satz
                # schon eine Nominalkette hat, und nicht, wenn Nebensatz → Nominalgruppe bzw. Verdichten im Bericht ausgesetzt ist
                continue
            fund = t.group(0) if kid != "redeverb_dass" else t.group(0)[:t.start("rest") - t.start()].strip()
            kand.append((delta, s, typ, fund, technik, verben, behalten, bilanz, neue_klammer(kid, mk, t)))
            L.fw_potenzial += delta
            break  # ein Funktionswort-Auftrag je Satz
    n_max = 5 if unter_p25 else 3
    n_fw = 0
    p75_21 = L.p_("teilsatz_verhaeltnis_21", "p75")
    for delta, s, typ, fund, technik, verben, behalten, bilanz, klammer_neu in sorted(kand, key=lambda x: (-x[0], x[1]["nr"])):
        if n_fw >= n_max:
            break
        if typ in ("fw_ankuendigung", "fw_dass") and p75_21 is not None and verhaeltnis_21(teilsatz_folge(L)) > p75_21 \
                and not teilsatz_ok(L, {"typ": typ, "satz": s["nr"], "fw_weg": dict(bilanz[0])}):
            # aus drei Teilsätzen würden zwei: das Verhältnis 2:1 stiege weiter (v6-Prüfung, Agile S41: 1,11 → 1,17)
            L.unterdrueckt["fw_teilsatz"] += 1
            L.fw_teilsatz_gesperrt.add((s["nr"], typ))
            continue
        ersetzbar = [w for w in re.findall(r"[A-Za-zÄÖÜäöüß]+", fund) if w.lower() not in analyse.FUNKTIONSWOERTER and len(w) > 3]
        if L.hinweis(typ, s, f"{zitat(s)}: „{fund}“ {technik}.", 0.8, fund=fund, ersetzbar=ersetzbar):
            L.hinweise[-1].update({"fw_delta": round(delta, 3), "verben": verben, "behalten": behalten,
                                   "fw_weg": dict(bilanz[0]), "fw_dazu": dict(bilanz[1]), "klammer_neu": klammer_neu})
            if typ == "fw_ankuendigung":
                L.hinweise[-1]["teilsaetze"] = sum(analyse.teilsatz_zerlegung(s["text"])[:2])
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


# Floskel-Ersatz ohne Steigerung: die Ersatzbeispiele aus ki_muster.json („gilt als wichtigstes …“, „ist laut … unverzichtbar“,
# „X entscheidet über …“) verstärken die Aussage (CSRD: „Schlüsselrolle“ → „unverzichtbar“). Neutrale Beispiele gleicher Stärke.
FLOSKEL_ERSATZ = {
    "schluessel": "das Modewort durch eine gleich starke, neutrale Formulierung ersetzen („wichtige Funktion für …“, „ist wichtig "
                  "für …“) oder die konkrete Funktion beschreiben. Schreibt eine Quelle X diese Rolle zu, die Zuschreibung samt "
                  "Quelle behalten und nur das Modewort ersetzen. Ist das Wort ein Fachbegriff der Quelle (z. B. "
                  "Schlüsselkompetenz), unverändert lassen.",
    "rolle_zukommen": "die Funktion gleich stark und konkret benennen („X ist wichtig für …“, „X hat eine wichtige Funktion für …“) "
                      "oder die Wichtigkeit belegen (Zahl, Quelle).",
}
STAERKE_MUSTER = {"schluessel", "rolle_zukommen", "rolle_spielen", "von_bedeutung", "bedeutung_gewinnen"}
STAERKE_HALTEN = " Stärke beibehalten, nicht steigern (kein „unverzichtbar“, „wichtigstes“)."


# Ersatz ohne neuen Inhalt: Die Ersatztexte einiger Muster verlangen eine Begründung, Zahl, Quelle oder Entwicklung („mit Begründung“,
# „durch Fakten zeigen“, „belegen“). Steht im Satz bzw. Folgesatz keine Begründung oder Quelle, wäre das neuer Inhalt (v4: Employer
# S17) – dann eine neutrale, gleich starke Variante.
INHALT_FORDERND_RE = re.compile(r"Begründung|Fakten|belegen|belegt\b|\(Zahl, Quelle\)|weil …|Rückbezug|Entwicklung belegen")
FLOSKEL_NEUTRAL = {
    "von_bedeutung": "„ist besonders wichtig für …“ oder „steht im Mittelpunkt“ – gleich stark, ohne neuen Inhalt.",
    "rolle_zukommen": "die Funktion gleich stark benennen („X ist wichtig für …“, „X hat eine wichtige Funktion für …“), ohne neuen Inhalt.",
    "rolle_spielen": "„ist wichtig für …“ oder „beeinflusst …“ – gleich stark, ohne neuen Inhalt.",
    "bedeutung_gewinnen": "„wird wichtiger“ – gleich stark, ohne neue Zahlen.",
    "einwand_formel": "Die Einleitungsformel weglassen und das Gegenargument als eigene Aussage formulieren; den Inhalt des dass-Satzes "
                      "vollständig behalten.",
    "kern_zentral": "die Rangfolge gleich stark nennen („der wichtigste …“, „vor allem“); „Im Kern“ kann wegfallen, wenn der Satz die "
                    "Hauptsache ohnehin nennt.",
    "spannungsfeld": "die beiden Seiten des Konflikts direkt nennen („der Konflikt zwischen X und Y“), ohne neue Begründung.",
    "insgesamt_zeigt": "das Ergebnis direkt nennen, ohne die Ankündigungsformel.",
}
# Begründung im Satz selbst (weil, da, denn …), Begründungsanschluss am Anfang des Folgesatzes („Denn …“, „Deshalb …“) oder eine
# Zahl mit Einheit (Prozent) bzw. Quelle – ein „da“-Satz im Folgesatz über etwas anderes zählt nicht (v4: Employer S17/S18)
BEGRUENDUNG_RE = re.compile(r"\b(?:weil|denn|aufgrund|wegen|nämlich)\b|,\s+da\s|\d+(?:[,.]\d+)?\s*(?:%|Prozent)", re.IGNORECASE)
BEGRUENDUNG_ANFANG_RE = re.compile(r"^(?:Denn|Deshalb|Daher|Dadurch|Damit|So\s+(?:zeigt|belegt|nennen|ergab)|Nach\s+[A-ZÄÖÜ]|Laut|Gemäß)\b")
ZAHL_RE = re.compile(r"\d+(?:[,.]\d+)?\s*(?:%|Prozent)", re.IGNORECASE)
# Rückbezug auf Vorhandenes („Aus den Befunden in Kapitel 4 folgt: …“) – nur, wenn Kapitel/Abschnitt bzw. Befunde im Text stehen
KAPITEL_RE = re.compile(r"\b(?:Kapitel|Abschnitt|Kap\.)\s+\d+(?:\.\d+)*")
BEFUND_NOMEN_RE = re.compile(r"\b(?:Befund|Befunde|Befunden|Ergebnisse|Ergebnissen|Analyse|Befragung|Interviews|Studie|Fallstudie|"
                             r"Untersuchung|Daten|Auswertung)\b")


def begruendung_im_kontext(L: Lauf, s: dict) -> bool:
    """Liefert der Satz selbst eine Begründung (weil, da, denn …) oder Zahl, oder schließt der Folgesatz (gleicher Absatz) mit
    einer Begründung an („Denn …“, „Deshalb …“) bzw. nennt eine Zahl oder Quelle? Nur dann darf ein Floskel-Ersatz „mit Begründung“
    oder „durch Fakten zeigen“ verlangen – sonst wäre es neuer Inhalt."""
    if BEGRUENDUNG_RE.search(L.masken.get(s["nr"], s["text"])):
        return True  # (eine Quellenangabe im Satz selbst belegt meist den Begriff, nicht seine Wichtigkeit)
    nach = L.nach_nr.get(s["nr"] + 1)
    if not nach or nach["absatz"] != s["absatz"]:
        return False
    mk = L.masken.get(nach["nr"], nach["text"])
    return bool(BEGRUENDUNG_ANFANG_RE.match(nach["text"].lstrip("„\"(»")) or ZAHL_RE.search(mk) or L.quelle.get(nach["nr"]))


def rueckbezug(L: Lauf, s: dict) -> str | None:
    """Konkreter Rückbezug auf Vorhandenes für eine Ankündigung: ein Kapitel bzw. Abschnitt, sonst ein Befund-Nomen – beides nur aus
    den drei Sätzen davor im selben Absatz („aus den Ergebnissen der Befragung“). Ein Kapitel, das irgendwo weiter vorn steht (etwa im
    Gliederungsüberblick der Einleitung), trägt die Folgerung nicht: „Aus Kapitel 2 folgt: …“ wäre eine neue Behauptung (v5-Prüfung).
    None = nichts da."""
    vorher = [x for x in L.saetze if x["nr"] < s["nr"]]
    nah = [x for x in vorher[-3:] if x["absatz"] == s["absatz"]]
    for x in reversed(nah):
        m = KAPITEL_RE.search(L.masken.get(x["nr"], x["text"]))
        if m:
            return m.group(0)
    for x in reversed(nah):
        m = BEFUND_NOMEN_RE.search(L.masken.get(x["nr"], x["text"]))
        if m:
            return m.group(0)
    return None


# Handelnde, die „ermöglicht es“ als Subjekt übernehmen darf: nur Organisationen, die in einem Vorsatz desselben Absatzes selbst Subjekt
# am Satzanfang sind („Händler, die …, können …“, „Das Unternehmen erhält …“) – ein Akteur als Objekt bzw. Genitiv („Merkmale zu
# den Unternehmen“, „die Selbstwahrnehmung der Unternehmen“) ist nicht der Handelnde (v5-Prüfung: ssoar-19287, hwr-851, hsmw-3538)
_AKTEUR_DET = {"der", "die", "das", "diese", "dieser", "dieses", "viele", "einige", "alle", "manche", "mehrere", "zahlreiche", "ein",
               "eine", "jedes", "jeder", "jede"}
_AKTEUR_EINZAHL_DET = {"der", "das", "ein", "eine", "dieser", "dieses", "jedes", "jeder", "jede"}
_AKTEUR_EINZAHL = {"führung", "leitung", "organisation", "firma", "bank", "hochschule", "schule", "verwaltung", "politik", "kommission",
                   "regierung", "behörde", "management", "gesetzgeber", "staat", "gericht", "verband", "konzern", "team", "betrieb"}


def akteur_subjekt(text: str) -> str | None:
    """Organisation als Subjekt am Satzanfang („Händler, die …“, „Das Unternehmen erhält …“, „Viele kleine Händler …“): die Wortgruppe
    wie im Text (Artikel + Nomen) samt passender Verbform („kann“ bzw. „können“), sonst None."""
    w = [t for t in analyse.tokens(text) if analyse.ist_wort(t)][:3]
    det = None
    if w and w[0].lower() in _AKTEUR_DET:
        det, w = w[0], w[1:]
        if w and w[0][:1].islower() and w[0].lower() not in AKTEURE:
            w = w[1:]  # ein Adjektiv („Viele kleine Händler“)
    if not w or not w[0][:1].isupper() or w[0].lower() not in AKTEURE:
        return None
    nomen = w[0]
    einzahl = (det or "").lower() in _AKTEUR_EINZAHL_DET or ((det or "").lower() in ("die", "diese") and nomen.lower() in _AKTEUR_EINZAHL)
    gruppe = f"{det.capitalize()} {nomen}" if det and det.lower() in _AKTEUR_EINZAHL_DET | {"die", "diese"} else nomen
    return f"„{gruppe} {'kann' if einzahl else 'können'} so …“"


def ermoeglicht_ersatz(L: Lauf, s: dict) -> str:
    """„ermöglicht es“: das handelnde Subjekt steht als Dativ im Satz („ermöglicht es Händlern, …“), sonst aus dem Absatz übernehmen –
    nur eine Organisation, die dort selbst Subjekt am Satzanfang ist; ohne genannte Handelnde Passiv mit „können“ – nie ein neues
    Subjekt erfinden (v4: DP S10, „Händler“ ergänzt). Keine selbst gebeugte Form („Händlern können“): die Wortgruppe aus dem Satz
    wird als Subjekt in den Nominativ gesetzt, das Verb passend zur Zahl."""
    mk = L.masken[s["nr"]]
    m = re.search(r"\b(?:ermöglicht|ermöglichen|ermöglichte|ermöglichten)\s+es\s+(?P<dat>[^,;.]{1,60}?)\s*,", mk)
    dativ = m and [w for w in analyse.tokens(m.group("dat")) if analyse.ist_wort(w) and w[:1].isupper()]
    if dativ:
        x = " ".join(m.group("dat").split())
        return (f"die Handelnden stehen schon im Satz („{x}“): sie als Subjekt nehmen – im Nominativ, Verb passend zur Zahl („… kann so …“ "
                "bzw. „… können so …“); Aussage und Stärke bleiben.")
    for x in [y for y in L.saetze if y["absatz"] == s["absatz"] and y["nr"] < s["nr"]][::-1]:
        # nur Organisationen als Handelnde (Unternehmen, Händler, Anbieter …) – Personen wie „Kunden“ sind meist die Betroffenen
        vorlage = akteur_subjekt(L.masken.get(x["nr"], x["text"]).lstrip("„\"(»"))
        if vorlage:
            nomen = vorlage.strip("„“").split(" kann")[0].split(" können")[0].split()[-1]
            return (f"das handelnde Subjekt aus dem Absatz übernehmen (dort Subjekt in Satz {x['nr']}: „{nomen}“): {vorlage} – nur, wenn "
                    "tatsächlich diese Handelnden gemeint sind; Aussage und Stärke bleiben.")
    return ("ohne genannte Handelnde mit Passiv und „können“ umstellen (Beispiel: „Das Verfahren ermöglicht es, Preise anzupassen.“ → "
            "„Mit dem Verfahren können Preise angepasst werden.“) – kein neues Subjekt erfinden.")


def floskel_ersatz(mu: dict, L: Lauf | None = None, s: dict | None = None) -> str:
    """Ersatz-Technik eines KI-Musters; bei Wichtigkeits-Floskeln neutrale Beispiele gleicher Stärke und der Zusatz
    „Stärke beibehalten, nicht steigern“. Verlangt der Ersatz neuen Inhalt (Begründung, Fakten, Zahl, Quelle), nur mit Begründung
    bzw. Quelle im Satz oder Folgesatz – sonst eine neutrale Variante; „ermöglicht es“ mit dem Subjekt aus dem Kontext."""
    mid = mu.get("id")
    text = FLOSKEL_ERSATZ.get(mid) or mu.get("ersatz") or "durch die konkrete Aussage ersetzen"
    if L is not None and s is not None:
        if mid == "ermoeglicht":
            return ermoeglicht_ersatz(L, s)
        if INHALT_FORDERND_RE.search(text):
            ok = rueckbezug(L, s) if mid == "insgesamt_zeigt" else begruendung_im_kontext(L, s)
            if not ok:
                text = FLOSKEL_NEUTRAL.get(mid) or re.sub(r"\s*–?\s*oder die Wichtigkeit belegen \(Zahl, Quelle\)\.?", ".", text)
        text = ersatz_ohne_nahe(L, s, text)
    if mid in STAERKE_MUSTER:
        text = text.rstrip() + STAERKE_HALTEN
    return text


ERSATZ_FENSTER = 15  # Floskel-Ersatz: Varianten, die in so vielen Sätzen davor/danach schon am Satzanfang stehen, entfallen
_VARIANTE_RE = re.compile(r"„([^“„]{2,60})“")


def _variante_staemme(v: str) -> tuple[list[str], set[str]]:
    """Inhaltswörter einer Ersatzvariante (ohne Platzhalter X/Y/A/B und „…“) und ihre Grundformen."""
    worte = [w for w in analyse.tokens(v) if analyse.ist_wort(w) and len(w) > 2 and w.lower() not in analyse.FUNKTIONSWOERTER]
    return worte, {_grund(w.lower()) for w in worte}


def ersatz_ohne_nahe(L: Lauf, s: dict, text: str) -> str:
    """Streicht Ersatzvarianten („steht im Mittelpunkt“), die in den ERSATZ_FENSTER Sätzen davor bzw. danach schon am Satzanfang
    stehen – der Ersatz wiederholte sonst eine Wendung aus der Nähe (v6-Prüfung: Employer S17 „steht im Mittelpunkt“ nach S3 „Im
    Mittelpunkt steht …“). Mehrwortvarianten: alle Inhaltswörter unter den ersten sechs Wörtern; Einzelwörter: als erstes oder
    zweites Wort. Bleibt keine Variante, ein Hinweis statt der Vorlage."""
    nahe = [x for x in L.saetze if x["nr"] != s["nr"] and abs(x["nr"] - s["nr"]) <= ERSATZ_FENSTER]
    koepfe = []
    for x in nahe:
        toks = [t for t in analyse.tokens(L.masken.get(x["nr"], x["text"])[fuehrende_quelle(x["text"]):]) if analyse.ist_wort(t)]
        koepfe.append((x["nr"], {_grund(t.lower()) for t in toks[:6]}, {_grund(t.lower()) for t in toks[:2]}))
    varianten = _VARIANTE_RE.findall(text)
    for v in varianten:
        worte, st = _variante_staemme(v)
        if not st:
            continue
        treffer = next((nr for nr, sechs, zwei in koepfe if (st <= sechs if len(st) > 1 else st <= zwei)), None)
        if treffer is None:
            continue
        rest = [x for x in _VARIANTE_RE.findall(text) if x != v]
        if not rest:
            text = text.rstrip(" .") + f" – „{v}“ steht schon in Satz {treffer}: eine andere, gleich starke Formulierung wählen."
            break
        for muster in (rf"(?:,\s*|\s+oder\s+)„{re.escape(v)}“", rf"„{re.escape(v)}“(?:,\s*|\s+oder\s+)"):
            neu = re.sub(muster, "", text, count=1)
            if neu != text:
                text = neu
                break
    return text


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
    # Gegenfolie: höchstens GEGENFOLIE_MAX Aufträge je Text (über alle Runden), die Technik wechselt (v4: „neben … auch“ 0 → 4)
    gf_frueher = {a for mess in L.messungen for h in mess.get("hinweise") or [] if isinstance(h, dict)
                  and "gegenfolie" in (h.get("typen") or [h.get("typ")]) for a in [h.get("anfang")] if a}
    gf_rest = max(0, GEGENFOLIE_MAX - len(gf_frueher))
    fokus_text = " ".join(L.masken[x["nr"]] for x in L.fokus)
    gf_technik = Counter({"neben": len(NEBEN_AUCH_RE.findall(fokus_text)), "außer": len(AUSSER_AUCH_RE.findall(fokus_text))})
    # Rotation über alle Runden: frühere Techniken zählen mit (v6-Prüfung: „X und … auch Y“ in R1 und R2)
    gf_technik.update(h["technik"] for mess in L.messungen for h in mess.get("hinweise") or [] if isinstance(h, dict)
                      and "gegenfolie" in (h.get("typen") or [h.get("typ")]) and h.get("technik"))
    kl, kl25 = L.wert("satzklammer_mittel"), L.p_("satzklammer_mittel", "p25")
    klammer_ok = kl is None or kl25 is None or kl >= kl25
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
        ersatz = floskel_ersatz(mu)
        typ = "floskel"
        if gegenfolie:
            typ = "gegenfolie"
            paar = wertungspaar(mk)
            mx = NICHT_X_RE.search(mk)
            x_staemme = analyse.inhaltsstaemme(analyse.tokens(ADDITIV_RE.sub(" ", mx.group("x")))) if mx else set()
            vorige = [L.nach_nr[n] for n in range(s["nr"] - 3, s["nr"]) if n in L.nach_nr]
            x_genannt = bool(x_staemme) and any(x_staemme & L.begriffe_info[v["nr"]]["staemme"] for v in vorige)
            x_worte = [w for w in analyse.tokens(ADDITIV_RE.sub(" ", mx.group("x"))) if analyse.ist_wort(w)] if mx else []
            grund = None
            if paar:
                grund = f"Kontrast „{paar[0]}“ ↔ „{paar[1]}“"
            elif x_worte and len(x_worte) <= 2 and all(w[:1].islower() for w in x_worte) and not ADDITIV_RE.search(fund):
                grund = "Kontrast zweier Eigenschaften"
            elif not ADDITIV_RE.search(fund):
                # begründete Gegenüberstellung: Aussage einer Quelle bzw. mit Redeverb, wiedergegebene Rede im Konjunktiv oder ein
                # X, das kurz vorher genannt wird – „nur umformulieren“ wäre dieselbe Figur in anderer Oberfläche (v6-Prüfung,
                # bt-wd9 S4: „Y und nicht X“ brachte allein Score 54 → 59, Detektor-Umgehung statt Stilverbesserung)
                if L.quelle.get(s["nr"]) or REDEVERB_RE.search(mk) or personen_subjekt(mk):
                    grund = "Aussage einer Quelle"
                elif konjunktiv_indirekt(L, s):
                    grund = "wiedergegebene Rede im Konjunktiv"
                elif x_genannt:
                    grund = "X wird kurz vorher genannt, die Gegenüberstellung ist begründet"
            if grund:
                # kein Auftrag: der Kontrast ist die Aussage. Einmal als Info-Zeile („Bewusst stehen lassen“), nie in der
                # Aufgabenliste und nie im Limit; in Folgerunden gar nicht mehr
                schl = schluessel_anfang(s["text"])
                if schl not in L.stehen_lassen_frueher and s["nr"] not in {x["satz"] for x in L.stehen_lassen}:
                    L.stehen_lassen.append({"satz": s["nr"], "anfang": schl, "grund": grund, "fund": fund})
                continue
            if gf_rest <= 0:
                continue  # Obergrenze je Text erreicht: weitere Gegenfolien würden nur eine neue Schablone vervielfachen
            gf_fw = ({"nicht": 1, "sondern": 1}, {})
            if ADDITIV_RE.search(fund):
                if not additiv_ok or re.search(r"\bnicht\s+mehr\s+nur\b", fund, re.IGNORECASE):
                    continue  # „nicht mehr nur“ trägt einen Wandel – „neben/außer … auch“ verlöre ihn
                ms = re.search(r",\s*sondern\b", mk)
                erster_hs = len([w for w in analyse.tokens(mk[:ms.start()]) if analyse.ist_wort(w)]) - 2 if ms else 99
                technik, ersatz = gegenfolie_technik(x_worte, gf_technik, klammer_ok, erster_hs)
                gf_technik[technik] += 1
                gf_fw = ({"nicht": 1, "nur": 1, "sondern": 1},
                         {"neben": {"neben": 1}, "außer": {"außer": 1}, "und_auch": {"und": 1}, "und_auch_verb": {"und": 1},
                          "aber_auch": {"aber": 1}}.get(technik, {}))
        # nur Auslöser-Wörter als ersetzbar melden, nie Platzhalter des Musters (die sind Inhalt des Nutzers)
        worte = [w for w in floskel_kopfwoerter(mk, _a, _e, mu["_re"])
                 if w.lower() not in analyse.FUNKTIONSWOERTER and len(w) > 2] if typ == "floskel" else []
        if typ == "floskel":
            ersatz = floskel_ersatz(mu, L, s)
        if L.hinweis(typ, s, f"{zitat(s)}: „{fund}“ – {ersatz}", 0.6 + 0.3 * g, fund=fund, ersetzbar=worte):
            L.hinweise[-1].update({"muster_gewicht": g, "spanne": (_a, _e), "muster_id": mu.get("id")})
            if typ == "gegenfolie":
                L.hinweise[-1].update({"fw_weg": dict(gf_fw[0]), "fw_dazu": dict(gf_fw[1]),
                                       "technik": technik if ADDITIV_RE.search(fund) else None})
            entfernt += g
            if typ == "gegenfolie":
                gf_rest -= 1


# Konjunktiv der indirekten Rede (I und als Ersatz II): „sei“, „habe“, „gäbe“, „hätte“ … im Satz oder im Satz davor (Absatz)
KONJ_INDIREKT_RE = re.compile(r"\b(?:sei|seien|habe|hätte|hätten|wäre|wären|gäbe|gäben|könne|müsse|solle|werde|dürfe|wolle|"
                              r"lägen?|stünden?|bestehe|fehle|führe|zeige)\b", re.IGNORECASE)


def konjunktiv_indirekt(L: Lauf, s: dict) -> bool:
    """Wiedergegebene Rede im Konjunktiv: der Satz selbst oder der Satz davor im selben Absatz steht im Konjunktiv."""
    if KONJ_INDIREKT_RE.search(L.masken.get(s["nr"], s["text"])):
        return True
    vor = L.nach_nr.get(s["nr"] - 1)
    return bool(vor and vor["absatz"] == s["absatz"] and KONJ_INDIREKT_RE.search(L.masken.get(vor["nr"], vor["text"])))


def personen_subjekt(mk: str) -> bool:
    """Personen als Urheber der Aussage im Hauptsatz („sehen Experten den Grund …“, „Die Autoren führen …“)."""
    haupt = hauptsatz_teile(mk)
    return any(t[:1].isupper() and ist_person(t) and t.lower() not in ("personen", "menschen") for t in analyse.tokens(haupt)[1:])


GEGENFOLIE_MAX = 4  # Gegenfolie-Aufträge je Text (alle Runden zusammen); die Technik wechselt, damit kein neues Muster entsteht
# (v5 mit 2: „sondern“ blieb in Controlling rot, −0,89 Logit)
NEBEN_AUCH_RE = re.compile(r"\bneben\b[^.;:]{1,80}?\bauch\b", re.IGNORECASE)
AUSSER_AUCH_RE = re.compile(r"\baußer\b[^.;:]{1,80}?\bauch\b", re.IGNORECASE)


GEGENFOLIE_HS_MIN = 8  # „zwei Hauptsätze“ nur, wenn der erste Hauptsatz mindestens so viele Wörter hätte (sonst ein Kurzsatz)


def gegenfolie_technik(x_worte: list[str], benutzt: Counter, klammer_ok: bool = True, erster_hs: int = 99) -> tuple[str, str]:
    """(Technik, Auftragstext) für „nicht nur X, sondern auch Y“: Verben bzw. Eigenschaften als X („nicht nur ersetzen“) vertragen
    kein „neben“ – „X und … auch Y“, „X, aber auch Y“ oder zwei Hauptsätze; zwei Hauptsätze nur, wenn die Satzklammer mindestens bei
    P25 liegt (klammer_ok) und der erste Hauptsatz mindestens GEGENFOLIE_HS_MIN Wörter hätte – sonst entstehen zwei kurze Klammern und
    ein Kurzsatz (v6-Prüfung: Controlling S32, Satzklammer 5,00 → 4,42). Ein Präpositionalobjekt („nicht nur von X“) behält die
    Präposition in beiden Gliedern; sonst „neben/außer X auch Y“. Die Technik wechselt über alle Runden (die seltenste zuerst, auch
    gegenüber dem Text selbst)."""
    rest = "beide Teile und ihre Gewichtung bleiben."
    x_worte = list(x_worte)
    while x_worte and x_worte[0].lower() in ("nur", "allein", "bloß", "lediglich", "mehr", "einfach"):
        x_worte.pop(0)  # „nicht allein von …“: die Gradpartikel gehört zur Gegenfolie, nicht zu X
    if x_worte and x_worte[-1][:1].islower():
        moeglich = ["und_auch_verb", "aber_auch"] + (["hauptsaetze"] if klammer_ok and erster_hs >= GEGENFOLIE_HS_MIN else [])
        technik = min(moeglich, key=lambda t: (benutzt[t], moeglich.index(t)))
        if technik == "und_auch_verb":
            return technik, ("X ist ein Verb bzw. eine Eigenschaft: zu „X und … auch Y“ umstellen (Angaben wie „in vielen Fällen“ bleiben "
                             "bei Y), kein „neben“ – das verlangte eine Nominalisierung; " + rest)
        if technik == "aber_auch":
            return technik, ("X ist ein Verb bzw. eine Eigenschaft: zu „X, aber auch Y“ umstellen – ein Satz, die Satzklammer bleibt; kein "
                             "„neben“; " + rest)
        return technik, ("X ist ein Verb bzw. eine Eigenschaft: als zwei Hauptsätze schreiben (der zweite mit „auch“); der zweite beginnt mit "
                         "Y oder einer Angabe oder wiederholt das Subjekt als Nomen – kein Pronomen; kein „neben“; " + rest)
    if x_worte and x_worte[0].lower() in analyse.PRAEPOSITIONEN:
        p = x_worte[0].lower()
        technik = min(("außer", "und_auch"), key=lambda t: benutzt[t])
        if technik == "außer":
            return technik, f"zu „außer {p} X auch {p} Y“ umstellen – „{p}“ steht in beiden Gliedern (nicht „neben X auch {p} Y“); " + rest
        return technik, f"zu „{p} X und auch {p} Y“ umstellen – „{p}“ steht in beiden Gliedern; " + rest
    technik = min(("neben", "außer", "und_auch"), key=lambda t: benutzt[t])
    vorlage = {"neben": "„neben X auch Y“", "außer": "„außer X auch Y“", "und_auch": "„X und auch Y“"}[technik]
    return technik, f"zu {vorlage} umstellen; " + rest


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
    """Konnektoren: nur, wenn die Konnektor-Dichte über P75 liegt (KI-Seite, außerhalb der Messunsicherheit). Gemeldet wird ein
    einzelnes Vorkommen nur bei Konnektoren, die bei Claude mehr als KONN_ALLEIN-mal so häufig sind; sonst nur bei Häufung im
    selben Absatz (≥ 2, „jedoch“ ≥ 3), eine Stelle je Absatz. Mittelfeld vor Satzanfang; Satzanfänge gar nicht, wenn
    Konnektor-Satzanfänge schon höchstens beim menschlichen Median liegen. Höchstens MAX_KONNEKTOR Aufträge je Runde."""
    kn = L.kz.get("konnektoren_pro_1000")
    if not kn or not L.ki_auffaellig("konnektoren_pro_1000") or kn["wert"] <= kn["mensch_p75"]:
        return
    # über P90: auch textweite Häufung (derselbe Konnektor ≥ KONN_TEXTWEIT× im Fokus, je Absatz eine Stelle), Kontingent bis zum
    # Median (v4: DP 14,1 je 1000 Wörter, „zudem“ 3× in verschiedenen Absätzen, nur ein Auftrag); darunter die Regel wie bisher
    ueber_p90 = kn.get("mensch_p90") is not None and kn["wert"] > kn["mensch_p90"]
    k_konn = min(MAX_KONNEKTOR_P90 if ueber_p90 else MAX_KONNEKTOR,
                 max(0, math.ceil((kn["wert"] - kn["mensch_p50"]) * L.tok_fokus / 1000)))
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
            if KORRELAT_VOR_RE.search(mk[:t_.start()]):
                L.unterdrueckt["konnektor_korrelat"] += 1
                continue  # „nicht nur …, er hat zudem …“: der Konnektor ist Korrelat – gestrichen hinge „nicht nur“ in der Luft
            funde.append((s["absatz"], s, t_.group(1), t_.start() > off))
    haeufung = Counter((a, w.lower()) for a, _s, w, _m in funde)
    textweit = Counter(w.lower() for _a, _s, w, _m in funde) if ueber_p90 else Counter()
    kand, gesehen = [], set()
    for a, s, wort, mitte in funde:
        v = konnektor_verhaeltnis(wort)
        if v is None or v <= 1.0 or (not mitte and not anfang_ok) or s["nr"] in gesehen:
            continue
        if wort.lower() == "schließlich" and not mitte and aufzaehlung_davor(L, s):
            continue  # „Schließlich …“ schließt eine Aufzählung ab („An erster Stelle …“, „Ein weiteres Risiko …“)
        allein = v > KONN_ALLEIN
        im_absatz = haeufung[(a, wort.lower())] >= KONN_HAEUFUNG.get(wort.lower(), 2)
        # textweit nur für deutlich KI-typische Konnektoren (mehr als doppelt so häufig wie bei Menschen): „jedoch“ (1,8×) oder
        # „somit“ (1,0×) stehen auch in echten Arbeiten oft dreimal (v3: hm-197 bekam sechs Streichungen)
        im_text = textweit[wort.lower()] >= KONN_TEXTWEIT and v > KONN_STARK
        if not allein and not im_absatz and not im_text:
            continue  # sonst nur gehäuft: derselbe Konnektor mindestens zweimal („jedoch“ dreimal) im Absatz (über P90: 3× im Text)
        frei = not any(h["satz"] == s["nr"] for h in L.hinweise)
        n_ = haeufung[(a, wort.lower())] if allein or im_absatz else -textweit[wort.lower()]
        kand.append((0 if allein else 1, 0 if mitte else 1, 0 if frei else 1, s["nr"], s, wort, v, n_))
        gesehen.add(s["nr"])
    n_k, gemeldet, je_wort = 0, set(), Counter()
    for allein_rang, _m, _f, _nr, s, wort, v, n_abs in sorted(kand):
        if n_k >= k_konn:
            break
        if (s["absatz"], wort.lower()) in gemeldet:
            continue  # eine Stelle je Absatz und Konnektor
        if allein_rang == 1 and n_abs < 0 and je_wort[wort.lower()] >= -n_abs - 1:
            continue  # textweite Häufung: die Wiederholung abbauen, nicht den Konnektor ganz tilgen (eine Stelle bleibt)
        if allein_rang == 1 and n_abs < 0:
            warum = f"steht im Text {-n_abs}×; an dieser Stelle"
        elif allein_rang == 1:
            warum = f"steht in Absatz {s['absatz']} {n_abs}×; an dieser Stelle"
        else:
            warum = f"bei Claude etwa {f'{v:.1f}'.replace('.', ',')}× so häufig wie in echten Arbeiten;"
        if L.hinweis("konnektor", s, f"{zitat(s)}: „{wort}“ {warum} streichen, wenn der Bezug klar ist, oder über das wiederholte "
                     "Nomen anschließen (nicht nur verschieben).", 0.9, fund=wort, ersetzbar=[wort]):
            L.hinweise[-1].update({"konnektor_verhaeltnis": round(v, 2), "streicht": [wort.lower()], "fw_weg": {wort.lower(): 1}})
            gemeldet.add((s["absatz"], wort.lower()))
            je_wort[wort.lower()] += 1
            n_k += 1


def semikolon_technik(mk: str) -> str:
    """Ersatz für Semikolons: steht nach dem „;“ kein finites Verb, trennt es Glieder einer Aufzählung – dann ein Komma; sonst
    trennt es zwei Hauptsätze – dann ein Punkt (oder „und“, wenn beide Aussagen eng zusammengehören)."""
    teile = mk.split(";")[1:]
    if teile and all(aufzaehlung_ohne_verb(t) for t in teile):
        return "Semikolon durch Komma ersetzen – es trennt Glieder einer Aufzählung (danach folgt kein eigenes Verb)."
    return "Semikolon durch Punkt ersetzen (zwei Hauptsätze) oder, wenn beide Aussagen eng zusammengehören, mit „und“ verbinden."


def _zeichen(L: Lauf) -> None:
    for s in L.fokus:
        if not L.nutzbar(s):
            continue
        mk = analyse._ohne_zahlzeichen(L.masken[s["nr"]]) if hasattr(analyse, "_ohne_zahlzeichen") else L.masken[s["nr"]]
        if ";" in mk:
            L.hinweis("semikolon", s, f"{zitat(s)}: {semikolon_technik(mk)}", 1.0, fund=";")
    if "doppelpunkt" in L.hebel:
        for s in L.fokus:
            if L.nutzbar(s) and re.search(r":(?!\d)\s", L.masken[s["nr"]]):
                L.hinweis("doppelpunkt", s, f"{zitat(s)}: Doppelpunkt prüfen – oft ist ein eigener Satz oder ein Nebensatz natürlicher.", 0.7,
                          fund=":")


def abk_familien(L: Lauf) -> list[dict]:
    """Ausgeschriebene gängige Abkürzungen im Fokus, je Familie (Kurzform): Treffer (Satz, Fund) außerhalb von Zitaten und nicht am
    Satzanfang, Zahl der Treffer, die die Kennzahl bewegen, und ein Sperrgrund (ein Treffer steht in einem Satz, der beim Bündeln
    im Nachbarsatz aufgeht – dort kein Abkürzungs-Teilauftrag; dann die ganze Familie nicht, sonst entstünde eine Mischform)."""
    fam: dict[str, dict] = {}
    for s in L.fokus:
        if not L.nutzbar(s):
            continue
        mk = L.masken[s["nr"]]
        for rx, kurz, zaehlt in ABK_ERSATZ:
            for t in rx.finditer(mk):
                if t.start() == 0 or MASKE in t.group(0):
                    continue
                f = fam.setdefault(kurz, {"kurz": kurz, "treffer": [], "n": 0, "zaehlt": zaehlt, "sperre": None})
                f["treffer"].append((s["nr"], t.start(), t.group(0)))
                f["n"] += 1 if zaehlt else 0
                if s["nr"] in L.gebuendelte_b:
                    f["sperre"] = "buendeln"
    return sorted(fam.values(), key=lambda f: (not f["zaehlt"], f["treffer"][0][0], f["treffer"][0][1]))


def abk_plan(L: Lauf) -> tuple[list[dict], int, int]:
    """(Familien, die ganz gekürzt werden dürfen; Abkürzungen jetzt; Kontingent bis zum menschlichen Median). Eine Familie kommt nur
    dran, solange der Median noch nicht erreicht ist, und nur ganz – alle ihre Langformen in einem Auftrag –, wenn das Ergebnis höchstens
    bei P75 liegt; sonst wird sie übersprungen (v4: CSRD „rund“ → „ca.“ in S8, eine Runde später „ca.“ neben „rund“/„etwa“ in S14)."""
    p50, p75 = L.p_("abkuerzungen_pro_1000", "p50"), L.p_("abkuerzungen_pro_1000", "p75")
    if p50 is None:
        return [], 0, 0
    stil_re = getattr(analyse, "ABK_STIL_RE", None)
    jetzt = sum(len(stil_re.findall(s["text"])) for s in L.fokus) if stil_re else 0
    bis50 = math.floor(p50 * L.tok_fokus / 1000)
    bis75 = math.floor((p75 if p75 is not None else p50) * L.tok_fokus / 1000)
    k0, plan, stand = bis50 - jetzt, [], jetzt
    for f in abk_familien(L):
        if f["sperre"] or k0 <= 0:
            continue
        if f["zaehlt"]:
            if stand >= bis50 or stand + f["n"] > bis75:
                continue
            stand += f["n"]
        plan.append(f)
    return plan, jetzt, k0


def _abkuerzungen(L: Lauf) -> None:
    """Inhaltsneutraler Modell-Hebel: ausgeschriebene gängige Abkürzungen kürzen, bis höchstens zum menschlichen Median (Kontingent in
    Treffern) – je Familie alle Langformen in einem Auftrag (Ergebnis ≤ P75), sonst die Familie gar nicht (keine Mischform „ca. …
    etwa“, kein Folgeauftrag zum Vereinheitlichen). Steht die Familie in einem Satz, nennt der Auftrag ihn; sonst ein Auftrag mit
    allen Satznummern."""
    if not (L.ki_auffaellig("abkuerzungen_pro_1000") or L.modell_hebel("abkuerzungen_pro_1000")):
        return
    _abk_auftraege(L, abk_plan(L)[0])


def _abk_auftraege(L: Lauf, plan: list[dict], vorsatz: str = "") -> list[dict]:
    """Abkürzungs-Aufträge für die Familien des Plans (ganz oder gar nicht); vorsatz = Kennzeichnung („Klein, aber sicher – “)."""
    # Sätze mit einem anderen Satzauftrag bzw. von einem Strohmann-Paar gesperrt: ein Textauftrag über mehrere Sätze (Satz None)
    # liefe an der Zusammenfassung „ein Auftrag je Satz“ vorbei (v5-Prüfung: hsmw-688 S13 „Mitte“ + „u. a.“) – dann die Familie
    # nicht (ganz oder gar nicht, keine Mischform)
    belegt = {n for h in L.hinweise if h.get("satz") and h["typ"] not in EINZEL_AUSGENOMMEN and h["typ"] != "abkuerzung"
              for n in [h["satz"]] + list(h.get("weitere_nr") or []) + list(h.get("sperrt") or [])}
    neu = []
    for f in plan:
        nach_fund: dict[str, list[int]] = {}
        for nr, _pos, fund in f["treffer"]:
            nach_fund.setdefault(fund, [])
            if nr not in nach_fund[fund]:
                nach_fund[fund].append(nr)
        nrn = list(dict.fromkeys(nr for nr, _p, _f in f["treffer"]))
        if len(nrn) > 1 and set(nrn) & belegt:
            L.unterdrueckt["abk_familie_belegt"] += 1
            continue
        funde = [fund for _nr, _p, fund in f["treffer"]]
        ersetzbar = [w for fund in funde for w in fund.split() if len(w) > 3]
        einheitlich = " – alle Stellen, einheitlich" if len(funde) > 1 else ""
        if len(nrn) == 1:
            s = L.nach_nr[nrn[0]]
            teile = " und ".join(f"„{fund}“" for fund in nach_fund)
            ok = L.hinweis("abkuerzung", s, f"{vorsatz}{zitat(s)}: {teile} als „{f['kurz']}“ schreiben{einheitlich} – in Hochschultexten "
                           "üblich, der Inhalt bleibt gleich.", 0.5, fund=funde[0], ersetzbar=ersetzbar)
        else:
            teile = "; ".join(f"„{fund}“ in {_nr_liste(n_)}" for fund, n_ in nach_fund.items())
            ok = L.hinweis("abkuerzung", None, f"{vorsatz}Abkürzung „{f['kurz']}“: {teile} als „{f['kurz']}“ schreiben – alle Stellen in "
                           "einem Durchgang, einheitlich (in Hochschultexten üblich, der Inhalt bleibt gleich).", 0.5, fund=funde[0],
                           ersetzbar=ersetzbar, anfang=f"abk:{f['kurz']}")
        if ok:
            L.hinweise[-1].update({"funde": funde, "saetze": nrn,
                                   "weitere": [schluessel_anfang(L.nach_nr[n]["text"]) for n in nrn if n in L.nach_nr]
                                   if len(nrn) > 1 else []})
            neu.append(L.hinweise[-1])
    return neu


def abk_selbsthilfe(L: Lauf) -> str | None:
    """Selbsthilfe für Abkürzungen nur mit vorhandenen Langformen (nie einstreuen): die kürzbaren Familien ohne Auftrag."""
    auftrag = {h.get("anfang") for h in L.hinweise if h["typ"] == "abkuerzung"} | \
              {n for h in L.hinweise if h["typ"] == "abkuerzung" for n in h.get("saetze") or [h.get("satz")]}
    teile = []
    for f in abk_plan(L)[0]:
        nrn = list(dict.fromkeys(nr for nr, _p, _f in f["treffer"]))
        if f"abk:{f['kurz']}" in auftrag or set(nrn) <= auftrag:
            continue
        funde = list(dict.fromkeys(fund for _nr, _p, fund in f["treffer"]))
        teile.append(f"{' / '.join(f'„{x}“' for x in funde)} ({_nr_liste(nrn)}) als „{f['kurz']}“")
    if not teile:
        return None
    return "nur die vorhandenen Langformen kürzen, alle Stellen je Abkürzung: " + "; ".join(teile) + " – nichts einstreuen"


# Satzanfang, der auf den Vorsatz antwortet (Gegensatz, Einschränkung, Folgerung, Gleichzeitigkeit): dort beginnt kein neuer
# Absatz („Allerdings ist die dortige Vernetzung …“, „Dennoch wird …“, „Zugleich verpflichtete …“)
ANTWORT_ANFANG_RE = re.compile(r"^(?:allerdings|jedoch|dennoch|trotzdem|doch|aber|gleichzeitig|zugleich|hingegen|dagegen|stattdessen|"
                               r"vielmehr|gleichwohl|indes|insofern|folglich|somit|also|nichtsdestotrotz|umgekehrt|andererseits)\b",
                               re.IGNORECASE)
# Rückverweis-Adjektive („die dortige Vernetzung“, „der beschriebenen Aspekte“) und Ordnungszahl ohne Nomen („Die erste besagt …“)
RUECKVERWEIS_ADJ_RE = re.compile(r"\b(?:dortige|derartige|obige|vorgenannte|genannte|beschriebene|erwähnte|skizzierte)[nmrs]?\b"
                                 r"|^(?:die|der|das)\s+(?:erste|zweite|dritte|vierte|letzte)\s+(?-i:[a-zäöüß])", re.IGNORECASE)
# Kurzer Ankündigungssatz (≤ KURZ_ANKUENDIGUNG_MAX Wörter): Kopula + Theorie- bzw. Begriffsname, „von zentraler Bedeutung“, „spielt
# eine wichtige Rolle“, „… geht auf X zurück.“ – die Erläuterung folgt im nächsten Satz, dort beginnt kein neuer Absatz
KURZ_ANKUENDIGUNG_MAX = 12
_THEORIE = r"\w*(?:[Tt]heorie|[Aa]nsatz|[Mm]odell|[Kk]onzept|[Bb]egriff|[Pp]rinzip|[Pp]aradigma|[Pp]erspektive|[Mm]odelle|[Tt]heorien)\w*"
KURZ_ANKUENDIGUNG_RE = re.compile(
    r"\bvon\s+(?:zentraler|großer|besonderer|entscheidender|wesentlicher|grundlegender|herausragender)\s+Bedeutung\b"
    r"|\b(?:eine|die)\s+(?:\w+\s+)?Rolle\s+(?:spielt|spielen|spielte|spielten)\b"
    r"|\b(?:spielt|spielen|spielte|spielten)\s+(?:dabei\s+|hier\s+)?(?:eine|die)\s+(?:\w+\s+)?Rolle\b"
    r"|\bzurück\.\s*$"
    rf"|\b(?:ist|sind|war|waren|bildet|bilden|liefert|liefern|bietet|bieten)\b[^.]*\b{_THEORIE}\b"
    rf"|\b{_THEORIE}\s+(?:nach|von)\s+[A-ZÄÖÜ]")
# Kontrast-Antwort in den ersten drei Wörtern („Neu ist jedoch …“) nach einem Satz mit „nicht“/„kein“
KONTRAST_KOPF_RE = re.compile(r"\b(?:jedoch|aber|allerdings|hingegen|dagegen|vielmehr)\b", re.IGNORECASE)
# Beispielsatz („Bekannt geworden ist ein Fall …“, „Ein Beispiel …“, „So …“, „etwa“ in den ersten Wörtern)
ABSATZ_BEISPIEL_RE = re.compile(r"^(?:Bekannt\s+(?:geworden\s+)?(?:ist|sind|wurde|wurden)|Ein\s+(?:\w+\s+)?(?:Fall|Beispiel)\b|"
                                r"Als\s+Beispiel|So\s)")
BEISPIEL_KOPF_RE = re.compile(r"\b(?:etwa|beispielsweise|zum\s+Beispiel|z\.\s?B\.)\b")
# Vorsatz endet mit einer Aufzählungsankündigung („… ergeben sich zwei Hypothesen.“, „… folgende Gründe:“)
ANKUENDIGUNG_ENDE_RE = re.compile(r"\b(?:zwei|drei|vier|fünf|sechs|mehrere[n]?|folgende[n]?|verschiedene[n]?)\s+(?:[a-zäöüß][\w-]*\s+)?"
                                  r"[A-ZÄÖÜ][\w-]*\s*[.:]?\s*$")


def _teilt_begriff(x: str, y: str) -> bool:
    """Gleicher Begriff zweier Inhaltswörter, auch über Komposita: gleicher Stamm, gemeinsames Bestimmungswort (Präfix ≥ 6
    bzw. ein Wort ist das Bestimmungswort des anderen: „Nachfrage“ – „Nachfrageschwankungen“ – „nachfragestarken“) oder
    gemeinsames Grundwort („Datenqualität“ – „Servicequalität“)."""
    if x == y or x[:9] == y[:9]:
        return True
    p = _gemeinsam_vorne(x, y)
    if p >= 6 or (p >= 5 and p == min(len(x), len(y)) and x[:p] not in _PARTIKEL_PRAEFIX):
        return True
    return gemeinsames_grundwort(_grund(x), _grund(y))


def begriffs_ueberlappung(L: Lauf, a: list[dict], b: list[dict]) -> float:
    """Anteil der Inhaltswörter (≥ 5 Zeichen) zweier Satzgruppen, die einen Begriff mit der anderen Gruppe teilen – Komposita
    werden über Bestimmungs- und Grundwort zerlegt (0 = kein gemeinsamer Begriff, 1 = alles gemeinsam)."""
    wa = set().union(*(L.begriffe_info[s["nr"]].get("roh", set()) for s in a)) if a else set()
    wb = set().union(*(L.begriffe_info[s["nr"]].get("roh", set()) for s in b)) if b else set()
    if not wa or not wb:
        return 0.0
    ta = {x for x in wa if any(_teilt_begriff(x, y) for y in wb)}
    tb = {y for y in wb if any(_teilt_begriff(x, y) for x in wa)}
    return (len(ta) + len(tb)) / (len(wa) + len(wb))


# Beleg, der auf die Quelle davor verweist (ssoar-66043 S13: wörtliches Zitat mit „(ders.)“ direkt nach dem Zitat derselben Person)
QUELLE_WIE_VORHER_RE = re.compile(r"\(\s*(?:vgl\.\s*)?(?:ebd\.?|ebenda|ders\.|dies\.|a\.\s?a\.\s?O\.)(?=\s*(?:[,;)]|S\.|\d))")
# Absatz teilen: Rückbezug („dies“, „diese“, „beide“) oder Gegensatz („allerdings“, „jedoch“) in den ersten sieben Wörtern
ABSATZ_RUECKBEZUG_RE = re.compile(r"\b(?:dies|diese[rsmn]?|beide[rsmn]?)\b", re.IGNORECASE)
ABSATZ_KONTRAST_RE = re.compile(r"\b(?:allerdings|jedoch|hingegen|dagegen|indes|demgegenüber|gleichwohl)\b", re.IGNORECASE)
# kurzer Themensatz, der einen neuen Aspekt ankündigt („Eine weitere Chance besteht in …“, „Ein zweiter Grund ist …“)
THEMENSATZ_RE = re.compile(r"^(?:Ein|Eine|Einen)\s+(?:weitere[nrs]?|zweite[nrs]?|dritte[nrs]?|andere[nrs]?|letzte[nrs]?)\s+[A-ZÄÖÜ]")
# Satz, der nur auf das Folgende verweist: als Ein-Satz-Absatz hinge er in der Luft
IM_FOLGENDEN_RE = re.compile(r"\b(?:im\s+Folgenden|nachfolgend|im\s+nächsten\s+(?:Abschnitt|Kapitel)|im\s+weiteren\s+Verlauf)\b",
                             re.IGNORECASE)
_DEFINIT = {"der", "die", "das", "den", "dem", "des"}


def definites_rueckbezug_nomen(L: Lauf, kopf: str, vor: dict) -> bool:
    """Definites Nomen in den ersten Wörtern, das den Vorsatz aufnimmt: ein Kapselwort („der Ansatz“, „die Entwicklung“) oder ein
    Nomen, dessen Grundform im Vorsatz steht („die Preissetzung“ nach „… dynamische Preissetzung …“)."""
    toks = [t for t in analyse.tokens(kopf) if analyse.ist_wort(t)]
    vor_g = {_grund(t.lower()) for t in analyse.tokens(L.masken.get(vor["nr"], vor["text"]))
             if t[:1].isupper() and analyse.ist_wort(t) and t.lower() not in analyse.FUNKTIONSWOERTER}
    # nur das erste definite Nomen im Vorfeld (Artikel unter den ersten drei Wörtern: „Der Ansatz …“, „Für das Controlling …“) –
    # ein wiederholtes Nomen tiefer im Satz ist gewöhnliche Themenfortführung
    i = next((j for j, t in enumerate(toks[:3]) if t.lower() in _DEFINIT), None)
    if i is None:
        return False
    for w in toks[i + 1:i + 4]:
        if w[:1].isupper() and w.lower() not in analyse.FUNKTIONSWOERTER:
            return ist_kapselwort(w) or _grund(w.lower()) in vor_g
        if w.lower() in analyse.FUNKTIONSWOERTER:
            break
    return False


def _absatz_trennbar(L: Lauf, liste: list[dict], k_: int) -> bool:
    """Darf vor liste[k_] ein neuer Absatz beginnen? Nicht im Zitat, nicht vor Aufzählung, Anapher, Rückverweis (auch im Beleg:
    „ders.“, „ebd.“) oder einem Satz, der auf den Vorsatz antwortet („Allerdings …“), nicht nach einer Aufzählungsankündigung, nicht mitten in einer
    Aufzählung (erstens … zweitens), nicht nach einem Doppelpunkt."""
    s, vor = liste[k_], liste[k_ - 1]
    if not L.nutzbar(s):
        return False
    if any(s["nr"] in (h.get("weitere_nr") or []) for h in L.hinweise):
        return False  # Satz soll in diesem Durchgang mit dem vorigen verbunden werden (Bündeln, Zickzack, Strohmann-Paar)
    mv, ms = L.masken[vor["nr"]].rstrip(), L.masken[s["nr"]][fuehrende_quelle(s["text"]):].lstrip()
    if mv[-1:] == MASKE and ms[:1] == MASKE:
        return False  # mitten in einem wörtlichen Zitat
    if vor["text"].rstrip().endswith(":") or ANKUENDIGUNG_ENDE_RE.search(vor["text"]):
        return False
    anf = s["text"].lstrip("„\"(»")
    kopf = " ".join(anf.split()[:6])
    if AUFZAEHLUNG_RE.match(anf) or ANAPHER_RE.match(anf) or RUECKVERWEIS_RE.search(kopf) or ANTWORT_ANFANG_RE.match(anf) \
            or RUECKVERWEIS_ADJ_RE.search(kopf):
        return False
    # rhetorische Bindungen, die der Begriffsüberlapp nicht sieht (v4: Employer S17/18, CSRD S3/4, DP S33/34): nach einem kurzen
    # Ankündigungssatz, vor der Antwort auf einen „nicht“-Satz („Neu ist jedoch …“) und vor einem Beispiel
    if vor["woerter"] <= KURZ_ANKUENDIGUNG_MAX and KURZ_ANKUENDIGUNG_RE.search(L.masken[vor["nr"]].rstrip()):
        return False
    if KONTRAST_KOPF_RE.search(" ".join(anf.split()[:3])) and re.search(r"\b(?:nicht|kein\w*)\b", L.masken[vor["nr"]], re.IGNORECASE):
        return False
    if BEISPIEL_ANFANG_RE.match(anf) or ABSATZ_BEISPIEL_RE.match(anf) or BEISPIEL_KOPF_RE.search(" ".join(anf.split()[:4])):
        return False
    if QUELLE_WIE_VORHER_RE.search(s["text"]):
        return False  # „(ders.)“, „(ebd., S. 12)“: der Beleg verweist auf die Quelle des Vorsatzes – am Absatzanfang ginge der Bezug verloren
    # Rückbezug oder Gegensatz in den ersten sieben Wörtern („Für das Controlling bedeutet dies allerdings …“) bzw. ein definites
    # Nomen, das den Vorsatz aufnimmt („Der Ansatz …“, „Die Preissetzung …“ nach einem Satz über Preissetzung): der Satz antwortet
    # auf den Vorsatz und beginnt keinen neuen Gedanken (v6-Prüfung: 3 von 7 Teilungen strukturell falsch)
    kopf7 = " ".join(L.masken[s["nr"]][fuehrende_quelle(s["text"]):].split()[:7])
    if ABSATZ_RUECKBEZUG_RE.search(kopf7) or ABSATZ_KONTRAST_RE.search(kopf7) or definites_rueckbezug_nomen(L, kopf7, vor):
        return False
    themensatz = [THEMENSATZ_RE.match(x["text"].lstrip("„\"(»")) and x["woerter"] <= 20 for x in (vor, liste[0])]
    if themensatz[0] or (themensatz[1] and len(liste) <= 6):
        # kurzer Themensatz („Eine weitere Chance besteht in …“) direkt davor oder am Absatzanfang: der Rest des Absatzes begründet
        # ihn und gehört dazu (v6-Prüfung: DP vor S14 trennte den Themensatz von seiner Begründung)
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
            ueb = {k_: begriffs_ueberlappung(L, liste[max(0, k_ - 2):k_], liste[k_:k_ + 2]) for k_ in stellen}
            # Ein-Satz-Kopf (vor dem zweiten Satz teilen) nur, wenn der erste Satz mehr mit dem vorigen Absatz teilt als mit dem
            # Rest seines Absatzes – ein kurzer Erstsatz („Die Entwicklung ist seitdem allerdings in Bewegung geraten.“) ist sonst
            # der Themensatz des Folgenden
            if 1 in stellen:
                vorig = L.absaetze.get(nr - 1) if i > 0 and nrs[i - 1] == nr - 1 else None
                kopf = liste[0]["text"].lstrip("„\"(»")
                ueberleitung = bool(AUFZAEHLUNG_RE.match(kopf) or ORDINAL_RE.match(kopf)
                                    or _AUFZAEHL_WORT_RE.search(" ".join(kopf.split()[:8])))
                if not vorig or ueberleitung or begriffs_ueberlappung(L, liste[:1], vorig[-2:]) \
                        <= begriffs_ueberlappung(L, liste[:1], liste[1:3]) + 0.05:
                    stellen = [k_ for k_ in stellen if k_ != 1]  # „Drittens …“, „Darüber hinaus …“: leitet das Folgende ein
            # ebenso ein Ein-Satz-Schluss (vor dem letzten Satz teilen): nur, wenn der Satz mehr mit dem nächsten Absatz teilt
            if len(liste) - 1 in stellen and len(liste) > 2:
                naechst = L.absaetze.get(nr + 1) if i + 1 < len(nrs) and nrs[i + 1] == nr + 1 else None
                if not naechst or begriffs_ueberlappung(L, liste[-1:], naechst[:2]) \
                        <= begriffs_ueberlappung(L, liste[-1:], liste[-3:-1]) + 0.05:
                    stellen = [k_ for k_ in stellen if k_ != len(liste) - 1]
            varianten = [(k_,) for k_ in stellen]
            if wl[i] > 500:  # sehr langer Absatz: auch zwei Trennstellen in einem Umbau (Teile ≥ 3 Sätze)
                varianten += [(a, b) for a in stellen for b in stellen if b - a >= 3 and a >= 3 and len(liste) - b >= 3]
            for grenzen in varianten:
                g = (0,) + grenzen + (len(liste),)
                teile = [liste[x:y] for x, y in zip(g, g[1:])]
                if any(len(t) == 1 and IM_FOLGENDEN_RE.search(L.masken.get(t[0]["nr"], t[0]["text"])) for t in teile):
                    continue  # Ein-Satz-Absatz, der nur auf das Folgende verweist (v6-Prüfung: DP vor S6, „… weshalb im Folgenden …“)
                extra = sim[i] - anz[i]  # Satz-Aufträge in diesem Absatz: dem letzten Teil zurechnen (Näherung)
                neu_anz = sim[:i] + [len(t) for t in teile[:-1]] + [max(1, len(teile[-1]) + extra)] + sim[i + 1:]
                neu_wl = wl[:i] + [sum(s["woerter"] for s in t) for t in teile] + wl[i + 1:]
                r = bewerte(neu_anz, neu_wl)
                if r:
                    guete = 1.0 - max(ueb[k_] for k_ in grenzen)
                    kand.append((r[0], "teilen", i, grenzen, guete, r[1]))
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
                guete = begriffs_ueberlappung(L, L.absaetze[x][-2:], L.absaetze[y][:2])
                kand.append((r[0], "zusammen", i, gemeinsam, guete, r[1]))
    if not kand:
        return
    # unter den Kandidaten mit ausreichendem Gewinn (bewerte) zuerst nach Thema – Teilen an einem Einschnitt mit wenig
    # Überlappung, Zusammenlegen bei gemeinsamem Thema (Komposita zerlegt) –, erst dann nach dem Gewinn an Variation
    def thema(k):
        return round(10 * (k[4] if k[1] == "teilen" else min(1.0, 3 * k[4])))
    wert, art, i, info, guete, neu = max(kand, key=lambda k: (thema(k), k[0], -k[2]))
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
        if L.hinweis("absatz_teilen", liste[info[0]], f"Absatz {nr} ({anz[i]} Sätze): {wo} einen neuen Absatz beginnen – danach {teile} "
                     f"Sätze.{thema}{grund}", 1.0, absatz=nr):
            L.hinweise[-1]["absatz_cv"] = [round(alt["cv"], 4), round(neu["cv"], 4)]
    else:
        x, y = nrs[i], nrs[i + 1]
        wort = next((t for s in L.absaetze[y] for t in analyse.tokens(s["text"]) if analyse.ist_wort(t) and t[:1].isupper()
                     and analyse.stamm(t) in info and t.lower() not in analyse.FUNKTIONSWOERTER), None)
        thema = f" – beide behandeln „{wort}“" if wort else ""
        # erster Satz von Absatz y als Schlüssel: so erkennt das Gedächtnis ein späteres Teilen an derselben Stelle als Pendeln
        if L.hinweis("absatz_zusammen", L.absaetze[y][0], f"Absatz {x} und {y} ({anz[i]} + {anz[i + 1]} Sätze) zusammenlegen{thema}.{grund}",
                     0.9, absatz=x):
            L.hinweise[-1]["absatz_cv"] = [round(alt["cv"], 4), round(neu["cv"], 4)]


def _vorgaben(L: Lauf) -> None:
    """Nutzer-Vorgaben (immer, außerhalb von Zitaten): generisches Maskulinum, keine Gedankenstriche."""
    _gender(L)
    _striche(L)


def _gender_maskulin_saetze(L: Lauf, maskulin: str, schl: str) -> list[int]:
    """Sätze, in denen die Maskulinform außerhalb wörtlicher Zitate schon steht (Teilumsetzung)."""
    stamm = GENDER_MASKULIN.get(schl, (None, None))[1] or maskulin.split("-")[-1]
    stamm_re = re.compile(r"(?<![\w-])" + re.escape(gender_schluessel(stamm)) + r"(?:e|en|er|ern|n|s)?(?![\wäöüß*:_/-])",
                          re.IGNORECASE)
    schon = []
    for x in L.saetze:
        mk = L.masken.get(x["nr"], x["text"])
        belegt = [(f["start"], f["start"] + len(f["wort"])) for f in gender_funde(mk)]
        if any(not any(a <= t.start() < e for a, e in belegt) for t in stamm_re.finditer(mk)):
            schon.append(x["nr"])
    return schon


def _gender(L: Lauf) -> None:
    """Ein Hinweis je Wortstamm mit allen Satznummern im ganzen Text und der abgeleiteten Maskulinform (Vorgabe, ändert den
    Score nicht); steht die Maskulinform schon im Text (Teilumsetzung), wird daraus ein Vereinheitlichungsauftrag. Gezählt wird
    nur außerhalb wörtlicher Zitate: Stehen alle Restformen in Zitaten, gibt es keinen Auftrag, sondern die Info „Rest steht in
    wörtlichen Zitaten – so lassen“. Zielformen im Hochschulkontext: „Lehrende“ → „Lehrkräfte“ oder „Dozenten“ (nie „Lehrer“),
    unbekannte Formen „eine passende maskuline Bezeichnung“."""
    gruppen: dict[str, dict] = {}
    im_zitat: dict[str, dict] = {}
    for s in L.saetze:
        if s["woerter"] < MIN_WOERTER:
            continue
        mk = L.masken[s["nr"]]
        eigen = gender_funde(mk) if L.nutzbar(s) else []
        for f in eigen:
            g = gruppen.setdefault(f["schluessel"], {"formen": Counter(), "saetze": [], "maskulin": f["maskulin"], "im_fokus": False})
            g["formen"][f["wort"]] += 1
            if s["nr"] not in g["saetze"]:
                g["saetze"].append(s["nr"])
            g["im_fokus"] |= L.von <= s["nr"] <= L.bis
        for f in gender_funde(s["text"]):
            if MASKE in mk[f["start"]:f["start"] + len(f["wort"])]:
                z = im_zitat.setdefault(f["schluessel"], {"formen": Counter(), "saetze": [], "maskulin": f["maskulin"]})
                z["formen"][f["wort"]] += 1
                if s["nr"] not in z["saetze"]:
                    z["saetze"].append(s["nr"])
    L.gender_info = []
    for schl, z in sorted(im_zitat.items(), key=lambda x: x[1]["saetze"][0]):
        if schl in gruppen or not any(L.von <= n <= L.bis for n in z["saetze"]):
            continue
        # alle Restformen stehen in wörtlichen Zitaten: kein Auftrag; als Info nur, wenn der eigene Text schon umgestellt ist
        vorher_genannt = any(("gender", f"gender:{schl}") in schl_ for _, schl_ in L.frueher)
        if vorher_genannt or (z["maskulin"] and _gender_maskulin_saetze(L, z["maskulin"], schl)):
            wort = z["formen"].most_common(1)[0][0]
            L.gender_info.append(f"„{wort}“ steht nur noch in wörtlichen Zitaten ({_nr_liste(z['saetze'])}) – Rest steht in wörtlichen "
                                 "Zitaten, so lassen.")
    for schl, g in sorted(gruppen.items(), key=lambda x: x[1]["saetze"][0]):
        if not g["im_fokus"]:
            continue  # gemeldet wird, wenn der Abschnitt mit dieser Form im Fokus ist
        wort = g["formen"].most_common(1)[0][0]
        nrn = g["saetze"]
        wo = f"in Satz {nrn[0]}" if len(nrn) == 1 else f"in Satz {', '.join(map(str, nrn[:-1]))} und {nrn[-1]}"
        weitere_formen = [w for w in g["formen"] if w != wort]
        formen = f"„{wort}“" + (f" (auch {', '.join(f'„{w}“' for w in weitere_formen[:2])})" if weitere_formen else "")
        ziel = f"„{g['maskulin']}“" if g["maskulin"] else (GENDER_ZIELTEXT.get(schl) or GENDER_UNBEKANNT)
        misch = ""
        if g["maskulin"]:
            schon = _gender_maskulin_saetze(L, g["maskulin"], schl)
            if schon:
                misch = (f" Die Maskulinform steht schon in Satz {', '.join(map(str, schon[:4]))}{' …' if len(schon) > 4 else ''}: "
                         "Mischform, alle Stellen außerhalb wörtlicher Zitate auf eine Form bringen.")
        z = im_zitat.get(schl)
        if z:
            misch += f" In wörtlichen Zitaten ({_nr_liste(z['saetze'])}) bleibt die Form stehen."
        s0 = L.nach_nr[nrn[0]] if len(nrn) == 1 else None
        if s0:
            text_ = f"{zitat(s0)}: {formen} → {ziel} (Vorgabe generisches Maskulinum).{misch}"
        else:
            text_ = f"{formen} {wo} → {ziel} (Vorgabe generisches Maskulinum), im ganzen Text einheitlich.{misch}"
        # Partizip- bzw. Zeichenformen und Maskulinform als „ersetzbar“: inhalt_check wertet die verlangte Umstellung dann
        # nicht als verschwundenen Begriff („bewerbend“); die neue Form als „erwartet“ (kein neuer Begriff)
        if g["maskulin"]:
            erwartet = [g["maskulin"].lower(), g["maskulin"].split("-")[-1].lower()]
        elif schl in GENDER_ZIELTEXT:
            erwartet = [w.lower() for w in re.findall(r"„([^“]+)“", GENDER_ZIELTEXT[schl]) if w.lower() != "lehrer"]
        else:
            erwartet = []
        ersetzbar = list(g["formen"]) + ([g["maskulin"]] if g["maskulin"] else []) + erwartet
        if L.hinweis("gender", s0, text_, 1.5, absatz=s0["absatz"] if s0 else None, fund=wort, anfang=f"gender:{schl}",
                     ersetzbar=ersetzbar):
            L.hinweise[-1]["saetze"] = nrn
            L.hinweise[-1]["erwartet"] = sorted(set(erwartet) | {gender_schluessel(w) for w in erwartet})


def _konsistenz(L: Lauf) -> None:
    """Mischformen nach Ersetzungen: Hat der Coach in einer Vorrunde eine Form zum Ersetzen genannt (Abkürzung, Synonym) und
    stehen jetzt Kurz- und Langform bzw. beide Synonyme nebeneinander („ca.“ neben „etwa“, „Kunden“ neben „Konsumenten“), gibt
    es einen einzigen Vereinheitlichungsauftrag. Mischformen, die der Coach nicht angestoßen hat, bleiben unberührt (auch
    echte Arbeiten wechseln); Gender-Mischformen nennt der Gender-Auftrag selbst."""
    frueher = {w for mess in L.messungen for e in (mess.get("ersetzbar") or []) for w in re.findall(r"[\wäöüß]+", str(e).lower())}
    if not frueher:
        return
    faelle, formen = [], set()
    for kurz, (rx_k, rx_l) in ABK_FAMILIEN.items():
        k_nr, l_nr, l_funde = [], [], []
        for s in L.fokus:
            mk = L.masken.get(s["nr"], s["text"])
            if rx_k.search(mk):
                k_nr.append(s["nr"])
            for m in rx_l.finditer(mk):
                if m.start() <= len(mk) - len(mk.lstrip("„\"(»")):
                    continue  # am Satzanfang bleibt die Langform („Beispielsweise …“, nie „Z. B. …“): keine Mischform
                l_nr.append(s["nr"])
                l_funde.append(m.group(0))
        if not (k_nr and l_nr) or not any(w in frueher for f in l_funde for w in re.findall(r"[\wäöüß]+", f.lower())):
            continue
        lang = sorted({f.lower() for f in l_funde})
        faelle.append(f"„{kurz}“ ({_nr_liste(k_nr)}) neben {' / '.join(f'„{f}“' for f in lang)} ({_nr_liste(l_nr)})")
        formen.update(lang)
    syn_jetzt = {h["anfang"] for h in L.hinweise if h["typ"] == "synonyme"}
    for c in synonym_cluster(L.fokus, L.masken):
        varianten = synonym_varianten(L, c)  # ohne geschützte Einzelform (Rechtsbegriff, Gleichsetzung)
        if len(varianten) < 2:
            continue
        v_formen = sorted({f for w, _ in varianten for f in c.get("formen_je", {}).get(w, [w.lower()])})
        if not any(f in frueher for f in v_formen):
            continue
        schl = "syn:" + "|".join(sorted(w.lower() for w, _ in varianten))
        if schl in syn_jetzt:
            continue  # der Synonym-Auftrag dieser Runde nennt den Fall schon
        teile = [f"„{w}“ ({_nr_liste(c['saetze'].get(w, []))})" for w, _ in varianten]
        faelle.append(" neben ".join(teile))
        formen.update(v_formen)
    if faelle:
        L.hinweis("konsistenz", None, "Uneinheitlich nach den Ersetzungen: " + "; ".join(faelle) + ". Je Fall eine Form wählen und im "
                  "ganzen Text einheitlich verwenden (bei Abkürzungen ist die Kurzform üblich, bei Fachbegriffen die Form der Quelle).",
                  1.2, ersetzbar=sorted(formen), anfang="konsistenz:" + "|".join(sorted(formen)))


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
            L.hinweis("gedankenstrich", s, f"{zitat(s)}: {strich_technik(mk)}", 0.8, fund="–")


_KEIN_VERB_DAVOR = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "einem", "einen", "eines", "zur", "zum", "im", "am",
                    "vom", "beim", "ins", "mit", "von", "zu", "für", "auf", "in", "aus", "bei", "nach", "über", "unter", "vor", "durch",
                    "gegen", "ohne", "um", "seine", "seiner", "seinen", "seinem", "ihre", "ihrer", "ihren", "ihrem", "diese", "dieser",
                    "diesen", "diesem", "dieses", "jede", "jeder", "jeden", "jedem", "alle", "allen", "viele", "vielen", "keine",
                    "keiner", "keinen", "per", "sowie", "und", "oder", "möglichst", "sehr", "besonders"}


_NACH_VERB = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "sich", "es", "nicht", "auch", "nur",
              "noch", "schon", "sie", "ihn", "ihm", "uns", "mich", "dich"}


def hat_finites_verb(teil: str) -> bool:
    """Steht in einem Satzteil ein finites Verb? Hilfs-/Modalverben und häufige Vollverben (analyse.FINIT) sicher; sonst ein
    kleingeschriebenes Inhaltswort mit Verbendung, das weder nach einem Artikel bzw. einer Präposition noch direkt vor einem Nomen
    steht („der sozialen Medien“ ist kein Verb). Grundlage für „Aufzählung oder Erklärung“ (kein Verb) nach „;“ bzw. „–“."""
    toks = [t for t in analyse.tokens(teil) if analyse.ist_wort(t)]
    for i, t in enumerate(toks):
        low = t.lower()
        if low in analyse.FINIT or low in analyse.FINIT_MEHRDEUTIG:
            return True
        if not t.islower() or low in analyse.FUNKTIONSWOERTER or len(low) < 4 or not re.search(r"(?:t|te|ten|en|st|ern|eln)$", low):
            continue
        folgt_artikel = i + 1 < len(toks) and toks[i + 1].lower() in _NACH_VERB
        if i > 0 and toks[i - 1].lower() in _KEIN_VERB_DAVOR and not folgt_artikel:
            continue  # „der sozialen …“; aber „das belastet die …“: Pronomen, Verb, Artikel
        if i + 1 < len(toks) and toks[i + 1][:1].isupper():
            continue
        return True
    return False


_EINSCHUB_NS_RE = re.compile(r",\s*(?:(?:in|an|auf|aus|bei|mit|nach|von|vor|zu|für|über|unter|durch|gegen|um)\s+)?(?:der|die|das|dem|den|"
                             r"deren|dessen|denen|welche[rsmn]?|wo|wie|was|dass|weil|da|wenn|als|ob|obwohl|während)\b[^,;]*(?:,|$)",
                             re.IGNORECASE)
AUFZAEHL_ANFANG_RE = re.compile(r"^\s*(?:einerseits|zum\s+einen|erstens|sowohl|nämlich|und\s+zwar|etwa|beispielsweise|insbesondere|"
                                r"vor\s+allem|darunter|z\.\s?B\.)\b", re.IGNORECASE)


def aufzaehlung_ohne_verb(rest: str) -> bool:
    """Folgt eine Aufzählung bzw. Erklärung ohne eigenes Verb? Eingeschobene Neben- und Relativsätze („…, in der … verfolgt wird,
    sowie …“) zählen nicht; ein Aufzählungsanfang („einerseits“, „zum einen“, „nämlich“) genügt."""
    if AUFZAEHL_ANFANG_RE.match(rest):
        return True
    kern = _EINSCHUB_NS_RE.sub(" ", rest)
    kern = re.sub(r"\b(?:und|oder|sowie)\s+(?:wie|dass|ob|was|warum|wo|wann|inwiefern|inwieweit)\b[^,;]*", " ", kern, flags=re.IGNORECASE)
    return bool(kern.strip()) and not hat_finites_verb(kern)


def strich_technik(mk: str) -> str:
    """Ersatz für Gedankenstriche nach ihrer Funktion: paariger Einschub („– wie oben angeführt –“) → Klammer oder Kommas;
    einzelner Strich vor einer Aufzählung oder Erklärung ohne eigenes Verb („ausgewählt – einerseits Amsterdam … sowie …“) →
    Doppelpunkt; sonst Komma oder neuer Satz."""
    striche = list(analyse.GEDANKENSTRICH_RE.finditer(mk))
    if len(striche) >= 2:
        return "den Einschub zwischen den Gedankenstrichen in Klammern oder zwischen Kommas setzen (Vorgabe: keine Gedankenstriche)."
    rest = mk[striche[0].end():] if striche else ""
    erstes = (analyse.tokens(rest) or [""])[0].lower()
    if rest.strip() and not hat_finites_verb(rest) and erstes in analyse.PRAEPOSITIONEN | {"im", "am", "zum", "zur", "beim", "vom"}:
        return ("Gedankenstrich durch ein Komma ersetzen oder den Zusatz in Klammern setzen (Vorgabe: keine Gedankenstriche).")
    if rest.strip() and aufzaehlung_ohne_verb(rest):
        return ("Gedankenstrich durch einen Doppelpunkt ersetzen – danach folgt eine Aufzählung bzw. Erklärung (Vorgabe: keine "
                "Gedankenstriche).")
    return "Gedankenstrich durch Komma oder einen neuen Satz ersetzen (Vorgabe: keine Gedankenstriche)."


def _gegenfolie_satz(L: Lauf, a: str | None) -> dict | None:
    """Satz einer früheren Gegenfolie, auch wenn „nicht nur“ inzwischen fehlt („solche systeme können nicht nur strukturierte“ →
    „Solche Systeme können strukturierte …“): exakt, sonst der einzige Satz mit denselben ersten vier Wörtern ohne die Gradpartikel."""
    if not a:
        return None
    s = L.anfang_index.get(a)
    if s is not None:
        return s
    kopf = [w for w in a.split() if w not in ("nicht", "nur", "allein", "bloß", "lediglich")][:4]
    if len(kopf) < 3:
        return None
    treffer = [x for k, x in L.anfang_index.items() if k.split()[:len(kopf)] == kopf]
    return treffer[0] if len(treffer) == 1 else None


def _neu_geteilt(L: Lauf) -> None:
    """Sätze, die erst durch einen befolgten Teilen-, Mitte- oder Herauslöse-Auftrag der Vorrunde entstanden sind: der Satz
    nach dem (kürzer gewordenen) Ausgangssatz im selben Absatz. Sie bekommen keine Anknüpfungs- und Begriffsaufnahme-Aufträge
    (höchstens „Folge des Teilens: Bezugsnomen statt Pronomen“)."""
    for h in (h for mess in L.messungen for h in mess.get("hinweise") or []):  # auch frühere Runden: der Satz bleibt eine Folge
        if isinstance(h, dict) and "gegenfolie" in (h.get("typen") or [h.get("typ")]) and h.get("technik") in (None, "hauptsaetze"):
            # „nicht nur X, sondern auch Y“ als zwei Hauptsätze umgesetzt: der zweite Satz ist eine Folge des eigenen Auftrags –
            # keine Anknüpfungs-Rüge dafür (v6-Prüfung: Controlling S32 → S34 „Sie können auch …“)
            s = _gegenfolie_satz(L, h.get("anfang"))
            nxt = L.nach_nr.get(s["nr"] + 1) if s else None
            if s and nxt and nxt["absatz"] == s["absatz"] and h.get("laenge") and s["woerter"] <= h["laenge"] - 4 \
                    and re.search(r"\bauch\b", nxt["text"]) and not re.search(r",\s*sondern\b", s["text"]):
                L.neu_geteilt.setdefault(nxt["nr"], "gegenfolie")
            continue
        if not isinstance(h, dict) or h.get("typ") not in ("teilen", "mitte", "kommas"):
            continue
        if h.get("typ") == "kommas" and h.get("variante") not in (None, "herausloesen"):
            continue
        if lokal_wirksam(L, h) is not True:
            continue
        s = L.anfang_index.get(h.get("anfang"))
        nxt = L.nach_nr.get(s["nr"] + 1) if s else None
        if nxt and nxt["absatz"] == s["absatz"]:
            L.neu_geteilt[nxt["nr"]] = h["typ"]


# Kürzende Aufträge ohne Längenziel: geschätzte Kürzung in Wörtern (Länge der gefundenen Wendung bzw. fester Wert)
KUERZUNG = {"fw_ankuendigung": None, "floskel": None, "konnektor": 1, "fw_zeigt": 1, "fw_ergibt": 1, "fw_lassen": 1, "fw_dass": 1}


# Artikel für den Rückbezug auf ein Befund-Nomen („Aus den Ergebnissen folgt: …“)
_RUECKBEZUG_ARTIKEL = {"befund": "dem Befund", "befunde": "den Befunden", "befunden": "den Befunden", "ergebnisse": "den Ergebnissen",
                       "ergebnissen": "den Ergebnissen", "analyse": "der Analyse", "befragung": "der Befragung",
                       "interviews": "den Interviews", "studie": "der Studie", "fallstudie": "der Fallstudie",
                       "untersuchung": "der Untersuchung", "daten": "den Daten", "auswertung": "der Auswertung"}


def auftrag_logit(L: Lauf, h: dict) -> float:
    """Geschätzter Δ-Logit eines kürzenden Wort-Auftrags im Modell: Funktionswort-Umbau über den simulierten LLR-Gewinn, Floskel über
    das Mustergewicht; Konnektoren sind kein Modellmerkmal (0)."""
    modell = L.ts.get("modell") or {}
    koef, sd = modell.get("koeffizienten") or {}, modell.get("sd") or {}
    if h["typ"] in FW_TYPEN and h.get("fw_delta") and sd.get("fw_profil_llr_pro_1000"):
        return koef["fw_profil_llr_pro_1000"] * h["fw_delta"] / sd["fw_profil_llr_pro_1000"]
    if h["typ"] == "floskel" and h.get("muster_gewicht") and sd.get("ki_muster_pro_1000"):
        return -koef["ki_muster_pro_1000"] * (1000.0 * h["muster_gewicht"] / L.tok_fokus) / sd["ki_muster_pro_1000"]
    return 0.0


def _laengenwirkung(L: Lauf) -> None:
    """Längenwirkung kürzender Wort-Aufträge (Ankündigung, Floskel, Konnektor, Funktionswort-Umbau). Fiele ein Satz dadurch aus den
    langen (≥ 30) bzw. fast langen (27–29) Sätzen ins mittlere Band, obwohl lange Sätze fehlen bzw. die Mitte überfüllt ist, bekommt
    der Auftrag keinen Zusatz, der nach der Kürzung nur durch Auffüllen erfüllbar wäre (v4: „Länge halten“ – Agile S42, Controlling S47).
    Stattdessen, je Satz in Auftragsreihenfolge mit der laufenden Länge:
    – Ankündigung: längenneutral durch einen konkreten Rückbezug auf Vorhandenes ersetzen (Kapitel bzw. Befund steht im Text);
    – Konnektor: über das wiederholte Nomen anschließen statt streichen (längenneutral);
    – sonst entfällt der Auftrag, wenn der Satz der einzige lange in seinem Absatz ist; andernfalls bleibt nur der stärkere von beiden:
      der geschätzte Δ-Logit des Auftrags gegen den simulierten Δ-Logit der Satzlängen.
    Die geschätzte Kürzung wird für die Wirkungsprüfung gespeichert."""
    lang50 = L.p_("anteil_lange_saetze", "p50")
    mitt50 = L.p_("anteil_mittlere_saetze", "p50")
    folge = laengen_folge(L.sim)
    n = len(folge) or 1
    lange_fehlen = lang50 is not None and sum(x >= LANG_AB for x in folge) / n < lang50
    mitte_voll = mitt50 is not None and sum(MITTEL_VON <= x <= MITTEL_BIS for x in folge) / n > mitt50
    laufend: dict[int, int] = {}
    weg: list[dict] = []
    for h in list(L.hinweise):
        if h["typ"] not in KUERZUNG or not h.get("satz") or h["satz"] in L.belegt or h["satz"] not in L.fokus_index:
            continue
        s = L.nach_nr[h["satz"]]
        w = laufend.get(s["nr"], h.get("laenge") or s["woerter"])
        cut = KUERZUNG[h["typ"]]
        if cut is None:  # Ankündigung: die ganze Wendung fällt weg (Folgerung: „folgt daraus“ bleibt); Floskel: Ersatz meist zwei
            n_fund = len((h.get("fund") or "").split())  # Wörter kürzer („sowohl … als auch“ → „und“)
            if h["typ"] == "fw_ankuendigung":
                cut = n_fund - 2 if FOLGERUNG_RE.search(h.get("fund") or "") else n_fund
            else:
                cut = min(2, n_fund - 1)
        cut = max(0, cut)
        if not cut:
            continue
        grenze = None
        if w >= LANG_AB and w - cut < LANG_AB and lange_fehlen:
            grenze = LANG_AB
        elif MITTEL_BIS < w < LANG_AB and w - cut <= MITTEL_BIS and mitte_voll:
            grenze = MITTEL_BIS + 1
        if grenze:
            rb = rueckbezug(L, s) if h["typ"] == "fw_ankuendigung" else None
            if rb:
                aus = rb if KAPITEL_RE.fullmatch(rb) else _RUECKBEZUG_ARTIKEL.get(rb.lower(), rb)
                bsp = f"„Aus {aus} folgt: …“" if doppelpunkt_ok(L) else f"„Aus {aus} folgt, dass …“"
                bleibt = "".join(f"; „{b}“ bleibt beim Verb" for b in h.get("behalten") or [])
                h["text"] = (f"{zitat(s)}: „{h['fund']}“ kündigt nur an – längenneutral durch einen konkreten Rückbezug auf "
                             f"„{rb}“ ersetzen ({bsp}){bleibt}; der Inhalt des „dass“-Satzes bleibt vollständig, eine Folgerung bleibt "
                             "eine Folgerung. Nichts Neues ergänzen.")
                h.pop("kern", None)
                h["variante"] = "rueckbezug"
                cut = 0
            elif h["typ"] == "konnektor":
                wort = h.get("fund") or ""
                h["text"] = (f"{zitat(s)}: „{wort}“ nicht ersatzlos streichen (der Satz fiele unter {grenze} Wörter), sondern über das "
                             "wiederholte Nomen aus dem Vorsatz anschließen – das hält die Länge.")
                h.pop("kern", None)
                h["variante"] = "nomen"
                h["streicht"] = []
                cut = 0
            else:
                i = L.fokus_index[s["nr"]]
                andere_lange = any(max(L.sim[L.fokus_index[x["nr"]]] or [0]) >= LANG_AB
                                   for x in L.absaetze.get(s["absatz"], []) if x["nr"] != s["nr"])
                wert, teile = L.laengen_umbau({i: [w - cut]})
                if grenze == LANG_AB and not andere_lange:
                    weg.append(h)
                    L.unterdrueckt["kuerzung_einziger_langer"] += 1
                    continue  # der einzige lange Satz im Absatz: der Auftrag entfällt
                if wert is None or auftrag_logit(L, h) < -teile["logit"]:
                    weg.append(h)
                    L.unterdrueckt["kuerzung_schwaecher_als_laenge"] += 1
                    continue  # die Kürzung kostet an den Satzlängen mehr, als der Auftrag bringt
        h.update({"laengen_alt": [w], "sim": [w - cut]})
        laufend[s["nr"]] = w - cut
    if weg:
        L.hinweise = [h for h in L.hinweise if not any(h is x for x in weg)]


GENANNT = " (schon in Runde {runde} genannt – überspringen, wenn unpassend)"


# Ein Auftrag je Satz: ausgenommen sind Nutzer-Vorgaben sowie Absatz- und Textaufträge (sie ändern keinen Satz)
EINZEL_AUSGENOMMEN = {"gender", "gedankenstrich", "bindestrich", "absatz_teilen", "absatz_zusammen", "synonyme", "konsistenz",
                      "bereinigung"}
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


_DAHER_ALSO_RE = re.compile(r"(?<!nicht )(?:mit\s+)?„daher“\s+oder\s+„also“")
LAENGE_HALTEN_RE = re.compile(r"\s*Länge halten \(mindestens (\d+) Wörter\)[^.]*\.")


def widersprueche_aufloesen(teile: list[dict], satztext: str = "") -> tuple[list[dict], list[str]]:
    """Innere Widersprüche eines kombinierten Auftrags auflösen (Teile in Auftragsreihenfolge):
    – „kürzen“ und „Länge halten (mindestens N Wörter)“, wo N nach der Kürzung nicht mehr erreichbar ist: der Zusatz entfällt;
    – ein Teil streicht ein Wort, das ein anderer ausdrücklich behält („dennoch“ streichen ↔ „dennoch“ bleibt beim Verb):
      der streichende Teil entfällt;
    – zwei Teile schlagen dasselbe Ersatzverb vor (doppeltes Verb): der spätere bekommt die andere Variante oder entfällt;
    – „daher/also“ neben einem konzessiven Adverb („dennoch“) im Satz: die Folgerung über das Verb („folgt“) erhalten.
    Gibt die bereinigten Teile und die Liste der Auflösungen zurück."""
    notiz: list[str] = []
    # „kürzen“ + „Länge halten (mindestens N Wörter)“: nach der Kürzung aller Teile nur durch Auffüllen erfüllbar – der Zusatz entfällt
    kuerzung = sum(max(0, (h.get("laengen_alt") or [0])[0] - (h.get("sim") or [0])[0]) for h in teile
                   if h["typ"] in KUERZUNG and h.get("laengen_alt") and h.get("sim") and len(h["sim"]) == 1)
    w = max((h.get("laenge") or 0) for h in teile) if teile else 0
    bereinigt0 = []
    for h in teile:
        m = LAENGE_HALTEN_RE.search(h.get("kern") or h["text"])
        grenze = h.get("laenge_halten") or (int(m.group(1)) if m else None)
        if grenze and (kuerzung > 0 or h.get("streicht")) and grenze > w - kuerzung:
            h = dict(h, text=LAENGE_HALTEN_RE.sub("", h["text"]), kern=LAENGE_HALTEN_RE.sub("", h.get("kern") or h["text"]))
            h.pop("laenge_halten", None)
            notiz.append(f"„Länge halten“ entfällt: nach der Kürzung (−{kuerzung} Wörter) nur durch Auffüllen erreichbar")
        bereinigt0.append(h)
    teile = bereinigt0
    behalten = {w.lower() for h in teile for w in h.get("behalten") or []}
    out = []
    for h in teile:
        weg = {w.lower() for w in h.get("streicht") or []} & behalten
        if weg:
            notiz.append(f"{TYP_NAME.get(h['typ'], h['typ'])} entfällt: „{'“, „'.join(sorted(weg))}“ bleibt laut anderem Teil stehen")
            continue
        out.append(h)
    gesehen: set[str] = set()
    bereinigt = []
    for h in out:
        v = list(h.get("verben") or [])
        doppelt = [x for x in v if x in gesehen]
        if doppelt:
            rest = [x for x in v if x not in gesehen]
            if not rest:
                notiz.append(f"{TYP_NAME.get(h['typ'], h['typ'])} entfällt: dasselbe Verb („{doppelt[0]}“) schlägt schon ein anderer Teil vor")
                continue
            if h["typ"] == "fw_als" and "→ „ist“ oder „bildet“" in (h.get("kern") or h["text"]):
                ersatz = f"→ „{rest[0]}“ („{doppelt[0]}“ schlägt schon ein anderer Teil vor)"
                h = dict(h, text=h["text"].replace("→ „ist“ oder „bildet“", ersatz),
                         kern=(h.get("kern") or h["text"]).replace("→ „ist“ oder „bildet“", ersatz), verben=rest)
                notiz.append(f"{TYP_NAME.get(h['typ'], h['typ'])}: nur „{rest[0]}“ (kein doppeltes Verb)")
            else:
                notiz.append(f"{TYP_NAME.get(h['typ'], h['typ'])} entfällt: dasselbe Verb („{doppelt[0]}“) schlägt schon ein anderer Teil vor")
                continue
        gesehen.update(v)
        bereinigt.append(h)
    konz = KONZESSIV_RE.search(satztext or "") or next((KONZESSIV_RE.search(w) for w in behalten if KONZESSIV_RE.search(w)), None)
    if konz:
        for i, h in enumerate(bereinigt):
            t = h.get("kern") or h["text"]
            if _DAHER_ALSO_RE.search(t):
                ersatz = f"über das Verb („folgt“; „{konz.group(0).lower()}“ bleibt)"
                bereinigt[i] = dict(h, text=_DAHER_ALSO_RE.sub(ersatz, h["text"]), kern=_DAHER_ALSO_RE.sub(ersatz, t))
                notiz.append("„daher/also“ ersetzt: der Satz enthält ein konzessives Adverb")
    return bereinigt, notiz


def ein_auftrag_je_satz(hinweise: list[dict], texte: dict[int, str] | None = None) -> list[dict]:
    """Höchstens ein Auftrag je Satz (Vorgaben ausgenommen): Treffen mehrere Hinweise denselben Satz – oder einen Satz, der in
    einem Mehrsatz-Auftrag (Bündeln, Strohmann-Paar) aufgeht –, werden sie zu einem Auftrag in fester Reihenfolge
    zusammengefasst; innere Widersprüche löst widersprueche_aufloesen() auf. Ein Strohmann-Paar sperrt alle übrigen Hinweise
    an seinen beiden Sätzen."""
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
            einzel, notiz = widersprueche_aufloesen(teile, (texte or {}).get(anker, ""))
            out.extend(dict(x, aufgeloest=notiz) if notiz else x for x in einzel)
            continue
        teile = sorted(teile, key=lambda h: (rang.get(h["typ"], 99), h["satz"]))
        teile, notiz = widersprueche_aufloesen(teile, (texte or {}).get(anker, ""))
        if not teile:
            continue
        if len(teile) == 1:
            out.append(dict(teile[0], aufgeloest=notiz) if notiz else teile[0])
            continue
        haupt = teile[0]
        text = haupt.get("kern") or haupt["text"]
        for h in teile[1:]:
            wo = f" in Satz {h['satz']}" if h["satz"] != haupt["satz"] else ""
            text += f" Im selben Durchgang{wo}: {_teilauftrag(h)}"
        genannt = [h.get("schon_genannt") for h in teile]
        neu = dict(haupt, text=text, typen=[h["typ"] for h in teile], gewicht=max(h["gewicht"] for h in teile) + 0.05 * (len(teile) - 1),
                   ersetzbar=sorted({w for h in teile for w in h.get("ersetzbar", [])}), info=all(h.get("info") for h in teile),
                   weitere_nr=sorted({n for h in teile for n in [h["satz"]] + list(h.get("weitere_nr") or [])} - {haupt["satz"]}),
                   teile=[{k: h.get(k) for k in ("typ", "satz", "fund")} for h in teile],
                   verben=sorted({v for h in teile for v in h.get("verben") or []}),
                   behalten=sorted({v for h in teile for v in h.get("behalten") or []}))
        if notiz:
            neu["aufgeloest"] = notiz
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
    # Verdichtungs-Auftrag der Vorrunde am selben Satz befolgt (Teilsatz weniger): nicht noch einmal stellen – übrige Kommas
    # gehören dann zu Aufzählungen oder Attributen („tiefgreifenden, nahezu alle … betreffenden“), nicht zu Teilsätzen
    erledigt = set()
    for alt in (L.vorher or {}).get("hinweise") or []:
        if isinstance(alt, dict) and alt.get("typ") in VERDICHTUNG_TYPEN and lokal_wirksam(L, alt):
            s_ = _satz_ungefaehr(L, alt.get("anfang"))
            if s_ is not None:
                erledigt.add((alt["typ"], s_["nr"]))
    if erledigt:
        L.hinweise = [h for h in L.hinweise if (h["typ"], h["satz"]) not in erledigt]
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
        h["kern"] = h["text"]
        if h["typ"] == "bereinigung":  # keine Ermessensfrage: bleibt vorn und gilt weiter
            h["text"] += f" (schon in Runde {runde} genannt – noch offen)"
            continue
        h["gewicht"] *= 0.4
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
              "fw_profil_llr_pro_1000": (0.0, "Konstruktionen umbauen"), "mattr_100": (0.0, "Wortwahl insgesamt")}
# Hinweistypen, mit denen der Coach ein Merkmal bewegt: gibt es diese Runde keinen davon, zählt das Merkmal als „ohne sichere
# Stelle“ – rechnerisch erreichbar, aber nicht mit den Stellen dieser Runde (Grenze des Coaches, nicht des Textes)
ERREICHBAR_TYPEN = {"saetze_pro_absatz_cv": {"absatz_teilen", "absatz_zusammen"}, "abkuerzungen_pro_1000": {"abkuerzung"},
                    "ki_muster_pro_1000": {"floskel", "gegenfolie", "strohmann"}, "semikolon_pro_1000": {"semikolon"},
                    "anteil_mittlere_saetze": {"buendeln", "mitte", "zickzack"},
                    "satzlaenge_dispersion": {"buendeln", "mitte", "teilen", "zickzack"}, "anteil_sehr_lange_saetze": {"buendeln"},
                    "satzklammer_mittel": {"klammer", "klammer_zusatz"}, "nachbarsatz_ueberlappung": {"anknuepfung", "kein_bezug", "synonyme"},
                    "woerter_pro_teilsatz": {"nebensatz", "kommas"}, "fw_profil_llr_pro_1000": set(FW_TYPEN)}
# Erfahrungswert für das Funktionswort-Profil: in der zweiten Evaluation hoben Einzelumbauten („kann … werden“, Nebensatz →
# Nominalgruppe, „lässt sich“ auflösen) das LLR je Text um +1,8 bis +3,8, also um etwa +0,9 bis +1,8 Logit. Angerechnet wird
# zusätzlich zu den simulierten Konstruktionen höchstens das untere Ende, und nie mehr als FW_RICHTWERT_ANTEIL des Beitrags.
FW_RICHTWERT_LOGIT, FW_RICHTWERT_ANTEIL = 0.9, 0.3
# Selbsthilfe je Merkmal: was man ohne Coach-Stelle selbst tun kann (Technik, kein Ersatzsatz für den Nutzertext)
SELBSTHILFE = {
    "satzklammer_mittel": "Angaben (Zeit, Ort, Grund, Quelle) zwischen Hilfsverb und Partizip stellen, das Subjekt nach vorn "
                          "(Beispiel: „In der Literatur wurde dies beschrieben.“ → „Dies wurde in der Literatur beschrieben.“)",
    "anteil_mittlere_saetze": "zwei zusammengehörige mittellange Sätze derselben Quelle zu einem Satz mit 30–40 Wörtern verbinden, den "
                              "zweiten als Nominal- oder Präpositionalgruppe – bis etwa jeder sechste Satz lang ist",
    "satzlaenge_dispersion": "Satzlängen mischen: einzelne Sätze mit 30–40 Wörtern (zwei Sätze derselben Quelle verbunden) neben kurze "
                             "stellen, statt alles bei 15–25 zu halten",
    "anteil_sehr_lange_saetze": "einen Satz mit Aufzählung oder Beispiel mit seinem Nachbarsatz derselben Quelle zu einem Satz mit "
                                "etwa 40 Wörtern verbinden – einer reicht (in echten Arbeiten hat etwa jeder dreißigste Satz so viele)",
    "nachbarsatz_ueberlappung": "den Schlüsselbegriff des Vorsatzes im nächsten Satz wieder aufnehmen, statt ihn zu umschreiben",
    "woerter_pro_teilsatz": "kurze „weil“-, „wenn“- oder „dass“-Sätze als Nominalgruppe fassen, wenn höchstens zwei Nomen hintereinander entstehen",
    "fw_profil_llr_pro_1000": "Konstruktionen wie „lässt sich“, „zeigt sich“, „dient als“ auflösen; nichts einstreuen",
    "saetze_pro_absatz_cv": "Absätze ungleich lang machen: an einem thematischen Einschnitt teilen oder zwei kurze Absätze zusammenlegen",
    "ki_muster_pro_1000": "Wendungen wie „spielt eine zentrale Rolle“ durch die konkrete Aussage ersetzen",
    "abkuerzungen_pro_1000": "nur vorhandene Langformen kürzen („beispielsweise“ → „z. B.“), nichts einstreuen",
    "semikolon_pro_1000": "Semikolons durch Punkt ersetzen (in Aufzählungen durch Komma) – höchstens 1–2 je 800 Wörter",
}
FW_EHRLICH = ("Der größte Teil des Abstands liegt im Funktionswort-Profil. Es entsteht beim eigenen Formulieren; Einzelumbauten verbessern "
              "seinen Beitrag erfahrungsgemäß nur um etwa 1. Wirksam ist, einzelne Absätze mit demselben Inhalt in eigenen Worten neu zu "
              "schreiben, statt Sätze umzubauen.")
FW_KEINE_KONSTRUKTION = "im Text keine umbaubare Konstruktion mehr – nur durch Neuformulieren ganzer Absätze (nichts einstreuen)"
DIAGNOSE_ANSTIEG = 0.1  # p_mensch direkt nach Runde 1 um so viel gestiegen: noch keine Diagnose (die Grenze ist noch nicht absehbar)
KNAPP_ANTEIL = 0.7  # erreichbar + ohne Auftrag < 0,7 · Lücke: Grenze der Einzelkorrekturen; 0,7–1,0: knapp, Schätzung unsicher


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


def _simulierte_merkmale(L: Lauf) -> dict[str, float]:
    """Δ-Logit je Modellmerkmal, den die Aufträge dieser Runde simuliert bringen: Satzlängen-Merkmale aus dem Endstand der
    Längensimulation, die Satzklammer aus den Klammer-Aufträgen. Fehlt die Simulation, bleibt das Merkmal draußen."""
    out: dict[str, float] = {}
    lm, sim, fokus = getattr(L, "laengen_modell", None), getattr(L, "sim", None), getattr(L, "fokus", None)
    if lm and sim is not None and fokus:
        w0, w1 = lm.werte([s["woerter"] for s in fokus]), lm.werte(laengen_folge(sim))
        for k, c in lm.koef.items():
            out[k] = c * (lm._z(k, w1[k]) - lm._z(k, w0[k]))
    gewinn = getattr(L, "sim_gewinn", None) or {}
    if "klammer" in gewinn or "klammer_zusatz" in gewinn:
        out["satzklammer_mittel"] = gewinn.get("klammer", 0.0) + gewinn.get("klammer_zusatz", 0.0)
    return out


def abkuerzung_potenzial(L: Lauf) -> float | None:
    """Δ-Logit, den übliche Abkürzungen höchstens bringen: nur vorhandene Langformen (nie einstreuen), familienweise wie
    _abkuerzungen (bis zum menschlichen Median, Familie ganz, Ergebnis ≤ P75). None = nicht berechenbar."""
    modell = L.ts.get("modell") or {}
    k = "abkuerzungen_pro_1000"
    koef, mu, sd = (modell.get("koeffizienten") or {}).get(k), (modell.get("mittel") or {}).get(k), (modell.get("sd") or {}).get(k)
    p50, wert = L.p_(k, "p50"), L.wert(k)
    if None in (koef, mu, sd, p50, wert) or not sd or not hasattr(L, "fokus"):
        return None
    n_max = sum(f["n"] for f in abk_plan(L)[0])
    z = lambda v: modell_z(L.ts, k, v)  # noqa: E731
    return max(0.0, koef * (z(wert + 1000 * n_max / L.tok_fokus) - z(wert)))


def fw_uebernutzt(L) -> list[str]:
    """Funktionswörter, die häufiger stehen als bei Menschen und Richtung KI ziehen (größter Beitrag zuerst, höchstens vier)."""
    return [r["wort"] for r in (getattr(L, "fw_diag", None) or {}).get("woerter", []) if r["zu_viel"] and r["beitrag"] < 0][:4]


def fw_offen(L) -> dict[str, list[int]]:
    """Umbaubare Funktionswort-Konstruktionen übernutzter Wörter (Technik → Sätze), an denen diese Runde kein Funktionswort- bzw.
    „sowohl … als auch“-Auftrag steht – dieselbe Stellenliste wie im Hebel (Orientierung), Grundlage der Selbsthilfe."""
    if not getattr(L, "fw_profil", None) or not getattr(L, "fw_diag", None) or not hasattr(L, "fokus"):
        return {}
    woerter = fw_uebernutzt(L)
    stellen = fw_stellen(L, woerter)
    auftrag = {h.get("satz") for h in L.hinweise if h["typ"] in FW_TYPEN or set(h.get("typen") or []) & set(FW_TYPEN)
               or h.get("muster_id") == "sowohl_als_auch"}
    out: dict[str, list[int]] = {}
    for w in woerter:
        for technik, nrn in stellen[w]["umbaubar"].items():
            for n in nrn:
                if n not in auftrag and n not in out.setdefault(technik, []):
                    out[technik].append(n)
    return {k: v for k, v in out.items() if v}


def fw_selbsthilfe(offen: dict[str, list[int]]) -> str:
    """Selbsthilfe für das Funktionswort-Profil aus der Stellenliste (nie eine Konstruktion, die im Text nicht vorkommt)."""
    if not offen:
        return FW_KEINE_KONSTRUKTION
    return "die übrigen umbaubaren Stellen: " + "; ".join(f"{t} {_nr_liste(n)}" for t, n in offen.items()) + " – nichts einstreuen"


def muster_rest(L) -> tuple[list[tuple[int, str, float]], float]:
    """KI-Muster ohne Auftrag (der Wert liegt im grünen Bereich, deshalb nur Muster mit Gewicht ≥ 1,5 als Auftrag), ohne Gegenfolien,
    nur so viele, wie bis zum menschlichen Median wegfallen müssten: [(Satz, Fund, Gewicht)] und ihr Δ-Logit im Modell. So nennt die
    Diagnose die Stellen, statt „ohne sichere Stelle“ zu schreiben (v4: CSRD −0,48)."""
    km = (getattr(L, "kz", None) or {}).get("ki_muster_pro_1000")
    modell = (getattr(L, "ts", None) or {}).get("modell") or {}
    k = "ki_muster_pro_1000"
    koef, mu, sd = (modell.get("koeffizienten") or {}).get(k), (modell.get("mittel") or {}).get(k), (modell.get("sd") or {}).get(k)
    if not km or None in (koef, mu, sd) or not sd or not hasattr(L, "fokus") or km["wert"] <= km["mensch_p50"]:
        return [], 0.0
    noetig = (km["wert"] - km["mensch_p50"]) * L.tok_fokus / 1000
    L._muster_kontraste = []
    gesperrt = {n for h in L.hinweise if h["typ"] == "strohmann" for n in h.get("sperrt") or []}
    rest = []
    for s in L.fokus:
        if not L.nutzbar(s) or s["nr"] in gesperrt:
            continue
        for a, e, g, mu_, fund, _v in analyse.muster_treffer(L.masken[s["nr"]], L.muster):
            if g <= 0 or MASKE in fund:
                continue
            if mu_["id"] in GEGENFOLIE_MUSTER:
                L._muster_kontraste = sorted(set(getattr(L, "_muster_kontraste", []) or []) | {s["nr"]})
                continue  # Kontrast „nicht …, sondern …“: eigene Regel (Gegenfolie bzw. bewusst stehen lassen)
            if any(h.get("satz") == s["nr"] and h.get("spanne") and h["spanne"][0] < e and a < h["spanne"][1]
                   for h in L.hinweise if h["typ"] in ("floskel", "strohmann")):
                continue  # hat schon einen Auftrag
            rest.append((g, s["nr"], fund))
    gewaehlt, summe = [], 0.0
    for g, nr, fund in sorted(rest, key=lambda x: (-x[0], x[1])):
        if summe >= noetig:
            break
        gewaehlt.append((nr, fund, g))
        summe += g
    z = lambda v: modell_z(L.ts, k, v)  # noqa: E731
    neu = max(km["mensch_p50"], km["wert"] - 1000.0 * summe / L.tok_fokus)
    return gewaehlt, max(0.0, koef * (z(neu) - z(km["wert"])))


KLEIN_SICHER_GEWICHT = 0.8  # „klein, aber sicher“: nur KI-Muster ab diesem Gewicht (hochpräzise, Ersatz ohne neuen Inhalt)
KLEIN_SICHER = "Klein, aber sicher – "


def muster_potenzial(L, summe: float) -> float:
    """Δ-Logit, wenn KI-Muster mit diesem Gesamtgewicht wegfallen (höchstens bis zum menschlichen Median)."""
    km = (getattr(L, "kz", None) or {}).get("ki_muster_pro_1000")
    k = "ki_muster_pro_1000"
    koef = ((L.ts.get("modell") or {}).get("koeffizienten") or {}).get(k)
    if not km or koef is None or summe <= 0:
        return 0.0
    neu = max(km["mensch_p50"], km["wert"] - 1000.0 * summe / L.tok_fokus)
    return max(0.0, koef * (modell_z(L.ts, k, neu) - modell_z(L.ts, k, km["wert"])))


def klein_sicher(L: Lauf) -> list[dict]:
    """Keine Sackgasse: Liegt p unter dem Ziel und gibt es keinen umsetzbaren Auftrag, kommen die sicheren kleinen Stellen als
    Auftrag, gekennzeichnet „klein, aber sicher“ – KI-Muster ohne Auftrag (Gewicht ≥ KLEIN_SICHER_GEWICHT, bis zum menschlichen Median;
    muster_rest) und vorhandene Langformen üblicher Abkürzungen (bis zum menschlichen Median; abk_plan). Nie etwas einstreuen
    (v6-Prüfung: Controlling R3 kannte S49 „sowohl … als auch“ samt Technik und Nutzen, gab aber keinen Auftrag)."""
    neu = []
    rest_m, _pot = muster_rest(L)
    kand = [(nr, fund, g) for nr, fund, g in rest_m if g >= KLEIN_SICHER_GEWICHT]
    summe = 0.0
    for nr, fund, g in kand:
        s = L.nach_nr.get(nr)
        if not s:
            continue
        mk = L.masken[nr]
        treffer = next(((a, e, mu) for a, e, gg, mu, f, _v in analyse.muster_treffer(mk, L.muster) if f == fund), None)
        if not treffer or treffer[2]["id"] in GEGENFOLIE_MUSTER:
            continue
        a, e, mu = treffer
        worte = [w for w in floskel_kopfwoerter(mk, a, e, mu["_re"]) if w.lower() not in analyse.FUNKTIONSWOERTER and len(w) > 2]
        if L.hinweis("floskel", s, f"{KLEIN_SICHER}{zitat(s)}: „{fund}“ – {floskel_ersatz(mu, L, s)}", 0.6 + 0.3 * g, fund=fund,
                     ersetzbar=worte):
            L.hinweise[-1].update({"muster_gewicht": g, "spanne": (a, e), "muster_id": mu.get("id"), "klein_sicher": True})
            neu.append(L.hinweise[-1])
            summe += g
    L._klein_muster_pot = muster_potenzial(L, summe)
    auftrag = {h.get("anfang") for h in L.hinweise if h["typ"] == "abkuerzung"} | \
              {n for h in L.hinweise if h["typ"] == "abkuerzung" for n in h.get("saetze") or [h.get("satz")]}
    plan = [f for f in abk_plan(L)[0] if f"abk:{f['kurz']}" not in auftrag
            and not set(dict.fromkeys(nr for nr, _p, _f in f["treffer"])) <= auftrag]
    for h in _abk_auftraege(L, plan, KLEIN_SICHER):
        h["klein_sicher"] = True
        neu.append(h)
    return neu


def muster_selbsthilfe(rest: list[tuple[int, str, float]]) -> str | None:
    if not rest:
        return None
    return ("verbleibende Wendungen durch die konkrete Aussage ersetzen (im grünen Bereich, deshalb kein Auftrag): "
            + ", ".join(f"„{f}“ (S{n})" for n, f, _g in rest[:5]) + " – nur bis zum menschlichen Median, nicht alle")


def muster_kein_rest(L) -> str:
    """Text, wenn keine KI-Wendung ohne Auftrag übrig ist: die verbleibenden Treffer sind Kontraste, die die Aussage tragen."""
    k = getattr(L, "_muster_kontraste", None) or []
    if k:
        return (f"keine weitere Wendung ohne Auftrag – die übrigen Treffer sind Kontraste „nicht …, sondern …“ ({_nr_liste(k)}), die die "
                "Aussage tragen oder schon einen Auftrag haben; stehen lassen")
    return "keine weitere Wendung ohne Auftrag – nichts ersetzen, was nicht dasteht"


def fw_absaetze(L: Lauf, n: int = 2) -> list[int]:
    """Die 1–2 Absätze im Fokus mit dem schlechtesten Beitrag zum Funktionswort-Profil (LLR je Absatz mal Wortzahl, nur Absätze ab
    30 Wörtern): dort lohnt das Neuformulieren mit demselben Inhalt am meisten. Den zweiten nur, wenn er mindestens halb so stark
    Richtung KI zieht wie der erste."""
    profil = getattr(L, "fw_profil", None)
    if not profil or not getattr(L, "absaetze", None):
        return []
    beitrag = []
    for nr, liste in L.absaetze.items():
        d = fw_diagnose(liste, profil)
        if d and d["n"] >= 30 and d["llr"] < 0:
            beitrag.append((d["llr"] * d["n"] / 1000.0, nr))
    beitrag.sort()
    out = [nr for b, nr in beitrag[:1]]
    if len(beitrag) > 1 and beitrag[1][0] <= 0.5 * beitrag[0][0]:
        out.append(beitrag[1][1])
    return sorted(out)[:n]


def fw_absatz_zusatz(L) -> str:
    """Zusatz zum Rat „Absätze neu formulieren“: die 1–2 Absätze mit dem schlechtesten Funktionswort-Beitrag (v6-Prüfung: in allen
    fünf Schlussdiagnosen „nur durch Neuformulieren ganzer Absätze“ ohne Ort)."""
    if getattr(L, "_fw_absaetze", None) is None:
        L._fw_absaetze = fw_absaetze(L) if hasattr(L, "fokus") else []
    nrn = L._fw_absaetze
    return f" – am ehesten {_absatz_liste(nrn)}, dort zieht das Funktionswort-Profil am stärksten Richtung KI" if nrn else ""


LAENGEN_BLOCK_REST = 0.3  # Längenblock: das größte Potenzial ganz, die übrigen nur zu 30 % (dieselbe Umstellung bewegt alle drei)


def _laengenblock(zeilen: list[dict]) -> list[dict]:
    """Mittellange Sätze, Dispersion und sehr lange Sätze bewegt derselbe Hebel (Satzlängen verteilen): als ein Block gezählt,
    Potenzial = größtes + 0,3 · übrige (v6-Prüfung: Agile 1,33 von 2,21 aus demselben Hebel). Erreichbar bleibt, was die Simulation
    der Aufträge für alle drei zusammen ergibt (höchstens das Blockpotenzial)."""
    glieder = [z for z in zeilen if z["id"] in LAENGEN_SELBST]
    if len(glieder) < 2:
        return zeilen
    pots = sorted((z["potenzial_logit"] for z in glieder), reverse=True)
    pot = pots[0] + LAENGEN_BLOCK_REST * sum(pots[1:])
    err = min(pot, sum(z["erreichbar_logit"] for z in glieder))
    rest = max(0.0, pot - err)
    haupt = max(glieder, key=lambda z: z["potenzial_logit"])
    kein_raum = any(z.get("wie") == "kein_raum" for z in glieder)
    block = {"id": "laengenblock", "name": "Satzlängen-Verteilung (" + ", ".join(z["name"] for z in glieder) + ")",
             "beitrag": sum(z["beitrag"] for z in glieder), "erreichbar": max(z["erreichbar"] for z in glieder),
             "erreichbar_logit": err, "potenzial_logit": pot, "rest_logit": rest,
             "wie": "kein_raum" if kein_raum and rest > 1e-9 else haupt.get("wie"), "glieder": [z["id"] for z in glieder],
             "ohne_stelle": err <= 1e-9 and rest > 0 and not kein_raum, "stellen": None,
             "selbsthilfe": None if kein_raum else (haupt.get("selbsthilfe") if rest > 0.05 else None)}
    if kein_raum:
        block["hinweis"] = next((z.get("hinweis") for z in glieder if z.get("hinweis")), None)
    i = zeilen.index(glieder[0])
    out = [z for z in zeilen if z not in glieder]
    out.insert(i, block)
    return out


def _diagnose(L: Lauf, auswahl: list[dict], ziel_p: float) -> dict | None:
    """Liegt p_mensch unter dem Ziel und gibt es < 3 umsetzbare Hinweise (oder hat sich p über zwei Runden um
    < STAGNATION_P bewegt), erklärt der Coach, woran es hängt: negative Modellbeiträge mit Größe, getrennt nach
    – erreichbar mit den Aufträgen dieser Runde (zählt),
    – rechnerisch erreichbar, aber diese Runde ohne Auftrag (keine sichere Stelle, Stelle im grünen Bereich): zählt als „ohne Auftrag“,
      mit Selbsthilfe aus dem Text, nie eine Aufforderung zum Einstreuen,
    – gesperrt (kein Spielraum im Bündelfenster bzw. Kontingent – eine Grenze des Coaches) und nur durch Neuformulieren erreichbar:
      eigene Summen, zählen nicht mit,
    – kaum erreichbar.
    Mittellange Sätze, Dispersion und sehr lange Sätze zählen als ein Block. Jede Zeile nennt ihr Potenzial, die Zeilen ergeben die
    genannten Summen. Einstufung (ohne gesperrt und Neuformulieren): „coach“, wenn erreichbar + ohne Auftrag die Lücke decken; „knapp“
    bei 70–100 %; „einzelkorrekturen“ unter 70 %. Aufschub nur direkt nach Runde 1 mit deutlichem Anstieg (≥ DIAGNOSE_ANSTIEG) und nur,
    wenn die offenen Aufträge simuliert samt den Potenzialen ohne Auftrag mindestens 0,7 der Lücke decken – sonst sofort, als
    „vorläufig“ gekennzeichnet, solange Aufträge offen sind."""
    p = L.bew.get("p_mensch")
    if not L.bew.get("verfuegbar") or p is None or p >= ziel_p:
        return None
    if text_unveraendert(L):
        return None  # nur erneut gemessen: die genannten Stellen sind noch offen, das ist keine Stagnation
    stil = [h for h in auswahl if h["hebel"] not in ("vorgaben", "bereinigung") and not h.get("info")]
    umsetzbar = [h for h in stil if not h.get("schon_genannt") and not h.get("klein_sicher")]
    stagniert, p_alt = False, None
    if len(L.messungen) >= 2 and L.messungen[-2].get("p_mensch") is not None:
        p_alt = L.messungen[-2]["p_mensch"]
        stagniert = abs(p - p_alt) < STAGNATION_P
    if len(umsetzbar) >= 3 and not stagniert:
        return None
    offen = [h for h in stil if not h.get("klein_sicher")]  # auch schon genannte, noch offene Aufträge
    beitraege = [b for b in L.bew.get("modell_beitraege") or [] if b["beitrag"] < -0.05]
    modell = L.ts.get("modell") or {}
    alle = [h for h in L.hinweise if not h.get("info")]  # alle Aufträge dieser Runde, auch die nicht angezeigten
    vorhanden = {h["typ"] for h in alle if not h.get("klein_sicher")}
    klein = {h["typ"] for h in alle if h.get("klein_sicher")}
    simuliert = _simulierte_merkmale(L)  # Δ-Logit je Modellmerkmal aus den Aufträgen dieser Runde (soweit simuliert)
    mit_text = hasattr(L, "fokus")
    zeilen, fw_offen_ = [], {}
    for b in beitraege:
        grad, wie = ERREICHBAR.get(b["id"], (0.5, ""))
        potenzial = -b["beitrag"] * grad
        selbst, stellen, hinweis = SELBSTHILFE.get(b["id"]), None, None
        typen = ERREICHBAR_TYPEN.get(b["id"])
        mit_stelle = typen is None or bool(typen & vorhanden)
        if b["id"] == "abkuerzungen_pro_1000":
            pot = abkuerzung_potenzial(L)  # nur vorhandene Langformen, familienweise, bis zum menschlichen Median
            if pot is not None:
                potenzial = min(potenzial, pot)
                if potenzial <= 0.01:
                    grad, potenzial = 0.0, 0.0
                    wie = "median" if abk_plan(L)[2] <= 0 else "keine_langform"
            selbst = abk_selbsthilfe(L) if mit_text else None
            if "abkuerzung" in klein and potenzial > 0:
                mit_stelle, wie = True, "klein_sicher"
        if b["id"] == "ki_muster_pro_1000" and mit_text and not mit_stelle:
            if "floskel" in klein:
                # die verbleibenden Wendungen stehen oben als Auftrag „klein, aber sicher“ (nicht hart „im grünen Bereich“)
                potenzial = min(potenzial, getattr(L, "_klein_muster_pot", potenzial))
                mit_stelle, wie, selbst = True, "klein_sicher", None
            else:
                rest_m, pot_m = muster_rest(L)
                potenzial = min(potenzial, pot_m)
                selbst = muster_selbsthilfe(rest_m)
                stellen = [f"„{f}“ (S{n})" for n, f, _g in rest_m] or None
                if not rest_m:
                    grad, potenzial, wie = 0.0, 0.0, "keine_stelle"
                    hinweis = muster_kein_rest(L)
        mit = potenzial if mit_stelle else 0.0
        if b["id"] == "fw_profil_llr_pro_1000":
            sim = 0.0
            if L.fw_potenzial > 0 and modell.get("sd", {}).get(b["id"]):
                sim = modell["koeffizienten"][b["id"]] * L.fw_potenzial / modell["sd"][b["id"]]  # LLR-Gewinn in Logit
            richtwert = min(FW_RICHTWERT_LOGIT, FW_RICHTWERT_ANTEIL * -b["beitrag"])
            potenzial = min(-b["beitrag"], sim + richtwert)
            mit = min(potenzial, sim) if mit_stelle else 0.0  # die gefundenen Konstruktionen; der Erfahrungswert ist Selbsthilfe
            grad = 0.5 if potenzial >= 0.25 * -b["beitrag"] else 0.0
            wie = (f"Konstruktionen oben (geschätzt etwa +{fmt(round(sim, 2))}) und Erfahrungswert für weitere Umbauten" if mit_stelle and sim
                   else "Erfahrungswert für Einzelumbauten")
            fw_offen_ = fw_offen(L)
            selbst = fw_selbsthilfe(fw_offen_) if mit_text else selbst
        elif mit_stelle and b["id"] in simuliert:
            mit = max(0.0, min(potenzial, simuliert[b["id"]]))  # nur, was die genannten Stellen simuliert bringen
        if b["id"] in LAENGEN_SELBST and potenzial > mit and buendel_raum(L) == 0:
            # kein Spielraum für weitere sichere lange Sätze (Bündelfenster, Kontingent, Aussetzung oder harte Grenzen): eine Grenze des
            # Coaches, nicht des Textes – das Potenzial steht als „gesperrt“ getrennt und zählt nicht mit; keine Selbsthilfe „bündeln“,
            # die dem Satzlängen-Hinweis widerspräche
            wie, selbst = "kein_raum", None
            hinweis = ("Bündeln ist diese Runde ausgesetzt" if "buendeln" in (getattr(L, "ausgesetzt", None) or set())
                       else "kein weiteres passendes Satzpaar bzw. die Grenzen gegen Überkorrektur")
        if b["id"] in LAENGEN_SELBST and selbst and wie != "kein_raum" and teilsatz_hoch(L):
            selbst = selbst.rstrip(".") + NUR_NEBENSATZ_PAARE
        rest = max(0.0, potenzial - mit)
        ohne_stelle = potenzial > 0 and mit <= 1e-9 and not stellen and wie != "kein_raum"
        zeilen.append({"id": b["id"], "name": b["name"], "beitrag": b["beitrag"], "erreichbar": grad,
                       "erreichbar_logit": mit, "potenzial_logit": potenzial, "rest_logit": rest,
                       "wie": wie, "ohne_stelle": ohne_stelle, "stellen": stellen, "selbsthilfe": selbst if rest > 0.05 else None})
        if hinweis:
            zeilen[-1]["hinweis"] = hinweis
    luecke = _logit(ziel_p) - _logit(p)
    summe = sum(-z["beitrag"] for z in zeilen) or 1e-9
    fw = next((z for z in zeilen if z["id"] == "fw_profil_llr_pro_1000"), None)
    fw_b = -fw["beitrag"] if fw else 0.0
    fw_err = fw["potenzial_logit"] if fw else 0.0
    # dominant nur, wenn das Profil die Mehrheit der negativen Beiträge stellt UND auch mit allen übrigen erreichbaren Beiträgen
    # (einschließlich der stellenlosen) und dem erreichbaren Teil des Profils eine Lücke bleibt, die nur der Rest des Profils deckt
    uebrige = sum(z["potenzial_logit"] for z in zeilen if z is not fw)
    rest_l = luecke - uebrige - fw_err
    fw_dominant = fw_b >= 1.0 and fw_b >= 0.5 * summe and rest_l > 0 and fw_b - fw_err >= rest_l
    if fw is not None and mit_text and getattr(L, "fw_profil", None) and not fw_offen_:
        # keine umbaubare Konstruktion mehr im Text: der Erfahrungswert zählt nur, wenn das Profil wirklich dominiert (dann ist das
        # Neuformulieren ganzer Absätze der Weg), sonst ist das Profil mit Einzelkorrekturen kaum erreichbar
        if fw_dominant:
            fw["selbsthilfe"] = FW_KEINE_KONSTRUKTION + fw_absatz_zusatz(L) if fw["rest_logit"] > 0.05 else None
            if fw["erreichbar_logit"] <= 1e-9:
                fw.update({"wie": "nur_neuformulieren", "ohne_stelle": False})
        else:
            fw.update({"potenzial_logit": fw["erreichbar_logit"], "rest_logit": 0.0, "erreichbar": 0.0, "wie": "keine_konstruktion",
                       "ohne_stelle": False, "selbsthilfe": None})
    zeilen = _laengenblock(zeilen)
    # auf zwei Stellen runden, Potenzial = erreichbar + Rest: so ergeben die angezeigten Zeilen genau die genannten Summen
    for z in zeilen:
        z["erreichbar_logit"], z["rest_logit"] = round(z["erreichbar_logit"], 2), round(z["rest_logit"], 2)
        z["potenzial_logit"] = round(z["erreichbar_logit"] + z["rest_logit"], 2)
    erreichbar = round(sum(z["erreichbar_logit"] for z in zeilen), 2)
    # nur durch Neuformulieren ganzer Absätze erreichbar (Funktionswort-Richtwert ohne umbaubare Konstruktion) bzw. gesperrt (kein
    # Spielraum für sichere Bündelungen): keine Einzelkorrektur dieser Runde – eigene Summen, nicht in der Einstufung (v6-Prüfung:
    # CSRD hieß „knapp“, obwohl 0,53 der 1,12 aus gesperrten Zeilen stammten)
    neu_formulieren = round(sum(z["rest_logit"] for z in zeilen if z["wie"] == "nur_neuformulieren"), 2)
    gesperrt = round(sum(z["rest_logit"] for z in zeilen if z["wie"] == "kein_raum"), 2)
    stellenlos = round(sum(z["rest_logit"] for z in zeilen if z["wie"] not in ("nur_neuformulieren", "kein_raum")), 2)
    if erreichbar >= luecke:
        grenze = "keine"
    elif erreichbar + stellenlos >= luecke:
        grenze = "coach"
    elif erreichbar + stellenlos >= KNAPP_ANTEIL * luecke:
        grenze = "knapp"
    else:
        grenze = "einzelkorrekturen"
    # Aufschub nur, wenn die erste Überarbeitung deutlich gewirkt hat UND die offenen Aufträge (simuliert) samt den Potenzialen ohne
    # Auftrag die Lücke voraussichtlich weitgehend decken; sonst die Diagnose sofort, „vorläufig“ (v6-Prüfung: DP R2 mit einem
    # Auftrag bei einer Lücke von 3,35 – „zeigt erst die nächste Messung“ war nicht ehrlich)
    sim_offen = sum(max(0.0, h.get("netto_logit") or 0.0) for h in offen)
    if offen and len(L.messungen) == 1 and L.messungen[0].get("p_mensch") is not None \
            and p - L.messungen[0]["p_mensch"] >= DIAGNOSE_ANSTIEG \
            and (sim_offen + stellenlos >= KNAPP_ANTEIL * luecke or len(umsetzbar) >= 3):
        L.diagnose_aufgeschoben = {"p_vorher": L.messungen[0]["p_mensch"], "p_mensch": p, "sim_offen": round(sim_offen, 2),
                                   "stellenlos": stellenlos, "luecke": round(luecke, 2)}
        return None
    fw_abs = []
    if mit_text and fw is not None:
        fw_absatz_zusatz(L)
        fw_abs = list(L._fw_absaetze or [])
    return {"p_mensch": p, "ziel_p_mensch": ziel_p, "stagniert": stagniert, "p_vorvorher": p_alt, "umsetzbar": len(umsetzbar),
            "beitraege": zeilen, "luecke_logit": round(luecke, 2), "erreichbar_logit": erreichbar,
            "stellenlos_logit": stellenlos, "gesperrt_logit": gesperrt, "neuformulieren_logit": neu_formulieren, "grenze": grenze,
            "realistisch": erreichbar >= luecke, "vorlaeufig": bool(offen), "offen_logit": round(sim_offen, 2),
            "klein": sum(1 for h in stil if h.get("klein_sicher")),
            "fw_dominant": fw_dominant, "fw_text": FW_EHRLICH if fw_dominant else None, "fw_top": (L.fw_diag or {}).get("top", []),
            "fw_absaetze": fw_abs}


# ---------------------------------------------------------------------------
# Coach
# ---------------------------------------------------------------------------

_FW_KONSTR_LABEL = {"ankuendigung": "Ankündigung vor „dass“ streichen", "laesst_sich": "„lässt sich“ auflösen",
                    "zeigt_sich": "„zeigt sich“ auflösen", "ergibt_sich": "„ergibt sich“ → „folgt“", "dient_als": "„dient als“ umbauen",
                    "versteht_sich_als": "„versteht sich als“ umbauen", "gilt_als": "„gilt als“ umbauen",
                    "redeverb_dass": "kurzer „dass“-Satz → Nominalgruppe"}
_FW_KONSTR_NAME = {"ankuendigung": "Ankündigung vor „dass“", "laesst_sich": "„lässt sich“", "zeigt_sich": "„zeigt sich“",
                   "ergibt_sich": "„ergibt sich“", "dient_als": "„dient als“", "versteht_sich_als": "„versteht sich als“",
                   "gilt_als": "„gilt als“", "redeverb_dass": "„zeigt, dass …“"}
_DEFINITION_VERB_RE = re.compile(r"\b(?:definier\w*|bezeichn\w*|versteh\w*|verstand\w*|begreif\w*|begriffen|betracht\w*|sieht|sehen|"
                                 r"gesehen|charakterisier\w*|beschreib\w*|beschrieben|einstuf\w*|eingestuft|wahrgenommen|wahrnehm\w*|"
                                 r"eingeordnet|einordn\w*|ansieht|angesehen|erweis\w*|erwiesen|entpupp\w*|fungier\w*|gilt|gelten|galt|galten)\b",
                                 re.IGNORECASE)
# Komparativ weiter vorn im selben Teilsatz („über geringere finanzielle und personelle Ressourcen als Großkonzerne“): Vergleich.
# Nur eindeutige Komparativstämme – „besondere“, „frühere“, „weitere“, „unsere“, „mittlere“ enden ebenfalls auf „-ere“.
_KOMPARATIV_RE = re.compile(r"\b(?:gering|höh|niedrig|größ|klein|stärk|schwäch|läng|kürz|bess|schlecht|häufig|selten|schnell|"
                            r"langsam|wichtig|einfach|schwierig|teur|günstig|jüng|ält)er(?:e|en|er|es|em)?\b", re.IGNORECASE)


def fw_stellen(L: Lauf, woerter: list[str]) -> dict[str, dict[str, list]]:
    """Vorkommen übernutzter Funktionswörter im Fokus (außerhalb wörtlicher Zitate), eingeordnet in notwendig (Kategorie →
    Satznummern) und umbaubar (Technik → Satznummern). Umbaubar ist nur, was der Coach selbst als Konstruktion umbauen
    würde (Schutzregeln wie beim Auftrag, Typ nicht ausgesetzt, simulierter Gewinn > 0) und „sowohl … als auch“ → „und“,
    wenn das Entfernen von „als“ und „auch“ den Funktionswort-Wert hebt."""
    out = {w: {"notwendig": {}, "umbaubar": {}, "anzahl": 0} for w in woerter}
    if not woerter or not L.fw_profil or not L.fw_diag:
        return out
    hz = L.kz.get("hedging_pro_1000")
    hedging_hoch = bool(hz and hz["wert"] > hz["mensch_p75"])
    sowohl_ok = fw_delta(L.fw_diag, L.fw_profil, Counter({"als": 1, "auch": 1}), Counter()) > 0
    for s in L.fokus:
        if not L.nutzbar(s):
            continue
        mk = L.masken[s["nr"]]
        konstr = []  # (start, ende, Technik) der umbaubaren Konstruktionen im Satz
        geschuetzt = []  # (start, ende, Kategorie) der KI-typischen Konstruktionen, die diese Runde nicht umgebaut werden
        for kid, typ, k_woerter, rx, _t in FW_KONSTRUKTIONEN:
            t = rx.search(mk)
            if not t or MASKE in t.group(0):
                continue
            name = _FW_KONSTR_NAME[kid]
            ende = t.start("rest") if kid == "redeverb_dass" else t.end()  # der Inhalt des „dass“-Satzes gehört nicht dazu
            if typ in L.ausgesetzt:
                grund = "diese Runde ausgesetzt"
            elif kid == "laesst_sich" and hedging_hoch:
                grund = "Hedging ist schon hoch"
            else:
                bilanz = _fw_bilanz(L, kid, s, mk, t)
                if bilanz is None:
                    grund = "Aussage einer Quelle bzw. Person"
                elif fw_delta(L.fw_diag, L.fw_profil, *bilanz) <= 0:
                    grund = "der Umbau entfernte menschlich häufige Wörter mit"
                elif fw_technik(L, kid, _t, mk, t) is None:
                    grund = "das Ersatzverb steht schon im Satz"
                elif (s["nr"], typ) in getattr(L, "fw_teilsatz_gesperrt", set()):
                    grund = "das Verhältnis der Sätze mit zwei zu einem Teilsatz stiege weiter"
                else:
                    konstr.append((t.start(), ende, _FW_KONSTR_LABEL[kid], k_woerter))
                    continue
            geschuetzt.append((t.start(), ende, f"{name} – bleibt ({grund})", k_woerter))
        for w in woerter:
            for m in re.finditer(rf"(?<![\wäöüß]){re.escape(w)}(?![\wäöüß])", mk, re.IGNORECASE):
                out[w]["anzahl"] += 1
                # eine Konstruktion erklärt nur die Wörter, die ihr Umbau entfernt („sich“ in „lässt sich“, „dass“ nach „zeigt“)
                technik = next((lab for a, e, lab, kw in konstr if a <= m.start() < e and w in kw), None)
                schutz = next((lab for a, e, lab, kw in geschuetzt if a <= m.start() < e and w in kw), None)
                vor = mk[:m.start()]
                nach = mk[m.end():]
                vor_wort = (re.findall(r"[\wäöüß]+", vor) or [""])[-1]
                if technik is None and w == "als" and re.match(r"\s+auch\b", nach) and re.search(r"\bsowohl\b", vor, re.IGNORECASE) \
                        and sowohl_ok:
                    technik = "„sowohl … als auch“ → „und“"
                if technik:
                    out[w]["umbaubar"].setdefault(technik, []).append(s["nr"])
                    continue
                if schutz:
                    out[w]["notwendig"].setdefault(schutz, []).append(s["nr"])
                    continue
                if w == "als":
                    if re.match(r"\s+auch\b", nach):
                        kat = ("„sowohl … als auch“ – bleibt („auch“ ist hier schon seltener als bei Menschen)"
                               if re.search(r"\bsowohl\b", vor, re.IGNORECASE) else "Aufzählung („als auch“)")
                    elif vor_wort.lower() in _VERGLEICH_VOR_ALS or (vor_wort.endswith("er") and vor_wort[:1].islower()) \
                            or re.match(r"\s+(?:\d|ein|zwei|drei|vier|fünf|zehn|hundert|tausend|die\s+Hälfte)", nach):
                        kat = "Vergleich/Mengenangabe"
                    elif (not vor.strip(" „\"(»") or re.search(r",\s*$", vor)) \
                            and re.match(r"\s+(?:der|die|das|den|dem|ein|eine|einer|sie|er|es|man|wir|ich)\b", nach, re.IGNORECASE):
                        kat = "Zeitangabe"
                    elif _DEFINITION_VERB_RE.search(mk):
                        kat = "Definition/Einordnung"
                    elif _KOMPARATIV_RE.search(" ".join(re.split(r"[,;:]", vor)[-1].split()[-6:])):
                        kat = "Vergleich/Mengenangabe"  # „geringere … Ressourcen als Großkonzerne“
                    else:
                        kat = "Rolle/Funktion"
                elif w == "sich":
                    kat = "reflexives Verb"
                elif w == "dass":
                    kat = "Inhaltssatz"
                elif w in ("sie", "diese", "es"):
                    kat = "Verweis"
                else:
                    kat = "Artikel/Präposition"
                out[w]["notwendig"].setdefault(kat, []).append(s["nr"])
    return out


def _nr_liste(nrn: list[int], n: int = 5) -> str:
    u = list(dict.fromkeys(nrn))
    return ", ".join(f"S{x}" for x in u[:n]) + (" …" if len(u) > n else "")


def _fw_hebeltext(L: Lauf, mit_konstruktion: bool = True) -> str | None:
    """Datenbasierter Hebeltext für das Funktionswort-Profil: die 2–3 Wörter mit dem größten Beitrag zum negativen LLR.
    „Nur über die genannten Konstruktionen“ steht nur, wenn diese Runde ein Funktionswort-Auftrag genannt ist; sonst folgen
    die Vorkommen der übernutzten Wörter mit Satznummer, eingeordnet in notwendig und umbaubar – oder „keine weitere
    umbaubare Konstruktion gefunden“."""
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
    if viel and mit_konstruktion:
        text += " Übernutzte Wörter nur über die genannten Konstruktionen abbauen."
    elif viel:
        # dieselbe Wortliste wie die Selbsthilfe der Diagnose (fw_offen): Orientierung und Diagnose widersprechen sich nicht
        liste = [next(r for r in L.fw_diag["woerter"] if r["wort"] == w) for w in fw_uebernutzt(L)] or viel
        stellen = fw_stellen(L, [r["wort"] for r in liste])
        zeilen, umbaubar = [], False
        for r in liste:
            st = stellen[r["wort"]]
            if not st["anzahl"]:
                continue
            notw = sum(len(v) for v in st["notwendig"].values())
            teil = f"„{r['wort']}“: "
            if set(st["notwendig"]) == {"Artikel/Präposition"} and not st["umbaubar"]:
                zeilen.append(teil + "Artikel bzw. Präposition, notwendig")  # keine Satzliste: dort gibt es nichts umzubauen
                continue
            if st["notwendig"]:
                teil += f"notwendig {notw}× (" + "; ".join(f"{k} {_nr_liste(v)}" for k, v in st["notwendig"].items()) + ")"
            if st["umbaubar"]:
                umbaubar = True
                teil += (", " if st["notwendig"] else "") + f"umbaubar {sum(len(v) for v in st['umbaubar'].values())}× (" \
                    + "; ".join(f"{k} {_nr_liste(v)}" for k, v in st["umbaubar"].items()) + ")"
            zeilen.append(teil)
        if zeilen:
            text += " Stellen – " + " · ".join(zeilen) + "."
        if not umbaubar:
            text += (" Im Text keine umbaubare Konstruktion mehr: Die Vorkommen sind notwendig – nur durch Neuformulieren ganzer Absätze "
                     f"zu ändern{fw_absatz_zusatz(L)}; nichts einstreuen, nichts erzwingen.")
    if not viel and not mit_konstruktion:
        text += (" Kein übernutztes Wort mit umbaubarer Konstruktion – das Profil ändert sich nur durch Neuformulieren ganzer Absätze"
                 f"{fw_absatz_zusatz(L)}.")
    if wenig:
        passiv = any(r["wort"] in ("werden", "wird") for r in wenig)
        text += (" Seltene Wörter nicht einstreuen – sie kommen beim eigenen Formulieren von selbst"
                 + (" (Passiv nicht wegformulieren)." if passiv else "."))
    return text


# ---------------------------------------------------------------------------
# Netto-Simulation je Auftrag (v7): Wirkung auf das Modell samt Nebeneffekten
# ---------------------------------------------------------------------------

NETTO_TOLERANZ = 0.01  # Δ-Logit, ab dem ein Auftrag als netto schädlich gilt (Schätzfehler der Simulation)
NETTO_FAKTOR = 1.5  # kleine Lücke: Aufträge, bis ihre simulierte Summe das 1,5-Fache der Lücke erreicht
KLEINE_LUECKE_P = 0.02  # Modell-Lücke in p, unter der höchstens KLEINE_LUECKE_MAX Aufträge kommen
KLEINE_LUECKE_MAX = 2
RAUSCHEN_P, RAUSCHEN_SCORE = 0.02, 1  # Lücke im Bereich der Messunsicherheit: höchstens ein Auftrag
NEBENSATZ_FW = {"dass": ({"dass": 1}, {}), "weil": ({"weil": 1}, {"wegen": 1}), "da": ({"da": 1}, {"wegen": 1}),
                "indem": ({"indem": 1}, {"durch": 1}), "wenn": ({"wenn": 1}, {"bei": 1}), "nachdem": ({"nachdem": 1}, {"nach": 1}),
                "obwohl": ({"obwohl": 1}, {"trotz": 1})}


def modell_z(ts: dict, k: str, v: float) -> float:
    """z-Wert eines Modellmerkmals wie analyse.bewerte: einseitig am menschlichen Band gekappt (modell['kappen'], v7; ohne
    Kappung unverändert) und auf ±Z_CLIP begrenzt."""
    modell = ts.get("modell") or {}
    kappe = (modell.get("kappen") or {}).get(k)
    gk = getattr(analyse, "gekappt", None)
    if kappe and gk:
        v = gk(v, kappe)
    elif kappe:
        v = min(v, kappe["wert"]) if kappe.get("seite") == "oben" else max(v, kappe["wert"])
    mu, sd_ = modell["mittel"][k], modell["sd"][k] or 1.0
    clip = modell.get("z_clip") or getattr(analyse, "Z_CLIP", 3.0)
    return max(-clip, min(clip, (v - mu) / sd_))


def modell_delta(L: Lauf, dm: dict[str, float]) -> float:
    """Δ-Logit des Modells, wenn sich Modellmerkmale (Wert im Fokus) um dm ändern."""
    modell = L.ts.get("modell") or {}
    koef = modell.get("koeffizienten") or {}
    out = 0.0
    for k, d in dm.items():
        v0 = L.wert(k)
        if k not in koef or not d or v0 is None or k not in (modell.get("mittel") or {}):
            continue
        out += koef[k] * (modell_z(L.ts, k, v0 + d) - modell_z(L.ts, k, v0))
    return out


def _fokus_woerter(L: Lauf) -> tuple[list[str], dict[int, tuple[int, int]]]:
    """Wörter des Fokus (klein, wie analyse.py für MATTR) und je Satz der Bereich darin."""
    if getattr(L, "_fw_liste", None) is None:
        woerter, bereich = [], {}
        for s in L.fokus:
            a = len(woerter)
            woerter.extend(t.lower() for t in analyse.tokens(s["text"]) if analyse.ist_wort(t))
            bereich[s["nr"]] = (a, len(woerter))
        L._fw_liste = (woerter, bereich)
    return L._fw_liste


def mattr_delta(L: Lauf, nr: int | None, weg: dict | None, dazu: dict | None, ersetzen: dict | None = None) -> float:
    """Änderung von MATTR-100, wenn im Satz nr die Wörter weg entfallen und dazu hinzukommen bzw. im ganzen Fokus die Wörter
    nach ersetzen ausgetauscht werden (Synonyme vereinheitlichen)."""
    woerter, bereich = _fokus_woerter(L)
    if len(woerter) < 2:
        return 0.0
    if getattr(L, "_mattr0", None) is None:
        L._mattr0 = analyse.mattr(woerter, 100)
    neu = list(woerter)
    if ersetzen:
        neu = [ersetzen.get(w, w) for w in neu]
    if nr is not None and nr in bereich and (weg or dazu):
        a, e = bereich[nr]
        teil = neu[a:e]
        for w, c in (weg or {}).items():
            for _ in range(c):
                if w in teil:
                    teil.remove(w)
        teil += [w for w, c in (dazu or {}).items() for _ in range(c)]
        neu = neu[:a] + teil + neu[e:]
    return analyse.mattr(neu, 100) - L._mattr0


def ueberlappung_delta(L: Lauf, nr: int, plus: set[str], minus: set[str] = frozenset()) -> float:
    """Änderung der Nachbarsatz-Überlappung (Jaccard der Inhaltsstämme benachbarter Sätze wie analyse.py), wenn Satz nr die
    Stämme plus dazubekommt und minus verliert."""
    staemme = [set(analyse.inhaltsstaemme(s.get("tokens") or analyse.tokens(s["text"]))) for s in L.fokus]
    i = L.fokus_index.get(nr)
    if i is None:
        return 0.0

    def mittel_ueberlappung(st):
        werte = [len(a & b) / len(a | b) for a, b in zip(st, st[1:]) if a and b]
        return sum(werte) / len(werte) if werte else 0.0
    vorher = mittel_ueberlappung(staemme)
    staemme[i] = (staemme[i] - set(minus)) | set(plus)
    return mittel_ueberlappung(staemme) - vorher


def _stamm_von(L: Lauf, wort: str) -> set[str]:
    return set(analyse.inhaltsstaemme(analyse.tokens(wort))) if wort else set()


def _klammer_basis(L: Lauf) -> tuple[int, float] | None:
    if getattr(L, "_klammer_basis", None) is None:
        spannen = [x for s in L.fokus for x in analyse.satzklammern(s["text"])]
        L._klammer_basis = (len(spannen), float(sum(spannen))) if len(spannen) >= 5 else (0, 0.0)
    n, summe = L._klammer_basis
    return (n, summe) if n else None


def _laengen_teile(L: Lauf, h: dict) -> dict[str, float]:
    """Änderung der längenabhängigen Modellmerkmale (Satzlängen, Sätze pro Absatz) durch diesen einen Auftrag allein."""
    pos = h.get("pos")
    alt_l, neu_l = h.get("laengen_alt"), h.get("sim")
    if pos is None and h.get("satz") in L.fokus_index:
        pos = L.fokus_index[h["satz"]]
    if pos is None:
        return {}
    if h["typ"] in ("zickzack", "klammer_zusatz") and not neu_l and h.get("weitere_nr"):
        b = L.fokus_index.get(h["weitere_nr"][0])
        if b is None or b != pos + 1:
            return {}
        alt_l = [L.fokus[pos]["woerter"], L.fokus[b]["woerter"]]
        neu_l = [sum(alt_l) - (1 if h["typ"] == "klammer_zusatz" else 0)]
    if not alt_l or not neu_l or pos + len(alt_l) > len(L.fokus):
        return {}
    basis = [[s["woerter"]] for s in L.fokus]
    if [x[0] for x in basis[pos:pos + len(alt_l)]] != list(alt_l):
        return {}
    neu = list(basis)
    neu[pos] = list(neu_l)
    for j in range(1, len(alt_l)):
        neu[pos + j] = []
    lm = L.laengen_modell
    w0 = lm.werte(laengen_folge(basis), L.absatz_anzahl(basis))
    w1 = lm.werte(laengen_folge(neu), L.absatz_anzahl(neu))
    return {k: w1[k] - w0[k] for k in w1 if k in w0 and (k in lm.koef or k == ABSATZ_CV)}


def netto_wirkung(L: Lauf, h: dict) -> tuple[float, dict[str, float]]:
    """Simulierter Netto-Δ-Logit eines Auftrags im Modell: die Zielwirkung (Längen, Satzklammer, Absätze, KI-Muster, Semikolons,
    Abkürzungen, Funktionswort-Profil, Begriffsaufnahme) samt Nebeneffekten – Funktionswort-Profil bei „um … zu“ bzw.
    „kann … werden“, neue kurze Satzklammern, MATTR (Wörter, die wegfallen oder dazukommen), Längenklassen bei Kürzungen."""
    dm: dict[str, float] = {}
    typ, nr = h["typ"], h.get("satz")
    tok = max(1, L.tok_fokus)

    def plus(k, d):
        dm[k] = dm.get(k, 0.0) + d
    # Längen und Sätze pro Absatz (Bündeln, Teilen, Mitte, Herauslösen, Kürzungen mit Längenwirkung, Zickzack, Angabe holen)
    if h.get("laengen_alt") or typ in ("zickzack", "klammer_zusatz"):
        for k, d in _laengen_teile(L, h).items():
            plus(k, d)
    if typ in ("absatz_teilen", "absatz_zusammen") and h.get("absatz_cv"):
        plus(ABSATZ_CV, h["absatz_cv"][1] - h["absatz_cv"][0])
    # Satzklammer: Zuwachs der Klammer-Aufträge, neue (kurze) Klammern der Funktionswort-Umbauten
    kb = _klammer_basis(L)
    if kb:
        n, summe = kb
        if typ in ("klammer", "klammer_zusatz") and h.get("klammer_zuwachs"):
            plus("satzklammer_mittel", h["klammer_zuwachs"] / n)
        if h.get("klammer_neu") is not None and h["klammer_neu"] >= 1:
            plus("satzklammer_mittel", (summe + h["klammer_neu"]) / (n + 1) - summe / n)
    # KI-Muster, Semikolons, Abkürzungen (je 1000 Token)
    if typ in ("floskel", "gegenfolie", "strohmann") and h.get("muster_gewicht"):
        plus("ki_muster_pro_1000", -1000.0 * h["muster_gewicht"] / tok)
    if typ == "semikolon" and nr in L.nach_nr:
        plus("semikolon_pro_1000", -1000.0 * max(1, L.masken.get(nr, "").count(";")) / tok)
    if typ == "abkuerzung":
        plus("abkuerzungen_pro_1000", 1000.0 * len(h.get("funde") or [h.get("fund")]) / tok)
    # Funktionswörter und MATTR
    weg, dazu = dict(h.get("fw_weg") or {}), dict(h.get("fw_dazu") or {})
    if typ == "nebensatz" and nr in L.nach_nr and not weg:
        mk = L.masken.get(nr, "")
        for w, (wg, dz) in NEBENSATZ_FW.items():
            if re.search(rf",\s+{w}\b", mk):
                weg, dazu = dict(wg), dict(dz)
                break
    if typ == "kein_bezug" and h.get("paar"):
        y, x = h["paar"]
        weg, dazu = {y.lower(): 1}, {x.lower(): 1}
    if typ == "anknuepfung" and h.get("bezug"):
        dazu[h["bezug"].lower()] = dazu.get(h["bezug"].lower(), 0) + 1
    if L.fw_profil and L.fw_diag:
        if typ in FW_TYPEN and h.get("fw_delta") is not None:
            d_llr = h["fw_delta"]
        elif weg or dazu:
            menge = set(L.fw_profil.get("woerter") or [])
            d_llr = fw_delta(L.fw_diag, L.fw_profil, Counter({w: c for w, c in weg.items() if w in menge}),
                             Counter({w: c for w, c in dazu.items() if w in menge}))
        else:
            d_llr = 0.0
        if d_llr:
            plus("fw_profil_llr_pro_1000", d_llr)
    if (weg or dazu) and nr is not None:
        plus("mattr_100", mattr_delta(L, nr, weg, dazu))
    if typ == "synonyme" and h.get("zaehlung"):
        z = {str(k).lower(): v for k, v in h["zaehlung"].items()} if isinstance(h["zaehlung"], dict) else {}
        if len(z) >= 2:
            haupt = max(z, key=lambda k: z[k])
            plus("mattr_100", mattr_delta(L, None, None, None, {k: haupt for k in z if k != haupt}))
    # Begriffsaufnahme: der Begriff des Vorsatzes steht danach auch in Satz nr
    if typ == "anknuepfung" and h.get("bezug") and nr is not None:
        plus("nachbarsatz_ueberlappung", ueberlappung_delta(L, nr, _stamm_von(L, h["bezug"])))
    if typ == "kein_bezug" and h.get("paar") and nr is not None:
        plus("nachbarsatz_ueberlappung", ueberlappung_delta(L, nr, _stamm_von(L, h["paar"][1]), _stamm_von(L, h["paar"][0])))
    # Wörter pro Teilsatz: ein Teilsatz weniger (Nebensatz bzw. Komma → Nominalgruppe)
    if typ in ("nebensatz", "fw_dass") or (typ == "kommas" and h.get("variante") == "nominal"):
        t_sum = sum(_teilsaetze(s) for s in L.fokus)
        if t_sum > 1:
            plus("woerter_pro_teilsatz", tok / (t_sum - 1) - tok / t_sum)
    teile = {k: round(modell_delta(L, {k: d}), 4) for k, d in dm.items() if d}
    return round(sum(teile.values()), 4), teile


# ---------------------------------------------------------------------------
# Eingabeprüfung (v7): verklebte Wörter, Anteil wörtlicher Zitate, erwartete neue Formen
# ---------------------------------------------------------------------------

# Rückfall, solange analyse.py info['verklebt'] nicht liefert – dieselbe Regel wie dort: Satzzeichen direkt vor ≥ 2 Buchstaben
# („erfasst.Merkmale“, „Note,wie“; nach . ! ? nur vor Großbuchstaben) oder ein Token über 25 Zeichen mit innerem Komma bzw.
# Klein-Groß-Wechsel; ausgenommen Abkürzungen und Initialen, URLs, E-Mail-Adressen, Dateinamen, Zahlen, Gender-Doppelpunkt, Binnen-I
_VERKLEBT_RE = re.compile(r"(?<=\w)([.,;:!?])([A-Za-zÄÖÜäöüß]{2,})")
_VERKLEBT_URL_RE = re.compile(r"://|^www\.|@|[A-Za-z0-9-]\.(?:de|com|org|net|eu|at|ch|edu|gov|info|io|uk|fr|it|nl)(?:/|$)")
_VERKLEBT_DATEI_RE = re.compile(r"\.(?:pdf|docx?|xlsx?|csv|txt|py|md|json|html?|jpe?g|png|gif|zip|pptx?|odt|xml|sav|dta|tex|bib|js|r)$",
                                re.IGNORECASE)
_KLEIN_GROSS_RE = re.compile(r"[a-zäöüß](?!I(?:nnen|n\b))[A-ZÄÖÜ]")


def _verklebt(kern: str) -> bool:
    if _VERKLEBT_URL_RE.search(kern) or _VERKLEBT_DATEI_RE.search(kern):
        return False
    abk = set(getattr(analyse, "ABKUERZUNGEN", set())) | set(getattr(analyse, "MEHRDEUTIG", set()))
    for m in _VERKLEBT_RE.finditer(kern):
        zeichen, rechts = m.group(1), m.group(2)
        links = kern[:m.start(1)]
        if links[-1:].isdigit():
            continue
        lw = re.search(r"[A-Za-zÄÖÜäöüß]+$", links)
        if not lw or len(lw.group(0)) == 1 or lw.group(0).lower() in abk:
            continue
        if zeichen in ".!?" and not rechts[0].isupper():
            continue
        if zeichen == ":" and re.match(r"in(?:nen)?$", rechts):
            continue
        return True
    if len(kern) > 25:
        if re.search(r"[^\W\d_],[^\W\d_]", kern):
            return True
        if any(len(teil) > 12 and _KLEIN_GROSS_RE.search(teil) for teil in kern.split("-")):
            return True
    return False


def verklebte_stellen(saetze: list[dict]) -> list[dict]:
    """Verklebte Wörter (PDF-Extraktion): [{'stelle', 'satz'}] wie analyse.py info['verklebt'] (Rückfall)."""
    f = getattr(analyse, "verklebte_stellen", None)
    if f:
        try:
            return f(saetze)
        except Exception:  # noqa: BLE001 – Rückfall auf die eigene Erkennung
            pass
    out = []
    for s in saetze:
        for tok in s["text"].split():
            kern = tok.strip("\"'„“”»«‚‘’()[]{}").rstrip(".,;:!?").rstrip("\"'“”»«’‘)]}")
            if kern and _verklebt(kern):
                out.append({"stelle": kern if len(kern) <= 60 else kern[:59] + "…", "satz": s.get("nr")})
    return out


def zitat_anteil_rueckfall(L: Lauf) -> float:
    """Anteil der Wörter im Fokus, die in wörtlichen Zitaten stehen (Zitatmasken; Quellenklammern mitgezählt)."""
    gesamt = zitiert = 0
    for s in L.fokus:
        alle = [t for t in analyse.tokens(s["text"]) if analyse.ist_wort(t)]
        frei = [t for t in analyse.tokens(L.masken.get(s["nr"], s["text"]).replace(MASKE, " ")) if analyse.ist_wort(t)]
        gesamt += len(alle)
        zitiert += max(0, len(alle) - len(frei))
    return round(zitiert / gesamt, 4) if gesamt else 0.0


ZITAT_ANTEIL_HOCH = 0.25


def _bereinigung(L: Lauf) -> None:
    """Verklebte Wörter (fehlende Leerzeichen aus der PDF-Extraktion) zuerst trennen: sie verzerren Satzgrenzen, Satz- und
    Wortlängen und damit die übrigen Messwerte (v6-Prüfung, fhws: allein die zwei Stellen getrennt → Score 51 → 56)."""
    info = L.erg.get("info") or {}
    stellen = info["verklebt"] if "verklebt" in info else verklebte_stellen(L.saetze)
    if not stellen:
        return
    teile = [f"„{x['stelle']}“" + (f" (S{x['satz']})" if x.get("satz") else "") for x in stellen[:6]]
    rest = f" und {len(stellen) - 6} weitere" if len(stellen) > 6 else ""
    neu = sorted({t.lower() for x in stellen for t in re.split(r"[.,;:!?]|(?<=[a-zäöüß])(?=[A-ZÄÖÜ])", x["stelle"]) if len(t) > 2})
    if L.hinweis("bereinigung", None, f"Verklebte Wörter trennen (verzerrt die Messung): {', '.join(teile)}{rest} – nur die fehlenden "
                 "Leerzeichen einfügen, sonst nichts ändern.", 5.0, anfang="bereinigung:" + "|".join(x["stelle"] for x in stellen[:6])):
        L.hinweise[-1].update({"stellen": stellen, "erwartet": neu})


def erwartete_formen(L: Lauf, h: dict) -> list[str]:
    """Neue Formen, die ein Auftrag erwartbar in den Text bringt (kleingeschrieben): Maskulinform der Gender-Vorgabe, Bezugsnomen
    bei Anknüpfung bzw. Begriffsaufnahme, wiederholtes Nomen beim Teilen, Kurzform der Abkürzungen, getrennte Wörter der
    Bereinigung. inhalt_check.py --verlauf zählt sie nicht als neuen Begriff."""
    out = set(h.get("erwartet") or [])
    typen = set(h.get("typen") or [h["typ"]])
    if "abkuerzung" in typen:
        kurz = re.search(r"als „([^“]+)“", h.get("text") or "")
        if kurz:
            out |= {kurz.group(1).lower(), kurz.group(1).lower().replace(" ", "")}
    if "anknuepfung" in typen and h.get("bezug"):
        out.add(h["bezug"].lower())
    if "kein_bezug" in typen and h.get("paar"):
        out.add(h["paar"][1].lower())
    if typen & {"teilen", "mitte", "kommas"} and h.get("satz") in L.nach_nr:
        mk = L.masken.get(h["satz"], L.nach_nr[h["satz"]]["text"])
        nomen = [t for t in analyse.tokens(mk) if t[:1].isupper() and analyse.ist_wort(t) and t.lower() not in analyse.FUNKTIONSWOERTER]
        out |= {w.lower() for w in nomen[1:4]}  # Subjekt bzw. Bezugswort, das der zweite Satz als Nomen wiederholt
    return sorted(out)


def coache(text: str, verlauf: dict | None = None, max_hinweise: int = 15, roh: bool = False) -> dict:
    """Misst den Text und erzeugt priorisierte, satzgenaue Hinweise. roh=True liefert zusätzlich 'hinweise_roh'
    (alle Hinweise vor der Auswahl und vor dem Filter bei „Ziel erreicht“, für Auswertungen)."""
    L = Lauf(text, verlauf)
    _bereinigung(L)
    _hebel_priorisieren(L)
    _waechter(L)
    _wirksamkeit(L)
    _neu_geteilt(L)
    _satzlaengen(L)
    _zickzack(L)
    _satzklammer(L)
    # Folgesätze einer Bündelung gehen im ersten Satz auf: dort keine weiteren Wort-Hinweise
    # (bei umgedrehter Richtung geht Satz a in b auf und der Anfang von b ändert sich: dann beide)
    L.gebuendelte_b = {n for h in L.hinweise if h["typ"] in ("buendeln", "klammer_zusatz")
                       for n in (h.get("weitere_nr") or []) + (h.get("eingebettet") or [])}
    _nebensaetze(L)
    _begriffe(L)
    _floskeln(L)  # vor den Funktionswörtern: deckt ein Muster dieselbe Wendung ab, entfällt der Funktionswort-Auftrag
    _funktionswoerter(L)
    _zeichen(L)
    _abkuerzungen(L)
    _absaetze(L)
    _vorgaben(L)
    _konsistenz(L)
    _laengenwirkung(L)
    _gedaechtnis(L)
    return _ergebnis(L, max_hinweise, roh)


VORGABE_TYPEN = {"gender", "gedankenstrich", "bindestrich"}  # Nutzer-Vorgaben: eigener Abschnitt, ändern den Score nicht


def _ziele(L: Lauf) -> dict:
    """Ziele und Lücken: Modell (p_mensch ≥ ziel_p_mensch) und einseitiger Score (score_ki ≥ ziel_score_ki – Abweichungen zur
    menschlichen Seite zählen nicht); solange die Messseite diese Felder nicht liefert, der zweiseitige Score mit ziel_score."""
    bew, ts = L.bew, L.ts
    ziel_p = bew.get("ziel_p_mensch") or ts.get("ziel_p_mensch") or 0.5
    ziel2 = ts.get("ziel_score") or bew.get("ziel_score") or bew.get("score_schwelle") or ts.get("score_schwelle") or 60
    ziel_ki = bew.get("ziel_score_ki") or ts.get("ziel_score_ki")
    if bew.get("score_ki") is not None and ziel_ki is not None:
        score, ziel_score, einseitig = bew["score_ki"], ziel_ki, True
    else:
        score, ziel_score, einseitig = bew.get("score"), ziel2, False
    p = bew.get("p_mensch")
    ganz = math.ceil(ziel_score - 1e-9)
    luecke_p = max(0.0, ziel_p - p) if p is not None else 0.0
    return {"ziel_p": ziel_p, "ziel_score": ziel_score, "ziel_score_anzeige": ganz, "score": score, "einseitig": einseitig,
            "p": p, "luecke_p": luecke_p, "luecke_score": max(0, ganz - (score or 0)),
            "luecke_logit": (_logit(ziel_p) - _logit(p)) if luecke_p > 0 else 0.0}


def gegenseite_punkte(L: Lauf, Z: dict) -> float:
    """Score-Punkte, die Kennzahlen auf der der KI abgewandten Seite kosten (gelb ≈ 50, rot ≈ 100 · Gewicht / Gewichtssumme). Nur im
    Rückfall auf den zweiseitigen Score; einseitig zählen sie ohnehin wie grün (0). Decken sie die Score-Lücke, wäre der Text
    einseitig gerechnet am Ziel: dann keine Score-Aufträge auf der KI-Seite (Info „Menschlicher als typisch“ statt Punktesammeln)."""
    if Z.get("einseitig"):
        return 0.0
    bew = L.bew
    gsum = sum(max(0.0, float(z["gewicht"] or 0)) for z in bew.get("kennzahlen", []) if z["bewertet"]) or 1.0
    return sum((50.0 if z["status"] == "gelb" else 100.0) * max(0.0, float(z["gewicht"] or 0)) / gsum
               for z in L.kz.values() if z["bewertet"] and z["status"] != "gruen" and z["seite"] == "gegen")


def _teilziel_familien(L: Lauf, fehlt: float) -> list[str]:
    """Hebel der gewichtigsten Kennzahlen auf der KI-Seite, die eine Score-Lücke schließen (je Kennzahl gelb → grün bzw.
    rot → gelb ≈ 50 · Gewicht / Gewichtssumme Punkte)."""
    bew, kz, diag = L.bew, L.kz, L.diag
    gsum = sum(max(0.0, float(z["gewicht"] or 0)) for z in bew["kennzahlen"] if z["bewertet"]) or 1.0
    offen = sorted((z for z in kz.values() if z["bewertet"] and z["status"] != "gruen" and z["seite"] == "ki"
                    and not (z["status"] == "gelb" and z.get("unsicher"))), key=lambda z: -(z["gewicht"] or 0))
    familien, punkte = [], 0.0
    semikolon_ok = semikolon_zahl(L) <= semikolon_erlaubt(L)
    for z in offen:
        if z["id"] == "semikolon_pro_1000" and semikolon_ok:
            continue  # höchstens 1–2 Semikolons je 800 Wörter: unauffällig, kein Score-Hebel
        h = HEBEL_VON.get(z["id"])
        if h == "satzlaenge" and diag.get("modus") == "teilen":
            if not diag.get("ueberkorrektur"):
                continue  # lange Sätze auf der Gegenseite ohne Überkorrektur: kein Teilen-Auftrag (Info „menschlicher als typisch“)
            h = "satzlaenge_bremse"
        punkte += 50.0 * max(0.0, float(z["gewicht"] or 0)) / gsum
        if h and h not in familien:
            familien.append(h)
        if punkte >= fehlt:
            break
    return familien


def semikolon_zahl(L: Lauf) -> int:
    """Semikolons im Fokus außerhalb wörtlicher Zitate (ohne Zahlzeichen)."""
    f = getattr(analyse, "_ohne_zahlzeichen", lambda x: x)
    return sum(f(L.masken.get(s["nr"], s["text"])).count(";") for s in L.fokus)


def semikolon_erlaubt(L: Lauf) -> int:
    """Semikolons, die in einem Text dieser Länge unauffällig sind: höchstens 1–2 je 800 Wörter (Mensch P90 ≈ 2,4 je 1000)."""
    woerter = sum(s["woerter"] for s in L.fokus)
    return max(1, round(2 * woerter / 800))


def _semikolon_vorher(L: Lauf) -> int | None:
    """Semikolons der Vorrunde: gespeichert (v7) oder aus dem Wert je 1000 Token geschätzt (ältere Verläufe)."""
    v = L.vorher or {}
    if (v.get("zaehler") or {}).get("semikolon") is not None:
        return v["zaehler"]["semikolon"]
    wert = ((v.get("kennzahlen") or {}).get("semikolon_pro_1000") or {}).get("wert")
    return round(wert * L.tok_fokus / 1000) if wert is not None else None


def menschlicher_als_typisch(L: Lauf, ausser: set[str]) -> list[dict]:
    """Kennzahlen jenseits P10/P90 auf der der KI abgewandten Seite (Feld jenseits_band der Messseite; Rückfall: selbst
    berechnet). Kein Auftrag – auf menschlichen Texten ist das Eigenart, bei Claudes eigenem Entwurf eine Überkorrektur, die der
    Schreib-Skill zurücknimmt. Bewertete und Modell-Kennzahlen zuerst."""
    out = []
    for z in L.bew.get("kennzahlen", []):
        if z["id"] in ausser or z["id"] not in L.ref:
            continue
        jb = z.get("jenseits_band")
        if jb is None:
            jb = z["status"] == "rot" and seite_von(z["wert"], L.ref[z["id"]]) == "gegen"
        if jb:
            out.append(z)
    return sorted(out, key=lambda z: (not (z["bewertet"] or z.get("nur_modell")), -(z.get("gewicht") or 0), z["id"]))


def _p_anzeige(p: float, ziel: float) -> str:
    """p in Prozent; mit einer Nachkommastelle, wenn es weniger als einen Prozentpunkt vom Ziel entfernt ist (85,6 % statt 86 %)."""
    if p is None:
        return "–"
    if abs(p - ziel) < 0.01 and p != ziel:
        return f"{100 * p:.1f}".replace(".", ",") + " %"
    return f"{round(100 * p)} %"


def _ergebnis(L: Lauf, max_hinweise: int, roh: bool) -> dict:
    """Auswahl (Ziel erreicht / Messunsicherheit / Teilziel / Modell-Lücke mit Netto-Simulation), Hebelanzeige, Verlaufseintrag
    und Diagnose. Vorgaben (Gender, Gedankenstrich) stehen getrennt und zählen nicht aufs Limit; die Bereinigung verklebter Wörter
    steht immer zuerst."""
    bew, ts, diag, kz = L.bew, L.ts, L.diag, L.kz
    Z = _ziele(L)
    ziel_p, ziel_score = Z["ziel_p"], Z["ziel_score"]
    ziel_rot = ts.get("ziel_rot_max")
    rot = [z for z in bew.get("kennzahlen", []) if z["bewertet"] and z["status"] == "rot"]
    ziel_erreicht = bool(bew.get("verfuegbar") and (Z["score"] or 0) >= ziel_score
                         and (Z["p"] is None or Z["p"] >= ziel_p)
                         and (ziel_rot is None or len(rot) <= ziel_rot))
    rauschen = bool(bew.get("verfuegbar") and not ziel_erreicht and Z["luecke_p"] <= RAUSCHEN_P
                    and Z["luecke_score"] <= RAUSCHEN_SCORE)
    gesehen, eindeutig = set(), []
    for h in sorted(L.hinweise, key=lambda h: -h["gewicht"]):
        schluessel = (h["typ"], h["satz"], h["absatz"], h["text"] if h["satz"] is None else h["text"][:40])
        if schluessel not in gesehen:
            gesehen.add(schluessel)
            eindeutig.append(h)
    alle_roh = list(eindeutig)
    bereinigung = [h for h in eindeutig if h["typ"] == "bereinigung"]
    vorgaben = [h for h in eindeutig if h["typ"] in VORGABE_TYPEN]
    eindeutig = [h for h in eindeutig if h["typ"] not in VORGABE_TYPEN and h["typ"] != "bereinigung"]
    for h in eindeutig:
        h["netto_logit"], h["netto_teile"] = netto_wirkung(L, h)
    # Semikolons: höchstens 1–2 je 800 Wörter sind unauffällig; bei „Ziel erreicht“ nur, wenn die Anzahl gestiegen ist; ohne
    # Modell-Lücke nur so viele Aufträge, wie über dieser Zahl liegen (mit Modell-Lücke entscheidet die Netto-Simulation)
    n_semi, n_semi_alt = semikolon_zahl(L), _semikolon_vorher(L)
    semi = [h for h in eindeutig if h["typ"] == "semikolon"]
    if ziel_erreicht:
        frei_semi = max(0, n_semi - n_semi_alt) if n_semi_alt is not None else 0
    elif Z["luecke_p"] > 0:
        frei_semi = len(semi)
    else:
        frei_semi = max(0, n_semi - semikolon_erlaubt(L))
    weg_semi = {id(h) for h in semi[frei_semi:]}
    eindeutig = [h for h in eindeutig if id(h) not in weg_semi]
    if ziel_erreicht:
        # nur hochpräzise Hinweise (Semikolon, KI-Muster mit Gewicht ≥ 1,5); dazu die Satzlängen-Bremse, wenn der Verlauf zeigt,
        # dass der Text über das menschliche Band hinaus getrieben wurde
        bremse = diag["ueberkorrektur"]  # nur mit Beleg aus dem Verlauf: ohne ihn ist ein Text am Ziel auch mit langen Sätzen unauffällig
        teilen_h = [h for h in eindeutig if h["typ"] == "teilen"][:2] if bremse else []
        eindeutig = [h for h in eindeutig if h["typ"] in ZIEL_TYPEN
                     and (h["typ"] != "floskel" or h.get("muster_gewicht", 0) >= 1.5)] + teilen_h
        max_hinweise = min(max_hinweise, ZIEL_MAX)
    teilziel = None
    if bew.get("verfuegbar") and not ziel_erreicht and not rauschen and Z["p"] is not None and Z["p"] >= ziel_p \
            and (Z["score"] or 0) < ziel_score:
        # Modell-Ziel erreicht, nur der Score fehlt: nur die Hebel der gewichtigsten Kennzahlen, die die Lücke schließen; kein
        # Auftrag, der das Modell simuliert unter das Ziel drückte
        fehlt = Z["luecke_score"]
        gegen = gegenseite_punkte(L, Z)
        deckt = gegen >= fehlt
        # deckt die Gegenseite die Lücke (Rückfall auf den zweiseitigen Score), kein Punktesammeln auf der KI-Seite – der Text wäre
        # einseitig gerechnet am Ziel (v7-Prüfung: fhws p = 1,0, Score 50 / KI-Seite 83 → Absatz teilen + Gegenfolie)
        familien = [] if deckt else _teilziel_familien(L, fehlt)
        teilziel = {"fehlt": fehlt, "hebel": familien, "gegenseite_punkte": round(gegen, 1), "gegenseite_deckt": deckt}
        eindeutig = [h for h in eindeutig if (h["hebel"] in familien or h["hebel"] == "vorgaben" or (h["typ"] == "teilen" and diag["ueberkorrektur"]))
                     and 1 / (1 + math.exp(-(_logit(Z["p"]) + h["netto_logit"]))) >= ziel_p]
        max_hinweise = min(max_hinweise, 8)
    if not ziel_erreicht and Z["luecke_p"] > 0:
        # Modell-Lücke: kein Auftrag, der das Modell simuliert netto verschlechtert
        schaedlich = [h for h in eindeutig if h["netto_logit"] < -NETTO_TOLERANZ and h["typ"] != "teilen"]
        if schaedlich:
            L.unterdrueckt["netto_schaedlich"] += len(schaedlich)
            eindeutig = [h for h in eindeutig if not any(h is x for x in schaedlich)]
    # kein Auftrag, dessen Typ im selben Bericht als ausgesetzt gemeldet wird
    eindeutig = [h for h in eindeutig if h["typ"] not in L.ausgesetzt]
    eindeutig = ein_auftrag_je_satz(eindeutig, {s["nr"]: L.masken.get(s["nr"], s["text"]) for s in L.saetze})
    messunsicherheit = None
    # Gegenaufträge nach einer Überkorrektur aus Coach-Aufträgen (Teilen) gelten wie bisher – außerhalb von Messunsicherheit und
    # Auftragsgrenze, die nur das Modell rechnen (Teilen nimmt dort lange Sätze zurück, die das Modell belohnt)
    gegen_uk = [h for h in eindeutig if diag.get("ueberkorrektur") and "teilen" in (h.get("typen") or [h["typ"]])]
    eindeutig = [h for h in eindeutig if not any(h is x for x in gegen_uk)]
    if rauschen:
        # im Bereich der Messunsicherheit: ausdrücklich sagen, höchstens der eine Auftrag mit dem größten Effekt
        if Z["luecke_p"] > 0:
            pos = [h for h in eindeutig if h.get("netto_logit", 0) > NETTO_TOLERANZ]
            bester = max(pos, key=lambda h: h["netto_logit"]) if pos else None
        else:
            familien = [] if gegenseite_punkte(L, Z) >= Z["luecke_score"] else _teilziel_familien(L, max(1, Z["luecke_score"]))
            pos = [h for h in eindeutig if h["hebel"] in familien and h.get("netto_logit", 0) >= -NETTO_TOLERANZ]
            bester = min(pos, key=lambda h: (familien.index(h["hebel"]), -h.get("netto_logit", 0))) if pos else None
        eindeutig = [bester] if bester else []
        messunsicherheit = {"luecke_p": round(Z["luecke_p"], 4), "luecke_score": Z["luecke_score"]}
    elif not ziel_erreicht and Z["luecke_p"] > 0:
        # kleine Modell-Lücke: Aufträge nach simuliertem Netto-Δ-Logit, bis die Summe das 1,5-Fache der Lücke erreicht (bei
        # einer Lücke unter 0,02 höchstens zwei); fehlt zusätzlich Score, kommen die Score-Hebel dazu
        luecke = Z["luecke_logit"]
        pos = sorted((h for h in eindeutig if h.get("netto_logit", 0) > NETTO_TOLERANZ), key=lambda h: -h["netto_logit"])
        klein = Z["luecke_p"] < KLEINE_LUECKE_P
        if klein or sum(h["netto_logit"] for h in pos) >= NETTO_FAKTOR * luecke:
            gewaehlt, summe = [], 0.0
            for h in pos:
                if summe >= NETTO_FAKTOR * luecke or (klein and len(gewaehlt) >= KLEINE_LUECKE_MAX):
                    break
                gewaehlt.append(h)
                summe += h["netto_logit"]
            score_teil = []
            if Z["luecke_score"] > RAUSCHEN_SCORE and gegenseite_punkte(L, Z) < Z["luecke_score"]:
                familien = _teilziel_familien(L, Z["luecke_score"])
                score_teil = [h for h in eindeutig if h["hebel"] in familien and not any(h is x for x in gewaehlt)]
                teilziel = {"fehlt": Z["luecke_score"], "hebel": familien, "mit_modell": True}
            L.auftragsgrenze = {"luecke_logit": round(luecke, 3), "summe_logit": round(summe, 3), "gewaehlt": len(gewaehlt),
                                "verworfen": len(eindeutig) - len(gewaehlt) - len(score_teil)}
            eindeutig = gewaehlt + score_teil[:max(0, 8 - len(gewaehlt))]
    eindeutig = gegen_uk + eindeutig
    stapel: dict[str, list[dict]] = {}
    for h in sorted(eindeutig, key=lambda h: -h["gewicht"]):  # schon genannte (herabgestuft) machen Platz für neue
        stapel.setdefault(h["hebel"], []).append(h)
    hebel = L.hebel
    hebel_folge = sorted(stapel, key=lambda h: -hebel.get(h, {}).get("prioritaet", 0))
    auswahl = []
    while len(auswahl) < max_hinweise and any(stapel.values()):
        for h in hebel_folge:
            if stapel[h] and len(auswahl) < max_hinweise:
                auswahl.append(stapel[h].pop(0))
    auswahl = bereinigung + auswahl
    if bew.get("verfuegbar") and not ziel_erreicht and not rauschen and Z["luecke_p"] > 0 \
            and not any(h["typ"] != "bereinigung" and not h.get("info") for h in auswahl):
        # keine Sackgasse: unter dem Modellziel ohne jeden Auftrag die sicheren kleinen Stellen („klein, aber sicher“)
        klein = []
        for h in klein_sicher(L):
            h["netto_logit"], h["netto_teile"] = netto_wirkung(L, h)
            if h["netto_logit"] >= -NETTO_TOLERANZ:
                klein.append(h)
        klein = klein[:max_hinweise]
        auswahl += klein
        eindeutig = eindeutig + klein
    if getattr(L, "auftragsgrenze", None) is not None:
        # die angezeigten Aufträge: reichen sie simuliert für das 1,5-Fache der Lücke? (sonst bleibt die Diagnose)
        L.auftragsgrenze["summe_logit"] = round(sum(max(0.0, h.get("netto_logit") or 0.0) for h in auswahl), 3)
        L.auftragsgrenze["reicht"] = L.auftragsgrenze["summe_logit"] >= NETTO_FAKTOR * Z["luecke_logit"]

    # Hebel-Anzeige: im TEILEN-Modus immer die Bremse statt „Lange Sätze ja … KI-Texte bleiben im mittleren Band“ – auch ohne
    # Teilen-Auftrag, sonst lädt der Hebeltext zu weiteren langen Sätzen ein
    if diag["modus"] == "teilen" and not diag.get("ueberkorrektur") and not any(h["typ"] == "teilen" for h in L.hinweise):
        hebel.pop("satzlaenge", None)  # lange Sätze auf der Gegenseite ohne Überkorrektur: Info „Menschlicher als typisch“, kein Hebel
    elif diag["modus"] == "teilen" and ("satzlaenge" in hebel or any(h["typ"] == "teilen" for h in L.hinweise)):
        alt = hebel.pop("satzlaenge", None)
        hebel.setdefault("satzlaenge_bremse", {"prioritaet": max(1.0, alt["prioritaet"] if alt else 0.0),
                                               "kennzahlen": [kz[k] for k in ("anteil_lange_saetze", "satzlaenge_mittel",
                                                                              "anteil_mittlere_saetze") if k in kz]})
    reihenfolge = sorted(hebel, key=lambda h: -hebel[h]["prioritaet"])
    daten = satzlaenge_daten(L.ref, L.ziel_vert)
    # „nur über die genannten Konstruktionen“ nur, wenn ein Funktionswort-Auftrag auch angezeigt wird
    fw_text = _fw_hebeltext(L, any(h["typ"] in FW_TYPEN or set(h.get("typen") or []) & set(FW_TYPEN) for h in auswahl))

    mit_stellen = {x["hebel"] for x in eindeutig} | {TYP_HEBEL.get(t, t) for x in eindeutig for t in x.get("typen") or []}
    konn_vorhanden = {t.group(1).lower() for s in L.fokus for t in KONNEKTOR_RE.finditer(L.masken.get(s["nr"], s["text"]))}

    def hebel_eintrag(h: str) -> dict:
        typen = set(HEBEL_TYPEN.get(h, set()))
        if h == "satzlaenge":  # der Typ, der im aktuellen Modus den Hebel trägt
            typen = {"mitte"} if diag.get("modus") == "mitte" else {"buendeln"}
        aus = bool(typen) and typen <= L.ausgesetzt and not any(x["hebel"] == h for x in auswahl)
        gruende = sorted({g for t in typen for g in L.aussetz_grund.get(t, [])}) if aus else []
        warum = fw_text if h == "funktionswoerter" and fw_text else hebel_warum(h, L.ref, daten, L.fw_profil, konn_vorhanden)
        # ohne einen einzigen Auftrag dieser Runde ist der Hebel kein Arbeitsauftrag, sondern nur Orientierung (mit Technik)
        stellenlos = not aus and h not in mit_stellen
        selbst = SELBSTHILFE_HEBEL.get(h) if stellenlos else None
        if stellenlos and h == "funktionswoerter" and fw_text:
            selbst = fw_text  # Stellenliste (notwendig / umbaubar) statt der allgemeinen Technik
        if stellenlos and h == "satzlaenge" and buendel_raum(L) == 0:
            selbst = "Satzlängen diese Runde so lassen – weitere lange Sätze ließen die Grenzen gegen Überkorrektur nicht zu"
        elif stellenlos and h == "satzlaenge" and selbst and teilsatz_hoch(L):
            selbst = selbst.rstrip(".") + NUR_NEBENSATZ_PAARE
        if stellenlos and h == "abkuerzungen":
            # dieselbe Quelle wie die Diagnose: nur vorhandene Langformen, nie einstreuen
            selbst = abk_selbsthilfe(L) or ("keine weiteren einbauen – schon eine weitere Abkürzung läge über dem menschlichen Median"
                                            if abk_plan(L)[2] <= 0 else
                                            "keine einstreuen – im Text steht keine ausgeschriebene Abkürzung, die sich kürzen ließe")
        if stellenlos and h == "konnektoren":
            # nur Konnektoren, die im Text stehen (v6-Prüfung, ssoar: Selbsthilfe „zugleich streichen“ ohne ein „zugleich“)
            typisch = [k for k in sorted(konn_vorhanden, key=lambda k: -(konnektor_verhaeltnis(k) or 0))
                       if (konnektor_verhaeltnis(k) or 0) > KONN_STARK]
            selbst = (f"{' bzw. '.join(f'„{k}“' for k in typisch[:3])} streichen, wo der Bezug klar ist (nicht nach „nicht nur“, "
                      "„zwar“, „einerseits“); andere Satzverknüpfer nur, wenn derselbe im Absatz gehäuft steht") if typisch else \
                "Erlaubt bleibt: die übrigen Konnektoren stehen lassen – im Text steht keiner, der bei Claude deutlich häufiger ist"
        if stellenlos and h == "floskeln":
            rest_m = muster_rest(L)[0]
            selbst = muster_selbsthilfe(rest_m) or (muster_kein_rest(L) if L.kz.get("ki_muster_pro_1000") else selbst)
        return {"id": h, "name": HEBEL_TEXT[h][0], "warum": warum, "prioritaet": round(hebel[h]["prioritaet"], 2),
                "ausgesetzt": gruende if aus else None, "alternative": alternative_text(L, h) if aus else None,
                "stellenlos": stellenlos, "selbsthilfe": selbst,
                "kennzahlen": [{k: z.get(k) for k in ("id", "name", "wert", "mensch_p25", "mensch_p50", "mensch_p75", "ki_p50", "status",
                                                      "richtung", "nur_modell", "beitrag", "bewertet")} for z in hebel[h]["kennzahlen"]]}

    ersetzbar = sorted({w for h in auswahl + vorgaben for w in h.get("ersetzbar", [])})
    erwartet = sorted({w for h in auswahl + vorgaben for w in erwartete_formen(L, h)})
    stehen_lassen = [] if ziel_erreicht else [x for x in L.stehen_lassen if L.von <= x["satz"] <= L.bis]
    werte = {k: L.wert(k) for k in set(ZIEL_KENNZAHL.values())}
    traeger = {"buendeln": "buendeln", "teilen": "teilen", "mitte": "mitte"}.get(diag.get("modus"))
    modus_json = "ausgesetzt" if traeger and traeger in L.ausgesetzt else diag["modus"]
    # keine Diagnose, wenn die Auftragsgrenze greift: die genannten Stellen reichen simuliert für das 1,5-Fache der Lücke
    diagnose = None if ziel_erreicht or (teilziel and not teilziel.get("mit_modell")) or rauschen \
        or (getattr(L, "auftragsgrenze", None) or {}).get("reicht") else _diagnose(L, auswahl, ziel_p)
    diagnose_wie = None
    if not diagnose and not ziel_erreicht and not teilziel and not rauschen and text_unveraendert(L) \
            and (L.vorher or {}).get("diagnose_kurz"):
        diagnose_wie = dict(L.vorher["diagnose_kurz"], messung=len(L.messungen))  # nur erneut gemessen: Kurzfassung
    hinweis_felder = ("typ", "typen", "anfang", "satz", "ziel", "ziel_wert", "laenge", "weitere", "zaehlung", "pos", "laengen_alt", "sim",
                      "variante", "teilsaetze", "netto_logit", "technik")
    stand = {"score": bew.get("score"), "score_ki": bew.get("score_ki"), "p_mensch": bew.get("p_mensch"),
             "kennzahlen": {z["id"]: {"wert": z["wert"], "status": z["status"]} for z in bew.get("kennzahlen", []) if z["bewertet"]},
             "roh": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in L.roh_jetzt.items()},
             "werte": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in werte.items() if v is not None},
             "bloecke": [{k: b.get(k) for k in ("nr", "satz_von", "satz_bis", "p_mensch", "score")} for b in L.bloecke],
             "hinweise": [{k: h.get(k) for k in hinweis_felder if k in ("typ", "anfang", "satz") or h.get(k) is not None}
                          for h in auswahl + vorgaben],
             "ersetzbar": ersetzbar, "erwartet": erwartet, "satzlaengen_modus": modus_json, "laengen": [x["woerter"] for x in L.fokus],
             "zaehler": {"semikolon": n_semi},
             "stehen_lassen": [x["anfang"] for x in stehen_lassen],
             "diagnose_kurz": ({k: diagnose[k] for k in ("grenze", "luecke_logit", "erreichbar_logit", "stellenlos_logit", "fw_dominant")}
                               if diagnose else (L.vorher or {}).get("diagnose_kurz") if diagnose_wie else None)}
    fortschritt = None
    vorher = L.vorher
    ueberkorrektur = list(L.ueberkorrektur)
    if ziel_erreicht:
        # am Ziel warnt der Coach erst jenseits P90/P10 (gelbe Verschiebungen innerhalb des menschlichen Bands sind unauffällig)
        ueberkorrektur = [u for u in ueberkorrektur if u["id"] in L.ref and status_von(u["wert"], L.ref[u["id"]]) == "rot"]
    if vorher:
        reihen = ["rot", "gelb", "gruen"]
        alt_kz = vorher.get("kennzahlen") or {}
        besser = [k for k, v in stand["kennzahlen"].items() if k in alt_kz and reihen.index(v["status"]) > reihen.index(alt_kz[k]["status"])]
        schlechter = [k for k, v in stand["kennzahlen"].items() if k in alt_kz and reihen.index(v["status"]) < reihen.index(alt_kz[k]["status"])]
        if "semikolon_pro_1000" in schlechter and n_semi_alt is not None and n_semi <= n_semi_alt:
            schlechter.remove("semikolon_pro_1000")  # Hysterese: Status kippt nur durch die Wortzahl, kein Semikolon dazugekommen
        # schon rot und auf der KI-Seite um ≥ 0,25 IQR weiter weg vom menschlichen Median (v6-Prüfung, Agile R2 → R3: Verhältnis 2:1
        # 1,11 → 1,17 ohne jede Erwähnung)
        weiter_rot = []
        for k, v in stand["kennzahlen"].items():
            if k not in alt_kz or k not in L.ref or v["status"] != "rot" or alt_kz[k].get("status") != "rot" or k == "semikolon_pro_1000":
                continue
            r = L.ref[k]["mensch"]
            iqr = (r["p75"] - r["p25"]) or ((r["p90"] - r["p10"]) / 2) or 1e-9
            w0, w1 = alt_kz[k].get("wert"), v["wert"]
            if w0 is not None and seite_von(w1, L.ref[k]) == "ki" and abs(w1 - r["p50"]) - abs(w0 - r["p50"]) >= 0.25 * iqr:
                weiter_rot.append(k)
        einseitig_vorher = Z["einseitig"] and vorher.get("score_ki") is not None
        fortschritt = {"score_vorher": vorher.get("score_ki") if einseitig_vorher else vorher.get("score"),
                       "p_mensch_vorher": vorher.get("p_mensch"), "besser": besser, "schlechter": schlechter, "weiter_rot": weiter_rot,
                       "messung_nr": len(L.messungen) + 1,
                       "mechanisch_verlaengert": mechanisch_verlaengert(vorher.get("roh", {}), stand["roh"]),
                       "ueberkorrektur": ueberkorrektur, "ausgesetzt": sorted(L.ausgesetzt), "wirkung": L.wirkung,
                       "unveraendert": text_unveraendert(L)}
    # menschlicher als typisch: Info, kein Auftrag (auch bei „Ziel erreicht“); ohne die schon gemeldeten Überkorrekturen und ohne
    # die Werte der Warnung „Schon jenseits des menschlichen Bereichs“, solange sie erscheint
    schon = {u["id"] for u in ueberkorrektur if u["art"] == "Überkorrektur"}
    if not ziel_erreicht:
        schon |= {j["id"] for j in L.jenseits}
    menschlich = [{k: z.get(k) for k in ("id", "name", "wert", "mensch_p10", "mensch_p90", "bewertet", "nur_modell")}
                  for z in menschlicher_als_typisch(L, schon)]
    menschlich_unbewertet = sum(1 for z in menschlich if not (z["bewertet"] or z["nur_modell"]))
    menschlich = [z for z in menschlich if z["bewertet"] or z["nur_modell"]]
    info = L.erg.get("info") or {}
    verklebt = info["verklebt"] if "verklebt" in info else verklebte_stellen(L.saetze)
    zitat_anteil = info["zitat_anteil"] if info.get("zitat_anteil") is not None else zitat_anteil_rueckfall(L)

    # „Schon gut“ nur, was im Modell kaum Richtung KI zieht (sonst stünde z. B. „keine Abkürzungen“ als gut da)
    gruen = sorted([z for z in bew.get("kennzahlen", []) if z["bewertet"] and z["status"] == "gruen"
                    and (z.get("beitrag") is None or z["beitrag"] >= SCHON_GUT_AB)], key=lambda z: -(z["gewicht"] or 0))
    diag_aus = {k: diag.get(k) for k in ("modus", "kontingent", "n", "lange", "mittlere", "kurze", "gruende", "abweichungen",
                                         "ueberkorrektur", "ueber_p90", "fehlende_mitte")}
    diag_aus.update({k: round(diag[k], 3) for k in ("anteil_lange", "anteil_mittlere", "anteil_kurze", "mittel", "schiefe") if diag.get(k) is not None})
    diag_aus["l1"] = round(diag["l1"], 3) if diag.get("l1") is not None else None
    diag_aus["mittlere_p75"] = L.p_("anteil_mittlere_saetze", "p75")
    diag_aus["selbst_buendeln"] = buendel_raum(L)  # Spielraum für weitere lange Sätze ohne Auftrag (0 = keiner)
    diag_aus["teilsatz_hoch"] = teilsatz_hoch(L)  # dann nur Paare aus zwei Sätzen mit je einem Nebensatz
    fw = kz.get("fw_profil_llr_pro_1000")
    ergebnis = {"info": L.erg["info"], "bewertung": {k: bew.get(k) for k in ("score", "score_ki", "p_mensch", "verfuegbar")},
                "hebel": [hebel_eintrag(h) for h in reihenfolge if h in HEBEL_TEXT],
                "hinweise": auswahl, "anzahl_hinweise_gesamt": len(eindeutig) + len(bereinigung),
                "vorgaben": vorgaben, "gender_info": list(L.gender_info),
                "rot": len(rot), "gut": [z["name"] for z in gruen[:4]], "stand": stand, "fortschritt": fortschritt,
                "ziel_p_mensch": ziel_p, "ziel_score": ziel_score, "ziel_score_anzeige": Z["ziel_score_anzeige"],
                "score_ziel_wert": Z["score"], "score_einseitig": Z["einseitig"], "ziel_rot_max": ziel_rot,
                "messunsicherheit": messunsicherheit, "auftragsgrenze": getattr(L, "auftragsgrenze", None),
                "menschlicher_als_typisch": menschlich, "menschlicher_unbewertet": menschlich_unbewertet,
                "verklebt": verklebt, "zitat_anteil": zitat_anteil,
                "bloecke": L.bloecke, "blockmodus": bool(bew.get("blockmodus")),
                "fokus": {"block": L.fokus_block["nr"] if L.fokus_block else None, "satz_von": L.von, "satz_bis": L.bis},
                "satzlaengen": diag_aus, "ersetzbar": ersetzbar, "erwartet": erwartet, "ziel_erreicht": ziel_erreicht,
                "teilziel": teilziel, "jenseits": L.jenseits, "fw_wert": fw["wert"] if fw else None,
                "funktionswoerter": {k: L.fw_diag[k] for k in ("n", "top", "llr")} if L.fw_diag else None,
                "ausgesetzt": {t: g for t, g in L.aussetz_grund.items()}, "unterdrueckt": dict(L.unterdrueckt),
                "diagnose": diagnose, "diagnose_wie": diagnose_wie, "stehen_lassen": stehen_lassen,
                "diagnose_aufgeschoben": getattr(L, "diagnose_aufgeschoben", None) if not diagnose else None}
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


def fmt_paar(a: float, b: float) -> tuple[str, str]:
    """Zwei Werte, die verglichen werden („8,250 über P75 8,249“): eine Stelle mehr, wenn sie gerundet gleich aussähen."""
    if fmt(a) != fmt(b):
        return fmt(a), fmt(b)
    return f"{a:.3f}".replace(".", ","), f"{b:.3f}".replace(".", ",")



def _selbsthilfe_zeilen(d: dict, n: int = 5) -> list[dict]:
    """Merkmale mit Rest ohne sichere Stelle und Selbsthilfe-Technik, die größten zuerst (höchstens n)."""
    zeilen = [z for z in d["beitraege"] if z.get("selbsthilfe") and z.get("rest_logit", z.get("potenzial_logit", 0)) > 0.05]
    return sorted(zeilen, key=lambda z: -z.get("rest_logit", z.get("potenzial_logit", 0)))[:n]


GRENZE_NAME = {"keine": "die genannten Stellen reichen rechnerisch",
               "coach": "Grenze des Coaches – mit den Aufträgen reicht es nicht, rechnerisch aber mit den Merkmalen ohne Auftrag",
               "knapp": "knapp, Schätzung unsicher", "einzelkorrekturen": "Grenze der Einzelkorrekturen",
               "text": "Grenze der Einzelkorrekturen"}  # „text“: Verläufe aus v4


def _absatz_liste(nrn: list[int]) -> str:
    return "Absatz " + " und ".join(str(n) for n in nrn) if nrn else ""


def diagnose_text(d: dict) -> list[str]:
    """Bericht-Abschnitt der ehrlichen Diagnose: Modellbeiträge, jede Zeile mit ihrem Potenzial (die Zeilen ergeben die genannten
    Summen: mit Aufträgen, ohne Auftrag, gesperrt, nur durch Neuformulieren), Einstufung (Grenze des Coaches, knapp, Grenze der
    Einzelkorrekturen; „vorläufig“, solange Aufträge offen sind), Selbsthilfe aus dem Text, Funktionswort-Hinweis nur bei echter
    Dominanz – mit den Absätzen, in denen das Neuformulieren am meisten bringt."""
    out = ["\n### Warum das Modellziel noch fehlt" + (" (vorläufig)" if d.get("vorlaeufig") else "") + "\n"]
    kopf = f"Modell {round(100 * d['p_mensch'])} % menschlich, Ziel {round(100 * d['ziel_p_mensch'])} %."
    if d.get("stagniert") and d.get("p_vorvorher") is not None:
        kopf += f" Seit zwei Messungen kaum Bewegung ({round(100 * d['p_vorvorher'])} % → {round(100 * d['p_mensch'])} %)."
    elif d.get("umsetzbar", 0) < 3:
        n = d.get("umsetzbar", 0)
        kopf += f" Neue sichere Einzelstellen gibt es nur {n}." if n else (
            " Größere sichere Einzelstellen gibt es keine mehr – oben nur noch kleine, aber sichere." if d.get("klein")
            else " Neue sichere Einzelstellen gibt es keine mehr.")
    if d.get("vorlaeufig"):
        o = d.get("offen_logit") or 0.0
        kopf += (f" Vorläufig: Die Aufträge oben sind noch offen (vorab gerechnet zusammen ≈ {fmt(o)}"
                 + (" – an der Einschätzung ändern sie voraussichtlich wenig)." if o < 0.25 * (d.get("luecke_logit") or 1.0)
                    else "); nach ihrer Umsetzung kann die Einschätzung besser ausfallen."))
    out.append(kopf + " Was den Text im Modell Richtung KI zieht (Beitrag, je negativer, desto stärker; dahinter, was davon erreichbar ist):\n")
    grade = {1.0: "mit Einzelkorrekturen erreichbar", 0.5: "teilweise erreichbar", 0.0: "mit Einzelkorrekturen kaum erreichbar"}
    fw_abs = _absatz_liste(d.get("fw_absaetze") or [])
    for z in d["beitraege"]:
        pot_w = z.get("potenzial_logit", 0)
        pot = fmt(round(pot_w, 2))
        err, rest = z.get("erreichbar_logit", 0), z.get("rest_logit", 0)
        wie = f" ({z['wie']})" if z.get("wie") and z.get("wie") not in ("kein_raum", "klein_sicher") and (z["erreichbar"] > 0 or err > 0) else ""
        stufe = grade.get(z["erreichbar"], "teilweise erreichbar")
        if z.get("wie") == "median":
            stufe, wie = "bleibt – schon eine weitere Abkürzung läge über dem menschlichen Median", ""
        elif z.get("wie") == "keine_langform":
            stufe, wie = "bleibt – im Text steht keine ausgeschriebene Abkürzung, die sich kürzen ließe (nichts einstreuen)", ""
        elif z.get("wie") == "keine_konstruktion":
            stufe, wie = (f"mit Einzelkorrekturen kaum erreichbar – {FW_KEINE_KONSTRUKTION}"
                          + (f"; am ehesten {fw_abs}" if fw_abs else "")), ""
        elif z.get("wie") == "keine_stelle":
            stufe, wie = "bleibt – " + (z.get("hinweis") or "keine weitere Wendung ohne Auftrag"), ""
        elif z.get("wie") == "klein_sicher":
            stufe, wie = f"≈ {pot} mit den Aufträgen „klein, aber sicher“ oben", ""
        elif z.get("wie") == "kein_raum":
            stufe = ((f"mit den genannten Stellen ≈ {fmt(round(err, 2))}; weitere ≈ {fmt(round(rest, 2))} gesperrt" if err > 0
                      else f"≈ {pot} gesperrt")
                     + ": diese Runde kein Spielraum für weitere sichere Bündelungen ("
                     + (z.get("hinweis") or "kein weiteres passendes Satzpaar bzw. die Grenzen gegen Überkorrektur")
                     + ") – eine Grenze des Coaches, zählt nicht mit")
            wie = ""
        elif z.get("wie") == "nur_neuformulieren":
            stufe, wie = (f"im Text keine umbaubare Konstruktion mehr – ≈ {pot} nur durch Neuformulieren ganzer Absätze erreichbar"
                          + (f" (am ehesten {fw_abs})" if fw_abs else "") + ", keine Einzelkorrektur; zählt nicht mit"), ""
        elif z.get("stellen"):
            stufe = (f"≈ {pot} ohne Auftrag – im grünen Bereich, Stellen: {', '.join(z['stellen'][:5])}")
            wie = ""
        elif z.get("ohne_stelle"):
            stufe = f"≈ {pot} ohne Auftrag – diese Runde ohne sichere Stelle"
            wie = ""
        elif rest > 0.005 and err > 0:
            stufe = f"mit den genannten Stellen ≈ {fmt(round(err, 2))}, weitere ≈ {fmt(round(rest, 2))} ohne Auftrag"
        elif pot_w > 0.005:
            stufe = f"{stufe}: ≈ {pot} mit den genannten Stellen"
        # „Beitrag“ ausdrücklich nennen: der Name trägt oft die Einheit der Kennzahl (LLR, pro 1000), der Wert ist aber Logit
        out.append(f"- {z['name']}: Beitrag {fmt(round(z['beitrag'], 2))} – {stufe}{wie}")
    grenze = d.get("grenze") or ("keine" if d["realistisch"] else "einzelkorrekturen")
    e_, s_ = d["erreichbar_logit"], d.get("stellenlos_logit", 0)
    g_, n_ = d.get("gesperrt_logit") or 0.0, d.get("neuformulieren_logit") or 0.0
    gesamt = fmt(round(e_ + s_, 2))
    teile = [f"mit Aufträgen ≈ {fmt(e_)}", f"ohne Auftrag ≈ {fmt(s_)}"]
    if g_ > 0:
        teile.append(f"gesperrt ≈ {fmt(g_)}")
    if n_ > 0:
        teile.append(f"nur durch Neuformulieren ≈ {fmt(n_)}")
    out.append(f"\nSumme der Zeilen: {' + '.join(teile)} = ≈ {fmt(round(e_ + s_ + g_ + n_, 2))}; Lücke zum Ziel ≈ {fmt(d['luecke_logit'])}. "
               "Gesperrt und nur durch Neuformulieren zählen für die Einschätzung nicht mit.")
    selbst = _selbsthilfe_zeilen(d)
    dazu = ""
    if g_ > 0.005:
        dazu += f"; dazu ≈ {fmt(g_)} gesperrt (kein Spielraum für sichere Bündelungen)"
    if n_ > 0.005:
        dazu += f"; dazu ≈ {fmt(n_)} nur durch Neuformulieren ganzer Absätze, keine Einzelkorrektur"
    if grenze == "keine":
        out.append(f"\nDie erreichbaren Beiträge (≈ {fmt(e_)}) reichen rechnerisch für die Lücke zum Ziel "
                   f"(≈ {fmt(d['luecke_logit'])}): die genannten Stellen zuerst umsetzen.")
    elif grenze == "coach":
        out.append(f"\n**Grenze des Coaches, nicht der Einzelkorrekturen:** Mit den Aufträgen dieser Runde reicht es nicht (≈ "
                   f"{fmt(e_)} von ≈ {fmt(d['luecke_logit'])}). Rechnerisch würden die Merkmale reichen, zu denen es "
                   f"diese Runde keinen Auftrag gibt (zusammen ≈ {gesamt}{dazu}) – keine sichere Stelle oder Stelle im grünen Bereich."
                   + (" So geht es selbst:" if selbst else " Nach der nächsten Messung sucht der Coach erneut."))
    elif grenze == "knapp":
        out.append(f"\n**Knapp – Schätzung unsicher:** Mit allen grundsätzlich erreichbaren Beiträgen (≈ {gesamt}, davon mit Aufträgen ≈ "
                   f"{fmt(e_)}{dazu}) fehlt rechnerisch nur wenig zur Lücke (≈ {fmt(d['luecke_logit'])}). Die Erreichbarkeit "
                   "ist grob geschätzt – ob Einzelkorrekturen reichen, ist offen." + (" Ohne Auftrag, aber selbst möglich:" if selbst else ""))
    else:
        out.append(f"\n**Ehrlich gesagt – Grenze der Einzelkorrekturen:** Auch mit allen grundsätzlich erreichbaren Beiträgen (≈ {gesamt}, "
                   f"davon mit Aufträgen ≈ {fmt(e_)}{dazu}) bleibt die Lücke zum Ziel (≈ {fmt(d['luecke_logit'])}) deutlich "
                   "größer; mit Einzelkorrekturen ist sie voraussichtlich nicht zu schließen." + (" Ohne Auftrag, aber selbst möglich:" if selbst else ""))
    for z in selbst:
        out.append(f"  - {z['name']} (erreichbar ≈ {fmt(round(z.get('rest_logit', z['potenzial_logit']), 2))}): {z['selbsthilfe']}")
    if d.get("fw_text"):
        out.append(f"\n{d['fw_text']}" + (f" Am meisten bringt das in {fw_abs} – dort zieht das Funktionswort-Profil am stärksten "
                                          "Richtung KI." if fw_abs else ""))
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
    zp = c.get("ziel_p_mensch") or 0.86
    if b.get("verfuegbar"):
        score_txt = (f"**Score {c['score_ziel_wert']}/100** (KI-Seite; beidseitig {b['score']})"
                     if c.get("score_einseitig") and c.get("score_ziel_wert") != b["score"] else f"**Score {b['score']}/100**")
        kopf += f" · {score_txt} · Modell: {_p_anzeige(b['p_mensch'] or 0, zp)} menschlich · {c['rot']} Kennzahlen rot"
    out.append(kopf)
    block_hinweis = getattr(analyse, "BLOCK_HINWEIS", None)
    for w in info["warnungen"]:
        out.append(f"\n> {'ℹ️' if block_hinweis and w.startswith(block_hinweis) else '⚠️'} {w}")
    if c.get("verklebt") and not any("verklebt" in w for w in info["warnungen"]):
        out.append(f"\n> ⚠️ {len(c['verklebt'])} verklebte Stelle{'n' if len(c['verklebt']) > 1 else ''} ohne Leerzeichen – solange sie "
                   "dastehen, sind die übrigen Messwerte unsicher (Satzgrenzen, Satz- und Wortlängen).")
    elif c.get("verklebt"):
        out.append("\n> ⚠️ Solange die verklebten Wörter dastehen, sind die übrigen Messwerte unsicher – zuerst trennen, dann neu messen.")
    if (c.get("zitat_anteil") or 0) >= ZITAT_ANTEIL_HOCH:
        out.append(f"\n> ℹ️ {round(100 * c['zitat_anteil'])} % wörtliche Zitate – Messung nur bedingt aussagekräftig.")
    f = c.get("fortschritt")
    if f:
        jetzt = c.get("score_ziel_wert") if c.get("score_einseitig") else b["score"]
        d = (jetzt or 0) - (f["score_vorher"] or 0)
        out.append(f"\n**Fortschritt (Messung {f['messung_nr']}):** Score {f['score_vorher']} → {jetzt} ({'+' if d >= 0 else ''}{d})"
                   + (f" · besser: {', '.join(analyse.NAMEN.get(k, k) for k in f['besser'])}" if f["besser"] else "")
                   + (f" · schlechter: {', '.join(analyse.NAMEN.get(k, k) for k in f['schlechter'])}" if f["schlechter"] else "")
                   + (f" · rot und weiter verschlechtert: {', '.join(analyse.NAMEN.get(k, k) for k in f['weiter_rot'])}"
                      if f.get("weiter_rot") else "")
                   + (" · Text seit der letzten Messung unverändert – die genannten Stellen sind noch offen." if f.get("unveraendert") else ""))
        # „vorab geprüft“ nur, wenn unten Satzlängen-Aufträge stehen und der Coach genau diese Kennzahl simuliert
        typen_unten = {t for h in c["hinweise"] for t in (h.get("typen") or [h["typ"]])}
        for u in f.get("ueberkorrektur") or []:
            aus = ", ".join(TYP_NAME.get(t, t) for t in u["aussetzen"])
            seit = f" (Messung {u['messung_vorher']})" if u.get("messung_vorher") else ""
            if u["id"] == "teilsatz_verhaeltnis_21":
                geprueft = bool(typen_unten & {"buendeln", "kommas", "fw_ankuendigung"})  # gegen das Verhältnis 2:1 simuliert
            else:
                geprueft = bool(typen_unten & {"buendeln", "teilen", "mitte", "zickzack", "kommas"}) \
                    and (u["id"] in LAENGEN_KENNZAHLEN or u["id"] == "rhythmus_r1_log")
            if u.get("geschuetzt") and not aus:
                folge = (" Ursache: die Bündelung der Vorrunde. Bündeln bleibt erlaubt, weil lange Sätze deutlich fehlen"
                         + ("; weitere Bündelungen nur noch, wenn sie das Verhältnis vorab gerechnet nicht weiter verschlechtern."
                            if u["id"] == "teilsatz_verhaeltnis_21" else "."))
            elif aus:
                folge = f" Diese Runde ausgesetzt: {aus}."
            elif u["id"] == "rhythmus_r1_log":
                folge = " Die Satzlängen-Aufträge unten sind vorab so geprüft, dass sie ihn nicht weiter verschlechtern." if geprueft else ""
            elif u["art"] == "Nebenwirkung":
                folge = (" Die Änderung lässt sich keinem befolgten Auftrag der Vorrunde zuordnen – nichts ausgesetzt."
                         + (" Die Satzlängen-Aufträge unten sind vorab so geprüft, dass sie diese Kennzahl nicht weiter verschlechtern."
                            if geprueft else ""))
            else:
                folge = ""
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
    ziel_s = c.get("ziel_score_anzeige") or math.ceil((c.get("ziel_score") or 0) - 1e-9)
    p_jetzt = b.get("p_mensch") or 0
    modell_txt = f"Modell {_p_anzeige(p_jetzt, zp)} (Ziel ≥ {round(100 * zp)} %)"
    score_jetzt = c.get("score_ziel_wert") if c.get("score_ziel_wert") is not None else b.get("score")
    score_art = "Score (KI-Seite)" if c.get("score_einseitig") else "Score"
    if c["ziel_erreicht"]:
        rot_teil = f", höchstens {c['ziel_rot_max']} Kennzahlen rot" if c.get("ziel_rot_max") is not None else ""
        out.append(f"\n✅ **Ziel erreicht:** {modell_txt}, {score_art} {score_jetzt} (Ziel ≥ {ziel_s}){rot_teil} – so "
                   "unauffällig wie die meisten echten Hochschularbeiten. **Kein weiterer Handlungsbedarf.**"
                   + (" Ausnahme: Die Satzlängen sind über den menschlichen Bereich hinaus gewachsen – die Teilen-Hinweise unten nehmen "
                      "das zurück." if any(h["typ"] == "teilen" for h in c["hinweise"]) else "")
                   + (" Unten nur noch sehr sichere Einzelstellen." if c["hinweise"] else ""))
    elif c.get("messunsicherheit"):
        m = c["messunsicherheit"]
        teile = []
        if m.get("luecke_p"):
            teile.append(modell_txt)
        if m.get("luecke_score"):
            teile.append(f"{score_art} {score_jetzt} (Ziel ≥ {ziel_s})")
        out.append(f"\n_Knapp unter dem Ziel – {' und '.join(teile) or modell_txt}: **im Bereich der Messunsicherheit.** Kein echter "
                   "Handlungsbedarf; " + ("höchstens die eine Stelle unten mit dem größten Effekt._" if c["hinweise"] else
                                         "keine Stelle verspricht eine sichere Verbesserung._"))
    elif c.get("teilziel") and not c["teilziel"].get("mit_modell"):
        namen = ", ".join(HEBEL_TEXT[h][0] for h in c["teilziel"]["hebel"] if h in HEBEL_TEXT)
        fehlt = c["teilziel"]["fehlt"]
        if c["teilziel"].get("gegenseite_deckt"):
            out.append(f"\n_{modell_txt} erreicht; dem {score_art} fehlen noch {fmt(fehlt)} Punkt{'e' if fehlt != 1 else ''} bis {ziel_s} – "
                       f"sie liegen auf der der KI abgewandten Seite (≈ {fmt(c['teilziel']['gegenseite_punkte'])} Punkte durch Werte, die "
                       "„menschlicher als typisch“ sind): kein Handlungsbedarf, keine Aufträge dazu._")
        else:
            out.append(f"\n_{modell_txt} erreicht; dem {score_art} fehlen noch {fmt(fehlt)} Punkt{'e' if fehlt != 1 else ''} bis {ziel_s}. "
                       f"Deshalb nur Hinweise zu: {namen or '–'}._")
    elif c["bewertung"].get("verfuegbar"):
        grenze = c.get("auftragsgrenze")
        zusatz = (f" Unten nur die Stellen mit der größten simulierten Wirkung – sie reichen rechnerisch (zusammen ≈ "
                  f"{fmt(grenze['summe_logit'])} für eine Lücke von ≈ {fmt(grenze['luecke_logit'])}); mehr ist nicht nötig."
                  if grenze and grenze.get("reicht") else "")
        out.append(f"\n_Ziel: Modell ≥ {round(100 * zp)} % menschlich (jetzt {_p_anzeige(p_jetzt, zp)}) und {score_art} ≥ {ziel_s}. "
                   f"Einzelne rote Kennzahlen sind normal – auch echte Arbeiten haben im Mittel mehrere.{zusatz}_")
    mt = c.get("menschlicher_als_typisch") or []
    if mt:
        def _wt(z):
            if z["id"].startswith("anteil_"):
                return f"{z['name']} {_pz(z['wert'])} (Band {_pz(z['mensch_p10'])}–{_pz(z['mensch_p90'])})"
            grenze = z["mensch_p90"] if z["wert"] > z["mensch_p90"] else z["mensch_p10"]
            w_, g_ = fmt_paar(z["wert"], grenze)
            lo, hi = (fmt(z["mensch_p10"]), g_) if z["wert"] > z["mensch_p90"] else (g_, fmt(z["mensch_p90"]))
            return f"{z['name']} {w_} (Band {lo}–{hi})"
        rest = f" und {len(mt) - 6} weitere" if len(mt) > 6 else ""
        out.append("\n> ℹ️ **Menschlicher als typisch (kein Auftrag):** " + "; ".join(_wt(z) for z in mt[:6]) + rest
                   + ". Auf einem eigenen Text ist das Eigenart – nichts ändern.")
    sl = c.get("satzlaengen") or {}
    mt_ids = {z["id"] for z in c.get("menschlicher_als_typisch") or []}
    if sl.get("modus") == "teilen" and (sl.get("ueber_p90") or sl.get("fehlende_mitte")) \
            and not any(h["typ"] == "teilen" for h in c["hinweise"]) and not c["ziel_erreicht"] \
            and not mt_ids & {"anteil_lange_saetze", "satzlaenge_mittel", "anteil_mittlere_saetze"}:
        out.append(f"\n**Satzlängen:** {'; '.join(sl['gruende'])}. Keine weiteren Sätze verlängern oder bündeln.")
    elif sl.get("modus") == "mitte" and any(h["typ"] == "mitte" for h in c["hinweise"]):
        out.append(f"\n**Satzlängen:** {sl['mittlere']} von {sl['n']} Sätzen sind mittellang ({MITTEL_VON}–{MITTEL_BIS} Wörter, "
                   f"{_pz(sl.get('anteil_mittlere') or 0)}; Menschen meist ≤ {_pz(sl.get('mittlere_p75') or 0)}), lange Sätze gibt es genug. Nur die unten "
                   f"genannten Sätze mit {MITTE_SATZ_VON}–{MITTE_SATZ_BIS} Wörtern teilen – nicht mehr, nichts bündeln.")
    elif sl.get("modus") and any(h["typ"] in ("buendeln", "teilen", "mitte") for h in c["hinweise"]):
        abw = ", ".join(f"{k.replace('-', '–')} W.: {_pz(t)} statt {_pz(mz)}" for k, t, mz in sl.get("abweichungen", []))
        if sl["modus"] == "teilen":
            out.append(f"\n**Satzlängen:** {'; '.join(sl['gruende'])}. Keine weiteren Bündelungen; stattdessen einzelne lange Sätze teilen"
                       + (f" ({abw})." if abw else "."))
        else:
            mitte = (f"; außerdem nur die genannten Sätze mit {MITTE_SATZ_VON}–{MITTE_SATZ_BIS} Wörtern teilen"
                     if any(h["typ"] == "mitte" for h in c["hinweise"]) else "")
            fehlen = "fehlt 1 langer Satz" if sl["kontingent"] == 1 else f"fehlen {sl['kontingent']} lange Sätze"
            raum = sl.get("selbst_buendeln") or 0
            n_b = sum(1 for h in c["hinweise"] if h["typ"] == "buendeln")
            if raum and n_b < sl["kontingent"]:
                # weniger sichere Paare als Kontingent und noch Spielraum unter den harten Grenzen: ehrlich sagen, was selbst geht
                paare = {0: "kein sicheres Paar", 1: "1 sicheres Paar"}.get(n_b, f"{n_b} sichere Paare")
                regel = (f"– unten {paare} (höchstens ~{BUENDEL_MAX_ZIEL} Wörter je Satz); weitere Stellen, an denen Quelle und "
                         "Aussagestatus sicher erhalten bleiben, fand der Coach nicht. Optional, kein Auftrag: zwei weitere Sätze derselben "
                         f"Quelle zur selben Sache verbinden, höchstens {'1 Paar' if raum == 1 else f'{raum} Paare'}"
                         + (NUR_NEBENSATZ_PAARE if sl.get("teilsatz_hoch") else ""))
            else:
                regel = f"– nicht mehr bündeln als unten genannt (höchstens ~{BUENDEL_MAX_ZIEL} Wörter je Satz)"
            out.append(f"\n**Satzlängen:** {sl['lange']} von {sl['n']} Sätzen haben ≥ {LANG_AB} Wörter; bis zum menschlichen Median (~15 %) {fehlen} "
                       f"{regel}{mitte}" + (f" ({abw})." if abw else "."))
    if c["hebel"] and not c["ziel_erreicht"] and not c.get("messunsicherheit") \
            and not (c.get("teilziel") or {}).get("gegenseite_deckt"):  # Score-Lücke nur auf der Gegenseite: keine Hebel
        normal = [h for h in c["hebel"] if not h.get("stellenlos")][:4]
        orientierung = [h for h in c["hebel"][:6] if h.get("stellenlos")][:3]
        # rote bewertete Kennzahlen ohne Auftrag immer nennen (v4: DP Konnektoren über P90, weder Auftrag noch Erwähnung)
        orientierung += [h for h in c["hebel"] if h.get("stellenlos") and h not in orientierung
                         and any(k.get("status") == "rot" and k.get("bewertet") for k in h["kennzahlen"])]
        if (c.get("auftragsgrenze") or {}).get("reicht") or c.get("teilziel"):
            orientierung = []  # die genannten Stellen reichen: keine Einladung zu weiterer Arbeit
        if normal:
            out.append("\n### Die wichtigsten Hebel\n")
        for i, h in enumerate(normal, 1):
            teile = []
            for k in h["kennzahlen"][:3]:
                if k.get("id") == "semikolon_pro_1000":
                    teile.append(f"{k['name']}: {fmt(k['wert'])} (Ziel: höchstens 1–2 je 800 Wörter)")
                elif k.get("nur_modell"):
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
        if orientierung:
            out.append("\n**Keine sichere Stelle – zur Orientierung** (diese Runde kein Auftrag dazu; so geht es selbst):")
            for h in orientierung:
                out.append(f"- {h['name']}: {h.get('selbsthilfe') or h['warum']}")
    if c["hinweise"]:
        out.append("\n### Konkrete Stellen\n")
        if any(h.get("klein_sicher") for h in c["hinweise"]) \
                and all(h.get("klein_sicher") or h["typ"] == "bereinigung" for h in c["hinweise"]):
            out.append("_Keine größere sichere Stelle mehr – nur noch kleine, aber sichere Einzelstellen. Allein schließen sie die Lücke "
                       + ("nicht (siehe Diagnose unten)" if c.get("diagnose") else "voraussichtlich nicht") + ", verschlechtern aber nichts._\n")
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
    elif c.get("teilziel") and not c["teilziel"].get("mit_modell") and not c["ziel_erreicht"]:
        tz = c["teilziel"]
        if tz.get("gegenseite_deckt"):
            pass  # die Kopfzeile sagt es schon („kein Handlungsbedarf, keine Aufträge dazu“)
        elif (tz.get("gegenseite_punkte") or 0) >= tz["fehlt"]:
            out.append(f"\n_Keine sichere Einzelstelle für die Score-Lücke. Die fehlenden Punkte liegen überwiegend auf der der KI abgewandten "
                       f"Seite (≈ {fmt(tz['gegenseite_punkte'])} Punkte durch Werte, die „menschlicher als typisch“ sind) – kein "
                       "Handlungsbedarf._")
        else:
            out.append("\n_Keine sichere Einzelstelle für die Score-Lücke gefunden – kein weiterer Auftrag; beim eigenen Formulieren die "
                       "genannten Hebel im Blick behalten._")
    elif not c["ziel_erreicht"] and c["bewertung"].get("verfuegbar") and not c.get("diagnose") and not c.get("diagnose_aufgeschoben") \
            and not c.get("messunsicherheit"):
        out.append("\n_Keine sicheren Einzelstellen gefunden – die Hebel oben beim eigenen Formulieren im Blick behalten._")
    if c.get("vorgaben") or c.get("gender_info"):
        out.append("\n### Vorgaben (ändern den Score nicht)\n")
        for h in sorted(c.get("vorgaben") or [], key=lambda h: (h.get("satz") or 0, h["typ"])):
            out.append(f"- {h['text']}")
        for g in c.get("gender_info") or []:
            out.append(f"- _{g}_")
    if c.get("stehen_lassen"):
        # trifft ein anderer Auftrag denselben Satz, ausdrücklich sagen, dass er trotzdem gilt (sonst liest sich das als Widerspruch)
        auch = sorted({x["satz"] for x in c["stehen_lassen"]} & {h.get("satz") for h in c["hinweise"]})
        out.append("\n_Bewusst stehen lassen: " + ", ".join(f"S{x['satz']}" + (f" ({x['grund']})" if x.get("grund") else "")
                                                         for x in c["stehen_lassen"])
                   + " – der Kontrast „nicht …, sondern …“ ist dort begründet bzw. die Aussage (kein Auftrag dazu"
                   + (f"; der andere Auftrag zu {', '.join(f'S{n}' for n in auch)} oben gilt trotzdem, der Kontrast bleibt" if auch else "")
                   + ")._")
    if c.get("diagnose"):
        out.extend(diagnose_text(c["diagnose"]))
    elif c.get("diagnose_wie"):
        d = c["diagnose_wie"]
        art = GRENZE_NAME.get(d.get("grenze"), "")
        out.append(f"\n_Diagnose wie in Messung {d['messung']}: {art} (erreichbar mit Aufträgen ≈ {fmt(d.get('erreichbar_logit'))}, "
                   f"Lücke ≈ {fmt(d.get('luecke_logit'))})._")
    elif c.get("diagnose_aufgeschoben"):
        a = c["diagnose_aufgeschoben"]
        deckung = (f" Die offenen Aufträge (vorab gerechnet ≈ {fmt(a['sim_offen'])}) und die Merkmale ohne Auftrag (≈ {fmt(a['stellenlos'])}) "
                   f"decken die Lücke (≈ {fmt(a['luecke'])}) rechnerisch weitgehend." if a.get("luecke") is not None else "")
        out.append(f"\n_Noch keine Diagnose: Das Modell ist in dieser Runde deutlich gestiegen ({round(100 * a['p_vorher'])} % → "
                   f"{round(100 * a['p_mensch'])} %).{deckung} Ob Einzelkorrekturen bis zum Ziel reichen, zeigt die nächste Messung._")
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
