"""Tests für v7.1, Auftrag B (Inhaltscheck und Messseite):

1. inhalt_check grenzt wörtliche Zitate ab wie coach.zitat_masken (Stapel für verschachtelte Zitate, Richtung der Guillemets
   nach dem ersten im Absatz, Belegklammer hinter dem Schlusszeichen, gerades " als Schluss von „). Regressionsfall fhws-1919
   Absatz 1: „Lehrenden“ → „Dozenten“ in S7 und S11 (eigener Text) ist kein Zitatverlust, eine Änderung in S10 (im Zitat)
   schon. Die eigene Spannenfunktion wird gegen coach.zitat_masken auf denselben Sätzen verglichen.
2. inhalt_check nennt neben der eigenen Wortzahl die Zählung des Coaches (ohne Überschriften, Quellenverweise, Fußnoten).
3. „Abkürzung: ESRS“: eine Abkürzung, die schon im Original steht und nur öfter genannt wird (Nomen beim Teilen wiederholt),
   ist kein neuer Inhalt – auch wenn der Coach-Verlauf unter "erwartet" andere Nomen des Satzes führt.
4. analyse.verklebte_stellen: ein Komma als entstelltes öffnendes ‚ („als,Bottom up'-Faktoren“) ist keine Verklebung; der
   Genitiv-Apostroph („Kreyenfelds,Tölkes/Diewalds und Niehaus‘ wertvolle …“) hebt eine echte Verklebung nicht auf.

python3 -m unittest discover -s tests
"""
import os
import sys
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
import inhalt_check  # noqa: E402
from test_coach_v7 import FHWS_ABSATZ  # noqa: E402

FHWS_KORPUS = os.path.join(REPO, "kalibrierung", "korpus", "mensch", "opus-fh", "fhws-1919.txt")


def saetze_analyse(text):
    """Sätze wie im Coach (analyse.analysiere_text: Nummer, Absatz, bereinigter Text)."""
    return [{"nr": s["nr"], "absatz": s["absatz"], "text": s["text"]} for s in analyse.analysiere_text(text, [])["saetze"]]


def saetze_aus(absaetze):
    """[[Satz, …], …] → Satz-Dicts wie analyse.py sie liefert."""
    out = []
    for ai, liste in enumerate(absaetze, 1):
        for s in liste:
            out.append({"nr": len(out) + 1, "absatz": ai, "text": s})
    return out


def masken_inhalt_check(saetze):
    """Zitatmasken je Satz wie coach.zitat_masken, aber mit den Spannen von inhalt_check.zitat_spannen_absatz."""
    absaetze = {}
    for s in saetze:
        absaetze.setdefault(s["absatz"], []).append(s)
    masken = {}
    for liste in absaetze.values():
        text, grenzen, pos = "", [], 0
        for s in liste:
            grenzen.append((pos, pos + len(s["text"])))
            text += s["text"] + "\n"
            pos = len(text)
        zeichen = list(text)
        for a, _schluss, e in inhalt_check.zitat_spannen_absatz(text, grenzen):
            for i in range(a, e):
                if zeichen[i] != "\n":
                    zeichen[i] = coach.MASKE
        maske = "".join(zeichen)
        for s, (a, e) in zip(liste, grenzen):
            masken[s["nr"]] = coach.QUELLE_KLAMMER_RE.sub(lambda x: coach.MASKE * len(x.group(0)), maske[a:e])
    return masken


def harte_zitate(res):
    return [e for e in res["harte_verluste"] + res["erfindungen"] if e["typ"] == "Wörtliches Zitat"]


