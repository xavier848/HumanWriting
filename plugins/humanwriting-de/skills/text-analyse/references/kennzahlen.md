# Kennzahlen, Referenzkorpus und Güte

Automatisch erzeugt aus `data/baselines.json` (kalibrierung/scripts/referenzen.py).

## Referenzkorpus

- **Mensch:** 412 Dokumente, 1116 Abschnitte. Quellen: haw-hamburg (54), hs-mittweida (49), opus-fh (120), ssoar (137), uni-hausarbeiten (52). Nur Texte bis einschließlich 2021 (sicher vor ChatGPT).
- **KI:** 412 Dokumente, 404 Abschnitte. Quellen: claude (412). Themengleich: Jeder KI-Text wurde aus einer inhaltlichen Gliederung eines menschlichen Auszugs geschrieben.

## Güte out-of-fold (5×5 gruppierte Kreuzvalidierung (Thema = basis_id bzw. doc_id))

Mittelwert ± SD über die Folds; pro Fold wurde alles (Perzentile, Gewichte, Funktionswort-Profil, Modell) nur aus den Train-Themen geschätzt.

| Verfahren | AUROC | Genauigkeit | bal. Genauigkeit | Median Mensch | Median KI |
|---|---|---|---|---|---|
| Modell P(menschlich) | 0,996 ± 0,002 | 0,970 ± 0,009 | 0,970 ± 0,010 | 1,00 ± 0,00 | 0,01 ± 0,00 |
| Menschlichkeits-Score | 0,788 ± 0,031 | 0,726 ± 0,030 | 0,724 ± 0,026 | 69,13 ± 0,77 | 56,97 ± 1,74 |
| Einseitiger Score | 0,957 ± 0,011 | 0,906 ± 0,016 | 0,892 ± 0,017 | 85,57 ± 0,90 | 57,96 ± 1,95 |

## Schwellen

- **Score-Schwelle 63,3**: Mitte zwischen den Medianen der Out-of-fold-Scores von Mensch und KI.
- **Ziel für P(menschlich) 0,85**: P10 der menschlichen Out-of-fold-Wahrscheinlichkeiten, begrenzt auf [0,5; 0,95], auf 2 Stellen gerundet. Zusammen mit der Score-Schwelle ist das das Ziel des Coachs.
- **Ziel für den Score 56,3**: P10 der menschlichen Out-of-fold-Scores.
- **Ziel für den einseitigen Score 73,2**: P10 der menschlichen Out-of-fold-Werte des einseitigen Scores (Abweichungen auf der Gegenseite der KI zählen wie grün).
- **Anteil „Ziel erreicht“ (out-of-fold)**: Mensch 83,3 %, KI 0,7 % – p_mensch ≥ ziel_p_mensch und score_ki ≥ ziel_score_ki (out-of-fold). Mit dem zweiseitigen Score statt des einseitigen: Mensch 81,5 %, KI 0,7 %. Auch ein Teil echter menschlicher Abschnitte verfehlt das Ziel; es ist eine Orientierung, kein Beweis.
- **Modell**: 12 Merkmale, L2-Strafe λ = 0,003162, standardisierte Merkmale auf ±3 begrenzt; k und λ nach der Ein-Standardfehler-Regel (erst wenige Merkmale, dann die stärkste Strafe, deren Log-Loss höchstens einen Standardfehler über dem besten liegt).

## Kalibrierung der Modell-Wahrscheinlichkeit (out-of-fold)

Brier-Score 0,023 (klassenbalanciert 0,023), ECE über 10 Klassen 0,025 (klassenbalanciert 0,015). Klein = gut kalibriert; „klassenbalanciert“ gewichtet Mensch und KI gleich, wie das Modell geschätzt ist.

| Gruppe | P5 | P10 | P25 | P50 | P75 | P90 |
|---|---|---|---|---|---|---|
| Mensch | 0,70 | 0,85 | 0,97 | 1,00 | 1,00 | 1,00 |
| KI | 0,00 | 0,00 | 0,00 | 0,01 | 0,03 | 0,14 |

