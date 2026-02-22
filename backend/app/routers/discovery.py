"""
Discovery API — stock research chat powered by the agent pipeline.

Endpoints:
  POST /api/discovery/sessions              Start a new discovery session
  GET  /api/discovery/sessions/{id}/stream  SSE stream of agent events
  POST /api/discovery/sessions/{id}/chat    Follow-up question or re-debate
  POST /api/discovery/sessions/{id}/push-to-approvals  Queue trades
  POST /api/discovery/sessions/{id}/push-to-watchlist  Add tickers
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import instructor
from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.discovery_pipeline import run_discovery_pipeline
from app.agents.ticker_extractor import TickerExtractor
from app.config import get_settings
from app.data.news_scanner import scan_news_for_candidates
from app.database import get_db
from app.execution.approval_queue import process_new_decisions
from app.models.discovery import DiscoverySession
from app.models.pipeline import PipelineRun
from app.models.trading import TradeDecision as TradeDecisionORM
from app.models.watchlist import Watchlist
from app.schemas.discovery import (
    ChatRequest,
    ChatResponse,
    PushToApprovalsRequest,
    PushToApprovalsResponse,
    PushToWatchlistRequest,
    PushToWatchlistResponse,
    StartDiscoveryRequest,
    StartDiscoveryResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_TICKERS = 8

# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_session_or_404(db: AsyncSession, session_id: int) -> DiscoverySession:
    session = await db.get(DiscoverySession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Discovery session #{session_id} not found.")
    return session


def _session_state(session: DiscoverySession) -> dict:
    return {
        "session_id": session.id,
        "pipeline_run_id": session.pipeline_run_id,
        "query": session.query,
        "query_mode": session.query_mode,
        "tickers_analyzed": session.tickers_analyzed,
        "status": session.status,
        "regime_snapshot": session.regime_snapshot,
        "recommendations": session.recommendations,
        "conversation": session.conversation,
        "created_at": session.created_at.isoformat(),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=StartDiscoveryResponse)
async def start_session(
    body: StartDiscoveryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Start a discovery session.

    EXPLORE mode: skips extraction entirely — the SSE pipeline will run the
    Explorer agent (Sonnet + tool calling) to autonomously find candidates.

    EXPLICIT / NEWS_SCAN: extracts tickers via TickerExtractor, optionally
    augments with Finnhub news scan, then returns resolved tickers immediately.

    The actual agent pipeline runs when the frontend opens the SSE stream.
    """
    session = DiscoverySession(
        query=body.query,
        query_mode=body.query_mode,
        tickers_analyzed=[],
        status="RUNNING",
    )
    db.add(session)
    await db.flush()

    # ── EXPLORE: hand off to the SSE pipeline, no extraction here ────────────
    if body.query_mode == "EXPLORE":
        await db.commit()
        logger.info(f"Discovery session #{session.id} started in EXPLORE mode.")
        return StartDiscoveryResponse(
            session_id=session.id,
            tickers=[],
            status="READY",
        )

    # ── EXPLICIT / NEWS_SCAN: run TickerExtractor now ─────────────────────────
    extractor_run = PipelineRun(
        run_type="DISCOVERY",
        started_at=datetime.now(timezone.utc),
        status="COMPLETED",
    )
    db.add(extractor_run)
    await db.flush()

    extractor = TickerExtractor(db, extractor_run.id)
    extraction = await extractor.extract(body.query)
    await db.flush()

    tickers = list(dict.fromkeys(extraction.tickers))[:_MAX_TICKERS]

    if body.query_mode == "NEWS_SCAN" or (extraction.scan_news and extraction.themes):
        news_candidates = await scan_news_for_candidates(extraction.themes, max_candidates=5)
        for t in news_candidates:
            if t not in tickers and len(tickers) < _MAX_TICKERS:
                tickers.append(t)

    if not tickers:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not identify any stock tickers from your query. "
                "Try naming specific tickers (e.g. 'NVDA, TSLA'), "
                "use News Scan mode with a theme (e.g. 'energy momentum plays'), "
                "or switch to Explore mode to let the AI find candidates itself."
            ),
        )

    session.tickers_analyzed = tickers
    await db.commit()

    logger.info(f"Discovery session #{session.id} started — tickers: {tickers}")
    return StartDiscoveryResponse(
        session_id=session.id,
        tickers=tickers,
        status="READY",
    )


