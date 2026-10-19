"""Access-controlled semantic retrieval service enforcing pre-retrieval authorization."""

import logging
from typing import List, Optional, Set
import numpy as np
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.permission import DocumentPermission
from app.models.user import User
from app.rag.embeddings import BaseEmbeddingService, get_embedding_service
from app.rag.vector_store import FAISSVectorStore, get_vector_store
from app.schemas.search import SearchResultItem

logger = logging.getLogger("securedocs.retrieval")


class RetrievalService:
    """
    Semantic retrieval service enforcing strict document authorization boundaries
    BEFORE similarity ranking is performed.
    """

    def __init__(
        self,
        embedding_service: Optional[BaseEmbeddingService] = None,
        vector_store: Optional[FAISSVectorStore] = None,
    ):
        self._embedding_service = embedding_service
        self._vector_store = vector_store

    @property
    def embedding_service(self) -> BaseEmbeddingService:
        return self._embedding_service or get_embedding_service()

    @property
    def vector_store(self) -> FAISSVectorStore:
        return self._vector_store or get_vector_store()

    def get_authorized_document_ids(self, db: Session, user: User) -> Set:
        """
        Query the database to identify all documents the user is authorized to read:
        1. Owned directly by the user (Document.owner_id == user.id)
        2. Explicitly granted to the user via DocumentPermission (user_id == user.id)
        3. Granted to the user's role via DocumentPermission (role_target == user.role)
        Only includes documents with status 'indexed'.
        """
        # Explicit user- or role-based permission subquery
        perm_subq = (
            select(DocumentPermission.document_id)
            .where(
                or_(
                    DocumentPermission.user_id == user.id,
                    DocumentPermission.role_target == user.role,
                )
            )
            .scalar_subquery()
        )

        authorized_docs = (
            db.query(Document.id)
            .filter(
                Document.status == "indexed",
                or_(
                    Document.owner_id == user.id,
                    Document.id.in_(perm_subq),
                ),
            )
            .all()
        )

        return {doc_id for (doc_id,) in authorized_docs}

    def search(
        self,
        db: Session,
        current_user: User,
        query: str,
        top_k: int = 5,
        similarity_threshold: Optional[float] = 0.0,
    ) -> List[SearchResultItem]:
        """
        Perform semantic similarity search restricted strictly to documents authorized for current_user.
        Unauthorized chunks are excluded at the FAISS candidate selection phase before scoring.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        effective_top_k = max(1, min(top_k, settings.MAX_SEARCH_TOP_K))
        effective_threshold = float(similarity_threshold) if similarity_threshold is not None else 0.0

        # Step 1: Pre-retrieval candidate authorization
        # Identify documents the current authenticated user can view
        authorized_doc_ids = self.get_authorized_document_ids(db, current_user)
        if not authorized_doc_ids:
            logger.info("User %s has zero authorized indexed documents. Returning empty search.", current_user.id)
            return []

        # Step 2: Fetch authorized vector IDs belonging to permitted documents
        chunk_vector_rows = (
            db.query(DocumentChunk.vector_id)
            .filter(DocumentChunk.document_id.in_(authorized_doc_ids))
            .all()
        )
        allowed_vector_ids = [row[0] for row in chunk_vector_rows]

        if not allowed_vector_ids:
            logger.info("Zero chunks found for user's authorized documents. Returning empty search.")
            return []

        # Step 3: Generate query embedding
        query_vector = self.embedding_service.generate_query_embedding(clean_query)

        # Step 4: Perform pre-filtered FAISS vector search
        # FAISS restricts candidates to allowed_vector_ids BEFORE computing scores
        hits = self.vector_store.search_prefiltered(
            query_vector=query_vector,
            top_k=effective_top_k,
            allowed_vector_ids=allowed_vector_ids,
            threshold=effective_threshold,
        )

        if not hits:
            return []

        hit_vector_ids = [vid for vid, _ in hits]
        hit_score_map = {vid: score for vid, score in hits}

        # Step 5: Hydrate chunk records from database and verify integrity
        chunks = (
            db.query(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(DocumentChunk.vector_id.in_(hit_vector_ids))
            .all()
        )

        chunk_dict = {chunk.vector_id: (chunk, doc) for chunk, doc in chunks}

        # Step 6: Construct results preserving FAISS similarity ranking order
        results: List[SearchResultItem] = []
        for vid in hit_vector_ids:
            if vid not in chunk_dict:
                continue  # Skip stale index entries (e.g., deleted chunk)

            chunk, doc = chunk_dict[vid]

            # Final defense-in-depth authorization check
            if doc.id not in authorized_doc_ids:
                continue

            raw_score = hit_score_map.get(vid, 0.0)
            # Clamp cosine similarity between 0.0 and 1.0
            clamped_score = round(max(0.0, min(1.0, raw_score)), 4)

            meta = chunk.metadata_json or {}
            page_num = meta.get("page_number")
            section = meta.get("section")

            results.append(
                SearchResultItem(
                    document_id=doc.id,
                    chunk_id=chunk.id,
                    content=chunk.content,
                    similarity_score=clamped_score,
                    page_number=page_num,
                    section=section,
                    original_filename=doc.original_filename,
                )
            )

        return results
