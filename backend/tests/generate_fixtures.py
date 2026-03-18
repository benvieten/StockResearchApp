"""
Fixture generator — run once after Phase 1 is validated.

Usage:
    python backend/tests/generate_fixtures.py AAPL

Writes real AAPL data to backend/tests/fixtures/ so tests can always
run without network access. Commit the fixture files to the repo.

Also saves agent signal fixtures after Phase 3 is validated, by running
each agent standalone and capturing its JSON output.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

# Make `backend` importable when run as a script (not via python -m)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)

AGENTS = ["fundamental", "technical", "quant", "sector", "sentiment", "synthesis"]


async def generate_data_fixtures(ticker: str) -> None:
    print(f"Generating data fixtures for {ticker}...")

    from backend.data.price import get_ohlcv, get_financials, get_company_info
    from backend.data.news import get_news
    from backend.data.reddit import get_reddit_posts
    from backend.data.stocktwits import get_stocktwits_messages

    sources = {
        "ohlcv": get_ohlcv,
        "financials": get_financials,
        "company_info": get_company_info,
        "news": get_news,
        "reddit": get_reddit_posts,
        "stocktwits": get_stocktwits_messages,
    }

    for name, fn in sources.items():
        print(f"  Fetching {name}...", end=" ")
        try:
            data = await fn(ticker)
            out_path = FIXTURES_DIR / f"{ticker}_{name}.json"
            out_path.write_text(json.dumps(data, indent=2, default=str))
            print(f"OK ({len(str(data))} chars)")
        except Exception as e:
            print(f"FAILED: {e}")


def generate_agent_fixtures(ticker: str) -> None:
    print(f"\nGenerating agent signal fixtures for {ticker}...")

    for agent in AGENTS:
        print(f"  Running {agent} agent...", end=" ")
        try:
            result = subprocess.run(
                [sys.executable, "-m", f"backend.agents.{agent}", ticker],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                print(f"FAILED (exit {result.returncode}): {result.stderr[:200]}")
                continue

            output = result.stdout.strip()
            # Strip any structlog lines that precede the JSON output
            json_start = output.find("{")
            if json_start == -1:
                print(f"No JSON found in output: {output[:200]}")
                continue
            output = output[json_start:]
            parsed = json.loads(output)
            out_path = FIXTURES_DIR / f"{ticker}_signal_{agent}.json"
            out_path.write_text(json.dumps(parsed, indent=2))
            print("OK")
        except subprocess.TimeoutExpired:
            print("TIMED OUT (>120s)")
        except json.JSONDecodeError as e:
            print(f"Invalid JSON output: {e}")
        except Exception as e:
            print(f"FAILED: {e}")


def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    mode = sys.argv[2] if len(sys.argv) > 2 else "all"

    if mode in ("all", "data"):
        asyncio.run(generate_data_fixtures(ticker))

    if mode in ("all", "agents"):
        generate_agent_fixtures(ticker)

    print(f"\nFixtures written to: {FIXTURES_DIR}")
    print("Commit these files to make tests runnable without network access.")


if __name__ == "__main__":
    main()
