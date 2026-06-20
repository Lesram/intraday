"""Edge experiments 3.1 (exit logic) + 3.2 (chop stand-down).

Audit 2026-06-09 plan, Phase 3. Runs the REAL organism engine (via
ReplayEngine, costed fills) over cached minute bars under different
configurations, each arm in a SUBPROCESS so import-time env constants
take effect.

Arms:
  baseline        — production defaults
  wide_exits      — 3.1: wider stops/trails + longer holds (live data:
                    active exits −$1,115 vs passive +$739; 63% MFE giveback)
  chop_standdown  — 3.2: bad-regime filter widened to all alpha-family
                    sources (live data: 364 chop trades ≈ $0 gross)
  combined        — both

Usage:
  python scripts/edge_experiments.py                 # full run, all arms
  python scripts/edge_experiments.py --max-ticks 200 # smoke run
  python scripts/edge_experiments.py --arm baseline  # (internal) one arm

Bars are loaded from artifacts/**/bars*.pkl (pandas>=3 pickles supported
via a compatibility shim). Results land in
artifacts/edge_experiments_<UTCdate>/report.json.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import pickle
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

ARMS: dict[str, dict[str, str]] = {
    "baseline": {},
    "wide_exits": {
        "ORGANISM_EXIT_ATR_MULT": "2.0",
        "ORGANISM_EXIT_TRAIL_START_ATR": "3.0",
        "ORGANISM_EXIT_TRAIL_DIST_ATR": "2.5",
        "ORGANISM_EXIT_MAX_BARS": "120",
        "ORGANISM_EXIT_DECAY_START": "90",
    },
    "chop_standdown": {
        "ORGANISM_BAD_REGIME_FILTER_SOURCES": "alpha,alpha+breakout,breakout",
    },
    "combined": {
        "ORGANISM_EXIT_ATR_MULT": "2.0",
        "ORGANISM_EXIT_TRAIL_START_ATR": "3.0",
        "ORGANISM_EXIT_TRAIL_DIST_ATR": "2.5",
        "ORGANISM_EXIT_MAX_BARS": "120",
        "ORGANISM_EXIT_DECAY_START": "90",
        "ORGANISM_BAD_REGIME_FILTER_SOURCES": "alpha,alpha+breakout,breakout",
    },
    # §8.2 structural exit policies (AltExitEngine, swapped in for replay only).
    "time_only": {
        "ORGANISM_EXIT_POLICY": "time_only",
        "ORGANISM_ALT_DISASTER_PCT": "0.05",
        "ORGANISM_ALT_TIME_CAP_BARS": "120",
    },
    "retracement": {
        "ORGANISM_EXIT_POLICY": "retracement",
        "ORGANISM_ALT_RETRACE_FRAC": "0.5",
        "ORGANISM_ALT_MIN_FAVORABLE_R": "0.5",
        "ORGANISM_ALT_DISASTER_PCT": "0.05",
        "ORGANISM_ALT_TIME_CAP_BARS": "120",
    },
}


# ── pandas>=3 pickle compatibility (cached bars were written by pandas 3.x) ──

def _load_bars_pickle(path: str):
    from pandas._libs.arrays import NDArrayBacked
    from pandas.core.arrays.string_ import StringArray

    class CompatString(StringArray):
        def __init__(self, *a, **k):  # noqa: D401
            pass

        def __setstate__(self, state):
            arr = None
            if isinstance(state, tuple):
                for s in state:
                    if isinstance(s, np.ndarray):
                        arr = s
            elif isinstance(state, dict):
                arr = state.get("_ndarray")
            NDArrayBacked.__init__(
                self, np.asarray(arr, dtype=object), pd.StringDtype()
            )

    def _shim(typ, checksum, state):
        obj = CompatString.__new__(CompatString)
        if state is not None:
            obj.__setstate__(state)
        return obj

    class U(pickle.Unpickler):
        def find_class(self, module, name):
            if module == "pandas._libs.arrays" and name.startswith("__pyx_unpickle"):
                return _shim
            return super().find_class(module, name)

    try:
        with open(path, "rb") as fh:
            return U(fh).load()
    except Exception:
        return None


def collect_cached_bars() -> dict[str, pd.DataFrame]:
    """Merge all cached symbol-day minute bars into continuous per-symbol
    frames (deduped by symbol+date, chronological)."""
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    for p in sorted(glob.glob(str(ROOT / "artifacts/**/bars*.pkl"), recursive=True)):
        b = _load_bars_pickle(p)
        if not isinstance(b, dict):
            continue
        for sym, df in b.items():
            if not isinstance(df, pd.DataFrame) or "close" not in df.columns:
                continue
            df = df.copy()
            df["timestamp"] = df["timestamp"].astype(str)
            ts = pd.to_datetime(df["timestamp"], utc=True)
            for date, day in df.groupby(ts.dt.tz_convert("America/New_York").dt.date):
                key = (sym, str(date))
                if key not in frames or len(day) > len(frames[key]):
                    frames[key] = day

    merged: dict[str, list[pd.DataFrame]] = {}
    for (sym, _date), day in sorted(frames.items()):
        merged.setdefault(sym, []).append(day)
    out = {
        sym: pd.concat(days, ignore_index=True).sort_values("timestamp")
        .reset_index(drop=True)
        for sym, days in merged.items()
    }
    # ReplayEngine's bar cursor is bounded by the SHORTEST symbol frame
    # (min(len(df))), so one thinly-cached symbol throttles every arm to
    # a handful of ticks (observed: COIN at 441 bars capped a ~15k-bar
    # corpus to 111 ticks, 0 trades). Drop outlier-thin symbols rather
    # than let them define the replay horizon.
    if out:
        counts = sorted(len(df) for df in out.values())
        median = counts[len(counts) // 2]
        min_rows = max(1000, int(0.25 * median))
        dropped = {s: len(df) for s, df in out.items() if len(df) < min_rows}
        if dropped:
            print(
                f"collect_cached_bars: dropping thin symbols (<{min_rows} "
                f"bars, median={median}): {dropped}",
                flush=True,
            )
            out = {s: df for s, df in out.items() if s not in dropped}
    return out


# ── single arm (runs in subprocess with arm env applied) ────────────────────

def _trade_history_metrics(brain_dir: str) -> dict:
    """Real per-trade metrics from the engine's persisted TradeRecords.

    result.trades (broker.trade_log) carries only symbol/side/qty/price/pnl —
    no exit_reason or mfe — so read the trade_history.csv the engine wrote into
    this arm's brain_dir to get the real exit mix and MFE-giveback.
    """
    paths = glob.glob(os.path.join(brain_dir, "**", "trade_history.csv"), recursive=True)
    if not paths:
        return {"th_found": False}
    try:
        df = pd.read_csv(max(paths, key=os.path.getsize))
    except Exception as e:
        return {"th_found": False, "th_error": str(e)}
    if "is_reconciliation_artifact" in df.columns:
        df = df[~df["is_reconciliation_artifact"].astype(str).str.lower().isin(["true", "1"])]
    if "pnl" not in df.columns:
        return {"th_found": True, "th_n_trades": int(len(df))}
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce")
    if "mfe" in df.columns:
        df["mfe"] = pd.to_numeric(df["mfe"], errors="coerce")
    df = df.dropna(subset=["pnl"])
    n = len(df)
    if n == 0:
        return {"th_found": True, "th_n_trades": 0}
    pnl = df["pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gl = float(abs(losses.sum()))
    out = {
        "th_found": True,
        "th_n_trades": int(n),
        "th_net_pnl": round(float(pnl.sum()), 2),
        "th_expectancy": round(float(pnl.mean()), 4),
        "th_win_rate": round(float((pnl > 0).mean()), 4),
        "th_profit_factor": round(float(wins.sum()) / gl, 4) if gl > 0 else None,
    }
    if "exit_reason" in df.columns:
        g = df.groupby("exit_reason")["pnl"].agg(["size", "sum"]).sort_values("sum")
        out["th_pnl_by_exit_reason"] = {
            str(k): {"n": int(r["size"]), "pnl": round(float(r["sum"]), 2)}
            for k, r in g.iterrows()
        }
    if "mfe" in df.columns:
        pos = df[df["mfe"] > 0]
        if len(pos):
            out["th_mfe_giveback"] = {
                "pos_mfe_trades": int(len(pos)),
                "closed_le_0": int((pos["pnl"] <= 0).sum()),
                "sum_mfe": round(float(pos["mfe"].sum()), 2),
                "realized": round(float(pos["pnl"].sum()), 2),
                "given_back": round(float((pos["mfe"] - pos["pnl"]).sum()), 2),
            }
    return out


async def run_arm(arm: str, max_ticks: int | None, out_path: str) -> None:
    sys.path.insert(0, str(ROOT))
    from backend.organism.replay_simulator import ReplayEngine

    # §8.2 structural arms: swap the exit policy for replay ONLY (no live-path
    # edits). Gated on the arm's env; rebinding the module global makes the
    # engine build an AltExitEngine for its self.exit_engine on construction.
    if os.getenv("ORGANISM_EXIT_POLICY"):
        import backend.organism.live_engine as _le
        from backend.organism.experimental.alt_exit_engine import AltExitEngine
        _le.AdaptiveExitEngine = AltExitEngine

    bars = collect_cached_bars()
    if not bars:
        Path(out_path).write_text(json.dumps({"error": "no cached bars found"}))
        return

    bdir = tempfile.mkdtemp(prefix=f"edge_exp_{arm}_")
    engine = ReplayEngine(
        bars_by_symbol=bars,
        timeframe="1Min",
        cost_profile="realistic",
        slippage_bps=1.0,
        brain_dir=bdir,
    )
    result = await engine.run(max_ticks=max_ticks)

    pnls = [float(t.get("pnl", 0)) for t in result.trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_loss = abs(sum(losses))

    payload = {
        "arm": arm,
        "env": ARMS[arm],
        "ticks": result.ticks,
        "n_trades": len(pnls),
        "total_pnl": round(sum(pnls), 4),
        "expectancy": round(sum(pnls) / len(pnls), 6) if pnls else None,
        "win_rate": round(len(wins) / len(pnls), 4) if pnls else None,
        "profit_factor": (
            round(sum(wins) / gross_loss, 4) if gross_loss > 0 else None
        ),
        "max_drawdown": round(result.max_drawdown, 6),
        "final_equity": result.equity_curve[-1] if result.equity_curve else None,
        "n_symbols": len(bars),
    }
    # Real exit_reason / MFE-giveback metrics from persisted TradeRecords.
    payload.update(_trade_history_metrics(bdir))
    Path(out_path).write_text(json.dumps(payload, indent=1))


# ── orchestrator ─────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default=None, help="(internal) run a single arm")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-ticks", type=int, default=None)
    ap.add_argument("--arms", default=",".join(ARMS))
    args = ap.parse_args()

    if args.arm:  # child mode
        asyncio.run(run_arm(args.arm, args.max_ticks, args.out))
        return

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = ROOT / "artifacts" / f"edge_experiments_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
        out_path = out_dir / f"{arm}.json"
        env = dict(os.environ)
        env.update(ARMS[arm])
        env["ORGANISM_REPLAY_MODE"] = "1"
        cmd = [sys.executable, __file__, "--arm", arm, "--out", str(out_path)]
        if args.max_ticks:
            cmd += ["--max-ticks", str(args.max_ticks)]
        print(f"=== running arm: {arm} ===", flush=True)
        subprocess.run(cmd, env=env, cwd=str(ROOT), check=False)
        if out_path.is_file():
            results[arm] = json.loads(out_path.read_text())
            print(json.dumps(results[arm], indent=1)[:400], flush=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_ticks": args.max_ticks,
        "arms": results,
    }
    if "baseline" in results and results["baseline"].get("n_trades"):
        base = results["baseline"]
        report["deltas_vs_baseline"] = {
            arm: {
                "d_total_pnl": round(
                    (r.get("total_pnl") or 0) - (base.get("total_pnl") or 0), 4
                ),
                "d_trades": (r.get("n_trades") or 0) - (base.get("n_trades") or 0),
            }
            for arm, r in results.items() if arm != "baseline"
        }
    (out_dir / "report.json").write_text(json.dumps(report, indent=1))
    print(f"\nReport: {out_dir / 'report.json'}")


if __name__ == "__main__":
    main()
