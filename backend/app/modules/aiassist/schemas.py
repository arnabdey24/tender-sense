"""Request and response bodies for the form-filling helpers."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.ai.research import CompanyResearch
from app.ai.writing import MAX_INPUT_CHARS, WritingField

#: Schemes a company website may use. Anything else is a way of asking the
#: provider to fetch something that is not a web page.
ALLOWED_SCHEMES = ("http", "https")


class ResearchRequest(BaseModel):
    url: str = Field(min_length=4, max_length=500)

    @field_validator("url")
    @classmethod
    def _normalise(cls, value: str) -> str:
        """Accept what a person types, reject what a person would not.

        People type `acme.com`, so a missing scheme is added rather than
        refused. Everything else is checked here rather than trusted to the
        provider: this string is handed to a fetcher, and `file://`,
        `gopher://` or a bare IP are not a company's website — they are
        somebody finding out what our fetcher can reach.
        """
        from urllib.parse import urlparse

        candidate = value.strip()
        if not candidate:
            raise ValueError("Enter your company's website address.")
        if "://" not in candidate:
            candidate = f"https://{candidate}"

        parsed = urlparse(candidate)
        if parsed.scheme not in ALLOWED_SCHEMES:
            raise ValueError("The address must start with http:// or https://.")
        host = (parsed.hostname or "").lower()
        if not host or "." not in host:
            raise ValueError("That does not look like a website address.")
        if host in {"localhost"} or host.endswith(".localhost"):
            raise ValueError("That does not look like a company website.")
        return candidate


class ResearchResponse(BaseModel):
    """The draft, and where it came from, for the form to show and the user to edit."""

    draft: CompanyResearch
    retrieved_url: str = ""
    model: str = ""


class WritingRequest(BaseModel):
    field: WritingField
    text: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)


class WritingResponse(BaseModel):
    text: str
    note: str = ""
