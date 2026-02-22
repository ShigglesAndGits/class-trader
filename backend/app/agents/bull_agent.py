from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, load_prompt
from app.agents.formatters import format_tickers_for_analysis
from app.schemas.agents import RegimeAssessment, TickerAnalyses, TickerAnalysis
from app.schemas.market import MarketContext


class BullAgent(BaseAgent):
    agent_type = "BULL"
    system_prompt = load_prompt("bull_agent.md")

    def __init__(self, db: AsyncSession, pipeline_run_id: int) -> None:
        super().__init__(db, pipeline_run_id)

    async def analyze(
        self,
        ctx: MarketContext,
        regime: RegimeAssessment,
        tickers: list[str],
        extra_context: str | None = None,
    ) -> list[TickerAnalysis]:
        """Build the bull case for each ticker in the main sleeve."""
        self.logger.info(f"Building bull case for {len(tickers)} tickers...")

        regime_context = (
            f"Current Regime: {regime.regime} (confidence={regime.confidence:.2f})\n"
            f"Regime Summary: {regime.reasoning}\n\n"
        )
        ticker_data = format_tickers_for_analysis(ctx, tickers)
        user_content = (
            f"{regime_context}"
            f"Analyze the following {len(tickers)} tickers and build the bull case for each:\n\n"
            f"{ticker_data}"
        )

        if extra_context:
            user_content += (
                f"\n\n## User Counter-Argument\n"
                f"The user has raised the following counter-point. "
                f"Address it directly in your bull analysis:\n{extra_context}"
            )

        result = await self._call(
            response_model=TickerAnalyses,
            user_content=user_content,
            max_tokens=4096,
        )
        return result.analyses
