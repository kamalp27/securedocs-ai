from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_db
from app.core.config import settings
from app.core.csrf import (
    clear_auth_cookies,
    generate_csrf_token,
    set_auth_cookies,
    validate_csrf_and_origin,
    validate_origin,
)
from app.core.rate_limiter import rate_limit_ip
from app.models.user import User
from app.schemas.auth import LogoutRequest, MessageResponse, TokenRefreshRequest, TokenResponse
from app.schemas.user import UserLogin, UserRead, UserRegister
from app.services.auth_service import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenServiceError,
    UserAlreadyExistsError,
    authenticate_user,
    create_token_pair_for_user,
    register_user,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    dependencies=[Depends(rate_limit_ip(max_requests=3, window_seconds=60, action="registration"))],
)
def register(
    user_in: UserRegister,
    db: Session = Depends(get_db),
):
    """
    Register a new user account with default analyst role.
    Rejects duplicate email addresses with HTTP 409 Conflict.
    """
    try:
        user = register_user(db=db, user_in=user_in)
        return user
    except UserAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and issue JWT access and refresh tokens",
    dependencies=[Depends(rate_limit_ip(max_requests=5, window_seconds=60, action="login"))],
)
async def login(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Authenticate user credentials and issue an access token & secure HttpOnly refresh cookie.
    Supports both JSON request body and application/x-www-form-urlencoded form data.
    """
    content_type = request.headers.get("content-type", "")
    email: str = ""
    password: str = ""

    if "application/json" in content_type:
        try:
            body = await request.json()
            email = body.get("email") or body.get("username", "")
            password = body.get("password", "")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload.",
            ) from e
    else:
        try:
            form = await request.form()
            email = form.get("username") or form.get("email", "")
            password = form.get("password", "")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid form data payload.",
            ) from e

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password must be provided.",
        )

    try:
        user = authenticate_user(db=db, email=email, password=password)
        token_pair = create_token_pair_for_user(db=db, user=user)

        # Generate anti-CSRF token and set secure cookies on response
        csrf_token = generate_csrf_token()
        set_auth_cookies(
            response=response,
            raw_refresh_token=token_pair.raw_refresh_token,
            csrf_token=csrf_token,
        )

        return TokenResponse(
            access_token=token_pair.access_token,
            token_type=token_pair.token_type,
            expires_in=token_pair.expires_in,
            csrf_token=csrf_token,
        )
    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except InactiveUserError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and issue new token pair",
)
def refresh_tokens(
    request: Request,
    response: Response,
    payload: Optional[TokenRefreshRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Rotate an existing refresh token: marks old token revoked and issues a new token pair.
    The refresh token is extracted from the HttpOnly cookie (or optional payload for non-browser clients).
    Enforces Origin verification and anti-CSRF token validation for cookie-authenticated requests.
    Detects replay attacks and revokes token family on token reuse.
    """
    cookie_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    body_token = payload.refresh_token if payload else None
    raw_refresh = cookie_token or body_token

    if not raw_refresh:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate CSRF and Origin when cookie authentication is active
    if cookie_token:
        validate_csrf_and_origin(request)
    else:
        # For non-browser clients providing explicit token in body, validate origin if declared
        validate_origin(request)

    try:
        new_token_pair = rotate_refresh_token(db=db, raw_refresh_token=raw_refresh)
        csrf_token = generate_csrf_token()
        set_auth_cookies(
            response=response,
            raw_refresh_token=new_token_pair.raw_refresh_token,
            csrf_token=csrf_token,
        )

        return TokenResponse(
            access_token=new_token_pair.access_token,
            token_type=new_token_pair.token_type,
            expires_in=new_token_pair.expires_in,
            csrf_token=csrf_token,
        )
    except InvalidTokenServiceError as e:
        # Clear cookies on invalid, expired, or replayed tokens
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke refresh token on logout",
)
def logout(
    request: Request,
    response: Response,
    payload: Optional[LogoutRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Revoke a refresh token and delete authentication cookies on logout.
    Validates CSRF and Origin for cookie-authenticated requests.
    """
    cookie_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    body_token = payload.refresh_token if payload else None
    raw_refresh = cookie_token or body_token

    if cookie_token:
        validate_csrf_and_origin(request)
    else:
        validate_origin(request)

    if raw_refresh:
        try:
            revoke_refresh_token(db=db, raw_refresh_token=raw_refresh)
        except Exception:
            pass

    clear_auth_cookies(response)
    return MessageResponse(message="Successfully logged out.")


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
):
    """
    Retrieve safe profile information for the authenticated user.
    """
    return current_user
