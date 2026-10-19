"""Pytest configuration and database fixtures using in-memory SQLite."""

import uuid
from typing import Generator
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.core.security import get_password_hash
from app.db.session import get_db
from app.main import app
from app.models import Base, User, Document, DocumentChunk, DocumentPermission, AuditLog, RefreshToken
from httpx import ASGITransport, AsyncClient

# In-memory SQLite engine using StaticPool to share connection across threads/fixtures
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforce foreign key constraints for SQLite connections in tests."""
    if type(dbapi_connection).__module__ == "sqlite3":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Provides a fresh database session with all tables created, torn down after test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


from app.core.rate_limiter import limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter_state():
    """Reset in-memory rate limiter state before and after each test."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
async def async_client(db_session: Session):
    """Provides an HTTP test client with database dependency overridden to test DB."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.state.session_factory = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    if hasattr(app.state, "session_factory"):
        delattr(app.state, "session_factory")


@pytest.fixture
def sample_user(db_session: Session) -> User:
    """Fixture providing a persisted test user."""
    user = User(
        id=uuid.uuid4(),
        email="analyst@securedocs.io",
        hashed_password=get_password_hash("SecurePassword123!"),
        full_name="Test Analyst",
        role="analyst",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


from pathlib import Path
from app.core.config import settings


@pytest.fixture(autouse=True)
def override_upload_dir(tmp_path: Path):
    """Automatically redirects file uploads to a fresh temporary directory for every test."""
    original_upload_dir = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path / "uploads")
    yield tmp_path / "uploads"
    settings.UPLOAD_DIR = original_upload_dir


from app.rag.embeddings import MockEmbeddingService, set_embedding_service
from app.rag.vector_store import FAISSVectorStore, set_vector_store


@pytest.fixture(autouse=True)
def override_vector_store_and_embeddings(tmp_path: Path):
    """
    Automatically isolates FAISS index and configures fast deterministic MockEmbeddingService
    for repeatable, offline test execution across all suites.
    """
    original_index_path = settings.FAISS_INDEX_PATH
    test_index_path = str(tmp_path / "test_securedocs.index")
    settings.FAISS_INDEX_PATH = test_index_path

    mock_emb = MockEmbeddingService(dimension=384)
    test_store = FAISSVectorStore(dimension=384, index_path=test_index_path, auto_load=True)

    set_embedding_service(mock_emb)
    set_vector_store(test_store)

    yield test_store

    set_embedding_service(None)
    set_vector_store(None)
    settings.FAISS_INDEX_PATH = original_index_path


@pytest.fixture
def sample_document(db_session: Session, sample_user: User) -> Document:
    """Fixture providing a persisted test document."""
    doc = Document(
        id=uuid.uuid4(),
        title="Q3 Security Report",
        original_filename="security_q3.pdf",
        storage_path="uploads/security_q3.pdf",
        mime_type="application/pdf",
        file_size_bytes=102400,
        sha256_checksum="a" * 64,
        classification="internal",
        status="indexed",
        owner_id=sample_user.id,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc
