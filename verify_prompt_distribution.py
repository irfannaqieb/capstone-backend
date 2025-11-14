"""
Verification script to ensure each prompt appears exactly once across all chunks
"""

from app.database import SessionLocal
from app.models import Prompt, ChunkPrompt, Chunk
from sqlalchemy import func


def verify_prompt_distribution():
    db = SessionLocal()

    try:
        print("\n" + "=" * 60)
        print("PROMPT DISTRIBUTION VERIFICATION")
        print("=" * 60)

        # 1. Get total prompts in database
        total_prompts_db = db.query(func.count(Prompt.id)).scalar()
        print(f"\n✓ Total prompts in database: {total_prompts_db}")

        # 2. Get total chunks
        total_chunks = db.query(func.count(Chunk.id)).scalar()
        print(f"✓ Total chunks: {total_chunks}")

        # 3. Check how many times each prompt appears in chunks
        prompt_counts = (
            db.query(ChunkPrompt.prompt_id, func.count(ChunkPrompt.id).label("count"))
            .group_by(ChunkPrompt.prompt_id)
            .all()
        )

        # 4. Find prompts that appear more than once (duplicates)
        duplicates = [(pid, count) for pid, count in prompt_counts if count > 1]

        # 5. Find prompts that appear exactly once
        unique_prompts = [(pid, count) for pid, count in prompt_counts if count == 1]

        # 6. Find prompts that don't appear at all
        prompts_in_chunks = {pid for pid, _ in prompt_counts}
        all_prompt_ids = {p.id for p in db.query(Prompt.id).all()}
        missing_prompts = all_prompt_ids - prompts_in_chunks

        print(f"\n--- ANALYSIS ---")
        print(f"Prompts appearing exactly once: {len(unique_prompts)}")
        print(f"Prompts appearing multiple times: {len(duplicates)}")
        print(f"Prompts not in any chunk: {len(missing_prompts)}")

        # 7. Show details if there are issues
        if duplicates:
            print(f"\n⚠️  WARNING: Found {len(duplicates)} duplicate prompts:")
            for prompt_id, count in duplicates[:5]:  # Show first 5
                print(f"   - Prompt '{prompt_id}' appears {count} times")
            if len(duplicates) > 5:
                print(f"   ... and {len(duplicates) - 5} more")

        if missing_prompts:
            print(f"\n⚠️  WARNING: Found {len(missing_prompts)} missing prompts:")
            for prompt_id in list(missing_prompts)[:5]:  # Show first 5
                print(f"   - Prompt '{prompt_id}' is not in any chunk")
            if len(missing_prompts) > 5:
                print(f"   ... and {len(missing_prompts) - 5} more")

        # 8. Show chunk distribution
        print(f"\n--- CHUNK DISTRIBUTION ---")
        chunk_sizes = (
            db.query(Chunk.id, func.count(ChunkPrompt.id).label("size"))
            .join(ChunkPrompt, ChunkPrompt.chunk_id == Chunk.id)
            .group_by(Chunk.id)
            .all()
        )

        for i, (chunk_id, size) in enumerate(chunk_sizes, 1):
            print(f"Chunk {i}: {size} prompts")

        # 9. Final verdict
        print(f"\n" + "=" * 60)
        if (
            len(unique_prompts) == total_prompts_db
            and len(duplicates) == 0
            and len(missing_prompts) == 0
        ):
            print("✅ VERIFICATION PASSED!")
            print("   All prompts appear exactly once across all chunks.")
        else:
            print("❌ VERIFICATION FAILED!")
            if duplicates:
                print(f"   - {len(duplicates)} prompts appear multiple times")
            if missing_prompts:
                print(f"   - {len(missing_prompts)} prompts are missing from chunks")
            if len(unique_prompts) != total_prompts_db:
                print(
                    f"   - Expected {total_prompts_db} unique prompts, found {len(unique_prompts)}"
                )
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    verify_prompt_distribution()
