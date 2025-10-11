from pydantic import BaseModel
from typing import Optional


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
