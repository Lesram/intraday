"""Audit 2026-10-05 surface regime isolation (C09-01, as adjusted by the verifier).

As built and as frozen, the routed market regime is the plain argmax of averaged
single-shot probabilities with sector-breadth conditioning: every per-symbol and
per-ETF ``detect()`` inside ``detect_market_regime`` / ``detect_cross_asset_regime``
starts from the detector's running prior and the prior is put back afterwards.
In production that prior is empty, so the EMA smoothing and the hysteresis band
never carry across ticks. That is what the forward verdict was measured on and
it is NOT changed here.

The latent hazard: on a tick with no usable XLK/XLE frame the SPY-only fallback
called ``detect()`` on the shared detector, which wrote ``_smoothed_probs`` and
``_history``. The aggregate paths then restored that stale vector into every
later per-symbol detect (and every brain save persisted it), so a single
SPY-only tick could pin the routed label for good (verifier, real bars: chop on
4,593 of 4,608 later ticks, or high_vol on all 4,079).

Fix: the fallback calls ``RegimeDetector.detect_isolated()``, which is
``detect()`` with the running state saved and restored. Its own label is
unchanged; nothing is left behind for later ticks. Unhashed observability:
``status()['regime']`` and the transfer record report the routed label
(``_last_regime``), and a CRITICAL tripwire logs once if the main detector's
prior is ever non-empty.

The engine runs the REAL ``_live_tick_inner`` with the REAL RegimeDetector;
only external services (broker, data fetch, brain save) are faked.
"""
from __future__ import annotations

import copy
import inspect
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backend.organism.regime import RegimeDetector

NOW = datetime(2026, 10, 1, 15, 0, 5, tzinfo=UTC)  # Thursday 11:00:05 ET
CYCLE_S = 15.7  # production tick cycle: 10 s sleep + tick time
UNIVERSE = ("SPY", "MSFT", "GOOGL", "XLK", "XLE")
TRIPWIRE = "REGIME PRIOR TRIPWIRE"

# No usable sector ETF this tick, SPY present: the SPY-only fallback branch.
FALLBACK_HIGH_VOL = {"SPY": "high_vol", "MSFT": "quiet", "GOOGL": "quiet"}
QUIET = {s: "quiet" for s in UNIVERSE}
UP = {s: "up" for s in UNIVERSE}
HIGH = {"SPY": "high_vol", "MSFT": "high_vol", "GOOGL": "quiet", "XLK": "high_vol", "XLE": "quiet"}
MIXED = {"SPY": "up", "MSFT": "quiet", "GOOGL": "down", "XLK": "up", "XLE": "down"}
SEQUENCE = [QUIET, UP, HIGH, MIXED, QUIET]
# Stateless cross-asset labels of SEQUENCE (a brand-new detector per tick).
SEQUENCE_LABELS = ["chop", "trending_up", "high_vol", "trending_up", "chop"]


def regime_frame(now, kind: str, n: int = 120, base: float = 100.0) -> pd.DataFrame:
    """A feature frame whose regime is known: close/volume/atr_14 drive the detector."""
    ts = pd.date_range(end=pd.Timestamp(now) - pd.Timedelta(minutes=1), periods=n,
                       freq="1min", tz="UTC")
    i = np.arange(n, dtype=float)
    if kind == "quiet":      # flat, ATR between the low/high thresholds -> chop
        closes, atr = base + 0.001 * np.sin(i), 0.001
    elif kind == "high_vol":  # +-0.5% zigzag, ATR 1% of price -> high_vol
        closes, atr = base * (1 + 0.005 * np.where(i % 2 == 0, 1.0, -1.0)), 0.01
    elif kind == "up":
        closes, atr = base * (1 + 0.0005 * i), 0.001
    elif kind == "down":
        closes, atr = base * (1 - 0.0005 * i), 0.001
    else:
        raise ValueError(kind)
    return pd.DataFrame({"timestamp": ts, "open": closes, "high": closes * 1.0005,
                         "low": closes * 0.9995, "close": closes, "volume": 50_000.0,
                         "atr_14": atr, "_nan_missingness": 0.0})


def frames(kinds: dict[str, str], now=NOW) -> dict[str, pd.DataFrame]:
    return {sym: regime_frame(now, kind) for sym, kind in kinds.items()}


def new_detector() -> RegimeDetector:
    """The live engine's detector configuration on 1-minute bars."""
    return RegimeDetector(is_intraday=True, bars_per_day=390)


