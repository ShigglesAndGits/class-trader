"""
Trading schemas for API request/response objects.
Mirrors the ORM models but shaped for the API layer.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class TradeDecisionResponse(BaseModel):
    id: int
    ticker: str
    sleeve: Literal["MAIN", "PENNY"]
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    position_size_pct: float
    reasoning: str
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    status: str
    wash_sale_flagged: bool
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    pipeline_run_id: Optional[int] = None

    model_config = {"from_attributes": True}


class ApproveRejectRequest(BaseModel):
    note: Optional[str] = None  # Optional human note for the audit log


class PositionResponse(BaseModel):
    ticker: str
    sleeve: str
    qty: float
    current_price: float
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    avg_entry_price: float
    side: str


class PortfolioSummary(BaseModel):
    main_equity: float
    penny_equity: float
    total_equity: float
    cash_balance: float
    positions: list[PositionResponse]
    daily_pnl: Optional[float] = None
    daily_pnl_pct: Optional[float] = None
    spy_benchmark_value: Optional[float] = None
