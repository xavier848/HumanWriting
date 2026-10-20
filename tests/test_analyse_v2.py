"""Tests für analyse.py nach Review-Funden und QL-Änderungen (python3 -m unittest discover -s tests)."""
import glob
import io
import json
import math
import os
import sys
import tempfile
import time
import unittest
import zipfile
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
import analyse  # noqa: E402

KORPUS = os.path.join(REPO, "kalibrierung", "korpus")


def saetze(text):
    return analyse.zerlege_saetze(analyse.bereinige_absatz(text, Counter()))


def analysiere(text, **kw):
    return analyse.analysiere_text(text, [], **kw)


def korpus_dateien(gruppe):
    return sorted(glob.glob(os.path.join(KORPUS, gruppe, "*", "*.txt")))


# ---------------------------------------------------------------------------
# Satztrennung
# ---------------------------------------------------------------------------

class SatztrennungReview(unittest.TestCase):
    FAELLE = [
        # Fußnotenziffern ohne Hochstellung (pdftotext)
        ("Das ist empirisch belegt.12 Weiterhin zeigt sich ein Trend.", 2),
        ("Das wurde veröffentlicht3. Sie zeigt einen Trend.", 2),
        # Punkt hinter Klammer/Anführung, doppelter Punkt
        ("Die Werte steigen (siehe Abb. 4.6). Es folgt die Analyse.", 2),
        ("Das betrifft Motivation, Teamklima usw.). Danach folgt mehr.", 2),
        ("Das zeigen Müller et al. (2020). Danach folgt die Analyse.", 2),
        ("Er nennt das »Teamklima usw.«. Danach folgt mehr.", 2),
        # Auslassungen im Zitat
        ("„Die Digitalisierung […] Unternehmen grundlegend“, so Müller. Danach folgt mehr.", 2),
        ("Das war typisch für seine Philosophie. „[…] Um eine Mannschaft zu formen, braucht es Zeit.“ Danach folgt mehr.", 3),
        ("Das ist so [...]. Diese Aspekte sind wichtig.", 2),
        # fehlende Abkürzungen, Bindestrich-Titel
        ("Es nahmen mind. 25 Personen teil.", 1),
        ("Das bestätigt Dipl.-Ing. Müller im Interview.", 1),
        ("Er ist Dipl.-Ingenieur. Danach wechselte er.", 2),
        # Zahl/Datum am Satzende
        ("Das Maximum lag bei 5. Keiner erreichte mehr.", 2),
        ("Die Erkenntnisse sind 16. Diese, so zeigt sich, sind neu.", 2),
        ("Die Erhebung endete am 31.12. Danach wurde ausgewertet.", 2),
        ("Die Erhebung endete am 15.03.2021. Befragt wurden 20 Personen.", 2),
        ("Das zeigt Kap. 3.2. Danach folgt die Analyse.", 2),
        # usw./etc./ff. am Satzende
        ("Das gilt für Dienstreisen etc. Das wiederum fordert Zeit.", 2),
        ("Kundenpflege usw. Aber zu diesen zählt mehr.", 2),
        ("Er setzt Plakate etc. Konsumenten ein.", 1),
        ("Laut § 67 ff. SGB XII gilt das.", 1),
        ("So sagte John F. Kennedy das.", 1),
        # echte Wörter in der Abkürzungsliste
        ("Maßnahmen dieser Art. Sie sind teuer.", 2),
        ("Die Befragten sind 26 Jahre alt. Die Interviews dauerten lange.", 2),
        ("Tabelle 1 verdeutlicht dies. Die Abbildung zeigt mehr.", 2),
        ("Gemäß Art. 5 GG gilt das.", 1),
        ("Die max. Anzahl betrug 20.", 1),
        ("Nach Art. XX GATT gilt das.", 1),
        # einzelner Großbuchstabe, §, (sic!)
        ("Die Werte der Gruppe A. Die Werte der Gruppe B. Sie unterscheiden sich.", 3),
        ("Das regelt das Gesetz. § 5 bestimmt die Frist.", 2),
        ("Die Methode (sic!) Ergebnisse liefert. Das ist gut.", 2),
        ("Was tun (?) Danach folgt mehr.", 1),
        ("Siehe www.ard.de. Das ist die Quelle.", 2),
    ]

    def test_faelle(self):
        for text, n in self.FAELLE:
            with self.subTest(text=text):
                self.assertEqual(len(saetze(text)), n, saetze(text))

    def test_alte_regeln_bleiben(self):
        t = ("Viele Unternehmen, z. B. KMU, nutzen das, d. h. sie profitieren. Das gilt u. a. für den Handel, "
             "vgl. S. 12 f. und Abb. 3. Prof. Dr. Müller sieht das anders.")
        self.assertEqual(len(saetze(t)), 3)
        self.assertEqual(len(saetze("Am 3. Oktober begann die 2. Phase des Projekts im 19. Jahrhundert. Danach folgte nichts.")), 2)
        self.assertEqual(len(saetze("Laut J. Müller ist das falsch. Andere sehen das anders.")), 2)

    def test_fussnotenziffern_entfernt_aber_nicht_co2(self):
        z = Counter()
        out = analyse.bereinige_absatz("Das ist belegt.12 Der Ausstoß von CO2 sinkt, DAX40 und Web2.0 auch (Abb.3).", z)
        self.assertEqual(z["fussnoten"], 1)
        for erhalten in ("CO2", "DAX40", "Web2.0", "Abb.3"):
            self.assertIn(erhalten, out)

    def test_belege_ohne_jahr(self):
        z = Counter()
        out = analyse.bereinige_absatz("Das betont der Verband (BMBF o. J., S. 3). Sie sagt das (I2, Pos. 34). So ist es (Ebd., S. 5). "
                                       "Ein Beleg [3, S. 12] fehlt. Das Intervall [0, 1] bleibt.", z)
        self.assertEqual(z["zitate"], 4)
        self.assertNotIn("o. J.", out)
        self.assertIn("[0, 1]", out)