| P(menschlich) | Abschnitte Mensch | Abschnitte KI | Ø Vorhersage | Anteil Mensch (balanciert) |
|---|---|---|---|---|
| 0,0–0,1 | 7 | 352 | 0,01 | 0,01 |
| 0,1–0,2 | 4 | 19 | 0,14 | 0,07 |
| 0,2–0,3 | 7 | 11 | 0,25 | 0,19 |
| 0,3–0,4 | 6 | 6 | 0,35 | 0,27 |
| 0,4–0,5 | 6 | 5 | 0,44 | 0,30 |
| 0,5–0,6 | 11 | 1 | 0,55 | 0,80 |
| 0,6–0,7 | 20 | 4 | 0,65 | 0,64 |
| 0,7–0,8 | 24 | 3 | 0,76 | 0,74 |
| 0,8–0,9 | 61 | 1 | 0,85 | 0,96 |
| 0,9–1,0 | 970 | 2 | 0,99 | 0,99 |

## Einseitiger Score

Wie der Menschlichkeits-Score (gewichteter Anteil grün/gelb/rot über die bewerteten Kennzahlen), aber nur Abweichungen in Richtung KI zählen: Liegt eine Kennzahl auf der der KI abgewandten Seite des menschlichen Medians („menschlicher als typisch“), zählt sie wie grün. Der zweiseitige Score bleibt als „score“ erhalten. Auf allen Abschnitten: AUROC 0,959, Median Mensch 85,8, Median KI 58,8. Ziel 73,2 (siehe Schwellen).

## Kappung der Modellmerkmale

Jedes Modellmerkmal wird vor der Standardisierung einseitig am menschlichen Band gekappt: auf der der KI abgewandten Seite höchstens bis zum menschlichen P90 bzw. P10, auf der KI-Seite unverändert (dort gilt das z-Clipping). Ein Wert „menschlicher als 90 % der Menschen“ zählt so nicht noch menschlicher; Übertreiben bringt keine Wahrscheinlichkeit.

| Merkmal | gekappt | Grenze | Mensch Median | KI Median | Koeffizient |
|---|---|---|---|---|---|
| Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich) | nach oben (P90) | 7,76 | 3,83 | -3,27 | +2,13 |
| Sätze-pro-Absatz-Variation (CV) | nach oben (P90) | 0,70 | 0,48 | 0,30 | +1,29 |
| KI-Floskeln & -Muster pro 1000 | nach unten (P10) | 0,00 | 2,00 | 6,24 | -1,21 |
| Abkürzungen pro 1000 (z. B., bzw., d. h. …) | nach oben (P90) | 7,47 | 1,29 | 0,00 | +0,95 |
| Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv | nach oben (P90) | 9,01 | 6,76 | 5,29 | +0,65 |
| Begriffsaufnahme zw. Nachbarsätzen | nach oben (P90) | 0,06 | 0,04 | 0,02 | +0,63 |
| Satzlängen-Dispersion (Var/Ø) | nach oben (P90) | 6,21 | 3,73 | 2,52 | +0,61 |
| Semikolons pro 1000 | nach unten (P10) | 0,00 | 0,00 | 1,27 | -0,60 |
| Anteil sehr langer Sätze (≥40 W.) | nach oben (P90) | 14 % | 3 % | 0 % | +0,45 |
| Anteil mittellanger Sätze (14–26 W.) | nach unten (P10) | 38 % | 52 % | 60 % | -0,40 |
| Lexikalische Variation (MATTR-100) | nach unten (P10) | 0,73 | 0,77 | 0,80 | -0,33 |
| Wörter pro Teilsatz | nach oben (P90) | 16,4 | 13,5 | 11,6 | -0,07 |

## Goodhart-Sensitivität des Modells

Was passiert, wenn ein KI-Text nur eine Kennzahl auf den menschlichen Median bringt? Je Modellmerkmal wurde in allen 404 KI-Abschnitten nur dieses Merkmal auf den Median der menschlichen Abschnitte gesetzt (finales Modell). Median P(menschlich) der KI-Abschnitte vorher: 0,005; Ziel: 0,85. ⚠ = das Merkmal allein hebt den mittleren KI-Abschnitt auf das Ziel; dann könnte man das Urteil mit einer einzigen Stellschraube kippen.

