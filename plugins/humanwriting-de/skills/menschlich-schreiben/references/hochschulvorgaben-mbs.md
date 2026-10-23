# Hochschulvorgaben: Munich Business School (MBS)

Kurzfassung der **MBS Research Guidelines 2026** (Version 09/2026) für das Schreiben mit diesem Plugin. Verbindlich ist das Original der Hochschule (Moodle bzw. Prüfungsamt); bei Abweichungen gilt immer das Original und die Absprache mit dem Betreuer. Die Richtlinien gelten für Seminararbeiten, Bachelor- und Masterarbeiten.

## 1. KI-Regeln (Teil C) und was sie für dieses Plugin bedeuten

**Erlaubt:** KI als Feedback- und Verbesserungswerkzeug für den eigenen Text (Stil, Struktur, Klarheit), für Ideen, Literatursuche und als Sparringspartner bei der Statistik. Wer selbst schreibt und den Text dann mit KI verbessert, bleibt Autor (Teil C, 4.3).

**Nicht erlaubt bzw. stark begrenzt:**
- Von KI formulierte Sätze (wörtlich oder paraphrasiert) dürfen auch mit Dokumentation nur **sparsam und ausgewählt** in die Arbeit. Eine Arbeit aus Zeile für Zeile erzeugtem KI-Text verstößt gegen die Regeln, auch wenn er gekennzeichnet ist (4.1, 4.2).
- Große Teile mit KI zu schreiben verstößt auch bei transparenter Kennzeichnung gegen die Grundsätze eigenständiger Arbeit. Beruhen große Teile auf KI-Formulierungen, kann die Arbeit abgewertet oder als nicht bestanden bewertet werden (4.2).
- KI ist keine Quelle: keine Fakten, Zahlen, Definitionen, Zitate oder Studienzusammenfassungen aus KI ohne eigene Prüfung an der Originalquelle (4.1).
- Empirische Daten dürfen nie von KI erzeugt, verändert oder simuliert werden (3.4).

**Dokumentationspflicht** (5.1, Anhänge 1–3):
- Erklärung zur Kenntnis und Einhaltung der KI-Richtlinien (bei Zulassung und Abgabe).
- Selbsterklärung zur KI-Nutzung als Anhang der Arbeit (Anhang 2). Zur Textformulierung wird dort erklärt, dass KI keine vollständigen Abschnitte oder Kapitel erzeugt hat und nur Klarheit, Grammatik oder Stil in selbst entworfenen Texten verbessert hat.
- Tabelle aller relevanten KI-Nutzungen als zusätzliches Verzeichnis in der Arbeit (Anhang 3), Spalten: **Kapitel/Abschnitt, Werkzeug, Zweck, repräsentative Prompts, Ergebnis/Einbindung**, mit 2–3 repräsentativen Beispielen je größerem Abschnitt. Auch reine Grammatik- und Stilhilfe wird aufgeführt.
- In der Arbeit selbst erklären, welche KI-Werkzeuge wie genutzt wurden.
- Auf Anfrage: **Denkprozess-Portfolio** (erste Entwürfe, datierte Fassungen, Notizen, Mindmaps) und eine **Reflexion** von etwa 350 Wörtern über die KI-Nutzung, die nicht von KI geschrieben sein darf.
- Bei empirischen Arbeiten: Rohdaten, Einwilligungen und Korrespondenz an den Betreuer; Speicherung nur in der Hochschulumgebung (MBS OneDrive), nicht auf privaten Geräten oder Cloud-Diensten.

