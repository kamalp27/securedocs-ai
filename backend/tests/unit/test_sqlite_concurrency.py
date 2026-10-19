"""Unit tests for SQLite pragmas and concurrent access handling."""

import sqlite3
import threading
import time
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.session import set_sqlite_pragma
from app.models import Base, User
from app.core.security import get_password_hash
import uuid


def test_sqlite_pragmas_applied_on_disk_database(tmp_path: Path):
    """Verify foreign_keys, busy_timeout, and journal_mode pragmas are set on SQLite."""
    db_file = tmp_path / "pragma_test.db"
    db_url = f"sqlite:///{db_file}"

    test_engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False, "timeout": 5.0},
    )

    with test_engine.connect() as conn:
        fk = conn.execute(text("PRAGMA foreign_keys;")).scalar()
        busy = conn.execute(text("PRAGMA busy_timeout;")).scalar()
        journal = conn.execute(text("PRAGMA journal_mode;")).scalar()

    assert fk == 1
    assert busy == 5000
    assert str(journal).lower() == "wal"
    test_engine.dispose()


def test_sqlite_concurrent_readers_and_writers(tmp_path: Path):
    """Verify concurrent reads and writes succeed without database locked errors under WAL mode and busy_timeout."""
    db_file = tmp_path / "concurrent_test.db"
    db_url = f"sqlite:///{db_file}"

    test_engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False, "timeout": 5.0},
    )
    Base.metadata.create_all(bind=test_engine)

    Session = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    errors = []
    num_threads = 6
    writes_per_thread = 5

    def writer_worker(thread_idx: int):
        try:
            for i in range(writes_per_thread):
                session = Session()
                try:
                    user = User(
                        id=uuid.uuid4(),
                        email=f"worker_{thread_idx}_{i}@test.com",
                        hashed_password=get_password_hash("password123"),
                        full_name=f"Worker {thread_idx} {i}",
                        role="analyst",
                        is_active=True,
                    )
                    session.add(user)
                    session.commit()
                finally:
                    session.close()
                time.sleep(0.01)
        except Exception as e:
            errors.append(e)

    def reader_worker():
        try:
            for _ in range(15):
                session = Session()
                try:
                    count = session.query(User).count()
                    assert count >= 0
                finally:
                    session.close()
                time.sleep(0.01)
        except Exception as e:
            errors.append(e)

    threads = []
    # 4 writers and 2 readers running concurrently
    for t_idx in range(4):
        threads.append(threading.Thread(target=writer_worker, args=(t_idx,)))
    for _ in range(2):
        threads.append(threading.Thread(target=reader_worker))

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    # Check that no thread timed out or died with database locked errors
    for t in threads:
        assert not t.is_alive(), "A worker thread deadlocked or timed out"
    assert len(errors) == 0, f"Concurrent workers encountered errors: {errors}"

    # Verify all writes committed successfully
    final_session = Session()
    try:
        total = final_session.query(User).count()
        assert total == 4 * writes_per_thread
    finally:
        final_session.close()
        test_engine.dispose()
