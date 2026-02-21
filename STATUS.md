# Class Trader — Development Status

**Last updated:** All development phases complete
**Next:** Phase 6 — Paper Trading Burn-in (requires API keys)

---

## What Has Been Built

### Phase 1: Foundation ✅ COMPLETE

**Docker infrastructure:**
- `docker-compose.yml` — three services: `db` (PostgreSQL 16), `backend` (FastAPI :8000), `frontend` (React/Vite :3000)
- `backend/Dockerfile` — Python 3.12-slim, installs from `backend/pyproject.toml`
- `frontend/Dockerfile` — Node 20 Alpine, `npm run dev` with `--host 0.0.0.0`
- `.env.example` — all required env vars documented
- `.gitignore` — `.env` excluded

**Backend core:**
- `backend/app/config.py` — pydantic-settings, `get_settings()` cached via `@lru_cache`. All env vars typed. Has `configured_apis()` method returning `dict[str, bool]` for health checks.
- `backend/app/database.py` — async SQLAlchemy engine (asyncpg), `AsyncSessionLocal`, `get_db` dependency, `init_db()` / `close_db()` for lifespan.
- `backend/app/main.py` — FastAPI app with CORS, all routers registered, `/health` endpoint, lifespan calls `init_db()`.

**Database models** (`backend/app/models/`):
- `pipeline.py` — `PipelineRun`, `AgentInteraction` (with JSONB `parsed_output`, full prompt/response logging)
- `trading.py` — `TradeDecision`, `Execution`, `Position`
- `market_data.py` — `NewsItem`, `PortfolioSnapshot`, `RedditMention`
- `risk.py` — `WashSale`, `CircuitBreakerEvent`
- `watchlist.py` — `Watchlist` (with unique constraint on ticker+sleeve)
- `models/__init__.py` — imports all models so SQLAlchemy `create_all` sees them

**Alembic** (`backend/alembic/`):
- `env.py` — async-aware, reads `DATABASE_URL` from env, imports all models
- `alembic.ini` — configured
- `script.py.mako` — migration template
- **Note:** No migration versions created yet. The app uses `init_db()` → `Base.metadata.create_all()` at startup for now. Alembic is wired up but `alembic revision --autogenerate` hasn't been run.

**Pydantic schemas** (`backend/app/schemas/`):
- `agents.py` — `RegimeAssessment`, `RetailSentiment`, `TickerAnalysis`, `ResearcherVerdict`, `TradeDecision` (agent schema, NOT ORM), `PortfolioDecision`, `DegenDecision`, plus Instructor wrappers: `TickerAnalyses`, `ResearcherVerdicts`, `DegenDecisions`
- `market.py` — `MarketContext`, `TickerContext`, `PriceBar`, `NewsItem`, `Position`, `WashSaleEntry`
- `trading.py` — `TradeDecisionResponse`, `ApproveRejectRequest`, `PositionResponse`, `PortfolioSummary` (API response shapes)
- `api.py` — `HealthResponse`, `PaginatedResponse`, `ErrorResponse`, `SuccessResponse`

**Data clients** (`backend/app/data/`):
- `alpaca_client.py` — `AlpacaClient`: `get_account()`, `get_positions()`, `get_daily_bars(tickers)`, `get_latest_quotes(tickers)`, `ping()`, `submit_market_order()`, `get_order_status()`, `cancel_order()`
- `finnhub_client.py` — `FinnhubClient`: `get_quote()`, `get_company_news()`, `get_news_sentiment()`, `get_insider_sentiment()`, `get_earnings_calendar()`, `get_vix()`, `get_treasury_yield_10y()`, `ping()`
- `alphavantage_client.py` — `AlphaVantageClient`: `get_rsi()`, `get_macd()`, `get_bollinger_bands()`, `ping()`
- `fmp_client.py` — `FMPClient`: `get_profile()`, `get_key_metrics()`, `get_earnings_surprises()`, `ping()`
- `tendiebot.py` — `TendieBot`: async reddit crawler using asyncpraw, `get_retail_sentiment(watchlist)`, naive keyword sentiment scoring, caution flag detection (pump-and-dump heuristic)
- `cache.py` — `TTLCache` (in-memory, per-cycle), `pipeline_cache` module-level singleton
- `aggregator.py` — **FULL IMPLEMENTATION** (see Phase 2 below)