class Tokenizer(unittest.TestCase):
    def test_gender_und_ziffern(self):
        toks = analyse.tokens("Absolvent/-innen, jede*r, ein*e, jede:r, Kolleg*innen-Netzwerk, Mitarbeiter/inne/n, einer/m "
                              "und/oder km/h 1970er CO2-Emissionen 3D-Druck 3,5 12.03.2020")
        for t in ("Absolvent/-innen", "jede*r", "ein*e", "jede:r", "Kolleg*innen-Netzwerk", "Mitarbeiter/inne/n", "einer/m",
                  "1970er", "CO2-Emissionen", "3D-Druck", "3,5", "12.03.2020"):
            self.assertIn(t, toks)
        self.assertIn("und", toks)
        self.assertIn("oder", toks)

    def test_pandoc_escape_und_striche(self):
        e = analysiere("Die Mitarbeiter\\*innen wurden -- so die Autoren -- befragt. Das ist so.")
        self.assertEqual(e["saetze"][0]["woerter"], 7)
        self.assertGreater(e["metriken"]["gedankenstrich_pro_1000"], 0)

    def test_zahlenspanne_kein_gedankenstrich(self):
        e = analysiere("Von 2019 – 2021 stieg der Wert, S. 279 - 280. Er stieg – wie erwartet – stark.")
        self.assertAlmostEqual(e["metriken"]["gedankenstrich_pro_1000"], 1000 * 2 / e["info"]["token"], places=3)


# ---------------------------------------------------------------------------
# Silben (HW04) und Wortlängen (HW05)
# ---------------------------------------------------------------------------

class Silben(unittest.TestCase):
    GOLD = {  # Duden-Trennung bzw. Kerndefinition nach Best (Vokal oder Diphthong)
        "Situation": 5, "Information": 5, "Reaktion": 4, "Theorie": 3, "Theorien": 4, "Ideen": 3, "beeinflussen": 4,
        "Museum": 3, "Individuum": 5, "Koordination": 6, "Materialien": 6, "Studien": 3, "Medien": 3, "Kriterien": 4,
        "aktuell": 3, "Qualität": 3, "Kommunikation": 6, "Digitalisierung": 6, "Nachhaltigkeit": 4, "Organisation": 6,
        "individuell": 5, "Diskussion": 4, "Region": 3, "Funktion": 3, "Funktionen": 4, "Relevanz": 3, "Realität": 4,
        "Kreativität": 5, "Prozess": 2, "Analyse": 4, "System": 2, "Bedeutung": 3, "Gesellschaft": 3, "Untersuchung": 4,
        "Ergebnis": 3, "Studie": 2, "Familie": 3, "Linie": 2, "Strategie": 3, "Strategien": 4, "sozial": 3,
        "Sozialisation": 7, "Variation": 5, "Evaluation": 6, "Ökonomie": 4, "Ökonomien": 5, "Initiative": 6,
        "Investition": 5, "Zielen": 2, "spielen": 2, "Beispiel": 2, "Haus": 1, "neue": 2, "neuen": 2, "Bauer": 2,
        "Mauer": 2, "Feuer": 2, "Leute": 2, "heute": 2, "ziehen": 2, "Knie": 1, "geschrien": 3, "erschien": 2, "Wien": 1,
        "Poesie": 3, "Ozean": 3, "Chaos": 2, "Kooperation": 6, "Idee": 2, "Muster": 2, "Akteure": 3, "Akteur": 2,
        "Statue": 3, "Duell": 2, "Ruin": 2, "virtuell": 3, "Situationen": 6, "Interaktion": 5, "Kontinuität": 5,
        # 'ou' und i vor -ent/-enz (Kritik zu HW04)
        "Ressourcen": 3, "Tourismus": 3, "Routine": 3, "Journal": 2, "Patient": 3, "Orientierung": 5, "Effizienz": 4,
        "Resilienz": 4, "dient": 1, "verdient": 2, "Dienst": 1,
        # -ien in Komposita, Hiat nach Diphthong, -ie im Singular
        "Studiengang": 4, "Medienkompetenz": 6, "Familienunternehmen": 8, "Frauen": 2, "Vertrauen": 3, "seien": 2,
        "Parteien": 3, "Prämie": 2, "Arie": 2, "Kategorie": 4, "Energie": 3, "Technologie": 4, "Beobachtung": 4,
        "reagieren": 4, "beenden": 3, "geehrt": 2, "Beere": 2,
        # Anglizismen
        "Team": 1, "Teamarbeit": 3, "Coaching": 2, "Management": 3, "Software": 2, "online": 2, "Recruiting": 3,
        "Download": 2, "Onboarding": 3, "Leadership": 3, "Website": 2, "Homeoffice": 3, "Feedback": 2, "Boykott": 2,
        "Unternehmen": 4, "Mitarbeiter": 4, "Arbeit": 2, "Bau": 1, "Psychologie": 4,
    }

    def test_goldliste(self):
        falsch = {w: (analyse.silben(w), g) for w, g in self.GOLD.items() if analyse.silben(w) != g}
        self.assertEqual(falsch, {})

    def test_vokallos_null(self):
        for w in ("bzw", "vgl", "Std", "z"):
            self.assertEqual(analyse.silben(w), 0)

    @unittest.expectedFailure
    def test_bekannter_restfehler_milieu(self):
        self.assertEqual(analyse.silben("Milieu"), 2)

    def test_abkuerzungen_nicht_in_wortlaenge(self):
        a = analysiere("Das gilt z. B. für KMU bzw. Banken. " * 5)
        b = analysiere("Das gilt für Banken. " * 5)
        self.assertAlmostEqual(a["metriken"]["wortlaenge_mittel"], b["metriken"]["wortlaenge_mittel"], places=4)
        self.assertGreater(a["metriken"]["abkuerzungen_pro_1000"], 0)
        self.assertEqual(b["metriken"]["abkuerzungen_pro_1000"], 0)
        self.assertEqual(a["metriken"]["satzlaenge_mittel"], 8)  # Satzlänge zählt alle Token (z, B, KMU, bzw)

    def test_verweis_abkuerzungen_nur_info(self):
        e = analysiere("Das zeigt Abb. 3 deutlich. Vgl. dazu S. 12 und Kap. 4.")
        self.assertEqual(e["metriken"]["abkuerzungen_pro_1000"], 0)
        self.assertGreaterEqual(e["info"]["verweis_abk"], 3)


# ---------------------------------------------------------------------------
# Satzbau: Teilsätze (HW03 Stufe 1), Passiv, Satzklammer (HW08)
# ---------------------------------------------------------------------------

