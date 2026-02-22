"""
TendieBot — retail sentiment via ApeWisdom.io.

ApeWisdom aggregates mention and upvote data from r/wallstreetbets, r/stocks,
r/pennystocks, r/options, r/investing, and more. No API key required.

This is a DATA SOURCE, not an agent. Feeds into MarketContext.
Retail sentiment is treated as a low-confidence supplementary signal.
See CLAUDE.md for per-agent guidance on how to weight it.

Originally wired to the Reddit API (asyncpraw). Switched to ApeWisdom after
Reddit's developer approval process proved to have its own ideas about timelines.
"""

import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)

_APEWISDOM_BASE = "https://apewisdom.io/api/v1.0"
_FILTER = "all-stocks"  # covers WSB, r/stocks, r/pennystocks, r/options, r/investing
_PAGES_TO_FETCH = 2     # ~188 tickers per call — enough for any reasonable watchlist
_SUBREDDITS_COVERED = ["wallstreetbets", "stocks", "pennystocks", "options", "investing"]


class TendieBot:
    """
    Retail sentiment client backed by ApeWisdom.io.
    Maintains the same interface as the original Reddit implementation.

    ApeWisdom provides: mentions (24h), mentions_24h_ago, upvotes, rank, rank_24h_ago.
    avg_sentiment is set to 0.0 (neutral) — ApeWisdom tracks volume, not tone.
    top_posts is empty — ApeWisdom aggregates counts; individual posts aren't available.
    """

    async def get_retail_sentiment(
        self,
        watchlist: list[str],
        baseline_mentions: dict[str, float] | None = None,
    ) -> dict[str, dict]:
        """
        Fetch ApeWisdom trending data and filter to watchlist tickers.
        Returns a dict of ticker → RetailSentiment-compatible data.
        """
        watchlist_set = {t.upper() for t in watchlist}
        trending = await self._fetch_trending()

        output: dict[str, dict] = {}
        for item in trending:
            ticker = item.get("ticker", "").upper()
            if ticker not in watchlist_set:
                continue

            mentions = int(item.get("mentions") or 0)
            mentions_24h_ago = int(item.get("mentions_24h_ago") or 0)
            upvotes = int(item.get("upvotes") or 0)
            rank = int(item.get("rank") or 999)
            rank_24h_ago = int(item.get("rank_24h_ago") or 999)

            # Velocity: ratio of current to previous 24h mentions (1.0 = flat, 3.0 = 3x spike)
            velocity = round(mentions / max(mentions_24h_ago, 1), 2) if mentions_24h_ago else 1.0

            # Rank improvement: positive = moved up in rankings
            rank_delta = rank_24h_ago - rank

            # Hype score: blend of mentions, velocity, upvotes, rank change
            hype_raw = (
                min(mentions / 100.0, 1.0) * 0.35
                + min(velocity / 5.0, 1.0) * 0.35
                + min(upvotes / 500.0, 1.0) * 0.20
                + min(max(rank_delta, 0) / 20.0, 1.0) * 0.10
            )
            hype_score = round(min(hype_raw, 1.0), 3)

            caution_flags = []
            if velocity > 3.0:
                caution_flags.append(f"mention spike: {velocity:.1f}x vs yesterday")
            if hype_score > 0.8:
                caution_flags.append("extreme hype level")
            if rank_delta > 20:
                caution_flags.append(f"rank jumped {rank_delta} positions in 24h")

            output[ticker] = {
                "ticker": ticker,
                "mention_count_24h": mentions,
                "mention_velocity": velocity,
                "avg_sentiment": 0.0,  # ApeWisdom tracks volume, not sentiment
                "hype_score": hype_score,
                "top_posts": [],  # aggregated counts only — no individual posts
                "subreddits": _SUBREDDITS_COVERED,
                "caution_flags": caution_flags,
            }

        logger.info(
            f"ApeWisdom: matched {len(output)}/{len(watchlist_set)} "
            f"watchlist tickers in top trending"
        )
        return output

    async def _fetch_trending(self) -> list[dict]:
        """Fetch trending tickers from ApeWisdom (up to _PAGES_TO_FETCH pages)."""
        results: list[dict] = []
        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for page in range(1, _PAGES_TO_FETCH + 1):
                url = f"{_APEWISDOM_BASE}/filter/{_FILTER}/page/{page}"
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            logger.warning(f"ApeWisdom returned HTTP {resp.status}")
                            break
                        data = await resp.json()
                        results.extend(data.get("results", []))
                        if page >= data.get("pages", 1):
                            break
                except Exception as e:
                    logger.warning(f"ApeWisdom fetch failed (page {page}): {e}")
                    break

                if page < _PAGES_TO_FETCH:
                    await asyncio.sleep(0.3)  # polite pacing

        return results

    async def ping(self) -> dict:
        """Connectivity check used by the health/settings endpoints."""
        try:
            results = await self._fetch_trending()
            if results:
                top = results[0]
                return {
                    "ok": True,
                    "top_ticker": top.get("ticker"),
                    "mentions": top.get("mentions"),
                    "source": "apewisdom.io",
                }
            return {"ok": False, "error": "No results from ApeWisdom"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
