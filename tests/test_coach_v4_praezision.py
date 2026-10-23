"""Tests für Coach v4 (Präzision): Gegenfolie als Info statt Auftrag, Begriffsaufnahme nur mit benanntem Wortpaar,
Funktionswort-Stellenliste, Ersatzverben ohne Dopplung und Folgerungsverben, thematische Absatzwahl, Floskel-Ersatz ohne
Steigerung, Abkürzungen bis zum Median, Gender als „ersetzbar“, strengere Konnektoren, Konsistenz nach Ersetzungen,
widerspruchsfreie kombinierte Aufträge und Aufträge im Einklang mit Wächter und Hebeln.

Alle Texte sind synthetisch (keine Korpustexte).

python3 -m unittest discover -s tests
"""
import os
import re
import sys
import unittest
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
import inhalt_check  # noqa: E402
from test_coach import KI_TEXT  # noqa: E402
from test_coach_wirksamkeit import gleichmaessig, mit_metriken  # noqa: E402

# Nachbarsätze ohne gemeinsamen Wortstamm: zwei Paare mit möglicher Bezeichnung derselben Sache (Preissetzung/Preisgestaltung,
# Systemlandschaften/IT-Landschaft), sonst Themenwechsel
BEGRIFFE_TEXT = (
    "Die Preissetzung im Einzelhandel folgt heute oft festen Regeln und Tabellen der Zentrale. "
    "Viele Anbieter passen die Preisgestaltung inzwischen mehrmals täglich an die aktuelle Nachfrage an. "
    "Algorithmen werten dafür Wetterdaten, Lagerbestände und Konkurrenzangebote in Echtzeit aus. "
    "Kritiker bemängeln seit Jahren fehlende Transparenz gegenüber der Kundschaft im Netz.\n\n"
    "Heterogene Systemlandschaften erschweren vielen mittelständischen Betrieben den Einstieg erheblich. "
    "Eine einheitliche IT-Landschaft gilt in Befragungen trotzdem selten als vorrangiges Ziel der Geschäftsführung. "
    "Investitionen fließen stattdessen meist in sichtbare Projekte mit schnellem Nutzen für den Vertrieb. "
    "Langfristige Schulungsprogramme für das Personal bleiben häufig auf der Strecke.\n\n"
    "Gesetzliche Vorgaben zur Barrierefreiheit treten im kommenden Sommer schrittweise in Kraft. "
    "Kleine Händler fürchten hohe Anpassungskosten bei älteren Onlineshops und Apps. "
    "Verbände fordern deshalb längere Übergangsfristen und kostenlose Beratungsangebote. "
    "Erste Förderprogramme der Länder sollen ab Herbst Abhilfe schaffen.")

ALS_TEXT = (
    "Die Literatur definiert die Arbeitgebermarke als Versprechen an künftige Beschäftigte. "
    "Viele Betriebe sehen die Marke als Werkzeug der Personalgewinnung. "
    "Kleine Firmen haben weniger als fünfzig Beschäftigte und kaum eigene Personalabteilungen. "
    "Die Autoren bezeichnen diese Haltung als pragmatisch. "
    "Die Marke wirkt sowohl nach außen als auch nach innen. "
    "Als Grundlage nutzen viele Betriebe einfache Umfragen unter den Beschäftigten. "
    "Der Bericht dient als Grundlage der jährlichen Planung im Betrieb. "
    "Die Geschäftsführung versteht die Marke als Aufgabe der gesamten Belegschaft. "
    "Größere Unternehmen investieren deutlich mehr als kleine Betriebe in ihre Außendarstellung. "
    "Die Beratung gilt als teuer und wird deshalb selten genutzt.")


def h(typ, satz, text=None, **extra):
    stelle = f"Satz {satz} („Anfang …“)"
    return {"typ": typ, "hebel": coach.TYP_HEBEL.get(typ, typ), "satz": satz, "absatz": 1, "stelle": stelle,
            "text": text or f"{stelle}: Auftrag {typ}.", "gewicht": 1.0, "ersetzbar": [], "weitere_nr": [], **extra}


