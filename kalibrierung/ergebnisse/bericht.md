# Kalibrierungsbericht

Mensch: 412 Dokumente / 1116 Abschnitte · KI: 412 Dokumente / 404 Abschnitte · Abschnittslänge 800 Wörter (verworfen: Mensch 93, KI 8) · themengleiche Paare: 396

Paarprüfung: Bei 0 von 396 Paaren hat ein anderer Abschnitt des Basisdokuments mehr Inhaltswort-Überlappung mit dem KI-Text als der gepaarte mittlere Auszug (Hinweis auf geänderte Extraktion).

## Kreuzvalidierung (5×5 gruppierte Kreuzvalidierung (Thema = basis_id bzw. doc_id))

Pro Fold komplette Kalibrierung auf den Train-Themen (Muster-Gewichte, Funktionswort-Profil, Perzentile, Gate, Cluster, Merkmalsauswahl, Modell), Bewertung auf den zurückgehaltenen Themen. Mittelwert ± SD über die Folds.

| Verfahren | AUROC | Genauigkeit | bal. Genauigkeit | Median Mensch | Median KI |
|---|---|---|---|---|---|
| Modell P(menschlich) | 0.996 ± 0.002 | 0.970 ± 0.009 | 0.970 ± 0.010 | 1.00 ± 0.00 | 0.01 ± 0.00 |
| Menschlichkeits-Score | 0.782 ± 0.030 | 0.721 ± 0.030 | 0.720 ± 0.027 | 69.19 ± 0.82 | 57.25 ± 1.59 |

### Wahl von k und λ

Modell: L2-regularisierte logistische Regression (Klassen balanciert) auf z-Werten, die auf ±3 begrenzt sind (z = max(−3, min(3, (x − Mittel)/SD)), identisch in Fit, Out-of-fold-Vorhersage, Schwellen, Goodhart-Analyse und analyse.bewerte). λ-Gitter (log-gleichabständig, halbe Dekaden): 0.0003162, 0.001, 0.003162, 0.01, 0.03162, 0.1, 0.3162, 1, 3.162, 10, 31.62; k-Gitter: 6, 9, 12, 15, 20.

Ein-Standardfehler-Regel auf dem balancierten Log-Loss out-of-fold (SE = SD über die Folds / √Folds), Reihenfolge:

1. Beste Konfiguration: k = 20, λ = 0.001 mit Log-Loss 0.0798 (SE 0.0042); Grenze 0.0840.
2. k = kleinstes k, dessen bestes λ die Grenze einhält: **k = 12** (bestes λ dort 0.001, Log-Loss 0.0822, SE 0.0040).
3. λ = größtes λ (stärkste Regularisierung) für dieses k mit Log-Loss ≤ Minimum(k) + SE(k) = 0.0862: **λ = 0.003162** (Log-Loss 0.0845).

Out-of-fold gepoolt (Mittel über die Wiederholungen je Abschnitt): Modell-AUROC 0.996, Score-AUROC 0.784. In-sample (finales Modell auf allen Daten): Modell-AUROC 0.997, Score-AUROC 0.785.

| k | λ | AUROC | bal. Genauigkeit | Log-Loss (bal.) |
|---|---|---|---|---|
| 6 | 0.0003162 | 0.994 ± 0.003 | 0.962 ± 0.010 | 0.1019 ± 0.0250 |
| 6 | 0.001 | 0.994 ± 0.003 | 0.962 ± 0.010 | 0.1019 ± 0.0226 |
| 6 | 0.003162 | 0.994 ± 0.003 | 0.961 ± 0.011 | 0.1058 ± 0.0192 |
| 6 | 0.01 | 0.994 ± 0.003 | 0.960 ± 0.009 | 0.1202 ± 0.0158 |
| 6 | 0.03162 | 0.994 ± 0.003 | 0.957 ± 0.011 | 0.1536 ± 0.0128 |
| 6 | 0.1 | 0.993 ± 0.003 | 0.957 ± 0.010 | 0.2167 ± 0.0105 |
| 6 | 0.3162 | 0.993 ± 0.004 | 0.955 ± 0.012 | 0.3188 ± 0.0085 |
| 6 | 1 | 0.992 ± 0.004 | 0.953 ± 0.013 | 0.4539 ± 0.0060 |
| 6 | 3.162 | 0.992 ± 0.004 | 0.952 ± 0.014 | 0.5782 ± 0.0030 |
| 6 | 10 | 0.992 ± 0.004 | 0.952 ± 0.014 | 0.6496 ± 0.0012 |
| 6 | 31.62 | 0.992 ± 0.004 | 0.952 ± 0.014 | 0.6784 ± 0.0004 |
| 9 | 0.0003162 | 0.995 ± 0.003 | 0.964 ± 0.011 | 0.0932 ± 0.0240 |
| 9 | 0.001 | 0.995 ± 0.002 | 0.964 ± 0.011 | 0.0923 ± 0.0209 |
| 9 | 0.003162 | 0.995 ± 0.002 | 0.962 ± 0.011 | 0.0955 ± 0.0176 |
| 9 | 0.01 | 0.995 ± 0.002 | 0.962 ± 0.012 | 0.1087 ± 0.0150 |
| 9 | 0.03162 | 0.994 ± 0.003 | 0.960 ± 0.012 | 0.1389 ± 0.0130 |
| 9 | 0.1 | 0.994 ± 0.003 | 0.960 ± 0.012 | 0.1954 ± 0.0114 |
| 9 | 0.3162 | 0.993 ± 0.003 | 0.956 ± 0.013 | 0.2892 ± 0.0095 |
| 9 | 1 | 0.992 ± 0.003 | 0.954 ± 0.014 | 0.4203 ± 0.0069 |
| 9 | 3.162 | 0.992 ± 0.003 | 0.952 ± 0.015 | 0.5532 ± 0.0037 |
| 9 | 10 | 0.992 ± 0.003 | 0.952 ± 0.015 | 0.6378 ± 0.0015 |
| 9 | 31.62 | 0.991 ± 0.003 | 0.951 ± 0.015 | 0.6741 ± 0.0005 |
| 12 | 0.0003162 | 0.996 ± 0.002 | 0.969 ± 0.011 | 0.0839 ± 0.0237 |
| 12 | 0.001 | 0.996 ± 0.002 | 0.970 ± 0.011 | 0.0822 ± 0.0199 |
| 12 | 0.003162 | 0.996 ± 0.002 | 0.970 ± 0.010 | 0.0845 ± 0.0163 ◀ |
| 12 | 0.01 | 0.996 ± 0.002 | 0.968 ± 0.010 | 0.0961 ± 0.0138 |
| 12 | 0.03162 | 0.996 ± 0.002 | 0.966 ± 0.011 | 0.1234 ± 0.0121 |
| 12 | 0.1 | 0.995 ± 0.002 | 0.965 ± 0.012 | 0.1757 ± 0.0108 |
| 12 | 0.3162 | 0.995 ± 0.003 | 0.964 ± 0.011 | 0.2648 ± 0.0095 |
| 12 | 1 | 0.994 ± 0.003 | 0.962 ± 0.010 | 0.3941 ± 0.0075 |
| 12 | 3.162 | 0.994 ± 0.003 | 0.960 ± 0.010 | 0.5332 ± 0.0045 |
| 12 | 10 | 0.993 ± 0.003 | 0.960 ± 0.010 | 0.6279 ± 0.0020 |
| 12 | 31.62 | 0.993 ± 0.003 | 0.959 ± 0.010 | 0.6705 ± 0.0007 |
| 15 | 0.0003162 | 0.996 ± 0.002 | 0.970 ± 0.009 | 0.0833 ± 0.0232 |
| 15 | 0.001 | 0.996 ± 0.002 | 0.970 ± 0.009 | 0.0810 ± 0.0197 |
| 15 | 0.003162 | 0.996 ± 0.002 | 0.970 ± 0.009 | 0.0826 ± 0.0164 |
| 15 | 0.01 | 0.996 ± 0.002 | 0.971 ± 0.008 | 0.0934 ± 0.0139 |
| 15 | 0.03162 | 0.996 ± 0.002 | 0.970 ± 0.009 | 0.1198 ± 0.0122 |
| 15 | 0.1 | 0.995 ± 0.002 | 0.968 ± 0.011 | 0.1702 ± 0.0109 |
| 15 | 0.3162 | 0.994 ± 0.003 | 0.964 ± 0.011 | 0.2556 ± 0.0096 |
| 15 | 1 | 0.993 ± 0.003 | 0.961 ± 0.011 | 0.3808 ± 0.0076 |
| 15 | 3.162 | 0.992 ± 0.003 | 0.959 ± 0.012 | 0.5206 ± 0.0046 |
| 15 | 10 | 0.992 ± 0.003 | 0.957 ± 0.012 | 0.6209 ± 0.0021 |
| 15 | 31.62 | 0.992 ± 0.003 | 0.956 ± 0.012 | 0.6677 ± 0.0007 |
| 20 | 0.0003162 | 0.996 ± 0.002 | 0.970 ± 0.010 | 0.0838 ± 0.0259 |
| 20 | 0.001 | 0.996 ± 0.002 | 0.970 ± 0.011 | 0.0798 ± 0.0209 |
| 20 | 0.003162 | 0.996 ± 0.002 | 0.971 ± 0.009 | 0.0802 ± 0.0169 |
| 20 | 0.01 | 0.996 ± 0.002 | 0.971 ± 0.009 | 0.0899 ± 0.0141 |
| 20 | 0.03162 | 0.996 ± 0.002 | 0.970 ± 0.010 | 0.1144 ± 0.0121 |
| 20 | 0.1 | 0.995 ± 0.002 | 0.968 ± 0.011 | 0.1615 ± 0.0108 |
| 20 | 0.3162 | 0.994 ± 0.003 | 0.962 ± 0.010 | 0.2413 ± 0.0098 |
| 20 | 1 | 0.993 ± 0.003 | 0.955 ± 0.009 | 0.3608 ± 0.0082 |
| 20 | 3.162 | 0.992 ± 0.003 | 0.951 ± 0.010 | 0.5014 ± 0.0053 |
| 20 | 10 | 0.991 ± 0.003 | 0.950 ± 0.010 | 0.6099 ± 0.0025 |
| 20 | 31.62 | 0.991 ± 0.003 | 0.948 ± 0.010 | 0.6633 ± 0.0009 |

