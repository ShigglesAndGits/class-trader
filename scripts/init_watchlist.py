"""
Seed script — initialize the watchlist with starter tickers.

Run inside the backend container after docker-compose up:
    docker exec class-trader-backend-1 python scripts/init_watchlist.py

Or locally with a DATABASE_URL pointing to the running Postgres container:
    DATABASE_URL=postgresql+asyncpg://classtrader:yourpassword@localhost:5432/class_trader \
        python scripts/init_watchlist.py

Re-running is safe — existing rows are skipped via ON CONFLICT DO NOTHING.
"""

import asyncio
import os
import sys
from pathlib import Path

# Allow running from the project root or scripts/ directory
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

MAIN_SLEEVE_TICKERS = [
    # Large-cap tech (high liquidity, strong news coverage)
    {"ticker": "AAPL", "notes": "Apple — mega cap, strong ecosystem moat"},
    {"ticker": "MSFT", "notes": "Microsoft — AI/cloud leader"},
    {"ticker": "NVDA", "notes": "NVIDIA — GPU/AI hardware dominance"},
    {"ticker": "GOOGL", "notes": "Alphabet — search/cloud/AI"},
    {"ticker": "AMZN", "notes": "Amazon — e-commerce/cloud"},
    {"ticker": "META", "notes": "Meta — social/advertising/AI"},
    # Sector diversification
    {"ticker": "JPM", "notes": "JPMorgan — banking bellwether"},
    {"ticker": "UNH", "notes": "UnitedHealth — healthcare leader"},
    {"ticker": "XOM", "notes": "Exxon — energy sector proxy"},
    {"ticker": "COST", "notes": "Costco — consumer defensive"},
]

BENCHMARK_TICKERS = [
    # Used for regime analysis — not traded
    {"ticker": "SPY", "notes": "S&P 500 ETF — benchmark"},
    {"ticker": "QQQ", "notes": "Nasdaq 100 ETF — tech benchmark"},
    {"ticker": "IWM", "notes": "Russell 2000 ETF — small cap benchmark"},
]

PENNY_SLEEVE_TICKERS = [
    # Review before deploying — prices change quickly.
    # The Degen agent will help surface better candidates dynamically.
    {"ticker": "SOFI", "notes": "SoFi Technologies — fintech"},
    {"ticker": "NIO", "notes": "NIO — EV manufacturer"},
    {"ticker": "RIVN", "notes": "Rivian — EV startup"},
    {"ticker": "DNA", "notes": "Ginkgo Bioworks — synthetic biology"},
    {"ticker": "SOUN", "notes": "SoundHound AI — voice AI"},
]


async def seed_watchlist() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://classtrader:password@localhost:5432/class_trader",
    )

    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Raw SQL with ON CONFLICT avoids pulling in the full app config stack.
    insert_sql = text("""
        INSERT INTO watchlist (ticker, sleeve, notes, is_active)
        VALUES (:ticker, :sleeve, :notes, true)
        ON CONFLICT ON CONSTRAINT uq_watchlist_ticker_sleeve DO NOTHING
    """)

    all_entries = (
        [{"ticker": t["ticker"], "sleeve": "MAIN", "notes": t["notes"]} for t in MAIN_SLEEVE_TICKERS]
        + [{"ticker": t["ticker"], "sleeve": "BENCHMARK", "notes": t["notes"]} for t in BENCHMARK_TICKERS]
        + [{"ticker": t["ticker"], "sleeve": "PENNY", "notes": t["notes"]} for t in PENNY_SLEEVE_TICKERS]
    )

    inserted = 0
    skipped = 0

    async with async_session() as session:
        for entry in all_entries:
            result = await session.execute(insert_sql, entry)
            if result.rowcount > 0:
                inserted += 1
                print(f"  + {entry['ticker']:6s} ({entry['sleeve']})")
            else:
                skipped += 1
                print(f"  · {entry['ticker']:6s} ({entry['sleeve']}) — already exists")
        await session.commit()

    await engine.dispose()

    print(f"\nDone. {inserted} inserted, {skipped} skipped.")
    if inserted == 0 and skipped > 0:
        print("Watchlist already seeded.")


if __name__ == "__main__":
    print("=" * 60)
    print("CLASS TRADER — Watchlist Seed")
    print("=" * 60)
    print()
    asyncio.run(seed_watchlist())
