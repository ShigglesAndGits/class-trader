"""
Risk management models: wash sale tracking and circuit breaker events.
These are enforcement records — facts about what happened, not decisions.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class WashSale(Base):
    __tablename__ = "wash_sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    loss_amount: Mapped[float] = mapped_column(Float, nullable=False)
    qty_sold: Mapped[float] = mapped_column(Float, nullable=False)
    sale_price: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis: Mapped[float] = mapped_column(Float, nullable=False)
    adjusted_cost_basis: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # Adjusted if rebought within 30 days
    blackout_until: Mapped[date] = mapped_column(
        Date, nullable=False
    )  # sale_date + 30 days
    is_year_end_blocked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # True during December 1-31
    rebought: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # Was it bought back within the window?
    rebought_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<WashSale id={self.id} ticker={self.ticker} loss={self.loss_amount} until={self.blackout_until}>"


class CircuitBreakerEvent(Base):
    __tablename__ = "circuit_breaker_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # DAILY_LOSS_MAIN, DAILY_LOSS_PENNY, CONSECUTIVE_LOSSES, API_FAILURE, SCHEMA_FAILURE
    sleeve: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # MAIN, PENNY, or None for system-wide
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # MANUAL, AUTO
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<CircuitBreakerEvent id={self.id} type={self.event_type} active={self.is_active}>"
