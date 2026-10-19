import hashlib
import hmac
import logging
import secrets
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings

logger = logging.getLogger("securedocs.csrf")


def generate_csrf_token() -> str:
    """Generate a high-entropy cryptographically signed anti-CSRF token (HMAC-SHA256)."""
    raw_token = secrets.token_urlsafe(32)
    sig = hmac.new(settings.SECRET_KEY.encode(), raw_token.encode(), hashlib.sha256).hexdigest()
    return f"{raw_token}.{sig}"


def get_allowed_origins(request: Request) -> set[str]:
    """Compile set of normalized origins permitted to perform credentialed operations."""
    allowed = {orig.lower().rstrip("/") for orig in settings.BACKEND_CORS_ORIGINS if orig != "*"}

    # Include current host (same-origin)
    current_origin = f"{request.url.scheme}://{request.url.netloc}".lower().rstrip("/")
    allowed.add(current_origin)

    # Permit ASGI test client synthetic origin in non-production environments
    if settings.ENVIRONMENT in ("development", "test"):
        allowed.add("http://test")
        allowed.add("http://localhost")
        allowed.add("http://127.0.0.1")

    return allowed


def validate_origin(request: Request) -> None:
    """
    Validate Origin or Referer header against allowed CORS origins.
    Rejects cross-origin state changes from unauthorized websites.
    """
    origin_header = request.headers.get("origin")
    referer_header = request.headers.get("referer")

    target_origin: Optional[str] = None
    if origin_header:
        target_origin = origin_header.lower().rstrip("/")
    elif referer_header:
        parsed = urlparse(referer_header)
        if parsed.scheme and parsed.netloc:
            target_origin = f"{parsed.scheme}://{parsed.netloc}".lower().rstrip("/")

    # If an origin is declared, it must match an allowed origin
    if target_origin:
        allowed_origins = get_allowed_origins(request)
        if target_origin not in allowed_origins:
            logger.warning(
                "Rejected state-changing request from unauthorized origin: %s", target_origin
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Untrusted request origin.",
            )


def validate_csrf(request: Request) -> None:
    """
    Validate anti-CSRF token using the signed double-submit cookie pattern.
    Requires matching X-CSRF-Token header and securedocs_csrf_token cookie,
    and validates HMAC signature to prevent cookie injection / tossing from untrusted subdomains.
    """
    header_name = settings.CSRF_HEADER_NAME.lower()
    csrf_header = request.headers.get(settings.CSRF_HEADER_NAME) or request.headers.get(header_name)
    csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)

    if not csrf_header or not csrf_cookie:
        logger.warning("CSRF validation failed: missing header or cookie token.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid.",
        )

    if not secrets.compare_digest(csrf_header, csrf_cookie):
        logger.warning("CSRF validation failed: header does not match cookie.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token validation failed.",
        )

    # Validate HMAC signature to ensure token was minted by this server with SECRET_KEY
    parts = csrf_cookie.split(".")
    if len(parts) != 2:
        logger.warning("CSRF validation failed: malformed token structure.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token validation failed.",
        )

    raw_part, sig_part = parts[0], parts[1]
    expected_sig = hmac.new(settings.SECRET_KEY.encode(), raw_part.encode(), hashlib.sha256).hexdigest()
    if not secrets.compare_digest(sig_part, expected_sig):
        logger.warning("CSRF validation failed: forged or invalid HMAC signature.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token signature invalid.",
        )


def validate_csrf_and_origin(request: Request) -> None:
    """Perform both origin and anti-CSRF checks for sensitive state-changing endpoints."""
    validate_origin(request)
    validate_csrf(request)


def set_auth_cookies(response: Response, raw_refresh_token: str, csrf_token: str) -> None:
    """
    Attach secure authentication cookies to the HTTP response.
    - Refresh token: HttpOnly, restricted Path, explicit SameSite & Secure
    - CSRF token: Non-HttpOnly (readable by frontend SPA to echo in X-CSRF-Token header)
    """
    cookie_kwargs = {
        "max_age": settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        "secure": settings.REFRESH_COOKIE_SECURE,
        "domain": settings.REFRESH_COOKIE_DOMAIN,
    }

    # 1. HttpOnly Refresh Token
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=raw_refresh_token,
        httponly=settings.REFRESH_COOKIE_HTTPONLY,
        samesite=settings.REFRESH_COOKIE_SAMESITE.lower(),  # type: ignore
        path=settings.REFRESH_COOKIE_PATH,
        **cookie_kwargs,
    )

    # 2. Readable Anti-CSRF Token
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=settings.CSRF_COOKIE_HTTPONLY,
        samesite=settings.CSRF_COOKIE_SAMESITE.lower(),  # type: ignore
        path=settings.CSRF_COOKIE_PATH,
        **cookie_kwargs,
    )


def clear_auth_cookies(response: Response) -> None:
    """Delete refresh and CSRF cookies on logout, session expiration, or revocation."""
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
    )
    response.delete_cookie(
        key=settings.CSRF_COOKIE_NAME,
        path=settings.CSRF_COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
    )
