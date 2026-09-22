#!/usr/bin/env python3
"""Read-only session diagnostics. Missing coverage is unknown, never zero proof."""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
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
SESSION_LOG_SCHEMA = "intra_session_log_v1"
MAX_CANONICAL_LOG_DEPTH = 32


def session_log_name(day: str) -> str:
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("invalid_session_log_date")
    return "logs/sessions/" + day + ".jsonl"


def session_log_paths(root: Path, day: str) -> list[Path]:
    """Require the unrotated canonical stream; never fall back to legacy logs."""
    expected = root / session_log_name(day)
    candidates = sorted(expected.parent.glob(expected.name + "*"))
    if not candidates:
        raise ValueError("canonical_session_log_missing")
    if candidates != [expected]:
        raise ValueError("canonical_session_log_rotated")
    return candidates


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(UTC)


def reject_log_constant(_value):
    raise ValueError("nonstandard_json_log_number")


def finite_log_number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite_json_log_number")
    return number


def unique_log_fields(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("duplicate_json_log_field")
        record[key] = value
    return record


def bounded_log_structure(value):
    """Decoder recursion limits differ by Python version; the contract does not."""
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, (dict, list)):
            if depth > MAX_CANONICAL_LOG_DEPTH:
                raise ValueError("excessive_json_log_depth")
            children = item.values() if isinstance(item, dict) else item
            pending.extend((child, depth + 1) for child in children)


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


def log_record(line: str, *, naive_timezone: str | None = None,
               contract: str | None = None) -> tuple[datetime, str]:
    """Accept structured UTC logs and explicitly zoned legacy text logs."""
    if line.lstrip().startswith("{"):
        options = ({"parse_constant": reject_log_constant, "parse_float": finite_log_number,
                    "object_pairs_hook": unique_log_fields} if contract is not None else {})
        try:
            row = json.loads(line, **options)
        except (RecursionError, OverflowError):
            raise ValueError("invalid_json_log_structure") from None
        if contract is not None:
            bounded_log_structure(row)
            if (contract != SESSION_LOG_SCHEMA or row.get("schema") != SESSION_LOG_SCHEMA
                    or not isinstance(row.get("message"), str)
                    or not isinstance(row.get("logger"), str) or not row["logger"]
                    or not row["timestamp"].endswith("Z")):
                raise ValueError("invalid_session_log_record")
        return timestamp(row["timestamp"]), str(row.get("message", ""))
    if contract is not None:
        raise ValueError("invalid_session_log_record")
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
                        logs: dict[str, bytes], *, naive_timezone: str | None = None,
                        log_contract: str | None = None) -> dict:
    counts = Counter(evidence_events=0, live_candidates=0, direction_zero=0,
                     scanner_empty=0, stale_bars=0, liquidity_blocks=0, orders=0,
                     ledger_closes=0, successful_ticks=0, tick_errors=0)
    regimes: Counter = Counter()
    malformed = Counter(events=0, logs=0, ledger=0)
    tick_times = []
    duplicate_log_records = 0
    seen_logs = set()
    log_contract_errors = []
    if log_contract is not None:
        if log_contract != SESSION_LOG_SCHEMA:
            log_contract_errors.append("unknown_session_log_contract")
        if sorted(logs) != [session_log_name(day)]:
            log_contract_errors.append("canonical_session_log_set_mismatch")
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
        if log_contract is not None and content and not content.endswith(b"\n"):
            malformed["logs"] += 1
        try:
            text = content.decode("utf-8", errors="strict" if log_contract is not None else "replace")
        except UnicodeError:
            malformed["logs"] += 1
            continue
        # JSON strings may legally contain U+0085/U+2028/U+2029; only physical
        # newline delimits canonical records. Preserve legacy replay behavior.
        for line in (text.split("\n") if log_contract is not None else text.splitlines()):
            if not line.strip():
                continue
            try:
                when, message = log_record(line, naive_timezone=naive_timezone, contract=log_contract)
                if log_contract is not None and when.date().isoformat() != day:
                    raise ValueError("wrong_utc_session_log_date")
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
                and not malformed["logs"] and not counts["tick_errors"] and not log_contract_errors else "UNVERIFIED")
    result = {"date": day, "counts": dict(counts), "regimes": dict(regimes),
            "malformed": dict(malformed), "log_files": sorted(logs),
            "duplicate_log_records": duplicate_log_records, "coverage": coverage,
            "max_successful_tick_gap_seconds": gap,
            "coverage_gap_budget_seconds": MAX_TICK_GAP_SECONDS,
            "limitations": ["Tick logs attest observations, not uninterrupted host availability or all trading paths.",
                            "Missing/unparseable logs make counters lower bounds, never complete zeros."]}
    if log_contract is not None:
        result.update(log_contract=log_contract, log_contract_errors=log_contract_errors,
                      legacy_logs="excluded_by_versioned_daily_stream; historical packs are unchanged")
    return result


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
        # Reuse the collector's no-follow, stable file capture without importing
        # platform services. This CLI remains diagnostic-only.
        from scripts.ops.paper_daily_evidence import stable_read
        paths = session_log_paths(args.root, args.date)
        logs = {str(p.relative_to(args.root)): stable_read(p) for p in paths}
        if paths != session_log_paths(args.root, args.date):
            raise ValueError("session_log_changed_during_capture")
        brain = args.root / "organism_brain"
        diagnostic = session_diagnostics(args.date, session,
            (brain / "strategy_evidence_events.jsonl").read_bytes(),
            (brain / "trade_history.csv").read_bytes(), logs, log_contract=SESSION_LOG_SCHEMA)
        diagnostic.update(calendar_authority=authority, forced=args.force,
                          completed_session_evidence=False)
        print(json.dumps(diagnostic, indent=2))
        return 0 if diagnostic["coverage"] == "OBSERVED_TICK_COVERAGE" and not args.force else 1
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "BLOCKED", "reason": "missing_or_invalid_session_input"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