**API routers** (`backend/app/routers/`): all registered in `main.py`
- `dashboard.py` — ✅ real implementation (Phase 4)
- `agents.py` — ✅ real implementation (Phase 2)
- `portfolio.py` — ✅ real implementation (Phase 4)
- `approvals.py` — ✅ real implementation (Phase 3)
- `news.py` — ✅ real implementation (Phase 4)
- `analytics.py` — ✅ real implementation (Phase 4)
- `watchlist.py` — ✅ real implementation (Phase 4)
- `settings.py` — ✅ real implementation with runtime toggle + circuit breakers (Phase 3/4)
- `ws.py` — `ConnectionManager` class, WebSocket endpoint at `/ws/updates`, 30s ping keepalive, `manager.broadcast()` for pushing events

**Frontend shell** (`frontend/`):
- Vite + React 18 + TypeScript + Tailwind CSS
- Dark theme colors exactly as specced: `bg=#0A0E17`, `surface=#111827`, `gain=#10B981`, `loss=#EF4444`, `warning=#F59E0B`, `info=#3B82F6`
- Fonts: JetBrains Mono (data), DM Sans (UI chrome)
- Custom CSS utilities: `.card`, `.card-header`, `.btn-primary`, `.btn-danger`, `.btn-ghost`, `.badge-gain`, `.badge-loss`, `.badge-warning`, `.badge-info`
- `src/components/layout/` — `Sidebar.tsx` (nav with "under protest" tagline), `Header.tsx`, `Layout.tsx`
- `src/hooks/` — `useWebSocket.ts` (auto-reconnect), `usePortfolio.ts`, `useApprovals.ts`
- `src/api/client.ts` — `api.get/post/put/patch/delete` fetch wrapper
- `src/lib/types.ts` — TypeScript types mirroring all backend schemas
- `src/lib/utils.ts` — `formatDollar`, `formatPct`, `formatConfidence`, `pnlColor`, `formatTime`, `formatDate`
- `src/lib/constants.ts` — `REGIME_LABELS`, `REGIME_COLORS`, `AGENT_LABELS`, `ACTION_COLORS`

**Scripts:**
- `scripts/test_connections.py` — tests Anthropic, Alpaca, Finnhub, Alpha Vantage, FMP, Reddit connections
- `scripts/init_watchlist.py` — seeds watchlist tickers to DB via `ON CONFLICT DO NOTHING`

---

### Phase 2: Agent Pipeline ✅ COMPLETE

**Agents** (`backend/app/agents/`):

`base.py` — `BaseAgent(ABC)`:
- Async Anthropic client via `instructor.from_anthropic(AsyncAnthropic())`
- `_call(response_model, user_content, max_tokens)` — calls LLM with Instructor structured output, uses `create_with_completion` to capture token usage
- Retry logic: up to `settings.llm_max_retries` (default 3) on `RateLimitError` / `APITimeoutError` with exponential backoff. Instructor handles internal validation retries (`max_retries=3` passed to create).
- `_log(...)` — writes `AgentInteraction` ORM record to DB after every call (success or failure), flushes immediately
- `load_prompt(filename)` — loads system prompt markdown from `agents/prompts/`

`formatters.py` — market data → LLM-readable text:
- `format_broad_market(ctx)` — for Regime Analyst; includes SPY bars, VIX, yield, sectors
- `format_ticker(ticker, ctx)` — per-ticker: price changes (5d/10d/30d), volume vs avg, RSI/MACD/Bollinger, news sentiment, insider, P/E, market cap, earnings date, retail sentiment with caution flags, top 5 headlines
- `format_tickers_for_analysis(ctx, tickers)` — all tickers for Bull/Bear
- `format_bull_bear_for_researcher(bull, bear)` — side-by-side for Researcher
- `format_portfolio_manager_context(...)` — full picture for PM: regime, portfolio state, wash sale blacklist, researcher verdicts with bull/bear confidence
- `format_penny_context(ctx, penny_tickers)` — for Degen

