"""V12 W82 (post-audit cleanup): tests for Dockerfile build-arg env wiring.

Closes the V12 external auditor's finding:

    "Container env has no GIT_SHA, BUILD_TIME, or IMAGE_SHA; only
     app env and risk caps."

Pre-W82 the deploy endpoint (added in W78) returned ``"unknown"`` for
all three provenance fields because the Dockerfile only baked
VCS_REF and BUILD_DATE into LABEL metadata, not into runtime ENV.
W82 wires them through.

Run with:
    ./venv/bin/python -m pytest tests/test_v12_w82_dockerfile_env.py -v
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"
COMPOSE_PAPER = REPO_ROOT / "docker-compose.paper.yml"
REBUILD_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "rebuild_paper.sh"


# ────────────────────────────────────────────────────────────────────
# Dockerfile structural assertions.
# ────────────────────────────────────────────────────────────────────

def test_w82_dockerfile_runtime_stage_exports_git_sha():
    """The runtime stage must set GIT_SHA from the VCS_REF build arg."""
    src = DOCKERFILE.read_text()
    # Find the runtime stage block.
    runtime_idx = src.find("FROM python:3.12-slim AS runtime")
    assert runtime_idx >= 0, "Dockerfile structure changed: no runtime stage"
    runtime_block = src[runtime_idx:]
    # ENV GIT_SHA=...  (with default).
    assert re.search(
        r"ENV\s+GIT_SHA\s*=\s*\$\{VCS_REF[^}]*\}",
        runtime_block,
    ), (
        "V12 W82 regression: runtime stage no longer exports "
        "GIT_SHA from VCS_REF build arg.  Deploy endpoint would "
        "return 'unknown' again."
    )


def test_w82_dockerfile_runtime_stage_exports_build_time():
    src = DOCKERFILE.read_text()
    runtime_idx = src.find("FROM python:3.12-slim AS runtime")
    runtime_block = src[runtime_idx:]
    assert re.search(
        r"BUILD_TIME\s*=\s*\$\{BUILD_DATE[^}]*\}",
        runtime_block,
    ), "V12 W82 regression: BUILD_TIME not exported from BUILD_DATE"


def test_w82_dockerfile_runtime_stage_exports_image_sha():
    src = DOCKERFILE.read_text()
    runtime_idx = src.find("FROM python:3.12-slim AS runtime")
    runtime_block = src[runtime_idx:]
    assert "IMAGE_SHA" in runtime_block, (
        "V12 W82 regression: IMAGE_SHA env not exported in runtime stage"
    )


def test_w82_dockerfile_redeclares_args_in_runtime_stage():
    """Build args declared at the top must be re-declared after the
    runtime FROM (Docker requirement) for the ENV substitution to
    work."""
    src = DOCKERFILE.read_text()
    runtime_idx = src.find("FROM python:3.12-slim AS runtime")
    runtime_block = src[runtime_idx:]
    # The ENV substitution requires VCS_REF + BUILD_DATE redeclared.
    assert "ARG VCS_REF" in runtime_block, (
        "ARG VCS_REF must be redeclared in runtime stage for "
        "${VCS_REF} substitution to work in ENV."
    )
    assert "ARG BUILD_DATE" in runtime_block, (
        "ARG BUILD_DATE must be redeclared in runtime stage."
    )


# ────────────────────────────────────────────────────────────────────
# docker-compose.paper.yml passes the build args.
# ────────────────────────────────────────────────────────────────────

def test_w82_compose_paper_passes_build_args():
    """docker-compose.paper.yml must pass VCS_REF + BUILD_DATE to the
    api service's build."""
    import yaml
    data = yaml.safe_load(COMPOSE_PAPER.read_text())
    api = data.get("services", {}).get("api", {})
    build = api.get("build", {})
    args = build.get("args") or {}
    assert "VCS_REF" in args, (
        "V12 W82 regression: paper compose no longer passes VCS_REF "
        "build arg.  Deploy endpoint would return 'unknown' for "
        "GIT_SHA on next rebuild."
    )
    assert "BUILD_DATE" in args, (
        "V12 W82 regression: paper compose no longer passes BUILD_DATE."
    )


