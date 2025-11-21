from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models, schemas
from .database import SessionLocal, engine
from fastapi.middleware.cors import CORSMiddleware

import uuid
import random
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://*.up.railway.app",
        "https://capstone-frontend-rho.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_admin_token(x_admin_token: str = Header(...)):
    """Verify admin token from header"""
    admin_token = os.getenv("ADMIN_TOKEN")
    if not admin_token:
        raise HTTPException(
            status_code=500, detail="Admin token not configured on server"
        )
    if x_admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return True


def update_session_activity(session: models.Session, db: Session):
    """Update session activity and check for abandoned status"""
    now = datetime.now(timezone.utc)

    # Check if session should be marked as abandoned
    # (24+ hours since last activity, not completed)
    if session.status == models.SessionStatus.active:
        time_since_activity = now - session.last_activity.replace(tzinfo=timezone.utc)
        if time_since_activity > timedelta(hours=24):
            # Count votes to see if it's incomplete
            vote_count = (
                db.query(models.Vote)
                .filter(models.Vote.user_session_id == session.id)
                .count()
            )

            # Get total prompts in the session's chunk
            total_prompts = (
                db.query(models.ChunkPrompt)
                .filter(models.ChunkPrompt.chunk_id == session.chunk_id)
                .count()
            )

            if vote_count < total_prompts:
                session.status = models.SessionStatus.abandoned

    # Update last activity timestamp
    session.last_activity = now
    db.commit()


@app.get("/healthz")
def health():
    return {"ok": True}


def assign_chunk_to_session(db: Session) -> models.Chunk:
    """
    Assign a chunk to a new session with the following priority:
    1. Prioritize chunks with fewer completed sessions (goal: 10 per chunk)
    2. Among chunks below goal, select the one with minimum completed sessions
    3. If all chunks have >= 10 completed sessions, randomly assign any chunk
    """
    COMPLETION_GOAL = 10

    # Get all chunks with their completed session counts
    chunk_completion_query = (
        db.query(
            models.Chunk.id, func.count(models.Session.id).label("completed_count")
        )
        .outerjoin(
            models.Session,
            (models.Session.chunk_id == models.Chunk.id)
            & (models.Session.status == models.SessionStatus.completed),
        )
        .group_by(models.Chunk.id)
        .all()
    )

    if not chunk_completion_query:
        raise HTTPException(
            status_code=500,
            detail="No chunks available. Please run migrations to create chunks.",
        )

    # Separate chunks by completion status relative to goal
    chunks_below_goal = [
        (chunk_id, count)
        for chunk_id, count in chunk_completion_query
        if count < COMPLETION_GOAL
    ]

    # Choose chunk based on priority
    if chunks_below_goal:
        # Find the minimum completed count among chunks below goal
        min_completed = min(count for _, count in chunks_below_goal)

        # Get all chunks with this minimum count
        chunks_with_min = [
            chunk_id for chunk_id, count in chunks_below_goal if count == min_completed
        ]

        # Randomly select one of the chunks with minimum completed sessions
        selected_chunk_id = random.choice(chunks_with_min)
        print(
            f"Assigned chunk with min completed sessions (goal: {COMPLETION_GOAL}): chunk_id={selected_chunk_id}, completed={min_completed}"
        )
    else:
        # Fallback: all chunks have >= COMPLETION_GOAL completions, pick randomly
        all_chunk_ids = [chunk_id for chunk_id, _ in chunk_completion_query]
        selected_chunk_id = random.choice(all_chunk_ids)
        print(
            f"All chunks met goal ({COMPLETION_GOAL}+), randomly assigned chunk: {selected_chunk_id}"
        )

    # Fetch and return the selected chunk
    chunk = db.query(models.Chunk).filter(models.Chunk.id == selected_chunk_id).first()
    return chunk


@app.post("/session/start", response_model=schemas.SessionCreateResponse)
def start_session(db: Session = Depends(get_db)):
    sid = uuid.uuid4()

    # Assign a chunk to this session (prioritize unvoted chunks)
    chunk = assign_chunk_to_session(db)

    # Create session with chunk assignment
    new_session = models.Session(
        id=sid, status=models.SessionStatus.active, chunk_id=chunk.id
    )
    db.add(new_session)
    db.commit()

    return schemas.SessionCreateResponse(
        user_session_id=str(sid), chunk_id=str(chunk.id)
    )


