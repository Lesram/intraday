"""Observe entry provenance without deciding, modifying or retrying orders.

The receipt fingerprints the actual causal feature frame at the shared gate,
then joins it to the database/client order identities returned by submission.
Missing evidence is explicit; telemetry errors never turn an accepted order
into a caller-visible submission failure that could provoke another order.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
from datetime import UTC
from functools import wraps
from pathlib import Path

import pandas as pd

from backend.infra.runtime_identity import runtime_identity_snapshot

EVIDENCE_FILE = "entry_evidence.jsonl"
SCHEMA = "intra_entry_evidence_v1"
logger = logging.getLogger(__name__)


def _frame_receipt(engine, symbol, direction, frame):
    observed = engine._now_fn().astimezone(UTC)
    reasons = []
    times = (frame["timestamp"] if "timestamp" in frame.columns
             else pd.Series(frame.index) if isinstance(frame.index, pd.DatetimeIndex)
             else pd.Series([], dtype="object"))
    parsed = []
    for raw in times:
        try:
            ts = pd.Timestamp(raw)
            if pd.isna(ts) or ts.tzinfo is None:
                raise ValueError("missing_timezone")
            parsed.append(ts.tz_convert("UTC"))
        except (TypeError, ValueError):
            reasons.append("invalid_bar_timestamp")
    complete = bool(len(frame)) and len(parsed) == len(frame)
    ordered = bool(parsed) and all(a < b for a, b in zip(parsed, parsed[1:]))
    if not complete:
        reasons.append("incomplete_bar_timestamps")
    if not ordered:
        reasons.append("unordered_or_duplicate_bar_timestamps")
    latest = max(parsed) if parsed else None
    if latest is not None and latest > observed:
        reasons.append("future_bar")
    digest = hashlib.sha256()
    digest.update(json.dumps([(str(c), str(t)) for c, t in zip(frame.columns, frame.dtypes)]).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    identity = runtime_identity_snapshot()
    for field in ("git_sha", "image_sha", "runtime_config_hash"):
        if identity.get(field) in (None, "", "unknown"):
            reasons.append("missing_" + field)
    timeframe = getattr(engine, "_timeframe", None)
    if not isinstance(timeframe, str) or not timeframe:
        timeframe = None
        reasons.append("missing_timeframe")
    feed = os.environ.get("ALPACA_DATA_FEED", "")
    if not feed:
        reasons.append("missing_feed")
    return {"schema": SCHEMA, "symbol": symbol, "direction": float(direction),
            "tick": int(engine._tick_count), "captured_at": observed.isoformat(),
            **identity, "feed": feed, "timeframe": timeframe,
            "last_bar_at": latest.isoformat() if latest is not None else None,
            "frame_hash": digest.hexdigest(), "frame_rows": len(frame),
            "timestamp_complete": complete, "timestamp_ordered": ordered,
            "gate_passed": True, "method": "pandas_hash_v1",
            "pandas_version": pd.__version__, "reasons": sorted(set(reasons))}


def observe_gate(method):
    """Record only the passed shared-gate input; preserve its exact result."""
    signature = inspect.signature(method)

    @wraps(method)
    def observed(engine, *args, **kwargs):
        result = method(engine, *args, **kwargs)
        try:
            call = signature.bind(engine, *args, **kwargs)
            call.apply_defaults()
            fields = call.arguments
            tick = int(engine._tick_count)
            if getattr(engine, "_entry_evidence_tick", None) != tick:
                engine._entry_evidence_tick = tick
                engine._entry_evidence_frames = {}
            key = (fields["symbol"], float(fields["direction"]))
            engine._entry_evidence_frames.pop(key, None)
            if result[0]:
                frame = fields["features_by_symbol"].get(fields["symbol"])
                if isinstance(frame, pd.DataFrame):
                    engine._entry_evidence_frames[key] = _frame_receipt(engine, *key, frame)
        except Exception as exc:  # noqa: BLE001 -- observational telemetry must preserve the gate result
            logger.warning("Entry frame evidence unavailable (%s)", type(exc).__name__)
        return result
    return observed


def append_receipt(engine, receipt):
    path = Path(engine.brain.brain_dir) / EVIDENCE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    # One append syscall avoids interleaved JSON from concurrent submissions.
    payload = (json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        if os.write(fd, payload) != len(payload):
            raise OSError("short evidence append")
        os.fsync(fd)
    finally:
        os.close(fd)


def observe_submission(method):
    """Bind observed inputs to the returned order; never submit or retry itself."""
    signature = inspect.signature(method)

    @wraps(method)
    async def observed(engine, *args, **kwargs):
        receipt = None
        try:
            call = signature.bind(engine, *args, **kwargs)
            call.apply_defaults()
            fields = call.arguments
            key = (fields["symbol"], float(fields["direction"]))
            frames = getattr(engine, "_entry_evidence_frames", {})
            candidate = frames.get(key) if isinstance(frames, dict) else None
            if candidate and candidate["tick"] == int(engine._tick_count):
                receipt = {**candidate, "reasons": list(candidate["reasons"])}
            else:
                receipt = {"schema": SCHEMA, "symbol": fields["symbol"],
                           "direction": float(fields["direction"]),
                           "tick": int(engine._tick_count),
                           "reasons": ["no_matching_gate_receipt"]}
            submitted = engine._now_fn().astimezone(UTC)
            receipt.update(submitted_at=submitted.isoformat(), shares=int(fields["shares"]),
                           entry_source=fields["entry_source"], strategy_id=fields["strategy_id"])
            if receipt.get("last_bar_at"):
                receipt["bar_age_seconds"] = (submitted - pd.Timestamp(receipt["last_bar_at"])).total_seconds()
            # A reload/config change between gate and submission must not pass
            # as the same decision context.
            identity = runtime_identity_snapshot()
            if any(receipt.get(k) != identity.get(k) for k in ("git_sha", "image_sha", "runtime_config_hash")):
                receipt["reasons"].append("runtime_changed_since_gate")
        except Exception as exc:  # noqa: BLE001 -- missing telemetry must never prevent an otherwise valid submission
            logger.warning("Entry submission evidence unavailable (%s)", type(exc).__name__)
            receipt = None

        result = await method(engine, *args, **kwargs)
        try:
            if receipt is not None and isinstance(result, dict) and result.get("order_id"):
                receipt.update(entry_order_id=str(result["order_id"]),
                               client_order_id=str(result.get("idempotency_key") or ""),
                               broker_order_id=str(result.get("broker_order_id") or ""),
                               recorded_at=engine._now_fn().astimezone(UTC).isoformat())
                if not receipt["client_order_id"]:
                    receipt["reasons"].append("missing_client_order_id")
                receipt["status"] = "UNVERIFIED" if receipt["reasons"] else "OBSERVED"
                append_receipt(engine, receipt)
        except Exception as exc:  # noqa: BLE001 -- publication failure must never retry an accepted order
            logger.warning("Entry evidence publication failed (%s); order result preserved", type(exc).__name__)
        return result
    return observed
