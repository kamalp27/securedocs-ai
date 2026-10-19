"""Base interfaces and data structures for generative Q&A providers."""

import uuid
from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.search import SearchResultItem


class GenerationError(Exception):
    """Raised when answer generation fails due to provider or configuration error."""
    pass


class RawCitation(BaseModel):
    """
    Unvalidated citation proposed by a generator before verification against source chunks.
    """

    chunk_id: uuid.UUID
    quoted_snippet: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class GenerationResult(BaseModel):
    """Internal output structure produced by a generator provider."""

    answer: str
    citations: List[RawCitation] = Field(default_factory=list)
    insufficient_evidence: bool = False
    provider: str

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class BaseGeneratorProvider(ABC):
    """
    Abstract interface for grounded Q&A generation providers.
    Implementations may be local deterministic extractors, local LLMs (Ollama/llama.cpp),
    or external API models.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier (e.g. 'deterministic_extractive', 'mock')."""
        pass

    @abstractmethod
    def generate(
        self,
        question: str,
        retrieved_chunks: List[SearchResultItem],
    ) -> GenerationResult:
        """
        Generate a grounded answer and candidate citations strictly using retrieved chunks.

        :param question: The user query string.
        :param retrieved_chunks: Authorized chunks retrieved via semantic search.
        :return: GenerationResult containing answer, candidate citations, and evidence flags.
        """
        pass
