from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pytest

from backend.organism.brain_persistence import (
    BRAIN_FORMAT_VERSION,
    OrganismBrain,
    _write_csv_atomic,
)


@dataclass
class _State:
    generation: int = 1
    total_bars_seen: int = 10
    total_trades: int = 0
    cumulative_pnl: float = 0.0
    best_sharpe: float = 0.0
    best_generation: int = 0
    retrain_count: int = 0
    drift_events: int = 0
    generation_accuracies: list[float] = field(default_factory=list)
    model_metrics: list = field(default_factory=list)
    evaluation_events: list = field(default_factory=list)


class _Learner:
    def __init__(self) -> None:
        self.state = _State()
        self._bars_since_retrain = 0
        self._reference_features = None
        self.trade_history = []


class _SignalGen:
    _is_trained = False
    _clf = None
    _reg = None
    _feature_cols = ["f1", "f2"]
    _xgb_params = {}
    generation = 1
    train_window = 200
    _latest_metrics = None

    def calibration_to_dict(self) -> dict:
        return {}


def _write_snapshot(root: Path, *, generation: int, symbol: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps({
            "brain_format_version": BRAIN_FORMAT_VERSION,
            "generation": generation,
            "total_runs": 1,
            "total_trades": 1,
            "cumulative_pnl": 12.34,
            "best_sharpe": 0.5,
            "ml_is_trained": True,
            "feature_count": 2,
        }),
        encoding="utf-8",
    )
    (root / "trade_history.csv").write_text(
        f"symbol,pnl\n{symbol},12.34\n",
        encoding="utf-8",
    )


def test_pp_1_atomic_csv_preserves_existing_file_on_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PP-1: failed CSV writes must not truncate the active brain file."""
    target = tmp_path / "trade_history.csv"
    target.write_text("symbol,pnl\nOLD,1.0\n", encoding="utf-8")

    def fail_to_csv(self, path, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        Path(path).write_text("symbol,pnl\nPARTIAL,0.0\n", encoding="utf-8")
        raise OSError("simulated disk-full during tmp write")

    monkeypatch.setattr(pd.DataFrame, "to_csv", fail_to_csv)

    with pytest.raises(OSError):
        _write_csv_atomic(pd.DataFrame({"symbol": ["NEW"], "pnl": [2.0]}), target)

    assert target.read_text(encoding="utf-8") == "symbol,pnl\nOLD,1.0\n"
    assert not (tmp_path / "trade_history.csv.tmp").exists()


def test_pp_1_full_save_creates_backup_directory(tmp_path: Path) -> None:
    """PP-1: full brain save must create backups/ in the brain root."""
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir=brain_dir)

    brain.save(
        signal_gen=_SignalGen(),
        learner=_Learner(),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        peak_equity=100000.0,
    )

    assert (brain_dir / "backups").is_dir()
    assert not (brain_dir / ".tmp_save").exists()


def test_pp_2_load_restores_newest_usable_backup_after_corrupt_head(
    tmp_path: Path,
) -> None:
    """PP-2: corrupt HEAD must load from the newest valid backup."""
    brain_dir = tmp_path / "brain"
    backup_root = brain_dir / "backups"
    brain_dir.mkdir()
    backup_root.mkdir()
    (brain_dir / "manifest.json").write_text("{not-json", encoding="utf-8")

    older = backup_root / "brain_gen1_older"
    newer = backup_root / "brain_gen9_newer"
    _write_snapshot(older, generation=1, symbol="OLD")
    _write_snapshot(newer, generation=9, symbol="NEW")
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_010, 1_700_000_010))

    brain = OrganismBrain(brain_dir=brain_dir)

    assert brain.load() is True
    assert brain.brain_dir == brain_dir.resolve()
    assert brain._manifest["generation"] == 9
    assert brain.trade_history == [{"symbol": "NEW", "pnl": 12.34}]
    assert any(d.name.startswith("corrupt_head_") for d in brain_dir.iterdir())
