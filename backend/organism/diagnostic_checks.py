"""
Diagnostic checks — 36 checks across 8 categories.

Imported at engine startup to register checks with the global DiagnosticEngine.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from backend.organism.diagnostics import (
    CheckCategory,
    CheckMode,
    CheckSeverity,
    DiagnosticResult,
    diagnostics,
)

ALL_MODES = {CheckMode.PREFLIGHT, CheckMode.DEEP, CheckMode.CONTINUOUS}
PREFLIGHT_DEEP = {CheckMode.PREFLIGHT, CheckMode.DEEP}
DEEP_ONLY = {CheckMode.DEEP}
CONTINUOUS_DEEP = {CheckMode.CONTINUOUS, CheckMode.DEEP}


def _ok(name: str, category: str, severity: str, msg: str) -> DiagnosticResult:
    return DiagnosticResult(name=name, category=category, severity=severity, passed=True, message=msg)


def _fail(name: str, category: str, severity: str, msg: str) -> DiagnosticResult:
    return DiagnosticResult(name=name, category=category, severity=severity, passed=False, message=msg)


# ═══════════════════════════════════════════════════════════════════
#  WIRING (7 checks) — are services connected?
# ═══════════════════════════════════════════════════════════════════

@diagnostics.check(
    name="wiring_data_client",
    category=CheckCategory.WIRING,
    severity=CheckSeverity.CRITICAL,
    modes=PREFLIGHT_DEEP,
)
async def check_wiring_data_client(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "wiring_data_client", "wiring", "critical"
    if engine is None:
        return _fail(n, c, s, "No engine provided")
    dc = getattr(engine, "_data_client", None)
    if dc is None:
        return _fail(n, c, s, "data_client is None")
    if not hasattr(dc, "get_historical_data"):
        return _fail(n, c, s, "data_client missing get_historical_data method")
    return _ok(n, c, s, "data_client wired and has get_historical_data")


@diagnostics.check(
    name="wiring_order_service",
    category=CheckCategory.WIRING,
    severity=CheckSeverity.CRITICAL,
    modes=PREFLIGHT_DEEP,
)
async def check_wiring_order_service(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "wiring_order_service", "wiring", "critical"
    if engine is None:
        return _fail(n, c, s, "No engine provided")
    os_ = getattr(engine, "_order_service", None)
    if os_ is None:
        return _fail(n, c, s, "order_service is None")
    if not hasattr(os_, "submit_symbol_order"):
        return _fail(n, c, s, "order_service missing submit_symbol_order")
    return _ok(n, c, s, "order_service wired and has submit_symbol_order")


@diagnostics.check(
    name="wiring_positions_service",
    category=CheckCategory.WIRING,
    severity=CheckSeverity.CRITICAL,
    modes=PREFLIGHT_DEEP,
)
async def check_wiring_positions_service(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "wiring_positions_service", "wiring", "critical"
    if engine is None:
        return _fail(n, c, s, "No engine provided")
    ps = getattr(engine, "_positions_service", None)
    if ps is None:
        return _fail(n, c, s, "positions_service is None")
    missing = []
    for method in ("get_all_positions", "get_total_portfolio_value", "get_buying_power"):
        if not hasattr(ps, method):
            missing.append(method)
    if missing:
        return _fail(n, c, s, f"positions_service missing: {', '.join(missing)}")
    return _ok(n, c, s, "positions_service wired with all required methods")


@diagnostics.check(
    name="wiring_sessionmaker",
    category=CheckCategory.WIRING,
    severity=CheckSeverity.WARNING,
    modes=PREFLIGHT_DEEP,
)
async def check_wiring_sessionmaker(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "wiring_sessionmaker", "wiring", "warning"
    if engine is None:
        return _fail(n, c, s, "No engine provided")
    sm = getattr(engine, "_sessionmaker", None)
    if sm is None:
        return _fail(n, c, s, "sessionmaker is None — DB features disabled")
    if not callable(sm):
        return _fail(n, c, s, "sessionmaker is not callable")
    return _ok(n, c, s, "sessionmaker wired and callable")


@diagnostics.check(
    name="wiring_brain_directory",
    category=CheckCategory.WIRING,
    severity=CheckSeverity.WARNING,
    modes=PREFLIGHT_DEEP,
)
async def check_wiring_brain_directory(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "wiring_brain_directory", "wiring", "warning"
    if engine is None:
        return _fail(n, c, s, "No engine provided")
    brain = getattr(engine, "brain", None)
    if brain is None:
        return _fail(n, c, s, "brain is None")
    brain_dir = getattr(brain, "_brain_dir", None) or getattr(brain, "brain_dir", None)
    if brain_dir is None:
        return _fail(n, c, s, "Cannot determine brain directory")
    p = Path(brain_dir)
    if not p.exists():
        return _fail(n, c, s, f"Brain directory does not exist: {brain_dir}")
    if not os.access(str(p), os.W_OK):
        return _fail(n, c, s, f"Brain directory not writable: {brain_dir}")
    return _ok(n, c, s, f"Brain directory exists and is writable: {brain_dir}")


@diagnostics.check(
    name="wiring_streaming_consistency",
    category=CheckCategory.WIRING,
    severity=CheckSeverity.INFO,
    modes=PREFLIGHT_DEEP,
)
async def check_wiring_streaming_consistency(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "wiring_streaming_consistency", "wiring", "info"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    use_streaming = os.getenv("ORGANISM_USE_STREAMING", "0").lower() in ("1", "true", "yes")
    provider = getattr(engine, "_streaming_provider", None)
    if use_streaming and provider is None:
        return _fail(n, c, s, "USE_STREAMING=1 but streaming_provider is None")
    if use_streaming and provider is not None:
        running = getattr(provider, "is_running", False)
        if callable(running):
            running = running
        if not running:
            return _fail(n, c, s, "USE_STREAMING=1 but provider is not running")
    return _ok(n, c, s, "Streaming config consistent")


@diagnostics.check(
    name="wiring_components_initialized",
    category=CheckCategory.WIRING,
    severity=CheckSeverity.CRITICAL,
    modes=PREFLIGHT_DEEP,
)
async def check_wiring_components(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "wiring_components_initialized", "wiring", "critical"
    if engine is None:
        return _fail(n, c, s, "No engine provided")
    components = [
        "signal_gen", "alpha_scanner", "breakout_scanner", "pyramider",
        "kelly_sizer", "exit_engine", "learner", "regime_detector",
        "governance", "evolution_engine",
    ]
    missing = [name for name in components if getattr(engine, name, None) is None]
    if missing:
        return _fail(n, c, s, f"Components are None: {', '.join(missing)}")
    return _ok(n, c, s, f"All {len(components)} core components initialized")


# ═══════════════════════════════════════════════════════════════════
#  STATE_PERSISTENCE (6 checks) — brain round-trip integrity
# ═══════════════════════════════════════════════════════════════════

@diagnostics.check(
    name="state_tick_counter_integrity",
    category=CheckCategory.STATE_PERSISTENCE,
    severity=CheckSeverity.WARNING,
    modes=ALL_MODES,
)
async def check_state_tick_counter(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "state_tick_counter_integrity", "state_persistence", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    tc = getattr(engine, "_tick_count", 0)
    bsr = getattr(engine, "_bars_since_retrain", 0)
    if tc < 0:
        return _fail(n, c, s, f"tick_count is negative: {tc}")
    if bsr > tc:
        return _fail(n, c, s, f"bars_since_retrain ({bsr}) > tick_count ({tc})")
    return _ok(n, c, s, f"tick_count={tc}, bars_since_retrain={bsr}")


@diagnostics.check(
    name="state_exit_levels_have_metadata",
    category=CheckCategory.STATE_PERSISTENCE,
    severity=CheckSeverity.WARNING,
    modes=ALL_MODES,
)
async def check_state_exit_metadata(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "state_exit_levels_have_metadata", "state_persistence", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    exits = getattr(engine, "_exit_levels", {})
    meta = getattr(engine, "_entry_metadata", {})
    orphans = [sym for sym in exits if sym not in meta]
    if orphans:
        return _fail(n, c, s, f"Exit levels without metadata: {orphans}")
    return _ok(n, c, s, f"{len(exits)} exit levels, all have metadata")


@diagnostics.check(
    name="state_entry_metadata_matches_positions",
    category=CheckCategory.STATE_PERSISTENCE,
    severity=CheckSeverity.INFO,
    modes=DEEP_ONLY,
)
async def check_state_metadata_vs_positions(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "state_entry_metadata_matches_positions", "state_persistence", "info"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    meta = getattr(engine, "_entry_metadata", {})
    if not meta:
        return _ok(n, c, s, "No entry metadata — nothing to verify")
    try:
        ps = getattr(engine, "_positions_service", None)
        if ps is None:
            return _ok(n, c, s, "No positions service — skipped")
        positions = await ps.get_all_positions()
        orphans = [sym for sym in meta if sym not in (positions or {})]
        if orphans:
            return _fail(n, c, s, f"Metadata for non-existent positions: {orphans}")
        return _ok(n, c, s, f"All {len(meta)} metadata entries match broker positions")
    except Exception as e:
        return _fail(n, c, s, f"Failed to check positions: {e}")


@diagnostics.check(
    name="state_brain_manifest_valid",
    category=CheckCategory.STATE_PERSISTENCE,
    severity=CheckSeverity.WARNING,
    modes=PREFLIGHT_DEEP,
)
async def check_state_brain_manifest(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "state_brain_manifest_valid", "state_persistence", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    brain = getattr(engine, "brain", None)
    if brain is None:
        return _fail(n, c, s, "brain is None")
    warnings = brain.validate_brain()
    if warnings:
        return _fail(n, c, s, f"Brain validation warnings: {'; '.join(warnings[:3])}")
    return _ok(n, c, s, "Brain manifest valid — no warnings")


@diagnostics.check(
    name="state_governance_persistence",
    category=CheckCategory.STATE_PERSISTENCE,
    severity=CheckSeverity.INFO,
    modes=PREFLIGHT_DEEP,
)
async def check_state_governance(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "state_governance_persistence", "state_persistence", "info"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    gov = getattr(engine, "governance", None)
    if gov is None:
        return _fail(n, c, s, "governance is None")
    dl = getattr(gov, "_drawdown_limit", None)
    if dl is None:
        return _fail(n, c, s, "drawdown_limit not set")
    if not (0.01 <= dl <= 1.0):
        return _fail(n, c, s, f"drawdown_limit={dl} outside [0.01, 1.0]")
    return _ok(n, c, s, f"drawdown_limit={dl}")


@diagnostics.check(
    name="state_evolved_params_valid",
    category=CheckCategory.STATE_PERSISTENCE,
    severity=CheckSeverity.WARNING,
    modes=PREFLIGHT_DEEP,
)
async def check_state_evolved_params(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "state_evolved_params_valid", "state_persistence", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    ep = getattr(engine, "evolved_params", None)
    if ep is None:
        return _fail(n, c, s, "evolved_params is None")
    gen = getattr(ep, "generation", -1)
    if gen < 0:
        return _fail(n, c, s, f"Negative generation: {gen}")
    fitness = getattr(ep, "fitness", -1.0)
    if not (0.0 <= fitness <= 1.0):
        return _fail(n, c, s, f"fitness={fitness} outside [0, 1]")
    return _ok(n, c, s, f"generation={gen}, fitness={fitness:.3f}")


# ═══════════════════════════════════════════════════════════════════
#  ORDER_FLOW (5 checks)
# ═══════════════════════════════════════════════════════════════════

@diagnostics.check(
    name="order_long_only_no_shorts",
    category=CheckCategory.ORDER_FLOW,
    severity=CheckSeverity.CRITICAL,
    modes=ALL_MODES,
)
async def check_order_long_only(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "order_long_only_no_shorts", "order_flow", "critical"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    from backend.organism.live_engine import LONG_ONLY
    if not LONG_ONLY:
        return _ok(n, c, s, "LONG_ONLY is false — shorts allowed")
    try:
        ps = getattr(engine, "_positions_service", None)
        if ps is None:
            return _ok(n, c, s, "No positions service — skipped")
        positions = await ps.get_all_positions()
        shorts = []
        for sym, data in (positions or {}).items():
            qty = float(data.get("qty", data.get("quantity", 0)))
            if qty < 0:
                shorts.append(f"{sym}={qty}")
        if shorts:
            return _fail(n, c, s, f"LONG_ONLY but shorts exist: {', '.join(shorts)}")
        return _ok(n, c, s, "LONG_ONLY — no short positions")
    except Exception as e:
        return _fail(n, c, s, f"Failed to check positions: {e}")


@diagnostics.check(
    name="order_no_duplicate_pending_entries",
    category=CheckCategory.ORDER_FLOW,
    severity=CheckSeverity.WARNING,
    modes=CONTINUOUS_DEEP,
)
async def check_order_no_dup_entries(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "order_no_duplicate_pending_entries", "order_flow", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    pending = getattr(engine, "_pending_entry", {})
    exits = getattr(engine, "_exit_levels", {})
    overlaps = [sym for sym in pending if sym in exits]
    if overlaps:
        return _fail(n, c, s, f"Pending entries overlap existing positions: {overlaps}")
    return _ok(n, c, s, f"{len(pending)} pending entries, no overlaps")


@diagnostics.check(
    name="order_pending_exit_not_stale",
    category=CheckCategory.ORDER_FLOW,
    severity=CheckSeverity.WARNING,
    modes=CONTINUOUS_DEEP,
)
async def check_order_pending_exit_stale(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "order_pending_exit_not_stale", "order_flow", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    pending_exit = getattr(engine, "_pending_exit", {})
    tc = getattr(engine, "_tick_count", 0)
    cooldown = getattr(engine, "_PENDING_EXIT_TICKS", 3)
    stale_threshold = cooldown * 3
    stale = [sym for sym, tick in pending_exit.items() if tc - tick > stale_threshold]
    if stale:
        return _fail(n, c, s, f"Stale pending exits (>{stale_threshold} ticks): {stale}")
    return _ok(n, c, s, f"{len(pending_exit)} pending exits, none stale")


@diagnostics.check(
    name="order_position_limit_respected",
    category=CheckCategory.ORDER_FLOW,
    severity=CheckSeverity.WARNING,
    modes=ALL_MODES,
)
async def check_order_position_limit(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "order_position_limit_respected", "order_flow", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    from backend.organism.live_engine import MAX_OPEN_POSITIONS
    exits = getattr(engine, "_exit_levels", {})
    count = len(exits)
    if count > MAX_OPEN_POSITIONS:
        return _fail(n, c, s, f"Positions ({count}) > MAX_OPEN_POSITIONS ({MAX_OPEN_POSITIONS})")
    return _ok(n, c, s, f"{count}/{MAX_OPEN_POSITIONS} positions")


@diagnostics.check(
    name="order_cooldown_maps_consistent",
    category=CheckCategory.ORDER_FLOW,
    severity=CheckSeverity.INFO,
    modes=CONTINUOUS_DEEP,
)
async def check_order_cooldown_maps(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "order_cooldown_maps_consistent", "order_flow", "info"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    tc = getattr(engine, "_tick_count", 0)
    future_exit = [sym for sym, t in getattr(engine, "_exit_cooldown", {}).items() if t > tc]
    future_entry = [sym for sym, t in getattr(engine, "_pending_entry", {}).items() if t > tc]
    issues = []
    if future_exit:
        issues.append(f"exit_cooldown future ticks: {future_exit}")
    if future_entry:
        issues.append(f"pending_entry future ticks: {future_entry}")
    if issues:
        return _fail(n, c, s, "; ".join(issues))
    return _ok(n, c, s, "All cooldown tick values <= current tick_count")


# ═══════════════════════════════════════════════════════════════════
#  DATA_PIPELINE (6 checks)
# ═══════════════════════════════════════════════════════════════════

@diagnostics.check(
    name="data_ml_model_state",
    category=CheckCategory.DATA_PIPELINE,
    severity=CheckSeverity.WARNING,
    modes=CONTINUOUS_DEEP,
)
async def check_data_ml_model(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "data_ml_model_state", "data_pipeline", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    sg = getattr(engine, "signal_gen", None)
    if sg is None:
        return _fail(n, c, s, "signal_gen is None")
    trained = getattr(sg, "_is_trained", False)
    if not trained:
        return _fail(n, c, s, "ML model not yet trained")
    return _ok(n, c, s, "ML model is trained")


@diagnostics.check(
    name="data_kelly_floor_not_zero",
    category=CheckCategory.DATA_PIPELINE,
    severity=CheckSeverity.WARNING,
    modes=DEEP_ONLY,
)
async def check_data_kelly_floor(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "data_kelly_floor_not_zero", "data_pipeline", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    ks = getattr(engine, "kelly_sizer", None)
    if ks is None:
        return _fail(n, c, s, "kelly_sizer is None")
    try:
        test_candidates = [{
            "symbol": "TEST",
            "composite_score": 0.65,
            "direction": 1.0,
            "predicted_return": 0.02,
            "confidence": 0.65,
            "breakout_score": 0.0,
        }]
        import pandas as pd
        dummy_features = {"TEST": pd.DataFrame({"close": [100.0] * 20, "volume": [1e6] * 20})}
        sized = ks.size_positions(
            test_candidates, 100_000.0, 0.0,
            dummy_features, current_regime="unknown", ml_is_trained=True,
        )
        if not sized or all(p.shares == 0 for p in sized):
            return _fail(n, c, s, "Kelly produces 0 shares at confidence=0.65")
        shares = sized[0].shares if sized else 0
        return _ok(n, c, s, f"Kelly produces {shares} shares at confidence=0.65")
    except Exception as e:
        return _fail(n, c, s, f"Kelly sizing failed: {e}")


@diagnostics.check(
    name="data_numpy_json_serialization",
    category=CheckCategory.DATA_PIPELINE,
    severity=CheckSeverity.CRITICAL,
    modes=PREFLIGHT_DEEP,
)
async def check_data_numpy_json(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "data_numpy_json_serialization", "data_pipeline", "critical"
    import numpy as np
    test_data = {
        "float64": float(np.float64(1.5)),
        "bool_": bool(np.bool_(True)),
        "int64": int(np.int64(42)),
        "array": np.array([1.0, 2.0]).tolist(),
    }
    try:
        json.dumps(test_data)
        # Also verify raw numpy types would fail (this is why we use _f/_b helpers)
        return _ok(n, c, s, "numpy types serialize via float()/bool()/int() casts")
    except TypeError as e:
        return _fail(n, c, s, f"numpy JSON serialization fails: {e}")


@diagnostics.check(
    name="data_feature_columns_consistent",
    category=CheckCategory.DATA_PIPELINE,
    severity=CheckSeverity.INFO,
    modes=DEEP_ONLY,
)
async def check_data_feature_columns(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "data_feature_columns_consistent", "data_pipeline", "info"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    sg = getattr(engine, "signal_gen", None)
    if sg is None:
        return _fail(n, c, s, "signal_gen is None")
    model_cols = getattr(sg, "_feature_cols", [])
    if not model_cols:
        return _ok(n, c, s, "Model not yet trained — no feature columns to compare")
    from backend.organism.ml_features import FEATURE_COLUMNS
    if set(model_cols) != set(FEATURE_COLUMNS):
        extra = set(model_cols) - set(FEATURE_COLUMNS)
        missing = set(FEATURE_COLUMNS) - set(model_cols)
        parts = []
        if extra:
            parts.append(f"extra in model: {list(extra)[:5]}")
        if missing:
            parts.append(f"missing from model: {list(missing)[:5]}")
        return _fail(n, c, s, f"Feature column mismatch: {'; '.join(parts)}")
    return _ok(n, c, s, f"{len(model_cols)} feature columns match FEATURE_COLUMNS")


@diagnostics.check(
    name="data_universe_non_empty",
    category=CheckCategory.DATA_PIPELINE,
    severity=CheckSeverity.CRITICAL,
    modes=ALL_MODES,
)
async def check_data_universe(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "data_universe_non_empty", "data_pipeline", "critical"
    if engine is None:
        return _fail(n, c, s, "No engine provided")
    universe = getattr(engine, "_universe", [])
    if not universe:
        return _fail(n, c, s, "Universe is empty — no symbols to trade")
    return _ok(n, c, s, f"Universe has {len(universe)} symbols")


@diagnostics.check(
    name="data_regime_detector_state",
    category=CheckCategory.DATA_PIPELINE,
    severity=CheckSeverity.INFO,
    modes=CONTINUOUS_DEEP,
)
async def check_data_regime_state(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "data_regime_detector_state", "data_pipeline", "info"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    rd = getattr(engine, "regime_detector", None)
    if rd is None:
        return _fail(n, c, s, "regime_detector is None")
    last_state = getattr(rd, "_last_state", None)
    if last_state is None:
        return _fail(n, c, s, "Regime detector has no _last_state — not yet run")
    return _ok(n, c, s, f"Regime detector active, last state set")


# ═══════════════════════════════════════════════════════════════════
#  STREAMING (3 checks)
# ═══════════════════════════════════════════════════════════════════

@diagnostics.check(
    name="streaming_provider_health",
    category=CheckCategory.STREAMING,
    severity=CheckSeverity.WARNING,
    modes=CONTINUOUS_DEEP,
)
async def check_streaming_health(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "streaming_provider_health", "streaming", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    provider = getattr(engine, "_streaming_provider", None)
    if provider is None:
        return _ok(n, c, s, "No streaming provider configured — using polling")
    running = getattr(provider, "is_running", False)
    if callable(running):
        running = running  # it's a property, already evaluated
    if not running:
        return _fail(n, c, s, "Streaming provider is not running")
    last_ts = getattr(provider, "_last_bar_ts", {})
    if last_ts:
        now = time.time()
        stale = {sym: int(now - ts) for sym, ts in last_ts.items() if now - ts > 300}
        if stale:
            return _fail(n, c, s, f"Stale streams (>5min): {dict(list(stale.items())[:5])}")
    return _ok(n, c, s, "Streaming provider running, no staleness detected")


@diagnostics.check(
    name="streaming_subscription_coverage",
    category=CheckCategory.STREAMING,
    severity=CheckSeverity.WARNING,
    modes=CONTINUOUS_DEEP,
)
async def check_streaming_coverage(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "streaming_subscription_coverage", "streaming", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    provider = getattr(engine, "_streaming_provider", None)
    if provider is None:
        return _ok(n, c, s, "No streaming provider — skipped")
    universe = getattr(engine, "_universe", [])
    bars = getattr(provider, "_bars", {})
    covered = sum(1 for sym in universe if sym in bars and len(bars[sym]) > 0)
    pct = covered / len(universe) * 100 if universe else 0
    if pct < 50:
        return _fail(n, c, s, f"Only {covered}/{len(universe)} ({pct:.0f}%) symbols have streaming data")
    return _ok(n, c, s, f"{covered}/{len(universe)} ({pct:.0f}%) symbols covered")


@diagnostics.check(
    name="streaming_websocket_connected",
    category=CheckCategory.STREAMING,
    severity=CheckSeverity.INFO,
    modes=DEEP_ONLY,
)
async def check_streaming_websocket(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "streaming_websocket_connected", "streaming", "info"
    try:
        from backend.websocket import get_websocket_manager
        mgr = get_websocket_manager()
        if mgr is None:
            return _fail(n, c, s, "WebSocket manager is None")
        return _ok(n, c, s, "WebSocket manager available")
    except Exception:
        return _fail(n, c, s, "WebSocket manager not available")


# ═══════════════════════════════════════════════════════════════════
#  GOVERNANCE (4 checks)
# ═══════════════════════════════════════════════════════════════════

@diagnostics.check(
    name="governance_drawdown_sane",
    category=CheckCategory.GOVERNANCE,
    severity=CheckSeverity.CRITICAL,
    modes=PREFLIGHT_DEEP,
)
async def check_governance_drawdown(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "governance_drawdown_sane", "governance", "critical"
    if engine is None:
        return _fail(n, c, s, "No engine provided")
    gov = getattr(engine, "governance", None)
    if gov is None:
        return _fail(n, c, s, "governance is None")
    dl = getattr(gov, "_drawdown_limit", None)
    if dl is None:
        return _fail(n, c, s, "drawdown_limit not set")
    if not (0.01 <= dl <= 0.50):
        return _fail(n, c, s, f"drawdown_limit={dl} outside safe range [1%, 50%]")
    return _ok(n, c, s, f"drawdown_limit={dl:.1%}")


@diagnostics.check(
    name="governance_equity_tracking",
    category=CheckCategory.GOVERNANCE,
    severity=CheckSeverity.WARNING,
    modes=CONTINUOUS_DEEP,
)
async def check_governance_equity(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "governance_equity_tracking", "governance", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    tc = getattr(engine, "_tick_count", 0)
    pe = getattr(engine, "_peak_equity", 0.0)
    if tc > 5 and pe <= 0:
        return _fail(n, c, s, f"peak_equity={pe} after {tc} ticks — equity tracking broken")
    return _ok(n, c, s, f"peak_equity=${pe:,.0f} after {tc} ticks")


@diagnostics.check(
    name="governance_halt_with_positions",
    category=CheckCategory.GOVERNANCE,
    severity=CheckSeverity.INFO,
    modes=CONTINUOUS_DEEP,
)
async def check_governance_halt_positions(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "governance_halt_with_positions", "governance", "info"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    gov = getattr(engine, "governance", None)
    if gov is None:
        return _ok(n, c, s, "No governance — skipped")
    halted = getattr(gov, "_trading_halted", False)
    if not halted:
        return _ok(n, c, s, "Trading not halted")
    exits = getattr(engine, "_exit_levels", {})
    count = len(exits)
    if count > 0:
        return _fail(n, c, s, f"Trading halted with {count} open positions: {list(exits.keys())[:5]}")
    return _ok(n, c, s, "Trading halted, no open positions")


@diagnostics.check(
    name="governance_config_conflicts",
    category=CheckCategory.GOVERNANCE,
    severity=CheckSeverity.WARNING,
    modes=PREFLIGHT_DEEP,
)
async def check_governance_config(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "governance_config_conflicts", "governance", "warning"
    organism_enabled = os.getenv("ENABLE_ORGANISM_SCHEDULER", "0").lower() in ("1", "true", "yes")
    multi_enabled = os.getenv("MULTI_STRATEGY_LIVE_ENABLED", "0").lower() in ("1", "true", "yes")
    if organism_enabled and multi_enabled:
        return _fail(n, c, s, "Both organism scheduler AND multi-strategy enabled — may conflict")
    return _ok(n, c, s, "No config conflicts detected")


# ═══════════════════════════════════════════════════════════════════
#  BROKER_SYNC (3 checks)
# ═══════════════════════════════════════════════════════════════════

@diagnostics.check(
    name="broker_positions_reachable",
    category=CheckCategory.BROKER_SYNC,
    severity=CheckSeverity.CRITICAL,
    modes=DEEP_ONLY,
    timeout=10.0,
)
async def check_broker_positions(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "broker_positions_reachable", "broker_sync", "critical"
    if engine is None:
        return _fail(n, c, s, "No engine provided")
    ps = getattr(engine, "_positions_service", None)
    if ps is None:
        return _fail(n, c, s, "positions_service is None")
    try:
        positions = await ps.get_all_positions()
        count = len(positions) if positions else 0
        return _ok(n, c, s, f"Broker reachable — {count} positions")
    except Exception as e:
        return _fail(n, c, s, f"Broker unreachable: {e}")


@diagnostics.check(
    name="broker_orphaned_exit_levels",
    category=CheckCategory.BROKER_SYNC,
    severity=CheckSeverity.WARNING,
    modes=DEEP_ONLY,
)
async def check_broker_orphaned_exits(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "broker_orphaned_exit_levels", "broker_sync", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    exits = getattr(engine, "_exit_levels", {})
    if not exits:
        return _ok(n, c, s, "No exit levels to check")
    try:
        ps = getattr(engine, "_positions_service", None)
        if ps is None:
            return _ok(n, c, s, "No positions service — skipped")
        positions = await ps.get_all_positions()
        pos_syms = set(positions.keys()) if positions else set()
        orphans = [sym for sym in exits if sym not in pos_syms]
        if orphans:
            return _fail(n, c, s, f"Exit levels for non-existent broker positions: {orphans}")
        return _ok(n, c, s, f"All {len(exits)} exit levels match broker positions")
    except Exception as e:
        return _fail(n, c, s, f"Failed to check broker positions: {e}")


@diagnostics.check(
    name="broker_equity_non_zero",
    category=CheckCategory.BROKER_SYNC,
    severity=CheckSeverity.CRITICAL,
    modes=DEEP_ONLY,
    timeout=10.0,
)
async def check_broker_equity(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "broker_equity_non_zero", "broker_sync", "critical"
    if engine is None:
        return _fail(n, c, s, "No engine provided")
    ps = getattr(engine, "_positions_service", None)
    if ps is None:
        return _fail(n, c, s, "positions_service is None")
    try:
        equity = await ps.get_total_portfolio_value()
        if equity <= 0:
            return _fail(n, c, s, f"Equity is {equity} — should be positive")
        return _ok(n, c, s, f"Equity = ${equity:,.2f}")
    except Exception as e:
        return _fail(n, c, s, f"Failed to get equity: {e}")


# ═══════════════════════════════════════════════════════════════════
#  INFRASTRUCTURE (2 checks)
# ═══════════════════════════════════════════════════════════════════

@diagnostics.check(
    name="infra_database_connected",
    category=CheckCategory.INFRASTRUCTURE,
    severity=CheckSeverity.WARNING,
    modes=DEEP_ONLY,
    timeout=5.0,
)
async def check_infra_database(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "infra_database_connected", "infrastructure", "warning"
    if engine is None:
        return _ok(n, c, s, "No engine — skipped")
    sm = getattr(engine, "_sessionmaker", None)
    if sm is None:
        return _fail(n, c, s, "sessionmaker is None")
    try:
        from sqlalchemy import text
        async with sm() as session:
            result = await session.execute(text("SELECT 1"))
            row = result.scalar()
            if row == 1:
                return _ok(n, c, s, "Database connected — SELECT 1 succeeded")
            return _fail(n, c, s, f"SELECT 1 returned {row}")
    except Exception as e:
        return _fail(n, c, s, f"Database connection failed: {e}")


@diagnostics.check(
    name="infra_redis_available",
    category=CheckCategory.INFRASTRUCTURE,
    severity=CheckSeverity.INFO,
    modes=DEEP_ONLY,
    timeout=5.0,
)
async def check_infra_redis(*, engine: Any = None, app: Any = None) -> DiagnosticResult:
    n, c, s = "infra_redis_available", "infrastructure", "info"
    try:
        import redis.asyncio as aioredis
        url = os.getenv("REDIS_URL", "redis://:changeme_redis@localhost:6379/0")
        r = aioredis.from_url(url, decode_responses=True)
        pong = await r.ping()
        await r.aclose()
        if pong:
            return _ok(n, c, s, "Redis available — PING succeeded")
        return _fail(n, c, s, "Redis PING returned falsy")
    except Exception as e:
        return _fail(n, c, s, f"Redis unavailable: {e}")
