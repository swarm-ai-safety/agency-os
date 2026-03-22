"""Add gateway provider key storage table.

Revision ID: a7f6c3d9b2e1
Revises: 9d8e7c6b5a4f
Create Date: 2026-03-08 23:25:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7f6c3d9b2e1"
down_revision: Union[str, Sequence[str], None] = "9d8e7c6b5a4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gateway_provider_keys",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("provider"),
    )


def downgrade() -> None:
    op.drop_table("gateway_provider_keys")
