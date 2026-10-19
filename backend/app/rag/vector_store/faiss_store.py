"""FAISS vector store with exact cosine search, atomic persistence, and pre-retrieval authorization."""

import logging
import os
from pathlib import Path
import threading
from typing import List, Optional, Set, Tuple
import uuid

import faiss
import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger("securedocs.vector_store")


class VectorStoreError(Exception):
    """Base exception for vector store operations."""
    pass


class IndexNotFoundError(VectorStoreError):
    """Raised when an index file does not exist."""
    pass


class IndexCorruptedError(VectorStoreError):
    """Raised when an index file is invalid or corrupt."""
    pass


class DimensionMismatchError(VectorStoreError):
    """Raised when vector dimensions do not match the index dimension."""
    pass


class PathTraversalError(VectorStoreError):
    """Raised when an index path escapes the allowed index directory."""
    pass


def validate_index_path(target_path: Path) -> Path:
    """
    Validate that target index path resides strictly within the configured index directory.
    Prevents path traversal attacks.
    """
    resolved_target = target_path.resolve()
    configured_root = Path(settings.FAISS_INDEX_PATH).resolve().parent
    configured_root.mkdir(parents=True, exist_ok=True)

    try:
        resolved_target.relative_to(configured_root)
    except ValueError as e:
        raise PathTraversalError(
            f"Index path '{resolved_target}' escapes configured index directory '{configured_root}'."
        ) from e

    return resolved_target


