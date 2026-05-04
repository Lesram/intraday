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


def test_orb_mark_fired_only_in_live_block():
    """mark_fired must be inside the ORB_LIVE_ENABLED-gated block, not in the
    shadow scan block."""
    src = _engine_source()

    # The shadow scan block (around `R3 ORB Stocks-in-Play scan`) should NOT
    # contain mark_fired. mark_fired belongs to the live entry block.
    shadow_start = src.find("R3 ORB Stocks-in-Play scan")
    assert shadow_start >= 0
    # Shadow block runs until the candidate-loop block starts ('# 4. GET CURRENT POSITIONS' marker)
    shadow_end = src.find("# 4. GET CURRENT POSITIONS", shadow_start)
    shadow_block = src[shadow_start:shadow_end]
    assert "_orb_scanner.mark_fired" not in shadow_block, (
        "mark_fired should NOT be in the shadow scan block — that belongs to "
        "the live entry block which is gated by ORB_LIVE_ENABLED"
    )

    # The live entry block (M2-B) should call mark_fired
    live_start = src.find("M2-B: ORB Stocks-in-Play LIVE entry path")
    assert live_start >= 0, "ORB LIVE entry block marker not found"
    # Live block ends at the cand_dicts.sort call
    live_end = src.find("cand_dicts.sort(", live_start)
    live_block = src[live_start:live_end]
    assert "self._orb_scanner.mark_fired" in live_block, (
        "Live ORB block should call mark_fired to prevent re-firing on later ticks"
    )


def test_orb_does_not_route_into_candidate_dicts_in_shadow():
    """Shadow scan block: NO cand_dicts.append. Live block: yes (and gated)."""
    src = _engine_source()
    shadow_start = src.find("R3 ORB Stocks-in-Play scan")
    assert shadow_start >= 0
    shadow_end = src.find("# 4. GET CURRENT POSITIONS", shadow_start)
    shadow_block = src[shadow_start:shadow_end]
    assert "cand_dicts.append" not in shadow_block, (
        "ORB shadow block must not append to cand_dicts (live entry pipeline). "
        "That's the live block's job."
    )
    forbidden = [
        "_submit_entry_order", "_submit_order(", "submit_symbol_order",
        "kelly_sizer.size_positions", "_pending_entry[",
    ]
    for f in forbidden:
        assert f not in shadow_block, (
            f"Forbidden call '{f}' found inside ORB shadow block"
        )


def test_orb_live_block_gated_by_feature_flag():
    """ORB live entry block must be gated by ORB_LIVE_ENABLED."""
    src = _engine_source()
    live_start = src.find("M2-B: ORB Stocks-in-Play LIVE entry path")
    assert live_start >= 0
    live_end = src.find("cand_dicts.sort(", live_start)
    live_block = src[live_start:live_end]
    assert "ORB_LIVE_ENABLED" in live_block, (
        "Live ORB block must check the ORB_LIVE_ENABLED feature flag"
    )
    # And the env var must default False
    assert 'ORGANISM_ORB_LIVE_ENABLED", False' in src or \
           'ORB_LIVE_ENABLED = _env_bool("ORGANISM_ORB_LIVE_ENABLED", False)' in src, (
        "ORGANISM_ORB_LIVE_ENABLED must default to False"
    )


def test_orb_shadow_failsafe_exception_handling():
    """ORB shadow logic must be wrapped in try/except so it can never
    affect the live tick decision path."""
    src = _engine_source()
    shadow_start = src.find("R3 ORB Stocks-in-Play scan")
    assert shadow_start >= 0
    after_block = src[shadow_start:shadow_start + 5000]
    assert "except Exception" in after_block, (
        "ORB shadow block must catch exceptions to prevent affecting live ticks"
    )


def test_orb_live_uses_composite_gate():
    """ORB live block must compute composite confidence and gate on it
    (consistency with RC-1.5 fix)."""
    src = _engine_source()
    live_start = src.find("M2-B: ORB Stocks-in-Play LIVE entry path")
    live_end = src.find("cand_dicts.sort(", live_start)
    live_block = src[live_start:live_end]
    assert "_orb_composite" in live_block
    assert "_MIN_MAIN_CONF" in live_block, (
        "ORB live entries must gate on composite >= _MIN_MAIN_CONF (RC-1.5 fix)"
    )
