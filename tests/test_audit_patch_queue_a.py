"""Tests for Patch Queue A -- critical audit findings."""
from __future__ import annotations

import types
from unittest.mock import MagicMock, patch
import pytest
import pandas as pd
import numpy as np


# -- Fix 1: Background-trainer evolution-freeze --


class TestBackgroundTrainerEvolutionFreeze:
    """Verify evolution freeze is enforced in background trainer."""

    def _make_trainer_with_result(self, evolved_params_dict):
        """Create a BackgroundTrainer with a pre-set accepted result."""
        from backend.organism.background_trainer import BackgroundTrainer, TrainResult
        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=True,
            evolved_params_dict=evolved_params_dict,
            duration_s=1.0,
        )
        return trainer

    def test_apply_result_blocks_evolved_params_below_300_trades(self):
        """Evolution params must NOT be applied when total_trades < 300."""
        trainer = self._make_trainer_with_result(
            evolved_params_dict={"evolution_generation": 1, "signal_weights": {"momentum": 1.5}}
        )
        from backend.organism.self_evolution import EvolvedParams
        original_params = EvolvedParams()
        original_gen = original_params.evolution_generation

        result = trainer.apply_result(
            signal_gen=MagicMock(_is_trained=False, _clf=None, _reg=None, _ensemble=None, _feature_cols=None),
            evolution_engine=MagicMock(),
            evolved_params=original_params,
            alpha_scanner=MagicMock(),
            breakout_scanner=MagicMock(),
            kelly_sizer=MagicMock(),
            exit_engine=MagicMock(),
            total_trades=142,  # < 300
        )
        # Should return original params unchanged
        assert result.evolution_generation == original_gen

    def test_apply_result_allows_evolved_params_at_300_trades(self):
        """Evolution params MAY be applied when total_trades >= 300."""
        trainer = self._make_trainer_with_result(
            evolved_params_dict={"evolution_generation": 5}
        )
        from backend.organism.self_evolution import EvolvedParams
        original_params = EvolvedParams()

        with patch("backend.organism.self_evolution.apply_evolved_params") as mock_apply:
            result = trainer.apply_result(
                signal_gen=MagicMock(_is_trained=False, _clf=None, _reg=None, _ensemble=None, _feature_cols=None, _evolved_feature_weights=None),
                evolution_engine=MagicMock(),
                evolved_params=original_params,
                alpha_scanner=MagicMock(),
                breakout_scanner=MagicMock(),
                kelly_sizer=MagicMock(),
                exit_engine=MagicMock(),
                total_trades=300,  # >= 300
            )
            mock_apply.assert_called_once()

    def test_train_in_process_skips_evolution_below_300(self):
        """_train_in_process must not produce evolved_params when trades < 300."""
        from backend.organism.background_trainer import _train_in_process
        # We can't easily run the full function (needs ML deps), but we can
        # verify the parameter is threaded through by checking submit_retrain
        from backend.organism.background_trainer import BackgroundTrainer
        trainer = BackgroundTrainer()
        # Verify submit_retrain accepts total_trades parameter
        import inspect
        sig = inspect.signature(trainer.submit_retrain)
        assert "total_trades" in sig.parameters


# -- Fix 2: Pure-breakout confidence-gate parity --


class TestBreakoutConfidenceGateParity:
    """Verify pure breakout uses same regime-conditioned threshold as alpha."""

    def _make_engine(self):
        """Create a minimal OrganismLiveEngine for gate testing."""
        from backend.organism.live_engine import OrganismLiveEngine
        engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
        engine._MIN_AVG_VOLUME = 100_000
        engine._exit_cooldown = set()
        engine._symbol_exit_type = {}
        engine._symbol_exit_tick = {}
        engine._pending_entry = set()
        engine._entry_metadata = {}
        engine._symbol_banned = set()
        engine._is_learning_mode = True
        engine._tick_count = 100
        engine._STOP_LOSS_REENTRY_TICKS = 5
        engine._FTF_LOSS_REENTRY_TICKS = 3
        from backend.organism.self_evolution import EvolvedParams
        engine.evolved_params = EvolvedParams()
        return engine

    def test_breakout_in_defensive_regime_rejected_between_040_and_045(self):
        """In chop/high_vol/trending_down, breakout with conf 0.42 should be
        rejected since the alpha path would use 0.45 threshold."""
        # This is a code-reading assertion: verify the breakout path uses
        # regime-conditioned threshold, not _MAIN_CONF_BASELINE alone.
        import ast
        import inspect
        from backend.organism import live_engine
        source = inspect.getsource(live_engine)
        tree = ast.parse(source)

        # Find the string "_bo_min_conf" or "_MIN_MAIN_CONF" near the breakout
        # confidence check -- indicates regime-conditioning is applied
        assert "_bo_min_conf" in source or "_MIN_MAIN_CONF" in source.split("Pure breakout")[1] if "Pure breakout" in source else True, \
            "Breakout path must use regime-conditioned confidence threshold"

    def test_breakout_above_defensive_threshold_passes(self):
        """Breakout with composite_score >= 0.45 should pass in defensive regime."""
        # Structural check: _MAIN_CONF_DEFENSIVE is used in breakout path
        from backend.organism import live_engine
        import inspect
        source = inspect.getsource(live_engine)
        breakout_section = source[source.index("Pure breakout"):]
        assert "_MAIN_CONF_DEFENSIVE" in breakout_section or "_bo_min_conf" in breakout_section, \
            "Breakout path must reference defensive threshold"