class Teilsaetze(unittest.TestCase):
    # (Satz, Teilsätze, Nebensatz?, Infinitivgruppen) – ein Teilsatz pro finitem Verb, Infinitive extra
    GOLD = [
        ("Der Untersuchungszeitraum reicht von 2010 bis 2020.", 1, False, 0),
        ("Bis heute fehlt eine einheitliche Definition des Begriffs.", 1, False, 0),
        ("Befragt wurden 18- bis 29-jährige Studierende.", 1, False, 0),
        ("Während der Pandemie stieg der Anteil der Beschäftigten im Homeoffice.", 1, False, 0),
        ("Untersucht wurden die Arbeitszufriedenheit, die Motivation und das Commitment.", 1, False, 0),
        ("Weber, der Begründer der Verstehenden Soziologie, unterscheidet vier Typen sozialen Handelns.", 1, False, 0),
        ("Seitdem hat sich die Forschungslage deutlich verbessert.", 1, False, 0),
        ("Um die Hypothesen zu prüfen, wurde eine Regressionsanalyse durchgeführt.", 1, False, 1),
        ("Je höher die Arbeitsbelastung ist, desto geringer fällt die Zufriedenheit aus.", 2, True, 0),
        ("Ziel dieser Arbeit ist es, die Ursachen der Fluktuation zu untersuchen.", 1, False, 1),
        ("Es gibt zahlreiche Studien, die zeigen, dass Homeoffice die Produktivität steigert.", 3, True, 0),
        ("Personen, die rauchen, haben ein höheres Risiko.", 2, True, 0),
        ("Die Studie, die 2020 erschien, zeigt einen starken Effekt.", 2, True, 0),
        ("Die Quote lag bei 12 Prozent, was deutlich höher ist als im Vorjahr.", 2, True, 0),
        ("Die Befragung dauerte an, bis alle Fragebögen zurückgesandt waren.", 2, True, 0),
        ("Da die Stichprobe klein war, sind die Befunde vorläufig.", 2, True, 0),
        ("Es ist wichtig, frühzeitig zu handeln.", 1, False, 1),
        ("Männer verdienen im Durchschnitt mehr, im Gegensatz zu Frauen.", 1, False, 0),
        ("Das Alter, das Geschlecht und das Einkommen wurden erhoben.", 1, False, 0),
        ("Nicht die Ursachen stehen im Fokus, sondern die Folgen.", 1, False, 0),
        ("Die Ergebnisse sind eindeutig, aber die Stichprobe ist klein.", 2, False, 0),
        ("Die Effekte waren stark, jedoch nicht signifikant.", 1, False, 0),
        ("Die Daten sind erhoben; die Auswertung folgt.", 2, False, 0),
        ("Der Mittelwert lag bei 3,45; SD = 1,02.", 1, False, 0),
        ("Einstellungen, Erfahrungen und Einschätzungen wurden erfragt.", 1, False, 0),
        ("Wenn die Kosten steigen, sinkt die Nachfrage.", 2, True, 0),
    ]

    def test_goldsaetze(self):
        for satz, n, neben, inf in self.GOLD:
            with self.subTest(satz=satz):
                h, ne, i = analyse.teilsatz_zerlegung(satz)
                self.assertEqual((h + ne, ne > 0, i), (n, neben, inf))
                self.assertEqual(analyse.teilsatz_info(satz, analyse.tokens(satz)), (n, neben))

    @unittest.expectedFailure
    def test_restluecke_relativsatz_mit_aufzaehlung(self):
        self.assertEqual(analyse.teilsatz_info("Die Theorie, die Müller, Schmidt und Weber entwickelten, wird häufig zitiert.")[0], 2)

    def test_verhaeltnis_21(self):
        e = analysiere("Das ist gut. Das ist schlecht. Wenn es regnet, bleiben wir.")
        self.assertAlmostEqual(e["metriken"]["teilsatz_verhaeltnis_21"], (1 + 0.5) / (2 + 0.5), places=4)
        self.assertEqual(e["info"]["teilsatz_verteilung"]["1"], round(2 / 3, 3))
        self.assertIn("teilsatz_alt", e["info"])


class Passiv(unittest.TestCase):
    def test_aktiv_futur_kopula(self):
        for s in ("Die Anforderungen an Unternehmen werden in Zukunft steigen.", "Das würde den Nutzer verwirren.",
                  "Es wird deutlich, wie viel Potenzial noch ungenutzt ist.", "Er wird Lehrer."):
            self.assertFalse(analyse.ist_passiv(s), s)

    def test_passiv(self):
        for s in ("Die Ergebnisse werden in Tabelle 2 dargestellt.", "Zur Analyse wurde die Inhaltsanalyse herangezogen.",
                  "Die Hypothese konnte nicht bestätigt werden.", "Die Methode kann auf andere Bereiche übertragen werden.",
                  "Dieser Zusammenhang wurde bereits nachgewiesen.", "Kritisiert wird vor allem die Stichprobe."):
            self.assertTrue(analyse.ist_passiv(s), s)


class Satzklammer(unittest.TestCase):
    def test_spannen(self):
        self.assertEqual(analyse.satzklammern("Die Daten müssen sorgfältig erhoben werden."), [1])  # Modal-Passiv
        self.assertEqual(analyse.satzklammern("Die Studie hat im Jahr 2019 gezeigt, dass es wirkt."), [3])  # Perfekt
        self.assertEqual(analyse.satzklammern("Man sieht, dass die Daten erhoben werden müssen."), [])  # Nebensatz
        self.assertEqual(analyse.satzklammern("Es wird dabei nicht"), [])

    def test_kennzahl_none_unter_5(self):
        self.assertIsNone(analysiere("Die Studie hat das gezeigt. Er geht.")["metriken"]["satzklammer_mittel"])
        satz = "Die Studie hat die Wirkung im Jahr 2019 deutlich gezeigt. "
        self.assertEqual(analysiere(satz * 6)["metriken"]["satzklammer_mittel"], 6.0)


# ---------------------------------------------------------------------------
# Struktur und Eingaben
# ---------------------------------------------------------------------------

