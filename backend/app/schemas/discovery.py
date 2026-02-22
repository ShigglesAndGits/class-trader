"""
Pydantic schemas for the Stock Discovery feature.

Discovery sessions use a separate action vocabulary from the main trading
pipeline:  BUY | CONSIDER | AVOID  instead of  BUY | SELL | HOLD.
Discovery PM proposes; it does not execute or manage existing positions.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.agents import RegimeAssessment


class DiscoveryRecommendation(BaseModel):
    """A single ticker proposal from the Discovery Portfolio Manager."""

    action: Literal["BUY", "CONSIDER", "AVOID"]
    ticker: str
    confidence: float = Field(ge=0.0, le=1.0)
    position_size_pct: float = Field(ge=0.0, le=30.0)
    reasoning: str
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    suggested_sleeve: Literal["MAIN", "PENNY"] = "MAIN"


class DiscoveryRecommendations(BaseModel):
    """
    Instructor-enforced output from the DiscoveryPM agent.
    Wraps a list of per-ticker proposals with a synthesis thesis.
    """

    recommendations: list[DiscoveryRecommendation]
    overall_thesis: str
    caveats: list[str]


class TickerExtractionResult(BaseModel):
    """
    LLM output from the TickerExtractor agent.
    Parses a natural language query into actionable ticker data.
    """

    tickers: list[str] = Field(
        description="Explicit stock tickers found or inferred from the query (uppercase, no $)"
    )
    themes: list[str] = Field(
        description="Thematic keywords if no explicit tickers (e.g. 'energy momentum', 'AI chips')"
    )
    scan_news: bool = Field(
        description="True if the query is theme-based and news scanning is needed to find candidates"
    )


class ChatMessage(BaseModel):
    """A single message in a discovery session conversation."""

    role: Literal["user", "assistant"]
    content: str
    ts: datetime


class DiscoverySessionState(BaseModel):
    """Full session state returned by the API after completion or during chat."""

    session_id: int
    pipeline_run_id: Optional[int]
    query: str
    query_mode: str
    tickers_analyzed: list[str]
    status: str
    regime_snapshot: Optional[RegimeAssessment]
    recommendations: Optional[DiscoveryRecommendations]
    conversation: list[ChatMessage]
    created_at: datetime


# ── Request/response schemas for the router ──────────────────────────────────

class StartDiscoveryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    query_mode: Literal["EXPLICIT", "NEWS_SCAN", "EXPLORE"] = "EXPLICIT"
    sleeve_hint: Literal["MAIN", "PENNY"] = "MAIN"


class StartDiscoveryResponse(BaseModel):
    session_id: int
    tickers: list[str]
    status: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    rebate: bool = False


class ChatResponse(BaseModel):
    reply: str
    rebate_session_id: Optional[int] = None


class PushToApprovalsRequest(BaseModel):
    recommendation_indices: list[int]
    sleeve: Literal["MAIN", "PENNY"] = "MAIN"


class PushToApprovalsResponse(BaseModel):
    queued: int
    trade_ids: list[int]


class PushToWatchlistRequest(BaseModel):
    tickers: list[str]
    sleeve: Literal["MAIN", "PENNY"] = "MAIN"
    notes: Optional[str] = None


class PushToWatchlistResponse(BaseModel):
    added: int
    already_existed: int