| Merkmal | Median P nachher | Median-Änderung | KI-Abschnitte ≥ Ziel | allein über Ziel |
|---|---|---|---|---|
| Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich) | 0,165 | +0,141 | 7 % | nein |
| KI-Floskeln & -Muster pro 1000 | 0,032 | +0,018 | 1 % | nein |
| Sätze-pro-Absatz-Variation (CV) | 0,024 | +0,013 | 2 % | nein |
| Begriffsaufnahme zw. Nachbarsätzen | 0,010 | +0,003 | 0 % | nein |
| Semikolons pro 1000 | 0,011 | +0,003 | 0 % | nein |
| Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv | 0,010 | +0,003 | 1 % | nein |
| Satzlängen-Dispersion (Var/Ø) | 0,009 | +0,002 | 0 % | nein |
| Anteil mittellanger Sätze (14–26 W.) | 0,007 | +0,002 | 0 % | nein |
| Abkürzungen pro 1000 (z. B., bzw., d. h. …) | 0,008 | +0,001 | 1 % | nein |
| Lexikalische Variation (MATTR-100) | 0,007 | +0,001 | 0 % | nein |
| Anteil sehr langer Sätze (≥40 W.) | 0,006 | +0,001 | 0 % | nein |
| Wörter pro Teilsatz | 0,005 | -0,000 | 0 % | nein |

Die 3 Merkmale mit dem stärksten Zug Richtung KI gemeinsam (Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich), KI-Floskeln & -Muster pro 1000, Sätze-pro-Absatz-Variation (CV)): Median P nachher 0,828, 46 % der KI-Abschnitte erreichen das Ziel; der mittlere KI-Abschnitt bleibt darunter.

## Alle Kennzahlen

