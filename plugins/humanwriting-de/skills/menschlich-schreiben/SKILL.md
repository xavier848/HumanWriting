---
name: menschlich-schreiben
description: Schreibt deutsche Hochschultexte – Hausarbeit, Bachelor-/Masterarbeit, Seminararbeit, Aufgaben- und Case-Study-Bearbeitung, Essay, Bericht, Exposé – so, dass sie in ihren messbaren Stilmerkmalen menschlichen Texten entsprechen: schwankende Satzlängen und natürlicher Rhythmus, Begriffswiederholung statt Synonym-Karussell, ungleich lange Absätze, keine KI-Floskeln und keine Gedankenstriche. Verwende diesen Skill IMMER, wenn ein formeller deutscher Text für Uni oder Hochschule geschrieben, fortgesetzt oder ausformuliert werden soll – auch bei knappen Bitten wie „schreib mir die Einleitung“, „beantworte Aufgabe 2“ oder „formulier das aus“.
---

# Menschlich schreiben (deutsche Hochschultexte)

Dieser Skill legt fest, *wie* du schreibst. Die Zielwerte stammen aus einer Kalibrierung an echten deutschen Hausarbeiten, Abschlussarbeiten und Fachtexten (vor 2022) im Vergleich zu KI-Texten zu denselben Themen. Konkrete Zahlen: `references/zielwerte.md`. Floskeln und Ersatzstrategien: `references/ki-muster.md`. Vorher/Nachher-Beispiele: `references/beispiele.md`. Persönlicher Wortschatz des Nutzers: `references/persoenlicher-wortschatz.md`. Theoretischer Hintergrund: `references/hintergrund.md`. Vorgaben der Munich Business School (APA 7, Form, KI-Regeln): `references/hochschulvorgaben-mbs.md`.

## Ablauf

1. **Inhalt klären.** Aufgabenstellung, Gliederung, vorhandene Quellen und Vorgaben (Umfang, Zitierstil) aus dem Kontext übernehmen. Schreibt der Nutzer an der Munich Business School (MBS), gelten zusätzlich `references/hochschulvorgaben-mbs.md` (APA 7, Gliederung, Form, Abstract auf Englisch). Fehlt Wesentliches, kurz nachfragen. Ist keine Rückfrage möglich (z. B. Diskussion ohne die Vorkapitel): mit allgemeinen Rückverweisen arbeiten, keine Methode, Ergebnisse oder Zahlen des Nutzers erfinden und die getroffenen Annahmen nach dem Text in einer kurzen Notiz nennen.
2. **Schreiben** nach den Regeln unten. Bei längeren Texten abschnittsweise (je Gliederungspunkt).
3. **Messen.** Den fertigen Text (nur Überschrift und Fließtext; Notizen zu Annahmen und fehlenden Belegen gehören in die Chat-Antwort, nicht in die Datei) in eine Datei schreiben und prüfen:
   `python3 "${CLAUDE_PLUGIN_ROOT}/skills/humanisieren/scripts/coach.py" DATEI --verlauf DATEI.coach.json`
4. **Nachbessern.** Bei Claudes eigenem Entwurf bessert Claude selbst nach den Coach-Hinweisen nach (Überarbeiten-Modus von **humanisieren**). Der Coach-Modus, in dem der Nutzer selbst formuliert, ist für Texte des Nutzers gedacht. Maßgeblich ist der Score der KI-Seite (`score_ki`), nicht der beidseitige. Fertig, wenn der Coach „Ziel erreicht“ meldet **und** im Kasten „Menschlicher als typisch“ nichts mehr steht. Für diese Werte gibt der Coach keine Aufträge, weil sie bei einem Nutzertext Eigenart wären; bei Claudes Entwurf entstehen sie durch zu konsequentes Befolgen der Regeln, und Claude nimmt sie selbst zurück, dann erneut messen:
   - Konnektoren unter dem Band: an 2–3 echten Gegensätzen oder Folgerungen ein Wort aus der Zählliste (Regel 3) einsetzen.
   - Zu wenig Nebensätze (Sätze mit Nebensatz, Wörter pro Teilsatz, Sätze ohne Komma, Verhältnis 2:1): 2–3 Nominalgruppen wieder als dass-, weil- oder Relativsatz schreiben.
   - Satzklammer zu voll: in den längsten Klammern eine Angabe vor das Hilfsverb oder ans Satzende holen.
   - Zu viele lange Sätze oder Begriffsaufnahme über dem Band: einen langen Satz teilen bzw. in 2–3 Sätzen das wiederholte Nomen durch ein Pronomen ersetzen.
   - Klammern über dem Band: Fundstellen in den Satz holen, Abkürzungen nur einführen, wenn sie mindestens dreimal vorkommen.
   Einzelne rote oder gelbe Kennzahlen auf der KI-Seite sind normal.

