"""
Market data formatters — convert MarketContext objects to readable LLM-friendly text.

These live here rather than in each agent to stay DRY and keep agent files focused
on agent logic.
"""

from datetime import datetime, timezone

from app.schemas.agents import RegimeAssessment, TickerAnalysis, ResearcherVerdict
from app.schemas.market import MarketContext, TickerContext


def _pct_change(bars: list, lookback: int) -> str | None:
    """Compute percentage change over lookback days from price bars."""
    closes = [b.close for b in bars if b.close]
    if len(closes) < 2:
        return None
    ref_idx = max(0, len(closes) - 1 - lookback)
    ref = closes[ref_idx]
    current = closes[-1]
    if ref == 0:
        return None
    return f"{((current - ref) / ref) * 100:+.1f}%"


def _vol_vs_avg(bars: list, lookback: int = 10) -> str | None:
    """Compare most recent volume to N-day average."""
    vols = [b.volume for b in bars if b.volume]
    if len(vols) < 2:
        return None
    recent = vols[-1]
    avg = sum(vols[-lookback:]) / min(len(vols), lookback)
    if avg == 0:
        return None
    return f"{recent / avg:.1f}x avg"


def format_broad_market(ctx: MarketContext) -> str:
    """Format broad market data for the Regime Analyst."""
    lines = [
        f"Analysis Date: {ctx.timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## SPY (S&P 500 ETF)",
    ]

    if ctx.spy_bars:
        last = ctx.spy_bars[-1]
        lines.append(f"Current: ${last.close:.2f}")
        for label, days in [("5d", 5), ("10d", 10), ("30d", 30)]:
            chg = _pct_change(ctx.spy_bars, days)
            if chg:
                lines.append(f"{label} return: {chg}")
        vol = _vol_vs_avg(ctx.spy_bars)
        if vol:
            lines.append(f"Volume: {vol}")

    lines.append("")
    lines.append("## Volatility & Macro")
    lines.append(f"VIX: {ctx.vix_level:.1f}" if ctx.vix_level else "VIX: unavailable")
    lines.append(
        f"10Y Treasury Yield: {ctx.treasury_yield_10y:.2f}%"
        if ctx.treasury_yield_10y
        else "10Y Yield: unavailable"
    )

    if ctx.sector_performance:
        lines.append("")
        lines.append("## Sector ETF Performance (Today)")
        for etf, ret in sorted(ctx.sector_performance.items(), key=lambda x: -x[1]):
            sign = "+" if ret >= 0 else ""
            lines.append(f"  {etf}: {sign}{ret:.2f}%")

    return "\n".join(lines)


def format_ticker(ticker: str, ctx: TickerContext) -> str:
    """Format a single ticker's data for Bull/Bear analysis."""
    lines = [f"## {ticker}"]
    lines.append(f"Current Price: ${ctx.current_price:.2f}")

    if ctx.price_bars:
        for label, days in [("5d", 5), ("10d", 10), ("30d", 30)]:
            chg = _pct_change(ctx.price_bars, days)
            if chg:
                lines.append(f"{label} change: {chg}")
        vol = _vol_vs_avg(ctx.price_bars)
        if vol:
            lines.append(f"Volume (latest vs 10d avg): {vol}")

    # Technicals
    tech_parts = []
    if ctx.rsi_14 is not None:
        flag = " ← OVERSOLD" if ctx.rsi_14 < 30 else " ← OVERBOUGHT" if ctx.rsi_14 > 70 else ""
        tech_parts.append(f"RSI(14)={ctx.rsi_14:.1f}{flag}")
    if ctx.macd:
        direction = "bullish" if ctx.macd.get("histogram", 0) > 0 else "bearish"
        tech_parts.append(f"MACD={ctx.macd.get('macd', 0):.3f} ({direction} histogram)")
    if ctx.bollinger_bands:
        bb = ctx.bollinger_bands
        if ctx.current_price and bb.get("upper") and bb.get("lower"):
            band_range = bb["upper"] - bb["lower"]
            if band_range > 0:
                pct = (ctx.current_price - bb["lower"]) / band_range * 100
                tech_parts.append(f"Bollinger: price at {pct:.0f}th pct of band")
    if tech_parts:
        lines.append("Technicals: " + " | ".join(tech_parts))

    # Sentiment & fundamentals
    if ctx.news_sentiment_avg is not None:
        sentiment_label = (
            "BULLISH" if ctx.news_sentiment_avg > 0.2
            else "BEARISH" if ctx.news_sentiment_avg < -0.2
            else "NEUTRAL"
        )
        lines.append(f"News Sentiment: {ctx.news_sentiment_avg:+.2f} ({sentiment_label})")
    if ctx.insider_sentiment is not None:
        ins_label = "buying" if ctx.insider_sentiment > 0.1 else "selling" if ctx.insider_sentiment < -0.1 else "neutral"
        lines.append(f"Insider Sentiment: {ctx.insider_sentiment:+.2f} ({ins_label})")
    if ctx.pe_ratio is not None:
        lines.append(f"P/E Ratio: {ctx.pe_ratio:.1f}")
    if ctx.market_cap is not None:
        cap_b = ctx.market_cap / 1e9
        lines.append(f"Market Cap: ${cap_b:.1f}B")
    if ctx.earnings_date:
        lines.append(f"Earnings Date: {ctx.earnings_date.isoformat()}")

    # Retail sentiment
    if ctx.retail_sentiment:
        rs = ctx.retail_sentiment
        lines.append(
            f"Retail (WSB/Reddit): {rs.mention_count_24h} mentions "
            f"({rs.mention_velocity:.1f}x normal), "
            f"hype={rs.hype_score:.2f}, "
            f"sentiment={rs.avg_sentiment:+.2f}"
        )
        if rs.caution_flags:
            lines.append(f"  ⚠ Caution flags: {', '.join(rs.caution_flags)}")
    else:
        lines.append("Retail Sentiment: no significant Reddit activity")

    # Headlines
    if ctx.recent_news:
        lines.append("Recent Headlines:")
        for item in ctx.recent_news[:5]:
            lines.append(f"  - {item.headline[:120]}")

    return "\n".join(lines)


