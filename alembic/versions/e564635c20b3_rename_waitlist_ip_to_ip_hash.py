"""rename_waitlist_ip_to_ip_hash

Revision ID: e564635c20b3
Revises: 6bc8e715fa66
Create Date: 2026-03-07 22:00:10.467757

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e564635c20b3"
down_revision: Union[str, Sequence[str], None] = "6bc8e715fa66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename waitlist.ip to ip_hash for clarity (stores SHA-256 hash, not plaintext)."""
    # SQLite 3.25.0+ supports ALTER TABLE RENAME COLUMN
    with op.batch_alter_table("waitlist", schema=None) as batch_op:
        batch_op.alter_column("ip", new_column_name="ip_hash")


def downgrade() -> None:
    """Revert ip_hash back to ip column name."""
    with op.batch_alter_table("waitlist", schema=None) as batch_op:
        batch_op.alter_column("ip_hash", new_column_name="ip")