# Absätze als Satzlisten: alle Regeln von coach.zitat_masken
FAELLE = [
    [["Er sagt: »Das ist »so« richtig.", "Und weiter.«", "Danach eigener Text."]],                 # verschachtelt, 2 Sätze
    [["Sie nennt das «schnell, aber teuer».", "Er widerspricht."]],                                # Schweizer Richtung
    [["Text mit «Swiss» zuerst und dann »German« falsch herum.", "Ende."]],                        # erstes Guillemet zählt
    [['Er nennt es „eine reine Formsache" und lacht.', "Sie sagt „das stimmt so nicht“."]],         # „…" gemischt
    [["Der Bericht spricht von „Zeitenwende.", "Danach nichts mehr."]],                            # nie geschlossen
    [['Die Skala reicht bis 5" und mehr.', "Sie sagt „ja“ dazu."]],                                # Zollzeichen
    [["„Das war knapp“ (ebd., S. 9) – so die Leitung.", "Weiter geht es."]],                       # Belegklammer ( )
    [["„Wir arbeiten gern hier“ [Interview 3, Absatz 8] Die Befragten bestätigen das."]],          # Belegklammer [ ]
    [["„Gut so“ (vor allem morgens) sagen viele.", "Mehr nicht."]],                                # Klammer ohne Beleg
    [["Er schreibt ›kurz‹ und «lang».", "»Mehr dazu."]],
    [["„Erster Satz.", "Zweiter Satz.“ Dann eigener Text (Müller 2019, S. 3)."]],                  # über Satzgrenze
    [["Sie sagt „das ist ‚so‘ gemeint“ und geht."]],
    [["“Autokorrektur“ ist für den Coach kein Zitat.", "Aber “so” schon."]],
    [['Er sagt „erstens“ und „zweitens".', "Dann „drittens“."]],
    [["„Offen bleibt das hier.", "Und »das« auch."], ["Neuer Absatz mit „Zitat“."]],
    [['Er sagt "ja" und "nein" und "vielleicht.', "Dann Schluss."]],
]


