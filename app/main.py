from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
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

            # Check if this is a chunked session
            if session.chunk_id is not None:
                # Get total pairs in the session's chunk
                total_pairs = (
                    db.query(models.ChunkPair)
                    .filter(models.ChunkPair.chunk_id == session.chunk_id)
                    .count()
                )
            else:
                # Legacy system - get all pairs
                total_pairs = db.query(models.Pair).count()

            if vote_count < total_pairs:
                session.status = models.SessionStatus.abandoned

    # Update last activity timestamp
    session.last_activity = now
    db.commit()


@app.get("/healthz")
def health():
    return {"ok": True}


def create_random_chunk(db: Session, chunk_size: int = 30):
    """Create a new chunk with randomly selected pairs"""
    # Get all available pairs
    all_pairs = db.query(models.Pair).all()

    if len(all_pairs) < chunk_size:
        # If we have fewer pairs than chunk size, use all available pairs
        selected_pairs = all_pairs
    else:
        # Randomly select chunk_size pairs
        selected_pairs = random.sample(all_pairs, chunk_size)

    # Create new chunk
    new_chunk = models.Chunk()
    db.add(new_chunk)
    db.flush()  # Get the chunk ID

    # Add pairs to chunk
    for pair in selected_pairs:
        chunk_pair = models.ChunkPair(chunk_id=new_chunk.id, pair_id=pair.id)
        db.add(chunk_pair)

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


@app.get("/pairs/next", response_model=schemas.PairOut)
def next_pair(session_id: str, db: Session = Depends(get_db)):
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

    # Check if this is a chunked session (new system) or legacy session
    is_chunked = session.chunk_id is not None

    if is_chunked:
        # NEW CHUNKED SYSTEM
        # Get pairs in this session's chunk
        chunk_pair_ids = (
            db.query(models.ChunkPair.pair_id)
            .filter(models.ChunkPair.chunk_id == session.chunk_id)
            .subquery()
        )

        # Get voted pairs in this chunk
        voted_subquery = (
            db.query(models.Vote.pair_id)
            .filter(models.Vote.user_session_id == session_uuid)
            .subquery()
        )

        # Get unvoted pairs within the chunk
        unvoted_pairs = (
            db.query(models.Pair)
            .filter(models.Pair.id.in_(chunk_pair_ids))
            .filter(~models.Pair.id.in_(voted_subquery))
            .all()
        )

        # Get total pairs in chunk for progress tracking
        total_pairs_in_chunk = (
            db.query(models.ChunkPair)
            .filter(models.ChunkPair.chunk_id == session.chunk_id)
            .count()
        )

        pairs_remaining = len(unvoted_pairs)
        pairs_completed = total_pairs_in_chunk - pairs_remaining

    else:
        # LEGACY SYSTEM (backward compatibility)
        # Get next unvoted pair with a DB query (efficient subquery)
        voted_subquery = (
            db.query(models.Vote.pair_id)
            .filter(models.Vote.user_session_id == session_uuid)
            .subquery()
        )

        unvoted_pairs = (
            db.query(models.Pair).filter(~models.Pair.id.in_(voted_subquery)).all()
        )

        # Get total pairs count for progress tracking
        total_pairs_in_chunk = db.query(models.Pair).count()
        pairs_remaining = len(unvoted_pairs)
        pairs_completed = total_pairs_in_chunk - pairs_remaining

    if not unvoted_pairs:
        # Mark session as completed when all pairs are voted
        if session.status == models.SessionStatus.active:
            session.status = models.SessionStatus.completed
            session.completed_at = datetime.now(timezone.utc)
            db.commit()

        # Return done:true when no more pairs to vote on
        return schemas.PairOut(
            done=True,
            total=total_pairs_in_chunk,
            index=pairs_completed,
            chunk_id=str(session.chunk_id) if is_chunked else None,
            is_chunked=is_chunked,
        )

    # Pick a random unvoted pair
    pair = random.choice(unvoted_pairs)

    # Get the prompt text
    prompt = db.query(models.Prompt).filter(models.Prompt.id == pair.prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=500, detail="Prompt not found for pair")

    # Get images for the pair
    image_a = db.query(models.Image).filter(models.Image.id == pair.image_a_id).first()
    image_b = db.query(models.Image).filter(models.Image.id == pair.image_b_id).first()

    if not image_a or not image_b:
        raise HTTPException(status_code=500, detail="Pair images not found")

    # Randomize left/right positioning to avoid position bias
    if random.choice([True, False]):
        left_image, right_image = image_a, image_b
    else:
        left_image, right_image = image_b, image_a

    return schemas.PairOut(
        done=False,
        pair_id=str(pair.id),
        prompt_id=pair.prompt_id,
        prompt_text=prompt.text,
        left=schemas.ImageOut(
            image_id=str(left_image.id),
            url=left_image.url,
            model=left_image.model.value,
        ),
        right=schemas.ImageOut(
            image_id=str(right_image.id),
            url=right_image.url,
            model=right_image.model.value,
        ),
        total=total_pairs_in_chunk,
        index=pairs_completed + 1,  # Current pair index (1-based)
        voting_options=["left", "right", "tie"],
        chunk_id=str(session.chunk_id) if is_chunked else None,
        is_chunked=is_chunked,
    )


@app.post("/votes")
def cast_vote(vote: schemas.VoteCreate, db: Session = Depends(get_db)):
    # Convert string UUIDs to UUID objects
    try:
        session_uuid = uuid.UUID(vote.session_id)
        pair_uuid = uuid.UUID(vote.pair_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid UUID format: {e}")

    # Validate session exists and update activity
    session = db.query(models.Session).filter(models.Session.id == session_uuid).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    update_session_activity(session, db)

    # Convert string enums to SQLAlchemy enums by value (not name)
    try:
        winner_enum = models.Winner(vote.winner_model)
        left_model_enum = models.ModelName(vote.left_model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid enum value: {e}")

    # Create vote object
    db_vote = models.Vote(
        user_session_id=session_uuid,
        pair_id=pair_uuid,
        winner_model=winner_enum,
        left_model=left_model_enum,
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
                status_code=409, detail="Vote already exists for this session and pair"
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

    # Check if this is a chunked session
    is_chunked = session.chunk_id is not None

    if is_chunked:
        # Get total pairs in the session's chunk
        total_pairs = (
            db.query(models.ChunkPair)
            .filter(models.ChunkPair.chunk_id == session.chunk_id)
            .count()
        )
    else:
        # Legacy system - get all pairs
        total_pairs = db.query(models.Pair).count()

    return schemas.SessionStatusResponse(
        session_id=str(session.id),
        status=session.status.value,
        created_at=session.created_at,
        last_activity=session.last_activity,
        completed_at=session.completed_at,
        total_votes=vote_count,
        total_pairs=total_pairs,
        chunk_id=str(session.chunk_id) if is_chunked else None,
        is_chunked=is_chunked,
    )
