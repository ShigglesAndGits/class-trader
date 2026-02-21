# Class Trader

An LLM-driven autonomous trading platform. Built with one hand, nose firmly held with the other.

This is a $100 experiment in pragmatic capitalism: a multi-agent AI pipeline that analyzes markets, debates itself, and executes trades via Alpaca — all running locally on your own hardware. It exists not out of enthusiasm for financial markets, but because the times seem to call for it.

Open-sourced because LLMs are trained on open-source code, and closed-source LLM-assisted development is, in this author's view, theft from the commons.

---

## What It Does

A sequential agent pipeline runs on a schedule during market hours:

1. **Data Fetch** — Pulls prices (Alpaca), news/sentiment (Finnhub), technical indicators (Alpha Vantage), fundamentals (FMP), and retail sentiment from WSB/Reddit (TendieBot)
2. **Regime Analyst** — Classifies the broad market: `TRENDING_UP`, `TRENDING_DOWN`, `RANGING`, or `HIGH_VOLATILITY`
3. **Bull Agent** — Argues *for* positions, must cite specific data points
4. **Bear Agent** — Argues *against* positions, flags risks (runs in parallel with Bull)
5. **Researcher** — Fact-checks both sides, flags thesis drift and data inconsistencies
6. **Portfolio Manager** — Makes final `BUY`/`SELL`/`HOLD` decisions with position sizing
7. **Degen** *(separate pipeline)* — Penny stock specialist with its own risk parameters and a higher tolerance for chaos

All agent reasoning is logged in full. Every decision is explainable. Nothing executes without passing hard-coded risk checks that the LLM cannot override.

### Two Sleeves

| Sleeve | Allocation | Max Position | Max Positions |
|--------|-----------|--------------|---------------|
| Main | $75 | 30% of sleeve | 8 |
| Penny | $25 | $8 | 5 |

### Schedule

| Time (ET) | Action |
|-----------|--------|
| 9:35 AM Mon-Fri | Morning rebalance (full pipeline) |
| 12:00 PM Mon-Fri | Noon review (full pipeline) |
| Every 15 min | News monitor — triggers pipeline if sentiment score > 0.8 |
| Every 30 min | TendieBot Reddit crawl |
| 4:10 PM | Portfolio snapshot |
| 4:15 PM | Daily summary notification |
| Sat 2:00 AM | Wash sale cleanup, weekly report |

---

## Architecture

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
│              │ (APScheduler)                         │
│              └──────┬──────┘                         │
│                     │                                │
│         ┌───────────┼───────────┐                    │
│         ▼           ▼           ▼                    │
│   ┌──────────┐ ┌─────────┐ ┌────────┐               │
│   │  Agent   │ │  Data   │ │ Exec   │               │
│   │ Pipeline │ │ Fetcher │ │ Engine │               │
│   └──────────┘ └─────────┘ └────────┘               │
│         │                       │                    │
│         ▼                       ▼                    │
│   Anthropic API           Alpaca API                │
│   (Claude Haiku 4.5)     (Paper or Live)            │
└─────────────────────────────────────────────────────┘
```

**External data:** Alpaca · Finnhub · Alpha Vantage · FMP · Reddit
**Notifications:** Apprise (Discord, Telegram, email, Slack, etc.)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), APScheduler |
| Frontend | React 18 (Vite), TailwindCSS, Recharts, TanStack Query |
| Database | PostgreSQL 16 |
| LLM | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) via Anthropic API |
| Structured output | Pydantic v2 + Instructor |
| Broker | Alpaca Markets (alpaca-py SDK) |
| Containerization | Docker Compose |

---

## Risk Management

Hard limits enforced in Python, not in LLM prompts. The agents cannot override them.

- Minimum confidence gates (0.65 main / 0.60 penny) before any execution
- Daily loss circuit breakers (5% main / 15% penny) — halts trading automatically
- Consecutive loss pause after 3 losses in a row
- Wash sale tracking with December hard-block and adjusted cost basis
- Auto-approve constraints: new tickers, large positions, and borderline-confidence trades always require manual approval even when auto-approve is enabled

---

## Web UI

A dark-themed financial terminal dashboard with:

- **Dashboard** — Portfolio value, regime badge, positions, recent decisions, next-run countdown
- **Agent Activity** — Full pipeline timeline with expandable reasoning chains per agent
- **Portfolio** — Holdings by sleeve, allocation chart, trade history with fill details
- **Approval Queue** — Pending trades with one-tap approve/reject and bulk actions
- **News & Sentiment** — Finnhub feed + TendieBot retail sentiment panel (WSB hype scores, velocity alerts)
- **Analytics** — Equity curve vs SPY, win rate, Sharpe ratio, agent accuracy
- **Settings** — Watchlist CRUD, circuit breaker management, API status indicators

---

## Getting Started

### Prerequisites

- Docker and Docker Compose
- API keys for: Anthropic, Alpaca (paper trading to start), Finnhub, Alpha Vantage, FMP
- Reddit API credentials (optional, for TendieBot retail sentiment)
- An Apprise-compatible notification URL (optional)

### Setup

```bash
git clone https://github.com/ShigglesAndGits/class-trader.git
cd class-trader

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start the stack
docker compose up --build

