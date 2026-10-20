"""FastAPI main application entrypoint."""

import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.db.session import SessionLocal
from app.rag.vector_store import get_vector_store
from app.services.document_service import reconcile_index_if_needed

logger = logging.getLogger("securedocs.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager:
    Verifies database connectivity and restores FAISS/database consistency on startup.
    """
    logger.info("Initializing %s in %s mode...", settings.PROJECT_NAME, settings.ENVIRONMENT)

    session_factory = getattr(app.state, "session_factory", SessionLocal)
    db = session_factory()
    try:
        # Verify database connectivity
        db.execute(text("SELECT 1"))

        # Reconcile FAISS index if database contains active chunks but index is empty
        inspector = inspect(db.get_bind())
        if inspector.has_table("document_chunks") and inspector.has_table("documents"):
            rebuilt_count = reconcile_index_if_needed(db)
            if rebuilt_count > 0:
                logger.info(
                    "Startup reconciliation: restored %d indexed vectors into FAISS vector store.",
                    rebuilt_count,
                )

        v_store = get_vector_store()
        logger.info(
            "FAISS vector store ready. Total vectors indexed: %d (dim=%d)",
            v_store.ntotal,
            v_store.dimension,
        )
    except Exception as e:
        logger.error("Startup initialization or index reconciliation failed: %s", e, exc_info=True)
        raise
    finally:
        db.close()

    yield

    logger.info("Shutting down %s cleanly.", settings.PROJECT_NAME)


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI-Powered Secure Document Management System API",
    version="0.1.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)


# Security response headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Inject standard security headers for browser-level defense."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    docs_paths = {
        f"{settings.API_V1_STR}/docs",
        "/docs",
        f"{settings.API_V1_STR}/redoc",
        "/redoc",
        f"{settings.API_V1_STR}/openapi.json",
        "/openapi.json",
    }
    if request.url.path.rstrip("/") in docs_paths:
        # Restrictive CSP permitting only resources required for interactive Swagger UI / ReDoc
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net; "
            "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com; "
            "connect-src 'self' https: http://localhost:* http://127.0.0.1:*;"
        )
    else:
        # Strict default CSP for all API endpoints and general traffic
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self' http://localhost:* http://127.0.0.1:* ws://localhost:* ws://127.0.0.1:*;"
        )

    if settings.ENABLE_HSTS or request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Global unhandled exception handler: prevents stack trace and path leakage
@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception processing request %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred."},
    )


# CORS Middleware
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include API v1 routes
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirect root requests to API documentation."""
    return RedirectResponse(url=f"{settings.API_V1_STR}/docs")


@app.get("/docs", include_in_schema=False)
def docs_redirect():
    """Redirect standard /docs to API documentation."""
    return RedirectResponse(url=f"{settings.API_V1_STR}/docs")


@app.get("/health", tags=["Health"])
def root_health_check():
    """Root health probe."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/ready", tags=["Health"])
def root_readiness_check(db: Session = Depends(get_db)):
    """Root readiness probe delegating to detailed component check."""
    from app.api.v1.health import readiness_check
    return readiness_check(db)
