"""Phase 1 step 6 — Breakout KEEP-DISTINCT: extraction onto the contract.

BreakoutStrategy wraps the unchanged BreakoutScanner and reproduces the live
pure-breakout ENTRY decision: surface scanner signals with composite >=
entry_composite_threshold as LONG candidates (direction forced to +1, mirroring
live_engine ~4371). These tests prove the threshold filter, the long-only force,
fail-closed config, and that the adapter faithfully surfaces the scanner's
signals (real-data parity) — without depending on a particular synthetic bar set
clearing the live 0.55 gate.
"""
from __future__ import annotations

import pandas as pd
import pytest

from backend.organism.breakout_scanner import BreakoutScanner, BreakoutSignal
from backend.organism.strategies import Candidate, build_strategy, registered_names
from backend.organism.strategies.breakout import BreakoutStrategy
from backend.organism.strategies.strategy_config import get_config
from backend.organism.replay_simulator import make_features_dict


def _strat(**overrides):
    cfg = get_config("breakout")
    cfg.update(overrides)
    return BreakoutStrategy(cfg)


def _sig(symbol, composite, direction):
    # All scoring sub-fields are irrelevant to the adapter (it reads only
    # symbol/composite_score/direction); default them.
    return BreakoutSignal(
        symbol=symbol, composite_score=composite, squeeze_score=0.0,
        volume_score=0.0, contraction_score=0.0, rs_score=0.0, pivot_score=0.0,
        flow_score=0.0, direction=direction, squeeze_fired=False, volume_ratio=1.0,
    )


def test_registered_and_builds_from_config():
    assert "breakout" in registered_names()
    s = build_strategy("breakout", get_config("breakout"))
    assert isinstance(s, BreakoutStrategy)
    assert s.required_features() == {"open", "high", "low", "close", "volume"}
    assert s.live_routing is True  # a live capital path (Rule A)
    assert s.eligible_regimes() == {"trending_up", "high_vol", "chop", "trending_down"}


def test_validate_config_fail_closed():
    with pytest.raises(ValueError):
        BreakoutStrategy({"eligible_regimes": ["x"]})  # missing scanner params


def test_long_only_forces_direction_and_threshold_filters(monkeypatch):
    """Deterministic: stub the scanner so the mapping is exercised regardless of
    data — a short, high-composite signal must come out LONG; a sub-threshold one
    must be dropped."""
    s = _strat(entry_composite_threshold=0.55)
    fake = [
        _sig("UP", 0.80, 1.0),
        _sig("DN", 0.70, -1.0),   # short -> forced long
        _sig("WEAK", 0.40, 1.0),  # below 0.55 -> dropped
    ]
    monkeypatch.setattr(s._scanner, "scan", lambda data, spy: fake)
    cands = s.scan({"UP": pd.DataFrame({"close": [1]})}, "trending_up")
    by = {c.symbol: c for c in cands}
    assert set(by) == {"UP", "DN"}                      # WEAK filtered by 0.55 gate
    assert all(isinstance(c, Candidate) for c in cands)
    assert by["UP"].direction == 1.0 and by["DN"].direction == 1.0  # long-only force
    assert by["DN"].confidence == 0.70                  # min(composite,1.0)
    assert by["UP"].extra["composite_score"] == 0.80


def test_short_emitted_when_long_only_disabled(monkeypatch):
    s = _strat(entry_composite_threshold=0.55, long_only=False)
    monkeypatch.setattr(s._scanner, "scan", lambda data, spy: [_sig("DN", 0.70, -1.0)])
    cands = s.scan({"DN": pd.DataFrame({"close": [1]})}, "trending_up")
    assert cands[0].direction == -1.0  # honors the scanner's direction


def test_realdata_adapter_surfaces_scanner_signals():
    """Real-data parity: with the threshold dropped to the scanner's own floor,
    the adapter must emit EXACTLY the scanner's signals, all as long candidates."""
    syms = ["AAPL", "MSFT", "NVDA", "GOOGL", "SPY"]
    feats = make_features_dict(syms, n=120, seed=7, trend="up")

    # Reference scanner configured identically to the strategy's internal one.
    cfg = get_config("breakout")
    ref = BreakoutScanner(top_n=int(cfg["top_n"]))
    ref.W_SQUEEZE, ref.W_VOLUME, ref.W_CONTRACTION = cfg["w_squeeze"], cfg["w_volume"], cfg["w_contraction"]
    ref.W_RS, ref.W_PIVOT, ref.W_FLOW = cfg["w_rs"], cfg["w_pivot"], cfg["w_flow"]
    ref.MIN_BREAKOUT_SCORE = cfg["min_breakout_score"]
    ref.BB_PERIOD, ref.ATR_SHORT, ref.ATR_LONG, ref.VOL_AVG_PERIOD = (
        cfg["bb_period"], cfg["atr_short"], cfg["atr_long"], cfg["vol_avg_period"])
    data = {s: df for s, df in feats.items()}
    ref_syms = {sig.symbol for sig in ref.scan(data, feats.get("SPY"))}

    s = _strat(entry_composite_threshold=cfg["min_breakout_score"])  # surface all
    cands = s.scan(feats, "trending_up")
    assert {c.symbol for c in cands} == ref_syms
    assert all(c.direction == 1.0 for c in cands)
    assert all(c.strategy_name == "breakout" for c in cands)
