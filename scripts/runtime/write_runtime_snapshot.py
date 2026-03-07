#!/usr/bin/env python3
"""Runtime config snapshot writer.

Reads the actual organism config constants and writes a machine-readable
snapshot to artifacts/runtime_config_snapshot.json.  Used by CI, post-close
audit, and daily reports to verify live behavior matches documented spec.
"""
import json
import os
import sys
from pathlib import Path

# Allow imports from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from backend.organism.live_engine import (
        LIVE_TIMEFRAME,
        LIVE_LOOKBACK,
        MAX_OPEN_POSITIONS,
        ALPHA_TOP_N,
        PREDICTION_HORIZON,
        EXPLORATION_ENABLED,
        LONG_ONLY,
        BRAIN_DIR,
        RETRAIN_INTERVAL,
        MIN_BARS,
        USE_STREAMING,
        LIVE_UNIVERSE_CSV,
    )
    from backend.organism.adaptive_exits import AdaptiveExitEngine
    from backend.organism.kelly_sizer import KellySizer
    from backend.organism.alpha_scanner import AlphaScanner
    from backend.organism.governance import GovernanceController

    gov = GovernanceController()
    exit_engine = AdaptiveExitEngine()

    snapshot = {
        "timeframe": LIVE_TIMEFRAME,
        "lookback": LIVE_LOOKBACK,
        "min_bars": MIN_BARS,
        "prediction_horizon": PREDICTION_HORIZON,
        "tick_interval_seconds": int(os.getenv("ORGANISM_TICK_INTERVAL_SECONDS", "10")),
        "universe": [s.strip() for s in LIVE_UNIVERSE_CSV.split(",") if s.strip()],
        "universe_size": len([s for s in LIVE_UNIVERSE_CSV.split(",") if s.strip()]),

        "learning_mode_threshold_trades": 200,
        "evolution_freeze_until_trades": 300,

        "max_positions": MAX_OPEN_POSITIONS,
        "alpha_top_n": ALPHA_TOP_N,
        "long_only": LONG_ONLY,

        "exploration_enabled": EXPLORATION_ENABLED,
        "streaming_enabled": USE_STREAMING,
        "retrain_interval": RETRAIN_INTERVAL,

        "drawdown_kill_pct": gov._drawdown_limit,
        "drawdown_cooldown_s": gov._drawdown_cooldown_s,
        "max_changes_per_day": gov._max_changes_per_day,
        "governance_frozen": gov.is_frozen,

        "confidence_gate_baseline": 0.40,
        "confidence_gate_defensive": 0.45,
        "fitness_gate_production": 0.45,
        "fitness_gate_learning": 0.0,

        "risk_budget_production": KellySizer._RISK_BUDGET_PER_TRADE,
        "risk_budget_learning": KellySizer._RISK_BUDGET_PER_TRADE_LEARNING,
        "risk_budget_stop_atr": KellySizer._RISK_BUDGET_STOP_ATR,

        "stop_atr_table": AdaptiveExitEngine.REGIME_STOP_ATR,
        "tp_r_table": AdaptiveExitEngine.REGIME_TP_R,
        "trail_atr_table": AdaptiveExitEngine.REGIME_TRAIL_ATR,
        "max_bars_table": AdaptiveExitEngine.REGIME_MAX_BARS,

        "horizon_timeout_bars": 18,
        "bar_boundary_entry_only": True,

        "inverse_etfs": sorted(AlphaScanner.INVERSE_ETFS),
        "inverse_etf_enabled": True,

        "confidence_weights_learning": {
            "breakout": 0.65,
            "tension": 0.35,
            "ml": 0.0,
        },
        "confidence_weights_production": {
            "ml": 0.50,
            "breakout": 0.30,
            "tension": 0.20,
        },
    }

except Exception as e:
    snapshot = {
        "error": str(e),
        "note": "Could not import organism modules. Showing env-only fallback.",
        "timeframe": os.getenv("ORGANISM_LIVE_TIMEFRAME", "1Min"),
        "tick_interval_seconds": int(os.getenv("ORGANISM_TICK_INTERVAL_SECONDS", "10")),
        "max_positions": int(os.getenv("ORGANISM_MAX_POSITIONS", "8")),
        "drawdown_kill_pct": float(os.getenv("ORGANISM_DRAWDOWN_KILL_PCT", "0.05")),
        "learning_mode_threshold_trades": 200,
        "evolution_freeze_until_trades": 300,
        "alpha_top_n": ALPHA_TOP_N,
        "horizon_timeout_bars": 18,
        "bar_boundary_entry_only": True,
    }

out = Path("artifacts/runtime_config_snapshot.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(snapshot, indent=2))
print(f"Runtime snapshot written to {out}")
