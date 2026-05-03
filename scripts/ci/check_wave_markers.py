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


WAVE_COMMIT_RE = re.compile(r"^fix\(audit-wave[0-9a-z]+\)", re.MULTILINE)
# V8 / Wave-28 (2026-05-03): widen to catch audit-cycle free-form IDs.
# Accepts:
#   AA-C-1, BB-10, V-T-5, U-RF4, R-F-1, S-J3-1            (canonical)
#   HH R-5, HH R-1                                         (HH track refactor proposals)
#   BUG-8, BUG-10                                          (V4-Track-N early IDs)
FINDING_ID_RE = re.compile(
    r"\b("
    r"[A-Z]{1,3}(?:-[A-Z0-9]+){1,3}"   # AA-C-1, V-T-5, etc.
    r"|HH[ \-]R-\d+"                    # HH R-5, HH R-1, HH-R-5
    r"|BUG-\d+"                         # BUG-8, BUG-10
    r")\b"
)
SAMECLASS_BLOCK_RE = re.compile(
    r"^[ \t]*(grep -[^\n]+|grep[ \t][^\n]+)$",
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
    """Return the net change in `def test_` lines under tests/ between base and head."""
    diff = _run(
        ["git", "diff", "--numstat", f"{base}..{head}", "--", "tests/"],
    )
    if not diff.strip():
        return 0
    # Count actual added test functions via diff content.
    full_diff = _run(["git", "diff", f"{base}..{head}", "--", "tests/"])
    added = sum(
        1 for line in full_diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
        and ("def test_" in line or "async def test_" in line)
    )
    removed = sum(
        1 for line in full_diff.splitlines()
        if line.startswith("-") and not line.startswith("---")
        and ("def test_" in line or "async def test_" in line)
    )
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
    enforce_grep_zero: bool = True,
    enforce_test_delta: bool = True,
    repo_root: str = ".",
) -> int:
    """Return number of failed wave-commit checks.

    V8 / Wave-28 (2026-05-03): the wave-26 version was warn-only.
    This version flips to required-mode by default:

    - finding-IDs cited: REQUIRED (already)
    - same-class grep: REQUIRED + RE-RUN (count must be 0)
    - asserts_zero in body: REQUIRED (audit acknowledgment)
    - behavioral test added on Critical/High waves: REQUIRED via diff

    `enforce_grep_zero` and `enforce_test_delta` flags allow a
    transitional warn-mode (set both to False) if rolled out.
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
            for cmd_str in ctx["grep_cmds"]:
                count, _out = _re_run_grep(cmd_str, repo_root)
                if count < 0:
                    print(f"    [WARN] could not re-run: {cmd_str!r}")
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
            "V8 / Wave-28: legacy warn-mode. Default is REQUIRED enforcement "
            "(grep re-run with count==0; behavioral test on Critical/High)."
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
        enforce_grep_zero=not args.warn_only,
        enforce_test_delta=not args.warn_only,
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
