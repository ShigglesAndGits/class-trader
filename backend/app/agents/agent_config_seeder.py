"""
Agent config seeder — populates LLMProviderConfig and AgentConfig with
default values on first startup. Idempotent: skips rows that already exist.

Called from main.py lifespan after init_db().
"""

import logging
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.agent_config import AgentConfig, LLMProviderConfig

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Inline prompt for TickerExtractor (no .md file)
_TICKER_EXTRACTOR_PROMPT = """You are a stock ticker extraction specialist.

Given a user's natural language query about stocks, extract:
1. **tickers**: Explicit stock symbols mentioned or strongly implied (e.g. "Tesla" → "TSLA").
   Return uppercase symbols only. No ETFs, no indexes, no funds.
2. **themes**: If no explicit tickers are given, identify thematic keywords
   (e.g. "energy momentum", "AI chips", "biotech catalyst").
3. **scan_news**: Set true if the query is theme-based and you couldn't find
   at least 2 explicit tickers — news scanning will find candidates.

Be conservative: only include tickers you're confident about.
If the user says "find me momentum plays in energy", return themes=["energy momentum"]
and scan_news=true. If they say "analyze NVDA and MSFT", return tickers=["NVDA", "MSFT"]
and scan_news=false."""

# agent_type → (prompt_file or None, default_max_tokens)
_AGENT_DEFAULTS: dict[str, tuple[str | None, int]] = {
    "REGIME_ANALYST": ("regime_analyst.md", 1024),
    "BULL": ("bull_agent.md", 4096),
    "BEAR": ("bear_agent.md", 4096),
    "RESEARCHER": ("researcher.md", 4096),
    "PORTFOLIO_MANAGER": ("portfolio_manager.md", 4096),
    "DEGEN": ("degen.md", 2048),
    "TICKER_EXTRACTOR": (None, 512),
    "DISCOVERY_PM": ("discovery_pm.md", 4096),
    # Explorer uses raw Anthropic tool-calling, not BaseAgent.
    # Stored here so model + max_tokens are configurable via the Settings UI.
    # custom_prompt overrides the inline _SYSTEM constant in explorer.py.
    "EXPLORER": (None, 4096),
}


_EXPLORER_SYSTEM = """\
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

_INLINE_PROMPTS: dict[str, str] = {
    "TICKER_EXTRACTOR": _TICKER_EXTRACTOR_PROMPT,
    "EXPLORER": _EXPLORER_SYSTEM,
}


def _load_default_prompt(agent_type: str, prompt_file: str | None) -> str:
    """Return the default prompt text for an agent."""
    if prompt_file is None:
        return _INLINE_PROMPTS.get(agent_type, "")
    path = _PROMPTS_DIR / prompt_file
    return path.read_text(encoding="utf-8").strip()


async def seed_agent_configs() -> None:
    """
    Ensure LLMProviderConfig (id=1) and all AgentConfig rows exist.
    Safe to call multiple times — only inserts missing rows.
    """
    settings = get_settings()
    default_model = settings.llm_model

    async with AsyncSessionLocal() as db:
        # ── Provider config (always id=1) ───────────────────────────────────
        result = await db.execute(
            select(LLMProviderConfig).where(LLMProviderConfig.id == 1)
        )
        if result.scalars().first() is None:
            db.add(LLMProviderConfig(
                id=1,
                provider="anthropic",
                openai_base_url=settings.openai_base_url or None,
                openai_api_key=settings.openai_api_key or None,
            ))
            logger.info("Seeded default LLMProviderConfig (Anthropic)")

        # ── Per-agent configs ────────────────────────────────────────────────
        existing_result = await db.execute(select(AgentConfig.agent_type))
        existing = {row[0] for row in existing_result.all()}

        for agent_type, (prompt_file, max_tokens) in _AGENT_DEFAULTS.items():
            if agent_type in existing:
                continue
            # Explorer defaults to Sonnet — it uses tool-calling and needs the extra power
            model = "claude-sonnet-4-6" if agent_type == "EXPLORER" else default_model
            db.add(AgentConfig(
                agent_type=agent_type,
                model=model,
                max_tokens=max_tokens,
                custom_prompt=None,
            ))
            logger.info(f"Seeded AgentConfig for {agent_type} (model={model}, max_tokens={max_tokens})")

        await db.commit()
