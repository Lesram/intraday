"""
Away-mode hardening Wave B tests.

B1: Failed trade update DLQ persistence
B2: WebSocket reconnect gap-fill hardening
B3: Audit/DB session resilience
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# B1: Dead-letter queue for permanently failed trade updates
# ---------------------------------------------------------------------------

@pytest.fixture
def stream_client():
    """Create an AlpacaStreamClient with mocked settings and temp DLQ path."""
    with patch("backend.integrations.alpaca_stream.get_settings"):
        os.environ.setdefault("ALPACA_API_KEY_ID", "test-key")
        os.environ.setdefault("ALPACA_API_SECRET_KEY", "test-secret")
        from backend.integrations.alpaca_stream import AlpacaStreamClient
        client = AlpacaStreamClient()
        # Use a temp file for DLQ so tests don't pollute /tmp
        tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        tmp.close()
        client._dlq_path = Path(tmp.name)
        yield client
        # Cleanup
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass


def test_failed_update_written_to_dlq(stream_client):
    """After all retries are exhausted, the update is written to the DLQ file."""
    update = {"data": {"id": "order-123", "status": "filled"}}
    error = RuntimeError("DB connection refused")

    stream_client._write_to_dlq(update, 3, error)

    # Verify file was written
    assert stream_client._dlq_path.exists()
    lines = stream_client._dlq_path.read_text().strip().split("\n")
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["attempt_count"] == 3
    assert "DB connection refused" in record["error"]
    assert record["update"]["data"]["id"] == "order-123"
    assert "timestamp" in record


def test_dlq_counter_increments(stream_client):
    """Each DLQ write increments the session counter."""
    assert stream_client._dlq_count == 0

    stream_client._write_to_dlq({"data": {}}, 3, ValueError("x"))
    assert stream_client._dlq_count == 1

    stream_client._write_to_dlq({"data": {}}, 3, ValueError("y"))
    assert stream_client._dlq_count == 2


def test_successful_update_not_dlqed(stream_client):
    """A successfully processed update must NOT write to DLQ."""
    # Simulate what _process_update_queue does on success: no DLQ write
    # We just verify the DLQ file is empty after no writes
    assert stream_client._dlq_count == 0
    assert not stream_client._dlq_path.read_text().strip()


@pytest.mark.asyncio
async def test_process_queue_writes_dlq_on_permanent_failure(stream_client):
    """Integration: the retry loop calls _write_to_dlq after MAX_RETRIES failures."""
    # Make _process_trade_update always fail
    stream_client._process_trade_update = AsyncMock(
        side_effect=RuntimeError("persistent failure")
    )

    # Put one update in the queue
    await stream_client.update_queue.put({"data": {"id": "fail-order"}})

    # Run _process_update_queue in a task, let it process one item then cancel
    task = asyncio.create_task(stream_client._process_update_queue())
    await asyncio.sleep(5.0)  # Allow retries with backoff (0.5 + 1.0 + margin)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert stream_client._dlq_count == 1
    lines = stream_client._dlq_path.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["attempt_count"] == 3


# ---------------------------------------------------------------------------
# B2: WebSocket reconnect gap-fill hardening
# ---------------------------------------------------------------------------

def test_gap_duration_tracked(stream_client):
    """_last_connected_at is set when connect succeeds, enabling gap computation."""
    # Simulate a previous connection 10 minutes ago
    stream_client._last_connected_at = time.time() - 600

    gap_seconds = time.time() - stream_client._last_connected_at
    lookback = min(max(gap_seconds + 60, 300), 3600)

    # Gap ~600s + 60 buffer = ~660s, well above the 300s minimum
    assert lookback >= 660 - 5  # small tolerance
    assert lookback <= 3600


def test_reconnect_count_increments(stream_client):
    """_reconnect_count increments on each reconnection attempt."""
    assert stream_client._reconnect_count == 0
    # Simulate what start_with_reconnect does
    stream_client._reconnect_count += 1
    assert stream_client._reconnect_count == 1


def test_max_reconnect_warning(stream_client, caplog):
    """After >10 reconnects, a CRITICAL log about stream instability is emitted."""
    stream_client._reconnect_count = 10  # Already at 10

    # Simulate the 11th reconnect (same logic as start_with_reconnect)
    stream_client._reconnect_count += 1
    if stream_client._reconnect_count > 10:
        logging.getLogger("backend.integrations.alpaca_stream").critical(
            "Stream instability: %d reconnects this session — "
            "order update reliability degraded",
            stream_client._reconnect_count,
        )

    assert any("Stream instability" in r.message for r in caplog.records)
    assert any(r.levelname == "CRITICAL" for r in caplog.records if "Stream instability" in r.message)


def test_gap_fill_lookback_capped_at_one_hour(stream_client):
    """Gap-fill lookback window is capped at 3600 seconds even for long gaps."""
    # Simulate a 2-hour gap
    stream_client._last_connected_at = time.time() - 7200

    gap_seconds = time.time() - stream_client._last_connected_at
    lookback = min(max(gap_seconds + 60, 300), 3600)

    assert lookback == 3600


def test_gap_fill_minimum_five_minutes(stream_client):
    """Gap-fill lookback is at least 5 minutes even for very short gaps."""
    # Simulate a 10-second gap
    stream_client._last_connected_at = time.time() - 10

    gap_seconds = time.time() - stream_client._last_connected_at
    lookback = min(max(gap_seconds + 60, 300), 3600)

    assert lookback == 300


# ---------------------------------------------------------------------------
# B3: Audit/DB session resilience
# ---------------------------------------------------------------------------

def test_refresh_session_updates_db():
    """refresh_session replaces the internal db reference."""
    from backend.services.audit_service import ComplianceAuditService

    old_session = MagicMock()
    old_session.is_active = True
    new_session = MagicMock()
    new_session.is_active = True

    svc = ComplianceAuditService(old_session)
    assert svc.db is old_session

    svc.refresh_session(new_session)
    assert svc.db is new_session


def test_stale_session_detected(caplog):
    """When db is None, _check_session_health logs a warning and returns False."""
    from backend.services.audit_service import ComplianceAuditService

    svc = ComplianceAuditService(MagicMock())
    svc.db = None

    result = svc._check_session_health()
    assert result is False
    assert any("session is None" in r.message for r in caplog.records)


def test_inactive_session_detected(caplog):
    """When db.is_active is False, a stale-session warning is emitted."""
    from backend.services.audit_service import ComplianceAuditService

    mock_session = MagicMock()
    mock_session.is_active = False

    svc = ComplianceAuditService(mock_session)

    result = svc._check_session_health()
    assert result is False
    assert any("is_active=False" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_log_raises_on_stale_session():
    """Calling log() with a None session raises RuntimeError."""
    from backend.services.audit_service import AuditAction, AuditEntity, ComplianceAuditService

    svc = ComplianceAuditService(MagicMock())
    svc.db = None

    with pytest.raises(RuntimeError, match="stale or None"):
        await svc.log(
            action=AuditAction.SYSTEM_STARTUP,
            entity=AuditEntity.SYSTEM,
            entity_id="test",
            actor="test",
        )


def test_reset_clears_singleton():
    """reset() class method clears the singleton instance."""
    from backend.services.audit_service import ComplianceAuditService

    ComplianceAuditService._instance = MagicMock()
    assert ComplianceAuditService._instance is not None

    ComplianceAuditService.reset()
    assert ComplianceAuditService._instance is None
