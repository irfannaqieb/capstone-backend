"""fix_cascade_delete_for_votes

Revision ID: 5c6c0112a5bc
Revises: 803efd3cedb9
Create Date: 2025-10-14 13:24:21.198825

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5c6c0112a5bc"
down_revision: Union[str, Sequence[str], None] = "803efd3cedb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop the existing foreign key constraint
    op.drop_constraint("votes_user_session_id_fkey", "votes", type_="foreignkey")

    # Add it back with ON DELETE CASCADE
    op.create_foreign_key(
        "votes_user_session_id_fkey",
        "votes",
        "sessions",
        ["user_session_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the cascade constraint
    op.drop_constraint("votes_user_session_id_fkey", "votes", type_="foreignkey")

    # Restore the original constraint without cascade
    op.create_foreign_key(
        "votes_user_session_id_fkey", "votes", "sessions", ["user_session_id"], ["id"]
    )