class ZitatWieCoach(unittest.TestCase):
    def test_spannen_gleich_coach_masken(self):
        for i, absaetze in enumerate(FAELLE):
            saetze = saetze_aus(absaetze)
            with self.subTest(fall=i, text=absaetze):
                self.assertEqual(masken_inhalt_check(saetze), coach.zitat_masken(saetze))

    def test_spannen_gleich_coach_masken_fhws(self):
        saetze = saetze_analyse(FHWS_ABSATZ)
        masken = coach.zitat_masken(saetze)
        self.assertTrue(any(coach.MASKE in m for m in masken.values()))
        self.assertEqual(masken_inhalt_check(saetze), masken)

    @unittest.skipUnless(os.path.exists(FHWS_KORPUS), "Korpus fehlt")
    def test_spannen_gleich_coach_masken_ganzes_korpusdokument(self):
        with open(FHWS_KORPUS, encoding="utf-8") as f:
            saetze = saetze_analyse(f.read())
        self.assertEqual(masken_inhalt_check(saetze), coach.zitat_masken(saetze))

    def test_beleg_ende_gleich_coach(self):
        for text in ("„x“ (ebd., S. 9) weiter", "„x“ [Interview 3] weiter", "„x“ (vor allem) weiter", "„x“\n(vgl. ders.) y",
                     "„x“ [Mergner et al. (2015), S. 9)] y", "„x“ (" + "a" * 130 + " 3) y", "„x“"):
            with self.subTest(text=text):
                i = text.index("“") + 1
                self.assertEqual(inhalt_check._beleg_ende(text, i), coach._beleg_ende(text, i))

    # Regressionsfall fhws-1919 Absatz 1 (v7-Prüfung echte Abschnitte): S7 „überwiegend die Lehrenden“ und S11 „Aufgabe der
    # Lehrenden“ sind eigener Text, S9–S10 ein Interviewzitat mit Belegklammer
    def test_fhws_lehrende_dozenten_kein_zitatverlust(self):
        neu = FHWS_ABSATZ.replace("überwiegend die Lehrenden", "überwiegend die Dozenten") \
            .replace("Aufgabe der Lehrenden", "Aufgabe der Dozenten")
        self.assertNotEqual(neu, FHWS_ABSATZ)
        res = inhalt_check.pruefe(FHWS_ABSATZ, neu)
        self.assertEqual(harte_zitate(res), [])
        self.assertTrue(res["ok"], res["harte_verluste"] + res["erfindungen"])

    def test_fhws_aenderung_im_zitat_bleibt_harter_verlust(self):
        neu = FHWS_ABSATZ.replace("sollten den Studierenden ermöglichen", "sollten den Studenten ermöglichen")
        self.assertNotEqual(neu, FHWS_ABSATZ)
        res = inhalt_check.pruefe(FHWS_ABSATZ, neu)
        self.assertFalse(res["ok"])
        verlust = [e for e in res["harte_verluste"] if e["typ"] == "Wörtliches Zitat"]
        self.assertEqual(len(verlust), 1)
        self.assertTrue(verlust[0]["wert"].startswith("Und so ist es ganz klar"))
        # auch im inneren Zitat des verschachtelten ersten Interviewzitats
        neu = FHWS_ABSATZ.replace("ich habe meine Ziele erreicht", "ich habe mein Ziel erreicht")
        res = inhalt_check.pruefe(FHWS_ABSATZ, neu)
        self.assertTrue([e for e in res["harte_verluste"] if e["wert"].startswith("Wie ich Studienerfolg")])

    def test_fhws_zitate_sind_die_interviewstellen(self):
        werte = [z["wert"] for z in inhalt_check.zitat_funde(FHWS_ABSATZ)]
        self.assertEqual(len(werte), 2)
        self.assertTrue(werte[0].startswith("Wie ich Studienerfolg") and werte[0].endswith("Genau (unv.) Ziele"))
        self.assertIn("»Jawoll, ich habe meine Ziele erreicht«", werte[0])     # das innere Zitat gehört zum äußeren
        self.assertTrue(werte[1].startswith("Und so ist es") and werte[1].endswith("aktuelle Probleme lösen"))
        # die Belegklammer gehört zur Spanne (Floskel-Maske), nicht zum verglichenen Wortlaut
        maske = inhalt_check._ohne_zitate(FHWS_ABSATZ)
        self.assertNotIn("Absolvent*in, Absatz 12", maske)
        self.assertNotIn("Lehrende, Absatz 8", maske)
        self.assertIn("überwiegend die Lehrenden", maske)
        self.assertIn("Aufgabe der Lehrenden", maske)

    @unittest.skipUnless(os.path.exists(FHWS_KORPUS), "Korpus fehlt")
    def test_fhws_korpusabsatz(self):
        with open(FHWS_KORPUS, encoding="utf-8") as f:
            absatz = next(z for z in f.read().split("\n") if "»Jawoll" in z)
        neu = absatz.replace("überwiegend die Lehrenden", "überwiegend die Dozenten").replace("Aufgabe der Lehrenden",
                                                                                              "Aufgabe der Dozenten")
        self.assertTrue(inhalt_check.pruefe(absatz, neu)["ok"])
        neu = absatz.replace("sollten den Studierenden ermöglichen", "sollten den Studenten ermöglichen")
        self.assertTrue(harte_zitate(inhalt_check.pruefe(absatz, neu)))

    def test_gerades_anfuehrungszeichen_schliesst_tiefes(self):
        t = 'Er nennt es „eine ganz reine Formsache" und lacht. Sie sagt „das stimmt so leider nicht“ und geht.'
        self.assertEqual([z["wert"] for z in inhalt_check.zitat_funde(t)],
                         ["eine ganz reine Formsache", "das stimmt so leider nicht"])

    def test_schweizer_guillemets_und_eigener_text_dazwischen(self):
        # früher paarte »…« und «…» unabhängig: « … » zwischen zwei deutschen Zitaten galt als Zitat
        t = ("»Das erste Zitat ist hier.« Eigener Text der Autorin mit vielen Wörtern. »Das zweite Zitat folgt.«\n\n"
             "«Ein Schweizer Zitat steht da.» Danach eigener Text.")
        werte = [z["wert"] for z in inhalt_check.zitat_funde(t)]
        self.assertEqual(werte, ["Das erste Zitat ist hier", "Das zweite Zitat folgt", "Ein Schweizer Zitat steht da"])
        neu = t.replace("Eigener Text der Autorin", "Eigener Text des Autors")
        self.assertTrue(inhalt_check.pruefe(t, neu)["ok"])

    def test_nie_geschlossen_maskiert_aber_nicht_verglichen(self):
        t = "Der Bericht spricht von „einer echten Zeitenwende in der Politik. Danach folgt eigener Text."
        self.assertEqual(inhalt_check.zitat_funde(t), [])
        maske = inhalt_check._ohne_zitate(t)
        self.assertNotIn("Zeitenwende", maske)          # bis zum Satzende geschützt (Floskeln), wie im Coach
        self.assertIn("Danach folgt eigener Text", maske)
        self.assertTrue(inhalt_check.pruefe(t, t.replace("Zeitenwende in", "Zeitenwende für"))["ok"])

    def test_zusatz_autokorrektur_und_einfache_anfuehrung(self):
        # “…“ und ‚…‘ erkennt der Coach nicht als Zitat; inhalt_check vergleicht sie weiter (außerhalb der Coach-Spannen)
        self.assertEqual(list(inhalt_check.woertlich("“trifft gar nicht zu“")), ["trifft gar nicht zu"])
        self.assertEqual(list(inhalt_check.woertlich("Er nennt es ‚eine Frage der Zeit‘ und geht.")), ["eine Frage der Zeit"])
        # innerhalb eines „…“ gehört ‚…‘ zum äußeren Zitat
        self.assertEqual(list(inhalt_check.woertlich("Sie sagt „das ist ‚so‘ gemeint“ und geht.")),
                         ["das ist ‚so‘ gemeint"])

    def test_zitat_ueber_absatzgrenze_nicht(self):
        t = "Er sagt „das hier ist offen\n\nund das ist ein neuer Absatz“ mit mehr Text."
        self.assertEqual(inhalt_check.zitat_funde(t), [])

    def test_absatzgrenze_auch_mit_crlf(self):
        # Windows-Zeilenenden: die Richtung der Guillemets gilt weiter je Absatz
        t = "»Erstes Zitat steht hier.« Text.\r\n\r\n«Schweizer Zitat steht hier.» Mehr."
        self.assertEqual([z["wert"] for z in inhalt_check.zitat_funde(t)],
                         ["Erstes Zitat steht hier", "Schweizer Zitat steht hier"])

    def test_ueberschrift_eigener_absatz(self):
        # die Überschrift bestimmt nicht die Guillemet-Richtung des folgenden Absatzes
        t = "## Teil «A»\n»Das ist ein langes Zitat hier.« Eigener Text."
        self.assertEqual([z["wert"] for z in inhalt_check.zitat_funde(t)], ["A", "Das ist ein langes Zitat hier"])


