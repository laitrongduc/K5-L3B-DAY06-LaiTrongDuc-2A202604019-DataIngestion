"""Verify recorded runs/audits and export submission tables; never retrieve or relabel."""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))
from scripts.validate_benchmark import read_jsonl, verify_frozen_snapshot
from src.benchmarking import locked_files, select_strategy, sha256, save_json
from src.evaluation import evaluate_query, summarize


def require(condition, message):
    if not condition:
        raise ValueError(message)


def matrix(rows, fields):
    result = {tuple(row[f] for f in fields): row for row in rows}
    require(len(result) == len(rows), "Duplicate audit case")
    return result


def main() -> None:
    verify_frozen_snapshot(ROOT)
    out = ROOT / "results"
    load = lambda name: json.loads((out / name).read_text(encoding="utf-8"))
    questions = read_jsonl(ROOT / "benchmark/questions.jsonl")
    traces = read_jsonl(out / "retrieval_dev.jsonl") + read_jsonl(out / "retrieval_test.jsonl")
    ingestion, selection = load("vector_ingestion_stats.json"), load("dev_selection.json")
    require(locked_files() == selection["sha256"], "Controlled artifacts changed after dev selection")
    require(select_strategy(load("retrieval_metrics_dev.json"), ingestion)["selected_strategy"]
            == selection["selected_strategy"], "Selection differs from frozen dev criteria")
    by_question = {q["id"]: q for q in questions}
    exports = {s: {c["chunk_id"]: c for c in read_jsonl(out / f"chunks_{s}.jsonl")} for s in "AB"}
    for trace in traces:
        q, s = by_question[trace["question_id"]], trace["strategy"]
        require(trace["question"] == q, "Trace question differs from frozen question")
        require(trace["applied_filter"] == (q["filter"] if s == "C" else None), "Unexpected retrieval filter")
        scored = evaluate_query(q, trace["hits"])
        require(trace["hit1"] == scored["hit1"] and trace["evidence_hit3"] == scored["evidence_hit3"],
                "Recorded hit flags differ from evidence rescoring")
        for hit in trace["hits"]:
            c = exports["B" if s == "C" else s][hit["chunk_id"]]
            require(hit["text"] == c["text"] and hit["metadata"] == c["metadata"], "Trace differs from exported chunk")
    metrics = summarize(traces, questions=questions)
    for split in ("dev", "test"):
        saved = load(f"retrieval_metrics_{split}.json")
        require(saved["by_strategy_split"] == [r for r in metrics["by_strategy_split"] if r["split"] == split],
                "Saved split summary differs from traces")
        require(saved["trace_sha256"] == sha256(out / f"retrieval_{split}.jsonl"), "Trace checksum changed")
    test = load("retrieval_metrics_test.json")
    require(test["selection_sha256"] == sha256(out / "dev_selection.json"), "Dev selection changed after test")
    require(datetime.fromisoformat(selection["selected_at"]) < datetime.fromisoformat(test["started_at"]),
            "Strategy was not selected before test retrieval")
    keyed = {(t["strategy"], t["question_id"]): t for t in traces}
    for q in questions:
        if q["filter"] is None:
            require(keyed["B", q["id"]]["hits"] == keyed["C", q["id"]]["hits"],
                    "B/C must be identical when no filter is supplied")
    packets, labels = load("audit_packets.json"), load("audit_labels.json")
    require(labels["audit_packets_sha256"] == sha256(out / "audit_packets.json"), "Audit labels refer to stale packets")
    require(bool(labels["reviewer"]) and bool(labels["review_method"]), "Missing reviewer/method disclosure")
    for category, fields in (("coherence", ("strategy", "sample_id")), ("grounding", ("strategy", "question_id")),
                             ("metadata", ("strategy", "question_id", "rank"))):
        expected, actual = matrix(packets[category], fields), matrix(labels[category], fields)
        require(set(expected) == set(actual), f"Incomplete {category} audit matrix")
        for key, row in actual.items():
            packet = expected[key]
            require(isinstance(row.get("reason"), str) and len(row["reason"].strip()) > 20, "Audit needs a specific reason")
            if category == "coherence":
                require(row["chunk_id"] == (packet["chunk"]["chunk_id"] if packet["chunk"] else None),
                        "Coherence chunk differs from frozen anchor selection")
            elif category == "grounding":
                require(all(type(r) is int and 1 <= r <= len(packet["hits"]) for r in row["supporting_ranks"]),
                        "Invalid grounding evidence rank")
                require(bool(row["supporting_ranks"]) == (row["score"] > 0), "Grounding support/score mismatch")
            else:
                require(row["chunk_id"] == packet["chunk_id"], "Metadata label refers to another chunk")
                require(type(row["complete_and_correct"]) is bool, "Metadata label must be boolean")
                require(not row["complete_and_correct"] or not packet["automatic_mismatches"], "Metadata pass contradicts source checks")
            if category != "metadata":
                require(type(row["score"]) is int and row["score"] in (0, 1, 2), "Audit score must be 0/1/2")
    coherence = matrix(labels["coherence"], ("strategy", "sample_id"))
    for sample in read_jsonl(ROOT / "benchmark/coherence_samples.jsonl"):
        b, c = coherence["B", sample["id"]], coherence["C", sample["id"]]
        require((b["chunk_id"], b["score"]) == (c["chunk_id"], c["score"]), "C coherence must inherit identical B chunks")
    audit_summary = {"reviewer": labels["reviewer"], "review_method": labels["review_method"],
                     "human_confirmation": labels["human_confirmation"], "by_strategy": {}}
    for s in "ABC":
        co = [r for r in labels["coherence"] if r["strategy"] == s]
        gr = [r for r in labels["grounding"] if r["strategy"] == s]
        me = [r for r in labels["metadata"] if r["strategy"] == s]
        audit_summary["by_strategy"][s] = {
            "coherence": {"n": len(co), "counts_0_1_2": {str(k): sum(r["score"] == k for r in co) for k in (0, 1, 2)},
                          "mean_out_of_2": sum(r["score"] for r in co) / len(co)},
            "grounding": {"n": len(gr), "counts_0_1_2": {str(k): sum(r["score"] == k for r in gr) for k in (0, 1, 2)},
                          "mean_out_of_2": sum(r["score"] for r in gr) / len(gr)},
            "metadata_complete_and_correct": {"n": sum(r["complete_and_correct"] for r in me), "N": len(me)}}
    save_json(out / "retrieval_metrics.json", metrics)
    save_json(out / "audit_summary.json", audit_summary)
    fields = ["strategy", "chunking", "chunk_size", "overlap", "metadata", "filter", "vectorizer", "hypothesis",
              "dev_hit1", "dev_hit3", "test_hit1", "test_hit3", "notes"]
    rows_by_split = {(r["strategy"], r["split"]): r for r in metrics["by_strategy_split"]}
    hypotheses = {"A": "Fixed windows with overlap provide a simple reference for chunk boundaries",
                  "B": "Paragraph boundaries may preserve more complete evidence than A",
                  "C": "Question-supplied chapter filters may exclude out-of-scope results without changing B vectors"}
    with (ROOT / "artifacts/experiment_log.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for s in "ABC":
            r = {"strategy": s, "chunking": "fixed_size" if s == "A" else "paragraph",
                 "chunk_size": "500 chars; split again at 128 tokens including special tokens", "overlap": 50 if s == "A" else 0,
                 "metadata": "document_id:str; source:str; page:int; chapter:int; offsets:int; version:str; language:str",
                 "filter": "supplied chapter only; otherwise none" if s == "C" else "none",
                 "vectorizer": ingestion["model"]["model_name"] + "@" + ingestion["model"]["revision"],
                 "hypothesis": hypotheses[s],
                 "notes": "Compiled after runs from frozen configurations; hypotheses describe design intent, not separately preregistered claims. "
                          f"Chunks={ingestion['strategies'][s]['chunk_count']}; pgvector exact cosine; "
                          "paid API USD=0; audit reviewer=Codex AI, human confirmation pending; "
                          "C shares B ingest cost; selected on dev=" + selection["selected_strategy"]}
            for split in ("dev", "test"):
                for metric, key in (("hit1", "hit1"), ("hit3", "evidence_hit3")):
                    value = rows_by_split[s, split][key]
                    r[f"{split}_{metric}"] = f"{value['n']}/{value['N']}"
            writer.writerow(r)
    validation = {"status": "passed", "checked_at": datetime.now(timezone.utc).isoformat(),
                  "frozen_snapshot_verified": True, "selection_lock_verified": True,
                  "selection_before_test_verified": True, "selected_strategy": selection["selected_strategy"],
                  "trace_count": len(traces), "returned_records": sum(len(t["hits"]) for t in traces),
                  "complete_audit_matrices": {k: len(labels[k]) for k in ("coherence", "grounding", "metadata")},
                  "unfiltered_B_C_identity_questions": sum(q["filter"] is None for q in questions),
                  "source_reextraction_pages": packets["pdf_pages_reextracted"],
                  "human_confirmation": labels["human_confirmation"],
                  "scope": "Validates artifacts and arithmetic; does not claim independent human judgment or remote submission"}
    save_json(out / "run_validation.json", validation)
    print(json.dumps({"validation": validation, "audits": audit_summary["by_strategy"]}, indent=2))


if __name__ == "__main__":
    main()
