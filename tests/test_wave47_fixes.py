"""V9 / Wave-47 (2026-05-03): tests for medium/low cleanup batch.

Locks regressions for:
- TT-4 (MEDIUM): 4 async AlpacaClient methods now use _async_rate_limit
  instead of sync _rate_limit (which blocked the event loop).
- TT-5 (LOW): trade_history, evaluation_events, model_metrics,
  generation_accuracies are bounded at 10k entries (FIFO).
- AA3-4 (INFO): JWT_CLOCK_SKEW now passed as `leeway=` to jwt.decode.

Wave-47 deferred (require schema migrations):
- BB3-F1: orders.user_id → users.id FK
- BB3-F3: ON DELETE CASCADE → RESTRICT on fill-history tables
- BB3-F4: unique index (broker_order_id, symbol)
- TT-3: partial expression index on orders attributes->>'source'

Run with: ./venv/bin/python -m pytest tests/test_wave47_fixes.py -v
"""
from __future__ import annotations

import inspect


def test_tt_4_async_alpaca_methods_use_async_rate_limit():
    """The 4 async AlpacaClient methods (submit_order, cancel_order,
    get_account_status, get_recent_orders) must call _async_rate_limit,
    not the sync _rate_limit."""
    from backend.data.alpaca_client import AlpacaClient
    for method_name in (
        "submit_order", "cancel_order",
        "get_account_status", "get_recent_orders",
    ):
        src = inspect.getsource(getattr(AlpacaClient, method_name))
        assert "await self._async_rate_limit()" in src, (
            f"TT-4 regression: {method_name} no longer uses async rate-limit. "
            "Sync time.sleep() blocks the event loop."
        )
        assert "self._rate_limit()" not in src, (
            f"TT-4 regression: {method_name} still calls sync _rate_limit. "
            "Mixing sync sleep in async path."
        )


def test_tt_5_trade_history_bounded():
    """ContinuousLearner.record_trade caps trade_history at _TT5_MAX_HISTORY."""
    from backend.organism.continuous_learner import ContinuousLearner
    src = inspect.getsource(ContinuousLearner)
    assert "_TT5_MAX_HISTORY" in src, (
        "TT-5 regression: _TT5_MAX_HISTORY constant removed."
    )
    assert ContinuousLearner._TT5_MAX_HISTORY == 10_000


def test_tt_5_record_trade_truncates_oversize_history():
    """Concrete: appending past _TT5_MAX_HISTORY trims to last N."""
    from backend.organism.continuous_learner import ContinuousLearner
    learner = ContinuousLearner.__new__(ContinuousLearner)
    learner.trade_history = [object() for _ in range(10_005)]

    class _State:
        total_trades = 0
        cumulative_pnl = 0.0
    learner.state = _State()

    class _Trade:
        pnl = 0.0
    # Manually invoke the method.
    ContinuousLearner.record_trade(learner, _Trade())
    assert len(learner.trade_history) == 10_000, (
        f"TT-5 regression: trade_history not capped — len="
        f"{len(learner.trade_history)}"
    )


def test_aa3_4_jwt_decode_passes_leeway():
    """decode_token must pass JWT_CLOCK_SKEW as leeway= to jwt.decode."""
    from backend.infra import security
    src = inspect.getsource(security.decode_token)
    assert "leeway=JWT_CLOCK_SKEW" in src, (
        "AA3-4 regression: JWT_CLOCK_SKEW is dead code again — "
        "leeway not passed to jwt.decode."
    )
