"""
Approval queue API — pending trades, approve/reject endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.execution.approval_queue import (
    approve_trade as _approve_trade,
    get_pending_approvals,
    reject_trade as _reject_trade,
)
from app.models.trading import TradeDecision as TradeDecisionORM

router = APIRouter()


def _to_dict(trade: TradeDecisionORM) -> dict:
    return {
        "id": trade.id,
        "pipeline_run_id": trade.pipeline_run_id,
        "ticker": trade.ticker,
        "sleeve": trade.sleeve,
        "action": trade.action,
        "confidence": trade.confidence,
        "position_size_pct": trade.position_size_pct,
        "reasoning": trade.reasoning,
        "stop_loss_pct": trade.stop_loss_pct,
        "take_profit_pct": trade.take_profit_pct,
        "status": trade.status,
        "wash_sale_flagged": trade.wash_sale_flagged,
        "resolved_by": trade.resolved_by,
        "created_at": trade.created_at.isoformat() if trade.created_at else None,
        "resolved_at": trade.resolved_at.isoformat() if trade.resolved_at else None,
    }


@router.get("/pending")
async def get_pending(db: AsyncSession = Depends(get_db)):
    """Return all trades currently awaiting manual approval."""
    trades = await get_pending_approvals(db)
    return {"pending": [_to_dict(t) for t in trades], "count": len(trades)}


@router.post("/{trade_id}/approve")
async def approve(trade_id: int, db: AsyncSession = Depends(get_db)):
    """Approve a pending trade and trigger execution."""
    trade = await _approve_trade(db, trade_id, resolved_by="MANUAL")
    if trade is None:
        raise HTTPException(status_code=404, detail=f"Trade #{trade_id} not found.")
    return {"status": "approved", "trade": _to_dict(trade)}


@router.post("/{trade_id}/reject")
async def reject(trade_id: int, db: AsyncSession = Depends(get_db)):
    """Reject a pending trade. No execution occurs."""
    trade = await _reject_trade(db, trade_id, resolved_by="MANUAL")
    if trade is None:
        raise HTTPException(status_code=404, detail=f"Trade #{trade_id} not found.")
    return {"status": "rejected", "trade": _to_dict(trade)}


@router.post("/bulk-approve")
async def bulk_approve(trade_ids: list[int], db: AsyncSession = Depends(get_db)):
    """Approve multiple pending trades."""
    results = []
    for trade_id in trade_ids:
        trade = await _approve_trade(db, trade_id, resolved_by="MANUAL")
        if trade:
            results.append(_to_dict(trade))
    return {"approved": len(results), "trades": results}


@router.post("/bulk-reject")
async def bulk_reject(trade_ids: list[int], db: AsyncSession = Depends(get_db)):
    """Reject multiple pending trades."""
    results = []
    for trade_id in trade_ids:
        trade = await _reject_trade(db, trade_id, resolved_by="MANUAL")
        if trade:
            results.append(_to_dict(trade))
    return {"rejected": len(results), "trades": results}
