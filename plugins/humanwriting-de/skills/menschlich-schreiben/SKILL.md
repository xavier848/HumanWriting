---
name: menschlich-schreiben
description: Schreibt deutsche Hochschultexte – Hausarbeit, Bachelor-/Masterarbeit, Seminararbeit, Aufgaben- und Case-Study-Bearbeitung, Essay, Bericht, Exposé – so, dass sie in ihren messbaren Stilmerkmalen menschlichen Texten entsprechen: schwankende Satzlängen und natürlicher Rhythmus, Begriffswiederholung statt Synonym-Karussell, ungleich lange Absätze, keine KI-Floskeln und keine Gedankenstriche. Verwende diesen Skill IMMER, wenn ein formeller deutscher Text für Uni oder Hochschule geschrieben, fortgesetzt oder ausformuliert werden soll – auch bei knappen Bitten wie „schreib mir die Einleitung“, „beantworte Aufgabe 2“ oder „formulier das aus“.
---

# Menschlich schreiben (deutsche Hochschultexte)

Dieser Skill legt fest, *wie* du schreibst. Die Zielwerte stammen aus einer Kalibrierung an echten deutschen Hausarbeiten, Abschlussarbeiten und Fachtexten (vor 2022) im Vergleich zu KI-Texten zu denselben Themen. Konkrete Zahlen: `references/zielwerte.md`. Floskeln und Ersatzstrategien: `references/ki-muster.md`. Vorher/Nachher-Beispiele: `references/beispiele.md`. Persönlicher Wortschatz des Nutzers: `references/persoenlicher-wortschatz.md`. Theoretischer Hintergrund: `references/hintergrund.md`. Vorgaben der Munich Business School (APA 7, Form, KI-Regeln): `references/hochschulvorgaben-mbs.md`.

## Ablauf

1. **Inhalt klären.** Aufgabenstellung, Gliederung, vorhandene Quellen und Vorgaben (Umfang, Zitierstil) aus dem Kontext übernehmen. Schreibt der Nutzer an der Munich Business School (MBS), gelten zusätzlich `references/hochschulvorgaben-mbs.md` (APA 7, Gliederung, Form, Abstract auf Englisch). Fehlt Wesentliches, kurz nachfragen. Ist keine Rückfrage möglich (z. B. Diskussion ohne die Vorkapitel): mit allgemeinen Rückverweisen arbeiten, keine Methode, Ergebnisse oder Zahlen des Nutzers erfinden und die getroffenen Annahmen nach dem Text in einer kurzen Notiz nennen.
2. **Schreiben** nach den Regeln unten. Bei längeren Texten abschnittsweise (je Gliederungspunkt).
3. **Messen.** Den fertigen Text in eine Datei schreiben und prüfen:
   `python3 "${CLAUDE_PLUGIN_ROOT}/skills/humanisieren/scripts/coach.py" DATEI --verlauf DATEI.coach.json`
4. **Nachbessern.** Bei Claudes eigenem Entwurf bessert Claude selbst nach den Coach-Hinweisen nach (Überarbeiten-Modus von **humanisieren**). Der Coach-Modus, in dem der Nutzer selbst formuliert, ist für Texte des Nutzers gedacht. Fertig, wenn der Coach „Ziel erreicht“ meldet **und** keine Kennzahl jenseits von P90/P10 auf der der KI abgewandten Seite liegt (der Coach zeigt sie als „menschlicher als typisch“). Solche Werte entstehen durch zu konsequentes Befolgen der Regeln unten (z. B. fast keine Konnektoren, fast nur lange Sätze) und werden zurückgenommen. Einzelne rote Kennzahlen auf der KI-Seite sind normal.

**KI-Regeln der Arbeit:** Es gilt die Vorgabe des Dozenten; viele erlauben KI-erstellte Arbeiten, solange der Student das Thema versteht. Ohne Hinweis schreiben. Nur wenn der Nutzer sagt, dass KI-Texte in einer Arbeit nicht erlaubt sind, einmal kurz anmerken, dass von Claude formulierter Text Anthropics Text-Wasserzeichen tragen kann, und den Coach-Modus für seine eigene Fassung anbieten. Nach einer vollständig geschriebenen Arbeit einmal anbieten, einen kurzen **Verständnis-Spickzettel** zu erstellen: Kernaussagen und Argumentationslinie, die verwendeten Quellen mit ihrer Rolle im Text, zentrale Zahlen und Begriffe, 6–8 mögliche Fragen des Dozenten mit knappen Antworten.

