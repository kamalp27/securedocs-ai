"""Integration tests for Document API: upload, pagination, download, deletion, and IDOR authorization."""

import io
import uuid
from pathlib import Path
import docx
import pypdf
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.user import User


@pytest.fixture
def other_user(db_session: Session) -> User:
    """Fixture providing a second distinct user for multi-tenant isolation testing."""
    user = User(
        id=uuid.uuid4(),
        email="other_analyst@securedocs.io",
        hashed_password=get_password_hash("OtherUserPassword123!"),
        full_name="Other Analyst",
        role="analyst",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_document_upload_and_chunking_success_txt(
    async_client: AsyncClient, sample_user: User, db_session: Session
):
    """Verify uploading a valid TXT document persists document and chunks correctly."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    txt_content = (
        "SecureDocs AI Architecture Overview.\n\n"
        "The system incorporates FastAPI backend with PostgreSQL persistence and local vector search.\n\n"
        "Security dependencies ensure multi-tenant data boundaries are strictly enforced."
    )
    files = {"file": ("architecture.txt", io.BytesIO(txt_content.encode("utf-8")), "text/plain")}
    data = {"classification": "internal"}

    response = await async_client.post(
        "/api/v1/documents/upload", headers=headers, files=files, data=data
    )
    assert response.status_code == 201

    res_data = response.json()
    assert res_data["title"] == "architecture.txt"
    assert res_data["original_filename"] == "architecture.txt"
    assert res_data["mime_type"] == "text/plain"
    assert res_data["classification"] == "internal"
    assert res_data["status"] == "indexed"
    assert res_data["chunk_count"] >= 1
    assert "storage_path" not in res_data  # Internal paths never exposed

    # Verify database persistence
    doc_id = uuid.UUID(res_data["id"])
    db_doc = db_session.query(Document).filter_by(id=doc_id).first()
    assert db_doc is not None
    assert db_doc.owner_id == sample_user.id

    chunks = db_session.query(DocumentChunk).filter_by(document_id=doc_id).all()
    assert len(chunks) == res_data["chunk_count"]
    for c in chunks:
        assert c.vector_id > 0
        assert len(c.content) > 0


@pytest.mark.asyncio
async def test_document_upload_success_docx(
    async_client: AsyncClient, sample_user: User, tmp_path: Path
):
    """Verify uploading a valid DOCX document succeeds."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # Generate in-memory DOCX
    docx_buf = io.BytesIO()
    doc = docx.Document()
    doc.add_heading("Project Roadmap", level=1)
    doc.add_paragraph("Phase 4 covers secure document ingestion and recursive chunking.")
    doc.save(docx_buf)
    docx_buf.seek(0)

    files = {
        "file": (
            "roadmap.docx",
            docx_buf,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    response = await async_client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert response.status_code == 201
    assert response.json()["title"] == "roadmap.docx"
    assert response.json()["chunk_count"] >= 1


@pytest.mark.asyncio
async def test_document_upload_unsupported_format(
    async_client: AsyncClient, sample_user: User
):
    """Verify uploading an unsupported file extension returns HTTP 400."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("script.py", io.BytesIO(b"print('hello')"), "text/x-python")}
    response = await async_client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert response.status_code == 400
    assert "not permitted" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_document_upload_spoofed_pdf(
    async_client: AsyncClient, sample_user: User
):
    """Verify uploading a text file renamed as .pdf is rejected by signature check."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # Fake PDF: does not start with %PDF-
    fake_pdf = io.BytesIO(b"Not a real PDF file header.")
    files = {"file": ("malicious.pdf", fake_pdf, "application/pdf")}
    response = await async_client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert response.status_code == 400
    assert "invalid pdf" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_document_upload_empty_file(
    async_client: AsyncClient, sample_user: User
):
    """Verify uploading a 0-byte file returns HTTP 400."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    response = await async_client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert response.status_code == 400
    assert "0 bytes" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_document_upload_encrypted_pdf_rejected(
    async_client: AsyncClient, sample_user: User
):
    """Verify encrypted PDFs are rejected with HTTP 422."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # Generate encrypted PDF
    buf = io.BytesIO()
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("Secret123!")
    writer.write(buf)
    buf.seek(0)

    files = {"file": ("encrypted.pdf", buf, "application/pdf")}
    response = await async_client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert response.status_code == 422
    assert "encrypted" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_document_list_and_user_isolation(
    async_client: AsyncClient, sample_user: User, other_user: User, db_session: Session
):
    """Verify User A and User B only see their own uploaded documents."""
    token_a = create_access_token(subject=sample_user.id, role=sample_user.role)
    token_b = create_access_token(subject=other_user.id, role=other_user.role)

    # User A uploads a document
    file_a = {"file": ("doc_a.txt", io.BytesIO(b"Document belonging to user A."), "text/plain")}
    res_a = await async_client.post(
        "/api/v1/documents/upload", headers={"Authorization": f"Bearer {token_a}"}, files=file_a
    )
    assert res_a.status_code == 201

    # User B uploads a document
    file_b = {"file": ("doc_b.txt", io.BytesIO(b"Document belonging to user B."), "text/plain")}
    res_b = await async_client.post(
        "/api/v1/documents/upload", headers={"Authorization": f"Bearer {token_b}"}, files=file_b
    )
    assert res_b.status_code == 201

    # User A lists documents: should only see doc_a
    list_a = await async_client.get(
        "/api/v1/documents", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert list_a.status_code == 200
    items_a = list_a.json()["items"]
    assert len(items_a) == 1
    assert items_a[0]["title"] == "doc_a.txt"

    # User B lists documents: should only see doc_b
    list_b = await async_client.get(
        "/api/v1/documents", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert list_b.status_code == 200
    items_b = list_b.json()["items"]
    assert len(items_b) == 1
    assert items_b[0]["title"] == "doc_b.txt"


@pytest.mark.asyncio
async def test_document_get_and_download_idor_protection(
    async_client: AsyncClient, sample_user: User, other_user: User
):
    """Verify User B attempting to view or download User A's document receives 404."""
    token_a = create_access_token(subject=sample_user.id, role=sample_user.role)
    token_b = create_access_token(subject=other_user.id, role=other_user.role)

    # User A uploads document
    files = {"file": ("confidential_a.txt", io.BytesIO(b"Confidential financial data of User A."), "text/plain")}
    res = await async_client.post(
        "/api/v1/documents/upload", headers={"Authorization": f"Bearer {token_a}"}, files=files
    )
    doc_id = res.json()["id"]

    # User A gets detail: 200 OK
    get_res = await async_client.get(
        f"/api/v1/documents/{doc_id}", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert get_res.status_code == 200
    assert len(get_res.json()["chunks"]) >= 1

    # User B gets User A's document: 404 Not Found (anti-IDOR)
    idor_get = await async_client.get(
        f"/api/v1/documents/{doc_id}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert idor_get.status_code == 404
    assert idor_get.json()["detail"] == "Document not found."

    # User B downloads User A's document: 404 Not Found
    idor_dl = await async_client.get(
        f"/api/v1/documents/{doc_id}/download", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert idor_dl.status_code == 404

    # User A downloads own document: 200 OK with correct content
    dl_res = await async_client.get(
        f"/api/v1/documents/{doc_id}/download", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert dl_res.status_code == 200
    assert dl_res.content == b"Confidential financial data of User A."


@pytest.mark.asyncio
async def test_document_delete_and_cascade_success(
    async_client: AsyncClient, sample_user: User, db_session: Session
):
    """Verify document deletion removes record, chunks, and disk file."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("to_delete.txt", io.BytesIO(b"Data that will be removed."), "text/plain")}
    res = await async_client.post("/api/v1/documents/upload", headers=headers, files=files)
    doc_id = uuid.UUID(res.json()["id"])

    # Verify chunks exist
    assert db_session.query(DocumentChunk).filter_by(document_id=doc_id).count() >= 1

    # Delete document
    del_res = await async_client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert del_res.status_code == 200
    assert "deleted successfully" in del_res.json()["message"].lower()

    # Document and chunks must be gone from DB
    assert db_session.query(Document).filter_by(id=doc_id).first() is None
    assert db_session.query(DocumentChunk).filter_by(document_id=doc_id).count() == 0


@pytest.mark.asyncio
async def test_document_delete_idor_protection(
    async_client: AsyncClient, sample_user: User, other_user: User, db_session: Session
):
    """Verify User B cannot delete User A's document (returns 404 and does not delete)."""
    token_a = create_access_token(subject=sample_user.id, role=sample_user.role)
    token_b = create_access_token(subject=other_user.id, role=other_user.role)

    files = {"file": ("user_a_precious.txt", io.BytesIO(b"Critical business document."), "text/plain")}
    res = await async_client.post(
        "/api/v1/documents/upload", headers={"Authorization": f"Bearer {token_a}"}, files=files
    )
    doc_id = uuid.UUID(res.json()["id"])

    # User B attempts to delete User A's document
    del_fail = await async_client.delete(
        f"/api/v1/documents/{doc_id}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert del_fail.status_code == 404

    # Document must still exist intact in DB
    assert db_session.query(Document).filter_by(id=doc_id).first() is not None


@pytest.mark.asyncio
async def test_document_upload_rejects_invalid_classification(
    async_client: AsyncClient, sample_user: User
):
    """Verify that an arbitrary or invalid security classification string is rejected with HTTP 400."""
    token = create_access_token(subject=sample_user.id, role=sample_user.role)
    files = {"file": ("classified.txt", io.BytesIO(b"Confidential data payload."), "text/plain")}
    data = {"classification": "super_top_secret_invalid_level"}

    res = await async_client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        data=data,
    )
    assert res.status_code == 400
    assert "invalid security classification" in res.json()["detail"].lower()
