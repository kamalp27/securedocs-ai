"""Pydantic v2 schemas for semantic vector search requests and responses."""

import uuid
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    """Semantic similarity search request schema."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Search query string",
        examples=["What is the company policy on encryption keys?"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of relevant chunks to retrieve",
    )
    similarity_threshold: Optional[float] = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score required for results",
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )


class SearchResultItem(BaseModel):
    """A single retrieved document chunk matching the search query."""

    document_id: uuid.UUID
    chunk_id: uuid.UUID
    content: str
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    page_number: Optional[int] = None
    section: Optional[str] = None
    original_filename: str

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    """Semantic vector search response envelope."""

    query: str
    total_results: int
    results: List[SearchResultItem]

    model_config = ConfigDict(from_attributes=True)
