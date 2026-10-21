# HumanWriting

Claude-Code-Plugin für **menschlich geschriebene deutsche Hochschultexte** (Hausarbeit, Bachelor-/Masterarbeit, Seminar- und Aufgabenbearbeitungen). Grundlage sind quantitative Kennzahlen menschlichen Schreibens, kalibriert an echten deutschen Hochschularbeiten vor 2022 im Vergleich zu themengleichen KI-Texten.

## Die drei Skills

| Skill | Wofür | Wie |
|---|---|---|
| `menschlich-schreiben` | Beim Schreiben von Uni-Texten | Stilregeln mit kalibrierten Zielwerten (lange, verdichtete Sätze statt Einheitslänge, gefüllte Satzklammer, wenige Konnektoren, Begriffswiederholung, keine Floskeln/Gedankenstriche/Semikolons …), Selbstcheck mit der Analyse |
| `text-analyse` | Text vermessen | `analyse.py`: rund 85 Kennzahlen (Satzlängen-Verteilung und -Rhythmus, Teilsätze, Satzklammer, Wortlänge, Silben, Wortschatz, Begriffsaufnahme, Funktionswort-Profil, Zeichensetzung, Absätze, Konnektoren, KI-Muster), jeweils mit Zielbereich (Mensch) und KI-Median, dazu Score, Modell-Wahrscheinlichkeit und die Merkmale, die am stärksten Richtung KI ziehen. Lange Texte werden in Abschnitten zu ~800 Wörtern gemessen. |
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
    menschlich-schreiben/  SKILL.md, references/{hintergrund,beispiele}.md, references/{zielwerte,ki-muster,persoenlicher-wortschatz}.md (generiert)
    text-analyse/          SKILL.md, scripts/analyse.py, data/{baselines,ki_muster,wortlisten}.json, references/kennzahlen*.md
    humanisieren/          SKILL.md, scripts/{coach,inhalt_check}.py, references/techniken.md
kalibrierung/              Korpus-Pipeline, Kalibrierung, Ergebnisse (siehe kalibrierung/README.md)
tests/                     python3 -m unittest discover -s tests
```

Eine englische Variante kommt als eigenes Plugin (`humanwriting-en`), damit jede Sprache eigene Referenzwerte und einen schlanken Kontext hat.

## Kalibrierung und Evaluation

**Referenzwerte** (`kalibrierung/ergebnisse/bericht.md`): 412 deutsche Hochschularbeiten vor 2022 (1116 Abschnitte zu 800 Wörtern) gegen 412 themengleiche Claude-Texte (404 Abschnitte). Das Modell „P(menschlich)“ trennt die beiden Gruppen in 5×5-facher, nach Thema gruppierter Kreuzvalidierung mit AUROC 0,996 (Score 0,78). „Ziel erreicht“ heißt: Modell ≥ 0,86 und Score ≥ 56 – das schaffen 81 % der echten und 0,5 % der KI-Abschnitte. Kein einzelnes Merkmal hebt einen typischen KI-Abschnitt allein über die Schwelle.

**Stil-Coach**, geprüft in mehreren Runden: Simulierte Studenten haben fünf neue Claude-Texte (BWL-Themen) ausschließlich nach den Coach-Hinweisen überarbeitet; ein unabhängiger Prüfer hat den Inhalt verglichen, ein Kritiker die Hinweise und Nebenwirkungen bewertet.

| Version | Modell Ø (Start ~0,00) | am Ziel | Überkorrektur-Markierungen | Textähnlichkeit zum Original |
|---|---|---|---|---|
| v1 | 0,84 | 3/5 | 66 | 0,82 |
| v2 | 0,41 | 1/5 | 24 | 0,89 |
| v3 | 0,34 | 0/5 | 12 | 0,94 |
| v4 | 0,35 | 0/5 | 8 | 0,95 |

- v1 erreichte das Ziel durch **Überkorrektur**: zu viele lange Sätze, schwerere Lesbarkeit, Inhaltsverschiebungen. Ab v2 gibt der Coach nur so viele Aufträge, wie bis zum menschlichen Median nötig sind, simuliert jeden Auftrag vorab und meldet Überkorrektur.
- Danach verbessert der Coach Claude-Texte deutlich (Logit-Summe −10,7 → −5,8), bringt sie mit Einzelkorrekturen aber **nicht** auf menschliches Niveau. Der größte Rest ist das **Funktionswort-Profil** (Verteilung kleiner Wörter wie „als“, „sich“, „es“, „werden“). Es entsteht beim Formulieren selbst und lässt sich durch Umbauen einzelner Sätze kaum verschieben. Der Coach sagt das ehrlich, statt weiter an Einzelstellen zu drehen.
- **Echte Texte** bekommen wenig: Auf menschlichen Abschnitten zeigt der Coach im Schnitt rund 2 Hinweise (KI-Abschnitte rund 13), am Ziel nur noch Vorgaben wie Semikolon oder Gender; nie Hinweise in wörtlichen Zitaten.

Fazit: Der Coach ist für **selbst geschriebene Texte** gebaut. Einen Claude-Entwurf statistisch „menschlich“ zu machen, gelingt durch Nachbessern nicht ohne Überkorrektur – und das Text-Wasserzeichen bleibt ohnehin.

## Grenzen

- Die Kennzahlen beschreiben Stilstatistik. Ein Text im grünen Bereich ist im Stil unauffällig – das ist kein Nachweis menschlicher Urheberschaft, und KI-Detektoren arbeiten mit anderen Verfahren.
- **Wasserzeichen:** Anthropic markiert von Claude formulierten Text statistisch in der Wortwahl ([Ankündigung](https://www.anthropic.com/news/claude-text-watermark)); Bildungseinrichtungen können eine Erkennungs-Schnittstelle nutzen. Stilistisches Überarbeiten durch Claude ändert daran nichts. Deshalb ist der Coach-Modus der Standard: Die Formulierungen stammen vom Nutzer, Claude misst und gibt Hinweise. Für Abgaben gelten die KI-Regeln der jeweiligen Hochschule.
