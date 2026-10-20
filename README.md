# HumanWriting

Claude-Code-Plugin für **menschlich geschriebene deutsche Hochschultexte** (Hausarbeit, Bachelor-/Masterarbeit, Seminar- und Aufgabenbearbeitungen). Grundlage sind quantitative Kennzahlen menschlichen Schreibens, kalibriert an echten deutschen Hochschularbeiten vor 2022 im Vergleich zu themengleichen KI-Texten.

## Die drei Skills

| Skill | Wofür | Wie |
|---|---|---|
| `menschlich-schreiben` | Beim Schreiben von Uni-Texten | Stilregeln mit kalibrierten Zielwerten (Satzlängen-Mix, Begriffswiederholung, keine Floskeln/Gedankenstriche …), Selbstcheck mit der Analyse |
| `text-analyse` | Text vermessen | `analyse.py`: Satzlänge und -varianz, Verteilung, Rhythmus, Wortlänge, Silben, Wortschatzvielfalt, Begriffsaufnahme, Satzbau, Zeichensetzung, Absätze, Lesbarkeit, KI-Muster – jeweils mit Zielbereich (Mensch) und KI-Median, Score und Modell-Wahrscheinlichkeit |
| `humanisieren` | Vorhandenen Text überarbeiten | Schleife: messen → gezielt umschreiben → erneut messen + Inhaltscheck (`inhalt_check.py`) → bis alle bewerteten Kennzahlen im menschlichen Bereich sind und der Inhalt unverändert ist |

## Installation (Claude Code, auch Desktop-App)

```
/plugin marketplace add xavier848/HumanWriting
/plugin install humanwriting-de@humanwriting
```

Danach stehen die Skills als `humanwriting-de:menschlich-schreiben`, `humanwriting-de:text-analyse` und `humanwriting-de:humanisieren` zur Verfügung und werden automatisch genutzt, wenn du z. B. „schreib mir die Einleitung meiner Hausarbeit“, „analysier den Text“ oder „mach den Text menschlicher“ sagst.

Die Analyse funktioniert auch ohne Claude:

```bash
python3 plugins/humanwriting-de/skills/text-analyse/scripts/analyse.py meine_arbeit.docx
python3 plugins/humanwriting-de/skills/humanisieren/scripts/inhalt_check.py alt.md neu.md
```

Nur Python 3.8+ (Standardbibliothek), keine Installation nötig.

## Aufbau

```
.claude-plugin/marketplace.json
plugins/humanwriting-de/
  .claude-plugin/plugin.json
  skills/
    menschlich-schreiben/  SKILL.md, references/{zielwerte,ki-muster}.md (generiert)
    text-analyse/          SKILL.md, scripts/analyse.py, data/{baselines,ki_muster}.json, references/kennzahlen.md
    humanisieren/          SKILL.md, scripts/inhalt_check.py, references/techniken.md
kalibrierung/              Korpus-Pipeline, Kalibrierung, Ergebnisse (siehe kalibrierung/README.md)
tests/                     python3 -m unittest discover -s tests
```

Eine englische Variante kommt als eigenes Plugin (`humanwriting-en`), damit jede Sprache eigene Referenzwerte und einen schlanken Kontext hat.

## Grenzen

Die Kennzahlen beschreiben Stilstatistik. Ein Text im grünen Bereich ist statistisch unauffällig. Das ist kein Nachweis menschlicher Urheberschaft, und kommerzielle KI-Detektoren nutzen zusätzlich andere Verfahren.
