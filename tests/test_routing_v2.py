"""5c Commit A — routing-v2 behavioral probes (engine-level parity lives in
scripts/verify_routing_v2_parity.py; these are the fast candidate-level teeth).
"""
from __future__ import annotations

import pandas as pd

import backend.organism.live_engine as le
from backend.organism.strategy_selector import StrategySelector


class _CountingScanner:
    """Stands in for a stateful scanner: counts scans, returns nothing."""
    def __init__(self):
        self.calls = 0

    def scan(self, *a, **k):
        self.calls += 1
        return []


def _mk_features(n=60):
    idx = pd.date_range("2026-06-01 14:00", periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame({
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
        "volume": 50_000, "timestamp": idx,
    })
    return {"AAPL": df.copy(), "SPY": df.copy()}


def test_scan_all_returns_every_strategy_with_rule_a_tags():
    sel = StrategySelector.from_config(mode="live")
    res = sel.scan_all(_mk_features(), "chop")
    assert set(res) == {"momentum", "breakout", "mean_reversion", "orb"}
    for name, entry in res.items():
        assert set(entry) == {"candidates", "routed"}
    # Rule A: MR/ORB are live_routing:false — never routed in live mode.
    assert res["mean_reversion"]["routed"] is False
    assert res["orb"]["routed"] is False


def test_scan_all_one_strategy_error_never_poisons_the_rest():
    sel = StrategySelector.from_config(mode="live")
    broken = next(s for s in sel.strategies if s.name == "orb")
    broken._scanner = None  # .scan will raise AttributeError
    res = sel.scan_all(_mk_features(), "chop")
    assert res["orb"]["candidates"] == []          # fail-closed = stand down
    assert set(res) == {"momentum", "breakout", "mean_reversion", "orb"}


def test_v2_scan_is_memoized_per_tick(monkeypatch):
    """The ORB/MR/breakout/momentum consumers all ask for the scan result —
    the stateful scanners must be scanned EXACTLY once per tick."""
    eng = object.__new__(le.OrganismLiveEngine)   # no full engine init needed
    eng._tick_count = 7
    counting = _CountingScanner()

    class _Sel:
        def scan_all(self, features, regime):
            counting.scan()
            return {"orb": {"candidates": [], "routed": False}}

    eng._strategy_selector_v2 = _Sel()
    feats = _mk_features()
    for _ in range(4):                             # four consumers, same tick
        eng._scan_all_strategies_v2(feats, "chop")
    assert counting.calls == 1
    eng._tick_count = 8                            # next tick -> fresh scan
    eng._scan_all_strategies_v2(feats, "chop")
    assert counting.calls == 2


def test_v2_scan_fail_closed_returns_empty(monkeypatch):
    eng = object.__new__(le.OrganismLiveEngine)
    eng._tick_count = 1

    class _Boom:
        def scan_all(self, *a):
            raise RuntimeError("boom")

    eng._strategy_selector_v2 = _Boom()
    res = eng._scan_all_strategies_v2(_mk_features(), "chop")
    assert res == {}                               # consumers see no candidates
    assert le.OrganismLiveEngine._v2_raws(res, "orb") == []


def test_v2_raws_unwraps_only_candidates_with_raw():
    from backend.organism.strategies.base import Candidate
    c_with = Candidate(symbol="A", direction=1.0, confidence=0.5,
                       strategy_name="orb", extra={"raw": "RAW_OBJ"})
    c_without = Candidate(symbol="B", direction=1.0, confidence=0.5,
                          strategy_name="orb", extra={})
    res = {"orb": {"candidates": [c_with, c_without], "routed": False}}
    assert le.OrganismLiveEngine._v2_raws(res, "orb") == ["RAW_OBJ"]
    assert le.OrganismLiveEngine._v2_raws(res, "missing") == []


def test_engine_scanner_instances_are_injected_when_selector_built():
    """The v2 selector must wrap the ENGINE's scanner objects (state identity),
    not fresh instances — duplicate stateful scanners would double-fire."""
    eng = object.__new__(le.OrganismLiveEngine)
    eng.breakout_scanner = _CountingScanner()
    eng._mean_reversion_scanner = _CountingScanner()
    eng._orb_scanner = _CountingScanner()
    sel = le.OrganismLiveEngine._get_strategy_selector_v2(eng)
    by_name = {s.name: s for s in sel.strategies}
    assert by_name["breakout"]._scanner is eng.breakout_scanner
    assert by_name["mean_reversion"]._scanner is eng._mean_reversion_scanner
    assert by_name["orb"]._scanner is eng._orb_scanner
    # momentum is a pure function — no scanner attribute contract.
    assert "momentum" in by_name
