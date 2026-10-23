---
name: humanisieren
description: Bringt einen deutschen Hochschultext (Hausarbeit, Bachelorarbeit, Aufgabenbearbeitung) in einer Messschleife auf das Stilniveau menschlicher Hochschultexte. Standard ist der Coach-Modus – messen, dann konkrete satzgenaue Arbeitsaufträge geben („Satz 7 und 8 verbinden“, „Semikolon in Satz 12 ersetzen“, „Begriff aus Satz 3 wieder aufgreifen“), der Nutzer formuliert selbst, dann erneut messen, bis der Text so unauffällig ist wie echte Hochschularbeiten. Nur auf ausdrücklichen Wunsch überarbeitet Claude den Text selbst. Verwende diesen Skill, wenn ein Text „menschlicher“, „natürlicher“, „weniger nach KI“ klingen soll, wenn jemand Feedback zum Stil oder einen Schreib-Coach möchte, oder einen Text „durch die Schleife schicken“ will.
---

# Humanisieren – Stil-Coach mit Messschleife

Ziel: ein Text, dessen messbare Stilmerkmale denen echter Hochschularbeiten entsprechen – bei unverändertem Inhalt. Gemessen wird immer mit Skripten, nie geschätzt.

Skripte (falls `${CLAUDE_PLUGIN_ROOT}` nicht ersetzt ist: `find ~/.claude -path '*humanisieren/scripts/coach.py'`):
- Coach: `python3 "${CLAUDE_PLUGIN_ROOT}/skills/humanisieren/scripts/coach.py" DATEI --verlauf DATEI.coach.json`
- Analyse (Detailwerte): `python3 "${CLAUDE_PLUGIN_ROOT}/skills/text-analyse/scripts/analyse.py" DATEI`
- Inhaltscheck: `python3 "${CLAUDE_PLUGIN_ROOT}/skills/humanisieren/scripts/inhalt_check.py" ORIGINAL NEU --verlauf DATEI.coach.json` (mit `--verlauf` gelten Wörter, die der Coach selbst zum Ersetzen empfohlen hat, nicht als Verlust)
- KI-Protokoll: `python3 "${CLAUDE_PLUGIN_ROOT}/skills/humanisieren/scripts/ki_protokoll.py" DATEI.coach.json --kapitel "2 Grundlagen" --prompt "…"` (Zeile für die KI-Dokumentationstabelle der Hochschule)

## Welcher Modus?

**Coach-Modus (Standard).** Immer, wenn nicht ausdrücklich „schreib es um“ / „überarbeite du es“ verlangt wird – und grundsätzlich für Texte, die als eigene Leistung abgegeben werden (Hausarbeit, Bachelorarbeit, Prüfungsleistung mit Eigenständigkeitserklärung). Claude formuliert dabei keine Sätze des Textes neu, sondern sagt präzise, was zu ändern ist. Die Worte stammen vom Nutzer. Das entspricht Hochschulregeln, die KI als Feedbackwerkzeug für selbst geschriebene Texte erlauben (z. B. MBS Research Guidelines 2026, Teil C 4.3, Kurzfassung in `../menschlich-schreiben/references/hochschulvorgaben-mbs.md`); dokumentiert wird die Nutzung trotzdem (Schritt 7).

**Überarbeiten-Modus.** Nur wenn der Nutzer ausdrücklich möchte, dass Claude selbst umschreibt. Dann vorher einmal kurz darauf hinweisen: Von Claude formulierter Text trägt Anthropics Text-Wasserzeichen (statistisch in der Wortwahl, für Bildungseinrichtungen über eine Erkennungs-Schnittstelle prüfbar). Stilistische Überarbeitung ändert daran nichts. Für eigene Prüfungsleistungen den Coach-Modus empfehlen und auf die KI-Regeln der Hochschule hinweisen. An der MBS gelten von Claude umformulierte Sätze als KI-Formulierungen, die auch dokumentiert nur sparsam in die Arbeit dürfen (Teil C, 4.2).

