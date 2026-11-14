"""Two page-local chunkers; offsets refer to the unchanged normalized page text."""
import copy
import hashlib
import json
import re

from .models import Chunk, DocumentPage


def _chunk(page: DocumentPage, start: int, end: int, method: str, parameters: dict) -> Chunk:
    text = page.text[start:end]
    page_hash = hashlib.sha256(page.text.encode("utf-8")).hexdigest()
    identity = [page.document_id, page.source, page.page, page.metadata.get("source_sha256"),
                page_hash, method, parameters, start, end]
    chunk_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    metadata = {**copy.deepcopy(page.metadata), "document_id": page.document_id,
                "source": page.source, "page": page.page, "start_char": start, "end_char": end,
                "page_char_count": len(page.text), "char_count": len(text),
                "chunking": method, "chunk_parameters": parameters.copy()}
    return Chunk(chunk_id, page.document_id, page.source, page.page, text, metadata)


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split into exact character windows, without crossing physical pages."""
    if type(size) is not int or size <= 0 or type(overlap) is not int or not 0 <= overlap < size:
        raise ValueError("Require size > 0 and 0 <= overlap < size (integers)")
    chunks = []
    for start in range(0, len(page.text), size - overlap):
        end = min(start + size, len(page.text))
        if page.text[start:end].strip():
            chunks.append(_chunk(page, start, end, "fixed_size", {"size": size, "overlap": overlap}))
        if end == len(page.text):
            break
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Pack blank-line paragraphs; split long ones at lines/words, then hard limit.

    Keep each span verbatim, including code indentation and separators. No
    overlap. Lines longer than max_size may need splitting inside code/text.
    """
    if type(max_size) is not int or max_size <= 0:
        raise ValueError("max_size must be a positive integer")
    chunks = []
    start = end = 0
    paragraph_ends = [m.end() for m in re.finditer(r"\n[ \t]*\n+", page.text)] + [len(page.text)]
    for paragraph_end in paragraph_ends:
        if paragraph_end - start > max_size and end > start:
            if page.text[start:end].strip():
                chunks.append(_chunk(page, start, end, "paragraph", {"max_size": max_size}))
            start = end
        while paragraph_end - start > max_size:
            limit = start + max_size
            cut = page.text.rfind("\n", start, limit) + 1
            if cut <= start:
                space = page.text.rfind(" ", start, limit)
                cut = space + 1 if space >= start + max_size // 2 else limit
            if page.text[start:cut].strip():
                chunks.append(_chunk(page, start, cut, "paragraph", {"max_size": max_size}))
            start = cut
        end = paragraph_end
    if page.text[start:end].strip():
        chunks.append(_chunk(page, start, end, "paragraph", {"max_size": max_size}))
    return chunks


def fit_token_limit(page: DocumentPage, chunks: list[Chunk], count_tokens,
                    max_tokens: int, tokenizer_revision: str) -> list[Chunk]:
    """Split only oversized spans; keep text/offsets and never truncate silently."""
    if type(max_tokens) is not int or max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    fitted = []
    for chunk in chunks:
        if count_tokens(chunk.text) <= max_tokens:
            pieces = [chunk]
        else:
            pieces = []
            start, stop = chunk.metadata["start_char"], chunk.metadata["end_char"]
            while start < stop:
                end = stop
                # Small source spans (<=500 chars): scanning down is simple and
                # avoids assuming tokenizer length is monotonic in character count.
                while end > start and count_tokens(page.text[start:end]) > max_tokens:
                    end -= 1
                if end == start:
                    raise ValueError("A source character cannot fit the token budget")
                boundary = max(page.text.rfind("\n", start, end), page.text.rfind(" ", start, end)) + 1
                if end < stop and boundary > start + (end - start) // 2 and count_tokens(page.text[start:boundary]) <= max_tokens:
                    end = boundary
                if page.text[start:end].strip():
                    params = {**chunk.metadata["chunk_parameters"], "max_tokens": max_tokens,
                              "tokenizer_revision": tokenizer_revision}
                    piece = _chunk(page, start, end, chunk.metadata["chunking"], params)
                    piece.metadata["parent_chunk_id"] = chunk.chunk_id
                    pieces.append(piece)
                start = end
        for piece in pieces:
            piece.metadata.update(token_count=count_tokens(piece.text), max_tokens=max_tokens,
                                  tokenizer_revision=tokenizer_revision)
        fitted.extend(pieces)
    return fitted
