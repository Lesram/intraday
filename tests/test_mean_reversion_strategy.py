"""Phase 1 step 7 — mean-reversion extraction (registered, live_routing:false).

MR is a benchmark only (evidence-negative after costs), so there is no live-
capital path to keep parity with. These tests prove contract conformance, the
verbatim/fail-closed config, the faithful confidence mapping (== live MR
composite), the timestamp-derived entry-window behavior, and that the adapter
surfaces the scanner's candidates.
"""
from __future__ import annotations

import pandas as pd
import pytest

from backend.organism.mean_reversion_scanner import MeanReversionCandidate
from backend.organism.strategies import Candidate, build_strategy, registered_names
from backend.organism.strategies.mean_reversion import MeanReversionStrategy
from backend.organism.strategies.strategy_config import get_config


def _strat(**overrides):
    cfg = get_config("mean_reversion")
    cfg.update(overrides)
    return MeanReversionStrategy(cfg)


def _mrc(symbol="XLF", direction=1.0, abs_distance_atr=4.0):
    return MeanReversionCandidate(
        symbol=symbol, direction=direction, current_price=100.0, vwap=104.0,
        distance_atr=-abs_distance_atr, abs_distance_atr=abs_distance_atr,
        target_price=103.2, stop_price=99.0, expected_r_r=3.2, atr_at_entry=1.0,
        session_high=105.0, session_low=99.5, n_bars_in_session=30, timestamp="t",
    )


def test_registered_and_builds_from_config():
    assert "mean_reversion" in registered_names()
    s = build_strategy("mean_reversion", get_config("mean_reversion"))
    assert isinstance(s, MeanReversionStrategy)
    assert s.required_features() == {"open", "high", "low", "close", "volume"}
    assert s.live_routing is False          # Rule A: evidence-negative benchmark
    assert s.eligible_regimes() == {"chop"}


def test_validate_config_fail_closed():
    with pytest.raises(ValueError):
        MeanReversionStrategy({"eligible_regimes": ["chop"]})  # missing params


def test_confidence_matches_live_mr_composite():
    # live_engine ~4770: min(1, 0.30 + 0.15*abs_distance_atr)
    assert MeanReversionStrategy._confidence(2.5) == pytest.approx(0.675)
    assert MeanReversionStrategy._confidence(4.0) == pytest.approx(0.90)
    assert MeanReversionStrategy._confidence(5.0) == 1.0     # capped
    assert MeanReversionStrategy._confidence(100.0) == 1.0   # capped


def test_stands_down_without_timestamp():
    s = _strat()
    # plain RangeIndex frames -> no derivable "now" -> stand down
    feats = {"XLF": pd.DataFrame({"open": [1.0] * 20, "high": [1.0] * 20,
             "low": [1.0] * 20, "close": [1.0] * 20, "volume": [1.0] * 20})}
    assert s.scan(feats, "chop") == []


def test_scan_delegates_with_derived_now_and_maps_candidate(monkeypatch):
    s = _strat()
    captured = {}

    def fake_scan(data, now, session_date=None):
        captured["now"] = now
        return [_mrc(symbol="XLF", direction=1.0, abs_distance_atr=4.0)]

    monkeypatch.setattr(s._scanner, "scan", fake_scan)
    idx = pd.date_range("2026-06-10 14:00", periods=20, freq="1min", tz="UTC")
    feats = {"XLF": pd.DataFrame({"close": range(20)}, index=idx)}

    cands = s.scan(feats, "chop")
    assert captured["now"] == idx[-1]               # now derived from latest bar
    assert len(cands) == 1 and isinstance(cands[0], Candidate)
    c = cands[0]
    assert c.symbol == "XLF" and c.direction == 1.0
    assert c.strategy_name == "mean_reversion"
    assert c.confidence == pytest.approx(0.90)       # 0.30 + 0.15*4.0
    assert c.extra["target_price"] == 103.2 and c.extra["expected_r_r"] == 3.2
