"""Regression checks for source traceability and Python code preservation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))

from src.ingestion import load_pdf, normalize_text, remove_running_header


class NormalizationTests(unittest.TestCase):
    def test_unicode_paragraphs_and_indentation(self):
        raw = "\r\nTie\u0302\u0301ng Vie\u0323\u0302t  \r\n\r\n\r\ndef f():\r\n    return 3 // 2  \r\n"
        text = normalize_text(raw)
        self.assertTrue(text.startswith("Tiếng Việt\n\ndef f():"))
        self.assertIn("\n    return 3 // 2", text)
        self.assertEqual(normalize_text(text), text)

    def test_operators_and_line_end_hyphens_are_retained(self):
        text = "a != b; x % 2; a <= b\nwell-\nknown"
        self.assertEqual(normalize_text(text), text)

    def test_header_removal_keeps_section_and_code_indent(self):
        text = "20       Chapter 3. Functions\n\ndef f():\n    pass"
        self.assertEqual(remove_running_header(text, 20, 3), "def f():\n    pass")
        text = "3.3. Composition      19\n\n3.3    Composition\nbody"
        self.assertEqual(remove_running_header(text, 19, 3), "3.3    Composition\nbody")

    def test_unverified_header_is_not_removed(self):
        text = "20       Chapter 3. Functions\nbody"
        self.assertEqual(remove_running_header(text, 21, 3), text)
        self.assertEqual(remove_running_header("Chapter 3\n\nFunctions", 17, 3), "Chapter 3\n\nFunctions")


class LoaderTests(unittest.TestCase):
    def test_blank_pages_keep_physical_page_numbers_and_log(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blank.pdf"
            log = Path(directory) / "errors.jsonl"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            writer.add_blank_page(width=200, height=200)
            writer.write(path)
            pages = load_pdf(path, "sample", "local-test", error_log=log)
            self.assertEqual([page.page for page in pages], [1, 2])
            self.assertTrue(all(page.text == "" for page in pages))
            issues = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual([issue["page"] for issue in issues], [1, 2])

    def test_missing_source_raises_and_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "errors.jsonl"
            with self.assertRaises(FileNotFoundError):
                load_pdf(Path(directory) / "missing.pdf", "sample", "local-test", error_log=log)
            issue = json.loads(log.read_text())
            self.assertEqual(issue["kind"], "load_error")

    def test_missing_poppler_fails_explicitly(self):
        with patch("src.ingestion.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "pdftotext is required"):
                load_pdf(Path("unused.pdf"), "sample", "local-test")


class PreparedCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = STARTER.parent
        cls.rows = [json.loads(line) for line in
                    (cls.root / "data/processed/pages.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_content_count_traceability_and_metadata(self):
        manifest = json.loads((self.root / "data/manifest.json").read_text())
        included = [p for p in manifest["pages"] if p["included"]]
        self.assertEqual(len(self.rows), 40)
        self.assertEqual([r["page"] for r in self.rows], [p["page"] for p in included])
        self.assertEqual(len({r["metadata"]["page_id"] for r in self.rows}), 40)
        self.assertEqual({r["metadata"]["chapter"] for r in self.rows}, {2, 3, 5, 7, 10, 11})
        for row, page in zip(self.rows, included):
            self.assertEqual(len(row["text"]), row["metadata"]["char_count"])
            self.assertEqual(len(row["text"]), page["normalized_char_count"])
            self.assertEqual(row["metadata"]["printed_page"], row["page"] - 22)
            self.assertEqual(row["document_id"], manifest["source_id"])
            self.assertEqual(row["source"], manifest["source_url"])

    def test_real_python_indentation_survives(self):
        page = next(r for r in self.rows if r["page"] == 87)
        self.assertIn("def countdown(n):\n    while n > 0:\n        print(n)", page["text"])
        self.assertIn("if n % 2 == 0:", page["text"])


if __name__ == "__main__":
    unittest.main()
