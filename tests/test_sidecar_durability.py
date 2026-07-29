"""Work order 2026-07-23 Task 2 — sidecar telemetry durability.

Two independent defects are covered:

1. brain_persistence.save()'s file-by-file atomic swap moved every head entry
   NOT listed in ``preserved_names`` into ``.brain_old`` and then rmtree'd it.
   The append-only sidecars (shadow_exit_telemetry / model_swap_audit /
   previous_model dir) were absent from that set, so a single full save
   silently deleted them. These are BEHAVIORAL probes — they run a real
   save()/backup/reload and assert the files survive with intact content.

2. The shadow-exit recorder emitted a row for every reconciled symbol,
   including replay/test symbols that never held shares (qty=0). Those rows
   were the bulk of the telemetry pollution. The real-close guard drops them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone

from backend.organism.brain_persistence import (
    OrganismBrain,
    SHADOW_EXIT_TELEMETRY_FILE,
    MODEL_SWAP_AUDIT_FILE,
    PREVIOUS_MODEL_DIR,
)
from backend.organism.continuous_learner import TradeRecord
from backend.organism.governance import GovernanceController
from backend.organism.regime import RegimeDetector
from backend.organism.experimental.shadow_exit import _ShadowExitMixin


# ── Minimal real-save stubs (mirrors test_organism_blueprint_persistence) ──

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
    total_trades: int = 5
    cumulative_pnl: float = -12.0
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


def _do_full_save(brain: OrganismBrain) -> None:
    brain.save(
        signal_gen=_StubSignalGenerator(),
        learner=_StubLearner(),
        equity_curve=[100000.0, 100010.0],
        all_trades=[TradeRecord(
            symbol="AAPL", direction=1.0, entry_price=100.0, exit_price=101.0,
            entry_bar=1, exit_bar=2, shares=10, pnl=10.0, exit_reason="test",
            predicted_return=0.01, actual_return=0.01, confidence=0.7,
        )],
        epoch_metrics=[],
        peak_equity=100010.0,
        evolved_params={"alpha_weight_ml": 0.35},
        governance_controller=GovernanceController(),
        regime_detector=RegimeDetector(),
    )


def _plant_sidecars(brain_dir: Path) -> None:
    (brain_dir / SHADOW_EXIT_TELEMETRY_FILE).write_text(
        '{"schema":"shadow_exit_v1","symbol":"META","qty":3.0,"delta_gross":-0.525}\n'
    )
    (brain_dir / MODEL_SWAP_AUDIT_FILE).write_text('{"swap":1,"gen":389}\n')
    prev = brain_dir / PREVIOUS_MODEL_DIR
    prev.mkdir(exist_ok=True)
    (prev / "ml_classifier.joblib").write_bytes(b"PREVIOUS_MODEL_BYTES")


class TestSwapPreservesSidecars:
    """A full atomic-swap save must not delete the append-only sidecars."""

    def test_full_save_preserves_sidecars(self, tmp_path):
        brain_dir = tmp_path / "brain"
        brain = OrganismBrain(brain_dir=brain_dir)
        _do_full_save(brain)          # establish a head
        _plant_sidecars(brain_dir)    # sidecars now live in the head
        _do_full_save(brain)          # the swap that used to delete them

        assert (brain_dir / SHADOW_EXIT_TELEMETRY_FILE).exists()
        assert "META" in (brain_dir / SHADOW_EXIT_TELEMETRY_FILE).read_text()
        assert (brain_dir / MODEL_SWAP_AUDIT_FILE).exists()
        assert (brain_dir / PREVIOUS_MODEL_DIR / "ml_classifier.joblib").read_bytes() \
            == b"PREVIOUS_MODEL_BYTES"

    def test_backup_captures_sidecars_and_previous_model(self, tmp_path):
        brain_dir = tmp_path / "brain"
        brain = OrganismBrain(brain_dir=brain_dir)
        _do_full_save(brain)
        _plant_sidecars(brain_dir)
        _do_full_save(brain)          # this save mints a backup of the head

        backups = sorted((brain_dir / "backups").iterdir())
        assert backups, "expected at least one backup"
        latest = backups[-1]
        assert (latest / SHADOW_EXIT_TELEMETRY_FILE).exists()
        assert (latest / MODEL_SWAP_AUDIT_FILE).exists()
        # _create_backup previously copied only files — previous_model/ (a dir)
        # was never captured; now it is.
        assert (latest / PREVIOUS_MODEL_DIR / "ml_classifier.joblib").exists()

    def test_restart_reloads_head_with_sidecars_intact(self, tmp_path):
        brain_dir = tmp_path / "brain"
        brain = OrganismBrain(brain_dir=brain_dir)
        _do_full_save(brain)
        _plant_sidecars(brain_dir)
        _do_full_save(brain)

        # Simulate a container restart: a fresh brain object loads the head.
        reloaded = OrganismBrain(brain_dir=brain_dir)
        assert reloaded.load() is True
        assert (brain_dir / SHADOW_EXIT_TELEMETRY_FILE).exists()
        assert (brain_dir / MODEL_SWAP_AUDIT_FILE).exists()
        assert (brain_dir / PREVIOUS_MODEL_DIR).is_dir()
        # A clean save/reload must not have quarantined anything.
        assert not list(brain_dir.glob("corrupt_head_*"))


# ── Real-close guard on the shadow-exit recorder ──

class _FakeRecorder:
    def __init__(self):
        self.rows = []

    def write(self, row):
        self.rows.append(row)


def _make_shadow_host(recorder, qty):
    """Minimal host exposing the attributes _shadow_evaluate_exits reads, wired
    so symbol 'X' was open last tick and is gone now → the reconcile/write
    branch fires with the given qty."""
    shadow_levels = SimpleNamespace(
        entry_price=100.0, direction=1.0, highest_favorable=105.0, bars_held=3,
    )
    return SimpleNamespace(
        _shadow_exit=recorder,
        _shadow_engine=SimpleNamespace(
            learning_mode=False, alt_policy="retracement",
            alt_retrace_frac=0.6, alt_min_fav_r=1.0,
            check_exit=lambda *a, **k: SimpleNamespace(should_exit=False, reason=""),
        ),
        exit_engine=SimpleNamespace(learning_mode=False),
        _last_prices={"X": 104.0},
        _last_regime="chop",
        _last_positions={},
        _last_bar_times={},
        _tick_count=5,
        _now_fn=lambda: datetime(2026, 7, 23, tzinfo=timezone.utc),
        _exit_levels={},                       # X is gone this tick → reconcile
        _shadow_levels={"X": shadow_levels},
        _shadow_pending={"X": {
            "qty": qty, "pnl": 1.0, "reason": "retrace",
            "price": 104.0, "bars_held": 3,
        }},
        _shadow_prev_syms={"X"},
        _shadow_last_price={"X": 104.0},
        _shadow_bar_seen={},
        _symbol_exit_type={"X": "stop_loss"},
    )


class TestQuarantineGuard:
    """Task 6: backups/quarantine/ holds moved-aside corrupt heads. It must
    survive backup pruning and never be treated as a restore candidate."""

    def test_quarantine_dir_survives_backup_pruning(self, tmp_path):
        brain_dir = tmp_path / "brain"
        brain = OrganismBrain(brain_dir=brain_dir)
        _do_full_save(brain)
        q = brain_dir / "backups" / "quarantine" / "corrupt_head_x"
        q.mkdir(parents=True)
        (q / "manifest.json").write_text("{}")
        # Exceed MAX_BACKUPS (5) so the pruner runs several times.
        for _ in range(7):
            _do_full_save(brain)
        assert q.exists(), "quarantine/ must not be pruned as if it were a backup"
        real = [d for d in (brain_dir / "backups").iterdir()
                if d.is_dir() and d.name.startswith("brain_gen")]
        assert len(real) <= 5

    def test_quarantine_dir_is_not_a_restore_candidate(self, tmp_path):
        brain_dir = tmp_path / "brain"
        brain = OrganismBrain(brain_dir=brain_dir)
        _do_full_save(brain)                       # establish the head
        _do_full_save(brain)                       # 2nd save mints a real backup
        # Corrupt the live HEAD so load() falls into the backup-restore path.
        (brain_dir / "manifest.json").write_text("{ not json")
        # A quarantine dir that would THROW if the loader tried to restore it.
        q = brain_dir / "backups" / "quarantine" / "corrupt_head_x"
        q.mkdir(parents=True)
        (q / "manifest.json").write_text("{ also not json")
        reloaded = OrganismBrain(brain_dir=brain_dir)
        assert reloaded.load() is True             # restored from the brain_gen backup


class TestRealCloseGuard:
    def test_qty_zero_row_is_not_emitted(self):
        rec = _FakeRecorder()
        host = _make_shadow_host(rec, qty=0.0)
        _ShadowExitMixin._shadow_evaluate_exits(host, None)
        assert rec.rows == [], "qty=0 replay/test row must be suppressed"
        # State for the reconciled symbol is still cleared.
        assert "X" not in host._shadow_pending

    def test_qty_positive_row_is_emitted(self):
        rec = _FakeRecorder()
        host = _make_shadow_host(rec, qty=3.0)
        _ShadowExitMixin._shadow_evaluate_exits(host, None)
        assert len(rec.rows) == 1
        assert rec.rows[0]["symbol"] == "X"
        assert rec.rows[0]["qty"] == 3.0


# ── Finalization 2026-07-29 item 3(b): non-armed real close emits its row ──
# Regression scenario = the first forward fill (SH 2026-07-27): a real position
# went straight to its stop, the retracement shadow never armed (no
# _shadow_pending entry), the reconcile branch hardcoded qty=0.0, and the
# qty>0 real-close guard silently suppressed the row. Fixed by capturing qty
# from live positions while the position is OPEN (_shadow_obs_qty).


def _make_two_tick_host(recorder, open_qty):
    """Host for a two-tick run: tick 1 sym open (never triggers the shadow),
    tick 2 sym gone → reconcile. Mirrors the real mixin lifecycle."""
    shadow_levels = SimpleNamespace(
        entry_price=33.59, direction=1.0, highest_favorable=33.60, bars_held=1,
    )
    return SimpleNamespace(
        _shadow_exit=recorder,
        _shadow_engine=SimpleNamespace(
            learning_mode=False, alt_policy="retracement",
            alt_retrace_frac=0.6, alt_min_fav_r=1.0,
            # Never arms — the straight-to-stop case.
            check_exit=lambda *a, **k: SimpleNamespace(should_exit=False, reason=""),
        ),
        exit_engine=SimpleNamespace(learning_mode=False),
        _last_prices={"SH": 33.55},
        _last_regime="chop",
        _last_positions={"SH": {"qty": open_qty}},
        _last_bar_times={},
        _tick_count=89501,
        _now_fn=lambda: datetime(2026, 7, 27, tzinfo=timezone.utc),
        _exit_levels={"SH": shadow_levels},   # OPEN at tick 1
        _shadow_levels={},
        _shadow_pending={},
        _shadow_prev_syms=set(),
        _shadow_last_price={},
        _shadow_bar_seen={},
        _symbol_exit_type={"SH": "stop_loss"},
    )


class TestNonArmedRealCloseEmits:
    def test_real_close_without_shadow_trigger_emits_exactly_one_row(self):
        rec = _FakeRecorder()
        host = _make_two_tick_host(rec, open_qty=59)
        # Tick 1: position open, shadow observes qty but never arms.
        _ShadowExitMixin._shadow_evaluate_exits(host, None)
        assert rec.rows == []
        # Tick 2: position closed (stop_loss) → reconcile must emit ONE row.
        host._exit_levels = {}
        host._last_positions = {}
        _ShadowExitMixin._shadow_evaluate_exits(host, None)
        assert len(rec.rows) == 1, "real non-armed close must emit its row"
        row = rec.rows[0]
        assert row["symbol"] == "SH"
        assert row["qty"] == 59.0
        assert row["shadow_triggered"] is False
        assert row["shadow_reason"] == "agreed_held_to_real_close"
        assert row["real_exit_reason"] == "stop_loss"
        # Agreement row: shadow held to the real close → delta is zero.
        assert row["delta_gross"] == 0.0
        # Tracking state fully cleared (incl. the observed-qty map).
        assert host._shadow_obs_qty == {}

    def test_never_held_symbol_still_suppressed(self):
        """Replay/test symbols that never held shares must stay suppressed —
        the original Task-2 pollution class."""
        rec = _FakeRecorder()
        host = _make_two_tick_host(rec, open_qty=0)   # tracked but never held
        _ShadowExitMixin._shadow_evaluate_exits(host, None)
        host._exit_levels = {}
        host._last_positions = {}
        _ShadowExitMixin._shadow_evaluate_exits(host, None)
        assert rec.rows == [], "qty=0 synthetic reconciliation must not emit"
