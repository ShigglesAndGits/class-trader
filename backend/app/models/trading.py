"""
Trade decision, execution, and position models.
The full paper trail from LLM decision to filled order.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class TradeDecision(Base):
    __tablename__ = "trade_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    sleeve: Mapped[str] = mapped_column(String(10), nullable=False)  # MAIN, PENNY
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY, SELL, HOLD
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    position_size_pct: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    stop_loss_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )  # PENDING, APPROVED, REJECTED, EXECUTED, FAILED, SKIPPED
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # AUTO, MANUAL
    wash_sale_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    pipeline_run: Mapped[Optional["PipelineRun"]] = relationship(  # type: ignore[name-defined]
        back_populates="trade_decisions"
    )
    execution: Mapped[Optional["Execution"]] = relationship(
        back_populates="trade_decision", uselist=False
    )

    def __repr__(self) -> str:
        return f"<TradeDecision id={self.id} {self.action} {self.ticker} status={self.status}>"


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_decision_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trade_decisions.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Alpaca order ID
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # buy, sell
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    filled_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    intended_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    slippage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # filled - intended
    fees: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )  # PENDING, FILLED, PARTIALLY_FILLED, CANCELLED, FAILED
    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    trade_decision: Mapped["TradeDecision"] = relationship(back_populates="execution")

    def __repr__(self) -> str:
        return f"<Execution id={self.id} {self.side} {self.qty} order={self.order_id}>"


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sleeve: Mapped[str] = mapped_column(String(10), nullable=False)  # MAIN, PENNY
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_qty: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis: Mapped[float] = mapped_column(Float, nullable=False)
    adjusted_cost_basis: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # Wash sale adjusted
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<Position id={self.id} {self.ticker} qty={self.current_qty} open={self.is_open}>"
