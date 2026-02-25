"""
Tests for the Diagnostic Scheduler — report store, scheduled runner, and alert mapping.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, date, datetime, time as dt_time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.organism.diagnostics import DiagnosticReport, DiagnosticResult
from backend.organism.diagnostic_scheduler import (
    DiagnosticReportStore,
    ScheduledDiagnosticRunner,
    _MAX_REPORTS,
)

_ET = ZoneInfo("America/New_York")


# ── Helpers ───────────────────────────────────────────────────────

def _make_report(
    mode: str = "deep",
    passed: int = 10,
    critical_fail: int = 0,
    warnings: int = 0,
) -> DiagnosticReport:
    """Build a synthetic DiagnosticReport."""
    results: list[DiagnosticResult] = []
    for i in range(passed):
        results.append(DiagnosticResult(
            name=f"check_pass_{i}",
            category="wiring",
            severity="info",
            passed=True,
            message="ok",
            duration_ms=1.0,
        ))
    for i in range(critical_fail):
        results.append(DiagnosticResult(
            name=f"check_crit_fail_{i}",
            category="wiring",
            severity="critical",
            passed=False,
            message="critical failure",
            duration_ms=1.0,
        ))
    for i in range(warnings):
        results.append(DiagnosticResult(
            name=f"check_warn_{i}",
            category="order_flow",
            severity="warning",
            passed=False,
            message="warning issue",
            duration_ms=1.0,
        ))
    return DiagnosticReport(
        mode=mode,
        timestamp=datetime.now(UTC).isoformat(),
        results=results,
        duration_ms=50.0,
    )


def _mock_engine() -> MagicMock:
    """Create a mock engine for scheduled runner tests."""
    engine = MagicMock()
    engine._last_diagnostic_report = None
    return engine


# ═══════════════════════════════════════════════════════════════════
#  Test: DiagnosticReportStore
# ═══════════════════════════════════════════════════════════════════

class TestDiagnosticReportStore:

    @pytest.mark.asyncio
    async def test_append_and_history(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        report = _make_report(passed=5)

        await store.append(report, trigger="manual")

        history = store.history(limit=10)
        assert len(history) == 1
        assert history[0]["trigger"] == "manual"
        assert history[0]["report"]["mode"] == "deep"
        assert history[0]["report"]["summary"]["passed"] == 5

    @pytest.mark.asyncio
    async def test_history_newest_first(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))

        await store.append(_make_report(passed=1), trigger="preflight")
        await store.append(_make_report(passed=2), trigger="continuous")
        await store.append(_make_report(passed=3), trigger="pre_open")

        history = store.history(limit=10)
        assert len(history) == 3
        # Newest first
        assert history[0]["trigger"] == "pre_open"
        assert history[1]["trigger"] == "continuous"
        assert history[2]["trigger"] == "preflight"

    @pytest.mark.asyncio
    async def test_max_capacity_enforced(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))

        for i in range(_MAX_REPORTS + 10):
            await store.append(_make_report(passed=i), trigger="continuous")

        assert store.count == _MAX_REPORTS

    @pytest.mark.asyncio
    async def test_trigger_filter(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))

        await store.append(_make_report(), trigger="preflight")
        await store.append(_make_report(), trigger="continuous")
        await store.append(_make_report(), trigger="pre_open")
        await store.append(_make_report(), trigger="manual")

        pre_open = store.history(limit=10, trigger="pre_open")
        assert len(pre_open) == 1
        assert pre_open[0]["trigger"] == "pre_open"

        continuous = store.history(limit=10, trigger="continuous")
        assert len(continuous) == 1

        all_reports = store.history(limit=10, trigger="all")
        assert len(all_reports) == 4


class TestFilePersistence:

    @pytest.mark.asyncio
    async def test_persist_and_reload(self, tmp_path):
        """Reports survive store restart (simulated)."""
        store1 = DiagnosticReportStore(brain_dir=str(tmp_path))
        await store1.append(_make_report(passed=7), trigger="pre_open")
        await store1.append(_make_report(passed=3, warnings=1), trigger="post_close")

        # Create a new store pointing to same dir — simulates restart
        store2 = DiagnosticReportStore(brain_dir=str(tmp_path))
        assert store2.count == 2
        history = store2.history(limit=10)
        assert history[0]["trigger"] == "post_close"
        assert history[1]["trigger"] == "pre_open"

    @pytest.mark.asyncio
    async def test_file_is_valid_json(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        await store.append(_make_report(passed=5), trigger="manual")

        path = tmp_path / "diagnostics" / "history.json"
        assert path.exists()

        data = json.loads(path.read_text())
        assert data["version"] == 1
        assert data["count"] == 1
        assert len(data["reports"]) == 1
        assert "last_updated" in data

    @pytest.mark.asyncio
    async def test_corrupt_file_handled_gracefully(self, tmp_path):
        """Store should start fresh if history file is corrupted."""
        diag_dir = tmp_path / "diagnostics"
        diag_dir.mkdir(parents=True)
        (diag_dir / "history.json").write_text("not valid json{{{")

        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        assert store.count == 0  # gracefully recovered


# ═══════════════════════════════════════════════════════════════════
#  Test: ScheduledDiagnosticRunner
# ═══════════════════════════════════════════════════════════════════

class TestScheduledDiagnosticRunner:

    @pytest.mark.asyncio
    async def test_pre_open_triggers_at_correct_time(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        runner = ScheduledDiagnosticRunner(store=store)
        engine = _mock_engine()

        # Mock datetime.now to return 9:26 AM ET on a Tuesday
        mock_now = datetime(2026, 2, 24, 9, 26, 0, tzinfo=_ET)  # Tuesday

        with patch("backend.organism.diagnostic_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch.object(runner, "_run_scheduled", new_callable=AsyncMock) as mock_run:
                await runner.check_and_run(engine)
                mock_run.assert_called_once_with(engine, trigger="pre_open")

    @pytest.mark.asyncio
    async def test_post_close_triggers_at_correct_time(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        runner = ScheduledDiagnosticRunner(store=store)
        engine = _mock_engine()

        mock_now = datetime(2026, 2, 24, 16, 6, 0, tzinfo=_ET)  # Tuesday 4:06 PM

        with patch("backend.organism.diagnostic_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch.object(runner, "_run_scheduled", new_callable=AsyncMock) as mock_run:
                await runner.check_and_run(engine)
                mock_run.assert_called_once_with(engine, trigger="post_close")

    @pytest.mark.asyncio
    async def test_weekend_skip(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        runner = ScheduledDiagnosticRunner(store=store)
        engine = _mock_engine()

        # Saturday at 9:26 AM
        mock_now = datetime(2026, 2, 28, 9, 26, 0, tzinfo=_ET)  # Saturday

        with patch("backend.organism.diagnostic_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch.object(runner, "_run_scheduled", new_callable=AsyncMock) as mock_run:
                await runner.check_and_run(engine)
                mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_holiday_skip(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        runner = ScheduledDiagnosticRunner(store=store)
        engine = _mock_engine()

        # Memorial Day 2026 (May 25) at 9:26 AM
        mock_now = datetime(2026, 5, 25, 9, 26, 0, tzinfo=_ET)  # Monday holiday

        with patch("backend.organism.diagnostic_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch.object(runner, "_run_scheduled", new_callable=AsyncMock) as mock_run:
                await runner.check_and_run(engine)
                mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_day_idempotency(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        runner = ScheduledDiagnosticRunner(store=store)
        engine = _mock_engine()

        mock_now = datetime(2026, 2, 24, 9, 26, 0, tzinfo=_ET)

        with patch("backend.organism.diagnostic_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch.object(runner, "_run_scheduled", new_callable=AsyncMock) as mock_run:
                await runner.check_and_run(engine)
                await runner.check_and_run(engine)
                await runner.check_and_run(engine)
                # Should only run once despite 3 calls
                assert mock_run.call_count == 1


# ═══════════════════════════════════════════════════════════════════
#  Test: Alert Mapping
# ═══════════════════════════════════════════════════════════════════

class TestAlertMapping:

    @pytest.mark.asyncio
    async def test_critical_failure_fires_critical_alert(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        runner = ScheduledDiagnosticRunner(store=store)

        report = _make_report(passed=8, critical_fail=2)

        mock_manager = MagicMock()
        mock_manager.send_alert = AsyncMock(return_value=True)

        # Patch at source — the function is imported lazily inside _evaluate_and_alert
        with patch("backend.infra.alerting.get_alert_manager", return_value=mock_manager):
            await runner._evaluate_and_alert(report, "pre_open")

        mock_manager.send_alert.assert_called_once()
        call_args = mock_manager.send_alert.call_args
        from backend.infra.alerting import AlertSeverity
        assert call_args.kwargs["severity"] == AlertSeverity.CRITICAL
        assert call_args.kwargs["respect_market_hours"] is False

    @pytest.mark.asyncio
    async def test_warnings_fire_warning_alert(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        runner = ScheduledDiagnosticRunner(store=store)

        report = _make_report(passed=8, warnings=2)

        mock_manager = MagicMock()
        mock_manager.send_alert = AsyncMock(return_value=True)

        with patch("backend.infra.alerting.get_alert_manager", return_value=mock_manager):
            await runner._evaluate_and_alert(report, "pre_open")

        mock_manager.send_alert.assert_called_once()
        call_args = mock_manager.send_alert.call_args
        from backend.infra.alerting import AlertSeverity
        assert call_args.kwargs["severity"] == AlertSeverity.WARNING

    @pytest.mark.asyncio
    async def test_all_pass_pre_open_fires_info(self, tmp_path):
        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        runner = ScheduledDiagnosticRunner(store=store)

        report = _make_report(passed=10)

        mock_manager = MagicMock()
        mock_manager.send_alert = AsyncMock(return_value=True)

        with patch("backend.infra.alerting.get_alert_manager", return_value=mock_manager):
            await runner._evaluate_and_alert(report, "pre_open")

        mock_manager.send_alert.assert_called_once()
        call_args = mock_manager.send_alert.call_args
        from backend.infra.alerting import AlertSeverity
        assert call_args.kwargs["severity"] == AlertSeverity.INFO

    @pytest.mark.asyncio
    async def test_all_pass_post_close_no_alert(self, tmp_path):
        """All-pass at post_close should not fire any alert (noise reduction)."""
        store = DiagnosticReportStore(brain_dir=str(tmp_path))
        runner = ScheduledDiagnosticRunner(store=store)

        report = _make_report(passed=10)

        mock_manager = MagicMock()
        mock_manager.send_alert = AsyncMock(return_value=True)

        with patch("backend.infra.alerting.get_alert_manager", return_value=mock_manager):
            await runner._evaluate_and_alert(report, "post_close")

        mock_manager.send_alert.assert_not_called()
