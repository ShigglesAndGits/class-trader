"""
Unit tests for app.execution.approval_queue

Covers the three public helper functions:

  approve_trade          — PENDING → APPROVED, triggers execute_trade
  reject_trade           — PENDING → REJECTED, no execution
  get_pending_approvals  — returns list of PENDING TradeDecision rows

process_new_decisions is an orchestration wrapper around check_trade +
execute_trade; its core branching (block/auto-approve/manual) is covered by
the integration of risk_manager + approval logic. Full integration tests
would require a live DB and Alpaca connection, so they live in Phase 6.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.execution.approval_queue import (
    approve_trade,
    get_pending_approvals,
    reject_trade,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pending_trade(trade_id: int = 1, status: str = "PENDING"):
    t = MagicMock()
    t.id = trade_id
    t.status = status
    t.ticker = "AAPL"
    t.action = "BUY"
    t.sleeve = "MAIN"
    t.confidence = 0.75
    t.position_size_pct = 10.0
    t.reasoning = "Bull thesis intact."
    t.wash_sale_flagged = False
    return t


def _make_db(trade=None):
    """DB mock that returns `trade` from a single-row query."""
    db = AsyncMock()
    db.execute.return_value.scalars.return_value.first.return_value = trade
    return db


# ── approve_trade ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_trade_sets_status_and_executes():
    """PENDING trade → status=APPROVED, execute_trade invoked."""
    trade = _pending_trade(status="PENDING")
    db = _make_db(trade)

    with patch('app.execution.engine.execute_trade', new=AsyncMock()) as mock_exec:
        result = await approve_trade(db, trade_id=1, resolved_by="MANUAL")

    assert result is trade
    assert trade.status == "APPROVED"
    assert trade.resolved_by == "MANUAL"
    assert trade.resolved_at is not None
    mock_exec.assert_awaited_once_with(db, trade)


@pytest.mark.asyncio
async def test_approve_trade_records_resolved_at_timestamp():
    """resolved_at is a timezone-aware datetime set during approval."""
    trade = _pending_trade(status="PENDING")
    db = _make_db(trade)

    before = datetime.now(timezone.utc)
    with patch('app.execution.engine.execute_trade', new=AsyncMock()):
        await approve_trade(db, trade_id=1)
    after = datetime.now(timezone.utc)

    assert before <= trade.resolved_at <= after


@pytest.mark.asyncio
async def test_approve_trade_skips_non_pending(db):
    """Trade that is already APPROVED/REJECTED is returned unchanged."""
    trade = _pending_trade(status="APPROVED")
    db = _make_db(trade)

    with patch('app.execution.engine.execute_trade', new=AsyncMock()) as mock_exec:
        result = await approve_trade(db, trade_id=1)

    assert result is trade
    assert trade.status == "APPROVED"    # unchanged
    mock_exec.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_trade_returns_none_for_missing_id(db):
    """Trade ID not found → returns None without crashing."""
    db = _make_db(trade=None)
    result = await approve_trade(db, trade_id=999)
    assert result is None


# ── reject_trade ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_trade_sets_status_rejected():
    """PENDING trade → status=REJECTED, no execute_trade call."""
    trade = _pending_trade(status="PENDING")
    db = _make_db(trade)

    with patch('app.execution.engine.execute_trade', new=AsyncMock()) as mock_exec:
        result = await reject_trade(db, trade_id=1, resolved_by="MANUAL")

    assert result is trade
    assert trade.status == "REJECTED"
    assert trade.resolved_by == "MANUAL"
    assert trade.resolved_at is not None
    mock_exec.assert_not_awaited()


@pytest.mark.asyncio
async def test_reject_trade_skips_non_pending():
    """Already-resolved trade is returned unchanged."""
    trade = _pending_trade(status="REJECTED")
    db = _make_db(trade)

    result = await reject_trade(db, trade_id=1)

    assert result is trade
    assert trade.status == "REJECTED"  # unchanged


@pytest.mark.asyncio
async def test_reject_trade_returns_none_for_missing_id():
    """Trade ID not found → returns None without crashing."""
    db = _make_db(trade=None)
    result = await reject_trade(db, trade_id=999)
    assert result is None


# ── get_pending_approvals ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_pending_approvals_returns_list():
    """Returns the list of pending trades from the DB query."""
    trades = [_pending_trade(1), _pending_trade(2)]
    db = AsyncMock()
    db.execute.return_value.scalars.return_value.all.return_value = trades

    result = await get_pending_approvals(db)

    assert result == trades
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_pending_approvals_empty_when_none_pending():
    """Returns an empty list when nothing is pending."""
    db = AsyncMock()
    db.execute.return_value.scalars.return_value.all.return_value = []

    result = await get_pending_approvals(db)

    assert result == []
