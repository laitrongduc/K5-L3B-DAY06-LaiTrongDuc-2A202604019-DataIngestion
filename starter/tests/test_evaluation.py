"""Synthetic ranked-hit fixtures test scoring, not real retrieval performance."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))

from src.evaluation import evaluate_query, summarize


class EvidenceEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.questions = {q["id"]: q for q in map(json.loads, (ROOT / "benchmark/questions.jsonl").read_text().splitlines())}

    def hit(self, question, *, chunk_id="chunk-1", text=None, page=None):
        return {"chunk_id": chunk_id, "text": question["evidence_quote"] if text is None else text,
                "score": 0.8, "metadata": {"document_id": question["gold_source_id"],
                "source": "https://greenteapress.com/thinkpython2/thinkpython2.pdf",
                "page": question["gold_page"] if page is None else page,
                **(question.get("filter") or {})}}

    def trace(self, question, strategy, hits):
        return {**evaluate_query(question, hits), "strategy": strategy}

    def test_top1_with_full_evidence(self):
        q = self.questions["q01"]
        result = evaluate_query(q, [self.hit(q)])
        self.assertTrue(result["hit1"])
        self.assertTrue(result["evidence_hit3"])
        self.assertTrue(result["manual_review_required"])
        self.assertNotIn("grounding_score", result)

    def test_second_rank_hit_does_not_become_hit1(self):
        q = self.questions["q01"]
        hits = [self.hit(q, chunk_id="noise", text="Unrelated passage"), self.hit(q)]
        result = evaluate_query(q, hits)
        self.assertFalse(result["hit1"])
        self.assertTrue(result["evidence_hit3"])

    def test_correct_page_alone_is_not_a_hit(self):
        q = self.questions["q01"]
        self.assertFalse(evaluate_query(q, [self.hit(q, text="Related words but insufficient evidence")])["evidence_hit3"])

    def test_wrong_source_or_page_is_not_a_hit(self):
        q = self.questions["q01"]
        hit = self.hit(q, page=q["gold_page"] + 1)
        self.assertFalse(evaluate_query(q, [hit])["evidence_hit3"])
        hit = self.hit(q)
        hit["metadata"]["document_id"] = "other-document"
        self.assertFalse(evaluate_query(q, [hit])["evidence_hit3"])

    def test_alternative_evidence_is_accepted(self):
        q = self.questions["q07"]
        alt = q["alternative_gold_evidence"][0]
        result = evaluate_query(q, [self.hit(q, text=alt["evidence_quote"], page=alt["gold_page"])])
        self.assertTrue(result["hit1"])
        self.assertEqual(result["hits"][0]["matched_gold_indices"], [1])

    def test_whitespace_changes_are_accepted_but_operator_changes_are_not(self):
        q = self.questions["q09"]
        text = "  \n".join(q["evidence_quote"].split())
        self.assertTrue(evaluate_query(q, [self.hit(q, text=text)])["hit1"])
        self.assertFalse(evaluate_query(q, [self.hit(q, text=q["evidence_quote"].replace("//", "/"))])["hit1"])

    def test_evidence_fragments_are_not_combined_for_required_hit(self):
        q = self.questions["q01"]
        quote = q["evidence_quote"]
        middle = len(quote) // 2
        result = evaluate_query(q, [self.hit(q, text=quote[:middle]),
                                    self.hit(q, chunk_id="chunk-2", text=quote[middle:])])
        self.assertFalse(result["evidence_hit3"])

    def test_empty_results_are_a_miss_and_not_filter_success(self):
        result = evaluate_query(self.questions["q03"], [])
        self.assertFalse(result["evidence_hit3"])
        self.assertFalse(result["requested_filter_compliance"])
        self.assertEqual(result["returned_count"], 0)

    def test_invalid_hits_are_rejected(self):
        q = self.questions["q01"]
        for hits in ([self.hit(q), self.hit(q)], [self.hit(q, chunk_id=str(i)) for i in range(4)]):
            with self.assertRaises(ValueError):
                evaluate_query(q, hits)
        hit = self.hit(q)
        hit["score"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            evaluate_query(q, [hit])
        hit = self.hit(q)
        del hit["metadata"]["page"]
        with self.assertRaisesRegex(ValueError, "physical page"):
            evaluate_query(q, [hit])

    def test_summary_separates_splits_and_keeps_empty_query_in_denominator(self):
        dev, test = self.questions["q01"], self.questions["q16"]
        traces = [self.trace(q, strategy, [self.hit(q)] if successful else [])
                  for strategy, q, successful in (("A", dev, False), ("A", test, False),
                                                   ("B", dev, True), ("B", test, False),
                                                   ("C", dev, True), ("C", test, True))]
        traces[0]["hit1"] = True  # Caller flags must not override rescoring.
        result = summarize(traces, questions=[dev, test])
        a_dev = next(r for r in result["by_strategy_split"] if r["strategy"] == "A" and r["split"] == "dev")
        self.assertEqual(a_dev["hit1"]["n"], 0)
        self.assertEqual(a_dev["hit1"]["N"], 1)
        self.assertIsNone(a_dev["filter_compliance"]["rate"])
        c_test = next(r for r in result["by_strategy_split"] if r["strategy"] == "C" and r["split"] == "test")
        self.assertEqual(c_test["evidence_hit3"], {"n": 1, "N": 1, "rate": 1.0})

    def test_missing_or_duplicate_trace_cannot_shrink_denominator(self):
        q = self.questions["q01"]
        traces = [self.trace(q, s, []) for s in ("A", "B", "C")]
        with self.assertRaisesRegex(ValueError, "Missing traces"):
            summarize(traces[:-1], questions=[q])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            summarize(traces + [traces[0]], questions=[q])

    def test_backend_failure_is_not_scored_as_empty_retrieval(self):
        q = self.questions["q01"]
        traces = [self.trace(q, s, []) for s in ("A", "B", "C")]
        traces[0]["retrieval_status"] = "error"
        with self.assertRaisesRegex(ValueError, "Retrieval failure"):
            summarize(traces, questions=[q])

    def test_evaluation_does_not_modify_frozen_question_or_hits(self):
        q = copy.deepcopy(self.questions["q07"])
        hits = [self.hit(q)]
        before = copy.deepcopy((q, hits))
        evaluate_query(q, hits)
        self.assertEqual((q, hits), before)


if __name__ == "__main__":
    unittest.main()
