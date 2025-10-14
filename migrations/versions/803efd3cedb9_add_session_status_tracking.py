"""add_session_status_tracking

Revision ID: 803efd3cedb9
Revises: 119a64d00552
Create Date: 2025-10-13 23:28:17.501644

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "803efd3cedb9"
down_revision: Union[str, Sequence[str], None] = "119a64d00552"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the SessionStatus enum type first
    sessionstatus_enum = sa.Enum(
        "active", "completed", "abandoned", name="sessionstatus"
    )
    sessionstatus_enum.create(op.get_bind(), checkfirst=True)

    # Add new columns
    op.add_column(
        "sessions",
        sa.Column(
            "last_activity",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.add_column(
        "sessions", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "sessions",
        sa.Column(
            "status", sessionstatus_enum, server_default="active", nullable=False
        ),
    )

    # Update existing sessions to have last_activity = created_at
    op.execute(
        "UPDATE sessions SET last_activity = created_at WHERE last_activity IS NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop columns
    op.drop_column("sessions", "status")
    op.drop_column("sessions", "completed_at")
    op.drop_column("sessions", "last_activity")

    # Drop the enum type
    sa.Enum(name="sessionstatus").drop(op.get_bind(), checkfirst=True)
