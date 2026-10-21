"""Tests für Coach v3 (Präzision): ein Auftrag je Satz, Nebensatz → Nominalgruppe, Anknüpfung, Begriffsaufnahme,
Synonym-Cluster, Gender-Vorgabe, Satzklammer, Bündeln, Gegenfolie, Konnektoren, Bindestrich und datengetreue Hebeltexte.

Alle Texte sind synthetisch (keine Korpustexte).

python3 -m unittest discover -s tests
"""
import os
import re
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
from test_coach import KI_TEXT  # noqa: E402
from test_coach_wirksamkeit import gleichmaessig, mit_metriken  # noqa: E402

TS = analyse.lade_baselines()["textsorten"]["hochschule"]
REF = TS["metriken"]


def saetze_von(text):
    return analyse.analysiere_text(text)["saetze"]


def nr_von(text, anfang):
    return next(s["nr"] for s in saetze_von(text) if s["text"].startswith(anfang))


def h(typ, satz, text=None, **extra):
    """Kleiner Hinweis-Datensatz für die Zusammenfassung (wie Lauf.hinweis ihn anlegt)."""
    stelle = f"Satz {satz} („Anfang …“)"
    return {"typ": typ, "hebel": coach.TYP_HEBEL.get(typ, typ), "satz": satz, "absatz": 1, "stelle": stelle,
            "text": text or f"{stelle}: Auftrag {typ}.", "gewicht": 1.0, "ersetzbar": [], "weitere_nr": [], **extra}


class EinAuftragJeSatz(unittest.TestCase):
    def test_zusammenfassen_in_fester_reihenfolge(self):
        aus = coach.ein_auftrag_je_satz([h("abkuerzung", 3), h("fw_als", 3), h("gender", 3), h("konnektor", 5)])
        am3 = [x for x in aus if x["satz"] == 3 and x["typ"] != "gender"]
        self.assertEqual(len(am3), 1)
        self.assertEqual(am3[0]["typen"], ["fw_als", "abkuerzung"])  # Wendung vor Abkürzung
        self.assertIn("Im selben Durchgang: Auftrag abkuerzung.", am3[0]["text"])
        self.assertTrue(am3[0]["text"].startswith("Satz 3 („Anfang …“): Auftrag fw_als."))
        self.assertEqual(len([x for x in aus if x["typ"] == "gender"]), 1)  # Vorgaben bleiben eigene Hinweise
        self.assertEqual(len([x for x in aus if x["satz"] == 5]), 1)

    def test_mehrsatzauftrag_nimmt_folgesatz_auf(self):
        aus = coach.ein_auftrag_je_satz([h("buendeln", 7, weitere_nr=[8]), h("abkuerzung", 8)])
        self.assertEqual(len(aus), 1)
        self.assertIn("Im selben Durchgang in Satz 8:", aus[0]["text"])

    def test_strohmann_sperrt_beide_saetze(self):
        aus = coach.ein_auftrag_je_satz([h("strohmann", 4, weitere_nr=[5], sperrt=[4, 5]), h("nebensatz", 4), h("anknuepfung", 5),
                                         h("gedankenstrich", 5), h("abkuerzung", 6)])
        self.assertEqual(sorted(x["typ"] for x in aus), ["abkuerzung", "gedankenstrich", "strohmann"])

    def test_gedaechtnis_nur_wenn_alle_teile_genannt(self):
        a = dict(h("fw_als", 3), schon_genannt=1, kern="Satz 3 („Anfang …“): Auftrag fw_als.")
        a["text"] = a["kern"] + coach.GENANNT.format(runde=1)
        aus = coach.ein_auftrag_je_satz([a, h("abkuerzung", 3)])
        self.assertNotIn("schon in Runde", aus[0]["text"])
        self.assertNotIn("schon_genannt", aus[0])

    def test_ankuendigung_mit_ableiten_ein_auftrag(self):
        text = KI_TEXT.replace("Insgesamt zeigt sich, dass die Arbeitgebermarke",
                               "Daraus lässt sich ableiten, dass die Arbeitgebermarke")
        c = coach.coache(text, None, 40, roh=True)
        nr = nr_von(text, "Daraus lässt sich ableiten")
        am = [x for x in c["hinweise_roh"] if x["satz"] == nr and x["typ"] in ("nebensatz", "fw_lassen", "fw_ankuendigung")]
        self.assertEqual([x["typ"] for x in am], ["fw_ankuendigung"])
        self.assertIn("nicht streichen", am[0]["text"])  # die Folgerung bleibt eine Folgerung
        self.assertIn("folgt", am[0]["text"])
        self.assertNotIn("„daher“ oder „also“", am[0]["text"])
        self.assertNotIn("kann … werden", am[0]["text"])

    def test_funktionswort_weicht_dem_muster(self):
        c = coach.coache(KI_TEXT, None, 40, roh=True)
        nr = nr_von(KI_TEXT, "Insgesamt zeigt sich")
        typen = {x["typ"] for x in c["hinweise_roh"] if x["satz"] == nr}
        self.assertIn("floskel", typen)
        self.assertNotIn("fw_zeigt", typen)

    def test_strohmann_paar_im_lauf(self):
        text = KI_TEXT.replace("Gleichzeitig zeigt sich, dass bereits kleine Maßnahmen eine messbare Wirkung entfalten können.",
                               "Auf den ersten Blick könnte man daraus schließen, dass kleine Betriebe keine Marke brauchen. "
                               "Diese Einschätzung greift jedoch zu kurz.")
        c = coach.coache(text, None, 40)
        a, b = nr_von(text, "Auf den ersten Blick"), nr_von(text, "Diese Einschätzung greift")
        st = [x for x in c["hinweise"] if x["typ"] == "strohmann"]
        self.assertEqual(len(st), 1)
        self.assertIn(f"Satz {a} bis {b}", st[0]["text"])
        self.assertIn("Gegenposition samt Abweisung", st[0]["text"])
        andere = [x for x in c["hinweise"] if x["satz"] in (a, b) and x["typ"] not in coach.EINZEL_AUSGENOMMEN | {"strohmann"}]
        self.assertFalse(andere)

    def test_hoechstens_ein_auftrag_je_satz_in_der_ausgabe(self):
        for text in (KI_TEXT, gleichmaessig(8, 5)):
            c = coach.coache(text, None, 40)
            nrn = [x["satz"] for x in c["hinweise"] if x["satz"] and x["typ"] not in coach.EINZEL_AUSGENOMMEN]
            self.assertEqual(len(nrn), len(set(nrn)))

    def test_kombinierter_auftrag_wird_nicht_einem_typ_zugeschrieben(self):
        text = gleichmaessig(8, 5)
        S = saetze_von(text)
        s3 = next(s for s in S if s["absatz"] == 3)
        cv = analyse.analysiere_text(text)["metriken"]["saetze_pro_absatz_cv"]
        verlauf = {"messungen": [{"score": 40, "p_mensch": 0.05, "kennzahlen": {}, "roh": {},
                                  "hinweise": [{"typ": "absatz_teilen", "typen": ["absatz_teilen", "abkuerzung"],
                                                "anfang": coach.schluessel_anfang(s3["text"]), "satz": s3["nr"],
                                                "ziel": "saetze_pro_absatz_cv", "ziel_wert": cv}]}]}
        c = coach.coache(text, verlauf, 40)
        self.assertFalse(c["fortschritt"]["wirkung"])


