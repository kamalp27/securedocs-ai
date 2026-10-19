"""Health check API router providing liveness and deep readiness probes."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.rag.vector_store import get_vector_store

logger = logging.getLogger("securedocs.api.health")

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Service liveness probe (lightweight, non-blocking)."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "version": "0.1.0",
    }


@router.get("/health/ready")
def readiness_check(db: Session = Depends(get_db)):
    """
    Service readiness probe for load balancers and orchestrators.
    Safely verifies database connectivity, vector index readiness,
    and storage writability without leaking internal paths or secrets.
    Returns HTTP 503 if any required component is unavailable.
    """
    components = {}
    is_ready = True

    # 1. Database Connectivity
    try:
        db.execute(text("SELECT 1"))
        components["database"] = "ok"
    except Exception as e:
        logger.error("Readiness probe database check failed: %s", e)
        components["database"] = "unavailable"
        is_ready = False

    # 2. Vector Store Readiness
    try:
        v_store = get_vector_store()
        # Verify store is loaded and has a valid dimension
        if v_store is not None and v_store.dimension > 0:
            components["vector_store"] = "ok"
        else:
            components["vector_store"] = "degraded"
            is_ready = False
    except Exception as e:
        logger.error("Readiness probe vector store check failed: %s", e)
        components["vector_store"] = "unavailable"
        is_ready = False

    # 3. Upload Storage Writability
    try:
        upload_path = Path(settings.UPLOAD_DIR).resolve()
        upload_path.mkdir(parents=True, exist_ok=True)
        # Transient write-and-delete probe
        probe_file = upload_path / f".probe_{uuid.uuid4().hex}"
        try:
            probe_file.touch()
            probe_file.unlink()
            components["storage"] = "ok"
        except Exception as e:
            logger.error("Readiness probe storage write check failed: %s", e)
            components["storage"] = "unavailable"
            is_ready = False
    except Exception as e:
        logger.error("Readiness probe storage directory check failed: %s", e)
        components["storage"] = "unavailable"
        is_ready = False

    response_status = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    payload = {
        "status": "ready" if is_ready else "not_ready",
        "service": settings.PROJECT_NAME,
        "components": components,
    }
    return JSONResponse(status_code=response_status, content=payload)
