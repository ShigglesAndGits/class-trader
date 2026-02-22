"""
News scanner for discovery mode.

When the user wants to find tickers by theme ("find energy momentum plays")
rather than naming tickers explicitly, this module fetches Finnhub's general
market news and uses a small LLM call to extract relevant ticker candidates.

Budget: 1 Finnhub call + 1 cheap LLM call per discovery session.
"""

import logging
from typing import Optional

import instructor
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.config import get_settings
from app.data.finnhub_client import FinnhubClient

logger = logging.getLogger(__name__)

_MAX_HEADLINES = 30  # How many news items to scan


class _CandidateTickers(BaseModel):
    tickers: list[str]
    rationale: str


async def scan_news_for_candidates(
    themes: list[str],
    max_candidates: int = 5,
) -> list[str]:
    """
    Scan Finnhub general news for tickers relevant to the given themes.

    Returns up to max_candidates ticker symbols, deduplicated and uppercased.
    Falls back to an empty list on any error (discovery can still proceed
    if the user provided explicit tickers too).
    """
    if not themes:
        return []

    settings = get_settings()

    # ── 1. Fetch general market news from Finnhub ──────────────────────────
    try:
        finnhub = FinnhubClient()
        import asyncio
        raw_news = await asyncio.to_thread(finnhub.get_general_news, category="general")
        headlines = [
            f"- {item.get('headline', '')} [{item.get('source', '')}]"
            for item in (raw_news or [])[:_MAX_HEADLINES]
            if item.get("headline")
        ]
    except Exception as e:
        logger.warning(f"News scanner: Finnhub fetch failed: {e}")
        return []

    if not headlines:
        return []

    # ── 2. LLM call to extract theme-relevant tickers ─────────────────────
    themes_str = ", ".join(themes)
    headlines_str = "\n".join(headlines)

    prompt = (
        f"The user is researching stocks matching these themes: {themes_str}\n\n"
        f"Here are recent news headlines:\n{headlines_str}\n\n"
        f"Extract up to {max_candidates} US stock tickers (e.g. NVDA, TSLA) that are "
        f"most relevant to the stated themes. Only include tickers explicitly mentioned "
        f"in the headlines or strongly implied by the theme + context. "
        f"Return uppercase tickers only, no ETFs or index funds."
    )

    try:
        raw_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        client = instructor.from_anthropic(raw_client)

        result: _CandidateTickers = await client.messages.create(
            model=settings.llm_model,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
            response_model=_CandidateTickers,
        )

        tickers = [t.upper().strip() for t in result.tickers if t.strip()]
        tickers = list(dict.fromkeys(tickers))[:max_candidates]
        logger.info(f"News scanner found candidates for themes {themes}: {tickers}")
        return tickers

    except Exception as e:
        logger.warning(f"News scanner: LLM extraction failed: {e}")
        return []