# ────────────────────────────────────────────────────────────────────
# Rebuild helper script exists + is executable.
# ────────────────────────────────────────────────────────────────────

def test_w82_rebuild_helper_exists_and_is_executable():
    """``scripts/deploy/rebuild_paper.sh`` must be present and +x —
    operators rely on it for clean rebuilds with provenance baked in."""
    assert REBUILD_SCRIPT.is_file()
    import os
    mode = os.stat(REBUILD_SCRIPT).st_mode
    assert mode & 0o100, (
        "V12 W82 regression: rebuild_paper.sh not executable — "
        "operators would have to run it with ``bash`` explicitly."
    )


def test_w82_rebuild_helper_captures_git_sha():
    """The helper must capture VCS_REF from ``git rev-parse HEAD`` and
    BUILD_DATE from ``date -u`` — those are the values the deploy
    endpoint reads back."""
    src = REBUILD_SCRIPT.read_text()
    assert "git rev-parse HEAD" in src
    assert "date -u" in src


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def test_w82_rebuild_helper_preserves_phase7_telemetry_defaults(
    tmp_path: Path,
    monkeypatch,
):
    """Run the helper against fake docker/curl tools and verify defaults."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_REBUILD_LOG", str(calls))
    monkeypatch.delenv("ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED", raising=False)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    _write_executable(
        fake_bin / "git",
        """#!/usr/bin/env bash
if [[ "$1 $2" == "rev-parse HEAD" ]]; then
  echo "abc123"
  exit 0
fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "docker-compose",
        """#!/usr/bin/env bash
echo "docker-compose $*" >> "$FAKE_REBUILD_LOG"
exit 0
""",
    )
    _write_executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
if [[ "$*" == *"/api/v1/health/deploy"* ]]; then
  printf "401"
  exit 0
fi
exit 0
""",
    )
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_REBUILD_LOG"
exit 0
""",
    )

    result = subprocess.run(
        [str(REBUILD_SCRIPT)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )

    assert "PHASE5_TELEMETRY = true" in result.stdout
    assert "PHASE6_TELEMETRY = true" in result.stdout
    assert "PHASE9_SHADOW_ENGINES = true" in result.stdout
    log = calls.read_text()
    assert "docker-compose -f docker-compose.paper.yml build api" in log
    assert "docker-compose -f docker-compose.paper.yml up -d api" in log


# ────────────────────────────────────────────────────────────────────
# Endpoint behavioral check (in-process — container rebuild verified
# in W83 separately).
# ────────────────────────────────────────────────────────────────────

def test_w82_deploy_endpoint_picks_up_env(monkeypatch):
    """Set GIT_SHA / BUILD_TIME / IMAGE_SHA in env; hit the resolver
    functions; assert they propagate.  Locks the wiring contract."""
    monkeypatch.setenv("GIT_SHA", "deadbeef" * 5)
    monkeypatch.setenv("BUILD_TIME", "2026-05-03T17:25:00Z")
    monkeypatch.setenv("IMAGE_SHA", "image-deadbeef")

    from backend.api.routes.deploy_health import deploy_health
    import asyncio
    payload = asyncio.run(deploy_health())
    assert payload["source_sha"] == "deadbeef" * 5
    assert payload["build_time"] == "2026-05-03T17:25:00Z"
    assert payload["image_sha"] == "image-deadbeef"


def test_w82_deploy_endpoint_falls_through_to_unknown(monkeypatch):
    """Without the env set, the endpoint reports ``unknown`` (graceful
    fallback) rather than crashing."""
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("VCS_SHA", raising=False)
    monkeypatch.delenv("BUILD_TIME", raising=False)
    monkeypatch.delenv("IMAGE_SHA", raising=False)

    from backend.api.routes.deploy_health import deploy_health
    import asyncio
    payload = asyncio.run(deploy_health())
    # source_sha may resolve via git rev-parse fallback if running
    # from a checkout; either real SHA or "unknown" is acceptable.
    assert isinstance(payload["source_sha"], str) and payload["source_sha"]
    assert payload["build_time"] == "unknown"
    assert payload["image_sha"] == "unknown"