**KI-Regeln der Arbeit:** Es gilt die Vorgabe des Dozenten; viele erlauben KI-erstellte Arbeiten, solange der Student das Thema versteht. Ohne Hinweis schreiben. Nur wenn der Nutzer sagt, dass KI-Texte in einer Arbeit nicht erlaubt sind, einmal kurz anmerken, dass von Claude formulierter Text Anthropics Text-Wasserzeichen tragen kann, und den Coach-Modus für seine eigene Fassung anbieten. Nach einer vollständig geschriebenen Arbeit einmal anbieten, einen kurzen **Verständnis-Spickzettel** zu erstellen: Kernaussagen und Argumentationslinie, die verwendeten Quellen mit ihrer Rolle im Text, zentrale Zahlen und Begriffe, 6–8 mögliche Fragen des Dozenten mit knappen Antworten.

## Die Regeln

### 1. Satzlängen: eine breite Verteilung, keine Einheitslänge
Claude-Texte bleiben im mittleren Band (12–24 Wörter). Menschliche Hochschultexte streuen stärker, und zwar in **beide** Richtungen. Zielverteilung für etwa 900 Wörter (rund 45 Sätze):
- **Rückgrat:** etwa die Hälfte der Sätze mit 12–25 Wörtern. Die häufigsten Klassen sind 11–15 und 16–20 Wörter.
- **Lang:** 5–8 Sätze mit 30 oder mehr Wörtern, davon 1–2 deutlich über 40. Nicht mehr: ein Plateau aus 30–39-Wort-Sätzen ist so auffällig wie Einheitslänge und schwer lesbar.
- **Kurz:** 4–6 Sätze mit höchstens 10 Wörtern (Befund, Einschränkung, Überleitung, Definition), nicht mehr. Kurze Sätze sind normal, nicht nur ein seltener Effekt.
- Ø-Satzlänge 18–23 Wörter.
- **Phasen statt Wechsel:** die Satzlänge an die Passage koppeln. In Herleitungen und Abwägungen 2–4 Sätze über 25 Wörter hintereinander, in Definitionen, Befunden und Überleitungen mehrere kurze bis mittlere Sätze hintereinander. Kurze Sätze paarweise oder als Folge von 2–3 kurzen bis mittleren Sätzen setzen, bevorzugt am Absatzanfang (Definition, Befund) oder am Absatzende (Überleitung). Einen kurzen Satz nicht allein zwischen zwei lange stellen; ein streng abwechselndes kurz–lang–kurz ist KI-typisch. Beispiel einer Längenfolge in einem Absatz: 9, 12, 28, 34, 22, 15.
- Lange Sätze über **Nominal- und Präpositionalgruppen** und Aufzählungen bauen („wegen der steigenden Kosten“ statt „…, weil die Kosten steigen“), nicht über angehängte „und“-Teilsätze.
- **Nebensätze in Maßen:** etwa jeder dritte Satz (30–45 %) hat genau einen Nebensatz (dass, weil, Relativsatz); zwei Nebensätze in einem Satz sind selten. Claude hängt öfter einen an, aber nicht alles nominal verdichten: höchstens gut die Hälfte der Sätze bleibt ganz ohne Nebensatz.
- Quellen ohne dass-Satz einbinden, wo es geht: „Nach Müller (2019) hängt …“, „In der Studie von Müller (2019) sank …“ statt immer „Müller (2019) zeigt, dass …“.
- Zielwerte für Ø-Satzlänge, Variation und Verteilung: `references/zielwerte.md`.

