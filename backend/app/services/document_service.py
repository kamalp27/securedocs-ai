"""Document ingestion, retrieval, streaming, and deletion service."""

import hashlib
import logging
import threading
import uuid
from pathlib import Path
from typing import List, Optional, Set, Tuple

from fastapi import UploadFile
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

ALLOWED_CLASSIFICATIONS: Set[str] = {
    "public",
    "internal",
    "confidential",
    "restricted",
    "secret",
    "top_secret",
}

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.rag.chunking.recursive_chunker import RecursiveChunker
from app.rag.embeddings import BaseEmbeddingService, get_embedding_service
from app.rag.ingestion.base import DocumentParserError, EmptyDocumentError, EncryptedDocumentError
from app.rag.ingestion.parser_factory import get_parser_for_path
from app.rag.vector_store import FAISSVectorStore, get_vector_store
from app.services.upload_validator import (
    UploadValidationError,
    save_upload_safely,
)

logger = logging.getLogger("securedocs.document_service")
_vector_id_lock = threading.Lock()


def allocate_next_vector_ids(db: Session, count: int) -> int:
    """
    Allocate a contiguous range of `count` unique vector IDs safely.
    Uses an in-process lock to prevent simultaneous read-modify-write races,
    querying the ground truth MAX(vector_id) from the database.
    Returns the starting vector_id (1-based).
    """
    with _vector_id_lock:
        max_vid = db.query(func.max(DocumentChunk.vector_id)).scalar() or 0
        return max_vid + 1


class DocumentServiceError(Exception):
    """Base exception for document service errors."""
    pass