**6 agent implementations** (all extend `BaseAgent`):
- `regime_analyst.py` — `RegimeAnalyst.analyze(ctx)` → `RegimeAssessment`
- `bull_agent.py` — `BullAgent.analyze(ctx, regime, tickers)` → `list[TickerAnalysis]`
- `bear_agent.py` — `BearAgent.analyze(ctx, regime, tickers)` → `list[TickerAnalysis]`
- `researcher.py` — `Researcher.analyze(ctx, bull_analyses, bear_analyses)` → `list[ResearcherVerdict]`
- `portfolio_manager.py` — `PortfolioManager.decide(ctx, regime, bull, bear, verdicts)` → `PortfolioDecision`
- `degen.py` — `DegenAgent.decide(ctx, regime, penny_tickers)` → `list[DegenDecision]`

**6 prompt files** (`agents/prompts/*.md`): KERNEL-structured system personas for each agent.

`pipeline.py` — orchestrator:
- `run_pipeline(db, run_type)` → `PipelineResult` — main entry point
- Creates `PipelineRun` DB record, runs agents, persists `TradeDecision` records, marks run COMPLETED or FAILED
- Bull and Bear run **in parallel** via `asyncio.gather`
- `_persist_trade_decisions()` — writes all decisions as PENDING, then calls `approval_queue.process_new_decisions()`
- `run_pipeline_background(run_type)` — creates its own `AsyncSessionLocal` session, for use with FastAPI `BackgroundTasks`

`aggregator.py` — full MarketContext builder:
- Loads watchlist from DB (main/benchmark/penny separation)
- SPY always included even if not in watchlist
- Parallel Alpaca fetches + Finnhub (VIX, yield) via `asyncio.gather` with `return_exceptions=True`
- Alpha Vantage RSI + MACD for shortlisted only (top 8 by news sentiment strength + 5d price move)
- FMP profiles for shortlisted (≤15)
- TendieBot crawl if Reddit configured
- Wash sale blacklist from DB
- Assembles `TickerContext` per ticker; handles all missing data gracefully

---

### Phase 3: Execution Engine ✅ COMPLETE

**`backend/app/execution/`:**

`wash_sale_tracker.py`:
- `record_wash_sale(db, ticker, ...)` — creates `WashSale` record with 30-day blackout window
- `is_wash_sale_blocked(db, ticker)` → bool — hard block for December 1–31 year-end protection
- `get_active_wash_sale(db, ticker)` → Optional[WashSale] — for cost basis flagging
- `mark_rebought(db, ticker)` — marks the wash sale as acted upon

`risk_manager.py`:
- `RiskCheckResult` dataclass — `allowed`, `blocked_reason`, `requires_manual_approval`, `wash_sale_flag`, `notes`
- `check_trade(db, ticker, action, sleeve, confidence, position_size_pct, ...)` → `RiskCheckResult`
  - Confidence gate (min 0.65 main / 0.60 penny)
  - Position size limit (max 30% main / $8 penny)
  - Max concurrent positions (8 main / 5 penny)
  - Circuit breaker active check
  - Wash sale check (hard block Dec, flag otherwise)
  - Manual approval override conditions (new ticker, >30%, low confidence, CB active)
- `is_circuit_breaker_active(db, sleeve)` → bool
- `trigger_circuit_breaker(db, event_type, sleeve, reason)` → CircuitBreakerEvent
- `resolve_circuit_breaker(db, event_id, resolved_by)` → Optional[CircuitBreakerEvent]
- `get_today_realized_pnl(db, sleeve)` → float
- `count_consecutive_losses(db, sleeve)` → int

`engine.py`:
- `execute_trade(db, trade)` → Optional[Execution]
  - Gets latest price via `asyncio.to_thread(alpaca.get_latest_quotes, [ticker])`
  - Calculates qty (BUY: based on position_size_pct of sleeve equity; SELL: full position from DB)
  - Submits via `asyncio.to_thread(alpaca.submit_market_order, ...)`
  - Polls for fill: 2s intervals, 90s timeout
  - Creates `Execution` ORM record with fill price and slippage
  - Updates `Position` (create or update existing)
  - On loss-generating SELL: calls `record_wash_sale`
  - Post-execution: daily loss limit check, consecutive loss check
  - Broadcasts WebSocket event: `{"type": "trade_executed", ...}`

`approval_queue.py`:
- `process_new_decisions(db, trade_ids)` — risk check → REJECTED / APPROVED+execute / PENDING+notify
  - Uses `get_auto_approve()` from `runtime_config` (not the cached Settings value)