class WortzahlWieCoach(unittest.TestCase):
    TEXT = ("## 2 Forschungsstand\n\n"
            "Müller (2019, S. 12) zeigt, dass 45 % der Betriebe zögern. Die Gründe sind vielfältig (Schmidt 2020; Weber et al. "
            "2021). Laut einer Befragung fehlen vor allem Fachkräfte.[^1] Thiel et al. [2006, 2008] beschreiben das Modell.\n\n"
            "»Wir haben keine Zeit dafür« [Interview 3, Absatz 8] Das sagen viele Befragte.\n\n"
            "[^1]: Eigene Erhebung.\n")

    def test_zaehlung_wie_analyse_info(self):
        n = inhalt_check.woerter_wie_coach(self.TEXT)
        erg, _bew = analyse.analysiere_und_bewerte(self.TEXT, analyse.lade_muster(), analyse.lade_baselines())
        self.assertEqual(n, erg["info"]["woerter"])
        self.assertLess(n, len(inhalt_check.WORT_RE.findall(self.TEXT)))   # ohne Überschrift und Verweise weniger

    def test_bericht_nennt_beide_zahlen(self):
        neu = self.TEXT.replace("vor allem Fachkräfte", "besonders Fachkräfte")
        res = inhalt_check.pruefe(self.TEXT, neu)
        k = res["kennzahlen"]
        self.assertEqual(k["woerter_coach_original"], inhalt_check.woerter_wie_coach(self.TEXT))
        self.assertEqual(k["woerter_coach_neu"], inhalt_check.woerter_wie_coach(neu))
        zeile = inhalt_check.bericht(res).split("\n")[2]
        self.assertIn(f"Wörter: {k['woerter_original']} → {k['woerter_neu']}", zeile)
        self.assertIn(f"wie im Coach gezählt (ohne Überschriften, Quellenverweise und Fußnoten): "
                      f"{k['woerter_coach_original']} → {k['woerter_coach_neu']}", zeile)

    def test_ohne_analyse_nur_eigene_zahl(self):
        with mock.patch.dict(inhalt_check._CACHE, {"analyse": None}):
            res = inhalt_check.pruefe(self.TEXT, self.TEXT)
            self.assertIsNone(res["kennzahlen"]["woerter_coach_original"])
            self.assertNotIn("wie im Coach gezählt", inhalt_check.bericht(res))