class DocumentNotFoundError(DocumentServiceError):
    """Raised when a document does not exist or the requester is not the owner (IDOR protection)."""
    pass


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 checksum of a file on disk."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def ingest_document(
    db: Session,
    upload_file: UploadFile,
    owner_id: uuid.UUID,
    classification: str = "internal",
    embedding_service: Optional[BaseEmbeddingService] = None,
    vector_store: Optional[FAISSVectorStore] = None,
) -> Document:
    """
    Validate, store, parse, chunk, persist, and vector-index an uploaded document.
    Transactional: on any parsing or persistence failure, cleans up the saved file.
    """
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    saved_path: Optional[Path] = None

    norm_classification = (classification or "internal").strip().lower()
    if norm_classification not in ALLOWED_CLASSIFICATIONS:
        raise DocumentServiceError(
            f"Invalid security classification '{classification}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_CLASSIFICATIONS))}."
        )

    try:
        # 1. Validate upload (size, MIME, magic bytes, path safety) and save to disk
        sanitized_filename, saved_path, file_size, verified_mime = save_upload_safely(
            upload_file=upload_file,
            upload_dir=upload_dir,
            max_size_bytes=settings.MAX_UPLOAD_SIZE_BYTES,
        )

        # 2. Compute cryptographic checksum
        sha256_hash = compute_sha256(saved_path)

        # 3. Parse document contents into structured segments
        parser = get_parser_for_path(saved_path)
        parsed_doc = parser.parse(file_path=saved_path, document_title=sanitized_filename)

        # 4. Chunk document segments with recursive character/token boundaries
        chunker = RecursiveChunker(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )
        chunk_outputs = chunker.chunk_segments(parsed_doc.segments)

        if not chunk_outputs:
            raise EmptyDocumentError("Document parsed but produced zero usable text chunks.")

        # 5. Persist Document record
        doc_id = uuid.uuid4()
        # Relative storage path for portability across environments
        storage_rel_path = str(saved_path.relative_to(upload_dir.parent))

        doc = Document(
            id=doc_id,
            title=sanitized_filename,
            original_filename=sanitized_filename,
            storage_path=storage_rel_path,
            mime_type=verified_mime,
            file_size_bytes=file_size,
            sha256_checksum=sha256_hash,
            classification=norm_classification,
            status="parsed",  # Intermediate state before vector indexing
            owner_id=owner_id,
        )
        db.add(doc)
        db.flush()

        # 6. Allocate vector IDs and persist DocumentChunk records with collision retry
        max_retries = 3
        created_chunks: List[DocumentChunk] = []

        for attempt in range(max_retries):
            try:
                start_vector_id = allocate_next_vector_ids(db, len(chunk_outputs))
                created_chunks = []
                for idx, chk in enumerate(chunk_outputs):
                    chunk_record = DocumentChunk(
                        id=uuid.uuid4(),
                        document_id=doc.id,
                        vector_id=start_vector_id + idx,
                        chunk_index=chk.chunk_index,
                        content=chk.content,
                        token_count=chk.token_count,
                        metadata_json=chk.metadata_json,
                    )
                    db.add(chunk_record)
                    created_chunks.append(chunk_record)

                # 7. Record audit log entry
                audit = AuditLog(
                    id=uuid.uuid4(),
                    user_id=owner_id,
                    action="UPLOAD",
                    document_id=doc.id,
                    status_code=201,
                )
                db.add(audit)

                db.commit()
                db.refresh(doc)
                break
            except IntegrityError as e:
                db.rollback()
                if attempt == max_retries - 1:
                    logger.error("Vector ID collision retry exhausted for document %s: %s", doc_id, e)
                    raise DocumentServiceError(
                        f"Failed to allocate unique vector IDs after {max_retries} attempts: {e}"
                    ) from e
                # Re-add doc for next attempt
                db.add(doc)
                db.flush()

        # 8. Generate embeddings and index in FAISS vector store
        try:
            emb_service = embedding_service or get_embedding_service()
            v_store = vector_store or get_vector_store()

            chunk_texts = [c.content for c in created_chunks]
            chunk_vids = [c.vector_id for c in created_chunks]

            embeddings = emb_service.generate_embeddings(chunk_texts)
            v_store.add_vectors(chunk_vids, embeddings, persist=True)

            doc.status = "indexed"
            db.commit()
            db.refresh(doc)
        except Exception as e:
            logger.error("Vector indexing failed for document %s: %s", doc.id, e)
            # Revert any partially added vectors from vector store memory
            try:
                v_store = vector_store or get_vector_store()
                chunk_vids = [c.vector_id for c in created_chunks]
                v_store.remove_vectors(chunk_vids, persist=False)
            except Exception:
                pass
            doc.status = "indexing_failed"
            doc.error_message = f"Vector indexing failed: {e}"
            db.commit()
            db.refresh(doc)

        return doc

    except (UploadValidationError, DocumentParserError):
        db.rollback()
        # Clean up file on disk if parsing/validation failed
        if saved_path and saved_path.exists():
            try:
                saved_path.unlink()
            except OSError:
                pass
        raise

    except Exception as e:
        db.rollback()
        if saved_path and saved_path.exists():
            try:
                saved_path.unlink()
            except OSError:
                pass
        raise DocumentServiceError(f"Internal document ingestion failure: {e}") from e


