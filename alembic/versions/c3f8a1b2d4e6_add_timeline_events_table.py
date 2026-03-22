"""Add timeline_events table for time-lapse company feature.

Revision ID: c3f8a1b2d4e6
Revises: b1d2c3e4f5a6
Create Date: 2026-03-11 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c3f8a1b2d4e6"
down_revision: Union[str, Sequence[str], None] = "b1d2c3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "timeline_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.Text,
            sa.ForeignKey("tenants.tenant_id"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            sa.Text,
            sa.ForeignKey("organizations.org_id"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.Text),
        sa.Column("agent_name", sa.Text),
        sa.Column("agent_division", sa.Text),
        sa.Column("agent_color", sa.Text),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("detail", sa.Text),
        sa.Column("artifact_type", sa.Text),
        sa.Column("artifact_ref", sa.Text),
        sa.Column("budget_snapshot", sa.Float),
        sa.Column("reputation_snapshot", sa.Float),
        sa.Column("metadata_json", sa.Text),
        sa.Column("timestamp", sa.Float, nullable=False),
    )
    op.create_index(
        "ix_timeline_events_org_ts", "timeline_events", ["org_id", "timestamp"]
    )
    op.create_index(
        "ix_timeline_events_tenant_org", "timeline_events", ["tenant_id", "org_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_timeline_events_tenant_org", table_name="timeline_events")
    op.drop_index("ix_timeline_events_org_ts", table_name="timeline_events")
    op.drop_table("timeline_events")
