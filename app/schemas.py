from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ---------- VOTES ----------
class VoteCreate(BaseModel):
    session_id: str
    pair_id: str
    winner_model: str
    left_model: str
    reaction_time_ms: Optional[int] = None


# ---------- SESSION ----------
class SessionCreateResponse(BaseModel):
    user_session_id: str
    chunk_id: Optional[str] = None  # For new chunked sessions


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    created_at: datetime
    last_activity: datetime
    completed_at: Optional[datetime] = None
    total_votes: int
    total_pairs: int
    chunk_id: Optional[str] = None  # For chunked sessions
    is_chunked: bool = False  # Indicates if this is a chunked session

    class Config:
        from_attributes = True


# ---------- PAIRS ----------
class ImageOut(BaseModel):
    image_id: str
    url: str
    model: str


class PairOut(BaseModel):
    done: bool
    pair_id: Optional[str] = None
    prompt_id: Optional[str] = None
    prompt_text: Optional[str] = None
    left: Optional[ImageOut] = None
    right: Optional[ImageOut] = None
    index: Optional[int] = None
    total: Optional[int] = None
    voting_options: Optional[list[str]] = None
    chunk_id: Optional[str] = None  # For chunked sessions
    is_chunked: bool = False  # Indicates if this is from a chunked session
