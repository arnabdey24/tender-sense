"""Notification settings, recipients, the in-app centre and the send ledger.

Revision ID: 0009_notifications
Revises: 0008_runs
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_notifications"
down_revision: str | None = "0008_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "instant_match",
                "daily_digest",
                "deadline_reminder",
                "tender_updated",
                "source_down",
                "system",
                name="notification_type",
            ),
            nullable=False,
        ),
        sa.Column("subject_key", sa.String(length=200), nullable=False),
        sa.Column("channel", sa.String(length=20), server_default="email", nullable=False),
        sa.Column("recipients", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_notification_ledger_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_ledger")),
        sa.UniqueConstraint(
            "org_id",
            "type",
            "subject_key",
            name=op.f("uq_notification_ledger_org_id_type_subject_key"),
        ),
    )
    op.create_index(
        "ix_notification_ledger_org_id_created_at",
        "notification_ledger",
        ["org_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "notification_recipients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column(
            "types", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("verify_token_hash", sa.String(length=64), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribe_token", sa.String(length=64), nullable=False),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("added_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["added_by_id"],
            ["users.id"],
            name=op.f("fk_notification_recipients_added_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_notification_recipients_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_recipients")),
        sa.UniqueConstraint(
            "org_id", "email", name=op.f("uq_notification_recipients_org_id_email")
        ),
    )
    op.create_index(
        "ix_notification_recipients_org_id", "notification_recipients", ["org_id"], unique=False
    )
    op.create_index(
        op.f("ix_notification_recipients_unsubscribe_token"),
        "notification_recipients",
        ["unsubscribe_token"],
        unique=True,
    )
    op.create_index(
        op.f("ix_notification_recipients_verify_token_hash"),
        "notification_recipients",
        ["verify_token_hash"],
        unique=False,
    )
    op.create_table(
        "notification_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("inapp_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("instant_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("instant_min_grade", sa.String(length=1), server_default="S", nullable=False),
        sa.Column("instant_requires_eligible", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("digest_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("digest_time", sa.Time(), server_default="08:00", nullable=False),
        sa.Column(
            "digest_timezone", sa.String(length=64), server_default="Asia/Dhaka", nullable=False
        ),
        sa.Column("digest_min_grade", sa.String(length=1), server_default="B", nullable=False),
        sa.Column("last_digest_sent_for", sa.Date(), nullable=True),
        sa.Column("reminders_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "reminder_offsets",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[7, 2]",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_notification_settings_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_settings")),
        sa.UniqueConstraint("org_id", name=op.f("uq_notification_settings_org_id")),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "type",
            sa.Enum(
                "instant_match",
                "daily_digest",
                "deadline_reminder",
                "tender_updated",
                "source_down",
                "system",
                name="notification_type",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column("tender_id", sa.Uuid(), nullable=True),
        sa.Column(
            "data", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_notifications_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tender_id"],
            ["tenders.id"],
            name=op.f("fk_notifications_tender_id_tenders"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "ix_notifications_org_id_created_at",
        "notifications",
        ["org_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_org_id_type", "notifications", ["org_id", "type"], unique=False
    )
    op.create_table(
        "notification_reads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "read_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name=op.f("fk_notification_reads_notification_id_notifications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_reads_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_reads")),
        sa.UniqueConstraint(
            "notification_id", "user_id", name=op.f("uq_notification_reads_notification_id_user_id")
        ),
    )
    op.create_index(
        "ix_notification_reads_user_id", "notification_reads", ["user_id"], unique=False
    )


#: Alembic creates this implicitly with the tables and never drops it, which
#: would make a downgrade followed by an upgrade fail with DuplicateObjectError.
ENUM_TYPES = ("notification_type",)


def downgrade() -> None:
    op.drop_index("ix_notification_reads_user_id", table_name="notification_reads")
    op.drop_table("notification_reads")
    op.drop_index("ix_notifications_org_id_type", table_name="notifications")
    op.drop_index("ix_notifications_org_id_created_at", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("notification_settings")
    op.drop_index(
        op.f("ix_notification_recipients_verify_token_hash"), table_name="notification_recipients"
    )
    op.drop_index(
        op.f("ix_notification_recipients_unsubscribe_token"), table_name="notification_recipients"
    )
    op.drop_index("ix_notification_recipients_org_id", table_name="notification_recipients")
    op.drop_table("notification_recipients")
    op.drop_index("ix_notification_ledger_org_id_created_at", table_name="notification_ledger")
    op.drop_table("notification_ledger")
    for enum_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
