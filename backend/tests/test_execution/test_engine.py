"""
Unit tests for app.execution.engine

The full execute_trade() flow integrates deeply with Alpaca polling and asyncio.sleep,
so tests focus on the internal helper that contains meaningful pure logic:

  _calculate_qty — quantity calculation for BUY and SELL orders

Tests for BUY:
  - MAIN sleeve: floor(size_pct% × main_equity / price)
  - PENNY sleeve: same, but hard-capped at max_position_dollars_penny
  - PENNY sleeve when calculated amount is below the cap (cap not applied)

Tests for SELL:
  - DB has an open position → returns its qty
  - DB has no position, Alpaca fallback returns an empty list → 0
  - DB has no position, Alpaca fallback raises → 0
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.execution.engine import _calculate_qty


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_settings(**overrides):
    s = MagicMock()
    s.main_sleeve_allocation = overrides.get('main_sleeve_allocation', 75.0)
    s.penny_sleeve_allocation = overrides.get('penny_sleeve_allocation', 25.0)
    s.max_position_dollars_penny = overrides.get('max_position_dollars_penny', 8.0)
    return s


def _mock_trade(action='BUY', sleeve='MAIN', ticker='AAPL', position_size_pct=20.0):
    t = MagicMock()
    t.action = action
    t.sleeve = sleeve
    t.ticker = ticker
    t.position_size_pct = position_size_pct
    return t


def _make_db_sell(position=None):
    """DB mock that returns `position` from scalars().first()."""
    db = AsyncMock()
    db.execute.return_value.scalars.return_value.first.return_value = position
    return db


# ── BUY: MAIN sleeve ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buy_main_calculates_correct_qty():
    """
    MAIN, 20% position size, $75 sleeve, $5/share →
    floor(0.20 × 75 / 5) = floor(3.0) = 3 shares
    """
    settings = _mock_settings(main_sleeve_allocation=75.0)
    trade = _mock_trade(action='BUY', sleeve='MAIN', position_size_pct=20.0)

    qty = await _calculate_qty(AsyncMock(), MagicMock(), trade, 5.0, settings)

    assert qty == 3


@pytest.mark.asyncio
async def test_buy_main_floors_fractional_shares():
    """
    floor(0.20 × 75 / 7) = floor(2.14) = 2 shares — fractional shares not allowed.
    """
    settings = _mock_settings(main_sleeve_allocation=75.0)
    trade = _mock_trade(action='BUY', sleeve='MAIN', position_size_pct=20.0)

    qty = await _calculate_qty(AsyncMock(), MagicMock(), trade, 7.0, settings)

    assert qty == 2


# ── BUY: PENNY sleeve ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buy_penny_capped_at_max_dollars():
    """
    PENNY, size_pct=100% → 100% × $25 = $25, cap is $8, price=$2.00 →
    floor(8 / 2) = 4 shares (not floor(25 / 2) = 12).
    """
    settings = _mock_settings(penny_sleeve_allocation=25.0, max_position_dollars_penny=8.0)
    trade = _mock_trade(action='BUY', sleeve='PENNY', position_size_pct=100.0)

    qty = await _calculate_qty(AsyncMock(), MagicMock(), trade, 2.0, settings)

    assert qty == 4   # capped at $8 / $2


@pytest.mark.asyncio
async def test_buy_penny_under_cap_uses_pct():
    """
    PENNY, size_pct=20% → 20% × $25 = $5 < $8 cap, price=$1.00 →
    floor(5 / 1) = 5 shares (cap not applied).
    """
    settings = _mock_settings(penny_sleeve_allocation=25.0, max_position_dollars_penny=8.0)
    trade = _mock_trade(action='BUY', sleeve='PENNY', position_size_pct=20.0)

    qty = await _calculate_qty(AsyncMock(), MagicMock(), trade, 1.0, settings)

    assert qty == 5


# ── SELL: DB hit ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sell_returns_qty_from_db_position():
    """Open position found in DB → returns its qty (no Alpaca call needed)."""
    mock_pos = MagicMock()
    mock_pos.current_qty = 10.0
    db = _make_db_sell(position=mock_pos)

    trade = _mock_trade(action='SELL', sleeve='MAIN', ticker='AAPL')

    qty = await _calculate_qty(db, MagicMock(), trade, 50.0, _mock_settings())

    assert qty == 10


# ── SELL: DB miss ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sell_returns_zero_when_no_position_and_alpaca_empty():
    """
    No open position in DB + Alpaca returns no matching ticker →
    nothing to sell → qty=0.
    """
    db = _make_db_sell(position=None)
    trade = _mock_trade(action='SELL', sleeve='MAIN', ticker='AAPL')

    # Alpaca returns a list with a different ticker — no match for AAPL
    alpaca_positions = [{"ticker": "MSFT", "qty": "5"}]
    with patch('asyncio.to_thread', new=AsyncMock(return_value=alpaca_positions)):
        qty = await _calculate_qty(db, MagicMock(), trade, 50.0, _mock_settings())

    assert qty == 0


@pytest.mark.asyncio
async def test_sell_returns_zero_when_alpaca_raises():
    """No position in DB + Alpaca API call fails → returns 0 gracefully."""
    db = _make_db_sell(position=None)
    trade = _mock_trade(action='SELL', sleeve='MAIN', ticker='AAPL')

    with patch('asyncio.to_thread', new=AsyncMock(side_effect=Exception("Alpaca timeout"))):
        qty = await _calculate_qty(db, MagicMock(), trade, 50.0, _mock_settings())

    assert qty == 0
