"""identity: users, orgs, memberships, invitations, auth tokens, email outbox

Revision ID: 0002_identity
Revises: 0001_extensions
Create Date: 2026-09-09 18:25:51.605804
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_identity"
down_revision: str | None = "0001_extensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("avatar_url", sa.String(length=1000), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_superuser", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "purpose",
            sa.Enum("verify_email", "reset_password", name="auth_token_purpose"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
            ["user_id"], ["users.id"], name=op.f("fk_auth_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_tokens")),
    )
    op.create_index(op.f("ix_auth_tokens_token_hash"), "auth_tokens", ["token_hash"], unique=True)
    op.create_index(
        "ix_auth_tokens_user_id_purpose", "auth_tokens", ["user_id", "purpose"], unique=False
    )
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_account_id", sa.String(length=255), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column(
            "raw_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_oauth_accounts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_accounts")),
        sa.UniqueConstraint(
            "provider",
            "provider_account_id",
            name=op.f("uq_oauth_accounts_provider_provider_account_id"),
        ),
    )
    op.create_index(
        "ix_oauth_accounts_user_id_provider",
        "oauth_accounts",
        ["user_id", "provider"],
        unique=False,
    )
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", postgresql.CITEXT(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("timezone", sa.String(length=64), server_default="Asia/Dhaka", nullable=False),
        sa.Column("plan", sa.String(length=50), server_default="free", nullable=False),
        sa.Column(
            "settings", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_organizations_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True)
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("to_email", postgresql.CITEXT(), nullable=False),
        sa.Column("to_name", sa.String(length=200), nullable=True),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column(
            "context", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "sending", "sent", "failed", "cancelled", name="email_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_id", sa.String(length=400), nullable=True),
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
            name=op.f("fk_email_outbox_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_outbox")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_email_outbox_dedupe_key")),
    )
    op.create_index("ix_email_outbox_org_id", "email_outbox", ["org_id"], unique=False)
    op.create_index(
        "ix_email_outbox_status_next_attempt_at",
        "email_outbox",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("role", sa.Enum("admin", "member", name="org_role"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            ["accepted_user_id"],
            ["users.id"],
            name=op.f("fk_invitations_accepted_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_id"],
            ["users.id"],
            name=op.f("fk_invitations_invited_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_invitations_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
    )
    op.create_index("ix_invitations_org_id", "invitations", ["org_id"], unique=False)
    op.create_index(op.f("ix_invitations_token_hash"), "invitations", ["token_hash"], unique=True)
    op.create_index(
        "uq_invitations_org_id_email_pending",
        "invitations",
        ["org_id", "email"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Enum("admin", "member", name="org_role"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", name="membership_status"),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
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
            name=op.f("fk_memberships_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memberships_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint("org_id", "user_id", name=op.f("uq_memberships_org_id_user_id")),
    )
    op.create_index(
        "ix_memberships_user_id_status", "memberships", ["user_id", "status"], unique=False
    )
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
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
            name=op.f("fk_refresh_sessions_org_id_organizations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_sessions.id"],
            name=op.f("fk_refresh_sessions_replaced_by_id_refresh_sessions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_sessions")),
    )
    op.create_index(
        "ix_refresh_sessions_family_id", "refresh_sessions", ["family_id"], unique=False
    )
    op.create_index(
        op.f("ix_refresh_sessions_token_hash"), "refresh_sessions", ["token_hash"], unique=True
    )
    op.create_index(
        "ix_refresh_sessions_user_id_revoked_at",
        "refresh_sessions",
        ["user_id", "revoked_at"],
        unique=False,
    )


#: Enum types Alembic creates implicitly with the tables above. They must be
#: dropped by hand on downgrade, otherwise re-running upgrade fails with
#: DuplicateObjectError.
ENUM_TYPES = ("auth_token_purpose", "email_status", "membership_status", "org_role")


def downgrade() -> None:
    op.drop_index("ix_refresh_sessions_user_id_revoked_at", table_name="refresh_sessions")
    op.drop_index(op.f("ix_refresh_sessions_token_hash"), table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_family_id", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
    op.drop_index("ix_memberships_user_id_status", table_name="memberships")
    op.drop_table("memberships")
    op.drop_index(
        "uq_invitations_org_id_email_pending",
        table_name="invitations",
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )
    op.drop_index(op.f("ix_invitations_token_hash"), table_name="invitations")
    op.drop_index("ix_invitations_org_id", table_name="invitations")
    op.drop_table("invitations")
    op.drop_index("ix_email_outbox_status_next_attempt_at", table_name="email_outbox")
    op.drop_index("ix_email_outbox_org_id", table_name="email_outbox")
    op.drop_table("email_outbox")
    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations")
    op.drop_table("organizations")
    op.drop_index("ix_oauth_accounts_user_id_provider", table_name="oauth_accounts")
    op.drop_table("oauth_accounts")
    op.drop_index("ix_auth_tokens_user_id_purpose", table_name="auth_tokens")
    op.drop_index(op.f("ix_auth_tokens_token_hash"), table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    for enum_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
