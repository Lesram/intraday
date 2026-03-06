"""
Smoke tests for the self-evolution engine.

Tests:
    1. EvolvedParams serialisation roundtrip
    2. EvolutionEngine adapts from trade data
    3. apply_evolved_params pushes values into components
    4. Feature selection respects weights
    5. Direction threshold calibration
    6. Brain persistence integration (save/restore evolved params)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pytest

from backend.organism.self_evolution import (
    EvolutionEngine,
    EvolvedParams,
    apply_evolved_params,
)
from backend.organism.continuous_learner import TradeRecord


# ── Helper ──────────────────────────────────────────────────────

def _make_trades(
    n: int = 20,
    win_rate: float = 0.65,
    high_conf_win_rate: float = 0.80,
) -> list[TradeRecord]:
    """Generate synthetic trades for testing."""
    trades = []
    for i in range(n):
        is_high_conf = i < n // 2
        confidence = 0.75 if is_high_conf else 0.40
        threshold = high_conf_win_rate if is_high_conf else win_rate * 0.7
        is_win = (i % 100) / 100 < threshold

        pnl = 500.0 if is_win else -200.0
        exit_reason = "trailing_stop" if is_win and i % 3 == 0 else (
            "stop_loss" if not is_win else "take_profit"
        )

        trades.append(TradeRecord(
            symbol=["AAPL", "TSLA", "NVDA", "MSFT"][i % 4],
            direction=1.0,
            entry_price=150.0,
            exit_price=155.0 if is_win else 148.0,
            entry_bar=i * 5,
            exit_bar=i * 5 + 10,
            shares=10,
            pnl=pnl,
            exit_reason=exit_reason,
            predicted_return=0.03,
            actual_return=0.03 if is_win else -0.01,
            confidence=confidence,
        ))
    return trades


# ── Tests ───────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.evolution
class TestEvolvedParams:
    def test_defaults_are_valid(self):
        p = EvolvedParams()
        assert abs(
            p.alpha_weight_ml + p.alpha_weight_volume
            + p.alpha_weight_momentum + p.alpha_weight_breakout
            + p.alpha_weight_regime - 1.0
        ) < 1e-6

    def test_serialisation_roundtrip(self):
        p = EvolvedParams()
        p.alpha_weight_ml = 0.42
        p.direction_threshold_buy = 0.58
        p.feature_weights = {"rsi_14": 1.5, "macd": 0.3}
        p.symbol_fitness = {"AAPL": 0.7, "TSLA": 0.3}
        p.evolution_generation = 5
        p.total_adaptations = 12

        d = p.to_dict()
        p2 = EvolvedParams.from_dict(d)

        assert p2.alpha_weight_ml == 0.42
        assert p2.direction_threshold_buy == 0.58
        assert p2.feature_weights["rsi_14"] == 1.5
        assert p2.symbol_fitness["AAPL"] == 0.7
        assert p2.evolution_generation == 5
        assert p2.total_adaptations == 12

    def test_feature_selection_threshold(self):
        p = EvolvedParams()
        # Need 15+ features above threshold, plus junk below 0.20
        good_features = [f"feat_{i}" for i in range(20)]
        p.feature_weights = {f: 1.0 for f in good_features}
        p.feature_weights["junk"] = 0.10   # below threshold — dropped
        p.feature_weights["extra"] = 0.80  # above threshold — kept

        all_feats = good_features + ["junk", "extra"]
        selected = p.get_selected_features(all_feats)
        assert all(f in selected for f in good_features)
        assert "extra" in selected
        assert "junk" not in selected  # below 0.20 → dropped

    def test_feature_selection_safety_floor(self):
        """Never drop below 15 features."""
        p = EvolvedParams()
        p.feature_weights = {f"f{i}": 0.01 for i in range(30)}
        all_features = [f"f{i}" for i in range(30)]
        selected = p.get_selected_features(all_features)
        assert len(selected) >= 15


@pytest.mark.unit
@pytest.mark.evolution
class TestEvolutionEngine:
    def test_evolve_changes_params(self):
        evo = EvolutionEngine(min_trades=5)
        params = EvolvedParams()
        trades = _make_trades(20)

        new_params = evo.evolve(
            params, trades,
            feature_importances={"rsi_14": 0.08, "macd": 0.05},
            epoch_regime="trending_up",
            all_feature_names=["rsi_14", "macd"],
        )

        assert new_params.evolution_generation == 1
        assert new_params.total_adaptations == 1
        assert len(evo.log) == 1

    def test_skips_with_few_trades(self):
        evo = EvolutionEngine(min_trades=50)
        params = EvolvedParams()
        trades = _make_trades(10)

        new_params = evo.evolve(params, trades)
        assert new_params.evolution_generation == 0  # unchanged

    def test_symbol_fitness_updated(self):
        evo = EvolutionEngine(min_trades=5)
        params = EvolvedParams()
        trades = _make_trades(20)

        new_params = evo.evolve(params, trades)
        assert "AAPL" in new_params.symbol_fitness
        assert "TSLA" in new_params.symbol_fitness

    def test_regime_scales_adapted(self):
        evo = EvolutionEngine(min_trades=5)
        params = EvolvedParams()
        original_trending = params.regime_size_scales["trending_up"]
        trades = _make_trades(20)

        new_params = evo.evolve(params, trades, epoch_regime="trending_up")
        # With mostly winning trades, trending scale should increase
        assert new_params.regime_size_scales["trending_up"] != original_trending

    def test_multiple_evolution_steps(self):
        evo = EvolutionEngine(min_trades=5)
        params = EvolvedParams()
        trades = _make_trades(20)

        for _ in range(5):
            params = evo.evolve(params, trades, epoch_regime="unknown")

        assert params.evolution_generation == 5
        assert params.total_adaptations == 5
        assert len(evo.log) == 5

    def test_evolution_is_gradual(self):
        """No parameter should change more than 20% per step."""
        evo = EvolutionEngine(min_trades=5, max_shift=0.20)
        params = EvolvedParams()
        original_ml = params.alpha_weight_ml
        trades = _make_trades(20)

        new_params = evo.evolve(params, trades)
        delta = abs(new_params.alpha_weight_ml - original_ml)
        max_allowed = original_ml * 0.20 + 0.005
        assert delta <= max_allowed + 1e-6


@pytest.mark.unit
@pytest.mark.evolution
class TestApplyEvolvedParams:
    def test_apply_to_alpha_scanner(self):
        from backend.organism.alpha_scanner import AlphaScanner

        scanner = AlphaScanner()
        params = EvolvedParams()
        params.alpha_weight_ml = 0.50
        params.alpha_weight_volume = 0.10

        apply_evolved_params(params, alpha_scanner=scanner)

        assert scanner.WEIGHT_ML == 0.50
        assert scanner.WEIGHT_VOLUME == 0.10

    def test_apply_to_exit_engine(self):
        from backend.organism.adaptive_exits import AdaptiveExitEngine

        engine = AdaptiveExitEngine()  # defaults: atr_multiplier=1.5, trailing_distance_atr=2.5
        params = EvolvedParams()
        params.stop_atr_scale = 1.3
        params.trailing_distance_scale = 0.8

        apply_evolved_params(params, exit_engine=engine)

        # Evolution uses _base_* attrs (= constructor args) as baselines
        assert abs(engine.atr_multiplier - 1.5 * 1.3) < 1e-6
        assert abs(engine.trailing_distance_atr - 2.5 * 0.8) < 1e-6

    def test_apply_to_signal_gen(self):
        from backend.organism.ml_signal import MLSignalGenerator

        sig = MLSignalGenerator()
        params = EvolvedParams()
        params.direction_threshold_buy = 0.60

        apply_evolved_params(params, signal_gen=sig)

        assert sig._direction_threshold_buy == 0.60

    def test_apply_to_kelly_sizer(self):
        from backend.organism.kelly_sizer import KellySizer

        sizer = KellySizer()
        params = EvolvedParams()
        params.regime_size_scales["trending_up"] = 1.15

        apply_evolved_params(params, kelly_sizer=sizer)

        assert hasattr(sizer, "_evolved_regime_scales")
        assert sizer._evolved_regime_scales["trending_up"] == 1.15

        # Evolved scales require 200+ total trades and 30+ in the regime
        # (improve7 freeze). Seed enough stats to unlock evolved scales.
        sizer._regime_stats["trending_up"] = {
            "wins": 25, "losses": 10, "total_pnl": 100.0,
            "total_win_pnl": 150.0, "total_loss_pnl": 50.0,
        }
        # Add enough trades in other regimes to reach 200+ total
        sizer._regime_stats["chop"] = {
            "wins": 80, "losses": 85, "total_pnl": -20.0,
            "total_win_pnl": 200.0, "total_loss_pnl": 220.0,
        }
        # Verify the regime_scale method uses evolved values
        scale, source, count = sizer._regime_scale("trending_up")
        assert scale == 1.15
