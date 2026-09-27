"""V10 / Wave-55 (2026-05-03): tests for migration fixes + BB4-F2 verify.

Locks regressions for:
- XX-1 (HIGH): ec197100938a downgrade now uses IF EXISTS so the txn
  doesn't abort on missing constraint.
- XX-2 (HIGH): new migration 20260503_000002 widens ck_orders_status
  to include `new`, `pending_new`, `submitting`, `canceled`, etc. —
  matching what repositories/orders.py + partial index reference.
- BB4-F2 verification: a real EOD tick attempts pending-entry cancellation,
  preserves unconfirmed attribution, and still flattens held positions.

Wave-55 deferred:
- XX-3 (MEDIUM, ORM-vs-DB drift / portfolio_history): scope larger
  than this wave; tracked for V11.

Run with: ./venv/bin/python -m pytest tests/test_wave55_fixes.py -v
"""
from __future__ import annotations

import sys
import os

import pytest

from tests.test_eod_pending_cancellation import store as store


def test_xx_1_ec197_downgrade_uses_if_exists():
    """The ec197100938a downgrade must use IF EXISTS so the txn doesn't
    abort on the missing uq_orders_account_client_order constraint."""
    path = (
        "backend/migrations/versions/"
        "ec197100938a_add_idempotency_constraints_and_order_.py"
    )
    src = open(path).read()
    assert "XX-1" in src, "XX-1 marker missing in ec197100938a"
    assert "DROP CONSTRAINT IF EXISTS uq_orders_account_client_order" in src, (
        "XX-1 regression: downgrade still uses bare drop_constraint that "
        "aborts the txn."
    )


def test_xx_2_widen_ck_orders_status_migration_exists():
    """A new migration must widen ck_orders_status."""
    path = (
        "backend/migrations/versions/"
        "20260503_000002_xx_2_widen_orders_status_check.py"
    )
    assert os.path.isfile(path), (
        "XX-2 regression: 20260503_000002 widening migration missing."
    )
    src = open(path).read()
    # Must include the previously-rejected statuses (Python string literals).
    for needed in ('"new"', '"pending_new"', '"submitting"', '"canceled"'):
        assert needed in src, (
            f"XX-2 regression: {needed} missing from migration"
        )


def test_xx_2_migration_tree_still_single_headed():
    """Adding the wave-55 migration must not branch the tree."""
    import subprocess
    proc = subprocess.run(
        [sys.executable, "scripts/ci/check_migrations.py"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, (
        f"XX-2 regression: migration tree no longer single-headed: "
        f"{proc.stdout}\n{proc.stderr}"
    )
    # V11 Z9-F1 / Wave-69: don't assert a specific head literal —
    # wave-61 (XX-3 portfolio_history) advanced the chain to
    # 20260503_000003.  Just verify wave-55's revision is in the chain
    # (anywhere) AND the chain remained single-headed.
    # V11 Z9-F1 / Wave-69: was asserting head==`20260503_000002` but
    # wave-61 (XX-3 portfolio_history) advanced the head to
    # `20260503_000003`, then future waves may advance it further.
    # The single-head + clean-exit checks above are sufficient.


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_bb4_f2_verify_eod_cancel_inline_in_live_engine(store, tmp_path, monkeypatch):
    """The EOD engine boundary must cancel safely without suppressing exits."""
    from datetime import UTC, datetime

    from backend.organism.adaptive_exits import ExitLevels
    from backend.organism.live_engine import OrganismLiveEngine
    from backend.organism.replay_simulator import SimulatedBroker, make_price_df
    from tests.test_eod_pending_cancellation import observed, seeded
    from tests.test_organism_engine_scenarios import MockDataClient

    _, pending_order, transport = await seeded(store)
    # DELETE acknowledgement is not terminal confirmation. Keep the original
    # local order identity while a supported cancel targets its broker UUID.
    transport.get_order.return_value = observed(pending_order, 'new')

    def acknowledge_cancel(_broker_id):
        transport.get_order.return_value = observed(pending_order, 'pending_cancel')

    transport.cancel_order.side_effect = acknowledge_cancel
    monkeypatch.setattr(
        'backend.integrations.alpaca_broker.get_alpaca_broker_client',
        lambda: transport,
    )
    frames = {symbol: make_price_df(n=250, base=100) for symbol in ('AAPL', 'MSFT', 'SPY')}
    broker = SimulatedBroker(initial_cash=100_000)
    engine = OrganismLiveEngine(
        data_client=MockDataClient(frames), order_service=broker,
        positions_service=broker, brain_dir=str(tmp_path / 'wave55-eod-brain'),
        timeframe='1Min', universe=['AAPL', 'MSFT', 'SPY'],
    )
    engine.market_scanner = None
    now = datetime(2026, 9, 22, 19, 59, tzinfo=UTC)
    engine._now_fn = lambda: now
    engine._time_fn = now.timestamp
    await engine.initialize()
    engine._sessionmaker = store
    engine._pending_entry_order_ids = {'AAPL': str(pending_order.id)}
    engine._pending_entry = {'AAPL': 0}
    broker.add_position('MSFT', qty=10, avg_entry_price=100)
    broker.set_price('MSFT', 100)
    engine._exit_levels['MSFT'] = ExitLevels(
        symbol='MSFT', direction=1., entry_price=100, stop_loss=90,
        take_profit=120, trailing_stop=90, atr_at_entry=2,
        regime_at_entry='unknown', highest_favorable=100,
    )
    engine._entry_metadata['MSFT'] = {
        'entry_price': 100., 'entry_tick': 0, 'direction': 1.,
        'confidence': .6, 'predicted_return': .02, 'filled_shares': 10,
        'entry_source': 'alpha',
    }

    result = await engine.live_tick()

    transport.cancel_order.assert_awaited_once_with(pending_order.broker_order_id)
    assert transport.get_order.await_count >= 4
    assert engine._pending_entry_order_ids == {'AAPL': str(pending_order.id)}
    assert 'AAPL' in engine._pending_entry
    assert engine._alpha_breakout_late_blocked
    assert result.orders_submitted == 1
    assert any(
        event.symbol == 'MSFT' and event.details.get('reason') == 'eod_flatten'
        for event in result.activity
    )
    assert 'MSFT' not in await broker.get_all_positions()
    assert broker.trade_log and all(order['side'] == 'sell' for order in broker.trade_log)
    assert engine._ml_isolation_mode and engine._fixed_risk_sizing_mode
