"""Ingest, search or benchmark real embeddings in PostgreSQL/pgvector."""
import argparse
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

from scripts.prepare_chunks import main as prepare_chunks
from scripts.validate_benchmark import read_jsonl, verify_frozen_snapshot

from .embeddings import SentenceTransformerEmbedder
from .models import Chunk
from .store import PgVectorStore

ROOT = Path(__file__).resolve().parents[2]


def write_json(name: str, data: dict) -> None:
    path = ROOT / "results" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def runtime() -> tuple:
    verify_frozen_snapshot(ROOT)
    config = json.loads((ROOT / "starter/model_config.json").read_text())
    if (config["dimensions"] != 384 or config["dtype"] != "float32" or config["device"] != "cpu"
            or config["max_tokens"] != 128 or config["vector_store"] != "pgvector"
            or config["query_prefix"] or config["document_prefix"]):
        raise ValueError("Runtime config differs from the selected plain-text MiniLM/pgvector pipeline")
    load_dotenv(ROOT / "starter/.env")
    database_url = os.getenv(config["database_url_env"])
    if not database_url:
        raise ValueError("DATABASE_URL missing; configure starter/.env")
    libraries = {name: version(name) for name in ("torch", "transformers", "sentence-transformers", "psycopg")}
    identity = {"config": config, "libraries": libraries,
                "strategies": json.loads((ROOT / "starter/strategies.json").read_text()),
                "corpus_sha256": hashlib.sha256((ROOT / "data/processed/pages.jsonl").read_bytes()).hexdigest()}
    signature = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    started = perf_counter()
    model = SentenceTransformerEmbedder(config["model_name"], config["revision"],
                                       ROOT / config["cache_path"], config["batch_size"])
    return config, libraries, signature, model, perf_counter() - started, database_url


def ingest(config: dict, libraries: dict, signature: str, model: SentenceTransformerEmbedder, load_seconds: float, database_url: str) -> None:
    prepare_chunks()
    store = PgVectorStore(database_url, model.dimensions, f"day6_{signature}")
    stats = {"model": config, "libraries": libraries, "embedding_signature": signature,
             "loaded_parameter_count": model.parameter_count, "verified_parameter_dtype": "float32",
             "run_at": datetime.now(timezone.utc).isoformat(), "model_load_seconds": load_seconds,
             "metric": "cosine", "search_mode": "pgvector exact (no ANN index)", "strategies": {},
             "paid_api_cost_usd": 0, "cost_scope": "Local inference; hardware/electricity excluded"}
    smoke_question = "In Chapter 2, what is a Python variable?"
    smoke = {"question": smoke_question, "purpose": "Unscored setup check, not dev/test evaluation", "results": {}}
    try:
        store.create_schema()
        stats["database"] = store.database_info()
        for strategy in ("A", "B"):
            chunks = [Chunk(**row) for row in read_jsonl(ROOT / f"results/chunks_{strategy}.jsonl")]
            started = perf_counter()
            vectors = model.embed_documents([c.text for c in chunks])
            embedding_seconds = perf_counter() - started
            started = perf_counter()
            store.upsert(strategy, chunks, vectors)
            store_seconds = perf_counter() - started
            first_count = store.count(strategy)
            store.upsert(strategy, chunks, vectors)
            second_count = store.count(strategy)
            if first_count != second_count or first_count != len(chunks):
                raise RuntimeError("Re-ingestion changed the expected point count")
            stats["strategies"][strategy] = {"chunk_count": first_count, "repeat_count": second_count,
                "embedding_seconds": embedding_seconds, "store_seconds": store_seconds,
                "ingest_seconds": embedding_seconds + store_seconds,
                "index": store.index_name(strategy), "reingestion_without_duplicates": True}
        stats["strategies"]["C"] = {"chunk_count": store.count("C"), "index": store.index_name("C"),
                                      "reuses_vectors_from": "B", "separate_embedding_performed": False}
        query_vector = model.embed_query(smoke_question)
        for strategy in ("A", "B", "C"):
            filters = {"chapter": 2} if strategy == "C" else None
            hits = store.search(strategy, query_vector, filters=filters)
            if len(hits) != 3 or (filters and any(h["metadata"]["chapter"] != 2 for h in hits)):
                raise RuntimeError("Top-3/filter smoke check failed")
            smoke["results"][strategy] = {"filter": filters, "hits": hits}
    finally:
        store.close()
    # Reopen the actual persistent database and repeat the same query.
    reopened = PgVectorStore(database_url, model.dimensions, f"day6_{signature}")
    try:
        for strategy, previous in smoke["results"].items():
            current = reopened.search(strategy, query_vector, filters=previous["filter"])
            if ([h["chunk_id"] for h in current] != [h["chunk_id"] for h in previous["hits"]]
                    or not all(math.isclose(a["score"], b["score"], abs_tol=1e-6)
                               for a, b in zip(current, previous["hits"]))
                    or reopened.count(strategy) != stats["strategies"][strategy]["chunk_count"]):
                raise RuntimeError("Persistent store reopen check failed")
    finally:
        reopened.close()
    stats["persistent_reopen_verified"] = True
    stats["token_counts"] = {kind: {"inputs": len(counts), "total": sum(counts), "max": max(counts)}
                             for kind, counts in model.token_counts.items()}
    write_json("vector_smoke.json", smoke)
    write_json("vector_ingestion_stats.json", stats)
    print(json.dumps({"stored_chunks": {s: v["chunk_count"] for s, v in stats["strategies"].items()},
                      "persistent_reopen_verified": True, "dimensions": model.dimensions,
                      "stats": "results/vector_ingestion_stats.json", "smoke": "results/vector_smoke.json"}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("ingest", "search", "benchmark"))
    parser.add_argument("--split", choices=("dev", "test"))
    parser.add_argument("--question")
    parser.add_argument("--chapter", type=int)
    args = parser.parse_args()
    if args.command == "search" and not args.question:
        parser.error("search requires --question")
    if args.command == "benchmark" and args.split is None:
        parser.error("benchmark requires --split dev|test")
    config, libraries, signature, model, load_seconds, database_url = runtime()
    if args.command == "ingest":
        ingest(config, libraries, signature, model, load_seconds, database_url)
    elif args.command == "benchmark":
        from .benchmarking import benchmark
        benchmark(config, libraries, signature, model, load_seconds, database_url, args.split)
    else:
        store = PgVectorStore(database_url, model.dimensions, f"day6_{signature}")
        try:
            vector = model.embed_query(args.question)
            results = {s: store.search(s, vector, filters={"chapter": args.chapter}
                       if s == "C" and args.chapter is not None else None) for s in ("A", "B", "C")}
            print(json.dumps(results, ensure_ascii=False, indent=2))
        finally:
            store.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        path = ROOT / "results/runtime_errors.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(),
                         "error_type": type(exc).__name__, "message": str(exc)}) + "\n")
        raise