- `get_pending_approvals(db)` → list[TradeDecision]
- `approve_trade(db, trade_id, resolved_by="MANUAL")` → Optional[TradeDecision]
- `reject_trade(db, trade_id, resolved_by="MANUAL")` → Optional[TradeDecision]
- `_notify_pending(trade)` — sends notification via Apprise when queuing for manual approval

**`backend/app/notifications/notifier.py`:**
- `Notifier` class using Apprise; no-ops gracefully if no APPRISE_URLS configured
- `get_notifier()` — `@lru_cache` singleton
- Events: `trade_proposed`, `trade_executed`, `circuit_breaker`, `system_error`, `daily_summary`

**`backend/app/runtime_config.py`:**
- In-memory `_auto_approve` toggle initialized from `.env`
- `get_auto_approve()` / `set_auto_approve(value)` — used by approval_queue and settings router
- Resets to `.env` value on container restart

**`routers/approvals.py`** — full implementation:
- `GET /api/approvals/pending`
- `POST /api/approvals/{trade_id}/approve`
- `POST /api/approvals/{trade_id}/reject`
- `POST /api/approvals/bulk-approve` (body: list of IDs)
- `POST /api/approvals/bulk-reject` (body: list of IDs)

**`scripts/init_watchlist.py`** — writes to DB via raw async SQL with `ON CONFLICT DO NOTHING`.

---

### Phase 4: Web UI ✅ COMPLETE

**Backend routers implemented:**

`routers/dashboard.py`:
- `GET /api/dashboard/summary` — portfolio totals, regime, open positions, recent decisions (24h), auto_approve state, pending approval count

`routers/portfolio.py`:
- `GET /api/portfolio/positions` — grouped by sleeve (main/penny), includes wash_sale_adjusted flag, adjusted_cost_basis, cost_per_share
- `GET /api/portfolio/snapshots` — PortfolioSnapshot history (limit 90, chronological)
- `GET /api/portfolio/trades` — TradeDecision + Execution join, with fill price and slippage
- `GET /api/portfolio/closed` — closed Position records

`routers/analytics.py`:
- `GET /api/analytics/performance` — win_rate, avg_gain, avg_loss, total_realized_pnl, largest_gain/loss, Sharpe ratio
- `GET /api/analytics/equity-curve` — PortfolioSnapshot history for chart, `has_benchmark` flag
- `GET /api/analytics/agent-accuracy` — rough PM win rate from closed positions

`routers/news.py`:
- `GET /api/news/feed` — NewsItem records (filterable by ticker, limit)
- `GET /api/news/sentiment` — aggregated sentiment per ticker
- `GET /api/news/retail` — RedditMention records sorted by hype_score

`routers/watchlist.py`:
- `GET /api/watchlist/` — all entries ordered by sleeve, ticker
- `POST /api/watchlist/` — add ticker (reactivates if previously deactivated)
- `PATCH /api/watchlist/{entry_id}` — update notes or is_active
- `DELETE /api/watchlist/{entry_id}` — soft delete (sets is_active=False)

`routers/settings.py`:
- `GET /api/settings/` — runtime config + API status + risk params
- `PUT /api/settings/auto-approve` — runtime toggle (resets on restart)
- `GET /api/settings/circuit-breakers` — all CB events, active first
- `POST /api/settings/circuit-breakers/{id}/resolve` — manually resolve

**Frontend shared components** (`src/components/shared/`):
- `SparkLine.tsx` — Recharts mini line chart (`data: number[]`)
- `PriceChange.tsx` — color-coded dollar/pct display
- `ConfidenceBadge.tsx` — green ≥0.80, amber ≥0.65, red otherwise
- `LoadingState.tsx` — animated spinner with message

**Frontend dashboard components** (`src/components/dashboard/`):
- `RegimeBadge.tsx` — colored regime classification badge with confidence %
- `AutoApproveToggle.tsx` — toggle button using `useMutation` → `PUT /api/settings/auto-approve`
- `PositionsTable.tsx` — open positions with sleeve badge, qty, entry price, cost basis
- `RecentActivity.tsx` — trade decision feed with action badge and status color

**Frontend approval components** (`src/components/approvals/`):
- `ApprovalCard.tsx` — expandable card with approve/reject, wash sale warning, reasoning

