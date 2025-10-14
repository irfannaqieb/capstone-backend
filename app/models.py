from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Enum,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from .database import Base
import enum


class ModelName(enum.Enum):
    gpt5 = "gpt5"
    gemini25 = "gemini25"


class Winner(enum.Enum):
    gpt5 = "gpt5"
    gemini25 = "gemini25"
    tie = "tie"


class SessionStatus(enum.Enum):
    active = "active"
    completed = "completed"
    abandoned = "abandoned"


MODEL_DISPLAY = {
    "gpt5": "gpt-5",
    "gemini25": "gemini-2.5",
}


class Prompt(Base):
    __tablename__ = "prompts"
    id = Column(String, primary_key=True)
    text = Column(String, nullable=False)
    category = Column(String, nullable=True)
    images = relationship("Image", back_populates="prompt")


class Image(Base):
    __tablename__ = "images"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_id = Column(String, ForeignKey("prompts.id"))
    model = Column(Enum(ModelName))
    url = Column(String)
    prompt = relationship("Prompt", back_populates="images")

    __table_args__ = (
        UniqueConstraint("prompt_id", "model", name="uq_images_prompt_model"),
    )


class Pair(Base):
    __tablename__ = "pairs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_id = Column(String, ForeignKey("prompts.id"))
    image_a_id = Column(UUID(as_uuid=True), ForeignKey("images.id"), nullable=False)
    image_b_id = Column(UUID(as_uuid=True), ForeignKey("images.id"), nullable=False)

    image_a = relationship("Image", foreign_keys=[image_a_id])
    image_b = relationship("Image", foreign_keys=[image_b_id])

    __table_args__ = (UniqueConstraint("prompt_id", name="uq_pairs_prompt"),)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(SessionStatus), default=SessionStatus.active, nullable=False)
    votes = relationship("Vote", back_populates="session", cascade="all, delete-orphan")


class Vote(Base):
    __tablename__ = "votes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    pair_id = Column(UUID(as_uuid=True), ForeignKey("pairs.id"), nullable=False)
    winner_model = Column(Enum(Winner), nullable=False)
    left_model = Column(Enum(ModelName), nullable=False)
    reaction_time_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("Session", back_populates="votes")

    __table_args__ = (
        UniqueConstraint("user_session_id", "pair_id", name="uq_votes_session_pair"),
    )