### Kalibrierung der Modell-Wahrscheinlichkeit (out-of-fold)

Brier-Score 0.0231 (klassenbalanciert 0.0230) · ECE (10 gleich breite Klassen) 0.0252 (klassenbalanciert 0.0163). Das Modell ist klassenbalanciert geschätzt; die balancierten Werte gewichten beide Gruppen gleich (Prior 50 : 50), die rohen folgen dem Korpusverhältnis.

| Gruppe | P5 | P10 | P25 | P50 | P75 | P90 | P95 |
|---|---|---|---|---|---|---|---|
| Mensch | 0.683 | 0.858 | 0.971 | 0.996 | 1.000 | 1.000 | 1.000 |
| KI | 0.000 | 0.000 | 0.001 | 0.007 | 0.034 | 0.146 | 0.318 |

Reliabilitätstabelle (gleich breite Klassen der Out-of-fold-Wahrscheinlichkeit):

| p-Klasse | n Mensch | n KI | Ø Vorhersage | Anteil Mensch | Ø Vorhersage (bal.) | Anteil Mensch (bal.) |
|---|---|---|---|---|---|---|
| 0.0–0.1 | 6 | 354 | 0.015 | 0.017 | 0.015 | 0.006 |
| 0.1–0.2 | 4 | 19 | 0.150 | 0.174 | 0.151 | 0.071 |
| 0.2–0.3 | 9 | 10 | 0.242 | 0.474 | 0.243 | 0.246 |
| 0.3–0.4 | 6 | 4 | 0.355 | 0.600 | 0.360 | 0.352 |
| 0.4–0.5 | 6 | 5 | 0.442 | 0.545 | 0.441 | 0.303 |
| 0.5–0.6 | 11 | 2 | 0.540 | 0.846 | 0.544 | 0.666 |
| 0.6–0.7 | 17 | 5 | 0.651 | 0.773 | 0.653 | 0.552 |
| 0.7–0.8 | 32 | 2 | 0.761 | 0.941 | 0.758 | 0.853 |
| 0.8–0.9 | 56 | 1 | 0.863 | 0.983 | 0.863 | 0.953 |
| 0.9–1.0 | 969 | 2 | 0.988 | 0.998 | 0.988 | 0.994 |

### Schwellen

- **score_schwelle = 63.4**: Mitte zwischen den Medianen der Out-of-fold-Scores von Mensch und KI (Score je Abschnitt gemittelt über die Wiederholungen).
- **ziel_p_mensch = 0.86**: P10 der menschlichen Out-of-fold-Wahrscheinlichkeiten, begrenzt auf [0.5; 0.95], auf 2 Stellen gerundet (90 % der menschlichen Abschnitte erreichen es).
- **ziel_score = 56.4**: P10 der menschlichen Out-of-fold-Scores; Untergrenze für „Ziel erreicht“ im Coach (der Score trennt schwächer als das Modell).
- **Beide Ziele erreicht (out-of-fold):** Mensch 81,2 %, KI 0,5 %.

## Goodhart-Sensitivität (kontrafaktisch, finales Modell)

Je Modellmerkmal wird nur dieses Merkmal in allen 404 KI-Abschnitten auf den menschlichen Median gesetzt (alles andere bleibt). Median p_mensch der KI-Abschnitte vorher: 0.0064; Ziel: 0.86. Beitrag = koef · (z(Wert) − z(Mensch-Median)), Median über die KI-Abschnitte (negativ = zieht Richtung KI). ⚠ = das Merkmal allein hebt den Median-KI-Abschnitt auf ziel_p_mensch: Wer nur darauf hinschreibt, bekäme ohne echten Stilwechsel ein „menschliches“ Urteil.

| Merkmal | Koef. | Mensch-Median | Median-Beitrag KI | Median p nachher | Median Δp | KI-Abschnitte ≥ Ziel | allein über Ziel |
|---|---|---|---|---|---|---|---|
| Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich) | +2.190 | 3.827 | -3.404 | 0.1665 | +0.1497 | 7% | nein |
| KI-Floskeln & -Muster pro 1000 | -1.164 | 1.929 | -1.506 | 0.0317 | +0.0158 | 1% | nein |
| Sätze-pro-Absatz-Variation (CV) | +1.365 | 0.4804 | -1.435 | 0.0288 | +0.0142 | 2% | nein |
| Begriffsaufnahme zw. Nachbarsätzen | +0.697 | 0.0398 | -0.625 | 0.0109 | +0.0033 | 0% | nein |
| Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv | +0.727 | 6.76 | -0.638 | 0.0117 | +0.0030 | 1% | nein |
| Semikolons pro 1000 | -0.626 | 0 | -0.498 | 0.0131 | +0.0028 | 0% | nein |
| Satzlängen-Dispersion (Var/Ø) | +0.734 | 3.729 | -0.519 | 0.0105 | +0.0025 | 0% | nein |
| Anteil mittellanger Sätze (14–26 W.) | -0.439 | 0.5152 | -0.356 | 0.0083 | +0.0018 | 0% | nein |
| Abkürzungen pro 1000 (z. B., bzw., d. h. …) | +1.020 | 1.292 | -0.450 | 0.0086 | +0.0013 | 0% | nein |
| Lexikalische Variation (MATTR-100) | -0.380 | 0.7736 | -0.332 | 0.0088 | +0.0012 | 0% | nein |
| Anteil sehr langer Sätze (≥40 W.) | +0.537 | 0.0278 | -0.247 | 0.0073 | +0.0009 | 0% | nein |
| Wörter pro Teilsatz | -0.033 | 13.51 | +0.031 | 0.0062 | -0.0001 | 0% | nein |

Die 3 Merkmale mit dem stärksten KI-Zug gemeinsam (Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich) -3.40, KI-Floskeln & -Muster pro 1000 -1.51, Sätze-pro-Absatz-Variation (CV) -1.43): Median p nachher 0.8026, Median Δp +0.7410, 37% der KI-Abschnitte ≥ Ziel – der Median-KI-Abschnitt bleibt unter ziel_p_mensch.

## Kennzahlen: Trennschärfe, Paar-Gate, Cluster

Gate: AUROC auf allen Abschnitten und auf den themengleichen Paaren ≥ 0.65 bzw. ≤ 0.35 (gleiche Richtung), Bootstrap-95-%-Intervalle (300 Ziehungen nach Dokument, Seed 1) von Paar-AUROC und Vorzeichen-Anteil ohne 0,5. Perzentile dokumentgewichtet. 'CV' = Anteil der Folds, in denen die Kennzahl bewertet war (bei 'nur Modell': das Gate bestand). ⚠ = |AUROC alle − AUROC Paare| > 0,10 (konfundiert).

