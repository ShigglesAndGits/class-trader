"""
Market data schemas — MarketContext, TickerContext, PriceBar.
Built by the aggregator once per pipeline cycle, shared across all agents.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.agents import RetailSentiment


class PriceBar(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None


class NewsItem(BaseModel):
    headline: str
    summary: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None
    sentiment: Optional[float] = None
    published_at: Optional[int] = None  # Unix timestamp from Finnhub


class Position(BaseModel):
    ticker: str
    qty: float
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    current_price: float
    avg_entry_price: float
    side: str


class WashSaleEntry(BaseModel):
    ticker: str
    sale_date: date
    loss_amount: float
    blackout_until: date
    is_year_end_blocked: bool


class TickerContext(BaseModel):
    ticker: str
    price_bars: list[PriceBar]         # Last 30 days daily bars
    current_price: float
    volume: int
    # Technical indicators
    rsi_14: Optional[float] = None
    macd: Optional[dict] = None
    bollinger_bands: Optional[dict] = None
    # News and sentiment
    recent_news: list[NewsItem] = []
    news_sentiment_avg: Optional[float] = None
    insider_sentiment: Optional[float] = None
    # Fundamentals
    pe_ratio: Optional[float] = None
    market_cap: Optional[float] = None
    earnings_date: Optional[date] = None
    # Retail sentiment
    retail_sentiment: Optional[RetailSentiment] = None


class MarketContext(BaseModel):
    timestamp: datetime
    # Broad market
    spy_bars: list[PriceBar]
    vix_level: Optional[float] = None
    sector_performance: dict[str, float] = {}  # ETF ticker → % return today
    treasury_yield_10y: Optional[float] = None
    # Retail (broad WSB trending, not per-ticker)
    wsb_trending_tickers: list[RetailSentiment] = []
    # Per-ticker data
    ticker_data: dict[str, TickerContext] = {}
    # Account state
    account_equity: float
    settled_cash: float
    current_positions: list[Position] = []
    wash_sale_blacklist: list[WashSaleEntry] = []
