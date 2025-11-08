from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models, schemas
from .database import SessionLocal, engine
from fastapi.middleware.cors import CORSMiddleware

import uuid
import random
from datetime import datetime, timedelta, timezone

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


def create_random_chunk(db: Session, chunk_size: int = 30):
    """Create a new chunk with randomly selected prompts"""

    # Get total count first
    total_count = db.query(func.count(models.Prompt.id)).scalar()

    if total_count <= chunk_size:
        # If we have fewer prompts than chunk size, use all available prompts
        selected_prompt_ids = [p.id for p in db.query(models.Prompt.id).all()]
    else:
        selected_prompts = (
            db.query(models.Prompt.id).order_by(func.random()).limit(chunk_size).all()
        )
        selected_prompt_ids = [p.id for p in selected_prompts]

    # Create new chunk
    new_chunk = models.Chunk()
    db.add(new_chunk)
    db.flush()  # Get the chunk ID

    # Add prompts to chunk in bulk
    chunk_prompts = [
        models.ChunkPrompt(chunk_id=new_chunk.id, prompt_id=prompt_id)
        for prompt_id in selected_prompt_ids
    ]
    db.add_all(chunk_prompts)

    db.commit()
    return new_chunk


@app.post("/session/start", response_model=schemas.SessionCreateResponse)
def start_session(db: Session = Depends(get_db)):
    sid = uuid.uuid4()

    # Create a random chunk for this session
    chunk = create_random_chunk(db)

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

    # Create vote object
    db_vote = models.Vote(
        user_session_id=session_uuid,
        prompt_id=vote.prompt_id,
        winner_model=winner_enum,
        reaction_time_ms=vote.reaction_time_ms,
    )

    # Handle unique constraint violation gracefully
    try:
        db.add(db_vote)
        db.commit()
        return {"ok": True}
    except Exception as e:
        db.rollback()
        # Check if it's a unique constraint violation
        if "unique constraint" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail="Vote already exists for this session and prompt",
            )
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


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