| Kennzahl | AUROC alle | AUROC Paare [95 %] | Vorzeichen [95 %] | Gate | bewertet | CV | Gewicht | Cluster | se_typ | Mensch P25–P50–P75 | KI P25–P50–P75 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich) (nur Modell) | 0.952 | 0.944 [0.93; 0.96] | 0.99 [0.99; 1.00] | ✔ | Modell | 100% |  |  | 2.7983 | 1.5 – 3.83 – 5.83 | -5.54 – -3.26 – -1.66 |
| Sätze-pro-Absatz-Variation (CV) | 0.858 | 0.859 [0.83; 0.89] | 0.87 [0.83; 0.90] | ✔ | ✔ | 100% | 0.368 | saetze_pro_absatz_cv | 0.1557 | 0.389 – 0.48 – 0.59 | 0.232 – 0.3 – 0.359 |
| KI-Floskeln & -Muster pro 1000 | 0.156 | 0.147 [0.12; 0.17] | 0.12 [0.09; 0.15] | ✔ | ✔ | 100% | 0.689 | ki_muster_pro_1000 | 1.9538 | 0.716 – 1.93 – 3.38 | 3.61 – 5.84 – 8.07 |
| Absatzlängen-Variation (CV) | 0.838 | 0.842 [0.81; 0.87] | 0.84 [0.80; 0.88] | ✔ | ✔ | 100% | 0.348 | saetze_pro_absatz_cv | 0.1476 | 0.367 – 0.454 – 0.559 | 0.225 – 0.288 – 0.351 |
| Begriffsaufnahme zw. Nachbarsätzen | 0.811 | 0.816 [0.80; 0.84] | 0.92 [0.90; 0.94] | ✔ | ✔ | 100% | 0.211 | nachbarsatz_ueberlappung | 0.0131 | 0.0294 – 0.0398 – 0.0511 | 0.0171 – 0.0236 – 0.0305 |
| Vielfalt der Inhaltswörter | 0.196 | 0.181 [0.16; 0.20] | 0.05 [0.04; 0.08] | ✔ | ✔ | 100% | 0.206 | nachbarsatz_ueberlappung | 0.0282 | 0.848 – 0.876 – 0.9 | 0.898 – 0.915 – 0.932 |
| Sätze, die einen Begriff des Vorsatzes aufnehmen | 0.801 | 0.796 [0.77; 0.82] | 0.89 [0.86; 0.92] | ✔ | ✔ | 100% | 0.205 | nachbarsatz_ueberlappung | 0.1090 | 0.406 – 0.5 – 0.626 | 0.262 – 0.349 – 0.422 |
| Satzlängen-Dispersion (Var/Ø) | 0.801 | 0.798 [0.77; 0.82] | 0.82 [0.79; 0.86] | ✔ | ✔ | 100% | 0.21 | satzlaenge_dispersion | 1.4191 | 2.93 – 3.73 – 4.95 | 2.12 – 2.52 – 3.1 |
| Wörter pro Teilsatz | 0.799 | 0.762 [0.74; 0.79] | 0.82 [0.79; 0.86] | ✔ | ✔ | 100% | 0.597 | woerter_pro_teilsatz | 1.4342 | 12.2 – 13.5 – 14.8 | 10.9 – 11.6 – 12.4 |
| Satzlänge Standardabweichung | 0.797 | 0.785 [0.76; 0.81] | 0.80 [0.77; 0.84] | ✔ | ✔ | 100% | 0.207 | satzlaenge_dispersion | 1.7247 | 7.45 – 8.82 – 10.5 | 6.2 – 6.8 – 7.67 |
| Lexikalische Variation (MATTR-100) | 0.209 | 0.200 [0.17; 0.23] | 0.10 [0.07; 0.13] | ✔ | ✔ | 100% | 0.296 | mattr_100 | 0.0210 | 0.753 – 0.774 – 0.791 | 0.786 – 0.8 – 0.814 |
| Lexikalische Variation (MTLD) | 0.220 | 0.211 [0.19; 0.24] | 0.12 [0.09; 0.15] | ✔ | ✔ | 100% | 0.286 | mattr_100 | 25.1364 | 120 – 142 – 166 | 160 – 181 – 206 |
| Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv | 0.777 | 0.764 [0.73; 0.80] | 0.78 [0.74; 0.82] | ✔ | ✔ | 100% | 0.555 | satzklammer_mittel | 1.5104 | 5.7 – 6.76 – 7.88 | 4.75 – 5.29 – 6.07 |
| Semikolons pro 1000 | 0.224 | 0.238 [0.21; 0.27] | 0.23 [0.20; 0.27] | ✔ | ✔ | 100% | 0.551 | semikolon_pro_1000 | 1.2261 | 0 – 0 – 0 | 0.809 – 1.27 – 2.55 |
| Abkürzungen pro 1000 (z. B., bzw., d. h. …) | 0.776 | 0.796 [0.77; 0.82] | 0.81 [0.78; 0.83] | ✔ | ✔ | 100% | 0.551 | abkuerzungen_pro_1000 | 2.2664 | 0 – 1.29 – 3.81 | 0 – 0 – 0 |
| Längster Satz | 0.768 | 0.754 | 0.76 |  |  | – |  |  | 9.3262 | 38 – 44 – 52 | 33 – 36 – 40 |
| Satzlängen-Variation (CV = SD/Ø) | 0.766 | 0.774 [0.74; 0.80] | 0.80 [0.75; 0.83] | ✔ | ✔ | 100% | 0.186 | satzlaenge_dispersion | 0.0659 | 0.385 – 0.428 – 0.48 | 0.343 – 0.373 – 0.401 |
| Anteil mittellanger Sätze (14–26 W.) | 0.233 | 0.234 [0.20; 0.26] | 0.21 [0.17; 0.26] | ✔ | ✔ | 100% | 0.533 | anteil_mittlere_saetze | 0.0877 | 0.444 – 0.515 – 0.578 | 0.551 – 0.6 – 0.652 |
| Lexikalische Variation (MATTR-50) | 0.238 | 0.229 | 0.14 |  |  | – |  |  | 0.0163 | 0.84 – 0.856 – 0.869 | 0.864 – 0.875 – 0.885 |
| Anteil sehr langer Sätze (≥40 W.) | 0.760 | 0.742 [0.72; 0.77] | 0.77 [0.74; 0.80] | ✔ | ✔ | 100% | 0.266 | anteil_sehr_lange_saetze | 0.0459 | 0 – 0.0278 – 0.0812 | 0 – 0 – 0.0224 |
| Sätze pro Absatz Ø | 0.247 | 0.239 [0.20; 0.27] | 0.21 [0.17; 0.25] | ✔ | ✔ | 100% | 0.308 | saetze_pro_absatz | 1.6679 | 3.2 – 4 – 5.25 | 4.74 – 5.38 – 6 |
| Lokale Begriffswiederholung (MATTR ÷ Zufallserwartung) (Kandidat) | 0.247 | 0.210 [0.19; 0.24] | 0.14 [0.11; 0.18] | ✔ | ✔ | 100% | 0.505 | mattr_klumpung_100 | 0.0141 | 0.963 – 0.975 – 0.986 | 0.981 – 0.988 – 0.997 |
| Anteil langer Sätze (≥30 W.) | 0.748 | 0.732 [0.70; 0.77] | 0.74 [0.69; 0.78] | ✔ | ✔ | 100% | 0.254 | anteil_sehr_lange_saetze | 0.0750 | 0.0789 – 0.152 – 0.242 | 0.0427 – 0.0682 – 0.108 |
| Satzlänge 90 %-Perzentil | 0.743 | 0.723 | 0.74 |  |  | – |  |  | 4.3133 | 28 – 32 – 36.6 | 25.8 – 27.2 – 29.3 |
| Wortlängen-Variation (CV) | 0.725 | 0.711 [0.69; 0.74] | 0.88 [0.85; 0.91] | ✔ | ✔ | 100% | 0.45 | wortlaenge_cv | 0.0238 | 0.611 – 0.634 – 0.658 | 0.584 – 0.606 – 0.625 |
| Kopplung Teilsatzzahl–Teilsatzlänge | 0.725 | 0.731 | 0.75 |  |  | – |  |  | 0.1152 | -0.472 – -0.395 – -0.309 | -0.536 – -0.481 – -0.428 |
| Konnektoren pro 1000 (alle Stellungen) | 0.276 | 0.266 [0.24; 0.29] | 0.22 [0.19; 0.26] | ✔ | ✔ | 100% | 0.448 | konnektoren_pro_1000 | 3.2573 | 3.77 – 6.25 – 8.79 | 7.27 – 9.83 – 12 |
| Verhältnis Sätze mit 2 zu 1 Teilsatz | 0.278 | 0.290 [0.26; 0.32] | 0.26 [0.22; 0.30] | ✔ | ✔ | 100% | 0.254 | teilsatz_verhaeltnis_21 | 0.2874 | 0.392 – 0.544 – 0.758 | 0.617 – 0.805 – 1 |
| Anteil Ein-Satz-Absätze | 0.714 | 0.706 [0.68; 0.73] | 0.71 [0.69; 0.74] | ✔ | ✔ | 100% | 0.427 | anteil_einsatz_absaetze | 0.0977 | 0 – 0 – 0.143 | 0 – 0 – 0 |
| Verhältnis Zwei- zu Einsilbern (Kandidat) | 0.287 | 0.274 [0.25; 0.30] | 0.22 [0.18; 0.26] | ✔ | ✔ | 100% | 0.426 | silben_q21 | 0.0656 | 0.536 – 0.589 – 0.644 | 0.6 – 0.651 – 0.697 |
| Rhythmus: Autokorrelation log-Satzlängen (Lag 1, biaskorrigiert) (Kandidat) | 0.713 | 0.695 [0.66; 0.73] | 0.69 [0.65; 0.74] | ✔ | ✔ | 100% | 0.425 | rhythmus_r1_log | 0.1662 | -0.0888 – 0.0264 – 0.137 | -0.204 – -0.102 – 0.0026 |
| Anteil Sätze ohne Komma | 0.705 | 0.702 [0.67; 0.73] | 0.72 [0.68; 0.77] | ✔ | ✔ | 100% | 0.41 | anteil_einfache_saetze | 0.0932 | 0.29 – 0.378 – 0.464 | 0.25 – 0.295 – 0.348 |
| Anteil kurzer Wörter (≤3 Buchst.) | 0.689 | 0.699 [0.67; 0.72] | 0.79 [0.75; 0.83] | ✔ | ✔ | 100% | 0.378 | anteil_kurze_woerter | 0.0185 | 0.302 – 0.316 – 0.332 | 0.286 – 0.3 – 0.314 |
| Nominalketten (Genitiv-/von-Ketten) pro 100 W. (Kandidat) | 0.682 | 0.626 [0.60; 0.66] | 0.66 [0.62; 0.71] |  |  | 0% |  |  | 0.8203 | 2.44 – 3.15 – 3.88 | 2.14 – 2.57 – 3.06 |
| Anführungen pro 1000 | 0.677 | 0.675 [0.65; 0.70] | 0.74 [0.71; 0.78] | ✔ | ✔ | 100% | 0.354 | anfuehrungen_pro_1000 | 4.7393 | 1.23 – 3.75 – 7.64 | 0 – 1.26 – 2.55 |
| Satzlänge Ø (Token inkl. Zahlen) | 0.676 | 0.644 [0.61; 0.68] | 0.66 [0.61; 0.71] |  |  | 32% |  |  | 2.3052 | 18.1 – 20.5 – 23.5 | 17.7 – 18.7 – 19.5 |
| Klammern pro 1000 | 0.669 | 0.693 [0.67; 0.72] | 0.74 [0.70; 0.77] | ✔ | ✔ | 100% | 0.338 | klammern_pro_1000 | 4.6593 | 1.26 – 3.81 – 8.61 | 0 – 1.27 – 3.8 |
| Anteil Sätze mit Nebensatz | 0.334 | 0.347 [0.32; 0.37] | 0.28 [0.24; 0.33] | ✔ | ✔ | 68% | 0.19 | teilsatz_verhaeltnis_21 | 0.0996 | 0.308 – 0.386 – 0.485 | 0.4 – 0.467 – 0.526 |
| ich/wir pro 1000 | 0.664 | 0.653 [0.63; 0.68] | 0.67 [0.65; 0.70] | ✔ | ✔ | 68% | 0.329 | ich_wir_pro_1000 | 5.9419 | 0 – 0 – 2.51 | 0 – 0 – 0 |
| Absatzlänge Ø (Wörter) | 0.337 | 0.321 [0.28; 0.35] | 0.28 [0.23; 0.32] | ✔ | ✔ | 96% | 0.198 | saetze_pro_absatz | 31.3646 | 63.6 – 82.4 – 110 | 88.2 – 99.3 – 116 |
| Anteil Funktionswörter | 0.660 | 0.676 | 0.76 |  |  | – |  |  | 0.0199 | 0.448 – 0.465 – 0.484 | 0.441 – 0.453 – 0.463 |
| „…, sondern“ pro 1000 | 0.344 | 0.349 [0.32; 0.38] | 0.31 [0.27; 0.34] | ✔ | ✔ | 60% | 0.311 | sondern_pro_1000 | 1.1498 | 0 – 0 – 1.27 | 0 – 1.26 – 2.54 |
| Satzlängen-Schiefe | 0.651 | 0.661 [0.63; 0.69] | 0.66 [0.62; 0.71] | ✔ | ✔ | 52% | 0.302 | satzlaenge_schiefe | 0.5134 | 0.418 – 0.684 – 1.04 | 0.242 – 0.463 – 0.736 |
| Wortlänge Standardabweichung | 0.651 | 0.618 [0.60; 0.64] | 0.77 [0.72; 0.81] |  |  | 0% |  |  | 0.2743 | 3.93 – 4.26 – 4.58 | 3.79 – 4.03 – 4.25 |
| Silben pro Wort SD | 0.646 | 0.614 | 0.77 |  |  | 0% |  |  | 0.1034 | 1.37 – 1.48 – 1.59 | 1.31 – 1.4 – 1.48 |
| Doppelpunkte pro 1000 | 0.355 | 0.404 | 0.40 |  |  | 0% |  |  | 2.8385 | 0 – 2.44 – 3.79 | 2.43 – 3.73 – 4.98 |
| Teilsätze pro Satz | 0.356 | 0.376 | 0.35 |  |  | 0% |  |  | 0.1662 | 1.38 – 1.5 – 1.66 | 1.52 – 1.6 – 1.7 |
| Absätze | 0.643 | 0.665 | 0.69 |  |  | – |  |  | 2.4153 | 6 – 9 – 12 | 6 – 7 – 8 |
| Kommas pro 1000 | 0.364 | 0.377 | 0.33 |  |  | 0% |  |  | 10.1546 | 44.6 – 52.6 – 61.2 | 51.7 – 58.3 – 64.9 |
| Anteil Wörter ≥5 Silben | 0.634 | 0.595 | 0.72 |  |  | 0% |  |  | 0.0180 | 0.0656 – 0.0845 – 0.104 | 0.0568 – 0.0729 – 0.0859 |
| Anteil einsilbiger Wörter | 0.634 | 0.667 | 0.74 |  |  | 0% |  |  | 0.0233 | 0.395 – 0.412 – 0.435 | 0.386 – 0.401 – 0.416 |
| Yules K (Wiederholungsrate) | 0.628 | 0.608 | 0.66 |  |  | 0% |  |  | 12.2833 | 68 – 76.2 – 87.4 | 62.9 – 71.2 – 79.4 |
| Flesch-Amstad (Lesbarkeit) | 0.374 | 0.420 | 0.38 |  |  | 0% |  |  | 6.3459 | 18.4 – 26.2 – 33.7 | 25.6 – 30.1 – 35.2 |
| Rhythmus: Längensprung zw. Nachbarsätzen | 0.616 | 0.623 | 0.63 |  |  | – |  |  | 0.0777 | 0.426 – 0.474 – 0.527 | 0.398 – 0.442 – 0.491 |
| „man“ pro 1000 | 0.612 | 0.618 | 0.64 |  |  | 0% |  |  | 1.7444 | 0 – 0 – 1.28 | 0 – 0 – 0 |
| Anteil sehr langer Wörter (≥13 Buchst.) | 0.611 | 0.584 | 0.68 |  |  | 0% |  |  | 0.0183 | 0.0788 – 0.101 – 0.122 | 0.0759 – 0.0895 – 0.105 |
| Satzlänge Median | 0.606 | 0.578 | 0.60 |  |  | – |  |  | 2.4955 | 17 – 19 – 22 | 17 – 18 – 19 |
| Fragesätze pro 1000 | 0.606 | 0.574 | 0.58 |  |  | 0% |  |  | 2.0062 | 0 – 0 – 1.23 | 0 – 0 – 0 |
| LIX (Lesbarkeitsindex) | 0.599 | 0.555 | 0.54 |  |  | 0% |  |  | 3.5847 | 57.7 – 61.7 – 65.6 | 57.9 – 60 – 62 |
| Anteil Passivsätze | 0.595 | 0.589 | 0.63 |  |  | 0% |  |  | 0.1041 | 0.205 – 0.298 – 0.394 | 0.186 – 0.25 – 0.333 |
| „sowohl … als auch“ pro 1000 | 0.405 | 0.396 | 0.39 |  |  | 0% |  |  | 0.8355 | 0 – 0 – 1.22 | 0 – 0 – 1.26 |
| Anteil sehr kurzer Sätze (≤6 W.) | 0.589 | 0.585 | 0.60 |  |  | 0% |  |  | 0.0307 | 0 – 0.0213 – 0.0417 | 0 – 0 – 0.0238 |
| Dreier-Aufzählungen pro 1000 | 0.417 | 0.406 | 0.29 |  |  | 0% |  |  | 2.6819 | 1.26 – 3.62 – 5.11 | 2.46 – 3.85 – 6.33 |
| Satzanfang mit Konnektor (Zudem, Darüber hinaus …) | 0.578 | 0.571 | 0.57 |  |  | 0% |  |  | 0.0510 | 0.05 – 0.0857 – 0.125 | 0.0465 – 0.0714 – 0.1 |
| Wiener Sachtextformel | 0.574 | 0.528 | 0.51 |  |  | 0% |  |  | 1.0002 | 12.1 – 13.2 – 14.3 | 12.2 – 12.9 – 13.6 |
| Silben pro Wort Ø | 0.568 | 0.522 | 0.54 |  |  | 0% |  |  | 0.0987 | 2.16 – 2.27 – 2.38 | 2.16 – 2.24 – 2.31 |
| Anteil Sätze in gleichförmigen Läufen | 0.434 | 0.427 | 0.43 |  |  | 0% |  |  | 0.1341 | 0.242 – 0.333 – 0.435 | 0.267 – 0.362 – 0.477 |
| Anteil der 3 häufigsten Satzanfänge | 0.561 | 0.560 | 0.58 |  |  | 0% |  |  | 0.0642 | 0.231 – 0.273 – 0.333 | 0.224 – 0.263 – 0.304 |
| Gleicher Satzanfang wie Vorsatz | 0.552 | 0.560 | 0.57 |  |  | 0% |  |  | 0.0315 | 0 – 0.027 – 0.0526 | 0 – 0.0238 – 0.0455 |
| Wortlänge Ø (Buchstaben) | 0.549 | 0.504 | 0.49 |  |  | 0% |  |  | 0.2650 | 6.37 – 6.7 – 7 | 6.43 – 6.63 – 6.82 |
| Nominalstil (-ung/-heit/-keit … pro 100 W.) | 0.548 | 0.511 | 0.53 |  |  | 0% |  |  | 1.4078 | 5.43 – 6.72 – 8.25 | 5.4 – 6.4 – 7.71 |
| Quellenverweise pro 1000 | 0.456 | 0.474 | 0.54 |  |  | – |  |  | 5.0315 | 0 – 1.29 – 7.61 | 0 – 3.74 – 8.53 |
| Satzlänge 10 %-Perzentil | 0.544 | 0.519 | 0.52 |  |  | – |  |  | 2.1363 | 9 – 10.8 – 12.1 | 9.2 – 10.1 – 11 |
| Satzanfang „Dies zeigt/verdeutlicht …“ | 0.538 | 0.558 | 0.56 |  |  | 0% |  |  | 0.0140 | 0 – 0 – 0 | 0 – 0 – 0 |
| Anteil langer Wörter (>6 Buchst.) | 0.466 | 0.432 | 0.35 |  |  | 0% |  |  | 0.0257 | 0.381 – 0.409 – 0.434 | 0.393 – 0.411 – 0.431 |
| „nicht nur … sondern“ pro 1000 | 0.466 | 0.453 | 0.46 |  |  | 0% |  |  | 0.7314 | 0 – 0 – 1.21 | 0 – 0 – 1.25 |
| Anteil Wörter ≥3 Silben | 0.533 | 0.490 | 0.47 |  |  | 0% |  |  | 0.0271 | 0.315 – 0.345 – 0.371 | 0.319 – 0.34 – 0.358 |
| Anteil kurzer Sätze (≤10 W.) | 0.473 | 0.498 | 0.53 |  |  | 0% |  |  | 0.0632 | 0.0606 – 0.105 – 0.171 | 0.0814 – 0.119 – 0.159 |
| Gedankenstriche pro 1000 | 0.525 | 0.521 | 0.51 |  |  | 0% |  |  | 2.0614 | 0 – 0 – 2.53 | 0 – 0 – 2.5 |
| Abschwächungen/Modalität pro 1000 | 0.521 | 0.529 | 0.57 |  |  | 0% |  |  | 5.0530 | 6.1 – 8.7 – 12.5 | 6.11 – 8.8 – 11.3 |
| Satzanfang mit Der/Die/Das | 0.484 | 0.490 | 0.52 |  |  | 0% |  |  | 0.0701 | 0.125 – 0.175 – 0.242 | 0.136 – 0.182 – 0.237 |
| Markdown-Elemente (Fett, Listen) | 0.485 | 0.485 | 0.48 |  |  | – |  |  | 0.0000 | 0 – 0 – 0 | 0 – 0 – 0 |
| Ausrufesätze pro 1000 | 0.514 | 0.518 | 0.52 |  |  | 0% |  |  | 0.2770 | 0 – 0 – 0 | 0 – 0 – 0 |
| Kommas pro Satz | 0.493 | 0.498 | 0.50 |  |  | 0% |  |  | 0.2776 | 0.85 – 1.06 – 1.36 | 0.956 – 1.07 – 1.23 |
| Listenpunkte | 0.500 | 0.500 | 0.50 |  |  | – |  |  | 0.0000 | 0 – 0 – 0 | 0 – 0 – 0 |
| Überschriften pro 1000 | 0.500 | 0.500 | 0.50 |  |  | – |  |  | 0.0000 | 0 – 0 – 0 | 0 – 0 – 0 |

