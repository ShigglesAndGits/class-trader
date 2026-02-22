"""
Agent pipeline router.

GET  /api/agents/runs          — list pipeline runs
GET  /api/agents/runs/{run_id} — single run with all agent interactions
POST /api/agents/trigger       — manually kick off a pipeline run
"""

import logging
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pipeline import run_pipeline_background
from app.database import get_db
from app.models.pipeline import AgentInteraction, PipelineRun

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/runs")
async def get_pipeline_runs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List recent pipeline runs, newest first."""
    rows = (await db.execute(
        select(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(limit)
    )).scalars().all()

    return {
        "runs": [
            {
                "id": r.id,
                "run_type": r.run_type,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "regime": r.regime,
                "regime_confidence": r.regime_confidence,
                "status": r.status,
                "error_message": r.error_message,
            }
            for r in rows
        ]
    }


@router.get("/runs/{run_id}")
async def get_pipeline_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return a single pipeline run with all its agent interactions."""
    run = (await db.execute(
        select(PipelineRun).where(PipelineRun.id == run_id)
    )).scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline run {run_id} not found.")

    interactions = (await db.execute(
        select(AgentInteraction)
        .where(AgentInteraction.pipeline_run_id == run_id)
        .order_by(AgentInteraction.created_at)
    )).scalars().all()

    return {
        "run": {
            "id": run.id,
            "run_type": run.run_type,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "regime": run.regime,
            "regime_confidence": run.regime_confidence,
            "status": run.status,
            "error_message": run.error_message,
        },
        "interactions": [
            {
                "id": i.id,
                "agent_type": i.agent_type,
                "prompt_text": i.prompt_text or "",
                "response_text": i.response_text or "",
                "parsed_output": i.parsed_output,
                "tokens_used": i.tokens_used,
                "latency_ms": i.latency_ms,
                "retry_count": i.retry_count,
                "success": i.success,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in interactions
        ],
    }


@router.get("/runs/{run_id}/interactions/{interaction_id}")
async def get_agent_interaction(
    run_id: int,
    interaction_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return full prompt, response, and parsed output for a single agent interaction."""
    interaction = (await db.execute(
        select(AgentInteraction).where(
            AgentInteraction.id == interaction_id,
            AgentInteraction.pipeline_run_id == run_id,
        )
    )).scalar_one_or_none()

    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found.")

    return {
        "id": interaction.id,
        "agent_type": interaction.agent_type,
        "prompt_text": interaction.prompt_text,
        "response_text": interaction.response_text,
        "parsed_output": interaction.parsed_output,
        "tokens_used": interaction.tokens_used,
        "latency_ms": interaction.latency_ms,
        "retry_count": interaction.retry_count,
        "success": interaction.success,
        "created_at": interaction.created_at.isoformat() if interaction.created_at else None,
    }


@router.post("/trigger")
async def trigger_pipeline(
    background_tasks: BackgroundTasks,
    run_type: Literal["MANUAL", "MORNING", "NOON"] = "MANUAL",
):
    """
    Manually trigger a pipeline run.
    Returns immediately; pipeline runs in the background.
    Poll GET /api/agents/runs to see status.
    """
    logger.info(f"Manual pipeline trigger requested (type={run_type})")
    background_tasks.add_task(run_pipeline_background, run_type)
    return {
        "status": "triggered",
        "run_type": run_type,
        "message": "Pipeline started in background. Check /api/agents/runs for status.",
    }
