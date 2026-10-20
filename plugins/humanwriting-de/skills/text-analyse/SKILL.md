---
name: text-analyse
description: Analysiert einen deutschen Text statistisch darauf, wie menschlich bzw. KI-typisch er geschrieben ist – Satzlängen mit Varianz und Verteilung, Satzrhythmus, Wortlänge, Silben, Wortschatzvielfalt, Begriffswiederholung, Satzbau, Zeichensetzung, Absätze und KI-Floskeln – und vergleicht jede Kennzahl mit Referenzwerten aus echten deutschen Hochschularbeiten und KI-Texten. Verwende diesen Skill, wenn ein Text geprüft, gescannt, vermessen oder auf KI-Klang untersucht werden soll („wie menschlich ist das?“, „check die Werte“, „analysiere meine Hausarbeit“, „klingt das nach KI?“), und als Messschritt innerhalb des Skills humanisieren.
---

# Textanalyse (Deutsch)

Misst einen Text mit einem deterministischen Python-Skript. **Schätze Kennzahlen nie selbst** – Sprachmodelle können Satzlängen, Varianzen oder Häufigkeiten nicht zuverlässig zählen. Immer das Skript ausführen.

## Aufruf

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/text-analyse/scripts/analyse.py" TEXTDATEI
```

- Eingabe: `.md`, `.txt`, `.docx`, `.odt` oder `.pdf` (PDF nur mit `pdftotext`; `.doc`, `.rtf` und `.pages` werden mit Meldung abgelehnt). Text aus dem Chat zuerst in eine Datei schreiben (z. B. `/tmp/text.md`) oder per stdin übergeben (`-` als Dateiname).
- Die Referenzwerte stammen aus Abschnitten à 800 Wörtern. Texte über 1200 Wörtern bewertet das Skript deshalb automatisch im **Blockmodus**: Es zerlegt den Text an Absatzgrenzen in Blöcke von etwa 800 Wörtern (eine Überschrift bleibt beim folgenden Absatz, ein Riesenabsatz wird an einer Satzgrenze geteilt), bewertet jeden Block und nimmt je Kennzahl den Median über die Blöcke. Lange Texte müssen also nicht von Hand aufgeteilt werden; am Stück gemessen lägen Absatz- und Streuungsmaße zu hoch.
- `--format json` liefert alle Werte maschinenlesbar inklusive Satzliste mit Markierungen (für die Umschreib-Schleife).
- `--alle` zeigt auch die nicht bewerteten Kennzahlen, `--stellen 30` mehr auffällige Sätze.
- Falls `${CLAUDE_PLUGIN_ROOT}` nicht ersetzt wurde: Skript suchen mit `find ~/.claude -path '*text-analyse/scripts/analyse.py' 2>/dev/null | head -1`.
- Nur Python-Standardbibliothek nötig, keine Installation.

Überschriften, Listenpunkte, Tabellen, Code, Fußnotenmarker, Quellenverweise in Klammern („(Müller 2019, S. 12)“) und alles ab „Literaturverzeichnis“ werden für die Messung ausgeblendet, damit nur der Fließtext zählt.

## Ergebnis lesen

Der Bericht enthält:

1. **Menschlichkeits-Score (0–100)**: gewichteter Anteil der trennscharfen Kennzahlen im menschlichen Zielbereich (grün = 1, gelb = 0,5, rot = 0). Gewicht = Trennschärfe der Kennzahl in der Kalibrierung.
2. **Modell-Einschätzung**: logistisches Modell über die trennschärfsten, wenig korrelierten Kennzahlen, kalibriert auf menschlichen vs. KI-Abschnitten. Wahrscheinlichkeit „menschlich“.
3. **Kennzahl-Tabelle**:
   - 🟢 innerhalb der mittleren 50 % menschlicher Texte (P25–P75)
   - 🟡 innerhalb der mittleren 80 % (P10–P90)
   - 🔴 außerhalb, „KI-typisch“ = näher am KI-Median als am Mensch-Median
   - „↑ erhöhen / ↓ senken“ zeigt die Richtung zum Zielbereich.
4. **Satzlängen-Verteilung** als Histogramm und **Satzlängen im Verlauf** (Rhythmus sichtbar machen).
5. **Auffällige Stellen**: Sätze mit Markierungen, z. B. `konnektor_anfang`, `konnektor_mitte` (Konnektor im Satzinneren – eher streichen als verschieben), `dies_anfang`, `gleicher_satzanfang`, `gedankenstrich`, `dreierliste`, `sehr_lang`, `muster:<id>` (KI-Floskel). Die Markierung `gleichfoermig` (Folge fast gleich langer Sätze) ist nur ein Hinweis auf die Stelle: Ähnlich lange Sätze hintereinander sind auch bei Menschen normal. Entscheidend ist die Verteilung insgesamt, nicht einzelne Folgen.
6. **Grenzfall** (Zusatz an einer gelben oder roten Kennzahl, im JSON `unsicher: true`): Der Wert liegt näher an P25/P75 als die halbe typische Messunsicherheit eines 800-Wörter-Abschnitts; bei längeren Texten schrumpft diese Spanne mit √(800 / Wörter). Gelbe Grenzfälle nicht als Hebel nennen. Weil einzelne Kennzahlen bei dieser Textlänge stark streuen, ist die Modell-Einschätzung das verlässlichere Gesamturteil.
7. **ℹ️ Funktionswort-Profil** (`fw_profil_llr_pro_1000`, > 0 = menschlich): geht nur in die Modell-Einschätzung ein, nicht in den Score. Nur als Tendenz lesen; nie einzelne Funktionswörter gezielt einstreuen.
8. **Stärkste KI-Signale im Modell** (im JSON `beitrag` je Kennzahl und `modell_beitraege`, am stärksten KI-ziehend zuerst): Beitrag einer Kennzahl zur Modell-Einschätzung gegenüber einem typischen menschlichen Text. Negativ = zieht Richtung KI. Damit lässt sich erklären, warum die Modell-Einschätzung niedrig ist, auch wenn kaum etwas rot ist.
9. **Blöcke** (nur im Blockmodus, im JSON `blockmodus`, `bloecke`): Tabelle mit Sätzen von–bis, Wörtern, Score und % menschlich je Block; der Block mit der niedrigsten Modell-Einschätzung ist als „am KI-nächsten“ markiert. Die Kennzahlwerte oben sind dann Mediane über die Blöcke, der Score wird aus diesen Medianen berechnet, die Modell-Einschätzung ist der Median der Block-Einschätzungen.

Welche Kennzahlen trennscharf sind, wie die Referenzkorpora aussehen und wie gut Score und Modell auf zurückgehaltenen Texten funktionieren, steht in `references/kennzahlen.md`. Wie gemessen wird (Bereinigung, Satzgrenzen, Silben, Teilsätze, Fenster) und welche Maße bewusst fehlen, steht in `references/kennzahlen-methodik.md`.

## Ergebnis an den Nutzer zurückgeben

- Score, Modell-Einschätzung und die roten/gelben Kennzahlen mit Wert, Zielbereich und KI-Median nennen – in der Art „Satzlängen-Variation 0,31 (Menschen 0,45–0,62, KI 0,33) → zu gleichförmig“.
- Die 3–5 wichtigsten Hebel benennen (nach Gewicht sortiert) und die konkreten Sätze zitieren, die sie verursachen.
- Kennzahlen, die stark miteinander zusammenhängen (z. B. Satzlängen-Variation, -Streuung und Anteil mittellanger Sätze), als **einen** Hebel behandeln. Das Gewicht im Score ist dafür schon gedeckelt.
- Bei weniger als ~300 Wörtern oder 15 Sätzen ausdrücklich auf die Unsicherheit hinweisen.
- Im Blockmodus den KI-nächsten Block mit seinen Satznummern nennen; dort lohnt die Überarbeitung zuerst.
- Wenn der Nutzer Verbesserung möchte: Skill **humanisieren** verwenden.

## Grenzen

- Die Analyse misst Stil-Statistik, keine Urheberschaft. Ein grüner Bericht beweist nicht, dass ein Mensch den Text geschrieben hat, und kommerzielle KI-Detektoren arbeiten zusätzlich mit Sprachmodell-Wahrscheinlichkeiten.
- Referenzwerte gelten für formelle Hochschultexte (Hausarbeit, Abschlussarbeit, Aufgabenbearbeitung). Für E-Mails, Blogtexte oder Literatur sind die Zielbereiche nicht passend.
