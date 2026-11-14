"""Selection is dev-only and C cannot win by claiming zero shared ingest cost."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.benchmarking import select_strategy


class SelectionTests(unittest.TestCase):
    def data(self):
        rows = [{"strategy": s, "split": "dev", "question_count": 15,
                 "hit1": {"n": 5, "N": 15}, "evidence_hit3": {"n": 8, "N": 15}} for s in "ABC"]
        resources = {s: {"ingest_seconds": 2, "chunk_count": 200} for s in "AB"}
        return {"by_strategy_split": rows}, {"strategies": resources}

    def test_hit3_has_priority_over_hit1_and_cost(self):
        dev, ingestion = self.data()
        dev["by_strategy_split"][1]["evidence_hit3"]["n"] = 9
        dev["by_strategy_split"][0]["hit1"]["n"] = 15
        ingestion["strategies"]["B"]["ingest_seconds"] = 100
        self.assertEqual(select_strategy(dev, ingestion)["selected_strategy"], "B")

    def test_c_inherits_b_cost_and_alphabetical_tie_break(self):
        dev, ingestion = self.data()
        ingestion["strategies"]["A"]["ingest_seconds"] = 3
        result = select_strategy(dev, ingestion)
        self.assertEqual(result["selected_strategy"], "B")
        self.assertEqual(result["ranking"][0]["ingest_seconds"], result["ranking"][1]["ingest_seconds"])

    def test_test_or_incomplete_results_cannot_select_strategy(self):
        dev, ingestion = self.data()
        for bad in (dev["by_strategy_split"][:-1], [dict(r, split="test") for r in dev["by_strategy_split"]]):
            with self.assertRaises(ValueError):
                select_strategy({"by_strategy_split": copy.deepcopy(bad)}, ingestion)


if __name__ == "__main__":
    unittest.main()
