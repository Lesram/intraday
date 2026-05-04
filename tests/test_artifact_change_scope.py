from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CHANGE_SCOPE_PATH = ROOT / "scripts" / "ci" / "change_scope.py"
AUDIT_INDEX_PATH = ROOT / "scripts" / "ci" / "generate_audit_index.py"


def _load_change_scope():
    spec = importlib.util.spec_from_file_location("change_scope_under_test", CHANGE_SCOPE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_audit_index():
    ci_dir = str(ROOT / "scripts" / "ci")
    if ci_dir not in sys.path:
        sys.path.insert(0, ci_dir)
    spec = importlib.util.spec_from_file_location("audit_index_under_test", AUDIT_INDEX_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=repo,
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def _commit_file(repo: Path, name: str, content: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    _git(repo, "add", name)
    _git(repo, "commit", "-m", f"add {name}")


def _repo_with_branch_history(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "audit@example.com")
    _git(repo, "config", "user.name", "Audit Test")
    _commit_file(repo, "base.txt", "base\n")
    _git(repo, "checkout", "-b", "feature")
    _commit_file(repo, "branch.txt", "branch\n")
    _commit_file(repo, "task.txt", "task\n")
    return repo


def _clear_scope_env(monkeypatch) -> None:
    for key in (
        "GITHUB_ACTIONS",
        "GITHUB_BASE_REF",
        "INTRA_CHANGE_SCOPE",
        "INTRA_DIFF_BASE",
        "INTRA_DIFF_RANGE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_local_default_reports_last_commit_only(tmp_path, monkeypatch):
    change_scope = _load_change_scope()
    repo = _repo_with_branch_history(tmp_path)
    _clear_scope_env(monkeypatch)

    change_set = change_scope.get_change_set(root=repo)

    assert change_set.scope == "task"
    assert change_set.ref == "HEAD"
    assert change_set.paths == ["task.txt"]


def test_github_default_reports_pr_range(tmp_path, monkeypatch):
    change_scope = _load_change_scope()
    repo = _repo_with_branch_history(tmp_path)
    _clear_scope_env(monkeypatch)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_BASE_REF", "main")

    change_set = change_scope.get_change_set(root=repo)

    assert change_set.scope == "pr"
    assert change_set.ref == "main...HEAD"
    assert change_set.paths == ["branch.txt", "task.txt"]


def test_explicit_diff_range_overrides_ci_pr_scope(tmp_path, monkeypatch):
    change_scope = _load_change_scope()
    repo = _repo_with_branch_history(tmp_path)
    _clear_scope_env(monkeypatch)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    monkeypatch.setenv("INTRA_DIFF_RANGE", "HEAD^..HEAD")

    change_set = change_scope.get_change_set(root=repo)

    assert change_set.scope == "range"
    assert change_set.ref == "HEAD^..HEAD"
    assert change_set.paths == ["task.txt"]


def test_working_tree_scope_includes_dirty_and_untracked_paths(tmp_path, monkeypatch):
    change_scope = _load_change_scope()
    repo = _repo_with_branch_history(tmp_path)
    _clear_scope_env(monkeypatch)
    monkeypatch.setenv("INTRA_CHANGE_SCOPE", "working-tree")
    (repo / "task.txt").write_text("dirty\n")
    (repo / "untracked.txt").write_text("untracked\n")

    change_set = change_scope.get_change_set(root=repo)

    assert change_set.scope == "working-tree"
    assert change_set.ref == "HEAD+working-tree"
    assert change_set.paths == ["task.txt", "untracked.txt"]


def test_audit_index_classifies_ci_scripts_as_tooling_evidence():
    audit_index = _load_audit_index()

    scope = audit_index.classify_pr_scope([
        "scripts/ci/change_scope.py",
        "scripts/ci/generate_artifacts.py",
        "tests/test_artifact_change_scope.py",
    ])

    assert scope == "tooling/evidence_only"
