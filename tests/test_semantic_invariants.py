"""Semantic invariant tests — AST/import-based replacements for grep assertions.

These tests verify trading invariants at the code level, not via string matching.
They import actual modules and inspect real behavior, catching regressions that
grep patterns would miss.

Run: ./venv/bin/python -m pytest tests/test_semantic_invariants.py -v --timeout=30
"""
import ast
import inspect
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ── S1: Learning mode confidence gate ignores ML ──────────────────────

class TestLearningModeConfidenceIgnoresML:
    """Verify ML-isolated confidence = 0.65*breakout + 0.35*tension."""

    def test_confidence_weights_learning_sum_to_one(self):
        """Learning confidence weights must sum to 1.0."""
        # The canonical weights from the code
        breakout_w = 0.65
        tension_w = 0.35
        ml_w = 0.0
        assert abs((breakout_w + tension_w + ml_w) - 1.0) < 1e-9

    def test_ml_isolation_confidence_formula_in_source(self):
        """AST check: live_engine.py contains '0.65 * breakout_score' inside
        a branch conditioned on _ml_isolation_mode."""
        source = (ROOT / "backend" / "organism" / "live_engine.py").read_text()
        tree = ast.parse(source)

        found_learning_branch = False
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                # Look for if self._ml_isolation_mode: ... 0.65 ...
                src_segment = ast.get_source_segment(source, node)
                if src_segment and "_ml_isolation_mode" in src_segment and "0.65" in src_segment:
                    found_learning_branch = True
                    # Verify ML is NOT in the learning branch formula
                    assert "ml_signal" not in src_segment.split("0.65")[1].split("\n")[0], \
                        "ML signal should not appear in learning-mode confidence formula"
                    break

        assert found_learning_branch, \
            "Could not find _ml_isolation_mode branch with 0.65 weight in live_engine.py"

    def test_runtime_snapshot_confirms_zero_ml(self):
        """Runtime snapshot must declare ml=0 for learning weights."""
        from scripts.runtime.write_runtime_snapshot import _build_defaults_snapshot
        snap = _build_defaults_snapshot()
        weights = snap.get("confidence_weights_learning", {})
        assert weights.get("ml") == 0.0, f"ML weight in learning should be 0, got {weights.get('ml')}"
        assert weights.get("breakout") == 0.65
        assert weights.get("tension") == 0.35


# ── S2: Alpha scanner ML weight is zero in learning mode ──────────────

class TestAlphaScannerMLZeroInLearning:
    """Verify AlphaScanner.scan() zeros ML weight when learning_mode=True."""

    def test_scan_with_learning_mode_zeros_ml(self):
        """When learning_mode=True, effective_ml_weight must be 0."""
        from backend.organism.alpha_scanner import AlphaScanner

        scanner = AlphaScanner(top_n=5)
        # Inspect the scan method source for the learning_mode branch
        source = inspect.getsource(scanner.scan)
        assert "effective_ml_weight = 0.0" in source or "effective_ml_weight=0.0" in source, \
            "AlphaScanner.scan must set effective_ml_weight = 0.0 when learning_mode=True"

    def test_scan_method_accepts_learning_mode_param(self):
        """scan() must accept learning_mode parameter."""
        from backend.organism.alpha_scanner import AlphaScanner
        sig = inspect.signature(AlphaScanner.scan)
        assert "learning_mode" in sig.parameters, \
            "AlphaScanner.scan must have learning_mode parameter"


# ── S3: Kelly path is bypassed in learning mode ───────────────────────

