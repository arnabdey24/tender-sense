"""Request bodies for the signed-in user's own account."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, TypeAdapter
from pydantic import HttpUrl as _HttpUrl
from pydantic import ValidationError as PydanticValidationError

_url_adapter: TypeAdapter[_HttpUrl] = TypeAdapter(_HttpUrl)


def _validate_avatar_url(value: str | None) -> str | None:
    if value is None:
        return None
    url = value.strip()
    if not url:
        return None
    try:
        _url_adapter.validate_python(url)
    except PydanticValidationError as exc:
        raise ValueError("avatar_url must be a valid http(s) URL") from exc
    return url


FullName = Annotated[str, Field(min_length=1, max_length=200)]
AvatarUrl = Annotated[str | None, Field(max_length=1000), AfterValidator(_validate_avatar_url)]


class UserUpdate(BaseModel):
    """Every field optional; fields left unset are not touched.

    Deliberately excludes ``email``: changing an address has to re-run
    verification, otherwise an account could be moved to an unproven address
    and inherit its organization's notifications.
    """

    full_name: FullName | None = None
    avatar_url: AvatarUrl = None
