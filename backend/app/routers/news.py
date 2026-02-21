"""
News & sentiment API — news feed, sentiment aggregation, retail (TendieBot) data.
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.market_data import NewsItem, RedditMention

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/feed")
async def get_news_feed(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    triggered_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """Latest news items, optionally filtered by ticker or trigger status."""
    query = select(NewsItem).order_by(NewsItem.fetched_at.desc())

    if ticker:
        query = query.where(NewsItem.ticker == ticker.upper())
    if triggered_only:
        query = query.where(NewsItem.triggered_analysis == True)  # noqa: E712

    query = query.limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": n.id,
                "ticker": n.ticker,
                "headline": n.headline,
                "summary": n.summary,
                "source": n.source,
                "url": n.url,
                "sentiment_score": n.sentiment_score,
                "published_at": n.published_at.isoformat() if n.published_at else None,
                "fetched_at": n.fetched_at.isoformat(),
                "triggered_analysis": n.triggered_analysis,
            }
            for n in items
        ],
        "count": len(items),
    }


@router.get("/sentiment")
async def get_sentiment(
    ticker: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Average sentiment score per ticker over the last 48 hours.
    Returns sorted by absolute sentiment (most opinionated first).
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func

    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    query = (
        select(
            NewsItem.ticker,
            func.avg(NewsItem.sentiment_score).label("avg_sentiment"),
            func.count(NewsItem.id).label("article_count"),
            func.min(NewsItem.sentiment_score).label("min_sentiment"),
            func.max(NewsItem.sentiment_score).label("max_sentiment"),
        )
        .where(
            NewsItem.ticker.is_not(None),
            NewsItem.sentiment_score.is_not(None),
            NewsItem.fetched_at >= cutoff,
        )
        .group_by(NewsItem.ticker)
    )

    if ticker:
        query = query.where(NewsItem.ticker == ticker.upper())

    result = await db.execute(query)
    rows = result.all()

    sentiment = [
        {
            "ticker": row.ticker,
            "avg_sentiment": round(float(row.avg_sentiment), 3),
            "article_count": row.article_count,
            "min_sentiment": round(float(row.min_sentiment), 3),
            "max_sentiment": round(float(row.max_sentiment), 3),
        }
        for row in rows
    ]
    sentiment.sort(key=lambda x: abs(x["avg_sentiment"]), reverse=True)

    return {"sentiment": sentiment, "count": len(sentiment)}


@router.get("/retail")
async def get_retail_sentiment(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    Latest Reddit/WSB mention data from TendieBot crawls.
    Sorted by hype_score descending — highest hype first.
    """
    query = select(RedditMention).order_by(
        RedditMention.fetched_at.desc(),
        RedditMention.hype_score.desc(),
    )

    if ticker:
        query = query.where(RedditMention.ticker == ticker.upper())

    query = query.limit(limit)
    result = await db.execute(query)
    mentions = result.scalars().all()

    return {
        "trending": [
            {
                "id": m.id,
                "ticker": m.ticker,
                "subreddit": m.subreddit,
                "post_title": m.post_title,
                "post_url": m.post_url,
                "post_score": m.post_score,
                "comment_count": m.comment_count,
                "sentiment_score": m.sentiment_score,
                "hype_score": m.hype_score,
                "mention_velocity": m.mention_velocity,
                "fetched_at": m.fetched_at.isoformat(),
            }
            for m in mentions
        ],
        "count": len(mentions),
    }
