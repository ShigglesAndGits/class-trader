"""
Trade execution engine.

Submits orders to Alpaca, polls for fills, records results to the database,
updates positions, checks circuit breakers, and handles wash sale tracking.

This is the only place in the system that actually sends orders to the broker.
The LLM pipeline produces decisions; this module executes them.
"""

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.alpaca_client import AlpacaClient
from app.execution.risk_manager import (
    get_today_realized_pnl,
    is_circuit_breaker_active,
    trigger_circuit_breaker,
)
from app.execution.wash_sale_tracker import (
    get_active_wash_sale,
    mark_rebought,
    record_wash_sale,
)
from app.models.trading import Execution, Position
from app.models.trading import TradeDecision as TradeDecisionORM
from app.routers.ws import manager as ws_manager

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SEC = 2
_POLL_TIMEOUT_SEC = 90  # Market orders in normal hours fill in seconds


async def execute_trade(
    db: AsyncSession,
    trade: TradeDecisionORM,
) -> Optional[Execution]:
    """
    Execute an APPROVED trade decision via Alpaca.

    Flow:
      1. Get current price quote
      2. Calculate share quantity
      3. Submit market order
      4. Poll for fill (up to 90 seconds)
      5. Record Execution + update Position in DB
      6. Post-execution: wash sale tracking, circuit breaker checks
      7. Broadcast WebSocket event

    Returns the filled Execution record, or None if execution failed or was skipped.
    """
    settings = _get_settings()
    alpaca = AlpacaClient()
    ticker = trade.ticker
    action = trade.action
    sleeve = trade.sleeve

    logger.info(
        f"Executing trade #{trade.id}: {action} {ticker} "
        f"({sleeve} sleeve, confidence={trade.confidence:.0%})"
    )

    try:
        # ── Step 1: Current price ───────────────────────────────────────────
        quotes = await asyncio.to_thread(alpaca.get_latest_quotes, [ticker])
        quote = quotes.get(ticker, {})
        current_price = quote.get("mid_price") or quote.get("ask_price") or quote.get("bid_price")
        if not current_price or current_price <= 0:
            raise ValueError(f"Could not get a valid current price for {ticker}")

        # ── Step 2: Calculate quantity ──────────────────────────────────────
        side = "buy" if action == "BUY" else "sell"
        qty = await _calculate_qty(db, alpaca, trade, current_price, settings)

        if qty <= 0:
            logger.warning(
                f"Calculated qty=0 for {action} {ticker} "
                f"(price=${current_price:.2f}, size_pct={trade.position_size_pct:.1f}%). Skipping."
            )
            trade.status = "SKIPPED"
            trade.resolved_at = datetime.now(timezone.utc)
            await db.flush()
            return None

        # ── Step 3: Submit order ────────────────────────────────────────────
        logger.info(f"Submitting {side} order: {qty} × {ticker} @ ~${current_price:.2f}")
        order = await asyncio.to_thread(alpaca.submit_market_order, ticker, qty, side)
        order_id = order["order_id"]

        # Write an execution shell immediately so we have a record even if polling fails
        execution = Execution(
            trade_decision_id=trade.id,
            order_id=order_id,
            side=side,
            qty=qty,
            intended_price=current_price,
            status="PENDING",
        )
        db.add(execution)
        await db.flush()

        # ── Step 4: Poll for fill ───────────────────────────────────────────
        filled = await _poll_for_fill(alpaca, order_id)

        if not filled:
            logger.error(f"Order {order_id} did not fill within {_POLL_TIMEOUT_SEC}s. Cancelling.")
            await asyncio.to_thread(alpaca.cancel_order, order_id)
            execution.status = "CANCELLED"
            trade.status = "FAILED"
            trade.resolved_at = datetime.now(timezone.utc)
            await db.flush()
            await ws_manager.broadcast(
                {"type": "trade_failed", "ticker": ticker, "action": action, "order_id": order_id}
            )
            return None

        # ── Step 5: Record fill ─────────────────────────────────────────────
        filled_price: float = filled["filled_avg_price"]
        filled_qty: float = filled["filled_qty"]
        slippage = filled_price - current_price  # positive = paid more / received less

        execution.filled_price = filled_price
        execution.qty = filled_qty
        execution.slippage = slippage
        execution.status = "FILLED"
        execution.executed_at = datetime.now(timezone.utc)

        trade.status = "EXECUTED"
        trade.resolved_at = execution.executed_at

        # ── Step 6a: Update position ────────────────────────────────────────
        await _update_position(db, trade, filled_price, filled_qty)

        # ── Step 6b: Post-execution checks ──────────────────────────────────
        await _post_execution_checks(db, trade, sleeve, settings)

        await db.flush()

        # ── Step 7: WebSocket broadcast ─────────────────────────────────────
        await ws_manager.broadcast(
            {
                "type": "trade_executed",
                "trade_id": trade.id,
                "ticker": ticker,
                "action": action,
                "side": side,
                "qty": filled_qty,
                "filled_price": filled_price,
                "slippage": slippage,
                "sleeve": sleeve,
                "order_id": order_id,
            }
        )

        logger.info(
            f"FILLED: {action} {filled_qty:.0f} × {ticker} @ ${filled_price:.2f} "
            f"(slippage ${slippage:+.3f})"
        )
        return execution

    except Exception as e:
        logger.error(f"Execution failed for trade #{trade.id} ({action} {ticker}): {e}", exc_info=True)
        trade.status = "FAILED"
        trade.resolved_at = datetime.now(timezone.utc)
        await db.flush()
        await ws_manager.broadcast(
            {"type": "trade_failed", "ticker": ticker, "action": action, "error": str(e)}
        )
        return None


