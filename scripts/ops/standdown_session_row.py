#!/usr/bin/env python3
"""Read-only session diagnostics. Missing coverage is unknown, never zero proof."""
from __future__ import annotations
import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ET = ZoneInfo("America/New_York")
UTC = timezone.utc
MAX_TICK_GAP_SECONDS = 120


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(UTC)


def calendar_session(day: str, calendar: list, now: datetime) -> dict:
    """Broker calendar has date and local Eastern open/close HH:MM fields."""
    requested = date.fromisoformat(day)
    if requested > now.astimezone(ET).date():
        raise ValueError("future_session")
    if not isinstance(calendar, list):
        raise ValueError("invalid_calendar")
    if not calendar:
        return {"state": "NO_SESSION", "date": day}
    if len(calendar) != 1 or not isinstance(calendar[0], dict) or calendar[0].get("date") != day:
        raise ValueError("calendar_date_mismatch")
    row = calendar[0]
    opened = datetime.fromisoformat(day + "T" + row["open"]).replace(tzinfo=ET).astimezone(UTC)
    closed = datetime.fromisoformat(day + "T" + row["close"]).replace(tzinfo=ET).astimezone(UTC)
    if opened >= closed or requested.weekday() >= 5:
        raise ValueError("invalid_calendar_hours")
    return {"state": "CLOSED" if now >= closed + timedelta(minutes=5) else "BEFORE_CLOSE",
            "date": day, "open": opened.isoformat(), "close": closed.isoformat(),
            "eligible_at": (closed + timedelta(minutes=5)).isoformat()}


def log_record(line: str, *, naive_timezone: str | None = None) -> tuple[datetime, str]:
    """Accept structured UTC logs and explicitly zoned legacy text logs."""
    if line.lstrip().startswith("{"):
        row = json.loads(line)
        return timestamp(row["timestamp"]), str(row.get("message", ""))
    match = re.match(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2})?)", line)
    if not match:
        raise ValueError("unparseable_log_record")
    parsed = datetime.fromisoformat(match[1].replace(",", ".").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        if naive_timezone is None:
            raise ValueError("unknown_log_timezone")
        parsed = parsed.replace(tzinfo=ZoneInfo(naive_timezone))
    return parsed.astimezone(UTC), line[match.end():]


def session_diagnostics(day: str, session: dict, evidence: bytes, ledger: bytes,
                        logs: dict[str, bytes], *, naive_timezone: str | None = None) -> dict:
    counts = Counter(evidence_events=0, live_candidates=0, direction_zero=0,
                     scanner_empty=0, stale_bars=0, liquidity_blocks=0, orders=0,
                     ledger_closes=0, successful_ticks=0, tick_errors=0)
    regimes: Counter = Counter()
    malformed = Counter(events=0, logs=0, ledger=0)
    tick_times = []
    duplicate_log_records = 0
    seen_logs = set()
    for raw in evidence.decode("utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
            when = timestamp(row["timestamp"])
            if when.astimezone(ET).date().isoformat() != day:
                continue
            counts["evidence_events"] += 1
            regimes[str(row.get("regime") or "unknown")] += 1
            counts["live_candidates"] += row.get("live_pipeline_candidate") is True
            counts["direction_zero"] += row.get("defensive_filter_reason") == "direction_zero"
        except (ValueError, KeyError, TypeError, AttributeError):
            malformed["events"] += 1
    for content in logs.values():
        for line in content.decode("utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                when, message = log_record(line, naive_timezone=naive_timezone)
            except (ValueError, KeyError, TypeError, AttributeError):
                malformed["logs"] += 1
                continue
            if when.astimezone(ET).date().isoformat() != day:
                continue
            key = (when, message)
            if key in seen_logs:
                duplicate_log_records += 1
                continue
            seen_logs.add(key)
            for needle, name in (("no stocks passed initial filters", "scanner_empty"),
                                 ("Streaming bars REJECTED", "stale_bars"),
                                 ("Liquidity gate blocked", "liquidity_blocks"),
                                 ("Order submitted successfully", "orders")):
                counts[name] += needle in message
            if "Organism tick: regime=" in message:
                counts["successful_ticks"] += 1
                tick_times.append(when)
            if "Organism tick completed with errors" in message or "Organism scheduler tick failed" in message:
                counts["tick_errors"] += 1
    for row in csv.DictReader(io.StringIO(ledger.decode("utf-8-sig"))):
        try:
            counts["ledger_closes"] += timestamp(row["closed_at"]).astimezone(ET).date().isoformat() == day
        except (ValueError, KeyError, TypeError, AttributeError):
            malformed["ledger"] += 1
    gap = None
    if session.get("open") and session.get("close"):
        opened, closed = timestamp(session["open"]), timestamp(session["close"])
        ticks = sorted(set(t for t in tick_times if opened <= t <= closed))
        if ticks:
            boundaries = [opened, *ticks, closed]
            gap = max((b - a).total_seconds() for a, b in zip(boundaries, boundaries[1:]))
    coverage = ("OBSERVED_TICK_COVERAGE" if gap is not None and gap <= MAX_TICK_GAP_SECONDS
                and not malformed["logs"] and not counts["tick_errors"] else "UNVERIFIED")
    return {"date": day, "counts": dict(counts), "regimes": dict(regimes),
            "malformed": dict(malformed), "log_files": sorted(logs),
            "duplicate_log_records": duplicate_log_records, "coverage": coverage,
            "max_successful_tick_gap_seconds": gap,
            "coverage_gap_budget_seconds": MAX_TICK_GAP_SECONDS,
            "limitations": ["Tick logs attest observations, not uninterrupted host availability or all trading paths.",
                            "Missing/unparseable logs make counters lower bounds, never complete zeros."]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date", nargs="?", default=datetime.now(ET).date().isoformat())
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--calendar", type=Path, help="Saved broker calendar response for the exact date")
    parser.add_argument("--log-timezone", help="Explicit timezone of legacy unzoned log timestamps")
    parser.add_argument("--force", action="store_true", help="Diagnostic only; never completed-session evidence")
    args = parser.parse_args(argv)
    try:
        now = datetime.now(UTC)
        if args.calendar:
            calendar = json.loads(args.calendar.read_bytes())
            authority = "saved_broker_calendar"
        else:
            from backend.utils.market_hours import is_trading_day, market_close_time
            day = date.fromisoformat(args.date)
            if abs(day.year - now.year) > 5:
                raise ValueError("local_calendar_out_of_range")
            calendar = ([{"date": args.date, "open": "09:30", "close": market_close_time(day).strftime("%H:%M")}] if is_trading_day(day) else [])
            authority = "local_calendar_diagnostic_only"
        session = calendar_session(args.date, calendar, now)
        if session["state"] != "CLOSED" and not args.force:
            print(json.dumps({"status": session["state"], "session": session}))
            return 3
        logs = {p.name: p.read_bytes() for p in sorted((args.root / "logs").glob("application.log*")) if p.is_file()}
        brain = args.root / "organism_brain"
        diagnostic = session_diagnostics(args.date, session,
            (brain / "strategy_evidence_events.jsonl").read_bytes(),
            (brain / "trade_history.csv").read_bytes(), logs, naive_timezone=args.log_timezone)
        diagnostic.update(calendar_authority=authority, forced=args.force,
                          completed_session_evidence=False)
        print(json.dumps(diagnostic, indent=2))
        return 0 if diagnostic["coverage"] == "OBSERVED_TICK_COVERAGE" and not args.force else 1
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "BLOCKED", "reason": "missing_or_invalid_session_input"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
