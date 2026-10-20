#!/usr/bin/env python3
"""Stil-Coach: macht aus der Textanalyse konkrete, satzgenaue Arbeitsaufträge.

Der Coach schreibt nichts um. Er sagt, WAS an WELCHER Stelle zu ändern ist
(„Satz 7 und 8 sind gleich lang und eng verbunden – zu einem langen Satz
verbinden“), damit der Nutzer selbst formuliert. Danach misst man erneut; mit
--verlauf zeigt der Coach den Fortschritt seit der letzten Messung.

    python3 coach.py TEXT.md                         # Bericht
    python3 coach.py TEXT.md --verlauf TEXT.coach.json   # mit Fortschritt (Datei wird fortgeschrieben)
    python3 coach.py TEXT.md --format json

Nur Python-Standardbibliothek. Nutzt analyse.py aus dem Skill text-analyse.
"""
from __future__ import annotations

import argparse
import json
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
                     "rhythmus_r1_log", "satzlaenge_mittel"], "satzlaenge"),
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
    "satzlaenge": ("Lange, dichte Sätze zulassen", "Menschen streuen stärker – vor allem durch lange, nominal verdichtete Sätze (30–50 Wörter) beim Argumentieren. KI-Texte bleiben im mittleren Band und wechseln oft streng kurz/lang ab."),
    "satzklammer": ("Satzklammer füllen, nominal verdichten", "Bei Menschen stehen zwischen Hilfsverb und Partizip/Infinitiv mehr Wörter (Ø ~7 statt ~5), und es gibt mehr Nominal- und Genitivgruppen. Claude lagert Angaben in eigene Sätze oder Nebensätze aus."),
    "konnektoren": ("Weniger Konnektoren", "Claude nutzt deutlich mehr Satzverknüpfer (zugleich, zudem, darüber hinaus, hingegen, jedoch …) als Menschen. Streichen, nicht verschieben."),
    "funktionswoerter": ("Funktionswort-Profil (Tendenz)", "Das Profil kleiner Wörter ist das stärkste Einzelsignal: Menschen schreiben häufiger mit „es“, „wie“, „auch“, „durch“, Claude häufiger mit „als“, „sich“, „dass“. Nur indirekt steuerbar."),
    "absaetze": ("Absätze ungleich lang machen", "Menschliche Absätze schwanken stark (mal 2, mal 7 Sätze). KI-Absätze sind fast gleich lang."),
    "begriffe": ("Begriffe wieder aufgreifen statt variieren", "Menschen wiederholen den Schlüsselbegriff des Vorsatzes. KI wechselt zu Synonymen oder knüpft nur mit „Dies“ an – das macht den Wortschatz künstlich vielfältig."),
    "nebensaetze": ("Weniger Nebensatz-Ketten", "KI-Sätze reihen viele kurze Teilsätze mit Kommas. Menschliche Teilsätze sind länger, und es gibt mehr Sätze ganz ohne Komma."),
    "semikolon": ("Semikolons ersetzen", "In menschlichen Hochschultexten kommen Semikolons kaum vor (Median 0). Claude setzt sie regelmäßig."),
    "doppelpunkt": ("Doppelpunkte reduzieren", "Doppelpunkte mitten im Satz sind bei Claude häufiger als bei Menschen."),
    "floskeln": ("KI-Floskeln und -Konstruktionen ersetzen", "Diese Wendungen kommen in Claude-Texten mehrfach häufiger vor als in echten Hochschularbeiten."),
    "wortwahl": ("Wortwahl einfacher und natürlicher", "Menschen nutzen mehr kurze Allerweltswörter („es gibt“, „so“, „auch“, „aber“, „man“) und gängige Abkürzungen (z. B., bzw.)."),
    "abkuerzungen": ("Übliche Abkürzungen stehen lassen", "Menschliche Hochschultexte nutzen gängige Abkürzungen (z. B., d. h., bzw., vgl., u. a.). Claude schreibt sie fast immer aus."),
    "stimme": ("Eigene Stimme zeigen", "Menschliche Arbeiten zitieren öfter wörtlich, verwenden Klammern und manchmal „ich/wir“ oder „man“."),
}

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
ANKNUEPF_RE = re.compile(r"^(dies|diese[rsmn]?|sie|er|hierbei|hierdurch|dabei|dadurch)\b", re.IGNORECASE)  # rein anaphorische Anschlüsse
# In den Korpora bei Menschen deutlich häufiger als bei Claude (Kalibrierung, log-odds): einfache Stil- und Funktionswörter
MENSCHLICHE_STILWOERTER = ["es gibt", "so", "auch", "aber", "man", "sehr", "doch", "schon", "denn", "außerdem", "viele", "aufgrund"]


