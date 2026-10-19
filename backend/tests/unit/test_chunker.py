"""Unit tests for RecursiveChunker and SimpleWordTokenizer."""

import pytest

from app.rag.chunking.recursive_chunker import RecursiveChunker, SimpleWordTokenizer
from app.rag.ingestion.base import ExtractedSegment


def test_chunker_parameter_validation():
    """Verify that invalid chunk sizes and overlaps raise ValueError."""
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        RecursiveChunker(chunk_size=0, chunk_overlap=0)

    with pytest.raises(ValueError, match="chunk_overlap cannot be negative"):
        RecursiveChunker(chunk_size=100, chunk_overlap=-5)

    with pytest.raises(ValueError, match="strictly less than chunk_size"):
        RecursiveChunker(chunk_size=100, chunk_overlap=100)

    with pytest.raises(ValueError, match="strictly less than chunk_size"):
        RecursiveChunker(chunk_size=100, chunk_overlap=150)


def test_chunker_empty_input():
    """Verify empty segments list or blank text produces empty chunks list."""
    chunker = RecursiveChunker(chunk_size=100, chunk_overlap=20)
    assert chunker.chunk_segments([]) == []

    empty_seg = ExtractedSegment(text="   \n\n  \t  ")
    assert chunker.chunk_segments([empty_seg]) == []


def test_chunker_short_text():
    """Verify text shorter than chunk_size produces exactly one chunk."""
    chunker = RecursiveChunker(chunk_size=50, chunk_overlap=10)
    seg = ExtractedSegment(
        text="A brief sentence that comfortably fits in one chunk.",
        page_number=1,
        section="Intro",
        start_char=0,
        end_char=52,
    )
    chunks = chunker.chunk_segments([seg])

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == seg.text
    assert chunks[0].metadata_json["page_number"] == 1
    assert chunks[0].metadata_json["section"] == "Intro"
    assert chunks[0].token_count > 0


def test_chunker_paragraph_boundaries_and_sequential_indices():
    """Verify chunker respects paragraph boundaries and assigns sequential 0-based indices."""
    chunker = RecursiveChunker(chunk_size=20, chunk_overlap=5)
    p1 = "Paragraph one contains some meaningful content about system architecture."
    p2 = "Paragraph two describes database schema, user permissions, and audit logs."
    p3 = "Paragraph three covers vector retrieval and FAISS indexing performance."

    seg = ExtractedSegment(
        text=f"{p1}\n\n{p2}\n\n{p3}",
        page_number=2,
        section="Chapter 1",
        start_char=100,
        end_char=100 + len(p1) + len(p2) + len(p3) + 4,
    )
    chunks = chunker.chunk_segments([seg])

    assert len(chunks) >= 3
    # Check sequential indices: 0, 1, 2, ...
    for i, c in enumerate(chunks):
        assert c.chunk_index == i
        assert c.metadata_json["page_number"] == 2
        assert c.metadata_json["section"] == "Chapter 1"


def test_chunker_overlap_behavior_and_no_duplicates():
    """Verify that overlap carries context forward without creating duplicate-only chunks."""
    chunker = RecursiveChunker(chunk_size=15, chunk_overlap=5)
    words = [f"word{i}" for i in range(40)]
    long_text = " ".join(words)

    seg = ExtractedSegment(text=long_text)
    chunks = chunker.chunk_segments([seg])

    assert len(chunks) > 1
    # Check that consecutive chunks are not identical
    for i in range(len(chunks) - 1):
        assert chunks[i].content != chunks[i + 1].content

    # Check that tail of first chunk shares words with start of second chunk
    first_words = chunks[0].content.split()
    second_words = chunks[1].content.split()
    overlap_shared = set(first_words[-3:]).intersection(set(second_words[:5]))
    assert len(overlap_shared) > 0


def test_chunker_unicode_preservation():
    """Verify Unicode symbols, emojis, and non-ASCII text are preserved."""
    chunker = RecursiveChunker(chunk_size=20, chunk_overlap=5)
    unicode_text = "SecureDocs AI supports multilingual documents: 日本語, Español, Français, and emojis 🔒📄."
    seg = ExtractedSegment(text=unicode_text)
    chunks = chunker.chunk_segments([seg])

    assert len(chunks) >= 1
    assert "日本語" in chunks[0].content
    assert "🔒📄" in chunks[-1].content


def test_chunker_offsets_accuracy():
    """Verify start_char and end_char accurately bound the chunk content within the source."""
    chunker = RecursiveChunker(chunk_size=25, chunk_overlap=5)
    source = "The quick brown fox jumps over the lazy dog. More text continues here to test offsets."
    seg = ExtractedSegment(text=source, start_char=50, end_char=50 + len(source))
    chunks = chunker.chunk_segments([seg])

    for c in chunks:
        # Start and end chars must be within segment bounds
        assert c.metadata_json["start_char"] >= 50
        assert c.metadata_json["end_char"] <= 50 + len(source)
        assert c.metadata_json["end_char"] > c.metadata_json["start_char"]


def test_chunker_oversized_unbreakable_string():
    """Verify continuous string with no whitespace is safely split without hanging."""
    chunker = RecursiveChunker(chunk_size=10, chunk_overlap=2)
    # 200 characters with zero spaces/punctuation
    unbreakable = "A" * 200
    seg = ExtractedSegment(text=unbreakable)
    chunks = chunker.chunk_segments([seg])

    assert len(chunks) > 1
    for c in chunks:
        assert len(c.content) > 0
