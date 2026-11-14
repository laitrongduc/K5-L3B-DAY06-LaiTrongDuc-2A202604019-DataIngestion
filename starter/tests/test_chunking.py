"""Check content preservation, source offsets and stable identities."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))

from src.chunking import by_paragraph, fixed_size, fit_token_limit
from src.models import DocumentPage


class ChunkingTests(unittest.TestCase):
    def page(self, text):
        return DocumentPage("sample", "sample.pdf", 3, text,
                            {"chapter": 2, "char_count": len(text), "nested": {"value": 1}})

    def test_fixed_windows_and_overlap(self):
        page = self.page("abcdefghijklm")
        chunks = fixed_size(page, 6, 2)
        self.assertEqual([c.text for c in chunks], ["abcdef", "efghij", "ijklm"])
        self.assertEqual([(c.metadata["start_char"], c.metadata["end_char"]) for c in chunks],
                         [(0, 6), (4, 10), (8, 13)])

    def test_empty_or_whitespace_only_pages_produce_no_chunks(self):
        for text in ("", " \n\n    "):
            self.assertEqual(fixed_size(self.page(text), 10, 2), [])
            self.assertEqual(by_paragraph(self.page(text), 10), [])

    def test_invalid_sizes_and_overlap_are_rejected(self):
        for size, overlap in ((0, 0), (5, -1), (5, 5), (5, 6), (True, 0)):
            with self.assertRaises(ValueError):
                fixed_size(self.page("text"), size, overlap)
        for maximum in (0, -1, True):
            with self.assertRaises(ValueError):
                by_paragraph(self.page("text"), maximum)

    def test_paragraphs_are_packed_without_changing_text(self):
        page = self.page("Alpha.\n\nBeta.\n\nGamma.")
        chunks = by_paragraph(page, 16)
        self.assertEqual([c.text for c in chunks], ["Alpha.\n\nBeta.\n\n", "Gamma."])
        self.assertEqual("".join(c.text for c in chunks), page.text)

    def test_oversized_paragraph_and_long_code_line_are_bounded(self):
        page = self.page("def f():\n    value = '" + "x" * 90 + "'\n    return value\n\nNext paragraph.")
        chunks = by_paragraph(page, 40)
        self.assertTrue(all(0 < len(c.text) <= 40 for c in chunks))
        self.assertEqual("".join(c.text for c in chunks), page.text)
        for c in chunks:
            self.assertEqual(c.text, page.text[c.metadata["start_char"]:c.metadata["end_char"]])

    def test_ids_are_stable_but_change_with_content_or_parameters(self):
        page = self.page("abcdefghijklm")
        ids = [c.chunk_id for c in fixed_size(page, 6, 2)]
        self.assertEqual(ids, [c.chunk_id for c in fixed_size(page, 6, 2)])
        self.assertTrue(set(ids).isdisjoint(c.chunk_id for c in fixed_size(page, 7, 2)))
        self.assertTrue(set(ids).isdisjoint(c.chunk_id for c in fixed_size(self.page(page.text + "!"), 6, 2)))

    def test_metadata_is_independent_and_lengths_are_chunk_lengths(self):
        page = self.page("Tiếng Việt\n    print('xin chào')")
        for c in [*fixed_size(page, 15, 3), *by_paragraph(page, 15)]:
            self.assertEqual(c.metadata["chapter"], 2)
            self.assertEqual((c.document_id, c.source, c.page), ("sample", "sample.pdf", 3))
            self.assertEqual(c.metadata["document_id"], c.document_id)
            self.assertEqual(c.metadata["source"], c.source)
            self.assertEqual(c.metadata["page"], c.page)
            self.assertEqual(c.metadata["char_count"], len(c.text))
            self.assertEqual(c.metadata["page_char_count"], len(page.text))
            c.metadata["nested"]["value"] = 99
            self.assertEqual(page.metadata["nested"]["value"], 1)

    def test_real_corpus_has_exact_spans_and_full_coverage(self):
        pages = [DocumentPage(**json.loads(line)) for line in
                 (ROOT / "data/processed/pages.jsonl").read_text().splitlines()]
        for method in (lambda p: fixed_size(p, 500, 50), lambda p: by_paragraph(p, 500)):
            ids = []
            for page in pages:
                chunks = method(page)
                self.assertTrue(chunks)
                covered = set()
                for c in chunks:
                    start, end = c.metadata["start_char"], c.metadata["end_char"]
                    self.assertEqual(c.text, page.text[start:end])
                    self.assertLessEqual(len(c.text), 500)
                    self.assertEqual(c.metadata["chapter"], page.metadata["chapter"])
                    covered.update(range(start, end))
                    ids.append(c.chunk_id)
                self.assertEqual(covered, set(range(len(page.text))))
            self.assertEqual(len(ids), len(set(ids)))

    def test_fixed_coherence_positions_are_covered_by_both_chunkers(self):
        pages = {(p["document_id"], p["page"]): DocumentPage(**p) for p in map(json.loads,
                 (ROOT / "data/processed/pages.jsonl").read_text().splitlines())}
        samples = [json.loads(line) for line in (ROOT / "benchmark/coherence_samples.jsonl").read_text().splitlines()]
        for sample in samples:
            page = pages[sample["source_id"], sample["page"]]
            for chunks in (fixed_size(page, 500, 50), by_paragraph(page, 500)):
                self.assertTrue(any(c.metadata["start_char"] <= sample["anchor_offset"] < c.metadata["end_char"] for c in chunks))

    def test_token_limit_preserves_offsets_and_keeps_fitting_tail_whole(self):
        page = self.page("abc def g.")
        chunks = fit_token_limit(page, fixed_size(page, 100, 0), len, 6, "test-tokenizer")
        self.assertEqual([c.text for c in chunks], ["abc ", "def g."])
        self.assertEqual("".join(c.text for c in chunks), page.text)
        self.assertTrue(all(c.metadata["token_count"] <= 6 for c in chunks))
        for c in chunks:
            self.assertEqual(c.text, page.text[c.metadata["start_char"]:c.metadata["end_char"]])

    def test_token_limit_rejects_impossible_budget(self):
        page = self.page("abc")
        with self.assertRaises(ValueError):
            fit_token_limit(page, fixed_size(page, 100, 0), lambda text: len(text) + 2, 2, "test-tokenizer")


if __name__ == "__main__":
    unittest.main()