def anfang(text: str, n: int = 7) -> str:
    w = text.split()
    return " ".join(w[:n]) + (" …" if len(w) > n else "")


def zitat(s: dict) -> str:
    return f"Satz {s['nr']} („{anfang(s['text'])}“)"


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


def lade_json(name: str) -> dict:
    pfad = os.path.join(DATA, name)
    if not os.path.exists(pfad):
        return {}
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


def klammer_spannen(satz_text: str) -> list[int]:
    """Satzklammer-Spannen eines Satzes (Wörter zwischen finitem Hilfsverb und Partizip/Infinitiv), wie in analyse.py (HW08)."""
    spannen = []
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
            spannen.append(j - aux - 1)
    return spannen


def zickzack(laengen: list[int]) -> list[tuple[int, int]]:
    """Bereiche (von, bis; 0-basiert) mit mindestens 4 Längenwechseln in Folge mit wechselndem Vorzeichen und |Differenz| ≥ 0,3·Ø."""
    if len(laengen) < 5:
        return []
    schwelle = 0.3 * (sum(laengen) / len(laengen))
    d = [laengen[i + 1] - laengen[i] for i in range(len(laengen) - 1)]
    bereiche, start = [], None
    for i in range(len(d)):
        ok = abs(d[i]) >= schwelle and (i == 0 or start is None or d[i] * d[i - 1] < 0)
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start >= 4:
                bereiche.append((start, i))
            start = i if abs(d[i]) >= schwelle else None
    if start is not None and len(d) - start >= 4:
        bereiche.append((start, len(d)))
    return bereiche


def mechanisch_verlaengert(vorher: dict, jetzt: dict) -> bool:
    """Plausibilitätsregel: Ø-Satzlänge +10 %, aber weder Wörter pro Teilsatz noch Satzklammer-Spanne gestiegen."""
    if not vorher.get("satzlaenge_mittel") or not jetzt.get("satzlaenge_mittel"):
        return False
    if jetzt["satzlaenge_mittel"] <= 1.1 * vorher["satzlaenge_mittel"]:
        return False
    return not any(vorher.get(k) is not None and jetzt.get(k) is not None and jetzt[k] > vorher[k]
                   for k in ("woerter_pro_teilsatz", "satzklammer_mittel"))


def schluesselbegriff(satz_text: str) -> str | None:
    """Wahrscheinlichster Hauptbegriff eines Satzes: längstes großgeschriebenes Nomen, nicht am Satzanfang."""
    toks = analyse.tokens(satz_text)
    kandidaten = [t for i, t in enumerate(toks) if i > 0 and t[:1].isupper() and analyse.ist_wort(t)
                  and t.lower() not in analyse.FUNKTIONSWOERTER and len(t) > 4]
    return max(kandidaten, key=len) if kandidaten else None