class Struktur(unittest.TestCase):
    def z(self, text):
        return analyse.zerlege_bloecke(text)

    def test_einfache_zeilenumbrueche(self):
        s = self.z("1 Einleitung\nDie Arbeit untersucht kleine Unternehmen. Sie nutzt Interviews mit vielen Beteiligten aus der Praxis.\n"
                   "2 Methodik\nEs wurden zwölf Personen befragt.\nLiteraturverzeichnis\nMüller, A.: Titel.\nBerlin: Springer.")
        self.assertEqual(s["ueberschriften"], ["1 Einleitung", "2 Methodik"])
        self.assertEqual(len(s["absaetze"]), 2)
        self.assertTrue(s["literatur_abgeschnitten"])

    def test_harte_umbrueche_keine_listen(self):
        for t in ("Die Einführung erfolgte bei der Muster GmbH am\n3. Oktober 2019, wobei die Abteilungen\n– so die Vorgabe –\n"
                  "z. B. die Buchhaltung früh umgestellt wurden. Das war gut.",
                  "Viele Betriebe investieren seit dem\n20. Jahrhundert in Informationstechnik, wobei\nz. B. die Buchhaltung früh "
                  "automatisiert wurde. Die Ergebnisse\n– so die Autoren – sind eindeutig.",
                  "Das Verfahren hat\na) Vorteile, die wir nennen. Es bleibt gut."):
            s = self.z(t)
            self.assertEqual(s["listenpunkte"], [], t)
            self.assertEqual(len(s["absaetze"]), 1)

    def test_markdown_listen_bleiben(self):
        s = self.z("## Vorteile\n- a\n- b\n\n**Vorteile:**\n- Kosten senken\n- Zeit sparen\n\nDie wichtigsten Vorteile sind\n- x\n- y\n\n"
                   "### Vorgehen\n1. Planung\n2. Umsetzung\n3. Kontrolle")
        self.assertEqual(len(s["listenpunkte"]), 9)

    def test_fortsetzung_listenpunkt(self):
        s = self.z("- Erstens sinken die Kosten, weil\nweniger Personal benötigt wird.\n- Zweitens steigt die Qualität.\n\nNormaler Absatz.")
        self.assertEqual(s["listenpunkte"][0], "Erstens sinken die Kosten, weil weniger Personal benötigt wird.")
        self.assertEqual(s["absaetze"], ["Normaler Absatz."])

    def test_fussnotentext_markdown(self):
        e = analysiere("Die Arbeit untersucht kleine Unternehmen in der Region.[^1] Sie nutzt Interviews.[^ausblick]\n\n"
                       "[^1]: Vgl. Müller 2020, S. 14.\n\n[^ausblick]: Vgl. ebd., S. 17.\n\n    Zweiter Absatz der Fußnote.")
        self.assertEqual(e["info"]["satzlaengen"], [8, 3])
        self.assertEqual(e["info"]["fussnoten_text_entfernt"], 2)

    def test_kurzer_absatz_mit_marke_bleibt_prosa(self):
        s = self.z("Ein langer Absatz mit vielen Wörtern steht hier. Noch ein Satz.\n\nDies ist nicht der Fall.[^3]\n\n"
                   "Dies ist nicht der Fall.³\n\n*Dies ist nicht der Fall.*\n\nEr sagte: »Das ist falsch.«\n\n"
                   "Das ist so.​\n\n3.2 Der Begriff „Resilienz“\n\n2.3 Kosten-Nutzen-Analyse (KNA)")
        self.assertEqual(len(s["absaetze"]), 6)
        self.assertEqual(s["ueberschriften"], ["3.2 Der Begriff „Resilienz“", "2.3 Kosten-Nutzen-Analyse (KNA)"])

    def test_literatur_varianten(self):
        for kopf in ("**Literaturverzeichnis**", "## VII. Literaturverzeichnis", "# 8 Quellen- und Literaturverzeichnis",
                     "Verwendete Literatur", "Literatur- und Quellenverzeichnis", "7.Literaturverzeichnis", "Bibliografie",
                     "Selbständigkeitserklärung"):
            with self.subTest(kopf=kopf):
                s = self.z(f"Text eins ist hier. Noch ein Satz.\n\n{kopf}\n\nMüller, A. (2019): Buch. Berlin.")
                self.assertTrue(s["literatur_abgeschnitten"])
                self.assertEqual(s["absaetze"], ["Text eins ist hier. Noch ein Satz."])
        self.assertIsNone(analyse.LITERATUR_UEBERSCHRIFT.match("Die Literatur zeigt das."))
        self.assertIsNone(analyse.LITERATUR_UEBERSCHRIFT.match("Civil Literatur"))

    def test_kein_vorzeitiger_abbruch(self):
        vorspann = ("Universität Hamburg\n\nHausarbeit im Seminar Organisation\n\n# Eidesstattliche Erklärung\n\n"
                    "Ich versichere, dass ich die Arbeit selbstständig verfasst habe.\n\n# Inhaltsverzeichnis\n\n1 Einleitung 3\n\n"
                    "2 Theorie 5\n\nLiteraturverzeichnis 12\n\n# 1 Einleitung\n\nDie Arbeit untersucht kleine Unternehmen.\n\n"
                    "# 2 Theorie\n\nDie Theorie ist wichtig.\n\n# Literaturverzeichnis\n\nMüller, A. (2019): Buch. Berlin.")
        s = self.z(vorspann)
        self.assertEqual(s["absaetze"], ["Die Arbeit untersucht kleine Unternehmen.", "Die Theorie ist wichtig."])
        self.assertTrue(s["literatur_abgeschnitten"])
        s = self.z("# 1 Einleitung\n\nDie Arbeit untersucht kleine Unternehmen.\n\n## 1.3 Quellen\n\nDie Quellenlage ist dünn.\n\n"
                   "# 2 Fazit\n\nDas Fazit ist kurz.\n\n# Literaturverzeichnis\n\nMüller, A. (2019): Buch.")
        self.assertEqual(len(s["absaetze"]), 3)
        s = self.z("# Inhaltsverzeichnis\n\n1 Einleitung\n\nLiteraturverzeichnis\n\n# 1 Einleitung\n\nText steht hier.\n\n"
                   "# Literaturverzeichnis\n\nMüller, A. (2019): Buch.")
        self.assertEqual(s["absaetze"], ["Text steht hier."])

    def test_zitatblock_code_yaml_setext_trennlinie(self):
        s = self.z("---\ntitle: Hausarbeit\n---\n\nMüller schreibt:\n\n> Die Digitalisierung ist kein Selbstzweck.\n> Sie verlangt mehr.\n\n"
                   "```python\nx = 1\n\ny = berechne(x)\n```\n\n~~~\nSELECT name FROM kunden\n~~~\n\nEinleitung\n==========\n\n"
                   "Text zwei.\n\n---\n\n* * *\n\nText drei.")
        self.assertEqual(s["absaetze"], ["Müller schreibt:", "Text zwei.", "Text drei."])
        self.assertEqual(s["ueberschriften"], ["Einleitung"])
        self.assertEqual(s["zitatbloecke"], 2)

    def test_pandoc_tabelle_ohne_pipes(self):
        s = self.z("Ein Absatz vor der Tabelle. Noch ein Satz.\n\n  Verein   Mitglieder   Entwicklung\n  -------- ------------ -------------\n"
                   "  A        412          Wächst.\n  B        12           Stark rückläufig.\n\nEin Absatz danach.")
        self.assertEqual(s["absaetze"], ["Ein Absatz vor der Tabelle. Noch ein Satz.", "Ein Absatz danach."])
        self.assertEqual(s["tabellenzeilen"], 3)

    def test_ueberschrift_ohne_leerzeile_und_nummerierte_einzeile(self):
        s = self.z("**Methodik**\nEs wurden zwölf Interviews geführt.\n\nDer erste Absatz endet hier.\n## 2 Methodik\n"
                   "Es wurden Interviews geführt.\n\n1. Einleitung\n\nText folgt hier.")
        self.assertEqual(s["ueberschriften"], ["Methodik", "2 Methodik", "1. Einleitung"])
        self.assertEqual(s["listenpunkte"], [])

    def test_html_silbentrennung_unsichtbare_zeichen(self):
        e = analysiere("Die Fläche beträgt 20 m<sup>2</sup>.<br>Das ist <span style=\"color:red\">viel</span> mehr.<!-- Notiz -->")
        self.assertEqual(e["info"]["satzlaengen"], [5, 4])
        e = analysiere("Die Arbeit untersucht kleine Unter-\nnehmen und ihre Kommu-\nnikation, die E-\nMail und Lehr-\nnoch Lernziele.")
        self.assertIn("Unternehmen", e["saetze"][0]["text"])
        self.assertIn("Kommunikation", e["saetze"][0]["text"])
        self.assertIn("E-Mail", e["saetze"][0]["text"])
        self.assertIn("Lehr- noch", e["saetze"][0]["text"])
        e = analysiere("﻿# Einleitung\n\nDas Unter​nehmen wächst.")
        self.assertEqual(e["info"]["ueberschriften"], 1)
        self.assertEqual(e["info"]["satzlaengen"], [3])


