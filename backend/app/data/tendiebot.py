"""
TendieBot — Reddit retail sentiment crawler.
Watches r/wallstreetbets, r/stocks, r/pennystocks.
This is a DATA SOURCE, not an agent. Feeds into MarketContext.

Retail sentiment is treated as low-confidence supplementary signal.
See CLAUDE.md for per-agent guidance on how to weight it.
"""

import asyncio
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpraw

from app.config import get_settings

logger = logging.getLogger(__name__)

SUBREDDITS = ["wallstreetbets", "stocks", "pennystocks"]
_TICKER_PATTERN = re.compile(r"\b([A-Z]{2,5})\b")

# Tickers to ignore — common false positives in financial communities
_IGNORED_TICKERS = {
    "I", "A", "DD", "OG", "CEO", "CFO", "IPO", "SEC", "ETF", "AI",
    "YOLO", "LOL", "IMO", "ATH", "GDP", "FED", "EPS", "WSB", "FOMO",
    "WSJ", "CNBC", "NYSE", "NASDAQ", "SP", "US", "USA", "UK", "EU",
    "USD", "GBP", "EUR", "YTD", "QOQ", "YOY", "ER", "PT", "OTC",
    "IV", "PE", "EV", "DD", "TA", "FA", "PM", "AM", "CPI", "PPI",
    "NFP", "FOMC", "ECB", "BOJ", "RBI", "IMF", "WTO",
}


class TendieBot:
    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = settings.reddit_client_id
        self._client_secret = settings.reddit_client_secret
        self._user_agent = settings.reddit_user_agent

    def _make_reddit(self) -> asyncpraw.Reddit:
        return asyncpraw.Reddit(
            client_id=self._client_id,
            client_secret=self._client_secret,
            user_agent=self._user_agent,
        )

    async def crawl_subreddit(
        self,
        subreddit_name: str,
        limit: int = 50,
        watchlist: Optional[set[str]] = None,
    ) -> list[dict]:
        """
        Crawl hot + new posts from a subreddit.
        Returns posts relevant to the watchlist (or all if watchlist is None).
        """
        posts = []
        async with self._make_reddit() as reddit:
            sub = await reddit.subreddit(subreddit_name)
            async for post in sub.hot(limit=limit):
                text = f"{post.title} {post.selftext or ''}"
                tickers_found = self._extract_tickers(text, watchlist)
                if not tickers_found:
                    continue
                posts.append({
                    "subreddit": subreddit_name,
                    "post_id": post.id,
                    "title": post.title,
                    "url": f"https://reddit.com{post.permalink}",
                    "score": post.score,
                    "upvote_ratio": post.upvote_ratio,
                    "num_comments": post.num_comments,
                    "created_utc": post.created_utc,
                    "tickers": list(tickers_found),
                    "flair": post.link_flair_text,
                })
        return posts

    def _extract_tickers(self, text: str, watchlist: Optional[set[str]]) -> set[str]:
        """Extract ticker symbols from post text."""
        found = _TICKER_PATTERN.findall(text)
        cleaned = {t for t in found if t not in _IGNORED_TICKERS and len(t) >= 2}
        if watchlist:
            cleaned = cleaned & watchlist
        return cleaned

    def _naive_sentiment(self, text: str) -> float:
        """
        Extremely naive sentiment scoring based on keyword lists.
        Real sentiment would use a model — this is a placeholder
        until we wire in a proper signal.
        Returns -1.0 (bearish) to 1.0 (bullish).
        """
        text_lower = text.lower()
        bullish_words = [
            "bull", "moon", "rocket", "calls", "buy", "long", "breakout",
            "squeeze", "tendies", "green", "profit", "gains", "yolo", "pump",
            "upside", "accumulate", "position", "hold",
        ]
        bearish_words = [
            "bear", "puts", "short", "crash", "dump", "red", "loss", "sell",
            "tank", "collapse", "downside", "overvalued", "bubble", "scam",
        ]
        bull_hits = sum(1 for w in bullish_words if w in text_lower)
        bear_hits = sum(1 for w in bearish_words if w in text_lower)
        total = bull_hits + bear_hits
        if total == 0:
            return 0.0
        return (bull_hits - bear_hits) / total

    async def get_retail_sentiment(
        self,
        watchlist: list[str],
        baseline_mentions: Optional[dict[str, float]] = None,
    ) -> dict[str, dict]:
        """
        Crawl all configured subreddits and aggregate sentiment per ticker.
        Returns a dict of ticker → RetailSentiment-compatible data.

        baseline_mentions: 7-day average mention count per ticker (for velocity calc).
        """
        watchlist_set = set(watchlist)
        all_posts: list[dict] = []

        tasks = [
            self.crawl_subreddit(sub, limit=50, watchlist=watchlist_set)
            for sub in SUBREDDITS
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_posts.extend(r)
            elif isinstance(r, Exception):
                logger.warning(f"Subreddit crawl failed: {r}")

        # Aggregate per ticker
        ticker_posts: dict[str, list[dict]] = defaultdict(list)
        for post in all_posts:
            for ticker in post["tickers"]:
                ticker_posts[ticker].append(post)

        output: dict[str, dict] = {}
        for ticker in watchlist:
            posts = ticker_posts.get(ticker, [])
            if not posts:
                continue

            mention_count = len(posts)
            baseline = baseline_mentions.get(ticker, mention_count) if baseline_mentions else mention_count
            velocity = mention_count / max(baseline, 1)

            sentiments = [self._naive_sentiment(p["title"]) for p in posts]
            avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

            # Hype score: blends mention count, velocity, and score
            avg_score = sum(p.get("score", 0) for p in posts) / max(len(posts), 1)
            hype_raw = min(mention_count / 20.0, 1.0) * 0.4 + min(velocity / 5.0, 1.0) * 0.4 + min(avg_score / 1000.0, 1.0) * 0.2
            hype_score = min(hype_raw, 1.0)

            # Caution flags
            caution_flags = []
            if velocity > 3.0 and not any(p.get("flair") in ["News", "DD"] for p in posts):
                caution_flags.append("spike with no news/DD flair")
            if hype_score > 0.8 and avg_sentiment > 0.5:
                caution_flags.append("extreme hype with high bullish sentiment")
            top_posts = sorted(posts, key=lambda p: p.get("score", 0), reverse=True)[:3]

            output[ticker] = {
                "ticker": ticker,
                "mention_count_24h": mention_count,
                "mention_velocity": round(velocity, 2),
                "avg_sentiment": round(avg_sentiment, 3),
                "hype_score": round(hype_score, 3),
                "top_posts": [p["title"] for p in top_posts],
                "subreddits": list({p["subreddit"] for p in posts}),
                "caution_flags": caution_flags,
            }

        return output

    # ── Connectivity check ─────────────────────────────────────────────────

    async def ping(self) -> dict:
        try:
            async with self._make_reddit() as reddit:
                sub = await reddit.subreddit("wallstreetbets")
                top_post = None
                async for post in sub.hot(limit=1):
                    top_post = post
                    break
            if top_post:
                return {"ok": True, "wsb_top_post": top_post.title[:60]}
            return {"ok": False, "error": "No posts found"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
