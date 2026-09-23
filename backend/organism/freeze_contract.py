"""Read-only authority checks for an active forward-evaluation cutoff.

Candidate surface verification is a separate operation. Legacy active artifacts
may omit the status flags; absence is compatibility, not proof of deployment
approval. Callers with activation/binding evidence must still verify that chain.
This module imports only the standard library and never loads trading state.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path


def validate_active_freeze(payload: object) -> dict:
    """Reject candidate/unapproved/malformed input without changing its cutoff."""
    if not isinstance(payload, dict):
        raise ValueError("invalid_active_freeze")
    for flag in ("candidate_only", "deployment_approved"):
        if flag in payload and type(payload[flag]) is not bool:
            raise ValueError("invalid_active_freeze_flags")
    if payload.get("candidate_only") is True or payload.get("deployment_approved") is False:
        raise ValueError("nonactive_freeze")
    cutoff = payload.get("FROZEN_AT")
    if not isinstance(cutoff, str) or not cutoff:
        raise ValueError("invalid_active_freeze_cutoff")
    try:
        parsed = datetime.fromisoformat(cutoff)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except (ValueError, OverflowError):
        raise ValueError("invalid_active_freeze_cutoff") from None
    # Do not normalize, replace, or fall back to an active_forward_cutoff field.
    return payload


def load_active_freeze(path: str | Path) -> dict:
    """Read once and validate; invalid/unavailable inputs expose no raw payload."""
    try:
        payload = json.loads(Path(path).read_bytes())
    except (OSError, ValueError, TypeError):
        raise ValueError("invalid_or_unavailable_active_freeze") from None
    return validate_active_freeze(payload)
