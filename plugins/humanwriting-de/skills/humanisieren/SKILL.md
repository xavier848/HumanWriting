---
name: humanisieren
description: Überarbeitet einen vorhandenen deutschen Text (z. B. einen KI-Entwurf einer Hausarbeit, Bachelorarbeit oder Aufgabenbearbeitung) in einer Prüfschleife, bis seine statistischen Kennzahlen im Bereich menschlicher Hochschultexte liegen, ohne den Inhalt zu verändern. Ablauf: messen → gezielt umschreiben → erneut messen und Inhalt prüfen, so lange bis alles stimmt. Verwende diesen Skill, wenn ein Text „menschlicher“, „natürlicher“, „weniger nach KI“ klingen, „humanisiert“, stilistisch überarbeitet oder „durch die Schleife geschickt“ werden soll.
---

# Humanisieren – Umschreib-Schleife mit Messung und Inhaltsprüfung

Ziel: Der Text hat danach **denselben Inhalt** (alle Aussagen, Zahlen, Quellen, Zitate, Fachbegriffe, Gliederung), aber Kennzahlen im menschlichen Zielbereich. Gemessen wird ausschließlich mit Skripten, nie geschätzt.

Skripte:
- Analyse: `python3 "${CLAUDE_PLUGIN_ROOT}/skills/text-analyse/scripts/analyse.py" DATEI [--format json]`
- Inhaltscheck: `python3 "${CLAUDE_PLUGIN_ROOT}/skills/humanisieren/scripts/inhalt_check.py" ORIGINAL NEU`
- Falls `${CLAUDE_PLUGIN_ROOT}` nicht ersetzt ist: `find ~/.claude -path '*text-analyse/scripts/analyse.py'` bzw. `-path '*humanisieren/scripts/inhalt_check.py'`.

Techniken je Kennzahl: `references/techniken.md`. Floskeln mit Ersatz: `../menschlich-schreiben/references/ki-muster.md`. Zielwerte: `../menschlich-schreiben/references/zielwerte.md`.

## Schritt 0: Vorbereiten

1. Text als Datei sichern: `<name>.original.md` (wird nie verändert) und Arbeitskopie `<name>.md`. Liegt der Text nur im Chat vor, beide Dateien anlegen (Arbeitsordner oder `/tmp/humanisieren/`).
2. **Lange Texte abschnittsweise:** Bei mehr als ~2.500 Wörtern Kapitel für Kapitel durch die Schleife schicken (jedes Kapitel hat genug Sätze für stabile Werte) und am Ende das Gesamtdokument noch einmal messen.
3. **Inhaltsinventar** erstellen und als `<name>.inventar.md` speichern: nummerierte Liste jeder inhaltlichen Aussage (eine Zeile pro Aussage, knapp), plus alle Zahlen, Quellenverweise, wörtlichen Zitate, Fachbegriffe und Eigennamen. Das Inventar ist der Maßstab für „Inhalt gleich“.

## Schritt 1: Messen

```bash
python3 ".../analyse.py" <name>.md --format json --ohne-saetze > /tmp/runde0.json   # Kennzahlen
python3 ".../analyse.py" <name>.md --stellen 40                                      # Bericht + Stellen
```
Notiere Score, Modell-Wahrscheinlichkeit und alle bewerteten Kennzahlen mit Status 🔴/🟡, Richtung (↑/↓) und Gewicht.

## Schritt 2: Umschreibplan für diese Runde

- Wähle **höchstens 3–4 Hebel** pro Runde: zuerst rote Kennzahlen mit dem höchsten Gewicht, dann gelbe.
- Ordne jedem Hebel die konkreten Sätze/Absätze zu (Satznummern und Markierungen aus dem Bericht, z. B. `gleichfoermig`, `konnektor_anfang`, `muster:…`).
- Plane die Technik aus `references/techniken.md`. Beispiel: „Satzlängen-Variation ↑: in Abs. 2 Sätze 5+6 zu einem Satz mit Relativsatz verbinden, Satz 9 in zwei Sätze teilen, nach Satz 12 einen kurzen Folgerungssatz bilden (Inhalt aus Satz 12, nicht neu).“

## Schritt 3: Gezielt umschreiben

Regeln:
- **Nur die geplanten Stellen ändern.** Den übrigen Text nicht anfassen. Kein Komplett-Neuschreiben pro Runde – das verschiebt den Inhalt.
- **Keine neuen Inhalte:** keine neuen Beispiele, Zahlen, Quellen, Behauptungen, Wertungen. Umstellen, Zusammenführen, Teilen, Kürzen von Füllwörtern und Ersetzen von Floskeln durch die schlichte Aussage sind erlaubt.
- **Unantastbar:** Zahlen, Quellenverweise (exakt), wörtliche Zitate, Fachbegriffe, Eigennamen, Überschriften, Fußnotenmarker, Abbildungs-/Tabellenverweise.
- Fachbegriffe vereinheitlichen statt variieren. Wenn der Entwurf für dieselbe Sache drei Wörter benutzt, auf den Hauptbegriff zurückführen (das senkt die zu hohe Wortschatzvielfalt und erhöht die Begriffsaufnahme).
- Keine neuen Floskeln einbauen (ki-muster.md), keine Gedankenstriche.
- Die Datei mit dem Edit-Werkzeug ändern (gezielte Ersetzungen), nicht neu schreiben.

## Schritt 4: Erneut messen und Inhalt prüfen

```bash
python3 ".../analyse.py" <name>.md --stellen 40
python3 ".../inhalt_check.py" <name>.original.md <name>.md
```
- **Inhaltscheck mit ❌** (fehlende/neue Zahl, Quelle, Zitat, Fußnote): sofort korrigieren, bevor es weitergeht.
- Warnungen prüfen („Begriff verschwunden“, „Umfang“): Bei Verlust eines Fachbegriffs oder >15 % Längenänderung nachbessern.
- **Inventar-Abgleich durch dich:** Jede Aussage des Inventars muss im neuen Text sinngleich vorkommen; keine Aussage darf hinzugekommen sein. Bei Abweichung zurücknehmen.
- Hat sich eine Kennzahl verschlechtert, die vorher grün war, diese Änderung prüfen und gegebenenfalls zurücknehmen.

## Schritt 5: Wiederholen oder beenden

Wiederhole Schritt 2–4. **Beenden**, sobald eine Bedingung erfüllt ist:
- ✅ Ziel erreicht: keine bewertete Kennzahl rot **und** Menschlichkeits-Score ≥ 80 **und** Inhaltscheck ohne ❌.
- ⏹ 6 Runden erreicht.
- ⏹ Zwei Runden ohne Verbesserung des Scores → stoppen und erklären, welche Kennzahl sich nicht ohne Inhaltsänderung bewegen lässt.

## Schritt 6: Abschlussbericht

Dem Nutzer ausgeben:
1. Tabelle **Vorher → Nachher** für Score, Modell-Wahrscheinlichkeit und jede bewertete Kennzahl (Wert, Zielbereich, Status).
2. Anzahl Runden und welche Hebel benutzt wurden.
3. Ergebnis des Inhaltschecks und Bestätigung des Inventar-Abgleichs (oder offene Punkte).
4. Den überarbeiteten Text bzw. den Pfad zur Datei.

Hinweis an den Nutzer, wenn zutreffend: Die Kennzahlen messen Stilstatistik. Sie garantieren nicht, wie ein kommerzieller KI-Detektor urteilt.
