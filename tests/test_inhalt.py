"""Tests für inhalt_check.py und die Regex-Muster in ki_muster.json.

Testbatterie: K* = korrekt umformuliert (darf keinen harten Fund melden),
F* = absichtlich verfälscht (jede Verfälschung in PRUEFUNGEN muss gemeldet werden).
"""
import json
import os
import re
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
import inhalt_check  # noqa: E402

MUSTER_PFAD = os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "data", "ki_muster.json")

# ---------------------------------------------------------------------------
# Testbatterie
# ---------------------------------------------------------------------------

K1_ALT = """## 2.1 Digitalisierung in KMU

Kleine und mittlere Unternehmen (KMU) stellen in Deutschland rund 99 % aller Unternehmen und beschäftigen etwa 55 % der sozialversicherungspflichtig Beschäftigten (IfM Bonn 2022). Trotz dieser wirtschaftlichen Bedeutung liegt der Digitalisierungsgrad von KMU deutlich unter dem von Großunternehmen. Laut dem Digitalisierungsindex erreichten KMU im Jahr 2021 einen Wert von 104,3 Punkten, Großunternehmen dagegen 128,9 Punkte (BMWK 2022, S. 14).[^1]

Als Hauptgründe nennen die befragten Unternehmen fehlende Fachkräfte, hohe Investitionskosten und Unsicherheit über den Nutzen. Müller (2019) zeigt in einer Befragung von N = 849 Betrieben, dass vor allem Unternehmen mit weniger als 50 Mitarbeitenden zögern. Die Digitalisierung wird dort häufig als „zusätzliche Belastung im ohnehin knappen Tagesgeschäft“ wahrgenommen (Schmidt 2020, S. 77).

Gleichzeitig zeigen Fallstudien, dass gezielte Förderprogramme wirken. Das Programm „Digital Jetzt“ unterstützte bis Ende 2023 mehr als 12.000 Vorhaben mit insgesamt 250 Mio. Euro. Die ERP-Systeme und Cloud-Lösungen, die dabei eingeführt wurden, steigerten die Produktivität der geförderten Betriebe im Mittel um 7,5 %. Ob dieser Effekt dauerhaft ist, bleibt offen, da Langzeitdaten bisher fehlen.

[^1]: Der Index wird jährlich im Auftrag des BMWK erhoben.
"""

K1_NEU = """## 2.1 Digitalisierung in KMU

In Deutschland gehören rund 99 % aller Unternehmen zu den kleinen und mittleren Unternehmen (KMU), und sie beschäftigen etwa 55 % der sozialversicherungspflichtig Beschäftigten (IfM Bonn 2022). Beim Digitalisierungsgrad liegen KMU trotzdem klar hinter Großunternehmen. Der Digitalisierungsindex weist für das Jahr 2021 bei KMU 104,3 Punkte aus, bei Großunternehmen 128,9 Punkte (BMWK 2022, S. 14).[^1]

Die befragten Unternehmen nennen vor allem fehlende Fachkräfte, hohe Investitionskosten und Unsicherheit über den Nutzen. Müller (2019) hat N = 849 Betriebe befragt und zeigt, dass besonders Unternehmen mit weniger als 50 Mitarbeitenden zögern. Dort gilt die Digitalisierung oft als „zusätzliche Belastung im ohnehin knappen Tagesgeschäft“ (Schmidt 2020, S. 77).

Fallstudien zeigen aber auch, dass gezielte Förderprogramme wirken. Bis Ende 2023 hat das Programm „Digital Jetzt“ mehr als 12.000 Vorhaben mit insgesamt 250 Mio. Euro unterstützt. Mit den eingeführten ERP-Systemen und Cloud-Lösungen stieg die Produktivität der geförderten Betriebe im Mittel um 7,5 %. Ob das so bleibt, ist offen, denn Langzeitdaten fehlen bisher.

[^1]: Der Index wird jährlich im Auftrag des BMWK erhoben.
"""

# Zahlen als Wort (3 → drei, Neun → 9, 12 → zwölf), Prozent → %
K2_ALT = """## 3 Methodik

Für die Untersuchung wurden im Zeitraum von März bis Mai 2022 insgesamt 3 Pflegeeinrichtungen in Sachsen ausgewählt. In jeder Einrichtung führten zwei Interviewerinnen leitfadengestützte Interviews mit Pflegefachkräften durch. Die Stichprobe umfasste 24 Personen, davon waren 10 Prozent männlich. Die Interviews dauerten zwischen 35 und 70 Minuten und wurden vollständig transkribiert.

Die Auswertung folgte der qualitativen Inhaltsanalyse nach Mayring (2015). Das Kategoriensystem wurde zunächst deduktiv aus dem Forschungsstand abgeleitet und anschließend induktiv am Material erweitert. Zwei Personen kodierten unabhängig voneinander 20 % des Materials; die Übereinstimmung lag bei κ = 0,81. Abweichungen wurden im Team diskutiert und das Kategoriensystem entsprechend angepasst.

Die Pflegefachkräfte berichteten übereinstimmend von hoher Arbeitsbelastung. Im Durchschnitt betreute eine Fachkraft im Frühdienst 12 Bewohnerinnen und Bewohner. Neun von 24 Befragten gaben an, in den letzten 12 Monaten über einen Berufswechsel nachgedacht zu haben. Als wichtigste Entlastung nannten die Befragten verlässliche Dienstpläne und mehr Zeit für die direkte Pflege. Die Pflegedokumentation wurde dagegen als belastend beschrieben, weil sie viel Zeit bindet, die in der direkten Pflege fehlt.
"""

K2_NEU = """## 3 Methodik

Zwischen März und Mai 2022 wurden drei Pflegeeinrichtungen in Sachsen für die Untersuchung ausgewählt. Zwei Interviewerinnen führten in jeder Einrichtung leitfadengestützte Interviews mit Pflegefachkräften. Befragt wurden 24 Personen, 10 % davon waren männlich. Die Interviews dauerten zwischen 35 und 70 Minuten und wurden vollständig transkribiert.

Ausgewertet wurde mit der qualitativen Inhaltsanalyse nach Mayring (2015). Das Kategoriensystem wurde zuerst deduktiv aus dem Forschungsstand abgeleitet und danach induktiv am Material erweitert. 20 % des Materials kodierten zwei Personen unabhängig voneinander, die Übereinstimmung lag bei κ = 0,81. Über Abweichungen wurde im Team gesprochen, und das Kategoriensystem wurde entsprechend angepasst.

Übereinstimmend berichteten die Pflegefachkräfte von hoher Arbeitsbelastung. Eine Fachkraft im Frühdienst betreute im Durchschnitt 12 Bewohnerinnen und Bewohner. 9 von 24 Befragten haben in den letzten zwölf Monaten über einen Berufswechsel nachgedacht. Am meisten entlasten würden nach Angabe der Befragten verlässliche Dienstpläne und mehr Zeit für die direkte Pflege. Die Pflegedokumentation empfanden sie dagegen als belastend, weil sie viel Zeit bindet, die in der direkten Pflege fehlt.
"""

# Zitierform: narrativ ↔ Klammer, & ↔ und, Reihenfolge im Mehrfachzitat
K3_ALT = """## 2.2 Führung und Motivation

Die Selbstbestimmungstheorie geht davon aus, dass Menschen drei psychologische Grundbedürfnisse haben: Autonomie, Kompetenz und soziale Eingebundenheit (Deci & Ryan 2000). Werden diese Bedürfnisse am Arbeitsplatz erfüllt, steigt die intrinsische Motivation. Gagné und Deci (2005) übertragen das Modell auf Organisationen und zeigen, dass autonomieförderndes Führungsverhalten mit höherer Arbeitszufriedenheit einhergeht.

Müller (2019) zeigt in einer Längsschnittstudie mit 412 Beschäftigten, dass dieser Zusammenhang auch nach zwei Jahren stabil bleibt. Die Effekte sind allerdings moderat; die erklärte Varianz liegt bei 18 % (ebd., S. 211). Andere Studien kommen zu ähnlichen Ergebnissen (vgl. Schneider 2017; Weber et al. 2021).

Kritisch ist anzumerken, dass die meisten Untersuchungen auf Selbstauskünften beruhen. Häufig werden Führungsverhalten und Motivation mit demselben Fragebogen erhoben, was gemeinsame Methodenvarianz begünstigt (Podsakoff et al. 2003, S. 879). Für die vorliegende Arbeit wird deshalb ein Design gewählt, bei dem die Führungskräfte und die Mitarbeitenden getrennt befragt werden. So lässt sich prüfen, ob der Zusammenhang auch dann besteht, wenn die Angaben aus unterschiedlichen Quellen stammen.
"""

K3_NEU = """## 2.2 Führung und Motivation

Nach der Selbstbestimmungstheorie haben Menschen drei psychologische Grundbedürfnisse, nämlich Autonomie, Kompetenz und soziale Eingebundenheit (Deci und Ryan 2000). Wenn der Arbeitsplatz diese Bedürfnisse erfüllt, steigt die intrinsische Motivation. Das Modell wurde von Gagné & Deci (2005) auf Organisationen übertragen; autonomieförderndes Führungsverhalten geht demnach mit höherer Arbeitszufriedenheit einher.

In einer Längsschnittstudie mit 412 Beschäftigten bleibt dieser Zusammenhang auch nach zwei Jahren stabil (Müller 2019). Die Effekte sind allerdings moderat, die erklärte Varianz liegt bei 18 % (ebd., S. 211). Zu ähnlichen Ergebnissen kommen andere Studien (vgl. Weber et al. 2021; Schneider 2017).

Kritisch ist anzumerken, dass die meisten Untersuchungen auf Selbstauskünften beruhen. Führungsverhalten und Motivation werden oft mit demselben Fragebogen erhoben, was gemeinsame Methodenvarianz begünstigt (Podsakoff et al. 2003, S. 879). Deshalb werden in dieser Arbeit Führungskräfte und Mitarbeitende getrennt befragt. So lässt sich prüfen, ob der Zusammenhang auch dann besteht, wenn die Angaben aus unterschiedlichen Quellen stammen.
"""

