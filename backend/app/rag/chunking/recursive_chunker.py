"""Deterministic recursive text chunker preserving document structure, page metadata, and offsets."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.rag.ingestion.base import ExtractedSegment


@dataclass
class ChunkOutput:
    """A single generated text chunk with positional metadata and token count."""
    chunk_index: int
    content: str
    token_count: int
    metadata_json: Dict[str, Any]


class SimpleWordTokenizer:
    """
    Lightweight, deterministic regex-based tokenizer.
    Splits text on word boundaries and punctuation symbols, providing
    an accurate token count without external heavy ML dependencies.
    """

    TOKEN_REGEX = re.compile(r"\w+|[^\w\s]", re.UNICODE)

    def count_tokens(self, text: str) -> int:
        """Count linguistic tokens (words + punctuation symbols) in text."""
        if not text:
            return 0
        tokens = self.TOKEN_REGEX.findall(text)
        total = 0
        for tok in tokens:
            if len(tok) > 16:
                total += max(1, (len(tok) + 3) // 4)
            else:
                total += 1
        return total


class RecursiveChunker:
    """
    Recursive character/token splitter that respects structural boundaries:
    paragraphs -> lines -> sentences -> words -> characters.
    """

    SEPARATORS = [
        "\n\n",   # Paragraphs
        "\n",     # Lines
        ". ",     # Sentences (period)
        "? ",     # Sentences (question)
        "! ",     # Sentences (exclamation)
        "; ",     # Clauses
        " ",      # Words
        "",       # Characters (ultimate fallback)
    ]

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        tokenizer: Optional[SimpleWordTokenizer] = None,
    ):
        """
        Initialize chunker with validated size and overlap constraints.
        Raises ValueError if parameters are invalid.
        """
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive (got {chunk_size}).")
        if chunk_overlap < 0:
            raise ValueError(f"chunk_overlap cannot be negative (got {chunk_overlap}).")
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) must be strictly less than chunk_size ({chunk_size})."
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tokenizer or SimpleWordTokenizer()

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        """Recursively split text using the first separator that successfully partitions it."""
        if not text.strip():
            return []

        token_count = self.tokenizer.count_tokens(text)
        if token_count <= self.chunk_size:
            return [text.strip()]

        if not separators:
            # Fallback character slice if no more separators exist
            # Approximate chars per token as 4
            slice_len = max(self.chunk_size * 4, 1)
            return [text[i:i + slice_len].strip() for i in range(0, len(text), slice_len) if text[i:i + slice_len].strip()]

        sep = separators[0]
        remaining_seps = separators[1:]

        if sep == "":
            # Character-level split
            slice_len = max(self.chunk_size * 4, 1)
            return [text[i:i + slice_len].strip() for i in range(0, len(text), slice_len) if text[i:i + slice_len].strip()]

        splits = text.split(sep)
        splits = [s.strip() for s in splits if s.strip()]

        result: List[str] = []
        for piece in splits:
            if self.tokenizer.count_tokens(piece) <= self.chunk_size:
                result.append(piece)
            else:
                result.extend(self._split_text(piece, remaining_seps))

        return result

    def _merge_splits_with_overlap(self, pieces: List[str]) -> List[str]:
        """
        Merge small split pieces into chunks up to chunk_size, carrying chunk_overlap
        forward into subsequent chunks to maintain context across boundaries.
        Guarantees loop termination and prevents duplicate chunks.
        """
        chunks: List[str] = []
        current_pieces: List[str] = []
        current_token_count = 0

        for piece in pieces:
            piece_tokens = self.tokenizer.count_tokens(piece)
            if piece_tokens == 0:
                continue

            if current_token_count + piece_tokens <= self.chunk_size:
                current_pieces.append(piece)
                current_token_count += piece_tokens
            else:
                if current_pieces:
                    chunk_text = " ".join(current_pieces).strip()
                    if chunk_text:
                        chunks.append(chunk_text)

                    # Build overlap from tail of current_pieces
                    overlap_pieces: List[str] = []
                    overlap_count = 0
                    for p in reversed(current_pieces):
                        p_cnt = self.tokenizer.count_tokens(p)
                        if overlap_count + p_cnt <= self.chunk_overlap:
                            overlap_pieces.insert(0, p)
                            overlap_count += p_cnt
                        else:
                            break

                    current_pieces = overlap_pieces + [piece]
                    current_token_count = sum(self.tokenizer.count_tokens(p) for p in current_pieces)
                else:
                    # Single oversized piece: append directly
                    chunks.append(piece)
                    current_pieces = []
                    current_token_count = 0

        if current_pieces:
            chunk_text = " ".join(current_pieces).strip()
            if chunk_text:
                chunks.append(chunk_text)

        return chunks

    def chunk_segments(self, segments: List[ExtractedSegment]) -> List[ChunkOutput]:
        """
        Transform extracted document segments into sequential, indexed ChunkOutput objects.
        Preserves page numbers, section titles, and character spans.
        """
        all_chunks: List[ChunkOutput] = []
        chunk_idx = 0

        for seg in segments:
            if not seg.text or not seg.text.strip():
                continue

            # Split segment recursively
            splits = self._split_text(seg.text, self.SEPARATORS)
            merged_chunks = self._merge_splits_with_overlap(splits)

            cursor = 0
            for chunk_content in merged_chunks:
                clean_content = chunk_content.strip()
                if not clean_content:
                    continue

                tok_count = self.tokenizer.count_tokens(clean_content)

                # Locate character offsets within the segment text using advancing cursor
                start_in_seg = seg.text.find(clean_content, cursor)
                if start_in_seg == -1:
                    start_in_seg = seg.text.find(clean_content)

                if start_in_seg != -1:
                    actual_start = seg.start_char + start_in_seg
                    actual_end = actual_start + len(clean_content)
                    cursor = max(cursor, start_in_seg + 1)
                else:
                    actual_start = seg.start_char
                    actual_end = seg.end_char

                meta = {
                    "page_number": seg.page_number,
                    "section": seg.section,
                    "start_char": actual_start,
                    "end_char": actual_end,
                }

                all_chunks.append(
                    ChunkOutput(
                        chunk_index=chunk_idx,
                        content=clean_content,
                        token_count=tok_count,
                        metadata_json=meta,
                    )
                )
                chunk_idx += 1

        return all_chunks
