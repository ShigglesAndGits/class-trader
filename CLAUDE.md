# CLASS TRADER — LLM-Driven Autonomous Trading Platform

## Project Overview

Class Trader is a dockerized, locally-hosted autonomous trading platform that uses a multi-agent LLM pipeline to analyze markets and execute trades via Alpaca. It features a polished React web UI for monitoring, approving/rejecting trades, and reviewing agent reasoning.

**Owner context:** The developer is learning investing through this project. They have casual market experience (pandemic-era Robinhood trading, WSB/GME degen in 2020) but no formal finance background. The system should be educational — surfacing reasoning, explaining decisions, and logging everything obsessively. This is a $100 experimental deployment: $75 in a main portfolio sleeve, $25 in a high-risk penny stock sleeve.

**Ideological context:** The project lead is an anarcho-socialist FOSS advocate who finds the stock market morally repugnant but pragmatically necessary. They are building this with their nose held firmly shut — not out of love for capital markets, but because they need to position their family well for uncertain times ahead. This context matters for development tone: the UI copy, error messages, and any user-facing text should carry a subtle, dry awareness of the absurdity of the situation. Think "reluctant participant in capitalism" energy — not preachy, not performative, just the quiet irony of someone who's read Kropotkin building a trading bot. For example: a daily summary might sign off with something understated, the empty state for "no trades today" might read "Nothing today. The market can wait." — that kind of thing. The agents themselves should remain analytically sharp and ideologically neutral in their reasoning. The personality lives in the chrome, not the engine. This project will be open-sourced, because LLMs are trained on open-source software and closed-source LLM-assisted development is, in the project lead's view, theft from the commons.

## Core Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Docker Compose                     │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐ │
│  │ Frontend  │  │ Backend  │  │    PostgreSQL       │ │
│  │  (React)  │◄─┤ (FastAPI)│◄─┤  (data + logs)     │ │
│  │  :3000    │  │  :8000   │  │  :5432             │ │
│  └──────────┘  └────┬─────┘  └────────────────────┘ │
│                     │                                │
│              ┌──────┴──────┐                         │
│              │  Scheduler  │                         │
│              │  (APScheduler)                        │
│              └──────┬──────┘                         │
│                     │                                │
│         ┌───────────┼───────────┐                    │
│         ▼           ▼           ▼                    │
│   ┌──────────┐ ┌─────────┐ ┌────────┐              │
│   │  Agent   │ │  Data   │ │ Exec   │              │
│   │ Pipeline │ │ Fetcher │ │ Engine │              │
│   └──────────┘ └─────────┘ └────────┘              │
│         │                       │                    │
│         ▼                       ▼                    │
│   Anthropic API           Alpaca API                │
│   (Claude Haiku 4.5)     (Trading + Data)           │
│                                                      │
│   External Data: Finnhub, Alpha Vantage, FMP, Reddit │
│   Notifications: Apprise                            │
└─────────────────────────────────────────────────────┘
```

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, APScheduler, Pydantic v2
- **Frontend:** React 18 (Vite), TailwindCSS, Recharts, TanStack Query
- **Database:** PostgreSQL 16
- **LLM:** Claude Haiku 4.5 via Anthropic API (`claude-haiku-4-5-20251001`)
- **Broker:** Alpaca Markets (alpaca-py SDK)
- **Data:** Alpaca (prices), Finnhub (news/sentiment/fundamentals), Alpha Vantage (technical indicators), FMP (SEC filings/fundamentals), Reddit API via asyncpraw (retail sentiment)
- **Notifications:** Apprise
- **Structured Output:** Pydantic v2 + Instructor library
- **Containerization:** Docker Compose
- **Schema Migrations:** Alembic

## Multi-Agent Pipeline

The agent pipeline runs as a sequential flow. Each agent receives structured JSON context and produces structured JSON output. All agent interactions are logged to the database with full prompt/response pairs.

### Pipeline Flow

```
Data Fetch (parallel)
    ├── Alpaca: price bars, quotes, current positions, account equity
    ├── Finnhub: news headlines + sentiment, insider sentiment, earnings
    ├── Alpha Vantage: RSI, MACD, Bollinger Bands for top candidates
    ├── FMP: key fundamentals for tickers under evaluation
    └── TendieBot (Reddit): WSB/retail mention frequency, velocity, sentiment
         │
         ▼
