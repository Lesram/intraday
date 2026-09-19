"""Atomic accounting projection for deferred broker-close reconciliation.

The legacy brain is several independently replaced files. This one checkpoint
is authoritative for close outcomes and their consumers, so a torn legacy save
cannot publish a trade without its learner/risk effects. No orders are sent.
"""
from __future__ import annotations

import copy
import asyncio
import concurrent.futures
import hashlib
import json
import os
import tempfile
from functools import wraps
from dataclasses import asdict
from pathlib import Path
from typing import Any

ACCOUNTING_POLICY = "exact_position_fills_or_pending_v1"
CHECKPOINT_FILE = "close_accounting.json"
CHECKPOINT_VERSION = 1


def serialized(method):
    """Serialize legacy saves with the no-await accounting commit."""
    @wraps(method)
    def invoke(engine, *args, **kwargs):
        with engine._accounting_lock:
            return method(engine, *args, **kwargs)
    return invoke


def save_serialized(method):
    """Publish on the owner loop; workers only write legacy mirrors afterward.

    The caller must not hold the accounting lock while waiting for the loop.
    No deferred immutable snapshot can overwrite a later close: capture and
    publication happen together in the callback, before any legacy I/O.
    """
    @wraps(method)
    def invoke(engine, *args, **kwargs):
        loop = getattr(engine, "_accounting_owner_loop", None)
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        def publish():
            with engine._accounting_lock:
                write(engine)

        if loop is not None and loop.is_running() and current_loop is not loop:
            completed = concurrent.futures.Future()
            def on_owner():
                if not completed.set_running_or_notify_cancel():
                    return
                try:
                    publish()
                    completed.set_result(None)
                except BaseException as exc:  # noqa: BLE001 - propagate callback termination to the waiting worker.
                    completed.set_exception(exc)
            loop.call_soon_threadsafe(on_owner)
            try:
                completed.result(timeout=10)
            except concurrent.futures.TimeoutError:
                completed.cancel()
                raise RuntimeError("Accounting owner loop unavailable; save not started") from None
        else:
            publish()
        with engine._accounting_lock:
            return method(engine, *args, **kwargs)
    return invoke

DAILY_FIELDS = (
    "_symbol_daily_pnl", "_symbol_consecutive_losses", "_symbol_wins_today",
    "_symbol_closed_today", "_symbol_stop_loss_times", "_symbol_exit_type",
    "_symbol_exit_tick", "_symbol_banned",
)
TRACKING_FIELDS = (
    "_entry_metadata", "_exit_levels", "_pyramid_positions",
    "_last_exit_reason", "_last_exit_fill_price", "_last_bar_times",
    "_ml_reversal_used",
)


def session_date(now: Any) -> str:
    from zoneinfo import ZoneInfo
    return now.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def capture(engine: Any) -> dict[str, Any]:
    """Snapshot every mutable close consumer, before an unawaited transaction."""
    return copy.deepcopy({
        "all_trades": engine._all_trades,
        "learner_history": engine.learner.trade_history,
        "learner_total": engine.learner.state.total_trades,
        "learner_pnl": engine.learner.state.cumulative_pnl,
        "kelly": engine.kelly_sizer.regime_stats_to_dict(),
        "calibration": engine.signal_gen.calibration_to_dict(),
        "symbol_counts": engine.evolved_params.symbol_trade_counts,
        "runtime_counts": engine._symbol_trade_counts_runtime,
        "daily": {name: getattr(engine, name) for name in DAILY_FIELDS},
        "session": engine._daily_loss_date or session_date(engine._now_fn()),
        "tracking": {name: getattr(engine, name) for name in TRACKING_FIELDS},
        "completed": getattr(engine, "_accounting_completed_entries", {}),
        "tick_count": engine._tick_count,
    })


def restore(engine: Any, state: dict[str, Any], *, startup: bool = False) -> None:
    """Rollback in memory, or override torn legacy projections on startup."""
    state = copy.deepcopy(state)
    engine._all_trades = state["all_trades"]
    engine.learner.trade_history = state["learner_history"]
    engine.learner.state.total_trades = state["learner_total"]
    engine.learner.state.cumulative_pnl = state["learner_pnl"]
    # Legacy load_regime_stats ignores {}, so explicitly restore an empty
    # preimage after a failed first consumer update as well.
    engine.kelly_sizer._regime_stats = {}
    engine.kelly_sizer.load_regime_stats(state["kelly"])
    engine.signal_gen.load_calibration(state["calibration"])
    engine.evolved_params.symbol_trade_counts = state["symbol_counts"]
    engine._symbol_trade_counts_runtime = state["runtime_counts"]
    engine._accounting_completed_entries = state["completed"]
    if startup:
        # Pending-close ticks and cooldowns share one monotonic coordinate.
        engine._tick_count = max(engine._tick_count, state["tick_count"])
    if not startup or state["session"] == session_date(engine._now_fn()):
        for name, value in state["daily"].items():
            setattr(engine, name, value)
        engine._daily_loss_date = state["session"]
    if not startup:
        for name, value in state["tracking"].items():
            setattr(engine, name, value)
        return

    # Normal brain metadata may be newer for still-open positions. Only the
    # pending/finalized close identities belong to this projection on startup.
    tracking = state["tracking"]
    for sym, meta in list(engine._entry_metadata.items()):
        if str(meta.get("entry_order_id", "")) in state["completed"]:
            for name in TRACKING_FIELDS:
                target = getattr(engine, name)
                target.discard(sym) if isinstance(target, set) else target.pop(sym, None)
        else:
            meta.pop("pending_close", None)
    for sym, meta in tracking["_entry_metadata"].items():
        identified_entry = bool(meta.get("entry_order_id")) and meta.get("entry_source") != "reconciliation_orphan"
        if not meta.get("pending_close") and not identified_entry:
            continue
        existing = engine._entry_metadata.get(sym)
        if (not meta.get("pending_close") and existing
                and existing.get("entry_order_id") != meta.get("entry_order_id")):
            continue  # A newer legacy entry is not this checkpoint's lifetime.
        for name in TRACKING_FIELDS:
            source, target = tracking[name], getattr(engine, name)
            if isinstance(source, set):
                if sym in source:
                    target.add(sym)
            elif sym in source:
                target[sym] = source[sym]


