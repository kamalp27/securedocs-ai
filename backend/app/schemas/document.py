"""Pydantic v2 schemas for Document API responses and pagination."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentChunkResponse(BaseModel):
    """Chunk metadata and snippet preview."""
    id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int
    metadata_json: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(BaseModel):
    """
    Document metadata response schema.
    Strictly omits server internal storage filesystem paths.
    """
    id: uuid.UUID
    title: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    sha256_checksum: str
    classification: str
    status: str
    created_at: datetime
    updated_at: datetime
    chunk_count: int = Field(0, description="Number of parsed and indexed chunks")

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailResponse(DocumentResponse):
    """Detailed document response including chunk previews."""
    chunks: List[DocumentChunkResponse] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    """Paginated document listing response."""
    items: List[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