async def _calculate_qty(
    db: AsyncSession,
    alpaca: AlpacaClient,
    trade: TradeDecisionORM,
    current_price: float,
    settings,
) -> int:
    """
    Calculate integer share quantity for the order.

    BUY:  position_size_pct % of sleeve allocation, floored to whole shares.
          Penny sleeve additionally capped at max_position_dollars_penny.
    SELL: full quantity of the open position (full exit).
    """
    if trade.action == "BUY":
        sleeve_equity = (
            settings.penny_sleeve_allocation
            if trade.sleeve == "PENNY"
            else settings.main_sleeve_allocation
        )
        dollar_amount = (trade.position_size_pct / 100.0) * sleeve_equity

        if trade.sleeve == "PENNY":
            dollar_amount = min(dollar_amount, settings.max_position_dollars_penny)

        qty = int(dollar_amount / current_price)
        return max(qty, 0)

    elif trade.action == "SELL":
        # Prefer our own Position record (more reliable than Alpaca API for qty)
        result = await db.execute(
            select(Position).where(
                Position.ticker == trade.ticker,
                Position.sleeve == trade.sleeve,
                Position.is_open == True,  # noqa: E712
            )
        )
        position = result.scalars().first()
        if position and position.current_qty > 0:
            return int(position.current_qty)

        # Fallback: ask Alpaca what we hold
        try:
            positions = await asyncio.to_thread(alpaca.get_positions)
            for p in positions:
                if p["ticker"] == trade.ticker:
                    qty = int(float(p["qty"]))
                    logger.warning(
                        f"Used Alpaca positions API for qty of {trade.ticker} — "
                        "local position record not found."
                    )
                    return qty
        except Exception as e:
            logger.error(f"Could not fetch position qty from Alpaca for {trade.ticker}: {e}")

        return 0

    return 0


async def _poll_for_fill(alpaca: AlpacaClient, order_id: str) -> Optional[dict]:
    """
    Poll Alpaca every 2 seconds until the order is filled or times out.
    Returns the fill dict (filled_avg_price, filled_qty) or None on timeout/cancellation.
    """
    elapsed = 0
    while elapsed < _POLL_TIMEOUT_SEC:
        await asyncio.sleep(_POLL_INTERVAL_SEC)
        elapsed += _POLL_INTERVAL_SEC
        try:
            status = await asyncio.to_thread(alpaca.get_order_status, order_id)
            if status["status"] == "filled" and status["filled_avg_price"]:
                return status
            if status["status"] in ("cancelled", "expired", "rejected"):
                logger.warning(f"Order {order_id} ended as: {status['status']}")
                return None
        except Exception as e:
            logger.warning(f"Error polling order {order_id}: {e}")

    logger.warning(f"Order {order_id} polling timed out after {_POLL_TIMEOUT_SEC}s.")
    return None


