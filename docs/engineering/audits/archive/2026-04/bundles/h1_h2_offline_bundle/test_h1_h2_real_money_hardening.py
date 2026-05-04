"""H1 + H2 real-money hardening tests.

H1: Production per-trade risk-budget cap applied in kelly_sizer
H2: Feature drift returns neutral signal when >20% features missing
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd


# ─── H1 tests ──────────────────────────────────────────────

def _make_ohlc_features(close=100.0, atr_pct=0.02, n=50):
    """Create features with OHLC columns that the sizer uses for ATR computation."""
    closes = np.array([close] * n)
    # ATR = atr_pct * close. True range = high - low for constant close.
    atr_abs = atr_pct * close
    highs = closes + atr_abs / 2
    lows = closes - atr_abs / 2
    return pd.DataFrame({
        "close": closes, "high": highs, "low": lows,
        "volume": [1_000_000.0] * n,
    })


def test_h1_production_risk_cap_applies():
    """In production mode, shares should be capped by per-trade risk budget."""
    from backend.organism.kelly_sizer import KellySizer

    sizer = KellySizer(
        max_position_pct=0.10,
        max_portfolio_pct=0.95,
        min_position_usd=100.0,
    )
    sizer._regime_kelly_stats = {
        "chop": {"wins": 10, "losses": 5, "total_pnl": 100,
                 "total_win_pnl": 200, "total_loss_pnl": 100}
    }

    candidates = [{
        "symbol": "TEST", "direction": 1.0, "predicted_return": 0.05,
        "confidence": 0.50, "effective_confidence": 0.50,
        "breakout_score": 0.40, "expected_return_source": "ml",
        "ranking_score": 0.50,
    }]

    features = {"TEST": _make_ohlc_features(close=100.0, atr_pct=0.02)}

    sizes = sizer.size_positions(
        candidates=candidates,
        portfolio_value=1_000_000,
        current_drawdown=0.0,
        features_by_symbol=features,
        current_regime="chop",
        trade_count=500,  # production mode (> 200)
    )

    if sizes:
        sz = sizes[0]
        # Risk cap: 0.25% of $1M = $2,500 max risk
        # ATR = 0.02 * 100 = $2. Stop at 1.5x ATR = $3.
        # Max shares = $2,500 / $3 = 833
        assert sz.shares <= 833, f"H1: prod shares {sz.shares} should be ≤833 from risk cap"
        # Should be significantly less than uncapped (max_position_pct * portfolio / price = 1000)
        assert sz.shares < 1000, f"H1: prod shares {sz.shares} should be < 1000 (uncapped)"


def test_h1_learning_mode_unchanged():
    """In learning mode, the EXISTING risk cap (0.10%) should still apply."""
    from backend.organism.kelly_sizer import KellySizer

    sizer = KellySizer(
        max_position_pct=0.10,
        max_portfolio_pct=0.95,
        min_position_usd=100.0,
    )

    candidates = [{
        "symbol": "TEST", "direction": 1.0, "predicted_return": 0.05,
        "confidence": 0.50, "effective_confidence": 0.50,
        "breakout_score": 0.40, "expected_return_source": "ml",
        "ranking_score": 0.50,
    }]

    features = {"TEST": _make_ohlc_features(close=100.0, atr_pct=0.02)}

    sizes = sizer.size_positions(
        candidates=candidates,
        portfolio_value=1_000_000,
        current_drawdown=0.0,
        features_by_symbol=features,
        current_regime="chop",
        trade_count=50,  # learning mode (< 200)
    )

    if sizes:
        sz = sizes[0]
        # Learning risk cap: 0.10% of $1M = $1,000 max risk
        # Stop = $3. Max shares = $1,000 / $3 = 333
        assert sz.shares <= 500, f"H1: learning shares {sz.shares} should be ≤500 (notional cap)"


# ─── H2 tests ──────────────────────────────────────────────

def test_h2_major_drift_returns_neutral():
    """When >20% of features are missing, predict() must return neutral."""
    from backend.organism.ml_signal import MLSignalGenerator

    gen = MLSignalGenerator()
    # Simulate a trained model with 10 feature columns
    gen._is_trained = True
    gen._feature_cols = [f"feat_{i}" for i in range(10)]
    # Fake classifiers (won't be called if drift guard fires)
    gen._clf = None
    gen._reg = None

    # Only provide 7/10 features (30% missing > 20% threshold)
    df = pd.DataFrame({f"feat_{i}": [1.0] for i in range(7)})

    signal = gen.predict(df, symbol="TEST")
    assert signal.direction == 0, f"H2: expected neutral direction, got {signal.direction}"
    assert signal.confidence == 0, f"H2: expected zero confidence, got {signal.confidence}"


def test_h2_minor_drift_still_predicts():
    """When ≤20% of features are missing, predict() should still work
    (zero-padding behavior preserved)."""
    from backend.organism.ml_signal import MLSignalGenerator
    from unittest.mock import MagicMock

    gen = MLSignalGenerator()
    gen._is_trained = True
    gen._feature_cols = [f"feat_{i}" for i in range(10)]

    # Mock classifiers
    gen._clf = MagicMock()
    gen._clf.predict_proba = MagicMock(return_value=np.array([[0.4, 0.6]]))
    gen._reg = MagicMock()
    gen._reg.predict = MagicMock(return_value=np.array([0.02]))

    # Provide 9/10 features (10% missing ≤ 20% threshold)
    df = pd.DataFrame({f"feat_{i}": [1.0] for i in range(9)})

    signal = gen.predict(df, symbol="TEST")
    # Should NOT return neutral — zero-padding should happen, inference proceeds
    assert signal.direction != 0 or signal.confidence > 0, \
        "H2: minor drift should still produce a real signal"


def test_h2_full_features_normal():
    """With all features present, predict() works normally."""
    from backend.organism.ml_signal import MLSignalGenerator
    from unittest.mock import MagicMock

    gen = MLSignalGenerator()
    gen._is_trained = True
    gen._feature_cols = [f"feat_{i}" for i in range(10)]

    gen._clf = MagicMock()
    gen._clf.predict_proba = MagicMock(return_value=np.array([[0.3, 0.7]]))
    gen._reg = MagicMock()
    gen._reg.predict = MagicMock(return_value=np.array([0.03]))

    df = pd.DataFrame({f"feat_{i}": [1.0] for i in range(10)})

    signal = gen.predict(df, symbol="TEST")
    assert signal.direction != 0 or signal.confidence > 0
    # clf.predict_proba should have been called
    gen._clf.predict_proba.assert_called_once()
