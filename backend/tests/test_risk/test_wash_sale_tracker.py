"""
Unit tests for app.execution.wash_sale_tracker

Four public functions are tested independently:
  record_wash_sale     — creates a WashSale ORM row from execution-engine data
  is_wash_sale_blocked — query: hard-blocked December rebuy?
  get_active_wash_sale — query: any open wash sale window?
  mark_rebought        — update: flip rebought=True after a fill

Tests that exercise DB queries mock db.execute() so no real session is needed.
Tests for mark_rebought patch get_active_wash_sale at the module level.
"""
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.execution.wash_sale_tracker import (
    get_active_wash_sale,
    is_wash_sale_blocked,
    mark_rebought,
    record_wash_sale,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_db_returning(record):
    """
    Return an AsyncMock db whose execute() → scalars() → first() chain
    resolves to `record`.  Used for query-path tests.
    """
    db = AsyncMock()
    db.execute.return_value.scalars.return_value.first.return_value = record
    return db


# ── record_wash_sale ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_december_sale_sets_year_end_blocked():
    """Sale in December → is_year_end_blocked=True."""
    db = AsyncMock()

    result = await record_wash_sale(
        db=db, ticker='AAPL', sale_date=date(2025, 12, 15),
        loss_amount=50.0, qty_sold=10.0,
        sale_price=95.0, cost_basis_per_share=100.0,
    )

    assert result.is_year_end_blocked is True


@pytest.mark.asyncio
async def test_non_december_sale_clears_year_end_blocked():
    """Sale outside December → is_year_end_blocked=False."""
    db = AsyncMock()

    result = await record_wash_sale(
        db=db, ticker='AAPL', sale_date=date(2025, 10, 15),
        loss_amount=50.0, qty_sold=10.0,
        sale_price=95.0, cost_basis_per_share=100.0,
    )

    assert result.is_year_end_blocked is False


@pytest.mark.asyncio
async def test_blackout_until_is_thirty_days_after_sale():
    """blackout_until == sale_date + 30 days (IRS window)."""
    db = AsyncMock()
    sale_date = date(2025, 10, 1)

    result = await record_wash_sale(
        db=db, ticker='TSLA', sale_date=sale_date,
        loss_amount=20.0, qty_sold=5.0,
        sale_price=200.0, cost_basis_per_share=204.0,
    )

    assert result.blackout_until == sale_date + timedelta(days=30)


@pytest.mark.asyncio
async def test_record_wash_sale_adds_and_flushes(db):
    """record_wash_sale must call db.add() and await db.flush()."""
    await record_wash_sale(
        db=db, ticker='MEME', sale_date=date(2025, 9, 10),
        loss_amount=5.0, qty_sold=100.0,
        sale_price=0.50, cost_basis_per_share=0.55,
    )

    db.add.assert_called_once()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_wash_sale_stores_correct_ticker_and_loss(db):
    """Fields passed in are faithfully stored on the returned ORM object."""
    result = await record_wash_sale(
        db=db, ticker='GME', sale_date=date(2025, 8, 20),
        loss_amount=123.45, qty_sold=7.0,
        sale_price=15.0, cost_basis_per_share=32.64,
    )

    assert result.ticker == 'GME'
    assert result.loss_amount == 123.45
    assert result.sale_price == 15.0


# ── is_wash_sale_blocked ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_is_wash_sale_blocked_true_when_record_exists():
    """DB returns a matching record → True (hard-blocked)."""
    db = _make_db_returning(MagicMock())  # non-None → record found
    assert await is_wash_sale_blocked(db, 'AAPL') is True


@pytest.mark.asyncio
async def test_is_wash_sale_blocked_false_when_no_record():
    """DB returns nothing → False (not blocked)."""
    db = _make_db_returning(None)
    assert await is_wash_sale_blocked(db, 'AAPL') is False


# ── get_active_wash_sale ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_active_wash_sale_returns_record_when_window_open():
    """DB returns a WashSale object → that same object is returned."""
    mock_ws = MagicMock()
    db = _make_db_returning(mock_ws)

    result = await get_active_wash_sale(db, 'AAPL')

    assert result is mock_ws


@pytest.mark.asyncio
async def test_get_active_wash_sale_returns_none_when_no_window():
    """No open wash sale window → None."""
    db = _make_db_returning(None)
    assert await get_active_wash_sale(db, 'AAPL') is None


# ── mark_rebought ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_rebought_sets_rebought_flag(db):
    """Active wash sale exists → rebought=True and rebought_at is populated."""
    mock_ws = MagicMock()
    mock_ws.loss_amount = 42.0

    with patch(
        'app.execution.wash_sale_tracker.get_active_wash_sale',
        new=AsyncMock(return_value=mock_ws),
    ):
        result = await mark_rebought(db, 'AAPL')

    assert result is mock_ws
    assert result.rebought is True
    assert result.rebought_at is not None


@pytest.mark.asyncio
async def test_mark_rebought_returns_none_when_no_active_sale(db):
    """No active wash sale → returns None without error."""
    with patch(
        'app.execution.wash_sale_tracker.get_active_wash_sale',
        new=AsyncMock(return_value=None),
    ):
        result = await mark_rebought(db, 'GOOG')

    assert result is None
