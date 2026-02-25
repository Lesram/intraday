"""
System Diagnostics Framework — validates component wiring, state integrity,
and cross-module consistency that unit tests miss.

Three modes:
    PREFLIGHT   — runs at startup before first tick
    DEEP        — on-demand via admin API
    CONTINUOUS  — every N ticks during operation

In-memory only — no DB storage. Results exposed via API and dashboard.
"""

from __future__ import annotations

import asyncio
import enum
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Coroutine

from backend.utils.logger import get_logger

logger = get_logger(__name__)


# ── Enums ──────────────────────────────────────────────────────────

class CheckSeverity(str, enum.Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class CheckMode(str, enum.Enum):
    PREFLIGHT = "preflight"
    DEEP = "deep"
    CONTINUOUS = "continuous"


class CheckCategory(str, enum.Enum):
    WIRING = "wiring"
    STATE_PERSISTENCE = "state_persistence"
    ORDER_FLOW = "order_flow"
    DATA_PIPELINE = "data_pipeline"
    STREAMING = "streaming"
    GOVERNANCE = "governance"
    BROKER_SYNC = "broker_sync"
    INFRASTRUCTURE = "infrastructure"


# ── Result dataclasses ─────────────────────────────────────────────

@dataclass
class DiagnosticResult:
    name: str
    category: str
    severity: str
    passed: bool
    message: str
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "severity": self.severity,
            "passed": self.passed,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class DiagnosticReport:
    mode: str
    timestamp: str
    results: list[DiagnosticResult] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def all_critical_passed(self) -> bool:
        return all(
            r.passed for r in self.results
            if r.severity == CheckSeverity.CRITICAL.value
        )

    @property
    def summary(self) -> dict[str, int]:
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        warnings = sum(
            1 for r in self.results
            if not r.passed and r.severity == CheckSeverity.WARNING.value
        )
        critical_failures = sum(
            1 for r in self.results
            if not r.passed and r.severity == CheckSeverity.CRITICAL.value
        )
        return {
            "total": len(self.results),
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "critical_failures": critical_failures,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "timestamp": self.timestamp,
            "duration_ms": round(self.duration_ms, 2),
            "all_critical_passed": self.all_critical_passed,
            "summary": self.summary,
            "results": [r.to_dict() for r in self.results],
        }


# ── Check registration metadata ───────────────────────────────────

@dataclass
class _CheckMeta:
    name: str
    category: CheckCategory
    severity: CheckSeverity
    modes: set[CheckMode]
    timeout: float  # seconds
    fn: Callable[..., Coroutine[Any, Any, DiagnosticResult]]


# ── Engine ─────────────────────────────────────────────────────────

class DiagnosticEngine:
    """Registry + runner for diagnostic checks."""

    def __init__(self) -> None:
        self._checks: list[_CheckMeta] = []

    def check(
        self,
        name: str,
        category: CheckCategory,
        severity: CheckSeverity,
        modes: set[CheckMode],
        timeout: float = 10.0,
    ) -> Callable:
        """Decorator to register a diagnostic check function.

        The decorated function must be ``async def(engine=None, app=None)``
        and return a ``DiagnosticResult``.
        """
        def decorator(fn: Callable) -> Callable:
            self._checks.append(_CheckMeta(
                name=name,
                category=category,
                severity=severity,
                modes=modes,
                timeout=timeout,
                fn=fn,
            ))
            return fn
        return decorator

    async def run(
        self,
        mode: CheckMode,
        *,
        engine: Any = None,
        app: Any = None,
    ) -> DiagnosticReport:
        """Run all checks applicable to *mode* and return a report."""
        start = time.monotonic()
        applicable = [c for c in self._checks if mode in c.modes]
        results: list[DiagnosticResult] = []

        for meta in applicable:
            t0 = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    meta.fn(engine=engine, app=app),
                    timeout=meta.timeout,
                )
                result.duration_ms = (time.monotonic() - t0) * 1000
            except asyncio.TimeoutError:
                result = DiagnosticResult(
                    name=meta.name,
                    category=meta.category.value,
                    severity=meta.severity.value,
                    passed=False,
                    message=f"Timed out after {meta.timeout}s",
                    duration_ms=(time.monotonic() - t0) * 1000,
                )
            except Exception as e:
                result = DiagnosticResult(
                    name=meta.name,
                    category=meta.category.value,
                    severity=meta.severity.value,
                    passed=False,
                    message=f"Exception: {e}",
                    duration_ms=(time.monotonic() - t0) * 1000,
                )
            results.append(result)

        elapsed = (time.monotonic() - start) * 1000
        report = DiagnosticReport(
            mode=mode.value,
            timestamp=datetime.now(UTC).isoformat(),
            results=results,
            duration_ms=elapsed,
        )
        return report


# ── Global singleton ───────────────────────────────────────────────
diagnostics = DiagnosticEngine()
