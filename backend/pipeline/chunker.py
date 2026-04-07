"""Paragraph-aware text chunking for per-chunk classification.

Ported from Shiv-Evil-AI-Finder/src/chunker.py.
"""
from __future__ import annotations

import re
from typing import List

from backend.pipeline.io_utils import stable_hash
from backend.schemas import CleanDocument, DocumentChunk


def chunk_document(
    doc: CleanDocument,
    *,
    max_chunk_chars: int = 1200,
) -> List[DocumentChunk]:
    """Split a clean document into overlapping chunks for classification.

    Each chunk respects paragraph boundaries when possible.
    """
    text = doc.cleaned_text
    if not text or len(text.strip()) < 20:
        return []

    paragraphs = doc.paragraphs or _split_paragraphs(text)
    if not paragraphs:
        return [_make_chunk(doc, text, 0, len(text), 0)]

    chunks: List[DocumentChunk] = []
    current_parts: List[str] = []
    current_len = 0
    chunk_start = 0
    offset = 0

    for paragraph in paragraphs:
        para_len = len(paragraph)
        # If a single paragraph exceeds the limit, split it further
        if para_len > max_chunk_chars:
            # Flush current buffer first
            if current_parts:
                chunk_text = "\n\n".join(current_parts)
                chunks.append(
                    _make_chunk(doc, chunk_text, chunk_start, offset, len(chunks))
                )
                current_parts = []
                current_len = 0
                chunk_start = offset

            # Split long paragraph on sentences
            for sentence_chunk in _split_long_text(paragraph, max_chunk_chars):
                chunks.append(
                    _make_chunk(doc, sentence_chunk, offset, offset + len(sentence_chunk), len(chunks))
                )
            offset += para_len
            chunk_start = offset
            continue

        # Would adding this paragraph exceed the limit?
        if current_len + para_len + 2 > max_chunk_chars and current_parts:
            chunk_text = "\n\n".join(current_parts)
            chunks.append(
                _make_chunk(doc, chunk_text, chunk_start, offset, len(chunks))
            )
            current_parts = []
            current_len = 0
            chunk_start = offset

        current_parts.append(paragraph)
        current_len += para_len + 2
        offset += para_len

    # Flush remaining
    if current_parts:
        chunk_text = "\n\n".join(current_parts)
        chunks.append(
            _make_chunk(doc, chunk_text, chunk_start, offset, len(chunks))
        )

    return chunks


def _make_chunk(
    doc: CleanDocument,
    text: str,
    start: int,
    end: int,
    index: int,
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=stable_hash(doc.document_id, str(index)),
        document_id=doc.document_id,
        source_url=doc.source_url,
        source_title=doc.source_title,
        source_type=doc.source_type,
        publication_date=doc.publication_date,
        text=text,
        start_offset=start,
        end_offset=end,
    )


def _split_paragraphs(text: str) -> List[str]:
    """Fallback paragraph splitter."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_long_text(text: str, max_chars: int) -> List[str]:
    """Split text on sentence boundaries to fit within max_chars."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for sentence in sentences:
        if current_len + len(sentence) + 1 > max_chars and current:
            chunks.append(" ".join(current))
            current = []
            current_len = 0
        current.append(sentence)
        current_len += len(sentence) + 1

    if current:
        chunks.append(" ".join(current))

    return chunks
