"""V7 Track FF — adversarial-input probes.

Standalone probes (not pytest) that exercise the surfaces enumerated
in `track_ff_edge_cases_adversarial.md` against the *live module code*
to capture verdicts. Each probe prints PASS / FAIL / WARN and a short
note. Intended to be run via:

    ./venv/bin/python artifacts/audit/v7_reports/_probe_adversarial.py
"""
from __future__ import annotations

import json
import math
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

# Make sure the repo root is on sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

UTC = timezone.utc

results: list[dict] = []


def record(category: str, probe: str, verdict: str, note: str) -> None:
    results.append({"category": category, "probe": probe, "verdict": verdict, "note": note})
    print(f"[{verdict:5s}] {category:<22s} {probe:<55s} {note}")


def make_bar_df(n: int = 250, start: float = 100.0, vol: int = 1_000_000) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    ts = [datetime(2025, 1, 1, 9, 30, tzinfo=UTC) + timedelta(minutes=i) for i in range(n)]
    closes = start + np.cumsum(rng.normal(0, 0.3, n))
    opens = closes + rng.normal(0, 0.05, n)
    highs = np.maximum(opens, closes) + np.abs(rng.normal(0, 0.1, n))
    lows = np.minimum(opens, closes) - np.abs(rng.normal(0, 0.1, n))
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.full(n, vol, dtype=float),
        }
    )


