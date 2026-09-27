"""Paired actual learning-mode replay with unequal stock/SPY warm-up history.

The only counterfactual is the old ordinal benchmark lookup. A test-only
history provider trims forty *past* stock bars; prices, clocks and the actual
engine/feeder, admission, sizing, exits and accounting remain unchanged.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from scripts.diagnostics import replay_composite_correction as replay
from tests.test_cross_asset_timestamp_alignment import CROSS, legacy_ordinal_alignment


def prepare(bars, baseline):
    from backend.organism import ml_features

    current = ml_features._cross_asset_alignment

    def legacy(a, b):
        with patch.object(ml_features, "_cross_asset_alignment", current):
            return legacy_ordinal_alignment(a, b)

    raw = {s: (f if s == "SPY" else f.iloc[40:].reset_index(drop=True)) for s, f in bars.items()}
    with patch.object(ml_features, "_cross_asset_alignment", legacy if baseline else current):
        computed = {
            s: ml_features.compute_ml_features(
                f, spy_df=raw["SPY"] if s != "SPY" else None, bars_per_day=390
            )
            for s, f in raw.items()
        }
        checks = []
        for end in (241, 270, 300):
            for symbol, frame in raw.items():
                count = end if symbol == "SPY" else end - 40
                direct = ml_features.compute_ml_features(
                    frame.iloc[:count],
                    spy_df=raw["SPY"].iloc[:end] if symbol != "SPY" else None,
                    bars_per_day=390,
                )
                pd.testing.assert_frame_equal(computed[symbol].iloc[:count], direct)
                checks.append({"symbol": symbol, "rows": count, "hash": replay.frame_hash(direct)})
        shocked = {s: f.copy() for s, f in raw.items()}
        boundary = bars["SPY"].timestamp.iloc[270]
        for frame in shocked.values():
            frame.loc[frame.timestamp >= boundary, ["open", "high", "low", "close", "volume"]] *= 10
        for s, f in shocked.items():
            future = ml_features.compute_ml_features(
                f, spy_df=shocked["SPY"] if s != "SPY" else None, bars_per_day=390
            )
            count = 270 if s == "SPY" else 230
            pd.testing.assert_frame_equal(computed[s].iloc[:count], future.iloc[:count])
    return raw, computed, checks


def prefix_factory(raw, computed, calls):
    def compute(frame, spy_df=None, bars_per_day=1):
        assert bars_per_day == 390
        matches = [
            s for s, f in raw.items() if frame.equals(f.iloc[: len(frame)].reset_index(drop=True))
        ]
        assert len(matches) == 1, "Unknown or shifted history cannot use prefix acceleration"
        symbol = matches[0]
        if symbol != "SPY":
            assert spy_df is not None and len(spy_df) == len(frame) + 40
            pd.testing.assert_frame_equal(spy_df, raw["SPY"].iloc[: len(frame) + 40])
        else:
            assert spy_df is None
        calls.append((symbol, len(frame)))
        result = computed[symbol].iloc[: len(frame)].copy(deep=True)
        # pandas slices preserve attrs verbatim; retain only actually visible
        # row metadata rather than future rows in this test-only acceleration.
        meta = deepcopy(result.attrs["cross_asset_alignment"])
        for key in ("matched", "matched_timestamps", "age_seconds"):
            meta[key] = meta[key][: len(frame)]
        meta["feature_valid"] = {k: v[: len(frame)] for k, v in meta["feature_valid"].items()}
        result.attrs["cross_asset_alignment"] = meta
        return result

    return compute


@pytest.mark.timeout(300)
@pytest.mark.parametrize("scenario", ["crash", "eod"])
def test_paired_current_learning_replay_has_real_entries_and_accounted_exits(
    scenario, record_property
):
    from backend.organism.replay_simulator import HistoricalBarProvider

    source_before = replay.source_hashes()
    # Same seeded W100 costed mechanics, with enough warm-up for shorter stocks.
    config = {**replay.CONFIG, "rows": 320, "lookback": 240}
    with patch.dict(replay.CONFIG, config):
        bars = replay.scenario_bars("up")
        start = "2026-09-22T15:36:00Z" if scenario == "eod" else "2026-09-22T10:00:00Z"
        for frame in bars.values():
            frame["timestamp"] = pd.date_range(start, periods=len(frame), freq="min")
            if scenario == "crash":
                frame.loc[280:, ["open", "high", "low", "close"]] *= 0.75
        actual_history = HistoricalBarProvider.get_historical_data

        def shorter_stock_history(provider, symbol, timeframe="1Day", limit=500):
            frame = actual_history(provider, symbol, timeframe, limit)
            return (
                frame.iloc[40:].reset_index(drop=True)
                if symbol != "SPY" and frame is not None
                else frame
            )

        results = {}
        frames = {}
        proof = {}
        for label in ("baseline_ordinal", "causal_timestamp"):
            raw, computed, checks = prepare(bars, label == "baseline_ordinal")
            frames[label] = computed
            proof[label] = checks
            with (
                patch.object(HistoricalBarProvider, "get_historical_data", shorter_stock_history),
                patch.object(
                    replay,
                    "prefix_compute",
                    lambda _bars, _computed, calls: prefix_factory(raw, computed, calls),
                ),
            ):
                # Corrected composite helper stays active in both arms; never
                # calls the old composite or any Git/source-history subprocess.
                result = asyncio.run(replay.run_arm(scenario, "corrected", bars, computed))
            result["arm"] = label
            results[label] = result
        changed = {}
        changed_executed = {}
        for symbol in replay.SYMBOLS:
            old, new = frames["baseline_ordinal"][symbol], frames["causal_timestamp"][symbol]
            pd.testing.assert_frame_equal(old.drop(columns=CROSS), new.drop(columns=CROSS))
            changed[symbol] = int((old[CROSS].iloc[200:] != new[CROSS].iloc[200:]).sum().sum())
            # Visible last rows on the actual replay ticks, not future tail
            # rows included only in the causal-prefix acceleration proof.
            first = 240 if symbol == "SPY" else 200
            tick_count = results["causal_timestamp"]["metrics"]["ticks"]
            changed_executed[symbol] = int(
                (
                    old[CROSS].iloc[first : first + tick_count]
                    != new[CROSS].iloc[first : first + tick_count]
                )
                .sum()
                .sum()
            )
        assert changed["AAPL"] > 0 and changed["MSFT"] > 0
        assert changed_executed["AAPL"] > 0 and changed_executed["MSFT"] > 0
        for row in results.values():
            assert row["feature_prefix_calls"] > 0
            assert all(row["safety"].values())
            assert row["metrics"]["entry_orders"] > 0 and row["metrics"]["accounted_closes"] > 0
            assert row["metrics"]["tick_errors"] == row["metrics"]["accounting_pending"] == 0
            if scenario == "crash":
                assert any(t["pnl"] < 0 for t in row["normalized_outcome"]["accounted_trades"])
            else:
                assert row["metrics"]["exit_mix"].get("eod_flatten", 0) > 0
                assert row["metrics"]["final_open_positions"] == 0
        # Current locked main book ignores these ML columns: prove nonempty
        # order/exit equality rather than silently accepting no-trade parity.
        for key in ("orders", "accounted_trades", "exit_legs", "equity_curve", "final_positions"):
            assert (
                results["baseline_ordinal"]["normalized_outcome"][key]
                == results["causal_timestamp"]["normalized_outcome"][key]
            )
        assert replay.source_hashes() == source_before, "Replay source changed during measurement"
        report = {
            "scenario": scenario,
            "scope": "Synthetic causal-feature mechanism; no strategy edge or historical lost-PnL inference",
            "config": config,
            "stock_history_trim": 40,
            "changed_cross_cells_after_warmup": changed,
            "changed_cross_cells_in_executed_rows": changed_executed,
            "noncross_features_equal": True,
            "orders_and_accounted_outcomes_equal": True,
            "direct_prefix_proofs": proof,
            "source_sha256": {
                **source_before,
                "tests/test_cross_asset_alignment_replay.py": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
            },
            "source_unchanged_during_replay": True,
            "input_sha256": {s: replay.frame_hash(f) for s, f in bars.items()},
            "arms": {
                k: {
                    "metrics": v["metrics"],
                    "safety": v["safety"],
                    "orders": v["normalized_outcome"]["orders"],
                    "accounted_trades": v["normalized_outcome"]["accounted_trades"],
                    "feature_prefix_calls": v["feature_prefix_calls"],
                }
                for k, v in results.items()
            },
            "limitations": [
                "Synthetic immediate next-open simulator with fixed5bp slippage and automatic half-spread; no live queue/latency/partial-fill model.",
                "Bar history transport is test-only; final actual engine/gates/positions/exits/accounting are observed unchanged.",
                "Repeated per-tick funnel counts are not unique opportunities; neutral placeholders do not qualify exported training data.",
            ],
        }
        output = (
            Path(replay.ROOT)
            / "artifacts/frozen_repairs_20260927/causal_features"
            / f"replay_{scenario}.json"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        record_property("scenario", scenario)
        record_property(
            "metrics", json.dumps({k: v["metrics"] for k, v in results.items()}, sort_keys=True)
        )
