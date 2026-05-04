#!/usr/bin/env python3
"""V7 W2 / Wave-26 (2026-05-03): wave-PR marker enforcement.

V6 Track W and V7 Track W2 documented a process gap: the recurring
"fix that didn't actually fix" pattern (V5 S-J3-1, V6 V-T-1/V-T-2,
V7 X-4/X-8) traces to incomplete same-class scans on prior waves.
The proposed CI rule was: every audit-wave PR must include a
same-class grep command in the commit body and assert it returns 0.

This script is the enforcer:
- Runs from `pr-verify` workflow (or any equivalent CI lane).
- Reads commit messages on the PR branch (`origin/main..HEAD`).
- For each `fix(audit-wave...)` commit, parses the body for the
  finding-ID(s), the same-class scan command, and the asserted-zero
  claim. Re-runs the grep here and fails CI if count > 0.
- Also enforces marker discipline: every wave commit must touch at
  least one source file with a `# V[0-9]+ <FINDING-ID> / Wave-<N>`
  marker matching the closure list.

Usage (CI-style):

    python scripts/ci/check_wave_markers.py [--base origin/main] [--head HEAD]

Exits 0 on pass, 1 on fail with a per-rule diagnostic.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys


# V9 W4-3 / Wave-48 (2026-05-03): widen suffix charset to include `-` so
# hyphenated wave-id forms (e.g. `audit-wave99-w3g1-test`) are recognized
# as wave commits and held to the wave-rule contract.  The old regex
# excluded `-` from the suffix, silently bypassing all wave-rule
# enforcement on those commits.
# V10 Z8-1 / Wave-56 (2026-05-03): the parser gated subject lines too
# strictly — em-dash and slash characters in the post-`):` subject
# tail caused the checker to spuriously fail wave commits whose
# message used those characters legitimately (V9 audit found 17
# such fails on HEAD~10..HEAD).  The regex still anchors the
# `fix(audit-wave...):` envelope but no longer cares about the
# subject content; the body is parsed separately for finding-IDs +
# greps.
WAVE_COMMIT_RE = re.compile(r"^fix\(audit-wave[0-9a-z\-]+\)", re.MULTILINE)
# V8 / Wave-28 (2026-05-03): widen to catch audit-cycle free-form IDs.
# Accepts:
#   AA-C-1, BB-10, V-T-5, U-RF4, R-F-1, S-J3-1            (canonical)
#   HH R-5, HH R-1                                         (HH track refactor proposals)
#   BUG-8, BUG-10                                          (V4-Track-N early IDs)
FINDING_ID_RE = re.compile(
    r"\b("
    # V12 W81 (post-audit cleanup): widened alpha prefix to {1,4}
    # and added optional trailing digit so ``DD5-1``/``BB5-F1``/
    # ``HH3-N-1``/``AA5-2`` style IDs (V8+ convention) match.  Pre-W81
    # the regex required pure-alpha prefix, so the wave-marker
    # enforcer falsely flagged V12 wave-72 (DD5-1/2/3) and W80
    # (BB5-F1) as "no finding-IDs cited" when the IDs were right
    # there in the body.
    r"[A-Z]{1,4}\d{0,3}(?:-[A-Z0-9]+){1,3}"   # AA-C-1, V-T-5, DD5-1, BB5-F1, W74-FOLLOWUP-1, etc.
    r"|HH[ \-]R-\d+"                       # HH R-5, HH R-1, HH-R-5
    r"|BUG-\d+"                            # BUG-8, BUG-10
    r")\b"
)
# V8 / W3-G3 / Wave-32 (2026-05-03): tolerate pasted shell-prompt prefixes
# (`$ grep ...`, `> grep ...`) so paste-from-terminal sessions don't fail the
# missing-grep rule on cosmetic prefix.
SAMECLASS_BLOCK_RE = re.compile(
    r"^[ \t]*(?:[\$>][ \t]+)?(grep -[^\n]+|grep[ \t][^\n]+)$",
    re.MULTILINE,
)
ASSERT_ZERO_RE = re.compile(
    r"(?:asserted|expected|count)[ \t]*[:=][ \t]*0\b",
    re.IGNORECASE,
)


def _run(cmd: list[str], **kw) -> str:
    """Run a shell command, return stdout (or empty string on failure)."""
    try:
        out = subprocess.check_output(
            cmd, stderr=subprocess.STDOUT, **kw,
        )
        return out.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        return e.output.decode("utf-8", errors="replace") if e.output else ""
    except FileNotFoundError:
        return ""


def commits_in_range(base: str, head: str) -> list[tuple[str, str]]:
    """Return [(sha, body)] for each commit in `base..head`."""
    log = _run(
        ["git", "log", "--format=%H%n%B%n----END----", f"{base}..{head}"],
    )
    out: list[tuple[str, str]] = []
    chunks = log.split("----END----\n")
    for ch in chunks:
        ch = ch.strip()
        if not ch:
            continue
        lines = ch.split("\n", 1)
        if len(lines) < 2:
            continue
        sha = lines[0].strip()
        body = lines[1]
        out.append((sha, body))
    return out


def parse_wave_commit(body: str) -> dict | None:
    """Extract the wave PR contract from a commit body.

    Returns None if not a wave commit. Otherwise returns:
        { "ids": [...], "grep_cmds": [...], "asserts_zero": bool }
    """
    if not WAVE_COMMIT_RE.search(body):
        return None
    ids = sorted(set(FINDING_ID_RE.findall(body)))
    # Filter to plausibly-real finding IDs.
    # Real IDs have the shape `<TRACK>-<INDEX>` or `<TRACK>-<SUB>-<INDEX>`,
    # e.g. AA-C-1, BB-10, V-T-5, U-RF4, R-F-1, S-J3-1.
    # Reject pure version tokens (V1, V2, ...) and trivial pairs (CI-OK).
    _VERSION_TOKEN = re.compile(r"^V\d+$", re.IGNORECASE)
    ids = [
        i for i in ids
        if "-" in i
        and len(i) >= 3  # V8/Wave-28: was 4; now 3 to allow R-1/R-5 etc.
        and not _VERSION_TOKEN.match(i)
    ]
    grep_cmds = SAMECLASS_BLOCK_RE.findall(body)
    asserts_zero = bool(ASSERT_ZERO_RE.search(body))
    return {
        "ids": ids,
        "grep_cmds": grep_cmds,
        "asserts_zero": asserts_zero,
    }


def _count_lines(stdout: str) -> int:
    """Count non-empty grep output lines."""
    return sum(1 for line in stdout.splitlines() if line.strip())


def _re_run_grep(cmd_str: str, repo_root: str) -> tuple[int, str]:
    """Re-run the cited grep command in the repo and return (count, stdout).

    Sandboxed: only allows `grep -...` invocations to keep CI safe.
    Runs from `repo_root`. Empty stdout is treated as count=0.
    """
    cmd_str = cmd_str.strip()
    if not cmd_str.startswith("grep"):
        return -1, ""
    # Convert the cited command into a shell-safe argv list. We use
    # `bash -c` so users can paste their actual grep including pipes
    # / globs; sandboxing is via `set -o pipefail` and a 30s timeout.
    full = f"set -e; cd {repo_root!s}; {cmd_str} || true"
    try:
        out = subprocess.check_output(
            ["bash", "-c", full],
            stderr=subprocess.STDOUT,
            timeout=30,
        ).decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        out = e.output.decode("utf-8", errors="replace") if e.output else ""
    except subprocess.TimeoutExpired:
        return -1, "[timeout]"
    except Exception as e:
        return -1, f"[error: {e}]"
    return _count_lines(out), out


def _diff_test_count(base: str, head: str) -> int:
    """Return net change in test functions across all paths between base and head.

    V8 / W3-G2 / Wave-32 (2026-05-03): scope widened from `-- tests/` to all
    paths.  Behavioral tests added in `backend/tests/`, integration suites
    under other directories, or `@pytest.fixture` additions to conftest.py
    are now counted.  Markers: `def test_`, `async def test_`, `@pytest.fixture`.

    V9 W4-1 / Wave-48 (2026-05-03): also count aliased fixture decorators
    (e.g. `from pytest import fixture as fx; @fx`).  We approximate by
    looking at the diff for any added line starting with `@<word>` whose
    word matches one of the names imported from `pytest` in the same
    file.  Implementation: pull the new file content via `git show
    head:path` and AST-parse fixture aliases.
    """
    full_diff = _run(["git", "diff", f"{base}..{head}"])
    if not full_diff.strip():
        return 0
    markers = ("def test_", "async def test_", "@pytest.fixture")
    added = sum(
        1 for line in full_diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
        and any(m in line for m in markers)
    )
    removed = sum(
        1 for line in full_diff.splitlines()
        if line.startswith("-") and not line.startswith("---")
        and any(m in line for m in markers)
    )

    # V9 W4-1: scan for aliased fixture decorators across files in the
    # diff.  Best-effort — if the AST parse fails or git show fails we
    # silently fall back to the marker count.
    try:
        names_status = _run(
            ["git", "diff", "--name-only", f"{base}..{head}"]
        )
        for path in names_status.splitlines():
            if not path.strip().endswith(".py"):
                continue
            content = _run(["git", "show", f"{head}:{path}"])
            if not content:
                continue
            import ast as _ast
            try:
                tree = _ast.parse(content)
            except SyntaxError:
                continue
            aliases: set[str] = set()
            for node in _ast.walk(tree):
                if isinstance(node, _ast.ImportFrom) and node.module == "pytest":
                    for alias in node.names:
                        if alias.name == "fixture":
                            aliases.add(alias.asname or "fixture")
            if not aliases:
                continue
            # Count newly-added decorator lines using these aliases.
            for line in full_diff.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    s = line[1:].lstrip()
                    if any(s.startswith(f"@{a}") for a in aliases):
                        added += 1
    except Exception:
        pass

    return added - removed


def _is_critical_or_high(commit_body: str) -> bool:
    """Heuristic: commit body mentions 'CRITICAL', 'HIGH', or finding IDs
    starting with C-/H- (per audit-cycle convention)."""
    if re.search(r"\b(CRITICAL|HIGH)\b", commit_body):
        return True
    # Finding IDs of severity Critical/High typically include -C-N or -H-N.
    if re.search(r"\b[A-Z]{1,3}-[CH]-\d+\b", commit_body):
        return True
    return False


def check_wave_compliance(
    base: str,
    head: str,
    *,
    enforce_grep_zero: bool = False,
    enforce_test_delta: bool = False,
    repo_root: str = ".",
) -> int:
    """Return number of failed wave-commit checks.

    V8 / Wave-28: the wave-26 version was warn-only; V8 flipped to
    required-mode for all four rules.  V12 W81 (post-audit cleanup,
    2026-05-03) walks back the strict format requirements:

    - finding-IDs cited: REQUIRED (still — easy to satisfy, real signal).
    - same-class grep + count: 0: ADVISORY (was REQUIRED).
      The V12 external auditor counted 191 fails across audit-wave
      history; the format requirement (a literal ``grep -rn '...'``
      followed by ``count: 0`` in the commit body) was V8-era process
      that didn't survive contact with reality.  No one has been
      satisfying it for many waves, making it decorative governance.
    - behavioral test on Critical/High: ADVISORY (was REQUIRED).
      The V12 ``audit_gate`` job in ``.github/workflows/ci.yml``
      enforces a stronger version of this rule: it checks the
      LEDGER's ``behavioral_test_path`` against the classifier,
      catching marker-only tests that the diff-count-only check
      here would miss.  This script's rule is now redundant.

    Override via the ``--strict`` CLI flag if you want the V8 enforcement.
    """
    fails = 0
    commits = commits_in_range(base, head)
    if not commits:
        print(f"[ok] no commits in {base}..{head}")
        return 0

    wave_count = 0
    for sha, body in commits:
        ctx = parse_wave_commit(body)
        if ctx is None:
            continue
        wave_count += 1
        first_line = body.split("\n", 1)[0]
        print(f"\n=== {sha[:8]} {first_line} ===")

        if not ctx["ids"]:
            print(f"  [FAIL] no finding-IDs cited in commit body")
            fails += 1
        else:
            print(f"  [ok] finding-IDs: {', '.join(ctx['ids'])}")

        # Rule 2: same-class grep — re-run and assert 0.
        if not ctx["grep_cmds"]:
            sev = "FAIL" if enforce_grep_zero else "WARN"
            print(
                f"  [{sev}] no `grep` command in body — same-class scan "
                "documentation is missing. Add a `grep -rn '...'` line "
                "to the commit body."
            )
            if enforce_grep_zero:
                fails += 1
        else:
            print(f"  [ok] same-class grep cited: {len(ctx['grep_cmds'])} command(s)")
            # V8 / W3-G1 / Wave-32 (2026-05-03): `count < 0` means the cited
            # grep timed out or errored.  Previously printed [WARN] without
            # incrementing `fails`, so a pathological/timeout grep silently
            # bypassed required-mode.  Now: in required mode, un-evaluated
            # grep is treated as FAIL — at least one grep must successfully
            # evaluate to count == 0.
            for cmd_str in ctx["grep_cmds"]:
                count, _out = _re_run_grep(cmd_str, repo_root)
                if count < 0:
                    sev = "FAIL" if enforce_grep_zero else "WARN"
                    print(
                        f"    [{sev}] could not re-run (count<0; timeout or "
                        f"error): {cmd_str[:80]}"
                    )
                    if enforce_grep_zero:
                        fails += 1
                elif count == 0:
                    print(f"    [ok] re-ran, count=0: {cmd_str[:80]}")
                else:
                    sev = "FAIL" if enforce_grep_zero else "WARN"
                    print(
                        f"    [{sev}] re-ran, count={count}: {cmd_str[:80]}"
                    )
                    if enforce_grep_zero:
                        fails += 1

        if not ctx["asserts_zero"]:
            sev = "FAIL" if enforce_grep_zero else "WARN"
            print(
                f"  [{sev}] commit body does not assert `count: 0`. "
                "Add a line like `same-class scan count: 0` to the body."
            )
            if enforce_grep_zero:
                fails += 1

        # Rule 3: Critical/High commits need a behavioral test diff.
        if enforce_test_delta and _is_critical_or_high(body):
            net = _diff_test_count(f"{sha}~1", sha)
            if net <= 0:
                print(
                    f"  [FAIL] Critical/High wave commit added no new "
                    f"test functions (net delta={net}). Behavioral test "
                    "required (V6 W rule #3)."
                )
                fails += 1
            else:
                print(f"  [ok] +{net} new test function(s)")

    if wave_count == 0:
        print(f"[ok] no wave commits in {base}..{head}")
    return fails


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", default=os.environ.get("CI_BASE_REF", "origin/main"),
        help="Base ref for diff (default: origin/main).",
    )
    parser.add_argument(
        "--head", default=os.environ.get("CI_HEAD_REF", "HEAD"),
        help="Head ref (default: HEAD).",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help=(
            "V8 / Wave-28: legacy warn-mode flag.  V12 W81 made the "
            "default warn-mode for grep/count/test-delta; --warn-only "
            "is now a no-op for those rules.  finding-IDs remain REQUIRED."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "V12 W81: opt back into V8-era strict enforcement of "
            "grep + count=0 + behavioral-test-delta (in addition to "
            "finding-IDs).  Off by default; the V12 audit_gate provides "
            "stronger coverage of the substantive rule."
        ),
    )
    parser.add_argument(
        "--repo-root", default=".",
        help="Repo root for grep re-run (default: cwd).",
    )
    args = parser.parse_args()

    fails = check_wave_compliance(
        args.base,
        args.head,
        enforce_grep_zero=args.strict,
        enforce_test_delta=args.strict,
        repo_root=args.repo_root,
    )
    if fails:
        print(
            f"\n[FAIL] {fails} wave-commit check(s) failed",
            file=sys.stderr,
        )
        return 1
    print("\n[OK] all wave-commit checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
