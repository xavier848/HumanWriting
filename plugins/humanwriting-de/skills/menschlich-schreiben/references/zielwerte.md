# Zielwerte für deutsche Hochschultexte

Automatisch erzeugt aus `text-analyse/data/baselines.json` (kalibrierung/scripts/referenzen.py). Nicht von Hand bearbeiten.

Grundlage: 412 menschliche Hochschultexte vor 2022 (1116 Abschnitte à 800 Wörter) und 412 KI-Texte zu denselben Themen (404 Abschnitte).

**Zielbereich** = mittlere 50 % der menschlichen Abschnitte (P25–P75, jedes Dokument zählt gleich). **Trennschärfe** = AUROC, richtungsunabhängig (0,5 = trennt nicht, 1,0 = trennt perfekt).

## Bewertete Kennzahlen (nach Trennschärfe)

| Kennzahl | Zielbereich Mensch | Mensch Median | KI Median | Trennschärfe | Tendenz bei KI |
|---|---|---|---|---|---|
| Sätze-pro-Absatz-Variation (CV) | 0,39 – 0,59 | 0,48 | 0,30 | 0,86 | zu niedrig |
| Absatzlängen-Variation (CV) | 0,37 – 0,56 | 0,45 | 0,29 | 0,84 | zu niedrig |
| KI-Floskeln & -Muster pro 1000 | 0,00 – 3,46 | 1,96 | 5,62 | 0,83 | zu hoch |
| Begriffsaufnahme zw. Nachbarsätzen | 0,03 – 0,05 | 0,04 | 0,02 | 0,81 | zu niedrig |
| Vielfalt der Inhaltswörter | 0,85 – 0,90 | 0,88 | 0,92 | 0,80 | zu hoch |
| Sätze, die einen Begriff des Vorsatzes aufnehmen | 41 % – 63 % | 50 % | 35 % | 0,80 | zu niedrig |
| Satzlängen-Dispersion (Var/Ø) | 2,93 – 4,95 | 3,73 | 2,52 | 0,80 | zu niedrig |
| Wörter pro Teilsatz | 12,2 – 14,8 | 13,5 | 11,6 | 0,80 | zu niedrig |
| Satzlänge Standardabweichung | 7,45 – 10,5 | 8,82 | 6,80 | 0,80 | zu niedrig |
| Lexikalische Variation (MATTR-100) | 0,75 – 0,79 | 0,77 | 0,80 | 0,79 | zu hoch |
| Lexikalische Variation (MTLD) | 120 – 166 | 142 | 181 | 0,78 | zu hoch |
| Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv | 5,70 – 7,88 | 6,76 | 5,29 | 0,78 | zu niedrig |
| Semikolons pro 1000 | 0,00 – 0,00 | 0,00 | 1,27 | 0,78 | zu hoch |
| Abkürzungen pro 1000 (z. B., bzw., d. h. …) | 0,00 – 3,81 | 1,29 | 0,00 | 0,78 | zu niedrig |
| Satzlängen-Variation (CV = SD/Ø) | 0,38 – 0,48 | 0,43 | 0,37 | 0,77 | zu niedrig |
| Anteil mittellanger Sätze (14–26 W.) | 44 % – 58 % | 52 % | 60 % | 0,77 | zu hoch |
| Anteil sehr langer Sätze (≥40 W.) | 0 % – 8 % | 3 % | 0 % | 0,76 | zu niedrig |
| Sätze pro Absatz Ø | 3,20 – 5,25 | 4,00 | 5,38 | 0,75 | zu hoch |
| Lokale Begriffswiederholung (MATTR ÷ Zufallserwartung) | 0,96 – 0,99 | 0,97 | 0,99 | 0,75 | zu hoch |
| Anteil langer Sätze (≥30 W.) | 8 % – 24 % | 15 % | 7 % | 0,75 | zu niedrig |
| Wortlängen-Variation (CV) | 0,61 – 0,66 | 0,63 | 0,61 | 0,72 | zu niedrig |
| Konnektoren pro 1000 (alle Stellungen) | 3,77 – 8,79 | 6,25 | 9,83 | 0,72 | zu hoch |
| Verhältnis Sätze mit 2 zu 1 Teilsatz | 0,39 – 0,76 | 0,54 | 0,80 | 0,72 | zu hoch |
| Anteil Ein-Satz-Absätze | 0 % – 14 % | 0 % | 0 % | 0,71 | zu niedrig |
| Verhältnis Zwei- zu Einsilbern | 0,54 – 0,64 | 0,59 | 0,65 | 0,71 | zu hoch |
| Rhythmus: Autokorrelation log-Satzlängen (Lag 1, biaskorrigiert) | -0,09 – 0,14 | 0,03 | -0,10 | 0,71 | zu niedrig |
| Anteil Sätze ohne Komma | 29 % – 46 % | 38 % | 30 % | 0,70 | zu niedrig |
| Anteil kurzer Wörter (≤3 Buchst.) | 30 % – 33 % | 32 % | 30 % | 0,69 | zu niedrig |
| Anführungen pro 1000 | 1,23 – 7,64 | 3,75 | 1,26 | 0,68 | zu niedrig |
| Klammern pro 1000 | 1,26 – 8,61 | 3,81 | 1,27 | 0,67 | zu niedrig |
| Anteil Sätze mit Nebensatz | 31 % – 48 % | 39 % | 47 % | 0,67 | zu hoch |
| ich/wir pro 1000 | 0,00 – 2,51 | 0,00 | 0,00 | 0,66 | zu niedrig |
| Absatzlänge Ø (Wörter) | 63,6 – 110 | 82,4 | 99,3 | 0,66 | zu hoch |
| „…, sondern“ pro 1000 | 0,00 – 1,27 | 0,00 | 1,26 | 0,66 | zu hoch |
| Satzlängen-Schiefe | 0,42 – 1,04 | 0,68 | 0,46 | 0,65 | zu niedrig |

