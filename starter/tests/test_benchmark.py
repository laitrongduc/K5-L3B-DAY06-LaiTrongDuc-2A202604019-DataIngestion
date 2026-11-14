"""Reject benchmark mistakes that would invalidate later retrieval metrics."""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter/scripts"))

import validate_benchmark as validation


class BenchmarkValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = validation.read_jsonl(ROOT / "benchmark/questions.jsonl")
        cls.pages = {(r["document_id"], r["page"]): r for r in
                     validation.read_jsonl(ROOT / "data/processed/pages.jsonl")}
        cls.protocol = json.loads((ROOT / "benchmark/protocol.json").read_text())

    def setUp(self):
        self.rows = copy.deepcopy(self.baseline)

    def validate(self):
        validation.validate_questions(self.rows, self.pages, self.protocol)

    def test_real_dataset_and_samples(self):
        report = validation.validate_dataset(ROOT, verify_pdf=False)
        self.assertEqual(report["split_counts"], {"dev": 15, "test": 5})
        self.assertEqual(report["accepted_evidence_passages"], 24)
        self.assertEqual(report["filter_counts_by_split"], {"dev": 2, "test": 2})

    def test_wrong_evidence_rejected(self):
        self.rows[0]["evidence_quote"] = "An answer that is absent from this source."
        with self.assertRaisesRegex(ValueError, "evidence does not match"):
            self.validate()

    def test_wrong_offsets_rejected(self):
        self.rows[0]["evidence_start_char"] += 1
        with self.assertRaisesRegex(ValueError, "evidence does not match"):
            self.validate()

    def test_wrong_source_or_page_rejected(self):
        self.rows[0]["gold_page"] = 1
        with self.assertRaisesRegex(ValueError, "not in corpus"):
            self.validate()

    def test_duplicate_question_rejected(self):
        self.rows[1]["question"] = self.rows[0]["question"]
        with self.assertRaisesRegex(ValueError, "Duplicate questions"):
            self.validate()

    def test_split_change_rejected(self):
        self.rows[-1]["split"] = "dev"
        with self.assertRaisesRegex(ValueError, "split counts"):
            self.validate()

    def test_gold_page_filter_rejected(self):
        self.rows[2]["filter"]["page"] = self.rows[2]["gold_page"]
        with self.assertRaisesRegex(ValueError, "forbidden filter field"):
            self.validate()

    def test_filter_must_appear_in_question(self):
        self.rows[2]["question"] = "What does * do when applied to a string?"
        with self.assertRaisesRegex(ValueError, "not supplied in question"):
            self.validate()

    def test_filter_cannot_exclude_gold(self):
        self.rows[2]["filter"] = {"chapter": 10}
        self.rows[2]["question"] = self.rows[2]["question"].replace("Chapter 2", "Chapter 10")
        with self.assertRaisesRegex(ValueError, "excludes accepted evidence"):
            self.validate()

    def test_invalid_alternative_rejected(self):
        self.rows[0]["alternative_gold_evidence"][0]["gold_source_id"] = "not-a-source"
        with self.assertRaisesRegex(ValueError, "not in corpus"):
            self.validate()

    def test_coherence_anchor_change_rejected(self):
        samples = validation.read_jsonl(ROOT / "benchmark/coherence_samples.jsonl")
        samples[0]["anchor_offset"] += 1
        with self.assertRaisesRegex(ValueError, "wrong coherence anchor"):
            validation.validate_samples(samples, self.pages, self.protocol)

    def test_frozen_content_change_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in validation.SNAPSHOT_FILES:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, root / name)
            freeze = {"sha256": validation.snapshot_hashes(root)}
            (root / "benchmark/freeze.json").write_text(json.dumps(freeze))
            validation.verify_frozen_snapshot(root)
            with (root / "benchmark/questions.jsonl").open("a") as stream:
                stream.write("\n")
            with self.assertRaisesRegex(ValueError, "Frozen snapshot changed"):
                validation.verify_frozen_snapshot(root)


if __name__ == "__main__":
    unittest.main()