class FAISSVectorStore:
    """
    Thread-safe FAISS vector store using exact inner-product (IndexFlatIP) wrapped in IndexIDMap2.
    Guarantees pre-retrieval candidate isolation via IDSelectorBatch, atomic persistence,
    and database-driven recovery.
    """

    def __init__(
        self,
        dimension: int = 384,
        index_path: Optional[str] = None,
        auto_load: bool = True,
    ):
        if dimension <= 0:
            raise ValueError(f"dimension must be positive (got {dimension})")

        self._dimension = dimension
        raw_path = Path(index_path or settings.FAISS_INDEX_PATH)
        self._index_path = validate_index_path(raw_path)
        self._lock = threading.Lock()
        self._index: Optional[faiss.IndexIDMap2] = None

        if auto_load:
            self._load_or_create_index()

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def index_path(self) -> Path:
        return self._index_path

    @property
    def ntotal(self) -> int:
        with self._lock:
            if self._index is None:
                return 0
            return self._index.ntotal

    def _load_or_create_index(self) -> None:
        """Load index from disk or create a fresh IndexFlatIP + IndexIDMap2."""
        with self._lock:
            if self._index_path.exists():
                try:
                    logger.info("Loading existing FAISS index from '%s'...", self._index_path)
                    loaded = faiss.read_index(str(self._index_path))
                    if loaded.d != self._dimension:
                        raise DimensionMismatchError(
                            f"Index dimension mismatch: file has dimension {loaded.d}, "
                            f"configured dimension is {self._dimension}."
                        )
                    # Ensure loaded index is wrapped in IndexIDMap2
                    if not isinstance(loaded, (faiss.IndexIDMap, faiss.IndexIDMap2)):
                        loaded = faiss.IndexIDMap2(loaded)
                    self._index = loaded
                    logger.info("FAISS index loaded. Total vectors: %d", self._index.ntotal)
                except DimensionMismatchError:
                    raise
                except Exception as e:
                    logger.error("Failed to read FAISS index from '%s': %s", self._index_path, e)
                    raise IndexCorruptedError(f"Corrupted or invalid FAISS index file: {e}") from e
            else:
                self._index_path.parent.mkdir(parents=True, exist_ok=True)
                sub_index = faiss.IndexFlatIP(self._dimension)
                self._index = faiss.IndexIDMap2(sub_index)
                logger.info("Initialized fresh FAISS IndexFlatIP + IndexIDMap2 (dim=%d)", self._dimension)

    def add_vectors(
        self,
        vector_ids: List[int],
        vectors: np.ndarray,
        persist: bool = True,
    ) -> int:
        """
        Add unit-normalized vectors with 64-bit integer IDs to the index.
        Idempotent: removes existing vectors with matching IDs prior to insertion.
        """
        if not vector_ids:
            return 0

        if len(vector_ids) != vectors.shape[0]:
            raise ValueError(
                f"Count mismatch: got {len(vector_ids)} IDs but {vectors.shape[0]} vector rows."
            )

        if vectors.shape[1] != self._dimension:
            raise DimensionMismatchError(
                f"Vectors dimension {vectors.shape[1]} does not match index dimension {self._dimension}."
            )

        if not np.isfinite(vectors).all():
            raise ValueError("Cannot index vectors containing non-finite values (NaN, Inf).")

        vecs_32 = vectors.astype(np.float32)
        ids_64 = np.array(vector_ids, dtype=np.int64)

        with self._lock:
            if self._index is None:
                self._load_or_create_index()

            # Ensure idempotency: remove pre-existing IDs first
            try:
                self._index.remove_ids(faiss.IDSelectorBatch(ids_64.tolist()))  # type: ignore
            except Exception:
                pass

            self._index.add_with_ids(vecs_32, ids_64)  # type: ignore
            count = len(vector_ids)

        if persist:
            self.save()

        return count

    def remove_vectors(self, vector_ids: List[int], persist: bool = True) -> int:
        """
        Remove vectors matching vector_ids from the index.
        """
        if not vector_ids:
            return 0

        ids_list = [int(i) for i in vector_ids]
        with self._lock:
            if self._index is None:
                return 0
            removed_count = self._index.remove_ids(faiss.IDSelectorBatch(ids_list))

        if persist:
            self.save()

        return removed_count

    def search_prefiltered(
        self,
        query_vector: np.ndarray,
        top_k: int,
        allowed_vector_ids: List[int],
        threshold: float = 0.0,
    ) -> List[Tuple[int, float]]:
        """
        CRITICAL SECURITY REQUIREMENT:
        Restrict similarity candidate evaluation strictly to allowed_vector_ids BEFORE ranking.
        Never computes similarities or exposes results from unauthorized documents.
        
        Returns:
            List of (vector_id, similarity_score) sorted descending by cosine similarity.
        """
        q = np.atleast_2d(query_vector).astype(np.float32)
        if q.shape[1] != self._dimension:
            raise DimensionMismatchError(
                f"Query vector dimension {q.shape[1]} does not match index dimension {self._dimension}."
            )

        if not allowed_vector_ids or top_k <= 0:
            return []

        with self._lock:
            if self._index is None or self._index.ntotal == 0:
                return []

            allowed_set: Set[int] = set(allowed_vector_ids)
            search_k = min(top_k, len(allowed_vector_ids))

            # FAISS pre-retrieval candidate filtering
            sel = faiss.IDSelectorBatch(list(allowed_set))
            params = faiss.SearchParameters(sel=sel)

            distances, indices = self._index.search(q, search_k, params=params)

        results: List[Tuple[int, float]] = []
        for vid, score in zip(indices[0], distances[0]):
            vid_int = int(vid)
            score_float = float(score)
            # Filter FAISS padding (-1) and enforce threshold & strict membership verification
            if vid_int != -1 and vid_int in allowed_set and score_float >= threshold:
                results.append((vid_int, score_float))

        return results

    def save(self, target_path: Optional[Path] = None) -> None:
        """
        Atomically persist index to disk using a temporary file and replace.
        Prevents index corruption on unexpected crash or termination.
        """
        out_path = validate_index_path(target_path or self._index_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = out_path.parent / f".tmp_{uuid.uuid4().hex}.index"

        with self._lock:
            if self._index is None:
                return
            try:
                faiss.write_index(self._index, str(temp_path))
                os.replace(str(temp_path), str(out_path))
                logger.info("FAISS index atomically persisted to '%s'.", out_path)
            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass

    def rebuild_from_db(self, db: Session, embedding_service) -> int:
        """
        Reconstruct the FAISS index from the ground truth database.
        Indexes all chunks belonging to documents with status 'indexed'.
        """
        from app.models.chunk import DocumentChunk
        from app.models.document import Document

        logger.info("Starting FAISS index rebuild from database...")

        # Re-initialize clean in-memory index
        sub_index = faiss.IndexFlatIP(self._dimension)
        new_index = faiss.IndexIDMap2(sub_index)

        # Query all active indexed chunks in batches
        chunks_query = (
            db.query(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(Document.status == "indexed")
            .order_by(DocumentChunk.vector_id.asc())
        )

        total_indexed = 0
        batch_size = 128
        offset = 0

        while True:
            batch = chunks_query.offset(offset).limit(batch_size).all()
            if not batch:
                break

            texts = [c.content for c in batch]
            vector_ids = [c.vector_id for c in batch]

            embeddings = embedding_service.generate_embeddings(texts)
            if embeddings.shape[0] != len(vector_ids):
                raise VectorStoreError("Embedding count mismatch during index rebuild.")

            new_index.add_with_ids(  # type: ignore
                embeddings.astype(np.float32),
                np.array(vector_ids, dtype=np.int64),
            )
            total_indexed += len(vector_ids)
            offset += batch_size

        with self._lock:
            self._index = new_index

        self.save()
        logger.info("FAISS index rebuild complete. Total indexed chunks: %d", total_indexed)
        return total_indexed

    def clear(self) -> None:
        """Clear all vectors from the index."""
        with self._lock:
            sub = faiss.IndexFlatIP(self._dimension)
            self._index = faiss.IndexIDMap2(sub)
        self.save()