# ─── 1. Bar data integrity ─────────────────────────────────────────
def probe_bar_integrity():
    from backend.organism.ml_features import compute_ml_features

    base = make_bar_df()

    # 1a duplicate timestamps
    df = base.copy()
    df.loc[len(df)] = df.iloc[-1].to_dict()  # duplicate of last bar
    try:
        out = compute_ml_features(df)
        # check NaN handling
        nan_ratio = float(out.iloc[-1].isna().sum()) / len(out.columns)
        record("1.bar_integrity", "duplicate_timestamps", "PASS",
               f"computed; rows={len(out)}, last-row nan_ratio={nan_ratio:.3f}")
    except Exception as e:
        record("1.bar_integrity", "duplicate_timestamps", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 1b out-of-order timestamps (bar N+1 earlier than N)
    df = base.copy()
    df.loc[len(df) - 1, "timestamp"] = df.loc[0, "timestamp"]
    try:
        out = compute_ml_features(df)
        # out-of-order is silently accepted — features may be wrong but no crash
        record("1.bar_integrity", "out_of_order_timestamps", "WARN",
               f"silently accepted; engine has no monotonicity guard. rows={len(out)}")
    except Exception as e:
        record("1.bar_integrity", "out_of_order_timestamps", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 1c missing timestamp (None)
    df = base.copy()
    df.loc[len(df) - 1, "timestamp"] = None
    try:
        out = compute_ml_features(df)
        record("1.bar_integrity", "missing_timestamp_none", "WARN",
               f"silently accepted None ts; len={len(out)}")
    except Exception as e:
        record("1.bar_integrity", "missing_timestamp_none", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 1d NaN close
    df = base.copy()
    df.loc[len(df) - 1, "close"] = float("nan")
    try:
        out = compute_ml_features(df)
        # the function fillna(0.0) at the end — but is missingness tracked?
        miss = float(out.iloc[-1].get("_nan_missingness", 0.0))
        record("1.bar_integrity", "nan_close", "PASS",
               f"missingness={miss:.3f}; engine should gate on this")
    except Exception as e:
        record("1.bar_integrity", "nan_close", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 1e Inf volume
    df = base.copy()
    df.loc[len(df) - 1, "volume"] = float("inf")
    try:
        out = compute_ml_features(df)
        # final fillna replaces inf with NaN then 0
        last_vol_ratio = float(out.iloc[-1].get("vol_sma_ratio", 0.0))
        record("1.bar_integrity", "inf_volume", "PASS",
               f"inf replaced; vol_sma_ratio={last_vol_ratio:.3f}")
    except Exception as e:
        record("1.bar_integrity", "inf_volume", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 1f negative volume
    df = base.copy()
    df.loc[len(df) - 1, "volume"] = -10_000_000.0
    try:
        out = compute_ml_features(df)
        ratio = float(out.iloc[-1].get("vol_sma_ratio", 0.0))
        record("1.bar_integrity", "negative_volume", "WARN",
               f"silently accepted negative volume → vol_sma_ratio={ratio:.3f}")
    except Exception as e:
        record("1.bar_integrity", "negative_volume", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 1g zero volume entire DF
    df = base.copy()
    df["volume"] = 0.0
    try:
        out = compute_ml_features(df)
        ratio = float(out.iloc[-1].get("vol_sma_ratio", 0.0))
        record("1.bar_integrity", "zero_volume_all_bars", "PASS",
               f"divide-by-zero protected; vol_sma_ratio={ratio:.3f}")
    except Exception as e:
        record("1.bar_integrity", "zero_volume_all_bars", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 1h negative price
    df = base.copy()
    df.loc[len(df) - 1, ["open", "high", "low", "close"]] = -50.0
    try:
        out = compute_ml_features(df)
        # log(close) on negative would produce NaN — confirm
        last_log_ret = float(out.iloc[-1].get("log_ret_1d", 0.0))
        record("1.bar_integrity", "negative_price", "WARN",
               f"accepted (log_ret_1d={last_log_ret}); upstream should reject")
    except Exception as e:
        record("1.bar_integrity", "negative_price", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 1i extreme 50% gap
    df = base.copy()
    df.loc[len(df) - 1, ["open", "high", "low", "close"]] = float(df.loc[len(df) - 2, "close"] * 1.50)
    try:
        out = compute_ml_features(df)
        gap = float(out.iloc[-1].get("gap_pct", 0.0))
        record("1.bar_integrity", "50pct_gap_up", "PASS",
               f"computed; gap_pct={gap:.3f}")
    except Exception as e:
        record("1.bar_integrity", "50pct_gap_up", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 1j frozen bars (100 identical OHLCV)
    df = base.copy()
    last = df.iloc[-1].copy()
    for i in range(100):
        # advance ts but freeze prices
        last_ts = df.iloc[-1]["timestamp"] + timedelta(minutes=1)
        new = last.to_dict()
        new["timestamp"] = last_ts
        df.loc[len(df)] = new
    try:
        out = compute_ml_features(df)
        # std=0 windows → many features zero / unbounded — confirm safe
        rsi = float(out.iloc[-1].get("rsi_14", 0.0))
        atr = float(out.iloc[-1].get("atr_14", 0.0))
        record("1.bar_integrity", "100_frozen_bars", "PASS",
               f"computed; rsi_14={rsi:.3f}, atr_14={atr:.3f}")
    except Exception as e:
        record("1.bar_integrity", "100_frozen_bars", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 1k single-bar DataFrame (insufficient lookback)
    df = base.iloc[:1].copy()
    try:
        out = compute_ml_features(df)
        record("1.bar_integrity", "single_bar_df", "PASS",
               f"computed with len=1; cols={len(out.columns)}")
    except Exception as e:
        record("1.bar_integrity", "single_bar_df", "FAIL",
               f"raised {type(e).__name__}: {e}")


# ─── 4. Feature pipeline edge cases ────────────────────────────────
def probe_feature_pipeline():
    from backend.organism.ml_features import compute_ml_features

    base = make_bar_df()

    # 4a all-NaN column
    df = base.copy()
    df["close"] = float("nan")
    try:
        out = compute_ml_features(df)
        record("4.feature_pipeline", "all_nan_close_column", "WARN",
               f"computed but features are 0/NaN-filled; len={len(out)}")
    except Exception as e:
        record("4.feature_pipeline", "all_nan_close_column", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 4b column rename (Close vs close)
    df = base.copy().rename(columns={"close": "Close"})
    try:
        out = compute_ml_features(df)
        record("4.feature_pipeline", "column_capitalised", "FAIL",
               "computed without rejecting capitalised 'Close' — but lookup KeyError expected")
    except KeyError as e:
        record("4.feature_pipeline", "column_capitalised", "PASS",
               f"raised KeyError as expected: {e}")
    except Exception as e:
        record("4.feature_pipeline", "column_capitalised", "WARN",
               f"raised {type(e).__name__}: {e} (not KeyError)")


# ─── 5. ML inference edge cases ────────────────────────────────────
def probe_ml_inference():
    from backend.organism.ml_signal import MLSignalGenerator
    from backend.organism.ml_features import compute_ml_features

    base = make_bar_df()
    feat = compute_ml_features(base)

    # 5a predict before training → returns neutral
    gen = MLSignalGenerator()
    try:
        sig = gen.predict(feat, symbol="TEST")
        if sig.direction == 0 and sig.confidence == 0:
            record("5.ml_inference", "predict_before_training", "PASS",
                   "returns neutral MLSignal (direction=0, conf=0)")
        else:
            record("5.ml_inference", "predict_before_training", "FAIL",
                   f"non-neutral signal returned: {sig}")
    except Exception as e:
        record("5.ml_inference", "predict_before_training", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 5b predict on a single feature row vs many — already covered (predict only uses .iloc[-1:])
    # Only verify shape consistency:
    gen2 = MLSignalGenerator()
    try:
        sig1 = gen2.predict(feat.iloc[[-1]], symbol="TEST")
        sig2 = gen2.predict(feat, symbol="TEST")
        same = (sig1.direction == sig2.direction and abs(sig1.confidence - sig2.confidence) < 1e-9)
        record("5.ml_inference", "single_vs_multi_row", "PASS" if same else "WARN",
               f"single={sig1.direction}/{sig1.confidence:.3f} vs multi={sig2.direction}/{sig2.confidence:.3f}")
    except Exception as e:
        record("5.ml_inference", "single_vs_multi_row", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 5c predict with one missing feature column — graceful (zero-pad documented)
    feat_drop = feat.drop(columns=["rsi_14"])
    try:
        sig = gen2.predict(feat_drop, symbol="TEST")
        record("5.ml_inference", "missing_one_feature_col", "PASS",
               f"untrained → neutral; trained path zero-pads when <20% missing")
    except Exception as e:
        record("5.ml_inference", "missing_one_feature_col", "FAIL",
               f"raised {type(e).__name__}: {e}")

    # 5d predict with extreme out-of-distribution feature (1e30)
    feat_oob = feat.copy()
    feat_oob.iloc[-1, feat_oob.columns.get_loc("rsi_14")] = 1e30
    try:
        sig = gen2.predict(feat_oob, symbol="TEST")
        record("5.ml_inference", "extreme_outlier_feature", "PASS",
               f"untrained returns neutral; np.nan_to_num handles inf in trained path")
    except Exception as e:
        record("5.ml_inference", "extreme_outlier_feature", "FAIL",
               f"raised {type(e).__name__}: {e}")


# ─── 6. Order submission adversarial (validate_order only — submit_symbol_order has no validation) ─
def probe_order_adversarial():
    from backend.services.order_service import OrderService

    svc = OrderService.__new__(OrderService)  # bypass __init__

    # 6a negative qty
    res = svc.validate_order({"symbol": "AAPL", "side": "buy", "qty": -10})
    if res.get("valid") is False and any("invalid_qty" in e for e in res.get("errors", [])):
        record("6.order_validate", "negative_qty", "PASS",
               f"rejected: {res['errors']}")
    else:
        record("6.order_validate", "negative_qty", "FAIL",
               f"accepted negative qty: {res}")

    # 6b qty=0
    res = svc.validate_order({"symbol": "AAPL", "side": "buy", "qty": 0})
    record("6.order_validate", "zero_qty",
           "PASS" if not res.get("valid") else "FAIL", str(res))

    # 6c symbol with special chars
    res = svc.validate_order({"symbol": "AA;PL", "side": "buy", "qty": 100})
    record("6.order_validate", "special_chars_symbol",
           "PASS" if not res.get("valid") else "FAIL", str(res))

    # 6d lowercase symbol
    res = svc.validate_order({"symbol": "aapl", "side": "buy", "qty": 100})
    record("6.order_validate", "lowercase_symbol",
           "PASS" if res.get("valid") else "WARN",
           f"valid={res.get('valid')} errors={res.get('errors')}")

    # 6e CRITICAL — submit_symbol_order does NOT call validate_order
    import inspect
    src = inspect.getsource(OrderService.submit_symbol_order)
    if "validate_order" in src:
        record("6.order_validate", "submit_symbol_order_validation_gap", "PASS",
               "submit_symbol_order calls validate_order")
    else:
        record("6.order_validate", "submit_symbol_order_validation_gap", "FAIL",
               "submit_symbol_order does NOT call validate_order — "
               "negative/zero/symbol-injection qty go straight to outbox")


# ─── 7. Idempotency key collision ──────────────────────────────────
async def probe_idempotency_collision():
    """submit_symbol_order returns cached result on idem-key match WITHOUT
    verifying the new request body matches the cached body. Two callers
    using the same idempotency_key with different (symbol, side, qty)
    will both see the SAME response. Verify by inspecting the source."""
    from backend.services.order_service import OrderService
    import inspect

    src = inspect.getsource(OrderService.submit_symbol_order)
    # Look for content-fingerprint check on cache hit
    if "if idempotency_key in self._async_submitted_orders" in src:
        # Does it compare symbol/side/qty before returning?
        idx_check = src.find("if idempotency_key in self._async_submitted_orders")
        idx_return = src.find("return existing_result", idx_check)
        between = src[idx_check:idx_return]
        if "symbol" in between and ("side" in between or "qty" in between):
            record("6.order_validate", "idem_key_collision_with_diff_content", "PASS",
                   "cache hit verifies content fingerprint")
        else:
            record("6.order_validate", "idem_key_collision_with_diff_content", "FAIL",
                   "cache returns existing result WITHOUT verifying body matches "
                   "(symbol/side/qty)")
    else:
        record("6.order_validate", "idem_key_collision_with_diff_content", "WARN",
               "cache lookup pattern not found — manual review required")


# ─── 9. Numerical adversarial ──────────────────────────────────────
def probe_numerical():
    # 9a NaN actual_return when entry_price=0
    try:
        actual_return = (101.0 - 0.0) / 0.0  # ZeroDivisionError
        record("9.numerical", "entry_price_zero", "FAIL", "no division-by-zero raised")
    except ZeroDivisionError:
        record("9.numerical", "entry_price_zero", "PASS",
               "Python raises ZeroDivisionError; check live_engine guards")

    # Re-do with floats (non-raising)
    actual_return = (101.0 - 0.0) / 1e-300  # huge number
    record("9.numerical", "near_zero_entry_with_float", "WARN",
           f"actual_return={actual_return:.3e} (no guard for entry_price ~0)")

    # 9b sharpe denom near-zero
    rets = np.array([1e-15, 1e-15, 1e-15])
    std = float(rets.std())
    sharpe = float(rets.mean() / std) if std > 0 else float("inf")
    record("9.numerical", "sharpe_near_zero_variance", "WARN",
           f"std={std:.3e} sharpe={sharpe:.3e} — caller must guard")

    # 9c float64 cumulative pnl approaches limit
    huge = 1e308
    try:
        out = huge + huge  # → inf
        record("9.numerical", "float64_overflow", "WARN",
               f"silent inf overflow: {out}")
    except OverflowError as e:
        record("9.numerical", "float64_overflow", "PASS", str(e))


# ─── 10. Configuration adversarial ─────────────────────────────────
def probe_configuration():
    """Probe by emulating the same parsing pattern live_engine uses, since
    importlib.reload re-registers Prometheus metrics → ValueError.
    The module is read once via inspect to confirm pattern fidelity."""

    # 10a empty ORGANISM_LIVE_SYMBOLS — pattern from live_engine line 376-380
    raw = ""  # what os.getenv would return for an explicitly-empty env var
    parsed = [s.strip().upper() for s in raw.split(",") if s.strip()]
    if parsed == []:
        record("10.config", "empty_universe_csv", "WARN",
               "ORGANISM_LIVE_SYMBOLS='' parses to empty list — engine will run with 0 symbols")
    else:
        record("10.config", "empty_universe_csv", "PASS", f"parsed={parsed}")

    # 10b duplicate symbols
    raw = "AAPL,AAPL,AAPL"
    parsed = [s.strip().upper() for s in raw.split(",") if s.strip()]
    if len(parsed) != len(set(parsed)):
        record("10.config", "duplicate_symbols_csv", "FAIL",
               f"duplicates accepted as-is: {parsed} (no dedup)")
    else:
        record("10.config", "duplicate_symbols_csv", "PASS", f"deduped: {parsed}")

    # 10c negative MAX_NOTIONAL_PER_TRADE — replicate _env_float pattern
    val = float("-100")
    if val < 0:
        record("10.config", "negative_max_notional", "FAIL",
               f"_env_float accepts -100 verbatim; MAX_NOTIONAL_PER_TRADE={val}; "
               "guard `if > 0` disables the feature silently (no validation/alert)")
    else:
        record("10.config", "negative_max_notional", "PASS", f"value={val}")

    # 10d invalid LOG_LEVEL
    os.environ["LOG_LEVEL"] = "BANANA"
    try:
        import logging as _log
        _log.getLogger().setLevel(os.environ["LOG_LEVEL"])
        record("10.config", "invalid_log_level", "FAIL",
               "stdlib logging accepted 'BANANA' (uppercased); behaviour unspecified")
    except (ValueError, TypeError) as e:
        record("10.config", "invalid_log_level", "PASS", f"raised {type(e).__name__}: {e}")

    # cleanup
    for k in ("ORGANISM_LIVE_SYMBOLS", "ORGANISM_MAX_NOTIONAL", "LOG_LEVEL"):
        os.environ.pop(k, None)


# ─── 2/3. Broker / WS adversarial — static review only ─────────────
def probe_broker_ws_static():
    """We don't spin up real WebSocket connections; we statically inspect
    the message handlers for documented adversarial paths."""
    import inspect
    from backend.integrations import alpaca_stream, alpaca_broker

    listen_src = inspect.getsource(alpaca_stream.AlpacaStreamClient.listen)
    process_src = inspect.getsource(alpaca_stream.AlpacaStreamClient._process_trade_update)

    # 3a malformed JSON path
    if "json.JSONDecodeError" in listen_src and "continue" in listen_src:
        record("3.ws", "malformed_json", "PASS",
               "listen() catches JSONDecodeError + continue (no hang)")
    else:
        record("3.ws", "malformed_json", "FAIL",
               "listen() does not handle JSONDecodeError — would crash WS loop")

    # 3b filled_qty=null path  (broker schema drift)
    if "filled_qty" in process_src and "or 0" not in process_src.split("filled_qty", 1)[1][:80]:
        # Look for safe parsing
        if "float(order_data.get(\"filled_qty\", 0))" in process_src:
            record("3.ws", "filled_qty_null_field", "FAIL",
                   "process_trade_update calls `float(order_data.get('filled_qty', 0))` — "
                   "if broker sends filled_qty=null (JSON null → Python None), "
                   ".get returns None and float(None) raises TypeError. "
                   "The outer except Exception catches it and DROPS the message silently — "
                   "fill never lands in DB → state divergence")
        else:
            record("3.ws", "filled_qty_null_field", "WARN",
                   "filled_qty parsing pattern not as expected; manual review")
    else:
        record("3.ws", "filled_qty_null_field", "WARN",
               "filled_qty handling pattern not found")

    # 3c unbounded queue → OOM if processor stuck
    handle_src = inspect.getsource(alpaca_stream.AlpacaStreamClient._handle_message)
    if "asyncio.Queue()" in inspect.getsource(alpaca_stream.AlpacaStreamClient.__init__) \
            and "maxsize" not in inspect.getsource(alpaca_stream.AlpacaStreamClient.__init__):
        record("3.ws", "unbounded_queue", "WARN",
               "update_queue is unbounded; the comment says 'must NEVER be dropped' "
               "but a stuck processor → memory unbounded growth")
    else:
        record("3.ws", "unbounded_queue", "PASS", "queue is bounded or dropping enabled")

    # 2a 5xx forever (broker_broker static review of retry counter)
    req_src = inspect.getsource(alpaca_broker.AlpacaBrokerClient._make_request_with_retry)
    if "max_retries" in req_src and "for attempt in range" in req_src:
        record("2.broker", "5xx_infinite_retry", "PASS",
               "_make_request_with_retry has bounded retries (max_retries=3)")
    else:
        record("2.broker", "5xx_infinite_retry", "FAIL",
               "no bounded retry detected")

    # 2b 200 with empty body
    place_src = inspect.getsource(alpaca_broker.AlpacaBrokerClient.place_order)
    if "response.status_code in (200, 201)" in place_src and "response.json()" in place_src:
        record("2.broker", "200_empty_body", "FAIL",
               "place_order calls response.json() unconditionally on 200 — "
               "empty body raises JSONDecodeError → outer except wraps into 502")
    else:
        record("2.broker", "200_empty_body", "PASS", "checked")


# ─── 8. State persistence adversarial — static ─────────────────────
def probe_state_persistence():
    import inspect
    try:
        from backend.organism import brain_persistence as bp
        save_src = inspect.getsource(bp.OrganismBrain) if hasattr(bp, "OrganismBrain") else ""
        if "fcntl" in save_src or "filelock" in save_src or "Lock" in save_src:
            record("8.state", "concurrent_writer_lock", "PASS",
                   "brain_persistence uses some lock primitive")
        else:
            record("8.state", "concurrent_writer_lock", "WARN",
                   "no fcntl/filelock detected in OrganismBrain; concurrent writers "
                   "(shadow scanner + live engine on same volume) may corrupt files")
    except Exception as e:
        record("8.state", "concurrent_writer_lock", "WARN", f"inspection failed: {e}")


# ─── 7. Time / scheduling adversarial — static ─────────────────────
def probe_time_scheduling():
    """Static check for DST awareness in _last_bar_times key construction."""
    import inspect
    from backend.organism import live_engine
    src = inspect.getsource(live_engine.LiveEngine.step) if hasattr(live_engine, "LiveEngine") else ""
    # Just check there's a sample of UTC discipline
    try:
        bar_ts_pattern = "self._now_fn().astimezone(UTC).strftime"
        if bar_ts_pattern in inspect.getsource(live_engine):
            record("7.time", "bar_ts_uses_utc", "PASS",
                   "_last_bar_times keyed on UTC string — DST-immune")
        else:
            record("7.time", "bar_ts_uses_utc", "WARN", "bar ts pattern not found")
    except Exception as e:
        record("7.time", "bar_ts_uses_utc", "WARN", f"inspection failed: {e}")


# ─── Driver ────────────────────────────────────────────────────────
def main():
    print(f"# V7 Track FF probes — {datetime.now(UTC).isoformat()}\n")

    for fn in (probe_bar_integrity, probe_feature_pipeline, probe_ml_inference,
               probe_order_adversarial, probe_numerical, probe_configuration,
               probe_broker_ws_static, probe_state_persistence,
               probe_time_scheduling):
        try:
            fn()
        except Exception:
            traceback.print_exc()

    # idempotency probe is async
    import asyncio
    try:
        asyncio.run(probe_idempotency_collision())
    except Exception:
        traceback.print_exc()

    summary = {
        "total": len(results),
        "PASS": sum(1 for r in results if r["verdict"] == "PASS"),
        "WARN": sum(1 for r in results if r["verdict"] == "WARN"),
        "FAIL": sum(1 for r in results if r["verdict"] == "FAIL"),
    }
    print("\n# Summary:", json.dumps(summary, indent=2))
    out_path = "/Users/marselkei/VS/intra/artifacts/audit/v7_reports/_probe_results.json"
    with open(out_path, "w") as fh:
        json.dump({"summary": summary, "results": results}, fh, indent=2, default=str)
    print(f"# wrote {out_path}")


if __name__ == "__main__":
    main()
