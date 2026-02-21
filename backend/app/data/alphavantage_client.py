"""
Alpha Vantage client — technical indicators (RSI, MACD, Bollinger Bands).
25 calls/day free. Use sparingly — only for shortlisted tickers.
"""

import logging
from typing import Optional

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)

_AV_BASE = "https://www.alphavantage.co/query"


class AlphaVantageClient:
    def __init__(self) -> None:
        self._key = get_settings().alpha_vantage_api_key

    def _get(self, params: dict) -> Optional[dict]:
        params["apikey"] = self._key
        try:
            resp = requests.get(_AV_BASE, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if "Note" in data:
                logger.warning("Alpha Vantage rate limit hit — daily cap reached")
                return None
            if "Error Message" in data:
                logger.error(f"Alpha Vantage error: {data['Error Message']}")
                return None
            return data
        except Exception as e:
            logger.error(f"Alpha Vantage request failed: {e}")
            return None

    # ── RSI ────────────────────────────────────────────────────────────────

    def get_rsi(self, ticker: str, period: int = 14) -> Optional[float]:
        """Return most recent RSI value."""
        data = self._get({
            "function": "RSI",
            "symbol": ticker,
            "interval": "daily",
            "time_period": period,
            "series_type": "close",
        })
        if not data:
            return None
        analysis = data.get("Technical Analysis: RSI", {})
        if not analysis:
            return None
        latest_date = sorted(analysis.keys())[-1]
        return float(analysis[latest_date]["RSI"])

    # ── MACD ───────────────────────────────────────────────────────────────

    def get_macd(self, ticker: str) -> Optional[dict]:
        """Return most recent MACD values (MACD line, signal line, histogram)."""
        data = self._get({
            "function": "MACD",
            "symbol": ticker,
            "interval": "daily",
            "series_type": "close",
        })
        if not data:
            return None
        analysis = data.get("Technical Analysis: MACD", {})
        if not analysis:
            return None
        latest_date = sorted(analysis.keys())[-1]
        row = analysis[latest_date]
        return {
            "macd": float(row["MACD"]),
            "signal": float(row["MACD_Signal"]),
            "histogram": float(row["MACD_Hist"]),
            "date": latest_date,
        }

    # ── Bollinger Bands ────────────────────────────────────────────────────

    def get_bollinger_bands(self, ticker: str, period: int = 20) -> Optional[dict]:
        """Return most recent Bollinger Bands (upper, middle, lower)."""
        data = self._get({
            "function": "BBANDS",
            "symbol": ticker,
            "interval": "daily",
            "time_period": period,
            "series_type": "close",
            "nbdevup": 2,
            "nbdevdn": 2,
        })
        if not data:
            return None
        analysis = data.get("Technical Analysis: BBANDS", {})
        if not analysis:
            return None
        latest_date = sorted(analysis.keys())[-1]
        row = analysis[latest_date]
        return {
            "upper": float(row["Real Upper Band"]),
            "middle": float(row["Real Middle Band"]),
            "lower": float(row["Real Lower Band"]),
            "date": latest_date,
        }

    # ── Connectivity check ─────────────────────────────────────────────────

    def ping(self) -> dict:
        rsi = self.get_rsi("AAPL")
        if rsi is not None:
            return {"ok": True, "aapl_rsi": rsi}
        return {"ok": False, "error": "RSI fetch failed or rate limited"}
