"""
Unit tests for app.execution.risk_manager.check_trade

Each test isolates one logical gate. DB-dependent sub-calls
(is_circuit_breaker_active, is_wash_sale_blocked, get_active_wash_sale)
are mocked so tests run without a real database.

Patch targets:
  app.config.get_settings                            — called inside check_trade
  app.execution.risk_manager.is_circuit_breaker_active — same-module async func
  app.execution.wash_sale_tracker.is_wash_sale_blocked — local import inside func
  app.execution.wash_sale_tracker.get_active_wash_sale — local import inside func
"""
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.execution.risk_manager import check_trade
from tests.conftest import mock_settings


# ── Helpers ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def _patch_all(
    settings=None,
    circuit_breaker_active: bool = False,
    wash_sale_blocked: bool = False,
    active_wash_sale=None,
):
    """Apply all standard mocks for check_trade sub-calls in one go."""
    if settings is None:
        settings = mock_settings()
    with (
        patch('app.config.get_settings', return_value=settings),
        patch(
            'app.execution.risk_manager.is_circuit_breaker_active',
            new=AsyncMock(return_value=circuit_breaker_active),
        ),
        patch(
            'app.execution.wash_sale_tracker.is_wash_sale_blocked',
            new=AsyncMock(return_value=wash_sale_blocked),
        ),
        patch(
            'app.execution.wash_sale_tracker.get_active_wash_sale',
            new=AsyncMock(return_value=active_wash_sale),
        ),
    ):
        yield


# ── Confidence gate ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confidence_gate_blocks_main_sleeve_below_065(db):
    """MAIN sleeve: confidence < 0.65 → blocked, no DB calls needed."""
    async with _patch_all():
        result = await check_trade(
            db=db, ticker='AAPL', action='BUY', sleeve='MAIN',
            confidence=0.50, position_size_pct=10.0,
            current_positions_count=0, is_new_ticker=False,
        )

    assert result.allowed is False
    assert result.blocked_reason is not None
    assert '0.65' in result.blocked_reason or '65%' in result.blocked_reason


@pytest.mark.asyncio
async def test_confidence_gate_blocks_penny_sleeve_below_060(db):
    """PENNY sleeve: confidence < 0.60 → blocked."""
    async with _patch_all():
        result = await check_trade(
            db=db, ticker='MEME', action='BUY', sleeve='PENNY',
            confidence=0.55, position_size_pct=5.0,
            current_positions_count=0, is_new_ticker=False,
        )

    assert result.allowed is False


@pytest.mark.asyncio
async def test_confidence_gate_penny_allows_062_above_min(db):
    """PENNY sleeve: 0.62 is above 0.60 minimum — should pass the gate."""
    async with _patch_all():
        result = await check_trade(
            db=db, ticker='MEME', action='BUY', sleeve='PENNY',
            confidence=0.62, position_size_pct=5.0,
            current_positions_count=0, is_new_ticker=False,
        )

    # 0.62 > 0.60 → gate passes. But 0.62 < 0.70 auto-approve threshold for PENNY (0.60 is fine)
    # Actually for PENNY, auto_approve_conf = 0.60, so 0.62 >= 0.60, no manual override.
    assert result.allowed is True


# ── Position size limit ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_oversized_position_blocks_main_sleeve(db):
    """BUY with position_size_pct > 30.0 in MAIN sleeve → blocked."""
    async with _patch_all():
        result = await check_trade(
            db=db, ticker='AAPL', action='BUY', sleeve='MAIN',
            confidence=0.80, position_size_pct=35.0,  # exceeds 30%
            current_positions_count=0, is_new_ticker=False,
        )

    assert result.allowed is False
    assert result.blocked_reason is not None
    assert '35.0%' in result.blocked_reason or '30%' in result.blocked_reason


@pytest.mark.asyncio
async def test_sell_ignores_position_size_limit(db):
    """SELL actions skip the size limit check — size is position liquidation, not new capital."""
    async with _patch_all():
        result = await check_trade(
            db=db, ticker='AAPL', action='SELL', sleeve='MAIN',
            confidence=0.80, position_size_pct=40.0,  # would block a BUY
            current_positions_count=5, is_new_ticker=False,
        )

    assert result.allowed is True


# ── Max concurrent positions ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_max_positions_blocks_main_at_8(db):
    """MAIN sleeve: 8 open positions → new BUY blocked."""
    async with _patch_all():
        result = await check_trade(
            db=db, ticker='TSLA', action='BUY', sleeve='MAIN',
            confidence=0.80, position_size_pct=10.0,
            current_positions_count=8,  # at capacity
            is_new_ticker=False,
        )

    assert result.allowed is False
    assert '8' in (result.blocked_reason or '')


@pytest.mark.asyncio
async def test_max_positions_blocks_penny_at_5(db):
    """PENNY sleeve: 5 open positions → new BUY blocked."""
    async with _patch_all():
        result = await check_trade(
            db=db, ticker='MEME', action='BUY', sleeve='PENNY',
            confidence=0.75, position_size_pct=5.0,
            current_positions_count=5,  # at capacity
            is_new_ticker=False,
        )

    assert result.allowed is False


@pytest.mark.asyncio
async def test_sell_ignores_position_capacity(db):
    """Capacity check only applies to BUY — SELL is always allowed."""
    async with _patch_all():
        result = await check_trade(
            db=db, ticker='AAPL', action='SELL', sleeve='MAIN',
            confidence=0.80, position_size_pct=10.0,
            current_positions_count=8,  # would block a BUY
            is_new_ticker=False,
        )

    assert result.allowed is True