### 1a. Satzklammer füllen
Zwischen Hilfsverb und Partizip/Infinitiv stehen bei Menschen deutlich mehr Wörter (Ø ~7 gegen ~5 bei Claude). Angaben zu Zeit, Ort, Art, Grund und Mittel ins Mittelfeld holen: „Die Daten wurden *im Frühjahr 2019 in einer Online-Befragung unter 240 Beschäftigten* erhoben.“ statt Angaben in eigene Sätze oder Nebensätze auszulagern. Ziel Ø 6–8 Wörter in der Klammer: etwa jede zweite Klammer füllen, nicht jede, und keine Klammer über 12–15 Wörter. Bei wenigen Klammersätzen zählt jede einzelne stark. Ketten aus vier, fünf Präpositionalgruppen machen den Satz schwer lesbar.

### 2. Begriffe wiederholen statt variieren
Menschen greifen das Schlüsselwort des Vorsatzes wieder auf. KI wechselt ständig zu Synonymen und erzeugt dadurch eine unnatürlich hohe Wortschatzvielfalt.
- Einen Fachbegriff, einmal eingeführt, beibehalten (*Arbeitgebermarke* bleibt *Arbeitgebermarke*, nicht abwechselnd *Employer Brand*, *Unternehmensmarke*, *Arbeitgeberimage*).
- **Maß:** etwa jeder zweite Satz knüpft über ein Nomen des Vorsatzes an (Menschen 41–63 %), nicht mehr als etwa zwei Drittel. Bei Theorievergleichen und Diskussionen jede Theorie in 2–3 aufeinanderfolgenden Sätzen behandeln statt jede in einem Satz und den Vergleichsbegriff (z. B. Autonomie, Berichtspflicht) als Anker in den Folgesätzen wieder aufnehmen. Pronomen (sie, er, diese, dies) bleiben normal. Autorennamen nicht im direkt folgenden Satz wiederholen („Lievens und Highhouse … Lievens und Highhouse …“), sondern „die Autoren“ oder „nach dieser Unterscheidung“.
- Anschluss an den Vorsatz über das wiederholte Nomen herstellen („Die Arbeitgebermarke …“), nicht über Possessiva am Satzanfang („Ihre Wirkung …“, „Seine Grenzen …“ – bei Claude doppelt so häufig). Ein schlichtes „Dies“, „Dabei“ oder „Dadurch“ am Satzanfang ist dagegen in menschlichen Arbeiten üblich.
- Keine Synonym-Ketten, um „Wiederholungen zu vermeiden“. In Fachtexten ist Wiederholung präzise.

### 3. Konnektoren und Satzanfänge
- **Konnektoren in Maßen:** Claude setzt rund 10 pro 1000 Wörter, Menschen 4–8. Gezählt werden nur: *zudem, außerdem, ferner, weiterhin, des Weiteren, folglich, somit, demnach, infolgedessen, allerdings, jedoch, dennoch, gleichwohl, nichtsdestotrotz, insbesondere, letztlich, letztendlich, zugleich, gleichzeitig, schließlich, hingegen, wiederum*. Nicht gezählt und ganz normal: *deshalb, daher, dabei, damit, aber, trotzdem*. Ziel: 4–7 Wörter aus der Zählliste pro 900 Wörter, an echten Gegensätzen und Folgerungen. Nicht auf null drücken, sonst bleiben Gegensätze und Folgerungen unklar. Nicht häufen: *zugleich, darüber hinaus, zudem, hingegen*. Einzeln normal: *allerdings, außerdem, insbesondere, schließlich, jedoch, somit*. Wo der Bezug klar ist, einen überzähligen Konnektor weglassen oder über das wiederholte Nomen anschließen – nicht bloß ins Satzinnere verschieben.
- Keine Sätze der Form „Dies zeigt/verdeutlicht/unterstreicht, dass …“; „Insgesamt zeigt sich“ vermeiden.
- Satzanfänge variieren: Subjekt, Objekt, Adverbial, Nebensatz, Präpositionalgruppe.

