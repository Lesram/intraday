"""Pull a different ~7-day period of bars to test ORB/EOD on mixed-direction data.

The existing cache (bars.pkl) covers Apr 15-20 which was down-trending.
We pull from a different recent window to get mixed conditions for fairer
strategy evaluation.
"""
from __future__ import annotations

import asyncio
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

UNIVERSE = [
    "NVDA", "SPY", "QQQ", "XLK", "XLE", "COST", "LLY", "PSQ", "SH",
    "AAPL", "AMD", "AMZN", "AVGO", "CAT", "CRM", "GOOGL", "IWM",
    "META", "MSFT", "TSLA", "WMT", "XOM",
]

OUTPUT = Path("/Users/marselkei/VS/intra/artifacts/backtest_rc_1_5/bars_alt.pkl")


async def main() -> None:
    from backend.integrations.alpaca_data import get_alpaca_data_client

    client = get_alpaca_data_client()
    # Alpaca client doubles `lookback` internally; cap at 4500 → 9000 bars
    lookback_bars = 4500

    bars: dict = {}
    for sym in UNIVERSE:
        try:
            df = await client.get_historical_bars_df(
                symbol=sym, timeframe="1Min", lookback=lookback_bars,
            )
            if df is not None and not df.empty:
                bars[sym] = df
                print(f"  {sym}: {len(df)} bars")
            else:
                print(f"  {sym}: NO DATA")
        except Exception as e:
            print(f"  {sym}: FAILED ({e})")

    if not bars:
        raise RuntimeError("No bars loaded")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "wb") as f:
        pickle.dump(bars, f)
    print(f"\nWrote {OUTPUT}")
    sample = bars[list(bars.keys())[0]]
    if "timestamp" in sample.columns:
        print(f"Sample first ts: {sample['timestamp'].iloc[0]}")
        print(f"Sample last ts: {sample['timestamp'].iloc[-1]}")


if __name__ == "__main__":
    asyncio.run(main())
