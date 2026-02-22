"""
Portfolio API — positions, trade history, equity snapshots.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.alpaca_client import AlpacaClient
from app.database import get_db
from app.models.market_data import PortfolioSnapshot
from app.models.trading import Execution, Position
from app.models.trading import TradeDecision as TradeDecisionORM

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/positions")
async def get_positions(db: AsyncSession = Depends(get_db)):
    """
    All currently open positions — live from Alpaca with sleeve annotation from DB.
    Falls back to DB-only if Alpaca is unreachable.
    """
    # Local DB positions for sleeve + cost basis metadata
    db_result = await db.execute(
        select(Position)
        .where(Position.is_open == True)  # noqa: E712
        .order_by(Position.sleeve, Position.ticker)
    )
    db_positions = {p.ticker: p for p in db_result.scalars().all()}

    # Live positions from Alpaca
    try:
        alpaca = AlpacaClient()
        live = await asyncio.to_thread(alpaca.get_positions)
    except Exception as e:
        logger.warning(f"Alpaca positions fetch failed, using DB only: {e}")
        live = []

    def _merge(ap: dict) -> dict:
        db_p = db_positions.get(ap["ticker"])
        effective_cost = None
        if db_p:
            effective_cost = db_p.adjusted_cost_basis or db_p.cost_basis
        return {
            "id": db_p.id if db_p else None,
            "ticker": ap["ticker"],
            "sleeve": db_p.sleeve if db_p else "MAIN",
            "qty": ap["qty"],
            "current_price": ap["current_price"],
            "market_value": ap["market_value"],
            "entry_price": ap["avg_entry_price"],
            "cost_basis": ap["cost_basis"],
            "adjusted_cost_basis": db_p.adjusted_cost_basis if db_p else None,
            "unrealized_pnl": ap["unrealized_pnl"],
            "unrealized_pnl_pct": ap["unrealized_pnl_pct"],
            "entry_date": db_p.entry_date.isoformat() if db_p and db_p.entry_date else None,
            "wash_sale_adjusted": bool(db_p and db_p.adjusted_cost_basis),
            "source": "alpaca_live",
        }

    def _db_only(p: Position) -> dict:
        effective_cost = p.adjusted_cost_basis or p.cost_basis
        cost_per_share = effective_cost / p.current_qty if p.current_qty > 0 else 0.0
        return {
            "id": p.id,
            "ticker": p.ticker,
            "sleeve": p.sleeve,
            "qty": p.current_qty,
            "current_price": None,
            "market_value": None,
            "entry_price": p.entry_price,
            "cost_basis": p.cost_basis,
            "adjusted_cost_basis": p.adjusted_cost_basis,
            "unrealized_pnl": None,
            "unrealized_pnl_pct": None,
            "entry_date": p.entry_date.isoformat() if p.entry_date else None,
            "wash_sale_adjusted": p.adjusted_cost_basis is not None,
            "source": "db_only",
        }

    if live:
        merged = [_merge(ap) for ap in live]
        main = [p for p in merged if p["sleeve"] == "MAIN"]
        penny = [p for p in merged if p["sleeve"] == "PENNY"]
    else:
        db_list = list(db_positions.values())
        merged = [_db_only(p) for p in db_list]
        main = [p for p in merged if p["sleeve"] == "MAIN"]
        penny = [p for p in merged if p["sleeve"] == "PENNY"]

    return {
        "positions": merged,
        "main": main,
        "penny": penny,
        "total_count": len(merged),
    }


@router.get("/snapshots")
async def get_snapshots(
    limit: int = Query(default=90, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Portfolio equity snapshots for the equity curve chart. Newest last."""
    result = await db.execute(
        select(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.timestamp.desc())
        .limit(limit)
    )
    snapshots = list(reversed(result.scalars().all()))  # chronological order

    return {
        "snapshots": [
            {
                "timestamp": s.timestamp.isoformat(),
                "total_equity": s.total_equity,
                "main_equity": s.main_equity,
                "penny_equity": s.penny_equity,
                "cash_balance": s.cash_balance,
                "spy_benchmark_value": s.spy_benchmark_value,
                "daily_pnl": s.daily_pnl,
                "daily_pnl_pct": s.daily_pnl_pct,
            }
            for s in snapshots
        ],
        "count": len(snapshots),
    }


@router.get("/trades")
async def get_trade_history(
    limit: int = Query(default=50, le=200),
    status: str | None = Query(default=None),
    sleeve: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Trade decision history with execution details.
    Excludes HOLD decisions (informational, never persisted).
    """
    query = select(TradeDecisionORM).order_by(TradeDecisionORM.created_at.desc())

    if status:
        query = query.where(TradeDecisionORM.status == status.upper())
    if sleeve:
        query = query.where(TradeDecisionORM.sleeve == sleeve.upper())

    query = query.limit(limit)
    result = await db.execute(query)
    trades = result.scalars().all()

    # Bulk fetch executions for these trades
    trade_ids = [t.id for t in trades]
    exec_result = await db.execute(
        select(Execution).where(Execution.trade_decision_id.in_(trade_ids))
    )
    executions_by_trade = {e.trade_decision_id: e for e in exec_result.scalars().all()}

    def _trade(t: TradeDecisionORM) -> dict:
        ex = executions_by_trade.get(t.id)
        return {
            "id": t.id,
            "pipeline_run_id": t.pipeline_run_id,
            "ticker": t.ticker,
            "sleeve": t.sleeve,
            "action": t.action,
            "confidence": t.confidence,
            "position_size_pct": t.position_size_pct,
            "reasoning": t.reasoning,
            "stop_loss_pct": t.stop_loss_pct,
            "take_profit_pct": t.take_profit_pct,
            "status": t.status,
            "wash_sale_flagged": t.wash_sale_flagged,
            "created_at": t.created_at.isoformat(),
            "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
            "resolved_by": t.resolved_by,
            "execution": {
                "order_id": ex.order_id,
                "side": ex.side,
                "qty": ex.qty,
                "filled_price": ex.filled_price,
                "intended_price": ex.intended_price,
                "slippage": ex.slippage,
                "status": ex.status,
                "executed_at": ex.executed_at.isoformat() if ex.executed_at else None,
            } if ex else None,
        }

    return {"trades": [_trade(t) for t in trades], "count": len(trades)}


@router.get("/closed")
async def get_closed_positions(
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Closed positions with realized P&L."""
    result = await db.execute(
        select(Position)
        .where(
            Position.is_open == False,  # noqa: E712
            Position.realized_pnl.is_not(None),
        )
        .order_by(Position.closed_at.desc())
        .limit(limit)
    )
    positions = result.scalars().all()

    return {
        "closed": [
            {
                "id": p.id,
                "ticker": p.ticker,
                "sleeve": p.sleeve,
                "entry_price": p.entry_price,
                "entry_date": p.entry_date.isoformat() if p.entry_date else None,
                "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                "realized_pnl": p.realized_pnl,
                "cost_basis": p.cost_basis,
                "adjusted_cost_basis": p.adjusted_cost_basis,
            }
            for p in positions
        ],
        "count": len(positions),
        "total_realized_pnl": sum(p.realized_pnl for p in positions if p.realized_pnl),
    }