# Verify connections (in another terminal)
docker exec -it class-trader-backend-1 python scripts/test_connections.py

# Seed the watchlist
docker exec -it class-trader-backend-1 python scripts/init_watchlist.py

# Check health
curl localhost:8000/health
```

Open `http://localhost:3000` — the dashboard will be waiting.

### First Run

1. Open the dashboard. Auto-approve is **off** by default.
2. Click **Run Pipeline** to trigger a manual analysis.
3. Watch the Agent Activity page fill in as each agent completes.
4. Go to the Approval Queue. Review the reasoning. Approve or reject manually.
5. Stay in manual mode for at least a week before considering auto-approve.

---

## Homelab Deployment

Pre-built images are available from a private registry. See [docker-compose.homelab.yml](docker-compose.homelab.yml) and [homelab.env.template](homelab.env.template) for deployment to a separate server.

---

## Configuration

All configuration is via `.env`. Copy `.env.example` to get started.

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `ALPACA_PAPER` | `true` | Paper trading mode. Set `false` only when ready to use real money. |
| `AUTO_APPROVE` | `false` | Auto-execute approved trades without manual review. |
| `MAIN_SLEEVE_ALLOCATION` | `75.0` | USD allocated to the main (large-cap) sleeve. |
| `PENNY_SLEEVE_ALLOCATION` | `25.0` | USD allocated to the penny stock sleeve. |
| `MIN_CONFIDENCE_MAIN` | `0.65` | Minimum agent confidence to execute a main sleeve trade. |
| `DAILY_LOSS_LIMIT_MAIN_PCT` | `5.0` | Daily loss % that triggers a circuit breaker on the main sleeve. |
| `APPRISE_URLS` | *(empty)* | Comma-separated Apprise notification URLs. |

---

## Development

```bash
# Backend tests
cd backend
pip install -e ".[dev]"
pytest

# The dev docker-compose mounts source directories for hot reload:
# backend/app → /app/app
# frontend/src → /app/src
docker compose up
```

The backend runs at `localhost:8000` with Swagger docs at `localhost:8000/docs`.
The frontend runs at `localhost:3000`.

---

## Project Status

See [STATUS.md](STATUS.md) for a detailed breakdown of what's implemented.

**Phases 1–5 are complete.** The system is fully built and ready for paper trading burn-in once API keys are configured.

---

## Disclaimer

This software does not constitute financial advice. It is an educational experiment. The market is a casino with better PR. Trade carefully, and probably index fund the bulk of your savings like a normal person.
