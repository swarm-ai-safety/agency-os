"""Add webhook deliveries table for retry/status tracking.

Revision ID: 9d8e7c6b5a4f
Revises: cf90691b667e
Create Date: 2026-03-08 09:55:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d8e7c6b5a4f"
down_revision: Union[str, Sequence[str], None] = "cf90691b667e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("webhook_id", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("org_id", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("event_timestamp", sa.Integer(), nullable=False),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
        sa.Column(
            "retryable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.ForeignKeyConstraint(["webhook_id"], ["webhooks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_deliveries_tenant_webhook",
        "webhook_deliveries",
        ["tenant_id", "webhook_id", "created_at"],
    )
    op.create_index(
        "ix_webhook_deliveries_retry_due",
        "webhook_deliveries",
        ["success", "retryable", "next_retry_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_webhook_deliveries_retry_due", table_name="webhook_deliveries")
    op.drop_index(
        "ix_webhook_deliveries_tenant_webhook", table_name="webhook_deliveries"
    )
    op.drop_table("webhook_deliveries")