class NebensatzNominal(unittest.TestCase):
    def test_relativsatz_regeln(self):
        ok = coach.relativsatz_umbaubar
        self.assertEqual(ok("Die Studie nutzt die Daten", "die erhoben wurden"), (True, True))
        self.assertEqual(ok("Die Kosten", "die steigen")[0], True)
        self.assertEqual(ok("Die Umsätze der großen Unternehmen", "die stark gewachsen sind")[0], True)
        self.assertFalse(ok("Der Begriff wurde von Ambler und Barrow (1996)", "die als Erste die Prinzipien übertragen haben")[0])
        self.assertFalse(ok("Der Begriff wurde von Ambler und Barrow", "die ihn prägten")[0])  # Eigenname ohne Begleiter
        self.assertFalse(ok("Berichtspflichtig waren große Unternehmen", "die kaum vergleichbar waren")[0])  # Adjektiv + sein
        self.assertFalse(ok("Die Firmen", "die investiert haben")[0])  # haben-Perfekt
        self.assertFalse(ok("Die Mitarbeiter", "die befragt wurden")[0])  # Personenwort
        self.assertFalse(ok("Die Daten", "die wir erheben")[0])  # Pronomen ist nicht Subjekt
        self.assertFalse(ok("Die Daten", "die in der zweiten Welle der Befragung erhoben wurden")[0])  # > 6 Wörter
        self.assertFalse(ok("Die Daten", "die erhoben werden können")[0])  # Modalverb
        self.assertIsNone(coach.NEBENSATZ_TYPEN[2][1].search("die Informationen, deren Qualität schwankt"))

    def lauf(self, text):
        L = coach.Lauf(text, None)
        coach._hebel_priorisieren(L)
        return L

    def auftrag(self, satz_text):
        L = self.lauf(satz_text + "\n\n" + KI_TEXT)
        s = L.saetze[0]
        self.assertEqual(s["text"], satz_text)
        return coach.nebensatz_auftrag(L, s, L.masken[s["nr"]])

    def test_dass_satz_kurz_ohne_modalverb_und_nicht_wiedergegeben(self):
        a = self.auftrag("Die Daten der Befragung zeigen, dass die Kosten im zweiten Jahr steigen.")
        self.assertIsNotNone(a)
        self.assertIn("Aussagestatus erhalten", a[1])
        self.assertIsNone(self.auftrag("Die Daten zeigen, dass die Kosten im zweiten Jahr der Einführung in allen untersuchten "
                                       "Betrieben deutlich steigen."))  # > 12 Wörter
        self.assertIsNone(self.auftrag("Die Daten zeigen, dass die Kosten im zweiten Jahr steigen können."))  # Modalverb
        self.assertIsNone(self.auftrag("Müller und Schmidt betonen, dass die Kosten im zweiten Jahr steigen."))  # wiedergegebene Rede
        self.assertIsNone(self.auftrag("Erik betont dreimal, dass er so etwas nie machen würde."))
        self.assertIsNone(self.auftrag("Die Daten zeigen, dass die Kosten, die Löhne und die Mieten steigen."))  # Komma: Kette

    def test_handelnde_behalten_und_begruendung(self):
        a = self.auftrag("Die Teams arbeiten schneller, weil die Führung mehr Spielraum gewährt.")
        self.assertIsNotNone(a)
        self.assertIn("Handelnde behalten", a[1])
        self.assertIn("Begründung bleibt eine Begründung", a[1])
        a = self.auftrag("Die Teams arbeiten schneller, weil Daten früher vorliegen.")
        self.assertNotIn("Handelnde behalten", a[1])

    def test_keine_folge_und_bezugssaetze(self):
        for satz_ in ("Die Preise steigen stark, sodass viele Kunden zu anderen Anbietern wechseln.",
                      "Die Preise steigen stark, wodurch viele Kunden zu anderen Anbietern wechseln.",
                      "Die Preise steigen stark, wobei vor allem kleine Händler betroffen sind."):
            self.assertIsNone(self.auftrag(satz_), satz_)

    def test_passiv_relativsatz_bei_wenig_passiv(self):
        text = "Die Studie nutzt die Daten, die erhoben wurden.\n\n" + KI_TEXT
        L = self.lauf(text)
        L.setze_aus({"nebensatz_relativ"}, "Test: wenig Passiv")
        s = L.saetze[0]
        self.assertIsNone(coach.nebensatz_auftrag(L, s, L.masken[s["nr"]]))
        self.assertEqual(L.unterdrueckt["nebensatz_relativ"], 1)
        text = "Die Händler senken die Preise, die steigen.\n\n" + KI_TEXT  # aktives Präsens: kein Passiv betroffen
        L = self.lauf(text)
        L.setze_aus({"nebensatz_relativ"}, "Test: wenig Passiv")
        s = L.saetze[0]
        self.assertIsNotNone(coach.nebensatz_auftrag(L, s, L.masken[s["nr"]]))


