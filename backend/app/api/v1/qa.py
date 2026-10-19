"""Grounded Generative Q&A API endpoint."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.core.rate_limiter import get_client_ip, rate_limit_user
from app.models.user import User
from app.rag.embeddings.base import EmbeddingError
from app.rag.generation.base import GenerationError
from app.rag.vector_store.faiss_store import VectorStoreError
from app.schemas.qa import QARequest, QAResponse
from app.services.qa_service import QAService

logger = logging.getLogger("securedocs.api.qa")

router = APIRouter(prefix="/qa", tags=["Grounded Q&A"])


@router.post(
    "/ask",
    response_model=QAResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask a question grounded in authorized documents with citations",
)
def ask_question(
    qa_request: QARequest,
    http_request: Request,
    current_user: User = Depends(rate_limit_user(max_requests=15, window_seconds=60, action="Q&A query")),
    db: Session = Depends(get_db),
) -> QAResponse:
    """
    Submit a natural language question. The system will:
    1. Retrieve relevant chunks strictly from documents the authenticated user has permission to read.
    2. Synthesize an answer grounded exclusively in retrieved evidence.
    3. Include strictly verified, deduplicated source citations with file, page/section, and snippet.
    4. Explicitly indicate if evidence is insufficient to answer the question.
    """
    client_ip = get_client_ip(http_request)

    try:
        service = QAService()
        response = service.answer_question(
            db=db,
            current_user=current_user,
            request=qa_request,
            ip_address=client_ip,
        )
        return response

    except EmbeddingError as e:
        logger.error("Embedding failure during Q&A for user %s: %s", current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding generation service is currently unavailable.",
        ) from e
    except VectorStoreError as e:
        logger.error("Vector store failure during Q&A for user %s: %s", current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vector retrieval engine encountered an internal error.",
        ) from e
    except GenerationError as e:
        logger.error("Generation failure during Q&A for user %s: %s", current_user.id, e)
        error_str = str(e)
        if "Unsupported generator provider" in error_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_str,
            ) from e
        if "unavailable" in error_str.lower() or "connection failed" in error_str.lower() or "timed out" in error_str.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_str,
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Answer generation provider encountered an internal error.",
        ) from e