def _encode(state: dict[str, Any]) -> dict[str, Any]:
    state = copy.deepcopy(state)
    for name in ("all_trades", "learner_history"):
        state[name] = [asdict(trade) for trade in state[name]]
    tracking = state["tracking"]
    tracking["_exit_levels"] = {sym: asdict(level) for sym, level in tracking["_exit_levels"].items()}
    tracking["_pyramid_positions"] = {sym: pos.to_persistence() for sym, pos in tracking["_pyramid_positions"].items()}
    tracking["_ml_reversal_used"] = sorted(tracking["_ml_reversal_used"])
    state["daily"]["_symbol_banned"] = sorted(state["daily"]["_symbol_banned"])
    return state


def _decode(state: dict[str, Any]) -> dict[str, Any]:
    from backend.organism.adaptive_exits import ExitLevels
    from backend.organism.continuous_learner import TradeRecord
    from backend.organism.pyramider import PyramidPosition
    for name in ("all_trades", "learner_history"):
        state[name] = [TradeRecord(**trade) for trade in state[name]]
    tracking = state["tracking"]
    tracking["_exit_levels"] = {sym: ExitLevels(**level) for sym, level in tracking["_exit_levels"].items()}
    tracking["_pyramid_positions"] = {sym: PyramidPosition.from_persistence(pos) for sym, pos in tracking["_pyramid_positions"].items()}
    tracking["_ml_reversal_used"] = set(tracking["_ml_reversal_used"])
    state["daily"]["_symbol_banned"] = set(state["daily"]["_symbol_banned"])
    return state


def _bytes(value: Any) -> bytes:
    # Legacy histories can contain NaN. Preserve their values; this checkpoint
    # does not repair or silently rewrite historical evidence.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=lambda x: x.item()).encode()


def write(engine: Any) -> None:
    """Replace one fsynced checkpoint. A failed replace leaves the old truth."""
    payload = _encode(capture(engine))
    encoded = _bytes(payload)
    envelope = {"version": CHECKPOINT_VERSION, "policy": ACCOUNTING_POLICY,
                "sha256": hashlib.sha256(encoded).hexdigest(), "state": payload}
    root = Path(engine.brain.brain_dir)
    root.mkdir(parents=True, exist_ok=True)
    # Preserve the existing trained-state guard BEFORE authority publication.
    # A later legacy-save rejection cannot undo an already published reset.
    previous = read(root)
    if previous is not None:
        if payload["learner_total"] < previous["learner_total"]:
            raise ValueError("Accounting publication refused: learner trade count regressed")
        if (payload["learner_total"] == previous["learner_total"]
                and payload["learner_pnl"] != previous["learner_pnl"]):
            raise ValueError("Accounting publication refused: learner PnL changed without an outcome")
        if len(payload["all_trades"]) < len(previous["all_trades"]):
            raise ValueError("Accounting publication refused: historical ledger regressed")
        if not set(previous["completed"]).issubset(payload["completed"]):
            raise ValueError("Accounting publication refused: completed identities regressed")
    else:
        # Upgrade from a pre-checkpoint brain must not bypass its manifest guard.
        manifest = root / "manifest.json"
        if manifest.exists():
            legacy = json.loads(manifest.read_bytes())
            if int(legacy.get("total_trades", 0) or 0) > payload["learner_total"]:
                raise ValueError("Accounting publication refused: learner predates legacy manifest")
    fd, temporary = tempfile.mkstemp(prefix=".close_accounting-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_bytes(envelope))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / CHECKPOINT_FILE)
        # Publication has committed. A later directory-fsync error cannot be
        # treated as rollback: restart may already observe the new checkpoint.
        try:
            directory = os.open(root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read(root: Path) -> dict[str, Any] | None:
    path = root / CHECKPOINT_FILE
    if not path.exists():
        return None
    envelope = json.loads(path.read_bytes())
    if envelope.get("version") != CHECKPOINT_VERSION or envelope.get("policy") != ACCOUNTING_POLICY:
        raise ValueError("Unsupported close-accounting checkpoint")
    state = envelope["state"]
    if hashlib.sha256(_bytes(state)).hexdigest() != envelope.get("sha256"):
        raise ValueError("Close-accounting checkpoint checksum mismatch")
    return _decode(state)