class Anknuepfung(unittest.TestCase):
    def test_koordinierte_namen_und_diese_richtung(self):
        k = coach.bezugskandidaten("Eine besonders einflussreiche Differenzierung stammt von Lievens und Highhouse.")
        self.assertIn("Lievens und Highhouse", [x["text"] for x in k])
        self.assertTrue(next(x for x in k if x["text"] == "Lievens und Highhouse")["person"])
        k = coach.bezugskandidaten("Ein erster Schritt in diese Richtung war die Non-Financial Reporting Directive.")
        self.assertNotIn("Richtung", [x["text"] for x in k])
        self.assertTrue(next(x for x in k if x["text"] == "Non-Financial Reporting Directive")["feminin"])
        self.assertEqual(coach.bezugsausdruecke("Die Theorie von Herzberg, Mausner und Snyderman wirkt.")[1],
                         "Herzberg, Mausner und Snyderman")

    def vorschlag(self, a_text, b_text, art, wort):
        text = a_text + " " + b_text + "\n\n" + KI_TEXT
        L = coach.Lauf(text, None)
        return coach.bezug_vorschlag(L, L.saetze[0], L.saetze[1], art, wort)

    def test_einziger_personenkandidat_kein_hinweis(self):
        self.assertEqual(self.vorschlag("Eine besonders einflussreiche Differenzierung stammt von Lievens und Highhouse.",
                                        "Sie unterscheiden zwischen zwei Arten von Merkmalen.", "pron", "Sie"), (False, []))
        self.assertEqual(self.vorschlag("Gleichzeitig steigen die Anforderungen an die Controller selbst.",
                                        "Sie müssen heute auch Daten auswerten.", "pron", "Sie"), (False, []))

    def test_genus_und_numerus(self):
        ok, k = self.vorschlag("Ein erster Schritt in diese Richtung war die Non-Financial Reporting Directive.",
                               "Ihr Anwendungsbereich war allerdings eng begrenzt.", "poss", "Ihr")
        self.assertTrue(ok)
        self.assertEqual(k, ["Non-Financial Reporting Directive"])
        ok, k = self.vorschlag("Hier setzt die vorliegende Arbeit an.", "Ihr Ziel ist eine Analyse der Pflichten.", "poss", "Ihr")
        self.assertEqual(k, ["Arbeit"])  # Genus unbekannt, aber einziger Kandidat
        ok, k = self.vorschlag("Die Planung und die Steuerung brauchen klare Ziele für das Team.", "Sein Erfolg hängt davon ab.",
                               "poss", "Sein")
        self.assertNotIn("Planung", k)
        self.assertNotIn("Steuerung", k)

    def test_ohne_raten_bei_vielen_kandidaten(self):
        self.assertIn("ausdrücklich nennen", coach._bezug_text(["A", "B", "C"], {"nr": 4}))
        self.assertIn("vermutlich „A“ aus Satz 4", coach._bezug_text(["A"], {"nr": 4}))
        c = coach.coache(KI_TEXT, None, 40, roh=True)
        for x in c["hinweise_roh"]:
            if x["typ"] == "anknuepfung":
                self.assertLessEqual(x["text"].count("“ oder „"), 1, x["text"])


