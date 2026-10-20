---
name: menschlich-schreiben
description: Schreibt deutsche Hochschultexte – Hausarbeit, Bachelor-/Masterarbeit, Seminararbeit, Aufgaben- und Case-Study-Bearbeitung, Essay, Bericht, Exposé – so, dass sie in ihren messbaren Stilmerkmalen menschlichen Texten entsprechen: schwankende Satzlängen und natürlicher Rhythmus, Begriffswiederholung statt Synonym-Karussell, ungleich lange Absätze, keine KI-Floskeln und keine Gedankenstriche. Verwende diesen Skill IMMER, wenn ein formeller deutscher Text für Uni oder Hochschule geschrieben, fortgesetzt oder ausformuliert werden soll – auch bei knappen Bitten wie „schreib mir die Einleitung“, „beantworte Aufgabe 2“ oder „formulier das aus“.
---

# Menschlich schreiben (deutsche Hochschultexte)

Dieser Skill legt fest, *wie* du schreibst. Die Zielwerte stammen aus einer Kalibrierung an echten deutschen Hausarbeiten, Abschlussarbeiten und Fachtexten (vor 2022) im Vergleich zu KI-Texten zu denselben Themen. Konkrete Zahlen: `references/zielwerte.md`. Floskeln und Ersatzstrategien: `references/ki-muster.md`. Vorher/Nachher-Beispiele: `references/beispiele.md`. Persönlicher Wortschatz des Nutzers: `references/persoenlicher-wortschatz.md`. Theoretischer Hintergrund: `references/hintergrund.md`.

## Ablauf

1. **Inhalt klären.** Aufgabenstellung, Gliederung, vorhandene Quellen und Vorgaben (Umfang, Zitierstil) aus dem Kontext übernehmen. Fehlt Wesentliches, kurz nachfragen.
2. **Schreiben** nach den Regeln unten – abschnittsweise, nicht alles in einem Zug.
3. **Messen.** Den fertigen Text in eine Datei schreiben und prüfen:
   `python3 "${CLAUDE_PLUGIN_ROOT}/skills/humanisieren/scripts/coach.py" DATEI`
4. **Nachbessern** mit dem Skill **humanisieren** (Coach-Modus), bis keine bewertete Kennzahl mehr rot ist.

**Eigene Prüfungsleistungen** (Hausarbeit, Bachelorarbeit mit Eigenständigkeitserklärung): Von Claude formulierter Text trägt Anthropics Text-Wasserzeichen, das Hochschulen prüfen können. Dort diesen Skill für Gliederung, Argumentationsgerüst, Stichpunkte und Musterabschnitte nutzen, die der Nutzer **selbst ausformuliert** – und den Coach-Modus zum Feinschliff seiner eigenen Fassung. Auf die KI-Regeln der Hochschule hinweisen, wenn der Nutzer einen fertigen Abgabetext verlangt.

## Die Regeln

### 1. Satzlängen: Streuung über lange, dichte Sätze
Menschliche Hochschultexte streuen in der Satzlänge stärker – vor allem durch **lange Sätze** (30–50 Wörter) in argumentierenden Passagen. Claude-Texte bleiben im mittleren Band (12–24 Wörter) und reihen viele kurze Teilsätze.
- Begründungen, Abwägungen und Bedingungen in langen Sätzen formulieren, die durch **Nominal- und Präpositionalgruppen** verdichtet sind („wegen der steigenden Kosten“ statt „…, weil die Kosten steigen“), nicht durch angehängte „und“-Teilsätze.
- Ähnlich lange Sätze dürfen aufeinander folgen. **Nicht** kurz–lang–kurz abwechseln – genau dieses Zickzack ist KI-typisch.
- Kurze Sätze nur für echte Zwischenergebnisse oder Einschränkungen, sparsam.
- Zielwerte für Ø-Satzlänge, Variation und Verteilung: `references/zielwerte.md`.

### 1a. Satzklammer füllen
Zwischen Hilfsverb und Partizip/Infinitiv stehen bei Menschen deutlich mehr Wörter (Ø ~7 gegen ~5 bei Claude). Angaben zu Zeit, Ort, Art, Grund und Mittel ins Mittelfeld holen: „Die Daten wurden *im Frühjahr 2019 in einer Online-Befragung unter 240 Beschäftigten* erhoben.“ statt Angaben in eigene Sätze oder Nebensätze auszulagern.

### 2. Begriffe wiederholen statt variieren
Menschen greifen das Schlüsselwort des Vorsatzes wieder auf. KI wechselt ständig zu Synonymen und erzeugt dadurch eine unnatürlich hohe Wortschatzvielfalt.
- Einen Fachbegriff, einmal eingeführt, beibehalten (*Arbeitgebermarke* bleibt *Arbeitgebermarke*, nicht abwechselnd *Employer Brand*, *Unternehmensmarke*, *Arbeitgeberimage*).
- Anschluss an den Vorsatz über das wiederholte Nomen herstellen („Die Arbeitgebermarke …“), nicht über „Dies …“.
- Keine Synonym-Ketten, um „Wiederholungen zu vermeiden“. In Fachtexten ist Wiederholung präzise.

