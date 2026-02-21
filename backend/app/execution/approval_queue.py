"""
Approval queue — manages pending trade decisions and auto-approve logic.

The pipeline writes all actionable decisions as PENDING. This module decides
what happens next: auto-approve + execute, or notify and wait for manual action.

Auto-approve override conditions (from CLAUDE.md):
  - Any single trade > 30% of sleeve value → manual
  - Any trade during a circuit breaker cooldown → manual (blocked by risk_manager anyway)
  - First trade on any ticker never previously held → manual
  - Any trade where confidence is below 0.70 (main) or 0.60 (penny) → manual
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.execution.risk_manager import check_trade
from app.models.trading import Position
from app.models.trading import TradeDecision as TradeDecisionORM

logger = logging.getLogger(__name__)


async def process_new_decisions(db: AsyncSession, trade_ids: list[int]) -> None:
    """
    Called by the pipeline after writing trade decisions to DB.

    For each PENDING decision:
      1. Run risk checks (confidence gate, position limits, circuit breakers, wash sales)
      2. If blocked → mark REJECTED immediately
      3. If allowed + auto-approve eligible → mark APPROVED and execute
      4. If allowed + manual required → leave PENDING, notify
    """
    from app.config import get_settings
    from app.runtime_config import get_auto_approve
    settings = get_settings()

    for trade_id in trade_ids:
        result = await db.execute(
            select(TradeDecisionORM).where(TradeDecisionORM.id == trade_id)
        )
        trade = result.scalars().first()
        if not trade or trade.status != "PENDING":
            continue

        # Count open positions in this sleeve
        pos_result = await db.execute(
            select(Position).where(
                Position.sleeve == trade.sleeve,
                Position.is_open == True,  # noqa: E712
            )
        )
        current_positions = list(pos_result.scalars().all())
        current_positions_count = len(current_positions)

        # Check if this ticker has ever been held (new ticker = manual approval required)
        ever_held_result = await db.execute(
            select(Position)
            .where(
                Position.ticker == trade.ticker,
                Position.sleeve == trade.sleeve,
            )
            .limit(1)
        )
        is_new_ticker = ever_held_result.scalars().first() is None

        # Run the risk check
        risk = await check_trade(
            db=db,
            ticker=trade.ticker,
            action=trade.action,
            sleeve=trade.sleeve,
            confidence=trade.confidence,
            position_size_pct=trade.position_size_pct,
            current_positions_count=current_positions_count,
            is_new_ticker=is_new_ticker,
        )

        if not risk.allowed:
            logger.info(
                f"Trade #{trade_id} ({trade.action} {trade.ticker}) blocked by risk check: "
                f"{risk.blocked_reason}"
            )
            trade.status = "REJECTED"
            trade.resolved_at = datetime.now(timezone.utc)
            trade.resolved_by = "AUTO"
            await db.flush()
            continue

        # Propagate wash sale flag to the DB record
        if risk.wash_sale_flag:
            trade.wash_sale_flagged = True

        if get_auto_approve() and not risk.requires_manual_approval:
            # Auto-approve and execute immediately
            logger.info(
                f"Auto-approving trade #{trade_id}: {trade.action} {trade.ticker} "
                f"({trade.sleeve}, {trade.confidence:.0%})"
            )
            trade.status = "APPROVED"
            trade.resolved_by = "AUTO"
            trade.resolved_at = datetime.now(timezone.utc)
            await db.flush()

            from app.execution.engine import execute_trade
            await execute_trade(db, trade)

        else:
            # Leave PENDING — queue for manual review and notify
            reason = (
                "auto-approve disabled"
                if not get_auto_approve()
                else f"manual required: {'; '.join(risk.notes)}"
            )
            logger.info(
                f"Trade #{trade_id} ({trade.action} {trade.ticker}) queued for manual approval — {reason}"
            )
            await db.flush()

            await _notify_pending(trade)

            from app.routers.ws import manager as ws_manager
            await ws_manager.broadcast(
                {
                    "type": "trade_pending",
                    "trade_id": trade.id,
                    "ticker": trade.ticker,
                    "action": trade.action,
                    "sleeve": trade.sleeve,
                    "confidence": trade.confidence,
                    "wash_sale_flagged": trade.wash_sale_flagged,
                }
            )


async def get_pending_approvals(db: AsyncSession) -> list[TradeDecisionORM]:
    """Return all trades currently awaiting manual approval, newest first."""
    result = await db.execute(
        select(TradeDecisionORM)
        .where(TradeDecisionORM.status == "PENDING")
        .order_by(TradeDecisionORM.created_at.desc())
    )
    return list(result.scalars().all())


async def approve_trade(
    db: AsyncSession,
    trade_id: int,
    resolved_by: str = "MANUAL",
) -> Optional[TradeDecisionORM]:
    """
    Approve a PENDING trade and trigger execution.
    Returns the updated TradeDecision, or None if not found.
    """
    result = await db.execute(
        select(TradeDecisionORM).where(TradeDecisionORM.id == trade_id)
    )
    trade = result.scalars().first()

    if not trade:
        logger.warning(f"approve_trade: trade #{trade_id} not found.")
        return None

    if trade.status != "PENDING":
        logger.warning(
            f"approve_trade: trade #{trade_id} is {trade.status}, not PENDING. No action taken."
        )
        return trade

    trade.status = "APPROVED"
    trade.resolved_by = resolved_by
    trade.resolved_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(f"Trade #{trade_id} approved by {resolved_by}. Executing...")

    from app.execution.engine import execute_trade
    await execute_trade(db, trade)

    return trade


async def reject_trade(
    db: AsyncSession,
    trade_id: int,
    resolved_by: str = "MANUAL",
) -> Optional[TradeDecisionORM]:
    """
    Reject a PENDING trade. No execution occurs.
    Returns the updated TradeDecision, or None if not found.
    """
    result = await db.execute(
        select(TradeDecisionORM).where(TradeDecisionORM.id == trade_id)
    )
    trade = result.scalars().first()

    if not trade:
        logger.warning(f"reject_trade: trade #{trade_id} not found.")
        return None

    if trade.status != "PENDING":
        logger.warning(
            f"reject_trade: trade #{trade_id} is {trade.status}, not PENDING. No action taken."
        )
        return trade

    trade.status = "REJECTED"
    trade.resolved_by = resolved_by
    trade.resolved_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(f"Trade #{trade_id} rejected by {resolved_by}.")
    return trade


async def _notify_pending(trade: TradeDecisionORM) -> None:
    """Send a notification when a trade is queued for manual approval."""
    from app.notifications.notifier import get_notifier

    wash_note = " ⚠️ Wash sale flag active." if trade.wash_sale_flagged else ""
    message = (
        f"{trade.action} {trade.ticker} — {trade.sleeve} sleeve\n"
        f"Confidence: {trade.confidence:.0%} | Size: {trade.position_size_pct:.1f}%\n"
        f"Reasoning: {trade.reasoning[:300]}{'...' if len(trade.reasoning) > 300 else ''}"
        f"{wash_note}"
    )
    await get_notifier().send(
        event_type="trade_proposed",
        message=message,
        title=f"Trade Pending Approval: {trade.action} {trade.ticker}",
    )
