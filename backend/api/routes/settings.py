"""
Settings API — read/write all engine/trading/ML configuration with hot-reload.

Endpoints:
    GET  /settings/organism   — engine configuration
    PUT  /settings/organism   — update engine configuration
    GET  /settings/trading    — trading parameters
    PUT  /settings/trading    — update trading parameters
    GET  /settings/ml         — ML model parameters
    PUT  /settings/ml         — update ML model parameters
    POST /settings/restart-engine — safely restart organism engine
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.infra.security import AuthenticatedUser, require_admin
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/settings")

# ── Persistence ───────────────────────────────────────────────────

_SETTINGS_FILE = Path(
    os.getenv("ORGANISM_SETTINGS_FILE", "organism_settings.json")
)

_settings_cache: dict[str, Any] = {}


def _load_settings() -> dict[str, Any]:
    """Load persisted settings from JSON file."""
    global _settings_cache
    if _settings_cache:
        return _settings_cache
    if _SETTINGS_FILE.exists():
        try:
            _settings_cache = json.loads(_SETTINGS_FILE.read_text())
            return _settings_cache
        except Exception as e:
            logger.warning("Failed to load settings: %s", e)
    return {}


def _save_settings(data: dict[str, Any]) -> None:
    """Persist settings to JSON file."""
    global _settings_cache
    _settings_cache.update(data)
    try:
        _SETTINGS_FILE.write_text(json.dumps(_settings_cache, indent=2))
    except Exception as e:
        logger.warning("Failed to save settings: %s", e)


# ── Pydantic Models ──────────────────────────────────────────────


class OrganismSettings(BaseModel):
    tick_interval_seconds: int = Field(default=60, ge=1, le=300)
    timeframe: str = Field(default="1Day", pattern=r"^(1Min|5Min|15Min|1Hour|1Day)$")
    lookback: int = Field(default=500, ge=50, le=2000)
    max_positions: int = Field(default=8, ge=1, le=50)
    retrain_interval: int = Field(default=60, ge=10, le=1000)
    use_streaming: bool = False
    universe: list[str] = Field(default_factory=list)
    min_bars: int = Field(default=200, ge=10, le=1000)


class TradingSettings(BaseModel):
    max_position_pct: float = Field(default=0.08, ge=0.01, le=0.50)
    vol_target: float = Field(default=0.15, ge=0.01, le=1.0)
    min_position_usd: float = Field(default=500.0, ge=0, le=100000)
    long_only: bool = True
    atr_multiplier: float = Field(default=1.0, ge=0.1, le=10.0)
    profit_r_multiple: float = Field(default=3.0, ge=0.5, le=20.0)
    trailing_distance_atr: float = Field(default=1.5, ge=0.1, le=10.0)
    max_bars_held: int = Field(default=120, ge=1, le=10000)
    partial_tp_pct: float = Field(default=0.40, ge=0.0, le=1.0)


class MLSettings(BaseModel):
    n_estimators: int = Field(default=200, ge=50, le=500)
    max_depth: int = Field(default=5, ge=3, le=15)
    learning_rate: float = Field(default=0.05, ge=0.01, le=0.5)
    direction_threshold: float = Field(default=0.52, ge=0.5, le=0.7)
    retrain_interval: int = Field(default=60, ge=10, le=1000)


# ── Helper: Get Scheduler ────────────────────────────────────────


def _get_scheduler(request: Request) -> Any:
    """Get the organism scheduler from app state."""
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    return scheduler


def _get_engine(request: Request) -> Any:
    """Get the organism live engine from app state."""
    scheduler = _get_scheduler(request)
    if scheduler and hasattr(scheduler, "_engine"):
        return scheduler._engine
    return None


# ── Organism Settings ─────────────────────────────────────────────


@router.get("/organism")
async def get_organism_settings(request: Request) -> dict[str, Any]:
    """Get current organism engine configuration."""
    from backend.organism.live_engine import (
        LIVE_LOOKBACK, LIVE_TIMEFRAME, MAX_OPEN_POSITIONS,
        RETRAIN_INTERVAL, MIN_BARS, USE_STREAMING,
    )

    scheduler = _get_scheduler(request)
    engine = _get_engine(request)

    saved = _load_settings().get("organism", {})

    settings = {
        "tick_interval_seconds": scheduler._tick_interval if scheduler else int(os.getenv("ORGANISM_TICK_INTERVAL_SECONDS", "60")),
        "timeframe": LIVE_TIMEFRAME,
        "lookback": LIVE_LOOKBACK,
        "max_positions": MAX_OPEN_POSITIONS,
        "retrain_interval": RETRAIN_INTERVAL,
        "use_streaming": USE_STREAMING,
        "min_bars": MIN_BARS,
        "universe": list(engine._universe) if engine else [],
    }

    # Override with any saved values not yet applied
    settings.update({k: v for k, v in saved.items() if k in settings})

    return settings


def _check_governance(request: Request) -> None:
    """H5: Enforce governance controls on settings mutations.
    Raises HTTPException if organism is frozen or halted."""
    governance = getattr(request.app.state, "organism_governance", None)
    if governance:
        if getattr(governance, "is_frozen", False):
            raise HTTPException(status_code=403, detail="Organism is frozen — settings changes blocked")
        if hasattr(governance, "is_trading_halted") and governance.is_trading_halted:
            raise HTTPException(status_code=403, detail="Trading is halted — settings changes blocked")


@router.put("/organism")
async def update_organism_settings(
    request: Request, body: OrganismSettings,
    # V7 AA-M-3 / Wave-24 (2026-05-03): admin-only.
    current_user: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    """Update organism engine configuration with hot-reload."""
    _check_governance(request)
    scheduler = _get_scheduler(request)
    config = body.model_dump(exclude_unset=True)

    changed: dict[str, Any] = {}
    if scheduler:
        changed = await scheduler.update_config(config)
    else:
        logger.warning("No scheduler available — saving settings for next restart")

    # Persist
    _save_settings({"organism": config})

    # Broadcast settings update via Socket.IO
    await _broadcast_settings_change("organism", config)

    return {"updated": changed, "saved": True}


# ── Trading Settings ──────────────────────────────────────────────


@router.get("/trading")
async def get_trading_settings(request: Request) -> dict[str, Any]:
    """Get current trading parameters."""
    from backend.organism.live_engine import LONG_ONLY

    engine = _get_engine(request)
    saved = _load_settings().get("trading", {})

    settings = {
        "max_position_pct": engine.kelly_sizer.max_position_pct if engine else 0.08,
        "vol_target": engine.kelly_sizer.vol_target if engine else 0.15,
        "min_position_usd": engine.kelly_sizer.min_position_usd if engine else 500.0,
        "long_only": LONG_ONLY,
        "atr_multiplier": engine.exit_engine.atr_multiplier if engine else 1.0,
        "profit_r_multiple": engine.exit_engine.profit_r_multiple if engine else 3.0,
        "trailing_distance_atr": engine.exit_engine.trailing_distance_atr if engine else 1.5,
        "max_bars_held": engine.exit_engine.max_bars_held if engine else 120,
        "partial_tp_pct": engine.exit_engine.partial_tp_pct if engine else 0.40,
    }

    settings.update({k: v for k, v in saved.items() if k in settings})
    return settings


@router.put("/trading")
async def update_trading_settings(
    request: Request, body: TradingSettings,
    # V7 AA-M-3 / Wave-24 (2026-05-03): admin-only.
    current_user: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    """Update trading parameters with hot-reload."""
    _check_governance(request)
    scheduler = _get_scheduler(request)
    config = body.model_dump(exclude_unset=True)

    changed: dict[str, Any] = {}
    if scheduler:
        changed = await scheduler.update_config(config)
    else:
        logger.warning("No scheduler available — saving settings for next restart")

    _save_settings({"trading": config})
    await _broadcast_settings_change("trading", config)

    return {"updated": changed, "saved": True}


# ── ML Settings ───────────────────────────────────────────────────


@router.get("/ml")
async def get_ml_settings(request: Request) -> dict[str, Any]:
    """Get current ML model parameters."""
    from backend.organism.live_engine import RETRAIN_INTERVAL

    engine = _get_engine(request)
    saved = _load_settings().get("ml", {})

    settings = {
        "n_estimators": engine.signal_gen._xgb_params.get("n_estimators", 200) if engine else 200,
        "max_depth": engine.signal_gen._xgb_params.get("max_depth", 5) if engine else 5,
        "learning_rate": engine.signal_gen._xgb_params.get("learning_rate", 0.05) if engine else 0.05,
        "direction_threshold": engine.signal_gen._direction_threshold_buy if engine else 0.52,
        "retrain_interval": RETRAIN_INTERVAL,
    }

    settings.update({k: v for k, v in saved.items() if k in settings})
    return settings


@router.put("/ml")
async def update_ml_settings(
    request: Request, body: MLSettings,
    # V7 AA-M-3 / Wave-24 (2026-05-03): admin-only.
    current_user: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    """Update ML model parameters with hot-reload."""
    _check_governance(request)
    scheduler = _get_scheduler(request)
    config = body.model_dump(exclude_unset=True)

    changed: dict[str, Any] = {}
    if scheduler:
        changed = await scheduler.update_config(config)
    else:
        logger.warning("No scheduler available — saving settings for next restart")

    _save_settings({"ml": config})
    await _broadcast_settings_change("ml", config)

    return {"updated": changed, "saved": True}


# ── Engine Restart ────────────────────────────────────────────────


@router.post("/restart-engine")
async def restart_engine(
    request: Request,
    # V7 AA-M-4 / Wave-24 (2026-05-03): admin-only.
    current_user: AuthenticatedUser = Depends(require_admin),
) -> dict[str, Any]:
    """Safely restart the organism engine with current settings."""
    scheduler = _get_scheduler(request)
    if not scheduler:
        raise HTTPException(status_code=503, detail="Organism scheduler not running")

    try:
        await scheduler.stop()
        await scheduler.start()
        return {"status": "restarted", "running": scheduler.is_running}
    except Exception as e:
        logger.error("Engine restart failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Restart failed: {e}")


# ── Broadcast Helper ──────────────────────────────────────────────


async def _broadcast_settings_change(category: str, settings: dict[str, Any]) -> None:
    """Broadcast settings update via Socket.IO."""
    try:
        from backend.api.socketio_server import broadcast_to_topic
        from datetime import datetime, UTC

        await broadcast_to_topic(
            "settings",
            "settings_update",
            {
                "category": category,
                "settings": settings,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    except Exception:
        pass  # Socket.IO not available — acceptable
