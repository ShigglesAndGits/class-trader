"""
Discovery Portfolio Manager — proposes positions without executing them.

Unlike the main PortfolioManager, the DiscoveryPM:
  - Does NOT receive portfolio state (positions, cash, wash sales)
  - Uses BUY / CONSIDER / AVOID instead of BUY / SELL / HOLD
  - Returns DiscoveryRecommendations rather than PortfolioDecision
  - Accepts an optional user_context for re-debate sessions
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent, load_prompt
from app.schemas.agents import RegimeAssessment, ResearcherVerdict, TickerAnalysis
from app.schemas.discovery import DiscoveryRecommendations
from app.schemas.market import MarketContext


def _format_ticker_debate(
    ticker: str,
    bull_analyses: list[TickerAnalysis],
    bear_analyses: list[TickerAnalysis],
    researcher_verdicts: list[ResearcherVerdict],
) -> str:
    """Format Bull + Bear + Researcher output for one ticker."""
    bull = next((a for a in bull_analyses if a.ticker == ticker), None)
    bear = next((a for a in bear_analyses if a.ticker == ticker), None)
    verdict = next((v for v in researcher_verdicts if v.ticker == ticker), None)

    parts = [f"### {ticker}"]

    if bull:
        parts.append(
            f"**Bull**: {bull.stance} (conf={bull.confidence:.2f})\n"
            f"{bull.reasoning}\n"
            f"Key points: {', '.join(bull.key_data_points[:3])}"
        )
    else:
        parts.append("**Bull**: No analysis available")

    if bear:
        parts.append(
            f"**Bear**: {bear.stance} (conf={bear.confidence:.2f})\n"
            f"{bear.reasoning}\n"
            f"Key points: {', '.join(bear.key_data_points[:3])}"
        )
    else:
        parts.append("**Bear**: No analysis available")

    if verdict:
        drift_flag = " ⚠️ THESIS DRIFT WARNING" if verdict.thesis_drift_warning else ""
        parts.append(
            f"**Researcher**: {verdict.bull_bear_agreement}{drift_flag}\n"
            f"{verdict.reasoning}"
        )
        if verdict.flagged_issues:
            parts.append(f"Issues: {'; '.join(verdict.flagged_issues)}")

    return "\n".join(parts)


class DiscoveryPM(BaseAgent):
    agent_type = "DISCOVERY_PM"
    system_prompt = load_prompt("discovery_pm.md")

    def __init__(self, db: AsyncSession, pipeline_run_id: int) -> None:
        super().__init__(db, pipeline_run_id)

    async def decide(
        self,
        ctx: MarketContext,
        regime: RegimeAssessment,
        bull_analyses: list[TickerAnalysis],
        bear_analyses: list[TickerAnalysis],
        researcher_verdicts: list[ResearcherVerdict],
        user_query: str,
        user_context: str | None = None,
    ) -> DiscoveryRecommendations:
        """Synthesize the debate and produce discovery recommendations."""
        tickers = list({a.ticker for a in bull_analyses + bear_analyses})
        self.logger.info(f"DiscoveryPM synthesizing debate for: {tickers}")

        regime_section = (
            f"## Market Regime\n"
            f"Regime: {regime.regime} | Confidence: {regime.confidence:.2f}\n"
            f"{regime.reasoning}\n"
            f"Key indicators: {', '.join(regime.key_indicators[:5])}"
        )

        debate_sections = "\n\n".join(
            _format_ticker_debate(t, bull_analyses, bear_analyses, researcher_verdicts)
            for t in tickers
        )

        user_content = (
            f"{regime_section}\n\n"
            f"## Agent Debate\n{debate_sections}\n\n"
            f"## User's Research Intent\n{user_query}"
        )

        if user_context:
            user_content += (
                f"\n\n## User Counter-Argument (Re-debate)\n"
                f"The user disagrees with aspects of the above analysis and argues:\n"
                f"{user_context}\n"
                f"Factor this counter-argument into your recommendations."
            )

        return await self._call(
            response_model=DiscoveryRecommendations,
            user_content=user_content,
            max_tokens=4096,
        )
