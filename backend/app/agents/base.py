"""
BaseAgent — foundation for all LLM agents in the pipeline.

Handles:
  - Provider-aware client construction (Anthropic or OpenAI-compatible)
  - Structured output via Instructor
  - Per-agent model, max_tokens, and prompt loaded from runtime config (DB-backed)
  - Retry logic with exponential backoff on API failures
  - Full interaction logging to the database (prompt, response, tokens, latency)
  - Consistent error handling and propagation
"""

import logging
import time
from abc import ABC
from pathlib import Path
from typing import TypeVar

import instructor
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.pipeline import AgentInteraction
from app.runtime_config import get_agent_config, get_provider_config

T = TypeVar("T")

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename: str) -> str:
    """Load a system prompt from the prompts/ directory."""
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def _build_instructor_client(settings):
    """
    Build an Instructor-patched async LLM client based on the active provider config.

    - anthropic: uses AsyncAnthropic + instructor.from_anthropic()
    - openai:    uses AsyncOpenAI (with configurable base_url) + instructor.from_openai()
    """
    provider_cfg = get_provider_config()
    provider = provider_cfg.get("provider", "anthropic")

    if provider == "openai":
        from openai import AsyncOpenAI
        base_url = provider_cfg.get("openai_base_url") or settings.openai_base_url or None
        api_key = provider_cfg.get("openai_api_key") or settings.openai_api_key or "ollama"
        raw_client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        return instructor.from_openai(raw_client)
    else:
        from anthropic import AsyncAnthropic
        raw_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        return instructor.from_anthropic(raw_client)


class BaseAgent(ABC):
    """
    Abstract base for all pipeline agents.

    Subclasses must define:
      - agent_type: str  — matches AgentInteraction.agent_type in DB
      - system_prompt: str  — default system persona (loaded from prompts/ or inline)

    At instantiation, runtime config (model, max_tokens, custom prompt) is loaded
    from the in-memory cache that is seeded from the database. Changes made via the
    settings API take effect on the next agent instantiation — no restart required.
    """

    agent_type: str
    system_prompt: str  # class-level default; may be overridden at init from DB

    def __init__(self, db: AsyncSession, pipeline_run_id: int) -> None:
        self.db = db
        self.pipeline_run_id = pipeline_run_id
        self.logger = logging.getLogger(f"agents.{self.agent_type.lower()}")

        settings = get_settings()
        self.max_retries = settings.llm_max_retries

        # Load per-agent config from runtime cache (populated from DB at startup)
        agent_cfg = get_agent_config(self.agent_type)
        if agent_cfg:
            self.model = agent_cfg["model"]
            self.max_tokens = agent_cfg["max_tokens"]
            # Custom prompt overrides the class-level default if set
            if agent_cfg.get("custom_prompt"):
                self.system_prompt = agent_cfg["custom_prompt"]
        else:
            # Fallback: env default (cache not yet populated or agent type unknown)
            self.logger.warning(
                f"No runtime config found for {self.agent_type}, using env defaults"
            )
            self.model = settings.llm_model
            self.max_tokens = 4096

        self.client = _build_instructor_client(settings)

    async def _call(
        self,
        response_model: type[T],
        user_content: str,
    ) -> T:
        """
        Call the LLM with structured output via Instructor.

        Uses self.model and self.max_tokens (set from runtime config at init).
        Logs every attempt (success or failure) to the database.
        Retries on transient API errors (rate limits, timeouts) up to max_retries.
        Instructor handles schema validation retries internally.
        """
        start_ms = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                result, completion = await self.client.messages.create_with_completion(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=self.system_prompt,
                    messages=[{"role": "user", "content": user_content}],
                    response_model=response_model,
                    max_retries=3,  # Instructor validation retries
                )

                latency_ms = int((time.monotonic() - start_ms) * 1000)
                tokens = (
                    completion.usage.input_tokens + completion.usage.output_tokens
                    if completion.usage else None
                )

                await self._log(
                    prompt_text=f"[{self.agent_type}]\n\n{user_content}",
                    response_text=result.model_dump_json(indent=2),
                    parsed_output=result.model_dump(),
                    tokens_used=tokens,
                    latency_ms=latency_ms,
                    retry_count=attempt,
                    success=True,
                )

                self.logger.info(
                    f"{self.agent_type} completed in {latency_ms}ms "
                    f"({tokens} tokens, attempt {attempt + 1})"
                )
                return result

            except Exception as e:
                # Separate transient vs fatal errors
                from anthropic import APITimeoutError, RateLimitError, APIError
                if isinstance(e, (RateLimitError, APITimeoutError)):
                    wait = 2 ** attempt
                    self.logger.warning(
                        f"{self.agent_type} transient error (attempt {attempt + 1}): {e}. "
                        f"Retrying in {wait}s..."
                    )
                    last_error = e
                    import asyncio
                    await asyncio.sleep(wait)
                elif isinstance(e, APIError):
                    last_error = e
                    self.logger.error(f"{self.agent_type} API error: {e}")
                    break
                else:
                    last_error = e
                    self.logger.error(f"{self.agent_type} unexpected error: {e}")
                    break

        # All attempts failed — log and re-raise
        latency_ms = int((time.monotonic() - start_ms) * 1000)
        await self._log(
            prompt_text=f"[{self.agent_type}]\n\n{user_content}",
            response_text=str(last_error),
            parsed_output=None,
            tokens_used=None,
            latency_ms=latency_ms,
            retry_count=self.max_retries,
            success=False,
        )
        raise RuntimeError(
            f"{self.agent_type} failed after {self.max_retries} attempts: {last_error}"
        ) from last_error

    async def _log(
        self,
        prompt_text: str,
        response_text: str,
        parsed_output: dict | None,
        tokens_used: int | None,
        latency_ms: int,
        retry_count: int,
        success: bool,
    ) -> None:
        """Write an AgentInteraction record to the database."""
        interaction = AgentInteraction(
            pipeline_run_id=self.pipeline_run_id,
            agent_type=self.agent_type,
            prompt_text=prompt_text,
            response_text=response_text,
            parsed_output=parsed_output,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            retry_count=retry_count,
            success=success,
        )
        self.db.add(interaction)
        await self.db.flush()