def cross_asset(detector: RegimeDetector, feats: dict[str, pd.DataFrame]):
    """The production cross-asset call, sector selection as in _live_tick_inner."""
    sectors = {s: feats[s] for s in RegimeDetector.SECTOR_ETFS
               if s in feats and len(feats[s]) >= 10}
    return detector.detect_cross_asset_regime(feats, sector_features=sectors)


class FakeTradingClient:
    """alpaca-py TradingClient stand-in for a flat account."""

    def get_all_positions(self):
        return []

    def get_account(self):
        return SimpleNamespace(portfolio_value="100000", buying_power="100000")


def make_engine(tmp_path):
    """Engine with every external dependency mocked; regime detection is real."""
    from backend.organism.live_engine import OrganismLiveEngine
    from backend.services.positions_service import PositionsService

    order_service = MagicMock()
    order_service.submit_symbol_order = AsyncMock(
        return_value={"order_id": "o1", "status": "submitted"})
    clock = {"now": NOW}
    with patch("backend.organism.brain_persistence.OrganismBrain.load", return_value=False), \
         patch("backend.organism.brain_persistence.OrganismBrain.exists",
               new_callable=lambda: property(lambda self: False)), \
         patch("backend.organism.live_engine.BackgroundTrainer") as bg_cls, \
         patch("backend.organism.live_engine.MarketScanner", return_value=MagicMock()):
        bg = MagicMock()
        bg.start = AsyncMock()
        bg.stop = AsyncMock()
        bg.is_training = False
        bg_cls.return_value = bg
        engine = OrganismLiveEngine(
            data_client=MagicMock(), order_service=order_service,
            positions_service=PositionsService(trading_client=FakeTradingClient()),
            brain_dir=str(tmp_path / "brain"), universe=list(UNIVERSE),
            timeframe="1Min",  # the production timeframe
        )
    engine._now_fn = lambda: clock["now"]
    engine._time_fn = lambda: clock["now"].timestamp()
    engine._get_equity = AsyncMock(return_value=100_000.0)
    engine._reconcile_fills = AsyncMock()
    engine._save_brain = MagicMock()
    engine._check_tick_invariants = MagicMock()
    engine._initialized = True
    return engine, clock


async def tick(engine, clock, i: int, kinds: dict[str, str]) -> dict[str, pd.DataFrame]:
    """One real live_tick on frames of the given kinds; returns the frames used."""
    clock["now"] = NOW + timedelta(seconds=CYCLE_S * i)
    feats = frames(kinds, clock["now"])
    engine._fetch_and_compute_features = AsyncMock(return_value=feats)
    with patch("backend.organism.live_engine.LONG_ONLY", True):
        await engine.live_tick()
    return feats


def tripwire_records(caplog):
    return [r for r in caplog.records
            if r.levelno == logging.CRITICAL and TRIPWIRE in r.getMessage()]


# ── the frozen aggregate design (must not change) ────────────────────────────
def test_aggregate_routed_label_carries_no_state_with_an_empty_prior():
    """No aggregate EMA or hysteresis: each routed label equals a brand-new
    detector's, and the detector's running state stays empty (what the forward
    sample was measured on). Turning on aggregate smoothing breaks this test."""
    detector = new_detector()
    for kinds, label in zip(SEQUENCE, SEQUENCE_LABELS):
        feats = frames(kinds)
        routed = cross_asset(detector, feats)
        fresh = cross_asset(new_detector(), feats)
        assert routed.primary == fresh.primary == label
        assert routed.probabilities == fresh.probabilities
        assert detector._smoothed_probs == {} and detector._history == []
        assert detector.current_regime == "unknown"


def test_the_old_fallback_pattern_pins_every_later_label():
    """The hazard these tests guard against: detect(spy) on the shared detector
    leaves its vector behind and every later cross-asset label follows it."""
    detector = new_detector()
    spy_only = detector.detect(regime_frame(NOW, "high_vol"))
    assert spy_only.primary == "high_vol"
    assert detector._history == ["high_vol"] and detector._smoothed_probs
    pinned = [cross_asset(detector, frames(kinds)).primary for kinds in SEQUENCE]
    assert pinned == ["high_vol"] * len(SEQUENCE) != SEQUENCE_LABELS
    assert detector.to_persistence_dict()["history"] == ["high_vol"]  # and it persists


