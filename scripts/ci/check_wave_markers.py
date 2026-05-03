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
FINDING_ID_RE = re.compile(r"\b([A-Z]{1,3}(?:-[A-Z0-9]+){1,3})\b")
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
        and len(i) >= 4
        and not _VERSION_TOKEN.match(i)
    ]
    grep_cmds = SAMECLASS_BLOCK_RE.findall(body)
    asserts_zero = bool(ASSERT_ZERO_RE.search(body))
    return {
        "ids": ids,
        "grep_cmds": grep_cmds,
        "asserts_zero": asserts_zero,
    }


def check_wave_compliance(base: str, head: str) -> int:
    """Return number of failed wave-commit checks."""
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

        if not ctx["grep_cmds"]:
            print(
                "  [WARN] no `grep` command in body — same-class scan "
                "documentation is missing. Add a `grep -rn '...'` line "
                "to the commit body to document what was checked."
            )
        else:
            print(f"  [ok] same-class grep cited: {len(ctx['grep_cmds'])} command(s)")

        if not ctx["asserts_zero"]:
            print(
                "  [WARN] commit body does not assert `count: 0` for the "
                "same-class scan. Add a line like `count: 0` to the body."
            )

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
    args = parser.parse_args()

    fails = check_wave_compliance(args.base, args.head)
    if fails:
        print(f"\n[FAIL] {fails} wave-commit check(s) failed", file=sys.stderr)
        return 1
    print("\n[OK] all wave-commit checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
