"""Offline profiling of the real feeder, with synthetic streaming bars only.

Run through the repository's network-denied test harness. This does not build
an engine/brain, load models, evaluate decisions, or connect to any service.
The only replacements are transport, historical input and position inventory.
"""

from __future__ import annotations

import argparse
import asyncio
import cProfile
from contextlib import nullcontext
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import pstats
import statistics
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = (
    "backend/organism/live_engine.py",
    "backend/organism/live_engine_data.py",
    "backend/organism/streaming_data_provider.py",
    "backend/organism/ml_features.py",
    "backend/organism/multi_timeframe.py",
    "backend/organism/feature_store.py",
    "backend/organism/pipeline_diagnostics.py",
    "backend/features/feature_engineering.py",
    "scripts/diagnostics/profile_paper_pipeline.py",
)
LAST_BAR = pd.Timestamp("2026-09-24T19:59:00Z")


def require_offline() -> None:
    """Refuse accidental use before importing any platform modules."""
    for key in ("TESTING", "USE_MOCK_DATA", "USE_MOCK_BROKER"):
        if os.environ.get(key, "").lower() != "true":
            raise ValueError("Offline profiling requires explicit test isolation")
    if os.environ.get("ORGANISM_LIVE_TIMEFRAME") != "1Min":
        raise ValueError("Offline profiling requires explicit 1Min configuration")


def source_hashes() -> dict[str, str]:
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCE_FILES}


def synthetic_bars(index: int, rows: int) -> pd.DataFrame:
    """Deterministic causal prefix: adding future rows cannot change old rows."""
    steps = np.arange(rows, dtype=float)
    close = 100 + index * 0.7 + steps * 0.017 + np.sin(steps / 7 + index) * 0.3
    return pd.DataFrame({
        "timestamp": pd.date_range(LAST_BAR - pd.Timedelta(minutes=499), periods=rows, freq="min"),
        "open": close - 0.03,
        "high": close + 0.14,
        "low": close - 0.12,
        "close": close,
        "volume": (10000 + steps * 13 + index * 101).astype(int),
    })


