# Vorher/Nachher-Beispiele

Neutrale Beispielsätze, je eine Technik. „Vorher“ ist typischer Claude-Stil, „Nachher“ entspricht dem, was in echten Hochschularbeiten häufiger vorkommt. Der Inhalt bleibt jeweils gleich. Die Zahlen in Klammern stammen aus der Kalibrierung (`zielwerte.md`, `ki-muster.md`).

## 1. Zusammengehörige Sätze bündeln, nominal verdichten

**Vorher** (3 Sätze mit je 10 Wörtern):
> Viele mittelständische Unternehmen investieren derzeit verstärkt in die betriebliche Ausbildung. Sie wollen damit dem wachsenden Fachkräftemangel in technischen Berufen begegnen. Die Kosten der Ausbildung steigen allerdings seit einigen Jahren deutlich.

**Nachher** (1 Satz mit 27 Wörtern):
> Trotz der seit einigen Jahren deutlich steigenden Kosten investieren viele mittelständische Unternehmen derzeit verstärkt in die betriebliche Ausbildung, um dem wachsenden Fachkräftemangel in technischen Berufen zu begegnen.

Warum: Menschen schreiben beim Argumentieren lange, dichte Sätze. Claude reiht mittellange Sätze aneinander und knüpft mit „Sie“ und „allerdings“ an. **Maß halten:** etwa jeder sechste Satz hat 30 oder mehr Wörter, nicht jeder.

## 2. Satzklammer füllen

**Vorher:**
> Die Daten wurden erhoben. Die Erhebung fand im Frühjahr 2019 statt und erfolgte über einen Online-Fragebogen.

**Nachher:**
> Die Daten wurden im Frühjahr 2019 über einen Online-Fragebogen erhoben.

Warum: Zwischen Hilfsverb und Partizip stehen bei Menschen im Mittel etwa 7 Wörter, bei Claude etwa 5.

## 3. Konnektor streichen, nicht verschieben

**Vorher:**
> Zudem zeigen die Ergebnisse, dass jüngere Beschäftigte häufiger wechseln.

**Nicht so** (nur verschoben):
> Die Ergebnisse zeigen zudem, dass jüngere Beschäftigte häufiger wechseln.

**Nachher:**
> Jüngere Beschäftigte wechseln nach den Ergebnissen häufiger.

Warum: Claude verwendet rund 10 Konnektoren pro 1000 Wörter, Menschen rund 6. Verschieben ändert die Dichte nicht.

## 4. Über das Nomen anknüpfen, nicht über Possessiva

**Vorher:**
> Das Förderprogramm richtet sich an Betriebe mit weniger als 50 Beschäftigten. Seine Wirkung ist bislang kaum untersucht.

**Nachher:**
> Das Förderprogramm richtet sich an Betriebe mit weniger als 50 Beschäftigten. Die Wirkung des Programms ist bislang kaum untersucht.

Warum: Possessiv-Anfänge („Seine“, „Ihre“) sind bei Claude doppelt so häufig. Ein schlichtes „Dies“ oder „Dabei“ am Satzanfang ist dagegen in menschlichen Arbeiten üblich und darf stehen.

## 5. Einen Begriff durchhalten

**Vorher:**
> Die Kunden reagieren empfindlich auf Preisänderungen. Konsumenten nehmen schwankende Preise häufig als unfair wahr, und Verbraucher wechseln dann den Anbieter.

**Nachher:**
> Die Kunden reagieren empfindlich auf Preisänderungen. Schwankende Preise nehmen die Kunden häufig als unfair wahr und wechseln dann den Anbieter.

Warum: Claude variiert Begriffe künstlich, der Wortschatz wird dadurch vielfältiger als bei Menschen (MATTR 0,80 statt 0,77). In Fachtexten ist Wiederholung präzise.

## 6. Floskel durch die konkrete Aussage ersetzen

**Vorher:**
> Die Unternehmenskultur spielt eine zentrale Rolle für die Bindung der Mitarbeiter.

**Nachher:**
> Wer die Unternehmenskultur positiv bewertet, bleibt nach Müller (2018) im Mittel zwei Jahre länger im Betrieb.

Warum: „spielt eine zentrale Rolle“ sagt nicht, *wie* und *wie stark*. Die konkrete Aussage steht nur, wenn sie in der Quelle steht. Fehlt sie, schlicht formulieren: „Die Unternehmenskultur beeinflusst die Bindung der Mitarbeiter.“

## 7. „lässt sich“ und Ankündigungen

**Vorher:**
> Aus den Interviews lässt sich ableiten, dass kleine Betriebe kaum strategisch rekrutieren.

**Nachher:**
> Kleine Betriebe rekrutieren nach den Interviews kaum strategisch.

**Oder mit Passiv ohne Modalverb:**
> Prozesse lassen sich automatisieren. → Prozesse werden automatisiert.

Warum: „lässt/lassen sich“ ist bei Claude rund 3,5-mal so häufig. Ankündigungen wie „lässt sich festhalten, dass“ kündigen nur an, was danach ohnehin kommt.

## 8. Gegenfolie nur, wenn jemand sie vertritt

**Vorher:**
> Employer Branding ist nicht bloß ein Marketinginstrument, sondern eine strategische Aufgabe der Personalarbeit.

**Nachher:**
> Employer Branding ist eine strategische Aufgabe der Personalarbeit.

Warum: „nicht X, sondern Y“ ist bei Claude rund dreimal so häufig. Die Gegenfolie bleibt nur, wenn eine Quelle X tatsächlich behauptet, dann mit Beleg.

## 9. Zeichensetzung

**Vorher:**
> Die Befragung war anonym; dennoch antworteten nur 38 Prozent. Der Grund liegt nahe – die Fragebögen waren sehr lang.

**Nachher:**
> Die Befragung war anonym. Trotzdem antworteten nur 38 Prozent, vermutlich wegen der sehr langen Fragebögen.

Warum: Semikolons kommen in menschlichen Hochschularbeiten kaum vor (Median 0), Gedankenstriche sind eine Nutzervorgabe.

## 10. Absätze ungleich lang

**Vorher:** fünf Absätze mit je 5 bis 6 Sätzen.

**Nachher:** ein Absatz mit 8 Sätzen für die Herleitung, einer mit 4 Sätzen, und die zentrale Folgerung als eigener Absatz mit 1 bis 2 Sätzen.

Warum: Die Zahl der Sätze pro Absatz schwankt bei Menschen deutlich stärker (Variationskoeffizient 0,48 statt 0,30).

## 11. Personenbezeichnungen

**Vorher:**
> Die befragten Mitarbeitenden und Führungskräfte bewerten die Maßnahme unterschiedlich.

**Nachher:**
> Die befragten Mitarbeiter und Führungskräfte bewerten die Maßnahme unterschiedlich.

Warum: Nutzervorgabe (generisches Maskulinum), sofern die Aufgabenstellung nichts anderes verlangt. Wörtliche Zitate bleiben unverändert.
