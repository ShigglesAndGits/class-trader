"""
TickerExtractor — parses a natural language query into structured ticker data.

This is a lightweight, cheap LLM call (max 512 tokens) that runs at the start
of a discovery session to figure out what the user actually wants to research.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.schemas.discovery import TickerExtractionResult

_SYSTEM_PROMPT = """You are a stock ticker extraction specialist.

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


class TickerExtractor(BaseAgent):
    agent_type = "TICKER_EXTRACTOR"
    system_prompt = _SYSTEM_PROMPT

    def __init__(self, db: AsyncSession, pipeline_run_id: int) -> None:
        super().__init__(db, pipeline_run_id)

    async def extract(self, query: str) -> TickerExtractionResult:
        """Parse a user query into tickers and themes."""
        self.logger.info(f"Extracting tickers from query: {query!r}")
        result = await self._call(
            response_model=TickerExtractionResult,
            user_content=f"User query: {query}",
        )
        # Normalize tickers
        result.tickers = [t.upper().strip() for t in result.tickers if t.strip()]
        self.logger.info(
            f"Extracted: tickers={result.tickers}, themes={result.themes}, "
            f"scan_news={result.scan_news}"
        )
        return result
