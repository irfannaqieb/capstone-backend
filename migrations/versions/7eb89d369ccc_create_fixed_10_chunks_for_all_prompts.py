"""create_fixed_10_chunks_for_all_prompts

Revision ID: 7eb89d369ccc
Revises: 5d6478fd533a
Create Date: 2025-11-14 17:13:03.402592

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
import random


# revision identifiers, used by Alembic.
revision: str = "7eb89d369ccc"
down_revision: Union[str, Sequence[str], None] = "5d6478fd533a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create 10 fixed chunks with all 300 prompts evenly distributed."""

    # Get database connection
    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        # Step 1: Clear existing chunk_prompts (must delete first due to FK)
        session.execute(text("DELETE FROM chunk_prompts"))

        # Step 2: Clear existing chunks
        session.execute(text("DELETE FROM chunks"))

        # Step 3: Fetch all prompt IDs
        result = session.execute(text("SELECT id FROM prompts ORDER BY id"))
        all_prompt_ids = [row[0] for row in result]

        total_prompts = len(all_prompt_ids)
        print(f"Found {total_prompts} prompts")

        if total_prompts == 0:
            print("WARNING: No prompts found in database. Skipping chunk creation.")
            return

        # Step 4: Shuffle the prompts randomly
        random.shuffle(all_prompt_ids)

        # Step 5: Create 10 chunks and distribute prompts
        num_chunks = 10
        chunk_size = 30

        for i in range(num_chunks):
            # Create chunk
            chunk_id = uuid.uuid4()
            session.execute(
                text("INSERT INTO chunks (id) VALUES (:chunk_id)"),
                {"chunk_id": chunk_id},
            )

            # Get prompts for this chunk
            start_idx = i * chunk_size
            end_idx = min(start_idx + chunk_size, total_prompts)
            chunk_prompt_ids = all_prompt_ids[start_idx:end_idx]

            # Insert chunk_prompts
            for prompt_id in chunk_prompt_ids:
                chunk_prompt_id = uuid.uuid4()
                session.execute(
                    text(
                        """
                        INSERT INTO chunk_prompts (id, chunk_id, prompt_id) 
                        VALUES (:id, :chunk_id, :prompt_id)
                    """
                    ),
                    {
                        "id": chunk_prompt_id,
                        "chunk_id": chunk_id,
                        "prompt_id": prompt_id,
                    },
                )

            print(f"Created chunk {i+1}/10 with {len(chunk_prompt_ids)} prompts")

        session.commit()
        print("Successfully created 10 fixed chunks!")

    except Exception as e:
        session.rollback()
        print(f"Error creating chunks: {e}")
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Remove the fixed chunks."""
    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        # Clear chunk_prompts first (FK constraint)
        session.execute(text("DELETE FROM chunk_prompts"))
        # Clear chunks
        session.execute(text("DELETE FROM chunks"))
        session.commit()
        print("Cleared all chunks and chunk_prompts")
    except Exception as e:
        session.rollback()
        print(f"Error in downgrade: {e}")
        raise
    finally:
        session.close()
