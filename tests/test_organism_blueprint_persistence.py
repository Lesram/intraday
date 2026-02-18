"""
Blueprint compliance tests for Organism brain persistence requirements.

Covers key blueprint persistence guarantees:
- Dedicated evolved params file
- Governance and regime state persistence
- Brain quality-gate warnings for invalid evolved weights
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from backend.organism.brain_persistence import OrganismBrain
from backend.organism.continuous_learner import TradeRecord
from backend.organism.governance import GovernanceController
from backend.organism.regime import RegimeDetector


class _StubSignalGenerator:
    def __init__(self) -> None:
        self._is_trained = False
        self._clf = None
        self._reg = None
        self._feature_cols = ["f1", "f2", "f3"]
        self._xgb_params = {}
        self.generation = 1
        self.train_window = 200
        self._latest_metrics = None


@dataclass
class _StubLearnerState:
    generation: int = 1
    total_bars_seen: int = 50
    total_trades: int = 1
    cumulative_pnl: float = 123.45
    best_sharpe: float = 1.2
    best_generation: int = 1
    retrain_count: int = 0
    drift_events: int = 0
    generation_accuracies: list[float] = field(default_factory=lambda: [0.6])
    model_metrics: list = field(default_factory=list)


class _StubLearner:
    def __init__(self) -> None:
        self.state = _StubLearnerState()
        self._bars_since_retrain = 0
        self._reference_features = None


@pytest.mark.unit
@pytest.mark.regression
def test_brain_save_writes_dedicated_blueprint_files(tmp_path: Path) -> None:
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir=brain_dir)

    signal_gen = _StubSignalGenerator()
    learner = _StubLearner()

    gov = GovernanceController()
    gov.freeze()
    gov.halt_trading()

    regime = RegimeDetector()

    trades = [
        TradeRecord(
            symbol="AAPL",
            direction=1.0,
            entry_price=100.0,
            exit_price=101.0,
            entry_bar=1,
            exit_bar=2,
            shares=10,
            pnl=10.0,
            exit_reason="test",
            predicted_return=0.01,
            actual_return=0.01,
            confidence=0.7,
        )
    ]

    evolved_params = {
        "alpha_weight_ml": 0.35,
        "alpha_weight_volume": 0.20,
        "alpha_weight_momentum": 0.20,
        "alpha_weight_breakout": 0.15,
        "alpha_weight_regime": 0.10,
    }

    brain.save(
        signal_gen=signal_gen,
        learner=learner,
        equity_curve=[100000.0, 100010.0],
        all_trades=trades,
        epoch_metrics=[],
        peak_equity=100010.0,
        evolved_params=evolved_params,
        governance_controller=gov,
        regime_detector=regime,
    )

    assert (brain_dir / "evolved_params.json").exists()
    assert (brain_dir / "governance_state.json").exists()
    assert (brain_dir / "regime_state.json").exists()


@pytest.mark.unit
@pytest.mark.evolution
def test_brain_load_restores_governance_and_regime_state(tmp_path: Path) -> None:
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir=brain_dir)

    signal_gen = _StubSignalGenerator()
    learner = _StubLearner()
    gov = GovernanceController()
    regime = RegimeDetector()

    brain.save(
        signal_gen=signal_gen,
        learner=learner,
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        peak_equity=100000.0,
        evolved_params={"alpha_weight_ml": 0.35},
        governance_controller=gov,
        regime_detector=regime,
    )

    loaded = OrganismBrain(brain_dir=brain_dir)
    assert loaded.load() is True
    assert isinstance(loaded.governance_state, dict)
    assert isinstance(loaded.regime_state, dict)


@pytest.mark.unit
@pytest.mark.regression
def test_validate_brain_flags_weight_sum_violation(tmp_path: Path) -> None:
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.evolved_params = {
        "alpha_weight_ml": 0.9,
        "alpha_weight_volume": 0.9,
        "alpha_weight_momentum": 0.9,
        "alpha_weight_breakout": 0.9,
        "alpha_weight_regime": 0.9,
    }

    warnings = brain.validate_brain()
    assert any("Alpha weights sum" in w for w in warnings)
