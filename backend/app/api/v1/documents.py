"""Document API endpoints: upload, list, detail, download, delete."""

import math
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.core.rate_limiter import rate_limit_user
from app.models.user import User
from app.rag.ingestion.base import (
    DocumentParserError,
    EmptyDocumentError,
    EncryptedDocumentError,
    MalformedDocumentError,
)
from app.schemas.auth import MessageResponse
from app.schemas.document import (
    DocumentChunkResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
)
from app.services.document_service import (
    DocumentNotFoundError,
    DocumentServiceError,
    delete_document_for_owner,
    get_document_for_owner,
    ingest_document,
    list_documents_for_owner,
    resolve_document_file_path,
)
from app.services.upload_validator import (
    EmptyFileError,
    MalformedFileError as UploadMalformedFileError,
    PathTraversalError,
    PayloadTooLargeError,
    UnsupportedFormatError,
)

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a document (PDF, DOCX, TXT)",
)
def upload_document(
    file: UploadFile = File(..., description="Document binary file"),
    classification: str = Form("internal", description="Document security classification"),
    current_user: User = Depends(rate_limit_user(max_requests=10, window_seconds=60, action="document upload")),
    db: Session = Depends(get_db),
):
    """
    Upload, validate signatures, stream to protected storage, parse, and chunk a document.
    Enforces document-level ownership assigned strictly to the authenticated user.
    """
    try:
        doc = ingest_document(
            db=db,
            upload_file=file,
            owner_id=current_user.id,
            classification=classification,
        )
        return DocumentResponse(
            id=doc.id,
            title=doc.title,
            original_filename=doc.original_filename,
            mime_type=doc.mime_type,
            file_size_bytes=doc.file_size_bytes,
            sha256_checksum=doc.sha256_checksum,
            classification=doc.classification,
            status=doc.status,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            chunk_count=len(doc.chunks) if doc.chunks else 0,
        )

    except EmptyFileError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except PayloadTooLargeError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e)) from e
    except (UnsupportedFormatError, PathTraversalError, UploadMalformedFileError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except EncryptedDocumentError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
    except (EmptyDocumentError, MalformedDocumentError, DocumentParserError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except DocumentServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List accessible documents for current user (paginated)",
)
@router.get(
    "/",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def list_documents(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by document status"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    List only documents owned by the authenticated user.
    Never exposes internal filesystem paths or documents belonging to other users.
    """
    items, total_count = list_documents_for_owner(
        db=db,
        owner_id=current_user.id,
        page=page,
        page_size=page_size,
        status_filter=status,
    )

    doc_responses = [
        DocumentResponse(
            id=d.id,
            title=d.title,
            original_filename=d.original_filename,
            mime_type=d.mime_type,
            file_size_bytes=d.file_size_bytes,
            sha256_checksum=d.sha256_checksum,
            classification=d.classification,
            status=d.status,
            created_at=d.created_at,
            updated_at=d.updated_at,
            chunk_count=len(d.chunks) if d.chunks else 0,
        )
        for d in items
    ]

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
    return DocumentListResponse(
        items=doc_responses,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get document metadata and chunk preview",
)
def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve document details and chunk previews.
    Returns HTTP 404 if the document does not exist OR belongs to another user (anti-IDOR).
    """
    try:
        doc = get_document_for_owner(db=db, document_id=document_id, owner_id=current_user.id)
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from e

    chunk_responses = [
        DocumentChunkResponse(
            id=c.id,
            chunk_index=c.chunk_index,
            content=c.content,
            token_count=c.token_count,
            metadata_json=c.metadata_json,
        )
        for c in sorted(doc.chunks, key=lambda x: x.chunk_index)
    ]

    return DocumentDetailResponse(
        id=doc.id,
        title=doc.title,
        original_filename=doc.original_filename,
        mime_type=doc.mime_type,
        file_size_bytes=doc.file_size_bytes,
        sha256_checksum=doc.sha256_checksum,
        classification=doc.classification,
        status=doc.status,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        chunk_count=len(chunk_responses),
        chunks=chunk_responses,
    )


@router.get(
    "/{document_id}/download",
    summary="Download original document binary",
)
def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Stream the original stored document binary with sanitized content-disposition filename.
    Returns HTTP 404 if not found or unauthorized.
    """
    try:
        doc = get_document_for_owner(db=db, document_id=document_id, owner_id=current_user.id)
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from e

    file_path = resolve_document_file_path(doc)
    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document binary file is missing from storage.",
        )

    return FileResponse(
        path=str(file_path),
        media_type=doc.mime_type,
        filename=doc.original_filename,
    )


@router.delete(
    "/{document_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete document, chunks, and stored binary file",
)
def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Safely delete document database record, cascading chunks, and stored file.
    Returns HTTP 404 if not found or unauthorized.
    """
    try:
        delete_document_for_owner(db=db, document_id=document_id, owner_id=current_user.id)
        return MessageResponse(message="Document and associated chunks deleted successfully.")
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from e
