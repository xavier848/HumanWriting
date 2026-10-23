"""Tests für die KI-Muster in ki_muster.json: Regex (Positiv-/Negativsätze), Abgrenzung der „sondern“-Muster,
Strohmann-Muster und Ersatzstrategien ohne Inhaltsverlust.

Alle Beispielsätze sind für die Tests formuliert (keine Korpustexte)."""
import json
import os
import re
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
import analyse  # noqa: E402

MUSTER_PFAD = os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "data", "ki_muster.json")

ADDITIV = [
    "Das betrifft nicht nur große Konzerne, sondern auch kleine Betriebe.",
    "Die Wirkung hängt nicht allein vom Budget ab, sondern von der Führung.",
    "Die Daten wurden nicht bloß gesammelt, sondern ausgewertet und veröffentlicht.",
    "Die Kosten steigen nicht lediglich kurzfristig, sondern dauerhaft.",
    "Viele arbeiten nicht mehr nur im Büro, sondern auch zu Hause.",
    "Die Reform senkt nicht nur die Kosten, sondern verkürzt auch die Wartezeiten.",
    "Die Zuständigkeit richtet sich nicht mehr allein nach Mehrheiten, sondern nach Argumenten.",
    "Der Verlag ist nicht einfach nur Vermittler, sondern auch Händler.",
]
KONTRAST = [
    "Entscheidend ist nicht die Technik, sondern die Organisation.",
    "Das Problem liegt nicht im fehlenden Budget, sondern in der Planung.",
    "Es handelt sich um keine Modeerscheinung, sondern um einen dauerhaften Wandel.",
    "Die Befragten nannten nicht die Bezahlung, sondern das Betriebsklima.",
]

