"""Extract physical PDF pages with Poppler; preserve paragraphs and code layout."""
import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .models import DocumentPage


def record_issue(error_log: Path | None, **issue: Any) -> None:
    """Append a structured issue. The caller owns resetting the log per run."""
    if error_log is not None:
        error_log.parent.mkdir(parents=True, exist_ok=True)
        with error_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(issue, ensure_ascii=False) + "\n")


def load_pdf(path: Path, document_id: str, source: str,
             *, error_log: Path | None = None) -> list[DocumentPage]:
    """Return every physical page, including empty pages, with 1-based numbering.

    Poppler's layout mode preserves code indentation and spaces around inline
    fonts better than pypdf on the selected corpus. pypdf validates page count.
    Fail explicitly on extraction errors; never silently skip unreadable pages.
    """
    try:
        executable = shutil.which("pdftotext")
        if executable is None:
            raise RuntimeError("pdftotext is required: install poppler-utils")
        with path.open("rb") as stream:
            reader = PdfReader(stream, strict=True)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDFs are not supported by this loader")
            page_count = len(reader.pages)
        result = subprocess.run(
            [executable, "-layout", "-enc", "UTF-8", str(path.resolve()), "-"],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        if result.stderr.strip():
            record_issue(error_log, document_id=document_id, source=source,
                         kind="extractor_warning", detail=result.stderr.strip())
        raw_pages = result.stdout.split("\f")
        if raw_pages and not raw_pages[-1].strip():
            raw_pages.pop()  # Poppler emits a trailing page separator.
        if len(raw_pages) != page_count:
            raise ValueError(f"Page count mismatch: PDF={page_count}, extracted={len(raw_pages)}")
        pages = []
        for number, raw in enumerate(raw_pages, start=1):
            text = normalize_text(raw)
            if not text:
                record_issue(error_log, document_id=document_id, source=source,
                             page=number, kind="empty_page", detail="No extractable text; OCR not applied")
            pages.append(DocumentPage(document_id, source, number, text,
                                      {"extraction_backend": "poppler-layout"}))
        return pages
    except Exception as exc:
        record_issue(error_log, document_id=document_id, source=source,
                     kind="load_error", error_type=type(exc).__name__, detail=str(exc))
        raise


def normalize_text(text: str) -> str:
    """Normalize NFC and line endings without collapsing indentation or paragraphs.

    Keep punctuation, operators and printed line-end hyphens verbatim. Global
    dehyphenation could corrupt Python code, so it is deliberately not applied.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\x00", "").expandtabs(4)
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


def remove_running_header(text: str, printed_page: int, chapter: int) -> str:
    """Remove only a verified Think Python running header on the first line.

    Keep actual section headings (e.g. '3.3 Composition') and chapter openings.
    """
    lines = text.splitlines()
    if not lines:
        return text
    number = re.escape(str(printed_page))
    patterns = [
        rf"\s*{number}\s+Chapter {chapter}\. .+\s*",
        rf"\s*{chapter}\.\d+\. .+\s+{number}\s*",
    ]
    if any(re.fullmatch(pattern, lines[0]) for pattern in patterns):
        return normalize_text("\n".join(lines[1:]))
    return text
