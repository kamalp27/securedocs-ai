"""Database engine and session factory."""

from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

# Configure connection args based on database dialect (e.g. SQLite thread check & timeout)
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 5.0

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG if settings.ENVIRONMENT == "development" else False,
    connect_args=connect_args,
    pool_pre_ping=True,
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforce foreign key constraints and concurrency pragmas for SQLite connections."""
    if type(dbapi_connection).__module__ == "sqlite3":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        try:
            # Query current journal mode; enable WAL only on persistent databases
            cursor.execute("PRAGMA journal_mode;")
            row = cursor.fetchone()
            current_mode = str(row[0]).lower() if row else ""
            if current_mode not in ("wal", "memory"):
                cursor.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        cursor.close()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields an active database session and closes it on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
