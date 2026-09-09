"""Request and response bodies for the company profile."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.ai.schemas import Sector


def _upper_codes(values: list[str]) -> list[str]:
    """ISO country codes, stored uppercase and de-duplicated."""
    seen: list[str] = []
    for value in values:
        code = value.strip().upper()
        if len(code) == 2 and code.isalpha() and code not in seen:
            seen.append(code)
    return seen


def canonical_certification(value: str) -> str:
    """Fold a certification into a comparable code.

    "ISO 9001", "iso-9001" and "ISO9001:2015" all have to match the same rule,
    so punctuation, spacing, case and any trailing revision are stripped.
    """
    head = value.split(":")[0]
    return "".join(character for character in head if character.isalnum()).upper()


CountryCodes = Annotated[list[str], AfterValidator(_upper_codes)]


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    sector: Sector | None = None
    position: int = 0


class ServiceRead(ServiceIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class PastProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    client: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    sector: Sector | None = None
    country: str | None = Field(default=None, max_length=2)
    value: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    started_on: date | None = None
    completed_on: date | None = None


class PastProjectRead(PastProjectIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class CertificationIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    valid_until: date | None = None


class CertificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    label: str
    issuer: str | None = None
    valid_until: date | None = None


class ProfileUpdate(BaseModel):
    """Every field optional; anything left unset is not touched."""

    overview: str | None = Field(default=None, max_length=8000)
    sectors: list[Sector] | None = None
    geographies: CountryCodes | None = None
    keywords: list[str] | None = None
    annual_turnover: float | None = Field(default=None, ge=0)
    turnover_currency: str | None = Field(default=None, max_length=3)
    turnover_year: int | None = Field(default=None, ge=1900, le=2200)
    years_in_business: int | None = Field(default=None, ge=0, le=500)
    employee_count: int | None = Field(default=None, ge=0)
    accepts_jv: bool | None = None


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    overview: str | None = None
    sectors: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    annual_turnover: float | None = None
    turnover_currency: str | None = None
    turnover_year: int | None = None
    years_in_business: int | None = None
    employee_count: int | None = None
    accepts_jv: bool = True
    completeness: int = 0
    version: int = 1
    updated_at: datetime

    services: list[ServiceRead] = Field(default_factory=list)
    past_projects: list[PastProjectRead] = Field(default_factory=list)
    certifications: list[CertificationRead] = Field(default_factory=list)


class CompletenessSection(BaseModel):
    key: str
    label: str
    complete: bool
    weight: int


class CompletenessRead(BaseModel):
    """What is filled in, and what to nudge the user towards next."""

    score: int
    sections: list[CompletenessSection]
    next_step: str | None = None


class TaxonomiesRead(BaseModel):
    """Option lists the profile forms need, served from the backend so the
    frontend cannot drift from what the matcher actually understands."""

    sectors: list[dict[str, str]]
    common_certifications: list[str]


class RematchResponse(BaseModel):
    enqueued: bool
    job_id: str | None = None
    reason: str = "profile_changed"
