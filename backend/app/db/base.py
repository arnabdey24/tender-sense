"""Declarative base and shared column mixins."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import new_id

#: Marker annotation for case-insensitive email columns.
type Email = str

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Every datetime is stored timezone-aware; `Email` is a case-insensitive
    # citext column so lookups never need LOWER().
    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
        list[str]: JSONB,
        datetime: DateTime(timezone=True),
        Email: CITEXT,
    }

    def __repr__(self) -> str:
        pk = getattr(self, "id", None)
        return f"<{type(self).__name__} id={pk}>"


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id, sort_order=-100)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, sort_order=100
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        sort_order=100,
    )
