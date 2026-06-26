"""Log-only retracement shadow exit (Task S, SHADOW_EXIT_AND_CORPUS_BRIEF).

On every live tick, evaluate what the `retracement` exit policy WOULD do on each
open position and log it vs the real exit — accumulating honest forward evidence
toward a future live-exit decision. **Zero effect on real trading.**

Design (all seams verified against live_engine.py):
- Uses the existing AltExitEngine (retracement policy) purely to *evaluate*.
- Keeps a PARALLEL dict of deep-copied ExitLevels per symbol — never calls
  check_exit on the live self._exit_levels (check_exit MUTATES
  highest_favorable / bars_held / trailing and would corrupt real exits).
- Each tick: seed/advance the shadow levels; if retracement says exit and we
  have not already recorded a shadow trigger for that symbol, stash it. When the
  real position later closes, write ONE comparison row (real exit vs shadow exit
  + gross pnl delta) to an append-only JSONL.
- Off by default; best-effort (never raises into the tick).

pnl is computed on a consistent GROSS basis ((exit-entry)*dir*qty) for BOTH the
shadow and the real exit, so the per-trade DELTA is apples-to-apples and not
polluted by a cost-model mismatch. real_exit_reason is logged for context.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from backend.infra.runtime_identity import runtime_identity_snapshot
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def _delta_stats(deltas: list[float]) -> dict:
    n = len(deltas)
    if n == 0:
        return {"n": 0, "sum": 0.0, "mean": 0.0, "t_stat": 0.0}
    mean = sum(deltas) / n
    var = sum((x - mean) ** 2 for x in deltas) / (n - 1) if n > 1 else 0.0
    sd = var ** 0.5
    t = (mean / (sd / (n ** 0.5))) if sd > 0 else 0.0
    return {"n": n, "sum": round(sum(deltas), 2), "mean": round(mean, 4),
            "t_stat": round(t, 3)}


def summarize_shadow_telemetry(path: str | Path) -> dict:
    """Cumulative shadow-vs-real gross-delta summary from the telemetry JSONL.

    Shared by the EOD scheduled task and scripts/analyze_shadow_exits.py so the
    Gate-2 accumulation has one source of truth. Returns overall + triggered-only
    delta stats and a per-regime breakdown. Returns {"n": 0} if no telemetry.
    """
    p = Path(path)
    if not p.exists():
        return {"n": 0}
    rows = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
    if not rows:
        return {"n": 0}
    deltas = [float(r.get("delta_gross", 0) or 0) for r in rows]
    trig = [r for r in rows if r.get("shadow_triggered")]
    by_regime: dict[str, dict] = {}
    for r in trig:
        by_regime.setdefault(str(r.get("regime")), {"_d": []})["_d"].append(
            float(r.get("delta_gross", 0) or 0))
    by_regime = {k: _delta_stats(v["_d"]) for k, v in by_regime.items()}
    return {
        "n": len(rows),
        "n_triggered": len(trig),
        "overall": _delta_stats(deltas),
        "triggered": _delta_stats([float(r.get("delta_gross", 0) or 0) for r in trig]),
        "by_regime": by_regime,
    }


class ShadowExitTelemetryRecorder:
    """Append-only JSONL writer for shadow-vs-real exit comparison rows."""

    def __init__(self, path: str | Path, runtime_identity: dict | None = None) -> None:
        self.path = Path(path)
        self.runtime_identity = runtime_identity or runtime_identity_snapshot()
        self.rows_written = 0

    def write(self, row: dict[str, Any]) -> None:
        row = {**row, "runtime_identity": self.runtime_identity}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        self.rows_written += 1


class _ShadowExitMixin:
    """Mixin (no __init__; relies on host OrganismLiveEngine attributes).

    Host must set, when the shadow is enabled: ``_shadow_exit`` (recorder or
    None), ``_shadow_engine`` (AltExitEngine), ``_shadow_levels``,
    ``_shadow_pending``, ``_shadow_prev_syms``, ``_shadow_last_price``,
    ``_shadow_bar_seen``.
    """

    def _shadow_evaluate_exits(self, result: Any) -> None:
        recorder = getattr(self, "_shadow_exit", None)
        if recorder is None:
            return
        # Match production gating so take-profit/horizon behavior aligns.
        self._shadow_engine.learning_mode = self.exit_engine.learning_mode

        prices = getattr(self, "_last_prices", {}) or {}
        regime = getattr(self, "_last_regime", "unknown")
        positions = getattr(self, "_last_positions", {}) or {}
        bar_times = getattr(self, "_last_bar_times", {}) or {}
        tick = getattr(self, "_tick_count", 0)
        ts = ""
        try:
            ts = self._now_fn().isoformat()
        except Exception:  # noqa: BLE001, S110
            pass

        live_levels_map = dict(self._exit_levels)
        current_syms = set(live_levels_map)

        # 1) Advance the shadow eval for every open position.
        for sym, live_levels in live_levels_map.items():
            try:
                if sym not in self._shadow_levels:
                    # Seed from the live history so far; diverges only on logic.
                    self._shadow_levels[sym] = copy.deepcopy(live_levels)
                shadow_levels = self._shadow_levels[sym]
                price = prices.get(sym, shadow_levels.highest_favorable)
                self._shadow_last_price[sym] = price

                bar_t = bar_times.get(sym, "")
                is_new_bar = bool(bar_t) and self._shadow_bar_seen.get(sym) != bar_t
                if bar_t:
                    self._shadow_bar_seen[sym] = bar_t

                sig = self._shadow_engine.check_exit(
                    shadow_levels, price, regime, is_new_bar=is_new_bar
                )
                if sig.should_exit and sym not in self._shadow_pending:
                    entry = float(live_levels.entry_price)
                    d = float(live_levels.direction)
                    qty = abs(float((positions.get(sym) or {}).get("qty", 0)))
                    self._shadow_pending[sym] = {
                        "trigger_tick": tick,
                        "trigger_time": ts,
                        "reason": sig.reason,
                        "price": price,
                        "entry": entry,
                        "direction": d,
                        "qty": qty,
                        "bars_held": int(getattr(shadow_levels, "bars_held", 0)),
                        "per_share": (price - entry) * d,
                        "pnl": (price - entry) * d * qty,
                    }
            except Exception as e:  # best-effort per symbol  # noqa: BLE001
                logger.warning("shadow eval failed for %s: %s", sym, e)

        # 2) Reconcile real closes: any sym seen last tick but gone now.
        for sym in (self._shadow_prev_syms - current_syms):
            try:
                pend = self._shadow_pending.get(sym)
                shadow_levels = self._shadow_levels.get(sym)
                real_exit_price = self._shadow_last_price.get(
                    sym,
                    getattr(shadow_levels, "highest_favorable", 0.0) if shadow_levels else 0.0,
                )
                entry = float(getattr(shadow_levels, "entry_price", 0.0)) if shadow_levels else 0.0
                d = float(getattr(shadow_levels, "direction", 1.0)) if shadow_levels else 1.0
                qty = pend["qty"] if pend else 0.0
                real_per_share = (real_exit_price - entry) * d
                real_pnl = real_per_share * qty
                shadow_triggered = pend is not None
                shadow_pnl = pend["pnl"] if pend else real_pnl  # agreed-held => same
                row = {
                    "schema": "shadow_exit_v1",
                    "symbol": sym,
                    "tick": tick,
                    "timestamp": ts,
                    "policy": getattr(self._shadow_engine, "alt_policy", ""),
                    "retrace_frac": getattr(self._shadow_engine, "alt_retrace_frac", None),
                    "min_fav_r": getattr(self._shadow_engine, "alt_min_fav_r", None),
                    "regime": regime,
                    "entry": round(entry, 4),
                    "direction": d,
                    "qty": qty,
                    "shadow_triggered": shadow_triggered,
                    "shadow_reason": pend["reason"] if pend else "agreed_held_to_real_close",
                    "shadow_exit_price": round(pend["price"], 4) if pend else None,
                    "shadow_bars_held": pend["bars_held"] if pend else None,
                    "shadow_pnl_gross": round(shadow_pnl, 4),
                    "real_exit_price": round(real_exit_price, 4),
                    "real_exit_reason": getattr(self, "_symbol_exit_type", {}).get(sym),
                    "real_pnl_gross": round(real_pnl, 4),
                    "delta_gross": round(shadow_pnl - real_pnl, 4),
                }
                recorder.write(row)
            except Exception as e:  # noqa: BLE001
                logger.warning("shadow reconcile failed for %s: %s", sym, e)
            finally:
                self._shadow_levels.pop(sym, None)
                self._shadow_pending.pop(sym, None)
                self._shadow_last_price.pop(sym, None)
                self._shadow_bar_seen.pop(sym, None)

        self._shadow_prev_syms = current_syms
