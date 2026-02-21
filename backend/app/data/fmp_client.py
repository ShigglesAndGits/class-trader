"""
Financial Modeling Prep client — fundamentals, key ratios, company profile.
250 calls/day free. Used for shortlisted tickers only.
"""

import logging
from typing import Optional

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)

_FMP_BASE = "https://financialmodelingprep.com/api/v3"


class FMPClient:
    def __init__(self) -> None:
        self._key = get_settings().fmp_api_key

    def _get(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict | list]:
        url = f"{_FMP_BASE}/{endpoint}"
        p = params or {}
        p["apikey"] = self._key
        try:
            resp = requests.get(url, params=p, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            # FMP returns error messages in a dict with "Error Message" key
            if isinstance(data, dict) and "Error Message" in data:
                logger.error(f"FMP API error: {data['Error Message']}")
                return None
            return data
        except Exception as e:
            logger.error(f"FMP request to {endpoint} failed: {e}")
            return None

    # ── Company profile ────────────────────────────────────────────────────

    def get_profile(self, ticker: str) -> Optional[dict]:
        """Return basic company profile including market cap and sector."""
        data = self._get(f"profile/{ticker}")
        if not data or not isinstance(data, list) or len(data) == 0:
            return None
        p = data[0]
        return {
            "ticker": p.get("symbol"),
            "company_name": p.get("companyName"),
            "sector": p.get("sector"),
            "industry": p.get("industry"),
            "market_cap": p.get("mktCap"),
            "pe_ratio": p.get("pe"),
            "beta": p.get("beta"),
            "52w_high": p.get("range", "").split("-")[-1] if p.get("range") else None,
            "52w_low": p.get("range", "").split("-")[0] if p.get("range") else None,
            "description": p.get("description"),
        }

    # ── Key metrics ────────────────────────────────────────────────────────

    def get_key_metrics(self, ticker: str) -> Optional[dict]:
        """Return most recent key financial metrics (TTM)."""
        data = self._get(f"key-metrics-ttm/{ticker}")
        if not data or not isinstance(data, list) or len(data) == 0:
            return None
        m = data[0]
        return {
            "ticker": ticker,
            "pe_ratio_ttm": m.get("peRatioTTM"),
            "pb_ratio_ttm": m.get("pbRatioTTM"),
            "ps_ratio_ttm": m.get("priceToSalesRatioTTM"),
            "ev_ebitda_ttm": m.get("enterpriseValueOverEBITDATTM"),
            "debt_to_equity_ttm": m.get("debtToEquityTTM"),
            "current_ratio_ttm": m.get("currentRatioTTM"),
            "roe_ttm": m.get("roeTTM"),
            "revenue_growth_3y": m.get("revenueGrowth3Y"),
            "eps_growth_3y": m.get("epsgrowth3Y"),
            "dividend_yield_ttm": m.get("dividendYieldTTM"),
            "payout_ratio_ttm": m.get("payoutRatioTTM"),
            "free_cash_flow_yield_ttm": m.get("freeCashFlowYieldTTM"),
        }

    # ── Earnings ───────────────────────────────────────────────────────────

    def get_earnings_surprises(self, ticker: str, limit: int = 4) -> list[dict]:
        """Return last N quarters of earnings surprises."""
        data = self._get(f"earnings-surprises/{ticker}")
        if not data or not isinstance(data, list):
            return []
        return [
            {
                "date": e.get("date"),
                "actual_eps": e.get("actualEarningResult"),
                "estimated_eps": e.get("estimatedEarning"),
                "surprise_pct": (
                    ((e["actualEarningResult"] - e["estimatedEarning"]) / abs(e["estimatedEarning"]) * 100)
                    if e.get("estimatedEarning") and e.get("actualEarningResult")
                    else None
                ),
            }
            for e in data[:limit]
        ]

    # ── Connectivity check ─────────────────────────────────────────────────

    def ping(self) -> dict:
        profile = self.get_profile("AAPL")
        if profile:
            return {"ok": True, "company": profile["company_name"]}
        return {"ok": False, "error": "Could not fetch AAPL profile"}
