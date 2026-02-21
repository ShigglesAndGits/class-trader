"""
Market data models: news items, portfolio snapshots, Reddit mentions.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    triggered_analysis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<NewsItem id={self.id} ticker={self.ticker} sentiment={self.sentiment_score}>"


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    main_equity: Mapped[float] = mapped_column(Float, nullable=False)
    penny_equity: Mapped[float] = mapped_column(Float, nullable=False)
    total_equity: Mapped[float] = mapped_column(Float, nullable=False)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False)
    spy_benchmark_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    daily_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    daily_pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<PortfolioSnapshot id={self.id} total={self.total_equity} at={self.timestamp}>"


class RedditMention(Base):
    __tablename__ = "reddit_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    subreddit: Mapped[str] = mapped_column(String(100), nullable=False)
    post_title: Mapped[str] = mapped_column(Text, nullable=False)
    post_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    post_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hype_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mention_velocity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<RedditMention id={self.id} ticker={self.ticker} sub={self.subreddit}>"