**Frontend agent components** (`src/components/agents/`):
- `AgentCard.tsx` — colored left border per agent type, parsed_output JSON, token/latency stats
- `ReasoningExpander.tsx` — show/hide prompt/response viewer

**Frontend pages** (`src/pages/`):
- `Dashboard.tsx` — portfolio card, regime badge, auto-approve toggle, positions table, recent activity, "Run Pipeline" trigger
- `AgentActivity.tsx` — two-panel: run list (left) + agent interaction detail (right)
- `Portfolio.tsx` — position lists by sleeve + trade history table with execution fill details
- `Approvals.tsx` — approval queue with bulk approve/reject, uses `usePendingApprovals` hook
- `Analytics.tsx` — Recharts AreaChart equity curve with optional SPY benchmark overlay + 6 metric cards
- `NewsSentiment.tsx` — news feed (sentiment colored) + TendieBot retail panel (hype score, velocity spike alert ≥5x)
- `Settings.tsx` — trading mode, auto-approve toggle, circuit breaker list+resolve, watchlist CRUD, risk params, API status

---

### Phase 5: Scheduling & Integration ✅ COMPLETE

**`backend/app/scheduling/scheduler.py`** — Full APScheduler implementation wired into FastAPI lifespan.

`AsyncIOScheduler` (APScheduler 3.x). All times Eastern (ET).

| Job | Schedule | Description |
|-----|----------|-------------|
| `_morning_rebalance` | 9:35 AM Mon-Fri | Full pipeline `run_pipeline_background("MORNING")` |
| `_noon_review` | 12:00 PM Mon-Fri | Full pipeline `run_pipeline_background("NOON")` |
| `_news_monitor` | every 15 min Mon-Fri | Finnhub sentiment poll; triggers `NEWS_TRIGGER` if \|score\| > 0.8; saves new articles to DB |
| `_tendiebot_crawl` | every 30 min Mon-Fri | Reddit crawl; saves `reddit_mentions`; hype alert if velocity ≥ 5x |
| `_portfolio_snapshot` | 4:10 PM Mon-Fri | Records `PortfolioSnapshot` — Alpaca live values preferred, DB fallback; includes SPY benchmark |
| `_daily_summary` | 4:15 PM Mon-Fri | Aggregates today's trades + snapshot; sends via `notifier.daily_summary()` |
| `_weekend_maintenance` | Sat 2:00 AM | Logs expired wash sale records; weekly performance summary |

Key design details:
- `_is_market_hours()` guard in news monitor and TendieBot (no-op outside 9:30–4:00 PM ET)
- 60-minute cooldown on news-triggered pipeline runs (`_last_news_trigger` module-level state)
- `max_instances=1` on all jobs prevents overlap
- Every job catches all exceptions internally — no job crash can propagate
- Jobs degrade gracefully when API keys aren't configured
- `start_scheduler()` / `shutdown_scheduler()` called from `main.py` lifespan

---

## Pre-API-Key Hardening ✅ COMPLETE

Changes made while waiting for API keys:

**WebSocket real-time updates** (`frontend/src/App.tsx`):
- `WS_INVALIDATIONS` map — 8 event types → affected TanStack Query cache keys
- `useWebSocket(handleMessage)` wired at app root — auto-invalidates queries on `trade_executed`, `pipeline_complete`, `circuit_breaker`, etc.

**Docker health check** (`docker-compose.yml`):
- `backend` service: Python urllib healthcheck against `http://localhost:8000/health`, 30s interval, 30s start_period
- `frontend` depends_on updated to `condition: service_healthy` — waits for backend to be ready

**Dashboard countdown** (`frontend/src/components/dashboard/NextRunCountdown.tsx`):
- Uses `Intl.DateTimeFormat` with `America/New_York` timezone (DST-aware)
- Shows next scheduled run: 9:35 AM ET or 12:00 PM ET (weekdays only)
- Handles after-noon and weekend rollover to next Monday
- Updates every 60 seconds

**Unit tests:**
- `backend/tests/test_risk/test_risk_manager.py` — 13 tests: confidence gate, position size, capacity, circuit breaker, wash sale (Dec hard block vs flag), auto-approve override conditions
- `backend/tests/test_risk/test_wash_sale_tracker.py` — 10 tests: all 4 public functions (`record_wash_sale`, `is_wash_sale_blocked`, `get_active_wash_sale`, `mark_rebought`)
- `backend/tests/test_execution/test_engine.py` — 7 tests: `_calculate_qty` for BUY (MAIN/PENNY/capped/floored) and SELL (DB hit, DB miss + Alpaca empty, Alpaca raises)
- `backend/tests/test_execution/test_approval_queue.py` — 9 tests: `approve_trade`, `reject_trade`, `get_pending_approvals` (including not-found, already-resolved, and empty-queue cases)

