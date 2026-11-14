"""Frozen dev/test retrieval; select on dev before encoding any test query."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from scripts.validate_benchmark import read_jsonl, verify_frozen_snapshot

from .evaluation import summarize, evaluate_query
from .store import PgVectorStore

ROOT = Path(__file__).resolve().parents[2]
STRATEGIES = ("A", "B", "C")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def select_strategy(dev_summary: dict, ingestion: dict) -> dict:
    """Apply the frozen lexicographic rule. C pays B's shared ingest cost."""
    rows = dev_summary["by_strategy_split"]
    if (len(rows) != 3 or {r["strategy"] for r in rows} != set(STRATEGIES)
            or any(r["split"] != "dev" or r["question_count"] != 15 for r in rows)):
        raise ValueError("Selection requires all three completed 15-question dev runs")
    ranked = []
    for row in rows:
        strategy = row["strategy"]
        resource = ingestion["strategies"]["B" if strategy == "C" else strategy]
        ranked.append({"strategy": strategy, "dev_evidence_hit3": row["evidence_hit3"],
                       "dev_hit1": row["hit1"], "ingest_seconds": resource["ingest_seconds"],
                       "chunk_count": resource["chunk_count"]})
    ranked.sort(key=lambda r: (-r["dev_evidence_hit3"]["n"], -r["dev_hit1"]["n"],
                               r["ingest_seconds"], r["chunk_count"], r["strategy"]))
    return {"selected_strategy": ranked[0]["strategy"], "ranking": ranked,
            "resource_policy": "C reuses B but is charged B's full ingest cost for tie-breaking"}


def locked_files() -> dict:
    paths = ["benchmark/freeze.json", "starter/model_config.json", "starter/strategies.json",
             "results/chunks_A.jsonl", "results/chunks_B.jsonl", "results/vector_ingestion_stats.json",
             "results/retrieval_dev.jsonl", "results/retrieval_metrics_dev.json",
             "starter/src/chunking.py", "starter/src/embeddings.py", "starter/src/store.py",
             "starter/src/evaluation.py", "starter/src/benchmarking.py", "starter/src/run.py"]
    return {name: sha256(ROOT / name) for name in paths}


def benchmark(config: dict, libraries: dict, signature: str, model, load_seconds: float,
              database_url: str, split: str) -> None:
    verify_frozen_snapshot(ROOT)
    out = ROOT / "results"
    trace_path, metric_path = out / f"retrieval_{split}.jsonl", out / f"retrieval_metrics_{split}.json"
    if trace_path.exists() or metric_path.exists():
        raise FileExistsError("Keep completed/partial evidence; archive the existing split outputs before rerunning")
    ingestion = json.loads((out / "vector_ingestion_stats.json").read_text())
    if (ingestion["embedding_signature"] != signature or ingestion["model"] != config
            or ingestion["libraries"] != libraries):
        raise ValueError("Stored embeddings do not match runtime; ingest the selected configuration first")
    selection_path = out / "dev_selection.json"
    selection = None
    if split == "test":
        # Rescore completed dev traces, lock the selection and every controlled
        # artifact BEFORE reading/encoding test queries. Never use test metrics.
        dev = [q for q in read_jsonl(ROOT / "benchmark/questions.jsonl") if q["split"] == "dev"]
        dev_summary = summarize(read_jsonl(out / "retrieval_dev.jsonl"), questions=dev)
        persisted = json.loads((out / "retrieval_metrics_dev.json").read_text())
        if persisted["by_strategy_split"] != dev_summary["by_strategy_split"]:
            raise ValueError("Dev metrics differ from rescored traces")
        selection = {**select_strategy(dev_summary, ingestion),
                     "selected_at": datetime.now(timezone.utc).isoformat(),
                     "criteria": json.loads((ROOT / "benchmark/protocol.json").read_text())["selection_criteria_in_order"],
                     "basis": "Frozen full-quote single-chunk evidence metric on dev only; no test-based tuning",
                     "embedding_signature": signature, "sha256": locked_files()}
        if selection_path.exists():
            previous = json.loads(selection_path.read_text())
            if (previous["sha256"] != selection["sha256"]
                    or previous["selected_strategy"] != selection["selected_strategy"]):
                raise ValueError("Locked configuration/selection changed after dev; stop rather than tune on test")
            selection = previous
        else:
            save_json(selection_path, selection)
    elif selection_path.exists():
        raise ValueError("Dev was already locked for test; do not retune")
    questions = [q for q in read_jsonl(ROOT / "benchmark/questions.jsonl") if q["split"] == split]
    if len(questions) != (15 if split == "dev" else 5):
        raise ValueError("Unexpected frozen split size")
    store = PgVectorStore(database_url, model.dimensions, f"day6_{signature}")
    traces, embedding_times = [], []
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        for strategy in STRATEGIES:
            if store.count(strategy) != ingestion["strategies"][strategy]["chunk_count"]:
                raise ValueError("Database snapshot incomplete; rerun ingest before benchmarking")
        with trace_path.open("x", encoding="utf-8") as stream:
            for question in questions:
                started = perf_counter()
                vector = model.embed_query(question["question"])
                query_seconds = perf_counter() - started
                embedding_times.append(query_seconds)
                for strategy in STRATEGIES:
                    applied_filter = question.get("filter") if strategy == "C" else None
                    started = perf_counter()
                    hits = store.search(strategy, vector, top_k=3, filters=applied_filter)
                    search_seconds = perf_counter() - started
                    trace = {**evaluate_query(question, hits), "strategy": strategy,
                             "applied_filter": applied_filter,
                             "query_embedding_seconds": query_seconds,
                             "search_seconds": search_seconds}
                    stream.write(json.dumps(trace, ensure_ascii=False) + "\n")
                    stream.flush()
                    traces.append(trace)
    finally:
        store.close()
    summary = {**summarize(traces, questions=questions), "split": split,
               "started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
               "embedding_signature": signature, "model": config, "libraries": libraries,
               "benchmark_freeze_sha256": sha256(ROOT / "benchmark/freeze.json"),
               "model_load_seconds": load_seconds, "paid_api_cost_usd": 0,
               "timing": {"query_embedding_seconds_once_per_question": sum(embedding_times),
                          "search_seconds_by_strategy": {s: sum(t["search_seconds"] for t in traces if t["strategy"] == s)
                                                         for s in STRATEGIES},
                          "scope": "Sequential local setup run; query embeddings shared across A/B/C, no load test"},
               "trace_sha256": sha256(trace_path)}
    if selection is not None:
        if locked_files() != selection["sha256"]:
            raise ValueError("Controlled artifacts changed while evaluating test")
        summary["selected_before_test"] = selection["selected_strategy"]
        summary["selection_sha256"] = sha256(selection_path)
    save_json(metric_path, summary)
    print(json.dumps({"split": split, "trace_count": len(traces),
                      "selected_before_test": summary.get("selected_before_test"),
                      "metrics": summary["by_strategy_split"]}, indent=2))