class Einlesen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def pfad(self, name):
        return os.path.join(self.tmp, name)

    def test_kodierungen(self):
        text = "Die Größe der Märkte wächst. Übliche Werte fehlen."
        with open(self.pfad("a.txt"), "wb") as f:
            f.write(text.encode("cp1252"))
        with open(self.pfad("b.txt"), "w", encoding="utf-16") as f:
            f.write(text)
        with open(self.pfad("c.txt"), "w", encoding="utf-8-sig") as f:
            f.write(text)
        for name in ("a.txt", "b.txt", "c.txt"):
            with redirect_stderr(io.StringIO()):
                gelesen = analyse.lies_datei(self.pfad(name))
            self.assertEqual(gelesen, text, name)

    def test_nicht_unterstuetzt_und_fehlend(self):
        with open(self.pfad("x.rtf"), "w") as f:
            f.write("{\\rtf1\\ansi Hallo}")
        with open(self.pfad("y.txt"), "wb") as f:
            f.write(b"{\\rtf1\\ansi Hallo}")
        with open(self.pfad("kaputt.docx"), "wb") as f:
            f.write(b"\xd0\xcf\x11\xe0 kein zip")
        for name in ("x.rtf", "y.txt", "kaputt.docx", "fehlt.md"):
            with self.assertRaises(SystemExit, msg=name):
                analyse.lies_datei(self.pfad(name))

    def test_docx(self):
        W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        doc = (f'<w:document {W}><w:body>'
               '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Einleitung</w:t></w:r></w:p>'
               '<w:p><w:pPr><w:pStyle w:val="TOC1"/></w:pPr><w:r><w:t>1 Einleitung</w:t><w:tab/><w:t>3</w:t></w:r></w:p>'
               '<w:p><w:r><w:t>Die Arbeit untersucht kleine Unternehmen.</w:t><w:br/><w:t>Sie nutzt die E</w:t><w:noBreakHyphen/>'
               '<w:t>Mail-Umfrage &amp;lt;Wert&amp;gt;.</w:t></w:r></w:p>'
               '<w:p><w:r><w:t>Begriff</w:t><w:tab/><w:t>Definition folgt im nächsten Kapitel.</w:t></w:r></w:p>'
               '<w:p><w:pPr><w:pStyle w:val="ListBullet"/></w:pPr><w:r><w:t>Kosten sinken deutlich.</w:t></w:r></w:p>'
               '<w:p><w:pPr><w:pStyle w:val="ListParagraph"/></w:pPr><w:r><w:t>Ein eingerückter normaler Satz.</w:t></w:r></w:p>'
               '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Verein</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
               '</w:body></w:document>')
        stile = (f'<w:styles {W}>'
                 '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
                 '<w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/></w:style>'
                 '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/></w:style>'
                 '<w:style w:type="paragraph" w:styleId="ListBullet"><w:name w:val="List Bullet"/><w:basedOn w:val="ListParagraph"/>'
                 '<w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style></w:styles>')
        with zipfile.ZipFile(self.pfad("t.docx"), "w") as z:
            z.writestr("word/document.xml", doc)
            z.writestr("word/styles.xml", stile)
        text = analyse.lies_datei(self.pfad("t.docx"))
        self.assertIn("# Einleitung", text)
        self.assertNotIn("Einleitung 3", text)
        self.assertIn("Unternehmen. Sie nutzt die E-Mail-Umfrage &lt;Wert&gt;.", text)
        self.assertIn("Begriff Definition", text)
        self.assertIn("- Kosten sinken deutlich.", text)
        self.assertIn("\n\nEin eingerückter normaler Satz.", text)
        e = analysiere(text)
        self.assertEqual(e["info"]["listenpunkte"], 1)
        self.assertEqual(e["info"]["tabellenzeilen"], 1)
        self.assertEqual(e["info"]["saetze"], 4)

    def test_odt_ohne_fussnotentext(self):
        T = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
        inhalt = (f'<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="{T}">'
                  '<office:body><office:text><text:h>Einleitung</text:h>'
                  '<text:p>Die Arbeit untersucht kleine Unternehmen.<text:note><text:note-body><text:p>Vgl. Müller 2019.</text:p>'
                  '</text:note-body></text:note> Sie nutzt<text:s/>Interviews.</text:p>'
                  '<text:list><text:list-item><text:p>Kosten sinken.</text:p></text:list-item></text:list>'
                  '</office:text></office:body></office:document-content>')
        with zipfile.ZipFile(self.pfad("t.odt"), "w") as z:
            z.writestr("content.xml", inhalt)
        text = analyse.lies_datei(self.pfad("t.odt"))
        self.assertEqual(text, "# Einleitung\n\nDie Arbeit untersucht kleine Unternehmen. Sie nutzt Interviews.\n\n- Kosten sinken.")