Kandidaten (HW08–HW13, HW22): mattr_klumpung_100: Gate bestanden (AUROC 0.247, Paare 0.21); nominalketten_pro_100: Gate nicht bestanden (AUROC 0.682, Paare 0.626); rhythmus_r1_log: Gate bestanden (AUROC 0.713, Paare 0.695); silben_q21: Gate bestanden (AUROC 0.287, Paare 0.274)

## Cluster redundanter Kennzahlen (|r| ≥ 0.7 in den menschlichen Abschnitten)

Gewicht je Mitglied = Trennschärfe · max/Σ im Cluster; ein Cluster wiegt höchstens so viel wie sein stärkstes Mitglied.

- **saetze_pro_absatz_cv**: saetze_pro_absatz_cv (0.368), absatzlaenge_cv (0.348)
- **ki_muster_pro_1000**: ki_muster_pro_1000 (0.689)
- **nachbarsatz_ueberlappung**: nachbarsatz_ueberlappung (0.211), inhaltswort_mattr_50 (0.206), anteil_saetze_mit_wortaufnahme (0.205)
- **satzlaenge_dispersion**: satzlaenge_dispersion (0.21), satzlaenge_sd (0.207), satzlaenge_cv (0.186)
- **woerter_pro_teilsatz**: woerter_pro_teilsatz (0.597)
- **mattr_100**: mattr_100 (0.296), mtld (0.286)
- **satzklammer_mittel**: satzklammer_mittel (0.555)
- **abkuerzungen_pro_1000**: abkuerzungen_pro_1000 (0.551)
- **semikolon_pro_1000**: semikolon_pro_1000 (0.551)
- **anteil_mittlere_saetze**: anteil_mittlere_saetze (0.533)
- **anteil_sehr_lange_saetze**: anteil_sehr_lange_saetze (0.266), anteil_lange_saetze (0.254)
- **saetze_pro_absatz**: saetze_pro_absatz (0.308), absatzlaenge_mittel (0.198)
- **mattr_klumpung_100**: mattr_klumpung_100 (0.505)
- **wortlaenge_cv**: wortlaenge_cv (0.45)
- **konnektoren_pro_1000**: konnektoren_pro_1000 (0.448)
- **teilsatz_verhaeltnis_21**: teilsatz_verhaeltnis_21 (0.254), anteil_saetze_mit_nebensatz (0.19)
- **anteil_einsatz_absaetze**: anteil_einsatz_absaetze (0.427)
- **silben_q21**: silben_q21 (0.426)
- **rhythmus_r1_log**: rhythmus_r1_log (0.425)
- **anteil_einfache_saetze**: anteil_einfache_saetze (0.41)
- **anteil_kurze_woerter**: anteil_kurze_woerter (0.378)
- **anfuehrungen_pro_1000**: anfuehrungen_pro_1000 (0.354)
- **klammern_pro_1000**: klammern_pro_1000 (0.338)
- **ich_wir_pro_1000**: ich_wir_pro_1000 (0.329)
- **sondern_pro_1000**: sondern_pro_1000 (0.311)
- **satzlaenge_schiefe**: satzlaenge_schiefe (0.302)

