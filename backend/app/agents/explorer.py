"""
Explorer Agent — autonomously finds stock candidates via tool calling.

Uses Claude Sonnet with Anthropic tool use to search news, get market
movers, and look up specific tickers, then finalises a list of candidates
to feed into the discovery pipeline.

Yields SSE-compatible event dicts:
  - {"event": "explorer_tool_call", "data": {"tool": ..., "input": ..., "result": ...}}
  - {"event": "explorer_complete",  "data": {"tickers": [...], "reasoning": ...}}
  - {"event": "pipeline_error",     "data": {"error": ...}}
"""

import asyncio
import logging
from typing import AsyncGenerator

from anthropic import AsyncAnthropic
from anthropic.types import ToolUseBlock

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Tool definitions ──────────────────────────────────────────────────────────

_TOOLS = [
    {
        "name": "search_financial_news",
        "description": (
            "Search recent financial news headlines for stocks matching a theme or "
            "criteria. Returns the most relevant headlines and any tickers mentioned. "
            "Use this to find news-driven opportunities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "What to look for — e.g. 'AI chip momentum', "
                        "'cheap energy stocks', 'biotech catalyst'"
                    ),
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_market_movers",
        "description": (
            "Get today's top gaining and losing stocks by percent change. "
            "Useful for momentum plays or finding what is moving right now."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "lookup_ticker",
        "description": (
            "Get the current price, daily % change, and company profile for a "
            "specific ticker. Use this to validate or compare a specific stock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "US stock ticker symbol, e.g. NVDA, SOFI, PLTR",
                }
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "finalize_candidates",
        "description": (
            "Submit your final list of 3-8 US stock tickers to feed into the "
            "full agent analysis pipeline. Call this when you have identified "
            "the best candidates for the user's request."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of US stock ticker symbols",
                    "minItems": 1,
                    "maxItems": 8,
                },
                "reasoning": {
                    "type": "string",
                    "description": "Brief explanation of why you selected these tickers",
                },
            },
            "required": ["tickers", "reasoning"],
        },
    },
]

_SYSTEM = """\
You are a stock research assistant. Your job is to identify the best US-listed \
stocks to analyze based on the user's request.

You have access to live market data tools. Use them to find stocks that genuinely \
match the user's intent — news-driven catalysts, sector momentum, price criteria, etc.

Process:
1. Make 1-3 targeted tool calls to gather relevant data
2. Reason about which stocks best fit the user's request
3. Call finalize_candidates with 3-8 tickers

Rules:
- US-listed equities only
- Prefer stocks with meaningful liquidity (not micro-caps under $50M market cap unless user asks)
- Be decisive — don't overthink it
- If the user mentions a price range (e.g. "cheap" / "under $20"), respect it
"""


# ── Main async generator ──────────────────────────────────────────────────────

