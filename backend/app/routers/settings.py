"""
Settings API — runtime configuration and system status.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.agent_config import AgentConfig, LLMProviderConfig
from app.models.risk import CircuitBreakerEvent
from app.runtime_config import (
    get_agent_config,
    get_auto_approve,
    get_provider_config,
    set_agent_config,
    set_auto_approve,
    set_provider_config,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_PROMPTS_DIR = Path(__file__).parent.parent / "agents" / "prompts"

# Inline prompts for agents without .md files
_TICKER_EXTRACTOR_DEFAULT_PROMPT = """You are a stock ticker extraction specialist.

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

_EXPLORER_DEFAULT_PROMPT = """\
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
- You have a limited number of iterations — finalize when you have enough data"""

_INLINE_PROMPTS: dict[str, str] = {
    "TICKER_EXTRACTOR": _TICKER_EXTRACTOR_DEFAULT_PROMPT,
    "EXPLORER": _EXPLORER_DEFAULT_PROMPT,
}

_AGENT_PROMPT_FILES: dict[str, str | None] = {
    "REGIME_ANALYST": "regime_analyst.md",
    "BULL": "bull_agent.md",
    "BEAR": "bear_agent.md",
    "RESEARCHER": "researcher.md",
    "PORTFOLIO_MANAGER": "portfolio_manager.md",
    "DEGEN": "degen.md",
    "TICKER_EXTRACTOR": None,
    "DISCOVERY_PM": "discovery_pm.md",
    "EXPLORER": None,
}

_AGENT_LABELS: dict[str, str] = {
    "REGIME_ANALYST": "Regime Analyst",
    "BULL": "Bull Agent",
    "BEAR": "Bear Agent",
    "RESEARCHER": "Researcher",
    "PORTFOLIO_MANAGER": "Portfolio Manager",
    "DEGEN": "Degen (Penny)",
    "TICKER_EXTRACTOR": "Ticker Extractor",
    "DISCOVERY_PM": "Discovery PM",
    "EXPLORER": "Explorer",
}


def _load_default_prompt(agent_type: str) -> str:
    prompt_file = _AGENT_PROMPT_FILES.get(agent_type)
    if prompt_file is None:
        return _INLINE_PROMPTS.get(agent_type, "")
    path = _PROMPTS_DIR / prompt_file
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


# ── Existing endpoints ──────────────────────────────────────────────────────

@router.get("/")
async def get_settings_view():
    """All current runtime settings and API configuration status."""
    s = get_settings()
    return {
        "auto_approve": get_auto_approve(),
        "auto_approve_env": s.auto_approve,
        "alpaca_paper": s.alpaca_paper,
        "main_sleeve_allocation": s.main_sleeve_allocation,
        "penny_sleeve_allocation": s.penny_sleeve_allocation,
        "max_position_pct_main": s.max_position_pct_main,
        "max_position_dollars_penny": s.max_position_dollars_penny,
        "min_confidence_main": s.min_confidence_main,
        "min_confidence_penny": s.min_confidence_penny,
        "daily_loss_limit_main_pct": s.daily_loss_limit_main_pct,
        "daily_loss_limit_penny_pct": s.daily_loss_limit_penny_pct,
        "consecutive_loss_pause": s.consecutive_loss_pause,
        "timezone": s.timezone,
        "apis_configured": s.configured_apis(),
        "llm_model": s.llm_model,
    }


class AutoApproveRequest(BaseModel):
    enabled: bool


@router.put("/auto-approve")
async def toggle_auto_approve(body: AutoApproveRequest):
    """Toggle auto-approve at runtime. Resets on restart."""
    set_auto_approve(body.enabled)
    state = "enabled" if body.enabled else "disabled"
    logger.info(f"Auto-approve {state} via API (runtime only — resets on restart).")
    return {
        "auto_approve": get_auto_approve(),
        "note": "Runtime change only. Update AUTO_APPROVE in .env to persist.",
    }


@router.get("/circuit-breakers")
async def get_circuit_breakers(db: AsyncSession = Depends(get_db)):
    """List all circuit breaker events, active first."""
    result = await db.execute(
        select(CircuitBreakerEvent).order_by(
            CircuitBreakerEvent.is_active.desc(),
            CircuitBreakerEvent.triggered_at.desc(),
        )
    )
    events = result.scalars().all()

    return {
        "circuit_breakers": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "sleeve": e.sleeve,
                "reason": e.reason,
                "is_active": e.is_active,
                "triggered_at": e.triggered_at.isoformat(),
                "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
                "resolved_by": e.resolved_by,
            }
            for e in events
        ],
        "active_count": sum(1 for e in events if e.is_active),
    }


@router.post("/circuit-breakers/{event_id}/resolve")
async def resolve_circuit_breaker(event_id: int, db: AsyncSession = Depends(get_db)):
    """Manually resolve (deactivate) a circuit breaker to resume trading."""
    from app.execution.risk_manager import resolve_circuit_breaker

    event = await resolve_circuit_breaker(db, event_id, resolved_by="MANUAL")
    if not event:
        raise HTTPException(status_code=404, detail=f"Circuit breaker #{event_id} not found.")

    logger.info(f"Circuit breaker #{event_id} resolved manually via API.")
    return {
        "status": "resolved",
        "event_id": event_id,
        "event_type": event.event_type,
        "sleeve": event.sleeve,
    }


# ── LLM provider config ─────────────────────────────────────────────────────