@router.get("/sessions/{session_id}/stream")
async def stream_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    SSE stream for a discovery session.

    Opens immediately after session creation. The pipeline runs inside the
    generator, yielding one JSON event per agent completion. The stream
    closes naturally after pipeline_complete or pipeline_error.
    """
    session = await _get_session_or_404(db, session_id)

    if session.status == "COMPLETED":
        # Already ran — return a single event with cached results
        async def _cached():
            yield {
                "data": json.dumps({
                    "event": "pipeline_complete",
                    "session_id": session_id,
                    "cached": True,
                    "recommendations": session.recommendations,
                })
            }

        return EventSourceResponse(_cached())

    async def _generate():
        async for event in run_discovery_pipeline(
            db=db,
            session_id=session_id,
            tickers=session.tickers_analyzed,
            user_query=session.query,
            sleeve_hint="MAIN",
        ):
            yield {"data": json.dumps(event)}

    return EventSourceResponse(_generate())


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return the current state of a discovery session."""
    session = await _get_session_or_404(db, session_id)
    return _session_state(session)


@router.post("/sessions/{session_id}/chat", response_model=ChatResponse)
async def chat(
    session_id: int,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a follow-up message to an active discovery session.

    If rebate=False: answers conversationally using the session context.
    If rebate=True: creates a child session with the user's argument
      injected into Bull and Bear prompts, returns the new session_id
      for a fresh SSE stream.
    """
    session = await _get_session_or_404(db, session_id)

    # Append user message to conversation
    user_msg = {
        "role": "user",
        "content": body.message,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    conversation = list(session.conversation or []) + [user_msg]

    if body.rebate:
        # Create a child session for the re-debate with the user's counter-argument
        child = DiscoverySession(
            query=session.query,
            query_mode=session.query_mode,
            tickers_analyzed=session.tickers_analyzed,
            status="RUNNING",
            conversation=conversation,
        )
        db.add(child)
        await db.flush()

        session.conversation = conversation
        await db.commit()

        logger.info(
            f"Re-debate session #{child.id} created from #{session_id} "
            f"with user_context: {body.message!r}"
        )
        return ChatResponse(
            reply="Re-debate started. Opening new analysis session...",
            rebate_session_id=child.id,
        )

    # Conversational follow-up — direct LLM call, no pipeline
    settings = get_settings()
    raw_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    context_parts = []
    if session.regime_snapshot:
        r = session.regime_snapshot
        context_parts.append(f"Regime: {r.get('regime')} (confidence={r.get('confidence', 0):.2f})")

    if session.recommendations:
        recs = session.recommendations.get("recommendations", [])
        rec_summary = "; ".join(
            f"{r['ticker']}: {r['action']} ({r['confidence']:.0%})"
            for r in recs[:6]
        )
        context_parts.append(f"Recommendations: {rec_summary}")
        context_parts.append(f"Thesis: {session.recommendations.get('overall_thesis', '')}")

    history_parts = []
    for msg in (session.conversation or [])[-6:]:  # last 6 messages for context
        history_parts.append(f"{msg['role'].upper()}: {msg['content']}")

    system_prompt = (
        "You are a research analyst assistant. The user has just reviewed an agent debate "
        "about the following stocks. Answer their follow-up questions concisely and accurately "
        "using the debate context provided. Be direct. Do not repeat the full analysis unless asked."
    )

    user_content = ""
    if context_parts:
        user_content += "## Session Context\n" + "\n".join(context_parts) + "\n\n"
    if history_parts:
        user_content += "## Conversation History\n" + "\n".join(history_parts) + "\n\n"
    user_content += f"## User Question\n{body.message}"

    try:
        response = await raw_client.messages.create(
            model=settings.llm_model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        reply_text = response.content[0].text if response.content else "No response."
    except Exception as e:
        logger.error(f"Discovery chat LLM call failed: {e}")
        reply_text = "I encountered an error generating a response. Please try again."

    assistant_msg = {
        "role": "assistant",
        "content": reply_text,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    conversation = conversation + [assistant_msg]
    session.conversation = conversation
    await db.commit()

    return ChatResponse(reply=reply_text)


@router.post("/sessions/{session_id}/push-to-approvals", response_model=PushToApprovalsResponse)
async def push_to_approvals(
    session_id: int,
    body: PushToApprovalsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Push selected discovery recommendations to the trade approval queue.

    CONSIDER maps to BUY with half position size.
    AVOID is skipped silently.
    """
    session = await _get_session_or_404(db, session_id)

    if not session.recommendations:
        raise HTTPException(status_code=422, detail="Session has no recommendations yet.")

    recs = session.recommendations.get("recommendations", [])
    trade_ids = []

    for idx in body.recommendation_indices:
        if idx < 0 or idx >= len(recs):
            continue
        rec = recs[idx]

        if rec["action"] == "AVOID":
            continue

        # CONSIDER → BUY with reduced position size
        action = "BUY"
        size_pct = rec["position_size_pct"]
        if rec["action"] == "CONSIDER":
            size_pct = size_pct * 0.5

        trade = TradeDecisionORM(
            pipeline_run_id=session.pipeline_run_id,
            ticker=rec["ticker"],
            sleeve=body.sleeve,
            action=action,
            confidence=rec["confidence"],
            position_size_pct=size_pct,
            reasoning=(
                f"{rec['reasoning']}\n\n"
                f"[Proposed via Discovery session #{session_id}]"
            ),
            stop_loss_pct=rec.get("stop_loss_pct"),
            take_profit_pct=rec.get("take_profit_pct"),
            status="PENDING",
            wash_sale_flagged=False,
        )
        db.add(trade)
        await db.flush()
        trade_ids.append(trade.id)

    if trade_ids:
        await process_new_decisions(db, trade_ids)

    await db.commit()
    logger.info(
        f"Discovery session #{session_id} pushed {len(trade_ids)} trades to approval queue."
    )
    return PushToApprovalsResponse(queued=len(trade_ids), trade_ids=trade_ids)


@router.post("/sessions/{session_id}/push-to-watchlist", response_model=PushToWatchlistResponse)
async def push_to_watchlist(
    session_id: int,
    body: PushToWatchlistRequest,
    db: AsyncSession = Depends(get_db),
):
    """Add tickers from a discovery session to the watchlist."""
    await _get_session_or_404(db, session_id)

    added = 0
    already_existed = 0

    for ticker in [t.upper().strip() for t in body.tickers]:
        result = await db.execute(
            select(Watchlist).where(
                Watchlist.ticker == ticker,
                Watchlist.sleeve == body.sleeve,
            )
        )
        existing = result.scalars().first()

        if existing:
            if not existing.is_active:
                existing.is_active = True
                if body.notes:
                    existing.notes = body.notes
                await db.flush()
                added += 1
            else:
                already_existed += 1
        else:
            entry = Watchlist(
                ticker=ticker,
                sleeve=body.sleeve,
                notes=body.notes or f"Added from discovery session #{session_id}",
                is_active=True,
            )
            db.add(entry)
            await db.flush()
            added += 1

    await db.commit()
    logger.info(
        f"Discovery session #{session_id} added {added} tickers to watchlist ({body.sleeve})."
    )
    return PushToWatchlistResponse(added=added, already_existed=already_existed)


@router.get("/sessions")
async def list_sessions(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List recent discovery sessions."""
    result = await db.execute(
        select(DiscoverySession)
        .order_by(DiscoverySession.created_at.desc())
        .limit(limit)
    )
    sessions = result.scalars().all()
    return {"sessions": [_session_state(s) for s in sessions]}
