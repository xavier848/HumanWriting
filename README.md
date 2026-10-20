# HumanWriting

Claude-Code-Plugin für **menschlich geschriebene deutsche Hochschultexte** (Hausarbeit, Bachelor-/Masterarbeit, Seminar- und Aufgabenbearbeitungen). Grundlage sind quantitative Kennzahlen menschlichen Schreibens, kalibriert an echten deutschen Hochschularbeiten vor 2022 im Vergleich zu themengleichen KI-Texten.

## Die drei Skills

| Skill | Wofür | Wie |
|---|---|---|
| `menschlich-schreiben` | Beim Schreiben von Uni-Texten | Stilregeln mit kalibrierten Zielwerten (lange, verdichtete Sätze statt Einheitslänge, gefüllte Satzklammer, wenige Konnektoren, Begriffswiederholung, keine Floskeln/Gedankenstriche/Semikolons …), Selbstcheck mit der Analyse |
| `text-analyse` | Text vermessen | `analyse.py`: Satzlänge und -varianz, Verteilung, Rhythmus, Wortlänge, Silben, Wortschatzvielfalt, Begriffsaufnahme, Satzbau, Zeichensetzung, Absätze, Lesbarkeit, KI-Muster – jeweils mit Zielbereich (Mensch) und KI-Median, Score und Modell-Wahrscheinlichkeit |
| `humanisieren` | Stil-Coach mit Messschleife | Standard: `coach.py` misst und gibt satzgenaue Arbeitsaufträge, du formulierst selbst, dann wird erneut gemessen (mit Fortschritt). Auf Wunsch überarbeitet Claude selbst, mit Inhaltscheck (`inhalt_check.py`). |

## Installation (Claude Code, auch Desktop-App)

```
/plugin marketplace add xavier848/HumanWriting
/plugin install humanwriting-de@humanwriting
```

Danach stehen die Skills als `humanwriting-de:menschlich-schreiben`, `humanwriting-de:text-analyse` und `humanwriting-de:humanisieren` zur Verfügung und werden automatisch genutzt, wenn du z. B. „schreib mir die Einleitung meiner Hausarbeit“, „analysier den Text“ oder „mach den Text menschlicher“ sagst.

Die Analyse funktioniert auch ohne Claude:

```bash
python3 plugins/humanwriting-de/skills/text-analyse/scripts/analyse.py meine_arbeit.docx
python3 plugins/humanwriting-de/skills/humanisieren/scripts/coach.py meine_arbeit.md --verlauf meine_arbeit.coach.json
python3 plugins/humanwriting-de/skills/humanisieren/scripts/inhalt_check.py alt.md neu.md
```

Nur Python 3.8+ (Standardbibliothek), keine Installation nötig.

## Aufbau

```
.claude-plugin/marketplace.json
plugins/humanwriting-de/
  .claude-plugin/plugin.json
  skills/
    menschlich-schreiben/  SKILL.md, references/hintergrund.md, references/{zielwerte,ki-muster,persoenlicher-wortschatz}.md (generiert)
    text-analyse/          SKILL.md, scripts/analyse.py, data/{baselines,ki_muster,wortlisten}.json, references/kennzahlen*.md
    humanisieren/          SKILL.md, scripts/{coach,inhalt_check}.py, references/techniken.md
kalibrierung/              Korpus-Pipeline, Kalibrierung, Ergebnisse (siehe kalibrierung/README.md)
tests/                     python3 -m unittest discover -s tests
```

Eine englische Variante kommt als eigenes Plugin (`humanwriting-en`), damit jede Sprache eigene Referenzwerte und einen schlanken Kontext hat.

## Grenzen

- Die Kennzahlen beschreiben Stilstatistik. Ein Text im grünen Bereich ist im Stil unauffällig – das ist kein Nachweis menschlicher Urheberschaft, und KI-Detektoren arbeiten mit anderen Verfahren.
- **Wasserzeichen:** Anthropic markiert von Claude formulierten Text statistisch in der Wortwahl ([Ankündigung](https://www.anthropic.com/news/claude-text-watermark)); Bildungseinrichtungen können eine Erkennungs-Schnittstelle nutzen. Stilistisches Überarbeiten durch Claude ändert daran nichts. Deshalb ist der Coach-Modus der Standard: Die Formulierungen stammen vom Nutzer, Claude misst und gibt Hinweise. Für Abgaben gelten die KI-Regeln der jeweiligen Hochschule.