# je Muster ≥ 3 Positiv- und ≥ 3 Negativsätze
MUSTER_SAETZE = {
    "nicht_x_sondern": (KONTRAST, ADDITIV + ["Die Frist war nicht lang genug, um alle Betriebe zu befragen."]),
    "nicht_nur_sondern": (ADDITIV, KONTRAST + ["Das gilt nicht nur für Banken. Sondern dafür fehlen Daten.",
                                               "Die Teilnahme ist nicht nur freiwillig.",
                                               "Die Befragten kamen nicht allein."]),
    "greift_zu_kurz": (
        ["Diese Erklärung greift jedoch zu kurz.",
         "Ansätze, die nur auf Anreize setzen, greifen zu kurz.",
         "Damit wird deutlich, dass eine rein technische Sicht zu kurz greift.",
         "Eine solche Deutung wäre zu kurz gegriffen."],
        ["Viele Betriebe greifen zu kurzfristigen Maßnahmen.",
         "Die Frist war zu kurz, um alle Daten zu erheben.",
         "Die Teilnehmer griffen kurz auf ihre Notizen zurück.",
         "Das Unternehmen greift auf kurze Lieferwege zurück.",
         # Nomen „Griff/Griffe“ (Werkzeug), kein Verb
         "Die Griffe der Werkzeuge sind zu kurz.",
         "Der Griff ist für kleine Hände zu kurz."]),
    "strohmann_aufbau": (
        ["Bei näherer Betrachtung zeigt sich jedoch ein anderes Bild.",
         "Naheliegend wäre es, beide Verfahren zu kombinieren.",
         "Die naheliegende Erklärung, nämlich höhere Löhne, reicht nicht aus.",
         "Bei genauerer Betrachtung erweist sich der Effekt als gering."],
        ["Bei näherer Betrachtung der Daten fällt eine Lücke auf.",
         "Bei genauerer Betrachtung von Tabelle 3 wird der Unterschied sichtbar.",
         "Es ist naheliegend, dass kleine Betriebe weniger investieren.",
         "Die Betrachtung beschränkt sich auf das Jahr 2020.",
         # mit Genitivobjekt: beschreibend, keine aufgebaute Gegenposition
         "Bei näherer Betrachtung eines Einzelfalls fällt eine Lücke auf.",
         "Bei genauerer Betrachtung einzelner Branchen zeigen sich Unterschiede."]),
    "einwand_formel": (
        ["Dem lässt sich entgegenhalten, dass die Kosten sinken.",
         "Gegen diese Sicht lässt sich allerdings einwenden, dass die Stichprobe klein ist.",
         "Man könnte einwenden, dass die Daten veraltet sind.",
         "Dem kann entgegengehalten werden, dass die Preise gestiegen sind."],
        ["Die Gewerkschaft hat Einwände gegen den Plan erhoben.",
         "Der Betriebsrat wandte sich gegen die Kürzungen.",
         "Die Befragten konnten keine Einwände nennen.",
         "Kritiker halten dem Konzept seine hohen Kosten entgegen."]),
    "keineswegs": (
        ["Das ist keineswegs selbstverständlich.",
         "Die Ergebnisse sind keineswegs eindeutig.",
         "Keineswegs alle Betriebe profitieren davon."],
        ["Das ist nicht selbstverständlich.",
         "Die Ergebnisse sind keinesfalls eindeutig.",
         "Keine der Firmen hat geantwortet."]),
    "nicht_zwangslaeufig": (
        ["Mehr Daten führen nicht zwangsläufig zu besseren Entscheidungen.",
         "Ein Abschluss ist nicht zwingend erforderlich.",
         "Das bedeutet nicht zwangsläufig, dass die Kosten steigen."],
        ["Mehr Daten führen nicht unbedingt zu besseren Entscheidungen.",
         "Die Folgen waren zwangsläufig.",
         "Die Regel ist zwingend einzuhalten."]),
    # v7: nachgestellte Gegenfolie (Umstellung von „nicht X, sondern Y“)
    "gegenfolie_nachgestellt": (
        ["Agile Führungskräfte verstehen sich als Unterstützer und nicht als Kontrollinstanz.",
         "Das Problem liegt in der Planung und nicht im fehlenden Budget.",
         "Entscheidend ist die Organisation und nicht das Werkzeug.",
         "Die Befragten nannten das Betriebsklima statt der Bezahlung.",
         "Viele Betriebe bilden eigene Fachkräfte aus, statt sie auf dem Markt zu suchen.",
         "Anstatt die Preise zu senken, erhöhte das Unternehmen die Werbeausgaben.",
         "Die Reform senkt die Kosten, nicht aber die Wartezeiten.",
         "Die Daten erfassen den Bestand, nicht jedoch die Zugänge."],
        [  # „statt“ als Verbpartikel (stattfinden), vor Zahlen, in Komposita
         "Die Befragung fand im Mai 2020 statt.",
         "Die Interviews finden in Einzelgesprächen statt und dauern eine Stunde.",
         "Die Treffen fanden statt, als die Krise begann.",
         "Der Anteil stieg auf 52 % statt 45 % im Vorjahr.",
         "Stattdessen wählten die Betriebe eine andere Lösung.",
         "Die Werkstatt liegt am Stadtrand.",
         # „und nicht“ ohne parallelen Bau, „, nicht“ ohne „aber/jedoch“ (bei Menschen genauso häufig)
         "Die Daten sind unvollständig und nicht repräsentativ.",
         "Die Stichprobe ist klein, nicht repräsentativ und veraltet.",
         "Die Kosten steigen und nicht nur die Preise.",
         "Die Kosten steigen, nicht die Erlöse."]),
}

# Ersatz, der Inhalt ohne Bedingung streicht („Streichen.“, „… oder streichen.“, „oft ersatzlos streichen“)
UNBEDINGT_STREICHEN = re.compile(
    r"(?:^|[.;:]\s+)(?:meist\s+|oft\s+)?(?:ersatzlos\s+)?streichen\s*(?:[.;]|$)"
    r"|oder\s+(?:ersatzlos\s+)?streichen\s*[.)]?\s*$|oft\s+ersatzlos\s+streichen", re.IGNORECASE)
# Muster, deren Fund Inhalt trägt (Gradangabe, Rangfolge, Quellenaussage, Einschränkung, Dauer, Bezug)
INHALT_TRAGEND = ["massgeblich", "kern_zentral", "schluessel", "nicht_x_sondern", "nicht_nur_sondern", "dies_verdeutlicht",
                  "zusammenhang_hintergrund", "darueber_hinaus", "modewort_adjektiv", "nachhaltig_wort", "insgesamt_zeigt",
                  "nicht_zwangslaeufig", "keineswegs", "greift_zu_kurz", "strohmann_aufbau", "einwand_formel", "hierbei_dabei",
                  "gegenfolie_nachgestellt"]