# gerade Anführungszeichen, Punkt innerhalb/außerhalb
K4_ALT = """## 4.1 Begriffsbestimmung

Der Begriff "Resilienz" wird in der Literatur uneinheitlich verwendet, ähnlich wie der Begriff "Agilität". Werner definiert Resilienz als „die Fähigkeit, sich von Belastungen zu erholen und daran zu wachsen“ (Werner 1993, S. 503). In der Organisationsforschung wird der Begriff auf Unternehmen übertragen. Hier bezeichnet er nach Duchek die »Fähigkeit einer Organisation, unerwartete Ereignisse zu antizipieren, zu bewältigen und daraus zu lernen« (Duchek 2020, S. 220).

Kritiker bemängeln, Resilienz sei zu einem „Container-Begriff“ geworden, der „alles und nichts erklären“ könne (Graefe 2019, S. 12). Tatsächlich zeigen Übersichtsarbeiten, dass über 40 verschiedene Definitionen im Umlauf sind. Für diese Arbeit wird deshalb die Definition von Duchek übernommen, weil sie Resilienz als Prozess versteht und sich empirisch in drei Phasen operationalisieren lässt.

Die drei Phasen umfassen die Antizipation, die Bewältigung und die Anpassung. In der ersten Phase geht es darum, schwache Signale früh zu erkennen. In der zweiten Phase müssen Organisationen schnell handeln, auch wenn Informationen unvollständig sind. In der dritten Phase sollen sie aus dem Ereignis lernen und ihre Routinen verändern. Diese Phasen bilden die Grundlage für den Interviewleitfaden in Kapitel 5.
"""

K4_NEU = """## 4.1 Begriffsbestimmung

In der Literatur wird "Resilienz" ebenso uneinheitlich verwendet wie "Agilität". Werner versteht unter Resilienz "die Fähigkeit, sich von Belastungen zu erholen und daran zu wachsen" (Werner 1993, S. 503). Die Organisationsforschung überträgt den Begriff auf Unternehmen. Nach Duchek meint er dort die „Fähigkeit einer Organisation, unerwartete Ereignisse zu antizipieren, zu bewältigen und daraus zu lernen“ (Duchek 2020, S. 220).

Kritisch wird angemerkt, Resilienz sei ein „Container-Begriff“, der „alles und nichts erklären“ könne (Graefe 2019, S. 12). Übersichtsarbeiten zählen tatsächlich über 40 verschiedene Definitionen. Diese Arbeit übernimmt daher die Definition von Duchek, denn sie versteht Resilienz als Prozess und lässt sich empirisch in drei Phasen operationalisieren.

Die drei Phasen sind Antizipation, Bewältigung und Anpassung. Zuerst geht es darum, schwache Signale früh zu erkennen. Danach müssen Organisationen schnell handeln, auch wenn Informationen unvollständig sind. Zuletzt sollen sie aus dem Ereignis lernen und ihre Routinen verändern. Auf diesen Phasen baut der Interviewleitfaden in Kapitel 5 auf.
"""

# Schreibvarianten: Tausenderpunkt, Euro/€, Mio./Millionen, N =, m²/R² (keine Fußnoten)
K5_ALT = """## 5.2 Ergebnisse der Regressionsanalyse

Die bereinigte Stichprobe umfasst N = 1.250 Haushalte. Das durchschnittliche Nettoeinkommen lag bei 3.420 Euro pro Monat, die durchschnittliche Wohnfläche bei 92 m². Für die Analyse wurde ein lineares Regressionsmodell mit dem Energieverbrauch als abhängiger Variable geschätzt.

Das Modell erklärt einen erheblichen Teil der Varianz (R² = 0,46). Die Wohnfläche hat den stärksten Effekt: Pro zusätzlichem Quadratmeter steigt der jährliche Verbrauch um 41 kWh. Auch das Baujahr wirkt sich aus; Gebäude, die vor 1978 errichtet wurden, verbrauchen im Mittel 18 % mehr Energie als neuere Gebäude.¹ Das Einkommen hat dagegen keinen signifikanten Effekt (p = 0,21).

Hochgerechnet auf alle 41 Mio. Haushalte in Deutschland ergibt sich ein Einsparpotenzial von etwa 2,3 Mrd. Euro pro Jahr, wenn die Gebäude mit Baujahr vor 1978 auf den heutigen Standard saniert würden. Diese Schätzung ist allerdings mit Unsicherheit behaftet, weil die Stichprobe Mehrfamilienhäuser unterrepräsentiert. Zudem bleiben Rebound-Effekte unberücksichtigt, die einen Teil der Einsparung wieder aufzehren können.

¹ Als Referenz dient die Wärmeschutzverordnung von 1977.
"""

K5_NEU = """## 5.2 Ergebnisse der Regressionsanalyse

Nach der Bereinigung bleiben 1250 Haushalte in der Stichprobe. Im Durchschnitt hatten sie ein Nettoeinkommen von 3420 € im Monat und eine Wohnfläche von 92 Quadratmetern. Geschätzt wurde ein lineares Regressionsmodell, abhängige Variable ist der Energieverbrauch.

Das Modell erklärt einen erheblichen Teil der Varianz (R2 = 0,46). Den stärksten Effekt hat die Wohnfläche. Jeder zusätzliche Quadratmeter erhöht den jährlichen Verbrauch um 41 kWh. Auch das Baujahr spielt mit: Vor 1978 errichtete Gebäude verbrauchen im Mittel 18 % mehr Energie als neuere.¹ Für das Einkommen zeigt sich kein signifikanter Effekt (p = 0,21).

Rechnet man das auf alle 41 Millionen Haushalte in Deutschland hoch, ergibt sich ein Einsparpotenzial von etwa 2,3 Milliarden Euro jährlich, falls die Gebäude mit Baujahr vor 1978 auf heutigen Standard saniert würden. Die Schätzung ist allerdings unsicher, weil Mehrfamilienhäuser in der Stichprobe unterrepräsentiert sind. Außerdem bleiben Rebound-Effekte unberücksichtigt, die einen Teil der Einsparung wieder aufzehren können.

¹ Als Referenz dient die Wärmeschutzverordnung von 1977.
"""

# Klammer-Einschub mit Jahreszahl wird Hauptsatz; (HDE 2022) → der HDE (2022)
K6_ALT = """## 2.3 Entwicklung des Onlinehandels

Der Onlinehandel in Deutschland ist in den letzten Jahren stark gewachsen. Der Umsatz stieg von 48,9 Mrd. Euro im Jahr 2017 auf 87,1 Mrd. Euro im Jahr 2021 (HDE 2022). Besonders deutlich war der Anstieg während der Corona-Pandemie (2020 wuchs der Umsatz um 23 % gegenüber dem Vorjahr). Seitdem hat sich das Wachstum abgeschwächt; 2022 ging der Umsatz erstmals leicht zurück.

Die Kategorien entwickelten sich unterschiedlich. Bekleidung bleibt mit einem Anteil von 24 % die umsatzstärkste Warengruppe, während Lebensmittel trotz hoher Wachstumsraten nur auf 3 % kommen. Für den stationären Handel bedeutet das vor allem in den Innenstädten einen Rückgang der Kundenfrequenz. Viele Händler reagieren mit Multichannel-Strategien und verbinden Filiale und Onlineshop.

Ob diese Strategien wirtschaftlich tragfähig sind, ist umstritten. Heinemann (2020) argumentiert, dass nur Händler mit klarer Positionierung profitieren. Kleinere Geschäfte haben dagegen oft nicht die Mittel, um eine eigene Plattform aufzubauen, und nutzen deshalb Marktplätze wie Amazon oder eBay. Damit geraten sie in eine neue Abhängigkeit, weil die Plattformen Gebühren und Regeln vorgeben.
"""

K6_NEU = """## 2.3 Entwicklung des Onlinehandels

In den letzten Jahren ist der Onlinehandel in Deutschland stark gewachsen. Sein Umsatz stieg von 48,9 Mrd. Euro im Jahr 2017 auf 87,1 Mrd. Euro im Jahr 2021, wie der HDE (2022) berichtet. Am deutlichsten war der Anstieg während der Corona-Pandemie: 2020 wuchs der Umsatz um 23 % gegenüber dem Vorjahr. Seitdem wächst er langsamer, und 2022 ging er erstmals leicht zurück.

Die Kategorien haben sich unterschiedlich entwickelt. Bekleidung ist mit einem Anteil von 24 % weiterhin die umsatzstärkste Warengruppe, Lebensmittel kommen trotz hoher Wachstumsraten nur auf 3 %. Für den stationären Handel heißt das vor allem in den Innenstädten, dass die Kundenfrequenz sinkt. Viele Händler antworten mit Multichannel-Strategien, die Filiale und Onlineshop verbinden.

Umstritten ist, ob diese Strategien wirtschaftlich tragfähig sind. Nach Heinemann (2020) profitieren nur Händler mit klarer Positionierung. Kleineren Geschäften fehlen dagegen oft die Mittel für eine eigene Plattform, deshalb nutzen sie Marktplätze wie Amazon oder eBay. Dadurch werden sie neu abhängig, weil die Plattformen Gebühren und Regeln vorgeben.
"""

