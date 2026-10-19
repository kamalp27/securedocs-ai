"""Search API endpoint: access-controlled semantic vector search."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.models.user import User
from app.rag.embeddings.base import EmbeddingError
from app.rag.vector_store.faiss_store import VectorStoreError
from app.schemas.search import SearchRequest, SearchResponse
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger("securedocs.api.search")

router = APIRouter(prefix="/search", tags=["Search"])


@router.post(
    "",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Semantic vector search across authorized documents",
)
def semantic_search(
    request: SearchRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """
    Search indexed document chunks matching semantic intent.
    Enforces multi-tenant pre-retrieval access control before FAISS candidate evaluation.
    Only returns document chunks the authenticated user is authorized to view.
    """
    try:
        service = RetrievalService()
        results = service.search(
            db=db,
            current_user=current_user,
            query=request.query,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
        )

        return SearchResponse(
            query=request.query,
            total_results=len(results),
            results=results,
        )

    except EmbeddingError as e:
        logger.error("Embedding failure during search for user %s: %s", current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding generation service is currently unavailable.",
        ) from e
    except VectorStoreError as e:
        logger.error("Vector store failure during search for user %s: %s", current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vector retrieval engine encountered an internal error.",
        ) from e
