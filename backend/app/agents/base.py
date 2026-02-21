"""
BaseAgent — foundation for all LLM agents in the pipeline.

Handles:
  - Async Anthropic client via Instructor (structured output enforcement)
  - Retry logic with exponential backoff on API failures
  - Full interaction logging to the database (prompt, response, tokens, latency)
  - Consistent error handling and propagation
"""

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypeVar

import instructor
from anthropic import AsyncAnthropic, APIError, APITimeoutError, RateLimitError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.pipeline import AgentInteraction

T = TypeVar("T")

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename: str) -> str:
    """Load a system prompt from the prompts/ directory."""
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


class BaseAgent(ABC):
    """
    Abstract base for all pipeline agents.

    Subclasses must define:
      - agent_type: str  — matches AgentInteraction.agent_type in DB
      - system_prompt: str  — the static system persona (loaded from prompts/)
    """

    agent_type: str
    system_prompt: str

    def __init__(self, db: AsyncSession, pipeline_run_id: int) -> None:
        self.db = db
        self.pipeline_run_id = pipeline_run_id

        settings = get_settings()
        raw_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.client = instructor.from_anthropic(raw_client)
        self.model = settings.llm_model
        self.max_retries = settings.llm_max_retries
        self.logger = logging.getLogger(f"agents.{self.agent_type.lower()}")

    async def _call(
        self,
        response_model: type[T],
        user_content: str,
        max_tokens: int = 4096,
    ) -> T:
        """
        Call the LLM with structured output via Instructor.

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
                    max_tokens=max_tokens,
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

            except (RateLimitError, APITimeoutError) as e:
                # Transient — retry with backoff
                wait = 2 ** attempt
                self.logger.warning(
                    f"{self.agent_type} transient error (attempt {attempt + 1}): {e}. "
                    f"Retrying in {wait}s..."
                )
                last_error = e
                import asyncio
                await asyncio.sleep(wait)

            except APIError as e:
                # Non-transient API error — fail fast
                last_error = e
                self.logger.error(f"{self.agent_type} API error: {e}")
                break

            except Exception as e:
                # Validation failure or unexpected error
                last_error = e
                self.logger.error(f"{self.agent_type} unexpected error: {e}")
                break

        # All attempts failed — log the failure and re-raise
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
