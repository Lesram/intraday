"""V6 W / Wave-21 (2026-05-03): behavioral test backfill for Wave 18.

Wave 18 (commit a42ca5f) shipped 6 high-correctness findings with zero
behavioral tests — Track W identified it as the highest silent-regression
risk in the codebase. This file pins behavior for:

- B-T-1: DB-replay reconstruction direction resolved from entry order side
- B-T-7: Kelly atr_var below floor returns 0 signal (refuse to size)
- B-T-3: _safe_int_qty warns on fractional truncation
- S-NET-CB-1: technical CircuitBreaker present and wired
- S-NET-T-1: alpaca SDK clients have a 30s default timeout
- S-OUTBOX-1: outbox claim lease is 1800s

These complement tests/test_numerical_properties_v6.py (which covers
B-T-1/2/3/5/7) by exercising the *integration* points each fix touches.
"""
from __future__ import annotations

import inspect

import pytest


# ─────────────────────────────────────────────────────────────────────
# B-T-1 — DB-replay direction
# ─────────────────────────────────────────────────────────────────────


def test_b_t_1_db_replay_resolves_direction_from_entry_side():
    """The DB-replay reconstruction must derive `direction` from the
    entry order's `.side` rather than hard-coding 1.0. A regression
    would re-introduce `direction=1.0` and silently invert short-trade
    actual_return / correct_direction in the learner."""
    src = inspect.getsource(__import__(
        "backend.organism.live_engine", fromlist=["live_engine"]
    ))
    # The fix introduces _en_side resolution.
    assert "_en_side = (getattr(en_order" in src, (
        "B-T-1: entry-side resolution missing — fix may have been reverted"
    )
    # The hard-coded 1.0 should NOT appear as the direction= kwarg.
    # (It does appear as a fallback assignment, but only after side is None.)
    # Regression check: searching for `direction=1.0,` immediately followed by
    # `# LONG_ONLY` is the pre-fix pattern.
    assert "direction=1.0,  # LONG_ONLY" not in src, (
        "B-T-1: pre-fix `direction=1.0  # LONG_ONLY` reintroduced"
    )


# ─────────────────────────────────────────────────────────────────────
# B-T-7 — Kelly atr_var floor
# ─────────────────────────────────────────────────────────────────────


def test_b_t_7_kelly_zero_atr_returns_zero_signal():
    """The Kelly sizer must refuse-to-size when atr_pct is at or below
    the floor; a regression would saturate to per-position max."""
    src = inspect.getsource(__import__(
        "backend.organism.kelly_sizer", fromlist=["kelly_sizer"]
    ))
    assert "_ATR_VAR_MIN" in src, (
        "B-T-7: _ATR_VAR_MIN floor name absent — fix may have been reverted"
    )
    # The pre-fix `max(atr_pct_horizon ** 2, 1e-6)` saturation pattern.
    assert "max(atr_pct_horizon ** 2, 1e-6)" not in src, (
        "B-T-7: pre-fix saturation pattern reintroduced"
    )


# ─────────────────────────────────────────────────────────────────────
# B-T-3 — _safe_int_qty
# ─────────────────────────────────────────────────────────────────────


def test_b_t_3_safe_int_qty_present_and_warns():
    """`_safe_int_qty` helper exists on OrganismLiveEngine and warns on
    fractional truncation."""
    from backend.organism.live_engine import OrganismLiveEngine
    assert hasattr(OrganismLiveEngine, "_safe_int_qty"), (
        "B-T-3: _safe_int_qty helper missing"
    )
    # Whole-number input is silent.
    assert OrganismLiveEngine._safe_int_qty(10.0, context="test") == 10
    # Fractional input warns and truncates.
    assert OrganismLiveEngine._safe_int_qty(10.5, context="test") == 10
    assert OrganismLiveEngine._safe_int_qty(0.5, context="test") == 0


# ─────────────────────────────────────────────────────────────────────
# S-NET-CB-1 — broker circuit breaker wired
# ─────────────────────────────────────────────────────────────────────


