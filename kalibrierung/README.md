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
                                   (Kennzahlen mit nur_modell erscheinen in zielwerte.md nur als „Tendenz“, ohne Zielbereich)
```

`kalibriere.py` arbeitet in diesen Schritten:

1. **Zerlegen und kürzen.** `zerlege()` bildet Abschnitte von etwa 900 Wörtern (höchstens 3 pro menschlichem Dokument, gleichmäßig verteilt; 1 pro KI-Text, bei mehreren der mittlere). `kuerze()` bringt jeden Abschnitt, menschlich wie KI, an einer Satzgrenze auf **800 bereinigte Wörter** (gezählt wie in `analyse.py`: nur Prosa-Absätze, ohne Quellenverweise, Überschriften, Listen). Abschnitte unter 760 Wörtern werden verworfen. Der letzte Absatz ist meist angeschnitten und zählt deshalb nicht in die Absatz-Kennzahlen (`analysiere_text(..., letzter_absatz_gekuerzt=True)`).
2. **Messen.** Alle Kennzahlen werden einmal pro Abschnitt berechnet (`features.csv`); Funktionswort-Zählungen und Muster-Treffer werden mitgespeichert, damit alles Weitere nur noch auf dieser Tabelle rechnet.
3. **Kennzahlen bewerten** (auf einer Trainingsmenge, siehe 6):
   - Perzentile P10–P90 **dokumentgewichtet** (Gewicht 1/Abschnitte des Dokuments), damit lange Arbeiten nicht dreifach zählen.
   - Trennschärfe = AUROC auf allen Abschnitten. Eine Kennzahl kommt nur in Frage, wenn die AUROC ≥ 0,65 bzw. ≤ 0,35 ist.
   - **Paar-Gate:** Zu jedem KI-Text gehört der mittlere Abschnitt seines menschlichen Basisdokuments (genau der Auszug, aus dem `auszuege.py` die Gliederung erzeugt hat). Auf diesen themengleichen Paaren muss die AUROC in derselben Richtung ebenfalls ≥ 0,65 bzw. ≤ 0,35 erreichen, und die Bootstrap-95-%-Intervalle (300 Ziehungen mit Zurücklegen über die Paare, also nach Dokument, Seed 1) von Paar-AUROC und Vorzeichen-Anteil (Mensch > KI) dürfen 0,5 nicht enthalten. So bekommen Kennzahlen, die eher Thema oder Quelle messen, kein Gewicht.
   - **Messunsicherheit `se_typ`:** gepoolte SD einer Kennzahl zwischen Abschnitten desselben menschlichen Dokuments. `bewerte()` markiert damit Werte nahe an P25/P75 als `unsicher`: Abstand zur nächsten Grenze < `UNSICHER_FAKTOR` (0,5) · se_typ · √(800 / max(800, Wörter)); bei langen Texten wird die Zone also schmaler. Status und Score ändert das nicht.
4. **Cluster.** Bewertete Kennzahlen, die innerhalb der menschlichen Abschnitte zu |r| ≥ 0,7 korrelieren, werden gierig nach Trennschärfe gebündelt. Gewicht je Mitglied = Trennschärfe · max/Σ im Cluster: Ein Cluster (z. B. Satzlängen-SD, -CV, -Dispersion) wiegt im Score höchstens so viel wie sein stärkstes Mitglied. `cluster` steht je Kennzahl in `baselines.json`, die Liste im Bericht.
5. **Funktionswort-Profil und KI-Muster.** Für die 40 häufigsten Funktionswörter (`analyse.FW_WOERTER`) werden Raten je Klasse ((Zählung + 0,5)/Wörter) und ein Größenparameter der negativen Binomialverteilung je Wort (Momentenmethode, s = Σμ²/Σ((k−μ)² − μ), sonst Poisson) geschätzt und als `fw_profil` gespeichert. Daraus rechnet `analyse.fw_llr` die Kennzahl `fw_profil_llr_pro_1000` (Log-Likelihood-Quotient pro 1000 Wörter, > 0 = menschlich). Sie geht ins Modell und wird angezeigt, aber nicht in den Score (erst nach einem Goodhart-Test an Schleifenausgaben). Die KI-Muster bekommen das Gewicht log2(KI-Rate/Mensch-Rate), gedeckelt auf 0–3. Gezählt wird dafür mit Gewicht 1 (bei Überlappung gewinnt der längste Treffer); `ki_muster_pro_1000` selbst wird pro Fold mit den geschätzten Gewichten neu aufgelöst (`analyse.muster_aufloesen`: höchstes Gewicht, dann längster Treffer; Gewicht 0 zählt nicht), also genau wie zur Laufzeit in `analyse.py`.
6. **Modell und Evaluation.** Statt eines einzelnen 75/25-Splits: **wiederholte gruppierte Kreuzvalidierung (5 × 5 Folds, gruppiert nach Thema** = `basis_id` bzw. `doc_id`, d. h. ein KI-Text und sein Basisdokument liegen immer im selben Fold). In jedem Fold werden Muster-Gewichte, Funktionswort-Profil, Perzentile, Gate, Cluster, Merkmalsauswahl und Modell nur aus den Train-Themen geschätzt und auf den zurückgehaltenen bewertet (keine Leckage). Das Modell ist eine L2-regularisierte logistische Regression (Klassen balanciert, Newton-Verfahren) auf den trennschärfsten Kennzahlen mit bestandenem Gate, die untereinander |r| < 0,8 haben.
   - **Einseitige Kappung (v7):** Vor der Standardisierung wird jedes Modellmerkmal auf der der KI abgewandten Seite höchstens bis zum menschlichen P90 (KI-Median niedriger) bzw. P10 (KI-Median höher) gesetzt (`analyse.kappe_von`/`analyse.gekappt`); die KI-Seite bleibt offen. Die Grenzen kommen in jedem Fold aus den dokumentgewichteten Perzentilen der Train-Themen, Mittel und SD werden aus den gekappten Werten geschätzt. Die finalen Grenzen stehen unter `textsorten.hochschule.modell.kappen` = {merkmal: {"seite": "oben"|"unten", "wert": x}}; `bewerte()` wendet sie identisch an. Grund: Das monotone Logit-Modell wertete Werte jenseits des menschlichen Bands auf der Gegenseite („menschlicher als 90 % der Menschen“) als „noch menschlicher“ und belohnte damit Übertreibung (Skill-A/B-Test: Begriffsaufnahme über P90 +1,47 Logit). Vergleichslauf ohne Kappung: `--ohne-kappung`.
   - **z-Clipping:** Jedes (gekappte) Merkmal geht als z = max(−3, min(3, (x − Mittel)/SD)) ein (`analyse.Z_CLIP`, von `kalibriere.py` importiert), identisch in Fit, Out-of-fold-Vorhersage, Schwellen, Goodhart-Analyse und `analyse.bewerte()`. Ein einzelner Ausreißer (z. B. viele Semikolons) bestimmt die Wahrscheinlichkeit dadurch nicht allein.
   - **Wahl von k und λ** (Ein-Standardfehler-Regel auf dem balancierten Log-Loss out-of-fold, SE = SD über die Folds/√Folds), in dieser Reihenfolge: (1) beste Konfiguration über das ganze Gitter; (2) k = kleinstes k, dessen bestes λ höchstens Minimum + 1 SE erreicht; (3) für dieses k das **größte** λ, dessen Log-Loss höchstens das Minimum dieses k plus dessen SE beträgt. Das λ-Gitter ist log-gleichabständig in halben Dekaden von 0,0003 bis 31,6 (11 Werte), das k-Gitter 6/9/12/15/20. Bei fast trennbaren Daten belohnt der Log-Loss immer schärfere Wahrscheinlichkeiten; Schritt 3 hält deshalb die stärkste noch gleichwertige Strafe. Der Bericht dokumentiert alle drei Schritte und warnt, wenn λ oder das Minimum am Gitterrand liegt.
   - Das finale Modell wird mit dieser Konfiguration auf allen Daten geschätzt. Der Bericht nennt AUROC und Genauigkeit von Modell und Score als Mittelwert ± SD über die 25 Folds, dazu für die Out-of-fold-Wahrscheinlichkeiten (je Abschnitt gemittelt über die Wiederholungen) Brier-Score, ECE über 10 gleich breite Klassen (jeweils roh und klassenbalanciert, weil das Modell klassenbalanciert geschätzt ist), P5–P95 je Gruppe und eine Reliabilitätstabelle (`evaluation.modell_oof_kalibrierung`).
7. **Schwellen.** `score_schwelle` = Mitte zwischen den Medianen der Out-of-fold-Scores von Mensch und KI; `ziel_p_mensch` = **P10** der menschlichen Out-of-fold-Wahrscheinlichkeiten, begrenzt auf [0,5; 0,95] und auf 2 Stellen gerundet (90 % der echten menschlichen Abschnitte erreichen es; das frühere P25 lag bei 0,98 und war für den Coach zu streng). `ziel_score` = P10 der menschlichen Out-of-fold-Scores (zweiseitig), `ziel_score_ki` (v7) = P10 der menschlichen Out-of-fold-Werte des **einseitigen Scores** `score_ki`, in dem Abweichungen auf der Gegenseite der KI wie grün zählen. Alle stehen unter `textsorten.hochschule`. Coach-Ziel ab v7: p ≥ `ziel_p_mensch` und `score_ki` ≥ `ziel_score_ki`; `evaluation.ziel_erreicht_anteil_oof` gibt den Anteil der Abschnitte je Gruppe an, die das out-of-fold erreichen, `ziel_erreicht_anteil_oof_zweiseitig` zum Vergleich die alte Regel (p und zweiseitiger Score). `features.csv` enthält zusätzlich die In-sample-Werte des finalen Modells (`final_p_mensch`, `final_score`, `final_score_ki`) für Konsistenzprüfungen gegen die Laufzeit.
8. **Goodhart-Sensitivität** (`textsorten.hochschule.goodhart`, Bericht-Abschnitt). Kontrafaktisch am finalen Modell (mit Kappung): Je Modellmerkmal wird in allen KI-Abschnitten nur dieses Merkmal auf den menschlichen Median gesetzt; berichtet werden Median von P(menschlich) vorher/nachher, Median der Änderung, Anteil der KI-Abschnitte über `ziel_p_mensch` und ob der Median-KI-Abschnitt allein dadurch das Ziel erreicht (⚠). Dasselbe für die 3 Merkmale mit dem stärksten KI-Zug gemeinsam (Beitrag = koef · (z(Wert) − z(Mensch-Median)), Median über die KI-Abschnitte). Erreicht ein einzelnes Merkmal das Ziel, ließe sich das Urteil mit einer Stellschraube kippen.
9. **Diagnosen.** AUROC je Quelle und je Texttyp (KI-Abschnitte zählen zur Quelle bzw. zum Typ ihres Basisdokuments) mit Vermerk bei einer Spannweite über 0,15; Pearson- und Spearman-Korrelation der Kennzahlen mit dem Erscheinungsjahr (menschliche Texte); Paarprüfung über Inhaltswort-Überlappung.
10. **Wortlisten** per log-odds-Verhältnis mit informativem Dirichlet-Prior (Monroe, Colaresi & Quinn 2008), Prior-Stärke = Korpusgröße, nur N-Gramme aus mindestens 4 Dokumenten.

## Designentscheidungen

- **Nur Texte bis 2021.** Alles danach könnte bereits KI-beeinflusst sein.
- **Register passend zum Einsatz:** Bachelor-/Masterarbeiten, Seminar- und Hausarbeiten, Fachartikel und Gutachten, vor allem aus Wirtschaft, Sozialwissenschaften, Psychologie, Medien und Bildung.
- **Themengleiches Design:** Jeder KI-Text entsteht aus der inhaltlichen Gliederung eines menschlichen Auszugs. Unterschiede in den Kennzahlen sind dadurch Stil- und keine Themenunterschiede. Der schreibende Agent sieht den menschlichen Wortlaut nie.
- **Feste Abschnittslänge:** Längenabhängige Kennzahlen (Schiefe, Satzanfangs-Anteile, Wortschatzmaße) messen sonst teilweise nur die Länge; vor der Kürzung trennte die Wortzahl allein Mensch und KI mit AUROC ≈ 0,70. In Nutzertexten misst `analyse.py` `satzlaenge_schiefe` und `mattr_klumpung_100` deshalb als Median über Fenster à `analyse.ABSCHNITT_L` = 800 Wörter (für Abschnitte ≤ 800 Wörter identisch mit der Messung am Stück). Texte über `analyse.BLOCK_AB` = 1200 Wörter bewertet `analyse.analysiere_und_bewerte()` im **Blockmodus**: Zerlegung an Absatzgrenzen in Blöcke von etwa 800 Wörtern, Bewertung je Block, Gesamtbewertung aus dem Median je Kennzahl (P(menschlich) = Median der Block-Werte); am Stück lagen sonst vor allem die Absatz-CVs langer Texte zu hoch. Wer mit `--laenge` ≠ 800 kalibriert, muss `ABSCHNITT_L` mitändern.
- **Gleiche Vorverarbeitung:** Überschriften, Listen, Quellenverweise in Klammern (seit v7 auch Belege mit Jahr in eckigen Klammern), Transkriptnotation in Interviewzitaten, Fußnotenmarker und Literaturverzeichnis werden in beiden Korpora identisch ausgeblendet.
- **Nicht bewertet** werden Längen- und Formatartefakte (Absatzzahl, längster Satz, Markdown, Listen, Überschriften, Zitate), Duplikate (Satzlängen-Median/-P10/-P90, MATTR-50, `rhythmus_sprung_rel` als Duplikat des CV, `menzerath_korrelation`, die vor allem Satzlängen-Gleichförmigkeit misst) und `anteil_funktionswoerter` (durch das Funktionswort-Profil ersetzt). Neue Kandidaten (`rhythmus_r1_log`, `nominalketten_pro_100`, `silben_q21`, `mattr_klumpung_100`) werden nur bewertet, wenn sie das Paar-Gate bestehen.

## Grenzen

- Der KI-Korpus stammt von einem Modell (Claude). Andere Modelle haben eigene Vorlieben; die meisten strukturellen Signale (Satzlängen-Gleichförmigkeit, Synonym-Vielfalt, Konnektoren) gelten erfahrungsgemäß modellübergreifend, die Floskel-Gewichte und das Funktionswort-Profil weniger. Vor einer stärkeren Gewichtung sollte ein zweites Modell als Test außerhalb der Verteilung dazukommen.
- **KI-Entwürfe wurden oft nachträglich auf Ziellänge verlängert.** Viele Texte im KI-Korpus sind zunächst zu kurz ausgefallen und dann ergänzt worden. Solche Ergänzungen können Absatzstruktur, Wiederholungen und Schlussformeln anders prägen als ein in einem Zug geschriebener Text; Kennzahlen, die darauf reagieren, messen dann teilweise das Verlängern und nicht das Schreiben. Die Kürzung auf 800 Wörter gleicht nur die Länge an, nicht diese Spuren.
- Strukturasymmetrie: Die KI-Texte sind vollständige Kurztexte mit Einleitung und Schluss, die menschlichen Abschnitte Auszüge aus längeren Arbeiten. Formelhafte Einleitungs- und Fazitsätze sind deshalb vor allem auf der KI-Seite vertreten.
- PDF-Extraktion ist nicht fehlerfrei. Absatzgrenzen menschlicher Texte sind weniger zuverlässig als Satzgrenzen; die starken Absatz-Kennzahlen (Absatzlängen-CV, Sätze-pro-Absatz-CV) hängen an der Absatzreparatur in `extract_text.py` und sind mit Vorsicht zu lesen.
- Die Kreuzvalidierung wählt k und λ und bewertet zugleich (nicht verschachtelt); weil nur zwei Hyperparameter gewählt werden, ist die Überschätzung klein. Die Paarzuordnung folgt der Regel aus `auszuege.py` (mittlerer Abschnitt); ändert sich die Extraktion eines Basisdokuments, kann ein Paar verrutschen (Paarprüfung im Bericht).
- Die Goodhart-Sensitivität ist kontrafaktisch (ein Merkmal wird auf den menschlichen Median gesetzt, alle anderen bleiben). Echte Überarbeitungen verändern mehrere Merkmale zugleich und verschieben sie unterschiedlich weit; ein Goodhart-Test an Schleifenausgaben als dritter Klasse fehlt weiterhin.
- Rohtexte der menschlichen Quellen werden nicht versioniert (Urheberrecht). `meta.jsonl` enthält die URLs; `extract_text.py` reproduziert die Texte.

## Neu kalibrieren

```bash
python3 kalibrierung/scripts/kalibriere.py      # benötigt korpus/mensch und korpus/ki; ca. 3–5 Minuten
python3 kalibrierung/scripts/referenzen.py      # Referenzdateien der Skills neu erzeugen
python3 -m unittest discover -s tests
```

`tests/test_integration_v3.py` kalibriert einen kleinen synthetischen Korpus und prüft die Kette bis zur Laufzeit: gleiches z-Clipping in `kalibriere.py` und `bewerte()` (S1), Modellbeiträge samt Intercept-Term = Logit und Median der KI-Beiträge = Goodhart-Analyse (S2), `unsicher`-Regel (S3) und Blockmodus mit den kalibrierten Dateien (S4).

Probelauf, ohne die Plugin-Daten zu überschreiben (`kalibriere.py` schreibt `baselines.json`, `ki_muster.json` und eine kompakte `wortlisten.json` neben `baselines.json`; liegt diese im `--aus`-Ordner, heißt die kompakte Fassung `wortlisten_kompakt.json`):

```bash
mkdir -p /tmp/kal && cp plugins/humanwriting-de/skills/text-analyse/data/ki_muster.json /tmp/kal/
python3 kalibrierung/scripts/kalibriere.py --aus /tmp/kal --baselines /tmp/kal/baselines.json --muster /tmp/kal/ki_muster.json
python3 kalibrierung/scripts/referenzen.py --baselines /tmp/kal/baselines.json --muster /tmp/kal/ki_muster.json \
        --wortlisten /tmp/kal/wortlisten.json --aus /tmp/kal/references   # Referenzdateien nur in den Probeordner
```

Weitere Optionen: `--laenge` (Abschnittslänge, Standard 800), `--max-abschnitte` (Standard 3), `--cv-wiederholungen`/`--cv-folds` (Standard 5/5), `--bootstrap` (Ziehungen für das Paar-Gate, Standard 300), `--ohne-kappung` (Modell ohne einseitige Kappung, nur als Vergleichslauf).

`tests/test_v7_messung.py` prüft die v7-Messseite: Seite der Abweichung, `score_ki`, Kappung in Fit und Laufzeit (eigener synthetischer Kalibrierlauf mit und ohne Kappung, p/score/score_ki aus `kalibriere.py` = `bewerte()`), verklebte Wörter, Zitatanteil, Transkriptnotation, Belege in eckigen Klammern und Autorenlisten.
