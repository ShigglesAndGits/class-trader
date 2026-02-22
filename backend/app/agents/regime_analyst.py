from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, load_prompt
from app.agents.formatters import format_broad_market
from app.schemas.agents import RegimeAssessment
from app.schemas.market import MarketContext


class RegimeAnalyst(BaseAgent):
    agent_type = "REGIME_ANALYST"
    system_prompt = load_prompt("regime_analyst.md")

    def __init__(self, db: AsyncSession, pipeline_run_id: int) -> None:
        super().__init__(db, pipeline_run_id)

    async def analyze(self, ctx: MarketContext) -> RegimeAssessment:
        """Classify the current market regime from broad market data."""
        self.logger.info("Analyzing market regime...")
        user_content = format_broad_market(ctx)
        return await self._call(
            response_model=RegimeAssessment,
            user_content=user_content,
        )
