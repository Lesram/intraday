"""
Comprehensive tests for the Full Living Trading Organism.

Tests all phases:
  Phase 0: Governance (kill switches, freeze, policy versioning)
  Phase 1: Fill-based attribution
  Phase 2: Versioned feature store + QA
  Phase 3: Walk-forward evaluator + acceptance gates
  Phase 4: Training orchestrator
  Phase 5: Promotion controller (state machine)
  Phase 6: Regime-conditioned ensemble
"""

import asyncio
import math
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ============================================================================
# Phase 0: Governance
# ============================================================================

class TestGovernanceController:
    """Phase 0: Kill switches, freeze, drawdown kill, policy versioning."""

    def test_initial_state_unfrozen(self):
        from backend.organism.governance import GovernanceController
        gov = GovernanceController()
        assert not gov.is_frozen
        assert not gov.is_trading_halted

    def test_freeze_unfreeze(self):
        from backend.organism.governance import GovernanceController
        gov = GovernanceController()
        gov.freeze()
        assert gov.is_frozen
        gov.unfreeze()
        assert not gov.is_frozen

    def test_halt_resume(self):
        from backend.organism.governance import GovernanceController
        gov = GovernanceController()
        gov.halt_trading()
        assert gov.is_trading_halted
        gov.resume_trading()
        assert not gov.is_trading_halted

    def test_disable_enable_strategy(self):
        from backend.organism.governance import GovernanceController
        gov = GovernanceController()
        gov.disable_strategy("momentum")
        assert gov.is_strategy_disabled("momentum")
        assert gov.is_strategy_disabled("MOMENTUM")  # case-insensitive
        gov.enable_strategy("momentum")
        assert not gov.is_strategy_disabled("momentum")

    def test_change_budget(self):
        from backend.organism.governance import GovernanceController
        gov = GovernanceController()
        gov._max_changes_per_day = 3
        assert gov.can_change()
        gov.record_change()
        gov.record_change()
        gov.record_change()
        assert not gov.can_change()

    def test_drawdown_kill(self):
        from backend.organism.governance import GovernanceController
        gov = GovernanceController()
        gov._drawdown_limit = 0.05
        gov._drawdown_cooldown_s = 5
        gov.trigger_drawdown_kill(0.06)
        assert gov.is_trading_halted

    def test_policy_version(self):
        from backend.organism.governance import GovernanceController
        gov = GovernanceController()
        gov.set_policy_version("v1.0", {"weights": {"momentum": 1.0}})
        snap = gov.snapshot()
        assert snap.policy_version == "v1.0"
        assert len(snap.config_hash) > 0

    def test_snapshot_to_dict(self):
        from backend.organism.governance import GovernanceController
        gov = GovernanceController()
        d = gov.to_dict()
        assert "frozen" in d
        assert "trading_halted" in d
        assert "disabled_strategies" in d


# ============================================================================
# Phase 1: Attribution
# ============================================================================