def leerer_stand(**extra):
    return {"score": 40, "p_mensch": 0.05, "kennzahlen": {}, "roh": {}, "hinweise": [], **extra}


class GegenfolieAlsInfo(unittest.TestCase):
    TEXT = gleichmaessig(6, 5) + "\n\nDie Firmen sehen den Bericht nicht nur als Last, sondern auch als Instrument der Steuerung im Betrieb."

    def lauf(self, verlauf=None):
        with mit_metriken(sondern_pro_1000=3.0):
            return coach.coache(self.TEXT, verlauf, 40, roh=True)

    def test_beibehalten_ist_kein_auftrag(self):
        c = self.lauf()
        nr = next(s["nr"] for s in analyse.analysiere_text(self.TEXT)["saetze"] if s["text"].startswith("Die Firmen sehen"))
        self.assertFalse([x for x in c["hinweise_roh"] if x["typ"] == "gegenfolie" and x["satz"] == nr])
        self.assertFalse([x for x in c["hinweise_roh"] if "beibehalten" in x["text"]])
        self.assertEqual([x["satz"] for x in c["stehen_lassen"]], [nr])
        bericht = coach.bericht(c)
        self.assertIn(f"Bewusst stehen lassen: S{nr}", bericht)
        if c["hinweise"]:
            self.assertNotIn("Keine sicheren Einzelstellen", bericht)
        self.assertEqual(len(c["stand"]["stehen_lassen"]), 1)

    def test_in_folgerunden_gar_nicht_mehr(self):
        c1 = self.lauf()
        c2 = self.lauf({"messungen": [c1["stand"]]})
        self.assertFalse(c2["stehen_lassen"])
        self.assertNotIn("Bewusst stehen lassen", coach.bericht(c2))


class Begriffsaufnahme(unittest.TestCase):
    def test_wortpaare(self):
        r = coach.begriffs_relation
        self.assertEqual(r("Kunden", "Konsumenten", set())[0], "synonym")
        self.assertEqual(r("Systemlandschaften", "IT-Landschaft", set())[0], "grundwort")
        self.assertEqual(r("Preissetzung", "Preisgestaltung", set())[0], "bestimmungswort")  # synonyme Grundwörter
        # v5: ein gemeinsames Bestimmungswort zählt nur mit synonymem Grundwort, auch wenn „Daten“ im Text steht
        self.assertIsNone(r("Datenqualität", "Datenbasis", {"daten"}))
        self.assertIsNone(r("Datenqualität", "Datenbasis", set()))
        self.assertIsNone(r("Unternehmen", "Unterstützung", set()))  # Verbpräfix
        self.assertIsNone(r("Beschäftigte", "Beschreibung", set()))
        self.assertIsNone(r("Führung", "Führungskonzepten", set()))  # bloßes Bestimmungswort ≠ Kompositum
        self.assertIsNone(r("Systemlandschaften", "Datenbasis", set()))  # Ursachenkette, kein gemeinsamer Wortteil
        self.assertIsNone(r("Wissenschaft", "Gesellschaft", set()))  # nur Ableitungssuffix

    def lauf(self, verlauf=None, text=BEGRIFFE_TEXT):
        with mit_metriken(anteil_saetze_mit_wortaufnahme=0.2):
            return coach.coache(text, verlauf, 40, roh=True)

    def test_nur_mit_benanntem_paar(self):
        c = self.lauf()
        kb = {x["satz"]: x for x in c["hinweise_roh"] if x["typ"] == "kein_bezug"}
        self.assertEqual(sorted(kb), [2, 6])  # Themenwechsel (Satz 3, 4, 7 …) bleiben ohne Auftrag
        self.assertIn("„Preisgestaltung“ → „Preissetzung“?", kb[2]["text"])
        self.assertIn("„IT-Landschaft“ → „Systemlandschaften“?", kb[6]["text"])
        self.assertIn("Nur wenn dieselbe Sache gemeint ist", kb[2]["text"])
        self.assertEqual(kb[2]["paar"], ["Preisgestaltung", "Preissetzung"])

    def test_nach_einmaliger_nennung_endgueltig_gestrichen(self):
        c1 = self.lauf()
        text = BEGRIFFE_TEXT.replace("Erste Förderprogramme der Länder", "Erste Programme der Länder")  # anderswo überarbeitet
        c2 = self.lauf({"messungen": [c1["stand"]]}, text)
        self.assertFalse([x for x in c2["hinweise_roh"] if x["typ"] == "kein_bezug"])
        c3 = self.lauf({"messungen": [c1["stand"]]})  # nur erneut gemessen: die Stellen sind noch offen
        self.assertTrue([x for x in c3["hinweise_roh"] if x["typ"] == "kein_bezug"])


