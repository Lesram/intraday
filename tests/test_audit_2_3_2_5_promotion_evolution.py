"""Audit 2026-06-09 plans 2.3–2.5 — swap staging, scaler leakage, evolution
guardrails.

2.3: model swaps preserve the incumbent + append an audit record.
2.4: ensemble scalers fit on train rows only.
2.5: shorts re-enable needs 100 observations; regime scale-ups above 1.0
     need 100 regime trades.
"""

import inspect
import json
from types import SimpleNamespace


from backend.organism.self_evolution import EvolutionEngine, EvolvedParams


# ── 2.3 Swap staging ─────────────────────────────────────────────────


def test_apply_result_preserves_incumbent(tmp_path, monkeypatch):
    from backend.organism.background_trainer import BackgroundTrainer

    monkeypatch.setenv("ORGANISM_BRAIN_DIR", str(tmp_path))

    trainer = BackgroundTrainer()
    sig = SimpleNamespace(
        _clf="OLD_CLF", _reg="OLD_REG", _ensemble=None,
        _feature_cols=["a"], _is_trained=True, generation=7,
        _latest_metrics=None,
    )
    result = SimpleNamespace(
        accepted=True,
        new_clf_state=None, new_reg_state=None, new_ensemble_state=None,
        feature_cols=None, is_trained=True, train_metrics={"generation": 8},
        evolved_params_dict=None, rejection_reason=None,
    )
    trainer._last_result = result
    trainer.apply_result(sig, None, "EP", None, None, None, None,
                         total_trades=0)

    prev = tmp_path / "previous_model"
    assert (prev / "clf.pkl").is_file()
    assert (prev / "reg.pkl").is_file()
    meta = json.loads((prev / "metrics.json").read_text())
    assert meta["generation"] == 7

    audit = (tmp_path / "model_swap_audit.jsonl").read_text().strip()
    entry = json.loads(audit.splitlines()[-1])
    assert entry["old_generation"] == 7
    assert entry["rollback_artifacts"] == str(prev)


def test_apply_result_skips_preservation_when_rejected(tmp_path, monkeypatch):
    from backend.organism.background_trainer import BackgroundTrainer

    monkeypatch.setenv("ORGANISM_BRAIN_DIR", str(tmp_path))
    trainer = BackgroundTrainer()
    trainer._last_result = SimpleNamespace(accepted=False)
    trainer.apply_result(SimpleNamespace(), None, "EP", None, None, None, None)
    assert not (tmp_path / "previous_model").exists()


# ── 2.4 Scaler leakage (structural) ──────────────────────────────────


def test_xgb_scaler_fit_inside_folds():
    from backend.models.ensemble_model import XGBoostModel

    src = inspect.getsource(XGBoostModel.train)
    assert "fold_scaler.fit_transform" in src
    assert "self.scaler.fit_transform(features)" not in src, (
        "scaler must not be fit on the full feature set before the split"
    )


def test_lstm_scaler_fit_on_train_rows_only():
    from backend.models.ensemble_model import LSTMModel

    src = inspect.getsource(LSTMModel.train)
    assert "self.scaler.fit(values[:max(1, train_rows)])" in src


# ── 2.5 Evolution guardrails ─────────────────────────────────────────


def _short_trade(pnl):
    return SimpleNamespace(direction=-1, side="short", pnl=pnl)


def test_shorts_not_enabled_on_small_sample():
    eng = EvolutionEngine()
    params = EvolvedParams()
    params.shorts_enabled = False
    changes = {}
    # 20 winning short trades — previously enough to flip shorts on.
    eng._evolve_short_side(params, [_short_trade(50.0)] * 20, changes)
    assert params.short_trade_count == 20
    assert params.shorts_enabled is False, (
        "20 trades must not clear the 100-trade enable bar"
    )


def test_shorts_enabled_with_sufficient_evidence():
    eng = EvolutionEngine()
    params = EvolvedParams()
    params.shorts_enabled = False
    changes = {}
    for _ in range(6):  # 6 epochs x 20 = 120 observations, all winners
        eng._evolve_short_side(params, [_short_trade(50.0)] * 20, changes)
    assert params.short_trade_count >= 100
    assert params.shorts_enabled is True


def test_shorts_disable_not_gated():
    """Risk-REDUCING transitions must not require the evidence bar."""
    eng = EvolutionEngine()
    params = EvolvedParams()
    params.shorts_enabled = True
    params.short_trade_count = 20  # small sample
    params.short_win_rate = 0.30   # bad
    changes = {}
    eng._evolve_short_side(params, [_short_trade(-50.0)] * 10, changes)
    assert params.shorts_enabled is False


def test_regime_scale_up_capped_without_evidence():
    eng = EvolutionEngine()
    params = EvolvedParams()
    regime = next(iter(params.regime_size_scales))
    params.regime_size_scales[regime] = 1.0
    trades = [SimpleNamespace(pnl=10.0)] * 5  # small winning epoch
    for _ in range(30):
        eng._evolve_regime_scales(params, trades, regime, {})
    assert params.regime_size_scales[regime] <= 1.0 + 1e-9, (
        "scale must not exceed 1.0 without >=100 regime trades"
    )


def test_regime_scale_down_never_gated():
    eng = EvolutionEngine()
    params = EvolvedParams()
    regime = next(iter(params.regime_size_scales))
    params.regime_size_scales[regime] = 1.0
    trades = [SimpleNamespace(pnl=-10.0)] * 5
    eng._evolve_regime_scales(params, trades, regime, {})
    assert params.regime_size_scales[regime] < 1.0