def coache(text: str, verlauf: dict | None = None, max_hinweise: int = 15) -> dict:
    muster = analyse.lade_muster()
    baselines = analyse.lade_baselines()
    ts = (baselines or {}).get("textsorten", {}).get("hochschule", {})
    if hasattr(analyse, "analysiere_und_bewerte"):
        erg, bew = analyse.analysiere_und_bewerte(text, muster, baselines)
    else:
        fw_profil = ts.get("fw_profil")
        erg = analyse.analysiere_text(text, muster, fw_profil=fw_profil) if fw_profil else analyse.analysiere_text(text, muster)
        bew = analyse.bewerte(erg, baselines)
    saetze = erg["saetze"]
    m = erg["metriken"]
    absaetze: dict[int, list[dict]] = {}
    for s in saetze:
        absaetze.setdefault(s["absatz"], []).append(s)

    # --- Hebel priorisieren ------------------------------------------------
    hebel: dict[str, dict] = {}
    if bew.get("verfuegbar"):
        # Modellbeitrag (koef · Abstand zum menschlichen Median, negativ = zieht Richtung KI): Was das Modell
        # tatsächlich als KI-typisch wertet, rückt nach vorn – auch Modellmerkmale ohne Ampel (Funktionswörter).
        for z in bew["kennzahlen"]:
            b = z.get("beitrag")
            h = HEBEL_VON.get(z["id"])
            if h and b is not None and b < -0.25:
                eintrag = hebel.setdefault(h, {"prioritaet": 0.0, "kennzahlen": []})
                eintrag["prioritaet"] += 0.5 * -b
                if z["status"] != "gruen" or z.get("nur_modell"):
                    eintrag["kennzahlen"].append(z)
        for z in bew["kennzahlen"]:
            if not z["bewertet"] or z["status"] == "gruen":
                continue
            # Gelb, aber innerhalb der Messunsicherheit an der Grenze: kein Arbeitsauftrag
            if z["status"] == "gelb" and z.get("unsicher"):
                continue
            # Abweichungen weg von der KI-Seite ("menschlicher als der Median") sind kein Arbeitsauftrag des Coachs
            if z["ki_p50"] is not None:
                ki_seite = z["ki_p50"] - z["mensch_p50"]
                if ki_seite * (z["wert"] - z["mensch_p50"]) <= 0:
                    continue
            h = HEBEL_VON.get(z["id"])
            if not h:
                continue
            eintrag = hebel.setdefault(h, {"prioritaet": 0.0, "kennzahlen": []})
            eintrag["prioritaet"] += (z["gewicht"] or 0.1) * (0.5 + abstand(z))
            if z not in eintrag["kennzahlen"]:
                eintrag["kennzahlen"].append(z)
    reihenfolge = sorted(hebel, key=lambda h: -hebel[h]["prioritaet"])

    hinweise: list[dict] = []  # {hebel, absatz, satz, text, gewicht}

    def hinweis(h: str, absatz: int | None, satz: int | None, text_: str, gewicht: float = 1.0):
        hinweise.append({"hebel": h, "absatz": absatz, "satz": satz, "text": text_,
                         "gewicht": gewicht * (hebel.get(h, {}).get("prioritaet", 0.3) + 0.1)})

    def kennzahl(id_):
        for z in bew.get("kennzahlen", []):
            if z["id"] == id_:
                return z
        return None

    # --- Satzlängen ----------------------------------------------------------
    if "satzlaenge" in hebel:
        braucht_lange = any(z["id"] in ("anteil_lange_saetze", "anteil_sehr_lange_saetze", "satzlaenge_sd", "satzlaenge_cv",
                                        "satzlaenge_dispersion", "anteil_mittlere_saetze", "satzlaenge_schiefe") and z["richtung"] in ("erhoehen", "senken")
                            for z in hebel["satzlaenge"]["kennzahlen"])
        braucht_kurze = any(z["id"] in ("anteil_kurze_saetze", "anteil_sehr_kurze_saetze") and z["richtung"] == "erhoehen"
                            for z in hebel["satzlaenge"]["kennzahlen"])
        for nr_abs, liste in absaetze.items():
            laengen = [s["woerter"] for s in liste]
            mittlere = [s for s in liste if 12 <= s["woerter"] <= 26]
            if len(liste) >= 3 and len(mittlere) >= len(liste) - 1 and max(laengen) < 30:
                folge = " · ".join(str(x) for x in laengen)
                hinweis("satzlaenge", nr_abs, None, f"Absatz {nr_abs} hat nur mittellange Sätze ({folge} Wörter). Ein deutlich längerer oder kürzerer Satz fehlt.", 1.2)
            # Verbinden: zwei benachbarte mittellange Sätze, zusammen 28–50 Wörter
            if braucht_lange:
                for a, b in zip(liste, liste[1:]):
                    if 10 <= a["woerter"] <= 24 and 10 <= b["woerter"] <= 24 and 28 <= a["woerter"] + b["woerter"] <= 50 \
                            and ";" not in a["text"] and not a["text"].rstrip().endswith(("?", "!")):
                        hinweis("satzlaenge", nr_abs, a["nr"], f"{zitat(a)} und Satz {b['nr']} ({a['woerter']} + {b['woerter']} Wörter) zu einem langen Satz bündeln – nominal verdichten (Präpositional-/Genitivgruppen), keine angehängten „und“-Teilsätze.", 1.0)
                        break
            # Abtrennen nur, wenn wirklich kurze Sätze fehlen – höchstens einmal im Text
            if braucht_kurze and not any(h["hebel"] == "satzlaenge" and "Zwischenergebnis" in h["text"] for h in hinweise):
                for s in liste:
                    if s["woerter"] >= 22 and s["text"].count(",") >= 2:
                        hinweis("satzlaenge", nr_abs, s["nr"], f"{zitat(s)}: Falls darin ein echtes Zwischenergebnis steckt, dieses als kurzen Satz formulieren.", 0.5)
                        break

    laengen_alle = [s["woerter"] for s in saetze]
    for von, bis in zickzack(laengen_alle):
        a, b = saetze[von], saetze[min(bis, len(saetze) - 1)]
        folge = " · ".join(str(x) for x in laengen_alle[von:bis + 1])
        hinweis("satzlaenge", a["absatz"], a["nr"], f"Satz {a['nr']}–{b['nr']} wechseln streng kurz/lang ab ({folge} Wörter). Längen in Phasen ordnen (Erklärpassage lang, Folgerung kurz) statt Satz für Satz zu wechseln.", 0.9)

    # --- Satzklammer / Verdichtung ---------------------------------------------
    if "satzklammer" in hebel:
        hinweis("satzklammer", None, None, "Angaben zu Zeit, Ort, Art, Grund und Mittel ins Mittelfeld zwischen Hilfsverb und Partizip holen, statt sie in eigene Sätze oder Nebensätze auszulagern („Die Daten wurden im Frühjahr 2019 online unter 240 Beschäftigten erhoben.“).", 1.0)
        n = 0
        for i, s in enumerate(saetze):
            sp = klammer_spannen(s["text"])
            if sp and max(sp) <= 2:
                nachbar = saetze[i + 1] if i + 1 < len(saetze) and saetze[i + 1]["absatz"] == s["absatz"] else None
                zusatz = f" – Angaben aus Satz {nachbar['nr']} hineinholen, falls sie dazugehören" if nachbar and nachbar["woerter"] <= 14 else ""
                hinweis("satzklammer", s["absatz"], s["nr"], f"{zitat(s)}: Satzklammer fast leer{zusatz}.", 0.8)
                n += 1
                if n >= 4:
                    break

    # --- Konnektoren ---------------------------------------------------------
    if "konnektoren" in hebel:
        n = 0
        for s in saetze:
            treffer = KONNEKTOR_RE.findall(s["text"])
            if treffer:
                hinweis("konnektoren", s["absatz"], s["nr"], f"{zitat(s)}: „{treffer[0]}“ streichen, wenn der Bezug klar ist, oder über das wiederholte Nomen anschließen (nicht nur verschieben).", 0.9)
                n += 1
                if n >= 6:
                    break

    # --- Funktionswörter (nur Tendenz) -------------------------------------------
    if "funktionswoerter" in hebel:
        hinweis("funktionswoerter", None, None, "Funktionswort-Profil KI-nah. Als Tendenz beim eigenen Formulieren: öfter „es“-Konstruktionen („es gibt“, „es zeigt sich“), „wie“-Vergleiche, „auch“, „durch“; seltener „sich“-, „als“- und „dass“-Konstruktionen. Keine Wörter einstreuen – das folgt meist aus Verdichten und Konnektoren-Streichen.", 0.8)

    # --- Absätze ---------------------------------------------------------------
    if "absaetze" in hebel and len(absaetze) >= 2:
        anz = {nr: len(l) for nr, l in absaetze.items()}
        folge = " · ".join(str(v) for v in anz.values())
        hinweis("absaetze", None, None, f"Sätze pro Absatz: {folge}. Das ist zu gleichmäßig.", 1.3)
        laengster = max(anz, key=anz.get)
        if anz[laengster] >= 5:
            hinweis("absaetze", laengster, None, f"Absatz {laengster} ({anz[laengster]} Sätze) an einem inhaltlichen Wechsel in zwei Absätze teilen – einer davon gern nur 1–2 Sätze.", 1.0)
        nrs = list(anz)
        paare = [(a, b) for a, b in zip(nrs, nrs[1:]) if anz[a] + anz[b] <= 9]
        if paare:
            a, b = min(paare, key=lambda p: anz[p[0]] + anz[p[1]])
            hinweis("absaetze", a, None, f"Absatz {a} und {b} ({anz[a]} + {anz[b]} Sätze) zusammenlegen, wenn sie dasselbe Thema behandeln.", 0.9)
        if m.get("anteil_einsatz_absaetze", 0) == 0:
            hinweis("absaetze", None, None, "Eine zentrale Aussage als eigenen, sehr kurzen Absatz (1–2 Sätze) setzen – das kommt in menschlichen Arbeiten regelmäßig vor.", 0.6)

    # --- Begriffe -------------------------------------------------------------
    if "begriffe" in hebel:
        gezaehlt = 0
        for nr_abs, liste in absaetze.items():
            for a, b in zip(liste, liste[1:]):
                sa = analyse.inhaltsstaemme(analyse.tokens(a["text"]))
                sb = analyse.inhaltsstaemme(analyse.tokens(b["text"]))
                if sa and sb and not (sa & sb):
                    begriff = schluesselbegriff(a["text"])
                    if ANKNUEPF_RE.match(b["text"]) and begriff:
                        hinweis("begriffe", nr_abs, b["nr"], f"{zitat(b)} knüpft nur über „{b['text'].split()[0]}“ an. Den Begriff „{begriff}“ aus Satz {a['nr']} wieder aufgreifen.", 1.0)
                        gezaehlt += 1
                    elif begriff and gezaehlt < 6:
                        hinweis("begriffe", nr_abs, b["nr"], f"{zitat(b)} teilt kein Inhaltswort mit Satz {a['nr']}. Prüfen, ob ein Synonym für „{begriff}“ o. Ä. steht – dann den gleichen Begriff verwenden.", 0.6)
                        gezaehlt += 1
        kern = erg["info"].get("kernbegriffe") or []
        formen = [k.get("form") or k.get("stamm") for k in kern if isinstance(k, dict)]
        top = ([f for f in formen if f and f[:1].isupper()] or formen)[:6]
        if not top:
            haeufig = Counter(t for s in saetze for t in analyse.tokens(s["text"])
                              if t[:1].isupper() and analyse.ist_wort(t) and t.lower() not in analyse.FUNKTIONSWOERTER and len(t) > 4)
            top = [w for w, n in haeufig.most_common(6) if n >= 2]
        if top:
            hinweis("begriffe", None, None, "Hauptbegriffe des Textes: " + ", ".join(f"„{w}“" for w in top) + ". Diese konsequent so benennen, keine Synonyme einstreuen.", 0.7)

    # --- Nebensätze -----------------------------------------------------------
    if "nebensaetze" in hebel:
        n = 0
        for s in saetze:
            teile = max(1, s.get("teilsaetze", 1))
            if s["text"].count(",") >= 3 and s["woerter"] / teile < 10:
                hinweis("nebensaetze", s["absatz"], s["nr"], f"{zitat(s)}: {s['text'].count(',')} Kommas bei kurzen Teilsätzen. Einen Einschub streichen oder in zwei Sätze teilen.", 0.9)
                n += 1
                if n >= 5:
                    break
        if kennzahl("anteil_einfache_saetze") and kennzahl("anteil_einfache_saetze")["status"] != "gruen":
            hinweis("nebensaetze", None, None, "Mehr Sätze ganz ohne Komma schreiben (einfache Hauptsätze).", 0.6)

    # --- Semikolon / Doppelpunkt ------------------------------------------------
    for s in saetze:
        if ";" in s["text"] and ("semikolon" in hebel or m.get("semikolon_pro_1000", 0) > 0):
            hinweis("semikolon", s["absatz"], s["nr"], f"{zitat(s)}: Semikolon durch Punkt ersetzen oder mit „und“/„weil“ verbinden.", 1.0)
    if "doppelpunkt" in hebel:
        for s in saetze:
            if re.search(r":(?!\d)\s", s["text"]):
                hinweis("doppelpunkt", s["absatz"], s["nr"], f"{zitat(s)}: Doppelpunkt prüfen – oft ist ein eigener Satz oder ein Nebensatz natürlicher.", 0.7)

    # --- Floskeln und KI-Wörter --------------------------------------------------
    muster_info = {mu["id"]: mu for mu in muster}
    for t in erg["muster_treffer"]:
        mu = muster_info.get(t["muster"], {})
        if (mu.get("gewicht") or 0) <= 0:
            continue
        s = saetze[t["satz"] - 1]
        hinweis("floskeln", s["absatz"], s["nr"], f"{zitat(s)}: „{t['fund']}“ – {mu.get('ersatz', 'durch die konkrete Aussage ersetzen')}", 0.6 + 0.3 * mu.get("gewicht", 1))
    wortlisten = lade_json("wortlisten.json")
    if wortlisten.get("ki_typisch"):
        n_tok = max(1, erg["info"]["token"])
        low = " " + " ".join(t.lower() for s in saetze for t in analyse.tokens(s["text"])) + " "
        auffaellig = []
        for e in wortlisten["ki_typisch"][:60]:
            anz = low.count(" " + e["ngramm"] + " ")
            verh = (e["ki_pro_1000"] + 0.02) / (e["mensch_pro_1000"] + 0.02)
            if (anz >= 2 or (anz == 1 and verh >= 4)) and 1000 * anz / n_tok > max(1.5 * e["mensch_pro_1000"], 0.5):
                auffaellig.append(f"„{e['ngramm']}“ {anz}× (Menschen {fmt(e['mensch_pro_1000'])}, Claude {fmt(e['ki_pro_1000'])} pro 1000 Wörter)")
        if auffaellig:
            hinweis("floskeln", None, None, "Typische Claude-Wörter, hier überdurchschnittlich oft: " + "; ".join(auffaellig[:8]) + ". Teils streichen oder anders sagen.", 0.9)

    # --- Wortwahl / Stimme ---------------------------------------------------------
    if "wortwahl" in hebel:
        beispiele = ", ".join(f"„{w}“" for w in MENSCHLICHE_STILWOERTER)
        hinweis("wortwahl", None, None, f"Einfachere Allerweltswörter zulassen. In echten Arbeiten deutlich häufiger als bei Claude: {beispiele}.", 0.7)
    if "abkuerzungen" in hebel:
        n = 0
        for s in saetze:
            treffer = AUSGESCHRIEBEN_RE.search(s["text"])
            if treffer:
                kurz = AUSGESCHRIEBEN[treffer.group(1).lower()]
                hinweis("abkuerzungen", s["absatz"], s["nr"], f"{zitat(s)}: „{treffer.group(1)}“ darf als „{kurz}“ stehen – in Hochschultexten üblich.", 0.5)
                n += 1
                if n >= 3:
                    break
        if not n:
            hinweis("abkuerzungen", None, None, "Wo es sich ergibt, gängige Abkürzungen verwenden statt auszuschreiben (z. B., d. h., bzw., vgl., u. a.). Nicht künstlich einstreuen.", 0.4)

    if "stimme" in hebel:
        hinweis("stimme", None, None, "Wo es passt: eine Quelle wörtlich zitieren, eine Präzisierung in Klammern setzen, und bei eigenen Entscheidungen „ich“ (bzw. „in dieser Arbeit“) verwenden.", 0.4)

    # --- Nutzer-Vorgaben (immer) --------------------------------------------------------
    for s in saetze:
        for f in PARTIZIP_RE.findall(s["text"]) or []:
            wort = f if isinstance(f, str) else next((x for x in f if x), "")
            if wort:
                hinweis("vorgaben", s["absatz"], s["nr"], f"{zitat(s)}: „{wort}“ → generisches Maskulinum (z. B. „Mitarbeiter“, „Teilnehmer“).", 1.5)
                break
        if analyse.GEDANKENSTRICH_RE.search(s["text"]):
            hinweis("vorgaben", s["absatz"], s["nr"], f"{zitat(s)}: Gedankenstrich durch Komma, Klammer oder neuen Satz ersetzen.", 0.8)

    # --- Auswahl und Fortschritt --------------------------------------------------
    # reihum über die Hebel auswählen (Nutzer-Vorgaben zuerst, dann nach Priorität), damit nicht ein Hebel alles füllt
    gesehen, eindeutig = set(), []
    for h in sorted(hinweise, key=lambda h: -h["gewicht"]):
        schluessel = (h["hebel"], h["satz"], h["absatz"], h["text"][:40])
        if schluessel not in gesehen:
            gesehen.add(schluessel)
            eindeutig.append(h)
    stapel: dict[str, list[dict]] = {}
    for h in eindeutig:
        stapel.setdefault(h["hebel"], []).append(h)
    hebel_folge = sorted(stapel, key=lambda h: (h != "vorgaben", -hebel.get(h, {}).get("prioritaet", 0)))
    auswahl = []
    while len(auswahl) < max_hinweise and any(stapel.values()):
        for h in hebel_folge:
            if stapel[h] and len(auswahl) < max_hinweise:
                auswahl.append(stapel[h].pop(0))

    stand = {"score": bew.get("score"), "p_mensch": bew.get("p_mensch"),
             "kennzahlen": {z["id"]: {"wert": z["wert"], "status": z["status"]} for z in bew.get("kennzahlen", []) if z["bewertet"]},
             "roh": {k: m.get(k) for k in ("satzlaenge_mittel", "woerter_pro_teilsatz", "satzklammer_mittel")},
             "bloecke": [{k: b.get(k) for k in ("nr", "satz_von", "satz_bis", "p_mensch", "score")} for b in (bew.get("bloecke") or [])]}
    fortschritt = None
    if verlauf and verlauf.get("messungen"):
        vorher = verlauf["messungen"][-1]
        besser = [k for k, v in stand["kennzahlen"].items() if k in vorher["kennzahlen"]
                  and ["rot", "gelb", "gruen"].index(v["status"]) > ["rot", "gelb", "gruen"].index(vorher["kennzahlen"][k]["status"])]
        schlechter = [k for k, v in stand["kennzahlen"].items() if k in vorher["kennzahlen"]
                      and ["rot", "gelb", "gruen"].index(v["status"]) < ["rot", "gelb", "gruen"].index(vorher["kennzahlen"][k]["status"])]
        fortschritt = {"score_vorher": vorher.get("score"), "p_mensch_vorher": vorher.get("p_mensch"), "besser": besser, "schlechter": schlechter,
                       "messung_nr": len(verlauf["messungen"]) + 1, "mechanisch_verlaengert": False}
        fortschritt["mechanisch_verlaengert"] = mechanisch_verlaengert(vorher.get("roh", {}), stand["roh"])

    rot = [z for z in bew.get("kennzahlen", []) if z["bewertet"] and z["status"] == "rot"]
    ziel_p = bew.get("ziel_p_mensch") or ts.get("ziel_p_mensch") or 0.5
    # Score-Untergrenze = P10 menschlicher Abschnitte (kalibriert); score_schwelle (Mitte Mensch/KI) nur als Rückfall
    ziel_score = ts.get("ziel_score") or bew.get("score_schwelle") or ts.get("score_schwelle") or 60
    # Rote Kennzahlen sind auch bei Menschen normal (Median ~6 von 35 bei 800 Wörtern) – nur als Obergrenze, falls kalibriert
    ziel_rot = ts.get("ziel_rot_max")
    gruen = sorted([z for z in bew.get("kennzahlen", []) if z["bewertet"] and z["status"] == "gruen"], key=lambda z: -(z["gewicht"] or 0))
    return {"info": erg["info"], "bewertung": {k: bew.get(k) for k in ("score", "p_mensch", "verfuegbar")},
            "hebel": [{"id": h, "name": HEBEL_TEXT[h][0], "warum": HEBEL_TEXT[h][1], "prioritaet": round(hebel[h]["prioritaet"], 2),
                       "kennzahlen": [{k: z.get(k) for k in ("id", "name", "wert", "mensch_p25", "mensch_p75", "ki_p50", "status", "richtung", "nur_modell", "beitrag")} for z in hebel[h]["kennzahlen"]]}
                      for h in reihenfolge],
            "hinweise": auswahl, "anzahl_hinweise_gesamt": len(eindeutig),
            "rot": len(rot), "gut": [z["name"] for z in gruen[:4]], "stand": stand, "fortschritt": fortschritt,
            "ziel_p_mensch": ziel_p, "ziel_score": ziel_score, "ziel_rot_max": ziel_rot,
            "bloecke": bew.get("bloecke") or [], "blockmodus": bool(bew.get("blockmodus")),
            "ziel_erreicht": bool(bew.get("verfuegbar") and (bew.get("score") or 0) >= ziel_score
                                  and (bew.get("p_mensch") is None or bew["p_mensch"] >= ziel_p)
                                  and (ziel_rot is None or len(rot) <= ziel_rot))}