# Statistik: Vorzeichen mit U+2212, r = .45, p < .001, η², R² mit Fußnote, et al. ↔ u. a.
K7_ALT = """## 4.2 Ergebnisse

Die Skala zur Arbeitszufriedenheit erreichte eine gute Reliabilität (α = .87). Zwischen Autonomie und Zufriedenheit zeigte sich ein mittlerer Zusammenhang (r = .45, p < .001). In der Regression wirkte die Arbeitsbelastung negativ (β = −0,27; p = 0,003), das Modell erklärte 31 % der Varianz (R² = 0,31).² Der Gruppenunterschied zwischen Voll- und Teilzeitkräften war klein (η² = 0,04).

Diese Befunde stimmen mit früheren Studien überein (Hackman & Oldham 1976; Bakker et al. 2014, S. 391 f.). Bakker und Demerouti (2007) erklären den Effekt mit dem Job-Demands-Resources-Modell. Danach erschöpfen hohe Anforderungen die Beschäftigten, während Ressourcen wie Autonomie motivierend wirken.³ Die Teilnehmenden arbeiteten im Schnitt 38,5 Stunden pro Woche; ein Drittel leistete regelmäßig Überstunden.

² Korrigiertes R² = 0,29.
³ Zur Kritik am Modell vgl. Schaufeli & Taris (2014).
"""

K7_NEU = """## 4.2 Ergebnisse

Die Skala zur Arbeitszufriedenheit war gut reliabel (α = .87). Autonomie und Zufriedenheit hingen mittelstark zusammen (r = .45, p < .001). Die Arbeitsbelastung wirkte in der Regression negativ (β = −0,27; p = 0,003), und das Modell erklärte 31 Prozent der Varianz (R² = 0,31).² Klein war der Unterschied zwischen Voll- und Teilzeitkräften (η² = 0,04).

Frühere Studien kommen zu denselben Befunden (Bakker u. a. 2014, S. 391 f.; Hackman und Oldham 1976). Nach Bakker & Demerouti (2007) lässt sich der Effekt mit dem Job-Demands-Resources-Modell erklären: Hohe Anforderungen erschöpfen die Beschäftigten, Ressourcen wie Autonomie wirken dagegen motivierend.³ Im Schnitt arbeiteten die Teilnehmenden 38,5 Stunden pro Woche, und ein Drittel leistete regelmäßig Überstunden.

² Korrigiertes R² = 0,29.
³ Zur Kritik am Modell vgl. Schaufeli & Taris (2014).
"""

# Einschub mit Autor+Jahr wird Hauptsatz, Zitat über Zeilenumbruch, (2020: 14) ↔ (2020, S. 14),
# 30.000 ↔ 30 000, fünf ↔ 5, 12 ↔ zwölf
K8_ALT = """## 2.4 Homeoffice

Der Anteil der Beschäftigten im Homeoffice stieg während der Pandemie stark an (vgl. Alipour et al. 2021, die 2020 rund 30.000 Personen befragten). Im Jahr 2023 arbeitete etwa jede vierte erwerbstätige Person zumindest gelegentlich von zu Hause, das sind 2 Prozentpunkte mehr als 2021 (Destatis 2024). Laut Grunau u. a. (2020: 14) gilt Homeoffice als „Arbeitsform mit
hohem Autonomiegewinn, aber auch mit neuen Belastungen“.

Für die Fallstudie wurden fünf Unternehmen aus der Metall- und Elektroindustrie ausgewählt. In zwei davon gab es bereits vor 2020 eine Betriebsvereinbarung zum mobilen Arbeiten. Die übrigen drei regelten das Homeoffice erst in der Pandemie, meist zunächst befristet für 12 Monate.
"""

K8_NEU = """## 2.4 Homeoffice

Während der Pandemie stieg der Anteil der Beschäftigten im Homeoffice stark an. Alipour et al. (2021) befragten dazu 2020 rund 30 000 Personen. 2023 arbeitete etwa jede vierte erwerbstätige Person zumindest gelegentlich von zu Hause, 2 Prozentpunkte mehr als 2021 (Destatis 2024). Homeoffice gilt laut Grunau et al. (2020, S. 14) als „Arbeitsform mit hohem Autonomiegewinn, aber auch mit neuen Belastungen“.

Für die Fallstudie wurden 5 Unternehmen aus der Metall- und Elektroindustrie ausgewählt. Zwei davon hatten schon vor 2020 eine Betriebsvereinbarung zum mobilen Arbeiten. Die anderen 3 regelten das Homeoffice erst in der Pandemie, meist zunächst befristet für zwölf Monate.
"""

KORREKT = {f"K{i}": (globals()[f"K{i}_ALT"], globals()[f"K{i}_NEU"]) for i in range(1, 9)}

F4_ALT = """## 5.3 Geschlechterunterschiede

Von den 640 Teilnehmenden waren 62 % Frauen und 38 % Männer. Frauen bewerteten die Work-Life-Balance im Mittel mit 3,1 Punkten, Männer mit 3,6 Punkten auf einer fünfstufigen Skala. Der Unterschied ist signifikant (t = 4,2; p < 0,001). Im Vergleich zur Vorgängerstudie stieg der Anteil der Beschäftigten in Teilzeit um 5 Prozentpunkte.

In der Regression zeigt sich für die Zahl der Überstunden ein negativer Zusammenhang mit der Zufriedenheit (β = 0,27). Je mehr Überstunden die Befragten leisten, desto unzufriedener sind sie also mit ihrer Work-Life-Balance. Für das Alter ergibt sich kein Effekt. Die Ergebnisse decken sich mit früheren Befunden zur Arbeitszeit in Dienstleistungsberufen (Klein 2018).

Aus den Befunden lassen sich zwei Empfehlungen ableiten. Erstens sollten Arbeitgeber Überstunden systematisch erfassen und zeitnah ausgleichen. Zweitens sollten Teilzeitmodelle so gestaltet werden, dass sie nicht zu Nachteilen bei der Karriereentwicklung führen. Beide Maßnahmen setzen voraus, dass Führungskräfte die Arbeitszeit ihrer Teams aktiv im Blick behalten und Probleme frühzeitig ansprechen.
"""

F4_NEU = """## 5.3 Geschlechterunterschiede

Von den 640 Teilnehmenden waren 38 % Frauen und 62 % Männer. Auf der fünfstufigen Skala bewerteten Frauen die Work-Life-Balance im Mittel mit 3,6 Punkten, Männer mit 3,1 Punkten. Der Unterschied ist signifikant (t = 4,2; p < 0,001). Gegenüber der Vorgängerstudie stieg der Anteil der Beschäftigten in Teilzeit um 5 %.

Die Regression zeigt für die Zahl der Überstunden einen negativen Zusammenhang mit der Zufriedenheit (β = -0,27). Wer mehr Überstunden leistet, ist also unzufriedener mit der Work-Life-Balance. Das Alter hat keinen Effekt. Die Ergebnisse decken sich mit früheren Befunden zur Arbeitszeit in Dienstleistungsberufen (Klein 2018).

Daraus folgen zwei Empfehlungen. Arbeitgeber sollten Überstunden systematisch erfassen und zeitnah ausgleichen. Außerdem sollten Teilzeitmodelle so gestaltet werden, dass sie nicht zu Nachteilen bei der Karriereentwicklung führen. Beides setzt voraus, dass Führungskräfte die Arbeitszeit ihrer Teams aktiv im Blick behalten und Probleme frühzeitig ansprechen. Rund 70 % der Unternehmen erfassen Überstunden bislang nicht.
"""

F7_ALT = """Der Begriff "KMU" ist ebenso unscharf wie "Mittelstand". Werner nennt Resilienz "die Fähigkeit, sich nach Störungen zu erholen" (Werner 1993, S. 503). Für diese Arbeit wird die engere Definition verwendet, weil sie sich besser operationalisieren lässt.
"""

F12_ALT = """## 2.5 Forschungsstand

Die Akzeptanz digitaler Lernplattformen ist in Pflegeschulen bislang gering (Müller u. a. 2019). Ähnliche Befunde liegen für Berufsschulen vor (vgl. auch Schmidt 2018). Der Anteil der Schulen mit eigener Plattform lag 2022 bei 41 % (Statistisches Bundesamt 2023). Als Hauptgrund gilt fehlende Zeit für die Einarbeitung (ebd., S. 14). Lehrkräfte beschreiben die Plattformen als „zusätzliche Verwaltungsaufgabe ohne erkennbaren Nutzen“ (zit. n. Weber 2017, S. 88). Klein u. a. (2016) sehen die Ursache vor allem in der fehlenden technischen Unterstützung.
"""

F12_NEU = """## 2.5 Forschungsstand

In Pflegeschulen ist die Akzeptanz digitaler Lernplattformen bislang gering. Für Berufsschulen liegen ähnliche Befunde vor. 2022 hatten 41 % der Schulen eine eigene Plattform. Als Hauptgrund gilt fehlende Zeit für die Einarbeitung. Lehrkräfte beschreiben die Plattformen als „zusätzliche Verwaltungsaufgabe ohne erkennbaren Nutzen“. Manche Autoren sehen die Ursache vor allem in der fehlenden technischen Unterstützung.
"""

