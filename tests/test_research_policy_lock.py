"""Runtime research lock: no promotion, no mutation, retained saved baseline."""
from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pandas as pd
import pytest
from fastapi import HTTPException

from backend.organism import research_policy
from backend.organism.background_trainer import BackgroundTrainer, TrainResult, _train_in_process
from backend.organism.continuous_learner import TradeRecord
from backend.organism.live_engine import OrganismLiveEngine
from backend.organism.self_evolution import EvolvedParams
from backend.organism.trading_phase import resolve_trading_phase


@pytest.mark.parametrize("count", [0, 199, 200, 299, 300, 609, 10_000])
@pytest.mark.parametrize("evidence", ["missing", "profitable", "losing"])
def test_counts_and_expectancy_cannot_promote(count, evidence):
    payload = None if evidence == "missing" else {
        "n_trades": count, "total_pnl": 123 if evidence == "profitable" else -123,
        "last_50_mean_pnl": 5, "last_50_win_rate": .9, "sharpe_ratio_per_trade": 2,
    }
    before = copy.deepcopy(payload)
    phase = resolve_trading_phase(count, strategy_expectancy=payload)
    assert phase["phase"] == "research_locked"
    assert phase["is_learning"] is (count < 200)
    assert phase["is_frozen"] is True
    assert phase["ml_influence_enabled"] is False
    assert phase["fixed_risk_sizing"] is True
    assert phase["total_trades"] == count
    assert phase["policy_lock"]["raw_strategy_trade_count"] == count
    assert phase["policy_lock"]["qualified_trade_count"] is None
    assert phase["policy_lock"]["qualification_status"] == "unverified"
    assert payload == before


def mature_engine():
    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._tick_count = 12
    engine._all_trades = [SimpleNamespace(pnl=2, is_reconciliation_artifact=False) for _ in range(609)]
    return engine


def test_lock_short_circuits_failed_phase_for_ml_and_kelly():
    engine = mature_engine()
    with patch.object(OrganismLiveEngine, "_trading_phase", new_callable=PropertyMock,
                      side_effect=RuntimeError("broken diagnostics")):
        assert engine._ml_isolation_mode is True
        assert engine._fixed_risk_sizing_mode is True


@pytest.mark.parametrize("failure", ["resolver", "expectancy"])
def test_failed_phase_diagnostics_preserve_risk_and_actual_learning_mode(monkeypatch, failure):
    path = "backend.organism.trading_phase.resolve_trading_phase" if failure == "resolver" else "backend.organism.strategy_expectancy.compute_from_trades"
    monkeypatch.setattr(path, MagicMock(side_effect=ValueError("invalid evidence")))
    engine = mature_engine()
    phase = engine._trading_phase
    assert phase["resolver_error"] == "ValueError"
    assert phase["phase"] == "research_locked"
    assert phase["total_trades"] == 609
    assert phase["ml_influence_enabled"] is False
    assert phase["fixed_risk_sizing"] is True
    assert engine._is_learning_mode is False
    assert len(engine._all_trades) == 609


def test_mature_profitable_engine_uses_real_atr_sizer():
    from backend.organism.kelly_sizer import KellySizer
    engine = mature_engine()
    frame = pd.DataFrame({"close": [100 + i*.1 for i in range(60)],
                          "high": [101 + i*.1 for i in range(60)],
                          "low": [99 + i*.1 for i in range(60)]})
    sizer = KellySizer(min_position_usd=100)
    sizes = sizer.size_positions(
        [{"symbol": "AAPL", "direction": 1., "predicted_return": .04,
          "confidence": .9, "breakout_score": .8, "ranking_score": .72}],
        portfolio_value=100_000, current_drawdown=0, features_by_symbol={"AAPL": frame},
        current_regime="low_vol", ml_is_trained=True, trade_count=609,
        fixed_risk_mode=engine._fixed_risk_sizing_mode,
    )
    assert sizes and sizes[0].shares > 0
    assert sizes[0].kelly_raw == sizes[0].kelly_half == 0
    assert sizer._last_intermediates["AAPL"]["risk_budget_applied"] is True


