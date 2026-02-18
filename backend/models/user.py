"""Minimal user model compatibility shim for legacy tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class User:
    """Simple user object used in unit-test specs."""

    id: int = 0
    username: str = ""
    is_admin: bool = False
    permissions: list[str] = field(default_factory=list)
