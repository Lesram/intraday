from __future__ import annotations


class _Sig:
    def __init__(self, symbol: str, source: str, target_exposure: float, close: float, sma_50: float | None = None):
        self.symbol = symbol
        self.source = source
        self.target_exposure = target_exposure
        self.metadata = {
            "price_close": close,
            "bar_timestamp": "2026-02-07T00:00:00Z",
            "sma_50": sma_50,
            "atr_ratio": 0.02,
        }


def test_policy_weights_are_bounded_and_rate_limited(monkeypatch):
    monkeypatch.setenv("LIVING_STRATEGY_SCORE_EMA_ALPHA", "1.0")
    monkeypatch.setenv("LIVING_STRATEGY_WEIGHT_MAX_DELTA", "0.05")
    monkeypatch.setenv("LIVING_STRATEGY_WEIGHT_MIN", "0.10")
    monkeypatch.setenv("LIVING_STRATEGY_WEIGHT_MAX", "2.50")
    monkeypatch.setenv("LIVING_STRATEGY_SCORE_MULT", "10.0")

    from backend.strategies.living_policy import LivingPolicyEngine

    policy = LivingPolicyEngine(sessionmaker=None)
    policy.weights["momentum"] = 1.0

    # First observation sets last_obs, no scoring yet
    snap1 = policy.observe_signals(engine_signals=[_Sig("MSFT", "momentum", 1.0, close=100.0, sma_50=90.0)])
    assert 0.10 <= snap1.weights["momentum"] <= 2.50

    # Second observation creates a realized return from 100 -> 101 with direction=+1
    snap2 = policy.observe_signals(engine_signals=[_Sig("MSFT", "momentum", 1.0, close=101.0, sma_50=90.0)])
    # Even if raw wants to jump, it can only move by max_delta
    assert snap2.weights["momentum"] <= 1.05 + 1e-9


def test_policy_breakout_boost_is_small(monkeypatch):
    monkeypatch.setenv("LIVING_STRATEGY_WEIGHT_MAX_DELTA", "0.05")
    from backend.strategies.living_policy import LivingPolicyEngine

    policy = LivingPolicyEngine(sessionmaker=None)
    base = policy.get_weights()["breakout"]

    # With breakout candidates, raw is boosted but still rate-limited
    snap = policy.observe_signals(
        engine_signals=[_Sig("AAPL", "breakout", 1.0, close=200.0, sma_50=190.0)],
        breakout_candidates=["AAPL", "TSLA"],
    )
    assert snap.weights["breakout"] >= base
    assert snap.weights["breakout"] <= base + 0.05 + 1e-9
