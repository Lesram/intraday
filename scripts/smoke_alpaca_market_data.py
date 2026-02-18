import asyncio
import os
from pathlib import Path
import sys


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        env_path = Path(".env")
        load_dotenv(env_path, override=False)
    except Exception:
        # Keep smoke test robust even if dotenv isn't present
        return


def _normalize_alpaca_env() -> None:
    # Support both naming conventions without printing secrets.
    if not os.getenv("ALPACA_API_KEY_ID") and os.getenv("ALPACA_API_KEY"):
        os.environ["ALPACA_API_KEY_ID"] = os.environ["ALPACA_API_KEY"]
    if not os.getenv("ALPACA_API_SECRET_KEY") and os.getenv("ALPACA_SECRET_KEY"):
        os.environ["ALPACA_API_SECRET_KEY"] = os.environ["ALPACA_SECRET_KEY"]


async def _run() -> int:
    _load_env()
    _normalize_alpaca_env()

    print(".env present:", Path(".env").exists())
    print("ALPACA_API_KEY_ID set:", bool(os.getenv("ALPACA_API_KEY_ID")))
    print("ALPACA_API_SECRET_KEY set:", bool(os.getenv("ALPACA_API_SECRET_KEY")))
    print("ALPACA_DATA_FEED:", os.getenv("ALPACA_DATA_FEED", "iex"))

    from backend.integrations.alpaca_data import AlpacaDataClient
    from backend.services.auto_breakout_scanner import scan_breakouts

    client = AlpacaDataClient()
    try:
        df = await client.get_historical_bars_df("AAPL", lookback=60, timeframe="1Day")
        print("Fetched AAPL bars:", len(df))
        if len(df) > 0:
            last = df.tail(1).to_dict(orient="records")[0]
            print("Last bar close:", last.get("close"), "volume:", last.get("volume"))

        scan = await scan_breakouts(
            data_client=client,
            symbols=["AAPL", "MSFT", "NVDA", "SPY"],
            timeframe="1Day",
            limit=120,
            allow_short=False,
        )
        print("Scan evaluated:", scan.evaluated, "universe_size:", scan.universe_size)
        print("Top candidates (up to 5):")
        for c in scan.candidates[:5]:
            print({"symbol": c.symbol, "score": round(c.score, 4), "direction": c.direction, "reason": c.reason})

        return 0
    except Exception as e:
        print("SMOKE TEST ERROR:", type(e).__name__, str(e)[:400])
        return 2
    finally:
        try:
            await client.client.aclose()
        except Exception:
            pass


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
