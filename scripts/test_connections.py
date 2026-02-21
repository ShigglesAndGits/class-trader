"""
Connection verification script.
Tests all external API connections before deployment.

Usage:
    python scripts/test_connections.py

Expects .env to be loaded (run from project root or set env vars manually).
"""

import os
import sys


def check_env_var(name: str) -> str | None:
    val = os.getenv(name)
    if not val or val.startswith("your-") or val.startswith("sk-ant-your"):
        return None
    return val


def test_anthropic():
    print("\n[1/5] Anthropic API...", end=" ")
    key = check_env_var("ANTHROPIC_API_KEY")
    if not key:
        print("❌ ANTHROPIC_API_KEY not set")
        return False
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{"role": "user", "content": "Respond with exactly: CLASS_TRADER_OK"}],
        )
        text = response.content[0].text
        if "CLASS_TRADER_OK" in text:
            print(f"✅ Connected (model: claude-haiku-4-5)")
            return True
        else:
            print(f"⚠️  Unexpected response: {text[:50]}")
            return True  # Connection works, just unexpected output
    except Exception as e:
        print(f"❌ {e}")
        return False


def test_alpaca():
    print("[2/5] Alpaca API...", end=" ")
    key = check_env_var("ALPACA_API_KEY")
    secret = check_env_var("ALPACA_SECRET_KEY")
    if not key or not secret:
        print("❌ ALPACA_API_KEY or ALPACA_SECRET_KEY not set")
        return False
    try:
        from alpaca.trading.client import TradingClient
        paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"
        client = TradingClient(key, secret, paper=paper)
        account = client.get_account()
        print(f"✅ Connected ({'paper' if paper else 'LIVE'} — equity: ${float(account.equity):,.2f})")
        return True
    except Exception as e:
        print(f"❌ {e}")
        return False


def test_finnhub():
    print("[3/5] Finnhub API...", end=" ")
    key = check_env_var("FINNHUB_API_KEY")
    if not key:
        print("❌ FINNHUB_API_KEY not set")
        return False
    try:
        import finnhub
        client = finnhub.Client(api_key=key)
        quote = client.quote("AAPL")
        if quote.get("c", 0) > 0:
            print(f"✅ Connected (AAPL current: ${quote['c']})")
            return True
        else:
            print("⚠️  Connected but got empty quote")
            return True
    except Exception as e:
        print(f"❌ {e}")
        return False


def test_alpha_vantage():
    print("[4/5] Alpha Vantage API...", end=" ")
    key = check_env_var("ALPHA_VANTAGE_API_KEY")
    if not key:
        print("❌ ALPHA_VANTAGE_API_KEY not set")
        return False
    try:
        import requests
        url = f"https://www.alphavantage.co/query?function=RSI&symbol=AAPL&interval=daily&time_period=14&series_type=close&apikey={key}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if "Technical Analysis: RSI" in data:
            print("✅ Connected (RSI endpoint working)")
            return True
        elif "Note" in data:
            print("⚠️  Rate limited — key is valid but hit daily cap")
            return True
        else:
            print(f"⚠️  Unexpected response: {list(data.keys())[:3]}")
            return False
    except Exception as e:
        print(f"❌ {e}")
        return False


def test_fmp():
    print("[5/6] Financial Modeling Prep API...", end=" ")
    key = check_env_var("FMP_API_KEY")
    if not key:
        print("❌ FMP_API_KEY not set")
        return False
    try:
        import requests
        url = f"https://financialmodelingprep.com/api/v3/profile/AAPL?apikey={key}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if isinstance(data, list) and len(data) > 0 and "companyName" in data[0]:
            print(f"✅ Connected ({data[0]['companyName']})")
            return True
        else:
            print(f"⚠️  Unexpected response format")
            return False
    except Exception as e:
        print(f"❌ {e}")
        return False


def test_reddit():
    print("[6/6] Reddit API (TendieBot)...", end=" ")
    client_id = check_env_var("REDDIT_CLIENT_ID")
    client_secret = check_env_var("REDDIT_CLIENT_SECRET")
    user_agent = check_env_var("REDDIT_USER_AGENT")
    if not client_id or not client_secret:
        print("❌ REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET not set")
        return False
    try:
        import praw
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent or "class-trader:v0.1",
        )
        # Read-only test — fetch top post from WSB
        sub = reddit.subreddit("wallstreetbets")
        top_post = next(iter(sub.hot(limit=1)))
        print(f"✅ Connected (WSB top: \"{top_post.title[:40]}...\")")
        return True
    except Exception as e:
        print(f"❌ {e}")
        return False


if __name__ == "__main__":
    # Try to load .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not installed, rely on env vars

    print("=" * 50)
    print("CLASS TRADER — Connection Test")
    print("=" * 50)

    results = [
        test_anthropic(),
        test_alpaca(),
        test_finnhub(),
        test_alpha_vantage(),
        test_fmp(),
        test_reddit(),
    ]

    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} connections verified")

    if all(results):
        print("🚀 All systems go!")
    else:
        print("⚠️  Some connections failed. Check your .env file.")
        sys.exit(1)
