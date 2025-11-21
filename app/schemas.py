from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ---------- VOTES ----------
class VoteCreate(BaseModel):
    session_id: str
    prompt_id: str
    winner_model: str
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
    total_prompts: int
    chunk_id: Optional[str] = None

    class Config:
        from_attributes = True


# ---------- PROMPTS ----------
class ImageOut(BaseModel):
    image_id: str
    url: str
    model: str


class PromptOut(BaseModel):
    done: bool
    prompt_id: Optional[str] = None
    prompt_text: Optional[str] = None
    images: Optional[list[ImageOut]] = None  # All 5 images
    index: Optional[int] = None  # Current progress (e.g., 15/30)
    total: Optional[int] = None  # Total prompts in chunk (30)
    chunk_id: Optional[str] = None


# ---------- ADMIN ----------
class ChunkStats(BaseModel):
    chunk_id: str
    completed_sessions: int
    total_votes: int
    meets_goal: bool  # True if completed_sessions >= 10

    class Config:
        from_attributes = True


class ImageStats(BaseModel):
    image_id: str
    model: str
    prompt_id: str
    vote_count: int

    class Config:
        from_attributes = True


class SessionStatusCounts(BaseModel):
    active: int
    completed: int
    abandoned: int
    total: int

    class Config:
        from_attributes = True


class AdminSummaryResponse(BaseModel):
    chunks: list[ChunkStats]
    images: list[ImageStats]
    sessions: SessionStatusCounts

    class Config:
        from_attributes = True


# ---------- PUBLIC RESULTS ----------
class ModelResult(BaseModel):
    model_id: str
    display_name: str
    wins: int
    win_percentage: float


class ResultsResponse(BaseModel):
    total_votes: int
    total_decisive_votes: int
    tie_votes: int
    models: list[ModelResult]


class PromptResult(BaseModel):
    prompt_id: str
    prompt_text: str
    images: list[ImageOut]
    total_votes: int
    tie_votes: int
    models: list[ModelResult]
    winning_model_id: Optional[str] = None
    winning_image_id: Optional[str] = None


class PromptResultsResponse(BaseModel):
    prompts: list[PromptResult]
