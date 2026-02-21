from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, load_prompt
from app.agents.formatters import format_penny_context
from app.schemas.agents import DegenDecision, DegenDecisions, RegimeAssessment
from app.schemas.market import MarketContext


class DegenAgent(BaseAgent):
    agent_type = "DEGEN"
    system_prompt = load_prompt("degen.md")

    def __init__(self, db: AsyncSession, pipeline_run_id: int) -> None:
        super().__init__(db, pipeline_run_id)

    async def decide(
        self,
        ctx: MarketContext,
        regime: RegimeAssessment,
        penny_tickers: list[str],
    ) -> list[DegenDecision]:
        """
        Produce high-risk trade decisions for the penny sleeve.

        Runs independently of the main pipeline — separate risk parameters,
        separate sleeve, separate logic. Knows it's playing with house money.
        """
        if not penny_tickers:
            self.logger.info("No penny tickers configured — Degen sitting out.")
            return []

        self.logger.info(f"Degen analyzing {len(penny_tickers)} penny tickers...")

        regime_note = (
            f"Regime Context: {regime.regime} (confidence={regime.confidence:.2f})\n"
            f"Note: Penny sleeve operates independently, but extreme regimes "
            f"(HIGH_VOLATILITY) should reduce position sizes.\n\n"
        )
        penny_data = format_penny_context(ctx, penny_tickers)
        user_content = regime_note + penny_data

        result = await self._call(
            response_model=DegenDecisions,
            user_content=user_content,
            max_tokens=2048,
        )
        return result.decisions
