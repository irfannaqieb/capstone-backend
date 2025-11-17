"""
Script to check detailed vote breakdown for each prompt
"""

from app.database import SessionLocal
from app.models import Prompt, Vote, Winner
from sqlalchemy import func


def check_detailed_prompt_votes():
    db = SessionLocal()

    try:
        print("\n" + "=" * 80)
        print("DETAILED PROMPT VOTE BREAKDOWN")
        print("=" * 80)

        # Get total prompts and votes
        total_prompts = db.query(func.count(Prompt.id)).scalar()
        total_votes = db.query(func.count(Vote.id)).scalar()

        print(f"\nTotal prompts: {total_prompts}")
        print(f"Total votes: {total_votes}\n")

        # Get all prompts with their votes
        prompts = db.query(Prompt).order_by(Prompt.id).all()

        prompts_with_votes = 0
        prompts_without_votes = 0

        for prompt in prompts:
            # Get vote counts per model for this prompt
            vote_counts = (
                db.query(Vote.winner_model, func.count(Vote.id).label("count"))
                .filter(Vote.prompt_id == prompt.id)
                .group_by(Vote.winner_model)
                .all()
            )

            total_votes_for_prompt = sum(count for _, count in vote_counts)

            if total_votes_for_prompt > 0:
                prompts_with_votes += 1
            else:
                prompts_without_votes += 1

            # Display prompt info
            prompt_display = (
                prompt.text[:70] + "..." if len(prompt.text) > 70 else prompt.text
            )
            status = "✓" if total_votes_for_prompt > 0 else "○"

            print(f"{status} Prompt: {prompt.id}")
            print(f'   Text: "{prompt_display}"')
            print(f"   Total votes: {total_votes_for_prompt}")

            if vote_counts:
                print(f"   Vote breakdown:")
                # Sort by count descending
                sorted_votes = sorted(vote_counts, key=lambda x: x[1], reverse=True)
                for winner_model, count in sorted_votes:
                    percentage = (
                        (count / total_votes_for_prompt * 100)
                        if total_votes_for_prompt > 0
                        else 0
                    )
                    print(
                        f"      - {winner_model.value:12} : {count:2} vote(s) ({percentage:5.1f}%)"
                    )
            else:
                print(f"   Vote breakdown: No votes yet")

            print()

        # Summary
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"✓ Prompts with votes: {prompts_with_votes}")
        print(f"○ Prompts without votes: {prompts_without_votes}")

        if prompts_without_votes == 0:
            print("\n✅ ALL PROMPTS HAVE AT LEAST ONE VOTE!")
        else:
            coverage = (
                (prompts_with_votes / total_prompts * 100) if total_prompts > 0 else 0
            )
            print(
                f"\n❌ Coverage: {prompts_with_votes}/{total_prompts} ({coverage:.1f}%)"
            )

        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    check_detailed_prompt_votes()