class Begriffsaufnahme(unittest.TestCase):
    def test_verbunden_erweitert(self):
        b = coach.satz_begriffe
        self.assertEqual(coach.verbunden(b("Teams stärken das Autonomieerleben."), b("Feedback fördert das Kompetenzerleben.")),
                         "kompositum")  # gemeinsames Grundwort
        self.assertEqual(coach.verbunden(b("Die Zwei-Faktoren-Theorie wirkt."), b("Schlechte Hygienefaktoren bleiben.")), "kompositum")
        self.assertEqual(coach.verbunden(b("Die Studienlage ist dünn."), b("Ein Großteil der Untersuchungen ist alt.")), "synonym")
        self.assertIsNone(coach.verbunden(b("Die Wissenschaft wächst."), b("Die Gesellschaft altert.")))  # nur Ableitungssuffix
        saetze = [{"nr": 1, "text": "Unter dynamischer Preissetzung (Dynamic Pricing) versteht man flexible Preise."}]
        aliase = coach.gleichsetzungen(saetze)
        self.assertTrue(aliase)
        self.assertEqual(coach.verbunden(b("Die Preissetzung folgt der Nachfrage.", aliase), b("Dynamic Pricing hilft Händlern.", aliase)),
                         "gleichsetzung")
        self.assertFalse(coach.gleichsetzungen([{"nr": 1, "text": "Die Studie (Müller 2020) zeigt das."}]))

    def lauf_kein_bezug(self, text):
        with mit_metriken(anteil_saetze_mit_wortaufnahme=0.2):
            return coach.coache(text, None, 40, roh=True)

    def test_kein_hinweis_bei_rueckverweis_aufzaehlung_und_fachbegriff(self):
        a = ("Agile Arbeitsformen setzen an allen drei Punkten der Motivation an. Selbstorganisierte Teams erweitern den Spielraum "
             "der Beschäftigten im Alltag deutlich. Kurze Iterationen machen Fortschritte sichtbar und fördern das Erleben von "
             "Kompetenz. Die Planung der Budgets kann dies im ganzen Unternehmen stark verändern.")
        b = ("Unter dynamischer Preissetzung (Dynamic Pricing) versteht man flexible Preise im Handel. Viele Händler im Netz "
             "beobachten ihre Konkurrenz rund um die Uhr sehr genau. Dynamic Pricing ermöglicht schnelle Reaktionen auf jede "
             "Veränderung am Markt.")
        text = a + "\n\n" + b + "\n\n" + gleichmaessig(4, 5)
        c = self.lauf_kein_bezug(text)
        S = saetze_von(text)
        verboten = {nr_von(text, x) for x in ("Selbstorganisierte Teams", "Kurze Iterationen", "Die Planung der Budgets",
                                               "Dynamic Pricing ermöglicht")}
        for x in c["hinweise_roh"]:
            if x["typ"] == "kein_bezug":
                self.assertNotIn(x["satz"], verboten, x["text"])
        self.assertTrue(S)