@router.get("/llm/provider")
async def get_llm_provider(db: AsyncSession = Depends(get_db)):
    """Current LLM provider config. API key is never returned — only has_api_key bool."""
    result = await db.execute(select(LLMProviderConfig).where(LLMProviderConfig.id == 1))
    row = result.scalars().first()
    if not row:
        return {"provider": "anthropic", "openai_base_url": None, "has_api_key": False}
    return {
        "provider": row.provider,
        "openai_base_url": row.openai_base_url,
        "has_api_key": bool(row.openai_api_key),
    }


class ProviderUpdateRequest(BaseModel):
    provider: str  # "anthropic" | "openai"
    openai_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None  # None = don't change existing key


@router.put("/llm/provider")
async def update_llm_provider(body: ProviderUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update active LLM provider and OpenAI-compatible endpoint details."""
    if body.provider not in ("anthropic", "openai"):
        raise HTTPException(status_code=422, detail="provider must be 'anthropic' or 'openai'")

    result = await db.execute(select(LLMProviderConfig).where(LLMProviderConfig.id == 1))
    row = result.scalars().first()

    if row is None:
        row = LLMProviderConfig(id=1)
        db.add(row)

    row.provider = body.provider
    row.openai_base_url = body.openai_base_url or None
    if body.openai_api_key is not None:  # explicit None = keep existing
        row.openai_api_key = body.openai_api_key or None
    row.updated_at = datetime.now(timezone.utc)

    await db.flush()

    # Update runtime cache so next agent instantiation picks up the change
    set_provider_config({
        "provider": row.provider,
        "openai_base_url": row.openai_base_url,
        "openai_api_key": row.openai_api_key,
    })

    logger.info(f"LLM provider updated to {row.provider}")
    return {
        "provider": row.provider,
        "openai_base_url": row.openai_base_url,
        "has_api_key": bool(row.openai_api_key),
    }


# ── Per-agent LLM config ────────────────────────────────────────────────────

def _agent_row_to_dict(row: AgentConfig) -> dict:
    default_prompt = _load_default_prompt(row.agent_type)
    return {
        "agent_type": row.agent_type,
        "label": _AGENT_LABELS.get(row.agent_type, row.agent_type),
        "model": row.model,
        "max_tokens": row.max_tokens,
        "has_custom_prompt": row.custom_prompt is not None,
        "effective_prompt": row.custom_prompt if row.custom_prompt else default_prompt,
        "default_prompt": default_prompt,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/llm/agents")
async def get_all_agent_configs(db: AsyncSession = Depends(get_db)):
    """List model, max_tokens, and prompt status for all agents."""
    result = await db.execute(
        select(AgentConfig).order_by(AgentConfig.agent_type)
    )
    rows = result.scalars().all()
    return {"agents": [_agent_row_to_dict(r) for r in rows]}


@router.get("/llm/agents/{agent_type}")
async def get_agent_config_detail(agent_type: str, db: AsyncSession = Depends(get_db)):
    """Full config for a single agent including both effective and default prompts."""
    agent_type = agent_type.upper()
    result = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_type == agent_type)
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No config found for agent {agent_type}")
    return _agent_row_to_dict(row)


class AgentModelUpdateRequest(BaseModel):
    model: str
    max_tokens: int


@router.put("/llm/agents/{agent_type}")
async def update_agent_config(
    agent_type: str,
    body: AgentModelUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update model and max_tokens for a specific agent."""
    agent_type = agent_type.upper()
    if body.max_tokens < 256:
        raise HTTPException(status_code=422, detail="max_tokens must be at least 256")

    result = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_type == agent_type)
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No config found for agent {agent_type}")

    row.model = body.model
    row.max_tokens = body.max_tokens
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Update runtime cache
    cached = get_agent_config(agent_type) or {}
    set_agent_config(agent_type, {**cached, "model": row.model, "max_tokens": row.max_tokens})

    logger.info(f"Agent {agent_type} updated: model={row.model}, max_tokens={row.max_tokens}")
    return _agent_row_to_dict(row)


class AgentPromptRequest(BaseModel):
    prompt: str


@router.put("/llm/agents/{agent_type}/prompt")
async def set_agent_prompt(
    agent_type: str,
    body: AgentPromptRequest,
    db: AsyncSession = Depends(get_db),
):
    """Set a custom system prompt for an agent. Overrides the default .md file."""
    agent_type = agent_type.upper()
    if not body.prompt.strip():
        raise HTTPException(status_code=422, detail="Prompt cannot be empty")

    result = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_type == agent_type)
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No config found for agent {agent_type}")

    row.custom_prompt = body.prompt.strip()
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Update runtime cache
    cached = get_agent_config(agent_type) or {}
    set_agent_config(agent_type, {**cached, "custom_prompt": row.custom_prompt})

    logger.info(f"Agent {agent_type} custom prompt saved ({len(row.custom_prompt)} chars)")
    return _agent_row_to_dict(row)


@router.delete("/llm/agents/{agent_type}/prompt")
async def reset_agent_prompt(agent_type: str, db: AsyncSession = Depends(get_db)):
    """Reset an agent's prompt to the default (.md file content). Clears custom_prompt."""
    agent_type = agent_type.upper()
    result = await db.execute(
        select(AgentConfig).where(AgentConfig.agent_type == agent_type)
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No config found for agent {agent_type}")

    row.custom_prompt = None
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Update runtime cache
    cached = get_agent_config(agent_type) or {}
    set_agent_config(agent_type, {**cached, "custom_prompt": None})

    logger.info(f"Agent {agent_type} prompt reset to default")
    return _agent_row_to_dict(row)