### 3. Konnektoren und Satzanfänge
- **Weniger Konnektoren insgesamt** (Claude ~10, Menschen ~7 pro 1000 Wörter; besonders *zugleich, darüber hinaus, hingegen, zudem, jedoch*). Wo der Bezug klar ist, den Konnektor weglassen oder über das wiederholte Nomen anschließen – nicht bloß ins Satzinnere verschieben.
- Keine Sätze der Form „Dies zeigt/verdeutlicht/unterstreicht, dass …“; „Insgesamt zeigt sich“ vermeiden.
- Satzanfänge variieren: Subjekt, Objekt, Adverbial, Nebensatz, Präpositionalgruppe.

### 4. Keine KI-Floskeln und -Konstruktionen
Verboten, auch nicht durch Synonyme ersetzen: „spielt eine zentrale/entscheidende Rolle“, „von entscheidender Bedeutung“, „In der heutigen (Arbeits-)Welt“, „Zusammenfassend lässt sich festhalten“, „nicht nur …, sondern auch“, „Es ist nicht X, sondern Y“-Korrekturen, „sowohl … als auch“ als Dauerformel, „Chancen und Herausforderungen“, „ganzheitlich“, „vielschichtig“, „maßgeblich“, „gewinnt zunehmend an Bedeutung“, „trägt maßgeblich dazu bei“, „im Kern“. Statt der Floskel die konkrete Aussage schreiben: *wofür* ist etwas wichtig, *wie stark*, *nach wem*. Vollständige Liste mit Häufigkeiten und Alternativen: `references/ki-muster.md`.

### 5. Zeichensetzung
- **Keine Semikolons.** In echten Hochschularbeiten kommen sie kaum vor (Median 0), Claude setzt sie regelmäßig.
- **Keine Gedankenstriche** (– oder —) als Einschub oder Pointe. Stattdessen Komma, Klammer oder ein eigener Satz.
- Doppelpunkte sparsam, kein Doppelpunkt-Effekt („Das Ergebnis: …“).
- Klammern für Präzisierungen und wörtliche Zitate aus Quellen sind normal und menschlich.

### 6. Aufzählungen und Formatierung
- Keine Dreier-Aufzählungen als Reflex („A, B und C“ in jedem zweiten Satz). Zwei Elemente, vier Elemente oder ein ausformulierter Satz sind oft natürlicher.
- Kein Fettdruck im Fließtext, keine Stichpunktlisten, wenn die Aufgabe Fließtext verlangt. Überschriften nur entsprechend der Gliederung.

### 7. Absätze
- Absätze unterschiedlich lang halten. Ein Absatz mit zwei Sätzen neben einem mit sieben ist normal.
- Absätze nicht mit einem zusammenfassenden Kommentarsatz beenden („Somit wird deutlich, dass …“). Der letzte Satz bringt Inhalt oder leitet über.

### 8. Persönlicher Wortschatz
Der Text soll nach dem Nutzer klingen, nicht nach einem generischen Autor. `references/persoenlicher-wortschatz.md` listet Wörter und Wendungen aus seinen eigenen Formulierungen, abgeglichen mit den Korpora:
- ✅-Wörter (menschentypisch) bevorzugen, wo sie passen, z. B. „im Vergleich zu“, „basierend auf“, „anhand von“, „Beispiel“, „Thema“, „Theorie“.
- ⚪-Wörter normal verwenden; ⚠️-Wörter erlaubt, aber nicht häufen.
- Nie Wörter erzwingen, nur damit sie vorkommen.

### 9. Personenbezeichnungen: generisches Maskulinum
Der Nutzer wünscht das generische Maskulinum („die Mitarbeiter“, „die Teilnehmer“, „die Studenten“). Keine Partizipformen wie „Mitarbeitende“, „Teilnehmende“, „Studierende“ und kein Gendersternchen – Partizipformen sind zudem ein messbares KI-Signal (Claude nutzt sie mehrfach so oft wie die Studierenden im Korpus). Ausnahme: Aufgabenstellung oder Prüfungsordnung verlangen ausdrücklich etwas anderes, oder es wird wörtlich zitiert.

### 10. Inhaltlich konkret bleiben
- Behauptungen mit Quelle, Zahl, Beispiel oder Begründung versehen statt mit Wertungsadjektiven.
- Einschränkungen und Gegenpositionen dort nennen, wo sie fachlich hingehören, nicht als symmetrische Abwägungsformel.
- **Keine erfundenen Quellen, Zahlen oder Zitate.** Fehlt eine Quelle, Platzhalter `[Quelle]` setzen und den Nutzer darauf hinweisen.

## Selbstkontrolle vor der Ausgabe

- [ ] Wenige Konnektoren, kein „Dies zeigt …“, kein „Insgesamt zeigt sich“
- [ ] Keine Semikolons, keine Gedankenstriche, keine Floskeln aus `references/ki-muster.md`
- [ ] Argumentierende Passagen in langen, nominal verdichteten Sätzen; kein kurz–lang-Zickzack
- [ ] Fachbegriffe durchgehend gleich benannt
- [ ] Generisches Maskulinum, keine Partizipformen („Mitarbeitende“)
- [ ] Analyse-Skript ausgeführt, keine bewertete Kennzahl rot