**Folgen für die Skills:**
- **Coach-Modus** (`humanisieren`) ist der Weg, der zu 4.3 passt: Der Nutzer schreibt, Claude misst und gibt Hinweise, die Formulierungen bleiben eigene. Die Nutzung trotzdem in der Tabelle aus Anhang 3 dokumentieren; `ki_protokoll.py` erzeugt die Zeilen aus dem Coach-Verlauf.
- **Von Claude geschriebene Abschnitte** (`menschlich-schreiben`, Überarbeiten-Modus) sind KI-Formulierungen im Sinne von 4.2. Für MBS-Prüfungsleistungen höchstens sparsam und dokumentiert verwenden. Claude weist einmal darauf hin und bietet den Coach-Weg an.
- Datierte Fassungen aufbewahren (z. B. `kapitel2_2026-10-23.md` vor jeder Coach-Runde); sie dienen als Denkprozess-Portfolio.
- Das Plugin misst Stil. Es ersetzt keine Dokumentation und dient nicht dazu, KI-Nutzung zu verbergen.

## 2. Zitieren nach APA 7 (Pflicht an der MBS)

**Im Text** (Autor, Jahr) an der passenden Stelle im Satz, Seitenzahl **nur bei wörtlichen Zitaten**:
- (Müller, 2019) · wörtlich (Müller, 2019, S. 12), mehrere Seiten (Müller, 2019, S. 12–14). In englischen Arbeiten „p.“ und „pp.“.
- Zwei Autoren: (Müller & Meier, 2019). Mehr als zwei: (Müller et al., 2020).
- Ist der Autor im Satz genannt, steht nur das Jahr in der Klammer: „Nach Müller (2019) …“, wörtlich „Müller (2019, S. 12) schreibt: …“.
- Auch vermeintliches Allgemeinwissen wird belegt.
- Bei Internetquellen möglichst DOI statt URL. Quellen ohne Autor, Jahr und Titel (nur eine URL) sind nicht zitierfähig, dann Institution als Autor oder Quelle verwerfen.

**Wörtliche Zitate:** in Anführungszeichen, nur wenn der Wortlaut zählt (z. B. Definitionen), keine Allgemeinplätze wörtlich zitieren. Auslassungen mit (...), eigene Ergänzungen in [ ], eigene Hervorhebungen in der Fußnote als „Hervorhebung durch den Verfasser“ kennzeichnen. **Über 40 Wörter:** als eingerücktes Blockzitat auf neuer Zeile, ohne Anführungszeichen, Beleg am Ende. In Markdown mit `>` markieren, damit die Analyse es als fremden Wortlaut ausblendet.

**Fremdsprachige Quellen:** gleiches System. Eine selbst übersetzte Stelle gilt als sinngemäßes Zitat (Paraphrase). Im Literaturverzeichnis Originaltitel mit Übersetzung in [eckigen Klammern], nicht kursiv.

**Unveröffentlichte Quellen** (Unternehmensunterlagen, Protokolle) gehören auszugsweise in den Anhang. Selbst erhobenes Material (Interviews, Umfragen) wird schriftlich belegt. Anmerkungen gehen in Fußnoten.

**Literaturverzeichnis** (MBS: „Reference List“): alphabetisch nach Nachnamen, hängender Einzug 2 cm, nicht nummeriert, keine Aufzählungszeichen. Mehrere Werke eines Autors chronologisch, im selben Jahr 2019a, 2019b. Keine akademischen oder beruflichen Titel. Abkürzungen Ed./Eds., et al., p./pp., Vol. Titel von Büchern, Zeitschriften und Sammelwerken kursiv. DOI angeben, wenn vorhanden. Nur Quellen, die im Text oder Anhang zitiert sind.
- Buch: Gardner, H. (1996). *Leading minds: An anatomy of leadership*. Basic Books.
- Zeitschrift: Kahneman, D. (2003). Maps of bounded rationality: Psychology for behavioral economics. *American Economic Review*, 93, pp. 1449–1475. (So im MBS-Beispiel; reines APA 7 lässt „pp.“ bei Zeitschriften weg. Wichtigste Regel der Richtlinien: einheitlich bleiben.)
- Sammelband: Bernardes, J., & O'Donoghue, J. (2003). Delivery and learning support systems. In C. Ghaoui (Ed.), *Usability evaluation of online learning programs* (pp. 19–39). Information Science Publishing.
- Internet: Autor bzw. Herausgeber oder Betreiber (Jahr, ggf. Datum). *Titel*. URL

