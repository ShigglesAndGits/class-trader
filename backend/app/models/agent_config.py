"""
ORM models for per-agent LLM configuration and global provider settings.

LLMProviderConfig — single row (id=1), stores which provider is active
                    and OpenAI-compatible endpoint details.
AgentConfig       — one row per agent type, stores model, max_tokens,
                    and optional user-edited system prompt override.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LLMProviderConfig(Base):
    __tablename__ = "llm_provider_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # "anthropic" | "openai"
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="anthropic")
    # For OpenAI-compatible endpoints (Ollama, OpenRouter, LM Studio, etc.)
    openai_base_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    openai_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)


class AgentConfig(Base):
    __tablename__ = "agent_configs"
    __table_args__ = (UniqueConstraint("agent_type", name="uq_agent_config_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    # null = use default .md file / inline constant
    custom_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)
