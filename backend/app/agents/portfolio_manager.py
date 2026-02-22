from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, load_prompt
from app.agents.formatters import format_portfolio_manager_context
from app.schemas.agents import (
    PortfolioDecision,
    RegimeAssessment,
    ResearcherVerdict,
    TickerAnalysis,
)
from app.schemas.market import MarketContext


class PortfolioManager(BaseAgent):
    agent_type = "PORTFOLIO_MANAGER"
    system_prompt = load_prompt("portfolio_manager.md")

    def __init__(self, db: AsyncSession, pipeline_run_id: int) -> None:
        super().__init__(db, pipeline_run_id)

    async def decide(
        self,
        ctx: MarketContext,
        regime: RegimeAssessment,
        bull_analyses: list[TickerAnalysis],
        bear_analyses: list[TickerAnalysis],
        researcher_verdicts: list[ResearcherVerdict],
    ) -> PortfolioDecision:
        """
        Produce final BUY/SELL/HOLD decisions for the main sleeve.

        Receives the full picture: regime, both sides of the debate,
        researcher synthesis, and live portfolio state.
        """
        self.logger.info(
            f"Making portfolio decisions for {len(researcher_verdicts)} tickers..."
        )

        user_content = format_portfolio_manager_context(
            ctx=ctx,
            regime=regime,
            bull_analyses=bull_analyses,
            bear_analyses=bear_analyses,
            researcher_verdicts=researcher_verdicts,
        )

        return await self._call(
            response_model=PortfolioDecision,
            user_content=user_content,
        )
