"""Changed-file scope helpers for local tasks and PR-wide artifact runs."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ChangeSet:
    paths: list[str]
    scope: str
    ref: str


def _sh(cmd: list[str], *, root: Path = ROOT) -> str:
    try:
        return subprocess.check_output(
            cmd,
            cwd=str(root),
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _split_paths(output: str) -> list[str]:
    return [p for p in output.splitlines() if p.strip()]


def _unique(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def default_change_scope() -> str:
    """Default to PR-wide in CI, task-local for local cleanup work."""
    explicit = os.environ.get("INTRA_CHANGE_SCOPE", "").strip().lower()
    if explicit:
        return explicit
    if os.environ.get("GITHUB_ACTIONS") or os.environ.get("GITHUB_BASE_REF"):
        return "pr"
    return "task"


def _diff_range_paths(diff_range: str, *, root: Path) -> list[str]:
    return _split_paths(_sh(["git", "diff", "--name-only", diff_range], root=root))


def _task_paths(*, root: Path) -> list[str]:
    paths = _split_paths(
        _sh(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"], root=root)
    )
    if paths:
        return paths
    return _diff_range_paths("HEAD^..HEAD", root=root)


def _pr_paths(*, root: Path) -> tuple[list[str], str]:
    base = os.environ.get("GITHUB_BASE_REF", "main").strip() or "main"
    candidates = [f"origin/{base}...HEAD", f"{base}...HEAD"]
    if base.startswith(("origin/", "HEAD", "refs/")):
        candidates.insert(0, f"{base}...HEAD")

    for diff_ref in _unique(candidates):
        paths = _diff_range_paths(diff_ref, root=root)
        if paths:
            return paths, diff_ref

    fallback = "HEAD^..HEAD"
    return _diff_range_paths(fallback, root=root), fallback


def _working_tree_paths(*, root: Path) -> list[str]:
    paths: list[str] = []
    paths.extend(_split_paths(_sh(["git", "diff", "--name-only", "HEAD"], root=root)))
    paths.extend(_split_paths(_sh(["git", "diff", "--name-only", "--cached"], root=root)))
    paths.extend(_split_paths(_sh(["git", "ls-files", "--others", "--exclude-standard"], root=root)))
    return _unique(paths)


def get_change_set(*, root: Path = ROOT, scope: str | None = None) -> ChangeSet:
    """Return changed files plus the scope/ref used to collect them.

    Overrides:
    - INTRA_DIFF_RANGE: exact git diff range/spec, highest precedence.
    - INTRA_DIFF_BASE: compared as ``<base>...HEAD``.
    - INTRA_CHANGE_SCOPE: one of task, commit, pr, working-tree.
    """
    explicit_range = os.environ.get("INTRA_DIFF_RANGE", "").strip()
    if explicit_range:
        return ChangeSet(
            paths=_diff_range_paths(explicit_range, root=root),
            scope="range",
            ref=explicit_range,
        )

    explicit_base = os.environ.get("INTRA_DIFF_BASE", "").strip()
    if explicit_base:
        diff_ref = f"{explicit_base}...HEAD"
        return ChangeSet(
            paths=_diff_range_paths(diff_ref, root=root),
            scope="base",
            ref=diff_ref,
        )

    resolved_scope = (scope or default_change_scope()).strip().lower()
    if resolved_scope in {"task", "commit", "last-commit"}:
        return ChangeSet(paths=_task_paths(root=root), scope="task", ref="HEAD")
    if resolved_scope in {"pr", "branch"}:
        paths, ref = _pr_paths(root=root)
        return ChangeSet(paths=paths, scope="pr", ref=ref)
    if resolved_scope in {"working-tree", "worktree", "dirty"}:
        return ChangeSet(
            paths=_working_tree_paths(root=root),
            scope="working-tree",
            ref="HEAD+working-tree",
        )

    return ChangeSet(paths=_task_paths(root=root), scope="task", ref="HEAD")
