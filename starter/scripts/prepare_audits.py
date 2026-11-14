"""Prepare source-linked audit packets, without inventing semantic labels."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "starter"))
from scripts.validate_benchmark import read_jsonl, verify_frozen_snapshot
from src.ingestion import normalize_text, remove_running_header


def main() -> None:
    verify_frozen_snapshot(ROOT)
    pages = {(p["document_id"], p["page"]): p for p in read_jsonl(ROOT / "data/processed/pages.jsonl")}
    chunks = {s: read_jsonl(ROOT / f"results/chunks_{s}.jsonl") for s in "AB"}
    chunks["C"] = chunks["B"]
    coherence = []
    for sample in read_jsonl(ROOT / "benchmark/coherence_samples.jsonl"):
        for strategy in "ABC":
            candidates = [c for c in chunks[strategy] if c["document_id"] == sample["source_id"]
                          and c["page"] == sample["page"]
                          and c["metadata"]["start_char"] <= sample["anchor_offset"] < c["metadata"]["end_char"]]
            chosen = min(candidates, key=lambda c: (abs((c["metadata"]["start_char"] + c["metadata"]["end_char"])/2
                                                       - sample["anchor_offset"]),
                                                    c["metadata"]["start_char"], c["chunk_id"])) if candidates else None
            coherence.append({"sample_id": sample["id"], "strategy": strategy, "sample": sample, "chunk": chosen})
    pdf = ROOT / "data/raw/thinkpython2.pdf"
    source_cache, metadata = {}, []
    traces = read_jsonl(ROOT / "results/retrieval_test.jsonl")
    for trace in traces:
        for hit in trace["hits"]:
            actual = hit["metadata"]
            page = pages[actual["document_id"], actual["page"]]
            key = page["page"]
            if key not in source_cache:
                raw = subprocess.run(["pdftotext", "-f", str(key), "-l", str(key), "-layout", "-enc", "UTF-8",
                                      str(pdf), "-"], check=True, capture_output=True, text=True, timeout=30).stdout
                normalized = normalize_text(raw)
                extracted = remove_running_header(normalized, page["metadata"]["printed_page"], page["metadata"]["chapter"])
                if extracted != page["text"]:
                    raise ValueError(f"PDF re-extraction differs on page {key}")
                source_cache[key] = normalized[:220]
            expected = {**page["metadata"], "page": page["page"], "source": page["source"], "document_id": page["document_id"]}
            fields = ("document_id", "source", "page", "page_id", "printed_page", "chapter", "chapter_title",
                      "language", "version", "source_sha256")
            mismatches = [f for f in fields if type(actual.get(f)) is not type(expected[f]) or actual.get(f) != expected[f]]
            start, end = actual["start_char"], actual["end_char"]
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(page["text"])
                    or page["text"][start:end] != hit["text"] or actual["char_count"] != len(hit["text"])):
                mismatches.append("source_span")
            metadata.append({"strategy": trace["strategy"], "question_id": trace["question_id"], "rank": hit["rank"],
                             "chunk_id": hit["chunk_id"], "metadata": actual, "checked_fields": list(fields) + ["source_span"],
                             "automatic_mismatches": mismatches, "pdf_header_reference": source_cache[key]})
    packet = {"method": "Packets only: semantic labels require explicit source/text review; automatic consistency is not a semantic score",
              "coherence": coherence, "grounding": traces, "metadata": metadata,
              "pdf_pages_reextracted": sorted(source_cache)}
    output = ROOT / "results/audit_packets.json"
    output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"coherence_cases": len(coherence), "grounding_cases": len(traces),
                      "metadata_records": len(metadata), "pdf_pages_reextracted": sorted(source_cache)}))


if __name__ == "__main__":
    main()
