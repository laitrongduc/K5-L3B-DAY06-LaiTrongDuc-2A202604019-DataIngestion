"""PostgreSQL/pgvector: atomic snapshot upserts, exact cosine and chapter filters."""
import json
import math

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import Chunk


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int, namespace: str) -> None:
        if type(dimensions) is not int or not 1 <= dimensions <= 2000:
            raise ValueError("Invalid vector dimensions")
        self.dimensions, self.namespace = dimensions, namespace
        self.connection = psycopg.connect(database_url, connect_timeout=5,
                                           autocommit=True, row_factory=dict_row)

    def create_schema(self) -> None:
        with self.connection.transaction():
            self.connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
            self.connection.execute(f"""CREATE TABLE IF NOT EXISTS day6_chunks (
                namespace text NOT NULL, strategy text NOT NULL CHECK (strategy IN ('A','B')),
                chunk_id text NOT NULL, text text NOT NULL, metadata jsonb NOT NULL,
                embedding vector({self.dimensions}) NOT NULL,
                PRIMARY KEY (namespace, strategy, chunk_id))""")
            row = self.connection.execute("""SELECT format_type(atttypid,atttypmod) AS kind
                FROM pg_attribute WHERE attrelid='day6_chunks'::regclass AND attname='embedding'""").fetchone()
            if row["kind"] != f"vector({self.dimensions})":
                raise ValueError("Existing table vector dimensions differ; do not mix model outputs")

    def index_name(self, strategy: str) -> str:
        return f"day6_chunks:{self.namespace}:{self._strategy(strategy)}"

    def _strategy(self, strategy: str) -> str:
        if strategy not in {"A", "B", "C"}:
            raise ValueError("Unknown strategy")
        return "B" if strategy == "C" else strategy

    def _vector(self, vector: list[float]) -> str:
        if len(vector) != self.dimensions or not all(math.isfinite(v) for v in vector):
            raise ValueError("Wrong vector dimensions or nonfinite values")
        if not any(v != 0 for v in vector):
            raise ValueError("Zero vectors are invalid for cosine similarity")
        return json.dumps(vector, allow_nan=False)

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Atomically replace all chunks for a strategy; remove obsolete IDs too."""
        if strategy not in {"A", "B"} or not chunks or len(chunks) != len(vectors):
            raise ValueError("Supply a complete nonempty A/B snapshot; C reuses B")
        ids = [c.chunk_id for c in chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate chunk IDs")
        encoded = [self._vector(v) for v in vectors]
        rows = [(self.namespace, strategy, c.chunk_id, c.text,
                 Jsonb({**c.metadata, "document_id": c.document_id, "source": c.source, "page": c.page}), v)
                for c, v in zip(chunks, encoded)]
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.executemany("""INSERT INTO day6_chunks
                    (namespace,strategy,chunk_id,text,metadata,embedding) VALUES (%s,%s,%s,%s,%s,%s::vector)
                    ON CONFLICT (namespace,strategy,chunk_id) DO UPDATE
                    SET text=EXCLUDED.text,metadata=EXCLUDED.metadata,embedding=EXCLUDED.embedding""", rows)
                cursor.execute("""DELETE FROM day6_chunks WHERE namespace=%s AND strategy=%s
                    AND NOT (chunk_id=ANY(%s::text[]))""", (self.namespace, strategy, ids))
            if self.count(strategy) != len(chunks):
                raise RuntimeError("Stored point count differs from snapshot")

    def count(self, strategy: str) -> int:
        return self.connection.execute("""SELECT count(*) AS n FROM day6_chunks
            WHERE namespace=%s AND strategy=%s""", (self.namespace, self._strategy(strategy))).fetchone()["n"]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict | None = None) -> list[dict]:
        vector = self._vector(query_vector)
        if type(top_k) is not int or top_k <= 0:
            raise ValueError("top_k must be positive")
        if filters is not None and (set(filters) != {"chapter"} or type(filters["chapter"]) is not int):
            raise ValueError("Only an integer chapter filter is supported")
        chapter = None if filters is None else filters["chapter"]
        return self.connection.execute("""SELECT chunk_id,text,metadata,
            1-(embedding <=> %s::vector) AS score FROM day6_chunks
            WHERE namespace=%s AND strategy=%s AND (%s::int IS NULL OR (metadata->>'chapter')::int=%s)
            ORDER BY embedding <=> %s::vector,chunk_id LIMIT %s""",
            (vector,self.namespace,self._strategy(strategy),chapter,chapter,vector,top_k)).fetchall()

    def database_info(self) -> dict:
        return self.connection.execute("""SELECT current_setting('server_version') AS postgresql,
            extversion AS pgvector FROM pg_extension WHERE extname='vector'""").fetchone()

    def close(self) -> None:
        self.connection.close()
