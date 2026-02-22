"""
Explorer Agent — autonomously finds stock candidates via tool calling.

Uses Claude Sonnet (or whatever model is configured for EXPLORER) with
Anthropic tool use to search news, web, market movers, and look up tickers,
then finalises a list of candidates to feed into the discovery pipeline.

Web search priority:
  1. SearXNG — if SEARXNG_URL is set in env, hits the JSON API directly
  2. DuckDuckGo — fallback via duckduckgo-search (no API key required)

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
from app.runtime_config import get_agent_config

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 8
_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_MAX_TOKENS = 4096

# ── Tool definitions ──────────────────────────────────────────────────────────

_TOOLS = [
    {
        "name": "search_web",
        "description": (
            "Search the web for general information, news, market trends, or anything "
            "not covered by the financial-specific tools. Good for: sector themes, "
            "macro trends, company news, analyst commentary, upcoming catalysts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for, e.g. 'AI infrastructure stocks 2025' or 'energy sector momentum'",
                }
            },
            "required": ["query"],
        },
    },
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

You have access to live market data tools AND a general web search tool. Use them \
to find stocks that genuinely match the user's intent — news-driven catalysts, \
sector momentum, price criteria, etc.

Process:
1. Make 1-4 targeted tool calls to gather relevant data
2. Use search_web for broad context, sector trends, or anything the financial tools don't cover
3. Reason about which stocks best fit the user's request
4. Call finalize_candidates with 3-8 tickers

Rules:
- US-listed equities only
- Prefer stocks with meaningful liquidity (not micro-caps under $50M market cap unless user asks)
- Be decisive — don't overthink it
- If the user mentions a price range (e.g. "cheap" / "under $20"), respect it
- You have a limited number of iterations — finalize when you have enough data\
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

    # Read model/max_tokens from runtime config (set via Settings UI)
    agent_cfg = get_agent_config("EXPLORER") or {}
    model = agent_cfg.get("model") or _DEFAULT_MODEL
    max_tokens = agent_cfg.get("max_tokens") or _DEFAULT_MAX_TOKENS
    system = agent_cfg.get("custom_prompt") or _SYSTEM

    messages = [
        {"role": "user", "content": f"Find stocks matching this request: {query}"}
    ]

    for iteration in range(_MAX_ITERATIONS):
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=_TOOLS,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
        )

        if response.stop_reason == "end_turn":
            yield {
                "event": "pipeline_error",
                "data": {"error": "Explorer stopped without finding candidates."},
            }
            return

        if response.stop_reason == "max_tokens":
            logger.warning(
                f"Explorer hit max_tokens ({max_tokens}) on iteration {iteration}. "
                "Consider increasing max_tokens for EXPLORER in Settings."
            )

        if response.stop_reason not in ("tool_use", "max_tokens"):
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
                result_text = await _execute_tool(tool_name, tool_input, settings)
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

        # Pressure-inject on the last two iterations so the model knows to commit
        remaining = _MAX_ITERATIONS - 1 - iteration
        if 0 < remaining <= 2 and not finalized:
            pressure = (
                f"⚠️ Only {remaining} iteration(s) remaining. "
                "You should call finalize_candidates now with your best candidates."
            )
            user_content: list = list(tool_results) + [{"type": "text", "text": pressure}]
        else:
            user_content = tool_results

        messages.append({"role": "user", "content": user_content})  # type: ignore[arg-type]

        if finalized:
            yield {"event": "explorer_complete", "data": finalized}
            return

    yield {
        "event": "pipeline_error",
        "data": {"error": "Explorer reached max iterations without finalizing."},
    }


# ── Tool implementations ──────────────────────────────────────────────────────

async def _execute_tool(name: str, inputs: dict, settings) -> str:
    try:
        if name == "search_web":
            return await _tool_search_web(inputs.get("query", ""), settings)
        elif name == "search_financial_news":
            return await asyncio.to_thread(_tool_search_news, inputs.get("query", ""))
        elif name == "get_market_movers":
            return await _tool_get_movers(settings)
        elif name == "lookup_ticker":
            return await asyncio.to_thread(_tool_lookup_ticker, inputs.get("ticker", ""))
    except Exception as e:
        logger.warning(f"Explorer tool '{name}' failed: {e}")
        return f"Tool error: {e}"
    return "Unknown tool."


async def _tool_search_web(query: str, settings) -> str:
    """
    Web search: tries SearXNG first (if SEARXNG_URL is configured),
    falls back to DuckDuckGo.
    """
    # ── SearXNG ──────────────────────────────────────────────────────────────
    if settings.searxng_url:
        try:
            result = await _searxng_search(query, settings.searxng_url)
            if result:
                return result
        except Exception as e:
            logger.warning(f"SearXNG search failed, falling back to DuckDuckGo: {e}")

    # ── DuckDuckGo fallback ──────────────────────────────────────────────────
    return await asyncio.to_thread(_ddg_search, query)


async def _searxng_search(query: str, base_url: str) -> str:
    """Query SearXNG's JSON API."""
    import aiohttp

    url = f"{base_url.rstrip('/')}/search"
    params = {
        "q": query,
        "format": "json",
        "categories": "news,general",
        "language": "en",
        "time_range": "month",
    }
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise RuntimeError(f"SearXNG returned HTTP {resp.status}")
            data = await resp.json()

    results = data.get("results", [])
    if not results:
        return "No results found."

    lines = []
    for r in results[:10]:
        title = r.get("title", "")
        content = r.get("content", "")[:150]
        src_url = r.get("url", "")
        lines.append(f"- {title}: {content}... [{src_url}]")

    return "\n".join(lines)


def _ddg_search(query: str) -> str:
    """DuckDuckGo search via duckduckgo-search package (no API key required)."""
    try:
        from duckduckgo_search import DDGS
        results = list(DDGS().text(query, max_results=10))
        if not results:
            return "No results found."
        lines = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")[:150]
            href = r.get("href", "")
            lines.append(f"- {title}: {body}... [{href}]")
        return "\n".join(lines)
    except ImportError:
        return "Web search unavailable (duckduckgo-search not installed)."
    except Exception as e:
        return f"Web search failed: {e}"


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


async def _tool_get_movers(settings) -> str:
    """Get top market gainers/losers via Alpaca screener API."""
    import aiohttp

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