class AbkuerzungSchonImOriginal(unittest.TestCase):
    # CSRD (Coach-Evaluation v7, vierter gleicher Fehlalarm): Teilen am Relativsatz, das Bezugswort ist die Abkürzung; der
    # Verlauf erwartete die ersten Nomen des Satzes („richtlinie“, „anwendung“, „european“), nicht „esrs“
    ALT = ("Die CSRD gilt seit 2024. Inhaltlich verpflichtet die Richtlinie zur Anwendung einheitlicher European Sustainability "
           "Reporting Standards (ESRS), die mit der Delegierten Verordnung (EU) 2023/2772 verabschiedet wurden. Angesichts der "
           "Kritik an der Komplexität der ESRS legte die Kommission 2025 das Omnibus-Paket vor.")
    NEU = ("Die CSRD gilt seit 2024. Inhaltlich verpflichtet die Richtlinie zur Anwendung einheitlicher European Sustainability "
           "Reporting Standards (ESRS). Die ESRS wurden mit der Delegierten Verordnung (EU) 2023/2772 verabschiedet. Angesichts "
           "der Kritik an der Komplexität der ESRS legte die Kommission 2025 das Omnibus-Paket vor.")
    ERWARTET = {"anwendung", "arbeit", "ca.", "directive", "european", "richtlinie"}   # wie in eval-csrd.coach.json

    def abk(self, res):
        return [w for w in res["warnungen"] if w["typ"] == "Abkürzung"]

    def test_esrs_mit_coach_verlauf_kein_alarm(self):
        self.assertEqual(self.abk(inhalt_check.pruefe(self.ALT, self.NEU, erwartet=self.ERWARTET)), [])
        self.assertEqual(self.abk(inhalt_check.pruefe(self.ALT, self.NEU)), [])

    def test_ganz_neue_abkuerzung_bleibt_gemeldet(self):
        res = inhalt_check.pruefe(self.ALT, self.NEU.replace("die Kommission", "die Kommission (EFRAG)"),
                                  erwartet=self.ERWARTET)
        self.assertEqual([w["wert"] for w in self.abk(res)], ["EFRAG"])
        self.assertIn("im Original nicht enthalten", self.abk(res)[0]["hinweis"])

    def test_fehlende_abkuerzung_mit_einordnung(self):
        res = inhalt_check.pruefe(self.ALT, self.NEU.replace("Die CSRD gilt", "Die Richtlinie gilt"))
        self.assertEqual([(w["wert"], w["hinweis"].split(" – ")[0]) for w in self.abk(res)],
                         [("CSRD", "fehlt in der Überarbeitung ganz")])
        res = inhalt_check.pruefe(self.ALT, self.ALT.replace("Komplexität der ESRS", "Komplexität der Standards"))
        self.assertEqual([(w["wert"], w["hinweis"].split(" – ")[0]) for w in self.abk(res)], [("ESRS", "im Original 2×, jetzt 1×")])
        self.assertIn("Abkürzung: ESRS – im Original 2×, jetzt 1×", inhalt_check.bericht(res))


