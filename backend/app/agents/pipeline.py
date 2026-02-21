"""
Pipeline orchestrator — runs the full multi-agent analysis sequence.

Flow:
  1. Build MarketContext (aggregator)
  2. Regime Analyst  → RegimeAssessment
  3. Bull + Bear     → list[TickerAnalysis] each  (parallel)
  4. Researcher      → list[ResearcherVerdict]
  5. Portfolio Mgr   → PortfolioDecision
  6. Degen           → list[DegenDecision]       (separate, independent)
  7. Write TradeDecision records to DB
  8. Mark PipelineRun as COMPLETED

All agent interactions are logged to the database. The pipeline run record
tracks overall status and is updated at the end.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.bear_agent import BearAgent
from app.agents.bull_agent import BullAgent
from app.agents.degen import DegenAgent
from app.agents.portfolio_manager import PortfolioManager
from app.agents.researcher import Researcher
from app.agents.regime_analyst import RegimeAnalyst
from app.data.aggregator import build_market_context
from app.database import AsyncSessionLocal
from app.models.pipeline import PipelineRun
from app.models.trading import TradeDecision as TradeDecisionORM
from app.models.watchlist import Watchlist
from app.schemas.agents import (
    DegenDecision,
    PortfolioDecision,
    RegimeAssessment,
    ResearcherVerdict,
    TickerAnalysis,
)
from app.schemas.market import MarketContext

logger = logging.getLogger(__name__)


class PipelineResult:
    """Structured result from a completed pipeline run."""

    def __init__(
        self,
        run_id: int,
        regime: RegimeAssessment,
        portfolio_decision: PortfolioDecision,
        degen_decisions: list[DegenDecision],
        bull_analyses: list[TickerAnalysis],
        bear_analyses: list[TickerAnalysis],
        researcher_verdicts: list[ResearcherVerdict],
        market_context: MarketContext,
    ) -> None:
        self.run_id = run_id
        self.regime = regime
        self.portfolio_decision = portfolio_decision
        self.degen_decisions = degen_decisions
        self.bull_analyses = bull_analyses
        self.bear_analyses = bear_analyses
        self.researcher_verdicts = researcher_verdicts
        self.market_context = market_context


async def run_pipeline(db: AsyncSession, run_type: str = "MANUAL") -> PipelineResult:
    """
    Execute the full agent pipeline.

    Creates a PipelineRun DB record, runs all agents in order,
    writes trade decisions to DB, and marks the run complete.

    This is the primary entry point called by the router and scheduler.
    """
    # ── Create PipelineRun record ──────────────────────────────────────────
    pipeline_run = PipelineRun(
        run_type=run_type,
        started_at=datetime.now(timezone.utc),
        status="RUNNING",
    )
    db.add(pipeline_run)
    await db.flush()
    run_id = pipeline_run.id
    logger.info(f"Pipeline run #{run_id} started (type={run_type})")

    try:
        result = await _execute_pipeline(db, run_id, run_type)

        # ── Mark run as completed ──────────────────────────────────────────
        pipeline_run.status = "COMPLETED"
        pipeline_run.completed_at = datetime.now(timezone.utc)
        pipeline_run.regime = result.regime.regime
        pipeline_run.regime_confidence = result.regime.confidence
        await db.commit()

        logger.info(
            f"Pipeline run #{run_id} completed. "
            f"Regime: {result.regime.regime} ({result.regime.confidence:.0%}). "
            f"Trades proposed: {len(result.portfolio_decision.trades)} main + "
            f"{len(result.degen_decisions)} degen."
        )
        return result

    except Exception as e:
        logger.error(f"Pipeline run #{run_id} failed: {e}", exc_info=True)
        pipeline_run.status = "FAILED"
        pipeline_run.completed_at = datetime.now(timezone.utc)
        pipeline_run.error_message = str(e)[:500]
        await db.commit()
        raise


async def _execute_pipeline(
    db: AsyncSession,
    run_id: int,
    run_type: str,
) -> PipelineResult:
    """Inner pipeline logic — separated from the run record management above."""

    # ── Step 1: Build MarketContext ────────────────────────────────────────
    logger.info(f"[{run_id}] Fetching market data...")
    ctx = await build_market_context(db)

    # Determine which tickers to analyze for each sleeve
    watchlist_rows = (await db.execute(
        select(Watchlist).where(Watchlist.is_active == True)  # noqa: E712
    )).scalars().all()

    main_tickers = [
        w.ticker for w in watchlist_rows
        if w.sleeve in ("MAIN", "BENCHMARK") and w.ticker in ctx.ticker_data
    ]
    penny_tickers = [
        w.ticker for w in watchlist_rows
        if w.sleeve == "PENNY" and w.ticker in ctx.ticker_data
    ]

    # Remove SPY/QQQ from main analysis (they're benchmarks, not trade candidates)
    _BENCHMARKS = {"SPY", "QQQ", "IWM", "DIA"}
    analysis_tickers = [t for t in main_tickers if t not in _BENCHMARKS]

    logger.info(
        f"[{run_id}] Analysis targets: {len(analysis_tickers)} main tickers, "
        f"{len(penny_tickers)} penny tickers"
    )

    # ── Step 2: Regime Analyst ─────────────────────────────────────────────
    logger.info(f"[{run_id}] Running Regime Analyst...")
    regime_agent = RegimeAnalyst(db, run_id)
    regime = await regime_agent.analyze(ctx)
    logger.info(f"[{run_id}] Regime: {regime.regime} ({regime.confidence:.0%})")

    # ── Steps 3a + 3b: Bull + Bear (parallel) ─────────────────────────────
    logger.info(f"[{run_id}] Running Bull and Bear agents in parallel...")
    bull_agent = BullAgent(db, run_id)
    bear_agent = BearAgent(db, run_id)

    bull_task = bull_agent.analyze(ctx, regime, analysis_tickers)
    bear_task = bear_agent.analyze(ctx, regime, analysis_tickers)

    bull_analyses, bear_analyses = await asyncio.gather(bull_task, bear_task)
    logger.info(
        f"[{run_id}] Bull: {len(bull_analyses)} analyses, "
        f"Bear: {len(bear_analyses)} analyses"
    )

    # ── Step 4: Researcher ─────────────────────────────────────────────────
    logger.info(f"[{run_id}] Running Researcher...")
    researcher = Researcher(db, run_id)
    researcher_verdicts = await researcher.analyze(ctx, bull_analyses, bear_analyses)
    logger.info(f"[{run_id}] Researcher: {len(researcher_verdicts)} verdicts")

    # ── Step 5: Portfolio Manager ──────────────────────────────────────────
    logger.info(f"[{run_id}] Running Portfolio Manager...")
    pm = PortfolioManager(db, run_id)
    portfolio_decision = await pm.decide(
        ctx=ctx,
        regime=regime,
        bull_analyses=bull_analyses,
        bear_analyses=bear_analyses,
        researcher_verdicts=researcher_verdicts,
    )
    logger.info(
        f"[{run_id}] PM decision: {len(portfolio_decision.trades)} trades, "
        f"cash reserve={portfolio_decision.cash_reserve_pct:.0f}%"
    )

    # ── Step 6: Degen (independent penny sleeve) ───────────────────────────
    logger.info(f"[{run_id}] Running Degen agent...")
    degen = DegenAgent(db, run_id)
    degen_decisions = await degen.decide(ctx, regime, penny_tickers)
    logger.info(f"[{run_id}] Degen: {len(degen_decisions)} decisions")

    # ── Step 7: Write trade decisions to DB ────────────────────────────────
    await _persist_trade_decisions(db, run_id, portfolio_decision, degen_decisions)

    return PipelineResult(
        run_id=run_id,
        regime=regime,
        portfolio_decision=portfolio_decision,
        degen_decisions=degen_decisions,
        bull_analyses=bull_analyses,
        bear_analyses=bear_analyses,
        researcher_verdicts=researcher_verdicts,
        market_context=ctx,
    )


async def _persist_trade_decisions(
    db: AsyncSession,
    run_id: int,
    portfolio_decision: PortfolioDecision,
    degen_decisions: list[DegenDecision],
) -> None:
    """
    Write all actionable trade decisions to the database as PENDING,
    then hand them off to the approval queue.

    HOLDs are skipped — they're informational and don't require approval or execution.
    Auto-approve logic lives in approval_queue.process_new_decisions, not here.
    """
    from app.config import get_settings
    settings = get_settings()
    new_trade_ids: list[int] = []

    # Main sleeve trades from Portfolio Manager
    for trade in portfolio_decision.trades:
        if trade.action == "HOLD":
            continue

        orm_trade = TradeDecisionORM(
            pipeline_run_id=run_id,
            ticker=trade.ticker,
            sleeve="MAIN",
            action=trade.action,
            confidence=trade.confidence,
            position_size_pct=trade.position_size_pct,
            reasoning=trade.reasoning,
            stop_loss_pct=trade.stop_loss_pct,
            take_profit_pct=trade.take_profit_pct,
            status="PENDING",
        )
        db.add(orm_trade)

    # Penny sleeve trades from Degen
    for decision in degen_decisions:
        if decision.action == "HOLD":
            continue

        penny_equity = settings.penny_sleeve_allocation
        pct = (decision.position_dollars / penny_equity * 100) if penny_equity > 0 else 0.0

        orm_trade = TradeDecisionORM(
            pipeline_run_id=run_id,
            ticker=decision.ticker,
            sleeve="PENNY",
            action=decision.action,
            confidence=decision.confidence,
            position_size_pct=pct,
            reasoning=(
                f"{decision.reasoning} | Catalyst: {decision.catalyst} | "
                f"Exit: {decision.exit_trigger}"
            ),
            status="PENDING",
        )
        db.add(orm_trade)

    await db.flush()

    # Collect the IDs of all newly-written PENDING decisions for this run
    from sqlalchemy import select as sa_select
    result = await db.execute(
        sa_select(TradeDecisionORM.id).where(
            TradeDecisionORM.pipeline_run_id == run_id,
            TradeDecisionORM.status == "PENDING",
        )
    )
    new_trade_ids = list(result.scalars().all())

    logger.info(
        f"[{run_id}] {len(new_trade_ids)} trade decision(s) persisted as PENDING. "
        "Handing off to approval queue."
    )

    # Delegate auto-approve / notify logic to the approval queue
    from app.execution.approval_queue import process_new_decisions
    await process_new_decisions(db, new_trade_ids)


async def run_pipeline_background(run_type: str = "MANUAL") -> None:
    """
    Entry point for background task execution.
    Creates its own DB session (not tied to a request lifecycle).
    """
    async with AsyncSessionLocal() as session:
        try:
            await run_pipeline(session, run_type)
        except Exception as e:
            logger.error(f"Background pipeline run failed: {e}", exc_info=True)
