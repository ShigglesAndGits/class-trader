"""
Alpaca client — prices, quotes, positions, account, orders.
Single source of truth for broker interaction in the data layer.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.models import Position

from app.config import get_settings

logger = logging.getLogger(__name__)


class AlpacaClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.alpaca_api_key
        self._secret_key = settings.alpaca_secret_key
        self._paper = settings.alpaca_paper

        self._trading = TradingClient(
            api_key=self._api_key,
            secret_key=self._secret_key,
            paper=self._paper,
        )
        self._data = StockHistoricalDataClient(
            api_key=self._api_key,
            secret_key=self._secret_key,
        )

    # ── Account ────────────────────────────────────────────────────────────

    def get_account(self) -> dict:
        """Return account details including equity and cash balance."""
        try:
            account = self._trading.get_account()
            return {
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
                "pattern_day_trader": account.pattern_day_trader,
                "trading_blocked": account.trading_blocked,
                "account_blocked": account.account_blocked,
                "currency": account.currency,
            }
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca account: {e}")
            raise

    # ── Positions ──────────────────────────────────────────────────────────

    def get_positions(self) -> list[dict]:
        """Return all open positions."""
        try:
            positions: list[Position] = self._trading.get_all_positions()
            return [
                {
                    "ticker": p.symbol,
                    "qty": float(p.qty),
                    "market_value": float(p.market_value),
                    "cost_basis": float(p.cost_basis),
                    "unrealized_pnl": float(p.unrealized_pl),
                    "unrealized_pnl_pct": float(p.unrealized_plpc),
                    "current_price": float(p.current_price),
                    "avg_entry_price": float(p.avg_entry_price),
                    "side": p.side.value,
                }
                for p in positions
            ]
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca positions: {e}")
            raise

    # ── Price bars ─────────────────────────────────────────────────────────

    def get_daily_bars(
        self,
        tickers: list[str],
        lookback_days: int = 30,
    ) -> dict[str, list[dict]]:
        """Return daily OHLCV bars for the given tickers."""
        start = date.today() - timedelta(days=lookback_days)
        try:
            request = StockBarsRequest(
                symbol_or_symbols=tickers,
                timeframe=TimeFrame.Day,
                start=start.isoformat(),
            )
            bars = self._data.get_stock_bars(request)
            result: dict[str, list[dict]] = {}
            for ticker in tickers:
                if ticker in bars.data:
                    result[ticker] = [
                        {
                            "timestamp": str(bar.timestamp),
                            "open": float(bar.open),
                            "high": float(bar.high),
                            "low": float(bar.low),
                            "close": float(bar.close),
                            "volume": int(bar.volume),
                            "vwap": float(bar.vwap) if bar.vwap else None,
                        }
                        for bar in bars.data[ticker]
                    ]
                else:
                    result[ticker] = []
            return result
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca bars for {tickers}: {e}")
            raise

    # ── Latest quotes ──────────────────────────────────────────────────────

    def get_latest_quotes(self, tickers: list[str]) -> dict[str, dict]:
        """Return latest bid/ask quotes for the given tickers."""
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=tickers)
            quotes = self._data.get_stock_latest_quote(request)
            return {
                ticker: {
                    "ask_price": float(q.ask_price) if q.ask_price else None,
                    "bid_price": float(q.bid_price) if q.bid_price else None,
                    "mid_price": (
                        (float(q.ask_price) + float(q.bid_price)) / 2
                        if q.ask_price and q.bid_price
                        else None
                    ),
                    "timestamp": str(q.timestamp),
                }
                for ticker, q in quotes.items()
            }
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca quotes for {tickers}: {e}")
            raise

    # ── Order submission ────────────────────────────────────────────────────

    def submit_market_order(self, ticker: str, qty: float, side: str) -> dict:
        """
        Submit a market day order.
        side: "buy" or "sell"
        Returns a dict with order_id, status, and submitted_at.
        """
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        alpaca_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        request = MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=alpaca_side,
            time_in_force=TimeInForce.DAY,
        )
        try:
            order = self._trading.submit_order(request)
            logger.info(f"Order submitted: {side} {qty} {ticker} — id={order.id}")
            return {
                "order_id": str(order.id),
                "ticker": order.symbol,
                "side": order.side.value,
                "qty": float(order.qty),
                "status": order.status.value,
                "submitted_at": str(order.submitted_at),
            }
        except Exception as e:
            logger.error(f"Failed to submit {side} order for {ticker}: {e}")
            raise

    def get_order_status(self, order_id: str) -> dict:
        """
        Fetch order status by ID.
        Returns filled_avg_price and filled_qty when the order has filled.
        """
        try:
            order = self._trading.get_order_by_id(order_id)
            return {
                "order_id": str(order.id),
                "status": order.status.value,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0.0,
                "filled_avg_price": (
                    float(order.filled_avg_price) if order.filled_avg_price else None
                ),
                "filled_at": str(order.filled_at) if order.filled_at else None,
            }
        except Exception as e:
            logger.error(f"Failed to get order status for {order_id}: {e}")
            raise

    def cancel_order(self, order_id: str) -> None:
        """Cancel an open order by ID. No-ops if already filled."""
        try:
            self._trading.cancel_order_by_id(order_id)
            logger.info(f"Order {order_id} cancelled.")
        except Exception as e:
            logger.warning(f"Cancel order {order_id} failed (may already be filled): {e}")

    # ── Connectivity check ─────────────────────────────────────────────────

    def ping(self) -> dict:
        """Quick connectivity check — returns account equity."""
        account = self.get_account()
        return {
            "ok": True,
            "mode": "paper" if self._paper else "LIVE",
            "equity": account["equity"],
        }