@app.get("/prompts/next", response_model=schemas.PromptOut)
def next_prompt(session_id: str, db: Session = Depends(get_db)):
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid session_id UUID format: {e}"
        )

    # Validate session exists
    session = db.query(models.Session).filter(models.Session.id == session_uuid).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Update activity and check for abandoned status
    update_session_activity(session, db)

    # Validate chunk exists
    if not session.chunk_id:
        raise HTTPException(status_code=500, detail="Session has no chunk assigned")

    # Get prompt IDs in this session's chunk
    chunk_prompt_ids = (
        db.query(models.ChunkPrompt.prompt_id)
        .filter(models.ChunkPrompt.chunk_id == session.chunk_id)
        .subquery()
    )

    # Get voted prompt IDs in this session
    voted_prompt_ids = (
        db.query(models.Vote.prompt_id)
        .filter(models.Vote.user_session_id == session_uuid)
        .subquery()
    )

    # Get unvoted prompts within the chunk
    unvoted_prompts = (
        db.query(models.Prompt)
        .filter(models.Prompt.id.in_(chunk_prompt_ids))
        .filter(~models.Prompt.id.in_(voted_prompt_ids))
        .all()
    )

    # Get total prompts in chunk for progress tracking
    total_prompts_in_chunk = (
        db.query(models.ChunkPrompt)
        .filter(models.ChunkPrompt.chunk_id == session.chunk_id)
        .count()
    )

    prompts_completed = total_prompts_in_chunk - len(unvoted_prompts)

    if not unvoted_prompts:
        # Mark session as completed when all prompts are voted
        if session.status == models.SessionStatus.active:
            session.status = models.SessionStatus.completed
            session.completed_at = datetime.now(timezone.utc)
            db.commit()

        # Return done:true when no more prompts to vote on
        return schemas.PromptOut(
            done=True,
            total=total_prompts_in_chunk,
            index=prompts_completed,
            chunk_id=str(session.chunk_id),
        )

    # Pick a random unvoted prompt
    prompt = random.choice(unvoted_prompts)

    # Get all images for this prompt (should be 5)
    # Using eager loading would be better, but since we filter by prompt_id, this is already efficient
    images = db.query(models.Image).filter(models.Image.prompt_id == prompt.id).all()

    if len(images) != 5:
        raise HTTPException(
            status_code=500,
            detail=f"Prompt {prompt.id} has {len(images)} images, expected 5",
        )

    # Randomize image order to avoid position bias
    random.shuffle(images)

    # Convert to schema
    image_outs = [
        schemas.ImageOut(
            image_id=str(img.id),
            url=img.url,
            model=img.model.value,
        )
        for img in images
    ]

    return schemas.PromptOut(
        done=False,
        prompt_id=prompt.id,
        prompt_text=prompt.text,
        images=image_outs,
        total=total_prompts_in_chunk,
        index=prompts_completed + 1,  # Current prompt index (1-based)
        chunk_id=str(session.chunk_id),
    )


@app.post("/votes")
def cast_vote(vote: schemas.VoteCreate, db: Session = Depends(get_db)):
    # Convert string UUID to UUID object
    try:
        session_uuid = uuid.UUID(vote.session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid UUID format: {e}")

    # Validate session exists and update activity
    session = db.query(models.Session).filter(models.Session.id == session_uuid).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    update_session_activity(session, db)

    # Convert string enum to SQLAlchemy enum by value
    try:
        winner_enum = models.Winner(vote.winner_model)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid winner_model enum value: {e}"
        )

    # Validate prompt exists
    prompt = db.query(models.Prompt).filter(models.Prompt.id == vote.prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Check if vote already exists (UPSERT logic)
    existing_vote = (
        db.query(models.Vote)
        .filter(
            models.Vote.user_session_id == session_uuid,
            models.Vote.prompt_id == vote.prompt_id,
        )
        .first()
    )

    if existing_vote:
        # Update existing vote
        existing_vote.winner_model = winner_enum
        existing_vote.reaction_time_ms = vote.reaction_time_ms
        existing_vote.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": True, "updated": True}
    else:
        # Create new vote
        db_vote = models.Vote(
            user_session_id=session_uuid,
            prompt_id=vote.prompt_id,
            winner_model=winner_enum,
            reaction_time_ms=vote.reaction_time_ms,
        )
        db.add(db_vote)
        db.commit()
        return {"ok": True, "updated": False}


@app.get("/session/{session_id}/status", response_model=schemas.SessionStatusResponse)
def get_session_status(session_id: str, db: Session = Depends(get_db)):
    """Get detailed status information about a session"""
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid session_id UUID format: {e}"
        )

    # Get session
    session = db.query(models.Session).filter(models.Session.id == session_uuid).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Update activity and check for abandoned status
    update_session_activity(session, db)

    # Get vote count
    vote_count = (
        db.query(models.Vote)
        .filter(models.Vote.user_session_id == session_uuid)
        .count()
    )

    # Get total prompts in the session's chunk
    total_prompts = (
        db.query(models.ChunkPrompt)
        .filter(models.ChunkPrompt.chunk_id == session.chunk_id)
        .count()
    )

    return schemas.SessionStatusResponse(
        session_id=str(session.id),
        status=session.status.value,
        created_at=session.created_at,
        last_activity=session.last_activity,
        completed_at=session.completed_at,
        total_votes=vote_count,
        total_prompts=total_prompts,
        chunk_id=str(session.chunk_id),
    )