async def test_background_start_submit_and_worker_cannot_train(monkeypatch):
    pool = MagicMock(side_effect=AssertionError("must not start process"))
    monkeypatch.setattr("backend.organism.background_trainer.ProcessPoolExecutor", pool)
    trainer = BackgroundTrainer()
    await trainer.start()
    await trainer.submit_retrain(None, "low_vol", None, None, None, None, total_trades=609)
    assert trainer._executor is None and not trainer.is_training
    assert trainer._train_count == 0
    pool.assert_not_called()
    result = _train_in_process(None, "low_vol", None, None, None, None)
    assert result["accepted"] is False
    assert result["rejection_reason"] == research_policy.RESEARCH_POLICY_REASON


@pytest.mark.parametrize("result_type", ["accepted", "rejected", "error", "cancelled"])
async def test_inflight_results_cannot_promote_or_trigger_sync_fallback(result_type):
    trainer = BackgroundTrainer()
    trainer._is_training = True
    future = asyncio.get_running_loop().create_future()
    if result_type == "error":
        future.set_exception(RuntimeError("worker failed"))
    elif result_type == "cancelled":
        future.cancel()
    else:
        future.set_result({"accepted": result_type == "accepted", "clf_pickle": b"invalid"})
    trainer._future = future
    done, result = trainer.get_result()
    assert done and result.accepted is False and result.error is None
    assert result.rejection_reason == research_policy.RESEARCH_POLICY_REASON
    assert not trainer.is_training and trainer._future is None
    assert trainer.get_result() == (False, None)


@pytest.mark.parametrize("accepted", [True, False])
def test_background_apply_never_decodes_or_replaces_retained_model(accepted):
    trainer = BackgroundTrainer()
    trainer._last_result = TrainResult(accepted=accepted, new_clf_state=b"invalid pickle",
                                      evolved_params_dict={"stop_atr_scale": 9})
    trainer._preserve_incumbent_for_rollback = MagicMock(side_effect=AssertionError("no swap"))
    params = EvolvedParams(stop_atr_scale=1.7)
    before = copy.deepcopy(vars(params))
    components = [MagicMock() for _ in range(6)]
    returned = trainer.apply_result(components[0], components[1], params,
                                   *components[2:], total_trades=609)
    assert returned is params and vars(params) == before
    assert all(not component.mock_calls for component in components)
    trainer._preserve_incumbent_for_rollback.assert_not_called()


def test_sync_training_and_calibration_map_do_not_mutate():
    engine = mature_engine()
    engine.learner = MagicMock()
    engine.signal_gen = MagicMock()
    engine.evolution_engine = MagicMock()
    history = list(engine._all_trades)
    engine._retrain_and_evolve({}, "low_vol")
    assert not engine.learner.mock_calls
    assert not engine.signal_gen.mock_calls
    assert not engine.evolution_engine.mock_calls
    assert engine._all_trades == history


def test_effective_projection_holds_actual_parameters_not_bookkeeping():
    params = EvolvedParams(stop_atr_scale=1.7, feature_weights={"ret_1d": .7})
    before = research_policy.effective_policy_hash(params)
    params.symbol_fitness["AAPL"] = .2
    params.symbol_trade_counts["AAPL"] = 999
    params.evolution_generation = 999
    assert research_policy.effective_policy_hash(params) == before
    view = research_policy.effective_policy_params(params)
    assert view["stop_atr_scale"] == 1.7
    view["feature_weights"]["ret_1d"] = .1
    assert params.feature_weights["ret_1d"] == .7
    params.stop_atr_scale = 1.8
    assert research_policy.effective_policy_hash(params) != before


def test_engine_config_guard_precedes_all_mutation():
    engine = mature_engine()
    engine.kelly_sizer = MagicMock()
    engine.exit_engine = MagicMock()
    with pytest.raises(ValueError, match=research_policy.RESEARCH_POLICY_REASON):
        engine.update_config({"max_position_pct": .5, "atr_multiplier": 9, "universe": ["NEW"]})
    assert not engine.kelly_sizer.mock_calls and not engine.exit_engine.mock_calls
    assert not hasattr(engine, "_universe")
    assert engine.update_config({}) == {}


async def test_scheduler_guard_precedes_tick_and_subscription_changes():
    from backend.organism.scheduler import OrganismScheduler
    scheduler = OrganismScheduler.__new__(OrganismScheduler)
    scheduler._tick_interval = 60
    scheduler._engine = MagicMock()
    scheduler._streaming_provider = MagicMock()
    with pytest.raises(ValueError, match=research_policy.RESEARCH_POLICY_REASON):
        await scheduler.update_config({"tick_interval_seconds": 1, "universe": ["NEW"]})
    assert scheduler._tick_interval == 60
    assert not scheduler._engine.mock_calls and not scheduler._streaming_provider.mock_calls


