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
korpus/ki/<modell>/       ← themengleiche KI-Texte (meta: basis_id = menschliches Dokument)
        │
        └─ kalibriere.py  → ergebnisse/features.csv, ergebnisse/bericht.md, ergebnisse/wortlisten.json,
                            text-analyse/data/baselines.json, Gewichte in text-analyse/data/ki_muster.json
                └─ referenzen.py → references/zielwerte.md, ki-muster.md, kennzahlen.md
```

`kalibriere.py` arbeitet in diesen Schritten:

1. **Zerlegen und kürzen.** `zerlege()` bildet Abschnitte von etwa 900 Wörtern (höchstens 3 pro menschlichem Dokument, gleichmäßig verteilt; 1 pro KI-Text, bei mehreren der mittlere). `kuerze()` bringt jeden Abschnitt, menschlich wie KI, an einer Satzgrenze auf **800 bereinigte Wörter** (gezählt wie in `analyse.py`: nur Prosa-Absätze, ohne Quellenverweise, Überschriften, Listen). Abschnitte unter 760 Wörtern werden verworfen. Der letzte Absatz ist meist angeschnitten und zählt deshalb nicht in die Absatz-Kennzahlen (`analysiere_text(..., letzter_absatz_gekuerzt=True)`).
2. **Messen.** Alle Kennzahlen werden einmal pro Abschnitt berechnet (`features.csv`); Funktionswort-Zählungen und Muster-Treffer werden mitgespeichert, damit alles Weitere nur noch auf dieser Tabelle rechnet.
3. **Kennzahlen bewerten** (auf einer Trainingsmenge, siehe 6):
   - Perzentile P10–P90 **dokumentgewichtet** (Gewicht 1/Abschnitte des Dokuments), damit lange Arbeiten nicht dreifach zählen.
   - Trennschärfe = AUROC auf allen Abschnitten. Eine Kennzahl kommt nur in Frage, wenn die AUROC ≥ 0,65 bzw. ≤ 0,35 ist.
   - **Paar-Gate:** Zu jedem KI-Text gehört der mittlere Abschnitt seines menschlichen Basisdokuments (genau der Auszug, aus dem `auszuege.py` die Gliederung erzeugt hat). Auf diesen themengleichen Paaren muss die AUROC in derselben Richtung ebenfalls ≥ 0,65 bzw. ≤ 0,35 erreichen, und die Bootstrap-95-%-Intervalle (300 Ziehungen mit Zurücklegen über die Paare, also nach Dokument, Seed 1) von Paar-AUROC und Vorzeichen-Anteil (Mensch > KI) dürfen 0,5 nicht enthalten. So bekommen Kennzahlen, die eher Thema oder Quelle messen, kein Gewicht.
   - **Messunsicherheit `se_typ`:** gepoolte SD einer Kennzahl zwischen Abschnitten desselben menschlichen Dokuments. `bewerte()` markiert damit Werte nahe an P25/P75 als `unsicher`.
4. **Cluster.** Bewertete Kennzahlen, die innerhalb der menschlichen Abschnitte zu |r| ≥ 0,7 korrelieren, werden gierig nach Trennschärfe gebündelt. Gewicht je Mitglied = Trennschärfe · max/Σ im Cluster: Ein Cluster (z. B. Satzlängen-SD, -CV, -Dispersion) wiegt im Score höchstens so viel wie sein stärkstes Mitglied. `cluster` steht je Kennzahl in `baselines.json`, die Liste im Bericht.
5. **Funktionswort-Profil und KI-Muster.** Für die 40 häufigsten Funktionswörter (`analyse.FW_WOERTER`) werden Raten je Klasse ((Zählung + 0,5)/Wörter) und ein Größenparameter der negativen Binomialverteilung je Wort (Momentenmethode, s = Σμ²/Σ((k−μ)² − μ), sonst Poisson) geschätzt und als `fw_profil` gespeichert. Daraus rechnet `analyse.fw_llr` die Kennzahl `fw_profil_llr_pro_1000` (Log-Likelihood-Quotient pro 1000 Wörter, > 0 = menschlich). Sie geht ins Modell und wird angezeigt, aber nicht in den Score (erst nach einem Goodhart-Test an Schleifenausgaben). Die KI-Muster bekommen das Gewicht log2(KI-Rate/Mensch-Rate), gedeckelt auf 0–3. Gezählt wird dafür mit Gewicht 1 (bei Überlappung gewinnt der längste Treffer); `ki_muster_pro_1000` selbst wird pro Fold mit den geschätzten Gewichten neu aufgelöst (`analyse.muster_aufloesen`: höchstes Gewicht, dann längster Treffer; Gewicht 0 zählt nicht), also genau wie zur Laufzeit in `analyse.py`.
6. **Modell und Evaluation.** Statt eines einzelnen 75/25-Splits: **wiederholte gruppierte Kreuzvalidierung (5 × 5 Folds, gruppiert nach Thema** = `basis_id` bzw. `doc_id`, d. h. ein KI-Text und sein Basisdokument liegen immer im selben Fold). In jedem Fold werden Muster-Gewichte, Funktionswort-Profil, Perzentile, Gate, Cluster, Merkmalsauswahl und Modell nur aus den Train-Themen geschätzt und auf den zurückgehaltenen bewertet (keine Leckage). Das Modell ist eine L2-regularisierte logistische Regression (Klassen balanciert, Newton-Verfahren) auf den trennschärfsten Kennzahlen mit bestandenem Gate, die untereinander |r| < 0,8 haben. Merkmalszahl k und Strafe λ wählt die Kreuzvalidierung (Ein-Standardfehler-Regel auf dem balancierten Log-Loss). Das finale Modell wird mit dieser Konfiguration auf allen Daten geschätzt. Der Bericht nennt AUROC und Genauigkeit von Modell und Score als Mittelwert ± SD über die 25 Folds.
7. **Schwellen.** `score_schwelle` = Mitte zwischen den Out-of-fold-Score-Medianen von Mensch und KI; `ziel_p_mensch` = P25 der menschlichen Out-of-fold-Wahrscheinlichkeiten (mindestens 0,5). Beide stehen unter `textsorten.hochschule` und dienen dem Coach als Abbruchkriterium.
8. **Diagnosen.** AUROC je Quelle und je Texttyp (KI-Abschnitte zählen zur Quelle bzw. zum Typ ihres Basisdokuments) mit Vermerk bei einer Spannweite über 0,15; Pearson- und Spearman-Korrelation der Kennzahlen mit dem Erscheinungsjahr (menschliche Texte); Paarprüfung über Inhaltswort-Überlappung.
9. **Wortlisten** per log-odds-Verhältnis mit informativem Dirichlet-Prior (Monroe, Colaresi & Quinn 2008), Prior-Stärke = Korpusgröße, nur N-Gramme aus mindestens 4 Dokumenten.

## Designentscheidungen

- **Nur Texte bis 2021.** Alles danach könnte bereits KI-beeinflusst sein.
- **Register passend zum Einsatz:** Bachelor-/Masterarbeiten, Seminar- und Hausarbeiten, Fachartikel und Gutachten, vor allem aus Wirtschaft, Sozialwissenschaften, Psychologie, Medien und Bildung.
- **Themengleiches Design:** Jeder KI-Text entsteht aus der inhaltlichen Gliederung eines menschlichen Auszugs. Unterschiede in den Kennzahlen sind dadurch Stil- und keine Themenunterschiede. Der schreibende Agent sieht den menschlichen Wortlaut nie.
- **Feste Abschnittslänge:** Längenabhängige Kennzahlen (Schiefe, Satzanfangs-Anteile, Wortschatzmaße) messen sonst teilweise nur die Länge; vor der Kürzung trennte die Wortzahl allein Mensch und KI mit AUROC ≈ 0,70. In Nutzertexten misst `analyse.py` `satzlaenge_schiefe` und `mattr_klumpung_100` deshalb als Median über Fenster à `analyse.ABSCHNITT_L` = 800 Wörter (für Abschnitte ≤ 800 Wörter identisch mit der Messung am Stück). Einen Blockmodus für alle Kennzahlen gibt es noch nicht; ab 1200 Wörtern warnt `analyse.py`, weil vor allem die Absatz-CVs bei langen Texten höher liegen. Wer mit `--laenge` ≠ 800 kalibriert, muss `ABSCHNITT_L` mitändern.
- **Gleiche Vorverarbeitung:** Überschriften, Listen, Quellenverweise in Klammern, Fußnotenmarker und Literaturverzeichnis werden in beiden Korpora identisch ausgeblendet.
- **Nicht bewertet** werden Längen- und Formatartefakte (Absatzzahl, längster Satz, Markdown, Listen, Überschriften, Zitate), Duplikate (Satzlängen-Median/-P10/-P90, MATTR-50, `rhythmus_sprung_rel` als Duplikat des CV, `menzerath_korrelation`, die vor allem Satzlängen-Gleichförmigkeit misst) und `anteil_funktionswoerter` (durch das Funktionswort-Profil ersetzt). Neue Kandidaten (`rhythmus_r1_log`, `nominalketten_pro_100`, `silben_q21`, `mattr_klumpung_100`) werden nur bewertet, wenn sie das Paar-Gate bestehen.

## Grenzen

- Der KI-Korpus stammt von einem Modell (Claude). Andere Modelle haben eigene Vorlieben; die meisten strukturellen Signale (Satzlängen-Gleichförmigkeit, Synonym-Vielfalt, Konnektoren) gelten erfahrungsgemäß modellübergreifend, die Floskel-Gewichte und das Funktionswort-Profil weniger. Vor einer stärkeren Gewichtung sollte ein zweites Modell als Test außerhalb der Verteilung dazukommen.
- **KI-Entwürfe wurden oft nachträglich auf Ziellänge verlängert.** Viele Texte im KI-Korpus sind zunächst zu kurz ausgefallen und dann ergänzt worden. Solche Ergänzungen können Absatzstruktur, Wiederholungen und Schlussformeln anders prägen als ein in einem Zug geschriebener Text; Kennzahlen, die darauf reagieren, messen dann teilweise das Verlängern und nicht das Schreiben. Die Kürzung auf 800 Wörter gleicht nur die Länge an, nicht diese Spuren.
- Strukturasymmetrie: Die KI-Texte sind vollständige Kurztexte mit Einleitung und Schluss, die menschlichen Abschnitte Auszüge aus längeren Arbeiten. Formelhafte Einleitungs- und Fazitsätze sind deshalb vor allem auf der KI-Seite vertreten.
- PDF-Extraktion ist nicht fehlerfrei. Absatzgrenzen menschlicher Texte sind weniger zuverlässig als Satzgrenzen; die starken Absatz-Kennzahlen (Absatzlängen-CV, Sätze-pro-Absatz-CV) hängen an der Absatzreparatur in `extract_text.py` und sind mit Vorsicht zu lesen.
- Die Kreuzvalidierung wählt k und λ und bewertet zugleich (nicht verschachtelt); weil nur zwei Hyperparameter gewählt werden, ist die Überschätzung klein. Die Paarzuordnung folgt der Regel aus `auszuege.py` (mittlerer Abschnitt); ändert sich die Extraktion eines Basisdokuments, kann ein Paar verrutschen (Paarprüfung im Bericht).
- Ein Goodhart-Test (Schleifenausgaben als dritte Klasse) fehlt noch.
- Rohtexte der menschlichen Quellen werden nicht versioniert (Urheberrecht). `meta.jsonl` enthält die URLs; `extract_text.py` reproduziert die Texte.

## Neu kalibrieren

```bash
python3 kalibrierung/scripts/kalibriere.py      # benötigt korpus/mensch und korpus/ki; ca. 3–5 Minuten
python3 kalibrierung/scripts/referenzen.py      # Referenzdateien der Skills neu erzeugen
python3 -m unittest discover -s tests
```

Probelauf, ohne die Plugin-Daten zu überschreiben (`kalibriere.py` schreibt `baselines.json`, `ki_muster.json` und eine kompakte `wortlisten.json` neben `baselines.json`; liegt diese im `--aus`-Ordner, heißt die kompakte Fassung `wortlisten_kompakt.json`):

```bash
mkdir -p /tmp/kal && cp plugins/humanwriting-de/skills/text-analyse/data/ki_muster.json /tmp/kal/
python3 kalibrierung/scripts/kalibriere.py --aus /tmp/kal --baselines /tmp/kal/baselines.json --muster /tmp/kal/ki_muster.json
```

Weitere Optionen: `--laenge` (Abschnittslänge, Standard 800), `--max-abschnitte` (Standard 3), `--cv-wiederholungen`/`--cv-folds` (Standard 5/5), `--bootstrap` (Ziehungen für das Paar-Gate, Standard 300).
