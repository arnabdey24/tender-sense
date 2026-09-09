"""Application error types and the JSON error envelope used by every endpoint.

Envelope (matches the frontend contract):
    {"error": {"code": "...", "message": "...", "details": [{"field": "...", "message": "..."}]}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = []


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    """Base class for expected, client-facing failures."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "Request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: list[ErrorDetail] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details or []
        self.headers = headers
        super().__init__(self.message)

    def to_response(self) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(code=self.code, message=self.message, details=self.details)
        )
        return JSONResponse(
            status_code=self.status_code,
            content=body.model_dump(mode="json"),
            headers=self.headers,
        )


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Resource not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "Resource already exists."


class ValidationError(AppError):
    status_code = 422  # UNPROCESSABLE CONTENT (constant name varies across Starlette)
    code = "validation_error"
    message = "The submitted data is invalid."


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"
    message = "Authentication required."

    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("headers", {"WWW-Authenticate": "Bearer"})
        super().__init__(message, **kwargs)


class TokenExpiredError(AuthenticationError):
    code = "token_expired"
    message = "Access token has expired."


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "You do not have permission to perform this action."


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many requests. Please try again later."


class ExternalServiceError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "external_service_error"
    message = "An upstream service failed."


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            ErrorDetail(
                field=".".join(str(part) for part in err["loc"][1:]) or None,
                message=err["msg"],
            )
            for err in exc.errors()
        ]
        return ValidationError(details=details).to_response()

    @app.exception_handler(PydanticValidationError)
    async def _model_validation_error(_: Request, exc: PydanticValidationError) -> JSONResponse:
        """A model built from user input outside a request body.

        Without this the error escapes as a 500 and tells the caller nothing
        about which value was wrong.
        """
        details = [
            ErrorDetail(
                field=".".join(str(part) for part in err["loc"]) or None,
                message=err["msg"],
            )
            for err in exc.errors()
        ]
        return ValidationError(details=details).to_response()

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "http_error")
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return AppError(detail, code=code, status_code=exc.status_code).to_response()

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", path=request.url.path, error=str(exc))
        return AppError(
            "An unexpected error occurred.",
            code="internal_error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        ).to_response()