def format_tickers_for_analysis(
    ctx: MarketContext,
    tickers: list[str],
) -> str:
    """Format all tickers for Bull/Bear/Researcher analysis."""
    regime_line = ""  # Regime is passed separately; tickers don't need it repeated
    sections = [format_ticker(t, ctx.ticker_data[t]) for t in tickers if t in ctx.ticker_data]
    return "\n\n".join(sections) if sections else "No ticker data available."


def format_bull_bear_for_researcher(
    bull_analyses: list[TickerAnalysis],
    bear_analyses: list[TickerAnalysis],
) -> str:
    """Format Bull and Bear analyses side-by-side for the Researcher."""
    bull_map = {a.ticker: a for a in bull_analyses}
    bear_map = {a.ticker: a for a in bear_analyses}
    all_tickers = sorted(set(list(bull_map) + list(bear_map)))

    lines = []
    for ticker in all_tickers:
        lines.append(f"## {ticker}")
        bull = bull_map.get(ticker)
        bear = bear_map.get(ticker)

        if bull:
            lines.append(
                f"BULL: {bull.stance} (confidence={bull.confidence:.2f})\n"
                f"  Reasoning: {bull.reasoning}\n"
                f"  Data: {'; '.join(bull.key_data_points)}"
            )
        else:
            lines.append("BULL: No analysis provided")

        if bear:
            lines.append(
                f"BEAR: {bear.stance} (confidence={bear.confidence:.2f})\n"
                f"  Reasoning: {bear.reasoning}\n"
                f"  Data: {'; '.join(bear.key_data_points)}"
            )
        else:
            lines.append("BEAR: No analysis provided")

    return "\n\n".join(lines)


def format_portfolio_manager_context(
    ctx: MarketContext,
    regime: RegimeAssessment,
    bull_analyses: list[TickerAnalysis],
    bear_analyses: list[TickerAnalysis],
    researcher_verdicts: list[ResearcherVerdict],
) -> str:
    """Format the full decision context for the Portfolio Manager."""
    lines = [
        "## Current Regime",
        f"Classification: {regime.regime} (confidence={regime.confidence:.2f})",
        f"Reasoning: {regime.reasoning}",
        f"Key indicators: {', '.join(regime.key_indicators)}",
        "",
        "## Portfolio State",
        f"Total Equity: ${ctx.account_equity:,.2f}",
        f"Settled Cash: ${ctx.settled_cash:,.2f}",
        f"Cash %: {(ctx.settled_cash / ctx.account_equity * 100) if ctx.account_equity else 0:.1f}%",
    ]

    if ctx.current_positions:
        lines.append("")
        lines.append("### Current Positions")
        for pos in ctx.current_positions:
            pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""
            lines.append(
                f"  {pos.ticker}: {pos.qty:.0f} shares @ ${pos.avg_entry_price:.2f} "
                f"(current ${pos.current_price:.2f}, "
                f"P&L: {pnl_sign}${pos.unrealized_pnl:.2f} / {pnl_sign}{pos.unrealized_pnl_pct:.1%})"
            )

    if ctx.wash_sale_blacklist:
        lines.append("")
        lines.append(
            "### Wash Sale Blacklist (do not buy without noting it)\n"
            + "\n".join(
                f"  {ws.ticker} — blackout until {ws.blackout_until.isoformat()}"
                f"{' (YEAR-END BLOCK)' if ws.is_year_end_blocked else ''}"
                for ws in ctx.wash_sale_blacklist
            )
        )

    # Researcher verdicts (the key signal for PM)
    lines.append("")
    lines.append("## Researcher Verdicts")
    verdict_map = {v.ticker: v for v in researcher_verdicts}
    bull_map = {a.ticker: a for a in bull_analyses}
    bear_map = {a.ticker: a for a in bear_analyses}

    for ticker in sorted(verdict_map):
        v = verdict_map[ticker]
        bull = bull_map.get(ticker)
        bear = bear_map.get(ticker)
        drift = " ⚠ THESIS DRIFT" if v.thesis_drift_warning else ""
        issues = f" | Issues: {', '.join(v.flagged_issues)}" if v.flagged_issues else ""
        bull_conf = f"{bull.confidence:.2f}" if bull else "n/a"
        bear_conf = f"{bear.confidence:.2f}" if bear else "n/a"
        lines.append(
            f"  {ticker}: {v.bull_bear_agreement}{drift} "
            f"(researcher conf={v.confidence:.2f}, bull={bull_conf}, bear={bear_conf})"
            f"{issues}"
        )
        if v.reasoning:
            lines.append(f"    → {v.reasoning}")

    return "\n".join(lines)


def format_penny_context(ctx: MarketContext, penny_tickers: list[str]) -> str:
    """Format penny stock data for the Degen agent."""
    lines = ["# Penny Sleeve — Ticker Analysis"]
    for ticker in penny_tickers:
        if ticker in ctx.ticker_data:
            lines.append(format_ticker(ticker, ctx.ticker_data[ticker]))
    return "\n\n".join(lines)
