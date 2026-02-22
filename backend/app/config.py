"""
Application configuration loaded from environment variables via pydantic-settings.
All settings are validated at startup — bad keys fail fast and loudly.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Anthropic ──────────────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # ── Alpaca ─────────────────────────────────────────────────────────────
    alpaca_api_key: str = Field(default="", alias="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(default="", alias="ALPACA_SECRET_KEY")
    alpaca_paper: bool = Field(default=True, alias="ALPACA_PAPER")

    # ── Market data APIs ───────────────────────────────────────────────────
    finnhub_api_key: str = Field(default="", alias="FINNHUB_API_KEY")
    alpha_vantage_api_key: str = Field(default="", alias="ALPHA_VANTAGE_API_KEY")
    fmp_api_key: str = Field(default="", alias="FMP_API_KEY")

    # ── Reddit (TendieBot) ─────────────────────────────────────────────────
    reddit_client_id: str = Field(default="", alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str = Field(default="", alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(
        default="class-trader:v0.1", alias="REDDIT_USER_AGENT"
    )

    # ── Database ───────────────────────────────────────────────────────────
    postgres_user: str = Field(default="classtrader", alias="POSTGRES_USER")
    postgres_password: str = Field(default="", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="class_trader", alias="POSTGRES_DB")
    database_url: str = Field(
        default="postgresql+asyncpg://classtrader:password@db:5432/class_trader",
        alias="DATABASE_URL",
    )

    # ── Notifications ──────────────────────────────────────────────────────
    apprise_urls: str = Field(default="", alias="APPRISE_URLS")

    # ── Trading config ─────────────────────────────────────────────────────
    auto_approve: bool = Field(default=False, alias="AUTO_APPROVE")
    main_sleeve_allocation: float = Field(default=75.0, alias="MAIN_SLEEVE_ALLOCATION")
    penny_sleeve_allocation: float = Field(default=25.0, alias="PENNY_SLEEVE_ALLOCATION")
    max_position_pct_main: float = Field(default=30.0, alias="MAX_POSITION_PCT_MAIN")
    max_position_dollars_penny: float = Field(default=8.0, alias="MAX_POSITION_DOLLARS_PENNY")
    min_confidence_main: float = Field(default=0.65, alias="MIN_CONFIDENCE_MAIN")
    min_confidence_penny: float = Field(default=0.60, alias="MIN_CONFIDENCE_PENNY")
    daily_loss_limit_main_pct: float = Field(default=5.0, alias="DAILY_LOSS_LIMIT_MAIN_PCT")
    daily_loss_limit_penny_pct: float = Field(default=15.0, alias="DAILY_LOSS_LIMIT_PENNY_PCT")
    consecutive_loss_pause: int = Field(default=3, alias="CONSECUTIVE_LOSS_PAUSE")

    # ── App config ─────────────────────────────────────────────────────────
    timezone: str = Field(default="America/New_York", alias="TIMEZONE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    frontend_port: int = Field(default=3000, alias="FRONTEND_PORT")

    # ── LLM config ─────────────────────────────────────────────────────────
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_max_retries: int = 3
    # OpenAI-compatible provider (Ollama, OpenRouter, LM Studio, etc.)
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}")
        return upper

    @property
    def apprise_url_list(self) -> list[str]:
        """Parse comma-separated APPRISE_URLS into a list."""
        if not self.apprise_urls:
            return []
        return [u.strip() for u in self.apprise_urls.split(",") if u.strip()]

    def configured_apis(self) -> dict[str, bool]:
        """Return which APIs have keys configured (for health checks)."""
        return {
            "anthropic": bool(self.anthropic_api_key and not self.anthropic_api_key.startswith("sk-ant-your")),
            "alpaca": bool(self.alpaca_api_key and not self.alpaca_api_key.startswith("your-")),
            "finnhub": bool(self.finnhub_api_key and not self.finnhub_api_key.startswith("your-")),
            "alpha_vantage": bool(self.alpha_vantage_api_key and not self.alpha_vantage_api_key.startswith("your-")),
            "fmp": bool(self.fmp_api_key and not self.fmp_api_key.startswith("your-")),
            "reddit": bool(self.reddit_client_id and not self.reddit_client_id.startswith("your-")),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