┌─────────────────┐
│  Regime Analyst  │  ← Broad market data (SPY, VIX, sector ETFs, treasury yields)
│  Output: regime  │  ← One of: TRENDING_UP, TRENDING_DOWN, RANGING, HIGH_VOLATILITY
│  classification  │  ← Includes confidence score and brief reasoning
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│  Bull  │ │  Bear  │  ← Both receive: regime context + ticker data + news
│ Agent  │ │ Agent  │  ← Bull argues FOR positions, Bear argues AGAINST
│        │ │        │  ← Both must cite specific data points, no vague claims
└───┬────┘ └───┬────┘
    │          │
    └────┬─────┘
         ▼
┌─────────────────┐
│   Researcher    │  ← Receives Bull + Bear arguments
│   Output: fact  │  ← Identifies agreements (strongest signals)
│   check + gaps  │  ← Flags data inconsistencies, checks for thesis drift
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│  Portfolio Manager   │  ← Receives: regime + bull/bear + researcher + portfolio state
│  Output: structured  │  ← Final BUY/SELL/HOLD decisions with position sizes
│  trade decisions     │  ← Respects wash sale status, position limits, cash available
└────────┬────────────┘
         │
         ▼
┌─────────────────┐
│  Execution Gate  │  ← If auto-approve ON: execute immediately (within hard limits)
│                  │  ← If auto-approve OFF: send notification, await approval
└─────────────────┘

