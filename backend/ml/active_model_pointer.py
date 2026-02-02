"""Utilities for exposing the latest trained model artifact to live trading.

This module writes/reads a small JSON "pointer" file on disk that records the
currently-active model artifact path and metadata.

Rationale: live strategy code often runs outside of a request context and may not
have a DB session available. A pointer file provides a simple, explicit bridge
from training jobs (which know the artifact path) to inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Any


def _pointer_dir() -> Path:
    root = os.environ.get("ACTIVE_MODEL_POINTER_DIR") or os.environ.get("MODEL_STORE_PATH") or "models"
    return Path(root) / "active_models"


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in name.strip())


@dataclass(frozen=True)
class ActiveModelInfo:
    name: str
    version: str | None
    path: str
    trained_at: str | None
    target_kind: str | None
    feature_columns: list[str] | None
    extra: dict[str, Any]


def write_active_model_pointer(
    *,
    model_name: str,
    model_path: str,
    version: str | None = None,
    trained_at: datetime | None = None,
    target_kind: str | None = None,
    feature_columns: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    pointer_dir = _pointer_dir()
    pointer_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "name": model_name,
        "version": version,
        "path": model_path,
        "trained_at": trained_at.isoformat() if trained_at else None,
        "target_kind": target_kind,
        "feature_columns": feature_columns or None,
        "extra": extra or {},
    }

    out_path = pointer_dir / f"{_safe_name(model_name)}.json"

    # Atomic-ish write (write to temp, then replace).
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(pointer_dir), encoding="utf-8") as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp_path = Path(tmp.name)

    tmp_path.replace(out_path)
    return out_path


def load_active_model_pointer(model_name: str) -> ActiveModelInfo | None:
    path = _pointer_dir() / f"{_safe_name(model_name)}.json"
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    extra = data.get("extra")
    if not isinstance(extra, dict):
        extra = {}

    feature_columns = data.get("feature_columns")
    if feature_columns is not None and not isinstance(feature_columns, list):
        feature_columns = None

    return ActiveModelInfo(
        name=str(data.get("name") or model_name),
        version=(str(data.get("version")) if data.get("version") is not None else None),
        path=str(data.get("path") or ""),
        trained_at=(str(data.get("trained_at")) if data.get("trained_at") is not None else None),
        target_kind=(str(data.get("target_kind")) if data.get("target_kind") is not None else None),
        feature_columns=feature_columns,
        extra=extra,
    )