def get_document_for_owner(
    db: Session,
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> Document:
    """
    Retrieve document by ID strictly verifying owner identity.
    Returns 404 (DocumentNotFoundError) if document does not exist OR belongs to another user.
    """
    doc = db.query(Document).filter_by(id=document_id, owner_id=owner_id).first()
    if not doc:
        raise DocumentNotFoundError("Document not found.")
    return doc


def list_documents_for_owner(
    db: Session,
    owner_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
) -> Tuple[List[Document], int]:
    """List paginated documents belonging strictly to the requesting user."""
    query = db.query(Document).filter_by(owner_id=owner_id)
    if status_filter:
        query = query.filter_by(status=status_filter)

    total_count = query.count()
    items = (
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total_count


def delete_document_for_owner(
    db: Session,
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
    vector_store: Optional[FAISSVectorStore] = None,
) -> None:
    """
    Delete document, associated chunks, vector index entries, and stored binary file on disk.
    Enforces ownership check before performing deletion.
    """
    doc = get_document_for_owner(db, document_id, owner_id)

    # 1. Invalidate and remove vectors from FAISS index
    chunk_vids = [c.vector_id for c in doc.chunks if c.vector_id is not None]
    if chunk_vids:
        try:
            v_store = vector_store or get_vector_store()
            v_store.remove_vectors(chunk_vids, persist=True)
        except Exception as e:
            logger.warning("Failed to remove vectors for doc %s from FAISS index: %s", doc.id, e)

    # 2. Safely remove file from disk
    resolved_path = resolve_document_file_path(doc)
    if resolved_path and resolved_path.exists():
        try:
            resolved_path.unlink()
        except OSError:
            pass

    # 3. Record audit log before deleting entity
    audit = AuditLog(
        id=uuid.uuid4(),
        user_id=owner_id,
        action="DELETE",
        document_id=doc.id,
        status_code=200,
    )
    db.add(audit)

    # 4. Deleting doc cascades to chunks and permissions via SQLAlchemy relationship
    db.delete(doc)
    db.commit()


def reindex_document(
    db: Session,
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
    embedding_service: Optional[BaseEmbeddingService] = None,
    vector_store: Optional[FAISSVectorStore] = None,
) -> Document:
    """
    Re-generate embeddings and index chunks for a previously failed or updated document.
    """
    doc = get_document_for_owner(db, document_id, owner_id)
    if not doc.chunks:
        raise DocumentServiceError("Cannot index document with zero chunks.")

    emb_service = embedding_service or get_embedding_service()
    v_store = vector_store or get_vector_store()

    try:
        chunk_texts = [c.content for c in doc.chunks]
        chunk_vids = [c.vector_id for c in doc.chunks]

        embeddings = emb_service.generate_embeddings(chunk_texts)
        v_store.add_vectors(chunk_vids, embeddings, persist=True)

        doc.status = "indexed"
        doc.error_message = None
        db.commit()
        db.refresh(doc)
        return doc
    except Exception as e:
        logger.error("Re-indexing failed for document %s: %s", doc.id, e)
        doc.status = "indexing_failed"
        doc.error_message = f"Re-indexing failed: {e}"
        db.commit()
        db.refresh(doc)
        raise DocumentServiceError(f"Re-indexing failed: {e}") from e


def resolve_document_file_path(doc: Document) -> Optional[Path]:
    """
    Safely resolve the absolute filesystem path for a stored document.
    Ensures path does not escape the configured storage directory.
    """
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    # Handle both relative path and direct filename stored in storage_path
    candidate = (upload_root.parent / doc.storage_path).resolve()
    if not candidate.exists():
        candidate = (upload_root / Path(doc.storage_path).name).resolve()

    try:
        candidate.relative_to(upload_root)
        return candidate
    except ValueError:
        # Storage path outside upload root: security alert
        return None


def reconcile_index_if_needed(
    db: Session,
    embedding_service: Optional[BaseEmbeddingService] = None,
    vector_store: Optional[FAISSVectorStore] = None,
) -> int:
    """
    Ensure the FAISS vector store is synchronized with the ground truth database.
    If the index has 0 vectors but the database contains indexed chunks,
    automatically triggers an index rebuild.
    Returns the count of rebuilt chunks (or 0 if already aligned).
    """
    v_store = vector_store or get_vector_store()
    emb_service = embedding_service or get_embedding_service()

    indexed_count = (
        db.query(func.count(DocumentChunk.id))
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(Document.status == "indexed")
        .scalar()
        or 0
    )

    if v_store.ntotal == 0 and indexed_count > 0:
        logger.warning(
            "FAISS index has 0 vectors but database contains %d indexed chunks. Triggering auto-rebuild...",
            indexed_count,
        )
        return v_store.rebuild_from_db(db, emb_service)

    return 0
