from types import SimpleNamespace

import pandas as pd
import pytest


def _losing_expectancy(n: int = 508) -> dict:
    return {
        "n_trades": n,
        "total_pnl": -642.65,
        "last_50_mean_pnl": -1.2,
        "last_50_win_rate": 0.20,
        "sharpe_ratio_per_trade": -1.05,
    }


def _profitable_expectancy(n: int = 508) -> dict:
    return {
        "n_trades": n,
        "total_pnl": 125.0,
        "last_50_mean_pnl": 0.75,
        "last_50_win_rate": 0.44,
        "sharpe_ratio_per_trade": 0.35,
    }


def test_losing_mature_brain_is_guarded_not_full_production():
    from backend.organism.trading_phase import resolve_trading_phase

    phase = resolve_trading_phase(
        508,
        strategy_expectancy=_losing_expectancy(),
    )

    assert phase["phase"] == "production_guarded"
    assert phase["is_learning"] is False
    assert phase["is_frozen"] is False
    assert phase["is_guarded"] is True
    assert phase["ml_influence_enabled"] is False
    assert phase["fixed_risk_sizing"] is True
    assert any("total_pnl" in b for b in phase["promotion_blockers"])


def test_profitable_mature_brain_promotes_to_full_production():
    from backend.organism.trading_phase import resolve_trading_phase

    phase = resolve_trading_phase(
        508,
        strategy_expectancy=_profitable_expectancy(),
    )

    assert phase["phase"] == "production"
    assert phase["is_guarded"] is False
    assert phase["ml_influence_enabled"] is True
    assert phase["fixed_risk_sizing"] is False
    assert phase["promotion_blockers"] == []


def test_missing_expectancy_payload_preserves_count_only_compatibility():
    from backend.organism.trading_phase import resolve_trading_phase

    assert resolve_trading_phase(199)["phase"] == "learning"
    assert resolve_trading_phase(250)["phase"] == "production_frozen"
    assert resolve_trading_phase(300)["phase"] == "production"


def test_live_engine_phase_cache_demotes_losing_brain_without_learning_gates():
    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._tick_count = 123
    engine._all_trades = [
        SimpleNamespace(pnl=-1.0, is_reconciliation_artifact=False)
        for _ in range(501)
    ] + [
        SimpleNamespace(pnl=100.0, is_reconciliation_artifact=True)
        for _ in range(7)
    ]

    phase = engine._trading_phase

    assert phase["phase"] == "production_guarded"
    assert phase["total_trades"] == 501
    assert engine._is_learning_mode is False
    assert engine._is_guarded_production_mode is True
    assert engine._ml_isolation_mode is True
    assert engine._fixed_risk_sizing_mode is True


def test_kelly_fixed_risk_mode_bypasses_kelly_after_300_trades():
    from backend.organism.kelly_sizer import KellySizer

    df = pd.DataFrame({
        "close": [100.0 + i * 0.1 for i in range(60)],
        "high": [101.0 + i * 0.1 for i in range(60)],
        "low": [99.0 + i * 0.1 for i in range(60)],
    })
    sizer = KellySizer(min_position_usd=100.0)
    sizes = sizer.size_positions(
        [{
            "symbol": "AAPL",
            "direction": 1.0,
            "predicted_return": 0.04,
            "confidence": 0.90,
            "breakout_score": 0.80,
            "ranking_score": 0.72,
        }],
        portfolio_value=100_000.0,
        current_drawdown=0.0,
        features_by_symbol={"AAPL": df},
        current_regime="low_vol",
        ml_is_trained=True,
        trade_count=508,
        fixed_risk_mode=True,
    )

    assert sizes
    assert sizes[0].kelly_raw == 0.0
    assert sizes[0].kelly_half == 0.0
    assert sizer._last_intermediates["AAPL"]["risk_budget_applied"] is True


def test_alpha_learning_mode_ignores_ml_direction_and_return_source():
    from backend.organism.alpha_scanner import AlphaScanner

    df = pd.DataFrame({
        "comp_breakout_readiness": [0.80] * 60,
        "comp_squeeze_momentum": [0.70] * 60,
        "comp_institutional_acc": [0.50] * 60,
        "comp_momentum_quality": [0.50] * 60,
        "comp_vol_price_div": [0.50] * 60,
        "vol_sma_ratio": [2.00] * 60,
        "trend_strength": [0.50] * 60,
        "ret_5d": [0.02] * 60,
        "ret_20d": [0.03] * 60,
    })
    ml_signal = SimpleNamespace(
        direction=-1.0,
        confidence=0.99,
        effective_confidence=0.99,
        predicted_return=-0.05,
    )

    candidates = AlphaScanner(top_n=1).scan(
        {"AAPL": df},
        {"AAPL": ml_signal},
        current_regime="low_vol",
        ml_is_trained=True,
        learning_mode=True,
    )

    assert candidates
    assert candidates[0].direction == 1.0
    assert candidates[0].expected_return_source == "heuristic"
    assert candidates[0].ml_signal is None


@pytest.mark.parametrize(
    "payload",
    [
        {"n_trades": 299, "total_pnl": -999.0},
        None,
    ],
)
def test_promotion_gate_does_not_block_immature_or_missing_payloads(payload):
    from backend.organism.trading_phase import promotion_blockers

    assert promotion_blockers(payload) == []