# ── Circuit breaker ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_active_circuit_breaker_blocks_trade(db):
    """An active circuit breaker halts all trades for the sleeve."""
    async with _patch_all(circuit_breaker_active=True):
        result = await check_trade(
            db=db, ticker='AAPL', action='BUY', sleeve='MAIN',
            confidence=0.90, position_size_pct=10.0,
            current_positions_count=0, is_new_ticker=False,
        )

    assert result.allowed is False
    assert 'circuit breaker' in (result.blocked_reason or '').lower()


@pytest.mark.asyncio
async def test_no_circuit_breaker_allows_trade(db):
    """With no active circuit breaker, a clean trade passes through."""
    async with _patch_all(circuit_breaker_active=False):
        result = await check_trade(
            db=db, ticker='AAPL', action='BUY', sleeve='MAIN',
            confidence=0.80, position_size_pct=10.0,
            current_positions_count=0, is_new_ticker=False,
        )

    assert result.allowed is True


# ── Wash sale ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_december_wash_sale_hard_blocks_rebuy(db):
    """is_wash_sale_blocked=True → BUY hard-blocked."""
    async with _patch_all(wash_sale_blocked=True):
        result = await check_trade(
            db=db, ticker='AAPL', action='BUY', sleeve='MAIN',
            confidence=0.80, position_size_pct=10.0,
            current_positions_count=0, is_new_ticker=False,
        )

    assert result.allowed is False
    assert 'wash sale' in (result.blocked_reason or '').lower()


@pytest.mark.asyncio
async def test_active_wash_sale_window_flags_but_allows(db):
    """Active wash sale outside December: trade allowed but wash_sale_flag=True."""
    mock_wash_sale = MagicMock()
    mock_wash_sale.sale_date = date(2025, 10, 1)
    mock_wash_sale.blackout_until = date(2025, 10, 31)

    async with _patch_all(wash_sale_blocked=False, active_wash_sale=mock_wash_sale):
        result = await check_trade(
            db=db, ticker='AAPL', action='BUY', sleeve='MAIN',
            confidence=0.80, position_size_pct=10.0,
            current_positions_count=0, is_new_ticker=False,
        )

    assert result.allowed is True
    assert result.wash_sale_flag is True
    assert len(result.notes) > 0


@pytest.mark.asyncio
async def test_sell_skips_wash_sale_checks(db):
    """Wash sale checks only apply to BUY actions."""
    # Even with wash_sale_blocked=True, a SELL should pass
    async with _patch_all(wash_sale_blocked=True):
        result = await check_trade(
            db=db, ticker='AAPL', action='SELL', sleeve='MAIN',
            confidence=0.80, position_size_pct=10.0,
            current_positions_count=0, is_new_ticker=False,
        )

    assert result.allowed is True


# ── Auto-approve override conditions ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_new_ticker_forces_manual_approval(db):
    """First-time position requires manual review even if auto-approve is ON."""
    async with _patch_all():
        result = await check_trade(
            db=db, ticker='NEWCO', action='BUY', sleeve='MAIN',
            confidence=0.80, position_size_pct=10.0,
            current_positions_count=0,
            is_new_ticker=True,  # <-- triggers manual requirement
        )

    assert result.allowed is True
    assert result.requires_manual_approval is True
    assert any('first-time' in n.lower() or 'new' in n.lower() for n in result.notes)


@pytest.mark.asyncio
async def test_oversized_pct_forces_manual_when_not_blocked(db):
    """
    position_size_pct > 30% forces manual approval.
    Note: the hard block is at max_position_pct_main (also 30% by default),
    so to test the manual override we need a setting where the two thresholds differ.
    This test uses a custom settings with max_position_pct_main=40% so the
    trade isn't hard-blocked but the >30% manual override still fires.
    """
    async with _patch_all(settings=mock_settings(max_position_pct_main=40.0)):
        result = await check_trade(
            db=db, ticker='AAPL', action='BUY', sleeve='MAIN',
            confidence=0.80,
            position_size_pct=32.0,  # > 30% → manual, < 40% → not blocked
            current_positions_count=0,
            is_new_ticker=False,
        )

    assert result.allowed is True
    assert result.requires_manual_approval is True


@pytest.mark.asyncio
async def test_low_confidence_between_thresholds_forces_manual_main(db):
    """
    MAIN sleeve: confidence 0.65–0.69 passes the gate but requires manual review
    because the auto-approve threshold is 0.70.
    """
    async with _patch_all():
        result = await check_trade(
            db=db, ticker='AAPL', action='BUY', sleeve='MAIN',
            confidence=0.67,  # above min 0.65, below auto-approve 0.70
            position_size_pct=10.0,
            current_positions_count=0, is_new_ticker=False,
        )

    assert result.allowed is True
    assert result.requires_manual_approval is True


@pytest.mark.asyncio
async def test_high_confidence_clean_buy_fully_auto_approvable(db):
    """A textbook clean BUY: high confidence, existing ticker, reasonable size."""
    async with _patch_all():
        result = await check_trade(
            db=db, ticker='AAPL', action='BUY', sleeve='MAIN',
            confidence=0.85, position_size_pct=15.0,
            current_positions_count=2, is_new_ticker=False,
        )

    assert result.allowed is True
    assert result.requires_manual_approval is False
    assert result.wash_sale_flag is False