async def _update_position(
    db: AsyncSession,
    trade: TradeDecisionORM,
    filled_price: float,
    filled_qty: float,
) -> None:
    """
    Create or update the local Position record after a fill.

    BUY:  Create new position, or average into an existing one.
          Apply wash sale cost basis adjustment if applicable.
    SELL: Reduce position qty and record realized P&L.
          If fully closed, record wash sale if it was a loss.
    """
    result = await db.execute(
        select(Position).where(
            Position.ticker == trade.ticker,
            Position.sleeve == trade.sleeve,
            Position.is_open == True,  # noqa: E712
        )
    )
    position = result.scalars().first()

    if trade.action == "BUY":
        fill_cost = filled_price * filled_qty

        if position:
            # Average into existing position
            total_qty = position.current_qty + filled_qty
            total_cost = position.cost_basis + fill_cost
            position.current_qty = total_qty
            position.cost_basis = total_cost
            position.entry_price = total_cost / total_qty  # weighted avg
        else:
            position = Position(
                ticker=trade.ticker,
                sleeve=trade.sleeve,
                entry_price=filled_price,
                entry_date=date.today(),
                current_qty=filled_qty,
                cost_basis=fill_cost,
                is_open=True,
            )
            db.add(position)

        await db.flush()

        # Check for active wash sale — if so, adjust cost basis and mark rebought
        active_wash = await get_active_wash_sale(db, trade.ticker)
        if active_wash:
            disallowed_loss = active_wash.loss_amount
            position.adjusted_cost_basis = position.cost_basis + disallowed_loss
            trade.wash_sale_flagged = True
            await mark_rebought(db, trade.ticker)
            logger.info(
                f"Wash sale adjustment: {trade.ticker} "
                f"cost basis ${position.cost_basis:.2f} → ${position.adjusted_cost_basis:.2f} "
                f"(+${disallowed_loss:.2f} disallowed loss)"
            )

    elif trade.action == "SELL":
        if not position:
            logger.error(
                f"SELL executed for {trade.ticker} but no open position found in DB. "
                "Position records may be out of sync with Alpaca."
            )
            return

        cost_per_share = position.cost_basis / position.current_qty if position.current_qty > 0 else 0.0
        cost_of_sold = cost_per_share * filled_qty
        sell_proceeds = filled_price * filled_qty
        realized_pnl = sell_proceeds - cost_of_sold

        position.current_qty = max(0.0, position.current_qty - filled_qty)
        position.cost_basis = max(0.0, position.cost_basis - cost_of_sold)

        if position.current_qty <= 0.001:
            # Fully closed
            position.is_open = False
            position.closed_at = datetime.now(timezone.utc)
            position.realized_pnl = realized_pnl

            if realized_pnl < 0:
                await record_wash_sale(
                    db=db,
                    ticker=trade.ticker,
                    sale_date=date.today(),
                    loss_amount=abs(realized_pnl),
                    qty_sold=filled_qty,
                    sale_price=filled_price,
                    cost_basis_per_share=cost_per_share,
                )

        logger.info(
            f"Position updated: SELL {filled_qty:.0f} × {trade.ticker} @ ${filled_price:.2f} "
            f"— realized P&L: ${realized_pnl:+.2f}"
        )


async def _post_execution_checks(
    db: AsyncSession,
    trade: TradeDecisionORM,
    sleeve: str,
    settings,
) -> None:
    """
    After a fill, check if any circuit breakers should be triggered.
    Currently checks the daily loss limit for the sleeve.
    """
    # Only check after sells (that's when we realize losses)
    if trade.action != "SELL":
        return

    pnl = await get_today_realized_pnl(db, sleeve)
    sleeve_equity = (
        settings.penny_sleeve_allocation if sleeve == "PENNY" else settings.main_sleeve_allocation
    )
    loss_limit_pct = (
        settings.daily_loss_limit_penny_pct if sleeve == "PENNY" else settings.daily_loss_limit_main_pct
    )
    loss_limit_dollars = sleeve_equity * (loss_limit_pct / 100.0)

    if pnl < -loss_limit_dollars:
        if not await is_circuit_breaker_active(db, sleeve=sleeve):
            event_type = f"DAILY_LOSS_{sleeve}"
            await trigger_circuit_breaker(
                db=db,
                event_type=event_type,
                reason=(
                    f"{sleeve} sleeve lost ${abs(pnl):.2f} today "
                    f"(limit: ${loss_limit_dollars:.2f} / {loss_limit_pct}%)"
                ),
                sleeve=sleeve,
            )
            # Notify — import here to avoid circular dependency at module level
            from app.notifications.notifier import get_notifier

            await get_notifier().send(
                event_type="circuit_breaker",
                message=(
                    f"Circuit breaker triggered: {sleeve} sleeve daily loss limit reached. "
                    f"Lost ${abs(pnl):.2f} today (limit: ${loss_limit_dollars:.2f}). "
                    "Trading halted until manually resolved."
                ),
            )
            await ws_manager.broadcast(
                {
                    "type": "circuit_breaker",
                    "sleeve": sleeve,
                    "event_type": event_type,
                    "pnl_today": pnl,
                    "limit": -loss_limit_dollars,
                }
            )


def _get_settings():
    from app.config import get_settings
    return get_settings()
