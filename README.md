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
python3 plugins/humanwriting-de/skills/humanisieren/scripts/coach.py meine_arbeit.md --verlauf meine_arbeit.coach.json --vorgaben gedankenstrich   # ohne Gender-Vorgabe
python3 plugins/humanwriting-de/skills/humanisieren/scripts/inhalt_check.py alt.md neu.md
```

Nur Python 3.8+ (Standardbibliothek), keine Installation nötig.

## Aufbau

```
.claude-plugin/marketplace.json
plugins/humanwriting-de/
  .claude-plugin/plugin.json
  skills/
    menschlich-schreiben/  SKILL.md, references/{hintergrund,beispiele,hochschulvorgaben-mbs}.md, references/{zielwerte,ki-muster,persoenlicher-wortschatz}.md (generiert)
    text-analyse/          SKILL.md, scripts/analyse.py, data/{baselines,ki_muster,wortlisten}.json, references/kennzahlen*.md
    humanisieren/          SKILL.md, scripts/{coach,inhalt_check}.py, references/techniken.md
kalibrierung/              Korpus-Pipeline, Kalibrierung, Ergebnisse (siehe kalibrierung/README.md)
tests/                     python3 -m unittest discover -s tests
```

Eine englische Variante kommt als eigenes Plugin (`humanwriting-en`), damit jede Sprache eigene Referenzwerte und einen schlanken Kontext hat.

## Kalibrierung und Evaluation

**Referenzwerte** (`kalibrierung/ergebnisse/bericht.md`): 412 deutsche Hochschularbeiten vor 2022 (1116 Abschnitte zu 800 Wörtern) gegen 412 themengleiche Claude-Texte (404 Abschnitte). Das Modell „P(menschlich)“ trennt die beiden Gruppen in 5×5-facher, nach Thema gruppierter Kreuzvalidierung mit AUROC 0,996. „Ziel erreicht“ heißt: Modell ≥ 0,85 und einseitiger Score ≥ 73 (der einseitige Score zählt nur Abweichungen in Richtung KI, AUROC 0,958). Das schaffen 83 % der echten und 0,7 % der KI-Abschnitte. Jedes Modellmerkmal ist auf der der KI abgewandten Seite am menschlichen Band gekappt: Übertreiben bringt keine Punkte. Kein einzelnes Merkmal hebt einen typischen KI-Abschnitt allein über die Schwelle.

**Skill `menschlich-schreiben`** (A/B-Test, fünf BWL-Abschnitte zu je ~900 Wörtern, alle von Claude geschrieben):

| Fassung | Modell Ø | Score KI-Seite Ø | am Ziel | KI-Muster pro 1000 W. (gewichtet) |
|---|---|---|---|---|
| ohne Skill | 0,003 | 52 | 0/5 | 7,6 |
| mit Skill (erste Fassung) | 0,92 | 82 | 4/5 | 1,3 |
| mit Skill (Zielbänder) | 0,96 | 90 | 5/5 | 0 |

Alle Quellen der Skill-Texte waren real und richtig zugeordnet. Ein Prüfer (nicht blind) hielt die Fassung mit Zielbändern auch inhaltlich für die beste. Rest-Schwächen (zu wenige gezählte Konnektoren, Einzelfälle von Überkorrektur) sind danach in den Regeln nachgeschärft.

**Stil-Coach** auf echten Texten (Hauptzweck): In einer Stichprobe von 60 echten Abschnitten erreichen 88 % das Ziel sofort, 47 von 60 bekommen gar keinen Hinweis (im Mittel 0,4 Hinweise; KI-Abschnitte rund 10). Fünf echte Abschnitte knapp unter dem Ziel erreichen es nach 0–3 kleinen Aufträgen alle; der Inhalt blieb laut unabhängigem Prüfer gleich, nie gab es Aufträge in wörtlichen Zitaten.

**Stil-Coach auf Claude-Texten**, geprüft in sieben Runden: Simulierte Studenten haben fünf Claude-Texte ausschließlich nach den Coach-Hinweisen überarbeitet; ein Prüfer hat den Inhalt verglichen, ein Kritiker Hinweise und Nebenwirkungen bewertet. Alle Stände mit der aktuellen Messung neu gemessen:

| Version | Modell Ø (Start 0,003) | Modellziel | Überkorrektur-Markierungen | Textähnlichkeit zum Original |
|---|---|---|---|---|
| v1 | 0,84 | 2/5 | 65 | 0,82 |
| v2 | 0,40 | 1/5 | 24 | 0,89 |
| v3 | 0,36 | 0/5 | 12 | 0,94 |
| v4 | 0,38 | 0/5 | 8 | 0,95 |
| v5 | 0,27 | 0/5 | 6 | 0,97 |
| v6 | 0,32 | 0/5 | 10 | 0,96 |
| v7 | 0,32 | 0/5 | 5 | 0,97 |

- v1 erreichte das Ziel durch **Überkorrektur**: zu viele lange Sätze, schwerere Lesbarkeit, Inhaltsverschiebungen. Ab v2 gibt der Coach nur so viele Aufträge, wie bis zum menschlichen Median nötig sind, simuliert jeden Auftrag vorab und meldet Überkorrektur.
- Danach verbessert der Coach Claude-Texte deutlich (Logit-Summe −11,1 → −6,2), bringt sie mit Einzelkorrekturen aber **nicht** auf menschliches Niveau. Der größte Rest ist das **Funktionswort-Profil** (Verteilung kleiner Wörter wie „als“, „sich“, „es“, „werden“). Es entsteht beim Formulieren selbst und lässt sich durch Umbauen einzelner Sätze kaum verschieben. Der Coach sagt das ehrlich und nennt die Absätze, die man neu formulieren müsste.
- v7 ist die schonendste Fassung (wenigste Markierungen, höchste Ähnlichkeit, Ziel einseitig, Vorgaben getrennt, Zitatschutz auch verschachtelt). v7.1 behebt danach die Befunde der Abschlussprüfungen (Berichtsklarheit, abschaltbare Vorgaben, Mindestwirkung je Auftrag).

Fazit: Der Coach ist für **selbst geschriebene Texte** gebaut. Ein Claude-Entwurf wird durch nachträgliches Coachen nicht menschlich; mit den Regeln von `menschlich-schreiben` von Anfang an geschrieben, erreicht er das Stil-Ziel dagegen schon im ersten Wurf.

## Hochschulvorgaben (Munich Business School)

`references/hochschulvorgaben-mbs.md` fasst die Form- und Zitiervorgaben der MBS Research Guidelines 2026 zusammen (APA 7, Gliederung, Seitenformat, Abstract auf Englisch). `menschlich-schreiben` nutzt sie, wenn an der MBS geschrieben wird. Ob und wie viel KI in einer Arbeit erlaubt ist, entscheidet der Dozent; die Skills schränken das nicht ein.

## Grenzen

- Die Kennzahlen beschreiben Stilstatistik. Ein Text im grünen Bereich ist im Stil unauffällig – das ist kein Nachweis menschlicher Urheberschaft, und KI-Detektoren arbeiten mit anderen Verfahren.
- **Wasserzeichen:** Anthropic markiert von Claude formulierten Text statistisch in der Wortwahl ([Ankündigung](https://www.anthropic.com/news/claude-text-watermark)); Bildungseinrichtungen können eine Erkennungs-Schnittstelle nutzen. Stilistisches Überarbeiten durch Claude ändert daran nichts. Deshalb ist der Coach-Modus der Standard: Die Formulierungen stammen vom Nutzer, Claude misst und gibt Hinweise. Für Abgaben gelten die KI-Regeln der jeweiligen Hochschule.
