"""
Finnhub client — news, sentiment, earnings, insider data, VIX, treasury yields.
Primary screening data source: cheap calls, good coverage.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import finnhub

from app.config import get_settings

logger = logging.getLogger(__name__)

# Finnhub free tier: 60 calls/minute
_RATE_LIMIT_DELAY = 1.1  # seconds between calls when batching


class FinnhubClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = finnhub.Client(api_key=settings.finnhub_api_key)

    def _safe_call(self, fn, *args, **kwargs):
        """Wrap Finnhub calls with basic error handling."""
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.error(f"Finnhub call failed ({fn.__name__}): {e}")
            return None

    # ── Quote ──────────────────────────────────────────────────────────────

    def get_quote(self, ticker: str) -> Optional[dict]:
        data = self._safe_call(self._client.quote, ticker)
        if not data or data.get("c", 0) == 0:
            return None
        return {
            "ticker": ticker,
            "current": data["c"],
            "open": data["o"],
            "high": data["h"],
            "low": data["l"],
            "prev_close": data["pc"],
            "change": data["d"],
            "change_pct": data["dp"],
        }

    # ── News + sentiment ───────────────────────────────────────────────────

    def get_company_news(self, ticker: str, lookback_hours: int = 48) -> list[dict]:
        """Return recent news articles for a ticker."""
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(hours=lookback_hours)
        data = self._safe_call(
            self._client.company_news,
            ticker,
            _from=from_date.strftime("%Y-%m-%d"),
            to=to_date.strftime("%Y-%m-%d"),
        )
        if not data:
            return []
        return [
            {
                "headline": item.get("headline", ""),
                "summary": item.get("summary", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "datetime": item.get("datetime", 0),
                "sentiment": None,  # Finnhub news doesn't include per-article scores
            }
            for item in data[:20]  # Cap at 20 per ticker
        ]

    def get_news_sentiment(self, ticker: str) -> Optional[dict]:
        """Aggregate news sentiment for a ticker (Finnhub sentiment endpoint)."""
        data = self._safe_call(self._client.news_sentiment, ticker)
        if not data:
            return None
        buzz = data.get("buzz", {})
        sentiment = data.get("sentiment", {})
        return {
            "ticker": ticker,
            "buzz_articles_in_last_week": buzz.get("articlesInLastWeek", 0),
            "buzz_score": buzz.get("buzz", 0.0),
            "weekly_average": buzz.get("weeklyAverage", 0.0),
            "bearish_pct": sentiment.get("bearishPercent", 0.0),
            "bullish_pct": sentiment.get("bullishPercent", 0.0),
            "score": sentiment.get("score", 0.0),  # -1 to 1
        }

    # ── Insider sentiment ──────────────────────────────────────────────────

    def get_insider_sentiment(self, ticker: str) -> Optional[float]:
        """
        Return a single normalized insider sentiment score (-1 to 1).
        Uses MSPR (Monthly Share Purchase Ratio) as proxy.
        """
        try:
            to_date = datetime.now(timezone.utc)
            from_date = to_date - timedelta(days=90)
            data = self._client.stock_insider_sentiment(
                ticker,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
            )
            if not data or not data.get("data"):
                return None
            # MSPR: -1 (all selling) to 1 (all buying). Take most recent.
            records = sorted(data["data"], key=lambda x: (x.get("year", 0), x.get("month", 0)))
            if not records:
                return None
            latest = records[-1]
            mspr = latest.get("mspr", 0.0)
            return float(mspr)
        except Exception as e:
            logger.warning(f"Could not fetch insider sentiment for {ticker}: {e}")
            return None

    # ── Earnings ───────────────────────────────────────────────────────────

    def get_earnings_calendar(self, ticker: str) -> Optional[dict]:
        """Return next earnings date if within 30 days."""
        try:
            to_date = datetime.now(timezone.utc) + timedelta(days=30)
            from_date = datetime.now(timezone.utc)
            data = self._client.earnings_calendar(
                symbol=ticker,
                _from=from_date.strftime("%Y-%m-%d"),
                to=to_date.strftime("%Y-%m-%d"),
            )
            earnings = data.get("earningsCalendar", [])
            if not earnings:
                return None
            next_event = earnings[0]
            return {
                "ticker": ticker,
                "date": next_event.get("date"),
                "eps_estimate": next_event.get("epsEstimate"),
                "revenue_estimate": next_event.get("revenueEstimate"),
            }
        except Exception as e:
            logger.warning(f"Could not fetch earnings for {ticker}: {e}")
            return None

    # ── Broad market ───────────────────────────────────────────────────────

    def get_vix(self) -> Optional[float]:
        """Return current VIX level."""
        data = self._safe_call(self._client.quote, "^VIX")
        if data and data.get("c", 0) > 0:
            return float(data["c"])
        return None

    def get_treasury_yield_10y(self) -> Optional[float]:
        """Return current 10-year treasury yield."""
        try:
            data = self._client.bond_yield(code="US10Y")
            if data and data.get("last"):
                return float(data["last"])
        except Exception as e:
            logger.warning(f"Could not fetch treasury yield: {e}")
        return None

    # ── Connectivity check ─────────────────────────────────────────────────

    def ping(self) -> dict:
        quote = self.get_quote("AAPL")
        if quote:
            return {"ok": True, "aapl_price": quote["current"]}
        return {"ok": False, "error": "Could not fetch AAPL quote"}
