"""
In-memory runtime configuration overrides.

Settings here take precedence over env vars for the current process lifetime.
They reset on restart — that's intentional. Persistent config changes should
go in .env or the database; these are for live updates without a restart.

Currently managed:
  - auto_approve: controls whether trades bypass the approval queue
  - _provider_config: active LLM provider + OpenAI-compatible endpoint details
  - _agent_configs: per-agent model, max_tokens, and custom prompt overrides
"""

from app.config import get_settings

_settings = get_settings()

# ── Auto-approve ────────────────────────────────────────────────────────────

# Initialized from env — mutable at runtime via the settings API
_auto_approve: bool = _settings.auto_approve


def get_auto_approve() -> bool:
    return _auto_approve


def set_auto_approve(value: bool) -> None:
    global _auto_approve
    _auto_approve = value


# ── LLM provider config ─────────────────────────────────────────────────────

_provider_config: dict = {
    "provider": "anthropic",
    "openai_base_url": None,
    "openai_api_key": None,
}


def get_provider_config() -> dict:
    return _provider_config


def set_provider_config(cfg: dict) -> None:
    global _provider_config
    _provider_config = cfg


# ── Per-agent LLM config ────────────────────────────────────────────────────

_agent_configs: dict[str, dict] = {}


def get_agent_config(agent_type: str) -> dict | None:
    """Return the runtime config for a given agent type, or None if not loaded."""
    return _agent_configs.get(agent_type)


def set_agent_config(agent_type: str, cfg: dict) -> None:
    _agent_configs[agent_type] = cfg


# ── DB → cache population ───────────────────────────────────────────────────

async def seed_runtime_from_db(db) -> None:
    """
    Load LLMProviderConfig and all AgentConfig rows from DB into memory.
    Called once at startup after seed_agent_configs().
    """
    from sqlalchemy import select
    from app.models.agent_config import AgentConfig, LLMProviderConfig

    global _provider_config

    # Provider
    result = await db.execute(select(LLMProviderConfig).where(LLMProviderConfig.id == 1))
    provider_row = result.scalars().first()
    if provider_row:
        _provider_config = {
            "provider": provider_row.provider,
            "openai_base_url": provider_row.openai_base_url,
            "openai_api_key": provider_row.openai_api_key,
        }

    # Per-agent
    agent_result = await db.execute(select(AgentConfig))
    for row in agent_result.scalars().all():
        _agent_configs[row.agent_type] = {
            "model": row.model,
            "max_tokens": row.max_tokens,
            "custom_prompt": row.custom_prompt,
        }
