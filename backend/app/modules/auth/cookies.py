"""Refresh-token cookie handling.

The refresh token lives in an HttpOnly cookie so JavaScript cannot read it,
scoped to the auth path so it is not attached to ordinary API calls. The access
token is returned in the response body and kept in memory by the SPA.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Request, Response

from app.core.config import settings


def cookie_path() -> str:
    return f"{settings.api_v1_prefix}/auth"


def set_refresh_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        expires=expires_at,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
        path=cookie_path(),
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
        path=cookie_path(),
    )


def read_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(settings.refresh_cookie_name)
