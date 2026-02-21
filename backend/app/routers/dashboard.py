"""
Dashboard API — aggregated summary for the main view.

Returns everything the dashboard needs in a single call to avoid waterfall
requests from the frontend. Queries are cheap; round-trips are not.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    # ── Portfolio value ─────────────────────────────────────────────────────
    # Prefer a recent snapshot (written by scheduler). Fall back to position math.
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
            "daily_pnl": snapshot.daily_pnl,
            "daily_pnl_pct": snapshot.daily_pnl_pct,
            "spy_benchmark_value": snapshot.spy_benchmark_value,
            "as_of": snapshot.timestamp.isoformat(),
            "source": "snapshot",
        }
    else:
        # No snapshots yet — estimate from open positions
        pos_result = await db.execute(
            select(Position).where(Position.is_open == True)  # noqa: E712
        )
        positions = pos_result.scalars().all()
        cost_basis_total = sum(p.cost_basis for p in positions)
        from app.config import get_settings
        s = get_settings()
        portfolio = {
            "total_equity": s.main_sleeve_allocation + s.penny_sleeve_allocation,
            "main_equity": s.main_sleeve_allocation,
            "penny_equity": s.penny_sleeve_allocation,
            "cash_balance": max(0.0, (s.main_sleeve_allocation + s.penny_sleeve_allocation) - cost_basis_total),
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

    # ── Open positions ──────────────────────────────────────────────────────
    open_pos_result = await db.execute(
        select(Position).where(Position.is_open == True)  # noqa: E712
    )
    open_positions = [
        {
            "ticker": p.ticker,
            "sleeve": p.sleeve,
            "qty": p.current_qty,
            "entry_price": p.entry_price,
            "cost_basis": p.cost_basis,
            "entry_date": p.entry_date.isoformat() if p.entry_date else None,
            # Unrealized P&L computed client-side with live prices in Phase 5
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