| Kennzahl | Mensch P10 / P25 / P50 / P75 / P90 | KI P25 / P50 / P75 | Trennschärfe | bewertet | Gewicht | Messunsicherheit | Bedeutung |
|---|---|---|---|---|---|---|---|
| Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich) | -0,57 / 1,50 / 3,83 / 5,82 / 7,76 | -5,54 / -3,27 / -1,66 | 0,95 | nur Modell |  | 2,80 | Wie menschentypisch die 40 häufigsten Funktionswörter verteilt sind (Menschen: mehr „es“, „wie“, „auch“, „durch“; KI: mehr „als“, „sich“, „dass“), als Log-Likelihood-Quotient pro 1000 Wörter; > 0 = eher menschlich. Nur im Modell, kein Schreibziel: keine Einzelwörter einstreuen. |
| KI-Floskeln & -Muster pro 1000 | 0,00 / 0,74 / 2,00 / 3,69 / 5,11 | 4,28 / 6,24 / 8,70 | 0,86 | ✔ | 0,72 | 2,05 | Treffer der KI-Muster pro 1000 Token, gewichtet nach log2(KI-Rate / Mensch-Rate). |
| Sätze-pro-Absatz-Variation (CV) | 0,30 / 0,39 / 0,48 / 0,59 / 0,70 | 0,23 / 0,30 / 0,36 | 0,86 | ✔ | 0,37 | 0,16 |  |
| Absatzlängen-Variation (CV) | 0,28 / 0,37 / 0,45 / 0,56 / 0,66 | 0,23 / 0,29 / 0,35 | 0,84 | ✔ | 0,35 | 0,15 |  |
| Begriffsaufnahme zw. Nachbarsätzen | 0,02 / 0,03 / 0,04 / 0,05 / 0,06 | 0,02 / 0,02 / 0,03 | 0,81 | ✔ | 0,21 | 0,01 | Jaccard-Überlappung der Inhaltswortstämme benachbarter Sätze. |
| Vielfalt der Inhaltswörter | 0,82 / 0,85 / 0,88 / 0,90 / 0,92 | 0,90 / 0,92 / 0,93 | 0,80 | ✔ | 0,21 | 0,03 |  |
| Satzlängen-Dispersion (Var/Ø) | 2,37 / 2,93 / 3,73 / 4,94 / 6,21 | 2,12 / 2,52 / 3,10 | 0,80 | ✔ | 0,21 | 1,42 | Varianz geteilt durch Mittelwert (Dispersionsindex der Satzlängen). |
| Sätze, die einen Begriff des Vorsatzes aufnehmen | 31 % / 41 % / 50 % / 63 % / 71 % | 26 % / 35 % / 42 % | 0,80 | ✔ | 0,20 | 11 % | Anteil der Sätze, die mindestens einen Inhaltswortstamm des Vorsatzes aufnehmen. |
| Wörter pro Teilsatz | 11,2 / 12,2 / 13,5 / 14,8 / 16,4 | 10,9 / 11,6 / 12,4 | 0,80 | ✔ | 0,60 | 1,43 |  |
| Satzlänge Standardabweichung | 6,44 / 7,45 / 8,81 / 10,5 / 12,2 | 6,20 / 6,80 / 7,67 | 0,80 | ✔ | 0,21 | 1,73 | Standardabweichung der Satzlängen in Wörtern. |
| Lexikalische Variation (MATTR-100) | 0,73 / 0,75 / 0,77 / 0,79 / 0,81 | 0,79 / 0,80 / 0,81 | 0,79 | ✔ | 0,30 | 0,02 | Moving-Average Type-Token-Ratio über 100-Wort-Fenster: Anteil verschiedener Wortformen. |
| Lexikalische Variation (MTLD) | 101 / 120 / 142 / 166 / 193 | 160 / 181 / 206 | 0,78 | ✔ | 0,28 | 25,2 | Measure of Textual Lexical Diversity (McCarthy & Jarvis 2010). |
| Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv | 4,88 / 5,70 / 6,76 / 7,88 / 9,01 | 4,75 / 5,29 / 6,07 | 0,78 | ✔ | 0,56 | 1,51 | Mittlere Zahl der Wörter zwischen finitem Hilfs-/Modalverb und Partizip/Infinitiv, also wie weit die Satzklammer gespannt ist („wurde in der Befragung erstmals … erhoben“). Bewertet ab 5 Klammern. |
| Semikolons pro 1000 | 0,00 / 0,00 / 0,00 / 0,00 / 2,42 | 0,81 / 1,27 / 2,55 | 0,78 | ✔ | 0,55 | 0,99 |  |
| Abkürzungen pro 1000 (z. B., bzw., d. h. …) | 0,00 / 0,00 / 1,29 / 3,81 / 7,47 | 0,00 / 0,00 / 0,00 | 0,78 | ✔ | 0,55 | 2,27 | Übliche Stil-Abkürzungen (z. B., bzw., d. h., u. a. …) pro 1000 Token; Verweis-Abkürzungen (vgl., S., ebd.) zählen nicht. |
| Längster Satz | 34,0 / 38,0 / 44,0 / 52,0 / 61,0 | 33,0 / 36,0 / 40,0 | 0,77 |  |  | 9,32 |  |
| Satzlängen-Variation (CV = SD/Ø) | 0,35 / 0,38 / 0,43 / 0,48 / 0,53 | 0,34 / 0,37 / 0,40 | 0,77 | ✔ | 0,19 | 0,07 | Standardabweichung geteilt durch Mittelwert – die längenunabhängige „Varianz“ der Satzlängen. |
| Anteil mittellanger Sätze (14–26 W.) | 38 % / 44 % / 52 % / 58 % / 63 % | 55 % / 60 % / 65 % | 0,77 | ✔ | 0,53 | 9 % |  |
| Lexikalische Variation (MATTR-50) | 0,82 / 0,84 / 0,86 / 0,87 / 0,88 | 0,86 / 0,87 / 0,89 | 0,76 |  |  | 0,02 |  |
| Anteil sehr langer Sätze (≥40 W.) | 0 % / 0 % / 3 % / 8 % / 14 % | 0 % / 0 % / 2 % | 0,76 | ✔ | 0,27 | 5 % |  |
| Sätze pro Absatz Ø | 2,64 / 3,19 / 4,00 / 5,25 / 6,67 | 4,74 / 5,38 / 6,00 | 0,75 | ✔ | 0,31 | 1,67 |  |
| Lokale Begriffswiederholung (MATTR ÷ Zufallserwartung) | 0,95 / 0,96 / 0,97 / 0,99 / 1,00 | 0,98 / 0,99 / 1,00 | 0,75 | ✔ | 0,50 | 0,01 | MATTR-100 geteilt durch die Zufallserwartung (Rarefaktion): < 1 = Begriffe kehren lokal gebündelt wieder (eher menschlich), ≈ 1 = Wortwahl gleichmäßig gestreut. Gemessen in 800-Wort-Fenstern. |
| Anteil langer Sätze (≥30 W.) | 4 % / 8 % / 15 % / 24 % / 35 % | 4 % / 7 % / 11 % | 0,75 | ✔ | 0,25 | 8 % |  |
| Satzlänge 90 %-Perzentil | 25,0 / 28,0 / 32,0 / 36,6 / 41,2 | 25,8 / 27,2 / 29,3 | 0,74 |  |  | 4,31 |  |
| Wortlängen-Variation (CV) | 0,59 / 0,61 / 0,63 / 0,66 / 0,68 | 0,58 / 0,61 / 0,63 | 0,72 | ✔ | 0,45 | 0,02 |  |
| Kopplung Teilsatzzahl–Teilsatzlänge | -0,54 / -0,47 / -0,39 / -0,31 / -0,23 | -0,54 / -0,48 / -0,43 | 0,72 |  |  | 0,12 | Korrelation zwischen Teilsatzzahl und Teilsatzlänge; misst vor allem die Gleichförmigkeit der Satzlängen, kein Menzerath-Befund (nicht bewertet). |
| Konnektoren pro 1000 (alle Stellungen) | 2,46 / 3,77 / 6,25 / 8,79 / 11,4 | 7,27 / 9,83 / 12,0 | 0,72 | ✔ | 0,45 | 3,26 | Satzverknüpfer wie „zudem“, „somit“, „folglich“, „jedoch“ in allen Satzstellungen pro 1000 Token. |
| Verhältnis Sätze mit 2 zu 1 Teilsatz | 0,29 / 0,39 / 0,55 / 0,76 / 1,06 | 0,62 / 0,80 / 1,00 | 0,72 | ✔ | 0,25 | 0,29 | Sätze mit genau zwei Teilsätzen im Verhältnis zu Sätzen mit einem Teilsatz (geglättet); hoch = viele gleich gebaute Zweier-Gefüge (typisch KI). |
| Verhältnis Zwei- zu Einsilbern | 0,49 / 0,54 / 0,59 / 0,64 / 0,70 | 0,60 / 0,65 / 0,70 | 0,71 | ✔ | 0,43 | 0,07 | Zahl der Zweisilber im Verhältnis zu den Einsilbern (geglättet); höher = mehr Zweisilber. |
| Anteil Ein-Satz-Absätze | 0 % / 0 % / 0 % / 14 % / 25 % | 0 % / 0 % / 0 % | 0,71 | ✔ | 0,43 | 10 % |  |
| Rhythmus: Autokorrelation log-Satzlängen (Lag 1, biaskorrigiert) | -0,18 / -0,09 / 0,03 / 0,14 / 0,23 | -0,20 / -0,10 / 0,00 | 0,71 | ✔ | 0,42 | 0,17 | Ob lange und kurze Sätze in Phasen kommen (positiv, eher menschlich) oder sich streng abwechseln (negativ): Lag-1-Autokorrelation der log-Satzlängen, um 1/n korrigiert (0 = Zufallsreihenfolge). Ab 30 Sätzen bewertet. |
| Anteil Sätze ohne Komma | 21 % / 29 % / 38 % / 46 % / 53 % | 25 % / 30 % / 35 % | 0,71 | ✔ | 0,41 | 9 % |  |
| Anteil kurzer Wörter (≤3 Buchst.) | 29 % / 30 % / 32 % / 33 % / 35 % | 29 % / 30 % / 31 % | 0,69 | ✔ | 0,38 | 2 % |  |
| Nominalketten (Genitiv-/von-Ketten) pro 100 W. | 1,91 / 2,46 / 3,16 / 3,89 / 4,55 | 2,14 / 2,57 / 3,06 | 0,68 |  |  | 0,82 | Ketten aus mindestens zwei Substantiven, verbunden über Genitiv oder „von“ („die Analyse der Daten der Befragung“), pro 100 Wörter. |
| Anführungen pro 1000 | 0,00 / 1,23 / 3,75 / 7,64 / 13,1 | 0,00 / 1,26 / 2,55 | 0,68 | ✔ | 0,35 | 4,74 |  |
| Satzlänge Ø (Token inkl. Zahlen) | 16,3 / 18,1 / 20,5 / 23,5 / 26,1 | 17,7 / 18,7 / 19,5 | 0,68 |  |  | 2,30 | Durchschnittliche Zahl der Wörter pro Satz. |
| Klammern pro 1000 | 0,00 / 1,26 / 3,81 / 8,61 / 13,7 | 0,00 / 1,27 / 3,80 | 0,67 | ✔ | 0,34 | 4,63 |  |
| Anteil Sätze mit Nebensatz | 24 % / 31 % / 39 % / 48 % / 58 % | 40 % / 47 % / 53 % | 0,67 | ✔ | 0,19 | 10 % |  |
| ich/wir pro 1000 | 0,00 / 0,00 / 0,00 / 2,51 / 8,97 | 0,00 / 0,00 / 0,00 | 0,66 | ✔ | 0,33 | 5,94 |  |
| Absatzlänge Ø (Wörter) | 53,1 / 63,4 / 82,4 / 110 / 145 | 88,2 / 99,3 / 116 | 0,66 | ✔ | 0,20 | 31,4 |  |
| Anteil Funktionswörter | 43 % / 45 % / 47 % / 48 % / 50 % | 44 % / 45 % / 46 % | 0,66 |  |  | 2 % |  |
| „…, sondern“ pro 1000 | 0,00 / 0,00 / 0,00 / 1,27 / 2,53 | 0,00 / 1,26 / 2,54 | 0,66 | ✔ | 0,31 | 1,15 |  |
| Satzlängen-Schiefe | 0,19 / 0,42 / 0,68 / 1,05 / 1,39 | 0,24 / 0,46 / 0,74 | 0,65 | ✔ | 0,30 | 0,51 | Asymmetrie der Satzlängen-Verteilung (positiv = langer Schwanz zu langen Sätzen). |
| Wortlänge Standardabweichung | 3,65 / 3,93 / 4,26 / 4,58 / 4,88 | 3,79 / 4,03 / 4,25 | 0,65 |  |  | 0,27 |  |
| Silben pro Wort SD | 1,27 / 1,37 / 1,48 / 1,59 / 1,71 | 1,31 / 1,40 / 1,48 | 0,65 |  |  | 0,10 |  |
| Doppelpunkte pro 1000 | 0,00 / 0,00 / 2,44 / 3,79 / 6,28 | 2,43 / 3,73 / 4,98 | 0,65 |  |  | 2,84 |  |
| Teilsätze pro Satz | 1,29 / 1,38 / 1,50 / 1,66 / 1,86 | 1,52 / 1,60 / 1,70 | 0,64 |  |  | 0,17 |  |
| Absätze | 5,00 / 6,00 / 9,00 / 12,0 / 14,0 | 6,00 / 7,00 / 8,00 | 0,64 |  |  | 2,42 |  |
| Kommas pro 1000 | 37,1 / 44,6 / 52,6 / 61,1 / 70,4 | 51,7 / 58,3 / 64,9 | 0,64 |  |  | 10,1 |  |
| Anteil einsilbiger Wörter | 38 % / 39 % / 41 % / 43 % / 45 % | 39 % / 40 % / 42 % | 0,63 |  |  | 2 % |  |
| Anteil Wörter ≥5 Silben | 5 % / 7 % / 8 % / 10 % / 12 % | 6 % / 7 % / 9 % | 0,64 |  |  | 2 % |  |
| Yules K (Wiederholungsrate) | 60,4 / 68,0 / 76,2 / 87,4 / 99,5 | 62,9 / 71,2 / 79,4 | 0,63 |  |  | 12,3 | Yules K: höher = mehr Wortwiederholung. |
| Flesch-Amstad (Lesbarkeit) | 11,9 / 18,4 / 26,2 / 33,7 / 40,4 | 25,6 / 30,1 / 35,2 | 0,63 |  |  | 6,35 | Flesch-Reading-Ease, deutsche Anpassung nach Amstad: 180 − ASL − 58,5·ASW. |
| Rhythmus: Längensprung zw. Nachbarsätzen | 0,38 / 0,43 / 0,47 / 0,53 / 0,58 | 0,40 / 0,44 / 0,49 | 0,62 |  |  | 0,08 | Mittlerer Längenunterschied zwischen aufeinanderfolgenden Sätzen, relativ zur Ø-Satzlänge. |
| „man“ pro 1000 | 0,00 / 0,00 / 0,00 / 1,28 / 3,77 | 0,00 / 0,00 / 0,00 | 0,61 |  |  | 1,74 |  |
| Anteil sehr langer Wörter (≥13 Buchst.) | 6 % / 8 % / 10 % / 12 % / 14 % | 8 % / 9 % / 10 % | 0,61 |  |  | 2 % |  |
| Fragesätze pro 1000 | 0,00 / 0,00 / 0,00 / 1,23 / 2,54 | 0,00 / 0,00 / 0,00 | 0,61 |  |  | 2,01 |  |
| Satzlänge Median | 15,0 / 17,0 / 19,0 / 22,0 / 25,0 | 17,0 / 18,0 / 19,0 | 0,60 |  |  | 2,49 |  |
| LIX (Lesbarkeitsindex) | 53,3 / 57,7 / 61,7 / 65,5 / 69,0 | 57,9 / 60,0 / 62,0 | 0,60 |  |  | 3,58 | Lesbarkeitsindex nach Björnsson: Ø-Satzlänge + Prozent Wörter mit mehr als 6 Buchstaben. |
| Anteil Passivsätze | 14 % / 21 % / 30 % / 39 % / 49 % | 19 % / 25 % / 33 % | 0,59 |  |  | 10 % |  |
| „sowohl … als auch“ pro 1000 | 0,00 / 0,00 / 0,00 / 1,22 / 1,27 | 0,00 / 0,00 / 1,26 | 0,59 |  |  | 0,84 |  |
| Anteil sehr kurzer Sätze (≤6 W.) | 0 % / 0 % / 2 % / 4 % / 7 % | 0 % / 0 % / 2 % | 0,59 |  |  | 3 % |  |
| Dreier-Aufzählungen pro 1000 | 0,00 / 1,26 / 3,60 / 5,10 / 7,61 | 2,46 / 3,83 / 6,31 | 0,58 |  |  | 2,67 |  |
| Satzanfang mit Konnektor (Zudem, Darüber hinaus …) | 2 % / 5 % / 9 % / 12 % / 17 % | 5 % / 7 % / 10 % | 0,58 |  |  | 5 % |  |
| Wiener Sachtextformel | 10,9 / 12,1 / 13,2 / 14,3 / 15,2 | 12,2 / 12,9 / 13,6 | 0,57 |  |  | 1,00 | 1. Wiener Sachtextformel (Bamberger & Vanecek): Schulstufe, höher = schwerer. |
| Silben pro Wort Ø | 2,07 / 2,16 / 2,27 / 2,38 / 2,48 | 2,16 / 2,24 / 2,31 | 0,57 |  |  | 0,10 |  |
| Anteil Sätze in gleichförmigen Läufen | 16 % / 24 % / 33 % / 43 % / 52 % | 27 % / 36 % / 48 % | 0,56 |  |  | 13 % | Anteil der Sätze, die in einer Dreierfolge fast gleich langer Sätze (±20 %) stehen. |
| Anteil der 3 häufigsten Satzanfänge | 20 % / 23 % / 27 % / 33 % / 38 % | 22 % / 26 % / 30 % | 0,56 |  |  | 6 % |  |
| Gleicher Satzanfang wie Vorsatz | 0 % / 0 % / 3 % / 5 % / 8 % | 0 % / 2 % / 5 % | 0,55 |  |  | 3 % |  |
| Wortlänge Ø (Buchstaben) | 6,12 / 6,37 / 6,70 / 7,00 / 7,24 | 6,43 / 6,63 / 6,82 | 0,55 |  |  | 0,27 |  |
| Nominalstil (-ung/-heit/-keit … pro 100 W.) | 4,27 / 5,46 / 6,73 / 8,25 / 9,42 | 5,40 / 6,40 / 7,71 | 0,55 |  |  | 1,41 |  |
| Satzlänge 10 %-Perzentil | 8,00 / 9,00 / 10,8 / 12,1 / 14,2 | 9,20 / 10,1 / 11,0 | 0,54 |  |  | 2,14 |  |
| Quellenverweise pro 1000 | 0,00 / 0,00 / 2,41 / 7,73 / 15,2 | 0,00 / 3,74 / 8,53 | 0,54 |  |  | 4,93 |  |
| Satzanfang „Dies zeigt/verdeutlicht …“ | 0 % / 0 % / 0 % / 0 % / 3 % | 0 % / 0 % / 0 % | 0,54 |  |  | 1 % |  |
| Anteil langer Wörter (>6 Buchst.) | 35 % / 38 % / 41 % / 43 % / 45 % | 39 % / 41 % / 43 % | 0,53 |  |  | 3 % |  |
| „nicht nur … sondern“ pro 1000 | 0,00 / 0,00 / 0,00 / 1,21 / 1,27 | 0,00 / 0,00 / 1,25 | 0,53 |  |  | 0,73 |  |
| Anteil Wörter ≥3 Silben | 28 % / 31 % / 34 % / 37 % / 39 % | 32 % / 34 % / 36 % | 0,53 |  |  | 3 % |  |
| Anteil kurzer Sätze (≤10 W.) | 3 % / 6 % / 11 % / 17 % / 24 % | 8 % / 12 % / 16 % | 0,53 |  |  | 6 % |  |
| Gedankenstriche pro 1000 | 0,00 / 0,00 / 0,00 / 2,53 / 5,46 | 0,00 / 0,00 / 2,50 | 0,53 |  |  | 2,06 |  |
| Abschwächungen/Modalität pro 1000 | 3,72 / 6,12 / 8,70 / 12,5 / 16,4 | 6,11 / 8,80 / 11,3 | 0,52 |  |  | 5,05 |  |
| Satzanfang mit Der/Die/Das | 8 % / 12 % / 18 % / 24 % / 30 % | 14 % / 18 % / 24 % | 0,52 |  |  | 7 % |  |
| Markdown-Elemente (Fett, Listen) | 0,00 / 0,00 / 0,00 / 0,00 / 0,00 | 0,00 / 0,00 / 0,00 | 0,52 |  |  | 0,00 |  |
| Ausrufesätze pro 1000 | 0,00 / 0,00 / 0,00 / 0,00 / 0,00 | 0,00 / 0,00 / 0,00 | 0,51 |  |  | 0,28 |  |
| Kommas pro Satz | 0,69 / 0,85 / 1,06 / 1,36 / 1,63 | 0,96 / 1,07 / 1,23 | 0,51 |  |  | 0,28 |  |
| Listenpunkte | 0,00 / 0,00 / 0,00 / 0,00 / 0,00 | 0,00 / 0,00 / 0,00 | 0,50 |  |  | 0,00 |  |
| Überschriften pro 1000 | 0,00 / 0,00 / 0,00 / 0,00 / 0,00 | 0,00 / 0,00 / 0,00 | 0,50 |  |  | 0,00 |  |

