"""Build the pinned Python basics corpus. Run from any working directory."""
import hashlib
import json
import platform
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
REPO_ROOT = STARTER.parent
sys.path.insert(0, str(STARTER))

from src.ingestion import load_pdf, record_issue, remove_running_header  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    config = json.loads((REPO_ROOT / "data/corpus_config.json").read_text(encoding="utf-8"))
    raw_path = REPO_ROOT / config["source_path"]
    error_log = REPO_ROOT / "results/ingestion_errors.jsonl"
    error_log.parent.mkdir(parents=True, exist_ok=True)
    error_log.write_text("", encoding="utf-8")
    if not raw_path.exists():
        record_issue(error_log, kind="missing_source", detail=config["source_path"])
        raise FileNotFoundError("Download the pinned PDF first; see starter/CHANGELOG.md at repository root")
    checksum = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    if checksum != config["sha256"]:
        record_issue(error_log, kind="checksum_mismatch", actual=checksum, expected=config["sha256"])
        raise ValueError("Source snapshot changed: review corpus_config.json before proceeding")

    pages = load_pdf(raw_path, config["source_id"], config["source_url"], error_log=error_log)
    selected = {}
    for item in config["selection"]:
        start, end = item["pdf_start"], item["pdf_end"]
        if not 1 <= start <= end <= len(pages):
            raise ValueError(f"Invalid page range: {start}-{end}")
        # Verify the metadata against the actual chapter opening in this snapshot.
        opening = pages[start - 1].text
        if f"Chapter {item['chapter']}\n" not in opening:
            raise ValueError(f"Chapter metadata mismatch at PDF page {start}")
        if item["chapter_title"] not in " ".join(opening.split()):
            raise ValueError(f"Chapter title mismatch at PDF page {start}")
        for number in range(start, end + 1):
            if number in selected:
                raise ValueError(f"Duplicate selected page: {number}")
            selected[number] = item

    records, page_manifest = [], []
    for page in pages:
        original_chars = len(page.text)
        item = selected.get(page.page)
        if item:
            printed = page.page + config["printed_page_offset"]
            original = page.text
            page.text = remove_running_header(original, printed, item["chapter"])
            if not page.text:
                record_issue(error_log, kind="empty_selected_page", page=page.page)
                raise ValueError(f"Selected page {page.page} has no content")
            page.metadata.update({
                "page_id": f"{config['source_id']}:pdf-{page.page:03d}",
                "printed_page": printed,
                "chapter": item["chapter"], "chapter_title": item["chapter_title"],
                "language": config["language"], "version": config["version"],
                "source_sha256": checksum,
                "char_count": len(page.text), "header_removed": original != page.text,
            })
            records.append(asdict(page))
        page_manifest.append({
            "page": page.page, "page_id": f"{config['source_id']}:pdf-{page.page:03d}",
            "included": item is not None,
            "reason": "Selected instructional content/glossary" if item else (
                "No extractable text" if not page.text else (
                    "Front matter: cover, license, preface or contents" if page.page < 23
                    else "Outside selected instructional ranges")),
            "normalized_char_count": len(page.text),
            "extracted_normalized_char_count": original_chars,
        })
    if len(records) < 30:
        raise ValueError(f"Need at least 30 content pages, got {len(records)}")
    output = REPO_ROOT / "data/processed/pages.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    poppler = subprocess.run(["pdftotext", "-v"], check=True, capture_output=True, text=True)
    issues = [json.loads(line) for line in error_log.read_text(encoding="utf-8").splitlines()]
    stats = {
        "source_id": config["source_id"], "source_sha256": checksum,
        "physical_pages": len(pages), "included_content_pages": len(records),
        "excluded_pages": len(pages) - len(records),
        "included_pdf_pages": [r["page"] for r in records],
        "pages_by_chapter": dict(Counter(str(r["metadata"]["chapter"]) for r in records)),
        "total_chars": sum(len(r["text"]) for r in records),
        "min_page_chars": min(len(r["text"]) for r in records),
        "max_page_chars": max(len(r["text"]) for r in records),
        "issue_counts": dict(Counter(i["kind"] for i in issues)),
        "python": platform.python_version(), "pypdf": version("pypdf"),
        "poppler": (poppler.stderr or poppler.stdout).splitlines()[0],
        "run_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest = {**config,
        "counting_rule": "Count each selected physical PDF page once; exclude front matter, blanks and all unselected ranges. Selected chapter openings contain substantive instruction; glossaries are instructional content. No duplicated pages.",
        "page_reference_rule": "page is 1-based physical PDF page; printed_page = page - 22 for selected ranges, verified against printed headers.",
        "transformations": ["Poppler layout extraction", "Unicode NFC; normalized line endings and blank lines", "Preserved code indentation, punctuation and line-end hyphens", "Removed verified first-line running headers"],
        "metadata_schema": {
            "chapter": {"type": "integer", "source": "Chapter heading and running headers in PDF", "purpose": "Filter by chapter explicitly requested in query/context"},
            "chapter_title": {"type": "string", "source": "Chapter heading in PDF"},
            "language": {"type": "string", "source": "English source text"},
            "version": {"type": "string", "source": "PDF cover, physical page 1"},
        },
        "limitations": ["English corpus; query language must be documented in benchmark", "Figures and diagrams are not represented faithfully in plain text", "Printed line-end hyphenation retained to avoid modifying code", "Selected page ranges are excerpts, not complete chapters"],
        "attribution": "Think Python, 2nd Edition, Version 2.4.1, Allen B. Downey, copyright 2015. Source: https://greenteapress.com/thinkpython2/thinkpython2.pdf. CC BY-NC 3.0. Derived text normalized and selected for a noncommercial educational lab; original PDF unchanged.",
        "physical_page_count": len(pages), "content_page_count": len(records),
        "pages": page_manifest,
    }
    write_json(REPO_ROOT / "data/manifest.json", manifest)
    write_json(REPO_ROOT / "results/ingestion_stats.json", stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