VERFAELSCHT = {
    # Zahl geändert (55 → 45 %), Jahreszahl geändert, Schwelle geändert
    "F1": (K1_ALT, K1_NEU.replace("etwa 55 %", "etwa 45 %").replace("für das Jahr 2021", "für das Jahr 2020")
           .replace("weniger als 50 Mitarbeitenden", "weniger als 250 Mitarbeitenden")),
    # Quelle gelöscht, langes Zitat in einem Wort verändert, kurzes Zitat verändert
    "F2": (K4_ALT, K4_NEU.replace('"die Fähigkeit, sich von Belastungen zu erholen und daran zu wachsen"',
                                  "„die Fähigkeit, sich von Belastungen zu erholen und daran zu reifen“")
           .replace(" (Graefe 2019, S. 12)", "").replace("„Container-Begriff“", "„Sammelbegriff“")),
    # Fachbegriff durch Synonym ersetzt (3× und 1×), Aussagesatz ohne Zahl gelöscht
    "F3": (K2_ALT, K2_NEU.replace("Pflegefachkräften", "Pflegekräften").replace("Pflegefachkräfte", "Pflegekräfte")
           .replace("qualitativen Inhaltsanalyse", "qualitativen Textanalyse")
           .replace(" Die Pflegedokumentation empfanden sie dagegen als belastend, weil sie viel Zeit bindet, die in der direkten Pflege fehlt.", "")),
    # vertauschte Werte, Prozentpunkte → Prozent, Vorzeichenwechsel, neue Behauptung
    "F4": (F4_ALT, F4_NEU),
    # narrative Quelle gelöscht, Zahl im Klammer-Einschub geändert
    "F5": (K6_ALT, K6_ALT.replace("Heinemann (2020) argumentiert", "Es wird argumentiert")
           .replace("(2020 wuchs der Umsatz um 23 %", "(2020 wuchs der Umsatz um 32 %")),
    # Fußnotenmarker gelöscht, dafür m² eingefügt (gleiche Anzahl hochgestellter Zeichen)
    "F6": (K5_ALT, K5_ALT.replace("neuere Gebäude.¹", "neuere Gebäude.").replace("Pro zusätzlichem Quadratmeter", "Pro zusätzlichem m²")),
    # gerade Anführungszeichen: echtes Zitat verändert
    "F7": (F7_ALT, F7_ALT.replace("nach Störungen", "nach kleinen Störungen")
           .replace("Für diese Arbeit wird die engere Definition verwendet", "Diese Arbeit verwendet die engere Definition")),
    # Vorzeichen (U+2212) gestrichen, Fußnote ² gelöscht, R² bleibt
    "F8": (K7_ALT, K7_NEU.replace("β = −0,27", "β = 0,27").replace("(R² = 0,31).²", "(R² = 0,31).")),
    # Jahr, Seite und Autor einer Quelle geändert, Quelle erfunden
    "F9": (K3_ALT, K3_NEU.replace("(Müller 2019)", "(Müller 2018)").replace("S. 879", "S. 897")
           .replace("Weber et al. 2021", "Wagner et al. 2021")
           .replace("steigt die intrinsische Motivation.", "steigt die intrinsische Motivation (Meyer 2020).")),
    # Zahlwort ersetzt (fünf → sechs), 12 → zehn
    "F10": (K8_ALT, K8_NEU.replace("5 Unternehmen", "sechs Unternehmen").replace("zwölf Monate", "zehn Monate")),
    # Fußnote getauscht ([^1] → [^2]), Anzahl bleibt gleich
    "F11": (K1_ALT, K1_NEU.replace("S. 14).[^1]", "S. 14).[^2]")),
    # gelöschte Verweise in verschiedenen Formen
    "F12": (F12_ALT, F12_NEU),
    # Skala geändert (Millionen → Milliarden), Zahl verdreht (1250 → 1520)
    "F13": (K5_ALT, K5_NEU.replace("41 Millionen", "41 Milliarden").replace("bleiben 1250", "bleiben 1520")),
    # Zitat und Quelle mit Seitenzahl erfunden
    "F14": (K6_ALT, K6_NEU.replace("vorgeben.\n", "vorgeben. Der Verband spricht von einer „dauerhaften Verschiebung "
                                                  "der Kaufgewohnheiten“ (HDE 2022, S. 5).\n")),
}

# (Beschreibung, Art, Typ, akzeptierte Werte); Art "hart" = harter Verlust/Erfindung, "warnung" = Warnung
PRUEFUNGEN = {
    "F1": [("Zahl 55 % → 45 %", "hart", "Zahl", ["55%", "45%"]), ("Jahr 2021 → 2020", "hart", "Zahl", ["2021", "2020"]),
           ("Schwelle 50 → 250", "hart", "Zahl", ["50", "250"])],
    "F2": [("Quelle (Graefe 2019) gelöscht", "hart", "Quellenverweis", ["Graefe"]),
           ("langes Zitat: wachsen → reifen", "hart", "Wörtliches Zitat", ["reifen", "wachsen"]),
           ("kurzes Zitat „Container-Begriff“ verändert", "warnung", None, ["Container-Begriff", "Sammelbegriff"])],
    "F3": [("Pflegefachkräfte → Pflegekräfte (3×)", "warnung", "Begriff verschwunden", ["pflegefac"]),
           ("Inhaltsanalyse → Textanalyse (1×)", "warnung", "Fachwort ersetzt?", ["Inhaltsanalyse"]),
           ("Aussagesatz gelöscht", "warnung", None, ["Absatz 3", "Pflegedokumentation"])],
    "F4": [("Werte vertauscht 62/38 %", "warnung", "Zahlen vertauscht?", ["62% / 38%"]),
           ("Mittelwerte vertauscht 3,1/3,6", "warnung", "Zahlen vertauscht?", ["3,1 / 3,6"]),
           ("Prozentpunkte → Prozent", "hart", "Zahl", ["5pp", "5%"]),
           ("Vorzeichen 0,27 → -0,27", "hart", "Zahl", ["-0,27"]),
           ("neue Behauptung 70 %", "hart", "Zahl", ["70%"])],
    "F5": [("narrative Quelle Heinemann (2020) gelöscht", "hart", "Quellenverweis", ["Heinemann"]),
           ("Zahl im Klammer-Einschub 23 → 32 %", "hart", None, ["32%", "23%"])],
    "F6": [("Fußnotenmarker ¹ gelöscht (m² neu)", "hart", "Fußnotenmarker", [])],
    "F7": [("Zitat in geraden Anführungszeichen verändert", "hart", "Wörtliches Zitat", ["kleinen", "nach Störungen"])],
    "F8": [("Vorzeichen −0,27 → 0,27", "hart", "Zahl", ["-0,27"]),
           ("Fußnote ² gelöscht, R² bleibt", "hart", "Fußnotenmarker", [])],
    "F9": [("Jahr 2019 → 2018", "hart", "Quellenverweis", ["Müller 2018", "Müller 2019", "Müller (2019)"]),
           ("Seite 879 → 897", "hart", "Quellenverweis", ["S. 897", "S. 879"]),
           ("Autor Weber → Wagner", "hart", "Quellenverweis", ["Wagner", "Weber"]),
           ("Quelle erfunden (Meyer 2020)", "hart", "Quellenverweis", ["Meyer"])],
    "F10": [("Zahlwort fünf → sechs", "hart", "Zahl", ["5", "6"]), ("12 → zehn", "hart", "Zahl", ["12", "10"])],
    "F11": [("Fußnote [^1] → [^2]", "hart", "Fußnotenmarker", [])],
    "F12": [("(Müller u. a. 2019) gelöscht", "hart", "Quellenverweis", ["Müller"]),
            ("(vgl. auch Schmidt 2018) gelöscht", "hart", "Quellenverweis", ["Schmidt"]),
            ("(Statistisches Bundesamt 2023) gelöscht", "hart", "Quellenverweis", ["Bundesamt"]),
            ("(ebd., S. 14) gelöscht", "hart", "Quellenverweis", ["ebd."]),
            ("(zit. n. Weber 2017, S. 88) gelöscht", "hart", "Quellenverweis", ["Weber"]),
            ("Klein u. a. (2016) gelöscht", "hart", "Quellenverweis", ["Klein"])],
    "F13": [("41 Mio. → 41 Mrd.", "hart", "Zahl", ["41Mio", "41Mrd"]), ("1250 → 1520", "hart", "Zahl", ["1250", "1520"])],
    "F14": [("Zitat erfunden", "hart", "Wörtliches Zitat", ["Kaufgewohnheiten"]),
            ("Quelle mit Seite erfunden", "hart", "Quellenverweis", ["S. 5", "HDE 2022, S. 5"])],
}


def treffer(res, art, typ, werte):
    """Einträge, die zur Prüfung passen (Werte exakt oder – ab 4 Zeichen – als Teilstring)."""
    eintraege = res["harte_verluste"] + res["erfindungen"] if art == "hart" else res["warnungen"]
    out = []
    for e in eintraege:
        if typ and e["typ"] != typ:
            continue
        w = str(e["wert"])
        if not werte or any(x == w or (len(x) > 3 and x.lower() in w.lower()) for x in werte):
            out.append(e)
    return out


def auswerten(modul):
    """Fehlalarme (korrekte Paare mit hartem Fund) und Trefferquote je Art für ein inhalt_check-Modul."""
    fehlalarm = [k for k, (a, n) in KORREKT.items() if not modul.pruefe(a, n)["ok"]]
    gefunden = {"hart": [0, 0], "warnung": [0, 0]}
    verpasst = []
    for f, pruefungen in PRUEFUNGEN.items():
        res = modul.pruefe(*VERFAELSCHT[f])
        for beschr, art, typ, werte in pruefungen:
            gefunden[art][1] += 1
            # eine Warnung gilt auch als erkannt, wenn das Skript sogar hart meldet
            ok = treffer(res, art, typ, werte) or (art == "warnung" and treffer(res, "hart", None, werte))
            gefunden[art][0] += bool(ok)
            if not ok:
                verpasst.append(f"{f}: {beschr}")
    return fehlalarm, gefunden, verpasst


