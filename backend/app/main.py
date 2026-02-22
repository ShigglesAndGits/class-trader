"""
Class Trader — FastAPI application entry point.

Starts up with DB initialization, registers all routers,
and exposes a health check so Docker knows we're alive.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import close_db, init_db
from app.scheduling.scheduler import shutdown_scheduler, start_scheduler
from app.routers import (
    agents,
    analytics,
    approvals,
    dashboard,
    discovery,
    news,
    portfolio,
    settings as settings_router,
    watchlist,
    ws,
)

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Class Trader backend...")
    await init_db()
    logger.info("Database initialized.")

    # Seed LLM config defaults (idempotent — skips existing rows)
    from app.agents.agent_config_seeder import seed_agent_configs
    await seed_agent_configs()

    # Populate runtime cache from DB so agents can read config immediately
    from app.database import AsyncSessionLocal
    from app.runtime_config import seed_runtime_from_db
    async with AsyncSessionLocal() as db:
        await seed_runtime_from_db(db)
    logger.info("LLM agent configs loaded into runtime cache.")

    start_scheduler()
    yield
    logger.info("Shutting down...")
    shutdown_scheduler()
    await close_db()


app = FastAPI(
    title="Class Trader",
    description="LLM-driven autonomous trading platform. We're here under protest.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])
app.include_router(news.router, prefix="/api/news", tags=["news"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["watchlist"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(discovery.router, prefix="/api/discovery", tags=["discovery"])
app.include_router(ws.router, prefix="/ws", tags=["websocket"])


# ── Health check ───────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health() -> dict[str, Any]:
    configured = settings.configured_apis()
    return {
        "status": "ok",
        "version": "0.1.0",
        "environment": "paper" if settings.alpaca_paper else "LIVE",
        "apis_configured": configured,
        "all_apis_ready": all(configured.values()),
    }
