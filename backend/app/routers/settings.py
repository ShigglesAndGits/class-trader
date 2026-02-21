"""
Settings API — runtime configuration and system status.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.risk import CircuitBreakerEvent
from app.runtime_config import get_auto_approve, set_auto_approve

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def get_settings_view():
    """All current runtime settings and API configuration status."""
    s = get_settings()
    return {
        "auto_approve": get_auto_approve(),  # Runtime value (may differ from env)
        "auto_approve_env": s.auto_approve,   # What's in .env
        "alpaca_paper": s.alpaca_paper,
        "main_sleeve_allocation": s.main_sleeve_allocation,
        "penny_sleeve_allocation": s.penny_sleeve_allocation,
        "max_position_pct_main": s.max_position_pct_main,
        "max_position_dollars_penny": s.max_position_dollars_penny,
        "min_confidence_main": s.min_confidence_main,
        "min_confidence_penny": s.min_confidence_penny,
        "daily_loss_limit_main_pct": s.daily_loss_limit_main_pct,
        "daily_loss_limit_penny_pct": s.daily_loss_limit_penny_pct,
        "consecutive_loss_pause": s.consecutive_loss_pause,
        "timezone": s.timezone,
        "apis_configured": s.configured_apis(),
        "llm_model": s.llm_model,
    }


class AutoApproveRequest(BaseModel):
    enabled: bool


@router.put("/auto-approve")
async def toggle_auto_approve(body: AutoApproveRequest):
    """
    Toggle auto-approve at runtime. Resets on restart.
    To make permanent, update AUTO_APPROVE in .env.
    """
    set_auto_approve(body.enabled)
    state = "enabled" if body.enabled else "disabled"
    logger.info(f"Auto-approve {state} via API (runtime only — resets on restart).")
    return {
        "auto_approve": get_auto_approve(),
        "note": "Runtime change only. Update AUTO_APPROVE in .env to persist.",
    }


@router.get("/circuit-breakers")
async def get_circuit_breakers(db: AsyncSession = Depends(get_db)):
    """List all circuit breaker events, active first."""
    result = await db.execute(
        select(CircuitBreakerEvent).order_by(
            CircuitBreakerEvent.is_active.desc(),
            CircuitBreakerEvent.triggered_at.desc(),
        )
    )
    events = result.scalars().all()

    return {
        "circuit_breakers": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "sleeve": e.sleeve,
                "reason": e.reason,
                "is_active": e.is_active,
                "triggered_at": e.triggered_at.isoformat(),
                "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
                "resolved_by": e.resolved_by,
            }
            for e in events
        ],
        "active_count": sum(1 for e in events if e.is_active),
    }


@router.post("/circuit-breakers/{event_id}/resolve")
async def resolve_circuit_breaker(event_id: int, db: AsyncSession = Depends(get_db)):
    """Manually resolve (deactivate) a circuit breaker to resume trading."""
    from app.execution.risk_manager import resolve_circuit_breaker

    event = await resolve_circuit_breaker(db, event_id, resolved_by="MANUAL")
    if not event:
        raise HTTPException(status_code=404, detail=f"Circuit breaker #{event_id} not found.")

    logger.info(f"Circuit breaker #{event_id} resolved manually via API.")
    return {
        "status": "resolved",
        "event_id": event_id,
        "event_type": event.event_type,
        "sleeve": event.sleeve,
    }