# ── C09-01: detect_isolated is detect() without the state write ──────────────
@pytest.mark.parametrize("prior_kind", [None, "high_vol"])
def test_detect_isolated_returns_what_detect_returns_and_restores_state(prior_kind):
    detector = new_detector()
    if prior_kind:  # a detector that already carries a prior and a history
        detector.detect(regime_frame(NOW, prior_kind))
    reference = copy.deepcopy(detector)
    probs_before, history_before = dict(detector._smoothed_probs), list(detector._history)

    got = detector.detect_isolated(regime_frame(NOW, "up"))
    want = reference.detect(regime_frame(NOW, "up"))

    assert (got.primary, got.probabilities, got.confidence, got.churn_rate) == (
        want.primary, want.probabilities, want.confidence, want.churn_rate)
    assert detector._smoothed_probs == probs_before
    assert detector._history == history_before
    assert detector._last_state is got  # updated, as on every routed tick
    assert detector._aggregate_history == []


def test_detect_isolated_restores_state_when_detect_fails_late(monkeypatch):
    detector = new_detector()

    def late_failure():  # detect() has already written the prior and history
        raise RuntimeError("late failure")

    monkeypatch.setattr(detector, "_compute_churn", late_failure)
    with pytest.raises(RuntimeError, match="late failure"):
        detector.detect_isolated(regime_frame(NOW, "high_vol"))
    assert detector._smoothed_probs == {}
    assert detector._history == []


# ── C09-01: the SPY-only fallback cannot write the shared detector's state ───
async def test_spy_only_fallback_keeps_its_label_and_leaves_no_prior(tmp_path):
    engine, clock = make_engine(tmp_path)
    detector = engine.regime_detector
    before = copy.deepcopy(detector)

    feats = await tick(engine, clock, 1, FALLBACK_HIGH_VOL)

    # Same label and probabilities as the pre-fix detect(spy) from the same state.
    expected = before.detect(feats["SPY"])
    assert engine._last_regime == expected.primary == "high_vol"
    assert detector._last_state.probabilities == expected.probabilities
    # Nothing left behind: no prior, no history, nothing for the brain to persist.
    assert detector._smoothed_probs == {}
    assert detector._history == []
    persisted = detector.to_persistence_dict()
    assert persisted["smoothed_probs"] == {} and persisted["history"] == []


async def test_later_routed_labels_ignore_an_earlier_spy_only_tick(tmp_path):
    with_fallback, clock_a = make_engine(tmp_path / "a")
    without, clock_b = make_engine(tmp_path / "b")

    await tick(with_fallback, clock_a, 1, FALLBACK_HIGH_VOL)
    assert with_fallback._last_regime == "high_vol"
    labels_a, labels_b = [], []
    for i, kinds in enumerate(SEQUENCE, start=2):
        await tick(with_fallback, clock_a, i, kinds)
        await tick(without, clock_b, i, kinds)
        labels_a.append(with_fallback._last_regime)
        labels_b.append(without._last_regime)
        assert with_fallback.regime_detector._smoothed_probs == {}
        assert with_fallback.regime_detector._history == []

    assert labels_a == labels_b == SEQUENCE_LABELS


async def test_consecutive_spy_only_ticks_do_not_blend(tmp_path):
    """A second SPY-only tick reads SPY alone, not 0.7 x the first one's vector."""
    engine, clock = make_engine(tmp_path)
    await tick(engine, clock, 1, FALLBACK_HIGH_VOL)
    await tick(engine, clock, 2, {"SPY": "up", "MSFT": "quiet", "GOOGL": "quiet"})
    assert engine._last_regime == "trending_up"
    fresh = new_detector().detect(regime_frame(NOW, "up"))
    assert engine.regime_detector._last_state.probabilities == fresh.probabilities
    assert engine.regime_detector._smoothed_probs == {} and engine.regime_detector._history == []


async def test_fallback_restores_the_running_state_even_when_detect_raises(tmp_path):
    engine, clock = make_engine(tmp_path)
    detector = engine.regime_detector

    def failing_detect(_features):
        detector._smoothed_probs = {"high_vol": 1.0}
        detector._history.append("high_vol")
        raise RuntimeError("detect failed mid-way")

    detector.detect = failing_detect
    clock["now"] = NOW + timedelta(seconds=CYCLE_S)
    engine._fetch_and_compute_features = AsyncMock(
        return_value=frames(FALLBACK_HIGH_VOL, clock["now"]))
    with patch("backend.organism.live_engine.LONG_ONLY", True):
        result = await engine.live_tick()  # the tick's own handler records the failure
    assert any("detect failed mid-way" in e for e in result.errors)
    assert detector._smoothed_probs == {}
    assert detector._history == []


def test_the_tick_never_calls_stateful_detect_on_the_shared_detector():
    from backend.organism.live_engine import OrganismLiveEngine

    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert "self.regime_detector.detect(" not in src
    start = src.index("elif spy_features is not None and len(spy_features) >= 10:")
    branch = src[start:src.index("else:", start)]
    assert "self.regime_detector.detect_isolated(spy_features)" in branch