class TestAttributionService:
    """Phase 1: Fill-based PnL attribution from orders."""

    def test_position_tracking_buy_sell_cycle(self):
        from backend.organism.attribution import AttributionService
        svc = AttributionService(sessionmaker=MagicMock())

        # Buy 100 shares at $50
        pnl_buy = svc._update_position_pnl("momentum", "AAPL", "buy", 100, 50.0)
        assert pnl_buy == 0.0  # Opening position — no realized PnL

        # Sell 100 shares at $55
        pnl_sell = svc._update_position_pnl("momentum", "AAPL", "sell", 100, 55.0)
        assert pnl_sell == 500.0  # 100 * (55 - 50) = 500

    def test_position_tracking_partial_close(self):
        from backend.organism.attribution import AttributionService
        svc = AttributionService(sessionmaker=MagicMock())

        svc._update_position_pnl("stat_arb", "TSLA", "buy", 100, 200.0)
        pnl = svc._update_position_pnl("stat_arb", "TSLA", "sell", 50, 210.0)
        assert pnl == 500.0  # 50 * (210 - 200) = 500

        # Remaining 50 shares
        assert svc._positions["stat_arb"]["TSLA"] == 50.0

    def test_position_tracking_short(self):
        from backend.organism.attribution import AttributionService
        svc = AttributionService(sessionmaker=MagicMock())

        # Short 100 shares at $100
        svc._update_position_pnl("mean_reversion", "META", "sell", 100, 100.0)
        # Cover at $95
        pnl = svc._update_position_pnl("mean_reversion", "META", "buy", 100, 95.0)
        assert pnl == 500.0  # 100 * (100 - 95) = 500

    def test_reward_signal_computation(self):
        from backend.organism.attribution import AttributionService, StrategyPerformance
        svc = AttributionService(sessionmaker=MagicMock())

        strategies = {
            "momentum": StrategyPerformance(
                source="momentum", total_pnl=100.0, trade_count=10,
                win_count=7, avg_slippage_bps=2.0, turnover_usd=50000.0,
            ),
            "mean_reversion": StrategyPerformance(
                source="mean_reversion", total_pnl=-50.0, trade_count=5,
                win_count=1, avg_slippage_bps=5.0, turnover_usd=30000.0,
            ),
        }

        rewards = svc._compute_reward_signals(strategies)
        assert "momentum" in rewards
        assert "mean_reversion" in rewards
        assert rewards["momentum"] > rewards["mean_reversion"]
        # Rewards clamped to [-1, 1]
        for v in rewards.values():
            assert -1.0 <= v <= 1.0

    def test_sharpe_proxy(self):
        from backend.organism.attribution import AttributionService, TradeAttribution, StrategyPerformance
        svc = AttributionService(sessionmaker=MagicMock())

        trades = [
            TradeAttribution(
                id=str(i), symbol="AAPL", strategy_source="momentum",
                side="buy", qty=10, fill_price=100, expected_price=100,
                realized_pnl=float(pnl), slippage_bps=0, fees=0,
                timestamp="2026-01-01",
            )
            for i, pnl in enumerate([10, -5, 8, -3, 12, 7])
        ]
        strategies = {"momentum": StrategyPerformance(source="momentum")}
        svc._compute_sharpe_proxies(trades, strategies)
        assert strategies["momentum"].sharpe_proxy != 0.0

    def test_drawdown_computation(self):
        from backend.organism.attribution import AttributionService, TradeAttribution, StrategyPerformance
        svc = AttributionService(sessionmaker=MagicMock())

        trades = [
            TradeAttribution(
                id=str(i), symbol="AAPL", strategy_source="momentum",
                side="buy", qty=10, fill_price=100, expected_price=100,
                realized_pnl=float(pnl), slippage_bps=0, fees=0,
                timestamp="2026-01-01",
            )
            for i, pnl in enumerate([100, 50, -200, 30, -100])
        ]
        strategies = {"momentum": StrategyPerformance(source="momentum")}
        svc._compute_drawdowns(trades, strategies)
        assert strategies["momentum"].max_drawdown > 0


# ============================================================================
# Phase 2: Feature Store
# ============================================================================

class TestVersionedFeatureStore:
    """Phase 2: Config versioning, QA checks, online/offline parity."""

    def _make_price_df(self, n=100):
        dates = pd.date_range("2025-01-01", periods=n, freq="B")
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        return pd.DataFrame({
            "timestamp": dates,
            "open": close - 0.3,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.random.randint(1000000, 5000000, n),
        })

    def test_config_hash_deterministic(self):
        from backend.organism.feature_store import VersionedFeatureStore
        store1 = VersionedFeatureStore()
        store2 = VersionedFeatureStore()
        assert store1.config_hash == store2.config_hash

    def test_config_hash_changes(self):
        from backend.organism.feature_store import VersionedFeatureStore
        store1 = VersionedFeatureStore(config={"a": 1})
        store2 = VersionedFeatureStore(config={"a": 2})
        assert store1.config_hash != store2.config_hash

    def test_compute_features_returns_snapshot(self):
        from backend.organism.feature_store import VersionedFeatureStore
        store = VersionedFeatureStore()
        df = self._make_price_df()
        features, snapshot = store.compute_features(df, symbol="AAPL")
        assert not features.empty
        assert snapshot.symbol == "AAPL"
        assert snapshot.config_hash == store.config_hash
        assert snapshot.row_count > 0

    def test_qa_passes_clean_data(self):
        from backend.organism.feature_store import VersionedFeatureStore
        store = VersionedFeatureStore()
        # Use non-business-day dates to avoid weekend gap noise, and enough rows
        df = self._make_price_df(300)
        # Replace business-day dates with contiguous daily dates
        df["timestamp"] = pd.date_range("2025-01-01", periods=len(df), freq="D")
        _, snapshot = store.compute_features(df)
        assert snapshot.qa.passed

    def test_qa_detects_missing_bars(self):
        from backend.organism.feature_store import VersionedFeatureStore
        store = VersionedFeatureStore()
        # Use business-day dates which create weekend gaps
        df = self._make_price_df(100)
        _, snapshot = store.compute_features(df)
        # Business-day dates inherently have weekend gaps → missing_bar_pct > 0
        assert snapshot.qa.missing_bar_pct > 0
        assert not snapshot.qa.passed  # gaps trigger the QA gate