@pytest.mark.parametrize("category", ["organism", "trading", "ml"])
@pytest.mark.parametrize("scheduler_present", [False, True])
async def test_api_rejects_policy_mutation_before_persistence_or_dispatch(monkeypatch, category, scheduler_present):
    from backend.api.routes import settings
    scheduler = MagicMock() if scheduler_present else None
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(organism_scheduler=scheduler)))
    save = MagicMock(side_effect=AssertionError("no persistence"))
    broadcast = AsyncMock(side_effect=AssertionError("no broadcast"))
    monkeypatch.setattr(settings, "_save_settings", save)
    monkeypatch.setattr(settings, "_broadcast_settings_change", broadcast)
    model = {"organism": settings.OrganismSettings, "trading": settings.TradingSettings, "ml": settings.MLSettings}[category]
    with pytest.raises(HTTPException) as error:
        await getattr(settings, f"update_{category}_settings")(request, model())
    assert error.value.status_code == 403
    assert error.value.detail == research_policy.RESEARCH_POLICY_REASON
    save.assert_not_called()
    broadcast.assert_not_called()
    if scheduler is not None:
        assert not scheduler.mock_calls


def isolated_engine(tmp_path):
    broker = MagicMock()
    broker.get_all_positions = AsyncMock(return_value={})
    engine = OrganismLiveEngine(data_client=MagicMock(), order_service=broker,
                                positions_service=broker, brain_dir=str(tmp_path / "brain"),
                                universe=["AAPL"])
    engine._reconstruct_position_state = AsyncMock()
    engine._save_brain = MagicMock()
    return engine


async def test_real_saved_baseline_and_history_survive_locked_startup(tmp_path, monkeypatch):
    from backend.organism.diagnostics import diagnostics
    monkeypatch.delenv("ORGANISM_APPROVED_POLICY_BASELINE", raising=False)
    monkeypatch.setattr(diagnostics, "run", AsyncMock(return_value=SimpleNamespace(
        summary={"passed": 0, "total": 0, "critical_failures": 0, "warnings": 0}, results=[])))
    saved = isolated_engine(tmp_path)
    saved.evolved_params = EvolvedParams(stop_atr_scale=1.7, feature_weights={"ret_1d": .7},
                                        evolution_generation=143, total_adaptations=172)
    for n in range(300):
        trade = TradeRecord("AAPL", 1, 100, 101, n, n+1, 1, 1, "take_profit", 0, .01, .6)
        saved._all_trades.append(trade)
        saved.learner.record_trade(trade)
    assert saved.force_save_brain()["success"]
    expected = research_policy.effective_policy_params(EvolvedParams.from_dict(saved.evolved_params.to_dict()))
    restored = isolated_engine(tmp_path)
    restored.transfer_engine.load_knowledge = MagicMock(side_effect=AssertionError("no transfer load"))
    restored.transfer_engine.warm_start_params = MagicMock(side_effect=AssertionError("no transfer mutation"))
    assert await restored.initialize()
    assert research_policy.effective_policy_params(restored.evolved_params) == expected
    assert restored.exit_engine.atr_multiplier == pytest.approx(restored.exit_engine._base_atr_multiplier * 1.7)
    assert restored.signal_gen._evolved_feature_weights == {"ret_1d": .7}
    assert restored.evolved_params.evolution_generation == 143
    assert len(restored._all_trades) == len(restored.learner.trade_history) == 300
    assert restored.learner.state.total_trades == 300
    assert restored.learner.state.cumulative_pnl == 300
    assert restored._bg_trainer._executor is None
    restored.transfer_engine.load_knowledge.assert_not_called()
    restored.transfer_engine.warm_start_params.assert_not_called()
    assert restored.status()["policy_lock"]["effective_policy_params"] == expected


async def test_configured_baseline_failure_aborts_before_broker_reconstruction(tmp_path, monkeypatch):
    engine = isolated_engine(tmp_path)
    monkeypatch.setattr("backend.organism.research_baseline.verify_configured_baseline",
                        MagicMock(side_effect=RuntimeError("baseline mismatch")))
    engine._bg_trainer.start = AsyncMock()
    with pytest.raises(RuntimeError, match="baseline mismatch"):
        await engine.initialize()
    engine._reconstruct_position_state.assert_not_called()
    engine._bg_trainer.start.assert_not_called()
    assert not engine._initialized
