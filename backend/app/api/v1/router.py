"""Aggregated API v1 router."""

from fastapi import APIRouter, Depends
from app.api.deps import require_role
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.search import router as search_router
from app.api.v1.qa import router as qa_router
from app.models.user import User

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(documents_router)
api_v1_router.include_router(search_router)
api_v1_router.include_router(qa_router)


@api_v1_router.get("/admin/ping", tags=["Admin"])
def admin_ping(current_user: User = Depends(require_role(["admin"]))):
    """Admin-only probe to verify role authorization."""
    return {"message": "Admin access granted", "admin_email": current_user.email}
