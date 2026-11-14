"""Score required Hit@1/Hit@3 metrics and preserve evidence traces."""
import copy
import math
import unicodedata
from collections import defaultdict
from typing import Any


def _fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """A hit needs correct source/page and a full primary or alternative quote.

    Use validated benchmark questions and successful backend responses only.
    Preserve backend rank order; an empty response is a miss. Manual grounding,
    coherence, metadata checks and equivalent evidence reviews stay separate.
    """
    if question.get("split") not in {"dev", "test"} or not question.get("id"):
        raise ValueError("Question needs an ID and dev/test split")
    if not isinstance(hits, list) or len(hits) > 3:
        raise ValueError("Expected a ranked list of at most three hits")
    golds = [question, *question.get("alternative_gold_evidence", [])]
    if any(not gold.get("evidence_quote", "").strip() for gold in golds):
        raise ValueError("Gold evidence must not be empty")
    annotated, ids = [], set()
    for rank, hit in enumerate(hits, 1):
        chunk_id, text, metadata = hit.get("chunk_id"), hit.get("text"), hit.get("metadata")
        if not isinstance(chunk_id, str) or not chunk_id or chunk_id in ids:
            raise ValueError("Missing or duplicate chunk ID")
        ids.add(chunk_id)
        if not isinstance(text, str) or not text.strip() or not isinstance(metadata, dict):
            raise ValueError("Hit needs nonempty text and metadata")
        for field in ("document_id", "source"):
            if not isinstance(metadata.get(field), str) or not metadata[field]:
                raise ValueError(f"Hit metadata missing {field}")
        if type(metadata.get("page")) is not int or metadata["page"] < 1:
            raise ValueError("Hit needs a positive physical page")
        score = hit.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError("Hit score must be finite")
        matched = [i for i, gold in enumerate(golds)
                   if metadata["document_id"] == gold["gold_source_id"]
                   and metadata["page"] == gold["gold_page"]
                   and _fold(gold["evidence_quote"]) in _fold(text)]
        annotated.append({**copy.deepcopy(hit), "rank": rank, "evidence_hit": bool(matched),
                          "matched_gold_indices": matched})
    requested_filter = question.get("filter")
    compliance = None
    if requested_filter is not None:
        if not isinstance(requested_filter, dict) or not requested_filter:
            raise ValueError("Filter must be null or a nonempty dictionary")
        compliance = bool(annotated) and all(
            all(hit["metadata"].get(key) == value for key, value in requested_filter.items()) for hit in annotated
        )
    return {"question_id": question["id"], "split": question["split"],
            "question": copy.deepcopy(question), "hits": annotated,
            "hit1": bool(annotated and annotated[0]["evidence_hit"]),
            "evidence_hit3": any(hit["evidence_hit"] for hit in annotated),
            "returned_count": len(annotated), "requested_filter_compliance": compliance,
            "retrieval_status": "ok",
            "manual_review_required": True}


def summarize(traces: list[dict[str, Any]], *, questions: list[dict],
              strategies: tuple[str, ...] = ("A", "B", "C")) -> dict[str, Any]:
    """Return counts/rates by strategy and split; reject missing/duplicate runs.

    Supply the frozen dev question list for dev runs, or the whole set for final
    reporting. Every expected query must have a successful retrieval trace.
    """
    expected = {q["id"]: q for q in questions}
    if not expected or len(expected) != len(questions) or not strategies or len(set(strategies)) != len(strategies):
        raise ValueError("Need unique questions and unique expected strategies")
    matrix = {}
    for trace in traces:
        strategy, qid = trace.get("strategy"), trace.get("question_id")
        if strategy not in strategies or qid not in expected:
            raise ValueError("Trace contains an unexpected strategy/question")
        key = (strategy, qid)
        if key in matrix:
            raise ValueError("Duplicate strategy/question trace")
        if trace.get("split") != expected[qid]["split"]:
            raise ValueError("Trace split differs from frozen question")
        if trace.get("retrieval_status") != "ok":
            raise ValueError("Retrieval failure or unknown status: report the error; do not score it as an empty response")
        # Recompute from hits; do not trust caller-supplied metric flags.
        matrix[key] = {**evaluate_query(expected[qid], trace["hits"]), "strategy": strategy}
    if set(matrix) != {(s, qid) for s in strategies for qid in expected}:
        raise ValueError("Missing traces: every query needs completed retrieval; valid empty responses count as misses")
    groups = defaultdict(list)
    for row in matrix.values():
        groups[row["strategy"], row["split"]].append(row)
    summaries = []
    for (strategy, split), rows in sorted(groups.items()):
        total = len(rows)
        summary = {"strategy": strategy, "split": split, "question_count": total}
        for key in ("hit1", "evidence_hit3"):
            correct = sum(row[key] for row in rows)
            summary[key] = {"n": correct, "N": total, "rate": correct / total}
        filtered = [r for r in rows if r["question"].get("filter") is not None]
        correct_filters = sum(r["requested_filter_compliance"] for r in filtered)
        summary["filter_compliance"] = {"n": correct_filters, "N": len(filtered),
                                        "rate": correct_filters / len(filtered) if filtered else None}
        summary["queries_with_fewer_than_three_hits"] = sum(r["returned_count"] < 3 for r in rows)
        summaries.append(summary)
    return {"by_strategy_split": summaries, "complete_matrix_verified": True}
