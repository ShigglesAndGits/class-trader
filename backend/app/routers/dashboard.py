"""
Dashboard API — aggregated summary for the main view.

Returns everything the dashboard needs in a single call to avoid waterfall
requests from the frontend. Queries are cheap; round-trips are not.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.alpaca_client import AlpacaClient
from app.database import get_db
from app.models.market_data import PortfolioSnapshot
from app.models.pipeline import PipelineRun
from app.models.trading import Position
from app.models.trading import TradeDecision as TradeDecisionORM
from app.runtime_config import get_auto_approve

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/summary")
async def get_dashboard_summary(db: AsyncSession = Depends(get_db)):
    """
    Aggregated dashboard data: portfolio, regime, positions, recent decisions,
    auto-approve state. One round-trip, then the UI has everything it needs.
    """

    # ── Portfolio value — live from Alpaca ──────────────────────────────────
    # Pull directly from the broker so the number always matches reality.
    # Fall back to the most recent DB snapshot if Alpaca is unreachable.
    alpaca_account: dict | None = None
    alpaca_positions_live: list[dict] = []
    try:
        alpaca = AlpacaClient()
        alpaca_account, alpaca_positions_live = await asyncio.gather(
            asyncio.to_thread(alpaca.get_account),
            asyncio.to_thread(alpaca.get_positions),
        )
    except Exception as e:
        logger.warning(f"Alpaca account fetch failed, falling back to DB snapshot: {e}")

    if alpaca_account:
        # Use daily P&L from most recent snapshot if available
        snapshot_result = await db.execute(
            select(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .limit(1)
        )
        snapshot = snapshot_result.scalars().first()

        # Compute sleeve breakdown from our local position records
        local_pos_result = await db.execute(
            select(Position).where(Position.is_open == True)  # noqa: E712
        )
        local_positions = local_pos_result.scalars().all()
        # Match Alpaca positions to local sleeve tracking
        sleeve_map = {p.ticker: p.sleeve for p in local_positions}
        penny_value = sum(
            float(ap["market_value"])
            for ap in alpaca_positions_live
            if sleeve_map.get(ap["ticker"]) == "PENNY"
        )
        main_invested = sum(
            float(ap["market_value"])
            for ap in alpaca_positions_live
            if sleeve_map.get(ap["ticker"]) != "PENNY"
        )
        total_equity = float(alpaca_account["equity"])
        cash = float(alpaca_account["cash"])
        portfolio = {
            "total_equity": total_equity,
            "main_equity": cash + main_invested,
            "penny_equity": penny_value,
            "cash_balance": cash,
            "buying_power": float(alpaca_account["buying_power"]),
            "daily_pnl": snapshot.daily_pnl if snapshot else None,
            "daily_pnl_pct": snapshot.daily_pnl_pct if snapshot else None,
            "spy_benchmark_value": snapshot.spy_benchmark_value if snapshot else None,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "source": "alpaca_live",
        }
    else:
        # Alpaca unreachable — use most recent DB snapshot or config estimate
        snapshot_result = await db.execute(
            select(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .limit(1)
        )
        snapshot = snapshot_result.scalars().first()
        if snapshot:
            portfolio = {
                "total_equity": snapshot.total_equity,
                "main_equity": snapshot.main_equity,
                "penny_equity": snapshot.penny_equity,
                "cash_balance": snapshot.cash_balance,
                "buying_power": None,
                "daily_pnl": snapshot.daily_pnl,
                "daily_pnl_pct": snapshot.daily_pnl_pct,
                "spy_benchmark_value": snapshot.spy_benchmark_value,
                "as_of": snapshot.timestamp.isoformat(),
                "source": "snapshot",
            }
        else:
            from app.config import get_settings
            s = get_settings()
            portfolio = {
                "total_equity": s.main_sleeve_allocation + s.penny_sleeve_allocation,
                "main_equity": s.main_sleeve_allocation,
                "penny_equity": s.penny_sleeve_allocation,
                "cash_balance": s.main_sleeve_allocation + s.penny_sleeve_allocation,
                "buying_power": None,
                "daily_pnl": None,
                "daily_pnl_pct": None,
                "spy_benchmark_value": None,
                "as_of": None,
                "source": "estimated",
            }

    # ── Current regime ──────────────────────────────────────────────────────
    regime_result = await db.execute(
        select(PipelineRun)
        .where(
            PipelineRun.status == "COMPLETED",
            PipelineRun.regime.is_not(None),
        )
        .order_by(PipelineRun.completed_at.desc())
        .limit(1)
    )
    latest_run = regime_result.scalars().first()

    regime = None
    if latest_run:
        regime = {
            "regime": latest_run.regime,
            "confidence": latest_run.regime_confidence,
            "run_id": latest_run.id,
            "run_type": latest_run.run_type,
            "timestamp": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
        }

    # ── Open positions — live from Alpaca + sleeve annotation from DB ───────
    if alpaca_positions_live:
        # sleeve_map already built above; if Alpaca succeeded it's available
        open_positions = [
            {
                "ticker": ap["ticker"],
                "sleeve": sleeve_map.get(ap["ticker"], "MAIN"),
                "qty": ap["qty"],
                "entry_price": ap["avg_entry_price"],
                "current_price": ap["current_price"],
                "market_value": ap["market_value"],
                "cost_basis": ap["cost_basis"],
                "unrealized_pnl": ap["unrealized_pnl"],
                "unrealized_pnl_pct": ap["unrealized_pnl_pct"],
            }
            for ap in alpaca_positions_live
        ]
    else:
        # Fall back to DB positions (no live prices)
        open_pos_result = await db.execute(
            select(Position).where(Position.is_open == True)  # noqa: E712
        )
        open_positions = [
            {
                "ticker": p.ticker,
                "sleeve": p.sleeve,
                "qty": p.current_qty,
                "entry_price": p.entry_price,
                "current_price": None,
                "market_value": None,
                "cost_basis": p.cost_basis,
                "unrealized_pnl": None,
                "unrealized_pnl_pct": None,
            }
            for p in open_pos_result.scalars().all()
        ]

    # ── Recent trade decisions (last 24h) ───────────────────────────────────
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    decisions_result = await db.execute(
        select(TradeDecisionORM)
        .where(TradeDecisionORM.created_at >= cutoff)
        .order_by(TradeDecisionORM.created_at.desc())
        .limit(20)
    )
    recent_decisions = [
        {
            "id": t.id,
            "ticker": t.ticker,
            "sleeve": t.sleeve,
            "action": t.action,
            "confidence": t.confidence,
            "status": t.status,
            "wash_sale_flagged": t.wash_sale_flagged,
            "created_at": t.created_at.isoformat(),
            "resolved_by": t.resolved_by,
        }
        for t in decisions_result.scalars().all()
    ]

    # ── Last pipeline run (for "next run" context) ──────────────────────────
    last_run_result = await db.execute(
        select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(1)
    )
    last_run = last_run_result.scalars().first()
    last_run_info = None
    if last_run:
        last_run_info = {
            "id": last_run.id,
            "run_type": last_run.run_type,
            "status": last_run.status,
            "started_at": last_run.started_at.isoformat(),
            "completed_at": last_run.completed_at.isoformat() if last_run.completed_at else None,
        }

    return {
        "portfolio": portfolio,
        "regime": regime,
        "positions": open_positions,
        "recent_decisions": recent_decisions,
        "last_run": last_run_info,
        "auto_approve": get_auto_approve(),
        "position_count": len(open_positions),
        "pending_approvals": sum(1 for d in recent_decisions if d["status"] == "PENDING"),
    }