class Batterie(unittest.TestCase):
    def test_korrekte_umformulierungen_ohne_harten_fund(self):
        for k, (alt, neu) in KORREKT.items():
            with self.subTest(paar=k):
                res = inhalt_check.pruefe(alt, neu)
                self.assertTrue(res["ok"], (res["harte_verluste"], res["erfindungen"]))

    def test_verfaelschungen_werden_erkannt(self):
        for f, pruefungen in PRUEFUNGEN.items():
            res = inhalt_check.pruefe(*VERFAELSCHT[f])
            for beschr, art, typ, werte in pruefungen:
                with self.subTest(paar=f, pruefung=beschr):
                    self.assertTrue(treffer(res, art, typ, werte), res)

    def test_verfaelschte_paare_nicht_ok(self):
        for f in VERFAELSCHT:
            if any(art == "hart" for _, art, _, _ in PRUEFUNGEN[f]):
                with self.subTest(paar=f):
                    self.assertFalse(inhalt_check.pruefe(*VERFAELSCHT[f])["ok"])


# ---------------------------------------------------------------------------
# Einzelne Bausteine
# ---------------------------------------------------------------------------

def werte(text):
    return [z["wert"] for z in inhalt_check.zahl_funde(text)]


class Zahlen(unittest.TestCase):
    def test_schreibvarianten_gleich(self):
        paare = [("N = 1.250", "1250"), ("3.420 Euro", "3420 €"), ("€ 3.420", "3420 EUR"), ("41 Mio.", "41 Millionen"),
                 ("2,3 Mrd. Euro", "2,3 Milliarden Euro"), ("55 %", "55 Prozent"), ("n=849", "N = 849"),
                 ("30.000", "30 000"), ("12 000", "12.000"), ("r = .45", "r = 0,45"), ("0.27", "0,27")]
        for a, b in paare:
            with self.subTest(a=a, b=b):
                self.assertEqual(werte(a), werte(b))

    def test_prozentpunkte_nicht_prozent(self):
        self.assertEqual(werte("um 5 Prozentpunkte"), ["5pp"])
        self.assertEqual(werte("um 5 Prozentpunkten"), ["5pp"])
        self.assertNotEqual(werte("um 5 Prozentpunkte"), werte("um 5 %"))

    def test_vorzeichen(self):
        self.assertEqual(werte("β = −0,27"), ["-0,27"])
        self.assertEqual(werte("β = -0,27"), ["-0,27"])
        self.assertEqual(werte("(–0,12)"), ["-0,12"])
        self.assertEqual(werte("COVID-19"), ["19"])
        self.assertEqual(werte("2019–2021"), ["2019", "2021"])

    def test_vergleichszeichen(self):
        self.assertEqual(werte("p < .001"), ["<0,001"])
        self.assertNotEqual(werte("p < 0,05"), werte("p = 0,05"))

    def test_zahlwoerter_weich(self):
        z = inhalt_check.zahl_funde("Neun von 24 Befragten, drei Fälle, außer Acht lassen, die deutsche Elf.")
        self.assertEqual([(x["wert"], x["weich"]) for x in z], [("9", True), ("24", False), ("3", True)])

    def test_zahlwort_ohne_ersatz_nur_warnung(self):
        res = inhalt_check.pruefe("Zwei Personen kodierten das Material.", "Beide Personen kodierten das Material.")
        self.assertTrue(res["ok"])
        self.assertTrue(any(w["typ"] == "Zahlwort fehlt" for w in res["warnungen"]))

    def test_kontext_bei_normalisierter_zahl(self):
        res = inhalt_check.pruefe("Etwa 55 % der Beschäftigten arbeiten in KMU.", "Etwa 45 % der Beschäftigten arbeiten in KMU.")
        fehlt = [e for e in res["harte_verluste"] if e["wert"] == "55%"]
        self.assertTrue(fehlt)
        self.assertIn("55 % der Beschäftigten", fehlt[0]["kontext_original"])


class Quellen(unittest.TestCase):
    def schluessel(self, text):
        return sorted(f["schluessel"] for f in inhalt_check.quellen(text)[0])

    def test_zitierform_egal(self):
        gleich = [("Müller (2019) zeigt das.", "Das zeigt sich (Müller 2019)."),
                  ("(Deci & Ryan 2000; Weber 2021)", "(Weber 2021; Deci und Ryan 2000)"),
                  ("(Weber et al. 2021)", "Weber u. a. (2021)"),
                  ("(Müller 2019: 14)", "(Müller 2019, S. 14)"),
                  ("(HDE 2022)", "wie der HDE (2022) berichtet"),
                  ("(vgl. Müller 2019)", "(Müller, 2019)"),
                  ("(Bundesministerium für Arbeit und Soziales 2021)", "Das Bundesministerium für Arbeit und Soziales (2021)")]
        for a, b in gleich:
            with self.subTest(a=a, b=b):
                self.assertEqual(self.schluessel(a), self.schluessel(b))
                self.assertTrue(self.schluessel(a))

    def test_keine_quelle(self):
        for t in ["(2020 wuchs der Umsatz um 23 %)", "(seit 2015)", "(2019: 45 %)", "(Stand: 2022)", "(n = 849)"]:
            with self.subTest(t=t):
                self.assertEqual(self.schluessel(t), [])

    def test_mehrere_jahre_und_seiten(self):
        self.assertEqual(self.schluessel("(Müller 2019, 2021)"), ["müller 2019", "müller 2021"])
        self.assertEqual(self.schluessel("(Müller 2019a, b)"), ["müller 2019a", "müller 2019b"])
        self.assertEqual(self.schluessel("(Müller 2019, S. 1650)"), ["müller 2019, S. 1650"])
        self.assertEqual(self.schluessel("(Müller 2019, S. 12; ebd., S. 14)"), ["ebd., S. 14", "müller 2019, S. 12"])

    def test_einschub_wird_hauptsatz(self):
        alt = "Der Anteil stieg stark an (vgl. Alipour et al. 2021, die 2020 rund 30.000 Personen befragten)."
        neu = "Der Anteil stieg stark an. Alipour et al. (2021) befragten dazu 2020 rund 30.000 Personen."
        self.assertTrue(inhalt_check.pruefe(alt, neu)["ok"])
        self.assertFalse(inhalt_check.pruefe(alt, neu.replace("2020 rund", "2019 rund"))["ok"])

    def test_verweis_im_fliesstext_aufgeloest_nur_warnung(self):
        res = inhalt_check.pruefe("Der Anstieg war deutlich (Corona-Pandemie 2020).", "Während der Corona-Pandemie 2020 war der Anstieg deutlich.")
        self.assertTrue(res["ok"])
        self.assertTrue(any(w["typ"] == "Quellenverweis umformuliert" for w in res["warnungen"]))

    def test_koautor_gestrichen_warnung(self):
        res = inhalt_check.pruefe("Das gilt (Deci & Ryan 2000).", "Das gilt (Ryan 2000).")
        self.assertTrue(res["ok"])
        self.assertTrue(any(w["typ"] == "Quellenangabe verändert" for w in res["warnungen"]))


