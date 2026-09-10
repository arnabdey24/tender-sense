"""Private conversations; every lookup is scoped to organization and owner."""

from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assistant_conversations"
    __table_args__ = (Index("ix_assistant_owner_tender", "org_id", "user_id", "tender_id"),)

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tender_id: Mapped[UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(500))


class AssistantMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "request_id", "role"),
        Index("ix_assistant_messages_conversation", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE")
    )
    request_id: Mapped[UUID]
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="complete")
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
