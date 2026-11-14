"""Export A/B chunks; C reuses B. No embedding, retrieval or benchmark scoring."""
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from statistics import mean, median
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))

from src.chunking import by_paragraph, fixed_size, fit_token_limit
from src.models import DocumentPage
from scripts.validate_benchmark import read_jsonl, verify_frozen_snapshot


def main() -> None:
    from transformers import AutoTokenizer

    verify_frozen_snapshot(ROOT)
    config_path = ROOT / "starter/strategies.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if (set(config) != {"A", "B", "C"} or config["A"].get("chunking") != "fixed_size"
            or config["B"].get("chunking") != "paragraph"
            or config["A"].get("use_question_filter") is not False
            or config["B"].get("use_question_filter") is not False
            or config["C"] != {"chunks_from": "B", "use_question_filter": True}):
        raise ValueError("Require A=fixed/no filter, B=paragraph/no filter, C=B plus question filter")
    pages = [DocumentPage(**row) for row in read_jsonl(ROOT / "data/processed/pages.jsonl")]
    model_config = json.loads((ROOT / "starter/model_config.json").read_text())
    tokenizer = AutoTokenizer.from_pretrained(model_config["model_name"], revision=model_config["revision"],
                                             cache_dir=str(ROOT / model_config["cache_path"]))
    def count_tokens(text):
        return len(tokenizer(text, truncation=False, add_special_tokens=True)["input_ids"])
    stats = {"source_pages": len(pages), "source_chars": sum(len(p.text) for p in pages),
             "strategies_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
             "model_config_sha256": hashlib.sha256((ROOT / "starter/model_config.json").read_bytes()).hexdigest(),
             "max_tokens_including_special_tokens": model_config["max_tokens"],
             "timing_scope": "chunking only; excludes embedding and database ingestion",
             "strategies": {}}
    for strategy in ("A", "B"):
        settings = config[strategy]
        start_time = perf_counter()
        chunks = []
        for page in pages:
            if strategy == "A":
                selected = fixed_size(page, settings["size"], settings["overlap"])
            else:
                selected = by_paragraph(page, settings["max_size"])
            selected = fit_token_limit(page, selected, count_tokens, model_config["max_tokens"], model_config["revision"])
            coverage = [False] * len(page.text)
            for chunk in selected:
                start, end = chunk.metadata["start_char"], chunk.metadata["end_char"]
                if chunk.text != page.text[start:end]:
                    raise ValueError(f"Chunk differs from page span: {chunk.chunk_id}")
                coverage[start:end] = [True] * (end - start)
            if any(not covered and not char.isspace() for covered, char in zip(coverage, page.text)):
                raise ValueError(f"Content lost on {page.document_id}, PDF page {page.page}")
            chunks.extend(selected)
        seconds = perf_counter() - start_time
        if len({c.chunk_id for c in chunks}) != len(chunks):
            raise ValueError(f"Duplicate chunk IDs in {strategy}")
        output = ROOT / f"results/chunks_{strategy}.jsonl"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("".join(json.dumps(asdict(c), ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")
        lengths = [len(c.text) for c in chunks]
        stats["strategies"][strategy] = {
            "config": settings, "chunks_file": str(output.relative_to(ROOT)), "chunk_count": len(chunks),
            "total_chars_including_overlap": sum(lengths), "min_chars": min(lengths),
            "median_chars": median(lengths), "mean_chars": mean(lengths), "max_chars": max(lengths),
            "length_buckets": dict(sorted(Counter(f"{(n-1)//100*100+1}-{(n-1)//100*100+100}" for n in lengths).items())),
            "chunking_seconds": seconds,
            "max_tokens": max(c.metadata["token_count"] for c in chunks),
        }
    stats["strategies"]["C"] = {"config": config["C"], "chunks_file": "results/chunks_B.jsonl",
                                  "chunk_count": stats["strategies"]["B"]["chunk_count"], "reuses_chunks_from": "B"}
    (ROOT / "results/chunking_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