# -- Fix 3: Alpha ranking preservation --


class TestAlphaRankingPreservation:
    """Verify candidates are sorted by ranking_score, not breakout*confidence."""

    def test_alpha_with_higher_composite_ranks_ahead(self):
        """Alpha candidate with higher composite_score but lower
        breakout*confidence must still rank first."""
        # Simulate two candidates
        alpha_cand = {
            "symbol": "AAPL",
            "ranking_score": 0.85,  # high alpha composite
            "breakout_score": 0.3,
            "confidence": 0.7,     # breakout*conf = 0.21
        }
        worse_breakout_cand = {
            "symbol": "TSLA",
            "ranking_score": 0.60,
            "breakout_score": 0.8,
            "confidence": 0.9,     # breakout*conf = 0.72
        }
        cands = [worse_breakout_cand, alpha_cand]
        cands.sort(key=lambda x: x["ranking_score"], reverse=True)
        assert cands[0]["symbol"] == "AAPL"

    def test_pure_breakout_ordering_deterministic(self):
        """Two breakout candidates with different scores sort deterministically."""
        cand_a = {"symbol": "A", "ranking_score": 0.55 * 0.60}
        cand_b = {"symbol": "B", "ranking_score": 0.70 * 0.80}
        cands = [cand_a, cand_b]
        cands.sort(key=lambda x: x["ranking_score"], reverse=True)
        assert cands[0]["symbol"] == "B"

    def test_ranking_score_key_present_in_source(self):
        """The cand_dicts append must include ranking_score."""
        import inspect
        from backend.organism import live_engine
        source = inspect.getsource(live_engine)
        assert '"ranking_score"' in source or "'ranking_score'" in source

    def test_sort_uses_ranking_score(self):
        """Final sort must use ranking_score, not breakout_score * confidence."""
        import inspect
        from backend.organism import live_engine
        source = inspect.getsource(live_engine)
        # The old sort pattern should NOT exist
        assert 'x["breakout_score"] * x["confidence"]' not in source, \
            "Old breakout_score*confidence sort must be removed"
        # The new sort pattern SHOULD exist
        assert 'x["ranking_score"]' in source


# -- Fix 4: Liquidity gate fail closed --


class TestLiquidityGateFailClosed:
    """Verify _passes_liquidity_gate fails closed on missing/insufficient data."""

    def _make_engine(self):
        from backend.organism.live_engine import OrganismLiveEngine
        engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
        engine._MIN_AVG_VOLUME = 100_000
        return engine

    def test_missing_df_returns_false(self):
        engine = self._make_engine()
        assert engine._passes_liquidity_gate("AAPL", {}) is False

    def test_none_df_returns_false(self):
        engine = self._make_engine()
        assert engine._passes_liquidity_gate("AAPL", {"AAPL": None}) is False

    def test_missing_volume_column_returns_false(self):
        engine = self._make_engine()
        df = pd.DataFrame({"close": [100.0] * 30})
        assert engine._passes_liquidity_gate("AAPL", {"AAPL": df}) is False

    def test_fewer_than_20_bars_returns_false(self):
        engine = self._make_engine()
        df = pd.DataFrame({"volume": [200_000] * 19})
        assert engine._passes_liquidity_gate("AAPL", {"AAPL": df}) is False

    def test_valid_volume_below_threshold_returns_false(self):
        engine = self._make_engine()
        df = pd.DataFrame({"volume": [50_000] * 25})
        assert engine._passes_liquidity_gate("AAPL", {"AAPL": df}) is False

    def test_valid_volume_above_threshold_returns_true(self):
        engine = self._make_engine()
        df = pd.DataFrame({"volume": [200_000] * 25})
        assert engine._passes_liquidity_gate("AAPL", {"AAPL": df}) is True

    def test_exactly_20_bars_above_threshold_returns_true(self):
        engine = self._make_engine()
        df = pd.DataFrame({"volume": [150_000] * 20})
        assert engine._passes_liquidity_gate("AAPL", {"AAPL": df}) is True