SEPARATE PIPELINE (runs after main):
┌─────────────────┐
│     Degen       │  ← Penny stock specialist, own risk params
│  (The Gambler)  │  ← Receives regime context but has independent analysis
│  Output: high-  │  ← Max $8/position, 3-5 positions, momentum-focused
│  risk trades    │  ← Aware it's playing with house money
└─────────────────┘
```

### Agent Prompt Design Principles

- Every agent gets a **persona** (who they are), **mandate** (what they must do), **constraints** (what they cannot do), and **output schema** (exact JSON structure).
- Prompts use the KERNEL methodology: Keep it simple, Easy to verify, Reproducible, Narrow scope, Explicit constraints, Logical structure.
- All agents output via Instructor-enforced Pydantic schemas. No free-form text reaches the execution engine.
- The Portfolio Manager prompt includes: current portfolio state, available settled cash, wash sale blacklist, per-position size limits, daily loss status, and the regime classification.
- The Degen agent is prompted with a distinct personality — higher risk tolerance, momentum-focused, shorter time horizons — but still outputs structured decisions through the same schema enforcement.
- **TendieBot retail sentiment is a DATA SOURCE, not an agent.** It feeds into the MarketContext alongside Finnhub news and Alpaca prices. All agents receive it, but they are prompted to treat it as a low-confidence supplementary signal. Specific prompt guidance per agent:
  - **Bull Agent:** May cite rising retail hype as supporting evidence for momentum, but must pair it with at least one non-retail data point.
  - **Bear Agent:** Should flag high retail hype with no fundamental catalyst as a warning sign (potential pump-and-dump or late-to-the-party risk).
  - **Researcher:** Should note when retail sentiment diverges sharply from institutional indicators (news sentiment, insider activity) — this divergence is itself a signal.
  - **Portfolio Manager:** Should never increase position size solely because of retail hype. Retail hype can support a decision but not drive it.
  - **Degen Agent:** Gets the most latitude with retail sentiment — for penny stocks, retail momentum IS a meaningful signal. But the Degen's prompt should explicitly warn: "A hype_score above 0.8 with mention_velocity above 3.0 and no corresponding news catalyst is a red flag for pump-and-dump. Proceed with extreme caution and reduced position size."

### Agent Output Schemas (Pydantic)

```python
class RegimeAssessment(BaseModel):
    regime: Literal["TRENDING_UP", "TRENDING_DOWN", "RANGING", "HIGH_VOLATILITY"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    key_indicators: list[str]

class RetailSentiment(BaseModel):
    """TendieBot output — retail/WSB sentiment data per ticker."""
    ticker: str
    mention_count_24h: int              # Raw mentions in last 24 hours
    mention_velocity: float             # % change vs 7-day average (1.0 = normal, 3.0 = 3x spike)
    avg_sentiment: float                # -1.0 (bearish) to 1.0 (bullish)
    hype_score: float                   # Composite: 0.0 (no buzz) to 1.0 (maximum hype)
    top_posts: list[str]                # Titles of highest-engagement posts mentioning ticker
    subreddits: list[str]              # Which subs are talking about it
    caution_flags: list[str]           # E.g. "sudden spike with no news catalyst", "bot-like posting pattern"

class TickerAnalysis(BaseModel):
    ticker: str
    stance: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    key_data_points: list[str]

class ResearcherVerdict(BaseModel):
    ticker: str
    bull_bear_agreement: Literal["AGREE_BULLISH", "AGREE_BEARISH", "DISAGREE", "INSUFFICIENT_DATA"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    flagged_issues: list[str]
    thesis_drift_warning: bool

class TradeDecision(BaseModel):
    action: Literal["BUY", "SELL", "HOLD"]
    ticker: str
    confidence: float = Field(ge=0.0, le=1.0)
    position_size_pct: float = Field(ge=0.0, le=30.0)  # max 30% per position
    reasoning: str
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None

class PortfolioDecision(BaseModel):
    regime: RegimeAssessment
    trades: list[TradeDecision]
    cash_reserve_pct: float = Field(ge=0.0, le=100.0)
    overall_reasoning: str
```

## Scheduling

Uses APScheduler running inside the FastAPI backend container.

| Schedule | Time (ET) | Action |
|----------|-----------|--------|
| Morning Rebalance | 9:35 AM | Full pipeline run (all agents). 5 min after open to avoid opening volatility. |
| Noon Review | 12:00 PM | Full pipeline run. Evaluates morning positions, checks for regime shifts. |
| News Monitor | Every 15 min during market hours | Lightweight Finnhub news poll. Only triggers a full pipeline run if a high-impact headline is detected (sentiment score > 0.8 or < -0.8). |
| TendieBot Crawl | Every 30 min during market hours | Reddit crawl of r/wallstreetbets, r/stocks, r/pennystocks. Updates retail sentiment data in MarketContext. Triggers alert if any watchlist ticker's mention_velocity exceeds 5x baseline. |
| Daily Summary | 4:15 PM | Post-close summary notification: P&L, trades executed, agent reasoning highlights. |
| Weekend Maintenance | Saturday 2:00 AM | Wash sale tracker cleanup, database maintenance, weekly performance report generation. |

## Risk Management (Hard-Coded, NOT LLM Decisions)

These are enforced in the execution engine code, not in agent prompts. The LLM cannot override them.

### Position Limits
- **Main sleeve:** No single position > 30% of sleeve equity ($75 base)
- **Penny sleeve:** No single position > $8 (32% of $25 base)
- **Main sleeve:** Maximum 8 concurrent positions
- **Penny sleeve:** Maximum 5 concurrent positions
- **Minimum confidence:** Do not execute trades below 0.65 confidence score
- **Penny minimum confidence:** Do not execute below 0.60 confidence (slightly more permissive)

### Circuit Breakers
- **Daily loss limit (main):** If main sleeve drops > 5% in a single day, halt all main trading and notify
- **Daily loss limit (penny):** If penny sleeve drops > 15% in a single day, halt penny trading and notify
- **Consecutive loss limit:** If 3 consecutive trades result in losses, pause and notify for manual review
- **API failure:** If Anthropic API fails 3 times consecutively, pause trading and notify
- **Schema failure:** If agent output fails Pydantic validation after 3 retries, pause and notify

### Wash Sale Tracking
- Maintain a database table tracking every sell-at-loss event: ticker, date, loss amount
- When Portfolio Manager proposes a BUY, the execution engine checks the wash sale table
- If the ticker was sold at a loss within the last 30 days: **allow the trade but flag it** in the UI and log the wash sale event with adjusted cost basis
- During December 1-31: **hard block** rebuys of any ticker sold at a loss within 30 days (year-end protection)
- Track adjusted cost basis for wash sale positions for accurate P&L reporting

### Auto-Approve Constraints
Even when auto-approve is toggled ON, the following require manual approval:
- Any single trade > 30% of sleeve value
- Any trade during a circuit breaker cooldown
- First trade on any new ticker not previously held
- Any trade where the Portfolio Manager's confidence is below 0.70

## Data Fetching Architecture

### Fetch Once, Share Everywhere
Data is fetched ONCE per pipeline cycle and stored in a `MarketContext` object. All agents read from this same context. The multi-agent architecture does NOT multiply data API calls.

```python
class MarketContext(BaseModel):
    timestamp: datetime
    # Broad market
    spy_bars: list[PriceBar]        # S&P 500 - from Alpaca
    vix_level: float                # Volatility index - from Finnhub
    sector_performance: dict        # Sector ETF returns - from Alpaca
    treasury_yield_10y: float       # From Finnhub
    # Retail sentiment (broad)
    wsb_trending_tickers: list[RetailSentiment]  # Top trending tickers on WSB
    # Per-ticker data
    ticker_data: dict[str, TickerContext]
    # Account state
    account_equity: float
    settled_cash: float
    current_positions: list[Position]
    wash_sale_blacklist: list[WashSaleEntry]

class TickerContext(BaseModel):
    ticker: str
    price_bars: list[PriceBar]      # From Alpaca (daily bars, last 30 days)
    current_price: float            # From Alpaca (latest quote)
    volume: int
    # Technical indicators - from Alpha Vantage
    rsi_14: Optional[float]
    macd: Optional[dict]
    bollinger_bands: Optional[dict]
    # News and sentiment - from Finnhub
    recent_news: list[NewsItem]     # Last 48 hours
    news_sentiment_avg: float       # Aggregated sentiment score
    insider_sentiment: Optional[float]
    # Fundamentals - from FMP
    pe_ratio: Optional[float]
    market_cap: Optional[float]
    earnings_date: Optional[date]
    # Retail sentiment - from TendieBot
    retail_sentiment: Optional[RetailSentiment]  # None if ticker not mentioned on Reddit
```

### API Rate Budget Per Cycle

| API | Calls per cycle | Daily budget (3 cycles) | Free limit |
|-----|----------------|------------------------|------------|
| Alpaca | ~5 (bars, quotes, positions, account) | ~15 | 200/min |
| Finnhub | ~60 (news + sentiment per ticker for ~50 tickers) | ~180 | 86,400/day |
| Alpha Vantage | ~8 (indicators for top candidates only) | ~24 | 25/day |
| FMP | ~15 (fundamentals for tickers under consideration) | ~45 | 250/day |
| Reddit | ~20 (subreddit hot/new posts + comment threads) | ~60 | 100/min |

Alpha Vantage is the tightest constraint. Strategy: only fetch AV indicators for tickers that the news/price screening suggests are worth analyzing. Use Finnhub for initial screening, AV for deep technical analysis on shortlisted candidates.

## Notification System

Uses Apprise for flexible notification routing. The user configures their preferred notification platform(s) via environment variables.

### Notification Events
- **Trade Proposed** (when auto-approve is OFF): Full trade details + agent reasoning summary + approve/reject links
- **Trade Executed**: Confirmation with fill price, slippage report
- **Circuit Breaker Triggered**: Immediate alert with reason
- **Daily Summary**: End-of-day P&L, trades, highlights
- **System Error**: API failures, schema validation failures, unexpected exceptions
- **Weekly Report**: Performance vs SPY benchmark, win rate, agent accuracy metrics

### Apprise Configuration
Set via `.env` — supports any Apprise-compatible URL scheme:
- Discord: `discord://webhook_id/webhook_token`
- Telegram: `tgram://bot_token/chat_id`
- Email: `mailto://user:pass@gmail.com`
- Slack: `slack://token_a/token_b/token_c`
- Pushover, Gotify, ntfy, etc.

## Web UI Design

### Design Direction
**Aesthetic:** Refined financial terminal meets modern dashboard. Dark theme primary. Think Bloomberg Terminal reimagined by a good design studio — data-dense but clean, with clear visual hierarchy.

**Typography:** Use a distinctive monospace or semi-monospace font for data (JetBrains Mono or IBM Plex Mono) paired with a clean sans-serif for UI chrome (DM Sans or Manrope). Numbers should feel precise and authoritative.

**Color Palette:**
- Background: Near-black (#0A0E17) with subtle blue undertone
- Surface: Dark navy (#111827) for cards
- Accent green: (#10B981) for gains/bullish
- Accent red: (#EF4444) for losses/bearish
- Accent amber: (#F59E0B) for warnings/neutral
- Accent blue: (#3B82F6) for informational/regime indicators
- Text primary: (#E5E7EB), Text secondary: (#9CA3AF)

**Key design principles:**
- Every number that matters should be glanceable
- Agent reasoning should be expandable, not in-your-face
- The approval/reject flow should be dead simple — prominent buttons, clear context
- Portfolio allocation should be visualized, not just listed
- Historical performance should tell a story with charts, not just numbers

### Pages / Views

1. **Dashboard (Home)**
   - Portfolio value with sparkline (main + penny sleeves shown separately)
   - Today's P&L (absolute and percentage, vs SPY benchmark)
   - Current regime classification with confidence badge
   - Active positions with live prices and unrealized P&L
   - Recent agent decisions (last 24h) as a compact feed
   - Next scheduled run countdown
   - Auto-approve toggle (prominent, with current state indicator)

2. **Agent Activity**
   - Timeline view of all pipeline runs
   - Expandable per-run view showing each agent's input/output
   - Full reasoning chains viewable for any decision
   - Filter by agent type, date range, ticker
   - Highlight disagreements between Bull and Bear agents

3. **Portfolio**
   - Current holdings with allocation pie/donut chart
   - Per-position detail: entry price, current price, P&L, days held
   - Separate sections for main sleeve and penny sleeve
   - Historical trades table with full details
   - Cash position and settled vs unsettled breakdown

4. **Trade Approval Queue**
   - Pending trades requiring approval (when auto-approve is OFF)
   - Each trade shows: ticker, action, size, confidence, agent reasoning summary
   - One-tap approve/reject buttons
   - Bulk approve/reject for multiple trades
   - Approval history with timestamps

5. **News & Sentiment**
   - Live news feed from Finnhub, filtered to watchlist tickers
   - Sentiment scores visualized per ticker over time
   - Highlighted articles that triggered agent analysis
   - News impact tracker: what the agents saw vs what the market did
   - **TendieBot / Retail Pulse panel:**
     - WSB trending tickers with hype scores and mention velocity sparklines
     - Reddit post feed for watchlist tickers (title, score, comment count, sentiment)
     - Hype alerts: visual callout when a ticker spikes above 5x baseline mention velocity
     - Historical retail sentiment vs price overlay chart (did the apes call it?)

6. **Performance & Analytics**
   - Equity curve chart (vs SPY benchmark)
   - Win rate, average gain, average loss, Sharpe ratio
   - Per-ticker performance breakdown
   - Agent accuracy: how often did Bull vs Bear vs PM get it right
   - Wash sale log with adjusted cost basis tracking
   - Monthly/weekly performance summaries

7. **Settings**
   - Watchlist management (add/remove tickers, tag as main or penny)
   - Risk parameter configuration (position limits, circuit breaker thresholds)
   - Auto-approve toggle and constraints
   - Notification configuration (Apprise URL)
   - API key status checks (green/red indicators for each service)
   - Scheduling configuration
   - Theme toggle (dark/light, though dark is default)

## Database Schema (PostgreSQL)

Key tables — use Alembic for migrations:

- **pipeline_runs**: id, run_type (MORNING/NOON/NEWS_TRIGGER), started_at, completed_at, regime, status
- **agent_interactions**: id, pipeline_run_id, agent_type, prompt_text, response_text, parsed_output (JSONB), tokens_used, latency_ms, created_at
- **trade_decisions**: id, pipeline_run_id, ticker, action, confidence, position_size_pct, reasoning, status (PENDING/APPROVED/REJECTED/EXECUTED/FAILED), created_at, resolved_at, resolved_by (AUTO/MANUAL)
- **executions**: id, trade_decision_id, order_id (Alpaca), side, qty, filled_price, slippage, fees, status, executed_at
- **positions**: id, ticker, sleeve (MAIN/PENNY), entry_price, entry_date, current_qty, cost_basis, is_open
- **wash_sales**: id, ticker, sale_date, loss_amount, adjusted_cost_basis, blackout_until, is_year_end_blocked
- **portfolio_snapshots**: id, timestamp, main_equity, penny_equity, total_equity, spy_benchmark_value, cash_balance
- **news_items**: id, ticker, headline, source, sentiment_score, published_at, fetched_at, triggered_analysis (bool)
- **reddit_mentions**: id, ticker, subreddit, post_title, post_url, post_score, comment_count, sentiment_score, hype_score, mention_velocity, fetched_at
- **notifications**: id, event_type, message, sent_at, delivery_status
- **watchlist**: id, ticker, sleeve (MAIN/PENNY), added_at, is_active, notes

## Environment Variables (.env)

```env
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Alpaca
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_PAPER=true          # Set to false for live trading

# Finnhub
FINNHUB_API_KEY=...

# Alpha Vantage
ALPHA_VANTAGE_API_KEY=...

# Financial Modeling Prep
FMP_API_KEY=...

# Reddit (TendieBot)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=class-trader:v0.1 (by /u/your-username)

# Database
POSTGRES_USER=classtrader
POSTGRES_PASSWORD=...
POSTGRES_DB=class_trader
DATABASE_URL=postgresql://classtrader:${POSTGRES_PASSWORD}@db:5432/class_trader

# Apprise Notifications (comma-separated for multiple)
APPRISE_URLS=discord://webhook_id/webhook_token

# App Config
AUTO_APPROVE=false
MAIN_SLEEVE_ALLOCATION=75.0
PENNY_SLEEVE_ALLOCATION=25.0
MAX_POSITION_PCT_MAIN=30.0
MAX_POSITION_DOLLARS_PENNY=8.0
MIN_CONFIDENCE_MAIN=0.65
MIN_CONFIDENCE_PENNY=0.60
DAILY_LOSS_LIMIT_MAIN_PCT=5.0
DAILY_LOSS_LIMIT_PENNY_PCT=15.0
CONSECUTIVE_LOSS_PAUSE=3
TIMEZONE=America/New_York
LOG_LEVEL=INFO
```

## Directory Structure

```
class-trader/
├── CLAUDE.md                          # This file
├── docker-compose.yml
├── .env.example
├── .gitignore
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml                 # Poetry or pip - dependencies
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app entry point
│   │   ├── config.py                  # Settings from .env via pydantic-settings
│   │   ├── database.py                # SQLAlchemy engine, session, Base
│   │   │
│   │   ├── models/                    # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py            # PipelineRun, AgentInteraction
│   │   │   ├── trading.py             # TradeDecision, Execution, Position
│   │   │   ├── market_data.py         # NewsItem, PortfolioSnapshot
│   │   │   ├── risk.py                # WashSale, CircuitBreakerEvent
│   │   │   └── watchlist.py           # Watchlist
│   │   │
│   │   ├── schemas/                   # Pydantic schemas (API + agent I/O)
│   │   │   ├── __init__.py
│   │   │   ├── agents.py              # RegimeAssessment, TickerAnalysis, etc.
│   │   │   ├── trading.py             # TradeDecision, PortfolioDecision
│   │   │   ├── market.py              # MarketContext, TickerContext, PriceBar
│   │   │   └── api.py                 # Request/response schemas for REST API
│   │   │
│   │   ├── agents/                    # LLM agent implementations
│   │   │   ├── __init__.py
│   │   │   ├── base.py                # BaseAgent class (Anthropic client, Instructor, logging)
│   │   │   ├── regime_analyst.py
│   │   │   ├── bull_agent.py
│   │   │   ├── bear_agent.py
│   │   │   ├── researcher.py
│   │   │   ├── portfolio_manager.py
│   │   │   ├── degen.py               # Penny stock specialist
│   │   │   ├── pipeline.py            # Orchestrates the full agent pipeline
│   │   │   └── prompts/               # Prompt templates (Jinja2 or string templates)
│   │   │       ├── regime_analyst.md
│   │   │       ├── bull_agent.md
│   │   │       ├── bear_agent.md
│   │   │       ├── researcher.md
│   │   │       ├── portfolio_manager.md
│   │   │       └── degen.md
│   │   │
│   │   ├── data/                      # Data fetching layer
│   │   │   ├── __init__.py
│   │   │   ├── alpaca_client.py       # Alpaca prices, positions, account, orders
│   │   │   ├── finnhub_client.py      # News, sentiment, earnings, insider data
│   │   │   ├── alphavantage_client.py # Technical indicators
│   │   │   ├── fmp_client.py          # Fundamentals, SEC filings
│   │   │   ├── tendiebot.py              # Reddit/WSB retail sentiment crawler
│   │   │   ├── aggregator.py          # Builds MarketContext from all sources
│   │   │   └── cache.py               # Simple in-memory cache to avoid redundant calls
│   │   │
│   │   ├── execution/                 # Trade execution engine
│   │   │   ├── __init__.py
│   │   │   ├── engine.py              # Core execution logic — submits orders to Alpaca
│   │   │   ├── risk_manager.py        # Position limits, circuit breakers, wash sale checks
│   │   │   ├── approval_queue.py      # Manages pending approvals
│   │   │   └── wash_sale_tracker.py   # Wash sale tracking and cost basis adjustment
│   │   │
│   │   ├── scheduling/                # APScheduler setup
│   │   │   ├── __init__.py
│   │   │   └── scheduler.py           # Cron jobs: morning, noon, news poll, daily summary
│   │   │
│   │   ├── notifications/             # Apprise integration
│   │   │   ├── __init__.py
│   │   │   └── notifier.py            # Send notifications via Apprise
│   │   │
│   │   └── routers/                   # FastAPI route handlers
│   │       ├── __init__.py
│   │       ├── dashboard.py           # GET portfolio summary, regime, recent activity
│   │       ├── agents.py              # GET pipeline runs, agent interactions
│   │       ├── portfolio.py           # GET positions, historical trades, snapshots
│   │       ├── approvals.py           # GET pending, POST approve/reject
│   │       ├── news.py                # GET news feed, sentiment data
│   │       ├── analytics.py           # GET performance metrics, equity curve
│   │       ├── watchlist.py           # CRUD watchlist tickers
│   │       ├── settings.py            # GET/PUT runtime config (auto-approve, thresholds)
│   │       └── ws.py                  # WebSocket endpoint for real-time UI updates
│   │
│   └── tests/
│       ├── __init__.py
│       ├── test_agents/
│       ├── test_execution/
│       ├── test_data/
│       └── test_risk/
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   │
│   ├── public/
│   │   └── favicon.svg
│   │
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── index.css                  # Tailwind imports + custom theme
│       │
│       ├── components/
│       │   ├── layout/
│       │   │   ├── Sidebar.tsx
│       │   │   ├── Header.tsx
│       │   │   └── Layout.tsx
│       │   ├── dashboard/
│       │   │   ├── PortfolioCard.tsx
│       │   │   ├── RegimeBadge.tsx
│       │   │   ├── RecentActivity.tsx
│       │   │   ├── AutoApproveToggle.tsx
│       │   │   └── PositionsTable.tsx
│       │   ├── agents/
│       │   │   ├── PipelineTimeline.tsx
│       │   │   ├── AgentCard.tsx
│       │   │   └── ReasoningExpander.tsx
│       │   ├── portfolio/
│       │   │   ├── AllocationChart.tsx
│       │   │   ├── PositionDetail.tsx
│       │   │   └── TradeHistory.tsx
│       │   ├── approvals/
│       │   │   ├── ApprovalCard.tsx
│       │   │   └── ApprovalQueue.tsx
│       │   ├── news/
│       │   │   ├── NewsFeed.tsx
│       │   │   ├── SentimentChart.tsx
│       │   │   ├── TendieBotPanel.tsx
│       │   │   └── HypeAlert.tsx
│       │   ├── analytics/
│       │   │   ├── EquityCurve.tsx
│       │   │   ├── WinRateCard.tsx
│       │   │   └── AgentAccuracy.tsx
│       │   └── shared/
│       │       ├── SparkLine.tsx
│       │       ├── PriceChange.tsx
│       │       ├── ConfidenceBadge.tsx
│       │       └── LoadingState.tsx
│       │
│       ├── pages/
│       │   ├── Dashboard.tsx
│       │   ├── AgentActivity.tsx
│       │   ├── Portfolio.tsx
│       │   ├── Approvals.tsx
│       │   ├── NewsSentiment.tsx
│       │   ├── Analytics.tsx
│       │   └── Settings.tsx
│       │
│       ├── hooks/
│       │   ├── useWebSocket.ts
│       │   ├── usePortfolio.ts
│       │   └── useApprovals.ts
│       │
│       ├── api/
│       │   └── client.ts              # TanStack Query + fetch wrapper
│       │
│       └── lib/
│           ├── types.ts               # TypeScript types matching backend schemas
│           ├── constants.ts
│           └── utils.ts
│
└── scripts/
    ├── init_watchlist.py              # Seed initial watchlist tickers
    └── test_connections.py            # Verify all API keys and connections work
```

## Implementation Phases

### Phase 1: Foundation
**Goal:** Docker Compose running with FastAPI + PostgreSQL + React shell. All API connections verified.

- Set up Docker Compose with three services (backend, frontend, db)
- Implement `config.py` with pydantic-settings loading from `.env`
- Set up SQLAlchemy models and Alembic migrations
- Implement all four data clients (Alpaca, Finnhub, Alpha Vantage, FMP) with basic connectivity tests
- Create `test_connections.py` script that verifies all API keys work
- Set up React app with Vite, Tailwind, routing, and the sidebar layout shell
- Implement dark theme with the specified color palette and typography

### Phase 2: Agent Pipeline
**Goal:** Full agent pipeline running end-to-end, producing structured decisions, logged to database.

- Implement `BaseAgent` class with Anthropic client, Instructor integration, retry logic, and logging
- Build each agent (Regime Analyst, Bull, Bear, Researcher, Portfolio Manager, Degen) with prompt templates
- Implement `aggregator.py` — builds `MarketContext` from all data sources
- Implement `pipeline.py` — orchestrates the sequential agent flow
- Write Pydantic schemas for all agent inputs/outputs
- Log every agent interaction (full prompt + response + parsed output) to database
- Test pipeline end-to-end with real market data (no execution yet)

### Phase 3: Execution Engine
**Goal:** Trades can be proposed, approved, and executed via Alpaca paper trading.

- Implement `risk_manager.py` — position limits, circuit breakers, confidence gates
- Implement `wash_sale_tracker.py` — tracking, flagging, year-end blocking
- Implement `engine.py` — Alpaca order submission with proper error handling
- Implement `approval_queue.py` — pending trade management
- Wire pipeline output → risk check → approval queue or auto-execute
- Implement Apprise notification integration
- Test full flow: pipeline → decision → risk check → paper trade execution

### Phase 4: Web UI
**Goal:** Polished, functional dashboard with all views implemented.

- Build Dashboard page with portfolio cards, regime badge, positions, activity feed
- Build Agent Activity page with timeline and expandable reasoning
- Build Portfolio page with allocation charts and trade history
- Build Approval Queue page with approve/reject functionality
- Build News & Sentiment page with feed and sentiment charts
- Build Analytics page with equity curve and performance metrics
- Build Settings page with watchlist management and config
- Implement WebSocket connection for real-time updates
- Polish: animations, loading states, responsive design, micro-interactions

### Phase 5: Scheduling & Integration
**Goal:** System runs autonomously on schedule, notifications working, full loop closed.

- Implement APScheduler with all scheduled jobs
- Wire up news polling with threshold-based pipeline triggering
- Implement daily summary generation and notification
- Implement portfolio snapshot recording for equity curve tracking
- End-to-end test: system runs for a full trading day on paper trading
- Monitor logs, fix edge cases, tune prompts based on observed behavior

### Phase 6: Paper Trading Burn-in
**Goal:** Run on paper trading for 2+ weeks, tune, stabilize.

- Deploy to homelab Docker environment
- Monitor daily, review agent reasoning
- Tune agent prompts based on observed decision quality
- Fix any scheduling, data, or execution edge cases
- Track performance vs SPY benchmark
- Adjust risk parameters if needed

### Phase 7: Go Live
**Goal:** Switch to live trading with real $100.

- Set `ALPACA_PAPER=false` in `.env`
- Fund Alpaca account with $100
- Start with auto-approve OFF for at least one week
- Monitor closely, approve trades manually
- Gradually increase autonomy as confidence builds

## Key Development Guidelines for Claude Code

- **Always use Pydantic v2** for all data validation and serialization
- **Always use `instructor`** library for LLM structured output enforcement
- **Never put risk management logic in LLM prompts** — enforce in Python code
- **Log everything** — every API call, every agent interaction, every order, every error
- **Handle errors gracefully** — API failures should trigger notifications, not crashes
- **Use async/await** throughout the FastAPI backend for non-blocking I/O
- **Type everything** — full type hints in Python, full TypeScript types in frontend
- **Test API connections on startup** — fail fast with clear error messages if keys are bad
- **Use WebSockets** for real-time UI updates (trade executions, pipeline status)
- **Rate limit awareness** — implement backoff and retry logic for all external API calls
- **Never store API keys in code** — everything via `.env` and pydantic-settings