## 3. Formvorgaben (Teil B)

- **Sprache:** Abschlussarbeit auf Deutsch oder Englisch (Dual Degree: Englisch), Seminararbeit in der Sprache des Kurses.
- **Abstract:** immer **auf Englisch**, 150–250 Wörter, ein oder zwei Absätze, keine Zitate und keine Belege, Hintergrund und Fazit im Präsens, Methode und Ergebnisse im Präteritum. Die deutschen Kennzahlen dieses Plugins gelten dafür nicht; das Abstract nicht mit `coach.py` messen.
- **Seite:** A4, Ränder 2,54 cm, Times New Roman 12 pt, Fußnoten 10 pt, Zeilenabstand doppelt (Fußnoten, Überschriften, Abbildungs- und Tabellentitel einfach), keine Leerzeile oder Abstand zwischen Absätzen, Erstzeileneinzug 0,5 (Einheit in der Richtlinie nicht genannt, im Zweifel beim Betreuer klären), Blocksatz mit Silbentrennung, jedes Kapitel auf neuer Seite.
- **Umfang** (Textseiten von der ersten bis zur letzten Textseite): Bachelorarbeit 40–60, Masterarbeit 60–80 Seiten; bei anderen Arbeiten gibt der Dozent den Umfang vor.
- **Reihenfolge:** Titelblatt (gezählt, ohne Nummer) – Abstract (Seite 2) – Inhaltsverzeichnis – ggf. Abbildungs-, Tabellen-, Anhangsverzeichnis, Glossar, Abkürzungsverzeichnis – Text – Literaturverzeichnis – ggf. Anhang (römisch nummeriert, im Text referenziert) – Eigenständigkeitserklärung (ohne Seitenzahl). Seitenzahlen arabisch, oben rechts. Das Titelblattformat ist verbindlich (Muster in den Anhängen 5 und 6 der Richtlinien).
- **Gliederung:** Jede Ebene hat mindestens zwei Punkte (auf 1.1 folgt 1.2). Überschriften sind keine ganzen Sätze und keine Fragen, nicht zu lang, im Text wortgleich wie im Inhaltsverzeichnis.
- **Abbildungen und Tabellen:** fortlaufend nummeriert, „Figure 1“ bzw. „Abbildung 1“ fett und linksbündig, darunter der Titel kursiv, Quelle am Titel („Adapted from …“ bzw. „in Anlehnung an …“ bei veränderten Darstellungen). Nur ins Verzeichnis, wenn vorhanden. Ergänzendes Material in den Anhang.
- **Abkürzungen:** sparsam, keine Bequemlichkeitsabkürzungen, bei erster Verwendung ausschreiben und die Abkürzung in Klammern dahinter. Ein Abkürzungsverzeichnis erst ab mindestens fünf Fachabkürzungen; gängige (z. B., EUR, CEO) gehören nicht hinein.
- **Plagiat** (fremde Gedanken ohne Beleg) führt zur Note 5,0 und kann weitere Maßnahmen nach sich ziehen. Arbeiten werden auf Plagiate geprüft.

## 4. Empirische Arbeiten (Teil A, kurz)

Vor der Datenerhebung prüfen, ob sensible Themen (z. B. psychische Gesundheit, Diskriminierung, politische oder religiöse Überzeugungen) oder vulnerable Gruppen (z. B. Minderjährige, Abhängigkeitsverhältnisse wie eigene Mitarbeiter oder Kommilitonen) betroffen sind. Dann Schutzmaßnahmen festlegen, im Zweifel Betreuer und danach das Research Committee fragen. Teilnahme nur mit informierter Einwilligung (freiwillig, informiert, jederzeit widerrufbar). Aufnahmen nur, wenn das Design sie braucht. Personenbezogene Daten löschen, sobald sie nicht mehr gebraucht werden. Anonymisierte Daten bis zu zehn Jahre aufbewahren.