---

## Phase 6: Paper Trading Burn-in — NEXT

**Goal:** Run on paper trading for 2+ weeks, tune, stabilize.

**Prerequisite:** API keys and `.env` file (copy from `.env.example`).

**First-boot integration checklist:**
```
docker-compose up --build
GET  localhost:8000/health                      # {"status": "ok"}
GET  localhost:8000/docs                        # Swagger — verify all routes visible
python scripts/test_connections.py             # all APIs green
python scripts/init_watchlist.py               # seed tickers to DB
POST localhost:8000/api/agents/trigger         # manual pipeline run
# Check: agent interactions in DB, approval queue populated
# Approve a trade, verify execution flow
```

**Tuning notes:**
- Agent reasoning quality: adjust prompt files in `agents/prompts/*.md`
- News monitor too noisy: raise the `|score| > 0.8` threshold in `scheduler.py`
- TendieBot alerts too frequent: raise the `5.0` velocity threshold

---

## Known Stubs / Not Yet Implemented

| Item | Status |
|------|--------|
| Alembic migrations | Not generated — app uses `create_all` at startup |
| Holiday calendar | No market holiday awareness — minor, jobs just return early |

---

## Key Architectural Notes

**Import paths:** All backend imports use `from app.xxx import yyy` (no relative imports). The `backend/` dir is the Docker working directory (`WORKDIR /app`), and the app source is at `/app/app/`.

**Async pattern:** The entire backend is async. Sync API client calls (Alpaca, Finnhub, AV, FMP) are wrapped in `asyncio.to_thread()` in the aggregator and execution engine. The Anthropic client uses the async variant (`AsyncAnthropic`).

**DB sessions:**
- Request-scoped sessions come from `get_db` FastAPI dependency (auto-commit on success, rollback on exception)
- Background tasks create their own sessions via `async with AsyncSessionLocal() as session:`
- Always use `await session.flush()` to get generated IDs before commit

**TradeDecision vs agent schema:** Two classes with the same name — beware:
- `app.schemas.agents.TradeDecision` — Pydantic model output by Portfolio Manager agent
- `app.models.trading.TradeDecision` — SQLAlchemy ORM model (stored in DB)

**WebSocket broadcasting:** `app.routers.ws.manager` is a module-level `ConnectionManager` instance. Import and call `await manager.broadcast({"type": "...", ...})` from anywhere in the backend.

**Auto-approve flow:**
1. Pipeline writes all decisions as PENDING
2. `approval_queue.process_new_decisions()` runs risk checks
3. If risk blocks: status → REJECTED
4. If `get_auto_approve()` is True AND risk doesn't require manual: status → APPROVED → `execute_trade()`
5. Otherwise: status stays PENDING → notification sent

**Risk limits are NOT in agent prompts.** Enforced exclusively in `risk_manager.py`. The LLM cannot override them.

**Runtime auto-approve toggle:** `runtime_config.py` holds an in-memory boolean initialized from `.env`. Changeable via `PUT /api/settings/auto-approve`. Resets on restart — edit `.env` to persist.

## LLM Model

`claude-haiku-4-5-20251001` — configured in `settings.llm_model`. This is the model ID used in all agent calls.

## Tech Choices Made

- **Instructor** for structured LLM output (not raw JSON parsing). Handles validation retries internally.
- **asyncpg** as the PostgreSQL async driver.
- **`asyncio.to_thread()`** to run synchronous API clients without blocking the event loop.
- Bull and Bear agents run **in parallel** — they're independent and both get the same MarketContext.
- AV technical indicators only fetched for **top 8 tickers** ranked by news sentiment strength + 5d price movement. Stays within 25-call/day free tier budget.
- All agent interactions logged to DB with full prompt/response text for the Agent Activity UI.
- Circuit breakers are hard-coded Python enforcement, not LLM guidance.
- Wash sale tracking is automatic: every SELL triggers a loss check; December is a hard block month.
