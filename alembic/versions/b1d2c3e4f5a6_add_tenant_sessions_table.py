"""Add tenant sessions table for persistent login sessions.

Revision ID: b1d2c3e4f5a6
Revises: a7f6c3d9b2e1
Create Date: 2026-03-11 07:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1d2c3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a7f6c3d9b2e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_sessions",
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("revoked_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_tenant_sessions_tenant_id", "tenant_sessions", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_tenant_sessions_expires_at", "tenant_sessions", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_sessions_expires_at", table_name="tenant_sessions")
    op.drop_index("ix_tenant_sessions_tenant_id", table_name="tenant_sessions")
    op.drop_table("tenant_sessions")
