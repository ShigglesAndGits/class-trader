"""
DiscoverySession ORM model.

Stores a stock discovery chat session: the original query, which tickers were
analyzed, the pipeline run that produced the agent debate, the recommendations
that came out, and the full conversation history with the user.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class DiscoverySession(Base):
    __tablename__ = "discovery_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Link to the PipelineRun that ran the agent debate for this session.
    # Nullable: populated after the SSE stream starts and creates the run.
    pipeline_run_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("pipeline_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # The original user query, verbatim.
    query: Mapped[str] = mapped_column(Text, nullable=False)

    # EXPLICIT: user provided tickers/themes directly
    # NEWS_SCAN: system scanned Finnhub news for candidates
    query_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="EXPLICIT")

    # List of ticker strings that were actually analyzed.
    tickers_analyzed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # RUNNING | COMPLETED | FAILED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")

    # RegimeAssessment dict from the discovery pipeline run.
    regime_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # DiscoveryRecommendations dict (list of proposals + overall_thesis + caveats).
    recommendations: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Conversation history: list of {role, content, ts} dicts.
    conversation: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    pipeline_run: Mapped[Optional["PipelineRun"]] = relationship(  # type: ignore[name-defined]
        "PipelineRun", foreign_keys=[pipeline_run_id]
    )