Niemals Techniken anbieten oder anwenden, die darauf zielen, Wasserzeichen oder KI-Detektoren zu umgehen.

## Coach-Modus

1. **Text als Datei.** Liegt der Text nur im Chat vor, als `.md` speichern (Arbeitsordner oder `/tmp/coach/`). Bei mehr als ~2.500 Wörtern kapitelweise coachen.
2. **Messen und coachen** (lange Texte misst der Coach automatisch abschnittsweise zu ~800 Wörtern und zeigt, welcher Abschnitt am KI-nächsten ist – dort anfangen):
   ```bash
   python3 ".../coach.py" text.md --verlauf text.coach.json
   ```
   Der Bericht enthält Score, Modell-Einschätzung, die 3–4 wichtigsten Hebel (mit Wert und Zielbereich) und konkrete Stellen, Absatz für Absatz. **Vorgaben** des Nutzers (generisches Maskulinum, keine Gedankenstriche) stehen in einem eigenen Abschnitt: Sie ändern den Score nicht und zählen nicht zum Hinweis-Limit. Meldet der Coach **verklebte Wörter** (aus PDF-Kopien, z. B. „Modell,wiesichdie…“), diese zuerst trennen lassen, sonst sind die übrigen Messwerte verzerrt. Bei hohem Anteil wörtlicher Zitate weist der Coach darauf hin, dass die Messung nur bedingt aussagekräftig ist. Der Coach gibt nur so viele Aufträge, wie bis zum menschlichen Median nötig sind, nie Aufträge innerhalb wörtlicher Zitate, und keine Bündelungen, die eine Aussage einer fremden Quelle zuschreiben würden. Bei langen Texten beziehen sich die Stellen auf den Abschnitt, der am KI-nächsten ist.
3. **Dem Nutzer zurückgeben:** die Hebel in eigenen Worten kurz erklären und die konkreten Stellen als Arbeitsliste ausgeben – mit Satznummer und Satzanfang, damit er sie findet. Pro Runde höchstens ~10–15 Aufträge, die wichtigsten zuerst.
   - Erklären *was* und *warum* („Absatz 3 hat fünf Sätze mit 17–21 Wörtern. Menschen mischen stärker: einen Satz deutlich kürzen oder zwei zu einem langen verbinden.“).
   - Keine fertigen Ersatzsätze für seinen Text liefern. Allgemeine Beispiele zur Technik aus `references/techniken.md` sind erlaubt (an fremden Beispielsätzen, nicht an seinem Text).
   - Bei Floskeln die Ersatzstrategie nennen („Ergebnis direkt nennen, ohne Ankündigung“), nicht die fertige Formulierung.
