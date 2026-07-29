"""Intra 2.0 Phase 1 — Step 1: the Strategy contract + registry + Candidate."""
from __future__ import annotations

import pandas as pd
import pytest

from backend.organism.strategies import (
    Candidate,
    Strategy,
    build_strategy,
    register,
    registered_names,
)
from backend.organism.strategies.registry import get_strategy_class


# ── Candidate ────────────────────────────────────────────────────────────
def test_candidate_normalizes_direction():
    assert Candidate("A", 0.7, 0.9, "m").direction == 1.0
    assert Candidate("A", -3.0, 0.9, "m").direction == -1.0
    assert Candidate("A", 0.0, 0.9, "m").direction == 0.0


def test_candidate_carries_engine_fields():
    c = Candidate("AAPL", 1, 0.8, "momentum",
                  expected_return_source="calibrated_breakout",
                  ml_signal="sig", extra={"breakout": 0.7})
    assert c.symbol == "AAPL" and c.strategy_name == "momentum"
    assert c.expected_return_source == "calibrated_breakout"
    assert c.ml_signal == "sig" and c.extra["breakout"] == 0.7


# ── Strategy contract + registry ─────────────────────────────────────────
@register("dummy_test_strat")
class _Dummy(Strategy):
    def required_features(self):
        return {"ret_5d"}

    def scan(self, features, regime):
        return [Candidate(s, 1.0, 0.5, self.name) for s in features]

    def eligible_regimes(self):
        return {"trending_up"}

    def validate_config(self):
        if self.config.get("thresh", 0.0) < 0:
            raise ValueError("thresh must be >= 0")


def test_registry_register_and_build():
    assert "dummy_test_strat" in registered_names()
    s = build_strategy("dummy_test_strat", {"thresh": 0.5})
    assert s.name == "dummy_test_strat"
    assert s.required_features() == {"ret_5d"}
    assert s.eligible_regimes() == {"trending_up"}
    assert s.live_routing is False  # default: capital gated off (Rule A)


def test_validate_config_fail_closed():
    with pytest.raises(ValueError):
        build_strategy("dummy_test_strat", {"thresh": -1.0})  # validates in __init__


def test_live_routing_reads_config():
    assert build_strategy("dummy_test_strat", {"live_routing": True}).live_routing is True


def test_scan_is_pure_returns_candidates():
    s = build_strategy("dummy_test_strat", {})
    feats = {"AAPL": pd.DataFrame({"ret_5d": [0.01]}), "MSFT": pd.DataFrame({"ret_5d": [0.02]})}
    out = s.scan(feats, "trending_up")
    assert {c.symbol for c in out} == {"AAPL", "MSFT"}
    assert all(isinstance(c, Candidate) for c in out)


def test_unknown_strategy_raises():
    with pytest.raises(KeyError):
        get_strategy_class("does_not_exist")


def test_duplicate_registration_rejected():
    with pytest.raises(ValueError):
        @register("dummy_test_strat")
        class _Other(Strategy):
            def required_features(self): return set()
            def scan(self, features, regime): return []
            def eligible_regimes(self): return set()
            def validate_config(self): return None