## Die Regeln

### 1. Satzlängen: eine breite Verteilung, keine Einheitslänge
Claude-Texte bleiben im mittleren Band (12–24 Wörter). Menschliche Hochschultexte streuen stärker, und zwar in **beide** Richtungen. Zielverteilung für etwa 900 Wörter (rund 45 Sätze):
- **Rückgrat:** etwa die Hälfte der Sätze mit 12–25 Wörtern. Die häufigsten Klassen sind 11–15 und 16–20 Wörter.
- **Lang:** 5–8 Sätze mit 30 oder mehr Wörtern, davon 1–2 deutlich über 40. Nicht mehr: ein Plateau aus 30–39-Wort-Sätzen ist so auffällig wie Einheitslänge und schwer lesbar.
- **Kurz:** 4–6 Sätze mit höchstens 10 Wörtern (Befund, Einschränkung, Überleitung, Definition). Kurze Sätze sind normal, nicht nur ein seltener Effekt.
- Ø-Satzlänge 18–23 Wörter.
- **Phasen statt Wechsel:** die Satzlänge an die Passage koppeln. In Herleitungen und Abwägungen 2–4 lange Sätze hintereinander, in Definitionen, Befunden und Überleitungen mehrere kurze bis mittlere Sätze hintereinander. Einen kurzen Satz nicht allein zwischen zwei lange stellen; ein streng abwechselndes kurz–lang–kurz ist KI-typisch.
- Lange Sätze über **Nominal- und Präpositionalgruppen** und Aufzählungen bauen („wegen der steigenden Kosten“ statt „…, weil die Kosten steigen“), nicht über angehängte „und“-Teilsätze, und **höchstens einen Nebensatz pro Satz** (Menschen: 31–48 % der Sätze haben einen Nebensatz, Claude mehr).
- Quellen ohne dass-Satz einbinden, wo es geht: „Nach Müller (2019) hängt …“, „In der Studie von Müller (2019) sank …“ statt immer „Müller (2019) zeigt, dass …“.
- Zielwerte für Ø-Satzlänge, Variation und Verteilung: `references/zielwerte.md`.

### 1a. Satzklammer füllen
Zwischen Hilfsverb und Partizip/Infinitiv stehen bei Menschen deutlich mehr Wörter (Ø ~7 gegen ~5 bei Claude). Angaben zu Zeit, Ort, Art, Grund und Mittel ins Mittelfeld holen: „Die Daten wurden *im Frühjahr 2019 in einer Online-Befragung unter 240 Beschäftigten* erhoben.“ statt Angaben in eigene Sätze oder Nebensätze auszulagern. Nicht übertreiben: Ketten aus vier, fünf Präpositionalgruppen machen den Satz schwer lesbar.

### 2. Begriffe wiederholen statt variieren
Menschen greifen das Schlüsselwort des Vorsatzes wieder auf. KI wechselt ständig zu Synonymen und erzeugt dadurch eine unnatürlich hohe Wortschatzvielfalt.
- Einen Fachbegriff, einmal eingeführt, beibehalten (*Arbeitgebermarke* bleibt *Arbeitgebermarke*, nicht abwechselnd *Employer Brand*, *Unternehmensmarke*, *Arbeitgeberimage*).
- **Maß:** etwa jeder zweite Satz knüpft über ein Nomen des Vorsatzes an (Menschen 41–63 %), nicht jeder. Pronomen (sie, er, diese, dies) bleiben normal. Autorennamen nicht im direkt folgenden Satz wiederholen („Lievens und Highhouse … Lievens und Highhouse …“), sondern „die Autoren“ oder „nach dieser Unterscheidung“.
- Anschluss an den Vorsatz über das wiederholte Nomen herstellen („Die Arbeitgebermarke …“), nicht über Possessiva am Satzanfang („Ihre Wirkung …“, „Seine Grenzen …“ – bei Claude doppelt so häufig). Ein schlichtes „Dies“, „Dabei“ oder „Dadurch“ am Satzanfang ist dagegen in menschlichen Arbeiten üblich.
- Keine Synonym-Ketten, um „Wiederholungen zu vermeiden“. In Fachtexten ist Wiederholung präzise.