## Modell (12 Merkmale, λ = 0.003162)

Logistische Regression auf standardisierten Kennzahlen (positiv = spricht für menschlich):

- Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich): +2.190
- Sätze-pro-Absatz-Variation (CV): +1.365
- KI-Floskeln & -Muster pro 1000: -1.164
- Abkürzungen pro 1000 (z. B., bzw., d. h. …): +1.020
- Satzlängen-Dispersion (Var/Ø): +0.734
- Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv: +0.727
- Begriffsaufnahme zw. Nachbarsätzen: +0.697
- Semikolons pro 1000: -0.626
- Anteil sehr langer Sätze (≥40 W.): +0.537
- Anteil mittellanger Sätze (14–26 W.): -0.439
- Lexikalische Variation (MATTR-100): -0.380
- Wörter pro Teilsatz: -0.033

## Funktionswort-Profil (HW07)

Verhältnis KI/Mensch der Raten; KI seltener: es 0.56, auch 0.67, um 0.70, durch 0.71, des 0.72, kann 0.74, wie 0.79, zur 0.80 · KI häufiger: als 1.53, sich 1.44, sie 1.31, ein 1.31, eine 1.20, aus 1.18, diese 1.17, an 1.16 · Poisson-Grenzfall bei 0 von 40 Wörtern.