@app.get("/admin/summary", response_model=schemas.AdminSummaryResponse)
def get_admin_summary(
    db: Session = Depends(get_db), _admin: bool = Depends(verify_admin_token)
):
    """
    Admin-only endpoint to get voting analytics summary.
    Requires X-Admin-Token header.
    """

    # 1. Get chunk statistics (completed sessions and total votes per chunk)
    chunk_stats_query = (
        db.query(
            models.Chunk.id.label("chunk_id"),
            func.count(
                func.distinct(
                    func.case(
                        (
                            models.Session.status == models.SessionStatus.completed,
                            models.Session.id,
                        ),
                        else_=None,
                    )
                )
            ).label("completed_sessions"),
            func.count(models.Vote.id).label("total_votes"),
        )
        .outerjoin(models.Session, models.Session.chunk_id == models.Chunk.id)
        .outerjoin(models.Vote, models.Vote.user_session_id == models.Session.id)
        .group_by(models.Chunk.id)
        .all()
    )

    chunk_stats = [
        schemas.ChunkStats(
            chunk_id=str(row.chunk_id),
            completed_sessions=row.completed_sessions,
            total_votes=row.total_votes,
            meets_goal=row.completed_sessions >= 10,
        )
        for row in chunk_stats_query
    ]

    # 2. Get image statistics (vote count per image)
    image_stats_query = (
        db.query(
            models.Image.id.label("image_id"),
            models.Image.model.label("model"),
            models.Image.prompt_id.label("prompt_id"),
            func.count(models.Vote.id).label("vote_count"),
        )
        .outerjoin(models.Vote, models.Vote.prompt_id == models.Image.prompt_id)
        .group_by(models.Image.id, models.Image.model, models.Image.prompt_id)
        .all()
    )

    image_stats = [
        schemas.ImageStats(
            image_id=str(row.image_id),
            model=row.model.value,
            prompt_id=row.prompt_id,
            vote_count=row.vote_count,
        )
        for row in image_stats_query
    ]

    # 3. Get session status counts
    session_counts_query = (
        db.query(models.Session.status, func.count(models.Session.id).label("count"))
        .group_by(models.Session.status)
        .all()
    )

    session_counts_dict = {row.status.value: row.count for row in session_counts_query}

    session_status_counts = schemas.SessionStatusCounts(
        active=session_counts_dict.get("active", 0),
        completed=session_counts_dict.get("completed", 0),
        abandoned=session_counts_dict.get("abandoned", 0),
        total=sum(session_counts_dict.values()),
    )

    return schemas.AdminSummaryResponse(
        chunks=chunk_stats, images=image_stats, sessions=session_status_counts
    )


@app.get("/results", response_model=schemas.ResultsResponse)
def get_results(db: Session = Depends(get_db)):
    """
    Public endpoint returning global aggregate voting results.

    Aggregates all votes to compute how often each model wins,
    excluding ties from the percentage denominator.
    """

    # Total votes (including ties)
    total_votes = db.query(func.count(models.Vote.id)).scalar() or 0

    # Tie votes
    tie_votes = (
        db.query(func.count(models.Vote.id))
        .filter(models.Vote.winner_model == models.Winner.tie)
        .scalar()
        or 0
    )

    # Wins per model (excluding ties)
    win_counts_query = (
        db.query(
            models.Vote.winner_model,
            func.count(models.Vote.id).label("count"),
        )
        .filter(models.Vote.winner_model != models.Winner.tie)
        .group_by(models.Vote.winner_model)
        .all()
    )

    win_counts = {row.winner_model.value: row.count for row in win_counts_query}

    total_decisive_votes = sum(win_counts.values())

    model_results: list[schemas.ModelResult] = []

    for winner in models.Winner:
        if winner == models.Winner.tie:
            continue

        model_id = winner.value
        wins = win_counts.get(model_id, 0)

        if total_decisive_votes > 0:
            win_percentage = wins / total_decisive_votes * 100
        else:
            win_percentage = 0.0

        display_name = models.MODEL_DISPLAY.get(model_id, model_id)

        model_results.append(
            schemas.ModelResult(
                model_id=model_id,
                display_name=display_name,
                wins=wins,
                win_percentage=win_percentage,
            )
        )

    return schemas.ResultsResponse(
        total_votes=total_votes,
        total_decisive_votes=total_decisive_votes,
        tie_votes=tie_votes,
        models=model_results,
    )


