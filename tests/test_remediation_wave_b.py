"""Tests for Wave B remediation -- paper-path reliability.

EXEC-001: Trade update retry on failure
EXEC-002: Gap-fill after WebSocket reconnect
PENDING_ENTRY_ORPHAN: Pending entry order ID persistence
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest


class TestEXEC001RetryOnFailure:
    """EXEC-001: _process_update_queue must retry failed updates."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self):
        """If first attempt fails but second succeeds, update is processed."""
        from backend.integrations.alpaca_stream import AlpacaStreamClient

        client = AlpacaStreamClient.__new__(AlpacaStreamClient)
        client.update_queue = asyncio.Queue()
        client._terminal_order_ids = set()

        call_count = 0
        async def mock_process(update):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Transient DB error")
            # Second call succeeds

        client._process_trade_update = mock_process
        await client.update_queue.put({"test": "data"})

        # Run processor for a short time
        async def run_briefly():
            task = asyncio.create_task(client._process_update_queue())
            await asyncio.sleep(1.5)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_briefly()
        assert call_count == 2, f"Expected 2 calls (1 fail + 1 success), got {call_count}"

    @pytest.mark.asyncio
    async def test_retry_exhaustion_logs_permanently_failed(self):
        """After 3 failed attempts, update is logged as permanently failed."""
        from backend.integrations.alpaca_stream import AlpacaStreamClient

        client = AlpacaStreamClient.__new__(AlpacaStreamClient)
        client.update_queue = asyncio.Queue()
        client._terminal_order_ids = set()

        call_count = 0
        async def mock_process(update):
            nonlocal call_count
            call_count += 1
            raise Exception("Persistent DB error")

        client._process_trade_update = mock_process
        await client.update_queue.put({"test": "data"})

        async def run_briefly():
            task = asyncio.create_task(client._process_update_queue())
            await asyncio.sleep(3.0)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_briefly()
        assert call_count == 3, f"Expected 3 retry attempts, got {call_count}"


class TestEXEC002GapFill:
    """EXEC-002: Gap-fill method must exist and be called after reconnect."""

    def test_gap_fill_method_exists(self):
        """AlpacaStreamClient must have _gap_fill_after_reconnect method."""
        from backend.integrations.alpaca_stream import AlpacaStreamClient
        assert hasattr(AlpacaStreamClient, '_gap_fill_after_reconnect')
        assert callable(getattr(AlpacaStreamClient, '_gap_fill_after_reconnect'))


class TestPendingEntryOrphanPersistence:
    """PENDING_ENTRY_ORPHAN: Pending entry order IDs must be persisted."""

    def test_pending_ids_persisted_in_extra_counters(self):
        """_persist_exit_levels_standalone saves pending_entry_order_ids."""
        from backend.organism.live_engine import OrganismLiveEngine

        engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
        engine._pending_entry_order_ids = {"AAPL": "order-123", "MSFT": "order-456"}

        # Mock brain.brain_dir
        with tempfile.TemporaryDirectory() as tmpdir:
            brain_mock = MagicMock()
            brain_mock.brain_dir = Path(tmpdir)
            engine.brain = brain_mock

            engine._persist_exit_levels_standalone(
                exit_levels={"AAPL": {"entry": 150.0}},
                entry_metadata={"AAPL": {"direction": 1}},
            )

            # Read back
            ec_path = Path(tmpdir) / "extra_counters.json"
            assert ec_path.exists()
            data = json.loads(ec_path.read_text())
            assert "pending_entry_order_ids" in data
            assert data["pending_entry_order_ids"] == {"AAPL": "order-123", "MSFT": "order-456"}