## Diagnose: AUROC je Quelle und Texttyp (HW19)

Mensch-Abschnitte einer Quelle bzw. eines Typs gegen KI-Abschnitte, deren Basisdokument dazugehört. Modell und Score out-of-fold, Kennzahlen mit den finalen Werten. ⚠ = Spannweite > 0,15.

| Quelle: Kennzahl | haw-hamburg (n=149/53) | hs-mittweida (n=140/49) | opus-fh (n=331/116) | ssoar (n=357/134) | uni-hausarbeiten (n=139/52) | Spannweite |
|---|---|---|---|---|---|---|
| Modell P(menschlich) (OOF) | 0.996 | 0.999 | 0.995 | 0.995 | 0.998 | 0.005 |
| Score (OOF) | 0.789 | 0.819 | 0.793 | 0.773 | 0.749 | 0.070 |
| Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich) | 0.958 | 0.959 | 0.952 | 0.948 | 0.958 | 0.010 |
| Sätze-pro-Absatz-Variation (CV) | 0.915 | 0.894 | 0.871 | 0.820 | 0.836 | 0.094 |
| KI-Floskeln & -Muster pro 1000 | 0.195 | 0.121 | 0.139 | 0.155 | 0.185 | 0.074 |
| Absatzlängen-Variation (CV) | 0.889 | 0.864 | 0.854 | 0.807 | 0.812 | 0.082 |
| Begriffsaufnahme zw. Nachbarsätzen | 0.856 | 0.751 | 0.791 | 0.825 | 0.847 | 0.104 |
| Vielfalt der Inhaltswörter | 0.140 | 0.173 | 0.196 | 0.217 | 0.217 | 0.077 |
| Sätze, die einen Begriff des Vorsatzes aufnehmen | 0.819 | 0.723 | 0.779 | 0.834 | 0.866 | 0.143 |
| Satzlängen-Dispersion (Var/Ø) | 0.795 | 0.780 | 0.809 | 0.822 | 0.827 | 0.047 |
| Wörter pro Teilsatz | 0.814 | 0.649 | 0.792 | 0.847 | 0.834 | 0.198 ⚠ |
| Satzlänge Standardabweichung | 0.796 | 0.713 | 0.797 | 0.844 | 0.847 | 0.133 |
| Lexikalische Variation (MATTR-100) | 0.151 | 0.197 | 0.198 | 0.217 | 0.288 | 0.137 |
| Lexikalische Variation (MTLD) | 0.158 | 0.186 | 0.201 | 0.241 | 0.307 | 0.149 |
| Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv | 0.806 | 0.792 | 0.781 | 0.766 | 0.767 | 0.040 |
| Semikolons pro 1000 | 0.336 | 0.139 | 0.200 | 0.185 | 0.342 | 0.203 ⚠ |
| Abkürzungen pro 1000 (z. B., bzw., d. h. …) | 0.724 | 0.741 | 0.764 | 0.815 | 0.798 | 0.092 |
| Satzlängen-Variation (CV = SD/Ø) | 0.755 | 0.815 | 0.782 | 0.751 | 0.769 | 0.064 |
| Anteil mittellanger Sätze (14–26 W.) | 0.212 | 0.264 | 0.229 | 0.239 | 0.216 | 0.052 |
| Anteil sehr langer Sätze (≥40 W.) | 0.721 | 0.660 | 0.760 | 0.816 | 0.813 | 0.156 ⚠ |
| Sätze pro Absatz Ø | 0.299 | 0.212 | 0.217 | 0.259 | 0.245 | 0.086 |
| Lokale Begriffswiederholung (MATTR ÷ Zufallserwartung) | 0.206 | 0.234 | 0.238 | 0.294 | 0.208 | 0.088 |
| Anteil langer Sätze (≥30 W.) | 0.755 | 0.597 | 0.719 | 0.826 | 0.818 | 0.229 ⚠ |
| Wortlängen-Variation (CV) | 0.676 | 0.737 | 0.730 | 0.764 | 0.772 | 0.095 |
| Konnektoren pro 1000 (alle Stellungen) | 0.337 | 0.245 | 0.313 | 0.245 | 0.249 | 0.091 |
| Verhältnis Sätze mit 2 zu 1 Teilsatz | 0.270 | 0.237 | 0.229 | 0.314 | 0.338 | 0.109 |
| Anteil Ein-Satz-Absätze | 0.752 | 0.736 | 0.740 | 0.676 | 0.685 | 0.076 |
| Verhältnis Zwei- zu Einsilbern | 0.317 | 0.345 | 0.297 | 0.249 | 0.261 | 0.096 |
| Rhythmus: Autokorrelation log-Satzlängen (Lag 1, biaskorrigiert) | 0.752 | 0.694 | 0.685 | 0.732 | 0.687 | 0.067 |
| Anteil Sätze ohne Komma | 0.686 | 0.802 | 0.728 | 0.673 | 0.656 | 0.146 |
| Anteil kurzer Wörter (≤3 Buchst.) | 0.708 | 0.681 | 0.699 | 0.698 | 0.635 | 0.073 |
| Anführungen pro 1000 | 0.640 | 0.661 | 0.688 | 0.697 | 0.665 | 0.057 |
| Klammern pro 1000 | 0.620 | 0.629 | 0.618 | 0.745 | 0.708 | 0.127 |
| Anteil Sätze mit Nebensatz | 0.313 | 0.286 | 0.297 | 0.368 | 0.402 | 0.116 |
| ich/wir pro 1000 | 0.633 | 0.672 | 0.640 | 0.673 | 0.733 | 0.100 |
| Absatzlänge Ø (Wörter) | 0.352 | 0.223 | 0.279 | 0.401 | 0.348 | 0.178 ⚠ |
| „…, sondern“ pro 1000 | 0.288 | 0.422 | 0.351 | 0.326 | 0.366 | 0.134 |
| Satzlängen-Schiefe | 0.667 | 0.634 | 0.669 | 0.638 | 0.661 | 0.036 |