4. **Nutzer überarbeitet selbst** und meldet sich (oder speichert die Datei). Dann Schritt 2 mit derselben `--verlauf`-Datei wiederholen: Der Bericht zeigt den Fortschritt (Score vorher → nachher, welche Kennzahlen besser oder schlechter wurden).
   - Meldet der Bericht **„Überkorrektur“** oder **„Nebenwirkung“**, ist eine Kennzahl über den menschlichen Bereich hinaus auf die andere Seite gekippt (z. B. zu viele lange Sätze, Lesbarkeit zu schwer) oder als Nebenwirkung schlechter geworden. Der Coach setzt die verursachenden Hinweistypen dann aus und gibt Gegenaufträge („Satz X teilen“). Das dem Nutzer so erklären: Ziel ist die menschliche Verteilung, nicht ein Extrem.
   - Hinweise mit dem Zusatz „schon in Runde N genannt“ darf der Nutzer überspringen, wenn sie nicht passen.
   - **„Menschlicher als typisch (kein Auftrag)“**: Eine Kennzahl liegt jenseits des Bands echter Texte, aber auf der der KI abgewandten Seite (z. B. sehr viele lange Sätze, sehr wenige Konnektoren). Bei einem Text des Nutzers ist das kein Fehler und kostet keine Punkte. Bei einem von Claude geschriebenen Entwurf (Skill menschlich-schreiben) entsteht es meist durch zu konsequentes Befolgen der Regeln und wird zurückgenommen.
   - **„Im Bereich der Messunsicherheit“**: Der Text liegt so knapp unter dem Ziel, dass der Unterschied Rauschen sein kann. Höchstens den einen genannten Auftrag umsetzen, nicht weiter an Zahlen drehen.
   - **„Modell-Ziel erreicht, dem Score fehlen noch …“** heißt: Nur noch die genannten Hebel bearbeiten, alles andere ist erledigt.
   - **„Wirkung geprüft“**: Ein befolgter Auftragstyp hat seine Kennzahl nicht verbessert; der Coach wechselt die Technik (z. B. Absätze zusammenlegen statt teilen) oder setzt den Typ aus.
   - **Diagnose bei Stillstand**: Bleibt das Modell unter dem Ziel und gibt es kaum noch Stellen, listet der Coach, welche Merkmale die Lücke ausmachen und ob sie mit Einzelkorrekturen erreichbar sind. Dominiert das **Funktionswort-Profil** (Verteilung kleiner Wörter wie „als“, „sich“, „es“, „werden“), dem Nutzer ehrlich sagen: Dieses Profil entsteht beim eigenen Formulieren und ändert sich durch Satz-Umbauten kaum. Wirksam ist, einzelne Absätze mit demselben Inhalt in eigenen Worten neu zu schreiben. Keine Wörter einstreuen, um die Zahl zu drücken.
   - Meldet der Bericht **„Mechanisch verlängert“** (Ø-Satzlänge um mehr als 10 % gestiegen, Wörter pro Teilsatz und Satzklammer aber nicht), zählt die Runde nicht als Fortschritt: Der Nutzer hat vermutlich Teilsätze angehängt. Dann auf Bündeln und nominales Verdichten verweisen (`references/techniken.md`, Abschnitt Satzlänge).
   - Wird eine Kennzahl besser, während andere schlechter werden, das offen benennen. Ziel ist der Gesamtstil, nicht eine einzelne Zahl.
5. **Inhalt sichern:** Nach jeder Runde `inhalt_check.py ORIGINAL NEU --verlauf text.coach.json` gegen die Ausgangsfassung laufen lassen und fehlende Zahlen, Quellen oder Zitate melden. Außerdem selbst darauf achten, ob beim Zusammenführen von Sätzen eine Aussage einer anderen Quelle zugeordnet oder eine Begründung umgedreht wurde – das erkennt das Skript nicht.
6. **Fertig**, wenn der Coach „Ziel erreicht“ meldet (Modell-Wahrscheinlichkeit „menschlich“ und der einseitige Score über Schwellen, die jeweils 90 % echter Hochschulabschnitte erreichen) oder der Nutzer zufrieden ist. Der einseitige Score zählt nur Abweichungen in Richtung KI; wer in manchem „menschlicher als typisch“ schreibt, verliert dadurch keine Punkte. Das Modell belohnt Übertreibung jenseits des menschlichen Bands nicht. Einzelne rote Kennzahlen sind kein Grund weiterzumachen: Auch echte Arbeiten haben bei 800 Wörtern im Mittel etwa sechs rote Kennzahlen, weil einzelne Kennzahlen auf kurzen Texten stark streuen. Nicht jede rote Zahl „reparieren“ lassen.
7. **Dokumentieren** (bei Prüfungsleistungen; viele Hochschulen verlangen ein Verzeichnis der KI-Nutzung, an der MBS die Tabelle nach Anhang 3): Vor jeder Runde eine datierte Fassung sichern lassen (z. B. `kapitel2_2026-10-23.md`); sie belegt den eigenen Arbeitsprozess. Am Ende die Tabellenzeile erzeugen:
   `ki_protokoll.py DATEI.coach.json --kapitel "2 Theoretische Grundlagen" --prompt "…"`
   Als Prompts 1–3 tatsächliche Bitten des Nutzers aus dem Gespräch einsetzen, als Werkzeug den eigenen Modellnamen, falls bekannt (`--werkzeug "Claude … in Claude Code mit Plugin humanwriting-de"`), bei englischer Arbeit `--sprache en`, mehrere Kapitel mit je einem Verlauf und `--kapitel`. Die Zeile ist ein Vorschlag: Der Nutzer prüft sie und ergänzt, was das Skript nicht weiß (z. B. weitere KI-Werkzeuge).

