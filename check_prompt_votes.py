"""
Script to check if all prompts have at least one vote
"""

from app.database import SessionLocal
from app.models import Prompt, Vote, Winner
from sqlalchemy import func


def check_prompt_votes():
    db = SessionLocal()

    try:
        print("\n" + "=" * 70)
        print("PROMPT VOTE COVERAGE CHECK")
        print("=" * 70)

        # Get total prompts
        total_prompts = db.query(func.count(Prompt.id)).scalar()
        print(f"\nTotal prompts in database: {total_prompts}")

        # Get prompts with their vote counts
        prompt_vote_counts = (
            db.query(Prompt.id, Prompt.text, func.count(Vote.id).label("vote_count"))
            .outerjoin(Vote, Vote.prompt_id == Prompt.id)
            .group_by(Prompt.id, Prompt.text)
            .order_by(func.count(Vote.id).asc(), Prompt.id)
            .all()
        )

        # Separate prompts by vote status
        prompts_with_votes = []
        prompts_without_votes = []

        for prompt_id, prompt_text, vote_count in prompt_vote_counts:
            if vote_count == 0:
                prompts_without_votes.append((prompt_id, prompt_text))
            else:
                prompts_with_votes.append((prompt_id, prompt_text, vote_count))

        # Calculate statistics
        total_votes = db.query(func.count(Vote.id)).scalar()
        avg_votes_per_prompt = total_votes / total_prompts if total_prompts > 0 else 0

        # Show summary
        print(f"Total votes cast: {total_votes}")
        print(f"Average votes per prompt: {avg_votes_per_prompt:.2f}")
        print(f"\n" + "-" * 70)

        print(f"\n✓ Prompts WITH at least 1 vote: {len(prompts_with_votes)}")
        print(f"○ Prompts WITHOUT any votes: {len(prompts_without_votes)}")

        # Show vote distribution
        if prompts_with_votes:
            vote_counts = [count for _, _, count in prompts_with_votes]
            min_votes = min(vote_counts)
            max_votes = max(vote_counts)
            print(f"\nVote distribution:")
            print(f"  - Minimum votes per prompt: {min_votes}")
            print(f"  - Maximum votes per prompt: {max_votes}")

        # Show prompts without votes (if any)
        if prompts_without_votes:
            print(
                f"\n⚠️  WARNING: {len(prompts_without_votes)} prompts have NO votes yet!"
            )
            print(f"\nUnvoted prompts (showing first 10):")
            for prompt_id, prompt_text in prompts_without_votes[:10]:
                # Truncate long prompts
                display_text = (
                    prompt_text[:60] + "..." if len(prompt_text) > 60 else prompt_text
                )
                print(f'  - {prompt_id}: "{display_text}"')

            if len(prompts_without_votes) > 10:
                print(f"  ... and {len(prompts_without_votes) - 10} more")

        # Show prompts with multiple votes (if any)
        prompts_with_multiple_votes = [
            (pid, txt, cnt) for pid, txt, cnt in prompts_with_votes if cnt > 1
        ]
        if prompts_with_multiple_votes:
            print(
                f"\n📊 {len(prompts_with_multiple_votes)} prompts have multiple votes:"
            )
            print(f"(showing top 10 by vote count)")
            for prompt_id, prompt_text, vote_count in sorted(
                prompts_with_multiple_votes, key=lambda x: x[2], reverse=True
            )[:10]:
                display_text = (
                    prompt_text[:50] + "..." if len(prompt_text) > 50 else prompt_text
                )
                print(f'  - {prompt_id} ({vote_count} votes): "{display_text}"')

        # Get winner distribution
        print(f"\n" + "-" * 70)
        print("WINNER MODEL DISTRIBUTION")
        print("-" * 70)

        winner_counts = (
            db.query(Vote.winner_model, func.count(Vote.id).label("count"))
            .group_by(Vote.winner_model)
            .order_by(func.count(Vote.id).desc())
            .all()
        )

        if winner_counts:
            for winner_model, count in winner_counts:
                percentage = (count / total_votes * 100) if total_votes > 0 else 0
                print(
                    f"  {winner_model.value:15} : {count:4} votes ({percentage:5.1f}%)"
                )
        else:
            print("  No votes cast yet.")

        # Final verdict
        print(f"\n" + "=" * 70)
        if len(prompts_without_votes) == 0:
            print("✅ ALL PROMPTS HAVE AT LEAST ONE VOTE!")
            print(f"   {total_prompts} prompts, {total_votes} total votes")
            coverage = (
                (len(prompts_with_votes) / total_prompts * 100)
                if total_prompts > 0
                else 0
            )
            print(f"   Coverage: {coverage:.1f}%")
        else:
            coverage = (
                (len(prompts_with_votes) / total_prompts * 100)
                if total_prompts > 0
                else 0
            )
            print(f"❌ NOT ALL PROMPTS VOTED YET")
            print(
                f"   Coverage: {len(prompts_with_votes)}/{total_prompts} ({coverage:.1f}%)"
            )
            print(f"   Remaining: {len(prompts_without_votes)} prompts need votes")
        print("=" * 70 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    check_prompt_votes()
