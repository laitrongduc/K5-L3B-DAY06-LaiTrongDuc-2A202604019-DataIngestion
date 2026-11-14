"""Validate source evidence and the frozen benchmark; never run retrieval."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_FILES = (
    "benchmark/questions.jsonl", "benchmark/protocol.json",
    "benchmark/coherence_samples.jsonl", "data/corpus_config.json",
    "data/manifest.json", "data/processed/pages.jsonl", "data/raw/thinkpython2.pdf",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def snapshot_hashes(root: Path) -> dict[str, str]:
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SNAPSHOT_FILES}


def verify_frozen_snapshot(root: Path) -> dict:
    freeze = json.loads((root / "benchmark/freeze.json").read_text(encoding="utf-8"))
    require(set(freeze["sha256"]) == set(SNAPSHOT_FILES), "Frozen file list differs from expected snapshot")
    for name, actual in snapshot_hashes(root).items():
        require(actual == freeze["sha256"][name], f"Frozen snapshot changed: {name}")
    return freeze


def validate_gold(gold: dict, pages: dict, context: str) -> dict:
    source, number = gold.get("gold_source_id"), gold.get("gold_page")
    require(isinstance(source, str) and type(number) is int, f"{context}: invalid source/page")
    require((source, number) in pages, f"{context}: source/page not in corpus")
    page = pages[(source, number)]
    quote = gold.get("evidence_quote")
    start, end = gold.get("evidence_start_char"), gold.get("evidence_end_char")
    require(isinstance(quote, str) and bool(quote.strip()), f"{context}: empty evidence")
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(page["text"]),
            f"{context}: invalid evidence offsets")
    require(page["text"][start:end] == quote, f"{context}: evidence does not match source offsets")
    return page


def validate_questions(rows: list[dict], pages: dict, protocol: dict) -> None:
    require(len(rows) >= protocol["minimum_questions"], "Too few benchmark questions")
    counts = dict(Counter(row.get("split") for row in rows))
    require(counts == protocol["expected_counts"], "Question split counts differ from fixed protocol")
    require(len({r.get("id") for r in rows}) == len(rows), "Duplicate question IDs")
    require(len({fold(r.get("question", "")).casefold() for r in rows}) == len(rows), "Duplicate questions")
    split_chapters = protocol["chapters_by_split"]
    require(not (set(split_chapters["dev"]) & set(split_chapters["test"])), "Dev/test chapters overlap")
    filter_counts = Counter()
    for row in rows:
        context = str(row.get("id"))
        for field in ("id", "question", "expected_answer", "answer_support_reason", "review_method"):
            require(isinstance(row.get(field), str) and bool(row[field].strip()), f"{context}: missing {field}")
        require(row.get("language") == protocol["language"], f"{context}: wrong language label")
        require(row.get("type") in {"direct", "paraphrase", "condition"}, f"{context}: invalid question type")
        require("filter" in row and "alternative_gold_evidence" in row, f"{context}: incomplete schema")
        alternatives = row["alternative_gold_evidence"]
        require(isinstance(alternatives, list), f"{context}: alternatives must be a list")
        accepted = [row, *alternatives]
        seen = set()
        for gold in accepted:
            page = validate_gold(gold, pages, context)
            require(page["metadata"]["chapter"] in split_chapters[row["split"]],
                    f"{context}: evidence crosses declared split topics")
            require(gold["gold_source_id"] not in row["question"], f"{context}: source ID leaked into query")
            key = (gold["gold_source_id"], gold["gold_page"], gold["evidence_quote"])
            require(key not in seen, f"{context}: duplicate accepted evidence")
            seen.add(key)
        filters = row["filter"]
        if filters is not None:
            require(isinstance(filters, dict) and set(filters) == {"chapter"}, f"{context}: forbidden filter field")
            chapter = filters["chapter"]
            require(type(chapter) is int, f"{context}: chapter filter must be an integer")
            require(bool(re.search(rf"\bChapter\s+{chapter}\b", row["question"])),
                    f"{context}: chapter filter is not supplied in question")
            require(bool(row.get("filter_origin")), f"{context}: filter origin missing")
            for gold in accepted:
                page = pages[(gold["gold_source_id"], gold["gold_page"])]
                require(page["metadata"]["chapter"] == chapter, f"{context}: filter excludes accepted evidence")
            filter_counts[row["split"]] += 1
        else:
            require(row.get("filter_origin") is None, f"{context}: unexpected filter origin")
    require(sum(filter_counts.values()) >= protocol["minimum_filter_questions"], "Too few filter questions")
    require(filter_counts["test"] >= protocol["minimum_test_filter_questions"], "Too few test filter questions")


def validate_samples(samples: list[dict], pages: dict, protocol: dict) -> None:
    count = protocol["coherence_sampling"]["sample_count"]
    require(len(samples) == count, "Wrong coherence sample count")
    expected = sorted(pages)[:count]
    require([(s["source_id"], s["page"]) for s in samples] == expected,
            "Coherence samples differ from first-10-page policy")
    require(len({s["id"] for s in samples}) == count, "Duplicate coherence sample IDs")
    for sample in samples:
        page = pages[(sample["source_id"], sample["page"])]
        start = 0
        for paragraph in page["text"].split("\n\n"):
            if len(paragraph) >= 100:
                break
            start += len(paragraph) + 2
        else:
            raise ValueError(f"No substantive paragraph at {sample['id']}")
        reference = paragraph[:160]
        require(sample["reference_start_char"] == start and sample["reference_end_char"] == start + len(reference)
                and sample["reference_text"] == reference, f"{sample['id']}: reference differs from source policy")
        require(sample["anchor_offset"] == start + min(80, len(paragraph) - 1),
                f"{sample['id']}: wrong coherence anchor")
        require(sample["page_id"] == page["metadata"]["page_id"], f"{sample['id']}: wrong page ID")
        require(sample["label_status"] == "not_scored", f"{sample['id']}: unexpected pre-retrieval score")


def validate_dataset(root: Path, *, verify_pdf: bool = True) -> dict:
    rows = read_jsonl(root / "benchmark/questions.jsonl")
    corpus = read_jsonl(root / "data/processed/pages.jsonl")
    pages = {(p["document_id"], p["page"]): p for p in corpus}
    require(len(pages) == len(corpus), "Duplicate source/page in corpus")
    protocol = json.loads((root / "benchmark/protocol.json").read_text(encoding="utf-8"))
    samples = read_jsonl(root / "benchmark/coherence_samples.jsonl")
    validate_questions(rows, pages, protocol)
    validate_samples(samples, pages, protocol)
    manifest = json.loads((root / "data/manifest.json").read_text(encoding="utf-8"))
    source_path = root / manifest["source_path"]
    require(hashlib.sha256(source_path.read_bytes()).hexdigest() == manifest["sha256"], "PDF checksum mismatch")
    passages = [gold for row in rows for gold in [row, *row["alternative_gold_evidence"]]]
    physical_pages = sorted({g["gold_page"] for g in passages})
    if verify_pdf:
        for number in physical_pages:
            raw = subprocess.run(["pdftotext", "-f", str(number), "-l", str(number), "-layout", "-enc", "UTF-8",
                                  str(source_path), "-"], check=True, capture_output=True, text=True, timeout=30).stdout
            for gold in passages:
                if gold["gold_page"] == number:
                    require(fold(gold["evidence_quote"]) in fold(raw), f"PDF page {number}: evidence missing in re-extraction")
    return {
        "status": "passed", "question_count": len(rows),
        "split_counts": dict(Counter(r["split"] for r in rows)),
        "question_type_counts": dict(Counter(r["type"] for r in rows)),
        "filter_counts_by_split": dict(Counter(r["split"] for r in rows if r["filter"] is not None)),
        "accepted_evidence_passages": len(passages), "coherence_sample_count": len(samples),
        "pdf_reextraction_checked": verify_pdf, "verified_pdf_pages": physical_pages if verify_pdf else [],
        "semantic_review": "AI-assisted author review recorded per question; independent human confirmation pending.",
        "retrieval_executed_by_this_validator": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="Create initial snapshot after validation; never overwrite it")
    args = parser.parse_args()
    path = REPO_ROOT / "benchmark/freeze.json"
    if args.freeze:
        require(not path.exists(), "Benchmark already frozen; refusing to overwrite freeze.json")
    elif path.exists():
        verify_frozen_snapshot(REPO_ROOT)
    report = validate_dataset(REPO_ROOT)
    now = datetime.now(timezone.utc).isoformat()
    if args.freeze:
        freeze = {"benchmark_version": "1.0.0", "frozen_at": now,
                  "stage": "before_retrieval", "sha256": snapshot_hashes(REPO_ROOT)}
        with path.open("x", encoding="utf-8") as stream:
            json.dump(freeze, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    if path.exists():
        verify_frozen_snapshot(REPO_ROOT)
    report.update(checked_at=now, frozen_snapshot_verified=path.exists(),
                  validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output = REPO_ROOT / "results/benchmark_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"Benchmark validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
