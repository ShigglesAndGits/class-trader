from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, load_prompt
from app.agents.formatters import format_bull_bear_for_researcher
from app.schemas.agents import ResearcherVerdict, ResearcherVerdicts, TickerAnalysis
from app.schemas.market import MarketContext


class Researcher(BaseAgent):
    agent_type = "RESEARCHER"
    system_prompt = load_prompt("researcher.md")

    def __init__(self, db: AsyncSession, pipeline_run_id: int) -> None:
        super().__init__(db, pipeline_run_id)

    async def analyze(
        self,
        ctx: MarketContext,
        bull_analyses: list[TickerAnalysis],
        bear_analyses: list[TickerAnalysis],
    ) -> list[ResearcherVerdict]:
        """Synthesize bull/bear analyses and produce per-ticker verdicts."""
        self.logger.info(
            f"Synthesizing {len(bull_analyses)} bull / {len(bear_analyses)} bear analyses..."
        )

        user_content = (
            "Review the following Bull and Bear analyses and produce a synthesis verdict "
            "for each ticker:\n\n"
            + format_bull_bear_for_researcher(bull_analyses, bear_analyses)
        )

        result = await self._call(
            response_model=ResearcherVerdicts,
            user_content=user_content,
        )
        return result.verdicts