class FunktionswortStellen(unittest.TestCase):
    def lauf(self):
        L = coach.Lauf(ALS_TEXT, None)
        coach._hebel_priorisieren(L)
        return L

    def test_einordnung_notwendig_umbaubar(self):
        st = self.lauf_stellen = coach.fw_stellen(self.lauf(), ["als"])["als"]
        self.assertEqual(st["anzahl"], 10)
        self.assertEqual(st["notwendig"]["Definition/Einordnung"], [1, 2, 4, 8])
        self.assertEqual(st["notwendig"]["Vergleich/Mengenangabe"], [3, 9])
        self.assertIn(6, st["notwendig"]["Rolle/Funktion"])  # „Als Grundlage nutzen …“ ist keine Zeitangabe
        self.assertEqual(st["umbaubar"]["„dient als“ umbauen"], [7])

    def test_hebeltext_nur_mit_auftrag_auf_konstruktionen_verweisen(self):
        L = self.lauf()
        mit = coach._fw_hebeltext(L, True)
        ohne = coach._fw_hebeltext(L, False)
        self.assertIn("nur über die genannten Konstruktionen", mit)
        self.assertNotIn("genannten Konstruktionen", ohne)
        self.assertIn("„als“: notwendig 8×", ohne)
        self.assertIn("umbaubar 2×", ohne)
        self.assertIn("S7", ohne)

    def test_keine_umbaubare_konstruktion(self):
        text = ALS_TEXT.replace("Der Bericht dient als Grundlage", "Der Bericht ist die Grundlage").replace(
            "Die Beratung gilt als teuer", "Die Beratung kostet viel Geld")
        L = coach.Lauf(text, None)
        coach._hebel_priorisieren(L)
        self.assertIn("Im Text keine umbaubare Konstruktion mehr", coach._fw_hebeltext(L, False))

    def test_stellenloser_hebel_zeigt_stellenliste(self):
        c = coach.coache(ALS_TEXT.replace("Der Bericht dient als Grundlage", "Der Bericht ist die Grundlage"), None, 0)
        fw = next((x for x in c["hebel"] if x["id"] == "funktionswoerter"), None)
        if fw and fw["stellenlos"]:
            self.assertIn("Stellen –", fw["selbsthilfe"])


class Ersatzverben(unittest.TestCase):
    def setUp(self):
        self.L = coach.Lauf(KI_TEXT, None)

    def technik(self, satz_, kid):
        rx = next(k for k in coach.FW_KONSTRUKTIONEN if k[0] == kid)
        t = rx[3].search(satz_)
        return coach.fw_technik(self.L, kid, rx[4], satz_, t)

    def test_vorhandenes_verb_nicht_doppelt(self):
        t, verben, _ = self.technik("Den Kern bildet ein Leitbild, das als Grundlage aller Maßnahmen dient.", "dient_als")
        self.assertEqual(verben, ["ist"])
        self.assertIn("„bildet“ steht schon im Satz", t)
        t, verben, _ = self.technik("Das Leitbild ist neu und dient als Grundlage aller Maßnahmen.", "dient_als")
        self.assertEqual(verben, ["bildet"])
        self.assertIsNone(self.technik("Das Leitbild ist neu, bildet den Kern und dient als Grundlage.", "dient_als"))
        self.assertIsNone(self.technik("Das Verfahren gilt als zuverlässig und wird oft für sicher gehalten.", "gilt_als"))

    def test_folgerung_nicht_streichen(self):
        for doppelpunkt, erwartet in ((0.0, "folgt daraus: …"), (9.0, "Daraus folgt, dass")):
            with mit_metriken(doppelpunkt_pro_1000=doppelpunkt):
                self.L = coach.Lauf(KI_TEXT, None)
            t, verben, behalten = self.technik("Für die Praxis lässt sich dennoch ableiten, dass Schulungen nötig sind.", "ankuendigung")
            self.assertIn("nicht streichen", t)
            self.assertIn(erwartet, t)
            self.assertEqual(verben, ["folgt"])
            self.assertEqual(behalten, ["dennoch"])
            self.assertIn("„dennoch“ bleibt beim Verb", t)
            self.assertNotIn("„daher“ oder „also“ erkennbar", t)

    def test_schliessen_und_folgern_als_ankuendigung(self):
        self.assertTrue(coach.ANKUENDIGUNG_RE.search("Daraus lässt sich schließen, dass die Kosten steigen."))
        self.assertTrue(coach.ANKUENDIGUNG_RE.search("Daraus kann gefolgert werden, dass die Kosten steigen."))
        t, _, _ = self.technik("Daraus lässt sich schließen, dass die Kosten steigen.", "ankuendigung")
        self.assertIn("trägt eine Folgerung", t)


