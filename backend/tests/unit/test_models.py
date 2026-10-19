"""Unit tests for SQLAlchemy 2.x models, constraints, and relationships."""

import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User, Document, DocumentChunk, DocumentPermission, AuditLog


def test_create_user_success(db_session: Session):
    """Verify that a valid user can be persisted and retrieved."""
    user = User(
        email="admin@securedocs.io",
        hashed_password="hashed_secret_test",
        full_name="Admin User",
        role="admin",
    )
    db_session.add(user)
    db_session.commit()

    retrieved = db_session.query(User).filter_by(email="admin@securedocs.io").first()
    assert retrieved is not None
    assert retrieved.email == "admin@securedocs.io"
    assert retrieved.role == "admin"
    assert retrieved.is_active is True
    assert isinstance(retrieved.id, uuid.UUID)


def test_user_email_unique_constraint(db_session: Session, sample_user: User):
    """Verify that attempting to create a user with duplicate email raises IntegrityError."""
    duplicate_user = User(
        email=sample_user.email,
        hashed_password="another_hash",
        full_name="Duplicate User",
    )
    db_session.add(duplicate_user)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_create_document_with_owner(db_session: Session, sample_user: User):
    """Verify document creation and relationship back to owner user."""
    doc = Document(
        title="Compliance Guide",
        original_filename="guide.docx",
        storage_path="uploads/guide.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_size_bytes=51200,
        sha256_checksum="b" * 64,
        classification="confidential",
        owner_id=sample_user.id,
    )
    db_session.add(doc)
    db_session.commit()

    retrieved = db_session.query(Document).filter_by(id=doc.id).first()
    assert retrieved is not None
    assert retrieved.owner.email == sample_user.email
    assert retrieved.classification == "confidential"


def test_document_cascade_delete_chunks_and_permissions(
    db_session: Session, sample_document: Document, sample_user: User
):
    """Verify cascading deletion of chunks and permissions when parent document is deleted."""
    # Add chunk
    chunk = DocumentChunk(
        document_id=sample_document.id,
        vector_id=101,
        chunk_index=0,
        content="First paragraph of security report.",
        token_count=6,
        metadata_json={"page": 1},
    )
    # Add permission
    perm = DocumentPermission(
        document_id=sample_document.id,
        user_id=sample_user.id,
        permission_level="view",
    )
    db_session.add_all([chunk, perm])
    db_session.commit()

    assert db_session.query(DocumentChunk).filter_by(document_id=sample_document.id).count() == 1
    assert db_session.query(DocumentPermission).filter_by(document_id=sample_document.id).count() == 1

    # Delete parent document
    db_session.delete(sample_document)
    db_session.commit()

    # Verify chunks and permissions are cascaded away
    assert db_session.query(DocumentChunk).filter_by(document_id=sample_document.id).count() == 0
    assert db_session.query(DocumentPermission).filter_by(document_id=sample_document.id).count() == 0


def test_chunk_unique_vector_id_constraint(db_session: Session, sample_document: Document):
    """Verify that FAISS vector_id must be globally unique across all chunks."""
    chunk1 = DocumentChunk(
        document_id=sample_document.id,
        vector_id=500,
        chunk_index=0,
        content="First chunk content",
        token_count=3,
    )
    chunk2 = DocumentChunk(
        document_id=sample_document.id,
        vector_id=500,  # Duplicate vector_id
        chunk_index=1,
        content="Second chunk content",
        token_count=3,
    )
    db_session.add(chunk1)
    db_session.commit()

    db_session.add(chunk2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_chunk_unique_doc_and_index_constraint(db_session: Session, sample_document: Document):
    """Verify that (document_id, chunk_index) compound index enforces uniqueness."""
    chunk1 = DocumentChunk(
        document_id=sample_document.id,
        vector_id=601,
        chunk_index=0,
        content="Chunk 0",
        token_count=2,
    )
    chunk2 = DocumentChunk(
        document_id=sample_document.id,
        vector_id=602,
        chunk_index=0,  # Duplicate index within same document
        content="Duplicate chunk 0",
        token_count=3,
    )
    db_session.add(chunk1)
    db_session.commit()

    db_session.add(chunk2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_document_permission_role_target(db_session: Session, sample_document: Document):
    """Verify permission can be granted to a role without a specific user_id."""
    perm = DocumentPermission(
        document_id=sample_document.id,
        role_target="manager",
        permission_level="view",
    )
    db_session.add(perm)
    db_session.commit()

    retrieved = db_session.query(DocumentPermission).filter_by(document_id=sample_document.id).first()
    assert retrieved is not None
    assert retrieved.role_target == "manager"
    assert retrieved.user_id is None


def test_audit_log_creation_and_set_null_on_user_delete(
    db_session: Session, sample_user: User, sample_document: Document
):
    """Verify audit log records actions and preserves log integrity when user is deleted."""
    log = AuditLog(
        user_id=sample_user.id,
        action="VIEW",
        document_id=sample_document.id,
        ip_address="127.0.0.1",
        status_code=200,
    )
    db_session.add(log)
    db_session.commit()

    log_id = log.id
    # Delete the user who performed the action
    db_session.delete(sample_user)
    db_session.commit()

    # The audit log entry should still exist, with user_id set to null (or foreign key preserved)
    retrieved_log = db_session.query(AuditLog).filter_by(id=log_id).first()
    assert retrieved_log is not None
    assert retrieved_log.action == "VIEW"
    assert retrieved_log.user_id is None


def test_sqlite_foreign_key_enforcement_rejects_invalid_fk(db_session: Session):
    """Verify that SQLite engine strictly rejects foreign keys pointing to non-existent rows."""
    non_existent_user_id = uuid.uuid4()
    invalid_doc = Document(
        title="Orphan Document",
        original_filename="orphan.pdf",
        storage_path="uploads/orphan.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        sha256_checksum="c" * 64,
        owner_id=non_existent_user_id,
    )
    db_session.add(invalid_doc)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_user_deletion_cascades_to_documents_and_chunks(
    db_session: Session, sample_user: User, sample_document: Document
):
    """Verify deleting a user cascades to documents and chunks, while preserving audit logs."""
    chunk = DocumentChunk(
        document_id=sample_document.id,
        vector_id=999,
        chunk_index=0,
        content="Cascade test chunk",
        token_count=3,
    )
    audit = AuditLog(
        user_id=sample_user.id,
        action="UPLOAD",
        document_id=sample_document.id,
        status_code=201,
    )
    db_session.add_all([chunk, audit])
    db_session.commit()

    audit_id = audit.id
    doc_id = sample_document.id

    # Delete user
    db_session.delete(sample_user)
    db_session.commit()

    # Document and its chunk must be gone
    assert db_session.query(Document).filter_by(id=doc_id).first() is None
    assert db_session.query(DocumentChunk).filter_by(document_id=doc_id).count() == 0

    # Audit log must be preserved with user_id set to NULL
    preserved_audit = db_session.query(AuditLog).filter_by(id=audit_id).first()
    assert preserved_audit is not None
    assert preserved_audit.action == "UPLOAD"
    assert preserved_audit.user_id is None
    assert preserved_audit.document_id is None

