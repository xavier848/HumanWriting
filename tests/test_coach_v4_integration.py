"""Tests für die Integration von Coach v4 (Funde aus Probeläufen und der CLI-Ende-zu-Ende-Probe über mehrere Runden):
Satzklammer-Quelle (Präposition je Subjunktion, Teilsatz direkt vor dem Nebensatz, Korrelat, Modalverb), Satzlängen-Hinweis
im Einklang mit der Selbsthilfe der Diagnose (Spielraum unter den harten Grenzen), Modalverb hinter Aufzählungskommas beim
Bündeln, Partikel-Stämme beim Begriffsbezug, lokale Wirkungsprüfung der Verdichtungs-Aufträge, „Bewusst stehen lassen“
neben einem anderen Auftrag und Gedächtnis ohne Wiederkehr gestrichener Hinweise.

Alle Texte sind synthetisch (keine Korpustexte).

python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
from test_coach_wirksamkeit import gleichmaessig, mit_metriken  # noqa: E402
from test_coach_v4 import lauf_bis_satzlaengen  # noqa: E402
from test_coach_v4_praezision import BEGRIFFE_TEXT  # noqa: E402
import test_coach_integration  # noqa: E402

FUELLER = ("Die Firma plant neue Wege für junge Leute in der Region. Viele Betriebe suchen seit Jahren dringend gute Fachkräfte. "
           "Die Kammer bietet dafür regelmäßig Kurse und Beratung an. Kleine Betriebe nutzen diese Angebote bisher eher selten.")


def klammer_hinweise(satz):
    """Satzklammer-Aufträge für einen Zielsatz (Merkmal als auffällig gesetzt, damit die Familie läuft)."""
    L = coach.Lauf(FUELLER + "\n\n" + satz + " " + FUELLER, None)
    L.ki_auffaellig = lambda *a, **k: True
    L.diag = {"modus": None}
    coach._satzklammer(L)
    nr = next(s["nr"] for s in L.saetze if s["text"] == satz)
    return [h for h in L.hinweise if h["satz"] == nr]


class KlammerQuelle(unittest.TestCase):
    def test_praeposition_passt_zur_subjunktion(self):
        weil = klammer_hinweise("Das Thema wird an dieser Stelle ausgeklammert, da es in eigenen Kapiteln ausführlich behandelt wird.")
        self.assertTrue(weil)
        self.assertIn("„wegen“ oder „aufgrund“", weil[0]["text"])
        self.assertNotIn("„zur“", weil[0]["text"])
        wenn = klammer_hinweise("Der Antrag wird von der Behörde geprüft, wenn alle Unterlagen vollständig eingereicht sind.")
        self.assertTrue(wenn)
        self.assertIn("„bei“", wenn[0]["text"])
        self.assertIn("keine Begründung", wenn[0]["text"])
        self.assertNotIn("„wegen“", wenn[0]["text"])

    def test_inhaltssatz_mit_korrelat(self):
        # Korrelat direkt vor dem Klammerende: Präposition aus dem Korrelat („auf“), nicht „bei“ oder „wegen“
        h = klammer_hinweise("Seit der Reform müssen Händler Kunden darauf hinweisen, wenn ein Preis automatisch personalisiert wurde.")
        self.assertTrue(h)
        self.assertIn("mit „auf“ – „darauf“ entfällt", h[0]["text"])
        self.assertNotIn("„bei“", h[0]["text"])
        # „da(r)…“-Wort an anderer Stelle (Adverb oder Korrelat?): mehrdeutig, kein Auftrag
        self.assertFalse(klammer_hinweise("Dabei wurde der Antrag von der Behörde sorgfältig geprüft, wenn alle Unterlagen "
                                          "vollständig vorlagen."))

    def test_nebensatz_gehoert_zum_teilsatz_davor(self):
        # vorangestellter Bedingungssatz mit leerer Klammer, der „ohne“-Teil gehört zum Relativsatz davor
        self.assertFalse(klammer_hinweise("Sind diese Bedingungen erfüllt, kann das Kind eine eigene Nische ausbilden, in der es "
                                          "Anerkennung erfährt, ohne in Konkurrenz zu treten."))
        # Klammer vor dem Doppelpunkt, „indem“ gehört zum Satz danach
        self.assertFalse(klammer_hinweise("Der Erzähler muss dabei in Vorleistung gehen: Er schenkt dem Publikum Vertrauen, indem er "
                                          "seine Sorgen offenlegt."))

    def test_modalverb_im_nebensatz_nicht(self):
        self.assertFalse(klammer_hinweise("Auf Gruppeninterviews wurde bewusst verzichtet, da die Befragten über belastende "
                                          "Erfahrungen sprechen sollten."))


class SatzlaengenSpielraum(unittest.TestCase):
    def test_kopfzeile_und_selbsthilfe_widersprechen_sich_nicht(self):
        c = coach.coache(gleichmaessig(8, 5), None, 40, roh=True)
        sl = c["satzlaengen"]
        self.assertEqual(sl["modus"], "buendeln")
        raum = sl["selbst_buendeln"]
        n_b = sum(1 for h in c["hinweise_roh"] if h["typ"] == "buendeln")
        self.assertGreaterEqual(raum, 0)
        self.assertLessEqual(raum + n_b, sl["kontingent"])  # nie über den menschlichen Median hinaus
        txt = coach.bericht(c)
        if raum:
            self.assertIn("Optional, kein Auftrag: zwei weitere Sätze derselben Quelle", txt)  # v5: Status klar
            self.assertNotIn("nicht mehr bündeln als unten genannt", txt)
        else:
            self.assertNotIn("Sätze derselben Quelle zur selben Sache verbinden", txt)

    def test_ohne_spielraum_keine_selbsthilfe_buendeln(self):
        L = lauf_bis_satzlaengen(gleichmaessig(8, 5))
        L.ausgesetzt.add("buendeln")  # z. B. Wächter: Bündeln ausgesetzt
        L._buendel_raum = None
        self.assertEqual(coach.buendel_raum(L), 0)
        d = coach._diagnose(L, [], 0.86)
        self.assertIsNotNone(d)
        for z in d["beitraege"]:
            if z["id"] in coach.LAENGEN_SELBST:
                self.assertIsNone(z["selbsthilfe"])
                # v5: kein Spielraum ist eine Grenze des Coaches – das Potenzial bleibt und zählt als „ohne Auftrag“
                self.assertEqual(z["wie"], "kein_raum")
                self.assertAlmostEqual(z["rest_logit"], z["potenzial_logit"] - z["erreichbar_logit"], places=2)
        txt = "\n".join(coach.diagnose_text(d))
        self.assertNotIn("zwei zusammengehörige mittellange Sätze", txt)

    def test_selbsthilfe_nennt_quelle_und_obergrenze(self):
        self.assertIn("derselben Quelle", coach.SELBSTHILFE["anteil_mittlere_saetze"])
        self.assertIn("derselben Quelle", coach.SELBSTHILFE_HEBEL["satzlaenge"])
        self.assertIn("etwa 40 Wörtern", coach.SELBSTHILFE["anteil_sehr_lange_saetze"])
        self.assertNotIn("40 Wörter und mehr", coach.SELBSTHILFE["anteil_sehr_lange_saetze"])


class BuendelnHauptsatz(unittest.TestCase):
    def test_hauptsatz_hinter_aufzaehlungskommas(self):
        h = coach.hauptsatz_teile("Aufgaben wie die Datensammlung, die Prüfung von Buchungen, die Erstellung von Berichten oder "
                                  "einfache Analysen können durch neue Systeme automatisiert werden.")
        self.assertIn("können", h)
        self.assertNotIn("sollte", coach.hauptsatz_teile("Data Governance wird damit zu einem Thema, an dem das Controlling "
                                                         "mitwirken sollte."))
        self.assertNotIn("können", coach.hauptsatz_teile("Viele verlieren an Zuversicht, ihre Ziele durch Leistung erreichen zu "
                                                         "können (−0,22)."))
        self.assertIn("können", coach.hauptsatz_teile("Unternehmen, die digitale Werkzeuge nutzen, können Kosten senken."))

    def test_modalverb_hinter_aufzaehlung_sperrt_bundeln(self):
        a = "Ein erstes zentrales Ergebnis betrifft die Automatisierung von Routinetätigkeiten in der Firma."
        b = ("Aufgaben wie die Datensammlung, die Prüfung von Buchungen und einfache Analysen können durch neue Systeme in der "
             "Firma automatisiert werden.")
        L = coach.Lauf(FUELLER + "\n\n" + a + " " + b + " " + FUELLER, None)
        sa = next(s for s in L.saetze if s["text"] == a)
        sb = next(s for s in L.saetze if s["text"] == b)
        self.assertEqual(coach.buendel_paar_grund(L, sa, sb, laenge=False), "b_modal_rede")

    def test_partikel_ist_kein_gemeinsamer_begriff(self):
        a = "Neben dem Verständnis betrieblicher Zusammenhänge brauchen sie heute auch Kompetenzen in Statistik."
        b = "In vielen Firmen bilden sich neue Rollen heraus, die eng mit den klassischen Controllern zusammenarbeiten."
        L = coach.Lauf(FUELLER + "\n\n" + a + " " + b + " " + FUELLER, None)
        sa = next(s for s in L.saetze if s["text"] == a)
        sb = next(s for s in L.saetze if s["text"] == b)
        self.assertEqual(analyse.stamm("Zusammenhänge"), analyse.stamm("zusammenarbeiten"))  # Kürzung auf 8 Buchstaben
        self.assertFalse(coach.nomen_bezug(L, sa, sb))
        # v5: ein gemeinsames Bestimmungswort allein („Therapie-“) ist kein Bezug (v4-Kritik: ssoar-21977 „Reproduktionszeiten“ –
        # „Reproduktionsgedanke“); Komposita mit gemeinsamem Grundwort zählen weiter
        a2 = "Die Vermittlung an Therapieeinrichtungen stand anfangs im Vordergrund der Arbeit."
        b2 = "Bis zum Therapiebeginn vergingen jedoch häufig lange Wartezeiten für die Betroffenen."
        L2 = coach.Lauf(FUELLER + "\n\n" + a2 + " " + b2 + " " + FUELLER, None)
        self.assertFalse(coach.nomen_bezug(L2, next(s for s in L2.saetze if s["text"] == a2),
                                           next(s for s in L2.saetze if s["text"] == b2)))
        b3 = "Auch die Beratungseinrichtungen der Stadt meldeten in dieser Zeit lange Wartezeiten."
        L3 = coach.Lauf(FUELLER + "\n\n" + a2 + " " + b3 + " " + FUELLER, None)
        self.assertTrue(coach.nomen_bezug(L3, next(s for s in L3.saetze if s["text"] == a2),
                                          next(s for s in L3.saetze if s["text"] == b3)))


class WirkungVerdichtung(unittest.TestCase):
    ALT = "Digitale Lösungen sind dafür eine wesentliche Voraussetzung, da sich die Datenmengen manuell kaum bewältigen lassen."
    NEU = "Digitale Lösungen sind dafür aufgrund der manuell kaum zu bewältigenden Datenmengen eine wesentliche Voraussetzung."

    def test_lokal_wirksam_ueber_teilsaetze(self):
        L = coach.Lauf(FUELLER + "\n\n" + self.NEU + " " + FUELLER, None)
        h = {"typ": "nebensatz", "anfang": coach.schluessel_anfang(self.ALT), "teilsaetze": 2}
        self.assertNotIn(h["anfang"], L.anfang_index)  # Satzanfang durch den Umbau verändert …
        self.assertIsNotNone(coach._satz_ungefaehr(L, h["anfang"]))  # … aber über die ersten vier Wörter gefunden
        self.assertTrue(coach.lokal_wirksam(L, h))
        self.assertFalse(coach.lokal_wirksam(L, dict(h, teilsaetze=1)))
        self.assertIsNone(coach.lokal_wirksam(L, {"typ": "nebensatz", "anfang": h["anfang"]}))  # alter Verlauf ohne Zahl

    def test_teilsaetze_im_verlauf(self):
        text = FUELLER + "\n\n" + self.ALT + " " + FUELLER
        L = coach.Lauf(text, None)
        s = next(x for x in L.saetze if x["text"] == self.ALT)
        L.hinweis("nebensatz", s, "Auftrag", 1.0)
        self.assertEqual(L.hinweise[-1]["teilsaetze"], 2)
        L.hinweis("floskel", next(x for x in L.saetze if x["nr"] == 1), "Auftrag", 1.0)
        self.assertIsNone(L.hinweise[-1]["teilsaetze"])


class StehenLassen(unittest.TestCase):
    def test_anderer_auftrag_am_selben_satz_gilt(self):
        c = coach.coache(gleichmaessig(8, 5), None, 40)
        h = next(x for x in c["hinweise"] if x.get("satz"))
        c["stehen_lassen"] = [{"satz": h["satz"], "anfang": "x"}]
        zeile = next(z for z in coach.bericht(c).splitlines() if "Bewusst stehen lassen" in z)
        self.assertIn(f"der andere Auftrag zu S{h['satz']} oben gilt trotzdem", zeile)
        c["stehen_lassen"] = [{"satz": 999, "anfang": "x"}]
        zeile = next(z for z in coach.bericht(c).splitlines() if "Bewusst stehen lassen" in z)
        self.assertNotIn("gilt trotzdem", zeile)


class GedaechtnisOhneWiederkehr(unittest.TestCase):
    def test_gestrichene_begriffsaufnahme_kommt_bei_erneuter_messung_nicht_wieder(self):
        def lauf(verlauf=None, text=BEGRIFFE_TEXT):
            with mit_metriken(anteil_saetze_mit_wortaufnahme=0.2):
                return coach.coache(text, verlauf, 40, roh=True)
        kb = lambda c: [x for x in c["hinweise_roh"] if x["typ"] == "kein_bezug"]  # noqa: E731
        c1 = lauf()
        self.assertTrue(kb(c1))
        text = BEGRIFFE_TEXT.replace("Erste Förderprogramme der Länder", "Erste Programme der Länder")
        c2 = lauf({"messungen": [c1["stand"]]}, text)  # überarbeitet, Stellen übersprungen: gestrichen
        self.assertFalse(kb(c2))
        c3 = lauf({"messungen": [c1["stand"], c2["stand"]]}, text)  # danach nur erneut gemessen
        self.assertTrue(c3["fortschritt"]["unveraendert"])
        self.assertFalse(kb(c3))

    def test_synonym_hinweis_pendelt_nicht(self):
        text = test_coach_integration.SynonymTeilschutz.TEXT + "\n\n" + gleichmaessig(3, 5)
        syn = lambda c: [x for x in c["hinweise_roh"] if x["typ"] == "synonyme"]  # noqa: E731
        # Wortaufnahme fest im grünen Bereich, sonst setzt der Überkorrektur-Wächter die Begriffs-Hinweise ohnehin aus
        with mit_metriken(mattr_100=0.9, anteil_saetze_mit_wortaufnahme=0.5):
            c1 = coach.coache(text, None, 40, roh=True)
            t2 = text.replace("Die Kunden lesen Testberichte.", "Die Kunden lesen oft Testberichte.")
            c2 = coach.coache(t2, {"messungen": [c1["stand"]]}, 40, roh=True)
            t3 = t2.replace("Die Kunden lesen oft Testberichte.", "Die Kunden lesen sehr oft Testberichte.")
            c3 = coach.coache(t3, {"messungen": [c1["stand"], c2["stand"]]}, 40, roh=True)
        self.assertNotIn("synonyme", c3["ausgesetzt"])
        self.assertTrue(syn(c1))
        self.assertFalse(syn(c2))
        self.assertFalse(syn(c3))  # nicht in der übernächsten Runde wieder (genannt – still – genannt)


if __name__ == "__main__":
    unittest.main()
