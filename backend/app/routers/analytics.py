"""
Analytics API — performance metrics and equity curve data.
"""

import logging
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.market_data import PortfolioSnapshot
from app.models.trading import Position

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/performance")
async def get_performance(db: AsyncSession = Depends(get_db)):
    """
    Performance metrics calculated from closed positions.
    Returns win rate, average gain/loss, total realized P&L.
    Sharpe ratio requires portfolio snapshot history — omitted if unavailable.
    """
    result = await db.execute(
        select(Position).where(
            Position.is_open == False,  # noqa: E712
            Position.realized_pnl.is_not(None),
        )
    )
    closed = result.scalars().all()

    if not closed:
        return {
            "metrics": {
                "trade_count": 0,
                "win_count": 0,
                "loss_count": 0,
                "win_rate": None,
                "avg_gain": None,
                "avg_loss": None,
                "total_realized_pnl": 0.0,
                "largest_gain": None,
                "largest_loss": None,
                "sharpe_ratio": None,
            }
        }

    gains = [p.realized_pnl for p in closed if p.realized_pnl > 0]
    losses = [p.realized_pnl for p in closed if p.realized_pnl < 0]
    all_pnl = [p.realized_pnl for p in closed]

    win_rate = len(gains) / len(closed) if closed else None

    # Simplified Sharpe: mean daily return / std dev of returns
    # Only meaningful with enough data points
    sharpe = None
    if len(all_pnl) >= 5:
        mean = sum(all_pnl) / len(all_pnl)
        variance = sum((x - mean) ** 2 for x in all_pnl) / len(all_pnl)
        std_dev = math.sqrt(variance)
        if std_dev > 0:
            sharpe = round((mean / std_dev) * math.sqrt(252), 2)  # annualized

    return {
        "metrics": {
            "trade_count": len(closed),
            "win_count": len(gains),
            "loss_count": len(losses),
            "win_rate": round(win_rate, 4) if win_rate is not None else None,
            "avg_gain": round(sum(gains) / len(gains), 2) if gains else None,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
            "total_realized_pnl": round(sum(all_pnl), 2),
            "largest_gain": round(max(gains), 2) if gains else None,
            "largest_loss": round(min(losses), 2) if losses else None,
            "sharpe_ratio": sharpe,
        }
    }


@router.get("/equity-curve")
async def get_equity_curve(
    limit: int = Query(default=90, le=365),
    db: AsyncSession = Depends(get_db),
):
    """
    Portfolio equity over time for the equity curve chart.
    Returns total equity and SPY benchmark value per snapshot, chronological.
    """
    result = await db.execute(
        select(PortfolioSnapshot)
        .order_by(PortfolioSnapshot.timestamp.desc())
        .limit(limit)
    )
    snapshots = list(reversed(result.scalars().all()))

    return {
        "data": [
            {
                "timestamp": s.timestamp.isoformat(),
                "total_equity": s.total_equity,
                "main_equity": s.main_equity,
                "penny_equity": s.penny_equity,
                "spy_benchmark_value": s.spy_benchmark_value,
                "daily_pnl": s.daily_pnl,
            }
            for s in snapshots
        ],
        "count": len(snapshots),
        "has_benchmark": any(s.spy_benchmark_value for s in snapshots),
    }


@router.get("/agent-accuracy")
async def get_agent_accuracy(db: AsyncSession = Depends(get_db)):
    """
    Rough proxy for agent accuracy: for each EXECUTED trade,
    did the position end up in profit or loss?
    Requires closed positions with realized P&L data.
    Phase 5 will have more sophisticated tracking.
    """
    from app.models.trading import TradeDecision as TradeDecisionORM

    result = await db.execute(
        select(TradeDecisionORM, Position)
        .join(Position, TradeDecisionORM.ticker == Position.ticker)
        .where(
            TradeDecisionORM.status == "EXECUTED",
            TradeDecisionORM.action == "BUY",
            Position.is_open == False,  # noqa: E712
            Position.realized_pnl.is_not(None),
        )
    )
    rows = result.all()

    bull_correct = bull_total = 0
    pm_correct = pm_total = 0

    for trade, pos in rows:
        is_win = pos.realized_pnl > 0
        pm_total += 1
        if is_win:
            pm_correct += 1

    return {
        "portfolio_manager": {
            "total": pm_total,
            "correct": pm_correct,
            "accuracy": round(pm_correct / pm_total, 4) if pm_total > 0 else None,
        }
    }