class Synonyme(unittest.TestCase):
    TEXT = ("Die Kunden vergleichen Preise im Netz. Viele Kunden kaufen heute online ein. Die Kunden reagieren schnell auf Rabatte. "
            "Seit der Richtlinie (EU) 2019/2161 müssen Händler Verbraucher über personalisierte Preise informieren. "
            "Die Kunden achten zudem auf Bewertungen. Die Kunden wechseln oft den Anbieter.")

    def cluster_hinweise(self, text, verlauf=None):
        with mit_metriken(mattr_100=0.9):
            c = coach.coache(text + "\n\n" + gleichmaessig(3, 5), verlauf, 40, roh=True)
        return c, [x for x in c["hinweise_roh"] if x["typ"] == "synonyme"]

    def test_rechtsbegriff_einmal_wird_geschuetzt(self):
        _, syn = self.cluster_hinweise(self.TEXT)
        self.assertFalse([x for x in syn if "Verbraucher" in x["text"]])
        text = self.TEXT.replace("Seit der Richtlinie (EU) 2019/2161 müssen Händler Verbraucher über personalisierte Preise informieren.",
                                 "Viele Verbraucher vergleichen Preise.")
        _, syn = self.cluster_hinweise(text)
        self.assertTrue([x for x in syn if "Verbraucher" in x["text"]])
        self.assertTrue(syn[0]["anfang"].startswith("syn:"))
        self.assertEqual(syn[0]["zaehlung"], {"kunden": 5, "verbraucher": 1})

    def test_unveraenderte_zaehlung_nicht_wiederholen(self):
        text = self.TEXT.replace("Seit der Richtlinie (EU) 2019/2161 müssen Händler Verbraucher über personalisierte Preise informieren.",
                                 "Viele Verbraucher vergleichen Preise.")
        c1, syn = self.cluster_hinweise(text)
        self.assertTrue(syn)
        stand = c1["stand"]
        self.assertTrue([x for x in stand["hinweise"] if x["typ"] == "synonyme" and x.get("zaehlung")])
        # an anderer Stelle überarbeitet, die Wörter aber stehen gelassen (ein bloß erneut gemessener Text wiederholt den
        # Hinweis, siehe test_coach_integration)
        _, syn2 = self.cluster_hinweise(text.replace("achten zudem auf", "achten zudem oft auf"), {"messungen": [stand]})
        self.assertFalse(syn2)  # Wahl offenbar bewusst
        _, syn3 = self.cluster_hinweise(text.replace("Die Kunden wechseln", "Die Verbraucher wechseln"), {"messungen": [stand]})
        self.assertTrue(syn3)  # Zählung verändert: wieder melden


class Gender(unittest.TestCase):
    def funde(self, text):
        return [(f["wort"], f["maskulin"]) for f in coach.gender_funde(text)]

    def test_partizipien_und_ausnahmen(self):
        self.assertEqual(self.funde("Die Bewerbenden und Mitarbeitende reden."), [("Bewerbenden", "Bewerber"), ("Mitarbeitende", "Mitarbeiter")])
        self.assertEqual(self.funde("Studierende und Peer-Forschende"), [("Studierende", "Studenten"), ("Peer-Forschende", "Peer-Forscher")])
        self.assertEqual(self.funde("Lesende fragen."), [("Lesende", "Leser")])
        for kein in ("Im Folgenden geht es um Preise.", "Am Wochenende kamen viele.", "Alleinerziehende brauchen Hilfe.",
                     "Die Vorsitzende sprach.", "Die Eizellspende ist umstritten.", "Steigende Preise ärgern alle.",
                     "Das Entscheidende ist klar.", "Die Legende lebt.", "Tausende kamen.", "Ein Reisender fragte."):
            self.assertEqual(self.funde(kein), [], kein)
        self.assertEqual(self.funde("Die Diskutierenden stritten."), [("Diskutierenden", None)])  # keine sichere Ableitung

    def test_genderzeichen_und_doppelnennung(self):
        self.assertEqual(self.funde("Die Interviewpartner_innen, Kund*innen, MitarbeiterInnen und Lehrer:innen."),
                         [("Interviewpartner_innen", "Interviewpartner"), ("Kund*innen", "Kunden"), ("MitarbeiterInnen", "Mitarbeiter"),
                          ("Lehrer:innen", "Lehrer")])
        self.assertEqual(self.funde("Kundinnen und Kunden sowie Bürger und Bürgerinnen."),
                         [("Kundinnen und Kunden", "Kunden"), ("Bürger und Bürgerinnen", "Bürger")])
        self.assertEqual(self.funde("Lehrerinnen und Schüler"), [])  # zwei Gruppen
        self.assertEqual(coach.gender_schluessel("Nutzern"), coach.gender_schluessel("Nutzer"))

    def test_ein_hinweis_je_stamm_mit_mischform(self):
        text = ("Die Bewerbenden achten auf das Image der Firma. Viele Bewerber lesen Bewertungen im Netz. "
                "Für Bewerbende zählt auch das Gehalt. Die Firma wirbt um Bewerbende in der Region.\n\n" + KI_TEXT)
        c = coach.coache(text, None, 40, roh=True)
        g = [x for x in c["hinweise_roh"] if x["typ"] == "gender" and "Bewerb" in x["text"]]
        self.assertEqual(len(g), 1)
        self.assertRegex(g[0]["text"], r"in Satz 1, 3 und 4 → „Bewerber“")
        self.assertIn("im ganzen Text einheitlich", g[0]["text"])
        self.assertIn("Maskulinform steht schon in Satz 2", g[0]["text"])
        self.assertEqual(g[0]["anfang"], "gender:bewerber")
        self.assertIsNone(g[0]["satz"])


