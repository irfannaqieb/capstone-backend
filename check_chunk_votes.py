"""
Script to check which chunks have been voted on (completed sessions)
"""

from app.database import SessionLocal
from app.models import Chunk, Session, SessionStatus, Vote
from sqlalchemy import func


def check_chunk_votes():
    db = SessionLocal()

    try:
        print("\n" + "=" * 70)
        print("CHUNK VOTING STATUS")
        print("=" * 70)

        # Get all chunks with their session statistics
        chunk_stats = (
            db.query(
                Chunk.id,
                func.count(Session.id)
                .filter(Session.status == SessionStatus.completed)
                .label("completed_sessions"),
                func.count(Session.id)
                .filter(Session.status == SessionStatus.active)
                .label("active_sessions"),
                func.count(Session.id)
                .filter(Session.status == SessionStatus.abandoned)
                .label("abandoned_sessions"),
                func.count(Session.id).label("total_sessions"),
            )
            .outerjoin(Session, Session.chunk_id == Chunk.id)
            .group_by(Chunk.id)
            .order_by(Chunk.id)
            .all()
        )

        if not chunk_stats:
            print("\n❌ No chunks found in database!")
            print("Please run the migration to create chunks.")
            return

        # Separate chunks by voting status
        unvoted_chunks = []
        voted_chunks = []

        print(f"\nTotal chunks: {len(chunk_stats)}\n")

        for i, (chunk_id, completed, active, abandoned, total) in enumerate(
            chunk_stats, 1
        ):
            status_icon = "✓" if completed > 0 else "○"
            status_text = "VOTED" if completed > 0 else "UNVOTED"

            print(f"{status_icon} Chunk {i}:")
            print(f"   Status: {status_text}")
            print(f"   Completed sessions: {completed}")
            print(f"   Active sessions: {active}")
            print(f"   Abandoned sessions: {abandoned}")
            print(f"   Total sessions: {total}")

            if completed > 0:
                voted_chunks.append((i, chunk_id, completed))
            else:
                unvoted_chunks.append((i, chunk_id))

            print()

        # Summary
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"✓ Chunks with completed votes: {len(voted_chunks)}")
        print(f"○ Chunks without completed votes: {len(unvoted_chunks)}")

        if voted_chunks:
            print(f"\nVoted chunks:")
            for chunk_num, chunk_id, completed in voted_chunks:
                print(f"  - Chunk {chunk_num}: {completed} completed session(s)")

        if unvoted_chunks:
            print(f"\nUnvoted chunks (will be prioritized for new sessions):")
            for chunk_num, chunk_id in unvoted_chunks:
                print(f"  - Chunk {chunk_num}")

        # Get total votes across all chunks
        total_votes = db.query(func.count(Vote.id)).scalar()
        print(f"\nTotal votes cast across all sessions: {total_votes}")

        print("=" * 70 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    check_chunk_votes()
