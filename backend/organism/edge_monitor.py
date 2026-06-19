"""Live edge monitor — realized predictive power of the signal stack.

Audit 2026-06-09 (plan 1.3): the platform tracked expectancy and win rate
but never the one number that distinguishes an edge from luck-plus-risk-
control: the correlation between what the system PREDICTED and what
actually HAPPENED. The project's own forensics found corr ≈ 0.056 (noise)
and anti-predictive high-confidence tails; nothing in the live loop would
have noticed. This module makes that measurement permanent:

- rolling corr(predicted_return, actual_return)
- rolling corr(confidence, correct_direction)
- expectancy / profit factor / win rate, full-sample and rolling
- breakdowns by entry_source and regime_at_entry
- alert evaluation: a mature window with corr <= 0 means the signal adds
  no information — size should not scale with it, and promotion gates
  must not pass it.

Pure functions over trade-history rows (dicts, as read from
``organism_brain/trade_history.csv`` or the in-memory brain history), so
the dashboard route, tests, and offline analysis all share one
implementation.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

DEFAULT_ROLLING_WINDOW = 100
MIN_TRADES_FOR_ALERT = 50


def _truthy(v: Any) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _corr(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation; None when undefined (n<3 or zero variance)."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def _pnl_stats(pnls: list[float]) -> dict[str, Any]:
    n = len(pnls)
    if n == 0:
        return {"n": 0, "total_pnl": 0.0, "expectancy": None,
                "win_rate": None, "profit_factor": None}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_loss = abs(sum(losses))
    return {
        "n": n,
        "total_pnl": round(sum(pnls), 4),
        "expectancy": round(sum(pnls) / n, 6),
        "win_rate": round(len(wins) / n, 4),
        "profit_factor": (
            round(sum(wins) / gross_loss, 4) if gross_loss > 0
            else (math.inf if wins else None)
        ),
    }


def _strategy_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exclude reconciliation bookkeeping rows (mirrors strategy_health)."""
    return [
        r for r in rows
        if not _truthy(r.get("is_reconciliation_artifact", ""))
    ]


def compute_edge_metrics(
    rows: Iterable[dict[str, Any]],
    window: int = DEFAULT_ROLLING_WINDOW,
) -> dict[str, Any]:
    """Compute the edge-monitor payload from trade-history rows."""
    rows = _strategy_rows(rows)

    def _signal_corrs(subset: list[dict[str, Any]]) -> dict[str, Any]:
        # Measurement-integrity audit 2026-06-11:
        # corr_pred_actual uses the SIGNED prediction
        # (predicted_return_signed), only on rows where the ML actually
        # spoke (ml_spoke), and only on horizon-matched exits
        # (horizon_timeout) — the legacy `predicted_return` column is
        # magnitude-only with a 0.01 heuristic default, which made the old
        # correlation meaningless. Rows lacking the new fields (legacy
        # data) are excluded rather than polluting the estimate.
        # corr_conf_win is corr(confidence, trade-won) — the old
        # `corr_conf_correct` name implied directional-prediction skill it
        # never measured; the old key is kept as an alias.
        pred, actual = [], []
        conf, correct = [], []
        for r in subset:
            ps = r.get("predicted_return_signed")
            spoke = str(r.get("ml_spoke", "")).strip().lower() in {
                "1", "true", "yes", "y",
            }
            reason = str(r.get("exit_reason", "")).strip()
            if (
                spoke
                and ps not in (None, "")
                and reason == "horizon_timeout"
            ):
                p = _f(ps)
                a = _f(r.get("actual_return"))
                pred.append(p)
                actual.append(a)
            c = _f(r.get("confidence"), default=-1.0)
            cd = str(r.get("correct_direction", "")).strip().lower()
            if c >= 0 and cd in {"true", "false"}:
                conf.append(c)
                correct.append(1.0 if cd == "true" else 0.0)
        cc = _round_or_none(_corr(conf, correct))
        return {
            "corr_pred_actual": _round_or_none(_corr(pred, actual)),
            "n_pred": len(pred),
            "corr_conf_win": cc,
            # Back-compat alias (same number, honest name above).
            "corr_conf_correct": cc,
            "n_conf": len(conf),
        }

    pnls = [_f(r.get("pnl")) for r in rows]
    recent = rows[-window:] if window and len(rows) > window else rows
    recent_pnls = [_f(r.get("pnl")) for r in recent]

    by_source: dict[str, dict[str, Any]] = {}
    by_regime: dict[str, dict[str, Any]] = {}
    for key_field, bucket in (("entry_source", by_source),
                              ("regime_at_entry", by_regime)):
        groups: dict[str, list[float]] = {}
        for r in rows:
            k = str(r.get(key_field) or "unknown").strip() or "unknown"
            groups.setdefault(k, []).append(_f(r.get("pnl")))
        for k, g in groups.items():
            bucket[k] = _pnl_stats(g)

    return {
        "window": window,
        "full_sample": {**_pnl_stats(pnls), **_signal_corrs(rows)},
        "rolling": {**_pnl_stats(recent_pnls), **_signal_corrs(list(recent))},
        "by_entry_source": by_source,
        "by_regime": by_regime,
    }


def _round_or_none(v: float | None) -> float | None:
    return None if v is None else round(v, 4)


def evaluate_edge_alerts(
    metrics: dict[str, Any],
    min_trades: int = MIN_TRADES_FOR_ALERT,
) -> list[str]:
    """Return alert strings for edge-quality violations on the rolling
    window. Empty list = no alerts. Only fires once the window is mature
    (>= min_trades) so early noise doesn't page anyone."""
    alerts: list[str] = []
    roll = metrics.get("rolling", {})
    n = int(roll.get("n") or 0)
    if n < min_trades:
        return alerts

    cpa = roll.get("corr_pred_actual")
    npred = int(roll.get("n_pred") or 0)
    if cpa is not None and npred >= min_trades and cpa <= 0:
        alerts.append(
            f"NO-EDGE: rolling corr(signed prediction, actual return) = "
            f"{cpa} over {npred} horizon-matched ML trades — the model's "
            f"predictions carry no information; promotion gates must not "
            f"pass and sizing must not scale with confidence."
        )
    elif cpa is None and int(roll.get("n") or 0) >= min_trades:
        alerts.append(
            f"EDGE-UNMEASURED: not enough horizon-matched ML-spoke trades "
            f"to compute corr(pred, actual) (have {npred}, need "
            f"{min_trades}). Legacy rows lack the signed-prediction field "
            f"(added 2026-06-11); the measurement matures as new trades "
            f"accumulate."
        )
    ccc = roll.get("corr_conf_win")
    nconf = int(roll.get("n_conf") or 0)
    if ccc is not None and nconf >= min_trades and ccc <= 0:
        alerts.append(
            f"ANTI-PREDICTIVE CONFIDENCE: rolling corr(confidence, win) "
            f"= {ccc} over {nconf} trades — higher confidence is not "
            f"associated with winning trades."
        )
    pf = roll.get("profit_factor")
    if pf is not None and pf is not math.inf and pf < 1.0:
        alerts.append(
            f"NEGATIVE-EXPECTANCY WINDOW: rolling profit factor {pf} over "
            f"{n} trades."
        )
    return alerts