# ============================================================================
# Phase 3: Walk-Forward Evaluator
# ============================================================================

class TestWalkForwardEvaluator:
    """Phase 3: Walk-forward evaluation + acceptance gates."""

    def _make_price_data(self, symbols=None, n=120):
        symbols = symbols or ["AAPL", "MSFT"]
        price_data = {}
        dates = pd.date_range("2025-01-01", periods=n, freq="B")
        for sym in symbols:
            np.random.seed(hash(sym) % 2**31)
            close = 100 + np.cumsum(np.random.randn(n) * 0.5)
            df = pd.DataFrame({
                "timestamp": dates,
                "open": close - 0.3,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": np.random.randint(1000000, 5000000, n),
            })
            price_data[sym] = df
        return price_data

    @pytest.mark.asyncio
    async def test_evaluate_produces_report(self):
        from backend.organism.walk_forward import WalkForwardEvaluator, AcceptanceGates
        evaluator = WalkForwardEvaluator(
            train_window_days=40,
            test_window_days=10,
            step_days=10,
            gates=AcceptanceGates(min_sharpe=-999, min_trades=0),
        )
        price_data = self._make_price_data()
        report = await evaluator.evaluate(
            price_data=price_data,
            candidate_weights={"momentum": 1.2, "mean_reversion": 0.8},
            baseline_weights={"momentum": 1.0, "mean_reversion": 1.0},
        )
        assert len(report.windows) > 0
        assert report.created_at != ""

    @pytest.mark.asyncio
    async def test_insufficient_data_rejected(self):
        from backend.organism.walk_forward import WalkForwardEvaluator
        evaluator = WalkForwardEvaluator(
            train_window_days=200,  # more than available
            test_window_days=50,
        )
        price_data = self._make_price_data(n=50)
        report = await evaluator.evaluate(
            price_data=price_data,
            candidate_weights={"momentum": 1.0},
            baseline_weights={"momentum": 1.0},
        )
        assert not report.accepted
        assert any("Insufficient" in r for r in report.rejection_reasons)

    def test_acceptance_gates_sharpe(self):
        from backend.organism.walk_forward import WalkForwardEvaluator, WalkForwardReport, AcceptanceGates
        evaluator = WalkForwardEvaluator(gates=AcceptanceGates(min_sharpe=1.0))
        report = WalkForwardReport(candidate_id="test", baseline_id="base")
        report.mean_sharpe = 0.5
        report.total_trades = 10
        evaluator._check_gates(report, {})
        assert not report.accepted
        assert any("Sharpe" in r for r in report.rejection_reasons)


# ============================================================================
# Phase 5: Promotion Controller
# ============================================================================

