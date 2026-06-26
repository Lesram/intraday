"""
Scheduled Diagnostics — time-based triggers with history persistence and alerts.

Two components:

    DiagnosticReportStore   — ring buffer + JSON file persistence
    ScheduledDiagnosticRunner — pre-open / post-close triggers + alert integration

Reports are persisted to ``organism_brain/diagnostics/history.json`` so they
survive container restarts and are readable by Claude or any JSON tool.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime, date as date_type, time as dt_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from backend.utils.logger import get_logger

logger = get_logger(__name__)

_ET = ZoneInfo("America/New_York")

# ── Report Store ──────────────────────────────────────────────────

_MAX_REPORTS = 50
_FILE_VERSION = 1


class DiagnosticReportStore:
    """Ring buffer of diagnostic reports persisted to a JSON file.

    Thread-safe via asyncio.Lock.  Atomic writes via tmp+rename
    (matches brain_persistence.py pattern).
    """

    def __init__(self, brain_dir: str = "organism_brain") -> None:
        self._dir = Path(brain_dir) / "diagnostics"
        self._path = self._dir / "history.json"
        self._lock = asyncio.Lock()
        self._reports: list[dict[str, Any]] = []
        self._load()

    # ── public ────────────────────────────────────────────────────

    async def append(self, report: Any, *, trigger: str) -> None:
        """Add a report to the store and persist to disk.

        *report* must have a ``.to_dict()`` method (DiagnosticReport).
        *trigger* is one of: preflight, pre_open, post_close, continuous, manual.
        """
        entry = {
            "trigger": trigger,
            "timestamp": datetime.now(UTC).isoformat(),
            "report": report.to_dict(),
        }
        async with self._lock:
            self._reports.append(entry)
            # Trim to max capacity
            if len(self._reports) > _MAX_REPORTS:
                self._reports = self._reports[-_MAX_REPORTS:]
            self._persist()

    def history(self, limit: int = 20, trigger: str | None = None) -> list[dict[str, Any]]:
        """Return newest-first reports, optionally filtered by trigger."""
        reports = self._reports
        if trigger and trigger != "all":
            reports = [r for r in reports if r.get("trigger") == trigger]
        return list(reversed(reports[-limit:]))

    @property
    def count(self) -> int:
        return len(self._reports)

    # ── persistence ───────────────────────────────────────────────

    def _load(self) -> None:
        """Load history from disk on init."""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            self._reports = data.get("reports", [])[-_MAX_REPORTS:]
            logger.info(
                "Loaded %d diagnostic reports from %s",
                len(self._reports), self._path,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to load diagnostic history: %s", e)
            self._reports = []

    def _persist(self) -> None:
        """Atomic write: tmp file → rename."""
        self._dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _FILE_VERSION,
            "count": len(self._reports),
            "last_updated": datetime.now(UTC).isoformat(),
            "reports": self._reports,
        }
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._dir), suffix=".tmp",
            )
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, str(self._path))
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to persist diagnostic history: %s", e)
            # Clean up tmp file if rename failed
            try:
                os.unlink(tmp_path)
            except Exception:  # noqa: BLE001, S110
                pass


# ── Scheduled Runner ──────────────────────────────────────────────

# Canonical market hours
from backend.utils.market_hours import (
    PRE_OPEN_TIME as _PRE_OPEN_TIME,
    POST_CLOSE_TIME as _POST_CLOSE_TIME,
    is_trading_day as _is_trading_day,
)


class ScheduledDiagnosticRunner:
    """Checks the clock every scheduler iteration and fires pre-open / post-close diagnostics."""

    def __init__(self, store: DiagnosticReportStore) -> None:
        self._store = store
        self._last_pre_open_date: date_type | None = None
        self._last_post_close_date: date_type | None = None

    async def check_and_run(self, engine: Any) -> None:
        """Called every scheduler loop iteration (~10s).

        Determines if a scheduled diagnostic run is due based on
        Eastern Time, weekday, and holidays.  Uses date-based
        idempotency to prevent re-runs on the same day.
        """
        now_et = datetime.now(_ET)

        # Skip weekends and holidays
        if not _is_trading_day(now_et.date()):
            return

        today = now_et.date()
        current_time = now_et.time()

        # PRE_OPEN: 9:25 AM ET — run DEEP before tick window opens (9:28)
        if (
            self._last_pre_open_date != today
            and _PRE_OPEN_TIME <= current_time < dt_time(9, 28)
        ):
            self._last_pre_open_date = today
            await self._run_scheduled(engine, trigger="pre_open")

        # POST_CLOSE: 4:05 PM ET — run DEEP after tick window closes (4:01)
        if (
            self._last_post_close_date != today
            and _POST_CLOSE_TIME <= current_time < dt_time(16, 15)
        ):
            self._last_post_close_date = today
            await self._run_scheduled(engine, trigger="post_close")

    async def _run_scheduled(self, engine: Any, *, trigger: str) -> None:
        """Execute a DEEP diagnostic run and evaluate results for alerts."""
        logger.info("Scheduled diagnostics: trigger=%s", trigger)
        try:
            from backend.organism.diagnostics import diagnostics as _diag, CheckMode
            import backend.organism.diagnostic_checks  # noqa: F401

            report = await _diag.run(CheckMode.DEEP, engine=engine)
            engine._last_diagnostic_report = report
            await self._store.append(report, trigger=trigger)
            await self._evaluate_and_alert(report, trigger)

            summary = report.summary
            logger.info(
                "Scheduled diagnostics [%s]: %d/%d passed (%d critical, %d warnings)",
                trigger, summary["passed"], summary["total"],
                summary["critical_failures"], summary["warnings"],
            )
            if trigger == "post_close":
                self._log_costed_book(engine)
                self._log_shadow_exit_delta(engine)
        except Exception as e:  # noqa: BLE001
            logger.error("Scheduled diagnostics [%s] failed: %s", trigger, e)

    @staticmethod
    def _log_costed_book(engine: Any) -> None:
        """Task A: log a COSTED book summary each post-close so the daily
        scoreboard reflects realistic costs (the recorded P&L is bar-close mids
        with no spread/slippage). Best-effort; no-op if history is unreadable."""
        try:
            import os

            import pandas as pd

            from backend.organism.costing import costed_summary

            brain_dir = getattr(getattr(engine, "brain", None), "brain_dir", None) or "organism_brain"
            path = os.path.join(str(brain_dir), "trade_history.csv")
            if not os.path.exists(path):
                return
            df = pd.read_csv(path)
            if "is_reconciliation_artifact" in df.columns:
                df = df[~df["is_reconciliation_artifact"].astype(str).str.lower().isin(["true", "1"])]
            s = costed_summary(df)
            if not s.get("n"):
                return
            logger.info(
                "Costed book @%.1fbps: n=%d gross=$%.2f NET=$%.2f exp=$%.4f "
                "PF=%s t=%.2f win=%.1f%% (recorded P&L is bar-close mids; this "
                "is the honest scoreboard).",
                s["cost_bps"], s["n"], s["gross_pnl"], s["net_pnl"], s["expectancy"],
                s["profit_factor"], s["t_stat"], 100 * (s["win_rate"] or 0),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Costed-book summary failed: %s", e)

    @staticmethod
    def _log_shadow_exit_delta(engine: Any) -> None:
        """Task S bridge: fold the retracement shadow-vs-real delta into the
        post-close report so Gate-2 evidence builds visibly each afternoon.
        Best-effort; no-op when the shadow is off or has no data."""
        try:
            recorder = getattr(engine, "_shadow_exit", None)
            if recorder is None:
                return
            from backend.organism.experimental.shadow_exit import (
                summarize_shadow_telemetry,
            )
            s = summarize_shadow_telemetry(recorder.path)
            if not s.get("n"):
                logger.info("Shadow exit: no closed-position rows yet.")
                return
            ov = s["overall"]
            engine._last_shadow_summary = s
            by_reg = "; ".join(
                f"{r}: sum=${st['sum']} t={st['t_stat']} (n={st['n']})"
                for r, st in s.get("by_regime", {}).items()
            )
            logger.info(
                "Shadow vs real (retracement) — closed=%d, shadow-diverged=%d | "
                "cumulative delta $%.2f, mean $%.4f, t=%.2f | by_regime: %s | "
                "Gate-2: flip live exits only when this delta is positive at t>=2.",
                s["n"], s["n_triggered"], ov["sum"], ov["mean"], ov["t_stat"],
                by_reg or "(none triggered yet)",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Shadow exit delta summary failed: %s", e)

    async def _evaluate_and_alert(self, report: Any, trigger: str) -> None:
        """Map diagnostic results to alerts via the existing alert system."""
        try:
            from backend.infra.alerting import (
                AlertCategory,
                AlertSeverity,
                get_alert_manager,
            )
        except ImportError:
            return  # alerting not available

        manager = get_alert_manager()
        summary = report.summary
        failed_names = [
            r.name for r in report.results if not r.passed
        ]

        if summary["critical_failures"] > 0:
            critical_names = [
                r.name for r in report.results
                if not r.passed and r.severity == "critical"
            ]
            await manager.send_alert(
                category=AlertCategory.SYSTEM_ERROR,
                severity=AlertSeverity.CRITICAL,
                title=f"Diagnostics [{trigger}]: {summary['critical_failures']} critical failure(s)",
                description=(
                    f"Failed checks: {', '.join(critical_names)}\n"
                    f"Total: {summary['passed']}/{summary['total']} passed"
                ),
                details={"trigger": trigger, "failed": failed_names},
                respect_market_hours=False,  # critical bypasses suppression
            )
        elif summary["warnings"] > 0:
            await manager.send_alert(
                category=AlertCategory.SYSTEM_ERROR,
                severity=AlertSeverity.WARNING,
                title=f"Diagnostics [{trigger}]: {summary['warnings']} warning(s)",
                description=(
                    f"Failed checks: {', '.join(failed_names)}\n"
                    f"Total: {summary['passed']}/{summary['total']} passed"
                ),
                details={"trigger": trigger, "failed": failed_names},
                respect_market_hours=True,
            )
        elif trigger == "pre_open":
            # All passed at pre_open → confirmation alert
            await manager.send_alert(
                category=AlertCategory.SYSTEM_ERROR,
                severity=AlertSeverity.INFO,
                title="Diagnostics [pre_open]: Engine ready",
                description=f"All {summary['total']} checks passed. Engine ready for market open.",
                details={"trigger": trigger},
                respect_market_hours=True,
            )
        # post_close all-pass → no alert (noise reduction)