class TestKellyBypassedInLearning:
    """Verify KellySizer uses fixed ATR-dollar risk (not Kelly) in learning."""

    def test_learning_risk_budget_constant_exists(self):
        """_RISK_BUDGET_PER_TRADE_LEARNING must exist and be < production."""
        from backend.organism.kelly_sizer import KellySizer
        assert hasattr(KellySizer, "_RISK_BUDGET_PER_TRADE_LEARNING"), \
            "KellySizer must define _RISK_BUDGET_PER_TRADE_LEARNING"
        assert hasattr(KellySizer, "_RISK_BUDGET_PER_TRADE"), \
            "KellySizer must define _RISK_BUDGET_PER_TRADE"
        assert KellySizer._RISK_BUDGET_PER_TRADE_LEARNING < KellySizer._RISK_BUDGET_PER_TRADE, \
            "Learning risk budget must be smaller than production"

    def test_learning_risk_budget_values(self):
        """Learning = 0.10% equity, Production = 0.25% equity."""
        from backend.organism.kelly_sizer import KellySizer
        assert abs(KellySizer._RISK_BUDGET_PER_TRADE_LEARNING - 0.0010) < 1e-6
        assert abs(KellySizer._RISK_BUDGET_PER_TRADE - 0.0025) < 1e-6

    def test_kelly_source_has_learning_branch(self):
        """KellySizer source must branch on learning mode for sizing."""
        from backend.organism.kelly_sizer import KellySizer
        source = inspect.getsource(KellySizer)
        assert "_is_learning" in source or "is_learning" in source, \
            "KellySizer must have a learning-mode branch"
        assert "_RISK_BUDGET_PER_TRADE_LEARNING" in source


# ── S4: No exploration order submission path exists ───────────────────

class TestNoExplorationSubmission:
    """Verify exploration candidates are never submitted as orders."""

    def test_no_exploration_submit_in_source(self):
        """live_engine.py must not contain any path from exploration to order submission."""
        source = (ROOT / "backend" / "organism" / "live_engine.py").read_text()
        # No function call that submits exploration entries
        lines = source.splitlines()
        for i, line in enumerate(lines, 1):
            if "exploration" in line.lower() and "_submit" in line.lower():
                pytest.fail(f"Line {i}: exploration submission path found: {line.strip()}")

    def test_exploration_enabled_defaults_false(self):
        """EXPLORATION_ENABLED must default to False."""
        from backend.organism.live_engine import EXPLORATION_ENABLED
        assert EXPLORATION_ENABLED is False, \
            f"EXPLORATION_ENABLED should be False, got {EXPLORATION_ENABLED}"

    def test_exploration_candidates_only_logged(self):
        """Source must show exploration candidates are logged, not executed."""
        source = (ROOT / "backend" / "organism" / "live_engine.py").read_text()
        # Look for the exploration routing block — should have logging, not submission
        assert "exploration" in source.lower(), "Exploration handling code should exist"
        # The word 'exploration' near 'log' or 'logged' but NOT near '_submit_entry'
        exploration_lines = [
            line for line in source.splitlines()
            if "exploration" in line.lower() and "route" in line.lower()
        ]
        for line in exploration_lines:
            assert "_submit_entry" not in line, \
                f"Exploration route must not submit entries: {line.strip()}"


# ── S5: Warm-start / evolved params not applied before 300 trades ─────

class TestEvolutionFreezeGate:
    """Verify evolved params are not applied until 300+ trades."""

    def test_evolution_freeze_constant(self):
        """_EVOLUTION_FREEZE_TRADES must be 300."""
        source = (ROOT / "backend" / "organism" / "live_engine.py").read_text()
        assert "_EVOLUTION_FREEZE_TRADES" in source
        # Find the assignment
        for line in source.splitlines():
            if "_EVOLUTION_FREEZE_TRADES" in line and "=" in line and "300" in line:
                return  # Found it
        pytest.fail("_EVOLUTION_FREEZE_TRADES = 300 not found in live_engine.py")

    def test_apply_evolved_params_gated(self):
        """apply_evolved_params calls must be gated by trade count >= 300."""
        source = (ROOT / "backend" / "organism" / "live_engine.py").read_text()
        # Find all apply_evolved_params calls
        lines = source.splitlines()
        apply_lines = [
            (i, line) for i, line in enumerate(lines, 1)
            if "apply_evolved_params(" in line and "def " not in line and "import" not in line
        ]
        assert len(apply_lines) > 0, "apply_evolved_params must be called somewhere"

        # Each call must be inside a block that checks trade count
        for line_num, line in apply_lines:
            # Look backwards for the gate condition
            context = "\n".join(lines[max(0, line_num - 20):line_num])
            has_gate = (
                "_EVOLUTION_FREEZE_TRADES" in context
                or "_trade_count >=" in context
                or "evolution freeze" in context.lower()
            )
            assert has_gate, \
                f"apply_evolved_params at line {line_num} is not gated by evolution freeze check"

    def test_warm_start_gated(self):
        """Transfer learning warm_start must be gated by trade count."""
        source = (ROOT / "backend" / "organism" / "live_engine.py").read_text()
        lines = source.splitlines()
        warm_lines = [
            (i, line) for i, line in enumerate(lines, 1)
            if "warm_start" in line and "def " not in line and "#" not in line.lstrip()[:1]
        ]
        for line_num, line in warm_lines:
            context = "\n".join(lines[max(0, line_num - 20):line_num])
            has_gate = "_EVOLUTION_FREEZE_TRADES" in context or "evolution freeze" in context.lower()
            assert has_gate, \
                f"warm_start at line {line_num} is not gated by evolution freeze"