def frame_hash(frame: pd.DataFrame) -> str:
    metadata = json.dumps({"columns": list(frame.columns), "dtypes": [str(t) for t in frame.dtypes]},
                          sort_keys=True).encode()
    return hashlib.sha256(metadata + pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()


class MemoryTransport:
    """Only transport is replaced; provider lifecycle/buffering is production code."""

    def __init__(self, **_kwargs):
        self.is_authenticated = True
        self.bar_subscriptions = {"1Min": set()}
        self.quote_subscriptions = set()

    async def connect(self):
        return True

    async def disconnect(self):
        self.is_authenticated = False

    async def subscribe_bars(self, symbols):
        self.bar_subscriptions["1Min"].update(symbols)
        return True

    async def subscribe_quotes(self, symbols):
        self.quote_subscriptions.update(symbols)
        return True


class SyntheticHistory:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    async def get_historical_bars_df(self, symbol, *, lookback, timeframe):
        if timeframe != "1Min":
            raise AssertionError("Synthetic history must be requested as 1Min")
        self.calls.append(symbol)
        return self.frames[symbol].tail(lookback).copy(deep=True)


class ForbiddenFallback:
    def __init__(self):
        self.calls = 0

    async def get_historical_bars_df(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("Streaming-only profile attempted REST fallback")


class StageMeasurements:
    """Thread-local profiles; event-loop-only cProfile misses this worker work."""

    def __init__(self, profile: bool):
        self.profile = profile
        self.calls = []
        self.profiles = {}
        self.lock = threading.Lock()
        # Python 3.12 cProfile reserves one interpreter-wide monitoring ID.
        # Only the separately labelled diagnostic pass runs functions inline;
        # timed passes preserve the feeder's original ten-symbol concurrency.
        self.profile_lock = threading.Lock()

    def wrap(self, name, function):
        def measured(*args, **kwargs):
            if self.profile:
                self.profile_lock.acquire()
            profiler = cProfile.Profile(timer=time.thread_time) if self.profile else None
            wall, cpu = time.perf_counter(), time.thread_time()
            try:
                if profiler:
                    profiler.enable()
                return function(*args, **kwargs)
            finally:
                if profiler:
                    profiler.disable()
                item = {"stage": name, "wall_seconds": time.perf_counter() - wall,
                        "thread_cpu_seconds": time.thread_time() - cpu,
                        "worker_thread": threading.get_ident()}
                with self.lock:
                    self.calls.append(item)
                    if profiler:
                        self.profiles.setdefault(name, []).append(profiler)
                if self.profile:
                    self.profile_lock.release()
        return measured

    def summary(self):
        stages = {}
        for name in sorted({c["stage"] for c in self.calls}):
            calls = [c for c in self.calls if c["stage"] == name]
            stage = {"calls": len(calls),
                     "summed_thread_cpu_seconds": sum(c["thread_cpu_seconds"] for c in calls),
                     "summed_call_wall_seconds": sum(c["wall_seconds"] for c in calls),
                     "worker_threads": len({c["worker_thread"] for c in calls})}
            if name in self.profiles:
                stats = pstats.Stats(*self.profiles[name])
                rows = [{"file": str(Path(key[0]).relative_to(ROOT)) if key[0].startswith(str(ROOT) + "/") else key[0],
                         "line": key[1], "function": key[2], "primitive_calls": value[0],
                         "calls": value[1], "own_cpu_seconds": value[2], "cumulative_cpu_seconds": value[3]}
                        for key, value in stats.stats.items()]
                stage["top_cumulative_cpu"] = sorted(rows, key=lambda v: v["cumulative_cpu_seconds"], reverse=True)[:20]
                stage["top_own_cpu"] = sorted(rows, key=lambda v: v["own_cpu_seconds"], reverse=True)[:20]
            stages[name] = stage
        return stages


async def measure_load(symbol_count: int, rows: int, repeats: int, *, profiles: bool,
                       feature_store: bool, held_symbol: bool = False) -> dict:
    require_offline()
    from backend.organism import live_engine, ml_features, multi_timeframe
    from backend.features.feature_engineering import TALIB_AVAILABLE
    from backend.organism.feature_store import VersionedFeatureStore
    from backend.organism.live_engine_data import _DataFeederMixin
    from backend.organism.streaming_data_provider import StreamingDataProvider

    if live_engine.LIVE_TIMEFRAME != "1Min" or live_engine.LIVE_LOOKBACK != rows:
        raise ValueError("Imported engine constants do not match the profile configuration")
    if rows < live_engine.MIN_BARS:
        raise ValueError("Synthetic history is shorter than the real minimum")
    symbols = ["SPY", *[f"SYN{i:03d}" for i in range(1, symbol_count)]]
    requested = [*symbols, *(["HELD"] if held_symbol else [])]
    frames = {symbol: synthetic_bars(i, rows) for i, symbol in enumerate(requested)}
    # The fixed clock is 15 seconds after the last causal bar, independently of CPU duration.
    clock = frames["SPY"]["timestamp"].iloc[-1].timestamp() + 15
    history, fallback = SyntheticHistory(frames), ForbiddenFallback()
    provider = StreamingDataProvider(time_fn=lambda: clock)
    store = VersionedFeatureStore() if feature_store else None

    async def inline_diagnostic(function, *args, **kwargs):
        # cProfile 3.12 observes cross-thread events even with serialized
        # profilers. Keep its diagnostic-only call tree on one clock/thread.
        return function(*args, **kwargs)

    async def positions():
        return {"HELD": {"qty": 1}} if held_symbol else {}

    engine = _DataFeederMixin()
    engine._streaming_provider = provider
    engine._feature_store = store
    engine._bars_per_day = 390
    engine._universe = symbols
    engine._positions_service = SimpleNamespace(get_all_positions=positions)
    engine._data_client = fallback
    input_hashes = {s: frame_hash(df) for s, df in frames.items()}
    passes = []
    with patch("backend.organism.streaming_data_provider.AlpacaMarketDataStream", MemoryTransport):
        await provider.start(requested, "synthetic-only", "synthetic-only", feed="iex", data_client=history)
        try:
            if not provider.is_running or provider.stale_symbols(120):
                raise AssertionError("Synthetic streaming prefill was not complete/fresh")
            for number in range(repeats + int(profiles)):
                profiled = number == repeats
                measurements = StageMeasurements(profiled)
                with patch.object(ml_features, "compute_ml_features", measurements.wrap("ml_features", ml_features.compute_ml_features)), \
                     patch.object(multi_timeframe, "add_multi_timeframe_features", measurements.wrap("multi_timeframe", multi_timeframe.add_multi_timeframe_features)), \
                     patch.object(VersionedFeatureStore, "compute_features", measurements.wrap("feature_store", VersionedFeatureStore.compute_features)), \
                     (patch.object(asyncio, "to_thread", inline_diagnostic) if profiled else nullcontext()):
                    wall, cpu = time.perf_counter(), time.process_time()
                    result = await engine._fetch_and_compute_features()
                    elapsed, process_cpu = time.perf_counter() - wall, time.process_time() - cpu
                if set(result) != set(requested) or fallback.calls:
                    raise AssertionError("Missing feature outputs or forbidden fallback; timings are not qualified")
                hashes = {s: frame_hash(df) for s, df in result.items()}
                if passes and hashes != passes[0]["output_hashes"]:
                    raise AssertionError("Unchanged bars produced different features")
                passes.append({"kind": "profiled" if profiled else "timed", "iteration": number,
                               "wall_seconds": elapsed, "process_cpu_seconds": process_cpu,
                               "feature_output_count": len(result), "output_hashes": hashes,
                               "output_rows": {s: len(df) for s, df in result.items()},
                               "output_columns": {s: len(df.columns) for s, df in result.items()},
                               "stages": measurements.summary()})
                print(json.dumps({"universe": symbol_count, "pass_kind": passes[-1]["kind"],
                                  "iteration": number, "elapsed_seconds": round(elapsed, 3)}), flush=True)
        finally:
            await provider.stop()
    if input_hashes != {s: frame_hash(df) for s, df in frames.items()}:
        raise AssertionError("Feature computation mutated synthetic input")
    timed = [p for p in passes if p["kind"] == "timed"]
    return {"universe_count": symbol_count, "held_only_count": int(held_symbol),
            "synthetic_input_hashes": input_hashes, "history_prefill_calls": history.calls,
            "rest_fallback_calls": fallback.calls, "input_unchanged": True, "outputs_identical": True,
            "feature_store_enabled": feature_store,
            "feature_store_config": store._config if store else None,
            "feature_store_config_hash": store.config_hash if store else None,
            "feature_engineer_resolved_config": store._engineer.config if store else None,
            "ta_lib_available": TALIB_AVAILABLE,
            "passes": passes, "median_timed_wall_seconds": statistics.median(p["wall_seconds"] for p in timed),
            "median_timed_process_cpu_seconds": statistics.median(p["process_cpu_seconds"] for p in timed)}


async def experiment(args) -> dict:
    require_offline()
    before = source_hashes()
    runs = [await measure_load(count, args.rows, args.repeats, profiles=args.profile,
                               feature_store=not args.no_feature_store, held_symbol=args.held_symbol)
            for count in args.loads]
    after = source_hashes()
    if before != after:
        raise RuntimeError("Profiled source changed during measurement; discard timing comparison")
    return {"schema": "intra_synthetic_pipeline_profile_v1", "observed_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "source_files_sha256": before, "source_unchanged_during_run": True,
            "configuration": {"loads": args.loads, "rows": args.rows, "timeframe": "1Min", "bars_per_day": 390,
                              "repeats": args.repeats, "profiled_extra_pass": args.profile,
                              "feed_argument_to_fake_transport": "iex", "max_concurrent_symbols": 10,
                              "minimum_bars": int(os.environ["ORGANISM_MIN_BARS"]),
                              "synthetic_clock": "15 seconds after each last bar; fixed throughout measurement",
                              "thread_pool": "asyncio default executor; not replaced",
                              "profile_clock": "time.thread_time (CPU of actual worker thread)"},
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "logical_cpus": os.cpu_count(), "numpy": np.__version__, "pandas": pd.__version__,
                            "scikit_learn": importlib.metadata.version("scikit-learn")},
            "runs": runs,
            "limitations": ["Synthetic 500-row continuous-minute data does not reproduce exchange sessions, sparse IEX delivery or live symbol distributions.",
                            "Measures feature acquisition/computation only; no decision, ranking, sizing, model inference, entry/exit, broker, database or persistence workload.",
                            "No engine/brain instance or model deserialization; VersionedFeatureStore computes real features without a DB session.",
                            "Timed passes include small stage counter/clock overhead. Profiled passes have substantial cProfile overhead and are not latency estimates.",
                            "The extra profile pass executes measured functions inline on one thread because Python 3.12 cProfile has interpreter-wide monitoring; timed passes retain original worker-thread concurrency.",
                            "Summed overlapping call wall times are not elapsed pipeline time; cumulative function CPU rows overlap and must not be added.",
                            "Fixed fresh synthetic clock excludes aging while CPU is busy; this cannot qualify live freshness or safe entry admission.",
                            "Concurrent machine load and local Python/library versions affect results; no live equivalence or profit claim."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loads", type=int, nargs="+", default=[20, 69])
    parser.add_argument("--rows", type=int, default=500)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--no-feature-store", action="store_true")
    parser.add_argument("--held-symbol", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not all(1 <= n <= 100 for n in args.loads) or not 50 <= args.rows <= 500 or not 1 <= args.repeats <= 5:
        parser.error("Use 1–100 symbols, 50–500 bars and 1–5 repeats")
    require_offline()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing profiling receipt")
    report = asyncio.run(experiment(args))
    with args.output.open("x") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), "loads": args.loads,
                      "median_seconds": [r["median_timed_wall_seconds"] for r in report["runs"]]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