class VerklebtKommaAlsAnfuehrung(unittest.TestCase):
    def stellen(self, text):
        return [x["stelle"] for x in analyse.verklebte_stellen([{"nr": 1, "text": text}])]

    def test_komma_als_oeffnendes_anfuehrungszeichen(self):
        # haw-10626 (echter Text, 4 Fehlalarme in v7) und die übrigen Korpusfälle derselben Art
        for text in ("So werden die technischen Faktoren als,Bottom up'-Faktoren bezeichnet.",
                     "Die Gruppe der kognitiven Faktoren von Seiten des Lesers,Top-down'-Faktoren genannt.",
                     "Zusammenhänge zwischen den,Bottom up'-Faktoren und den,Top-down'-Faktoren.",
                     "Trotz Bemühungen – wie zum Beispiel des Netzwerkes,People First‘ – erschwert.",
                     "Im Folgenden wird der Terminus,Menschen mit Behinderungen‘ verwendet.",
                     "Andere Bereiche, wie zum Beispiel,Zeit‘ oder,Beziehungsaufbau‘, werden kaum ausgefüllt.",
                     "Er hat den Charakter eines,Wachstumsbedarfs’, sondern ist vor allem,Erneuerungs- und Anpassungsbedarf’."):
            with self.subTest(text=text):
                self.assertEqual(self.stellen(text), [])

    def test_echte_verklebungen_bleiben(self):
        faelle = {
            # Genitiv-Apostroph vor einem Wort ist kein schließendes Anführungszeichen (ssoar-36849)
            "Zwar geben die Studien Kreyenfelds,Tölkes/Diewalds und Niehaus‘ wertvolle Erkenntnisse.": ["Kreyenfelds,Tölkes/Diewalds"],
            "Das zeigt die Note,Wie sich zeigt, ist das so.": ["Note,Wie"],
            "Er sagte,Peter's Buch sei gut.": ["sagte,Peter's"],                       # Apostroph vor Buchstabe
            "Sie nennt es,Lean Management in der öffentlichen Verwaltung' und meint anderes.": ["es,Lean"],  # > 4 Wörter
            "Das Modell,wiesichdieHZB-Note,dieStudienwahlmotive auswirkt.": ["Modell,wiesichdieHZB-Note,dieStudienwahlmotive"],
            "Die Merkmale werden erfasst.Merkmale des Studiums folgen.": ["erfasst.Merkmale"],
        }
        for text, erwartet in faelle.items():
            with self.subTest(text=text):
                self.assertEqual(self.stellen(text), erwartet)

    def test_keine_warnung_in_der_analyse(self):
        text = ("Die Leseeffizienz hängt von zwei Faktorengruppen ab. So werden die technischen Faktoren als,Bottom up'-Faktoren "
                "bezeichnet, während die kognitiven Faktoren von Seiten des Lesers,Top-down'-Faktoren genannt werden.")
        info = analyse.analysiere_text(text, [])["info"]
        self.assertEqual(info["verklebt"], [])
        self.assertFalse([w for w in info["warnungen"] if "verklebt" in w])


if __name__ == "__main__":
    unittest.main()
