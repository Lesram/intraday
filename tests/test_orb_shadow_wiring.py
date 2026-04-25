"""Verify ORB scanner is wired into live_engine as shadow telemetry.

The wiring should:
1. Instantiate _orb_scanner on engine __init__
2. Call _orb_scanner.scan() during the tick loop
3. NOT route ORB candidates into the entry pipeline (shadow only)
4. Log breakouts when triggered
"""

from __future__ import annotations

from pathlib import Path


def _engine_source() -> str:
    return (
        Path(__file__).parent.parent / "backend" / "organism" / "live_engine.py"
    ).read_text()


def test_orb_scanner_imported_in_live_engine():
    src = _engine_source()
    assert "from backend.organism.orb_scanner import ORBScanner" in src


def test_orb_scanner_instantiated():
    src = _engine_source()
    assert "self._orb_scanner = ORBScanner(" in src


def test_orb_shadow_counters_initialized():
    src = _engine_source()
    assert "self._orb_shadow_log_count" in src
    assert "self._orb_shadow_breakout_count" in src


def test_orb_scan_called_in_tick_loop():
    src = _engine_source()
    assert "self._orb_scanner.scan(" in src


def test_orb_breakout_log_present():
    src = _engine_source()
    assert "ORB shadow BREAKOUT:" in src


def test_orb_does_not_call_mark_fired():
    """In shadow mode, ORB candidates should NOT call mark_fired (no actual entries).
    mark_fired only gets called when we promote to live entry path (R4)."""
    src = _engine_source()
    assert "_orb_scanner.mark_fired" not in src, (
        "ORB scanner should NOT mark_fired in shadow mode — that's an R4 promotion task"
    )


def test_orb_does_not_route_into_candidate_dicts():
    """Shadow mode: ORB candidates should NOT be added to cand_dicts entry pipeline.

    Verification: scan the ORB shadow block (between marker comment and 'except')
    and confirm it doesn't contain 'cand_dicts.append'."""
    src = _engine_source()
    orb_start = src.find("R3 ORB Stocks-in-Play shadow scan")
    assert orb_start >= 0, "ORB shadow block marker comment not found"
    orb_end_excl = src.find("# 4. GET CURRENT POSITIONS", orb_start)
    assert orb_end_excl > orb_start, (
        "ORB shadow block end marker not found"
    )
    orb_block = src[orb_start:orb_end_excl]
    assert "cand_dicts.append" not in orb_block, (
        "ORB candidates appear to leak into cand_dicts entry path inside the "
        "shadow block — that's a wiring bug. Shadow must log only."
    )
    # Also: no calls to _submit_entry_order or similar inside the shadow block
    forbidden = [
        "_submit_entry_order", "_submit_order(", "submit_symbol_order",
        "kelly_sizer.size_positions", "_pending_entry[",
    ]
    for f in forbidden:
        assert f not in orb_block, (
            f"Forbidden call '{f}' found inside ORB shadow block — must be log-only"
        )


def test_orb_shadow_failsafe_exception_handling():
    """ORB shadow logic must be wrapped in try/except so it can never
    affect the live tick decision path."""
    src = _engine_source()
    # The ORB block should have its own try/except (or be in the regime-block try/except)
    # Look for the comment + nearby exception handling.
    orb_block_start = src.find("R3 ORB Stocks-in-Play shadow scan")
    assert orb_block_start >= 0
    # Find the exception handler within ~50 lines of the start
    after_block = src[orb_block_start:orb_block_start + 5000]
    assert "except Exception" in after_block, (
        "ORB shadow block must catch exceptions to prevent affecting live ticks"
    )
