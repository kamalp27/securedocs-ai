"""In-process sliding-window rate limiter with safe IP/identity isolation."""

import logging
import math
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException, Request, status

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.models.user import User

logger = logging.getLogger("securedocs.rate_limiter")


def get_client_ip(request: Request) -> str:
    """
    Safely extract client IP address.
    Does NOT trust arbitrary X-Forwarded-For headers unless TRUST_PROXY_HEADERS is True
    AND the connecting host is explicitly listed in TRUSTED_PROXIES.
    """
    direct_host = request.client.host if request.client else "127.0.0.1"

    if settings.TRUST_PROXY_HEADERS and direct_host in settings.TRUSTED_PROXIES:
        x_forwarded = request.headers.get("x-forwarded-for")
        if x_forwarded:
            first_ip = x_forwarded.split(",")[0].strip()
            if first_ip:
                return first_ip

    return direct_host


class InMemoryRateLimiter:
    """
    Thread-safe in-memory sliding-window rate limiter.
    
    NOTE ON ARCHITECTURE:
    This rate limiter stores state in process memory. It provides zero-overhead,
    self-contained protection for single-process, local, and pilot deployments.
    For horizontal multi-worker or multi-container deployments, a centralized
    store (e.g. Redis) is required to coordinate limits across instances.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._requests: Dict[str, List[float]] = {}

    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int]:
        """
        Check if request is within limits.
        
        Returns:
            (is_allowed: bool, retry_after_seconds: int)
        """
        if not settings.RATE_LIMIT_ENABLED:
            return True, 0

        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            timestamps = self._requests.get(key, [])
            # Prune timestamps outside current window
            valid_timestamps = [t for t in timestamps if t > window_start]

            if len(valid_timestamps) >= max_requests:
                # Limit exceeded: compute time until oldest entry rolls out
                oldest_entry = valid_timestamps[0]
                retry_after = max(1, math.ceil(window_seconds - (now - oldest_entry)))
                self._requests[key] = valid_timestamps
                return False, retry_after

            # Allowed: record current timestamp
            valid_timestamps.append(now)
            self._requests[key] = valid_timestamps
            return True, 0

    def reset(self) -> None:
        """Reset all rate limiter state. Useful for test isolation."""
        with self._lock:
            self._requests.clear()


limiter = InMemoryRateLimiter()


def rate_limit_ip(max_requests: int, window_seconds: int = 60, action: str = "request") -> Callable:
    """
    FastAPI dependency factory enforcing rate limits per client IP.
    """
    def dependency(request: Request) -> None:
        client_ip = get_client_ip(request)
        key = f"ip:{action}:{client_ip}"
        allowed, retry_after = limiter.check_rate_limit(
            key=key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        if not allowed:
            logger.warning(
                "Rate limit exceeded for IP %s on %s (limit: %d/%ds)",
                client_ip,
                action,
                max_requests,
                window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests for {action}. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency


def rate_limit_user(max_requests: int, window_seconds: int = 60, action: str = "request") -> Callable:
    """
    FastAPI dependency factory enforcing rate limits per authenticated user.
    """
    def dependency(
        request: Request,
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        user_id_str = str(current_user.id)
        key = f"user:{action}:{user_id_str}"
        allowed, retry_after = limiter.check_rate_limit(
            key=key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        if not allowed:
            logger.warning(
                "Rate limit exceeded for user %s on %s (limit: %d/%ds)",
                user_id_str,
                action,
                max_requests,
                window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests for {action}. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
        return current_user

    return dependency
