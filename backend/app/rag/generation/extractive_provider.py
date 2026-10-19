"""Deterministic extractive Q&A provider for offline, zero-API-key operation."""

import re
from typing import List, Set, Tuple
from app.rag.generation.base import BaseGeneratorProvider, GenerationResult, RawCitation
from app.schemas.search import SearchResultItem

STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "did", "do", "does", "doing", "don't", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is",
    "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs",
    "them", "themselves", "then", "there", "these", "they", "this", "those",
    "through", "to", "too", "under", "until", "up", "very", "was", "we", "were",
    "what", "when", "where", "which", "while", "who", "whom", "why", "with",
    "would", "you", "your", "yours", "yourself", "yourselves",
}


def tokenize(text: str) -> List[str]:
    """Extract lowercase alpha-numeric tokens from text."""
    return [t.lower() for t in re.findall(r"\b\w+\b", text)]


def split_sentences(text: str) -> List[str]:
    """Split text into sentences while preserving meaningful segments."""
    # Split on sentence terminals followed by whitespace
    raw_sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in raw_sentences if s.strip()]
    if not sentences and text.strip():
        sentences = [text.strip()]
    return sentences


class DeterministicExtractiveProvider(BaseGeneratorProvider):
    """
    Deterministic offline Q&A engine.
    Extracts directly grounded sentences from authorized retrieved chunks with exact citations.
    Requires no GPU, no network requests, and no paid API keys.
    """

    @property
    def name(self) -> str:
        return "deterministic_extractive"

    def generate(
        self,
        question: str,
        retrieved_chunks: List[SearchResultItem],
    ) -> GenerationResult:
        """
        Synthesize an extractive answer grounded strictly in retrieved chunks.
        """
        if not retrieved_chunks:
            return GenerationResult(
                answer="Insufficient evidence: I could not find sufficient evidence in your authorized documents to answer this question.",
                citations=[],
                insufficient_evidence=True,
                provider=self.name,
            )

        q_tokens = [t for t in tokenize(question) if t not in STOPWORDS]

        # Score candidate sentences from retrieved chunks
        candidate_sentences: List[Tuple[float, str, SearchResultItem]] = []

        for chunk_idx, chunk in enumerate(retrieved_chunks):
            sentences = split_sentences(chunk.content)
            base_score = float(chunk.similarity_score)

            for sentence in sentences:
                s_tokens = set(tokenize(sentence))
                if not s_tokens:
                    continue

                if q_tokens:
                    overlap = sum(1 for t in q_tokens if t in s_tokens)
                    token_overlap_ratio = overlap / max(1, len(q_tokens))
                else:
                    token_overlap_ratio = 0.0

                # Score combines FAISS semantic similarity with question term overlap
                # and penalizes rank position slightly
                rank_discount = 1.0 / (1.0 + 0.1 * chunk_idx)
                sentence_score = (base_score * 0.6 + token_overlap_ratio * 0.4) * rank_discount

                if token_overlap_ratio > 0 or chunk_idx == 0:
                    candidate_sentences.append((sentence_score, sentence, chunk))

        # Check if any evidence is relevant
        if not candidate_sentences:
            return GenerationResult(
                answer="Insufficient evidence: I could not find sufficient evidence in your authorized documents to answer this question.",
                citations=[],
                insufficient_evidence=True,
                provider=self.name,
            )

        # Sort descending by relevance score
        candidate_sentences.sort(key=lambda x: x[0], reverse=True)

        # Take up to top 2 distinct sentences for a concise answer
        selected_sentences: List[str] = []
        raw_citations: List[RawCitation] = []
        seen_chunk_ids = set()

        for score, sentence, chunk in candidate_sentences:
            if len(selected_sentences) >= 2:
                break
            # Avoid repeating nearly identical sentences
            if any(sentence.lower() in s.lower() or s.lower() in sentence.lower() for s in selected_sentences):
                continue

            selected_sentences.append(sentence)

            if chunk.chunk_id not in seen_chunk_ids:
                raw_citations.append(
                    RawCitation(
                        chunk_id=chunk.chunk_id,
                        quoted_snippet=sentence,  # exact verbatim substring from chunk.content
                    )
                )
                seen_chunk_ids.add(chunk.chunk_id)

        if not selected_sentences:
            # Fallback to top chunk direct snippet
            top_chunk = retrieved_chunks[0]
            first_sentence = split_sentences(top_chunk.content)[0]
            selected_sentences.append(first_sentence)
            raw_citations.append(
                RawCitation(
                    chunk_id=top_chunk.chunk_id,
                    quoted_snippet=first_sentence,
                )
            )

        # Build clean answer text with citation markers
        answer_body = " ".join(selected_sentences)
        answer = f"According to your documents: {answer_body}"

        return GenerationResult(
            answer=answer,
            citations=raw_citations,
            insufficient_evidence=False,
            provider=self.name,
        )
