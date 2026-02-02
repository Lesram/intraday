import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_outbox_shadow_mode_skips_broker_and_marks_shadow():
    from backend.infra.outbox_worker import OutboxWorker

    mode_state = SimpleNamespace(mode="shadow", source="test", overridden=True)

    with patch("backend.services.trading_execution_mode.get_trading_execution_mode", return_value=mode_state):
        worker = OutboxWorker(sessionmaker=AsyncMock())
        worker.use_mock_broker = False
        worker._update_order_status = AsyncMock()
        worker._submit_real_broker_order = AsyncMock(
            side_effect=AssertionError("Broker submission should not run in shadow mode")
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
        assert result["status"] == "shadow"
        assert result.get("execution_mode") == "shadow"
        assert result.get("skipped") is True

        worker._submit_real_broker_order.assert_not_called()
        worker._update_order_status.assert_awaited_once()

        _, kwargs = worker._update_order_status.await_args
        assert kwargs["order_id"] == payload["order_id"]
        assert kwargs["status"] == "shadow"
        assert kwargs["broker_order_id"] is None
        assert kwargs["details"]["execution_mode"] == "shadow"
