"""initial schema

Revision ID: 629d23245c09
Revises:
Create Date: 2025-10-09 00:18:02.969760

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "629d23245c09"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Create all tables."""
    # Create enums if they don't exist
    conn = op.get_bind()

    # Check and create modelname enum
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'modelname'"))
    if not result.fetchone():
        postgresql.ENUM("gpt5", "gemini25", name="modelname").create(conn)

    # Check and create winner enum
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'winner'"))
    if not result.fetchone():
        postgresql.ENUM("gpt5", "gemini25", "tie", name="winner").create(conn)

    # Create prompts table
    op.create_table(
        "prompts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create images table
    op.create_table(
        "images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", sa.String(), nullable=True),
        sa.Column(
            "model",
            postgresql.ENUM("gpt5", "gemini25", name="modelname", create_type=False),
            nullable=True,
        ),
        sa.Column("url", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prompt_id", "model", name="uq_images_prompt_model"),
    )

    # Create pairs table
    op.create_table(
        "pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", sa.String(), nullable=True),
        sa.Column("image_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("image_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["image_a_id"], ["images.id"]),
        sa.ForeignKeyConstraint(["image_b_id"], ["images.id"]),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prompt_id", name="uq_pairs_prompt"),
    )

    # Create sessions table
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create votes table
    op.create_table(
        "votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pair_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "winner_model",
            postgresql.ENUM("gpt5", "gemini25", "tie", name="winner", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "left_model",
            postgresql.ENUM("gpt5", "gemini25", name="modelname", create_type=False),
            nullable=False,
        ),
        sa.Column("reaction_time_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["pair_id"], ["pairs.id"]),
        sa.ForeignKeyConstraint(["user_session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_session_id", "pair_id", name="uq_votes_session_pair"),
    )


def downgrade() -> None:
    """Downgrade schema - Drop all tables."""
    op.drop_table("votes")
    op.drop_table("sessions")
    op.drop_table("pairs")
    op.drop_table("images")
    op.drop_table("prompts")

    # Drop enums
    postgresql.ENUM("gpt5", "gemini25", "tie", name="winner").drop(
        op.get_bind(), checkfirst=True
    )
    postgresql.ENUM("gpt5", "gemini25", name="modelname").drop(
        op.get_bind(), checkfirst=True
    )