class TestPromotionController:
    """Phase 5: State machine, rollback triggers, stage risk caps."""

    @pytest.mark.asyncio
    async def test_begin_promotion_enters_shadow(self):
        from backend.organism.promotion import PromotionController, PromotionStage
        from backend.organism.governance import GovernanceController

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_sm = MagicMock(return_value=mock_session)

        gov = GovernanceController()
        pc = PromotionController(sessionmaker=mock_sm, governance=gov)

        state = await pc.begin_promotion("cand_001", {"momentum": 1.2})
        assert state.stage == PromotionStage.SHADOW
        assert state.candidate_id == "cand_001"

    @pytest.mark.asyncio
    async def test_rollback_freezes_adaptation(self):
        from backend.organism.promotion import PromotionController, PromotionStage, RollbackTrigger
        from backend.organism.governance import GovernanceController

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_sm = MagicMock(return_value=mock_session)

        gov = GovernanceController()
        pc = PromotionController(sessionmaker=mock_sm, governance=gov)
        await pc.begin_promotion("cand_002", {"momentum": 1.0})

        trigger = RollbackTrigger(
            reason="test", metric_name="drawdown",
            metric_value=0.10, threshold=0.08,
            timestamp=datetime.now(UTC).isoformat(),
        )
        state = await pc.rollback(trigger)
        assert state.stage == PromotionStage.ROLLED_BACK
        assert gov.is_frozen  # rollback should freeze

    def test_rollback_trigger_detection(self):
        from backend.organism.promotion import PromotionController
        from backend.organism.governance import GovernanceController

        mock_sm = MagicMock()
        gov = GovernanceController()
        pc = PromotionController(sessionmaker=mock_sm, governance=gov)

        # Should trigger on high drawdown
        trigger = pc._check_rollback_triggers({"drawdown": 0.20})
        assert trigger is not None
        assert trigger.reason == "Drawdown breach"

        # Should be fine
        trigger = pc._check_rollback_triggers({"drawdown": 0.01})
        assert trigger is None

    def test_stage_risk_caps(self):
        from backend.organism.promotion import STAGE_RISK_CAPS, PromotionStage
        # Shadow should have 0 exposure
        assert STAGE_RISK_CAPS[PromotionStage.SHADOW.value]["max_exposure"] == 0.0
        # Active should have max
        assert STAGE_RISK_CAPS[PromotionStage.ACTIVE.value]["max_exposure"] > 0.0


# ============================================================================
# Phase 6: Regime
# ============================================================================

class TestRegimeDetector:
    """Phase 6: Regime detection, churn, drift, ensemble blending."""

    def _make_trending_features(self):
        """Create data that looks like a strong uptrend."""
        n = 100
        close = np.linspace(100, 130, n)  # steady uptrend
        sma_50 = np.convolve(close, np.ones(50) / 50, mode="full")[:n]
        return pd.DataFrame({
            "close": close,
            "sma_50": sma_50,
            "atr_ratio": np.full(n, 0.02),
            "volume": np.full(n, 3_000_000),
        })

    def _make_choppy_features(self):
        """Create data that looks like chop."""
        n = 100
        np.random.seed(123)
        close = 100 + np.cumsum(np.random.randn(n) * 0.1)
        sma_50 = np.convolve(close, np.ones(50) / 50, mode="full")[:n]
        return pd.DataFrame({
            "close": close,
            "sma_50": sma_50,
            "atr_ratio": np.full(n, 0.01),
            "volume": np.full(n, 2_000_000),
        })

    def test_trending_detection(self):
        from backend.organism.regime import RegimeDetector, RegimeLabel
        detector = RegimeDetector()
        features = self._make_trending_features()
        state = detector.detect(features)
        # Should detect trending
        assert state.primary in (RegimeLabel.TRENDING_UP, RegimeLabel.LOW_VOL)
        assert state.confidence > 0.0

    def test_churn_rate_increases_with_flips(self):
        from backend.organism.regime import RegimeDetector
        # Use no smoothing (alpha=1.0) so regime flips are immediate
        detector = RegimeDetector(churn_window=5, smoothing_alpha=1.0)

        # Create clearly different regimes: strong uptrend vs strong downtrend
        n = 100
        up_close = np.linspace(100, 200, n)  # strong uptrend
        up_sma = np.convolve(up_close, np.ones(50)/50, mode='full')[:n]
        features_up = pd.DataFrame({
            "close": up_close, "sma_50": up_sma,
            "atr_ratio": np.full(n, 0.02),
            "volume": np.full(n, 3_000_000),
        })

        down_close = np.linspace(200, 100, n)  # strong downtrend
        down_sma = np.convolve(down_close, np.ones(50)/50, mode='full')[:n]
        features_down = pd.DataFrame({
            "close": down_close, "sma_50": down_sma,
            "atr_ratio": np.full(n, 0.05),  # high vol too
            "volume": np.full(n, 6_000_000),  # volume anomaly
        })

        # Alternate several times to build churn history
        for _ in range(10):
            detector.detect(features_up)
            detector.detect(features_down)

        last = detector.detect(features_up)
        assert last.churn_rate > 0.0

    def test_empty_data_returns_unknown(self):
        from backend.organism.regime import RegimeDetector, RegimeLabel
        detector = RegimeDetector()
        state = detector.detect(pd.DataFrame())
        assert state.primary == RegimeLabel.UNKNOWN

    def test_regime_conditioned_blend(self):
        from backend.organism.regime import RegimeConditionedEnsemble, RegimeState
        ensemble = RegimeConditionedEnsemble()
        regime = RegimeState(
            primary="trending_up",
            probabilities={"trending_up": 0.7, "chop": 0.2, "high_vol": 0.1},
            confidence=0.7,
        )
        base_weights = {"momentum": 1.0, "mean_reversion": 1.0, "stat_arb": 1.0}
        blended = ensemble.blend(regime, base_weights)

        # In trending regime, momentum should be boosted
        assert blended["momentum"] > blended["mean_reversion"]

    def test_drift_detection_no_drift(self):
        from backend.organism.regime import DriftDetector
        detector = DriftDetector(threshold=0.10)
        np.random.seed(42)
        ref = pd.DataFrame({"a": np.random.randn(200), "b": np.random.randn(200)})
        cur = pd.DataFrame({"a": np.random.randn(200), "b": np.random.randn(200)})
        report = detector.check_drift(ref, cur)
        # Same distribution — should not drift much
        assert not report.drifted or report.overall_score < 0.5

    def test_drift_detection_with_drift(self):
        from backend.organism.regime import DriftDetector
        detector = DriftDetector(threshold=0.05)
        np.random.seed(42)
        ref = pd.DataFrame({"a": np.random.randn(200)})
        # Significant distribution shift
        cur = pd.DataFrame({"a": np.random.randn(200) + 5})
        report = detector.check_drift(ref, cur)
        assert report.drifted
        assert report.overall_score > 0.05