## Nur als Tendenz (Modell, kein Zielbereich)

Diese Kennzahlen gehen nur in die Modell-Einschätzung (P(menschlich)) ein, nicht in den Score, und haben deshalb keinen Zielbereich. Gezielt auf sie hinzuschreiben (z. B. bestimmte Funktionswörter einstreuen) verfälscht die Messung, statt den Text menschlicher zu machen; sie zeigen nur die Richtung.

| Kennzahl | Mensch Median | KI Median | Trennschärfe | Tendenz bei KI | Bedeutung |
|---|---|---|---|---|---|
| Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich) | 3,83 | -3,26 | 0,95 | niedriger | Wie menschentypisch die 40 häufigsten Funktionswörter verteilt sind (Menschen: mehr „es“, „wie“, „auch“, „durch“; KI: mehr „als“, „sich“, „dass“), als Log-Likelihood-Quotient pro 1000 Wörter; > 0 = eher menschlich. Nur im Modell, kein Schreibziel: keine Einzelwörter einstreuen. |

## Was das fürs Schreiben heißt

- **Sätze-pro-Absatz-Variation (CV)**: Menschen liegen typischerweise bei 0,39–0,59, KI-Texte bei 0,23–0,36. Beim Schreiben höher ansetzen als der KI-Reflex.
- **Absatzlängen-Variation (CV)**: Menschen liegen typischerweise bei 0,37–0,56, KI-Texte bei 0,23–0,35. Beim Schreiben höher ansetzen als der KI-Reflex.
- **KI-Floskeln & -Muster pro 1000**: Menschen liegen typischerweise bei 0,00–3,46, KI-Texte bei 3,48–7,85. Beim Schreiben niedriger ansetzen als der KI-Reflex. Treffer der KI-Muster pro 1000 Token, gewichtet nach log2(KI-Rate / Mensch-Rate).
- **Begriffsaufnahme zw. Nachbarsätzen**: Menschen liegen typischerweise bei 0,03–0,05, KI-Texte bei 0,02–0,03. Beim Schreiben höher ansetzen als der KI-Reflex. Jaccard-Überlappung der Inhaltswortstämme benachbarter Sätze.
- **Vielfalt der Inhaltswörter**: Menschen liegen typischerweise bei 0,85–0,90, KI-Texte bei 0,90–0,93. Beim Schreiben niedriger ansetzen als der KI-Reflex.
- **Sätze, die einen Begriff des Vorsatzes aufnehmen**: Menschen liegen typischerweise bei 41 %–63 %, KI-Texte bei 26 %–42 %. Beim Schreiben höher ansetzen als der KI-Reflex. Anteil der Sätze, die mindestens einen Inhaltswortstamm des Vorsatzes aufnehmen.
- **Satzlängen-Dispersion (Var/Ø)**: Menschen liegen typischerweise bei 2,93–4,95, KI-Texte bei 2,12–3,10. Beim Schreiben höher ansetzen als der KI-Reflex. Varianz geteilt durch Mittelwert (Dispersionsindex der Satzlängen).
- **Wörter pro Teilsatz**: Menschen liegen typischerweise bei 12,2–14,8, KI-Texte bei 10,9–12,4. Beim Schreiben höher ansetzen als der KI-Reflex.
- **Satzlänge Standardabweichung**: Menschen liegen typischerweise bei 7,45–10,5, KI-Texte bei 6,20–7,67. Beim Schreiben höher ansetzen als der KI-Reflex. Standardabweichung der Satzlängen in Wörtern.
- **Lexikalische Variation (MATTR-100)**: Menschen liegen typischerweise bei 0,75–0,79, KI-Texte bei 0,79–0,81. Beim Schreiben niedriger ansetzen als der KI-Reflex. Moving-Average Type-Token-Ratio über 100-Wort-Fenster: Anteil verschiedener Wortformen.
- **Lexikalische Variation (MTLD)**: Menschen liegen typischerweise bei 120–166, KI-Texte bei 160–206. Beim Schreiben niedriger ansetzen als der KI-Reflex. Measure of Textual Lexical Diversity (McCarthy & Jarvis 2010).
- **Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv**: Menschen liegen typischerweise bei 5,70–7,88, KI-Texte bei 4,75–6,07. Beim Schreiben höher ansetzen als der KI-Reflex. Mittlere Zahl der Wörter zwischen finitem Hilfs-/Modalverb und Partizip/Infinitiv, also wie weit die Satzklammer gespannt ist („wurde in der Befragung erstmals … erhoben“). Bewertet ab 5 Klammern.

## Satzlängen-Verteilung (Anteil der Sätze je Klasse)

| Wörter | Mensch | KI |
|---|---|---|
| 1-5 | 2 % | 0 % |
| 6-10 | 12 % | 12 % |
| 11-15 | 22 % | 24 % |
| 16-20 | 22 % | 27 % |
| 21-25 | 17 % | 20 % |
| 26-30 | 11 % | 10 % |
| 31-40 | 10 % | 5 % |
| 41+ | 4 % | 1 % |
