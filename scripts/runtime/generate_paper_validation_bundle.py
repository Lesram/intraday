#!/usr/bin/env python3
"""Generate a daily paper-validation evidence bundle.

Reads trading data from:
  1. organism_brain/trade_history.csv  -- completed trades
  2. organism_brain/manifest.json      -- brain metadata
  3. /api/v1/organism/status           -- live engine state (optional)
  4. artifacts/resolved_config_snapshot.json -- resolved runtime config (preferred)
  5. Code defaults                     -- config constants (fallback)

Outputs 8 files under docs/engineering/paper_validation/<DATE>-<SHA>/:
  daily_runtime_snapshot.json
  daily_trading_report.md
  daily_trade_log.json
  daily_exit_breakdown.json
  daily_entry_breakdown.json
  daily_model_quality.json
  daily_signal_quality.json
  daily_kpi_summary.json

Usage:
  python scripts/runtime/generate_paper_validation_bundle.py [--date YYYY-MM-DD] [--lifetime]

If --date is omitted, defaults to today.
If --lifetime is set, includes all trades (not just today's).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BRAIN_DIR = ROOT / "organism_brain"

REQUIRED_BUNDLE_FILES = [
    "daily_runtime_snapshot.json",
    "daily_trade_log.json",
    "daily_exit_breakdown.json",
    "daily_entry_breakdown.json",
    "daily_model_quality.json",
    "daily_signal_quality.json",
]


# -- Helpers ----------------------------------------------------------------

def _verify_bundle_files(bundle_dir: Path) -> bool:
    """Check that all required bundle files exist and are non-empty."""
    for name in REQUIRED_BUNDLE_FILES:
        p = bundle_dir / name
        if not p.is_file() or p.stat().st_size == 0:
            return False
    return True


def _load_evaluation_event_history() -> list[dict]:
    """Load evaluation event history from brain dir."""
    path = BRAIN_DIR / "evaluation_event_history.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True, cwd=ROOT, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
    except Exception:
        return "unknown"


def _load_trades_csv() -> list[dict]:
    """Load trade_history.csv from brain dir."""
    path = BRAIN_DIR / "trade_history.csv"
    if not path.exists():
        return []
    trades = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Parse numeric fields
            for k in ["direction", "entry_price", "exit_price", "pnl",
                       "predicted_return", "actual_return", "confidence",
                       "mfe", "mae", "time_in_trade_seconds"]:
                if k in row:
                    try:
                        row[k] = float(row[k])
                    except (ValueError, TypeError):
                        row[k] = 0.0
            for k in ["entry_bar", "exit_bar", "shares", "bars_held_at_exit"]:
                if k in row:
                    try:
                        row[k] = int(row[k])
                    except (ValueError, TypeError):
                        row[k] = 0
            for k in ["correct_direction", "is_exploration"]:
                if k in row:
                    row[k] = str(row[k]).lower() in ("true", "1", "yes")
            # closed_at is a string field -- read as-is (J2)
            if "closed_at" not in row:
                row["closed_at"] = ""
            trades.append(row)
    return trades


def _load_manifest() -> dict:
    path = BRAIN_DIR / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _load_ml_state() -> dict:
    path = BRAIN_DIR / "ml_state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _load_learning_state() -> dict:
    path = BRAIN_DIR / "learning_state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _load_governance_state() -> dict:
    path = BRAIN_DIR / "governance_state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _query_organism_status() -> dict | None:
    """Try to query the running organism API."""
    base = os.getenv("ORGANISM_API_BASE", "http://localhost:8000")
    # Auth
    token = ""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{base}/api/v1/auth/login",
            data=json.dumps({
                "username": os.getenv("INTRA_API_USER", "admin@example.com"),
                "password": os.getenv("INTRA_API_PASSWORD", "admin123"),
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            token = json.loads(resp.read()).get("access_token", "")
    except Exception:
        pass

    for path in ["/api/v1/organism/status", "/api/organism/status"]:
        try:
            cmd = ["curl", "-s", "--max-time", "5", f"{base}{path}"]
            if token:
                cmd += ["-H", f"Authorization: Bearer {token}"]
            out = subprocess.check_output(
                cmd, text=True, stderr=subprocess.DEVNULL, timeout=10,
            ).strip()
            if out:
                data = json.loads(out)
                if "detail" not in data:
                    return data
        except Exception:
            continue
    return None


def _build_defaults() -> dict:
    """Get code defaults (same as write_runtime_snapshot)."""
    try:
        from backend.organism.live_engine import (
            LIVE_TIMEFRAME, MAX_OPEN_POSITIONS, ALPHA_TOP_N,
            EXPLORATION_ENABLED, LIVE_UNIVERSE_CSV,
        )
        return {
            "timeframe": LIVE_TIMEFRAME,
            "max_positions": MAX_OPEN_POSITIONS,
            "alpha_top_n": ALPHA_TOP_N,
            "exploration_enabled": EXPLORATION_ENABLED,
            "universe_size": len([s for s in LIVE_UNIVERSE_CSV.split(",") if s.strip()]),
            "learning_mode_threshold_trades": 200,
            "evolution_freeze_until_trades": 300,
        }
    except Exception as e:
        return {"error": str(e)}


def _load_resolved_snapshot() -> dict | None:
    """Load the resolved runtime config snapshot if available."""
    path = ROOT / "artifacts" / "resolved_config_snapshot.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _get_runtime_sha() -> str | None:
    """Try to get the deployed SHA from the running container."""
    try:
        container = subprocess.check_output(
            ["docker", "ps", "--filter", "name=intra-api", "--format", "{{.Names}}"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip().split("\n")[0]
        if not container:
            return None
        sha = subprocess.check_output(
            ["docker", "exec", container, "git", "rev-parse", "--short", "HEAD"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
        return sha if sha else None
    except Exception:
        return None


def _extract_unrealized_pnl(api_status: dict | None) -> float | None:
    """Extract unrealized PnL from API status, checking multiple locations."""
    if api_status is None:
        return None
    # Direct field
    if "unrealized_pnl" in api_status:
        return api_status["unrealized_pnl"]
    # Nested in live_engine.engine
    if isinstance(api_status.get("live_engine"), dict):
        engine = api_status["live_engine"].get("engine", {})
        if isinstance(engine, dict) and "unrealized_pnl" in engine:
            return engine["unrealized_pnl"]
    # Check for open_positions_pnl
    if "open_positions_pnl" in api_status:
        return api_status["open_positions_pnl"]
    return None


def _filter_trades_by_date(trades: list[dict], date: str) -> tuple[list[dict], int]:
    """Filter trades to only those closed on the given date.

    Returns (filtered_trades, legacy_excluded_count).
    Legacy trades without closed_at are excluded from daily bundles.
    """
    filtered = []
    legacy_count = 0
    for t in trades:
        closed_at = t.get("closed_at", "")
        if not closed_at:
            legacy_count += 1
            continue
        # Compare date portion of ISO timestamp
        try:
            trade_date = closed_at[:10]  # "YYYY-MM-DD" from ISO
            if trade_date == date:
                filtered.append(t)
        except (ValueError, IndexError):
            legacy_count += 1
    return filtered, legacy_count


# -- Bundle Generators ------------------------------------------------------

def generate_runtime_snapshot(
    trades: list[dict], day_trades: list[dict], manifest: dict,
    api_status: dict | None, sha: str, date: str,
) -> dict:
    """A. daily_runtime_snapshot.json"""
    resolved = _load_resolved_snapshot()
    governance = _load_governance_state()
    total_trades = len(trades)
    is_learning = total_trades < 200

    if resolved:
        res = resolved.get("resolved", {})
        snap = {
            "date": date,
            "deployed_sha": sha,
            "snapshot_taken_at": datetime.now(timezone.utc).isoformat(),
            "snapshot_source": "resolved_config_snapshot",
            "timeframe": res.get("timeframe", "1Min"),
            "timeframe_source": res.get("timeframe_source", "unknown"),
            "universe_size": res.get("universe_size", 22),
            "max_positions": res.get("max_positions", 8),
            "alpha_top_n": res.get("alpha_top_n", 5),
            "tick_interval_seconds": res.get("tick_interval_seconds", 10),
            "exploration_enabled": res.get("exploration_enabled", False),
            "drawdown_kill_pct": res.get("drawdown_kill_pct", 0.05),
            "risk_budget_learning": res.get("risk_budget_learning", 0.001),
            "risk_budget_production": res.get("risk_budget_production", 0.0025),
            "confidence_gate_baseline": res.get("confidence_gate_baseline", 0.4),
            "fitness_gate_production": res.get("fitness_gate_production", 0.45),
            "horizon_timeout_bars": res.get("horizon_timeout_bars", 18),
            "learning_mode": is_learning,
            "total_trades_lifetime": total_trades,
            "total_trades_today": len(day_trades),
            "evolution_freeze": total_trades < 300,
            "ml_trained": manifest.get("ml_is_trained", False),
            "brain_generation": manifest.get("generation", 0),
            "brain_total_runs": manifest.get("total_runs", 0),
        }
    else:
        defaults = _build_defaults()
        snap = {
            "date": date,
            "deployed_sha": sha,
            "snapshot_taken_at": datetime.now(timezone.utc).isoformat(),
            "snapshot_source": "code_defaults",
            "timeframe": defaults.get("timeframe", "1Min"),
            "universe_size": defaults.get("universe_size", 22),
            "max_positions": defaults.get("max_positions", 8),
            "alpha_top_n": defaults.get("alpha_top_n", 5),
            "exploration_enabled": defaults.get("exploration_enabled", False),
            "drawdown_kill_pct": governance.get("drawdown_limit", 0.05),
            "learning_mode": is_learning,
            "total_trades_lifetime": total_trades,
            "total_trades_today": len(day_trades),
            "evolution_freeze": total_trades < 300,
            "ml_trained": manifest.get("ml_is_trained", False),
            "brain_generation": manifest.get("generation", 0),
            "brain_total_runs": manifest.get("total_runs", 0),
        }

    if api_status:
        snap["api_reachable"] = True
        snap["api_tick_count"] = api_status.get("tick_count")
        snap["api_total_trades"] = api_status.get("total_trades")
        snap["api_ml_trained"] = api_status.get("ml_trained")
        snap["api_learning_mode"] = api_status.get("learning_mode")
        snap["api_regime"] = api_status.get("regime")
        snap["api_equity"] = api_status.get("current_equity")
    else:
        snap["api_reachable"] = False

    # SHA verification (J3)
    runtime_sha = _get_runtime_sha()
    snap["local_bundle_sha"] = sha
    snap["runtime_reported_sha"] = runtime_sha if runtime_sha else "unknown"
    snap["sha_match"] = (sha == runtime_sha) if runtime_sha else "unknown"

    return snap


def generate_trade_log(trades: list[dict]) -> list[dict]:
    """C. daily_trade_log.json -- every completed trade."""
    log = []
    for t in trades:
        log.append({
            "symbol": t.get("symbol", ""),
            "direction": t.get("direction", 0),
            "entry_source": t.get("entry_source", ""),
            "regime_at_entry": t.get("regime_at_entry", ""),
            "regime_at_exit": t.get("regime_at_exit", ""),
            "confidence": t.get("confidence", 0),
            "predicted_return": t.get("predicted_return", 0),
            "actual_return": t.get("actual_return", 0),
            "pnl": t.get("pnl", 0),
            "exit_reason": t.get("exit_reason", ""),
            "mfe": t.get("mfe", 0),
            "mae": t.get("mae", 0),
            "bars_held_at_exit": t.get("bars_held_at_exit", 0),
            "time_in_trade_seconds": t.get("time_in_trade_seconds", 0),
            "is_exploration": t.get("is_exploration", False),
            "closed_at": t.get("closed_at", ""),
        })
    return log


def generate_exit_breakdown(trades: list[dict]) -> dict:
    """D. daily_exit_breakdown.json -- aggregate by exit reason."""
    by_exit: dict[str, list[dict]] = {}
    for t in trades:
        reason = t.get("exit_reason", "unknown")
        by_exit.setdefault(reason, []).append(t)

    breakdown = {}
    for reason, group in sorted(by_exit.items()):
        pnls = [t["pnl"] for t in group]
        wins = [p for p in pnls if p > 0]
        hold_times = [t.get("time_in_trade_seconds", 0) for t in group]
        breakdown[reason] = {
            "count": len(group),
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0,
            "win_rate": round(len(wins) / len(pnls), 4) if pnls else 0,
            "avg_hold_time_seconds": round(sum(hold_times) / len(hold_times), 1) if hold_times else 0,
        }
    return breakdown


def generate_entry_breakdown(trades: list[dict]) -> dict:
    """E. daily_entry_breakdown.json -- aggregate by entry source."""
    by_source: dict[str, list[dict]] = {}
    for t in trades:
        src = t.get("entry_source", "unknown") or "unknown"
        by_source.setdefault(src, []).append(t)

    breakdown = {}
    for source, group in sorted(by_source.items()):
        pnls = [t["pnl"] for t in group]
        wins = [p for p in pnls if p > 0]
        confs = [t.get("confidence", 0) for t in group]
        pred_rets = [t.get("predicted_return", 0) for t in group]
        breakdown[source] = {
            "count": len(group),
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0,
            "win_rate": round(len(wins) / len(pnls), 4) if pnls else 0,
            "avg_confidence": round(sum(confs) / len(confs), 4) if confs else 0,
            "avg_predicted_return": round(sum(pred_rets) / len(pred_rets), 6) if pred_rets else 0,
        }
    return breakdown


def generate_model_quality(
    manifest: dict, ml_state: dict, learning_state: dict,
    date: str = "",
    evaluation_event_history: list[dict] | None = None,
) -> dict:
    """F. daily_model_quality.json"""
    # System-level calibration from ml_state persisted bins
    cal = ml_state.get("calibration", {})
    cal_counts = cal.get("counts", [])
    cal_map = cal.get("map", [])
    cal_total = sum(c[1] for c in cal_counts) if cal_counts else 0
    cal_correct = sum(c[0] for c in cal_counts) if cal_counts else 0

    # Check monotonicity from map
    cal_monotonic = True
    populated_bins = [cal_map[i] for i in range(len(cal_map)) if cal_counts[i][1] >= 5] if cal_counts and cal_map else []
    for i in range(1, len(populated_bins)):
        if populated_bins[i] < populated_bins[i - 1]:
            cal_monotonic = False
            break

    # Calibration error (mean absolute difference between bin accuracy and bin midpoint)
    cal_error = 0.0
    n_bins_used = 0
    if cal_counts and cal_map:
        for i, (counts, acc) in enumerate(zip(cal_counts, cal_map)):
            if counts[1] >= 5:
                midpoint = (i + 0.5) / len(cal_map)
                cal_error += abs(acc - midpoint)
                n_bins_used += 1
    if n_bins_used > 0:
        cal_error = round(cal_error / n_bins_used, 4)

    # Latest candidate calibration from model_metrics_history
    metrics_history = ml_state.get("model_metrics_history", [])
    latest_candidate = {}
    if metrics_history:
        latest = metrics_history[-1]
        latest_candidate = {
            "candidate_calibration_sample_count": latest.get("candidate_calibration_sample_count", 0),
            "candidate_calibration_monotonic": latest.get("candidate_calibration_monotonic", True),
            "candidate_calibration_error": latest.get("candidate_calibration_error", 0.0),
            "model_accuracy": latest.get("accuracy"),
            "model_sharpe": latest.get("sharpe"),
            "accepted": latest.get("accepted"),
        }

    # Acceptance/rejection event accounting (J4)
    if evaluation_event_history:
        # Real evaluation-event history -- includes both accepted and rejected
        lifetime_accepted = sum(1 for e in evaluation_event_history if e.get("accepted", False))
        lifetime_rejected = sum(1 for e in evaluation_event_history if not e.get("accepted", True))
        today_accepted = 0
        today_rejected = 0
        today_evaluations = 0
        for e in evaluation_event_history:
            eval_at = e.get("evaluated_at", "")
            if eval_at and eval_at[:10] == date:
                today_evaluations += 1
                if e.get("accepted", False):
                    today_accepted += 1
                else:
                    today_rejected += 1
        acceptance_events = {
            "source": "evaluation_event_history",
            "lifetime_evaluations": len(evaluation_event_history),
            "lifetime_accepted": lifetime_accepted,
            "lifetime_rejected": lifetime_rejected,
            "today_evaluations": today_evaluations,
            "today_accepted": today_accepted,
            "today_rejected": today_rejected,
        }
    else:
        # Fallback: model_metrics_history contains only accepted models (J2/J3 legacy)
        accepted_count = sum(1 for m in metrics_history if m.get("accepted", False))
        rejected_count = sum(1 for m in metrics_history if not m.get("accepted", True))
        today_accepted = 0
        today_rejected = 0
        today_evaluations = 0
        for m in metrics_history:
            eval_at = m.get("evaluated_at", "")
            if eval_at and eval_at[:10] == date:
                today_evaluations += 1
                if m.get("accepted", True):
                    today_accepted += 1
                else:
                    today_rejected += 1
        acceptance_events = {
            "source": "model_metrics_history_accepted_only",
            "note": "Rejection counts may be incomplete -- model_metrics_history primarily contains accepted models.",
            "lifetime_evaluations": len(metrics_history),
            "lifetime_accepted": accepted_count,
            "lifetime_rejected": rejected_count,
            "today_evaluations": today_evaluations,
            "today_accepted": today_accepted,
            "today_rejected": today_rejected,
        }

    return {
        "ml_trained": manifest.get("ml_is_trained", False),
        "ml_generation": ml_state.get("generation", 0),
        "brain_generation": manifest.get("generation", 0),
        "learner_generation": learning_state.get("generation", 0),
        "learner_retrain_count": learning_state.get("retrain_count", 0),
        "learner_best_sharpe": learning_state.get("best_sharpe"),
        "learner_total_trades": learning_state.get("total_trades", 0),
        "learner_cumulative_pnl": learning_state.get("cumulative_pnl", 0),
        "system_calibration": {
            "sample_count": cal_total,
            "correct_count": cal_correct,
            "monotonic": cal_monotonic,
            "error": cal_error,
            "bin_counts": cal_counts,
            "bin_accuracies": cal_map,
        },
        "candidate_calibration": latest_candidate if latest_candidate else {
            "note": "No model evaluations yet (ML not trained).",
        },
        "model_metrics_history_count": len(metrics_history),
        "acceptance_events": acceptance_events,
    }


def generate_signal_quality(trades: list[dict]) -> dict:
    """G. daily_signal_quality.json"""
    # Check if ML predictions are actually available
    trades_with_nonzero_pred = [t for t in trades if t.get("predicted_return", 0) != 0]
    has_predictions = len(trades_with_nonzero_pred) > 0

    # Direction match (only when predictions exist)
    direction_match_rate = None
    if has_predictions:
        matches = sum(
            1 for t in trades_with_nonzero_pred
            if t.get("actual_return", 0) != 0
            and ((t["predicted_return"] > 0 and t["actual_return"] > 0)
                 or (t["predicted_return"] < 0 and t["actual_return"] < 0))
        )
        denom = sum(1 for t in trades_with_nonzero_pred if t.get("actual_return", 0) != 0)
        direction_match_rate = round(matches / denom, 4) if denom > 0 else None

    # Confidence vs outcome (always available since confidence comes from breakout+tension)
    high_conf = [t for t in trades if t.get("confidence", 0) >= 0.5]
    low_conf = [t for t in trades if t.get("confidence", 0) < 0.5]
    high_conf_wr = (
        sum(1 for t in high_conf if t["pnl"] > 0) / len(high_conf)
        if high_conf else None
    )
    low_conf_wr = (
        sum(1 for t in low_conf if t["pnl"] > 0) / len(low_conf)
        if low_conf else None
    )

    # Confidence quintile analysis
    quintiles = []
    if trades:
        sorted_trades = sorted(trades, key=lambda t: t.get("confidence", 0))
        n = len(sorted_trades)
        for qi in range(5):
            start = n * qi // 5
            end = n * (qi + 1) // 5
            bucket = sorted_trades[start:end]
            if bucket:
                confs = [t.get("confidence", 0) for t in bucket]
                pnls = [t["pnl"] for t in bucket]
                bucket_wins = sum(1 for p in pnls if p > 0)
                quintiles.append({
                    "quintile": qi + 1,
                    "count": len(bucket),
                    "confidence_range": [round(min(confs), 4), round(max(confs), 4)],
                    "avg_confidence": round(sum(confs) / len(confs), 4),
                    "win_rate": round(bucket_wins / len(bucket), 4),
                    "avg_pnl": round(sum(pnls) / len(pnls), 2),
                    "total_pnl": round(sum(pnls), 2),
                })

    result = {
        "ml_predictions_available": has_predictions,
        "total_trades": len(trades),
        "total_trades_with_predictions": len(trades_with_nonzero_pred),
        "predicted_return_direction_match_rate": direction_match_rate,
        "ranking_quality_available": False,
        "ranking_quality_note": "Per-tick candidate ranking data requires engine decision logs, not available in trade history.",
    }

    if high_conf is not None or low_conf is not None:
        result["high_confidence_trades"] = len(high_conf)
        result["high_confidence_win_rate"] = round(high_conf_wr, 4) if high_conf_wr is not None else None
        result["low_confidence_trades"] = len(low_conf)
        result["low_confidence_win_rate"] = round(low_conf_wr, 4) if low_conf_wr is not None else None
        result["confidence_correlated_with_outcome"] = (
            high_conf_wr > low_conf_wr
            if high_conf_wr is not None and low_conf_wr is not None
            else None
        )
        result["confidence_quintiles"] = quintiles

    return result


def generate_kpi_summary(
    trades: list[dict], exit_breakdown: dict, date: str, sha: str,
    *, bundle_files_ok: bool = True, api_reachable: bool = False,
    legacy_excluded: int = 0, runtime_stale: bool = False,
) -> dict:
    """H. daily_kpi_summary.json"""
    total = len(trades)
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    realized_pnl = sum(pnls)
    win_rate = len(wins) / total if total > 0 else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    payoff_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf") if avg_win > 0 else 0

    total_loss = abs(sum(losses))
    total_profit = sum(wins)

    def _exit_loss_share(reason: str) -> float:
        """Share of total loss attributable to this exit reason."""
        if total_loss == 0:
            return 0.0
        reason_losses = sum(
            t["pnl"] for t in trades
            if t.get("exit_reason") == reason and t["pnl"] < 0
        )
        return round(abs(reason_losses) / total_loss, 4)

    def _exit_profit_share(reason: str) -> float:
        """Share of total profit attributable to this exit reason."""
        if total_profit == 0:
            return 0.0
        reason_profits = sum(
            t["pnl"] for t in trades
            if t.get("exit_reason") == reason and t["pnl"] > 0
        )
        return round(reason_profits / total_profit, 4)

    exploration_count = sum(1 for t in trades if t.get("is_exploration", False))

    # Operational pass criteria -- evidence-based (J3)
    operational_checks = {
        "exploration_count_zero": exploration_count == 0,
        "bundle_files_complete": bundle_files_ok,
        "no_stale_runtime": not runtime_stale,
    }

    # API-unreachable policy (J4): API unreachability is a WARNING-ONLY
    # operational note, NOT an operational failure. The bundle is valid
    # without API data -- it degrades gracefully (missing live equity,
    # tick count, etc). This is deliberate: the bundle generator can run
    # from CI or offline environments where the API is not available.
    operational_notes: list[str] = []
    if not api_reachable:
        operational_notes.append("api_not_reachable")
    if legacy_excluded > 0:
        operational_notes.append(f"legacy_trades_excluded={legacy_excluded}")

    passed = all(operational_checks.values())

    # Strategy quality pass -- separate from operational pass (J2)
    strategy_pass = True
    strategy_fail_reasons = []

    if total > 0:
        if payoff_ratio != float("inf") and payoff_ratio <= 1.0:
            strategy_pass = False
            strategy_fail_reasons.append(f"payoff_ratio={round(payoff_ratio, 4)}")

        sl_loss_share = _exit_loss_share("stop_loss")
        if sl_loss_share > 0.60:
            strategy_pass = False
            strategy_fail_reasons.append(f"stop_loss_share={sl_loss_share}")
    else:
        strategy_pass = False
        strategy_fail_reasons.append("no_trades")

    return {
        "date": date,
        "deployed_sha": sha,
        "total_trades": total,
        "realized_pnl": round(realized_pnl, 2),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "payoff_ratio": round(payoff_ratio, 4) if payoff_ratio != float("inf") else "inf",
        "stop_loss_share_of_total_loss": _exit_loss_share("stop_loss"),
        "FTF_share_of_total_loss": _exit_loss_share("failure_to_follow"),
        "trailing_share_of_total_profit": _exit_profit_share("trailing_stop"),
        "horizon_timeout_share_of_total_profit": _exit_profit_share("horizon_timeout"),
        "exploration_execution_count": exploration_count,
        "operational_checks": operational_checks,
        "operational_notes": operational_notes,
        "paper_validation_pass": passed,
        "strategy_quality_pass": strategy_pass,
        "strategy_quality_fail_reasons": strategy_fail_reasons,
    }


def generate_trading_report(
    trades: list[dict], exit_breakdown: dict, entry_breakdown: dict,
    kpi: dict, date: str, sha: str, api_status: dict | None = None,
) -> str:
    """B. daily_trading_report.md"""
    total = kpi["total_trades"]

    # Top winners / losers
    sorted_by_pnl = sorted(trades, key=lambda t: t["pnl"], reverse=True)
    top_winners = sorted_by_pnl[:5]
    top_losers = sorted_by_pnl[-5:][::-1] if len(sorted_by_pnl) > 5 else sorted_by_pnl[::-1]

    # Regime distribution at entry
    regime_dist: dict[str, int] = {}
    for t in trades:
        r = t.get("regime_at_entry", "unknown") or "unknown"
        regime_dist[r] = regime_dist.get(r, 0) + 1

    exploration_count = kpi["exploration_execution_count"]

    lines = [
        f"# Daily Trading Report -- {date}",
        f"",
        f"**Deployed SHA**: `{sha}`",
        f"**Paper Validation**: {'PASS' if kpi['paper_validation_pass'] else 'FAIL'}",
        f"**Strategy Quality**: {'PASS' if kpi['strategy_quality_pass'] else 'FAIL'}",
        f"",
        f"## Summary",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total trades | {total} |",
        f"| Realized PnL | ${kpi['realized_pnl']:.2f} |",
        f"| Win rate | {kpi['win_rate']:.2%} |",
        f"| Avg win | ${kpi['avg_win']:.2f} |",
        f"| Avg loss | ${kpi['avg_loss']:.2f} |",
        f"| Payoff ratio | {kpi['payoff_ratio']} |",
        f"| Unrealized PnL | {'${:.2f}'.format(_extract_unrealized_pnl(api_status)) if _extract_unrealized_pnl(api_status) is not None else 'N/A (not exposed by engine)'} |",
        f"| Exploration count | {exploration_count} |",
        f"",
        f"## Exit Breakdown",
        f"| Exit Reason | Count | Total PnL | Avg PnL | Win Rate |",
        f"|-------------|-------|-----------|---------|----------|",
    ]

    for reason, data in sorted(exit_breakdown.items()):
        lines.append(
            f"| {reason} | {data['count']} | ${data['total_pnl']:.2f} "
            f"| ${data['avg_pnl']:.2f} | {data['win_rate']:.2%} |"
        )

    lines += [
        f"",
        f"## Entry Source Breakdown",
        f"| Source | Count | Total PnL | Avg PnL | Win Rate | Avg Conf |",
        f"|--------|-------|-----------|---------|----------|----------|",
    ]
    for source, data in sorted(entry_breakdown.items()):
        lines.append(
            f"| {source} | {data['count']} | ${data['total_pnl']:.2f} "
            f"| ${data['avg_pnl']:.2f} | {data['win_rate']:.2%} | {data['avg_confidence']:.3f} |"
        )

    lines += [
        f"",
        f"## Regime Distribution at Entry",
        f"| Regime | Count |",
        f"|--------|-------|",
    ]
    for regime, count in sorted(regime_dist.items(), key=lambda x: -x[1]):
        lines.append(f"| {regime} | {count} |")

    lines += [
        f"",
        f"## Top Winners",
        f"| Symbol | PnL | Exit | Source | Conf |",
        f"|--------|-----|------|--------|------|",
    ]
    for t in top_winners[:5]:
        lines.append(
            f"| {t.get('symbol','')} | ${t['pnl']:.2f} | {t.get('exit_reason','')} "
            f"| {t.get('entry_source','')} | {t.get('confidence',0):.3f} |"
        )

    lines += [
        f"",
        f"## Top Losers",
        f"| Symbol | PnL | Exit | Source | Conf |",
        f"|--------|-----|------|--------|------|",
    ]
    for t in top_losers[:5]:
        lines.append(
            f"| {t.get('symbol','')} | ${t['pnl']:.2f} | {t.get('exit_reason','')} "
            f"| {t.get('entry_source','')} | {t.get('confidence',0):.3f} |"
        )

    return "\n".join(lines) + "\n"


# -- Main -------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate paper validation bundle")
    parser.add_argument("--date", default=None, help="Date (YYYY-MM-DD), default today")
    parser.add_argument("--lifetime", action="store_true", help="Include all trades (not just today)")
    args = parser.parse_args()

    date = args.date or datetime.now().strftime("%Y-%m-%d")
    sha = _git_sha()

    # Create output directory
    bundle_dir = ROOT / "docs" / "engineering" / "paper_validation" / f"{date}-{sha}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Load data sources
    all_trades = _load_trades_csv()
    manifest = _load_manifest()
    ml_state = _load_ml_state()
    learning_state = _load_learning_state()
    api_status = _query_organism_status()

    print(f"Loaded {len(all_trades)} trades from brain")
    print(f"API status: {'reachable' if api_status else 'not reachable'}")

    # Filter to daily trades
    if args.lifetime:
        day_trades = all_trades
        legacy_excluded = 0
    else:
        day_trades, legacy_excluded = _filter_trades_by_date(all_trades, date)

    if legacy_excluded > 0:
        print(f"Excluded {legacy_excluded} legacy trades without closed_at timestamp")
    print(f"Day trades: {len(day_trades)}, Lifetime trades: {len(all_trades)}")

    # Generate all 8 files

    # A. Runtime snapshot (uses both lifetime + day counts)
    runtime = generate_runtime_snapshot(all_trades, day_trades, manifest, api_status, sha, date)
    (bundle_dir / "daily_runtime_snapshot.json").write_text(
        json.dumps(runtime, indent=2)
    )

    # C. Trade log
    trade_log = generate_trade_log(day_trades)
    (bundle_dir / "daily_trade_log.json").write_text(
        json.dumps(trade_log, indent=2)
    )

    # D. Exit breakdown
    exit_breakdown = generate_exit_breakdown(day_trades)
    (bundle_dir / "daily_exit_breakdown.json").write_text(
        json.dumps(exit_breakdown, indent=2)
    )

    # E. Entry breakdown
    entry_breakdown = generate_entry_breakdown(day_trades)
    (bundle_dir / "daily_entry_breakdown.json").write_text(
        json.dumps(entry_breakdown, indent=2)
    )

    # F. Model quality
    eval_event_history = _load_evaluation_event_history()
    model_quality = generate_model_quality(
        manifest, ml_state, learning_state, date=date,
        evaluation_event_history=eval_event_history,
    )
    (bundle_dir / "daily_model_quality.json").write_text(
        json.dumps(model_quality, indent=2)
    )

    # G. Signal quality
    signal_quality = generate_signal_quality(day_trades)
    (bundle_dir / "daily_signal_quality.json").write_text(
        json.dumps(signal_quality, indent=2)
    )

    # Check if runtime is stale (from API status if available) (J3)
    runtime_stale = False
    if api_status:
        live_engine = api_status.get("live_engine", {})
        if isinstance(live_engine, dict):
            engine_status = live_engine.get("engine", {})
            if isinstance(engine_status, dict):
                runtime_stale = engine_status.get("data_stale", False)

    # H. KPI summary
    bundle_files_ok = _verify_bundle_files(bundle_dir)
    kpi = generate_kpi_summary(
        day_trades, exit_breakdown, date, sha,
        bundle_files_ok=bundle_files_ok,
        api_reachable=api_status is not None,
        legacy_excluded=legacy_excluded,
        runtime_stale=runtime_stale,
    )
    (bundle_dir / "daily_kpi_summary.json").write_text(
        json.dumps(kpi, indent=2)
    )

    # B. Trading report (last, needs breakdowns + kpi)
    report = generate_trading_report(
        day_trades, exit_breakdown, entry_breakdown, kpi, date, sha,
        api_status=api_status,
    )
    (bundle_dir / "daily_trading_report.md").write_text(report)

    # Print summary
    print(f"\nBundle written to: {bundle_dir.relative_to(ROOT)}")
    print(f"Date: {date}")
    print(f"SHA: {sha}")
    print(f"Trades (day): {kpi['total_trades']}, PnL: ${kpi['realized_pnl']:.2f}, "
          f"WR: {kpi['win_rate']:.2%}")
    print(f"Operational pass: {kpi['paper_validation_pass']}, "
          f"Strategy pass: {kpi['strategy_quality_pass']}")


if __name__ == "__main__":
    main()
