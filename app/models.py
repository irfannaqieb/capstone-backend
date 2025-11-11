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
    flux1_dev = "flux1_dev"
    flux1_krea = "flux1_krea"
    kolors = "kolors"


class Winner(enum.Enum):
    gpt5 = "gpt5"
    gemini25 = "gemini25"
    flux1_dev = "flux1_dev"
    flux1_krea = "flux1_krea"
    kolors = "kolors"
    tie = "tie"


class SessionStatus(enum.Enum):
    active = "active"
    completed = "completed"
    abandoned = "abandoned"


MODEL_DISPLAY = {
    "gpt5": "gpt-5",
    "gemini25": "gemini-2.5",
    "flux1_dev": "Flux.1 Dev",
    "flux1_krea": "Flux.1 Krea",
    "kolors": "Kolors",
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


class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    sessions = relationship("Session", back_populates="chunk")
    chunk_prompts = relationship(
        "ChunkPrompt", back_populates="chunk", cascade="all, delete-orphan"
    )


class ChunkPrompt(Base):
    __tablename__ = "chunk_prompts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id = Column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    prompt_id = Column(
        String, ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False
    )

    # Relationships
    chunk = relationship("Chunk", back_populates="chunk_prompts")
    prompt = relationship("Prompt")

    __table_args__ = (
        UniqueConstraint("chunk_id", "prompt_id", name="uq_chunk_prompts_chunk_prompt"),
    )


class Session(Base):
    __tablename__ = "sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(SessionStatus), default=SessionStatus.active, nullable=False)
    chunk_id = Column(
        UUID(as_uuid=True), ForeignKey("chunks.id"), nullable=True
    )  # Nullable for backward compatibility

    # Relationships
    votes = relationship("Vote", back_populates="session", cascade="all, delete-orphan")
    chunk = relationship("Chunk", back_populates="sessions")


class Vote(Base):
    __tablename__ = "votes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    prompt_id = Column(String, ForeignKey("prompts.id"), nullable=False)
    winner_model = Column(Enum(Winner), nullable=False)
    reaction_time_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    session = relationship("Session", back_populates="votes")
    prompt = relationship("Prompt")

    __table_args__ = (
        UniqueConstraint(
            "user_session_id", "prompt_id", name="uq_votes_session_prompt"
        ),
    )