class Absaetze(unittest.TestCase):
    def test_komposita_teilen_begriffe(self):
        self.assertTrue(coach._teilt_begriff("nachfrage", "nachfrageschwankungen"))
        self.assertTrue(coach._teilt_begriff("nachfrageschwankungen", "nachfragestarken"))
        self.assertTrue(coach._teilt_begriff("datenqualität", "servicequalität"))
        self.assertFalse(coach._teilt_begriff("unternehmen", "unterstützung"))
        self.assertFalse(coach._teilt_begriff("wissenschaft", "gesellschaft"))

    def test_kein_ein_satz_kopf_vor_ueberleitung(self):
        abs_ = ("Drittens hat die Studie auch eine Veränderung der Instrumente gezeigt. "
                "Klassische Berichte werden durch Prognosen ergänzt, mit denen sich Entwicklungen früher erkennen lassen. "
                "Damit wandelt sich die Rolle der Abteilung vom Berichtersteller zum Berater der Leitung. "
                "Diese Rolle verlangt neue Kenntnisse in Statistik und Kommunikation.")
        text = gleichmaessig(3, 5) + "\n\n" + abs_ + "\n\n" + gleichmaessig(3, 5, 40)
        c = coach.coache(text, None, 40, roh=True)
        zweiter = next(s["nr"] for s in analyse.analysiere_text(text)["saetze"] if s["text"].startswith("Klassische Berichte"))
        for x in c["hinweise_roh"]:
            if x["typ"] == "absatz_teilen":
                self.assertNotIn(f"vor Satz {zweiter} ", x["text"])


class Floskeln(unittest.TestCase):
    def test_ersatz_ohne_steigerung(self):
        t = coach.floskel_ersatz({"id": "schluessel", "ersatz": "… („gilt als wichtigstes …“, „ist laut … unverzichtbar für …“)"})
        self.assertIn("wichtige Funktion für", t)
        self.assertNotIn("gilt als wichtigstes", t)
        self.assertIn("Stärke beibehalten, nicht steigern (kein „unverzichtbar“, „wichtigstes“)", t)
        self.assertIn("Stärke beibehalten", coach.floskel_ersatz({"id": "von_bedeutung", "ersatz": "„ist wichtig für …“."}))
        self.assertEqual(coach.floskel_ersatz({"id": "x", "ersatz": "Anders sagen."}), "Anders sagen.")

    def test_neutrale_beispiele_sind_selbst_keine_floskel(self):
        muster = analyse.lade_muster()
        for bsp in ("Die Marke hat eine wichtige Funktion für die Gewinnung von Personal.",
                    "Die Marke ist wichtig für die Gewinnung von Personal."):
            self.assertFalse([t for t in analyse.muster_treffer(bsp, muster) if t[2] > 0], bsp)


