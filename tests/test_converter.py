from pathlib import Path
import shutil
import tempfile
import unittest

from click.testing import CliRunner
from lxml import etree as ET

from ladas2tei.main import main
from ladas2tei.models import AltoBlock, AltoPage, TeiConversion
from ladas2tei.ordering import order_page, order_theatre_page
from ladas2tei.tei import build_tei


FIXTURE_DIR = Path(__file__).parent / "test_image"
SIMPLE_DIR = FIXTURE_DIR / "simple_page"
MULTIPLE_DIR = FIXTURE_DIR / "multiple_page"
ARTICLE_DIR = FIXTURE_DIR / "article"
THEATRE_DIR = FIXTURE_DIR / "theatre"
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


SIMPLE_CASES = [
    "2011LYO30049_88",
    "bd6t5333271j_f25",
    "bourgey_12148-bpt6k9779838f_f60",
    "govreport_jo-debats_1965_05_08_8",
]


class LadasToTeiSimpleAndMultipleTest(unittest.TestCase):
    def test_simple_page_outputs_have_reference_body_structure(self):
        for name in SIMPLE_CASES:
            with self.subTest(name=name):
                generated = build_tei(
                    [SIMPLE_DIR / "alto" / f"{name}.xml"],
                    TeiConversion(title=name),
                )
                expected = ET.parse(str(SIMPLE_DIR / "tei" / f"{name}.xml"))

                self.assertCountEqual(body_signature(expected), body_signature(generated))
                self.assertEqual([f"{name}.xml"], pb_facsimiles(generated))

    def test_multiple_page_output_has_reference_body_structure(self):
        generated = build_tei(
            [
                MULTIPLE_DIR / "alto" / "bd6t53694697_105.xml",
                MULTIPLE_DIR / "alto" / "bd6t53694697_f106.xml",
            ],
            TeiConversion(title="bd6t53694697_105_106"),
        )
        expected = ET.parse(str(MULTIPLE_DIR / "tei" / "bd6t53694697_105_106.xml"))

        self.assertCountEqual(body_signature(expected), body_signature(generated))
        self.assertEqual(["bd6t53694697_105.xml", "bd6t53694697_f106.xml"], pb_facsimiles(generated))

    def test_representative_reference_features_are_serialized(self):
        multiple = build_tei(
            [
                MULTIPLE_DIR / "alto" / "bd6t53694697_105.xml",
                MULTIPLE_DIR / "alto" / "bd6t53694697_f106.xml",
            ],
            TeiConversion(title="bd6t53694697_105_106"),
        )
        catalogue = build_tei(
            [SIMPLE_DIR / "alto" / "bourgey_12148-bpt6k9779838f_f60.xml"],
            TeiConversion(title="bourgey_12148-bpt6k9779838f_f60"),
        )

        self.assertTrue(multiple.xpath('//tei:fw[@type="digitisation-artefact"]', namespaces=TEI_NS))
        self.assertEqual("105", multiple.xpath('string(//tei:milestone[@unit="page"][1]/@n)', namespaces=TEI_NS))
        self.assertTrue(catalogue.xpath("//tei:list/tei:item", namespaces=TEI_NS))

    def test_article_page_preserves_article_and_table_structure(self):
        generated = build_tei(
            [ARTICLE_DIR / "alto" / "bd6t545006677_1.xml"],
            TeiConversion(title="bd6t545006677_1"),
        )

        article_heads = [
            head.xpath("string()", namespaces=TEI_NS).strip()
            for head in generated.xpath('//tei:div[@type="article"]/tei:head', namespaces=TEI_NS)
        ]
        table_text = " ".join(generated.xpath('//tei:figure[@type="table"]//text()', namespaces=TEI_NS))
        article_texts = [
            " ".join(article.xpath(".//text()", namespaces=TEI_NS))
            for article in generated.xpath('//tei:div[@type="article"]', namespaces=TEI_NS)
        ]

        self.assertEqual(["Chin qu' nous donnonscheull' fos ichi.", "Salut!!!", "L’UNION"], article_heads)
        self.assertIn("ABONN'MINTS", table_text)
        self.assertIn("ANNONCES :", table_text)
        self.assertIn("Un an. ... Tros francs.", table_text)
        self.assertIn("L'line. . . . . . . . . Chinq sous.", table_text)
        self.assertIn("L' Rédaction.", article_texts[1])
        self.assertIn("faires à eusses", article_texts[2])

    def test_article_mode_wraps_content_in_article_div(self):
        generated = build_tei(
            [SIMPLE_DIR / "alto" / "bd6t5333271j_f25.xml"],
            TeiConversion(title="bd6t5333271j_f25", article=True),
        )

        body_children = generated.xpath("/tei:TEI/tei:text/tei:body/*", namespaces=TEI_NS)
        article_children = generated.xpath(
            "/tei:TEI/tei:text/tei:body/tei:div[@type='article']/tei:div",
            namespaces=TEI_NS,
        )

        self.assertEqual(1, len(body_children))
        self.assertEqual("article", body_children[0].get("type"))
        self.assertGreaterEqual(len(article_children), 1)
        self.assertFalse(
            generated.xpath(
                "/tei:TEI/tei:text/tei:body/tei:div[not(@type='article')]",
                namespaces=TEI_NS,
            )
        )
        self.assertEqual(["bd6t5333271j_f25.xml"], pb_facsimiles(generated))

    def test_cli_article_option_wraps_content_in_article_div(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "article.xml"
            result = CliRunner().invoke(
                main,
                [
                    str(SIMPLE_DIR / "alto" / "bd6t5333271j_f25.xml"),
                    "-o",
                    str(output),
                    "--title",
                    "Article",
                    "--article",
                ],
            )

            self.assertEqual(0, result.exit_code, result.output)
            generated = ET.parse(str(output))
            article_children = generated.xpath(
                "/tei:TEI/tei:text/tei:body/tei:div[@type='article']/tei:div",
                namespaces=TEI_NS,
            )
            self.assertGreaterEqual(len(article_children), 1)

    def test_theatre_mode_serializes_speeches_and_verse_lines(self):
        generated = build_tei(
            [THEATRE_DIR / "alto" / "theatre_1699_bpt6k97930799_f38.xml"],
            TeiConversion(title="theatre_1699_bpt6k97930799_f38", theatre=True),
        )

        speakers = [
            speaker.xpath("string()", namespaces=TEI_NS).strip()
            for speaker in generated.xpath("//tei:sp/tei:speaker", namespaces=TEI_NS)
        ]
        first_verse_lines = [
            line.xpath("string()", namespaces=TEI_NS).strip()
            for line in generated.xpath("//tei:sp[1]/tei:lg/tei:l", namespaces=TEI_NS)
        ]

        self.assertEqual("14", generated.xpath("string(//tei:milestone[@unit='page'][1]/@n)", namespaces=TEI_NS))
        self.assertEqual("MYRTIL ET MELICERTE,", generated.xpath("string(//tei:fw[@type='runningTitle'][1])", namespaces=TEI_NS))
        self.assertEqual("DAPHNE'.", speakers[0])
        self.assertEqual("EROXENE.", speakers[1])
        self.assertEqual(9, len(speakers))
        self.assertEqual("Ah que de badinage!", first_verse_lines[0])
        self.assertEqual("Tes yeux le connoistront d’abord.", first_verse_lines[-1])
        self.assertFalse(generated.xpath("//tei:sp/tei:head", namespaces=TEI_NS))

    def test_theatre_mode_allows_prose_paragraphs_and_stage_directions(self):
        with tempfile.TemporaryDirectory() as tmp:
            alto_path = Path(tmp) / "theatre_prose.xml"
            alto_path.write_text(THEATRE_PROSE_ALTO, encoding="utf-8")

            generated = build_tei([alto_path], TeiConversion(title="theatre_prose", theatre=True))

        self.assertEqual(1, len(generated.xpath("//tei:sp", namespaces=TEI_NS)))
        self.assertEqual("ALCESTE.", generated.xpath("string(//tei:sp/tei:speaker)", namespaces=TEI_NS).strip())
        self.assertEqual(
            ["Premier paragraphe.", "Second paragraphe."],
            [
                paragraph.xpath("string()", namespaces=TEI_NS).strip()
                for paragraph in generated.xpath("//tei:sp/tei:p", namespaces=TEI_NS)
            ],
        )
        self.assertEqual(
            "Il s'assied.",
            generated.xpath("string(//tei:sp/tei:stage)", namespaces=TEI_NS).strip(),
        )
        self.assertFalse(generated.xpath("//tei:sp/tei:p[@rend='styled']", namespaces=TEI_NS))

    def test_theatre_ordering_reads_columns_before_vertical_position(self):
        blocks = [
            AltoBlock("MainZone-Head", ("LEFT.",), hpos=100, vpos=100, width=80, height=20),
            AltoBlock("MainZone-P", ("left first",), hpos=100, vpos=140, width=80, height=20),
            AltoBlock("MainZone-P", ("left second",), hpos=100, vpos=180, width=80, height=20),
            AltoBlock("MainZone-P", ("left third",), hpos=100, vpos=220, width=80, height=20),
            AltoBlock("MainZone-P", ("left fourth",), hpos=100, vpos=260, width=80, height=20),
            AltoBlock("MainZone-Head", ("RIGHT.",), hpos=700, vpos=120, width=80, height=20),
            AltoBlock("MainZone-P", ("right first",), hpos=700, vpos=160, width=80, height=20),
            AltoBlock("MainZone-P", ("right second",), hpos=700, vpos=200, width=80, height=20),
            AltoBlock("MainZone-P", ("right third",), hpos=700, vpos=240, width=80, height=20),
            AltoBlock("MainZone-P", ("right fourth",), hpos=700, vpos=280, width=80, height=20),
        ]

        ordered = order_theatre_page(AltoPage(Path("columns.xml"), tuple(blocks)))

        self.assertEqual(
            ["LEFT.", "left first", "left second", "left third", "left fourth", "RIGHT."],
            [block.text for block in ordered.blocks[:6]],
        )

    def test_ordering_uses_running_title_coordinates_for_page_position(self):
        blocks = [
            AltoBlock("MainZone-P", ("body first",), hpos=100, vpos=120, width=300, height=20),
            AltoBlock("RunningTitleZone", ("TOP TITLE",), hpos=100, vpos=40, width=300, height=20),
            AltoBlock("RunningTitleZone", ("MID TITLE",), hpos=100, vpos=500, width=300, height=20),
            AltoBlock("MainZone-P", ("body second",), hpos=100, vpos=540, width=300, height=20),
        ]

        ordered = order_page(AltoPage(Path("running_title.xml"), tuple(blocks)))

        self.assertEqual(["TOP TITLE", "body first", "MID TITLE", "body second"], [block.text for block in ordered.blocks])

    def test_ordering_reads_multiple_columns_left_to_right_then_top_to_bottom(self):
        blocks = [
            AltoBlock("MainZone-P", ("left 1",), hpos=100, vpos=100, width=80, height=20),
            AltoBlock("MainZone-P", ("middle 1",), hpos=500, vpos=90, width=80, height=20),
            AltoBlock("MainZone-P", ("right 1",), hpos=900, vpos=80, width=80, height=20),
            AltoBlock("MainZone-P", ("left 2",), hpos=100, vpos=140, width=80, height=20),
            AltoBlock("MainZone-P", ("middle 2",), hpos=500, vpos=130, width=80, height=20),
            AltoBlock("MainZone-P", ("right 2",), hpos=900, vpos=120, width=80, height=20),
            AltoBlock("MainZone-P", ("left 3",), hpos=100, vpos=180, width=80, height=20),
            AltoBlock("MainZone-P", ("middle 3",), hpos=500, vpos=170, width=80, height=20),
            AltoBlock("MainZone-P", ("right 3",), hpos=900, vpos=160, width=80, height=20),
        ]

        ordered = order_page(AltoPage(Path("three_columns.xml"), tuple(blocks)))

        self.assertEqual(
            ["left 1", "left 2", "left 3", "middle 1", "middle 2", "middle 3", "right 1", "right 2", "right 3"],
            [block.text for block in ordered.blocks],
        )

    def test_cli_theatre_option_serializes_speeches(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "theatre.xml"
            result = CliRunner().invoke(
                main,
                [
                    str(THEATRE_DIR / "alto" / "theatre_1699_bpt6k97930799_f38.xml"),
                    "-o",
                    str(output),
                    "--title",
                    "Theatre",
                    "--theatre",
                ],
            )

            self.assertEqual(0, result.exit_code, result.output)
            generated = ET.parse(str(output))
            self.assertEqual(9, len(generated.xpath("//tei:sp", namespaces=TEI_NS)))
            self.assertEqual("DAPHNE'.", generated.xpath("string(//tei:sp[1]/tei:speaker)", namespaces=TEI_NS).strip())

    def test_cli_converts_one_document_directory_with_alto_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "single.xml"
            result = CliRunner().invoke(
                main,
                [
                    str(MULTIPLE_DIR),
                    "-o",
                    str(output),
                    "--title",
                    "bd6t53694697_105_106",
                ],
            )

            self.assertEqual(0, result.exit_code, result.output)
            generated = ET.parse(str(output))
            self.assertEqual(["bd6t53694697_105.xml", "bd6t53694697_f106.xml"], pb_facsimiles(generated))

    def test_cli_converts_parent_directory_to_one_tei_per_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "corpus"
            output = Path(tmp) / "tei"
            shutil.copytree(MULTIPLE_DIR, parent / "doc_multiple")
            shutil.copytree(SIMPLE_DIR, parent / "doc_simple")
            metadata_csv = Path(tmp) / "metadata.csv"
            metadata_csv.write_text(
                "file_name,title\n"
                "doc_multiple,Document multiple\n"
                "doc_simple,Document simple\n",
                encoding="utf-8",
            )

            result = CliRunner().invoke(
                main,
                [
                    str(parent),
                    "-o",
                    str(output),
                    "--metadata-csv",
                    str(metadata_csv),
                ],
            )

            self.assertEqual(0, result.exit_code, result.output)
            self.assertTrue((output / "doc_multiple.xml").exists())
            self.assertTrue((output / "doc_simple.xml").exists())

            multiple = ET.parse(str(output / "doc_multiple.xml"))
            simple = ET.parse(str(output / "doc_simple.xml"))
            self.assertEqual(["bd6t53694697_105.xml", "bd6t53694697_f106.xml"], pb_facsimiles(multiple))
            self.assertEqual(SIMPLE_CASES, [Path(facs).stem for facs in pb_facsimiles(simple)])

    def test_cli_requires_metadata_csv_for_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "corpus"
            shutil.copytree(MULTIPLE_DIR, parent / "doc_multiple")

            result = CliRunner().invoke(main, [str(parent)])

            self.assertNotEqual(0, result.exit_code)
            self.assertIn("--metadata-csv est obligatoire", result.output)


def body_signature(tree: ET._ElementTree) -> list[tuple[str, tuple[tuple[str, str], ...]]]:
    body = tree.getroot().xpath("//tei:body", namespaces=TEI_NS)[0]
    return [
        (
            ET.QName(element).localname,
            tuple(sorted((ET.QName(name).localname, value) for name, value in element.attrib.items())),
        )
        for element in body.iter()
        if ET.QName(element).localname not in {"lb", "pb"}
    ]


def pb_facsimiles(tree: ET._ElementTree) -> list[str]:
    return tree.xpath("//tei:pb/@facs", namespaces=TEI_NS)


THEATRE_PROSE_ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
  <Tags>
    <OtherTag ID="head" LABEL="MainZone-Head"/>
    <OtherTag ID="p" LABEL="MainZone-P"/>
    <OtherTag ID="stage" LABEL="MainZone-PStyled"/>
  </Tags>
  <Layout>
    <Page>
      <PrintSpace>
        <TextBlock ID="b1" HPOS="100" VPOS="100" WIDTH="100" HEIGHT="20" TAGREFS="head">
          <TextLine><String CONTENT="ALCESTE."/></TextLine>
        </TextBlock>
        <TextBlock ID="b2" HPOS="100" VPOS="130" WIDTH="300" HEIGHT="20" TAGREFS="p">
          <TextLine><String CONTENT="Premier paragraphe."/></TextLine>
        </TextBlock>
        <TextBlock ID="b3" HPOS="100" VPOS="160" WIDTH="300" HEIGHT="20" TAGREFS="p">
          <TextLine><String CONTENT="Second paragraphe."/></TextLine>
        </TextBlock>
        <TextBlock ID="b4" HPOS="100" VPOS="190" WIDTH="300" HEIGHT="20" TAGREFS="stage">
          <TextLine><String CONTENT="Il s'assied."/></TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>
"""


if __name__ == "__main__":
    unittest.main()