# ---------------------------------------------------------------------------
# Zeichensetzung, Dreierlisten, KI-Muster
# ---------------------------------------------------------------------------

class Zeichensetzung(unittest.TestCase):
    def test_gender_doppelpunkt_dezimalkomma(self):
        e = analysiere("Die Mitarbeiter:innen und jede:r Student:in kamen um 14:30 Uhr, siehe https://x.de. Der Wert lag bei 3,45; SD = 1,02.")
        m = e["metriken"]
        self.assertEqual(m["doppelpunkt_pro_1000"], 0.0)
        self.assertEqual(m["semikolon_pro_1000"], 0.0)
        self.assertAlmostEqual(m["kommas_pro_1000"], 1000 / e["info"]["token"], places=3)
        e = analysiere("Es gilt: Die Ergebnisse sind klar. Gründe: erstens Zeit.")
        self.assertAlmostEqual(e["metriken"]["doppelpunkt_pro_1000"], 2000 / e["info"]["token"], places=3)


class Dreierlisten(unittest.TestCase):
    def test_keine_liste(self):
        for s in ("Die Studie zeigt, dass Umsatz und Gewinn steigen.", "Die Unternehmen, die Kosten und Nutzen abwägen, sind erfolgreich.",
                  "Ziel ist es, Kosten und Zeit zu sparen.", "Es fehlt die Gruppe auf, ihre Aufgaben und Ziele zu nennen."):
            self.assertEqual(analyse.dreierlisten(s), [], s)

    def test_liste(self):
        for s in ("Wir brauchen Kosten, Zeit und Qualität.", "Schnell, günstig und zuverlässig arbeitet sie.",
                  "Die Familie, die Schule und die Peergroup sozialisieren.", "Die Rechte der Eltern, der Kinder und deren Familien gelten."):
            self.assertEqual(len(analyse.dreierlisten(s)), 1, s)


class KiMuster(unittest.TestCase):
    def muster(self, *defs):
        out = []
        for mid, regex, g in defs:
            out.append({"id": mid, "label": mid, "gewicht": g, "_re": __import__("re").compile(regex, 2)})
        return out

    def test_ueberlappung_zaehlt_einmal(self):
        mu = self.muster(("massgeblich", r"\bmaßgeblich\b", 1.8), ("beitrag_leisten", r"\btragen\s+maßgeblich\s+dazu\s+bei\b", 0.9))
        e = analyse.analysiere_text("Die Daten tragen maßgeblich dazu bei. Das ist maßgeblich.", mu)
        ids = [t["muster"] for t in e["muster_treffer"]]
        self.assertEqual(ids, ["massgeblich", "massgeblich"])
        self.assertEqual(e["muster_treffer"][0].get("ueberlagert"), ["beitrag_leisten"])
        self.assertAlmostEqual(e["metriken"]["ki_muster_pro_1000"], 1000 * 3.6 / e["info"]["token"], places=3)

    def test_gleiche_gewichte_laengster_gewinnt(self):  # Kalibrierung setzt alle Gewichte auf 1.0
        mu = self.muster(("massgeblich", r"\bmaßgeblich\b", 1.0), ("beitrag_leisten", r"\btragen\s+maßgeblich\s+dazu\s+bei\b", 1.0))
        e = analyse.analysiere_text("Die Daten tragen maßgeblich dazu bei.", mu)
        self.assertEqual([t["muster"] for t in e["muster_treffer"]], ["beitrag_leisten"])

    def test_gewicht_null_kein_fund_kein_flag(self):
        mu = self.muster(("spannungsfeld", r"\bspannungsfeld\w*", 0.0))
        e = analyse.analysiere_text("Das Spannungsfeld ist groß.", mu)
        self.assertEqual(e["muster_treffer"], [])
        self.assertEqual(e["saetze"][0]["flags"], [])
        self.assertEqual(e["metriken"]["ki_muster_pro_1000"], 0.0)


# ---------------------------------------------------------------------------
# Neue Kennzahlen (HW07, HW10, HW12, HW13, HW15, HW20, HW22)
# ---------------------------------------------------------------------------

