"""
Pipeline run and agent interaction models.
Every agent invocation is logged in full — prompt, response, tokens, latency.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # MORNING, NOON, NEWS_TRIGGER, MANUAL
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    regime: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # TRENDING_UP, TRENDING_DOWN, RANGING, HIGH_VOLATILITY
    regime_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="RUNNING"
    )  # RUNNING, COMPLETED, FAILED, PAUSED
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    agent_interactions: Mapped[list["AgentInteraction"]] = relationship(
        back_populates="pipeline_run", cascade="all, delete-orphan"
    )
    trade_decisions: Mapped[list["TradeDecision"]] = relationship(  # type: ignore[name-defined]
        back_populates="pipeline_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PipelineRun id={self.id} type={self.run_type} status={self.status}>"


class AgentInteraction(Base):
    __tablename__ = "agent_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False
    )
    agent_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # REGIME_ANALYST, BULL, BEAR, RESEARCHER, PORTFOLIO_MANAGER, DEGEN
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_output: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(nullable=False, default=True)

    # Relationship
    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="agent_interactions")

    def __repr__(self) -> str:
        return f"<AgentInteraction id={self.id} agent={self.agent_type} run={self.pipeline_run_id}>"
