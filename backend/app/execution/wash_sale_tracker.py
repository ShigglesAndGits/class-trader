"""
Wash sale tracking service.

Records loss-generating sells and enforces IRS wash sale rules:
  - Tracks 30-day rebuy windows with informational flags (outside December)
  - Hard-blocks rebuys of loss-sold tickers during December (year-end protection)
  - Adjusts cost basis on rebought positions to disallow the paper loss

The execution engine calls this module after fills. The risk manager reads it
before approvals. Nothing here makes trade decisions — it just keeps receipts.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import WashSale

logger = logging.getLogger(__name__)


async def record_wash_sale(
    db: AsyncSession,
    ticker: str,
    sale_date: date,
    loss_amount: float,
    qty_sold: float,
    sale_price: float,
    cost_basis_per_share: float,
) -> WashSale:
    """
    Record a loss-generating sell as a potential wash sale event.
    Called by the execution engine after a sell fills at a loss.

    blackout_until = sale_date + 30 days (IRS 30-day window).
    is_year_end_blocked = True if the sale occurs in December.
    """
    blackout_until = sale_date + timedelta(days=30)
    is_year_end_blocked = sale_date.month == 12

    wash_sale = WashSale(
        ticker=ticker,
        sale_date=sale_date,
        loss_amount=loss_amount,
        qty_sold=qty_sold,
        sale_price=sale_price,
        cost_basis=cost_basis_per_share,
        blackout_until=blackout_until,
        is_year_end_blocked=is_year_end_blocked,
    )
    db.add(wash_sale)
    await db.flush()

    msg = (
        f"Wash sale recorded: {ticker} sold at ${sale_price:.2f} "
        f"(loss ${loss_amount:.2f}, blackout until {blackout_until})"
    )
    if is_year_end_blocked:
        msg += " — DECEMBER: rebuy hard-blocked."
    logger.warning(msg)

    return wash_sale


async def is_wash_sale_blocked(db: AsyncSession, ticker: str) -> bool:
    """
    Returns True if a BUY of this ticker is hard-blocked.
    Only applies when the original loss-sell occurred in December
    (year-end wash sale protection).
    """
    today = date.today()
    result = await db.execute(
        select(WashSale).where(
            WashSale.ticker == ticker,
            WashSale.is_year_end_blocked == True,  # noqa: E712
            WashSale.blackout_until >= today,
            WashSale.rebought == False,  # noqa: E712
        )
    )
    return result.scalars().first() is not None


async def get_active_wash_sale(db: AsyncSession, ticker: str) -> Optional[WashSale]:
    """
    Returns the most recent active WashSale record for this ticker if one exists,
    or None if there's no open window.

    Used to flag (but not block) rebuys outside December, and to calculate
    adjusted cost basis when the rebuy does happen.
    """
    today = date.today()
    result = await db.execute(
        select(WashSale)
        .where(
            WashSale.ticker == ticker,
            WashSale.blackout_until >= today,
            WashSale.rebought == False,  # noqa: E712
        )
        .order_by(WashSale.sale_date.desc())
    )
    return result.scalars().first()


async def mark_rebought(db: AsyncSession, ticker: str) -> Optional[WashSale]:
    """
    Mark the most recent active wash sale for this ticker as rebought.
    Called by the execution engine after a BUY fills during an active window.

    The disallowed loss amount is tracked for cost basis adjustment,
    which the caller is responsible for applying to the new position.
    """
    wash_sale = await get_active_wash_sale(db, ticker)
    if wash_sale:
        wash_sale.rebought = True
        wash_sale.rebought_at = datetime.now(timezone.utc)
        logger.info(
            f"Wash sale marked rebought: {ticker} "
            f"(disallowed loss ${wash_sale.loss_amount:.2f} added to cost basis)"
        )
    return wash_sale
