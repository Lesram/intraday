#!/usr/bin/env python3
"""Runtime config snapshot writer.

Produces TWO snapshot files:
  artifacts/runtime_defaults_snapshot.json  — code defaults (offline, from source)
  artifacts/resolved_live_runtime_snapshot.json — resolved values from running container

Used by CI, post-close audit, and daily reports to verify live behavior
matches documented spec.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

# Allow imports from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)


def _build_defaults_snapshot() -> dict:
    """Build snapshot from code defaults (no container required)."""
    try:
        from backend.organism.live_engine import (
            LIVE_TIMEFRAME,
            LIVE_LOOKBACK,
            MAX_OPEN_POSITIONS,
            ALPHA_TOP_N,
            PREDICTION_HORIZON,
            EXPLORATION_ENABLED,
            LONG_ONLY,
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

        return {
            "source": "code_defaults",
            "timeframe": LIVE_TIMEFRAME,
            "lookback": LIVE_LOOKBACK,
            "min_bars": MIN_BARS,
            "prediction_horizon": PREDICTION_HORIZON,
            "tick_interval_seconds": 10,
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
                "breakout": 0.65, "tension": 0.35, "ml": 0.0,
            },
            "confidence_weights_production": {
                "ml": 0.50, "breakout": 0.30, "tension": 0.20,
            },
        }

    except Exception as e:
        return {
            "source": "env_fallback",
            "error": str(e),
            "timeframe": os.getenv("ORGANISM_LIVE_TIMEFRAME", "1Min"),
            "tick_interval_seconds": int(os.getenv("ORGANISM_TICK_INTERVAL_SECONDS", "10")),
            "max_positions": int(os.getenv("ORGANISM_MAX_POSITIONS", "8")),
            "drawdown_kill_pct": float(os.getenv("ORGANISM_DRAWDOWN_KILL_PCT", "0.05")),
            "learning_mode_threshold_trades": 200,
            "evolution_freeze_until_trades": 300,
            "alpha_top_n": 5,
            "horizon_timeout_bars": 18,
            "bar_boundary_entry_only": True,
        }


def _build_resolved_live_snapshot() -> dict:
    """Query the running paper-trader container for resolved runtime values.

    Tries in order:
    1. Docker exec into the api container and read env + config
    2. curl the /api/organism/status endpoint
    3. Fall back to .env file parsing + code defaults overlay
    """
    resolved = {"source": "resolved_live"}

    # --- Attempt 1: docker exec env dump ---
    api_container = _find_api_container()
    if api_container:
        env_text = _docker_exec(api_container, "env")
        if env_text:
            env_map = _parse_env_text(env_text)
            resolved["container"] = api_container
            resolved["container_env"] = {
                "ORGANISM_DRAWDOWN_KILL_PCT": env_map.get("ORGANISM_DRAWDOWN_KILL_PCT"),
                "ORGANISM_MAX_POSITIONS": env_map.get("ORGANISM_MAX_POSITIONS"),
                "ORGANISM_TICK_INTERVAL_SECONDS": env_map.get("ORGANISM_TICK_INTERVAL_SECONDS"),
                "ORGANISM_EXPLORATION_ENABLED": env_map.get("ORGANISM_EXPLORATION_ENABLED"),
                "ORGANISM_ALPHA_TOP_N": env_map.get("ORGANISM_ALPHA_TOP_N"),
                "ORGANISM_LIVE_TIMEFRAME": env_map.get("ORGANISM_LIVE_TIMEFRAME"),
                "APP_ENVIRONMENT": env_map.get("APP_ENVIRONMENT"),
                "ALPACA_PAPER": env_map.get("ALPACA_PAPER"),
            }

    # --- Attempt 2: curl organism status ---
    status_json = _curl_organism_status()
    if status_json:
        resolved["organism_status"] = status_json

    # --- Attempt 3: parse .env file ---
    env_file = ROOT / ".env"
    if env_file.exists():
        env_map = _parse_env_file(env_file)
        resolved["dotenv"] = {
            "ORGANISM_DRAWDOWN_KILL_PCT": env_map.get("ORGANISM_DRAWDOWN_KILL_PCT"),
            "ORGANISM_MAX_POSITIONS": env_map.get("ORGANISM_MAX_POSITIONS"),
            "ORGANISM_TICK_INTERVAL_SECONDS": env_map.get("ORGANISM_TICK_INTERVAL_SECONDS"),
            "ORGANISM_EXPLORATION_ENABLED": env_map.get("ORGANISM_EXPLORATION_ENABLED"),
            "ORGANISM_ALPHA_TOP_N": env_map.get("ORGANISM_ALPHA_TOP_N"),
        }

    # --- Resolve final values: container env > .env > code default ---
    defaults = _build_defaults_snapshot()
    container_env = resolved.get("container_env", {})
    dotenv = resolved.get("dotenv", {})

    def _resolve_float(env_key: str, default_key: str) -> float:
        for src in [container_env, dotenv]:
            v = src.get(env_key)
            if v is not None:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
        return defaults.get(default_key, 0.0)

    def _resolve_int(env_key: str, default_key: str) -> int:
        for src in [container_env, dotenv]:
            v = src.get(env_key)
            if v is not None:
                try:
                    return int(v)
                except (ValueError, TypeError):
                    pass
        return defaults.get(default_key, 0)

    def _resolve_bool(env_key: str, default_key: str) -> bool:
        for src in [container_env, dotenv]:
            v = src.get(env_key)
            if v is not None:
                return v.lower() in ("true", "1", "yes")
        return defaults.get(default_key, False)

    resolved["resolved"] = {
        "drawdown_kill_pct": _resolve_float("ORGANISM_DRAWDOWN_KILL_PCT", "drawdown_kill_pct"),
        "max_positions": _resolve_int("ORGANISM_MAX_POSITIONS", "max_positions"),
        "alpha_top_n": _resolve_int("ORGANISM_ALPHA_TOP_N", "alpha_top_n"),
        "tick_interval_seconds": _resolve_int("ORGANISM_TICK_INTERVAL_SECONDS", "tick_interval_seconds"),
        "exploration_enabled": _resolve_bool("ORGANISM_EXPLORATION_ENABLED", "exploration_enabled"),
        "timeframe": defaults.get("timeframe"),
        "learning_mode_threshold_trades": defaults.get("learning_mode_threshold_trades"),
        "evolution_freeze_until_trades": defaults.get("evolution_freeze_until_trades"),
        "horizon_timeout_bars": defaults.get("horizon_timeout_bars"),
        "bar_boundary_entry_only": defaults.get("bar_boundary_entry_only"),
        "confidence_gate_baseline": defaults.get("confidence_gate_baseline"),
        "confidence_gate_defensive": defaults.get("confidence_gate_defensive"),
        "fitness_gate_production": defaults.get("fitness_gate_production"),
        "risk_budget_learning": defaults.get("risk_budget_learning"),
        "risk_budget_production": defaults.get("risk_budget_production"),
        "inverse_etfs": defaults.get("inverse_etfs"),
        "universe_size": defaults.get("universe_size"),
        "confidence_weights_learning": defaults.get("confidence_weights_learning"),
        "confidence_weights_production": defaults.get("confidence_weights_production"),
        "stop_atr_table": defaults.get("stop_atr_table"),
    }

    return resolved


# ── helpers ──────────────────────────────────────────────────────────

def _find_api_container() -> str:
    """Find the running api container name."""
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--filter", "name=api", "--format", "{{.Names}}"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
        for line in out.splitlines():
            if "api" in line:
                return line
    except Exception:
        pass
    return ""


def _docker_exec(container: str, cmd: str) -> str:
    try:
        return subprocess.check_output(
            ["docker", "exec", container, cmd],
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        ).strip()
    except Exception:
        return ""


def _curl_organism_status() -> dict | None:
    try:
        out = subprocess.check_output(
            ["curl", "-s", "--max-time", "5", "http://localhost:8000/api/organism/status"],
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        ).strip()
        if out:
            return json.loads(out)
    except Exception:
        pass
    return None


def _parse_env_text(text: str) -> dict:
    result = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _parse_env_file(path: Path) -> dict:
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            result[k.strip()] = v
    return result


# ── main ─────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Code defaults snapshot
    defaults = _build_defaults_snapshot()
    p1 = ART / "runtime_defaults_snapshot.json"
    p1.write_text(json.dumps(defaults, indent=2))
    print(f"Defaults snapshot written to {p1}")

    # 2. Resolved live snapshot
    resolved = _build_resolved_live_snapshot()
    p2 = ART / "resolved_live_runtime_snapshot.json"
    p2.write_text(json.dumps(resolved, indent=2))
    print(f"Resolved live snapshot written to {p2}")

    # 3. Backward compat: also write the combined file CI expects
    p3 = ART / "runtime_config_snapshot.json"
    p3.write_text(json.dumps(defaults, indent=2))
    print(f"Legacy snapshot written to {p3}")


if __name__ == "__main__":
    main()
