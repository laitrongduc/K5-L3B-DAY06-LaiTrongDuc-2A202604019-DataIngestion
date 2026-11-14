"""Real pgvector checks with test-only vectors and isolated namespaces."""
import os
import sys
import uuid
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))

from src.models import Chunk
from dotenv import load_dotenv
from src.store import PgVectorStore


@unittest.skipUnless(os.getenv("RUN_PGVECTOR_TESTS") == "1", "Set RUN_PGVECTOR_TESTS=1 for live PostgreSQL checks")
class StoreTests(unittest.TestCase):
    def setUp(self):
        load_dotenv(ROOT / "starter/.env")
        self.database_url = os.environ["DATABASE_URL"]
        self.namespace = "test_" + uuid.uuid4().hex
        self.store = PgVectorStore(self.database_url, 384, self.namespace)
        self.store.create_schema()
        self.chunks = [Chunk(f"c{i}", "sample", "sample.pdf", i + 1, f"Test passage {i}", {"chapter": i + 1})
                       for i in range(3)]
        self.vectors = [v + [0.0] * 381 for v in [[1.0, 0.0, 0.0], [0.8, 0.6, 0.0], [0.0, 0.0, 1.0]]]

    def tearDown(self):
        self.store.connection.execute("DELETE FROM day6_chunks WHERE namespace=%s", (self.namespace,))
        self.store.close()

    def test_cosine_order_metadata_and_filter(self):
        self.store.upsert("B", self.chunks, self.vectors)
        hits = self.store.search("B", self.vectors[0])
        self.assertEqual([h["chunk_id"] for h in hits], ["c0", "c1", "c2"])
        self.assertAlmostEqual(hits[0]["score"], 1.0, places=6)
        self.assertAlmostEqual(hits[1]["score"], 0.8, places=6)
        self.assertEqual(hits[0]["metadata"]["document_id"], "sample")
        filtered = self.store.search("C", self.vectors[0], filters={"chapter": 2})
        self.assertEqual([h["chunk_id"] for h in filtered], ["c1"])
        self.assertEqual(self.store.search("C", self.vectors[0], filters={"chapter": 99}), [])
        self.assertEqual(self.store.index_name("B"), self.store.index_name("C"))

    def test_reingestion_and_obsolete_point_removal(self):
        self.store.upsert("A", self.chunks, self.vectors)
        self.store.upsert("A", self.chunks, self.vectors)
        self.assertEqual(self.store.count("A"), 3)
        self.store.upsert("A", self.chunks[:2], self.vectors[:2])
        self.assertEqual(self.store.count("A"), 2)
        self.assertEqual({h["chunk_id"] for h in self.store.search("A", self.vectors[0])}, {"c0", "c1"})

    def test_data_survives_close_and_reopen(self):
        self.store.upsert("A", self.chunks, self.vectors)
        self.store.close()
        self.store = PgVectorStore(self.database_url, 384, self.namespace)
        self.assertEqual(self.store.count("A"), 3)
        self.assertEqual(self.store.search("A", self.vectors[0])[0]["chunk_id"], "c0")

    def test_invalid_vectors_and_gold_filters_are_rejected_before_writes(self):
        for vectors in ([[1.0, 0.0]], [[0.0, 0.0, 0.0]], [[float("nan"), 0.0, 1.0]]):
            with self.assertRaises(ValueError):
                self.store.upsert("A", self.chunks[:1], vectors)
        self.assertEqual(self.store.count("A"), 0)
        with self.assertRaises(ValueError):
            self.store.search("A", self.vectors[0], filters={"page": 1})


if __name__ == "__main__":
    unittest.main()
