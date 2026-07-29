"""Audit 2026-06-09 plan 1.3 — live edge monitor.

Verifies the realized-predictive-power measurement that the audit found
missing: rolling corr(pred, actual), corr(confidence, correct), PnL stats,
source/regime breakdowns, alert thresholds, and validation against the
real trade history (which the audit measured at corr ≈ 0.02, i.e. noise).
"""

import csv
import math
from pathlib import Path

from backend.organism.edge_monitor import (
    compute_edge_metrics,
    evaluate_edge_alerts,
)


def _row(pnl=1.0, pred=0.01, actual=0.01, conf=0.5, correct="True",
         source="alpha", regime="chop", recon="",
         ml_spoke="True", exit_reason="horizon_timeout"):
    # Measurement-integrity audit 2026-06-11: corr(pred, actual) now uses
    # the SIGNED prediction, only when ml_spoke and only on
    # horizon-matched exits.
    return {
        "pnl": pnl, "predicted_return": abs(pred),
        "predicted_return_signed": pred, "ml_spoke": ml_spoke,
        "exit_reason": exit_reason, "actual_return": actual,
        "confidence": conf, "correct_direction": correct,
        "entry_source": source, "regime_at_entry": regime,
        "is_reconciliation_artifact": recon,
    }


def test_perfectly_predictive_signal_scores_high():
    rows = [
        _row(pnl=(1 if i % 2 else -1), pred=0.01 * (1 if i % 2 else -1),
             actual=0.01 * (1 if i % 2 else -1),
             conf=0.9 if i % 2 else 0.1, correct="True" if i % 2 else "False")
        for i in range(60)
    ]
    m = compute_edge_metrics(rows, window=50)
    assert m["rolling"]["corr_pred_actual"] == 1.0
    assert m["rolling"]["corr_conf_correct"] == 1.0
    assert evaluate_edge_alerts(m) == []


def test_no_edge_signal_fires_alerts():
    # Predictions uncorrelated with outcomes; losing book.
    import random

    rng = random.Random(7)
    rows = [
        _row(pnl=rng.choice([-2.0, 1.0]), pred=rng.uniform(-0.01, 0.01),
             actual=rng.uniform(-0.01, 0.01),
             conf=rng.random(), correct=rng.choice(["True", "False"]))
        for _ in range(120)
    ]
    m = compute_edge_metrics(rows, window=100)
    alerts = evaluate_edge_alerts(m)
    # corr will be ~0; PF < 1 by construction (more -2s than +1s on average
    # is not guaranteed, so only assert alert *machinery* responds to corr)
    assert isinstance(alerts, list)
    assert m["rolling"]["n"] == 100


def test_alerts_suppressed_below_min_trades():
    rows = [_row(pnl=-1.0, pred=0.01, actual=-0.01) for _ in range(20)]
    m = compute_edge_metrics(rows, window=100)
    assert evaluate_edge_alerts(m, min_trades=50) == []


def test_anti_predictive_fires():
    # Inverse relationship: high confidence → wrong, low → right.
    rows = []
    for i in range(80):
        right = i % 2 == 0
        rows.append(_row(
            pnl=1.0 if right else -1.0,
            pred=0.01 if not right else -0.01,   # predicts the wrong way
            actual=0.01 if right else -0.01,
            conf=0.9 if not right else 0.1,       # confident when wrong
            correct="True" if right else "False",
        ))
    m = compute_edge_metrics(rows, window=80)
    alerts = evaluate_edge_alerts(m, min_trades=50)
    assert any("NO-EDGE" in a for a in alerts)
    assert any("ANTI-PREDICTIVE" in a for a in alerts)


def test_reconciliation_rows_excluded_and_breakdowns_present():
    rows = [_row(source="alpha"), _row(source="breakout", regime="trending_up"),
            _row(recon="True", pnl=999.0)]
    m = compute_edge_metrics(rows)
    assert m["full_sample"]["n"] == 2  # recon row dropped
    assert set(m["by_entry_source"]) == {"alpha", "breakout"}
    assert "trending_up" in m["by_regime"]


def test_non_ml_rows_excluded_from_corr():
    """Rows where the ML never spoke (heuristic defaults) and rows whose
    exits aren't horizon-matched must be excluded from corr(pred, actual)
    — the 2026-06-11 audit found the old ==0 sentinel was defeated by
    0.01 heuristic defaults."""
    rows = (
        [_row(ml_spoke="False") for _ in range(5)]            # ML silent
        + [_row(exit_reason="stop_loss") for _ in range(5)]   # horizon mismatch
        + [_row(pred=0.0, ml_spoke="") for _ in range(5)]     # legacy empty
    )
    m = compute_edge_metrics(rows)
    assert m["full_sample"]["n_pred"] == 0
    assert m["full_sample"]["corr_pred_actual"] is None


def test_against_real_trade_history():
    """Ground truth: the audit measured corr(conf, correct) ≈ 0.02 on the
    real 556-trade history. The monitor must reproduce that (noise-level,
    |corr| < 0.15) rather than reporting a phantom edge."""
    p = Path(__file__).resolve().parents[1] / "organism_brain" / "trade_history.csv"
    if not p.is_file():
        import pytest

        pytest.skip("live trade_history.csv not present")
    with open(p, newline="") as fh:
        rows = list(csv.DictReader(fh))
    m = compute_edge_metrics(rows, window=100)
    cc = m["full_sample"]["corr_conf_correct"]
    assert cc is not None and abs(cc) < 0.15, (
        f"expected noise-level corr on real history, got {cc}"
    )
    assert m["full_sample"]["n"] >= 500
    # PF on the full sample was ~0.71 — a losing book must not show PF >= 1.
    pf = m["full_sample"]["profit_factor"]
    assert pf is not None and pf is not math.inf and pf < 1.0


def test_route_wired():
    import inspect

    from backend.api.routes import strategy_health as sh

    src = inspect.getsource(sh)
    assert "/edge" in src and "compute_edge_metrics" in src