### 4. Keine KI-Floskeln und -Konstruktionen
Verboten, auch nicht durch Synonyme ersetzen: „spielt eine zentrale/entscheidende Rolle“, „von entscheidender Bedeutung“, „In der heutigen (Arbeits-)Welt“, „Zusammenfassend lässt sich festhalten“, „nicht nur …, sondern auch“, „Es ist nicht X, sondern Y“-Korrekturen, „sowohl … als auch“ als Dauerformel, „Chancen und Herausforderungen“, „ganzheitlich“, „vielschichtig“, „maßgeblich“, „gewinnt zunehmend an Bedeutung“, „trägt maßgeblich dazu bei“, „im Kern“. Statt der Floskel die konkrete Aussage schreiben: *wofür* ist etwas wichtig, *wie stark*, *nach wem*. Vollständige Liste mit Häufigkeiten und Alternativen: `references/ki-muster.md`. Null Floskeln ist menschlich normal (P10 = 0), auch wenn die Analyse den Wert gelb färbt: nie Floskeln einbauen, um eine Kennzahl zu treffen. Ausgenommen sind etablierte Fachbegriffe („Ganzheitlichkeit der Aufgabe“ im Job-Characteristics-Modell) und Wörter aus der Aufgabenstellung oder einer vorgegebenen Überschrift („Chancen und Risiken“). Die Wortliste in `ki-muster.md` ist nur in der ersten Gruppe Schreibhilfe (dieselbe Wendung höchstens zweimal pro 900 Wörter); Funktions- und Themenwörter darin nicht krampfhaft meiden.

### 5. Zeichensetzung
- **Keine Semikolons.** In echten Hochschularbeiten kommen sie kaum vor (Median 0), Claude setzt sie regelmäßig. Ausgenommen sind Semikolons in APA-Klammerbelegen mit mehreren Quellen („(Diller, 2008; Simon & Fassnacht, 2016)“); die Analyse blendet sie aus.
- **Keine Gedankenstriche** (– oder —) als Einschub oder Pointe. Stattdessen Komma, Klammer oder ein eigener Satz.
- Doppelpunkte sparsam, kein Doppelpunkt-Effekt („Das Ergebnis: …“).
- Klammern für Präzisierungen und wörtliche Zitate aus Quellen sind normal und menschlich.

### 6. Aufzählungen und Formatierung
- Keine Dreier-Aufzählungen als Reflex („A, B und C“ in jedem zweiten Satz). Zwei Elemente, vier Elemente oder ein ausformulierter Satz sind oft natürlicher. Ausgenommen sind Dreiergruppen, die die Quelle vorgibt (Modelldimensionen, Definitionen), und Autorennamen.
- Kein Fettdruck im Fließtext, keine Stichpunktlisten, wenn die Aufgabe Fließtext verlangt. Überschriften nur entsprechend der Gliederung.

### 7. Absätze
- Absätze unterschiedlich lang halten: im Mittel 65–110 Wörter pro Absatz, bei 900 Wörtern also 8–12 Absätze. Die Satzzahlen der Absätze sollen etwa so streuen wie 2, 3, 4, 5, 6, 9: der längste Absatz mindestens dreimal so lang wie der kürzeste (in Wörtern etwa 40 bis 160), nicht mehr als drei Absätze mit gleicher Satzzahl. Ein Ein-Satz-Absatz nur für eine echte Folgerung, nicht als Pseudo-Überschrift.
- Absätze nicht mit einem zusammenfassenden Kommentarsatz beenden („Somit wird deutlich, dass …“). Der letzte Satz bringt Inhalt oder leitet über.

### 8. Persönlicher Wortschatz
Der Text soll nach dem Nutzer klingen, nicht nach einem generischen Autor. `references/persoenlicher-wortschatz.md` listet Wörter und Wendungen aus seinen eigenen Formulierungen, abgeglichen mit den Korpora:
- ✅-Wörter (menschentypisch) bevorzugen, wo sie passen, z. B. „im Vergleich zu“, „basierend auf“, „anhand von“, „Beispiel“, „Thema“, „Theorie“.
- ⚪-Wörter normal verwenden; ⚠️-Wörter erlaubt, aber nicht häufen.
- Nie Wörter erzwingen, nur damit sie vorkommen. Gängige Abkürzungen (z. B., d. h., u. a., bzw.) nur dort, wo sie natürlich stehen, nie einstreuen; „wie z. B.“ ist doppelt.

