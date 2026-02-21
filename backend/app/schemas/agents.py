"""
Pydantic schemas for all LLM agent inputs and outputs.
Every agent produces structured output via Instructor-enforced schemas.
These are the schemas — enforcement happens in BaseAgent (Phase 2).
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class RegimeAssessment(BaseModel):
    regime: Literal["TRENDING_UP", "TRENDING_DOWN", "RANGING", "HIGH_VOLATILITY"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    key_indicators: list[str]


class RetailSentiment(BaseModel):
    """TendieBot output — retail/WSB sentiment data per ticker."""
    ticker: str
    mention_count_24h: int
    mention_velocity: float  # % change vs 7-day average (1.0 = normal, 3.0 = 3x spike)
    avg_sentiment: float     # -1.0 (bearish) to 1.0 (bullish)
    hype_score: float        # Composite: 0.0 (no buzz) to 1.0 (maximum hype)
    top_posts: list[str]
    subreddits: list[str]
    caution_flags: list[str]


class TickerAnalysis(BaseModel):
    ticker: str
    stance: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    key_data_points: list[str]


class ResearcherVerdict(BaseModel):
    ticker: str
    bull_bear_agreement: Literal["AGREE_BULLISH", "AGREE_BEARISH", "DISAGREE", "INSUFFICIENT_DATA"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    flagged_issues: list[str]
    thesis_drift_warning: bool


class TradeDecision(BaseModel):
    action: Literal["BUY", "SELL", "HOLD"]
    ticker: str
    confidence: float = Field(ge=0.0, le=1.0)
    position_size_pct: float = Field(ge=0.0, le=30.0)  # max 30% per position
    reasoning: str
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None


class PortfolioDecision(BaseModel):
    regime: RegimeAssessment
    trades: list[TradeDecision]
    cash_reserve_pct: float = Field(ge=0.0, le=100.0)
    overall_reasoning: str


class DegenDecision(BaseModel):
    """High-risk penny stock decision from the Degen agent."""
    action: Literal["BUY", "SELL", "HOLD"]
    ticker: str
    confidence: float = Field(ge=0.0, le=1.0)
    position_dollars: float = Field(ge=0.0, le=8.0)  # Hard cap $8
    reasoning: str
    catalyst: str  # What's the momentum driver?
    exit_trigger: str  # What would make the Degen cut and run?


# ── Instructor list-response wrappers ────────────────────────────────────────
# Instructor requires a top-level BaseModel to extract structured output.
# These wrappers let agents return lists of analyses in one LLM call.

class TickerAnalyses(BaseModel):
    """Wrapper for Bull/Bear agent output — one TickerAnalysis per ticker."""
    analyses: list[TickerAnalysis]


class ResearcherVerdicts(BaseModel):
    """Wrapper for Researcher output — one ResearcherVerdict per ticker."""
    verdicts: list[ResearcherVerdict]


class DegenDecisions(BaseModel):
    """Wrapper for Degen agent output — one DegenDecision per penny ticker."""
    decisions: list[DegenDecision]