class SatzklammerUndStriche(unittest.TestCase):
    def test_klammer_nur_umstellbare_nebensaetze(self):
        for w in ("während", "obwohl", "sodass", "wodurch", "womit"):
            self.assertIsNone(coach.KLAMMER_QUELLE_RE.search(f"Die Preise können erhöht werden, {w} die Kosten sinken."), w)
        for w in ("um", "indem", "ohne", "weil", "da", "wenn", "nachdem", "bevor", "sobald"):
            self.assertTrue(coach.KLAMMER_QUELLE_RE.search(f"Die Preise können erhöht werden, {w} die Kosten sinken."), w)

    def test_bindestrich_mit_leerzeichen(self):
        text = ("Ein konkretes und symbolisch - pragmatisches Sportbild prägt die Werbung der Vereine im ganzen Land. "
                "Das ist wichtig - aber teuer für die kleinen Vereine im Land.\n\n" + KI_TEXT)
        c = coach.coache(text, None, 60, roh=True)
        S = saetze_von(text)
        b = [x for x in c["hinweise_roh"] if x["typ"] == "bindestrich"]
        self.assertEqual([x["satz"] for x in b], [S[0]["nr"]])
        self.assertIn("„symbolisch-pragmatisches“", b[0]["text"])
        self.assertNotIn("Komma, Klammer", b[0]["text"])
        g = [x["satz"] for x in c["hinweise_roh"] if x["typ"] == "gedankenstrich"]
        self.assertIn(S[1]["nr"], g)
        self.assertNotIn(S[0]["nr"], g)


class Buendeln(unittest.TestCase):
    def lauf(self, text):
        L = coach.Lauf(text, None)
        coach._hebel_priorisieren(L)
        return L

    def paar(self, a, b):
        L = self.lauf(a + " " + b + "\n\n" + KI_TEXT)
        return coach.buendel_paar_ok(L, L.saetze[0], L.saetze[1])

    # 22 Wörter; die Folgesätze haben 15–16 Wörter (zusammen 37–38, im Bündel-Bereich 30–46)
    A = ("Die neue Richtlinie verlangt von allen großen Unternehmen in der Europäischen Union ab dem nächsten Jahr einen jährlichen "
         "Bericht über ihre Ziele.")

    def test_gemeinsames_nomen_oder_anapher(self):
        self.assertTrue(self.paar(self.A, "Der Bericht enthält auch Angaben zu Lieferketten, Energie und Personal im ganzen Betrieb und im Ausland."))
        self.assertFalse(self.paar(self.A, "Dabei müssen sie Angaben zu Lieferketten, Energie und Personal im ganzen Betrieb und im Ausland liefern."))  # Modalverb
        self.assertFalse(self.paar(self.A, "Große Spielräume bei Inhalt und Form erschweren Vergleiche zwischen Firmen und Branchen erheblich und dauerhaft."))

    def test_eigener_aussagestatus_bleibt(self):
        for b in ("Es liegt nahe, dass der Bericht vor allem großen Firmen und ihren Banken bei Krediten hilft.",
                  "Hinzu kommt, dass der Bericht vor allem großen Firmen und ihren Banken bei Krediten hilft.",
                  "Der Bericht hilft vermutlich vor allem großen Firmen und ihren Banken bei Krediten und Ratings.",
                  "Der Bericht ist nicht nur eine Last, sondern eine Hilfe für Firmen und Banken bei Krediten."):
            self.assertFalse(self.paar(self.A, b), b)

    def test_obergrenze_und_auftragstext(self):
        lang = ("Der Bericht enthält dazu Angaben zu Lieferketten, Energie, Wasser, Abfall, Personal, Vielfalt, Weiterbildung, Gesundheit "
                "und Sicherheit in allen Tochterfirmen und Werken im In- und Ausland samt ihren Lieferanten.")
        self.assertGreater(len(self.A.split()) + len(lang.split()), coach.BUENDEL_MAX)
        self.assertFalse(self.paar(self.A, lang))
        c = coach.coache(gleichmaessig(8, 5), None, 40, roh=True)
        for x in c["hinweise_roh"]:
            if x["typ"] == "buendeln":
                self.assertIn(f"höchstens ~{coach.BUENDEL_MAX_ZIEL} Wörtern", x["text"])
                self.assertIn("Aussagestatus erhalten", x["text"])
                self.assertIn("„weshalb“ oder „wobei“", x["text"])


class Gegenfolie(unittest.TestCase):
    def test_wertungspaar_beibehalten(self):
        self.assertEqual(coach.wertungspaar("Die Firmen sehen den Bericht nicht nur als Last, sondern auch als Instrument der Steuerung."),
                         ("Last", "Instrument"))
        self.assertEqual(coach.wertungspaar("Das ist nicht nur ein Risiko, sondern vor allem eine Chance."), ("Risiko", "Chance"))
        self.assertIsNone(coach.wertungspaar("Das betrifft nicht nur Kunden, sondern auch Händler."))

    def test_additiv_nur_ueber_p75_und_nie_x_und_auch_y(self):
        c = coach.coache(KI_TEXT, None, 40, roh=True)
        for x in c["hinweise_roh"]:
            if x["typ"] == "gegenfolie":
                self.assertNotIn("X und auch Y", x["text"])
        # ein additiver Fall in einem langen Text: ohne ihn läge „…, sondern“ unter P75 → kein Auftrag
        text = gleichmaessig(8, 5) + "\n\nDie Planung ist nicht nur für die Leitung wichtig, sondern auch für die Teams im Betrieb."
        with mit_metriken(sondern_pro_1000=2.0):
            c = coach.coache(text, None, 40, roh=True)
        self.assertFalse([x for x in c["hinweise_roh"] if x["typ"] == "gegenfolie"])