### 9. Personenbezeichnungen: generisches Maskulinum
Der Nutzer wünscht das generische Maskulinum („die Mitarbeiter“, „die Teilnehmer“, „die Studenten“, „die Dozenten“). Keine gendergerechten Ersatzformen wie „Mitarbeitende“, „Teilnehmende“, „Studierende“, „Bewerbende“, „Lehrende“ und kein Gendersternchen – diese Formen sind zudem ein messbares KI-Signal. Erlaubt sind lexikalisierte Substantivierungen und Rechtsbegriffe: „Beschäftigte“, „Befragte“, „Angestellte“, „Vorgesetzte“, „Auszubildende“, „Arbeitnehmer“. Ausnahme: Aufgabenstellung oder Prüfungsordnung verlangen ausdrücklich etwas anderes, oder es wird wörtlich zitiert.

### 10. Inhaltlich konkret bleiben
- Behauptungen mit Quelle, Zahl, Beispiel oder Begründung versehen statt mit Wertungsadjektiven.
- Einschränkungen und Gegenpositionen dort nennen, wo sie fachlich hingehören, nicht als symmetrische Abwägungsformel.
- **Keine erfundenen Quellen, Zahlen oder Zitate.** Zitierstil aus der Vorgabe übernehmen, sonst APA 7 (an der MBS Pflicht): (Müller, 2019), zwei Autoren (Müller & Meier, 2019), ab drei (Müller et al., 2020), im Satz genannt „Nach Müller (2019) …“; Seitenzahl nur bei wörtlichen Zitaten (Müller, 2019, S. 12). Seitenzahlen nur, wenn sie sicher bekannt sind, nie schätzen. Wörtliche Zitate über 40 Wörter als eingerücktes Blockzitat ohne Anführungszeichen, in Markdown mit `>` (die Analyse blendet es dann aus). Rechtsakte und amtliche Dokumente mit amtlicher Bezeichnung zitieren („Richtlinie (EU) 2022/2464, Art. 29b“), die Fundstelle möglichst in den Satz holen („nach Art. 29b der Richtlinie (EU) 2022/2464“) oder in eine Fußnote; höchstens eine Klammer pro Satz. Eine Abkürzung nur dann bei der ersten Verwendung in Klammern einführen, wenn sie mindestens dreimal vorkommt. `[Quelle]` nur für empirische Zahlen, Fälle und Befunde, deren Beleg nicht sicher bekannt ist, und nach dem Text kurz auflisten, wofür noch ein Beleg fehlt.
- **Umfang:** Längenangaben des Nutzers beziehen sich auf sein Textprogramm (Fließtext mit Belegen, ohne Überschrift). `coach.py` zählt ohne Klammerbelege und liegt je nach Belegdichte 2–7 % darunter. Satzlängen zählen ebenfalls ohne Klammerbelege.
- **Englische Teile** (an der MBS immer das Abstract): Die Regeln und Kennzahlen dieses Skills gelten nur für deutschen Fließtext. Ein englisches Abstract nach den Vorgaben der Hochschule schreiben und nicht mit `coach.py` messen.

## Selbstkontrolle vor der Ausgabe

- [ ] Satzlängen breit verteilt: 5–8 lange (davon 1–2 über 40), 4–6 kurze, die Hälfte 12–25 Wörter; Phasen statt Zickzack
- [ ] 4–7 Konnektoren aus der Zählliste pro 900 Wörter, kein „Dies zeigt …“, kein „Insgesamt zeigt sich“
- [ ] Etwa jeder dritte Satz mit einem Nebensatz, Satzklammern Ø 6–8 Wörter
- [ ] Keine Semikolons, keine Gedankenstriche, keine Floskeln aus `references/ki-muster.md`
- [ ] Fachbegriffe durchgehend gleich benannt, aber keine mechanische Wiederholung von Namen
- [ ] 8–12 Absätze pro 900 Wörter, ungleich lang
- [ ] Generisches Maskulinum, keine Ersatzformen („Mitarbeitende“)
- [ ] Coach ausgeführt: Ziel erreicht und nichts im Kasten „Menschlicher als typisch“ (sonst nach Schritt 4 zurücknehmen)
