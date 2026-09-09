from __future__ import annotations

import json

import pytest

from app.core.exceptions import (
    AppError,
    ConflictError,
    ErrorDetail,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (NotFoundError(), 404, "not_found"),
        (ConflictError(), 409, "conflict"),
        (ValidationError(), 422, "validation_error"),
        (PermissionDeniedError(), 403, "permission_denied"),
    ],
)
def test_error_types_carry_status_and_code(error: AppError, status_code: int, code: str) -> None:
    assert error.status_code == status_code
    assert error.code == code


def test_response_uses_the_shared_envelope() -> None:
    error = ValidationError(
        "Email is already registered.",
        details=[ErrorDetail(field="email", message="Already registered.")],
    )

    payload = json.loads(bytes(error.to_response().body))

    assert payload == {
        "error": {
            "code": "validation_error",
            "message": "Email is already registered.",
            "details": [{"field": "email", "message": "Already registered."}],
        }
    }


def test_message_and_code_can_be_overridden() -> None:
    error = AppError("Nope.", code="custom_code", status_code=418)

    assert (error.message, error.code, error.status_code) == ("Nope.", "custom_code", 418)


class TestModelValidationHandler:
    """A model built from user input outside a request body must still yield 422.

    Query-parameter dependencies construct models by hand, and without a handler
    the pydantic error escapes as a 500 that names nothing useful.
    """

    async def test_a_model_error_becomes_a_validation_response(self) -> None:
        from httpx import ASGITransport, AsyncClient
        from pydantic import BaseModel, field_validator

        from app.main import create_app

        class Payload(BaseModel):
            value: str

            @field_validator("value")
            @classmethod
            def _reject(cls, v: str) -> str:
                raise ValueError("never acceptable")

        app = create_app()

        @app.get("/boom")
        async def boom() -> dict[str, str]:
            Payload(value="anything")
            return {}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/boom")

        assert response.status_code == 422
        body = response.json()["error"]
        assert body["code"] == "validation_error"
        assert body["details"][0]["field"] == "value"