class Abkuerzungen(unittest.TestCase):
    def test_nur_gaengige(self):
        kurz = {k for _, k, _ in coach.ABK_ERSATZ}
        self.assertEqual(kurz, {"z. B.", "d. h.", "u. a.", "bzw.", "ca.", "vgl."})

    def test_diagnose_ehrlich_bei_median_grenze(self):
        from test_coach_wirksamkeit import ABK_TEXT, ABK_ANHANG
        c = coach.coache(ABK_TEXT + "\n" + ABK_ANHANG, None, 40)  # ~580 Wörter: schon eine Abkürzung läge über dem Median
        self.assertFalse([x for x in c["hinweise"] if x["typ"] == "abkuerzung"])
        bericht = coach.bericht(c)
        self.assertNotIn("übliche Abkürzungen (z. B., d. h., bzw.) verwenden", bericht)
        self.assertIn("läge über dem menschlichen Median", bericht)


class GenderErsetzbar(unittest.TestCase):
    TEXT = ("Die Bewerbenden achten heute stark auf flexible Arbeitszeiten im Betrieb. Viele Bewerbende vergleichen dafür "
            "mehrere Angebote im Netz. Die Firma reagiert mit klaren Regeln für die Bewerbenden und einer schnellen Rückmeldung.")

    def test_formen_und_maskulinform_ersetzbar(self):
        c = coach.coache(self.TEXT + "\n\n" + gleichmaessig(3, 5), None, 40)
        g = next(x for x in c["vorgaben"] if x["typ"] == "gender")  # v7: Vorgaben stehen in einem eigenen Abschnitt
        self.assertIn("bewerbende", g["ersetzbar"])
        self.assertIn("bewerber", g["ersetzbar"])
        self.assertIn("bewerbende", c["stand"]["ersetzbar"])
        neu = self.TEXT.replace("Bewerbenden", "Bewerber").replace("Bewerbende", "Bewerber")
        res = inhalt_check.pruefe(self.TEXT, neu, c["stand"]["ersetzbar"])
        self.assertFalse([w for w in res["warnungen"] if w["typ"] == "Begriff verschwunden" and "bewerbend" in w["wert"]])


class Konsistenz(unittest.TestCase):
    TEXT = ("Die Firma beschäftigt ca. 500 Personen an drei Standorten in der Region. Die Zentrale plant neue Büros für das Team. "
            "Im Ausland arbeiten etwa 120 weitere Personen für den Vertrieb.\n\n" + gleichmaessig(4, 5))

    def test_mischform_nach_ersetzung(self):
        c = coach.coache(self.TEXT, {"messungen": [leerer_stand(ersetzbar=["etwa"])]}, 40, roh=True)
        k = [x for x in c["hinweise_roh"] if x["typ"] == "konsistenz"]
        self.assertEqual(len(k), 1)
        self.assertIn("„ca.“ (S1) neben „etwa“ (S3)", k[0]["text"])
        self.assertIn("einheitlich", k[0]["text"])

    def test_ohne_ersetzungsauftrag_kein_hinweis(self):
        c = coach.coache(self.TEXT, {"messungen": [leerer_stand(ersetzbar=["maßgeblich"])]}, 40, roh=True)
        self.assertFalse([x for x in c["hinweise_roh"] if x["typ"] == "konsistenz"])
        c = coach.coache(self.TEXT, None, 40, roh=True)
        self.assertFalse([x for x in c["hinweise_roh"] if x["typ"] == "konsistenz"])