| Texttyp: Kennzahl | Bachelorarbeit (n=482/171) | Diplomarbeit (n=103/38) | Masterarbeit (n=133/47) | Working Paper (n=278/105) | übrige (n=120/43) | Spannweite |
|---|---|---|---|---|---|---|
| Modell P(menschlich) (OOF) | 0.996 | 0.994 | 0.999 | 0.993 | 1.000 | 0.007 |
| Score (OOF) | 0.819 | 0.770 | 0.857 | 0.712 | 0.748 | 0.145 |
| Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich) | 0.946 | 0.938 | 0.962 | 0.959 | 0.974 | 0.036 |
| Sätze-pro-Absatz-Variation (CV) | 0.902 | 0.866 | 0.846 | 0.790 | 0.854 | 0.112 |
| KI-Floskeln & -Muster pro 1000 | 0.150 | 0.187 | 0.116 | 0.179 | 0.143 | 0.071 |
| Absatzlängen-Variation (CV) | 0.882 | 0.868 | 0.838 | 0.758 | 0.831 | 0.124 |
| Begriffsaufnahme zw. Nachbarsätzen | 0.785 | 0.821 | 0.879 | 0.799 | 0.870 | 0.094 |
| Vielfalt der Inhaltswörter | 0.177 | 0.244 | 0.121 | 0.252 | 0.164 | 0.131 |
| Sätze, die einen Begriff des Vorsatzes aufnehmen | 0.746 | 0.839 | 0.874 | 0.820 | 0.894 | 0.147 |
| Satzlängen-Dispersion (Var/Ø) | 0.769 | 0.805 | 0.824 | 0.844 | 0.876 | 0.107 |
| Wörter pro Teilsatz | 0.747 | 0.819 | 0.856 | 0.839 | 0.869 | 0.122 |
| Satzlänge Standardabweichung | 0.741 | 0.814 | 0.831 | 0.870 | 0.891 | 0.150 |
| Lexikalische Variation (MATTR-100) | 0.183 | 0.292 | 0.162 | 0.253 | 0.183 | 0.130 |
| Lexikalische Variation (MTLD) | 0.191 | 0.299 | 0.159 | 0.284 | 0.177 | 0.140 |
| Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv | 0.799 | 0.754 | 0.767 | 0.733 | 0.843 | 0.110 |
| Semikolons pro 1000 | 0.214 | 0.204 | 0.218 | 0.247 | 0.227 | 0.043 |
| Abkürzungen pro 1000 (z. B., bzw., d. h. …) | 0.730 | 0.747 | 0.791 | 0.849 | 0.811 | 0.120 |
| Satzlängen-Variation (CV = SD/Ø) | 0.767 | 0.754 | 0.761 | 0.767 | 0.809 | 0.056 |
| Anteil mittellanger Sätze (14–26 W.) | 0.237 | 0.263 | 0.230 | 0.227 | 0.206 | 0.057 |
| Anteil sehr langer Sätze (≥40 W.) | 0.694 | 0.756 | 0.805 | 0.838 | 0.855 | 0.161 ⚠ |
| Sätze pro Absatz Ø | 0.246 | 0.237 | 0.244 | 0.254 | 0.237 | 0.017 |
| Lokale Begriffswiederholung (MATTR ÷ Zufallserwartung) | 0.234 | 0.357 | 0.191 | 0.263 | 0.219 | 0.166 ⚠ |
| Anteil langer Sätze (≥30 W.) | 0.669 | 0.786 | 0.796 | 0.852 | 0.825 | 0.183 ⚠ |
| Wortlängen-Variation (CV) | 0.719 | 0.726 | 0.741 | 0.772 | 0.733 | 0.053 |
| Konnektoren pro 1000 (alle Stellungen) | 0.306 | 0.247 | 0.287 | 0.250 | 0.237 | 0.068 |
| Verhältnis Sätze mit 2 zu 1 Teilsatz | 0.232 | 0.318 | 0.308 | 0.336 | 0.253 | 0.104 |
| Anteil Ein-Satz-Absätze | 0.723 | 0.780 | 0.707 | 0.670 | 0.725 | 0.110 |
| Verhältnis Zwei- zu Einsilbern | 0.308 | 0.305 | 0.327 | 0.244 | 0.217 | 0.111 |
| Rhythmus: Autokorrelation log-Satzlängen (Lag 1, biaskorrigiert) | 0.708 | 0.790 | 0.676 | 0.715 | 0.691 | 0.114 |
| Anteil Sätze ohne Komma | 0.761 | 0.663 | 0.650 | 0.643 | 0.716 | 0.118 |
| Anteil kurzer Wörter (≤3 Buchst.) | 0.710 | 0.617 | 0.657 | 0.709 | 0.663 | 0.093 |
| Anführungen pro 1000 | 0.670 | 0.706 | 0.599 | 0.713 | 0.680 | 0.114 |
| Klammern pro 1000 | 0.622 | 0.742 | 0.663 | 0.734 | 0.696 | 0.120 |
| Anteil Sätze mit Nebensatz | 0.283 | 0.397 | 0.359 | 0.387 | 0.332 | 0.113 |
| ich/wir pro 1000 | 0.647 | 0.679 | 0.702 | 0.692 | 0.620 | 0.082 |
| Absatzlänge Ø (Wörter) | 0.281 | 0.350 | 0.379 | 0.384 | 0.364 | 0.103 |
| „…, sondern“ pro 1000 | 0.340 | 0.344 | 0.310 | 0.377 | 0.315 | 0.068 |
| Satzlängen-Schiefe | 0.649 | 0.624 | 0.661 | 0.653 | 0.666 | 0.042 |

## Diagnose: Korrelation mit dem Erscheinungsjahr (menschliche Abschnitte, HW19)

1116 Abschnitte mit Jahr (1997–2021). Keine Kennzahl mit |r| oder |ρ| > 0,2.

| Kennzahl | Pearson r | Spearman ρ |
|---|---|---|
| Anführungen pro 1000 | -0.173 | -0.199 |
| Sätze pro Absatz Ø | +0.104 | +0.092 |
| Funktionswort-Profil (LLR pro 1000 W., > 0 = menschlich) | +0.094 | +0.076 |
| Wortlängen-Variation (CV) | -0.089 | -0.075 |
| Lexikalische Variation (MATTR-100) | -0.089 | -0.080 |
| Satzlänge Standardabweichung | -0.087 | -0.082 |
| Satzlängen-Dispersion (Var/Ø) | -0.084 | -0.091 |
| Lexikalische Variation (MTLD) | -0.083 | -0.077 |
| Abkürzungen pro 1000 (z. B., bzw., d. h. …) | -0.082 | -0.091 |
| Absatzlänge Ø (Wörter) | +0.082 | +0.068 |
| Satzlängen-Variation (CV = SD/Ø) | -0.075 | -0.093 |
| Verhältnis Zwei- zu Einsilbern | +0.073 | +0.070 |
| Konnektoren pro 1000 (alle Stellungen) | +0.073 | +0.054 |
| KI-Floskeln & -Muster pro 1000 | +0.065 | +0.052 |
| Anteil langer Sätze (≥30 W.) | -0.063 | -0.053 |
| Anteil mittellanger Sätze (14–26 W.) | +0.057 | +0.046 |
| Anteil sehr langer Sätze (≥40 W.) | -0.056 | -0.059 |
| „…, sondern“ pro 1000 | +0.054 | +0.041 |
| Teilsätze pro Satz | -0.052 | -0.043 |
| Satzlänge Ø (Token inkl. Zahlen) | -0.046 | -0.048 |
| Anteil Ein-Satz-Absätze | -0.037 | -0.036 |
| Anteil Sätze mit Nebensatz | -0.035 | -0.027 |
| Begriffsaufnahme zw. Nachbarsätzen | +0.032 | +0.045 |
| Verhältnis Sätze mit 2 zu 1 Teilsatz | -0.031 | -0.020 |
| Satzlängen-Schiefe | -0.030 | -0.019 |
| ich/wir pro 1000 | -0.027 | -0.116 |
| Satzklammer: Wörter zwischen Hilfsverb und Partizip/Infinitiv | +0.026 | +0.012 |
| Anteil kurzer Wörter (≤3 Buchst.) | +0.025 | +0.008 |
| Rhythmus: Autokorrelation log-Satzlängen (Lag 1, biaskorrigiert) | +0.025 | +0.018 |
| Vielfalt der Inhaltswörter | -0.016 | -0.017 |
| Anteil Sätze ohne Komma | -0.015 | -0.018 |
| Sätze-pro-Absatz-Variation (CV) | +0.013 | +0.017 |
| Absatzlängen-Variation (CV) | +0.011 | +0.022 |
| Semikolons pro 1000 | -0.008 | -0.060 |
| Wörter pro Teilsatz | -0.007 | -0.011 |
| Sätze, die einen Begriff des Vorsatzes aufnehmen | +0.006 | +0.022 |
| Lokale Begriffswiederholung (MATTR ÷ Zufallserwartung) | -0.005 | -0.015 |
| Klammern pro 1000 | +0.002 | -0.026 |

## KI-Muster (Häufigkeit pro 1000 Token, alle Abschnitte)

