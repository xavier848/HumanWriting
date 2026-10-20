# Kalibrierung

Hier entstehen die Referenzwerte, an denen `analyse.py` jeden Text misst. Ziel ist, dass die Zielbereiche aus **echten Daten** stammen und nicht aus Vermutungen.

## Ablauf

```
korpus/mensch/<quelle>/   ← menschliche Hochschultexte (≤ 2021), per extract_text.py aus PDFs
        │
        ├─ auszuege.py    → pro Dokument ein Auszug (mittlerer Abschnitt)
        │       │
        │       └─ Agent A: inhaltliche Gliederung in Stichpunkten (kein Wortlaut)
        │               │
        │               └─ Agent B (sieht nur die Gliederung): schreibt den Abschnitt
        │                       als Antwort auf eine typische Studierenden-Anfrage
        ▼
korpus/ki/<modell>/       ← themengleiche KI-Texte
        │
        └─ kalibriere.py  → ergebnisse/features.csv, ergebnisse/bericht.md, ergebnisse/wortlisten.json,
                            text-analyse/data/baselines.json, Gewichte in text-analyse/data/ki_muster.json
                └─ referenzen.py → references/zielwerte.md, ki-muster.md, kennzahlen.md
```

## Designentscheidungen

- **Nur Texte bis 2021.** Alles danach könnte bereits KI-beeinflusst sein.
- **Register passend zum Einsatz:** Bachelor-/Masterarbeiten, Seminar- und Hausarbeiten, Fachartikel und Gutachten, vor allem aus Wirtschaft, Sozialwissenschaften, Psychologie, Medien und Bildung.
- **Themengleiches Design:** Jeder KI-Text entsteht aus der inhaltlichen Gliederung eines menschlichen Auszugs. Unterschiede in den Kennzahlen sind dadurch Stil- und keine Themenunterschiede. Der schreibende Agent sieht den menschlichen Wortlaut nie.
- **Vergleichbare Abschnitte:** Alle Texte werden in Abschnitte von ~600–1300 Wörtern zerlegt (höchstens 3 pro menschlichem Dokument, gleichmäßig verteilt), damit längenabhängige Kennzahlen vergleichbar sind und lange Arbeiten nicht dominieren.
- **Gleiche Vorverarbeitung:** Überschriften, Listen, Quellenverweise in Klammern, Fußnotenmarker und Literaturverzeichnis werden in beiden Korpora identisch ausgeblendet.
- **Test-Split nach Thema:** 25 % der Dokumente (samt ihrem KI-Gegenstück) werden zurückgehalten und nur zur Bewertung von Score und Modell genutzt.
- **Trennschärfe statt Bauchgefühl:** Eine Kennzahl geht nur in die Bewertung ein, wenn ihre AUROC mindestens 0,65 (bzw. höchstens 0,35) beträgt. Ihr Gewicht ist proportional zur Trennschärfe.
- **Wortlisten** per log-odds-Verhältnis mit informativem Dirichlet-Prior (Monroe, Colaresi & Quinn 2008), nur N-Gramme, die in mindestens 4 Dokumenten vorkommen.

## Grenzen

- Der KI-Korpus stammt von einem Modell (Claude). Andere Modelle haben eigene Vorlieben; die meisten strukturellen Signale (Satzlängen-Gleichförmigkeit, Synonym-Vielfalt, Konnektor-Anfänge) gelten erfahrungsgemäß modellübergreifend, die Floskel-Gewichte weniger.
- PDF-Extraktion ist nicht fehlerfrei. Absatzgrenzen menschlicher Texte sind weniger zuverlässig als Satzgrenzen; Absatz-Kennzahlen sind deshalb mit Vorsicht zu lesen.
- Rohtexte der menschlichen Quellen werden nicht versioniert (Urheberrecht). `meta.jsonl` enthält die URLs; `extract_text.py` reproduziert die Texte.

## Neu kalibrieren

```bash
python3 kalibrierung/scripts/kalibriere.py      # benötigt korpus/mensch und korpus/ki
python3 kalibrierung/scripts/referenzen.py      # Referenzdateien der Skills neu erzeugen
python3 -m unittest discover -s tests
```