# ── observability: the routed label, not the detector's frozen 'unknown' ─────
async def test_status_regime_reports_the_routed_label(tmp_path):
    engine, clock = make_engine(tmp_path)
    await tick(engine, clock, 1, QUIET)
    assert engine._last_regime == "chop"
    assert engine.regime_detector.current_regime == "unknown"  # never advances
    assert engine.status()["regime"] == "chop"
    await tick(engine, clock, 2, UP)
    assert engine.status()["regime"] == "trending_up"
    await tick(engine, clock, 3, FALLBACK_HIGH_VOL)
    assert engine.status()["regime"] == "high_vol"


def test_status_regime_without_a_tick_is_unknown(tmp_path):
    engine, _ = make_engine(tmp_path)
    assert engine.status()["regime"] == "unknown"
    del engine._last_regime  # engines built without __init__ (as some fixtures do)
    assert engine.status()["regime"] == "unknown"


def test_transfer_record_uses_the_routed_label(tmp_path):
    from backend.organism.live_engine import OrganismLiveEngine

    engine, _ = make_engine(tmp_path)
    engine._last_regime = "trending_up"
    engine.transfer_engine = MagicMock()
    engine.signal_gen._get_feature_importance = MagicMock(return_value={})
    with patch.object(engine.brain, "walk_forward_gate", return_value=(True, "ok")), \
         patch.object(engine.brain, "save") as brain_save, \
         patch.object(OrganismLiveEngine, "_persist_exit_levels_standalone"):
        OrganismLiveEngine._save_brain(engine)  # the real method, not the fixture mock
    brain_save.assert_called_once()
    engine.transfer_engine.record_run.assert_called_once()
    assert engine.transfer_engine.record_run.call_args.kwargs["regime"] == "trending_up"
    assert engine.regime_detector.current_regime == "unknown"


def test_status_and_transfer_record_do_not_read_the_detector_label():
    from backend.organism.live_engine import OrganismLiveEngine

    for method in (OrganismLiveEngine.status, OrganismLiveEngine._save_brain):
        src = inspect.getsource(method)
        assert "regime_detector.current_regime" not in src
        assert "_last_regime" in src


# ── tripwire: CRITICAL once if the main detector ever carries a prior ────────
async def test_tripwire_logs_critical_once_for_a_restored_prior(tmp_path, caplog):
    engine, clock = make_engine(tmp_path)
    # What OrganismBrain.apply_regime_state does with a regime_state.json that
    # carries a frozen prior (the startup guard is a separate follow-up).
    engine.regime_detector.from_persistence_dict({
        "history": ["high_vol"],
        "smoothed_probs": {"trending_up": 0.033, "trending_down": 0.09, "chop": 0.148,
                           "high_vol": 0.663, "low_vol": 0.033, "stress": 0.033},
    })
    with caplog.at_level(logging.CRITICAL):
        await tick(engine, clock, 1, QUIET)
        await tick(engine, clock, 2, QUIET)
    hits = tripwire_records(caplog)
    assert len(hits) == 1
    assert "history_len=1" in hits[0].getMessage()


async def test_tripwire_stays_silent_on_clean_and_spy_only_ticks(tmp_path, caplog):
    engine, clock = make_engine(tmp_path)
    with caplog.at_level(logging.CRITICAL):
        await tick(engine, clock, 1, FALLBACK_HIGH_VOL)  # used to leave a prior
        await tick(engine, clock, 2, QUIET)
    assert tripwire_records(caplog) == []


def test_tripwire_never_raises_and_latches(caplog):
    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    with caplog.at_level(logging.DEBUG):
        engine._check_regime_prior_tripwire()  # no detector at all
        engine.regime_detector = SimpleNamespace(_smoothed_probs=None, _history=None)
        engine._check_regime_prior_tripwire()  # unusable state
        assert tripwire_records(caplog) == []
        engine.regime_detector = SimpleNamespace(_smoothed_probs={}, _history=["chop"])
        engine._check_regime_prior_tripwire()
        engine._check_regime_prior_tripwire()
    assert len(tripwire_records(caplog)) == 1


def test_tripwire_runs_outside_the_hashed_tick():
    """Log-only observability stays out of the frozen _live_tick_inner hash."""
    from backend.organism.live_engine import OrganismLiveEngine

    assert "_check_regime_prior_tripwire" in inspect.getsource(OrganismLiveEngine.live_tick)
    assert "_check_regime_prior_tripwire" not in inspect.getsource(
        OrganismLiveEngine._live_tick_inner)