NEUE_MUSTER = ["greift_zu_kurz", "strohmann_aufbau", "einwand_formel", "keineswegs", "nicht_zwangslaeufig",
               "gegenfolie_nachgestellt"]


def lade_json():
    with open(MUSTER_PFAD, encoding="utf-8") as f:
        return json.load(f)


class Aufbau(unittest.TestCase):
    def test_felder_und_eindeutige_ids(self):
        muster = lade_json()["muster"]
        ids = [m["id"] for m in muster]
        self.assertEqual(len(ids), len(set(ids)))
        for m in muster:
            with self.subTest(muster=m["id"]):
                for feld in ("label", "kategorie", "regex", "ersatz"):
                    self.assertTrue(str(m.get(feld, "")).strip(), feld)
                re.compile(m["regex"])
                # Gewicht und Raten stammen aus kalibriere.py (nicht von Hand)
                for feld in ("gewicht", "rate_mensch_pro_1000", "rate_ki_pro_1000", "verhaeltnis_ki_mensch"):
                    self.assertIn(feld, m)

    def test_neue_muster_vorhanden(self):
        ids = {m["id"] for m in lade_json()["muster"]}
        for mid in NEUE_MUSTER:
            self.assertIn(mid, ids)


class Regex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.muster = {m["id"]: m["_re"] for m in analyse.lade_muster(MUSTER_PFAD)}

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


class SondernAbgrenzung(unittest.TestCase):
    """Additive Formen („nicht nur/allein/bloß … sondern“) gehören zu nicht_nur_sondern, nicht zur Gegenfolie
    nicht_x_sondern (früher gewann dort zur Laufzeit das höhere Gewicht und empfahl „Gegenfolie streichen“)."""

    @classmethod
    def setUpClass(cls):
        cls.muster = analyse.lade_muster(MUSTER_PFAD)

    def treffer(self, satz):
        return [t[3]["id"] for t in analyse.muster_treffer(satz, self.muster) if t[3]["id"].endswith("sondern")]

    def test_additiv_nur_nicht_nur_sondern(self):
        for s in ADDITIV:
            with self.subTest(satz=s):
                self.assertEqual(self.treffer(s), ["nicht_nur_sondern"])

    def test_kontrast_nur_nicht_x_sondern(self):
        for s in KONTRAST:
            with self.subTest(satz=s):
                self.assertEqual(self.treffer(s), ["nicht_x_sondern"])


class Ersatzstrategien(unittest.TestCase):
    """Kein Ersatz darf Inhalt ersatzlos streichen lassen (Quantoren, Hecken mit Inhalt, Quellenaussagen)."""

    @classmethod
    def setUpClass(cls):
        cls.muster = {m["id"]: m for m in lade_json()["muster"]}

    def test_kein_unbedingtes_streichen_bei_angezeigten_mustern(self):
        for mid, m in self.muster.items():
            if (m.get("gewicht") or 0) <= 0:
                continue        # Muster mit Gewicht 0 zeigt der Coach nicht an
            with self.subTest(muster=mid):
                self.assertIsNone(UNBEDINGT_STREICHEN.search(m["ersatz"]), m["ersatz"])

    def test_inhalt_tragende_muster_mit_bedingung(self):
        for mid in INHALT_TRAGEND:
            ersatz = self.muster[mid]["ersatz"]
            with self.subTest(muster=mid):
                self.assertIsNone(UNBEDINGT_STREICHEN.search(ersatz), ersatz)
                if re.search(r"streich|weglassen|wegfallen", ersatz, re.IGNORECASE):
                    self.assertRegex(ersatz, r"(?i)\bnur\b|\bwenn\b|nicht ersatzlos|nicht streichen|behalten|bleib")

    def test_gegenfolie_quellenaussage_behalten(self):
        ersatz = self.muster["nicht_x_sondern"]["ersatz"]
        self.assertIn("Quellenaussage", ersatz)
        self.assertIn("behalten", ersatz)

    def test_strohmann_ersatz_ohne_gegenposition(self):
        for mid in ("greift_zu_kurz", "strohmann_aufbau"):
            with self.subTest(muster=mid):
                self.assertIn("eigene These direkt nennen", self.muster[mid]["ersatz"])

    def test_gegenfolie_ersatz_empfiehlt_keine_umstellung(self):
        # früher: „X behalten und nur die Formel auflösen („Y statt X“ …)“ – „statt“ ist selbst KI-typisch (v7)
        for mid in ("nicht_x_sondern", "gegenfolie_nachgestellt"):
            ersatz = self.muster[mid]["ersatz"]
            with self.subTest(muster=mid):
                self.assertNotIn("Formel auflösen", ersatz)
                self.assertIn("zwei Sätze", ersatz)
                self.assertIn("behalten", ersatz)
        self.assertIn("dieselbe Gegenfolie", self.muster["nicht_x_sondern"]["ersatz"])


