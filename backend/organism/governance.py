"""
Phase 0 — Governance: kill switches, freeze controls, policy versioning, audit hooks.

Provides the "immune system" for the living organism:
- Global freeze/unfreeze for all adaptation
- Per-strategy disable switches
- Global stop-trading switch
- Policy version tracking with config hashes
- Rate-limit enforcement on weight/param changes
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GovernanceState:
    """Snapshot of all governance controls at a point in time."""
    frozen: bool = False
    trading_halted: bool = False
    disabled_strategies: set[str] = field(default_factory=set)
    policy_version: str = ""
    config_hash: str = ""
    last_changed: str = ""
    change_count_today: int = 0
    max_changes_per_day: int = 50


class GovernanceController:
    """Central kill-switch and freeze controller for the organism."""

    def __init__(self) -> None:
        # Read from env (can be toggled live via supervisor)
        self._frozen = os.getenv("ORGANISM_FREEZE_ADAPTATION", "0") in ("1", "true")
        self._trading_halted = os.getenv("ORGANISM_HALT_TRADING", "0") in ("1", "true")
        self._disabled: set[str] = set()
        disabled_csv = os.getenv("ORGANISM_DISABLED_STRATEGIES", "")
        if disabled_csv:
            self._disabled = {s.strip().lower() for s in disabled_csv.split(",") if s.strip()}

        self._max_changes_per_day = int(os.getenv("ORGANISM_MAX_CHANGES_PER_DAY", "100"))
        self._change_count = 0
        self._last_reset_date: str = ""
        self._policy_version: str = ""
        self._config_hash: str = ""

        # Drawdown kill switch
        self._drawdown_limit = float(os.getenv("ORGANISM_DRAWDOWN_KILL_PCT", "0.05"))
        self._drawdown_cooldown_s = int(os.getenv("ORGANISM_DRAWDOWN_COOLDOWN_S", "3600"))
        self._drawdown_triggered_at: datetime | None = None
        # P&L-028: adaptive cooldown — may be scaled up by trigger_drawdown_kill()
        self._effective_cooldown_s: int = self._drawdown_cooldown_s

    # ── queries ──────────────────────────────────────────────────────

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    @property
    def is_trading_halted(self) -> bool:
        if self._trading_halted:
            return True
        if self._drawdown_triggered_at:
            elapsed = (datetime.now(UTC) - self._drawdown_triggered_at).total_seconds()
            if elapsed < self._effective_cooldown_s:
                return True
            # Cooldown expired — reset
            self._drawdown_triggered_at = None
        return False

    def is_strategy_disabled(self, source: str) -> bool:
        return source.lower() in self._disabled

    def can_change(self) -> bool:
        """Check if the daily change budget allows another adaptation."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self._change_count = 0
            self._last_reset_date = today
        return self._change_count < self._max_changes_per_day

    # ── mutations (called by other organism modules) ─────────────────

    def record_change(self) -> None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self._change_count = 0
            self._last_reset_date = today
        self._change_count += 1

    def freeze(self) -> None:
        self._frozen = True
        logger.warning("Organism adaptation FROZEN")

    def unfreeze(self) -> None:
        self._frozen = False
        logger.info("Organism adaptation UNFROZEN")

    def halt_trading(self) -> None:
        self._trading_halted = True
        logger.warning("Organism trading HALTED")

    def resume_trading(self) -> None:
        self._trading_halted = False
        logger.info("Organism trading RESUMED")

    def disable_strategy(self, source: str) -> None:
        self._disabled.add(source.lower())
        logger.warning("Strategy disabled", extra={"source": source})

    def enable_strategy(self, source: str) -> None:
        self._disabled.discard(source.lower())
        logger.info("Strategy enabled", extra={"source": source})

    def trigger_drawdown_kill(self, drawdown_pct: float) -> None:
        """Called when portfolio drawdown exceeds limit.

        P&L-028: Adaptive cooldown — the cooldown period scales with the
        severity of the drawdown so minor dips recover faster and large
        drawdowns enforce longer cooling periods.

        Sets a cooldown-based halt: trading resumes automatically after
        ``_effective_cooldown_s`` seconds.  We intentionally do NOT set
        ``_trading_halted = True`` here so that ``is_trading_halted`` can
        detect cooldown expiry and auto-recover.
        """
        if drawdown_pct >= self._drawdown_limit:
            self._drawdown_triggered_at = datetime.now(UTC)
            # P&L-028: Adaptive cooldown — scale with drawdown severity.
            # Base cooldown at the limit; 2× at +5% over limit; 3× at +10%.
            excess = max(0.0, drawdown_pct - self._drawdown_limit)
            severity_mult = 1.0 + min(2.0, excess / 0.05)
            self._effective_cooldown_s = int(self._drawdown_cooldown_s * severity_mult)
            logger.critical(
                "DRAWDOWN KILL SWITCH TRIGGERED",
                extra={
                    "drawdown_pct": drawdown_pct,
                    "limit": self._drawdown_limit,
                    "cooldown_s": self._effective_cooldown_s,
                },
            )

    def set_policy_version(self, version: str, config: dict[str, Any]) -> None:
        self._policy_version = version
        self._config_hash = hashlib.sha256(
            json.dumps(config, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

    # ── snapshot ─────────────────────────────────────────────────────

    def snapshot(self) -> GovernanceState:
        return GovernanceState(
            frozen=self._frozen,
            trading_halted=self.is_trading_halted,
            disabled_strategies=set(self._disabled),
            policy_version=self._policy_version,
            config_hash=self._config_hash,
            last_changed=datetime.now(UTC).isoformat(),
            change_count_today=self._change_count,
            max_changes_per_day=self._max_changes_per_day,
        )

    def to_dict(self) -> dict[str, Any]:
        s = self.snapshot()
        return {
            "frozen": s.frozen,
            "trading_halted": s.trading_halted,
            "disabled_strategies": sorted(s.disabled_strategies),
            "policy_version": s.policy_version,
            "config_hash": s.config_hash,
            "change_count_today": s.change_count_today,
            "max_changes_per_day": s.max_changes_per_day,
        }

    # ── persistence (Phase 1.2) ─────────────────────────────────────

    def to_persistence_dict(self) -> dict[str, Any]:
        """Serialize governance state for brain persistence.

        Captures internal state fields that survive across runs.
        """
        return {
            "frozen": self._frozen,
            "trading_halted": self._trading_halted,
            "disabled_strategies": sorted(self._disabled),
            "change_count": self._change_count,
            "last_reset_date": self._last_reset_date,
            "policy_version": self._policy_version,
            "config_hash": self._config_hash,
            "effective_cooldown_s": self._effective_cooldown_s,
            "drawdown_limit": self._drawdown_limit,
            "max_changes_per_day": self._max_changes_per_day,
            "drawdown_triggered_at": (
                self._drawdown_triggered_at.isoformat()
                if self._drawdown_triggered_at else None
            ),
        }

    def from_persistence_dict(self, data: dict[str, Any]) -> None:
        """Restore governance state from brain persistence."""
        self._frozen = data.get("frozen", self._frozen)
        self._trading_halted = data.get("trading_halted", self._trading_halted)
        self._change_count = data.get("change_count", 0)
        self._last_reset_date = data.get("last_reset_date", "")
        self._policy_version = data.get("policy_version", "")
        self._config_hash = data.get("config_hash", "")
        self._effective_cooldown_s = data.get(
            "effective_cooldown_s", self._drawdown_cooldown_s
        )
        # Restore governance limits (may have been tuned at runtime)
        self._drawdown_limit = data.get(
            "drawdown_limit", self._drawdown_limit
        )
        self._max_changes_per_day = data.get(
            "max_changes_per_day", self._max_changes_per_day
        )
        # Restore disabled strategies — MERGE with env-var overrides so that
        # ORGANISM_DISABLED_STRATEGIES remains authoritative as a safety control
        persisted_disabled = set(data.get("disabled_strategies", []))
        env_csv = os.getenv("ORGANISM_DISABLED_STRATEGIES", "")
        env_disabled = {s.strip().lower() for s in env_csv.split(",") if s.strip()}
        self._disabled = persisted_disabled | env_disabled

        # Restore drawdown cooldown state
        dd_at = data.get("drawdown_triggered_at")
        if dd_at:
            try:
                self._drawdown_triggered_at = datetime.fromisoformat(dd_at)
            except (ValueError, TypeError):
                self._drawdown_triggered_at = None
        else:
            self._drawdown_triggered_at = None
        logger.info(
            "Governance state restored from brain",
            extra={"frozen": self._frozen, "halted": self._trading_halted},
        )