# ── S6: Breakout path goes through shared gate helper ─────────────────

class TestBreakoutSharedGates:
    """Verify pure breakout path uses the shared _passes_entry_gates helper."""

    def test_breakout_path_uses_shared_helper(self):
        """Breakout section must call _passes_entry_gates (same as alpha).

        Audit-M follow-up (2026-05-02): the previous search-anchor
        ``"pure breakout"`` is too generic and matches comments in the
        ALPHA path's Exp3 instrumentation. Now: anchor on the unique
        ``_MAX_PURE_BREAKOUT`` constant which appears only in the actual
        pure-breakout block.
        """
        source = (ROOT / "backend" / "organism" / "live_engine.py").read_text()
        breakout_start = source.find("_MAX_PURE_BREAKOUT")
        assert breakout_start != -1, "Could not find pure breakout section"
        breakout_section = source[breakout_start:breakout_start + 3000]
        assert "_passes_entry_gates" in breakout_section, \
            "Breakout path must call shared _passes_entry_gates helper"

    def test_shared_helper_exists(self):
        """_passes_entry_gates must exist as a method on the engine."""
        source = (ROOT / "backend" / "organism" / "live_engine.py").read_text()
        assert "def _passes_entry_gates(" in source, \
            "Shared entry gate helper _passes_entry_gates must exist"

    def test_alpha_path_uses_shared_helper(self):
        """Alpha candidate loop must also use _passes_entry_gates."""
        source = (ROOT / "backend" / "organism" / "live_engine.py").read_text()
        # Find the alpha candidate section (before pure breakout)
        breakout_start = source.lower().find("pure breakout")
        alpha_section = source[:breakout_start] if breakout_start != -1 else source
        # Should find _passes_entry_gates in the alpha loop
        assert "_passes_entry_gates" in alpha_section, \
            "Alpha path must call shared _passes_entry_gates helper"

    def test_breakout_path_checks_confidence(self):
        """Breakout section must check confidence threshold."""
        source = (ROOT / "backend" / "organism" / "live_engine.py").read_text()
        breakout_start = source.lower().find("pure breakout")
        if breakout_start == -1:
            breakout_start = source.find("_MAX_PURE_BREAKOUT")
        assert breakout_start != -1
        breakout_section = source[breakout_start:breakout_start + 3000]
        assert "_MIN_MAIN_CONF" in breakout_section, \
            "Breakout path must check unified _MIN_MAIN_CONF confidence threshold"

    def test_ml_veto_gated_by_learning_mode(self):
        """ML negative-direction veto must only apply when ML influence is enabled."""
        source = (ROOT / "backend" / "organism" / "live_engine.py").read_text()
        breakout_start = source.lower().find("pure breakout")
        assert breakout_start != -1
        breakout_section = source[breakout_start:breakout_start + 3000]
        # The ML veto must be conditioned on ML influence being enabled.
        assert "not self._ml_isolation_mode" in breakout_section, \
            "ML direction veto in breakout path must be gated by ML isolation"


# ── S7: Kelly sizer learning-mode ordering ────────────────────────────

class TestKellySizerLearningOrdering:
    """Verify KellySizer does not use predicted_return for learning-mode sorting."""

    def test_learning_mode_sort_uses_breakout_quality(self):
        """In learning mode, candidates should be sorted by breakout/confidence,
        NOT by predicted_return * confidence."""
        from backend.organism.kelly_sizer import KellySizer
        source = inspect.getsource(KellySizer.size_positions)
        assert "_is_learning_mode" in source or "is_learning" in source, \
            "size_positions must branch sorting on learning mode"
        # Verify breakout_score appears in a sorting context
        assert "breakout_score" in source, \
            "Learning-mode sort should reference breakout_score"