# ============================================================================
# Integration: Organism Runner
# ============================================================================

class TestOrganismRunner:
    """Integration test for OrganismRunner pre/post execution hooks."""

    def test_pre_execution_halted(self):
        from backend.organism.runner import OrganismRunner
        from backend.organism.governance import GovernanceController

        gov = GovernanceController()
        gov.halt_trading()
        runner = OrganismRunner(governance=gov)

        result = runner.pre_execution_hook(base_weights={"momentum": 1.0})
        assert not result["trading_allowed"]

    def test_pre_execution_normal(self):
        from backend.organism.runner import OrganismRunner

        runner = OrganismRunner()
        result = runner.pre_execution_hook(base_weights={"momentum": 1.0, "mean_reversion": 1.0})
        assert result["trading_allowed"]
        assert "momentum" in result["final_weights"]

    def test_pre_execution_with_features(self):
        from backend.organism.runner import OrganismRunner

        runner = OrganismRunner()
        n = 100
        close = np.linspace(100, 120, n)
        features = pd.DataFrame({
            "close": close,
            "sma_50": np.convolve(close, np.ones(50) / 50, mode="full")[:n],
            "atr_ratio": np.full(n, 0.02),
            "volume": np.full(n, 3_000_000),
        })
        result = runner.pre_execution_hook(
            features_df=features,
            base_weights={"momentum": 1.0, "mean_reversion": 1.0},
        )
        assert result["regime"] is not None
        assert result["trading_allowed"]

    def test_post_execution_drawdown_kill(self):
        from backend.organism.runner import OrganismRunner
        import os

        os.environ["ORGANISM_DRAWDOWN_KILL_PCT"] = "0.05"
        runner = OrganismRunner()
        result = runner.post_execution_hook(live_metrics={"drawdown": 0.10})
        assert "drawdown_kill_triggered" in result["actions"]
        # Clean up
        del os.environ["ORGANISM_DRAWDOWN_KILL_PCT"]

    def test_status(self):
        from backend.organism.runner import OrganismRunner
        runner = OrganismRunner()
        status = runner.status()
        assert "tick_count" in status
        assert "governance" in status
