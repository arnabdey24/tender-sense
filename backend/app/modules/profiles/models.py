"""What a company can do — the other half of every match.

One profile per organization. Its text is embedded per *facet* rather than as
one blob: an overview vector, one per service, one per past project, and one for
the sector/geography footprint. A tender then scores against the facet it
actually resembles, so a firm that does both civil works and IT is not penalised
on either by having its two halves averaged into a vector that means neither.

Facets are re-embedded only when their own text hash changes, which is what
keeps editing one service line from re-embedding an entire profile.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

EMBEDDING_DIMS = settings.embedding_dims


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )


class ProfileFacet(enum.StrEnum):
    """Which part of the profile a vector represents."""

    OVERVIEW = "overview"
    SERVICE = "service"
    PAST_PROJECT = "past_project"
    SECTOR_GEO = "sector_geo"


class CompanyProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The organization's capability statement.

    ``version`` increments on every meaningful edit and is stamped onto each
    match, so a score can always be traced back to the profile that produced it
    even after the profile has moved on.
    """

    __tablename__ = "company_profiles"
    __table_args__ = (UniqueConstraint("org_id"),)

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    overview: Mapped[str | None] = mapped_column(Text, default=None)
    #: Coarse sector codes matching `app.ai.schemas.Sector`.
    sectors: Mapped[list[str]] = mapped_column(default=list, server_default="[]")
    #: ISO 3166-1 alpha-2 codes the company will bid in.
    geographies: Mapped[list[str]] = mapped_column(default=list, server_default="[]")
    #: Free-text terms the company uses about itself; feeds the hybrid keyword
    #: term in scoring, not the embedding.
    keywords: Mapped[list[str]] = mapped_column(default=list, server_default="[]")

    annual_turnover: Mapped[float | None] = mapped_column(Numeric(18, 2), default=None)
    turnover_currency: Mapped[str | None] = mapped_column(String(3), default=None)
    turnover_year: Mapped[int | None] = mapped_column(Integer, default=None)
    years_in_business: Mapped[int | None] = mapped_column(Integer, default=None)
    employee_count: Mapped[int | None] = mapped_column(Integer, default=None)
    #: Whether the company is willing to bid as part of a joint venture.
    accepts_jv: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    #: 0..100, driven by which sections are filled in. Shown as an onboarding nudge.
    completeness: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    #: When this organization's one welcome pull was started.
    #:
    #: Filling in a profile is the moment someone expects the product to do
    #: something, and until then the pool may be whatever the last scheduled
    #: pass left. So the first save that carries the profile over the matching
    #: threshold pulls the portals once. Once, ever: after that the schedule
    #: owns it, and a stamp here is what makes the difference between a
    #: courtesy and a portal being asked again on every edit.
    welcome_sync_at: Mapped[datetime | None] = mapped_column(default=None)


class ProfileService(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One thing the company sells. Embedded as its own facet."""

    __tablename__ = "profile_services"
    __table_args__ = (Index("ix_profile_services_profile_id", "profile_id"),)

    profile_id: Mapped[UUID] = mapped_column(ForeignKey("company_profiles.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    sector: Mapped[str | None] = mapped_column(String(50), default=None)
    #: Orders the list in the UI; not used in scoring.
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ProfilePastProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Evidence of delivery. Feeds both matching and the experience rules."""

    __tablename__ = "profile_past_projects"
    __table_args__ = (Index("ix_profile_past_projects_profile_id", "profile_id"),)

    profile_id: Mapped[UUID] = mapped_column(ForeignKey("company_profiles.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    client: Mapped[str | None] = mapped_column(String(300), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    sector: Mapped[str | None] = mapped_column(String(50), default=None)
    country: Mapped[str | None] = mapped_column(String(2), default=None)
    value: Mapped[float | None] = mapped_column(Numeric(18, 2), default=None)
    currency: Mapped[str | None] = mapped_column(String(3), default=None)
    started_on: Mapped[date | None] = mapped_column(Date, default=None)
    completed_on: Mapped[date | None] = mapped_column(Date, default=None)


class ProfileCertification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A credential the company holds.

    ``code`` is canonicalised (upper case, punctuation stripped) so a rule
    comparing "ISO 9001" against "iso-9001" still matches; ``label`` keeps
    whatever the user typed, for display.
    """

    __tablename__ = "profile_certifications"
    __table_args__ = (
        UniqueConstraint("profile_id", "code"),
        Index("ix_profile_certifications_profile_id", "profile_id"),
    )

    profile_id: Mapped[UUID] = mapped_column(ForeignKey("company_profiles.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(200))
    issuer: Mapped[str | None] = mapped_column(String(200), default=None)
    valid_until: Mapped[date | None] = mapped_column(Date, default=None)


class ProfileEmbedding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One vector for one facet of a profile.

    ``source_id`` points at the service or project the facet came from, so a
    deleted service takes its vector with it. ``text_hash`` is what makes
    re-embedding incremental: unchanged facets are skipped.
    """

    __tablename__ = "profile_embeddings"
    __table_args__ = (
        UniqueConstraint("profile_id", "facet_kind", "source_id", "model"),
        Index("ix_profile_embeddings_profile_id", "profile_id"),
        Index(
            "ix_profile_embeddings_vector",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    profile_id: Mapped[UUID] = mapped_column(ForeignKey("company_profiles.id", ondelete="CASCADE"))
    facet_kind: Mapped[ProfileFacet] = mapped_column(_pg_enum(ProfileFacet, "profile_facet"))
    #: Null for the overview and sector/geo facets, which have no owning row.
    source_id: Mapped[UUID | None] = mapped_column(default=None)
    label: Mapped[str] = mapped_column(String(300), default="")
    model: Mapped[str] = mapped_column(String(100))
    dims: Mapped[int] = mapped_column(Integer, default=EMBEDDING_DIMS)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS))
    text_hash: Mapped[str] = mapped_column(String(64))
