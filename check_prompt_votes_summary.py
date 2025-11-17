"""
Script to check vote breakdown - shows only prompts with votes (summary view)
"""

from app.database import SessionLocal
from app.models import Prompt, Vote, Winner
from sqlalchemy import func


def check_prompt_votes_summary(show_all=False, limit=50):
    db = SessionLocal()

    try:
        print("\n" + "=" * 80)
        print("PROMPT VOTE BREAKDOWN SUMMARY")
        print("=" * 80)

        # Get total prompts and votes
        total_prompts = db.query(func.count(Prompt.id)).scalar()
        total_votes = db.query(func.count(Vote.id)).scalar()

        print(f"\nTotal prompts: {total_prompts}")
        print(f"Total votes: {total_votes}\n")

        # Get all prompts with their votes
        prompts_with_vote_counts = (
            db.query(Prompt.id, Prompt.text, func.count(Vote.id).label("vote_count"))
            .outerjoin(Vote, Vote.prompt_id == Prompt.id)
            .group_by(Prompt.id, Prompt.text)
            .order_by(func.count(Vote.id).desc(), Prompt.id)
            .all()
        )

        prompts_with_votes = 0
        prompts_without_votes = 0
        prompts_displayed = 0

        print("-" * 80)
        print(f"PROMPTS WITH VOTES (showing {'all' if show_all else f'top {limit}'})")
        print("-" * 80 + "\n")

        for prompt_id, prompt_text, total_prompt_votes in prompts_with_vote_counts:
            if total_prompt_votes > 0:
                prompts_with_votes += 1

                # Only display if show_all or within limit
                if show_all or prompts_displayed < limit:
                    # Get vote counts per model for this prompt
                    vote_counts = (
                        db.query(Vote.winner_model, func.count(Vote.id).label("count"))
                        .filter(Vote.prompt_id == prompt_id)
                        .group_by(Vote.winner_model)
                        .all()
                    )

                    # Display prompt info
                    prompt_display = (
                        prompt_text[:65] + "..."
                        if len(prompt_text) > 65
                        else prompt_text
                    )

                    print(f"✓ Prompt: {prompt_id}")
                    print(f'   Text: "{prompt_display}"')
                    print(f"   Total: {total_prompt_votes} vote(s)")

                    if total_prompt_votes > 1:
                        print(f"   Breakdown:")
                        # Sort by count descending
                        sorted_votes = sorted(
                            vote_counts, key=lambda x: x[1], reverse=True
                        )
                        for winner_model, count in sorted_votes:
                            percentage = count / total_prompt_votes * 100
                            print(
                                f"      • {winner_model.value:12} : {count:2} vote(s) ({percentage:5.1f}%)"
                            )
                    else:
                        # Single vote - show winner directly
                        winner_model = vote_counts[0][0]
                        print(f"   Winner: {winner_model.value}")

                    print()
                    prompts_displayed += 1
            else:
                prompts_without_votes += 1

        if prompts_with_votes > prompts_displayed:
            print(
                f"... and {prompts_with_votes - prompts_displayed} more prompts with votes\n"
            )

        # Show prompts without votes
        if prompts_without_votes > 0:
            print("-" * 80)
            print(f"PROMPTS WITHOUT VOTES (showing first 20)")
            print("-" * 80 + "\n")

            unvoted_count = 0
            for prompt_id, prompt_text, total_prompt_votes in prompts_with_vote_counts:
                if total_prompt_votes == 0 and unvoted_count < 20:
                    prompt_display = (
                        prompt_text[:65] + "..."
                        if len(prompt_text) > 65
                        else prompt_text
                    )
                    print(f'○ {prompt_id}: "{prompt_display}"')
                    unvoted_count += 1

            if prompts_without_votes > 20:
                print(f"\n... and {prompts_without_votes - 20} more unvoted prompts")
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
            print(f"   Remaining: {prompts_without_votes} prompts need votes")

        # Overall winner distribution
        print("\n" + "-" * 80)
        print("OVERALL WINNER DISTRIBUTION")
        print("-" * 80)

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
                    f"  {winner_model.value:15} : {count:4} vote(s) ({percentage:5.1f}%)"
                )
        else:
            print("  No votes cast yet.")

        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import sys

    # Check if user wants to see all prompts
    show_all = "--all" in sys.argv
    check_prompt_votes_summary(show_all=show_all)