| Muster | Mensch | KI | Verhältnis | Gewicht |
|---|---|---|---|---|
| „ermöglicht es …, zu …“ | 0.026 | 0.161 | 3.95 | 1.98 |
| „Dies zeigt/verdeutlicht/unterstreicht, dass …“ | 0.012 | 0.093 | 3.49 | 1.8 |
| Scheinbare Gegenposition: „Naheliegend wäre …“, „bei näherer Betrachtung …“ | 0.004 | 0.062 | 3.34 | 1.74 |
| „Dem lässt sich entgegenhalten / einwenden, dass …“ | 0.006 | 0.065 | 3.32 | 1.73 |
| „Insgesamt zeigt sich / wird deutlich“ | 0.004 | 0.056 | 3.09 | 1.63 |
| „nicht zwangsläufig / nicht zwingend“ | 0.021 | 0.105 | 3.03 | 1.6 |
| Korrektur-Konstruktion „nicht X, sondern Y“ | 0.256 | 0.789 | 2.93 | 1.55 |
| „maßgeblich“ | 0.084 | 0.282 | 2.89 | 1.53 |
| „keineswegs“ (Widerspruch gegen eine unterstellte Annahme) | 0.040 | 0.133 | 2.53 | 1.34 |
| „Darüber hinaus“ | 0.279 | 0.718 | 2.47 | 1.31 |
| „… greift zu kurz“ (Gegenposition aufbauen und abweisen) | 0.002 | 0.034 | 2.43 | 1.28 |
| „kommt eine zentrale Rolle/Bedeutung zu“ | 0.008 | 0.040 | 2.16 | 1.11 |
| „In diesem Zusammenhang / Vor diesem Hintergrund“ | 0.204 | 0.464 | 2.16 | 1.11 |
| „verdeutlicht“ | 0.136 | 0.310 | 2.11 | 1.08 |
| „prägt/gestaltet maßgeblich“ | 0.007 | 0.028 | 1.79 | 0.84 |
| „Schlüsselfaktor/-rolle/-element“ | 0.019 | 0.050 | 1.78 | 0.83 |
| „von entscheidender/zentraler Bedeutung“ | 0.064 | 0.127 | 1.75 | 0.81 |
| „sowohl … als auch“ | 0.453 | 0.805 | 1.74 | 0.8 |
| „unterstreicht“ (übertragen) | 0.029 | 0.065 | 1.73 | 0.79 |
| „im Spannungsfeld / Balance / Gleichgewicht finden“ | 0.039 | 0.071 | 1.54 | 0.62 |
| „nicht nur/allein …, sondern (auch)“ | 0.444 | 0.669 | 1.48 | 0.57 |
| „im Kern / Kernaspekt / zentraler Aspekt“ | 0.054 | 0.090 | 1.48 | 0.57 |
| „gewinnt zunehmend an Bedeutung“ | 0.003 | 0.012 | 1.39 | 0.47 |
| „trägt maßgeblich/entscheidend dazu bei“ | 0.009 | 0.019 | 1.33 | 0.41 |
| „spielt eine zentrale/entscheidende Rolle“ | 0.072 | 0.093 | 1.23 | 0.0 |
| „wertvolle Erkenntnisse / wertvoller Beitrag“ | 0.004 | 0.009 | 1.20 | 0.0 |
| „sicherstellen / gewährleisten“ | 0.165 | 0.192 | 1.14 | 0.0 |
| „nicht zuletzt“ | 0.069 | 0.077 | 1.10 | 0.0 |
| „Chancen und Herausforderungen“ | 0.010 | 0.012 | 1.08 | 0.0 |
| „Zusammenfassend lässt sich …“ | 0.028 | 0.031 | 1.06 | 0.0 |
| „rückt in den Fokus / steht im Mittelpunkt“ | 0.035 | 0.037 | 1.04 | 0.0 |
| „nachhaltig“ (übertragen: nachhaltig stärken/prägen) | 0.004 | 0.003 | 0.94 | 0.0 |
| „mehr als nur / nicht einfach nur“ | 0.009 | 0.006 | 0.90 | 0.0 |
| „zunehmend / immer mehr“ | 0.633 | 0.539 | 0.86 | 0.0 |
| „eine weitere Dimension/Ebene“ | 0.004 | 0.000 | 0.82 | 0.0 |
| Satzinterne Pointe mit Doppelpunkt („Das Ergebnis: …“) | 0.004 | 0.000 | 0.82 | 0.0 |
| KI-Modeadjektive (ganzheitlich, vielschichtig, facettenreich …) | 0.202 | 0.158 | 0.80 | 0.0 |
| „Es ist wichtig/entscheidend, …“ | 0.007 | 0.000 | 0.75 | 0.0 |
| „einerseits … andererseits / auf der einen Seite“ | 0.215 | 0.149 | 0.72 | 0.0 |
| „Hierbei / Hierdurch“ | 0.672 | 0.436 | 0.66 | 0.0 |
| „gilt es / es gilt, …“ | 0.069 | 0.037 | 0.65 | 0.0 |
| „letztlich/letztendlich“ | 0.166 | 0.099 | 0.64 | 0.0 |
| „eine Vielzahl von/an“ | 0.084 | 0.031 | 0.49 | 0.0 |
| „Mit anderen Worten / Kurz gesagt“ | 0.028 | 0.000 | 0.42 | 0.0 |
| „in der heutigen Zeit/Welt“ | 0.042 | 0.000 | 0.32 | 0.0 |
| „Des Weiteren“ | 0.170 | 0.000 | 0.11 | 0.0 |

## Wörter/Phrasen, die KI überdurchschnittlich nutzt (Top 60)

etwa (1.97 vs 0.37), zugleich (0.96 vs 0.14), lässt (1.77 vs 0.55), lässt sich (1.38 vs 0.35), als (10.10 vs 6.62), sich (12.74 vs 8.86), diese weise (0.51 vs 0.05), auf diese weise (0.51 vs 0.05), hinzu (0.57 vs 0.09), damit (2.51 vs 1.27), häufig (1.09 vs 0.39), lassen sich (0.83 vs 0.25), auf diese (0.60 vs 0.13), sodass (0.58 vs 0.13), während (1.48 vs 0.65), kaum (0.86 vs 0.27), ergibt sich (0.50 vs 0.10), hinzu kommt (0.33 vs 0.04), ergibt (0.57 vs 0.14), sondern (1.90 vs 0.98), lassen (1.26 vs 0.55), jedoch (2.31 vs 1.29), dagegen (0.54 vs 0.14), selbst (1.52 vs 0.76), weitgehend (0.46 vs 0.11), unmittelbar (0.36 vs 0.07), ein (8.00 vs 6.12), bemerkenswert (0.20 vs 0.01), nutzerinnen und (0.16 vs 0.00), die (44.94 vs 40.81), hinaus (0.86 vs 0.36), über (3.86 vs 2.67), darüber hinaus (0.72 vs 0.28), zudem (1.22 vs 0.61), überwiegend (0.39 vs 0.10), erscheint (0.45 vs 0.13), bemerkenswert ist (0.15 vs 0.00), daher (1.16 vs 0.58), lediglich (0.69 vs 0.28), weise (0.73 vs 0.30), mitarbeitenden (0.22 vs 0.03), in der regel (0.47 vs 0.15), der regel (0.47 vs 0.15), umfasst (0.40 vs 0.11), und nutzer (0.13 vs 0.00), nutzerinnen und nutzer (0.13 vs 0.00), während die (0.33 vs 0.08), ist dabei (0.31 vs 0.07), darüber (0.96 vs 0.46), sondern als (0.22 vs 0.03), eigene (0.80 vs 0.35), befund (0.20 vs 0.03), regel (0.50 vs 0.17), gezielt (0.30 vs 0.07), maßgeblich (0.29 vs 0.06), nutzerinnen (0.16 vs 0.01), bislang (0.41 vs 0.13), folgenden werden (0.20 vs 0.03), im folgenden werden (0.20 vs 0.03), zeigt sich (0.51 vs 0.18)

## Wörter/Phrasen, die Menschen überdurchschnittlich nutzen (Top 60)

es (5.78 vs 3.25), z (0.93 vs 0.03), z b (0.79 vs 0.00), ich (1.02 vs 0.15), kapitel (1.10 vs 0.22), immer (1.02 vs 0.22), wir (0.67 vs 0.03), auch (6.63 vs 4.41), man (1.24 vs 0.35), arbeit (2.15 vs 0.96), b (0.99 vs 0.22), so (2.23 vs 1.09), des (8.00 vs 5.75), aber (1.66 vs 0.71), sehr (1.01 vs 0.30), schon (0.54 vs 0.05), haben (1.86 vs 0.92), gibt (0.94 vs 0.32), bzw (1.01 vs 0.39), zu (12.90 vs 10.53), der (38.21 vs 33.98), in (19.07 vs 16.16), innen (0.58 vs 0.14), von (12.23 vs 9.98), gibt es (0.45 vs 0.07), welche (1.35 vs 0.68), mitarbeiter (0.53 vs 0.13), zum beispiel (0.28 vs 0.00), aber auch (0.48 vs 0.10), dieser arbeit (0.50 vs 0.12), doch (0.46 vs 0.10), durch (3.87 vs 2.74), hierbei (0.43 vs 0.09), und somit (0.27 vs 0.01), um (3.38 vs 2.36), werden (9.14 vs 7.41), letzten (0.33 vs 0.05), aufgrund (0.60 vs 0.21), hat (1.76 vs 1.06), bezüglich (0.22 vs 0.00), in den (2.30 vs 1.51), d h (0.21 vs 0.00), in bezug (0.25 vs 0.02), außerdem (0.38 vs 0.10), d (0.31 vs 0.06), uns (0.21 vs 0.01), durch die (1.09 vs 0.60), in bezug auf (0.23 vs 0.02), bezug auf (0.28 vs 0.05), welches (0.30 vs 0.06), ist es (0.70 vs 0.32), deutschland (0.76 vs 0.36), bisher (0.27 vs 0.05), noch (1.54 vs 0.96), auswirkungen (0.26 vs 0.04), des weiteren (0.17 vs 0.00), mit hilfe (0.17 vs 0.00), siehe (0.25 vs 0.04), viel (0.30 vs 0.07), sein (1.34 vs 0.81)

Laufzeit: 196 s
