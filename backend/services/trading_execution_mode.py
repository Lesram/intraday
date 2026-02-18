"""Runtime trading execution mode override.

This provides an admin-controlled, in-process override for TRADING_EXECUTION_MODE.

Notes:
- The default mode comes from the canonical settings (AppSettings.trading_execution_mode).
- The override is process-local (per worker). In multi-worker deployments, use a
  shared store (DB/Redis) or restart all workers with updated env.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
import threading

# §2.1 FIX: Use canonical config instead of separate UnifiedSettings
from backend.config.settings import get_settings
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


ALLOWED_EFFECTIVE_MODES: tuple[str, ...] = ("execute", "shadow", "dry_run")


@dataclass(frozen=True)
class TradingExecutionModeState:
    mode: str
    source: str  # "override" | "env"
    default_mode: str
    overridden: bool
    override_set_by: str | None
    override_set_at: str | None
    allowed_modes: tuple[str, ...]
    alpaca_paper: bool
    alpaca_base_url: str
    use_mock_broker: bool


_lock = threading.Lock()
_override_mode: str | None = None
_override_set_by: str | None = None
_override_set_at: datetime | None = None


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_mode(mode: str) -> str:
    """Normalize and validate the trading execution mode."""
    mode = (mode or "").strip().lower()
    # Normalize aliases
    if mode in {"paper", "live"}:
        mode = "execute"
    if mode not in ALLOWED_EFFECTIVE_MODES:
        raise ValueError(
            f"Unsupported trading execution mode '{mode}'. Allowed: {ALLOWED_EFFECTIVE_MODES}"
        )
    return mode


def _build_state(effective_mode: str) -> TradingExecutionModeState:
    settings = get_settings()
    default_mode = getattr(settings, "trading_execution_mode", "execute")
    try:
        default_mode = _normalize_mode(default_mode)
    except Exception:
        default_mode = "execute"

    with _lock:
        overridden = _override_mode is not None
        override_set_by = _override_set_by
        override_set_at = _override_set_at

    source = "override" if overridden else "env"

    return TradingExecutionModeState(
        mode=effective_mode,
        source=source,
        default_mode=default_mode,
        overridden=overridden,
        override_set_by=override_set_by,
        override_set_at=override_set_at.isoformat() if override_set_at else None,
        allowed_modes=ALLOWED_EFFECTIVE_MODES,
        alpaca_paper=_bool_env("ALPACA_PAPER", "false"),
        alpaca_base_url=str(getattr(settings, "alpaca_base_url", "")),
        use_mock_broker=bool(getattr(settings, "USE_MOCK_BROKER", False)),
    )


def get_trading_execution_mode() -> TradingExecutionModeState:
    """Return the current effective trading execution mode."""
    settings = get_settings()
    default_mode = getattr(settings, "trading_execution_mode", "execute")
    try:
        default_mode = _normalize_mode(default_mode)
    except Exception:
        default_mode = "execute"

    with _lock:
        effective = _override_mode or default_mode

    return _build_state(effective)


def set_trading_execution_mode_override(mode: str, *, actor: str) -> TradingExecutionModeState:
    """Set a process-local override for the trading execution mode."""
    normalized = _normalize_mode(mode)
    now = datetime.now(UTC)

    with _lock:
        global _override_mode, _override_set_by, _override_set_at
        _override_mode = normalized
        _override_set_by = actor
        _override_set_at = now

    logger.warning(
        "Trading execution mode override set",
        actor=actor,
        mode=normalized,
        overridden=True,
    )
    return _build_state(normalized)


def clear_trading_execution_mode_override(*, actor: str) -> TradingExecutionModeState:
    """Clear the process-local override (falls back to env/default)."""
    with _lock:
        global _override_mode, _override_set_by, _override_set_at
        _override_mode = None
        _override_set_by = None
        _override_set_at = None

    logger.warning(
        "Trading execution mode override cleared",
        actor=actor,
        overridden=False,
    )
    return get_trading_execution_mode()
