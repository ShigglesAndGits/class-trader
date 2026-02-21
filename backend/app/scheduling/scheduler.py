"""
Scheduler — APScheduler cron jobs for autonomous trading.

Jobs run on Eastern Time since US markets run ET.
Each job creates its own DB session and handles errors independently —
a crashed job must never crash the scheduler or halt other jobs.

Schedule:
  Morning Rebalance:   9:35 AM ET   Mon-Fri  — full pipeline run
  Noon Review:        12:00 PM ET   Mon-Fri  — full pipeline run
  News Monitor:       every 15 min  Mon-Fri  — Finnhub poll, pipeline trigger on spikes
  TendieBot Crawl:    every 30 min  Mon-Fri  — Reddit crawl, alerts on velocity spikes
  Portfolio Snapshot:  4:10 PM ET   Mon-Fri  — record equity curve data point
  Daily Summary:       4:15 PM ET   Mon-Fri  — send end-of-day notification
  Weekend Maintenance: 2:00 AM ET   Saturday — wash sale log cleanup, weekly report

Notes:
  - News Monitor and TendieBot both check _is_market_hours() at runtime so they
    no-op outside 9:30–4:00 PM ET even if cron fires on a holiday.
  - A cooldown prevents the news monitor from triggering more than one pipeline
    run per hour.
  - All jobs degrade gracefully when APIs are not configured.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.sql import func as sqlfunc

from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_scheduler: Optional[AsyncIOScheduler] = None

# Prevents news monitor from triggering more than one pipeline run per hour.
_last_news_trigger: Optional[datetime] = None
_NEWS_TRIGGER_COOLDOWN_MINUTES = 60


# ── Helpers ─────────────────────────────────────────────────────────────────

def _is_market_hours() -> bool:
    """Rough check: Mon–Fri, 9:30 AM – 4:00 PM ET. No holiday awareness."""
    now = datetime.now(_ET)
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now < market_close


def _settings():
    from app.config import get_settings
    return get_settings()


# ── Jobs ────────────────────────────────────────────────────────────────────

async def _morning_rebalance() -> None:
    """Full pipeline run at 9:35 AM ET."""
    logger.info("Scheduler: Morning Rebalance starting.")
    try:
        from app.agents.pipeline import run_pipeline_background
        await run_pipeline_background("MORNING")
    except Exception as e:
        logger.error(f"Scheduler: Morning Rebalance failed: {e}", exc_info=True)
        try:
            from app.notifications.notifier import get_notifier
            await get_notifier().system_error(f"Morning Rebalance job failed: {e}")
        except Exception:
            pass


async def _noon_review() -> None:
    """Full pipeline run at noon."""
    logger.info("Scheduler: Noon Review starting.")
    try:
        from app.agents.pipeline import run_pipeline_background
        await run_pipeline_background("NOON")
    except Exception as e:
        logger.error(f"Scheduler: Noon Review failed: {e}", exc_info=True)
        try:
            from app.notifications.notifier import get_notifier
            await get_notifier().system_error(f"Noon Review job failed: {e}")
        except Exception:
            pass


async def _news_monitor() -> None:
    """
    Lightweight Finnhub news + sentiment poll.
    Saves new articles to the DB and triggers a pipeline run when any watchlist
    ticker's aggregate sentiment score exceeds |0.8|.
    """
    global _last_news_trigger

    if not _is_market_hours():
        return

    s = _settings()
    if not s.finnhub_api_key:
        return

    logger.debug("Scheduler: News monitor tick.")

    try:
        from app.data.finnhub_client import FinnhubClient
        from app.models.market_data import NewsItem
        from app.models.watchlist import Watchlist

        client = FinnhubClient()
        high_impact_ticker: Optional[str] = None
        high_impact_score: float = 0.0

        async with AsyncSessionLocal() as db:
            # Load active non-benchmark tickers.
            result = await db.execute(
                select(Watchlist.ticker).where(
                    Watchlist.is_active == True,  # noqa: E712
                    Watchlist.sleeve.in_(["MAIN", "PENNY"]),
                )
            )
            tickers = [row[0] for row in result.all()]

            if not tickers:
                return

            for ticker in tickers:
                try:
                    # ── Aggregate sentiment ────────────────────────────────
                    sentiment_data = await asyncio.to_thread(client.get_news_sentiment, ticker)
                    score = sentiment_data["score"] if sentiment_data else None

                    is_high_impact = score is not None and abs(score) > 0.8

                    if is_high_impact and (
                        high_impact_ticker is None or abs(score) > abs(high_impact_score)
                    ):
                        high_impact_ticker = ticker
                        high_impact_score = score

                    # ── Fetch and store articles ───────────────────────────
                    articles = await asyncio.to_thread(
                        client.get_company_news, ticker, 2  # last 2 hours
                    )

                    for item in articles:
                        url = item.get("url") or None
                        headline = item.get("headline", "").strip()
                        if not headline:
                            continue

                        # Dedup: skip if URL already exists in DB.
                        if url:
                            dup = await db.execute(
                                select(NewsItem.id).where(NewsItem.url == url).limit(1)
                            )
                            if dup.scalars().first():
                                continue
                        else:
                            dup = await db.execute(
                                select(NewsItem.id).where(
                                    NewsItem.ticker == ticker,
                                    NewsItem.headline == headline,
                                ).limit(1)
                            )
                            if dup.scalars().first():
                                continue

                        # Convert Finnhub unix timestamp → datetime.
                        raw_ts = item.get("datetime")
                        published_at = (
                            datetime.fromtimestamp(raw_ts, tz=timezone.utc)
                            if raw_ts
                            else None
                        )

                        db.add(
                            NewsItem(
                                ticker=ticker,
                                headline=headline,
                                summary=item.get("summary") or None,
                                source=item.get("source") or None,
                                url=url,
                                sentiment_score=score,  # aggregate score, best we have
                                published_at=published_at,
                                triggered_analysis=is_high_impact,
                            )
                        )

                    # Gentle rate limiting between tickers.
                    await asyncio.sleep(0.2)

                except Exception as e:
                    logger.warning(f"News monitor: error for {ticker}: {e}")
                    continue

            await db.commit()

        # Trigger a pipeline if high-impact sentiment found and cooldown elapsed.
        if high_impact_ticker:
            now = datetime.now(_ET)
            cooldown_ok = (
                _last_news_trigger is None
                or (now - _last_news_trigger).total_seconds()
                > _NEWS_TRIGGER_COOLDOWN_MINUTES * 60
            )
            if cooldown_ok:
                logger.info(
                    f"Scheduler: High-impact news for {high_impact_ticker} "
                    f"(score={high_impact_score:+.2f}) — triggering NEWS_TRIGGER pipeline."
                )
                _last_news_trigger = now
                from app.agents.pipeline import run_pipeline_background
                await run_pipeline_background("NEWS_TRIGGER")

    except Exception as e:
        logger.error(f"Scheduler: News monitor failed: {e}", exc_info=True)


async def _tendiebot_crawl() -> None:
    """
    Reddit retail sentiment crawl every 30 minutes during market hours.
    Saves RedditMention records and sends a hype alert if any watchlist ticker
    shows mention_velocity ≥ 5x above its baseline.
    """
    if not _is_market_hours():
        return

    s = _settings()
    if not (s.reddit_client_id and s.reddit_client_secret):
        return

    logger.debug("Scheduler: TendieBot crawl tick.")

    try:
        from app.data.tendiebot import TendieBot
        from app.models.market_data import RedditMention
        from app.models.watchlist import Watchlist

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Watchlist.ticker).where(
                    Watchlist.is_active == True,  # noqa: E712
                    Watchlist.sleeve.in_(["MAIN", "PENNY"]),
                )
            )
            watchlist_tickers = [row[0] for row in result.all()]

            if not watchlist_tickers:
                return

            bot = TendieBot()
            sentiments = await bot.get_retail_sentiment(watchlist_tickers)

            spike_alerts: list[str] = []

            for sent in sentiments:
                # Save one RedditMention row per ticker per crawl (top post as representative).
                top_post = sent.top_posts[0] if sent.top_posts else f"{sent.ticker} mentioned on Reddit"
                subreddit = sent.subreddits[0] if sent.subreddits else "wallstreetbets"

                db.add(
                    RedditMention(
                        ticker=sent.ticker,
                        subreddit=subreddit,
                        post_title=top_post[:500],  # guard against extremely long titles
                        post_url=None,
                        sentiment_score=sent.avg_sentiment,
                        hype_score=sent.hype_score,
                        mention_velocity=sent.mention_velocity,
                    )
                )

                if sent.mention_velocity is not None and sent.mention_velocity >= 5.0:
                    spike_alerts.append(
                        f"{sent.ticker}: {sent.mention_velocity:.1f}x velocity "
                        f"(hype={sent.hype_score:.2f})"
                    )

            await db.commit()

        if spike_alerts:
            from app.notifications.notifier import get_notifier
            alert_body = "Retail mention velocity spike:\n" + "\n".join(
                f"• {a}" for a in spike_alerts
            )
            await get_notifier().send(
                event_type="retail_spike",
                message=alert_body,
                title="TendieBot — Hype Alert",
            )
            logger.info(f"TendieBot: spike alerts for {len(spike_alerts)} ticker(s).")

    except Exception as e:
        logger.error(f"Scheduler: TendieBot crawl failed: {e}", exc_info=True)


async def _portfolio_snapshot() -> None:
    """
    Record a PortfolioSnapshot after market close (4:10 PM ET).
    This feeds the equity curve chart in the Analytics page.

    Tries to get live market values from Alpaca; falls back to DB cost_basis.
    """
    logger.info("Scheduler: Recording portfolio snapshot.")

    try:
        s = _settings()
        from app.models.market_data import PortfolioSnapshot
        from app.models.trading import Position

        total_equity = float(s.main_sleeve_allocation + s.penny_sleeve_allocation)
        cash_balance = 0.0
        alpaca_market_values: dict[str, float] = {}

        # ── Try live Alpaca data ───────────────────────────────────────────
        if s.alpaca_api_key and s.alpaca_secret_key:
            try:
                from app.data.alpaca_client import AlpacaClient
                alpaca = AlpacaClient()
                account = await asyncio.to_thread(alpaca.get_account)
                total_equity = float(account["equity"])
                cash_balance = float(account["cash"])
                live_positions = await asyncio.to_thread(alpaca.get_positions)
                alpaca_market_values = {p["ticker"]: float(p["market_value"]) for p in live_positions}
            except Exception as e:
                logger.warning(f"Snapshot: Alpaca unavailable, using DB fallback: {e}")

        # ── Split equity by sleeve using DB positions ──────────────────────
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Position).where(Position.is_open == True)  # noqa: E712
            )
            db_positions = result.scalars().all()

            main_equity = 0.0
            penny_equity = 0.0

            for pos in db_positions:
                value = alpaca_market_values.get(pos.ticker, pos.cost_basis)
                if pos.sleeve == "MAIN":
                    main_equity += value
                elif pos.sleeve == "PENNY":
                    penny_equity += value

            # When Alpaca data wasn't available, derive totals from DB.
            if not alpaca_market_values:
                cash_balance = max(
                    0.0,
                    s.main_sleeve_allocation + s.penny_sleeve_allocation
                    - main_equity - penny_equity,
                )
                total_equity = main_equity + penny_equity + cash_balance

            # ── SPY benchmark quote ────────────────────────────────────────
            spy_value: Optional[float] = None
            if s.finnhub_api_key:
                try:
                    from app.data.finnhub_client import FinnhubClient
                    fh = FinnhubClient()
                    spy_quote = await asyncio.to_thread(fh.get_quote, "SPY")
                    if spy_quote:
                        spy_value = float(spy_quote["current"])
                except Exception as e:
                    logger.warning(f"Snapshot: SPY quote unavailable: {e}")

            # ── Daily P&L vs yesterday's snapshot ─────────────────────────
            yesterday = date.today() - timedelta(days=1)
            prev = await db.execute(
                select(PortfolioSnapshot)
                .where(sqlfunc.date(PortfolioSnapshot.timestamp) == yesterday)
                .order_by(PortfolioSnapshot.timestamp.desc())
                .limit(1)
            )
            prev_snap = prev.scalars().first()

            daily_pnl: Optional[float] = None
            daily_pnl_pct: Optional[float] = None
            if prev_snap and prev_snap.total_equity > 0:
                daily_pnl = total_equity - prev_snap.total_equity
                daily_pnl_pct = daily_pnl / prev_snap.total_equity

            db.add(
                PortfolioSnapshot(
                    main_equity=main_equity,
                    penny_equity=penny_equity,
                    total_equity=total_equity,
                    cash_balance=cash_balance,
                    spy_benchmark_value=spy_value,
                    daily_pnl=daily_pnl,
                    daily_pnl_pct=daily_pnl_pct,
                )
            )
            await db.commit()

        logger.info(
            f"Snapshot saved: total=${total_equity:.2f} "
            f"(main=${main_equity:.2f}, penny=${penny_equity:.2f}, cash=${cash_balance:.2f})"
        )

    except Exception as e:
        logger.error(f"Scheduler: Portfolio snapshot failed: {e}", exc_info=True)


async def _daily_summary() -> None:
    """
    End-of-day notification at 4:15 PM ET.
    Aggregates today's executed trade count, P&L, and current regime.
    """
    logger.info("Scheduler: Generating daily summary.")

    try:
        from app.models.market_data import PortfolioSnapshot
        from app.models.pipeline import PipelineRun
        from app.models.trading import TradeDecision
        from app.notifications.notifier import get_notifier

        today = date.today()

        async with AsyncSessionLocal() as db:
            # Count executed trades today.
            trades_result = await db.execute(
                select(sqlfunc.count(TradeDecision.id)).where(
                    sqlfunc.date(TradeDecision.created_at) == today,
                    TradeDecision.status == "EXECUTED",
                )
            )
            trades_executed = int(trades_result.scalar() or 0)

            # Today's P&L from the snapshot just recorded by _portfolio_snapshot.
            snap_result = await db.execute(
                select(PortfolioSnapshot)
                .where(sqlfunc.date(PortfolioSnapshot.timestamp) == today)
                .order_by(PortfolioSnapshot.timestamp.desc())
                .limit(1)
            )
            snap = snap_result.scalars().first()

            main_pnl = 0.0
            penny_pnl = 0.0
            if snap and snap.daily_pnl is not None:
                sleeve_total = snap.main_equity + snap.penny_equity
                if sleeve_total > 0:
                    main_pnl = snap.daily_pnl * (snap.main_equity / sleeve_total)
                    penny_pnl = snap.daily_pnl * (snap.penny_equity / sleeve_total)

            # Most recent regime from today's pipeline runs.
            regime_result = await db.execute(
                select(PipelineRun.regime)
                .where(
                    sqlfunc.date(PipelineRun.started_at) == today,
                    PipelineRun.status == "COMPLETED",
                    PipelineRun.regime.is_not(None),
                )
                .order_by(PipelineRun.started_at.desc())
                .limit(1)
            )
            regime = str(regime_result.scalar() or "UNKNOWN")

        await get_notifier().daily_summary(
            main_pnl=main_pnl,
            penny_pnl=penny_pnl,
            trades_executed=trades_executed,
            regime=regime,
        )
        logger.info(f"Daily summary sent: {trades_executed} trade(s), regime={regime}.")

    except Exception as e:
        logger.error(f"Scheduler: Daily summary failed: {e}", exc_info=True)


async def _weekend_maintenance() -> None:
    """
    Saturday 2:00 AM maintenance.
    Logs expired wash sale records and the week's performance.
    Records are kept for history; we don't delete anything.
    """
    logger.info("Scheduler: Weekend maintenance starting.")

    try:
        from app.models.market_data import PortfolioSnapshot
        from app.models.risk import WashSale

        today = date.today()
        week_ago = today - timedelta(days=7)

        async with AsyncSessionLocal() as db:
            # Log wash sale records whose blackout window has passed.
            expired_result = await db.execute(
                select(WashSale).where(
                    WashSale.blackout_until < today,
                    WashSale.rebought == False,  # noqa: E712
                )
            )
            expired = expired_result.scalars().all()
            for ws in expired:
                logger.info(
                    f"Maintenance: wash sale window expired — {ws.ticker} "
                    f"(loss=${ws.loss_amount:.2f}, blackout ended {ws.blackout_until})"
                )

            # Weekly performance summary (log only for now).
            snaps_result = await db.execute(
                select(PortfolioSnapshot)
                .where(sqlfunc.date(PortfolioSnapshot.timestamp) >= week_ago)
                .order_by(PortfolioSnapshot.timestamp)
            )
            snaps = snaps_result.scalars().all()

            if len(snaps) >= 2:
                first, last = snaps[0], snaps[-1]
                weekly_pnl = last.total_equity - first.total_equity
                weekly_pct = weekly_pnl / first.total_equity if first.total_equity else 0.0
                logger.info(
                    f"Weekly performance: {weekly_pct:+.1%} (${weekly_pnl:+.2f}) "
                    f"— ${first.total_equity:.2f} → ${last.total_equity:.2f}"
                )
            else:
                logger.info("Weekly performance: not enough snapshot data yet.")

        logger.info("Scheduler: Weekend maintenance complete.")

    except Exception as e:
        logger.error(f"Scheduler: Weekend maintenance failed: {e}", exc_info=True)


# ── Lifecycle ───────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """
    Initialize and start the AsyncIOScheduler.
    Called from FastAPI lifespan startup. All times are Eastern (ET).
    """
    global _scheduler

    _scheduler = AsyncIOScheduler()

    et = {"timezone": "America/New_York"}

    # Full pipeline runs
    _scheduler.add_job(
        _morning_rebalance,
        CronTrigger(hour=9, minute=35, day_of_week="mon-fri", **et),
        id="morning_rebalance",
        name="Morning Rebalance",
        max_instances=1,
        replace_existing=True,
    )
    _scheduler.add_job(
        _noon_review,
        CronTrigger(hour=12, minute=0, day_of_week="mon-fri", **et),
        id="noon_review",
        name="Noon Review",
        max_instances=1,
        replace_existing=True,
    )

    # Market monitoring (runtime market-hours guard inside each job)
    _scheduler.add_job(
        _news_monitor,
        CronTrigger(minute="*/15", day_of_week="mon-fri", **et),
        id="news_monitor",
        name="News Monitor",
        max_instances=1,
        replace_existing=True,
    )
    _scheduler.add_job(
        _tendiebot_crawl,
        CronTrigger(minute="*/30", day_of_week="mon-fri", **et),
        id="tendiebot_crawl",
        name="TendieBot Crawl",
        max_instances=1,
        replace_existing=True,
    )

    # End-of-day
    _scheduler.add_job(
        _portfolio_snapshot,
        CronTrigger(hour=16, minute=10, day_of_week="mon-fri", **et),
        id="portfolio_snapshot",
        name="Portfolio Snapshot",
        max_instances=1,
        replace_existing=True,
    )
    _scheduler.add_job(
        _daily_summary,
        CronTrigger(hour=16, minute=15, day_of_week="mon-fri", **et),
        id="daily_summary",
        name="Daily Summary",
        max_instances=1,
        replace_existing=True,
    )

    # Weekend
    _scheduler.add_job(
        _weekend_maintenance,
        CronTrigger(day_of_week="sat", hour=2, minute=0, **et),
        id="weekend_maintenance",
        name="Weekend Maintenance",
        max_instances=1,
        replace_existing=True,
    )

    _scheduler.start()
    job_names = [j.name for j in _scheduler.get_jobs()]
    logger.info(f"Scheduler started — {len(job_names)} jobs: {', '.join(job_names)}")


def shutdown_scheduler() -> None:
    """Stop the scheduler gracefully. Called from FastAPI lifespan shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
    _scheduler = None