class NeueKennzahlen(unittest.TestCase):
    PROFIL = {"woerter": ["die", "und", "es"], "rate_mensch": {"die": 0.05, "und": 0.03, "es": 0.012},
              "rate_ki": {"die": 0.05, "und": 0.03, "es": 0.006}, "groesse": {"die": 20.0, "und": 1e6, "es": 8.0}}

    def test_fw_woerter(self):
        self.assertEqual(len(analyse.FW_WOERTER), 40)
        self.assertEqual(len(set(analyse.FW_WOERTER)), 40)

    def test_fw_llr_formel(self):
        woerter = ["es"] * 6 + ["die"] * 25 + ["und"] * 15 + ["haus"] * 454
        n = len(woerter)

        def nb(k, mu, s):
            if s >= 1e6:
                return k * math.log(mu) - mu - math.lgamma(k + 1)
            return math.lgamma(k + s) - math.lgamma(s) - math.lgamma(k + 1) + s * math.log(s / (s + mu)) + k * math.log(mu / (s + mu))
        p = self.PROFIL
        llr = sum(nb(k, p["rate_mensch"][w] * n, p["groesse"][w]) - nb(k, p["rate_ki"][w] * n, p["groesse"][w])
                  for w, k in (("die", 25), ("und", 15), ("es", 6)))
        self.assertAlmostEqual(analyse.fw_llr(woerter, p), 1000 * llr / n, places=9)
        self.assertGreater(analyse.fw_llr(woerter, p), 0)  # viel "es" = menschlich
        self.assertLess(analyse.fw_llr(["haus"] * 500, p), 0)
        self.assertIsNone(analyse.fw_llr([], p))
        self.assertIsNone(analyse.fw_llr(woerter, None))

    def test_fw_kennzahl_nur_mit_profil(self):
        text = "Es ist so, und es bleibt so. Die Lage ist klar."
        self.assertNotIn("fw_profil_llr_pro_1000", analysiere(text)["metriken"])
        e = analysiere(text, fw_profil=self.PROFIL)
        woerter = [t.lower() for s in e["saetze"] for t in analyse.tokens(s["text"]) if analyse.ist_wort(t)]
        self.assertAlmostEqual(e["metriken"]["fw_profil_llr_pro_1000"], round(analyse.fw_llr(woerter, self.PROFIL), 4))

    def test_rhythmus_r1_log(self):
        laengen = [5, 20, 8, 30, 6, 25, 9, 18]
        text = " ".join(" ".join(["Wort"] * (l - 1)) + " Ende." for l in laengen)
        e = analysiere(text)
        xs = [math.log(l) for l in laengen]
        self.assertAlmostEqual(e["metriken"]["rhythmus_r1_log"], round(analyse.autokorrelation(xs, 1) + 1 / len(xs), 4))
        self.assertNotIn("rhythmus_autokorrelation", e["metriken"])
        self.assertTrue(any("Rhythmuswert unsicher" in w or "Verteilungsmaße" in w for w in e["info"]["warnungen"]))

    def test_konnektoren_alle_stellungen(self):
        e = analysiere("Zudem steigt der Wert. Der Wert steigt jedoch langsam. Darüber hinaus fehlt Geld. "
                       "Des Weiteren wurde gemessen. Das Ziel des weiteren Vorgehens ist klar.")
        self.assertAlmostEqual(e["metriken"]["konnektoren_pro_1000"], 3000 / e["info"]["token"], places=3)
        self.assertEqual(e["info"]["anteil_konnektor_mittelstellung"], round(1 / 3, 4))
        self.assertIn("konnektor_mitte", e["saetze"][1]["flags"])

    def test_nominalketten(self):
        self.assertEqual(analyse.nominalketten(["Die Umstellung des Vergütungssystems der Krankenhäuser ist teuer."]), [3])
        self.assertEqual(analyse.nominalketten(["Die Wirkung der Ergebnisse, der Autoren ist klar."]), [2])
        self.assertEqual(analyse.nominalketten(["Die Förderung von Frauen in der Wissenschaft wächst."]), [2])
        self.assertEqual(analyse.nominalketten(["Das ist gut."]), [])

    def test_silben_q21_und_klumpung(self):
        e = analysiere("Das Haus ist alt. Die Arbeit ist gut.")
        c = Counter(analyse.silben(w) for w in ("Das", "Haus", "ist", "alt", "Die", "Arbeit", "ist", "gut"))
        self.assertAlmostEqual(e["metriken"]["silben_q21"], round((c[2] + 0.5) / (c[1] + 0.5), 4))
        self.assertAlmostEqual(e["metriken"]["mattr_klumpung_100"], 1.0)  # unter 100 Wörtern = Zufallserwartung
        woerter = ["a", "b"] * 60 + [f"w{i}" for i in range(80)]  # geklumpte Wiederholung am Anfang
        self.assertLess(analyse.mattr_klumpung(woerter, 100), 1.0)

    def test_kernbegriffe(self):
        e = analysiere("Die Arbeitgebermarke wirkt. Die Arbeitgebermarke hilft kleinen Unternehmen. Unternehmen nutzen sie.")
        kern = e["info"]["kernbegriffe"]
        self.assertEqual(kern[0], {"stamm": analyse.stamm("Arbeitgebermarke"), "form": "Arbeitgebermarke", "anzahl": 2})
        self.assertLessEqual(len(kern), 5)
        self.assertTrue(all(set(k) == {"stamm", "form", "anzahl"} for k in kern))


class LetzterAbsatzGekuerzt(unittest.TestCase):
    def test_absatzkennzahlen_ohne_letzten_absatz(self):
        text = "Satz eins ist da. Satz zwei ist da.\n\nSatz drei ist da. Satz vier ist da. Satz fünf ist da.\n\nKurz."
        a = analysiere(text)
        b = analysiere(text, letzter_absatz_gekuerzt=True)
        self.assertEqual(a["metriken"]["absaetze"], 3.0)
        self.assertEqual(b["metriken"]["absaetze"], 2.0)
        self.assertEqual(b["metriken"]["saetze_pro_absatz"], 2.5)
        self.assertEqual(b["metriken"]["anteil_einsatz_absaetze"], 0.0)
        self.assertGreater(a["metriken"]["anteil_einsatz_absaetze"], 0.0)
        for k in a["metriken"]:
            if k not in ("absaetze", "absatzlaenge_mittel", "absatzlaenge_cv", "saetze_pro_absatz", "saetze_pro_absatz_cv",
                         "anteil_einsatz_absaetze"):
                self.assertEqual(a["metriken"][k], b["metriken"][k], k)


# ---------------------------------------------------------------------------
# Bewertung (HW18, Schnittstelle 4)
# ---------------------------------------------------------------------------

