"""Runtime identity helpers shared by deploy health and evidence telemetry."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any

from backend.config import get_settings


def resolve_git_sha() -> str:
    """Return the running source SHA without raising during early startup."""
    env_sha = os.environ.get("GIT_SHA") or os.environ.get("VCS_SHA")
    if env_sha:
        return env_sha
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, OSError, FileNotFoundError):
        return "unknown"


def runtime_config_hash() -> str:
    """Stable non-secret hash of runtime settings that affect trading behavior."""
    settings = get_settings()
    keys = (
        "BUILD_VERSION",
        "APP_ENVIRONMENT",
        "TRADING_EXECUTION_MODE",
        "USE_MOCK_BROKER",
    )
    payload: dict[str, Any] = {key: str(getattr(settings, key, None)) for key in keys}
    for env_name in (
        "ORGANISM_DRAWDOWN_KILL_PCT",
        "ORGANISM_MAX_DAILY_LOSS",
        "ORGANISM_MAX_NOTIONAL",
        "ORGANISM_ORB_LIVE_ENABLED",
        "ORGANISM_EOD_LIVE_ENABLED",
        "ORGANISM_MEAN_REVERSION_LIVE_ENABLED",
        "ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED",
    ):
        payload[env_name] = os.environ.get(env_name, "")
    blob = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def runtime_identity_snapshot() -> dict[str, str]:
    """Return provenance fields that every strategy evidence row should carry."""
    return {
        "git_sha": resolve_git_sha(),
        "runtime_config_hash": runtime_config_hash(),
        "image_sha": os.environ.get("IMAGE_SHA", "unknown"),
        "build_time": os.environ.get("BUILD_TIME", "unknown"),
    }
