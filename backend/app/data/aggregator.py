"""
Market data aggregator — builds MarketContext from all external data sources.

Data is fetched ONCE per pipeline cycle. Every agent reads from the same
MarketContext object. This keeps API call counts predictable and cheap.

Fetch strategy:
  - Alpaca: all tickers at once (batch endpoints, very cheap)
  - Finnhub: all tickers sequentially with small delay (60/min rate limit)
  - Alpha Vantage: top N shortlisted tickers only (25/day budget)
  - FMP: shortlisted tickers only (250/day budget)
  - Reddit/TendieBot: async, all watchlist tickers
"""

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.data.alpaca_client import AlpacaClient
from app.data.alphavantage_client import AlphaVantageClient
from app.data.finnhub_client import FinnhubClient
from app.data.fmp_client import FMPClient
from app.data.tendiebot import TendieBot
from app.models.risk import WashSale
from app.models.watchlist import Watchlist
from app.schemas.agents import RetailSentiment
from app.schemas.market import (
    MarketContext,
    NewsItem,
    Position,
    PriceBar,
    TickerContext,
    WashSaleEntry,
)

logger = logging.getLogger(__name__)


def _parse_date_safe(date_str: Optional[str]) -> Optional[date]:
    """Parse an ISO date string ('YYYY-MM-DD') without raising on bad input."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except Exception:
        return None


# Alpha Vantage free tier: 5 calls/min. Space calls 13s apart to stay safe.
_AV_CALL_DELAY = 13.0
# Max tickers to send to AV per cycle (25/day ÷ 3 cycles ≈ 8)
_AV_MAX_TICKERS = 8
# Max tickers to send to FMP per cycle
_FMP_MAX_TICKERS = 15


async def build_market_context(db: AsyncSession) -> MarketContext:
    """
    Fetch all market data and assemble a MarketContext.
    Called once at the start of each pipeline run.
    """
    settings = get_settings()

    # ── 1. Load watchlist from DB ──────────────────────────────────────────
    watchlist_rows = (await db.execute(
        select(Watchlist).where(Watchlist.is_active == True)  # noqa: E712
    )).scalars().all()

    main_tickers = [w.ticker for w in watchlist_rows if w.sleeve in ("MAIN", "BENCHMARK")]
    penny_tickers = [w.ticker for w in watchlist_rows if w.sleeve == "PENNY"]

    # Always include SPY for regime analysis
    if "SPY" not in main_tickers:
        main_tickers.append("SPY")

    all_tickers = list(dict.fromkeys(main_tickers + penny_tickers))  # preserve order, dedup

    if not all_tickers:
        logger.warning("Watchlist is empty — using fallback tickers. Run init_watchlist.py.")
        all_tickers = ["SPY", "QQQ", "AAPL", "MSFT"]
        main_tickers = all_tickers
        penny_tickers = []

    logger.info(f"Building MarketContext for {len(all_tickers)} tickers...")

    # ── 2. Init data clients ───────────────────────────────────────────────
    alpaca = AlpacaClient()
    finnhub = FinnhubClient()
    av = AlphaVantageClient()
    fmp = FMPClient()

    # ── 3. Parallel batch fetches (Alpaca — no rate concerns) ─────────────
    logger.info("Fetching prices, quotes, account, positions...")
    (
        bars_result,
        quotes_result,
        account_result,
        positions_result,
        vix_result,
        yield_result,
    ) = await asyncio.gather(
        asyncio.to_thread(alpaca.get_daily_bars, all_tickers),
        asyncio.to_thread(alpaca.get_latest_quotes, all_tickers),
        asyncio.to_thread(alpaca.get_account),
        asyncio.to_thread(alpaca.get_positions),
        asyncio.to_thread(finnhub.get_vix),
        asyncio.to_thread(finnhub.get_treasury_yield_10y),
        return_exceptions=True,
    )

    bars: dict = bars_result if isinstance(bars_result, dict) else {}
    quotes: dict = quotes_result if isinstance(quotes_result, dict) else {}
    account: dict = account_result if isinstance(account_result, dict) else {}
    raw_positions: list = positions_result if isinstance(positions_result, list) else []
    vix: Optional[float] = vix_result if isinstance(vix_result, float) else None
    treasury_yield: Optional[float] = yield_result if isinstance(yield_result, float) else None

    if isinstance(bars_result, Exception):
        logger.error(f"Failed to fetch price bars: {bars_result}")
    if isinstance(account_result, Exception):
        logger.error(f"Failed to fetch account: {account_result}")

    # ── 4. News + sentiment + insider + earnings (Finnhub — rate limited, sequential) ──
    logger.info(f"Fetching Finnhub data for {len(all_tickers)} tickers...")
    ticker_news: dict[str, list] = {}
    ticker_sentiment: dict[str, dict] = {}
    ticker_insider: dict[str, Optional[float]] = {}
    ticker_earnings_date: dict[str, Optional[str]] = {}

    for ticker in all_tickers:
        try:
            news = await asyncio.to_thread(finnhub.get_company_news, ticker)
            ticker_news[ticker] = news
        except Exception as e:
            logger.warning(f"News fetch failed for {ticker}: {e}")
            ticker_news[ticker] = []

        try:
            sentiment = await asyncio.to_thread(finnhub.get_news_sentiment, ticker)
            if sentiment:
                ticker_sentiment[ticker] = sentiment
        except Exception as e:
            logger.warning(f"Sentiment fetch failed for {ticker}: {e}")

        try:
            insider = await asyncio.to_thread(finnhub.get_insider_sentiment, ticker)
            if insider is not None:
                ticker_insider[ticker] = insider
        except Exception as e:
            logger.warning(f"Insider sentiment fetch failed for {ticker}: {e}")

        try:
            earnings = await asyncio.to_thread(finnhub.get_earnings_calendar, ticker)
            if earnings:
                ticker_earnings_date[ticker] = earnings.get("date")
        except Exception as e:
            logger.warning(f"Earnings calendar fetch failed for {ticker}: {e}")

        await asyncio.sleep(0.5)  # ~60 calls/min safe zone

    # ── 5. Shortlist tickers for expensive API calls ───────────────────────
    shortlisted = _shortlist_tickers(all_tickers, ticker_sentiment, bars, n=_AV_MAX_TICKERS)
    logger.info(f"Shortlisted {len(shortlisted)} tickers for deep analysis: {shortlisted}")

    # ── 6. Alpha Vantage technical indicators (shortlisted only) ──────────
    ticker_rsi: dict[str, Optional[float]] = {}
    ticker_macd: dict[str, Optional[dict]] = {}

    if settings.configured_apis().get("alpha_vantage"):
        logger.info(f"Fetching AV technicals for {len(shortlisted)} tickers...")
        for ticker in shortlisted:
            try:
                rsi = await asyncio.to_thread(av.get_rsi, ticker)
                ticker_rsi[ticker] = rsi
                await asyncio.sleep(_AV_CALL_DELAY)

                macd = await asyncio.to_thread(av.get_macd, ticker)
                ticker_macd[ticker] = macd
                await asyncio.sleep(_AV_CALL_DELAY)
            except Exception as e:
                logger.warning(f"AV fetch failed for {ticker}: {e}")
    else:
        logger.info("Alpha Vantage not configured — skipping technical indicators.")

    # ── 7. FMP fundamentals (shortlisted only) ────────────────────────────
    ticker_profile: dict[str, Optional[dict]] = {}

    if settings.configured_apis().get("fmp"):
        fmp_tickers = shortlisted[:_FMP_MAX_TICKERS]
        logger.info(f"Fetching FMP fundamentals for {len(fmp_tickers)} tickers...")
        for ticker in fmp_tickers:
            try:
                profile = await asyncio.to_thread(fmp.get_profile, ticker)
                ticker_profile[ticker] = profile
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"FMP fetch failed for {ticker}: {e}")
    else:
        logger.info("FMP not configured — skipping fundamentals.")

    # ── 8. TendieBot retail sentiment via ApeWisdom (no API key required) ──
    retail_sentiment: dict[str, dict] = {}
    try:
        bot = TendieBot()
        retail_sentiment = await bot.get_retail_sentiment(watchlist=all_tickers)
    except Exception as e:
        logger.warning(f"ApeWisdom sentiment fetch failed: {e}")

    # ── 9. Wash sale blacklist from DB ────────────────────────────────────
    wash_sales = await _load_wash_sales(db)

    # ── 10. Assemble TickerContext for each ticker ─────────────────────────
    ticker_data: dict[str, TickerContext] = {}
    for ticker in all_tickers:
        ticker_bars_raw = bars.get(ticker, [])
        ticker_quote = quotes.get(ticker, {})
        profile = ticker_profile.get(ticker) or {}
        retail = retail_sentiment.get(ticker)

        # Current price: prefer mid-price from quote, fall back to latest bar close
        current_price = (
            ticker_quote.get("mid_price")
            or ticker_quote.get("ask_price")
            or (ticker_bars_raw[-1]["close"] if ticker_bars_raw else 0.0)
        )

        # Volume from latest bar
        volume = ticker_bars_raw[-1]["volume"] if ticker_bars_raw else 0

        # Finnhub sentiment score (-1 to 1)
        sentiment_score = (
            ticker_sentiment[ticker].get("score")
            if ticker_sentiment.get(ticker)
            else None
        )

        # Retail sentiment schema
        retail_obj = None
        if retail:
            try:
                retail_obj = RetailSentiment(**retail)
            except Exception:
                pass

        ticker_data[ticker] = TickerContext(
            ticker=ticker,
            price_bars=[PriceBar(**b) for b in ticker_bars_raw],
            current_price=float(current_price or 0.0),
            volume=int(volume),
            rsi_14=ticker_rsi.get(ticker),
            macd=ticker_macd.get(ticker),
            bollinger_bands=None,  # AV BBANDS not fetched to stay in budget
            recent_news=[
                NewsItem(
                    headline=n.get("headline", ""),
                    summary=n.get("summary"),
                    source=n.get("source"),
                    url=n.get("url"),
                    published_at=n.get("datetime"),
                )
                for n in ticker_news.get(ticker, [])[:10]
            ],
            news_sentiment_avg=sentiment_score,
            insider_sentiment=ticker_insider.get(ticker),
            pe_ratio=profile.get("pe_ratio") if profile else None,
            market_cap=profile.get("market_cap") if profile else None,
            earnings_date=_parse_date_safe(ticker_earnings_date.get(ticker)),
            retail_sentiment=retail_obj,
        )

    # ── 11. SPY bars for regime analysis ──────────────────────────────────
    spy_bars_raw = bars.get("SPY", [])

    # ── 12. Positions ──────────────────────────────────────────────────────
    positions = []
    for p in raw_positions:
        try:
            positions.append(Position(**p))
        except Exception as e:
            logger.warning(f"Could not parse position: {e}")

    logger.info(
        f"MarketContext built: {len(ticker_data)} tickers, "
        f"{len(positions)} positions, "
        f"VIX={vix}, equity=${account.get('equity', 0):,.0f}"
    )

    return MarketContext(
        timestamp=datetime.now(timezone.utc),
        spy_bars=[PriceBar(**b) for b in spy_bars_raw],
        vix_level=vix,
        sector_performance={},  # Phase 5: add sector ETF performance
        treasury_yield_10y=treasury_yield,
        wsb_trending_tickers=[],  # TendieBot per-ticker data lives in TickerContext
        ticker_data=ticker_data,
        account_equity=float(account.get("equity", 0.0)),
        settled_cash=float(account.get("cash", 0.0)),
        current_positions=positions,
        wash_sale_blacklist=wash_sales,
    )


def _shortlist_tickers(
    all_tickers: list[str],
    sentiment: dict[str, dict],
    bars: dict[str, list],
    n: int,
) -> list[str]:
    """
    Rank tickers by 'worth analyzing deeply' score.
    Criteria: absolute news sentiment strength + recent price movement magnitude.
    Returns top N, excluding pure benchmark ETFs.
    """
    _EXCLUDE = {"SPY", "QQQ", "IWM", "DIA"}

    scores: dict[str, float] = {}
    for ticker in all_tickers:
        if ticker in _EXCLUDE:
            continue
        score = 0.0

        sent = sentiment.get(ticker, {})
        if sent:
            score += abs(sent.get("score", 0.0)) * 2.0
            score += sent.get("buzz_score", 0.0) * 1.0

        ticker_bars = bars.get(ticker, [])
        if len(ticker_bars) >= 6:
            closes = [b["close"] for b in ticker_bars if b.get("close")]
            if len(closes) >= 6 and closes[-6] > 0:
                move_5d = abs((closes[-1] - closes[-6]) / closes[-6])
                score += move_5d * 10.0

        scores[ticker] = score

    return sorted(scores, key=lambda t: -scores[t])[:n]


async def build_partial_market_context(
    db: AsyncSession,
    tickers: list[str],
) -> MarketContext:
    """
    Build a MarketContext for an explicit ticker list — used by the discovery
    pipeline instead of reading the watchlist.

    Always prepends SPY for regime analysis. Applies the same shortlisting
    logic for expensive AV/FMP calls.
    """
    settings = get_settings()

    all_tickers = list(dict.fromkeys(["SPY"] + [t.upper().strip() for t in tickers]))
    logger.info(f"Building partial MarketContext for discovery: {all_tickers}")

    alpaca = AlpacaClient()
    finnhub = FinnhubClient()
    av = AlphaVantageClient()
    fmp = FMPClient()

    (
        bars_result,
        quotes_result,
        vix_result,
        yield_result,
    ) = await asyncio.gather(
        asyncio.to_thread(alpaca.get_daily_bars, all_tickers),
        asyncio.to_thread(alpaca.get_latest_quotes, all_tickers),
        asyncio.to_thread(finnhub.get_vix),
        asyncio.to_thread(finnhub.get_treasury_yield_10y),
        return_exceptions=True,
    )

    bars: dict = bars_result if isinstance(bars_result, dict) else {}
    quotes: dict = quotes_result if isinstance(quotes_result, dict) else {}
    vix: Optional[float] = vix_result if isinstance(vix_result, float) else None
    treasury_yield: Optional[float] = yield_result if isinstance(yield_result, float) else None

    ticker_news: dict[str, list] = {}
    ticker_sentiment: dict[str, dict] = {}
    ticker_insider: dict[str, Optional[float]] = {}
    ticker_earnings_date: dict[str, Optional[str]] = {}

    for ticker in all_tickers:
        try:
            news = await asyncio.to_thread(finnhub.get_company_news, ticker)
            ticker_news[ticker] = news
        except Exception as e:
            logger.warning(f"News fetch failed for {ticker}: {e}")
            ticker_news[ticker] = []

        try:
            sentiment = await asyncio.to_thread(finnhub.get_news_sentiment, ticker)
            if sentiment:
                ticker_sentiment[ticker] = sentiment
        except Exception as e:
            logger.warning(f"Sentiment fetch failed for {ticker}: {e}")

        try:
            insider = await asyncio.to_thread(finnhub.get_insider_sentiment, ticker)
            if insider is not None:
                ticker_insider[ticker] = insider
        except Exception as e:
            logger.warning(f"Insider sentiment fetch failed for {ticker}: {e}")

        try:
            earnings = await asyncio.to_thread(finnhub.get_earnings_calendar, ticker)
            if earnings:
                ticker_earnings_date[ticker] = earnings.get("date")
        except Exception as e:
            logger.warning(f"Earnings calendar fetch failed for {ticker}: {e}")

        await asyncio.sleep(0.5)

    shortlisted = _shortlist_tickers(all_tickers, ticker_sentiment, bars, n=_AV_MAX_TICKERS)

    ticker_rsi: dict[str, Optional[float]] = {}
    ticker_macd: dict[str, Optional[dict]] = {}

    if settings.configured_apis().get("alpha_vantage"):
        for ticker in shortlisted:
            try:
                rsi = await asyncio.to_thread(av.get_rsi, ticker)
                ticker_rsi[ticker] = rsi
                await asyncio.sleep(_AV_CALL_DELAY)
                macd = await asyncio.to_thread(av.get_macd, ticker)
                ticker_macd[ticker] = macd
                await asyncio.sleep(_AV_CALL_DELAY)
            except Exception as e:
                logger.warning(f"AV fetch failed for {ticker}: {e}")

    ticker_profile: dict[str, Optional[dict]] = {}

    if settings.configured_apis().get("fmp"):
        for ticker in shortlisted[:_FMP_MAX_TICKERS]:
            try:
                profile = await asyncio.to_thread(fmp.get_profile, ticker)
                ticker_profile[ticker] = profile
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"FMP fetch failed for {ticker}: {e}")

    # ── ApeWisdom retail sentiment (no API key required) ──────────────────
    retail_sentiment: dict[str, dict] = {}
    try:
        bot = TendieBot()
        retail_sentiment = await bot.get_retail_sentiment(watchlist=tickers)
    except Exception as e:
        logger.warning(f"ApeWisdom sentiment fetch failed: {e}")

    ticker_data: dict[str, TickerContext] = {}
    for ticker in all_tickers:
        ticker_bars_raw = bars.get(ticker, [])
        ticker_quote = quotes.get(ticker, {})
        profile = ticker_profile.get(ticker) or {}
        retail = retail_sentiment.get(ticker)

        current_price = (
            ticker_quote.get("mid_price")
            or ticker_quote.get("ask_price")
            or (ticker_bars_raw[-1]["close"] if ticker_bars_raw else 0.0)
        )
        volume = ticker_bars_raw[-1]["volume"] if ticker_bars_raw else 0
        sentiment_score = (
            ticker_sentiment[ticker].get("score")
            if ticker_sentiment.get(ticker)
            else None
        )

        retail_obj = None
        if retail:
            try:
                retail_obj = RetailSentiment(**retail)
            except Exception:
                pass

        ticker_data[ticker] = TickerContext(
            ticker=ticker,
            price_bars=[PriceBar(**b) for b in ticker_bars_raw],
            current_price=float(current_price or 0.0),
            volume=int(volume),
            rsi_14=ticker_rsi.get(ticker),
            macd=ticker_macd.get(ticker),
            bollinger_bands=None,
            recent_news=[
                NewsItem(
                    headline=n.get("headline", ""),
                    summary=n.get("summary"),
                    source=n.get("source"),
                    url=n.get("url"),
                    published_at=n.get("datetime"),
                )
                for n in ticker_news.get(ticker, [])[:10]
            ],
            news_sentiment_avg=sentiment_score,
            insider_sentiment=ticker_insider.get(ticker),
            pe_ratio=profile.get("pe_ratio") if profile else None,
            market_cap=profile.get("market_cap") if profile else None,
            earnings_date=_parse_date_safe(ticker_earnings_date.get(ticker)),
            retail_sentiment=retail_obj,
        )

    spy_bars_raw = bars.get("SPY", [])
    wash_sales = await _load_wash_sales(db)

    return MarketContext(
        timestamp=datetime.now(timezone.utc),
        spy_bars=[PriceBar(**b) for b in spy_bars_raw],
        vix_level=vix,
        sector_performance={},
        treasury_yield_10y=treasury_yield,
        wsb_trending_tickers=[],
        ticker_data=ticker_data,
        account_equity=0.0,   # Not needed for discovery — no portfolio state
        settled_cash=0.0,
        current_positions=[],
        wash_sale_blacklist=wash_sales,
    )


async def _load_wash_sales(db: AsyncSession) -> list[WashSaleEntry]:
    """Load active wash sale blacklist entries from DB."""
    from datetime import date
    today = date.today()
    rows = (await db.execute(
        select(WashSale).where(WashSale.blackout_until >= today)
    )).scalars().all()

    result = []
    for ws in rows:
        try:
            result.append(WashSaleEntry(
                ticker=ws.ticker,
                sale_date=ws.sale_date,
                loss_amount=ws.loss_amount,
                blackout_until=ws.blackout_until,
                is_year_end_blocked=ws.is_year_end_blocked,
            ))
        except Exception as e:
            logger.warning(f"Could not parse wash sale entry: {e}")
    return result
