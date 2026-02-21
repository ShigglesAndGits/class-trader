"""
Risk management — hard limits enforced in code, not in LLM prompts.

The LLM decides what to trade. The risk manager decides if the trade is allowed
to proceed at all, and whether it qualifies for auto-approval.

All checks here are deterministic and config-driven. Nothing probabilistic.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import cast, func, select
from sqlalchemy import Date as DateType
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import CircuitBreakerEvent
from app.models.trading import Position

logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    allowed: bool
    blocked_reason: Optional[str] = None
    # True means this trade bypasses auto-approve even when the toggle is ON
    requires_manual_approval: bool = False
    # Informational: wash sale window open — flag in UI, adjust cost basis, but allow
    wash_sale_flag: bool = False
    notes: list[str] = field(default_factory=list)


async def check_trade(
    db: AsyncSession,
    ticker: str,
    action: str,
    sleeve: str,
    confidence: float,
    position_size_pct: float,
    current_positions_count: int,
    is_new_ticker: bool,
) -> RiskCheckResult:
    """
    Run all hard risk checks on a proposed trade.

    Returns RiskCheckResult with allowed=False if any hard limit is violated.
    Returns allowed=True with requires_manual_approval=True if the trade is
    valid but must go through manual review regardless of the auto-approve setting.

    Checks (in order):
      1. Confidence gate
      2. Position size limit
      3. Max concurrent positions
      4. Circuit breaker (active halt)
      5. Wash sale (hard block in December; flag + note otherwise)
      6. Auto-approve override conditions
    """
    from app.config import get_settings
    settings = get_settings()
    notes: list[str] = []

    # ── 1. Confidence gate ─────────────────────────────────────────────────
    min_conf = (
        settings.min_confidence_penny if sleeve == "PENNY" else settings.min_confidence_main
    )
    if confidence < min_conf:
        return RiskCheckResult(
            allowed=False,
            blocked_reason=(
                f"Confidence {confidence:.0%} below {sleeve} sleeve minimum {min_conf:.0%}."
            ),
        )

    # ── 2. Position size limit ─────────────────────────────────────────────
    if action == "BUY":
        if sleeve == "MAIN" and position_size_pct > settings.max_position_pct_main:
            return RiskCheckResult(
                allowed=False,
                blocked_reason=(
                    f"Proposed position {position_size_pct:.1f}% exceeds "
                    f"main sleeve max {settings.max_position_pct_main:.0f}%."
                ),
            )

        # ── 3. Max concurrent positions ────────────────────────────────────
        max_positions = 5 if sleeve == "PENNY" else 8
        if current_positions_count >= max_positions:
            return RiskCheckResult(
                allowed=False,
                blocked_reason=(
                    f"{sleeve} sleeve at capacity ({current_positions_count}/{max_positions} positions)."
                ),
            )

    # ── 4. Circuit breaker ─────────────────────────────────────────────────
    if await is_circuit_breaker_active(db, sleeve=sleeve):
        return RiskCheckResult(
            allowed=False,
            blocked_reason=f"Circuit breaker active for {sleeve} sleeve. All trading halted.",
        )

    # ── 5. Wash sale checks (BUY only) ─────────────────────────────────────
    wash_sale_flag = False
    if action == "BUY":
        from app.execution.wash_sale_tracker import get_active_wash_sale, is_wash_sale_blocked

        if await is_wash_sale_blocked(db, ticker):
            return RiskCheckResult(
                allowed=False,
                blocked_reason=(
                    f"{ticker} hard-blocked: December wash sale protection. "
                    "Cannot rebuy a ticker sold at a loss in December."
                ),
            )

        active_wash = await get_active_wash_sale(db, ticker)
        if active_wash:
            wash_sale_flag = True
            notes.append(
                f"Wash sale window active for {ticker} "
                f"(sold at loss on {active_wash.sale_date}, "
                f"window closes {active_wash.blackout_until}). "
                "Disallowed loss will be added to cost basis."
            )

    # ── 6. Auto-approve override conditions ───────────────────────────────
    # These don't block the trade — they just force manual review.
    requires_manual = False

    if is_new_ticker and action == "BUY":
        requires_manual = True
        notes.append(f"First-time position in {ticker} — requires manual approval.")

    if action == "BUY" and position_size_pct > 30.0:
        requires_manual = True
        notes.append(
            f"Position size {position_size_pct:.1f}% exceeds 30% threshold "
            "— requires manual approval."
        )

    # Per CLAUDE.md: auto-approve requires confidence >= 0.70 (main) or >= 0.60 (penny)
    auto_approve_conf = 0.70 if sleeve == "MAIN" else 0.60
    if confidence < auto_approve_conf:
        requires_manual = True
        notes.append(
            f"Confidence {confidence:.0%} below auto-approve threshold "
            f"{auto_approve_conf:.0%} for {sleeve} sleeve."
        )

    return RiskCheckResult(
        allowed=True,
        requires_manual_approval=requires_manual,
        wash_sale_flag=wash_sale_flag,
        notes=notes,
    )


async def is_circuit_breaker_active(
    db: AsyncSession,
    sleeve: Optional[str] = None,
) -> bool:
    """
    Check if any active circuit breaker is blocking trading.
    If sleeve is provided, checks for sleeve-specific OR system-wide breakers.
    """
    from sqlalchemy import or_

    query = select(CircuitBreakerEvent).where(
        CircuitBreakerEvent.is_active == True  # noqa: E712
    )
    if sleeve:
        query = query.where(
            or_(
                CircuitBreakerEvent.sleeve == sleeve,
                CircuitBreakerEvent.sleeve.is_(None),
            )
        )
    result = await db.execute(query)
    return result.scalars().first() is not None


async def trigger_circuit_breaker(
    db: AsyncSession,
    event_type: str,
    reason: str,
    sleeve: Optional[str] = None,
) -> CircuitBreakerEvent:
    """
    Record and activate a circuit breaker event. Halts all trading for the sleeve.

    event_type options:
      DAILY_LOSS_MAIN, DAILY_LOSS_PENNY, CONSECUTIVE_LOSSES,
      API_FAILURE, SCHEMA_FAILURE
    """
    event = CircuitBreakerEvent(
        event_type=event_type,
        sleeve=sleeve,
        reason=reason,
        triggered_at=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(event)
    await db.flush()

    logger.critical(
        f"CIRCUIT BREAKER TRIGGERED: {event_type} "
        f"(sleeve={sleeve or 'ALL'}). {reason}"
    )
    return event


async def resolve_circuit_breaker(
    db: AsyncSession,
    event_id: int,
    resolved_by: str = "MANUAL",
) -> Optional[CircuitBreakerEvent]:
    """Deactivate a circuit breaker. Called from the settings API."""
    result = await db.execute(
        select(CircuitBreakerEvent).where(CircuitBreakerEvent.id == event_id)
    )
    event = result.scalars().first()
    if event:
        event.is_active = False
        event.resolved_at = datetime.now(timezone.utc)
        event.resolved_by = resolved_by
        logger.info(f"Circuit breaker #{event_id} ({event.event_type}) resolved by {resolved_by}.")
    return event


async def get_today_realized_pnl(db: AsyncSession, sleeve: str) -> float:
    """
    Sum realized P&L from positions closed today for the given sleeve.
    Returns a negative number if the sleeve has net losses today.

    Note: this uses realized_pnl from the positions table, which is only
    populated when a position is fully closed by the execution engine.
    """
    today = date.today()
    result = await db.execute(
        select(func.coalesce(func.sum(Position.realized_pnl), 0.0)).where(
            Position.sleeve == sleeve,
            Position.is_open == False,  # noqa: E712
            Position.realized_pnl.is_not(None),
            cast(Position.closed_at, DateType) == today,
        )
    )
    return float(result.scalar() or 0.0)


async def count_consecutive_losses(db: AsyncSession) -> int:
    """
    Count the number of consecutive losing closed positions at the tail of history.
    A 'loss' is a closed position with realized_pnl < 0.
    """
    result = await db.execute(
        select(Position)
        .where(
            Position.is_open == False,  # noqa: E712
            Position.realized_pnl.is_not(None),
        )
        .order_by(Position.closed_at.desc())
        .limit(10)
    )
    positions = result.scalars().all()
    consecutive = 0
    for pos in positions:
        if pos.realized_pnl is not None and pos.realized_pnl < 0:
            consecutive += 1
        else:
            break
    return consecutive
