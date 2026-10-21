"""Regressionstests zu den Funden der adversarialen Prüfung von Coach v4:
1. Bündeln/Längenaufbau verlangen, den eingebetteten Satz „als Nominal- oder Präpositionalgruppe“ einzubauen – das darf nie
   einen Konjunktiv II/ein Kontrafaktum treffen („wäre“, „hätte“, „würde“), und beim Längenaufbau mit dem kurzen Satz vorn
   muss dessen Aussagestatus (Vermutung, Modalverb) genauso geprüft werden wie sonst der von Satz b.
2. Kontingent beim Bündeln: jede Bündelung kostet einen Satz – der Anteil langer Sätze landet am nächsten beim menschlichen
   Median, nicht bis zu ~0,6 Sätze darüber.
3. Die Satzlängen-Simulation rechnet die Wirkung auf die Sätze-pro-Absatz-Variation (Modellmerkmal) mit.

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
from test_coach import KI_TEXT, _KURZE_WORTE, satz  # noqa: E402
from test_coach_wirksamkeit import gleichmaessig  # noqa: E402

W = _KURZE_WORTE
T = ["Firma", "Region", "Branche", "Messe", "Schule", "Klinik", "Bank", "Kammer"]
B = analyse.lade_baselines()["textsorten"]["hochschule"]
REF = B["metriken"]


def aufbau_kurz_vorn(kurz0: str) -> str:
    """Wie test_coach_v4.aufbau_text, aber in Absatz 1 steht der kurze Satz (6 Wörter) VOR dem fast langen (26)."""
    teile = []
    for i in range(8):
        kurz = kurz0 if i == 0 else satz(T[i], 6, i + 5, W)
        teile.append(" ".join([satz(T[(i + 1) % 8], 21, i, W), kurz, satz(T[i], 26, i + 3, W),
                               satz(T[(i + 3) % 8], 22, i + 7, W), satz(T[(i + 5) % 8], 25, i + 9, W)]))
        teile.append(" ".join([satz(T[(i + 2) % 8], 9, i, W), satz(T[(i + 4) % 8], 10, i + 2, W)]))
    return "\n\n".join(teile)


def buendel_paare(c: dict) -> list[tuple[int, int, str | None]]:
    return [(h["satz"], h["weitere_nr"][0], h.get("variante")) for h in c["hinweise_roh"] if h["typ"] == "buendeln"]


class EingebetteterSatz(unittest.TestCase):
    def test_kein_konjunktiv_als_nominalgruppe(self):
        basis = gleichmaessig(8, 5)
        c0 = coach.coache(basis, None, 40, roh=True)
        paare = buendel_paare(c0)
        self.assertTrue(paare)
        saetze = {s["nr"]: s for s in analyse.analysiere_text(basis)["saetze"]}
        text = basis
        konj_texte = set()
        for _, b_nr, _ in paare:  # jeden bisher eingebetteten Satz b durch einen gleich langen Satz mit Kontrafaktum ersetzen
            sb = saetze[b_nr]
            thema = sb["text"].split()[1]
            neu = " ".join(["Ohne", "die", thema, "wäre"] + sb["text"].rstrip(".").split()[3:3 + sb["woerter"] - 5] + ["gewesen"]) + "."
            text = text.replace(sb["text"], neu, 1)
            konj_texte.add(neu)
        c = coach.coache(text, None, 40, roh=True)
        neu_saetze = {s["nr"]: s["text"] for s in analyse.analysiere_text(text)["saetze"]}
        for a_nr, b_nr, _ in buendel_paare(c):
            self.assertNotIn(neu_saetze[b_nr], konj_texte, (a_nr, b_nr))  # das Kontrafaktum ginge als Nominalgruppe verloren
        L = coach.Lauf(text, None)
        a, b = L.nach_nr[paare[0][0]], L.nach_nr[paare[0][1]]
        self.assertEqual(coach.buendel_paar_grund(L, a, b, laenge=False), "b_konjunktiv")

    def test_laengenaufbau_kurzer_satz_vorn_wird_geprueft(self):
        # Kontrolle: ein schlichter kurzer Satz vorn wird vom fast langen Satz aufgenommen (Längenaufbau, umgekehrte Reihenfolge)
        c = coach.coache(aufbau_kurz_vorn("Die Firma plant das bald neu."), None, 40, roh=True)
        self.assertIn((2, 3, "aufbau"), buendel_paare(c))
        # mit Vermutung, Konjunktiv II oder Modalverb nicht: der kurze Satz ginge als Nominalgruppe samt Aussagestatus verloren
        for kurz in ("Die Firma dürfte das bald ändern.", "Die Firma würde das bald ändern.", "Die Firma kann das bald ändern."):
            c = coach.coache(aufbau_kurz_vorn(kurz), None, 40, roh=True)
            self.assertFalse([p for p in buendel_paare(c) if 2 in p[:2]], kurz)


class NominalisierungGleicheSperren(unittest.TestCase):
    """Der kurze „dass“-Satz → Nominalgruppe (fw_dass) ist dieselbe Nominalisierung wie der Nebensatz-Auftrag und hat
    dieselben Sperren; zwei mit „und/oder“ koordinierte Teilsätze im Nebensatz werden nicht nominalisiert."""

    def lauf(self, satz_text):
        L = coach.Lauf(satz_text + "\n\n" + KI_TEXT, None)
        coach._hebel_priorisieren(L)
        coach._waechter(L)
        s = L.saetze[0]
        self.assertEqual(s["text"], satz_text)
        return L, s, L.masken[s["nr"]]

    def test_fw_dass_mit_den_sperren_des_nebensatz_auftrags(self):
        L, s, mk = self.lauf("Die Daten zeigen, dass die Kosten steigen.")
        self.assertIsNotNone(coach._fw_bilanz(L, "redeverb_dass", s, mk, coach.REDEVERB_KURZ_RE.search(mk)))  # Kontrolle
        for satz_text in ("Die Daten zeigen, dass die Kosten der Einführung der Software steigen.",  # Kette aus 4 Nomen
                          "Die Daten zeigen, dass es täglich Neuigkeiten gibt und man oft in Kontakt steht.",  # Koordination
                          "Die Daten zeigen, dass die Kosten ohne die Reform gestiegen wären."):  # Kontrafaktum
            L, s, mk = self.lauf(satz_text)
            self.assertIsNone(coach._fw_bilanz(L, "redeverb_dass", s, mk, coach.REDEVERB_KURZ_RE.search(mk)), satz_text)
            self.assertIsNone(coach.nebensatz_auftrag(L, s, mk), satz_text)

    def test_koordinierte_teilsaetze(self):
        k = coach.koordinierte_teilsaetze
        self.assertTrue(k("dass psychische Störungen unter Studierenden verbreitet sind und viele von ihnen Substanzen konsumieren"))
        self.assertTrue(k("weil sie Werbung dort nicht wahrnehmen oder sich von ihr nicht angesprochen fühlen"))
        self.assertTrue(k("da diese mit geringem Aufwand verbunden ist und schnell zu Ergebnissen führt"))
        self.assertFalse(k("dass die Kosten und die Preise steigen"))  # Nomen koordiniert, ein Teilsatz
        self.assertFalse(k("wenn ausschließlich geimpfte oder genesene Personen beteiligt sind"))  # Attribute koordiniert
        self.assertFalse(k("dass die Kosten im zweiten Jahr der Einführung steigen"))
        L, s, mk = self.lauf("Die Befragung zeigt, dass viele Betriebe sparen und die Teams kleiner werden.")
        self.assertIsNone(coach.nebensatz_auftrag(L, s, mk))


class KontingentBisZumMedian(unittest.TestCase):
    def test_anteil_langer_saetze_am_naechsten_beim_median(self):
        p50 = REF["anteil_lange_saetze"]["mensch"]["p50"]
        ziel = B["satzlaengen_verteilung_mensch"]
        for n, lange in ((44, 5), (43, 5), (42, 4), (49, 1), (45, 2), (40, 0)):
            fokus = [{"woerter": 35}] * lange + [{"woerter": w} for w in ([18, 20, 17, 22, 19, 21, 16, 23] * 7)[:n - lange]]
            d = coach.satzlaengen_diagnose(fokus, REF, ziel, None)
            if d["modus"] != "buendeln":
                continue
            k = d["kontingent"]
            abstand = lambda j: abs((lange + j) / (n - j) - p50)  # noqa: E731
            self.assertLessEqual(abstand(k), min(abstand(j) for j in range(0, 10)) + 1e-9, (n, lange, k))
            # nie mehr als einen halben Satz über dem Median
            self.assertLessEqual((lange + k) / (n - k), p50 + 0.5 / (n - k) + 1e-9, (n, lange, k))

    def test_simulierter_stand_nach_dem_buendeln(self):
        p50 = REF["anteil_lange_saetze"]["mensch"]["p50"]
        for text in (gleichmaessig(8, 5), gleichmaessig(10, 6)):
            L = coach.Lauf(text, None)
            coach._hebel_priorisieren(L)
            coach._waechter(L)
            coach._satzlaengen(L)
            folge = coach.laengen_folge(L.sim)
            anteil = sum(x >= coach.LANG_AB for x in folge) / len(folge)
            self.assertLessEqual(anteil, p50 + 0.5 / len(folge) + 1e-9)


class AbsatzVariationInDerSimulation(unittest.TestCase):
    def test_laengenmodell_mit_absaetzen(self):
        lm = coach.LaengenModell(REF, B)
        ki = [12, 18, 22, 15, 25, 19, 14, 21, 17, 24, 16, 20, 23, 13, 26, 18, 27, 11, 19, 22] * 2  # KI-typisch
        neu = [34] + ki[2:]  # Bündeln der ersten beiden Sätze
        ohne, t_ohne = lm.bewerte(ki, neu)
        self.assertIsNotNone(ohne)
        self.assertNotIn("absatz", t_ohne)
        # Bündeln im längsten Absatz macht die Absätze gleichmäßiger: kostet im Modell (saetze_pro_absatz_cv)
        lang_vorn = [12, 4, 4, 4, 4, 4, 4, 4]
        mit, t_mit = lm.bewerte(ki, neu, lang_vorn, [11] + lang_vorn[1:])
        self.assertLess(t_mit["absatz"], 0)
        self.assertLess(mit, ohne)
        # in einem kurzen Absatz streuen sie danach stärker: bringt etwas
        kurz_vorn = [3, 6, 6, 6, 6, 6, 6, 1]
        mit2, t_mit2 = lm.bewerte(ki, neu, kurz_vorn, [2] + kurz_vorn[1:])
        self.assertGreater(t_mit2["absatz"], 0)
        self.assertGreater(mit2, ohne)
        self.assertAlmostEqual(lm.werte(ki, lang_vorn)[coach.ABSATZ_CV], analyse.cv(lang_vorn), places=9)

    def test_lauf_rechnet_die_absaetze_mit(self):
        text = gleichmaessig(8, 5)  # alle Absätze gleich lang: jede Bündelung macht sie ungleicher
        L = coach.Lauf(text, None)
        erg_cv = L.m.get(coach.ABSATZ_CV)
        self.assertAlmostEqual(analyse.cv(L.absatz_anzahl(L.sim)) if len(L.absaetze) > 1 else 0.0, erg_cv, places=4)
        wert, teile = L.laengen_umbau({0: [34], 1: []})
        self.assertIn("absatz", teile)
        self.assertGreater(teile["absatz"], 0)


if __name__ == "__main__":
    unittest.main()
