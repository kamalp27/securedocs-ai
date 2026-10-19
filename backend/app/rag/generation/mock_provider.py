"""Mock generator provider for testing and validation of Q&A pipelines."""

import uuid
from typing import List, Optional
from app.rag.generation.base import BaseGeneratorProvider, GenerationError, GenerationResult, RawCitation
from app.schemas.search import SearchResultItem


class MockGeneratorProvider(BaseGeneratorProvider):
    """
    Mock generator allowing explicit test configuration of outputs,
    hallucinated citations, prompt injections, and simulated provider failures.
    """

    def __init__(
        self,
        canned_answer: Optional[str] = None,
        canned_citations: Optional[List[RawCitation]] = None,
        simulate_insufficient_evidence: bool = False,
        simulate_error: bool = False,
    ):
        self._canned_answer = canned_answer
        self._canned_citations = canned_citations
        self._simulate_insufficient_evidence = simulate_insufficient_evidence
        self._simulate_error = simulate_error

    @property
    def name(self) -> str:
        return "mock_generator"

    def generate(
        self,
        question: str,
        retrieved_chunks: List[SearchResultItem],
    ) -> GenerationResult:
        if self._simulate_error:
            raise GenerationError("Simulated generator provider failure.")

        if self._simulate_insufficient_evidence or not retrieved_chunks:
            return GenerationResult(
                answer="Insufficient evidence: I could not find sufficient evidence in your authorized documents to answer this question.",
                citations=[],
                insufficient_evidence=True,
                provider=self.name,
            )

        if self._canned_answer is not None:
            citations = self._canned_citations if self._canned_citations is not None else [
                RawCitation(
                    chunk_id=retrieved_chunks[0].chunk_id,
                    quoted_snippet=retrieved_chunks[0].content[:60],
                )
            ]
            return GenerationResult(
                answer=self._canned_answer,
                citations=citations,
                insufficient_evidence=False,
                provider=self.name,
            )

        # Default mock response using first retrieved chunk
        top_chunk = retrieved_chunks[0]
        snippet = top_chunk.content[:80] if len(top_chunk.content) >= 80 else top_chunk.content
        return GenerationResult(
            answer=f"Mock answer for '{question}': {snippet}",
            citations=[
                RawCitation(
                    chunk_id=top_chunk.chunk_id,
                    quoted_snippet=snippet,
                )
            ],
            insufficient_evidence=False,
            provider=self.name,
        )
