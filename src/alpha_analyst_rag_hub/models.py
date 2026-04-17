"""Shared Pydantic models for the RAG Hub."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class Document(BaseModel):
    """A raw text document with metadata, used as input to the synthesis chain."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str  # e.g. "news", "sec"
    ticker: str
    title: str
    content: str
    published_at: datetime | None = None
    url: str | None = None
    metadata: dict = Field(default_factory=dict)


class Insight(BaseModel):
    """A synthesised investment insight produced by the Synthesis agent."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    ticker: str
    type: str  # "Fundamental" | "Sentiment" | "TechnicalRisk"
    summary: str
    detailed_analysis: str | None = None
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.0)
    sources: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
