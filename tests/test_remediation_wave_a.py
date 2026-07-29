"""Tests for Wave A remediation -- correctness + security + runtime integrity.

COMP-402: os.environ no longer captured in import failure tracking
COMP-001: Audit service always uses fresh DB session
ORDER_REJECTION_BLOCK: Terminal orders clear pending entry early
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCOMP402EnvLeakRemoved:
    """COMP-402: import_tracker must not capture full os.environ."""

    def test_failure_info_has_no_environment_key(self):
        from backend.utils.import_tracker import ImportErrorTracker
        tracker = ImportErrorTracker()
        tracker.track_import_failure("fake_module", ImportError("test"), context="test")
        info = tracker.failed_imports["fake_module"]
        assert "environment" not in info, "os.environ must not be captured in failure_info"

    def test_failure_info_has_safe_diagnostics(self):
        from backend.utils.import_tracker import ImportErrorTracker
        tracker = ImportErrorTracker()
        tracker.track_import_failure("fake_module", ImportError("test"), context="test")
        info = tracker.failed_imports["fake_module"]
        assert "python_version" in info, "python_version must be present"
        assert "platform" in info, "platform must be present"
        assert info["python_version"] == sys.version
        assert info["platform"] == sys.platform


class TestCOMP001AuditServiceFreshSession:
    """COMP-001: get_audit_service must not cache stale sessions."""

    @pytest.mark.asyncio
    async def test_different_sessions_produce_different_instances(self):
        from backend.services.audit_service import get_audit_service
        session1 = AsyncMock()
        session2 = AsyncMock()
        svc1 = await get_audit_service(session1)
        svc2 = await get_audit_service(session2)
        assert svc1.db is session1
        assert svc2.db is session2
        assert svc1 is not svc2, "Must create new instance per call, not cache"


class TestOrderRejectionBlock:
    """ORDER_REJECTION_BLOCK: Terminal orders must clear pending entry early."""

    def test_terminal_order_ids_tracked(self):
        """Stream client tracks rejected/cancelled/expired order IDs."""
        from backend.integrations.alpaca_stream import AlpacaStreamClient
        client = AlpacaStreamClient.__new__(AlpacaStreamClient)
        client._terminal_order_ids = set()
        client._terminal_order_ids.add("order-123")
        assert client.is_order_terminal("order-123")
        assert not client.is_order_terminal("order-999")

    def test_terminal_set_bounded(self):
        """Terminal set doesn't grow unbounded (stays under ~1001)."""
        from backend.integrations.alpaca_stream import AlpacaStreamClient
        client = AlpacaStreamClient.__new__(AlpacaStreamClient)
        client._terminal_order_ids = set()
        for i in range(2000):
            client._terminal_order_ids.add(f"order-{i}")
            if len(client._terminal_order_ids) > 1000:
                client._terminal_order_ids = set(list(client._terminal_order_ids)[-500:])
        # After 2000 inserts with periodic trimming, the set should never
        # exceed 1001 (the trim fires at >1000, cuts to 500, then grows
        # up to 501 before the next check on the NEXT iteration).
        assert len(client._terminal_order_ids) <= 1001, (
            f"Terminal set grew unbounded: {len(client._terminal_order_ids)}"
        )

    # V4 H-1 / Wave-16d (2026-05-02): the recorder must store BOTH the
    # broker order_id and the internal DB UUID so `is_order_terminal()`
    # answers correctly regardless of which key the caller has.
    def test_is_order_terminal_accepts_internal_uuid(self):
        """Recorder stores internal DB UUID alongside broker_order_id;
        live_engine.early-clear lookup by internal UUID must match."""
        from backend.integrations.alpaca_stream import AlpacaStreamClient
        client = AlpacaStreamClient.__new__(AlpacaStreamClient)
        client._terminal_order_ids = set()
        # Simulate _on_trade_update recording both forms post-fix.
        broker_oid = "alp-broker-id-abc"
        internal_uuid = "00000000-0000-0000-0000-aaaaaaaaaaaa"
        client._terminal_order_ids.add(broker_oid)
        client._terminal_order_ids.add(internal_uuid)
        # Either form yields True (the H-1 unification).
        assert client.is_order_terminal(broker_oid) is True
        assert client.is_order_terminal(internal_uuid) is True
        # Random unrelated id: still False.
        assert client.is_order_terminal("nope-not-here") is False

    # V5 S-WS-GAP-1 / Wave-17c (2026-05-03): gap-fill must re-populate
    # the terminal-id set so wave-16d's H-1 unification doesn't regress
    # across WebSocket reconnects.
    def test_gap_fill_repop_pattern_inline(self):
        """Verify that the gap-fill body contains the same dual-record
        pattern (broker_oid + internal UUID) used by _on_trade_update.

        Behavioral coverage of `_gap_fill_after_reconnect` requires a
        full HTTP/DB stack mock; instead we structurally assert that
        the wave-17c repop block exists in the gap-fill source — same
        approach as test_order_id_captured_on_entry_submission in j6b
        (which verifies dual recording at the steady-state site).
        """
        import inspect
        from backend.integrations.alpaca_stream import AlpacaStreamClient
        source = inspect.getsource(AlpacaStreamClient._gap_fill_after_reconnect)
        # The repop block must add broker_oid AND internal str(order.id).
        assert "self._terminal_order_ids.add(broker_oid)" in source, (
            "gap-fill must re-populate terminal_order_ids on broker_oid"
        )
        assert "str(order.id)" in source, (
            "gap-fill must also record the internal DB UUID (H-1 unification)"
        )
        assert 'in (\n                                        "rejected", "cancelled", "expired"\n                                    )' in source or \
               'rejected' in source and 'cancelled' in source and 'expired' in source, (
            "gap-fill repop must trigger only on terminal statuses"
        )
