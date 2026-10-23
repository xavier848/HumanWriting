"""Tests für Messkorrekturen aus den MBS-Formvorgaben: englische Absätze (Abstract), englische Verzeichnis-
Überschriften (Reference List, Appendix, Table of Contents) und eingerückte Blockzitate in .docx."""
import os
import sys
import tempfile
import unittest
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugins", "humanwriting-de", "skills", "text-analyse", "scripts"))
import analyse  # noqa: E402

DEUTSCH = ("Viele mittelständische Unternehmen investieren derzeit verstärkt in die betriebliche Ausbildung, um dem "
           "wachsenden Fachkräftemangel zu begegnen. Die Kosten der Ausbildung steigen allerdings seit einigen Jahren "
           "deutlich, wie die Befragung von 240 Betrieben zeigt.")
ABSTRACT = ("This paper examines the effect of employer branding on the retention of employees in medium-sized "
            "companies. Based on a survey of 240 employees, it shows that perceived culture matters more than pay.")


class EnglischeAbsaetze(unittest.TestCase):
    def test_ist_englisch(self):
        self.assertTrue(analyse.ist_englisch(ABSTRACT))
        self.assertFalse(analyse.ist_englisch(DEUTSCH))
        # deutscher Absatz mit englischem Zitat bleibt deutsch
        self.assertFalse(analyse.ist_englisch(
            DEUTSCH + " Nach Lievens (2007) ist es „the package of functional, economic and psychological benefits "
                      "provided by employment and identified with the employing company“."))
        self.assertFalse(analyse.ist_englisch("The results of the study."))  # zu kurz für ein Urteil
        # Anglizismen im deutschen Fachtext
        self.assertFalse(analyse.ist_englisch(
            "Das Employer Branding und das Onboarding gelten im Human Resource Management als Teil des Talent "
            "Managements, wobei Social Media und Recruiting Events die Candidate Experience prägen."))

    def test_abstract_wird_nicht_gemessen(self):
        e = analyse.analysiere_text(f"# Abstract\n\n{ABSTRACT}\n\n# 1 Einleitung\n\n{DEUTSCH}\n")
        self.assertEqual(e["info"]["englische_absaetze"], 1)
        self.assertEqual(e["info"]["absaetze"], 1)
        self.assertNotIn("employer", " ".join(s["text"] for s in e["saetze"]).lower())

    def test_bericht_nennt_ignorierte_absaetze(self):
        text = f"{ABSTRACT}\n\n{ABSTRACT}\n\n{DEUTSCH}\n\n{DEUTSCH}\n"
        e = analyse.analysiere_text(text)
        self.assertIn("2 englische Absätze ignoriert", analyse.bericht_markdown(e, {"verfuegbar": False}))


class EnglischeUeberschriften(unittest.TestCase):
    def test_reference_list_und_appendix_beenden_den_fliesstext(self):
        for kopf in ("Reference List", "References", "List of References", "Appendix", "Appendices",
                     "Submission Declaration", "Statutory Declaration", "Declaration of Authorship"):
            with self.subTest(kopf=kopf):
                text = ("# 1 Einleitung\n\n" + (DEUTSCH + "\n\n") * 8 + f"# {kopf}\n\n"
                        "Die Abschlussarbeit habe ich selbständig verfasst und keine anderen Hilfsmittel benutzt.\n")
                e = analyse.analysiere_text(text)
                self.assertTrue(e["info"]["literatur_abgeschnitten"])
                self.assertEqual(e["info"]["absaetze"], 8)

    def test_table_of_contents_wird_uebersprungen(self):
        for kopf in ("Table of Contents", "Contents", "List of Figures", "Index of Tables", "List of Abbreviations"):
            with self.subTest(kopf=kopf):
                self.assertTrue(analyse.INHALTSVERZEICHNIS_UEBERSCHRIFT.match(kopf))
        self.assertFalse(analyse.INHALTSVERZEICHNIS_UEBERSCHRIFT.match("Contents of the survey"))


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def absatz(text, links=None, haengend=None, stil=None):
    ppr = ""
    if stil or links is not None:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{stil}"/>' if stil else "")
        if links is not None:
            ppr += f'<w:ind w:left="{links}"' + (f' w:hanging="{haengend}"' if haengend else "") + "/>"
        ppr += "</w:pPr>"
    return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"


ZITAT = ("Als Arbeitgebermarke gilt das Bündel funktionaler, wirtschaftlicher und psychologischer Vorteile, das ein "
         "Arbeitgeber seinen Beschäftigten bietet und das diese mit dem Unternehmen verbinden. (Ambler &amp; Barrow, 1996, S. 187)")


class DocxBlockzitate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def docx(self, *absaetze, styles=None):
        pfad = os.path.join(self.tmp.name, "t.docx")
        with zipfile.ZipFile(pfad, "w") as z:
            z.writestr("word/document.xml", f"<w:document {W}><w:body>{''.join(absaetze)}</w:body></w:document>")
            if styles:
                z.writestr("word/styles.xml", f"<w:styles {W}>{styles}</w:styles>")
        return analyse.lies_docx(pfad)

    def test_eingeruecktes_blockzitat(self):
        text = self.docx(absatz(DEUTSCH), absatz(ZITAT, links=1134), absatz(DEUTSCH))
        teile = text.split("\n\n")
        self.assertTrue(teile[1].startswith("> "))
        self.assertFalse(teile[0].startswith(">") or teile[2].startswith(">"))
        e = analyse.analysiere_text(text)
        self.assertEqual(e["info"]["zitatbloecke"], 1)
        self.assertEqual(e["info"]["absaetze"], 2)

    def test_zitat_formatvorlage(self):
        stile = ('<w:style w:type="paragraph" w:styleId="Zitat"><w:name w:val="Quote"/></w:style>')
        text = self.docx(absatz(DEUTSCH), absatz(ZITAT, stil="Zitat"), styles=stile)
        self.assertTrue(text.split("\n\n")[1].startswith("> "))

    def test_gleich_eingerueckter_fliesstext_ist_kein_zitat(self):
        # Vorlagen, die den ganzen Fließtext links einrücken, dürfen nicht alles ausblenden
        text = self.docx(absatz(DEUTSCH, links=720), absatz(DEUTSCH, links=720), absatz(DEUTSCH, links=720))
        self.assertNotIn(">", text)

    def test_haengender_einzug_ist_kein_zitat(self):
        text = self.docx(absatz(DEUTSCH), absatz(DEUTSCH), absatz(ZITAT, links=1134, haengend=1134))
        self.assertNotIn(">", text)

    def test_kleiner_einzug_bleibt_fliesstext(self):
        text = self.docx(absatz(DEUTSCH), absatz(DEUTSCH, links=284), absatz(DEUTSCH))
        self.assertNotIn(">", text)


if __name__ == "__main__":
    unittest.main()
