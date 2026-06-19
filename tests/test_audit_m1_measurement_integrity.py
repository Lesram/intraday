"""Measurement-integrity audit 2026-06-11 — fidelity-field fixes.

Findings fixed and pinned here:
M-1 partial exits: positions that scale out are flagged (had_partial_exits)
    so their approximate single-row PnL is segregable.
M-2 signed prediction: predicted_return_signed + ml_spoke preserve what the
    legacy abs()-ed, 0.01-defaulted predicted_return destroyed.
M-3 price_source: rows priced from bar-close/quote fallbacks (not broker
    fills) are identifiable.
M-4 real MAE: ExitLevels tracks worst_adverse; the record uses it over the
    static stop-distance proxy.
M-5 edge monitor: corr(pred, actual) uses signed+ml_spoke+horizon-matched
    rows only; corr_conf_win honestly labeled.
M-6 stub metadata: recovered positions carry entry_source/regime.
"""

import inspect

from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels
from backend.organism.continuous_learner import TradeRecord
from backend.organism.live_engine import OrganismLiveEngine


# ── M-2/M-1/M-3 schema + persistence roundtrip ───────────────────────


def test_trade_record_fidelity_fields_default_safe():
    t = TradeRecord(
        symbol="X", direction=1.0, entry_price=10, exit_price=11,
        entry_bar=0, exit_bar=1, shares=5, pnl=5.0, exit_reason="stop_loss",
        predicted_return=0.01, actual_return=0.1, confidence=0.5,
    )
    assert t.predicted_return_signed is None
    assert t.ml_spoke is False
    assert t.price_source == ""
    assert t.had_partial_exits is False


def test_persistence_roundtrip_of_fidelity_fields(tmp_path):
    import pandas as pd

    from backend.organism.brain_persistence import (
        _float_or_none,
        _truthy_cell,
    )

    # CSV cells come back as strings/NaN — the parsers must be tolerant.
    assert _float_or_none("-0.0123") == -0.0123
    assert _float_or_none("") is None
    assert _float_or_none(float("nan")) is None
    assert _truthy_cell("True") and not _truthy_cell("") \
        and not _truthy_cell("nan")

    # Save-path emits the new columns.
    from backend.organism import brain_persistence as bp

    src = inspect.getsource(bp.OrganismBrain._save_trade_history)
    for col in ("predicted_return_signed", "ml_spoke", "price_source",
                "had_partial_exits"):
        assert col in src, f"save path must persist {col}"


def test_entry_candidates_carry_signed_prediction():
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert src.count("predicted_return_signed") >= 3, (
        "alpha + breakout candidates and entry metadata must carry the "
        "signed prediction"
    )
    assert "ml_spoke" in src


def test_exit_price_ladder_tags_source():
    src = inspect.getsource(OrganismLiveEngine._reconcile_fills)
    for tag in ('"fill"', '"db_fill"', '"bar_close"', '"quote_mid"'):
        assert tag in src, f"exit-price ladder must tag {tag}"
    assert "price_source=_price_source" in src


def test_partial_exit_sets_flag():
    src = inspect.getsource(OrganismLiveEngine._submit_exit_order)
    assert "had_partial_exits" in src
    assert '"partial" in reason' in src


# ── M-4 real MAE ─────────────────────────────────────────────────────


def _levels(entry=100.0, direction=1.0):
    return ExitLevels(
        symbol="X", direction=direction, entry_price=entry,
        stop_loss=entry - 2, take_profit=entry + 6, trailing_stop=entry - 2,
        atr_at_entry=1.0, regime_at_entry="chop", highest_favorable=entry,
    )


def test_worst_adverse_tracked_long():
    eng = AdaptiveExitEngine.for_timeframe("1Min")
    lvl = _levels(100.0, 1.0)
    for px in (100.5, 99.2, 101.0, 98.7, 103.0):
        eng.check_exit(lvl, px, current_regime="chop", is_new_bar=False)
    assert lvl.worst_adverse == 98.7
    assert lvl.highest_favorable == 103.0


def test_worst_adverse_serialized():
    lvl = _levels()
    lvl.worst_adverse = 98.7
    assert lvl.to_dict()["worst_adverse"] == 98.7


def test_record_uses_real_mae_when_available():
    src = inspect.getsource(OrganismLiveEngine._reconcile_fills)
    assert "worst_adverse" in src, "record must prefer the tracked MAE"
    assert "_stop_dist * shares" in src, "legacy proxy kept as fallback"


# ── M-6 stub metadata ────────────────────────────────────────────────


def test_stub_metadata_carries_source_and_regime():
    src = inspect.getsource(OrganismLiveEngine._check_tick_invariants)
    assert '"entry_source": "stub_recovered"' in src
    assert '"regime_at_entry"' in src


# ── M-5 edge monitor semantics ───────────────────────────────────────


def test_monitor_corr_requires_spoke_signed_and_horizon():
    from backend.organism.edge_monitor import compute_edge_metrics

    # A heuristic-default row (the old poison: predicted_return=0.01,
    # no signed field) must NOT enter the correlation.
    legacy_poison = [{
        "pnl": 1.0, "predicted_return": 0.01, "actual_return": 0.05,
        "confidence": 0.5, "correct_direction": "True",
        "entry_source": "alpha", "regime_at_entry": "chop",
        "is_reconciliation_artifact": "", "exit_reason": "stop_loss",
    } for _ in range(30)]
    m = compute_edge_metrics(legacy_poison)
    assert m["full_sample"]["n_pred"] == 0

    # A proper ML-spoke, horizon-matched negative prediction counts —
    # and the SIGN must matter.
    rows = []
    for i in range(30):
        neg = i % 2 == 0
        rows.append({
            "pnl": -1.0 if neg else 1.0,
            "predicted_return": 0.02,                  # legacy abs column
            "predicted_return_signed": -0.02 if neg else 0.02,
            "ml_spoke": "True",
            "actual_return": -0.02 if neg else 0.02,   # perfectly tracked
            "confidence": 0.5, "correct_direction": "True",
            "entry_source": "alpha", "regime_at_entry": "chop",
            "is_reconciliation_artifact": "",
            "exit_reason": "horizon_timeout",
        })
    m2 = compute_edge_metrics(rows)
    assert m2["full_sample"]["n_pred"] == 30
    assert m2["full_sample"]["corr_pred_actual"] == 1.0, (
        "signed predictions tracking signed outcomes must show corr=1 — "
        "the legacy abs() column would have shown ~0"
    )


def test_monitor_reports_unmeasured_not_false_negative():
    from backend.organism.edge_monitor import (
        compute_edge_metrics,
        evaluate_edge_alerts,
    )

    # 60 trades, none ML-horizon-matched → corr must be None and the
    # alert must say UNMEASURED, not NO-EDGE.
    rows = [{
        "pnl": 1.0, "predicted_return": 0.01, "actual_return": 0.05,
        "confidence": 0.5, "correct_direction": "True",
        "entry_source": "alpha", "regime_at_entry": "chop",
        "is_reconciliation_artifact": "", "exit_reason": "stop_loss",
    } for _ in range(60)]
    m = compute_edge_metrics(rows, window=50)
    alerts = evaluate_edge_alerts(m)
    assert m["rolling"]["corr_pred_actual"] is None
    assert any("EDGE-UNMEASURED" in a for a in alerts)
    assert not any(a.startswith("NO-EDGE") for a in alerts)