class Konnektoren(unittest.TestCase):
    def test_korpustabelle(self):
        for k, (m, ki) in coach.KONNEKTOR_KORPUS.items():
            self.assertGreaterEqual(m, 0)
            self.assertGreaterEqual(ki, 0)
        self.assertGreater(coach.konnektor_verhaeltnis("zugleich"), coach.KONN_STARK)
        self.assertLess(coach.konnektor_verhaeltnis("außerdem"), 1)
        self.assertIn("„zugleich“", coach.hebel_warum("konnektoren", REF))
        # kein Konnektor als Ersatz angepriesen (Grundsatz 6: keine Wörter einstreuen); Fund der Prüfung
        self.assertNotIn("„außerdem“", coach.hebel_warum("konnektoren", REF))
        self.assertIn("nicht durch einen anderen Konnektor ersetzen", coach.hebel_warum("konnektoren", REF))

    TEXT = ("Die Planung im Betrieb ändert sich zugleich durch neue Werkzeuge und Daten. Außerdem nutzen die Teams neue Wege für die Arbeit. "
            "Die Leitung prüft jedoch die Kosten der Werkzeuge im Detail. Die Teams lernen jedoch schnell dazu und teilen Wissen. "
            "Zudem plant die Leitung mehr Zeit für Schulungen der Teams ein. Die Kosten sinken somit langfristig für den ganzen Betrieb.")

    def hinweise(self, **metriken):
        text = self.TEXT + "\n\n" + gleichmaessig(3, 5)
        with mit_metriken(konnektoren_pro_1000=20.0, **metriken):
            c = coach.coache(text, None, 60, roh=True)
        return text, {x["fund"].lower(): x for x in c["hinweise_roh"] if x["typ"] == "konnektor"}

    def test_nur_ki_typische_oder_gehaeufte(self):
        text, k = self.hinweise(anteil_konnektor_satzanfang=0.2)
        self.assertIn("zugleich", k)  # bei Claude mehr als 4× so häufig: auch einzeln
        self.assertNotIn("jedoch", k)  # nur 2× im Absatz: „jedoch“ erst ab 3
        self.assertNotIn("zudem", k)  # Verhältnis ≈ 2, einzeln: nicht gemeldet
        self.assertNotIn("außerdem", k)  # bei Menschen häufiger
        self.assertNotIn("somit", k)  # Verhältnis ≈ 1, nicht gehäuft
        self.assertIn("7,0×", k["zugleich"]["text"])

    def test_jedoch_ab_drei_und_hoechstens_zwei(self):
        text = (self.TEXT.replace("Die Kosten sinken somit", "Die Kosten sinken jedoch") + "\n\n"
                + "Die Teams arbeiten hingegen gern im Büro und hingegen selten daheim. Die Leitung plant hingegen neue Räume.")
        with mit_metriken(konnektoren_pro_1000=10.0, anteil_konnektor_satzanfang=0.2):  # über P75, unter P90: Regel wie v4
            c = coach.coache(text + "\n\n" + gleichmaessig(3, 5), None, 60, roh=True)
        k = [x for x in c["hinweise_roh"] if x["typ"] == "konnektor"]
        self.assertIn("jedoch", {x["fund"].lower() for x in k})  # 3× im selben Absatz
        self.assertLessEqual(len(k), coach.MAX_KONNEKTOR)
        with mit_metriken(konnektoren_pro_1000=7.0, anteil_konnektor_satzanfang=0.2):  # unter P75: gar nicht
            c = coach.coache(text + "\n\n" + gleichmaessig(3, 5), None, 60, roh=True)
        self.assertFalse([x for x in c["hinweise_roh"] if x["typ"] == "konnektor"])

    def test_keine_satzanfaenge_unter_dem_median(self):
        _, k = self.hinweise(anteil_konnektor_satzanfang=0.05)
        self.assertNotIn("zudem", k)  # Satzanfang
        self.assertIn("zugleich", k)  # Mittelfeld bleibt