## Gebündelte Kennzahlen (Cluster)

Kennzahlen, die in menschlichen Texten stark korrelieren (|r| ≥ 0,7), zählen im Score zusammen höchstens so viel wie ihr stärkstes Mitglied:

- Sätze-pro-Absatz-Variation (CV), Absatzlängen-Variation (CV)
- Begriffsaufnahme zw. Nachbarsätzen, Vielfalt der Inhaltswörter, Sätze, die einen Begriff des Vorsatzes aufnehmen
- Satzlängen-Dispersion (Var/Ø), Satzlänge Standardabweichung, Satzlängen-Variation (CV = SD/Ø)
- Lexikalische Variation (MATTR-100), Lexikalische Variation (MTLD)
- Anteil sehr langer Sätze (≥40 W.), Anteil langer Sätze (≥30 W.)
- Sätze pro Absatz Ø, Absatzlänge Ø (Wörter)
- Verhältnis Sätze mit 2 zu 1 Teilsatz, Anteil Sätze mit Nebensatz

## Modell

Logistische Regression auf standardisierten Kennzahlen (positiv = spricht für menschlich); jedes Merkmal vor der Standardisierung einseitig am menschlichen Band gekappt (siehe Kappung):

- Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich): +2.13
- Sätze-pro-Absatz-Variation (CV): +1.29
- KI-Floskeln & -Muster pro 1000: -1.21
- Abkürzungen pro 1000 (z. B., bzw., d. h. …): +0.95
- Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv: +0.65
- Begriffsaufnahme zw. Nachbarsätzen: +0.63
- Satzlängen-Dispersion (Var/Ø): +0.61
- Semikolons pro 1000: -0.60
- Anteil sehr langer Sätze (≥40 W.): +0.45
- Anteil mittellanger Sätze (14–26 W.): -0.40
- Lexikalische Variation (MATTR-100): -0.33
- Wörter pro Teilsatz: -0.07