@app.get("/results/prompts", response_model=schemas.PromptResultsResponse)
def get_prompt_results(db: Session = Depends(get_db)):
    """
    Public endpoint returning per-prompt voting results.
    
    For each prompt, returns:
    - Prompt text and ID
    - All 5 images (one per model)
    - Vote counts and percentages per model
    - Total votes and tie votes
    - Winning model and winning image ID
    """
    
    # Get all prompts
    all_prompts = db.query(models.Prompt).order_by(models.Prompt.id).all()
    
    # Get all images and group by prompt_id
    all_images = db.query(models.Image).all()
    images_by_prompt: dict[str, list[models.Image]] = {}
    for image in all_images:
        if image.prompt_id not in images_by_prompt:
            images_by_prompt[image.prompt_id] = []
        images_by_prompt[image.prompt_id].append(image)
    
    # Get vote counts per prompt and per model
    vote_counts_query = (
        db.query(
            models.Vote.prompt_id,
            models.Vote.winner_model,
            func.count(models.Vote.id).label("count"),
        )
        .group_by(models.Vote.prompt_id, models.Vote.winner_model)
        .all()
    )
    
    # Build vote data structure: prompt_id -> {winner_model: count}
    votes_by_prompt: dict[str, dict[str, int]] = {}
    for prompt_id, winner_model, count in vote_counts_query:
        if prompt_id not in votes_by_prompt:
            votes_by_prompt[prompt_id] = {}
        votes_by_prompt[prompt_id][winner_model.value] = count
    
    # Build results for each prompt
    prompt_results: list[schemas.PromptResult] = []
    
    for prompt in all_prompts:
        prompt_id = prompt.id
        
        # Get images for this prompt
        prompt_images = images_by_prompt.get(prompt_id, [])
        image_outs = [
            schemas.ImageOut(
                image_id=str(img.id),
                url=img.url,
                model=img.model.value,
            )
            for img in prompt_images
        ]
        
        # Get vote data for this prompt
        prompt_votes = votes_by_prompt.get(prompt_id, {})
        total_votes = sum(prompt_votes.values())
        tie_votes = prompt_votes.get(models.Winner.tie.value, 0)
        
        # Calculate wins per model (excluding ties)
        model_wins: dict[str, int] = {}
        for winner in models.Winner:
            if winner != models.Winner.tie:
                model_id = winner.value
                model_wins[model_id] = prompt_votes.get(model_id, 0)
        
        total_decisive_votes = sum(model_wins.values())
        
        # Build ModelResult list for this prompt
        model_results: list[schemas.ModelResult] = []
        for winner in models.Winner:
            if winner == models.Winner.tie:
                continue
            
            model_id = winner.value
            wins = model_wins.get(model_id, 0)
            
            if total_decisive_votes > 0:
                win_percentage = wins / total_decisive_votes * 100
            else:
                win_percentage = 0.0
            
            display_name = models.MODEL_DISPLAY.get(model_id, model_id)
            
            model_results.append(
                schemas.ModelResult(
                    model_id=model_id,
                    display_name=display_name,
                    wins=wins,
                    win_percentage=win_percentage,
                )
            )
        
        # Determine winning model (non-tie model with highest wins)
        winning_model_id: Optional[str] = None
        winning_image_id: Optional[str] = None
        
        if total_decisive_votes > 0 and len(model_wins) > 0:
            # Find model with maximum wins
            max_wins = max(model_wins.values())
            winning_models = [
                model_id for model_id, wins in model_wins.items() if wins == max_wins
            ]
            
            # If there's a clear winner (not a tie), use it
            if len(winning_models) == 1:
                winning_model_id = winning_models[0]
                
                # Find the corresponding image for the winning model
                for img in prompt_images:
                    if img.model.value == winning_model_id:
                        winning_image_id = str(img.id)
                        break
        
        prompt_results.append(
            schemas.PromptResult(
                prompt_id=prompt_id,
                prompt_text=prompt.text,
                images=image_outs,
                total_votes=total_votes,
                tie_votes=tie_votes,
                models=model_results,
                winning_model_id=winning_model_id,
                winning_image_id=winning_image_id,
            )
        )
    
    return schemas.PromptResultsResponse(prompts=prompt_results)