class KombinierteAuftraege(unittest.TestCase):
    def test_streichen_gegen_behalten(self):
        aus = coach.ein_auftrag_je_satz([h("fw_ankuendigung", 4, behalten=["dennoch"], verben=["folgt"]),
                                         h("konnektor", 4, streicht=["dennoch"]), h("abkuerzung", 4)])
        self.assertEqual(len(aus), 1)
        self.assertEqual(aus[0]["typen"], ["fw_ankuendigung", "abkuerzung"])
        self.assertTrue(aus[0]["aufgeloest"])

    def test_doppeltes_verb(self):
        a = h("fw_ergibt", 3, verben=["folgt", "entsteht"])
        b = h("fw_als", 3, text="Satz 3 („Anfang …“): „dient als“ → „ist“ oder „bildet“ (Beispiel …).", verben=["ist", "bildet"])
        c_ = h("floskel", 3, verben=["ist"])
        aus = coach.ein_auftrag_je_satz([c_, b])
        self.assertIn("→ „bildet“ („ist“ schlägt schon ein anderer Teil vor)", aus[0]["text"])
        aus = coach.ein_auftrag_je_satz([a, h("fw_dass", 3, verben=["folgt"])])
        self.assertEqual(aus[0]["typ"], "fw_ergibt")
        self.assertNotIn("typen", aus[0])  # der zweite Teil entfällt

    def test_daher_also_gegen_dennoch(self):
        a = h("fw_ankuendigung", 5, text="Satz 5 („Anfang …“): Ankündigung streichen; die Folgerung bleibt mit „daher“ oder „also“ "
              "erkennbar.")
        aus = coach.ein_auftrag_je_satz([a, h("abkuerzung", 5)], {5: "Daraus lässt sich dennoch festhalten, dass X gilt."})
        self.assertNotIn("„daher“ oder „also“", aus[0]["text"])
        self.assertIn("über das Verb", aus[0]["text"])
        # „nicht „daher“ oder „also““ ist schon die Auflösung und bleibt stehen
        b = h("fw_ankuendigung", 6, text="Satz 6 („Anfang …“): … „dennoch“ bleibt beim Verb, nicht „daher“ oder „also“.")
        aus = coach.ein_auftrag_je_satz([b, h("abkuerzung", 6)], {6: "Es lässt sich dennoch ableiten, dass X gilt."})
        self.assertIn("nicht „daher“ oder „also“", aus[0]["text"])

    def test_keine_widersprueche_im_lauf(self):
        text = KI_TEXT.replace("Insgesamt zeigt sich, dass die Arbeitgebermarke",
                               "Daraus lässt sich dennoch ableiten, dass die Arbeitgebermarke")
        c = coach.coache(text, None, 40)
        for x in c["hinweise"]:
            if "dennoch" in x["text"]:
                self.assertNotRegex(x["text"], r"„dennoch“[^.]*streichen")


class WaechterUndHebel(unittest.TestCase):
    def test_keine_ausgesetzten_typen_im_bericht(self):
        for text in (KI_TEXT, gleichmaessig(8, 5)):
            c = coach.coache(text, None, 40, roh=True)
            aus = set(c["ausgesetzt"])
            for x in c["hinweise"]:
                self.assertFalse(set(x.get("typen") or [x["typ"]]) & aus, x["text"])

    def test_alternative_nennt_keine_ausgesetzte_technik(self):
        L = SimpleNamespace(ausgesetzt={"buendeln", "teilen"}, hinweise=[])
        self.assertEqual(coach.alternative_text(L, "satzlaenge"), "Erlaubt bleibt: Satzlängen diese Runde so lassen.")
        L = SimpleNamespace(ausgesetzt={"buendeln"}, hinweise=[{"typ": "teilen"}])
        self.assertIn("nur dort teilen", coach.alternative_text(L, "satzlaenge"))
        self.assertNotIn("herauslösen", coach.ALTERNATIVE["nebensaetze"])

    def test_keine_nominalisierung_in_nominalkette_bei_hebel_wortwahl(self):
        satz_ = "Die Kenntnis der Grenzen des Instruments ist wichtig, weil die Daten fehlen."
        L = coach.Lauf(satz_ + "\n\n" + gleichmaessig(3, 5), None)
        s = L.saetze[0]
        self.assertGreaterEqual(max(analyse.nominalketten([s["text"]])), 3)
        L.hebel.pop("wortwahl", None)
        self.assertIsNotNone(coach.nebensatz_auftrag(L, s, L.masken[s["nr"]]))
        L.hebel["wortwahl"] = {"prioritaet": 1.0, "kennzahlen": []}
        L.kette_max.clear()
        self.assertIsNone(coach.nebensatz_auftrag(L, s, L.masken[s["nr"]]))
        self.assertTrue(coach.nominal_gesperrt(L, s))


if __name__ == "__main__":
    unittest.main()