class NarrativeVerweiseUndFunktionswoerter(unittest.TestCase):
    """Regressionen: ein vorangestelltes Nomen samt „von“ gehört nicht zum Verweis; Funktionswörter sind keine Begriffe."""

    def warnungen(self, res, *typen):
        return [w for w in res["warnungen"] if w["typ"] in typen]

    def test_nomen_von_bleibt_im_resttext(self):
        faelle = [("Der Literaturüberblick von Christensen (2019) zeigt das.", ["christensen 2019"], "Literaturüberblick von"),
                  ("Laut der Studie von Müller (2020) gilt das.", ["müller 2020"], "Laut der Studie von"),
                  ("Die Metaanalyse von Weber et al. (2018, S. 4) belegt das.", ["weber et al. 2018, S. 4"], "Metaanalyse von"),
                  ("Gemäß Müller und Schmidt (2020) gilt das.", ["müller & schmidt 2020"], "Gemäß")]
        for text, schluessel, rest in faelle:
            with self.subTest(text=text):
                funde, r = inhalt_check.quellen(text)
                self.assertEqual(sorted(f["schluessel"] for f in funde), schluessel)
                self.assertIn(rest, r)
                self.assertNotIn("(", r)  # der Verweis selbst ist ausgeblendet
                self.assertTrue(funde[0]["roh"].endswith(")") and not funde[0]["roh"].startswith(rest.split()[0]))

    def test_vorname_aendert_schluessel_nicht(self):
        self.assertEqual([f["schluessel"] for f in inhalt_check.quellen("Ludwig von Mises (1940) schrieb das.")[0]],
                         [f["schluessel"] for f in inhalt_check.quellen("Das schrieb schon (Mises 1940).")[0]])
        self.assertEqual([f["schluessel"] for f in inhalt_check.quellen("Das Bundesministerium für Arbeit und Soziales (2021) meldet.")[0]],
                         [f["schluessel"] for f in inhalt_check.quellen("(Bundesministerium für Arbeit und Soziales 2021)")[0]])

    def test_umgestellter_verweis_ohne_fachwort_warnung(self):
        paare = [("Christensen (2019) zeigt in seinem Literaturüberblick, dass digitale Werkzeuge helfen.",
                  "Der Literaturüberblick von Christensen (2019) zeigt, dass digitale Werkzeuge helfen."),
                 ("Müller (2020) belegt in seiner Längsschnittuntersuchung, dass Teamarbeit wirkt.",
                  "Laut der Längsschnittuntersuchung von Müller (2020) wirkt Teamarbeit.")]
        for alt, neu in paare:
            for a, n in ((alt, neu), (neu, alt)):
                with self.subTest(alt=a):
                    res = inhalt_check.pruefe(a, n)
                    self.assertTrue(res["ok"], (res["harte_verluste"], res["erfindungen"]))
                    self.assertEqual(self.warnungen(res, "Fachwort ersetzt?", "Begriff verschwunden"), [])

    def test_geloeschter_verweis_mit_nomen_bleibt_harter_verlust(self):
        res = inhalt_check.pruefe("Laut der Studie von Müller (2020) wirkt Teamarbeit.", "Laut einer Studie wirkt Teamarbeit.")
        self.assertFalse(res["ok"])
        self.assertEqual([e["wert"] for e in res["harte_verluste"] if e["typ"] == "Quellenverweis"], ["Müller (2020)"])

    def test_funktionswoerter_nie_begriff_verschwunden(self):
        alt = ("Neben den Kosten zählt die Zeit. Neben der Qualität zählt der Service. Trotz hoher Kosten investieren Betriebe. "
               "Trotz allem bleibt der Bedarf. Gemäß der Umfrage wächst der Markt. Gemäß den Daten sinken die Preise. "
               "Zudem steigt die Nachfrage. Zudem fehlen Fachkräfte. Hinsichtlich der Kosten gibt es Streit. "
               "Hinsichtlich der Löhne auch. Infolgedessen wächst der Druck. Infolgedessen handeln Betriebe.")
        neu = ("Außer den Kosten zählt die Zeit. Außer der Qualität zählt der Service. Obwohl die Kosten hoch sind, investieren "
               "Betriebe. Der Bedarf bleibt. Die Umfrage zeigt: Der Markt wächst. Die Daten zeigen: Die Preise sinken. "
               "Auch die Nachfrage steigt. Es fehlen Fachkräfte. Bei den Kosten gibt es Streit. Bei den Löhnen auch. "
               "Deshalb wächst der Druck. Deshalb handeln Betriebe.")
        res = inhalt_check.pruefe(alt, neu)
        gemeldet = ", ".join(w["wert"] for w in self.warnungen(res, "Begriff verschwunden", "Fachwort ersetzt?"))
        for wort in ("neben", "trotz", "gemäß", "zudem", "hinsichtlich", "infolgedessen"):
            with self.subTest(wort=wort):
                self.assertNotIn(inhalt_check.stamm(wort), gemeldet.lower())
        # echte Fachbegriffe werden weiter gemeldet
        res = inhalt_check.pruefe("Die Pflegefachkräfte klagen. Pflegefachkräfte fehlen.", "Die Pflegekräfte klagen. Pflegekräfte fehlen.")
        self.assertTrue(self.warnungen(res, "Begriff verschwunden"))

    def test_haeufige_funktionswoerter_nie_begriff_verschwunden(self):
        # Prüfer-Fund: „vor allem“, „zusätzlich“, Konjunktiv I u. a. fehlten in der Liste
        for wort in ("allem", "alles", "jeden", "ihnen", "weitere", "zusätzlich", "daneben", "desto", "diesbezüglich",
                     "dementsprechend", "einschließlich", "könne", "müsse", "musste", "wenigen", "meisten", "sonst"):
            with self.subTest(wort=wort):
                res = inhalt_check.pruefe(f"Das Ergebnis ist {wort} gut. Der Befund ist {wort} klar.",
                                          "Das Ergebnis ist gut. Der Befund ist klar.")
                self.assertEqual(self.warnungen(res, "Begriff verschwunden", "Neuer häufiger Begriff"), [])
        res = inhalt_check.pruefe("Vor allem kleine Betriebe leiden. Die Kosten steigen vor allem im Handwerk. "
                                  "Zusätzlich fehlen Fachkräfte. Zusätzlich steigen die Mieten.",
                                  "Kleine Betriebe leiden. Die Kosten steigen besonders im Handwerk. Auch fehlen Fachkräfte. "
                                  "Außerdem steigen die Mieten.")
        self.assertEqual(self.warnungen(res, "Begriff verschwunden"), [])

    def test_nomen_homographe_bleiben_begriffe(self):
        # Prüfer-Fund: „des Mangels“, „das Selbst“ sind Nomen und dürfen nicht als Funktionswort wegfallen
        for alt, neu, stamm in (("Der Mangel an Fachkräften wächst. Die Folgen des Mangels sind gravierend.",
                                 "Der Engpass an Fachkräften wächst. Die Folgen des Engpasses sind gravierend.", "mangel"),
                                ("Das Selbst entwickelt sich früh. Nach Mead entsteht das Selbst im Austausch.",
                                 "Das Ich entwickelt sich früh. Nach Mead entsteht das Ich im Austausch.", "selbst")):
            with self.subTest(stamm=stamm):
                self.assertIn(stamm, ", ".join(w["wert"] for w in self.warnungen(inhalt_check.pruefe(alt, neu), "Begriff verschwunden")))
        # als Funktionswort (klein oder am Satzanfang) weiterhin nie gemeldet
        res = inhalt_check.pruefe("Selbst kleine Betriebe investieren. Das gilt selbst im Handwerk. Mangels Daten fehlt ein Vergleich. "
                                  "„Mangels Personal“ schließen Praxen.",
                                  "Auch kleine Betriebe investieren. Das gilt auch im Handwerk. Ohne Daten fehlt ein Vergleich. "
                                  "„Ohne Personal“ schließen Praxen.")
        self.assertEqual(self.warnungen(res, "Begriff verschwunden"), [])