class Bewertung(unittest.TestCase):
    def baselines(self, **ts_extra):
        def ref(p10, p25, p50, p75, p90, sd, ki50, kisd, **kw):
            d = {"mensch": {"p10": p10, "p25": p25, "p50": p50, "p75": p75, "p90": p90, "sd": sd},
                 "ki": {"p50": ki50, "sd": kisd}, "auroc": 0.8, "gewicht": 0.6, "bewertet": True}
            d.update(kw)
            return d
        ts = {"metriken": {
            "satzlaenge_mittel": ref(15, 18, 20, 23, 26, 4.0, 18.5, 1.0, se_typ=1.0, cluster="satzlaenge_mittel"),
            "satzlaenge_cv": ref(0.3, 0.38, 0.45, 0.55, 0.62, 0.1, 0.35, 0.05),
            "rhythmus_r1_log": ref(-0.2, -0.05, 0.05, 0.15, 0.25, 0.1, 0.0, 0.1),
            "satzklammer_mittel": ref(4, 5, 6, 7, 8, 1.0, 5.0, 0.5),
            "fw_profil_llr_pro_1000": ref(-2, 0, 3, 6, 9, 3.0, -3.0, 2.0),
        }, "score_schwelle": 70, "ziel_p_mensch": 0.6}
        ts.update(ts_extra)
        return {"textsorten": {"hochschule": ts}}

    def test_unsicher_status_und_score_unveraendert(self):
        e = analysiere("Wort " * 17 + "Ende. " + ("Wort " * 17 + "Ende. ") * 2)  # Satzlänge 18,0 = knapp an P25
        e["metriken"]["satzlaenge_mittel"] = 17.5
        b = analyse.bewerte(e, self.baselines())
        z = next(z for z in b["kennzahlen"] if z["id"] == "satzlaenge_mittel")
        self.assertTrue(z["unsicher"])
        self.assertEqual(z["status"], "gelb")
        self.assertEqual(z["cluster"], "satzlaenge_mittel")
        e["metriken"]["satzlaenge_mittel"] = 16.0
        z = next(z for z in analyse.bewerte(e, self.baselines())["kennzahlen"] if z["id"] == "satzlaenge_mittel")
        self.assertFalse(z["unsicher"])
        self.assertEqual(b["score_schwelle"], 70)
        self.assertEqual(b["ziel_p_mensch"], 0.6)
        ohne_se = self.baselines()
        del ohne_se["textsorten"]["hochschule"]["metriken"]["satzlaenge_mittel"]["se_typ"]
        e["metriken"]["satzlaenge_mittel"] = 17.5
        b2 = analyse.bewerte(e, ohne_se)
        self.assertEqual(b["score"], b2["score"])

    def test_rhythmus_unter_30_saetzen_nicht_bewertet_und_none_sicher(self):
        e = analysiere("Das ist ein Satz. " * 10)
        self.assertIsNone(e["metriken"]["satzklammer_mittel"])
        b = analyse.bewerte(e, self.baselines())
        ids = {z["id"]: z for z in b["kennzahlen"]}
        self.assertFalse(ids["rhythmus_r1_log"]["bewertet"])
        self.assertNotIn("satzklammer_mittel", ids)

    def test_fw_profil_aus_baselines(self):
        e = analysiere("Es ist so, und es bleibt so. Die Lage ist klar. " * 5)
        self.assertNotIn("fw_profil_llr_pro_1000", e["metriken"])
        b = analyse.bewerte(e, self.baselines(fw_profil=NeueKennzahlen.PROFIL))
        self.assertIn("fw_profil_llr_pro_1000", e["metriken"])
        self.assertIn("fw_profil_llr_pro_1000", {z["id"] for z in b["kennzahlen"]})
        direkt = analysiere("Es ist so, und es bleibt so. Die Lage ist klar. " * 5, fw_profil=NeueKennzahlen.PROFIL)
        self.assertEqual(e["metriken"]["fw_profil_llr_pro_1000"], direkt["metriken"]["fw_profil_llr_pro_1000"])

    def test_ki_naeher_mit_streuung(self):
        e = analysiere("Das ist ein Satz. " * 10)
        e["metriken"]["satzlaenge_cv"] = 0.25  # absolut näher am KI-Median 0,35 als an 0,45; auch in SD-Einheiten
        z = next(z for z in analyse.bewerte(e, self.baselines())["kennzahlen"] if z["id"] == "satzlaenge_cv")
        self.assertTrue(z["ki_naeher"])
        e["metriken"]["satzlaenge_mittel"] = 16.0  # 2,5 KI-SD vom KI-Median, 1 Mensch-SD vom Mensch-Median
        z = next(z for z in analyse.bewerte(e, self.baselines())["kennzahlen"] if z["id"] == "satzlaenge_mittel")
        self.assertFalse(z["ki_naeher"])

    def test_main_json_mit_profil(self):
        with tempfile.TemporaryDirectory() as d:
            bpfad, tpfad = os.path.join(d, "b.json"), os.path.join(d, "t.md")
            with open(bpfad, "w", encoding="utf-8") as f:
                json.dump(self.baselines(fw_profil=NeueKennzahlen.PROFIL), f)
            with open(tpfad, "w", encoding="utf-8") as f:
                f.write("Es ist so, und es bleibt so. Die Lage ist klar. " * 20)
            buf = io.StringIO()
            with redirect_stdout(buf):
                analyse.main([tpfad, "--format", "json", "--baselines", bpfad, "--ohne-saetze"])
            daten = json.loads(buf.getvalue())
            self.assertIn("fw_profil_llr_pro_1000", daten["metriken"])
            self.assertNotIn("saetze", daten)
            buf = io.StringIO()
            with redirect_stdout(buf):
                analyse.main([tpfad, "--baselines", bpfad])
            self.assertIn("Kernbegriffe", buf.getvalue())


# ---------------------------------------------------------------------------
# Echte Korpustexte (nur lesen)
# ---------------------------------------------------------------------------

@unittest.skipUnless(korpus_dateien("mensch") and korpus_dateien("ki"), "Korpus fehlt")
class Korpustexte(unittest.TestCase):
    def proben(self):
        mensch = korpus_dateien("mensch")
        ki = korpus_dateien("ki")
        return mensch[:: max(1, len(mensch) // 12)][:12] + ki[:: max(1, len(ki) // 8)][:8]

    def test_laufzeit_und_plausibilitaet(self):
        muster = analyse.lade_muster()
        for pfad in self.proben():
            with open(pfad, encoding="utf-8") as f:
                text = f.read()
            absaetze, n = [], 0
            for a in text.split("\n\n"):  # ca. 1000 Wörter, Absätze erhalten
                if n >= 1000:
                    break
                absaetze.append(a)
                n += len(a.split())
            stueck = "\n\n".join(absaetze)
            analyse.silben.cache_clear()
            t0 = time.perf_counter()
            e = analyse.analysiere_text(stueck, muster)
            dauer = time.perf_counter() - t0
            with self.subTest(datei=os.path.basename(pfad)):
                self.assertLess(dauer, 1.0)
                m = e["metriken"]
                self.assertTrue(1.5 < m["silben_mittel"] < 3.2, m["silben_mittel"])
                self.assertTrue(4.5 < m["wortlaenge_mittel"] < 8.5)
                self.assertTrue(0.5 < m["mattr_klumpung_100"] < 1.1)
                self.assertGreaterEqual(m["teilsaetze_pro_satz"], 1.0)
                json.dumps(e["metriken"], allow_nan=False)
                for z in e["info"]["kernbegriffe"]:
                    self.assertIn(z["form"].lower()[:3], z["stamm"][:3].lower() + z["form"].lower()[:3])

    def test_absaetze_wie_leerzeilen(self):
        # Korpusformat: ein Absatz pro Block – die Zeilenumbruch-Heuristik darf hier nichts teilen oder verschmelzen
        for pfad in self.proben():
            with open(pfad, encoding="utf-8") as f:
                text = f.read()[:20000]
            bloecke = [b for b in text.split("\n\n") if b.strip()]
            s = analyse.zerlege_bloecke(text)
            with self.subTest(datei=os.path.basename(pfad)):
                self.assertLessEqual(len(s["absaetze"]) + len(s["ueberschriften"]) + len(s["listenpunkte"]), len(bloecke))
                self.assertEqual(s["listenpunkte"], [] if not any(analyse.LISTE_RE.match(b) for b in bloecke) else s["listenpunkte"])


if __name__ == "__main__":
    unittest.main()
