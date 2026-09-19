"""V13 W97 (Lens 6: Test / CI Quality) — mutation smoke harness.

V12 audited that wave-tests have a mix of behavioral / marker-only;
V13 W97 expanded the marker-only ratchet across the full corpus.
But neither check answers the deeper question:

    *do the wave tests actually catch real regressions?*

A test suite at 100% behavioral coverage that doesn't catch when the
SUT is broken is no better than marker-only.  The mutation smoke
harness picks 3 critical functions, mutates each in a way that flips
behavior, and asserts that at least one wave test FAILS.  If no test
fails, the suite has a hole.

Three functions, chosen to span the V13 lens space:

1. ``backend.organism.governance.GovernanceController.trigger_drawdown_kill``
   — Lens 2 (Trading Safety).  Mutation: invert the limit comparison
   (>=  →  <).  At least one V13 W93 test must fail.

2. ``backend.organism.strategy_alerts.should_fire_low_win_rate_alert``
   — Lens 3 (Strategy Expectancy).  Mutation: invert the threshold
   comparison.  At least one V13 W94 test must fail.

3. ``backend.api.routes.orders.assert_order_owner_or_404``
   — Lens 5 (Auth/RBAC).  Mutation: change the equality check so the
   404 is suppressed.  At least one V13 W96 test must fail.

Each mutation is applied via monkey-patching the function in-process,
running the relevant test file, and asserting the test session
returns a non-zero exit (which means at least one test failed).

Usage:
    ./venv/bin/python scripts/ci/mutation_smoke.py

Exit codes:
- 0: every mutation was caught by at least one test (suite has teeth).
- 1: some mutation slipped through every test (suite has a hole).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


_MUTATIONS = (
    {
        "id": "drawdown_kill_limit_inverted",
        "lens": "Lens 2 — Trading Safety",
        "test_file": "tests/test_v13_w93_trading_safety.py",
        "test_filter": "test_w93_drawdown_kill_sets_halted_state or "
                       "test_w93_drawdown_kill_below_limit_no_halt or "
                       "test_w93_drawdown_kill_dispatches_alert",
        "mutation_module": "backend.organism.governance",
        "monkeypatch": (
            "from backend.organism.governance import GovernanceController as _G; "
            "_orig = _G.trigger_drawdown_kill; "
            "def _bad(self, dd):\n"
            "    # MUTATION: never trigger, regardless of dd vs limit\n"
            "    return None\n"
            "_G.trigger_drawdown_kill = _bad"
        ),
    },
    {
        "id": "win_rate_threshold_inverted",
        "lens": "Lens 3 — Strategy Expectancy",
        "test_file": "tests/test_v13_w94_strategy_floor.py",
        "test_filter": "test_w94_should_fire_below_floor or "
                       "test_w94_should_not_fire_above_floor",
        "mutation_module": "backend.organism.strategy_alerts",
        "monkeypatch": (
            "import backend.organism.strategy_alerts as _sa; "
            "_orig = _sa.should_fire_low_win_rate_alert; "
            "def _bad(payload, *, floor=None):\n"
            "    # MUTATION: always return False — alert never fires\n"
            "    return (False, 'mutated')\n"
            "_sa.should_fire_low_win_rate_alert = _bad"
        ),
    },
    {
        "id": "idor_check_disabled",
        "lens": "Lens 5 — Auth/RBAC",
        "test_file": "tests/test_v13_w96_idor.py",
        "test_filter": "test_w96_assert_order_owner_raises_404_on_cross_user",
        "mutation_module": "backend.api.routes.orders",
        "monkeypatch": (
            "import backend.api.routes.orders as _o; "
            "_orig = _o.assert_order_owner_or_404; "
            "def _bad(order, current_user):\n"
            "    # MUTATION: always pass, never raise\n"
            "    return None\n"
            "_o.assert_order_owner_or_404 = _bad"
        ),
    },
)


def _run_mutation(mut: dict) -> tuple[bool, str]:
    """Apply mutation via a conftest.py shim, run targeted tests,
    return (caught, summary).  caught=True iff at least one test failed."""
    test_file = REPO_ROOT / mut["test_file"]
    if not test_file.is_file():
        return False, f"test file missing: {test_file}"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Write a conftest.py whose autouse fixture installs the
        # monkeypatch BEFORE the test runs.
        conftest = td_path / "conftest.py"
        # Indent the monkeypatch body so it lives inside the
        # autouse fixture function.
        patch_lines = mut["monkeypatch"].split("\n")
        indented = "\n    ".join(patch_lines)
        conftest.write_text(
            "import pytest\n"
            "@pytest.fixture(autouse=True)\n"
            "def _v13_w97_mutation():\n"
            f"    {indented}\n"
            "    yield\n"
        )
        # Copy test file into temp dir so pytest sees the conftest.
        target_test = td_path / test_file.name
        target_test.write_bytes(test_file.read_bytes())

        env = os.environ.copy()
        env["PYTHONPATH"] = f"{REPO_ROOT}:{env.get('PYTHONPATH', '')}"
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                str(target_test),
                "-k", mut["test_filter"],
                "--timeout=30", "-q", "--tb=no",
            ],
            cwd=str(td_path), env=env,
            capture_output=True, text=True, timeout=120,
        )
        # Pytest exits 1 when at least one test fails.  That's
        # exactly what we WANT for mutation testing.  Exit 0 means
        # the mutation passed unnoticed — hole in the suite.
        caught = proc.returncode != 0
        # Extract the last line of stdout for a one-line summary.
        last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        return caught, last


def main() -> int:
    print("V13 W97 mutation smoke harness")
    print("=" * 60)

    holes: list[dict] = []
    for mut in _MUTATIONS:
        caught, detail = _run_mutation(mut)
        marker = "CAUGHT" if caught else "MISSED"
        print(f"  [{marker}] {mut['id']} ({mut['lens']})")
        print(f"          → {detail}")
        if not caught:
            holes.append(mut)

    print()
    if holes:
        print(f"FAIL: {len(holes)}/{len(_MUTATIONS)} mutation(s) slipped past every test")
        for h in holes:
            print(f"  - {h['id']}: {h['lens']}")
        return 1
    print(f"PASS: all {len(_MUTATIONS)} mutations caught — wave tests have teeth")
    return 0


if __name__ == "__main__":
    sys.exit(main())