class CoachErsetzbar(unittest.TestCase):
    """Regressionen aus der Coach-Evaluation: Was der Coach zum Ersetzen empfiehlt (Floskel-Auslöser, typische
    Claude-Wörter, „ersetzbar“ im Verlauf), meldet der Inhaltscheck nicht als verschwundenen Begriff."""

    TYPEN = ("Begriff verschwunden", "Fachwort ersetzt?")

    def gemeldet(self, res):
        return ", ".join(w["wert"] for w in res["warnungen"] if w["typ"] in self.TYPEN).lower()

    def ohne_coach_daten(self):
        """Kontrolle: ohne ki_muster.json/wortlisten.json prüft das Skript wie früher."""
        alt = (inhalt_check.MUSTER_PFAD, inhalt_check.WORTLISTEN_PFAD)
        inhalt_check.MUSTER_PFAD = inhalt_check.WORTLISTEN_PFAD = os.path.join(REPO, "gibt-es-nicht.json")
        self.addCleanup(lambda: setattr(inhalt_check, "MUSTER_PFAD", alt[0]))
        self.addCleanup(lambda: setattr(inhalt_check, "WORTLISTEN_PFAD", alt[1]))

    ALT_CLAUDE = ("Die Nachfrage bildet den Rahmen. Der Preis bildet die Grenze. Kunden kaufen häufig online. "
                  "Händler werben häufig mit Rabatten. Das lässt sich messen. Der Effekt lässt rasch nach. "
                  "Hinzu kommt der Wettbewerb. Es kommt auf die Lage an.")
    NEU_CLAUDE = ("Die Nachfrage steckt den Rahmen ab. Der Preis zieht die Grenze. Kunden kaufen oft online. "
                  "Händler werben oft mit Rabatten. Das kann man messen. Der Effekt nimmt rasch ab. "
                  "Dazu tritt der Wettbewerb. Entscheidend ist die Lage.")

    def test_claude_woerter_kein_begriff_verschwunden(self):
        res = inhalt_check.pruefe(self.ALT_CLAUDE, self.NEU_CLAUDE)
        for wort in ("bildet", "häufig", "lässt", "kommt"):
            with self.subTest(wort=wort):
                self.assertNotIn(inhalt_check.stamm(wort), self.gemeldet(res))
                self.assertIn(wort, res["nicht_gemeldet"])
        self.assertIn("Nicht als Verlust gewertet", inhalt_check.bericht(res))

    def test_ohne_coach_daten_wie_bisher(self):
        self.ohne_coach_daten()
        gemeldet = self.gemeldet(inhalt_check.pruefe(self.ALT_CLAUDE, self.NEU_CLAUDE))
        for wort in ("bildet", "häufig", "lässt", "kommt"):
            with self.subTest(wort=wort):
                self.assertIn(inhalt_check.stamm(wort), gemeldet)

    def test_fachnomen_aus_wortliste_bleiben_geschuetzt(self):
        # „befund“ steht in der Claude-Wortliste; großgeschrieben mitten im Satz ist es ein Nomen und bleibt Begriff
        res = inhalt_check.pruefe("Der Befund ist eindeutig. Den Befund bestätigen zwei weitere Studien.",
                                  "Das Ergebnis ist eindeutig. Das Ergebnis bestätigen zwei weitere Studien.")
        self.assertIn("befund", self.gemeldet(res))
        # am Satzanfang Nomen, wenn das Wort auch mitten im Satz großgeschrieben steht; sonst Adverb („Häufig …“)
        res = inhalt_check.pruefe("Befunde aus Japan fehlen. Neuere Befunde liegen nur für Europa vor.",
                                  "Ergebnisse aus Japan fehlen. Neuere Ergebnisse liegen nur für Europa vor.")
        self.assertIn("befund", self.gemeldet(res))
        res = inhalt_check.pruefe("Häufig fehlen Daten. Häufig fehlt auch Personal.", "Oft fehlen Daten. Oft fehlt auch Personal.")
        self.assertEqual(self.gemeldet(res), "")

    def test_schluesselrolle_als_floskel(self):
        alt = "Der Kommunikation kommt im Wandel eine Schlüsselrolle zu. Ohne sie scheitern viele Projekte."
        neu = "Die Kommunikation entscheidet im Wandel über den Erfolg. Ohne sie scheitern viele Projekte."
        res = inhalt_check.pruefe(alt, neu)
        self.assertNotIn("schlüssel", self.gemeldet(res))
        self.assertIn("schlüsselrolle", res["nicht_gemeldet"])
        self.ohne_coach_daten()
        self.assertIn("schlüsselrolle", self.gemeldet(inhalt_check.pruefe(alt, neu)))

    def test_schluesselrolle_als_fachwort(self):
        # wiederholt verwendet = Fachwort des Textes, kein Floskel-Einzelfund
        res = inhalt_check.pruefe("Belbin beschreibt die Schlüsselrolle des Koordinators. Die Schlüsselrolle wechselt "
                                  "im Projektverlauf.",
                                  "Belbin beschreibt die Hauptrolle des Koordinators. Die Hauptrolle wechselt im "
                                  "Projektverlauf.")
        self.assertIn(inhalt_check.stamm("Schlüsselrolle"), self.gemeldet(res))
        # in Anführungszeichen ist es das Wort der Quelle: kein Floskel-Auslöser, Hinweis bleibt
        alt = "Die Autoren sprechen von einer „Schlüsselrolle“ der Kommunen beim Klimaschutz."
        self.assertEqual(inhalt_check.floskel_kopfwoerter(alt), set())
        res = inhalt_check.pruefe(alt, "Die Autoren sprechen von einer wichtigen Aufgabe der Kommunen beim Klimaschutz.")
        self.assertNotIn("schlüsselrolle", res["nicht_gemeldet"])
        self.assertTrue(any("Schlüsselrolle" in w["wert"] for w in res["warnungen"]))

    def test_spannungsfeld_als_floskel(self):
        res = inhalt_check.pruefe("Unternehmen bewegen sich im Spannungsfeld zwischen Kosten und Qualität.",
                                  "Unternehmen können Kosten und Qualität nicht zugleich maximieren.")
        self.assertNotIn("spannungsfeld", self.gemeldet(res))

    def test_platzhalter_der_muster_bleiben_begriffe(self):
        # Inhalt in „nicht X, sondern“ und das Objekt in „trägt maßgeblich zu … bei“ sind keine Floskel
        res = inhalt_check.pruefe("Entscheidend ist nicht die Fertigungstechnik, sondern die Organisation der Abläufe.",
                                  "Entscheidend ist die Organisation der Abläufe.")
        self.assertIn("fertigungstechnik", self.gemeldet(res))
        alt = "Klare Ziele tragen maßgeblich zur Mitarbeiterzufriedenheit bei."
        kopf = {alt[a:b] for a, b in inhalt_check.floskel_kopfwoerter(alt)}
        self.assertIn("maßgeblich", kopf)
        self.assertNotIn("Mitarbeiterzufriedenheit", kopf)
        res = inhalt_check.pruefe(alt, "Klare Ziele erhöhen die Motivation.")
        self.assertIn("mitarbeiterzufriedenheit", self.gemeldet(res))
        self.assertNotIn("maßgeb", self.gemeldet(res))

    def test_muster_ohne_gewicht_nicht_ausgenommen(self):
        # „zunehmend“ ist ein Muster mit Gewicht 0: der Coach empfiehlt es nicht, also bleibt die Warnung
        res = inhalt_check.pruefe("Die Kosten steigen zunehmend. Die Nachfrage wächst zunehmend.",
                                  "Die Kosten steigen. Die Nachfrage wächst.")
        self.assertIn("zunehmend", self.gemeldet(res))

    ALT_VERLAUF = ("Konsumenten vergleichen Preise im Netz. Viele Konsumenten warten auf Rabatte. Ein einzelner Konsument "
                   "zählt wenig. Die Preisgestaltung folgt der Nachfrage.")
    NEU_VERLAUF = ("Kunden vergleichen Preise im Netz. Viele Kunden warten auf Rabatte. Ein einzelner Kunde zählt wenig. "
                   "Die Preissetzung folgt der Nachfrage.")

    def test_verlauf_ersetzbar(self):
        verlauf = {"datei": "text.md", "messungen": [{"score": 50, "ersetzbar": ["konsumenten"]},
                                                     {"score": 60, "ersetzbar": ["Preisgestaltung"]}, {"score": 70}]}
        ersetzbar = inhalt_check.ersetzbar_aus_verlauf(verlauf)
        self.assertEqual(ersetzbar, {"konsumenten", "preisgestaltung"})
        ohne = self.gemeldet(inhalt_check.pruefe(self.ALT_VERLAUF, self.NEU_VERLAUF))
        self.assertIn("konsument", ohne)
        self.assertIn("preisgestaltung", ohne)
        self.assertEqual(self.gemeldet(inhalt_check.pruefe(self.ALT_VERLAUF, self.NEU_VERLAUF, ersetzbar)), "")

    def test_verlauf_kompositum_bleibt_geschuetzt(self):
        # „konsumenten“ im Verlauf (Synonym-Variante) erfasst flektierte Formen, aber kein Kompositum wie „Konsumentenrente“
        # (früher über den auf 9 Zeichen gekürzten Stamm „konsument“ mit unterdrückt)
        alt = ("Konsumenten vergleichen Preise. Viele Konsumenten warten auf Rabatte. Die Konsumentenrente sinkt bei "
               "dynamischen Preisen. Ohne Preisbindung steigt die Konsumentenrente wieder.")
        neu = ("Kunden vergleichen Preise. Viele Kunden warten auf Rabatte. Der Vorteil der Kunden sinkt bei dynamischen "
               "Preisen. Ohne Preisbindung steigt der Vorteil wieder.")
        res = inhalt_check.pruefe(alt, neu, {"konsumenten"})
        self.assertIn("konsument", self.gemeldet(res))
        self.assertNotIn("konsumentenrente", res["nicht_gemeldet"])
        # flektierte Form derselben Grundform bleibt befreit
        res = inhalt_check.pruefe("Die Konsumenten zögern. Ein Konsument wartet.", "Die Kunden zögern. Ein Kunde wartet.",
                                  {"konsumenten"})
        self.assertEqual(self.gemeldet(res), "")

    def test_verlauf_platzhalter_aus_floskel_bleibt_begriff(self):
        # Der Coach schreibt alle Inhaltswörter eines Floskel-Funds unter „ersetzbar“, auch den Platzhalter
        # („sowohl die Kostenstruktur der Abteilungen als auch“, „kommt in diesem Prozess eine zentrale Rolle zu“).
        # Ein Fachnomen, das dort nur Platzhalter ist, bleibt Begriff.
        alt = ("Die Kostenstruktur betrifft sowohl die Kostenstruktur der Abteilungen als auch die Budgets. "
               "Die Kostenstruktur ist keineswegs starr. Der Planung kommt in diesem Prozess eine zentrale Rolle zu.")
        neu = ("Die Ausgabenplanung betrifft die Abteilungen und die Budgets. Die Ausgabenplanung ist nicht starr. "
               "Die Planung steuert diesen Prozess.")
        ersetzbar = {"kostenstruktur", "abteilungen", "keineswegs", "kommt", "prozess", "zentrale", "rolle"}
        res = inhalt_check.pruefe(alt, neu, ersetzbar)
        self.assertIn("kostenstr", self.gemeldet(res))
        self.assertNotIn("kostenstruktur", res["nicht_gemeldet"])
        # dasselbe Wort als echte Synonym-Variante (außerhalb einer Floskel) bleibt befreit
        res = inhalt_check.pruefe("Die Kostenstruktur ist starr. Die Kostenstruktur wächst.",
                                  "Die Ausgabenplanung ist starr. Die Ausgabenplanung wächst.", {"kostenstruktur"})
        self.assertEqual(self.gemeldet(res), "")

    def test_verlauf_cli(self):
        import contextlib
        import io
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            pfade = {}
            for name, inhalt in (("alt.md", self.ALT_VERLAUF), ("neu.md", self.NEU_VERLAUF),
                                 ("neu.coach.json", json.dumps({"messungen": [{"ersetzbar": ["konsumenten", "preisgestaltung"]}]}))):
                pfade[name] = os.path.join(d, name)
                with open(pfade[name], "w", encoding="utf-8") as f:
                    f.write(inhalt)
            for extra, erwartet_leer in (([], False), (["--verlauf", pfade["neu.coach.json"]], True)):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rc = inhalt_check.main([pfade["alt.md"], pfade["neu.md"], "--format", "json"] + extra)
                with self.subTest(verlauf=bool(extra)):
                    self.assertEqual(rc, 0)
                    self.assertEqual(self.gemeldet(json.loads(out.getvalue())) == "", erwartet_leer)

    def test_harte_funde_bleiben_trotz_verlauf(self):
        res = inhalt_check.pruefe("Müller (2019) zeigt, dass 45 % der Betriebe zögern.",
                                  "Studien zeigen, dass 54 % der Betriebe zögern.", {"müller", "zeigt", "45"})
        self.assertFalse(res["ok"])
        self.assertEqual({e["typ"] for e in res["harte_verluste"]}, {"Quellenverweis", "Zahl"})


class Zitate(unittest.TestCase):
    def test_gerade_anfuehrungszeichen_paaren_richtig(self):
        t = 'Der Begriff "KMU" ist ebenso unscharf wie "Mittelstand". Werner nennt es "die Fähigkeit, sich zu erholen".'
        self.assertEqual(list(inhalt_check.woertlich(t)), ["die Fähigkeit, sich zu erholen"])

    def test_satzzeichen_innen_aussen(self):
        alt = "Er nennt das „schnell, aber leider viel zu billig.“ Danach folgt nichts."
        neu = "Er nennt das „schnell, aber leider viel zu billig“. Danach folgt nichts."
        self.assertTrue(inhalt_check.pruefe(alt, neu)["ok"])

    def test_zitat_ueber_zeilenumbruch_und_autokorrektur(self):
        self.assertEqual(list(inhalt_check.woertlich("„die Fähigkeit eines Systems,\nsich zu erholen“")),
                         ["die Fähigkeit eines Systems, sich zu erholen"])
        self.assertEqual(list(inhalt_check.woertlich("“trifft gar nicht zu“")), ["trifft gar nicht zu"])

    def test_kurzes_zitat_ohne_anfuehrung_kein_alarm(self):
        res = inhalt_check.pruefe('Der Begriff "Resilienz" ist unscharf.', "Der Begriff Resilienz ist unscharf.")
        self.assertTrue(res["ok"])
        self.assertFalse([w for w in res["warnungen"] if w["typ"].startswith("Kurzes Zitat")])