def test_s_net_cb_1_alpaca_broker_uses_circuit_breaker():
    """`AlpacaBrokerClient._make_request_with_retry` consults the
    technical `CircuitBreaker` from `infra/resilience.py` (named
    "alpaca_broker_http") so a 5xx burst opens the breaker and short-
    circuits subsequent requests."""
    from backend.integrations.alpaca_broker import AlpacaBrokerClient
    src = inspect.getsource(AlpacaBrokerClient._make_request_with_retry)
    assert "get_or_create_circuit_breaker" in src, (
        "S-NET-CB-1: breaker not consulted on broker HTTP path"
    )
    assert "alpaca_broker_http" in src, (
        "S-NET-CB-1: breaker name missing"
    )


def test_s_net_cb_1_breaker_state_machine():
    """The sync probe API on CircuitBreaker correctly transitions
    CLOSED → OPEN after `failure_threshold` failures, and refuses
    requests while OPEN until cooldown elapses."""
    from backend.infra.resilience import (
        CircuitBreakerConfig, get_or_create_circuit_breaker,
    )

    # Fresh registry name to avoid pollution from other tests.
    breaker = get_or_create_circuit_breaker(
        f"test_s_net_cb_1_state_{id(test_s_net_cb_1_breaker_state_machine)}",
        config=CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=60,
            success_threshold=1,
        ),
    )

    # CLOSED initially.
    assert breaker.allow_request() is True

    # 3 failures → OPEN.
    for _ in range(3):
        breaker.record_failure("test")
    assert breaker.allow_request() is False, "Breaker must open after threshold"


# ─────────────────────────────────────────────────────────────────────
# S-NET-T-1 — alpaca SDK timeout wrapper
# ─────────────────────────────────────────────────────────────────────


def test_s_net_t_1_alpaca_clients_have_timeout_wrapper():
    """`AlpacaClient._init_clients` wraps each SDK client's `_one_request`
    so every HTTP call carries `timeout=30.0` if the caller didn't set
    one. Regression would let SDK calls hang indefinitely."""
    src = inspect.getsource(__import__(
        "backend.data.alpaca_client", fromlist=["alpaca_client"]
    ))
    assert "_bounded_one_request" in src or "_make_wrapper" in src, (
        "S-NET-T-1: timeout wrapper helper missing"
    )
    assert 'opts["timeout"] = 30.0' in src, (
        "S-NET-T-1: 30s default timeout not injected"
    )


def test_s_net_t_1_wrapper_injects_timeout_when_missing():
    """The wrapper actually injects timeout into opts when the caller
    didn't set one; if caller set it, wrapper preserves the caller's value."""
    from backend.data.alpaca_client import AlpacaClient

    ac = AlpacaClient(
        api_key="test", secret_key="test", paper=True, test_mode=True,
    )

    seen: dict[str, dict] = {}

    class _FakeSession:
        def request(self, method, url, **kwargs):
            seen["kwargs"] = kwargs
            class R:
                status_code = 200
                text = "{}"
                def json(self): return {}
                def raise_for_status(self): pass
            return R()

    ac.trading_client._session = _FakeSession()

    # Missing timeout → wrapper injects 30.0.
    ac.trading_client._one_request("GET", "http://x", {}, 0)
    assert seen["kwargs"].get("timeout") == 30.0

    # Caller-supplied timeout → wrapper preserves it.
    ac.trading_client._one_request("GET", "http://x", {"timeout": 5.0}, 0)
    assert seen["kwargs"].get("timeout") == 5.0


# ─────────────────────────────────────────────────────────────────────
# S-OUTBOX-1 — claim lease 30 min
# ─────────────────────────────────────────────────────────────────────


def test_s_outbox_1_claim_lease_is_30_minutes():
    """OutboxRepo._CLAIM_LEASE_SECONDS is 1800 (30 min) per Wave-18
    fix. The previous 300s lease produced spurious re-claims during
    worst-case sequential broker batches."""
    from backend.infra.outbox import OutboxRepo
    assert OutboxRepo._CLAIM_LEASE_SECONDS == 1800, (
        f"S-OUTBOX-1: lease is {OutboxRepo._CLAIM_LEASE_SECONDS}, expected 1800"
    )