### 3. Konnektoren und Satzanfänge
- **Konnektoren in Maßen:** Claude setzt rund 10 pro 1000 Wörter, Menschen 4–8 (in 900 Wörtern also 3–7). Nicht auf null drücken, sonst bleiben Gegensätze und Folgerungen unklar. Nicht häufen: *zugleich, darüber hinaus, zudem, hingegen*. Einzeln normal: *allerdings, außerdem, insbesondere, schließlich, jedoch, somit*. Wo der Bezug klar ist, einen überzähligen Konnektor weglassen oder über das wiederholte Nomen anschließen – nicht bloß ins Satzinnere verschieben.
- Keine Sätze der Form „Dies zeigt/verdeutlicht/unterstreicht, dass …“; „Insgesamt zeigt sich“ vermeiden.
- Satzanfänge variieren: Subjekt, Objekt, Adverbial, Nebensatz, Präpositionalgruppe.

### 4. Keine KI-Floskeln und -Konstruktionen
Verboten, auch nicht durch Synonyme ersetzen: „spielt eine zentrale/entscheidende Rolle“, „von entscheidender Bedeutung“, „In der heutigen (Arbeits-)Welt“, „Zusammenfassend lässt sich festhalten“, „nicht nur …, sondern auch“, „Es ist nicht X, sondern Y“-Korrekturen, „sowohl … als auch“ als Dauerformel, „Chancen und Herausforderungen“, „ganzheitlich“, „vielschichtig“, „maßgeblich“, „gewinnt zunehmend an Bedeutung“, „trägt maßgeblich dazu bei“, „im Kern“. Statt der Floskel die konkrete Aussage schreiben: *wofür* ist etwas wichtig, *wie stark*, *nach wem*. Vollständige Liste mit Häufigkeiten und Alternativen: `references/ki-muster.md`. Null Floskeln ist menschlich normal (P10 = 0), auch wenn die Analyse den Wert gelb färbt: nie Floskeln einbauen, um eine Kennzahl zu treffen. Die Wortliste in `ki-muster.md` ist Diagnose: Funktions- und Themenwörter darin nicht krampfhaft meiden.

### 5. Zeichensetzung
- **Keine Semikolons.** In echten Hochschularbeiten kommen sie kaum vor (Median 0), Claude setzt sie regelmäßig.
- **Keine Gedankenstriche** (– oder —) als Einschub oder Pointe. Stattdessen Komma, Klammer oder ein eigener Satz.
- Doppelpunkte sparsam, kein Doppelpunkt-Effekt („Das Ergebnis: …“).
- Klammern für Präzisierungen und wörtliche Zitate aus Quellen sind normal und menschlich.

### 6. Aufzählungen und Formatierung
- Keine Dreier-Aufzählungen als Reflex („A, B und C“ in jedem zweiten Satz). Zwei Elemente, vier Elemente oder ein ausformulierter Satz sind oft natürlicher. Ausgenommen sind Dreiergruppen, die die Quelle vorgibt (Modelldimensionen, Definitionen), und Autorennamen.
- Kein Fettdruck im Fließtext, keine Stichpunktlisten, wenn die Aufgabe Fließtext verlangt. Überschriften nur entsprechend der Gliederung.

### 7. Absätze
- Absätze unterschiedlich lang halten: im Mittel 65–110 Wörter pro Absatz, bei 900 Wörtern also 8–12 Absätze. Mindestens ein Absatz mit 2–3 Sätzen und einer mit 7 oder mehr. Ein Ein-Satz-Absatz nur für eine echte Folgerung, nicht als Pseudo-Überschrift.
- Absätze nicht mit einem zusammenfassenden Kommentarsatz beenden („Somit wird deutlich, dass …“). Der letzte Satz bringt Inhalt oder leitet über.

