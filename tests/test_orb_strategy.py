"""Phase 1 step 9 — ORB strategy (built to the contract, live_routing:false)."""
from __future__ import annotations

import pandas as pd
import pytest

from backend.organism.orb_scanner import ORBCandidate
from backend.organism.strategies import Candidate, build_strategy, registered_names
from backend.organism.strategies.orb import ORBStrategy
from backend.organism.strategies.strategy_config import get_config


def _strat(**overrides):
    cfg = get_config("orb")
    cfg.update(overrides)
    return ORBStrategy(cfg)


def _oc(symbol="AAPL", direction=1.0, rv_ratio=2.0, triggered=True):
    return ORBCandidate(
        symbol=symbol, direction=direction, rv_ratio=rv_ratio,
        orb_high=101.0, orb_low=99.0, orb_close=100.5, orb_open=100.0,
        current_price=101.2, breakout_triggered=triggered, suggested_stop=99.0,
        atr_at_entry=1.0, timestamp="t",
    )


def test_registered_and_builds_from_config():
    assert "orb" in registered_names()
    s = build_strategy("orb", get_config("orb"))
    assert isinstance(s, ORBStrategy)
    assert s.required_features() == {"open", "high", "low", "close", "volume"}
    assert s.live_routing is False           # Rule A: untested
    assert s.eligible_regimes() == {"high_vol"}


def test_validate_config_fail_closed():
    with pytest.raises(ValueError):
        ORBStrategy({"eligible_regimes": ["high_vol"]})  # missing scanner params


def test_confidence_is_rv_intensity():
    assert ORBStrategy._confidence(2.0) == 0.5      # 2.0/4
    assert ORBStrategy._confidence(4.0) == 1.0      # capped
    assert ORBStrategy._confidence(8.0) == 1.0      # capped


def test_stands_down_without_timestamp():
    s = _strat()
    feats = {"AAPL": pd.DataFrame({"open": [1.0] * 20, "high": [1.0] * 20,
             "low": [1.0] * 20, "close": [1.0] * 20, "volume": [1.0] * 20})}
    assert s.scan(feats, "high_vol") == []


def test_only_triggered_breakouts_emitted_and_direction_honored(monkeypatch):
    s = _strat()
    fake = [
        _oc("UP", 1.0, rv_ratio=2.0, triggered=True),
        _oc("DN", -1.0, rv_ratio=3.0, triggered=True),   # short honored (not long-forced)
        _oc("PENDING", 1.0, rv_ratio=5.0, triggered=False),  # not ready -> dropped
    ]
    monkeypatch.setattr(s._scanner, "scan", lambda data, now, **k: fake)
    idx = pd.date_range("2026-06-10 13:35", periods=10, freq="1min", tz="UTC")
    feats = {"UP": pd.DataFrame({"close": range(10)}, index=idx)}
    cands = s.scan(feats, "high_vol")
    by = {c.symbol: c for c in cands}
    assert set(by) == {"UP", "DN"}                   # PENDING (not triggered) dropped
    assert all(isinstance(c, Candidate) for c in cands)
    assert by["DN"].direction == -1.0                # honors scanner direction
    assert by["DN"].confidence == 0.75               # 3.0/4
    assert by["UP"].extra["rv_ratio"] == 2.0
