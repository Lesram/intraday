"""Final admission of entries using the shared gate's actual feature bar.

The provider timestamp is the bar START. There is no completion-time grace;
protective exits do not call this gate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

MAX_ENTRY_BAR_AGE_SECONDS = 120.0
ENTRY_TIMEFRAME = "1Min"


@dataclass(frozen=True)
class EntryAdmission:
    submitted_at: str
    age_seconds: float


class EntryFreshnessRejected(RuntimeError):
    """An ordinary entry skip, with bounded diagnostic fields only."""

    def __init__(self, reason: str, age_seconds: float | None = None):
        self.reason = reason
        self.age_seconds = age_seconds
        super().__init__(reason)


def _timestamp(value):
    if not isinstance(value, (str, datetime, pd.Timestamp)):
        raise ValueError("invalid_timestamp")
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError("invalid_timestamp")
    # Force a bounded, nanosecond-precise UTC representation before subtraction.
    return stamp.tz_convert("UTC").value


def require_fresh_entry(engine, symbol: str, direction: float) -> EntryAdmission:
    """Raise a normal skip unless this exact tick's feature receipt is fresh."""
    tick = getattr(engine, "_tick_count", None)
    frames = getattr(engine, "_entry_evidence_frames", None)
    if (type(tick) is not int or not isinstance(direction, (int, float))
            or isinstance(direction, bool) or not math.isfinite(direction)
            or direction == 0 or not isinstance(frames, dict)
            or getattr(engine, "_entry_evidence_tick", None) != tick):
        raise EntryFreshnessRejected("missing_matching_frame")
    receipt = frames.get((symbol, float(direction)))
    if (not isinstance(receipt, dict) or receipt.get("schema") != "intra_entry_evidence_v1"
            or receipt.get("symbol") != symbol or receipt.get("direction") != direction
            or type(receipt.get("tick")) is not int or receipt["tick"] != tick
            or receipt.get("gate_passed") is not True):
        raise EntryFreshnessRejected("missing_matching_frame")
    try:
        now = _timestamp(engine._now_fn())
        captured = _timestamp(receipt.get("captured_at"))
        bar = _timestamp(receipt.get("last_bar_at"))
    except (TypeError, ValueError, OverflowError, AttributeError):
        raise EntryFreshnessRejected("invalid_timestamp") from None
    elapsed_ns = now - bar
    age = elapsed_ns / 1_000_000_000
    if (getattr(engine, "_timeframe", None) != ENTRY_TIMEFRAME
            or receipt.get("timeframe") != ENTRY_TIMEFRAME):
        raise EntryFreshnessRejected("unsupported_timeframe", age)
    if (receipt.get("timestamp_complete") is not True
            or receipt.get("timestamp_ordered") is not True
            or type(receipt.get("frame_rows")) is not int or receipt["frame_rows"] < 1):
        raise EntryFreshnessRejected("invalid_frame_timestamps", age)
    # A frame that was future-dated when captured never becomes admissible
    # merely because processing/quote lookup took long enough to catch up.
    reasons = receipt.get("reasons")
    if not isinstance(reasons, list):
        raise EntryFreshnessRejected("invalid_frame_timestamps", age)
    if bar > captured or "future_bar" in reasons:
        raise EntryFreshnessRejected("future_bar_at_capture", age)
    if now < captured or elapsed_ns < 0:
        raise EntryFreshnessRejected("clock_before_capture", age)
    if elapsed_ns > int(MAX_ENTRY_BAR_AGE_SECONDS * 1_000_000_000):
        raise EntryFreshnessRejected("stale_bar", age)
    return EntryAdmission(pd.Timestamp(now, tz="UTC").isoformat(), age)