Fragen des Nutzers („Wie mache ich einen Satz länger, ohne Inhalt zu erfinden?“) mit den Techniken aus `references/techniken.md` beantworten, gern mit eigenen neutralen Beispielsätzen.

Was die Daten sagen (für Erklärungen an den Nutzer): Claude bleibt im mittleren Satzlängen-Band; Menschen streuen in beide Richtungen, mit einigen langen, nominal verdichteten Sätzen und einigen kurzen. Ein streng abwechselnder Rhythmus kurz–lang–kurz ist eher KI-typisch. Überzählige Konnektoren werden gestrichen, nicht verschoben, aber nicht auf null. Nominal- und Genitivketten sind bei Menschen häufiger und werden nicht aufgelöst. Hintergrund: `../menschlich-schreiben/references/hintergrund.md`.

## Überarbeiten-Modus

Nur nach ausdrücklichem Wunsch und dem Hinweis oben.

0. Original sichern (`<name>.original.md`), Arbeitskopie `<name>.md`, Inhaltsinventar erstellen (jede Aussage, alle Zahlen, Quellen, Zitate, Fachbegriffe) als `<name>.inventar.md`.
1. `coach.py <name>.md --verlauf <name>.coach.json` – die Hebel und Stellen sind der Umschreibplan.
2. Höchstens 3–4 Hebel pro Runde, **nur die genannten Stellen** mit dem Edit-Werkzeug ändern (Techniken: `references/techniken.md`). Keine neuen Inhalte, Zahlen, Quellen oder Beispiele. Zahlen, Quellenverweise, wörtliche Zitate, Fachbegriffe, Überschriften und Fußnotenmarker bleiben unangetastet. Generisches Maskulinum, keine Gedankenstriche, keine Floskeln aus `../menschlich-schreiben/references/ki-muster.md`.
3. `coach.py` erneut (Fortschritt prüfen) und `inhalt_check.py <name>.original.md <name>.md --verlauf <name>.coach.json`. Bei ❌ sofort korrigieren; jede Aussage des Inventars muss sinngleich erhalten sein. Meldet der Coach „Mechanisch verlängert“, die Änderungen der Runde durch Verdichten ersetzen statt weiter zu verlängern.
4. Wiederholen, bis „Ziel erreicht“, höchstens 6 Runden; nach zwei Runden ohne Fortschritt stoppen und erklären, woran es hängt.
5. Abschluss: Vorher/Nachher-Tabelle (Score, Modell, bewertete Kennzahlen), Ergebnis des Inhaltschecks, Pfad zur Datei. Bei Prüfungsleistungen die Zeile für das KI-Verzeichnis mit `ki_protokoll.py … --modus ueberarbeiten` anbieten.

## Grenzen (dem Nutzer bei Bedarf sagen)

- Die Kennzahlen messen Stil, nicht Urheberschaft. „Ziel erreicht“ heißt: statistisch unauffällig im Vergleich zu echten Hochschularbeiten – nicht „nicht als KI erkennbar“.
- Das Modell („X % menschlich“) ist ein Fortschrittsanzeiger dieses Werkzeugs, kein Detektor-Ergebnis.
