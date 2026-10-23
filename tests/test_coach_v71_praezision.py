"""Tests für Coach v7.1, Auftrag A2 (KI-Pfad und Präzision), nach den beiden Abschlussprüfungen von v7:

1. Mindestwirkung: unter dem Modellziel nur Aufträge mit netto_logit > NETTO_TOLERANZ, auch bei großer Lücke; Ausnahme Score-Hebel
   mit positiver Score-Simulation; Zähl-Familien (KI-Muster, Semikolons …) zählen gemeinsam, aber nur mit Mindestwirkung je Auftrag;
   Konnektor-Aufträge ohne Wirkung entfallen, die Orientierung sagt dann nicht „streichen“.
2. Wort-Aufträge mit festem Wortverlust speichern laengen_alt/sim; „klein, aber sicher“ nur ohne Längenklassen-Kippen in Richtung KI;
   der Wächter ordnet eine Nebenwirkung einem kürzenden Wort-Auftrag zu.
3. Diagnose: „mit Aufträgen“ = Summe der netto_teile der angezeigten Aufträge; „knapp“ nur, wenn die Aufträge selbst ≥ 70 % decken.
4. Wirksamkeitsprüfung einseitig; Abkürzungen gegen P75; „rund“/„etwa“ keine Langform von „ca.“.
5. Absatz teilen: Fortsetzungsmarker, Fazit am Absatzende bzw. als Ein-Satz-Kopf (Schlussabsatz), Themensatz, Befund-Ankündigung.
6. Rundensperre für in der Vorrunde umgebaute Sätze; nominal_sperre für reflexives Prädikativ und Satzadverb.
7. „zugleich/zudem“ vor einer Einschränkung: „aber“ erlaubt statt streichen; Hebeltext nur mit Konnektoren, zu denen eine Stelle steht.
8. Strohmann-Technik nur mit Kontrastmarker.
9. Themenbedingtes Funktionswort-Profil statt Neuschreib-Empfehlung.
10. „darüber hinaus“ mitten im Satz/nach „und“: eigener Text; Muster im Band nur, wenn das Modellziel verfehlt wird.

Synthetische Texte; Felder der Messseite und die Netto-Simulation werden, wo nötig, per Mock gesetzt.

python3 -m unittest discover -s tests
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "humanisieren", "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyse  # noqa: E402
import coach  # noqa: E402
from test_coach import KI_TEXT, THEMEN, satz  # noqa: E402
from test_coach_wirksamkeit import W, gleichmaessig, mit_metriken  # noqa: E402

TS = analyse.lade_baselines()["textsorten"]["hochschule"]
VORG = {"gender", "gedankenstrich", "bindestrich", "konsistenz", "bereinigung"}


def stil(c):
    return [h for h in c["hinweise"] if h["typ"] not in VORG and not h.get("info")]


def konnektor_text():
    """Sechs Absätze mit je zwei „Zudem“-Sätzen: Konnektor-Dichte weit über P90 (≈ 32 je 1000 Wörter)."""
    out = []
    for th in ("Firma", "Region", "Branche", "Messe", "Schule", "Klinik"):
        out.append(f"Die {th} plant neue Wege für den Kontakt mit jungen Leuten in der Stadt und auf dem Land. "
                   f"Zudem nutzt die {th} oft kurze Wege und flache Strukturen für schnelle Entscheidungen im Alltag. "
                   f"Zudem prüft die {th} regelmäßig die Kosten und die Wirkung der neuen Angebote vor Ort. "
                   f"Die Leute schätzen diese Angebote sehr und kommen gern wieder in die {th} zurück.")
    return "\n\n".join(out)


def diag_ns(beitraege, p, hinweise=()):
    return SimpleNamespace(bew={"verfuegbar": True, "p_mensch": p, "modell_beitraege": beitraege}, messungen=[],
                           ts={"modell": TS["modell"]}, fw_potenzial=0.0, fw_diag=None, hinweise=list(hinweise))


# ---------------------------------------------------------------------------------------------------------------------------
# 1. Mindestwirkung
# ---------------------------------------------------------------------------------------------------------------------------

class Mindestwirkung(unittest.TestCase):
    def test_grosse_luecke_nur_auftraege_mit_wirkung(self):
        # Agile R2 (v7-Prüfung): Synonyme +0,0003 und Nebensatz −0,005 bei einer Lücke von 3,7 – danach Score −3
        echt = coach.netto_wirkung

        def fake(L, h):
            n, t = echt(L, h)
            return (0.0003, {}) if h["typ"] != "absatz_teilen" else (n, t)
        with mock.patch.object(coach, "netto_wirkung", fake), mock.patch.object(coach, "familie_retten", lambda *a, **k: []), \
                mock.patch.object(coach, "_teilziel_familien", lambda L, f: []):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertLess(c["bewertung"]["p_mensch"], 0.1)
        self.assertTrue(stil(c))
        self.assertTrue(all(h["netto_logit"] > coach.NETTO_TOLERANZ for h in stil(c)), [(h["typ"], h["netto_logit"]) for h in stil(c)])
        self.assertGreater(c["unterdrueckt"].get("ohne_wirkung", 0), 0)

    def test_score_hebel_mit_positiver_score_wirkung_bleibt(self):
        # Ausnahme: fehlt auch Score, bleibt ein Hebel des Score-Teilziels, dessen simulierte Score-Wirkung positiv ist
        with mock.patch.object(coach, "netto_wirkung", lambda L, h: (0.0, {})), \
                mock.patch.object(coach, "familie_retten", lambda *a, **k: []), \
                mock.patch.object(coach, "_teilziel_familien", lambda L, f: ["semikolon"]), \
                mock.patch.object(coach, "score_wirkung", lambda L, h: 2.5 if h["typ"] == "semikolon" else 0.0):
            c = coach.coache(KI_TEXT, None, 15)
        typen = {h["typ"] for h in stil(c) if not h.get("klein_sicher")}
        self.assertEqual(typen, {"semikolon"})
        self.assertTrue(all(h.get("score_delta") == 2.5 for h in stil(c) if h["typ"] == "semikolon"))

    def test_score_wirkung_simuliert_ampelwechsel(self):
        L = coach.Lauf(KI_TEXT, None)
        z = L.kz["semikolon_pro_1000"]
        self.assertEqual(z["status"], "rot")
        # alle Semikolons weg: der Wert fällt ins grüne Band – positiver Score; ein Zehntel davon ändert die Ampel nicht
        alle = {"typ": "semikolon", "satz": None}
        with mock.patch.object(coach, "wirkung_kennzahlen", lambda L_, h, alle=False: {"semikolon_pro_1000": -z["wert"]}):
            self.assertGreater(coach.score_wirkung(L, alle), 0)
        with mock.patch.object(coach, "wirkung_kennzahlen", lambda L_, h, alle=False: {"semikolon_pro_1000": -0.01}):
            self.assertEqual(coach.score_wirkung(L, alle), 0.0)
        with mock.patch.object(coach, "wirkung_kennzahlen", lambda L_, h, alle=False: {"hedging_pro_1000": 1.0}):
            self.assertIsNone(coach.score_wirkung(L, alle))  # unbewertete Kennzahl: keine Score-Wirkung

    def test_score_simulation_nebensatz(self):
        # Nebensatz → Nominalgruppe: für den Score zählen auch Verhältnis 2:1 und Anteil Sätze mit Nebensatz (keine Modellmerkmale)
        L = coach.Lauf(KI_TEXT, None)
        s = next(x for x in L.fokus if analyse.teilsatz_zerlegung(x["text"])[:2] == (1, 1))
        h = {"typ": "nebensatz", "satz": s["nr"]}
        roh = coach.wirkung_kennzahlen(L, h, alle=True)
        self.assertLess(roh["anteil_saetze_mit_nebensatz"], 0)
        self.assertLess(roh["teilsatz_verhaeltnis_21"], 0)
        self.assertNotIn("teilsatz_verhaeltnis_21", coach.wirkung_kennzahlen(L, h))  # die Netto-Simulation des Modells bleibt gleich

    def test_zaehl_familie_gemeinsam_aber_nicht_durch_summieren(self):
        # KI_TEXT: KI-Muster weit über der Kappung – einzeln bringt eine Wendung nichts, mehrere zusammen schon
        c = coach.coache(KI_TEXT, None, 40)
        fam = [h for h in stil(c) if h.get("familie")]
        self.assertTrue(fam)
        for h in fam:
            self.assertEqual(h["familie"]["kennzahl"], "ki_muster_pro_1000")
            self.assertGreater(h["netto_logit"], coach.NETTO_TOLERANZ)
        # Konnektoren: je Auftrag +0,0027 (Funktionswort-Profil), zusammen +0,013 – das ist kein Grund, sie zu retten
        c = coach.coache(konnektor_text(), None, 15)
        self.assertFalse([h for h in stil(c) if h["typ"] == "konnektor"])
        self.assertGreaterEqual(c["unterdrueckt"].get("ohne_wirkung", 0), 2)

    def test_konnektoren_ohne_wirkung_keine_streich_orientierung(self):
        # hslb3 (v7-Prüfung): drei „Zudem streichen“ ohne Statuswechsel, in Runde 2 weiter „zudem streichen“ als Orientierung
        c = coach.coache(konnektor_text(), None, 15)
        h = next(x for x in c["hebel"] if x["id"] == "konnektoren")
        self.assertTrue(h["stellenlos"])
        self.assertIn("brächte vorab gerechnet nichts", h["selbsthilfe"])
        self.assertNotIn("streichen, wo der Bezug klar ist", h["selbsthilfe"])

    def test_klein_sicher_nur_mit_mindestwirkung(self):
        L = coach.Lauf(KI_TEXT, None)
        treffer = [(s["nr"], fund, g) for s in L.fokus for _a, _e, g, mu, fund, _v in analyse.muster_treffer(L.masken[s["nr"]], L.muster)
                   if g >= coach.KLEIN_SICHER_GEWICHT and mu["id"] not in coach.GEGENFOLIE_MUSTER]
        with mock.patch.object(coach, "ein_auftrag_je_satz", lambda hs, texte=None: []), \
                mock.patch.object(coach, "muster_rest", lambda L_: (treffer[:1], 0.3)):
            c = coach.coache(KI_TEXT, None, 15)
        # eine einzelne Wendung weit über der Kappung: simuliert ohne Wirkung – keine „klein, aber sicher“-Stelle, auch nicht im Lauf
        self.assertFalse([h for h in c["hinweise"] if h.get("klein_sicher")])
        self.assertGreaterEqual(c["unterdrueckt"].get("klein_sicher_ohne_wirkung", 0), 1)


# ---------------------------------------------------------------------------------------------------------------------------
# 2. Wort-Aufträge: Längen speichern, Längenklassen, Wächter
# ---------------------------------------------------------------------------------------------------------------------------

S31 = ("Unternehmen, die diesen Wandel aktiv gestalten und dabei sowohl in ihre Datenqualität als auch in die Qualifikation ihrer "
       "Mitarbeiter investieren, können die Chancen der Digitalisierung für das Controlling langfristig besser nutzen.")
S25 = ("Unternehmen, die sowohl in ihre Datenqualität als auch in die Qualifikation ihrer Mitarbeiter investieren, nutzen die "
       "Chancen der Digitalisierung besser.")


class WortAuftraegeLaengen(unittest.TestCase):
    def test_laengenklasse_richtung_ki(self):
        f = coach.laengenklasse_richtung_ki
        self.assertEqual(f(31, 29), 30)
        self.assertEqual(f(41, 39), 40)
        self.assertEqual(f(28, 26), 26)
        self.assertEqual(f(13, 14), 14)
        self.assertIsNone(f(25, 23))
        self.assertIsNone(f(29, 31))  # länger in Richtung Mensch
        self.assertIsNone(f(15, 13))  # aus dem mittleren Band nach unten: weg von KI

    def klein(self, s_text):
        text = gleichmaessig(3, 5) + "\n\n" + s_text + " " + satz(THEMEN[2], 18, 5, W) + "\n\n" + gleichmaessig(2, 5, 20)
        L = coach.Lauf(text, None)
        s = next(x for x in L.saetze if x["text"].startswith("Unternehmen, die"))
        fund = next(f for _a, _e, g, mu, f, _v in analyse.muster_treffer(L.masken[s["nr"]], L.muster) if mu["id"] == "sowohl_als_auch")
        with mock.patch.object(coach, "muster_rest", lambda L_: ([(s["nr"], fund, 0.8)], 0.3)), \
                mock.patch.object(coach, "abk_plan", lambda L_: ([], 0, 0)):
            neu = coach.klein_sicher(L)
        return L, s, neu

    def test_klein_sicher_nicht_ueber_die_grenze_von_30(self):
        # Controlling S48 (v7-Prüfung): „sowohl … als auch“ → „und“ kürzte 31 → 29 Wörter, lange Sätze wurden rot
        L, s, neu = self.klein(S31)
        self.assertEqual(s["woerter"], 31)
        self.assertEqual(neu, [])
        self.assertEqual(L.unterdrueckt.get("klein_sicher_laengenklasse"), 1)

    def test_klein_sicher_speichert_laengen(self):
        L, s, neu = self.klein(S25)
        self.assertEqual(len(neu), 1)
        self.assertEqual(neu[0]["laengen_alt"], [s["woerter"]])
        self.assertEqual(neu[0]["sim"], [s["woerter"] - 2])

    def wächter_lauf(self):
        """Vorrunde: ein befolgter Floskel-Auftrag an einem 31-Wort-Satz, der jetzt 29 Wörter hat; lange Sätze jetzt unter P10."""
        s29 = S31.replace("dabei sowohl in ihre Datenqualität als auch in", "dabei in ihre Datenqualität und in")
        text = gleichmaessig(8, 5) + "\n\n" + s29 + " " + satz(THEMEN[2], 18, 5, W)
        schl = coach.schluessel_anfang(s29)
        h = {"typ": "floskel", "anfang": schl, "satz": 41, "laenge": 31, "pos": 40}
        verlauf = {"messungen": [{"hinweise": [h], "kennzahlen": {}, "werte": {"anteil_lange_saetze": 0.06},
                                  "roh": {"anteil_lange_saetze": 0.06}}]}
        return text, verlauf

    def test_waechter_ordnet_kuerzung_zu(self):
        text, verlauf = self.wächter_lauf()
        L = coach.Lauf(text, verlauf)
        s = next(x for x in L.saetze if x["text"].startswith("Unternehmen, die"))
        self.assertEqual(s["woerter"], 29)
        ursache = coach.wort_kuerzung_ursache(L, "anteil_lange_saetze")
        self.assertEqual([(u["typ"], u["vorher"], u["jetzt"], u["grenze"]) for u in ursache], [("floskel", 31, 29, 30)])
        c = coach.coache(text, verlauf, 15)
        u = next(x for x in c["fortschritt"]["ueberkorrektur"] if x["id"] == "anteil_lange_saetze")
        self.assertTrue(u["ursache_wort"])
        b = coach.bericht(c)
        self.assertIn("Ursache: der befolgte Auftrag „Floskeln“ an Satz 41 der Vorrunde (31 → 29 Wörter, jetzt unter 30)", b)
        self.assertNotIn("keinem befolgten Auftrag der Vorrunde zuordnen", b)

    def test_waechter_sperrt_weitere_kuerzung_ueber_die_grenze(self):
        text, verlauf = self.wächter_lauf()
        L = coach.Lauf(text, verlauf)
        coach._hebel_priorisieren(L)
        coach._waechter(L)
        self.assertIn("anteil_lange_saetze", L.kuerzung_sperre)

    def test_verschlechtert_nichts_nur_nach_pruefung(self):
        L = coach.Lauf(KI_TEXT, None)
        treffer = [(s["nr"], fund, g) for s in L.fokus for _a, _e, g, mu, fund, _v in analyse.muster_treffer(L.masken[s["nr"]], L.muster)
                   if g >= coach.KLEIN_SICHER_GEWICHT and mu["id"] not in coach.GEGENFOLIE_MUSTER]
        with mock.patch.object(coach, "ein_auftrag_je_satz", lambda hs, texte=None: []), \
                mock.patch.object(coach, "muster_rest", lambda L_: (treffer, 0.3)):
            c = coach.coache(KI_TEXT, None, 15)
        b = coach.bericht(c)
        self.assertNotIn("verschlechtern aber nichts", b)
        self.assertTrue(c["klein_sicher_geprueft"])
        self.assertIn("Vorab geprüft: Sie verschlechtern weder Modell noch Score", b)
        c["klein_sicher_geprueft"] = False
        self.assertNotIn("Vorab geprüft", coach.bericht(c))


# ---------------------------------------------------------------------------------------------------------------------------
# 3. Diagnose aus den netto_teile der angezeigten Aufträge
# ---------------------------------------------------------------------------------------------------------------------------

class DiagnoseNettoTeile(unittest.TestCase):
    B = [{"id": "nachbarsatz_ueberlappung", "name": "Begriffsaufnahme", "beitrag": -1.07},
         {"id": "satzklammer_mittel", "name": "Satzklammer", "beitrag": -0.87}]

    def test_nicht_simuliertes_merkmal_zaehlt_nicht_pauschal(self):
        # Agile R2 (v7-Prüfung): „teilweise erreichbar ≈ 0,53 mit den genannten Stellen“ für einen Synonym-Auftrag mit +0,0003
        h = {"typ": "synonyme", "hebel": "begriffe", "netto_logit": 0.0003, "netto_teile": {"mattr_100": 0.0003}}
        d = coach._diagnose(diag_ns(self.B, 0.122, [h]), [h], 0.85)
        self.assertEqual(d["erreichbar_logit"], 0.0)
        z = {x["id"]: x for x in d["beitraege"]}
        self.assertEqual(z["nachbarsatz_ueberlappung"]["erreichbar_logit"], 0.0)
        txt = "\n".join(coach.diagnose_text(d))
        self.assertIn("mit Aufträgen ≈ 0,00", txt)
        self.assertNotIn("mit den genannten Stellen", txt)

    def test_simulierter_teil_zaehlt(self):
        h = {"typ": "anknuepfung", "hebel": "begriffe", "netto_logit": 0.2, "netto_teile": {"nachbarsatz_ueberlappung": 0.2}}
        d = coach._diagnose(diag_ns(self.B, 0.122, [h]), [h], 0.85)
        z = {x["id"]: x for x in d["beitraege"]}
        self.assertAlmostEqual(z["nachbarsatz_ueberlappung"]["erreichbar_logit"], 0.2)
        self.assertAlmostEqual(d["erreichbar_logit"], 0.2)

    def test_knapp_nur_wenn_die_auftraege_decken(self):
        # pauschal geschätzte Merkmale ohne Auftrag allein machen kein „knapp“ (v7-Prüfung: CSRD 93 %, Controlling 85 %)
        d = coach._diagnose(diag_ns(self.B, 0.62), [], 0.86)
        self.assertGreaterEqual(d["stellenlos_logit"], coach.KNAPP_ANTEIL * d["luecke_logit"])
        self.assertEqual(d["grenze"], "einzelkorrekturen")
        txt = "\n".join(coach.diagnose_text(d))
        self.assertIn("nur grob geschätzt", txt)
        self.assertNotIn("Knapp", txt)


# ---------------------------------------------------------------------------------------------------------------------------
# 4. Wirksamkeitsprüfung einseitig, Abkürzungen
# ---------------------------------------------------------------------------------------------------------------------------

class WirksamkeitEinseitig(unittest.TestCase):
    TEXT = gleichmaessig(8, 5)

    def lauf(self, wert):
        h = {"typ": "abkuerzung", "anfang": "ein satz der nicht mehr da ist", "satz": 3, "ziel": "abkuerzungen_pro_1000",
             "ziel_wert": 0.0}
        verlauf = {"messungen": [{"hinweise": [h], "kennzahlen": {}, "werte": {"abkuerzungen_pro_1000": 0.0}, "roh": {}}]}
        with mit_metriken(abkuerzungen_pro_1000=wert):
            L = coach.Lauf(self.TEXT, verlauf)
        coach._wirksamkeit(L)
        return L

    def test_gruen_oder_gegenseite_im_band_ist_wirksam(self):
        # CSRD R2 (v7-Prüfung): Abkürzungen 0,00 → 3,52 grün, trotzdem „ausgesetzt“ neben „Schon gut“
        for wert in (3.52, 6.0):  # grün bzw. Gegenseite im Band (P75 3,81 < 6,0 < P90 7,47)
            self.assertNotIn("abkuerzung", self.lauf(wert).ausgesetzt, wert)
        self.assertIn("abkuerzung", self.lauf(9.0).ausgesetzt)  # jenseits P90: nicht wirksam

    def test_rund_und_etwa_sind_keine_langform(self):
        kurz = {k: rx for rx, k, _z in coach.ABK_ERSATZ}
        self.assertFalse(kurz["ca."].search("rund 500 Beschäftigte"))
        self.assertFalse(kurz["ca."].search("etwa 120 Personen"))
        self.assertTrue(kurz["ca."].search("circa 500 Beschäftigte"))
        self.assertFalse(coach.ABK_FAMILIEN["ca."][1].search("etwa 15.000"))


# ---------------------------------------------------------------------------------------------------------------------------
# 5. Absatz teilen
# ---------------------------------------------------------------------------------------------------------------------------

class AbsatzTeilen(unittest.TestCase):
    def trennbar(self, saetze, vor_text=None, nach_text=True):
        text = ((vor_text + "\n\n") if vor_text else "") + " ".join(saetze) + ("\n\n" + gleichmaessig(4, 5) if nach_text else "")
        L = coach.Lauf(text, None)
        nr = 2 if vor_text else 1
        liste = L.absaetze[nr]
        return [coach._absatz_trennbar(L, liste, k) for k in range(1, len(saetze))]

    A = "Viele Händler testen neue Modelle für die Preisgestaltung in ihren Online-Shops."
    B = "Die Käufer reagieren darauf sehr unterschiedlich und vergleichen die Angebote im Netz."

    def test_fortsetzungsmarker(self):
        f = coach.fortsetzung_im_hauptsatz
        self.assertTrue(f("Häufige Preisänderungen schwächen außerdem die Wirkung von Referenzpreisen."))  # DP vor S30
        self.assertTrue(f("In vielen Unternehmen bilden sich auch neue Rollen heraus, etwa Data Analysts."))  # Controlling vor S16
        self.assertTrue(f("Schätzungen gingen von ca. 50.000 betroffenen Unternehmen in der EU aus."))  # CSRD vor S14
        self.assertTrue(f("Besondere Bedeutung hat für ihn die Familie."))
        self.assertTrue(f("Viele der zugrunde liegenden Studien und Praxisberichte beziehen sich zudem auf große Unternehmen."))
        # ssoar-5763 (Nachprüfung): Demonstrativ mit Nomen tief im Satz verweist zurück; die eigene Arbeit nicht
        self.assertTrue(f("Sowohl Zoe als auch Erik beziehen sich auf Erfahrungen ihrer Geschwister in diesem Bereich."))
        self.assertFalse(f("In dieser Arbeit wird der Markt für gebrauchte Fahrräder untersucht."))
        self.assertFalse(f("Mit der Richtlinie wurde die Erstanwendung zunächst um zwei Jahre verschoben."))
        self.assertFalse(f("Die Weiterbildung betrifft Wege für den Kontakt mit jungen Leuten in der Region und plant dazu auch mehr."))
        self.assertFalse(f("Sie unterscheiden sowohl instrumentelle als auch symbolische Attribute."))

    def test_kein_absatz_vor_fortsetzung(self):
        c = "Häufige Preisänderungen schwächen außerdem die Wirkung von Referenzpreisen im Handel."
        self.assertEqual(self.trennbar([self.A, self.B, c, satz(THEMEN[2], 18, 5, W)])[1], False)

    def test_kein_fazit_als_eigener_absatz(self):
        fazit = "Insgesamt hängt der Erfolg der Preissetzung stark von der Akzeptanz der Kunden ab."
        self.assertEqual(self.trennbar([self.A, self.B, fazit])[-1], False)  # vor dem Fazit am Absatzende
        # Ein-Satz-Kopf im Schlussabsatz des Textes (DP R2: Fazit S41 als Ein-Satz-Absatz)
        schluss = ["Dynamische Preissetzung kann für Händler ein wirksames Instrument sein, ihr Erfolg hängt aber von den Kunden ab.",
                   "Entscheidend ist, dass Unternehmen die Grenzen des Instruments kennen und es mit Augenmaß einsetzen.",
                   "Bei personalisierten Preisen erscheint Zurückhaltung geboten, weil Vertrauen schnell verloren geht."]
        self.assertEqual(self.trennbar(schluss, vor_text=gleichmaessig(3, 5), nach_text=False)[0], False)

    def test_nicht_nach_befund_ankuendigung(self):
        # Controlling vor S24: der kurze Befundsatz und seine Erläuterung bleiben zusammen
        befund = "Als einer der größten Engpässe hat sich in der Untersuchung die Datenqualität erwiesen."
        erl = "Heterogene Systemlandschaften und unklare Verantwortlichkeiten schränken den Nutzen moderner Werkzeuge ein."
        self.assertEqual(self.trennbar([self.A, befund, erl, satz(THEMEN[2], 18, 5, W)])[1], False)

    def test_nicht_nach_themensatz(self):
        thema = "Das Preisportal übernimmt dabei eine zentrale Rolle als Vergleichsinstanz der Kunden."
        s = [self.A, self.B, thema, "Das Preisportal zeigt den günstigsten Anbieter für jedes Produkt sofort an.",
             "Viele Kunden kaufen erst, wenn das Preisportal einen guten Preis meldet."]
        L = coach.Lauf(" ".join(s) + "\n\n" + gleichmaessig(4, 5), None)
        self.assertTrue(coach.themensatz_davor(L, L.absaetze[1], 3))
        self.assertFalse(coach.themensatz_davor(L, L.absaetze[1], 2))

    def test_neutrale_teilung_bleibt(self):
        neu = "Die Gesetzgebung regelt seit dem letzten Jahr die Kennzeichnung personalisierter Preise im Onlinehandel."
        self.assertEqual(self.trennbar([self.A, self.B, neu, satz(THEMEN[2], 18, 5, W)])[1], True)


# ---------------------------------------------------------------------------------------------------------------------------
# 6. Rundensperre und nominal_sperre
# ---------------------------------------------------------------------------------------------------------------------------

S11 = "Da sich agile Führungskräfte idealerweise als Unterstützer verstehen, besteht hier eine große konzeptionelle Nähe zum Modell."


class Rundensperre(unittest.TestCase):
    def lauf(self, hinweis, anfaenge=None):
        text = gleichmaessig(2, 5) + "\n\n" + S11 + " " + satz(THEMEN[2], 18, 5, W) + "\n\n" + gleichmaessig(2, 5, 20)
        v = {"hinweise": [hinweis], "kennzahlen": {}, "roh": {}}
        if anfaenge is not None:
            v["anfaenge"] = anfaenge
        L = coach.Lauf(text, {"messungen": [v]})
        L.umgebaut = coach.vorrunde_umgebaut(L)
        return L, next(x for x in L.saetze if x["text"].startswith("Da sich agile"))

    def test_umgebauter_satz_keine_struktur_auftraege(self):
        # Agile S11 (v7-Prüfung): erst gekürzt (Gegenfolie/Floskel), dann Nebensatz → Nominalgruppe – eine Nominalkette entstand
        L, s = self.lauf({"typ": "floskel", "anfang": coach.schluessel_anfang(S11), "satz": 11, "laenge": 22})
        self.assertEqual(L.umgebaut, {s["nr"]})
        self.assertFalse(L.hinweis("nebensatz", s, "Nebensatz als Präpositionalgruppe", 0.8))
        self.assertFalse(L.hinweis("gegenfolie", s, "Gegenfolie", 0.8))
        self.assertEqual(L.unterdrueckt["rundensperre"], 2)
        self.assertTrue(L.hinweis("abkuerzung", s, "Abkürzung", 0.5))  # kein Struktur-Auftrag: erlaubt

    def test_kleine_wortaenderung_ist_kein_umbau(self):
        L, _s = self.lauf({"typ": "floskel", "anfang": coach.schluessel_anfang(S11), "satz": 11, "laenge": 18})
        self.assertEqual(L.umgebaut, set())  # nur ±2 Wörter: nicht befolgt im Sinne eines Umbaus

    def test_umgeschriebener_satzanfang_ueber_die_anfaenge_der_vorrunde(self):
        text = gleichmaessig(2, 5) + "\n\n" + S11 + " " + satz(THEMEN[2], 18, 5, W) + "\n\n" + gleichmaessig(2, 5, 20)
        L0 = coach.Lauf(text, None)
        s = next(x for x in L0.saetze if x["text"].startswith("Da sich agile"))
        anfaenge = [coach.schluessel_anfang(x["text"]) for x in L0.fokus]
        pos = L0.fokus_index[s["nr"]]
        anfaenge[pos] = "weil sich agile chefs als helfer"  # Anfang der Vorrunde, heute umformuliert
        L, s2 = self.lauf({"typ": "gegenfolie", "anfang": anfaenge[pos], "satz": s["nr"], "laenge": 25, "pos": pos}, anfaenge)
        self.assertEqual(L.umgebaut, {s2["nr"]})

    def test_stand_speichert_satzanfaenge(self):
        c = coach.coache(gleichmaessig(3, 5), None, 15)
        self.assertEqual(len(c["stand"]["anfaenge"]), len(c["stand"]["laengen"]))

    def test_nominal_sperre_reflexiv_und_satzadverb(self):
        L, s = self.lauf({"typ": "floskel", "anfang": "x", "satz": 1})
        mk = L.masken[s["nr"]]
        self.assertEqual(coach.nominal_sperre(L, s, mk, "da sich agile Führungskräfte als Unterstützer verstehen"), "reflexiv")
        self.assertEqual(coach.nominal_sperre(L, s, mk, "weil die Daten vermutlich fehlen"), "satzadverb")
        self.assertEqual(coach.nominal_sperre(L, s, mk, "da sie idealerweise beraten"), "satzadverb")
        self.assertIsNone(coach.nominal_sperre(L, s, mk, "weil Daten fehlen"))


# ---------------------------------------------------------------------------------------------------------------------------
# 7. Konnektoren: adversativ, Hebeltext
# ---------------------------------------------------------------------------------------------------------------------------

class KonnektorAdversativ(unittest.TestCase):
    def test_erkennung(self):
        f = coach.konnektor_adversativ
        self.assertEqual(f("Zugleich zeigt sich, dass dieser Zusammenhang weniger eindeutig ist.", "Zugleich"), "weniger")
        self.assertEqual(f("Die Firma wächst, zudem sind die Kosten nicht gestiegen.", "zudem"), "nicht")
        self.assertIsNone(f("Zugleich wächst der Markt in allen Regionen deutlich.", "Zugleich"))
        self.assertIsNone(f("Außerdem ist der Markt nicht gewachsen.", "Außerdem"))  # nur zugleich/zudem/gleichzeitig

    def test_auftrag_erlaubt_aber_statt_streichen(self):
        text = konnektor_text().replace("Zudem nutzt die Firma oft kurze Wege und flache Strukturen für schnelle Entscheidungen im Alltag.",
                                        "Zudem nutzt die Firma kurze Wege und flache Strukturen für schnelle Entscheidungen kaum.")
        L = coach.Lauf(text, None)
        coach._hebel_priorisieren(L)
        coach._konnektoren(L)
        s = next(x for x in L.saetze if "für schnelle Entscheidungen kaum" in x["text"])
        h = next(x for x in L.hinweise if x["typ"] == "konnektor" and x["satz"] == s["nr"])
        self.assertIn("„aber“ im Mittelfeld hier erlaubt", h["text"])
        self.assertIn("„kaum“", h["text"])
        self.assertEqual(h["streicht"], [])
        self.assertEqual(h["fw_dazu"], {"aber": 1})

    def test_hebeltext_nur_mit_stelle(self):
        ref = TS["metriken"]
        t = coach.hebel_warum("konnektoren", ref, vorhanden={"zugleich"})
        self.assertIn("„zugleich“", t)
        self.assertNotIn("„schließlich“", t)
        self.assertNotIn("„zudem“", t)
        self.assertNotIn("vor allem", coach.hebel_warum("konnektoren", ref, vorhanden=set()))


# ---------------------------------------------------------------------------------------------------------------------------
# 8. Strohmann nur mit Kontrast, 10. „darüber hinaus“, Muster im Band
# ---------------------------------------------------------------------------------------------------------------------------

class FloskelTexte(unittest.TestCase):
    def ersatz(self, saetze, nr, mid):
        L = coach.Lauf(" ".join(saetze) + "\n\n" + gleichmaessig(3, 5), None)
        mu = next(m for m in L.muster if m.get("id") == mid)
        s = L.nach_nr[nr]
        a = mu["_re"].search(L.masken[nr]).start()
        return coach.floskel_ersatz(mu, L, s, a)

    def test_strohmann_ohne_kontrast(self):
        # haw-7747 S42 (v7-Prüfung): „Bei näherer Betrachtung fällt auf, dass …“ baut keine Sicht auf und kippt sie nicht
        vor = "Die Befragung umfasste zwanzig Probanden aus drei Gruppen."
        s = "Bei näherer Betrachtung fällt auf, dass sich für zehn Probanden die Laune nicht geändert hat."
        self.assertEqual(self.ersatz([vor, s], 2, "strohmann_aufbau"), coach.STROHMANN_OHNE_KONTRAST)

    def test_strohmann_mit_kontrast(self):
        vor = "Viele Studien halten den Effekt für stabil."
        s = "Bei näherer Betrachtung zeigt sich jedoch, dass der Effekt nur in einer Gruppe auftritt."
        self.assertIn("naheliegende Sicht", self.ersatz([vor, s], 2, "strohmann_aufbau"))
        vor = "Viele Studien halten den Effekt für stabil, doch die Daten sind dünn."
        s = "Bei näherer Betrachtung fällt auf, dass der Effekt nur in einer Gruppe auftritt."
        self.assertIn("naheliegende Sicht", self.ersatz([vor, s], 2, "strohmann_aufbau"))

    def test_darueber_hinaus_mitten_im_satz(self):
        a = "Die Teilnehmer schätzen die Teilung der Aufgaben sowie die eigene Motivation und darüber hinaus den Kundenbezug."
        b = "Einige Mitarbeiter wünschen sich darüber hinaus mehr Austausch mit den Kollegen im Team."
        c = "Darüber hinaus wünschen sich einige Mitarbeiter mehr Austausch mit den Kollegen im Team."
        self.assertEqual(self.ersatz([a], 1, "darueber_hinaus"), coach.DARUEBER_HINAUS_UND)
        self.assertEqual(self.ersatz([b], 1, "darueber_hinaus"), coach.DARUEBER_HINAUS_MITTE)
        self.assertIn("Streichen, wenn der Satz erkennbar etwas Neues anfügt", self.ersatz([c], 1, "darueber_hinaus"))

    def test_muster_im_band_nur_ohne_modellziel(self):
        L = coach.Lauf(KI_TEXT, None)
        km = L.kz["ki_muster_pro_1000"]
        L.kz["ki_muster_pro_1000"] = dict(km, wert=km["mensch_p75"] - 0.1)
        L.bew = dict(L.bew, p_mensch=0.95)
        self.assertFalse(coach.muster_im_band_erlaubt(L))
        L.bew = dict(L.bew, p_mensch=0.4)
        self.assertTrue(coach.muster_im_band_erlaubt(L))
        L.bew = dict(L.bew, p_mensch=0.95)
        L.kz["ki_muster_pro_1000"] = dict(km, wert=km["mensch_p75"] + 0.1)
        self.assertTrue(coach.muster_im_band_erlaubt(L))

    def test_am_ziel_keine_muster_im_band(self):
        echt = coach.analyse.analysiere_und_bewerte

        def fake(*a, **k):
            erg, bew = echt(*a, **k)
            for z in bew["kennzahlen"]:
                if z["id"] == "ki_muster_pro_1000":
                    z.update(wert=3.0, status="gruen", unsicher=False)
            return erg, dict(bew, p_mensch=0.99, score_ki=95, score=95)
        with mock.patch.object(coach.analyse, "analysiere_und_bewerte", fake):
            c = coach.coache(KI_TEXT, None, 15)
        self.assertTrue(c["ziel_erreicht"])
        self.assertFalse([h for h in c["hinweise"] if h["typ"] == "floskel"])


# ---------------------------------------------------------------------------------------------------------------------------
# 9. Themenbedingtes Funktionswort-Profil
# ---------------------------------------------------------------------------------------------------------------------------

class Themenbedingt(unittest.TestCase):
    def stellen(self, notw_sie, notw_als, umbau=0, artikel=0):
        st = {"sie": {"notwendig": {"Verweis": list(range(1, notw_sie + 1))}, "umbaubar": {}, "anzahl": notw_sie},
              "als": {"notwendig": {"Rolle/Funktion": list(range(1, notw_als + 1))},
                      "umbaubar": ({"„dient als“ umbauen": list(range(1, umbau + 1))} if umbau else {}), "anzahl": notw_als + umbau}}
        if artikel:
            st["die"] = {"notwendig": {"Artikel/Präposition": list(range(1, artikel + 1))}, "umbaubar": {}, "anzahl": artikel}
        return st

    def lauf(self, st):
        L = coach.Lauf(KI_TEXT, None)
        return L, mock.patch.multiple(coach, fw_uebernutzt=lambda L_: list(st), fw_stellen=lambda L_, w: st)

    def test_ueberwiegend_notwendig(self):
        # ssoar-5763 (v7-Prüfung): „sie“ 15× und „als“ 15× notwendig – trotzdem „in eigenen Worten neu schreiben“
        L, p = self.lauf(self.stellen(15, 14, umbau=1))
        with p:
            th = coach.fw_themenbedingt(L)
        self.assertIsNotNone(th)
        self.assertEqual(th["anteil"], 0.97)
        self.assertIn("überwiegend themenbedingt", th["text"])
        self.assertIn("„sie“ als Verweis", th["text"])

    def test_nicht_themenbedingt(self):
        L, p = self.lauf(self.stellen(5, 5, umbau=5))
        with p:
            self.assertIsNone(coach.fw_themenbedingt(L))
        L, p = self.lauf(self.stellen(2, 2, artikel=20))  # Artikel sind Grammatik, nicht Thema
        with p:
            self.assertIsNone(coach.fw_themenbedingt(L))

    def test_diagnose_ohne_neuschreib_empfehlung(self):
        L = coach.Lauf(KI_TEXT, None)
        L.hinweise = []
        L.messungen = [{"p_mensch": 0.0}, {"p_mensch": L.bew["p_mensch"]}]  # Stagnation
        th = {"anteil": 0.94, "bsp": "„sie“ als Verweis", "text": coach.FW_THEMA.format(pct=94, bsp="„sie“ als Verweis")}
        with mock.patch.object(coach, "fw_themenbedingt", lambda L_: th), mock.patch.object(coach, "fw_offen", lambda L_: {}):
            d = coach._diagnose(L, [], 0.85)
        self.assertIsNotNone(d)
        fw = next(z for z in d["beitraege"] if z["id"] == "fw_profil_llr_pro_1000")
        self.assertEqual(fw["wie"], "themenbedingt")
        self.assertEqual(d["fw_absaetze"], [])
        txt = "\n".join(coach.diagnose_text(d))
        self.assertIn("überwiegend themenbedingt", txt)
        self.assertNotIn("in eigenen Worten neu zu schreiben", txt)
        self.assertNotIn("am ehesten Absatz", txt)


if __name__ == "__main__":
    unittest.main()
