"""initial schema

Revision ID: 6bc8e715fa66
Revises:
Create Date: 2026-03-07 15:44:12.771306

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "6bc8e715fa66"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text),
        sa.Column("api_key_hash", sa.Text, unique=True),
        sa.Column("active", sa.Boolean),
        sa.Column("metadata", sa.Text),
        sa.Column("created_at", sa.Text),
    )
    op.create_table(
        "organizations",
        sa.Column("org_id", sa.Text, primary_key=True),
        sa.Column(
            "tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False
        ),
        sa.Column("package_name", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("created_at", sa.Text),
    )
    op.create_table(
        "tasks",
        sa.Column("task_id", sa.Text, primary_key=True),
        sa.Column(
            "tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False
        ),
        sa.Column(
            "org_id", sa.Text, sa.ForeignKey("organizations.org_id"), nullable=False
        ),
        sa.Column("description", sa.Text),
        sa.Column("assigned_to", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("result", sa.Text),
        sa.Column("governance_preset", sa.Text),
        sa.Column("created_at", sa.Text),
    )
    op.create_table(
        "metering_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False
        ),
        sa.Column("org_id", sa.Text),
        sa.Column("agent_id", sa.Text),
        sa.Column("event_type", sa.Text),
        sa.Column("tokens_in", sa.Integer),
        sa.Column("tokens_out", sa.Integer),
        sa.Column("timestamp", sa.Float),
        sa.Column("metadata", sa.Text),
    )
    op.create_table(
        "wallet_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.Text),
        sa.Column("agent_id", sa.Text),
        sa.Column("balance", sa.Float),
        sa.Column("reputation", sa.Float),
        sa.Column("snapshot_at", sa.Text),
    )
    op.create_table(
        "trust_scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Text),
        sa.Column("org_id", sa.Text),
        sa.Column("agent_id", sa.Text, nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("tier", sa.Text, nullable=False),
        sa.Column("total_tasks", sa.Integer, nullable=False),
        sa.Column("successes", sa.Integer, nullable=False),
        sa.Column("failures", sa.Integer, nullable=False),
        sa.Column("partials", sa.Integer, nullable=False),
        sa.Column("computed_at", sa.Float, nullable=False),
    )
    op.create_table(
        "processed_webhook_events",
        sa.Column("event_id", sa.Text, primary_key=True),
        sa.Column("event_type", sa.Text),
        sa.Column("processed_at", sa.Text),
    )
    op.create_table(
        "waitlist",
        sa.Column("email", sa.Text, primary_key=True),
        sa.Column("signed_up_at", sa.Float),
        sa.Column("ip", sa.Text),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Text),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("resource", sa.Text),
        sa.Column("resource_id", sa.Text),
        sa.Column("detail", sa.Text),
        sa.Column("timestamp", sa.Float, nullable=False),
    )
    op.create_table(
        "gateway_requests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.Text, unique=True),
        sa.Column(
            "tenant_id", sa.Text, sa.ForeignKey("tenants.tenant_id"), nullable=False
        ),
        sa.Column("model_id", sa.Text),
        sa.Column("provider", sa.Text),
        sa.Column("tokens_in", sa.Integer),
        sa.Column("tokens_out", sa.Integer),
        sa.Column("latency_ms", sa.Float),
        sa.Column("provider_cost", sa.Float),
        sa.Column("customer_cost", sa.Float),
        sa.Column("margin", sa.Float),
        sa.Column("cached", sa.Boolean, server_default=sa.false()),
        sa.Column("routed_by", sa.Text),
        sa.Column("complexity", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("timestamp", sa.Float),
    )


def downgrade() -> None:
    op.drop_table("gateway_requests")
    op.drop_table("audit_log")
    op.drop_table("waitlist")
    op.drop_table("processed_webhook_events")
    op.drop_table("trust_scores")
    op.drop_table("wallet_snapshots")
    op.drop_table("metering_events")
    op.drop_table("tasks")
    op.drop_table("organizations")
    op.drop_table("tenants")