class Fussnoten(unittest.TestCase):
    def test_einheiten_keine_fussnoten(self):
        t = "Die Fläche betrug 92 m² (R² = 0,46; η² = 0,12; χ² = 8,4; 10⁶ Zellen).¹"
        self.assertEqual([f for f, _ in inhalt_check.fussnoten(t)], ["¹"])

    def test_einheiten_entfernt_kein_verlust(self):
        res = inhalt_check.pruefe("Fläche 92 m², Modell R² = 0,46.", "Fläche 92 Quadratmeter, Modell R2 = 0,46.")
        self.assertTrue(res["ok"])

    def test_markdown_fussnote_getauscht(self):
        res = inhalt_check.pruefe("Text.[^2] Mehr.[^3]", "Text.[^2] Mehr.[^4]")
        self.assertFalse(res["ok"])


# ---------------------------------------------------------------------------
# Regex-Muster in ki_muster.json (je geändertes Muster ≥ 3 Positiv- und ≥ 3 Negativsätze)
# ---------------------------------------------------------------------------

MUSTER_SAETZE = {
    "rolle_spielen": (
        ["Dabei spielt die Digitalisierung eine zentrale Rolle.",
         "Hierbei spielen digitale Medien eine immer größere Rolle.",
         "Es zeigt sich, dass Vertrauen eine entscheidende Rolle spielt.",
         "Die Führungskraft hat dabei eine wichtige Rolle gespielt."],
        ["Er spielt eine Rolle im Theaterstück.",
         "Die zentrale Rolle des Staates wird kritisch diskutiert.",
         "Das Alter spielt keine wichtige Rolle.",
         "Die Kinder spielten eine Szene nach."]),
    "rolle_zukommen": (
        ["Der Führungskraft kommt eine zentrale Rolle zu.",
         "Dabei kommt der Kommunikation im Veränderungsprozess eine besondere Bedeutung zu.",
         "Es zeigt sich, dass dem Vertrauen eine wichtige Rolle zukommt."],
        ["Die Rolle kommt aus dem Theater.",
         "Er kommt zu einer wichtigen Erkenntnis.",
         "Eine besondere Bedeutung hat die Kommunikation."]),
    "gilt_es": (
        ["Daher gilt es, die Kosten zu senken.",
         "Es gilt, die Mitarbeitenden früh einzubinden.",
         "Deren Bedürfnisse gilt es als Erstes zu erfüllen.",
         "Es gilt: Qualität vor Quantität."],
        ["Mittlerweile gilt es als erwiesen, dass Bewegung hilft.",
         "Es gilt das Prinzip der Gleichbehandlung.",
         "Diese Regel gilt seit 2019.",
         "Ob das auch für KMU gilt, ist offen."]),
    "beitrag_leisten": (
        ["Schulungen tragen maßgeblich dazu bei, Fehler zu vermeiden.",
         "Das Programm trägt entscheidend zur Motivation der Beschäftigten bei.",
         "Es zeigt sich, dass klare Ziele wesentlich zum Erfolg beitragen."],
        ["Er trägt die Verantwortung für das Projekt.",
         "Das trägt zur Verwirrung bei.",
         "Die Kosten trug maßgeblich der Bund."]),
    "des_weiteren": (
        ["Des Weiteren wurde eine Befragung durchgeführt.",
         "Des weiteren zeigt sich ein deutlicher Effekt.",
         "Es wurde des Weiteren festgestellt, dass die Kosten steigen.",
         "Die Kosten sind des weiteren gestiegen."],
        ["Das dient der Planung des weiteren Vorgehens.",
         "Im Laufe des weiteren Verlaufs zeigte sich nichts.",
         "Die Phase des weiteren beruflichen Werdegangs ist offen."]),
    "insgesamt_zeigt": (
        ["Insgesamt zeigt sich ein positives Bild.",
         "Insgesamt wird deutlich, dass die Maßnahmen wirken.",
         "Insgesamt ergibt sich ein differenziertes Bild."],
        ["Insgesamt ergibt sich eine Zahl von 53 Vereinen.",
         "Insgesamt lässt sich festhalten, dass der Effekt klein ist.",
         "Insgesamt wurden 412 Personen befragt."]),
    "zusammenfassend": (
        ["Zusammenfassend lässt sich festhalten, dass der Effekt klein ist.",
         "Abschließend kann man sagen, dass das Projekt gelungen ist.",
         "Insgesamt lässt sich feststellen, dass die Kosten steigen."],
        ["Insgesamt können 128 Fehler festgestellt werden.",
         "Insgesamt können drei Fehler festgestellt werden.",
         "Zusammenfassend werden die Ergebnisse dargestellt."]),
    "dies_verdeutlicht": (
        ["Dies zeigt, dass Vertrauen wichtig ist.",
         "Das verdeutlicht, wie wichtig Kommunikation ist.",
         "Dieses Ergebnis unterstreicht, dass die Maßnahme wirkt."],
        ["Es gibt ein Modell, das zeigt, dass Lernen wirkt.",
         "Ein Experiment, das belegt, dass Schlaf hilft, fehlt.",
         "Die Tabelle zeigt die Ergebnisse."]),
    "mehr_als_nur": (
        ["Führung ist weit mehr als Kontrolle.",
         "Nachhaltigkeit ist mehr als nur ein Trend.",
         "Es geht nicht einfach um Kosten."],
        ["Weit mehr als 90 Prozent der Befragten stimmten zu.",
         "Weit mehr als die Hälfte der Betriebe nutzt Cloud-Dienste.",
         "Das kostet weit mehr als doppelt so viel.",
         "Die Umstellung dauerte weit mehr als drei Jahre."]),
    "praegt_gestaltet": (
        ["Die Digitalisierung prägt den Alltag maßgeblich.",
         "Diese Erfahrungen prägen Kinder nachhaltig.",
         "Es sind Akteure, die den Wandel entscheidend gestalten."],
        ["Viele Unternehmen gestalten ihre Verpackungen nachhaltig.",
         "Wir gestalten den Prozess nachhaltig und fair.",
         "Diese Zeit prägte ihn."]),
    "kern_zentral": (
        ["Im Kern geht es um Vertrauen.",
         "Ein zentraler Faktor ist die Kommunikation.",
         "Ein wesentlicher Hebel ist die Führungskultur."],
        ["Im Kern der Zelle befindet sich die DNA.",
         "Ein wesentlicher Bestandteil des Vertrags ist die Laufzeit.",
         "Das Kerngeschäft des Unternehmens wächst."]),
    "spannungsfeld": (
        ["Unternehmen bewegen sich im Spannungsfeld zwischen Kosten und Qualität.",
         "Es gilt, die richtige Balance zu finden.",
         "Ein Gleichgewicht zwischen Arbeit und Freizeit ist wichtig."],
        ["Der Preis ergibt sich aus dem Gleichgewicht zwischen Angebot und Nachfrage.",
         "Das Gleichgewicht zwischen Nachfrage und Angebot verschiebt sich.",
         "Die Balance des Körpers verbessert sich."]),
    "fokus_mittelpunkt": (
        ["Im Folgenden steht die Kommunikation im Mittelpunkt.",
         "Dabei rückt die Nachhaltigkeit in den Fokus.",
         "Die Kundenzufriedenheit steht im Zentrum der Arbeit.",
         "Zwei Fragen stehen im Mittelpunkt."],
        ["Das Gebäude steht im Zentrum von Hamburg.",
         "Das Rathaus steht im Zentrum der Stadt.",
         "Die Kamera rückt näher an das Objekt."]),
}


def lade_muster():
    """Wie analyse.lade_muster: IGNORECASE, außer bei gross_klein."""
    with open(MUSTER_PFAD, encoding="utf-8") as f:
        daten = json.load(f)
    return {m["id"]: re.compile(m["regex"], 0 if m.get("gross_klein") else re.IGNORECASE) for m in daten["muster"]}


class KiMuster(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.muster = lade_muster()

    def test_alle_muster_kompilieren(self):
        self.assertGreaterEqual(len(self.muster), 40)

    def test_mindestens_drei_saetze_je_richtung(self):
        for mid, (pos, neg) in MUSTER_SAETZE.items():
            with self.subTest(muster=mid):
                self.assertIn(mid, self.muster)
                self.assertGreaterEqual(len(pos), 3)
                self.assertGreaterEqual(len(neg), 3)

    def test_positiv(self):
        for mid, (pos, _) in MUSTER_SAETZE.items():
            for s in pos:
                with self.subTest(muster=mid, satz=s):
                    self.assertTrue(self.muster[mid].search(s))

    def test_negativ(self):
        for mid, (_, neg) in MUSTER_SAETZE.items():
            for s in neg:
                with self.subTest(muster=mid, satz=s):
                    self.assertIsNone(self.muster[mid].search(s))

    def test_insgesamt_nicht_doppelt(self):
        s = "Insgesamt lässt sich festhalten, dass der Effekt klein ist."
        treffer = [mid for mid in ("insgesamt_zeigt", "zusammenfassend") if self.muster[mid].search(s)]
        self.assertEqual(treffer, ["zusammenfassend"])


if __name__ == "__main__":
    unittest.main()
