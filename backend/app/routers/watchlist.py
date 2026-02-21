"""
Watchlist API — CRUD for tracked tickers.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.watchlist import Watchlist

logger = logging.getLogger(__name__)
router = APIRouter()


class AddTickerRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    sleeve: str = Field(pattern="^(MAIN|PENNY|BENCHMARK)$")
    notes: str | None = None


class UpdateTickerRequest(BaseModel):
    notes: str | None = None
    is_active: bool | None = None


@router.get("/")
async def get_watchlist(db: AsyncSession = Depends(get_db)):
    """All watchlist entries, active and inactive, grouped by sleeve."""
    result = await db.execute(
        select(Watchlist).order_by(Watchlist.sleeve, Watchlist.ticker)
    )
    entries = result.scalars().all()

    def _entry(w: Watchlist) -> dict:
        return {
            "id": w.id,
            "ticker": w.ticker,
            "sleeve": w.sleeve,
            "is_active": w.is_active,
            "notes": w.notes,
            "added_at": w.added_at.isoformat() if w.added_at else None,
        }

    return {
        "tickers": [_entry(w) for w in entries],
        "active_count": sum(1 for w in entries if w.is_active),
        "total_count": len(entries),
    }


@router.post("/")
async def add_ticker(body: AddTickerRequest, db: AsyncSession = Depends(get_db)):
    """Add a ticker to the watchlist. Reactivates if previously deactivated."""
    ticker = body.ticker.upper().strip()

    # Check if already exists
    result = await db.execute(
        select(Watchlist).where(
            Watchlist.ticker == ticker,
            Watchlist.sleeve == body.sleeve,
        )
    )
    existing = result.scalars().first()

    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=409,
                detail=f"{ticker} ({body.sleeve}) is already on the watchlist.",
            )
        # Reactivate
        existing.is_active = True
        if body.notes:
            existing.notes = body.notes
        await db.flush()
        return {"status": "reactivated", "ticker": ticker, "sleeve": body.sleeve}

    entry = Watchlist(
        ticker=ticker,
        sleeve=body.sleeve,
        notes=body.notes,
        is_active=True,
    )
    db.add(entry)
    await db.flush()
    logger.info(f"Watchlist: added {ticker} ({body.sleeve})")
    return {"status": "added", "ticker": ticker, "sleeve": body.sleeve, "id": entry.id}


@router.patch("/{entry_id}")
async def update_ticker(
    entry_id: int,
    body: UpdateTickerRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update notes or active status for a watchlist entry."""
    result = await db.execute(
        select(Watchlist).where(Watchlist.id == entry_id)
    )
    entry = result.scalars().first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Watchlist entry #{entry_id} not found.")

    if body.notes is not None:
        entry.notes = body.notes
    if body.is_active is not None:
        entry.is_active = body.is_active

    await db.flush()
    return {"status": "updated", "id": entry_id}


@router.delete("/{entry_id}")
async def remove_ticker(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Deactivate a watchlist entry (soft delete)."""
    result = await db.execute(
        select(Watchlist).where(Watchlist.id == entry_id)
    )
    entry = result.scalars().first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Watchlist entry #{entry_id} not found.")

    entry.is_active = False
    await db.flush()
    logger.info(f"Watchlist: deactivated {entry.ticker} ({entry.sleeve})")
    return {"status": "removed", "ticker": entry.ticker, "sleeve": entry.sleeve}