class WeiterePraezision(unittest.TestCase):
    """Schutzregeln aus der Sichtprüfung der 60/60-Stichprobe (Quellenzuordnung, Aufzählungen, Pronomen-Ketten)."""

    def lauf(self, text):
        L = coach.Lauf(text + "\n\n" + KI_TEXT, None)
        coach._hebel_priorisieren(L)
        return L

    def test_pronomen_kette_und_name_als_subjekt(self):
        L = self.lauf("Erik spricht zunächst das Risiko an, das mit illegalen Tätigkeiten verbunden ist. "
                      "Er verfügt über ein genaues Wissen über die zuständigen Stellen.")
        self.assertEqual(coach.bezug_vorschlag(L, L.saetze[0], L.saetze[1], "pron", "Er"), (False, []))
        L = self.lauf("Wissen verbreite sich seiner Wahrnehmung nach diffus, was er als ineffektiv empfindet. "
                      "Er wünscht sich daher feste Spielregeln für das ganze Team.")
        self.assertEqual(coach.bezug_vorschlag(L, L.saetze[0], L.saetze[1], "pron", "Er"), (False, []))

    def test_buendeln_schreibt_satz_b_keiner_quelle_zu(self):
        L = self.lauf("Die Geschäftsleitungen heben in diesem Zusammenhang die Verlässlichkeit langjähriger Mitarbeiter im Betrieb hervor. "
                      "Eine schnelle Kündigung von Mitarbeitern war in den untersuchten Betrieben der Region dagegen nicht festzustellen.")
        self.assertFalse(coach.buendel_paar_ok(L, L.saetze[0], L.saetze[1]))
        L = self.lauf("Im Folgenden werden das erste und das dritte Modell der betrieblichen Suchthilfe näher betrachtet. "
                      "Das erste Modell legt den Schwerpunkt auf die Suchtkrankenhilfe mit präventiven Elementen im Betrieb.")
        self.assertFalse(coach.buendel_paar_ok(L, L.saetze[0], L.saetze[1]))

    def test_klammer_ohne_langen_quellsatz(self):
        lang = ("Die Nebenwirkungen würden geringer ausfallen, wenn sich die Entscheidungsträger nicht nur anhand der ökonomischen "
                "Vernunft bei ihren Entscheidungen im Alltag leiten ließen.")
        self.assertTrue(coach.KLAMMER_QUELLE_RE.search(lang))
        text = "\n\n".join([lang] * 3 + [KI_TEXT])
        with mit_metriken(satzklammer_mittel=3.0):
            c = coach.coache(text, None, 40, roh=True)
        nr = saetze_von(text)[0]["nr"]
        self.assertFalse([x for x in c["hinweise_roh"] if x["typ"] == "klammer" and x["satz"] == nr])

    def test_kein_bezug_nicht_bei_erlaeuterung_eines_aufzaehlungsglieds(self):
        text = ("Diesen Chancen stehen jedoch erhebliche Risiken für den Handel gegenüber. Ein weiteres Risiko liegt in der Technik selbst. "
                "Preisalgorithmen reagieren auf die Preise anderer Algorithmen und führen so zu unerwarteten Ergebnissen.\n\n"
                + gleichmaessig(4, 5))
        with mit_metriken(anteil_saetze_mit_wortaufnahme=0.2):
            c = coach.coache(text, None, 40, roh=True)
        nr = nr_von(text, "Preisalgorithmen reagieren")
        self.assertFalse([x for x in c["hinweise_roh"] if x["typ"] == "kein_bezug" and x["satz"] == nr])

    def test_absatz_nie_zwischen_gebuendelten_saetzen(self):
        c = coach.coache(gleichmaessig(8, 5), None, 40, roh=True)
        folge = {n for x in c["hinweise_roh"] for n in x.get("weitere_nr") or []}
        for x in c["hinweise_roh"]:
            if x["typ"] == "absatz_teilen":
                for nr in map(int, re.findall(r"vor Satz (\d+)", x["text"])):
                    self.assertNotIn(nr, folge)


class Hebeltexte(unittest.TestCase):
    def test_jeder_beleg_entspricht_den_daten(self):
        for h_, (kz, richtung, _f, _art) in coach.HEBEL_BELEG.items():
            r = REF[kz]
            m, k = r["mensch"]["p50"], r["ki"]["p50"]
            self.assertNotEqual(m, k, kz)
            self.assertEqual(k > m, richtung == "ki", f"{h_}: {kz} Mensch {m}, KI {k}")
            self.assertIn("(", coach.hebel_warum(h_, REF, "Daten."))  # Zahlen stehen im Text

    def test_funktionswoerter_aus_dem_profil(self):
        ki, mensch = coach.fw_typische(TS["fw_profil"])
        rm, rk = TS["fw_profil"]["rate_mensch"], TS["fw_profil"]["rate_ki"]
        self.assertTrue(all(rk[w] > rm[w] for w in ki))
        self.assertTrue(all(rm[w] > rk[w] for w in mensch))
        text = coach.hebel_warum("funktionswoerter", REF, "", TS["fw_profil"])
        for w in ki + mensch:
            self.assertIn(f"„{w}“", text)

    def test_ki_nah_nur_bei_negativem_wert(self):
        self.assertEqual(coach.kennzahl_lage({"wert": -1.2, "mensch_p50": 3.8}), "KI-nah")
        self.assertIn("unter dem menschlichen Median", coach.kennzahl_lage({"wert": 1.2, "mensch_p50": 3.8}))
        self.assertIn("über dem menschlichen Median", coach.kennzahl_lage({"wert": 5.0, "mensch_p50": 3.8}))


if __name__ == "__main__":
    unittest.main()