### 8. Persönlicher Wortschatz
Der Text soll nach dem Nutzer klingen, nicht nach einem generischen Autor. `references/persoenlicher-wortschatz.md` listet Wörter und Wendungen aus seinen eigenen Formulierungen, abgeglichen mit den Korpora:
- ✅-Wörter (menschentypisch) bevorzugen, wo sie passen, z. B. „im Vergleich zu“, „basierend auf“, „anhand von“, „Beispiel“, „Thema“, „Theorie“.
- ⚪-Wörter normal verwenden; ⚠️-Wörter erlaubt, aber nicht häufen.
- Nie Wörter erzwingen, nur damit sie vorkommen.

### 9. Personenbezeichnungen: generisches Maskulinum
Der Nutzer wünscht das generische Maskulinum („die Mitarbeiter“, „die Teilnehmer“, „die Studenten“, „die Dozenten“). Keine gendergerechten Ersatzformen wie „Mitarbeitende“, „Teilnehmende“, „Studierende“, „Bewerbende“, „Lehrende“ und kein Gendersternchen – diese Formen sind zudem ein messbares KI-Signal. Erlaubt sind lexikalisierte Substantivierungen und Rechtsbegriffe: „Beschäftigte“, „Befragte“, „Angestellte“, „Vorgesetzte“, „Auszubildende“, „Arbeitnehmer“. Ausnahme: Aufgabenstellung oder Prüfungsordnung verlangen ausdrücklich etwas anderes, oder es wird wörtlich zitiert.

### 10. Inhaltlich konkret bleiben
- Behauptungen mit Quelle, Zahl, Beispiel oder Begründung versehen statt mit Wertungsadjektiven.
- Einschränkungen und Gegenpositionen dort nennen, wo sie fachlich hingehören, nicht als symmetrische Abwägungsformel.
- **Keine erfundenen Quellen, Zahlen oder Zitate.** Zitierstil aus der Vorgabe übernehmen, sonst APA 7 (an der MBS Pflicht): (Müller, 2019), zwei Autoren (Müller & Meier, 2019), ab drei (Müller et al., 2020), im Satz genannt „Nach Müller (2019) …“; Seitenzahl nur bei wörtlichen Zitaten (Müller, 2019, S. 12). Seitenzahlen nur, wenn sie sicher bekannt sind, nie schätzen. Wörtliche Zitate über 40 Wörter als eingerücktes Blockzitat ohne Anführungszeichen, in Markdown mit `>` (die Analyse blendet es dann aus). Rechtsakte und amtliche Dokumente mit amtlicher Bezeichnung zitieren („Richtlinie (EU) 2022/2464, Art. 29b“). `[Quelle]` nur für empirische Zahlen, Fälle und Befunde, deren Beleg nicht sicher bekannt ist, und nach dem Text kurz auflisten, wofür noch ein Beleg fehlt.
- **Umfang:** Längenangaben des Nutzers beziehen sich auf sein Textprogramm (Fließtext mit Belegen, ohne Überschrift). `coach.py` zählt ohne Klammerbelege und liegt etwa 5–7 % darunter.
- **Englische Teile** (an der MBS immer das Abstract): Die Regeln und Kennzahlen dieses Skills gelten nur für deutschen Fließtext. Ein englisches Abstract nach den Vorgaben der Hochschule schreiben und nicht mit `coach.py` messen.

## Selbstkontrolle vor der Ausgabe

- [ ] Satzlängen breit verteilt: 5–8 lange (davon 1–2 über 40), 4–6 kurze, die Hälfte 12–25 Wörter; Phasen statt Zickzack
- [ ] Konnektoren 3–7 pro 900 Wörter, kein „Dies zeigt …“, kein „Insgesamt zeigt sich“
- [ ] Keine Semikolons, keine Gedankenstriche, keine Floskeln aus `references/ki-muster.md`
- [ ] Fachbegriffe durchgehend gleich benannt, aber keine mechanische Wiederholung von Namen
- [ ] 8–12 Absätze pro 900 Wörter, ungleich lang
- [ ] Generisches Maskulinum, keine Ersatzformen („Mitarbeitende“)
- [ ] Coach ausgeführt: Ziel erreicht und nichts „menschlicher als typisch“ jenseits von P90/P10
