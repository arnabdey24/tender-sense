"""Stored bidding criteria.

A rule set is mutable in name only: every edit writes a new immutable version,
because each match records the version that graded it. Without that, changing a
rule would silently rewrite the reasoning behind every verdict already shown to
a customer — and the "why was this rejected?" question would have no answer.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )


class OverrideVerdict(enum.StrEnum):
    """A human's answer to a rule the engine could not decide."""

    PASS = "pass"
    FAIL = "fail"


class RuleSet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One organization's bidding criteria.

    At most one active set per organization: a customer reasoning about "am I
    eligible" needs a single answer, not one per draft they left lying around.
    """

    __tablename__ = "rule_sets"
    __table_args__ = (
        Index(
            "uq_rule_sets_active_per_org",
            "org_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        Index("ix_rule_sets_org_id", "org_id"),
    )

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200), default="Bidding criteria")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    #: Points at the version currently in force. The definition itself lives on
    #: the version row, so this table never holds rule content.
    current_version_id: Mapped[UUID | None] = mapped_column(default=None)


class RuleSetVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An immutable snapshot of a rule set's definition.

    Never updated after insert. A match stores this row's id, so the exact
    criteria behind any verdict can always be reconstructed.
    """

    __tablename__ = "rule_set_versions"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "version_number"),
        Index("ix_rule_set_versions_rule_set_id", "rule_set_id"),
    )

    rule_set_id: Mapped[UUID] = mapped_column(ForeignKey("rule_sets.id", ondelete="CASCADE"))
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    definition: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    #: Why this version was created, for the activity trail.
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    created_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )


class RuleOverride(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A human's ruling on one rule for one tender.

    The engine says "I could not determine this"; a person reads the bidding
    document and answers. Scoped to a single tender because the answer usually
    is — "this particular notice does accept a JV" is not a general fact.
    """

    __tablename__ = "rule_overrides"
    __table_args__ = (
        UniqueConstraint("org_id", "tender_id", "rule_id"),
        Index("ix_rule_overrides_org_id_tender_id", "org_id", "tender_id"),
    )

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    tender_id: Mapped[UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    #: The rule's id inside the definition, not a foreign key — rules live in
    #: JSON and a version can drop one.
    rule_id: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[OverrideVerdict] = mapped_column(_pg_enum(OverrideVerdict, "override_verdict"))
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )


class FxRate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Units of ``currency`` per one unit of ``base``.

    Money rules compare across currencies constantly — a BDT turnover
    requirement against a USD profile — and comparing them unconverted is a
    hundredfold error, not a rounding one. A missing rate makes the rule
    unknown rather than guessing.
    """

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("base", "currency", "as_of"),)

    base: Mapped[str] = mapped_column(String(3), default="USD")
    currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[float] = mapped_column(Float)
    as_of: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    fetched_at: Mapped[datetime | None] = mapped_column(default=None)
