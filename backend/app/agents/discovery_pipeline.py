"""
Discovery pipeline orchestrator.

Runs a subset of the main pipeline against an arbitrary ticker list,
yielding SSE-compatible events as each agent completes. Used by the
/api/discovery/sessions/{id}/stream endpoint.

Unlike the main pipeline:
  - Tickers come from user input, not the watchlist
  - Bull and Bear run sequentially (SSE shows them appearing one at a time)
  - No Degen agent (penny stock discovery is handled by sleeve_hint)
  - Portfolio Manager outputs proposals, not executable trades
  - Results are stored on the DiscoverySession, not as TradeDecision rows
"""

import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.bear_agent import BearAgent
from app.agents.bull_agent import BullAgent
from app.agents.discovery_pm import DiscoveryPM
from app.agents.explorer import run_explorer
from app.agents.researcher import Researcher
from app.agents.regime_analyst import RegimeAnalyst
from app.data.aggregator import build_partial_market_context
from app.models.discovery import DiscoverySession
from app.models.pipeline import PipelineRun

logger = logging.getLogger(__name__)

_MAX_TICKERS = 8  # Cap to stay within API rate budgets


def _event(event_type: str, **data) -> dict:
    return {"event": event_type, "data": data}


async def run_discovery_pipeline(
    db: AsyncSession,
    session_id: int,
    tickers: list[str],
    user_query: str,
    user_context: Optional[str] = None,
    sleeve_hint: str = "MAIN",
) -> AsyncGenerator[dict, None]:
    """
    Async generator that runs the discovery agent pipeline and yields
    structured events for each completed step.

    Callers wrap this in an SSE EventSourceResponse.

    Event types:
      - "data_ready"      → market context fetched, tickers confirmed
      - "agent_complete"  → one agent finished; includes agent name + output
      - "pipeline_complete" → all agents done; includes final recommendations
      - "pipeline_error"  → unrecoverable error; pipeline stopped
    """
    tickers = list(dict.fromkeys(t.upper().strip() for t in tickers))[:_MAX_TICKERS]

    # ── Create PipelineRun ────────────────────────────────────────────────
    run = PipelineRun(
        run_type="DISCOVERY",
        started_at=datetime.now(timezone.utc),
        status="RUNNING",
    )
    db.add(run)
    await db.flush()

    # ── Link to DiscoverySession ──────────────────────────────────────────
    session_result = await db.get(DiscoverySession, session_id)
    if session_result:
        session_result.pipeline_run_id = run.id
        await db.flush()

    try:
        # ── Explorer (EXPLORE mode only) ──────────────────────────────────
        # If no tickers were provided, run the Explorer agent first to find
        # candidates autonomously via tool calling.
        if not tickers:
            logger.info(f"Discovery pipeline {run.id}: running Explorer for '{user_query}'")
            async for explorer_event in run_explorer(user_query):
                yield explorer_event
                if explorer_event["event"] == "explorer_complete":
                    found = [
                        t.upper().strip()
                        for t in explorer_event["data"].get("tickers", [])
                    ]
                    tickers = list(dict.fromkeys(found))[:_MAX_TICKERS]
                    if session_result:
                        session_result.tickers_analyzed = tickers
                        await db.flush()
                elif explorer_event["event"] == "pipeline_error":
                    # Explorer failed — surface the error and stop
                    if session_result:
                        session_result.status = "FAILED"
                    run.status = "FAILED"
                    run.completed_at = datetime.now(timezone.utc)
                    try:
                        await db.commit()
                    except Exception:
                        await db.rollback()
                    return

            if not tickers:
                raise RuntimeError("Explorer returned no ticker candidates.")

        # ── Fetch market data ─────────────────────────────────────────────
        logger.info(f"Discovery pipeline {run.id}: fetching data for {tickers}")
        ctx = await build_partial_market_context(db, tickers)
        confirmed_tickers = [t for t in tickers if t in ctx.ticker_data]

        yield _event("data_ready", tickers=confirmed_tickers, run_id=run.id)

        # ── Regime Analyst ────────────────────────────────────────────────
        regime_agent = RegimeAnalyst(db, run.id)
        regime = await regime_agent.analyze(ctx)

        yield _event(
            "agent_complete",
            agent="REGIME_ANALYST",
            regime=regime.model_dump(),
        )

        # ── Bull Agent ────────────────────────────────────────────────────
        bull_agent = BullAgent(db, run.id)
        bull_analyses = await bull_agent.analyze(
            ctx, regime, confirmed_tickers, extra_context=user_context
        )

        yield _event(
            "agent_complete",
            agent="BULL",
            analyses=[a.model_dump() for a in bull_analyses],
        )

        # ── Bear Agent ────────────────────────────────────────────────────
        bear_agent = BearAgent(db, run.id)
        bear_analyses = await bear_agent.analyze(
            ctx, regime, confirmed_tickers, extra_context=user_context
        )

        yield _event(
            "agent_complete",
            agent="BEAR",
            analyses=[a.model_dump() for a in bear_analyses],
        )

        # ── Researcher ────────────────────────────────────────────────────
        researcher = Researcher(db, run.id)
        researcher_verdicts = await researcher.analyze(ctx, bull_analyses, bear_analyses)

        yield _event(
            "agent_complete",
            agent="RESEARCHER",
            verdicts=[v.model_dump() for v in researcher_verdicts],
        )

        # ── Discovery PM ──────────────────────────────────────────────────
        pm = DiscoveryPM(db, run.id)
        recommendations = await pm.decide(
            ctx=ctx,
            regime=regime,
            bull_analyses=bull_analyses,
            bear_analyses=bear_analyses,
            researcher_verdicts=researcher_verdicts,
            user_query=user_query,
            user_context=user_context,
        )

        yield _event(
            "agent_complete",
            agent="DISCOVERY_PM",
            recommendations=recommendations.model_dump(),
        )

        # ── Persist results ───────────────────────────────────────────────
        if session_result:
            session_result.status = "COMPLETED"
            session_result.regime_snapshot = regime.model_dump()
            session_result.recommendations = recommendations.model_dump()

        run.status = "COMPLETED"
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Discovery pipeline {run.id} completed.")
        yield _event(
            "pipeline_complete",
            session_id=session_id,
            run_id=run.id,
            recommendations=recommendations.model_dump(),
        )

    except Exception as e:
        logger.error(f"Discovery pipeline {run.id} failed: {e}", exc_info=True)

        # Mark both records as failed
        if session_result:
            session_result.status = "FAILED"
        run.status = "FAILED"
        run.completed_at = datetime.now(timezone.utc)
        try:
            await db.commit()
        except Exception:
            await db.rollback()

        yield _event("pipeline_error", error=str(e), run_id=run.id)
