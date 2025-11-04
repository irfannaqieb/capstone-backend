"""remove_pairs_add_chunk_prompts_modify_votes

Revision ID: abae5aa694da
Revises: dbd30e4a87bf
Create Date: 2025-11-04 22:47:54.578828

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "abae5aa694da"
down_revision: Union[str, Sequence[str], None] = "dbd30e4a87bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Modify votes table first (remove dependencies on pairs)
    op.drop_constraint("uq_votes_session_pair", "votes", type_="unique")
    op.drop_constraint("votes_pair_id_fkey", "votes", type_="foreignkey")
    op.drop_column("votes", "pair_id")
    op.drop_column("votes", "left_model")

    # Add new columns to votes
    op.add_column("votes", sa.Column("prompt_id", sa.String(), nullable=True))

    # Add foreign key constraint
    op.create_foreign_key(None, "votes", "prompts", ["prompt_id"], ["id"])

    # Add new unique constraint
    op.create_unique_constraint(
        "uq_votes_session_prompt", "votes", ["user_session_id", "prompt_id"]
    )

    # Make prompt_id non-nullable (after it's added and populated if needed)
    op.alter_column("votes", "prompt_id", nullable=False)

    # Step 2: Now drop chunk_pairs table (depends on pairs)
    op.drop_table("chunk_pairs")

    # Step 3: Drop pairs table (no more dependencies)
    op.drop_table("pairs")

    # Step 4: Create chunk_prompts table
    op.create_table(
        "chunk_prompts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "chunk_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("prompt_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "chunk_id", "prompt_id", name="uq_chunk_prompts_chunk_prompt"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Reverse votes modifications
    op.drop_constraint("uq_votes_session_prompt", "votes", type_="unique")
    op.drop_constraint(None, "votes", type_="foreignkey")  # Drop FK to prompts
    op.alter_column("votes", "prompt_id", nullable=True)
    op.drop_column("votes", "prompt_id")

    # Add back old columns
    op.add_column(
        "votes",
        sa.Column(
            "left_model",
            sa.Enum(
                "gpt5",
                "gemini25",
                "flux1_dev",
                "flux1_krea",
                "kolors",
                name="modelname",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "votes",
        sa.Column("pair_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Add back old constraint
    op.create_foreign_key(None, "votes", "pairs", ["pair_id"], ["id"])
    op.create_unique_constraint(
        "uq_votes_session_pair", "votes", ["user_session_id", "pair_id"]
    )
    op.alter_column("votes", "pair_id", nullable=False)
    op.alter_column("votes", "left_model", nullable=False)

    # Drop chunk_prompts
    op.drop_table("chunk_prompts")

    # Recreate pairs table
    op.create_table(
        "pairs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prompt_id", sa.String(), nullable=True),
        sa.Column(
            "image_a_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "image_b_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"]),
        sa.ForeignKeyConstraint(["image_a_id"], ["images.id"]),
        sa.ForeignKeyConstraint(["image_b_id"], ["images.id"]),
        sa.UniqueConstraint("prompt_id", name="uq_pairs_prompt"),
    )

    # Recreate chunk_pairs table
    op.create_table(
        "chunk_pairs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "chunk_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("pair_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pair_id"], ["pairs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("chunk_id", "pair_id", name="uq_chunk_pairs_chunk_pair"),
    )