async def run_explorer(query: str) -> AsyncGenerator[dict, None]:
    """
    Async generator that runs the Explorer agent and yields SSE events.

    The caller should pipe these events into the SSE stream before continuing
    with the regular agent pipeline steps.
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    messages = [
        {"role": "user", "content": f"Find stocks matching this request: {query}"}
    ]

    for _iteration in range(4):
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_SYSTEM,
            tools=_TOOLS,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
        )

        if response.stop_reason == "end_turn":
            yield {
                "event": "pipeline_error",
                "data": {"error": "Explorer stopped without finding candidates."},
            }
            return

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        finalized: dict | None = None

        for block in response.content:
            if not isinstance(block, ToolUseBlock):
                continue

            tool_name = block.name
            tool_input = block.input  # type: ignore[union-attr]

            if tool_name == "finalize_candidates":
                tickers = [
                    t.upper().strip() for t in tool_input.get("tickers", [])
                ]
                reasoning = tool_input.get("reasoning", "")
                finalized = {"tickers": tickers, "reasoning": reasoning}
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Candidates finalized.",
                    }
                )
            else:
                result_text = await _execute_tool(tool_name, tool_input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    }
                )
                yield {
                    "event": "explorer_tool_call",
                    "data": {
                        "tool": tool_name,
                        "input": tool_input,
                        "result": result_text,
                    },
                }

        messages.append({"role": "assistant", "content": response.content})  # type: ignore[arg-type]
        messages.append({"role": "user", "content": tool_results})  # type: ignore[arg-type]

        if finalized:
            yield {"event": "explorer_complete", "data": finalized}
            return

    yield {
        "event": "pipeline_error",
        "data": {"error": "Explorer reached max iterations without finalizing."},
    }


# ── Tool implementations ──────────────────────────────────────────────────────

async def _execute_tool(name: str, inputs: dict) -> str:
    try:
        if name == "search_financial_news":
            return await asyncio.to_thread(_tool_search_news, inputs.get("query", ""))
        elif name == "get_market_movers":
            return await _tool_get_movers()
        elif name == "lookup_ticker":
            return await asyncio.to_thread(_tool_lookup_ticker, inputs.get("ticker", ""))
    except Exception as e:
        logger.warning(f"Explorer tool '{name}' failed: {e}")
        return f"Tool error: {e}"
    return "Unknown tool."


def _tool_search_news(query: str) -> str:
    """Search Finnhub general news, rank by keyword relevance, return headlines."""
    from app.data.finnhub_client import FinnhubClient

    client = FinnhubClient()
    try:
        news = client._client.general_news("general", min_id=0)
        if not news:
            return "No news available right now."

        query_lower = query.lower()
        keywords = {w for w in query_lower.split() if len(w) > 3}

        scored = []
        for article in news[:60]:
            headline = article.get("headline", "")
            summary = article.get("summary", "")
            text = (headline + " " + summary).lower()
            score = sum(1 for kw in keywords if kw in text)
            scored.append((score, article))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:12]

        lines = []
        for _score, article in top:
            headline = article.get("headline", "")
            related = article.get("related", "")
            if headline:
                line = f"- {headline}"
                if related:
                    line += f"  [tickers: {related}]"
                lines.append(line)

        return "\n".join(lines) if lines else "No relevant news found."
    except Exception as e:
        return f"News search failed: {e}"


async def _tool_get_movers() -> str:
    """Get top market gainers/losers via Alpaca screener API."""
    import aiohttp

    settings = get_settings()
    url = "https://data.alpaca.markets/v1beta1/screener/stocks/movers"
    headers = {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url, params={"top": 10, "by": "percent_change"}, headers=headers
            ) as resp:
                if resp.status != 200:
                    return f"Market movers unavailable (HTTP {resp.status})."
                data = await resp.json()

        gainers = data.get("gainers", [])
        losers = data.get("losers", [])

        lines = ["Top Gainers today:"]
        for g in gainers[:5]:
            sym = g.get("symbol", "?")
            pct = g.get("percent_change", 0.0)
            vol = g.get("volume", 0)
            lines.append(f"  {sym}  +{pct:.1f}%  vol={vol:,}")

        lines.append("Top Losers today:")
        for lo in losers[:5]:
            sym = lo.get("symbol", "?")
            pct = lo.get("percent_change", 0.0)
            vol = lo.get("volume", 0)
            lines.append(f"  {sym}  {pct:.1f}%  vol={vol:,}")

        return "\n".join(lines)
    except Exception as e:
        return f"Market movers error: {e}"


def _tool_lookup_ticker(ticker: str) -> str:
    """Return price, daily change, and company profile for a ticker."""
    from app.data.finnhub_client import FinnhubClient

    client = FinnhubClient()
    ticker = ticker.upper().strip()

    quote = client.get_quote(ticker)
    if not quote:
        return f"{ticker}: No data found — may be invalid or not trading."

    lines = [
        f"{ticker}: ${quote['current']:.2f}",
        f"  Change today: {quote['change_pct']:+.2f}%",
        f"  Day range: ${quote['low']:.2f} – ${quote['high']:.2f}",
    ]

    try:
        profile = client._client.company_profile2(symbol=ticker)
        if profile:
            name = profile.get("name", "")
            industry = profile.get("finnhubIndustry", "")
            mktcap = profile.get("marketCapitalization", 0)
            if name:
                lines.append(f"  Company: {name}")
            if industry:
                lines.append(f"  Sector: {industry}")
            if mktcap:
                lines.append(f"  Market cap: ${mktcap:.0f}M")
    except Exception:
        pass

    return "\n".join(lines)
