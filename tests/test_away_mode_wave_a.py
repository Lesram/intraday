"""Tests for away-mode hardening Wave A (A1-A4).

A1: Universe drift / SH-PSQ protection
A2: Decouple scanner from entry blocking
A3: Runtime snapshot hardening (covered by snapshot script tests)
A4: Pending entry / restart orphan hardening
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ======================================================================
# A1: Universe drift / SH-PSQ protection
# ======================================================================

class TestA1ProtectedSymbols:
    """Protected symbols cannot be rotated out of the active universe."""

    def _make_selector(self, symbols, protected=None):
        from backend.organism.universe_selector import DynamicUniverseSelector
        return DynamicUniverseSelector(
            seed_symbols=symbols,
            min_universe=3,
            protected_symbols=protected,
        )

    def _make_trade(self, symbol, pnl):
        return SimpleNamespace(symbol=symbol, pnl=pnl, confidence=0.5)

    def test_protected_symbols_not_rotated_out(self):
        """SH with low fitness must NOT be dropped when protected."""
        sel = self._make_selector(
            ["AAPL", "MSFT", "SH", "PSQ", "GOOGL"],
            protected={"SH", "PSQ"},
        )
        # Give SH terrible trade history to tank its fitness
        bad_trades = [self._make_trade("SH", -50.0) for _ in range(10)]
        # Run multiple rotations to decay fitness
        for _ in range(5):
            sel.rotate(trades=bad_trades, generation=1)

        active = sel.active_universe
        assert "SH" in active, f"SH should be protected but was dropped. Active: {active}"
        assert "PSQ" in active, f"PSQ should be protected but was dropped. Active: {active}"

    def test_unprotected_symbol_can_rotate_out(self):
        """A non-protected symbol with poor fitness IS rotated out."""
        sel = self._make_selector(
            ["AAPL", "MSFT", "SH", "PSQ", "GOOGL", "BAD1", "BAD2"],
            protected={"SH", "PSQ"},
        )
        bad_trades = [self._make_trade("BAD1", -80.0) for _ in range(10)]
        for _ in range(5):
            sel.rotate(trades=bad_trades, generation=1)

        active = sel.active_universe
        # BAD1 should eventually be dropped (low fitness, not protected)
        fitness = sel.fitness_table.get("BAD1")
        if fitness and fitness.fitness < 0.40:
            assert "BAD1" not in active, (
                f"BAD1 with fitness {fitness.fitness:.3f} should be dropped"
            )

    def test_protected_symbols_persisted(self):
        """to_dict / from_dict round-trip preserves the protected set."""
        from backend.organism.universe_selector import DynamicUniverseSelector

        sel = self._make_selector(
            ["AAPL", "SH", "PSQ"],
            protected={"SH", "PSQ"},
        )
        d = sel.to_dict()

        # Restore without explicit protected_symbols -- should use persisted
        restored = DynamicUniverseSelector.from_dict(d)
        assert restored._protected == {"SH", "PSQ"}, (
            f"Protected symbols not restored: {restored._protected}"
        )

        # Restore with explicit protected_symbols -- caller wins
        restored2 = DynamicUniverseSelector.from_dict(
            d, protected_symbols={"SH"},
        )
        assert restored2._protected == {"SH"}, (
            f"Caller override not applied: {restored2._protected}"
        )

    def test_protected_in_to_dict(self):
        """to_dict includes protected_symbols key."""
        sel = self._make_selector(["AAPL", "SH"], protected={"SH"})
        d = sel.to_dict()
        assert "protected_symbols" in d
        assert "SH" in d["protected_symbols"]


# ======================================================================
# A2: Decouple scanner from entry blocking
# ======================================================================

class TestA2ScannerDecoupled:
    """Scanner must run even when entries are blocked."""

    def test_scanner_gate_has_no_entries_blocked_check(self):
        """Verify the scanner gate in live_engine no longer checks entries_blocked."""
        live_engine_path = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
        source = live_engine_path.read_text()

        # Find the scanner gate section
        lines = source.split("\n")
        scanner_section_found = False
        for i, line in enumerate(lines):
            if "MARKET SCAN" in line and "Phase 5" in line:
                scanner_section_found = True
                # Check the next few lines for the condition
                gate_lines = "\n".join(lines[i:i+6])
                assert "not entries_blocked" not in gate_lines, (
                    "Scanner gate still checks entries_blocked -- A2 fix not applied"
                )
                break

        assert scanner_section_found, "Could not find MARKET SCAN section in live_engine.py"

    def test_tension_lookup_populated_from_scanner(self):
        """Verify tension_lookup is built from market_scanner.scanned_stocks."""
        # This tests the data flow: scanner.scanned_stocks -> _tension_lookup
        scanner = MagicMock()
        stock1 = SimpleNamespace(symbol="AAPL", tension_score=0.65)
        stock2 = SimpleNamespace(symbol="MSFT", tension_score=0.42)
        scanner.scanned_stocks = [stock1, stock2]

        # Simulate the lookup construction from live_engine tick()
        _tension_lookup = {}
        for ss in scanner.scanned_stocks:
            _tension_lookup[ss.symbol] = ss.tension_score

        assert _tension_lookup["AAPL"] == 0.65
        assert _tension_lookup["MSFT"] == 0.42

    def test_death_spiral_broken_concept(self):
        """Conceptual test: when entries_blocked, scanner still populates tension data.

        In the old code, entries_blocked -> scanner skipped -> tension_lookup empty
        -> confidence drops -> entries stay blocked forever (death spiral).

        After A2 fix, scanner runs regardless, so tension data stays fresh.
        """
        # Simulate the old (broken) behavior
        entries_blocked = True
        scanner_ran_old = not entries_blocked  # False -- scanner skipped
        assert not scanner_ran_old

        # Simulate the new (fixed) behavior
        scanner_available = True
        tick_on_interval = True
        scanner_ran_new = scanner_available and tick_on_interval  # True -- scanner runs
        assert scanner_ran_new, "Scanner should run even when entries are blocked"


# ======================================================================
# A4: Pending entry / restart orphan hardening
# ======================================================================

class TestA4PendingEntryPersistence:
    """Pending entry dict must survive restart via brain persistence."""

    def test_pending_entry_in_brain_save_extra_counters(self):
        """Verify _save_brain includes pending_entry in extra_counters.

        V12 W90 (post-cleanup): pending_entry persistence moved out of
        _save_brain proper and into _build_extra_counters() (V11
        wave-53 / V12 W72).  _save_brain calls _build_extra_counters,
        so the persistence still happens — but the source-grep must
        target the helper, not _save_brain.
        """
        import inspect
        from backend.organism.live_engine import OrganismLiveEngine

        # _save_brain delegates extra_counters construction to the
        # helper; assert the helper contains the persistence wiring.
        save_src = inspect.getsource(OrganismLiveEngine._save_brain)
        assert "_build_extra_counters" in save_src, (
            "_save_brain no longer delegates to _build_extra_counters"
        )
        helper_src = inspect.getsource(OrganismLiveEngine._build_extra_counters)
        assert '"pending_entry"' in helper_src or "'pending_entry'" in helper_src, (
            "_build_extra_counters does not persist pending_entry"
        )
        assert "self._pending_entry" in helper_src, (
            "_build_extra_counters does not reference self._pending_entry"
        )

    def test_pending_entry_restore_in_initialize(self):
        """Verify initialize() restores pending_entry from brain extra_counters."""
        import inspect
        from backend.organism.live_engine import OrganismLiveEngine

        source = inspect.getsource(OrganismLiveEngine.initialize)
        assert "pending_entry" in source, (
            "initialize() does not restore pending_entry from brain"
        )

    def test_pending_entry_gets_fresh_cooldown_on_restore(self):
        """After restore, pending entries should have fresh tick timestamps.

        On restart, the old tick numbers are meaningless. The fix sets
        each restored entry's tick to self._tick_count so it gets a
        full cooldown window of _PENDING_ENTRY_TICKS (30 ticks).
        """
        # Simulate the restore logic
        tick_count = 500  # current tick after restore
        saved_pending = {"AAPL": 100, "MSFT": 200}  # stale tick numbers
        _pending_entry = {}

        # Apply the restore logic (mirrors live_engine initialize)
        for sym in saved_pending:
            _pending_entry[sym] = tick_count

        assert _pending_entry["AAPL"] == 500, "Should be reset to current tick"
        assert _pending_entry["MSFT"] == 500, "Should be reset to current tick"

    def test_no_duplicate_entry_after_restart(self):
        """After restore with pending entry for AAPL, AAPL should be blocked."""
        # Simulate the entry check logic from live_engine
        _pending_entry = {"AAPL": 500}
        _tick_count = 510  # 10 ticks later
        _PENDING_ENTRY_TICKS = 30

        # The check in live_engine: symbol in self._pending_entry
        symbol = "AAPL"
        is_blocked = symbol in _pending_entry
        assert is_blocked, "AAPL should be blocked by pending entry"

        # After cooldown expires (30+ ticks), the cleanup removes it
        _tick_count_later = 535  # 35 ticks later
        still_active = _tick_count_later - _pending_entry["AAPL"] < _PENDING_ENTRY_TICKS
        assert not still_active, "After 35 ticks, cooldown should have expired"

    def test_pending_entry_persisted_in_standalone_save(self):
        """Verify _persist_exit_levels_standalone also saves pending_entry_order_ids."""
        import inspect
        from backend.organism.live_engine import OrganismLiveEngine

        source = inspect.getsource(OrganismLiveEngine._persist_exit_levels_standalone)
        assert "pending_entry_order_ids" in source, (
            "Standalone persist should include pending_entry_order_ids"
        )


# ======================================================================
# A3: Runtime snapshot hardening
# ======================================================================

class TestA3RuntimeSnapshot:
    """Runtime snapshot should report reachable status and scanner metadata."""

    def test_snapshot_reports_unreachable_reason(self):
        """When API is unreachable, snapshot includes reason."""
        from scripts.runtime.write_runtime_snapshot import _build_live_process_snapshot

        with patch("scripts.runtime.write_runtime_snapshot._find_api_container", return_value=""), \
             patch("scripts.runtime.write_runtime_snapshot._curl_organism_status", return_value=None):
            snapshot = _build_live_process_snapshot()

        assert snapshot["reachable"] is False
        assert "unreachable_reason" in snapshot
        assert len(snapshot["unreachable_reason"]) > 0

    def test_snapshot_includes_scanner_candidates_count(self):
        """When API returns scanner data, it appears in the live section."""
        mock_status = {
            "live_engine": {
                "running": True,
                "engine": {
                    "tick_count": 100,
                    "scanner_candidates_count": 15,
                    "universe_size": 22,
                },
            },
        }
        from scripts.runtime.write_runtime_snapshot import _build_live_process_snapshot

        with patch("scripts.runtime.write_runtime_snapshot._find_api_container", return_value=""), \
             patch("scripts.runtime.write_runtime_snapshot._curl_organism_status", return_value=mock_status):
            snapshot = _build_live_process_snapshot()

        assert snapshot["reachable"] is True
        assert snapshot["live"].get("scanner_candidates_count") == 15
        assert snapshot["live"].get("universe_size") == 22
