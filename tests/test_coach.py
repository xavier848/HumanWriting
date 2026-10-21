"""Tests für den Stil-Coach (coach.py): Satzlängen-Steuerung, Zitatschutz, Anknüpfung, Überkorrektur, Gedächtnis.

python3 -m unittest discover -s tests
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
import analyse  # noqa: E402
import coach  # noqa: E402

# Eigener, synthetischer Text im Stil eines KI-Entwurfs (kein Korpustext)
KI_TEXT = """## Arbeitgebermarke im Mittelstand

Die Arbeitgebermarke spielt für kleine und mittlere Unternehmen eine zentrale Rolle bei der Gewinnung von Fachkräften. Darüber hinaus verdeutlicht die aktuelle Forschung, dass die Bindung der Mitarbeitenden stark von der Marke abhängt. Ihr Einfluss reicht dabei weit über die reine Personalgewinnung hinaus und betrifft auch die interne Kommunikation. Zudem lässt sich beobachten, dass viele Betriebe ihre Arbeitgebermarke bislang kaum systematisch planen; die Ressourcen fehlen oft.

Die Kunden achten zunehmend auf die Werte eines Unternehmens, und die Konsumenten vergleichen Angebote online. Viele Verbraucher erwarten heute transparente Informationen über Arbeitsbedingungen und Nachhaltigkeit. Auch die Kunden reagieren sensibel auf negative Bewertungen von ehemaligen Beschäftigten. Die Konsumenten nutzen dafür vor allem Bewertungsportale, die in den letzten Jahren stark gewachsen sind.

Eine klare Positionierung ist nicht nur für die Rekrutierung wichtig, sondern auch für die Motivation im Team. Sie entsteht jedoch nicht von selbst, sondern erfordert eine bewusste Gestaltung durch die Geschäftsführung. Diese Herausforderung wird in vielen Betrieben unterschätzt, obwohl die Folgen deutlich spürbar sind. Gleichzeitig zeigt sich, dass bereits kleine Maßnahmen eine messbare Wirkung entfalten können.

Müller und Schmidt betonen, dass die Glaubwürdigkeit der Botschaft entscheidend ist (Müller & Schmidt, 2021). Seine Wirkung entfaltet ein Versprechen nur, wenn der Alltag im Betrieb dazu passt. Insgesamt zeigt sich, dass die Arbeitgebermarke ein wirksames Instrument der Personalpolitik sein kann. Die Umsetzung erfordert allerdings Zeit, Geduld und eine realistische Einschätzung der eigenen Stärken.