class GegenfolieUmstellung(unittest.TestCase):
    """Coach-Evaluation v7 (echte menschliche Abschnitte): „nicht X, sondern Y“ wurde zu „Y und nicht X“ umgestellt und
    entging so dem Muster. Die nachgestellten Formen zählen jetzt als eigenes Muster mit fast gleichem Gewicht – Umstellen
    bringt (höchstens) einen Bruchteil der Punkte."""

    PAARE = [
        ("Experten sehen den Grund für den Anstieg nicht in der Gesetzesänderung von 1976, sondern in der Ausweitung der "
         "kommerziellen Werbung hinsichtlich des Cannabiskonsums in Coffeeshops.",
         ["Experten sehen den Grund für den Anstieg in der Ausweitung der kommerziellen Werbung hinsichtlich des "
          "Cannabiskonsums in Coffeeshops und nicht in der Gesetzesänderung von 1976.",
          "Experten sehen den Grund für den Anstieg in der Ausweitung der kommerziellen Werbung statt in der "
          "Gesetzesänderung von 1976.",
          "Experten sehen den Grund für den Anstieg in der Ausweitung der kommerziellen Werbung, nicht aber in der "
          "Gesetzesänderung von 1976."]),
        ("Agile Führungskräfte verstehen sich nicht als Kontrollinstanz, sondern als Unterstützer.",
         ["Agile Führungskräfte verstehen sich als Unterstützer und nicht als Kontrollinstanz.",
          "Agile Führungskräfte verstehen sich als Unterstützer statt als Kontrollinstanz."]),
    ]

    @classmethod
    def setUpClass(cls):
        cls.muster = analyse.lade_muster(MUSTER_PFAD)
        cls.gewicht = {m["id"]: m["gewicht"] for m in cls.muster}

    def summe(self, satz):
        return sum(t[2] for t in analyse.muster_treffer(satz, self.muster) if t[2] > 0), \
            [t[3]["id"] for t in analyse.muster_treffer(satz, self.muster)]

    def test_umgestellte_form_wird_erkannt(self):
        for original, umgestellt in self.PAARE:
            g_alt, ids_alt = self.summe(original)
            self.assertIn("nicht_x_sondern", ids_alt)
            for neu in umgestellt:
                with self.subTest(neu=neu):
                    g_neu, ids_neu = self.summe(neu)
                    self.assertIn("gegenfolie_nachgestellt", ids_neu)
                    self.assertNotIn("nicht_x_sondern", ids_neu)
                    # Kalibrierungsabhängiger Wächter: Umstellen darf höchstens ein Viertel des Gewichts einsparen
                    self.assertGreaterEqual(g_neu, 0.75 * g_alt)

    def test_gewicht_aus_kalibrierung(self):
        # Verhältnis KI/Mensch im Korpus 2,7 (v7-Messung): klar KI-typisch, Gewicht > 0
        self.assertGreater(self.gewicht["gegenfolie_nachgestellt"], 0)
        self.assertGreaterEqual(self.gewicht["gegenfolie_nachgestellt"], 0.75 * self.gewicht["nicht_x_sondern"])


if __name__ == "__main__":
    unittest.main()
