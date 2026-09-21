"""Durable operator entry halt, independent of automatic risk recovery.

The configured authority lives outside the brain directory: a brain save or
backup recovery cannot clear it. This module never cancels orders or ticks.
A successful halt acknowledges a drained engine tick, not a flat portfolio or
cancellation of orders already accepted by the order service/broker.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "intra_operator_controls_v1"
STATE_ENV = "ORGANISM_OPERATOR_CONTROL_STATE"
DRAIN_TIMEOUT_SECONDS = 10.0


class OperatorControlError(RuntimeError):
    def __init__(self, result):
        self.result = result
        super().__init__(result.get("error", "Operator control incomplete"))


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read_record(path):
    record = json.loads(Path(path).read_text())
    if not isinstance(record, dict):
        raise ValueError("Invalid operator control record")
    payload = {k: v for k, v in record.items() if k != "checksum"}
    if (set(payload) != {"schema", "operator_halted", "reason", "changed_at"}
            or payload["schema"] != SCHEMA
            or type(payload["operator_halted"]) is not bool
            or not isinstance(payload["reason"], str)
            or not payload["reason"]
            or hashlib.sha256(_canonical(payload)).hexdigest() != record.get("checksum")):
        raise ValueError("Invalid operator control schema/checksum")
    changed = datetime.fromisoformat(payload["changed_at"])
    if changed.tzinfo is None:
        raise ValueError("Operator control timestamp requires timezone")
    return record


def write_record(path, *, operator_halted: bool, reason: str):
    """Atomically persist and read back a control record; never swallow errors."""
    path = Path(path)
    if not path.is_absolute() or type(operator_halted) is not bool or not reason:
        raise ValueError("Absolute control path, boolean halt and reason required")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA, "operator_halted": operator_halted,
               "reason": reason, "changed_at": datetime.now(UTC).isoformat()}
    record = {**payload, "checksum": hashlib.sha256(_canonical(payload)).hexdigest()}
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_canonical(record) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        if read_record(path) != record:
            raise OSError("Operator control readback mismatch")
    finally:
        Path(temporary).unlink(missing_ok=True)
    return record


def initialize_control_state(path, *, operator_halted: bool, reason: str):
    """Offline rollout utility; caller must verify prior state, never overwrite."""
    if Path(path).exists():
        raise FileExistsError("Operator control state already exists")
    return write_record(path, operator_halted=operator_halted, reason=reason)


def _configured_path(engine=None):
    raw = os.environ.get(STATE_ENV)
    if not raw:
        raise ValueError("Operator control state path is not configured")
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError("Operator control state path must be absolute")
    brain = getattr(engine, "brain", None)
    if brain is not None and path.resolve().is_relative_to(Path(brain.brain_dir).resolve()):
        raise ValueError("Operator control state must be outside the brain directory")
    return path


def restore_governance_controls(gov, *, engine=None):
    """Load independent authority for live and legacy controllers, read-only."""
    if not os.environ.get(STATE_ENV):
        gov._operator_control_state = {"configured": False, "persistence": "unconfigured"}
        return
    try:
        record = read_record(_configured_path(engine))
    except (OSError, ValueError, TypeError) as exc:
        gov._operator_halted = True
        gov._operator_control_fault = True
        gov._operator_control_state = {"configured": True, "persistence": "failed",
                                       "path": os.environ.get(STATE_ENV), "error": type(exc).__name__}
        return
    _apply_record([gov], record)


def restore_engine_controls(engine):
    """Revalidate outside-brain authority before legacy recovery can run."""
    restore_governance_controls(engine.governance, engine=engine)


def live_engine(app):
    return getattr(getattr(app.state, "organism_scheduler", None), "_engine", None)


def governance_targets(app):
    engine = live_engine(app)
    candidates = [getattr(engine, "governance", None),
                  getattr(app.state, "organism_governance", None),
                  getattr(getattr(app.state, "organism_runner", None), "governance", None)]
    targets = []
    for gov in candidates:
        if gov is not None and all(gov is not other for other in targets):
            targets.append(gov)
    return targets


def authoritative_governance(app):
    targets = governance_targets(app)
    return targets[0] if targets else None


def _apply_record(targets, record):
    for gov in targets:
        gov._operator_halted = record["operator_halted"]
        gov._operator_control_fault = False
        gov._operator_control_state = {"configured": True, "persistence": "verified",
                                       "path": os.environ.get(STATE_ENV), "checksum": record["checksum"],
                                       "changed_at": record["changed_at"], "reason": record["reason"]}


def _latch(targets, *, fault=False):
    for gov in targets:
        gov._operator_halted = True
        if fault:
            gov._operator_control_fault = True
            gov._operator_control_state = {"configured": bool(os.environ.get(STATE_ENV)),
                                           "path": os.environ.get(STATE_ENV), "persistence": "failed"}


def operation_lock(app):
    """Serialize operator commands and post-halt emergency cancellation receipts."""
    lock = getattr(app.state, "_operator_control_lock", None)
    if lock is None:
        lock = app.state._operator_control_lock = asyncio.Lock()
    return lock


def runtime_readiness(app):
    """Report actual scheduler lifecycle, never infer active exits from a latch."""
    scheduler = getattr(app.state, "organism_scheduler", None)
    engine = live_engine(app)
    initialized = getattr(engine, "_initialized", False) is True
    running = getattr(scheduler, "is_running", False) is True
    stop = getattr(scheduler, "_stop", None)
    stopping = isinstance(stop, asyncio.Event) and stop.is_set()
    ready = engine is not None and initialized and running and not stopping
    return {"engine_available": engine is not None, "engine_initialized": initialized,
            "scheduler_running": running, "scheduler_stopping": stopping,
            "runtime_ready": ready, "protective_exits_active": ready}


def control_status(app):
    gov = authoritative_governance(app)
    if gov is None:
        return {"available": False}
    return {"available": True, "operator_halted": gov._operator_halted,
            "halt_epoch": getattr(app.state, "_operator_halt_epoch", 0),
            "entries_halted": gov.is_trading_halted,
            "persistence": dict(gov._operator_control_state),
            "governance": gov.to_dict(), **runtime_readiness(app),
            "orders_cancelled": False, "portfolio_flattened": False}


async def _change_entries(app, *, halted):
    targets = governance_targets(app)
    if not targets:
        raise OperatorControlError({"error": "Organism governance unavailable", "available": False})
    engine = live_engine(app)
    epoch = getattr(app.state, "_operator_halt_epoch", 0)
    if halted:
        app.state._operator_halt_epoch = epoch + 1
        _latch(targets)
        # Durable halt precedes the first await, including a slow in-flight tick.
        try:
            record = write_record(_configured_path(engine), operator_halted=True, reason="operator_halt")
            _apply_record(targets, record)
        except (OSError, ValueError, TypeError) as exc:
            _latch(targets, fault=True)
            raise OperatorControlError({**control_status(app), "drained": False,
                                        "error": f"Halt persistence failed: {type(exc).__name__}"}) from exc
    try:
        async with operation_lock(app):
            tick_lock = getattr(engine, "_tick_lock", None)
            acquired = False
            try:
                if not runtime_readiness(app)["runtime_ready"]:
                    raise ValueError("Live engine protection unavailable")
                if engine is not None:
                    if tick_lock is None:
                        raise ValueError("Engine tick drain unavailable")
                    await asyncio.wait_for(tick_lock.acquire(), timeout=DRAIN_TIMEOUT_SECONDS)
                    acquired = True
                if not runtime_readiness(app)["runtime_ready"]:
                    raise ValueError("Live engine stopped during drain")
                if not halted:
                    # A halt received while this resume waited always wins.
                    if epoch != getattr(app.state, "_operator_halt_epoch", 0):
                        raise ValueError("Resume superseded by newer halt")
                    record = write_record(_configured_path(engine), operator_halted=False, reason="operator_resume")
                    _apply_record(targets, record)
                result = control_status(app)
                result.update(drained=True, status="halted" if halted else
                              "still_halted" if result["entries_halted"] else "resumed")
                return result
            finally:
                if acquired:
                    tick_lock.release()
    except (OSError, ValueError, TypeError, TimeoutError) as exc:
        _latch(targets, fault=True)
        # A failed resume never clears in-memory safety. Best effort durable
        # re-halt also covers an error after replacement/readback of its record.
        try:
            record = write_record(_configured_path(engine), operator_halted=True, reason="operator_control_failed")
            _apply_record(targets, record)
        except (OSError, ValueError, TypeError):
            pass
        raise OperatorControlError({**control_status(app), "drained": False,
                                    "error": f"Control incomplete: {type(exc).__name__}"}) from exc


async def halt_entries(app):
    """Persist an immediate entry halt, then acknowledge only after tick drain."""
    return await _change_entries(app, halted=True)


async def resume_entries(app):
    """Clear only the operator latch; preserve automatic/environment protections."""
    return await _change_entries(app, halted=False)