In einem Interview sagte ein Geschäftsführer: „Wir haben keine Zeit für Marketing; wir müssen produzieren – und zwar jeden Tag.“ Dieses Zitat zeigt die Spannung zwischen Tagesgeschäft und strategischer Planung. Die Arbeitgebermarke bleibt dennoch ein zentrales Thema für die Zukunft der Betriebe. Sie verbindet Personalpolitik, Kommunikation und Unternehmenskultur zu einem gemeinsamen Ansatz.
"""

_WORTE = ("regionale Betriebe nutzen digitale Kanäle für die gezielte Ansprache junger Fachkräfte im ländlichen Raum während "
          "größere Konzerne eigene Abteilungen für Kommunikation Personalplanung Weiterbildung Gesundheitsförderung und "
          "Nachwuchsprogramme unterhalten sowie externe Agenturen mit Kampagnen Messen Workshops Befragungen Analysen "
          "Berichten Schulungen Veranstaltungen Kooperationen Hochschulen Verbänden Kammern Netzwerken beauftragen").split()


# kurze Allerweltswörter: Lesbarkeit im menschlichen Bereich (mit _WORTE liegen LIX/Nominalstil weit über P90, dann setzt der
# Coach alle Verdichtungs-Hinweise aus)
_KURZE_WORTE = ("die Firma nutzt oft neue Wege für den Kontakt mit jungen Leuten in der Region und plant dazu auch mehr Zeit und "
                "Geld ein weil der Markt sich schnell ändert und gute Kräfte rar sind so dass jede Stelle lange offen bleibt und das "
                "Team die Arbeit teilen muss").split()


def satz(thema: str, n: int, start: int = 0, worte=_WORTE) -> str:
    """Satz mit genau n Wörtern, der mit „Die {thema}“ beginnt (synthetisch, inhaltlich beliebig)."""
    rest = [worte[(start + i) % len(worte)] for i in range(n - 3)]
    return " ".join(["Die", thema, "betrifft"] + rest) + "."


def absatz(thema: str, laengen: list[int], start: int = 0, worte=_WORTE) -> str:
    return " ".join(satz(thema, n, start + 7 * i, worte) for i, n in enumerate(laengen))


def coache_still(text, verlauf=None, n=15, roh=False):
    return coach.coache(text, verlauf, n, roh=roh)


class Hilfsfunktionen(unittest.TestCase):
    def test_zickzack_absolute_klassen(self):
        # kurz ≤ 15, lang ≥ 25, mindestens fünf Sätze im strengen Wechsel
        self.assertEqual(coach.zickzack([6, 28, 7, 31, 6, 27, 8]), [(0, 6)])
        # 24 und 23 Wörter sind mittellang: kein Zickzack (früher relativ zum Mittel gemessen)
        self.assertEqual(coach.zickzack([6, 24, 7, 25, 6, 23, 8]), [])
        self.assertEqual(coach.zickzack([18, 19, 21, 17, 20, 18]), [])
        # lange Sätze ohne Wechsel (alle ≥ 25) sind kein Zickzack
        self.assertEqual(coach.zickzack([28, 48, 36, 44, 30]), [])
        # zwei Bereiche überlappen nicht
        b = coach.zickzack([6, 28, 7, 31, 6, 6, 30, 8, 27, 9])
        self.assertEqual(b, [(0, 4), (5, 9)])

    def test_klammer(self):
        self.assertEqual(coach.klammer_spannen("Die Daten wurden im Frühjahr 2019 online erhoben."), [3])  # Zahlen zählen nicht
        self.assertEqual(coach.klammer_spannen("Die Befragung wurde durchgeführt."), [])
        self.assertEqual(coach.klammer_details("Die Studie wurde im Jahr erhoben."), [(2, "wurde", "erhoben")])

    def test_mechanisch_verlaengert(self):
        vorher = {"satzlaenge_mittel": 16.0, "woerter_pro_teilsatz": 8.0, "satzklammer_mittel": 5.0}
        angehaengt = {"satzlaenge_mittel": 20.0, "woerter_pro_teilsatz": 7.5, "satzklammer_mittel": 5.0}
        verdichtet = {"satzlaenge_mittel": 20.0, "woerter_pro_teilsatz": 9.0, "satzklammer_mittel": 5.0}
        self.assertTrue(coach.mechanisch_verlaengert(vorher, angehaengt))
        self.assertFalse(coach.mechanisch_verlaengert(vorher, verdichtet))
        self.assertFalse(coach.mechanisch_verlaengert(vorher, {**angehaengt, "satzlaenge_mittel": 17.0}))
        self.assertFalse(coach.mechanisch_verlaengert({}, angehaengt))

    def test_anknuepfung_nur_ki_typische_anfaenge(self):
        for anfang in ("Ihr Anwendungsbereich war begrenzt.", "Seine Wirkung ist klar.", "Deren Umsetzung fehlt.",
                       "Sie zeigen das.", "Diese Einschätzung greift zu kurz."):
            self.assertTrue(coach.ANKNUEPF_RE.match(anfang), anfang)
        # bei Menschen häufiger als bei Claude: kein Anknüpfungs-Hinweis mehr
        for anfang in ("Dies deckt sich mit den Befunden.", "Dabei zeigt sich ein Muster.", "Dadurch sinken Kosten.",
                       "Hierbei hilft eine Liste.", "Hierdurch entsteht Druck."):
            self.assertIsNone(coach.ANKNUEPF_RE.match(anfang), anfang)
        self.assertTrue(coach.ist_kapselwort("Einschätzung"))
        self.assertTrue(coach.ist_kapselwort("Doppelperspektive"))
        self.assertTrue(coach.ist_kapselwort("Entwicklungen"))
        self.assertFalse(coach.ist_kapselwort("Ergebnisse"))
        self.assertTrue(coach.KATAPHER_RE.match("Seine Wirkung entfaltet ein Versprechen nur, wenn …"))
        self.assertIsNone(coach.KATAPHER_RE.match("Ihr Anwendungsbereich war allerdings eng begrenzt."))

    def test_bezugsausdruck_nicht_laengstes_wort(self):
        k = coach.bezugsausdruecke("Die Richtlinie ließ große Spielräume bei der Nachhaltigkeitsberichterstattung.")
        self.assertEqual(k[0], "Richtlinie")
        k = coach.bezugsausdruecke("Näher betrachtet nutzen die Mitarbeitenden die Plattform im Jahr 2020.")
        self.assertNotIn("Näher", k)
        self.assertNotIn("Mitarbeitenden", k)  # Gender-Partizip nie als Leitbegriff
        self.assertNotIn("Jahr", k)
        self.assertIn("Plattform", k)
        k = coach.bezugsausdruecke("Mit der Corporate Sustainability Reporting Directive hat die Europäische Union reagiert.")
        self.assertIn("Europäische Union", k)

    def test_verbunden_komposita_und_akronyme(self):
        b = coach.satz_begriffe
        self.assertEqual(coach.verbunden(b("Die Berichterstattung war lückenhaft."),
                                         b("Für die Nachhaltigkeitsberichterstattung fehlten Standards.")), "kompositum")
        self.assertEqual(coach.verbunden(b("Der Preis bleibt gleich."), b("Eine differenzierte Preissetzung hilft.")), "kompositum")
        self.assertEqual(coach.verbunden(b("Die Corporate Sustainability Reporting Directive trat in Kraft."),
                                         b("Die CSRD verlangt mehr.")), "akronym")
        self.assertEqual(coach.verbunden(b("Kleine und mittlere Unternehmen investieren wenig."),
                                         b("KMU fehlen Ressourcen.")), "akronym")
        self.assertIsNone(coach.verbunden(b("Die Marke wirkt nach außen."), b("Gehälter steigen jährlich.")))

    def test_funktionswoerter(self):
        for t in ("Das lässt sich messen.", "Daraus lassen sich drei Typen ableiten.", "wie sich der Effekt beschreiben lässt."):
            self.assertTrue(coach.LASSEN_SICH_RE.search(t), t)
        self.assertIsNone(coach.LASSEN_SICH_RE.search("welche sie sich mit einem Anteil am Unternehmen honorieren lassen, sondern"))
        z = coach.fw_zaehlung(analyse.tokens("Sowohl Kunden als auch Händler sehen mehr als früher, sie gilt als Vorbild"),
                              {"als", "sie"})
        self.assertEqual(z, {"als": 1, "sie": 1})  # „als auch“ und „mehr als“ zählen nicht

    def test_synonym_cluster(self):
        saetze = [{"nr": i + 1, "absatz": 1, "text": t} for i, t in enumerate([
            "Die Kunden vergleichen Preise.", "Viele Konsumenten kaufen online.", "Die Kunden reagieren schnell.",
            "Verbraucher achten auf Werte.", "Die Führungskräfte entscheiden.", "Eine Führungskraft plant.",
            "Die Führungskräfte prüfen."])]
        c = coach.synonym_cluster(saetze, {})
        self.assertEqual(len(c), 1)  # Führungskraft/Führungskräfte ist dasselbe Wort, kein Synonym-Wechsel
        self.assertEqual([w for w, _ in c[0]["varianten"]][0], "Kunden")
        self.assertIn("konsumenten", c[0]["formen"])

    def test_zitat_masken(self):
        saetze = [{"nr": 1, "absatz": 1, "text": "Er sagte: „Wir haben keine Zeit; wir müssen produzieren – jeden Tag.“"},
                  {"nr": 2, "absatz": 1, "text": "„Das ist der erste Satz des Zitats."},
                  {"nr": 3, "absatz": 1, "text": "Das ist der zweite Satz.“ Danach folgt die Begründung."},
                  {"nr": 4, "absatz": 1, "text": "Hier steht ein Semikolon; außerhalb (vgl. ebd., S. 12) des Zitats."}]
        m = coach.zitat_masken(saetze)
        self.assertNotIn(";", m[1])
        self.assertNotIn("–", m[1])
        self.assertFalse(any(ch.isalpha() for ch in m[2]))  # ganzer Satz liegt im Zitat
        self.assertIn("Danach", m[3])
        self.assertIn(";", m[4])
        self.assertNotIn("ebd", m[4])
        self.assertEqual(len(m[4]), len(saetze[3]["text"]))

    def test_quellen_flags(self):
        text = ("Die Studie zeigt einen klaren Effekt auf die Bindung (Müller, 2019). Die Bindung steigt mit dem Alter der Befragten.\n\n"
                "Ambler und Barrow (1996) definieren die Marke als Paket. Sie betonen den Nutzen.")
        erg = analyse.analysiere_text(text)
        q, a = coach.quellen_flags(text, erg["saetze"])
        self.assertEqual([q.get(s["nr"]) for s in erg["saetze"]], [True, False, True, False])
        self.assertTrue(a.get(3))  # Autorenangabe am Satzanfang

    def test_satzlaengen_diagnose(self):
        ref = analyse.lade_baselines()["textsorten"]["hochschule"]["metriken"]
        ziel = analyse.lade_baselines()["textsorten"]["hochschule"]["satzlaengen_verteilung_mensch"]
        ki = [{"woerter": w} for w in [18, 20, 17, 22, 19, 21, 16, 23] * 5]
        d = coach.satzlaengen_diagnose(ki, ref, ziel, None)
        self.assertEqual(d["modus"], "buendeln")
        p50 = ref["anteil_lange_saetze"]["mensch"]["p50"]
        # k Bündelungen: (0 + k) / (40 − k) soll am nächsten beim Median liegen (jede Bündelung kostet einen Satz)
        self.assertEqual(d["kontingent"], round(p50 * 40 / (1 + p50)))
        ueber = [{"woerter": w} for w in [35, 38, 33, 12, 9, 36, 31, 34, 11, 40] * 3]
        d = coach.satzlaengen_diagnose(ueber, ref, ziel, None)
        self.assertEqual(d["modus"], "teilen")
        self.assertTrue(d["fehlende_mitte"])
        self.assertGreaterEqual(d["kontingent"], 1)

    def test_teilstelle(self):
        t = ("Die Unternehmen haben in den letzten Jahren viele neue Instrumente für die Personalgewinnung eingeführt, wobei "
             "vor allem kleinere Betriebe auf digitale Kanäle und persönliche Empfehlungen aus dem Umfeld setzen.")
        st = coach.teilstelle(t, t)
        self.assertIsNotNone(st)
        self.assertIn("wobei", st[3])
        self.assertGreaterEqual(min(st[1], st[2]), 8)


class CoachLauf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = coache_still(KI_TEXT, None, 40, roh=True)
        cls.alle = cls.c["hinweise_roh"]
        cls.erg = analyse.analysiere_text(KI_TEXT)

    def satz_nr(self, anfang):
        return next(s["nr"] for s in self.erg["saetze"] if s["text"].startswith(anfang))

    def test_coach_laeuft_und_schreibt_verlauf(self):
        text = ("## Einleitung\n\nDie Arbeitgebermarke ist für kleine Unternehmen wichtig. Darüber hinaus verdeutlicht dies, dass "
                "die Mitarbeitenden profitieren; die Bindung steigt. Insgesamt zeigt sich ein klarer Effekt für die Unternehmen.\n\n"
                "Die Studie untersucht drei Fälle aus dem Mittelstand. Sie nutzt Interviews mit Führungskräften und Beschäftigten.\n")
        c = coach.coache(text * 3, None, 10)
        self.assertIn("hinweise", c)
        texte = " ".join(h["text"] for h in c["hinweise"])
        self.assertIn("Mitarbeitende", texte)  # Nutzer-Vorgabe generisches Maskulinum wird immer gemeldet
        self.assertIn("Semikolon", texte)
        with tempfile.TemporaryDirectory() as d:
            pfad, vpfad = os.path.join(d, "t.md"), os.path.join(d, "t.coach.json")
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(KI_TEXT)
            with redirect_stdout(io.StringIO()):
                coach.main([pfad, "--verlauf", vpfad])
                coach.main([pfad, "--verlauf", vpfad, "--format", "json"])
            with open(vpfad, encoding="utf-8") as f:
                v = json.load(f)
        self.assertEqual(len(v["messungen"]), 2)
        stand = v["messungen"][-1]
        for k in ("score", "p_mensch", "kennzahlen", "roh", "hinweise", "ersetzbar"):
            self.assertIn(k, stand)
        self.assertTrue(stand["ersetzbar"])
        self.assertTrue(all(w == w.lower() for w in stand["ersetzbar"]))
        self.assertIn("anteil_lange_saetze", stand["roh"])
        self.assertTrue(all({"typ", "anfang", "satz"} <= set(h) for h in stand["hinweise"]))

    def test_keine_hinweise_in_zitaten(self):
        nr = self.satz_nr("In einem Interview")
        self.assertFalse([h for h in self.alle if h["satz"] == nr and h["typ"] in ("semikolon", "gedankenstrich", "floskel")])
        self.assertTrue([h for h in self.alle if h["typ"] == "semikolon" and h["satz"] == self.satz_nr("Zudem lässt sich")])

    def test_anknuepfung(self):
        ank = {h["satz"]: h for h in self.alle if h["typ"] == "anknuepfung"}
        self.assertIn(self.satz_nr("Diese Herausforderung"), ank)  # abstraktes Sammelwort
        self.assertNotIn(self.satz_nr("Seine Wirkung"), ank)  # Bezug folgt im selben Satz
        self.assertNotIn(self.satz_nr("Dieses Zitat"), ank)  # kein abstraktes Sammelwort
        for h in ank.values():
            self.assertNotRegex(h["text"], r"„Mitarbeitende")

    def test_gegenfolie_additiv(self):
        g = [h for h in self.alle if h["typ"] == "gegenfolie" and h["satz"] == self.satz_nr("Eine klare Positionierung")]
        self.assertTrue(g)
        self.assertIn("neben X auch Y", g[0]["text"])
        self.assertNotIn("streichen", g[0]["text"])

    def test_konkrete_stellen_und_keine_claude_woerter(self):
        self.assertFalse([h for h in self.alle if "Typische Claude-Wörter" in h["text"]])
        allgemein = {h["typ"] for h in self.alle if h["satz"] is None}
        self.assertLessEqual(allgemein, {"synonyme", "absatz_zusammen", "zickzack"})
        syn = [h for h in self.alle if h["typ"] == "synonyme"]
        self.assertTrue(any("Konsumenten" in h["text"] for h in syn))

    def test_struktureller_auftrag_hoechstens_einmal_je_satz(self):
        strukturell = [h["satz"] for h in self.alle if h["typ"] in coach.STRUKTURELL and h["satz"]]
        self.assertEqual(len(strukturell), len(set(strukturell)))

    def test_bericht(self):
        b = coach.bericht(self.c)
        self.assertIn("Konkrete Stellen", b)
        self.assertNotIn("Ziel erreicht", b)


class Satzlaengen(unittest.TestCase):
    def ki_text(self):
        # gleichförmige, mittellange Sätze (KI-typisch), gleiches Thema je Absatz; Absatz 1: nur Satz 1 mit Quellenverweis
        w = _KURZE_WORTE
        absaetze = [satz("Arbeitgebermarke", 19, 0, w) + " (Meier, 2020) " + absatz("Arbeitgebermarke", [18, 13, 22, 16], 3, w)]
        for i, thema in enumerate(["Personalplanung", "Weiterbildung", "Kommunikation", "Gesundheitsförderung", "Nachwuchsarbeit",
                                   "Unternehmenskultur", "Mitarbeiterbindung"]):
            absaetze.append(absatz(thema, [[14, 21, 17, 23, 12], [19, 16, 25, 13, 20], [22, 15, 18, 24, 11]][i % 3], 11 * i, w))
        return "\n\n".join(absaetze)

    def test_buendeln_mit_kontingent_und_quellenschutz(self):
        text = self.ki_text()
        c = coache_still(text, None, 40, roh=True)
        self.assertEqual(c["satzlaengen"]["modus"], "buendeln")
        b = [h for h in c["hinweise_roh"] if h["typ"] == "buendeln"]
        self.assertTrue(b)
        self.assertLessEqual(len(b), c["satzlaengen"]["kontingent"])
        self.assertNotIn(1, [h["satz"] for h in b])  # Satz 1 trägt eine Quelle, Satz 2 nicht: nicht bündeln
        erg = analyse.analysiere_text(text)
        laenge = {s["nr"]: s["woerter"] for s in erg["saetze"]}
        for h in b:
            self.assertGreaterEqual(laenge[h["satz"]] + laenge[h["satz"] + 1], coach.BUENDEL_SUMME[0])
            self.assertLessEqual(laenge[h["satz"]] + laenge[h["satz"] + 1], coach.BUENDEL_SUMME[1])

    def ueber_text(self):
        absaetze = []
        for i, thema in enumerate(["Arbeitgebermarke", "Personalplanung", "Weiterbildung", "Kommunikation", "Nachwuchsarbeit",
                                   "Unternehmenskultur"]):
            absaetze.append(absatz(thema, [34, 12, 38, 33, 9, 44], 5 * i))
        return "\n\n".join(absaetze)

    def test_ueberkorrigiert_kein_buendeln_aber_teilen(self):
        text = self.ueber_text()
        c = coache_still(text, None, 40, roh=True)
        self.assertEqual(c["satzlaengen"]["modus"], "teilen")
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] in ("buendeln", "klammer_zusatz")])
        self.assertTrue([h for h in c["hinweise_roh"] if h["typ"] == "teilen"])

    def test_ueberkorrektur_waechter(self):
        text = self.ueber_text()
        verlauf = {"messungen": [{"score": 40, "p_mensch": 0.01, "kennzahlen": {},
                                  "roh": {"anteil_lange_saetze": 0.05, "satzlaenge_mittel": 18.5, "anteil_mittlere_saetze": 0.62,
                                          "satzlaenge_median": 18.0}}]}
        c = coache_still(text, verlauf, 40, roh=True)
        uk = {u["id"]: u for u in c["fortschritt"]["ueberkorrektur"]}
        self.assertIn("anteil_lange_saetze", uk)
        self.assertEqual(uk["anteil_lange_saetze"]["art"], "Überkorrektur")
        self.assertIn("buendeln", c["fortschritt"]["ausgesetzt"])
        teilen = [h for h in c["hinweise_roh"] if h["typ"] == "teilen"]
        self.assertGreater(len(teilen), 2)  # mit Beleg aus dem Verlauf bis zum Median (mehr als ohne Verlauf)
        self.assertIn("Überkorrektur", coach.bericht(c))

    def test_pendeln_wird_unterdrueckt(self):
        text = self.ueber_text()
        erg = analyse.analysiere_text(text)
        laengster = max(erg["saetze"], key=lambda s: s["woerter"])
        anfang = coach.schluessel_anfang(laengster["text"])
        verlauf = {"messungen": [{"score": 40, "p_mensch": 0.01, "kennzahlen": {},
                                  "roh": {"anteil_lange_saetze": 0.05, "satzlaenge_mittel": 18.5},
                                  "hinweise": [{"typ": "buendeln", "anfang": anfang, "satz": laengster["nr"]}]}]}
        c = coache_still(text, verlauf, 40, roh=True)
        geteilt = {coach.schluessel_anfang(erg["saetze"][h["satz"] - 1]["text"]) for h in c["hinweise_roh"] if h["typ"] == "teilen"}
        self.assertTrue(geteilt)
        self.assertNotIn(anfang, geteilt)


class VerlaufUndModi(unittest.TestCase):
    def test_hinweis_gedaechtnis(self):
        # höchstens 8 angezeigt: seit „ein Auftrag je Satz“ passen sonst alle Hinweise des kurzen Texts in die erste Runde
        c1 = coache_still(KI_TEXT, None, 8)
        c2 = coache_still(KI_TEXT, {"messungen": [c1["stand"]]}, 8, roh=True)
        genannt = [h for h in c2["hinweise_roh"] if h.get("schon_genannt")]
        self.assertTrue(genannt)
        self.assertTrue(all("schon in Runde 1 genannt" in h["text"] for h in genannt))
        # Herabgestufte Hinweise machen Platz für neue
        neu = {(h["typ"], h["anfang"]) for h in c2["hinweise"]} - {(h["typ"], h["anfang"]) for h in c1["hinweise"]}
        self.assertTrue(neu)

    def test_ziel_erreicht_nur_vorgaben_und_sichere_hinweise(self):
        echt = coach.analyse.analysiere_und_bewerte

        def fake(*a, **k):
            erg, bew = echt(*a, **k)
            return erg, dict(bew, score=95, p_mensch=0.99)

        with mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake):
            c = coache_still(KI_TEXT)
        self.assertTrue(c["ziel_erreicht"])
        self.assertLessEqual(len(c["hinweise"]), coach.ZIEL_MAX)
        for h in c["hinweise"]:
            self.assertIn(h["typ"], coach.ZIEL_TYPEN)
            if h["typ"] == "floskel":
                self.assertGreaterEqual(h["muster_gewicht"], 1.5)
        self.assertIn("Kein weiterer Handlungsbedarf", coach.bericht(c))

    def test_teilziel_score(self):
        echt = coach.analyse.analysiere_und_bewerte

        def fake(*a, **k):
            erg, bew = echt(*a, **k)
            return erg, dict(bew, score=40, p_mensch=0.99)

        with mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake):
            c = coache_still(KI_TEXT)
        self.assertIsNotNone(c["teilziel"])
        self.assertLessEqual(len(c["hinweise"]), 8)
        for h in c["hinweise"]:
            self.assertTrue(h["hebel"] in c["teilziel"]["hebel"] or h["hebel"] == "vorgaben", h)

    def test_blockmodus_nur_schwaechster_block(self):
        teile = [KI_TEXT]
        for i, thema in enumerate(["Personalplanung", "Weiterbildung", "Kommunikation", "Nachwuchsarbeit", "Unternehmenskultur",
                                   "Mitarbeiterbindung", "Gesundheitsförderung", "Arbeitszeitmodelle"]):
            teile.append(absatz(thema, [9, 31, 14, 26, 41, 12, 22, 7], 3 * i))
        text = "\n\n".join(teile)
        c = coache_still(text, None, 40, roh=True)
        self.assertTrue(c["blockmodus"])
        fo = c["fokus"]
        self.assertIsNotNone(fo["block"])
        for h in c["hinweise_roh"]:
            if h["satz"]:
                self.assertTrue(fo["satz_von"] <= h["satz"] <= fo["satz_bis"], h)

    def test_fragmente_ohne_hinweise(self):
        text = KI_TEXT + "\n\nSiehe oben; ebd.\n"
        c = coache_still(text, None, 40, roh=True)
        erg = analyse.analysiere_text(text)
        kurz = {s["nr"] for s in erg["saetze"] if s["woerter"] < coach.MIN_WOERTER}
        self.assertTrue(kurz)
        self.assertFalse([h for h in c["hinweise_roh"] if h["satz"] in kurz])

    def test_mechanisch_verlaengert_im_bericht(self):
        c = coach.coache("Die Unternehmen investieren in die Ausbildung. Sie wollen Fachkräfte binden.\n\n" * 8,
                         {"messungen": [{"score": 50, "p_mensch": 0.5, "kennzahlen": {}, "roh": {"satzlaenge_mittel": 2.0,
                                                                                               "woerter_pro_teilsatz": 99.0}}]}, 5)
        self.assertTrue(c["fortschritt"]["mechanisch_verlaengert"])
        self.assertIn("Mechanisch verlängert", coach.bericht(c))


THEMEN = ["Arbeitgebermarke", "Personalplanung", "Weiterbildung", "Kommunikation", "Nachwuchsarbeit", "Unternehmenskultur",
          "Mitarbeiterbindung", "Gesundheitsförderung", "Arbeitszeitmodelle", "Führungskultur", "Vergütung", "Onboarding"]


class Regressionen(unittest.TestCase):
    """Funde der adversarialen Prüfung (Coach v2)."""

    def test_zickzack_ueber_absaetze_ist_allgemeiner_hinweis(self):
        w = _KURZE_WORTE
        teile = [absatz(THEMEN[0], [18, 20, 8, 31], 1, w), absatz(THEMEN[1], [9, 32, 7, 20, 19], 2, w)]
        teile += [absatz(t, [8, 30, 16, 26, 9, 21], 3 * i, w) for i, t in enumerate(THEMEN[2:7])]
        text = "\n\n".join(teile)
        c = coache_still(text, None, 40, roh=True)
        S = {s["nr"]: s for s in analyse.analysiere_text(text)["saetze"]}
        zz = [h for h in c["hinweise_roh"] if h["typ"] == "zickzack"]
        self.assertTrue(zz)
        for h in zz:
            a, b = map(int, re.search(r"Satz (\d+)–(\d+)", h["text"]).groups())
            if S[a]["absatz"] != S[b]["absatz"]:
                self.assertIsNone(h["absatz"], h["text"])  # nicht unter „Absatz N“ einsortieren

    def test_kein_zickzack_verbinden_im_teilen_modus(self):
        # 50 % lange Sätze im strengen Wechsel: TEILEN-Modus, also kein „Satz X mit X+1 verbinden“ (ergäbe ≥ 40 Wörter)
        text = "\n\n".join(absatz(t, [8, 34, 9, 36, 7, 33, 9, 35], 5 * i, _KURZE_WORTE) for i, t in enumerate(THEMEN[:6]))
        c = coache_still(text, None, 40, roh=True)
        self.assertEqual(c["satzlaengen"]["modus"], "teilen")
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] in ("zickzack", "buendeln", "klammer_zusatz")])
        # der Hebeltext lädt nicht zu weiteren langen Sätzen ein
        self.assertNotIn("satzlaenge", [h["id"] for h in c["hebel"]])
        self.assertNotIn("KI-Texte bleiben im mittleren Band", coach.bericht(c))

    def test_zickzack_pendeln(self):
        self.assertIn("zickzack", coach.GEGENTEIL["teilen"])
        self.assertIn("teilen", coach.GEGENTEIL["zickzack"])
        self.assertIn("zickzack", coach.WAECHTER["anteil_lange_saetze"]["gegen"])

    def test_absatz_pendeln_wird_erkannt(self):
        paare = [THEMEN[i // 2] for i in range(12)]  # je zwei Nachbarabsätze zum selben Thema
        text = "\n\n".join(absatz(t, [17, 19, 21], 4 * i, _KURZE_WORTE) for i, t in enumerate(paare))
        c = coache_still(text, None, 40, roh=True)
        z = [h for h in c["hinweise_roh"] if h["typ"] == "absatz_zusammen"]
        self.assertTrue(z)
        x, y = map(int, re.search(r"Absatz (\d+) und (\d+)", z[0]["text"]).groups())
        erster_y = next(s for s in analyse.analysiere_text(text)["saetze"] if s["absatz"] == y)
        verlauf = {"messungen": [{"score": 40, "p_mensch": 0.1, "kennzahlen": {}, "roh": {},
                                  "hinweise": [{"typ": "absatz_teilen", "anfang": coach.schluessel_anfang(erster_y["text"]),
                                                "satz": erster_y["nr"]}]}]}
        c2 = coache_still(text, verlauf, 40, roh=True)
        self.assertFalse([h for h in c2["hinweise_roh"] if h["typ"] == "absatz_zusammen" and f"Absatz {x} und {y} " in h["text"]])

    def test_absatz_teilen_nicht_gegen_die_eigene_kennzahl(self):
        # gleichmäßige kleine Absätze (3 Sätze) und einer mit 5: Teilen des größten senkt die Streuung weiter und drückt
        # Sätze pro Absatz unter P25 – kein Auftrag
        laengen = [[18, 16, 21], [15, 20, 17], [19, 22, 14]]
        groessen = [3, 3, 3, 3, 5, 3, 3, 3, 3, 3, 3, 3]
        text = "\n\n".join(absatz(t, (laengen[i % 3] + [17, 23])[:g], 5 * i, _KURZE_WORTE)
                           for i, (t, g) in enumerate(zip(THEMEN, groessen)))
        c = coache_still(text, None, 40, roh=True)
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] == "absatz_teilen"])

    def test_lesbarkeit_jenseits_keine_verdichtung(self):
        # mit _WORTE liegen LIX, Wiener Sachtextformel und Nominalstil weit über P90 (Gegenseite der KI)
        absaetze = [absatz(t, [[14, 21, 17, 23, 12], [19, 16, 25, 13, 20], [22, 15, 18, 24, 11]][i % 3], 11 * i)
                    for i, t in enumerate(THEMEN[:8])]
        text = "\n\n".join(absaetze)
        c = coache_still(text, None, 40, roh=True)
        self.assertIn("nominalstil_pro_100", [j["id"] for j in c["jenseits"]])
        self.assertFalse([h for h in c["hinweise_roh"] if h["typ"] in coach._VERDICHTEN])
        self.assertIn("Schon jenseits des menschlichen Bereichs", coach.bericht(c))

    def test_teilen_nicht_im_woertlichen_zitat(self):
        absaetze = [absatz(t, [34, 12, 38, 33, 9, 44], 5 * i, _KURZE_WORTE) for i, t in enumerate(THEMEN[:5])]
        zitat = ("Meier schreibt: „Die Marke umfasst die Entwicklung und Kommunikation einer klaren Identität des Betriebs als "
                 "Arbeitgeber gegenüber allen aktuellen und künftigen Beschäftigten sowie die Ausrichtung aller Maßnahmen an diesem "
                 "Versprechen und seiner glaubwürdigen Einlösung im Alltag der ganzen Organisation und darüber hinaus in allen "
                 "Gesprächen mit Bewerbern, Kunden und Partnern“.")
        text = "\n\n".join(absaetze + [zitat])
        verlauf = {"messungen": [{"score": 40, "p_mensch": 0.01, "kennzahlen": {},
                                  "roh": {"anteil_lange_saetze": 0.05, "satzlaenge_mittel": 18.5, "anteil_mittlere_saetze": 0.62}}]}
        c = coache_still(text, verlauf, 40, roh=True)
        letzter = analyse.analysiere_text(text)["saetze"][-1]
        # der längste Satz des Texts: ohne Zitatschutz wäre er der erste Teilen-Kandidat
        self.assertEqual(letzter["woerter"], max(s["woerter"] for s in analyse.analysiere_text(text)["saetze"]))
        self.assertTrue([h for h in c["hinweise_roh"] if h["typ"] == "teilen"])
        self.assertFalse([h for h in c["hinweise_roh"] if h["satz"] == letzter["nr"] and h["typ"] == "teilen"])

    def test_synonym_cluster_ohne_verbpartikel(self):
        texte = ["Die Ausbildung im Betrieb dauert drei Jahre.", "Die Ausgestaltung der Verträge ist frei.",
                 "Viele junge Leute beginnen eine Ausbildung.", "Die Ausbildung endet mit einer Prüfung.",
                 "Die Fortbildung ist freiwillig.", "Die Fortsetzung der Reihe folgt.", "Eine Fortbildung kostet Geld.",
                 "Die Fortbildung wird gefördert.", "Die Preissetzung ist dynamisch.", "Die Preisgestaltung folgt der Nachfrage.",
                 "Die Preissetzung ändert sich stündlich.", "Die Preissetzung bleibt umstritten."]
        saetze = [{"nr": i + 1, "absatz": 1, "text": t} for i, t in enumerate(texte)]
        cluster = [[w for w, _ in c["varianten"]] for c in coach.synonym_cluster(saetze, {})]
        self.assertEqual(cluster, [["Preissetzung", "Preisgestaltung"]])  # „Aus-“/„Fort-“ sind kein Bestimmungswort

    def test_keine_anknuepfung_am_zitatanfang(self):
        zus = ("Die Berichtspflicht verändert die Arbeit der Controller in mittelständischen Unternehmen grundlegend und dauerhaft. "
               "„Ihre Rolle wandelt sich vom Zahlenlieferanten zum Gestalter der Strategie im ganzen Betrieb“, schreibt Weber (2022). "
               "Die Unternehmen planen deshalb neue Stellen im Controlling und in der Nachhaltigkeitsabteilung. "
               "„Sie müssen Daten aus allen Bereichen zusammenführen und prüfen“, ergänzt ein befragter Leiter.")
        text = zus + "\n\n" + KI_TEXT.split("\n\n", 1)[1]
        c = coache_still(text, None, 40, roh=True)
        S = analyse.analysiere_text(text)["saetze"]
        zitat_nr = {s["nr"] for s in S[:4] if s["text"].startswith("„")}
        self.assertEqual(len(zitat_nr), 2)
        self.assertFalse([h for h in c["hinweise_roh"] if h["satz"] in zitat_nr and h["typ"] in ("anknuepfung", "kein_bezug")])


class ErsetzbarEndeZuEnde(unittest.TestCase):
    """Vereinbarung Coach ↔ Inhaltscheck: coach.py --verlauf schreibt „ersetzbar“, inhalt_check.py --verlauf liest es."""

    def test_floskel_nur_ausloeser_nicht_platzhalter(self):
        muster = analyse.lade_muster()
        faelle = {"Die Planung betrifft sowohl die Kostenstruktur der Abteilungen als auch die Budgets der Projekte.":
                  ({"sowohl"}, {"Kostenstruktur", "Abteilungen"}),
                  "Der Kommunikation kommt in diesem Prozess eine zentrale Rolle zu.": ({"zentrale", "Rolle"}, {"Prozess"}),
                  "Eine solche Sicht greift jedoch zu kurz.": ({"greift"}, {"Sicht"})}
        for satz_, (ja, nein) in faelle.items():
            treffer = analyse.muster_treffer(satz_, muster)
            self.assertTrue(treffer, satz_)
            kopf = {w for a, e, _g, mu, _f, _v in treffer for w in coach.floskel_kopfwoerter(satz_, a, e, mu["_re"])}
            self.assertLessEqual(ja, kopf, satz_)
            self.assertFalse(kopf & nein, satz_)

    def test_coach_meldet_keine_platzhalter_als_ersetzbar(self):
        text = ("## Planung im Betrieb\n\n"
                "Darüber hinaus trägt eine klare Planung maßgeblich zur Zufriedenheit im Team bei. Dies verdeutlicht, dass Planung "
                "mehr ist als Kontrolle. Der Kommunikation kommt in diesem Prozess eine zentrale Rolle zu. Insgesamt zeigt sich, "
                "dass die Beschäftigten ihre Leitung gut bewerten.\n\n"
                "Vor diesem Hintergrund ermöglicht es eine offene Kultur, Konflikte früh zu erkennen. Eine solche Sicht greift "
                "jedoch zu kurz. Die Kostenstruktur betrifft sowohl die Kostenstruktur der Abteilungen als auch die Budgets der "
                "Projekte. Mehr Planung führt nicht zwangsläufig zu besseren Ergebnissen. Darüber hinaus ist die Kostenstruktur "
                "keineswegs starr.\n")
        c = coache_still(text, None, 60, roh=True)
        floskeln = [h for h in c["hinweise_roh"] if h["typ"] == "floskel"]
        self.assertTrue(any("Rolle" in h["fund"] and {"zentrale", "rolle"} <= set(h["ersetzbar"]) for h in floskeln))
        self.assertTrue(any("sowohl" in h["fund"] for h in floskeln))
        alle = {w for h in floskeln for w in h["ersetzbar"]}
        self.assertFalse(alle & {"kostenstruktur", "abteilungen", "prozess", "sicht", "kultur", "budgets"})

    def test_coach_schreibt_inhaltscheck_liest(self):
        import inhalt_check
        neu = (KI_TEXT.replace("die Konsumenten vergleichen", "sie vergleichen").replace("Die Konsumenten nutzen", "Sie nutzen")
               .replace("Viele Verbraucher", "Viele Kunden").replace("Arbeitgebermarke", "Marke")
               .replace(" (Müller & Schmidt, 2021)", ""))
        with tempfile.TemporaryDirectory() as d:
            alt_p, neu_p, v_p = (os.path.join(d, n) for n in ("t.md", "t.neu.md", "t.coach.json"))
            for pfad, inhalt in ((alt_p, KI_TEXT), (neu_p, neu)):
                with open(pfad, "w", encoding="utf-8") as f:
                    f.write(inhalt)
            with redirect_stdout(io.StringIO()):
                coach.main([alt_p, "--verlauf", v_p, "--max-hinweise", "60"])
            with open(v_p, encoding="utf-8") as f:
                ersetzbar = json.load(f)["messungen"][-1]["ersetzbar"]
            self.assertIn("konsumenten", ersetzbar)  # Synonym-Variante aus dem Cluster-Hinweis
            self.assertNotIn("arbeitgebermarke", ersetzbar)

            def pruefen(*extra):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    inhalt_check.main([alt_p, neu_p, "--format", "json", *extra])
                r = json.loads(buf.getvalue())
                weg = " ".join(w["wert"] for w in r["warnungen"] if w["typ"] == "Begriff verschwunden")
                return r, weg

            r0, weg0 = pruefen()
            r1, weg1 = pruefen("--verlauf", v_p)
        self.assertIn("konsument", weg0)
        self.assertNotIn("konsument", weg1)  # vom Coach empfohlen: kein Verlust
        self.assertIn("konsumenten", r1["nicht_gemeldet"])
        self.assertIn("arbeitgeb", weg1)  # echter Begriffsverlust bleibt
        self.assertEqual([h["wert"] for h in r0["harte_verluste"]], [h["wert"] for h in r1["harte_verluste"]])
        self.assertIn("Müller & Schmidt, 2021", [h["wert"] for h in r1["harte_verluste"]])


if __name__ == "__main__":
    unittest.main()
