"""V8 / Wave-39 (2026-05-03): tests for HH R-1 entries_blocked uplift.

Mechanical refactor — replaces 25 occurrences of local `entries_blocked`
in `_live_tick_inner` with the instance attribute `self._entries_blocked`.
Unblocks stages 0.5 / 1 / 1.1 / 1.2 extraction in wave-40.

Locks the regressions for:
- HH2 plan-feedback: stages 1 / 1.1 / 1.2 share local flow-var; uplift
  required before extraction.

Run with: ./venv/bin/python -m pytest tests/test_wave39_fixes.py -v
"""
from __future__ import annotations

import inspect
import re

import pytest


def test_wave39_no_local_entries_blocked():
    """Local var `entries_blocked = ...` (without `self.`) must not
    appear in `_live_tick_inner` after wave-39."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    # Strip comments so a documentation-only mention of the old name
    # doesn't fail the test.
    code = "\n".join(
        line.split("#", 1)[0] for line in src.splitlines()
    )
    # Find any "entries_blocked" not preceded by "self._" or "_last_"
    # or followed by "_reason" / "_total" or preceded by backtick (markdown).
    pattern = re.compile(
        r"(?<!self\._)(?<!_last_)(?<!`)\bentries_blocked\b(?!_reason|_total)"
    )
    hits = pattern.findall(code)
    assert len(hits) == 0, (
        f"Wave-39 regression: {len(hits)} bare `entries_blocked` "
        "references in _live_tick_inner — uplift to self._entries_blocked "
        "incomplete; stages 1 / 1.1 / 1.2 extraction blocked again."
    )


def test_wave39_self_entries_blocked_initialized_at_tick_entry():
    """`self._entries_blocked = False` must be set at the top of
    `_live_tick_inner` so each tick re-evaluates."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert "self._entries_blocked: bool = False" in src or \
           "self._entries_blocked = False" in src, (
        "Wave-39 regression: `self._entries_blocked` is no longer "
        "initialized in _live_tick_inner. Cross-tick state would persist "
        "across ticks and entries_blocked could lock True forever."
    )


def test_wave39_plan_doc_updated():
    """The HH R-1 plan must reflect the wave-39 prep."""
    with open("docs/architecture/HH_R1_PIPELINE_SPLIT_PLAN.md") as f:
        doc = f.read()
    assert "Wave-39 prep" in doc, (
        "Wave-39 regression: HH R-1 plan doc no longer mentions "
        "the entries_blocked uplift."
    )
    # Either the wave-39 "unblocked" marker (pre-wave-40) OR the
    # wave-40 "shipped" markers (post-wave-40) prove that wave-39's
    # uplift work is recorded.
    assert (
        "unblocked by wave-39" in doc
        or "shipped wave-40" in doc
    ), (
        "Wave-39 regression: HH R-1 plan doc has neither the wave-39 "
        "'unblocked' marker nor the wave-40 'shipped' marker. The "
        "entries_blocked uplift's downstream effect is undocumented."
    )