def fmt(x):
    return analyse.fmt(x).replace(".", ",") if isinstance(x, float) else str(x)


def bericht(c: dict) -> str:
    out = ["## Stil-Coach", ""]
    b, info = c["bewertung"], c["info"]
    kopf = f"{info['woerter']} Wörter · {info['saetze']} Sätze · {info['absaetze']} Absätze"
    if b.get("verfuegbar"):
        kopf += f" · **Score {b['score']}/100** · Modell: {round(100 * (b['p_mensch'] or 0))} % menschlich · {c['rot']} Kennzahlen rot"
    out.append(kopf)
    for w in info["warnungen"]:
        out.append(f"\n> ⚠️ {w}")
    if c["fortschritt"]:
        f = c["fortschritt"]
        d = (b["score"] or 0) - (f["score_vorher"] or 0)
        out.append(f"\n**Fortschritt (Messung {f['messung_nr']}):** Score {f['score_vorher']} → {b['score']} ({'+' if d >= 0 else ''}{d})"
                   + (f" · besser: {', '.join(analyse.NAMEN.get(k, k) for k in f['besser'])}" if f["besser"] else "")
                   + (f" · schlechter: {', '.join(analyse.NAMEN.get(k, k) for k in f['schlechter'])}" if f["schlechter"] else ""))
    if c["fortschritt"] and c["fortschritt"].get("mechanisch_verlaengert"):
        out.append("\n> ⚠️ **Mechanisch verlängert:** Die Sätze sind länger geworden, aber Teilsätze und Satzklammern nicht – vermutlich angehängte Teilsätze. Das zählt nicht als Fortschritt; stattdessen nominal verdichten.")
    if c["blockmodus"] and c["bloecke"]:
        out.append("\n**Abschnitte** (lange Texte werden in Abschnitten zu ~800 Wörtern gemessen, wie die Referenz):\n")
        out.append("| Abschnitt | Sätze | Score | Modell |\n|---|---|---|---|")
        schwach = min(c["bloecke"], key=lambda b: b.get("p_mensch") if b.get("p_mensch") is not None else 1)
        for bl in c["bloecke"]:
            marke = " ← am KI-nächsten" if bl is schwach and len(c["bloecke"]) > 1 else ""
            p = bl.get("p_mensch")
            out.append(f"| {bl['nr']} | {bl['satz_von']}–{bl['satz_bis']} | {bl.get('score')} | {round(100 * p) if p is not None else '–'} %{marke} |")
    if c["ziel_erreicht"]:
        rot_teil = f", höchstens {c['ziel_rot_max']} Kennzahlen rot" if c.get("ziel_rot_max") is not None else ""
        out.append(f"\n✅ **Ziel erreicht:** Modell ≥ {round(100 * c['ziel_p_mensch'])} % menschlich, Score ≥ {round(c['ziel_score'])}{rot_teil} – so unauffällig wie die meisten echten Hochschularbeiten. Die Hinweise unten sind optionaler Feinschliff.")
    elif c["bewertung"].get("verfuegbar"):
        out.append(f"\n_Ziel: Modell ≥ {round(100 * c['ziel_p_mensch'])} % menschlich und Score ≥ {round(c['ziel_score'])}. Einzelne rote Kennzahlen sind normal – auch echte Arbeiten haben im Mittel mehrere._")
    if c["hebel"]:
        out.append("\n### Die wichtigsten Hebel\n")
        for i, h in enumerate(c["hebel"][:4], 1):
            werte = "; ".join(f"{k['name']}: {fmt(k['wert'])}" + (" (Tendenz, fließt ins Modell)" if k.get("nur_modell") else f" (Ziel {fmt(k['mensch_p25'])}–{fmt(k['mensch_p75'])})")
                              for k in h["kennzahlen"][:3])
            out.append(f"{i}. **{h['name']}** – {h['warum']}  \n   _{werte}_")
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
