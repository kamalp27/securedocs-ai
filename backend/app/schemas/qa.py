"""Pydantic v2 schemas for Grounded Generative Q&A and Citations."""

import uuid
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    """
    Structured citation referencing a verified retrieved document chunk.
    Guaranteed to point only to chunks actually retrieved and verified.
    """

    chunk_id: uuid.UUID = Field(
        ...,
        description="Unique identifier of the verified source document chunk",
    )
    document_id: uuid.UUID = Field(
        ...,
        description="Unique identifier of the parent document",
    )
    original_filename: str = Field(
        ...,
        description="Original filename of the source document",
    )
    page_number: Optional[int] = Field(
        default=None,
        description="Page number where the chunk content originated (if applicable)",
    )
    section: Optional[str] = Field(
        default=None,
        description="Section heading or structural location (if applicable)",
    )
    quoted_snippet: Optional[str] = Field(
        default=None,
        description="Verbatim excerpt or evidence text verified against the source chunk",
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class RetrievedChunkDiagnostic(BaseModel):
    """Safe, minimal diagnostic view of a retrieved chunk used for Q&A."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    original_filename: str
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    page_number: Optional[int] = None
    section: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class QARequest(BaseModel):
    """User question request schema for grounded Q&A."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User question to be answered using authorized documents",
        examples=["What is the company policy on data encryption at rest?"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of relevant chunks to retrieve for evidence",
    )
    similarity_threshold: Optional[float] = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score threshold for retrieved chunks",
    )
    provider: Optional[str] = Field(
        default=None,
        description="Optional generation provider name (e.g., 'extractive', 'mock')",
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )


class QAResponse(BaseModel):
    """Grounded Q&A response envelope with verified citations."""

    question: str = Field(..., description="The original normalized question")
    answer: str = Field(..., description="Grounded answer synthesized from evidence")
    citations: List[Citation] = Field(
        default_factory=list,
        description="List of verified, deduplicated source citations supporting the answer",
    )
    insufficient_evidence: bool = Field(
        default=False,
        description="True if the retrieved evidence was inadequate to answer the question",
    )
    provider: str = Field(
        ...,
        description="Name of the generation provider used (e.g., 'deterministic_extractive')",
    )
    retrieved_chunk_count: int = Field(
        default=0,
        description="Total number of authorized chunks retrieved before generation",
    )
    retrieved_chunks: List[RetrievedChunkDiagnostic] = Field(
        default_factory=list,
        description="Safe diagnostic metadata of chunks retrieved for this query",
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid")
