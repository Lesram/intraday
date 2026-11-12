"""Outbox worker in non-execute modes (updated for audit 2026-10-05 A3-01).

shadow and dry_run send nothing to a broker and invent nothing: the order row is
finalized 'rejected' (ck_orders_status has no 'shadow') with no broker id and no
fill, and attributes.execution_mode records why. The behaviour against the real
status constraint is covered in tests/test_audit_20261005_ui_loop_and_execution_mode.py.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["shadow", "dry_run"])
async def test_outbox_non_execute_mode_skips_broker_and_finalizes_rejected(mode):
    from backend.infra.outbox_worker import OutboxWorker

    mode_state = SimpleNamespace(mode=mode, default_mode="execute", source="test", overridden=True)

    with patch("backend.services.trading_execution_mode.get_trading_execution_mode", return_value=mode_state):
        worker = OutboxWorker(sessionmaker=AsyncMock())
        worker.use_mock_broker = False
        worker._update_order_status = AsyncMock()
        worker._submit_real_broker_order = AsyncMock(
            side_effect=AssertionError("Broker submission should not run in a non-execute mode")
        )
        worker._simulate_broker_order = AsyncMock(
            side_effect=AssertionError("No simulated fill in a non-execute mode")
        )

        payload = {
            "order_id": "123e4567-e89b-12d3-a456-426614174000",
            "symbol": "AAPL",
            "side": "buy",
            "qty": "1",
            "order_type": "market",
            "tif": "gtc",
        }

        result = await worker._process_order_submitted(payload)

        assert result["success"] is True
        assert result["status"] == "rejected"
        assert result.get("execution_mode") == mode
        assert result.get("skipped") is True
        assert result.get("broker") == "none"

        worker._submit_real_broker_order.assert_not_called()
        worker._simulate_broker_order.assert_not_called()
        worker._update_order_status.assert_awaited_once()

        _, kwargs = worker._update_order_status.await_args
        assert kwargs["order_id"] == payload["order_id"]
        assert kwargs["status"] == "rejected"
        assert kwargs["broker_order_id"] is None
        assert kwargs["details"] == {
            "broker": "none", "execution_mode": mode, "not_submitted": "execution_mode",
        }
        assert "filled_qty" not in kwargs["details"]
        assert "avg_fill_price" not in kwargs["details"]
