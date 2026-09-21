"""Receipts observe causal inputs and actual order IDs without changing orders."""
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.organism import entry_evidence as evidence


IDENTITY = {"git_sha": "source-a", "image_sha": "image-a", "runtime_config_hash": "config-a"}


class Engine:
    def __init__(self, path):
        self.brain = SimpleNamespace(brain_dir=path)
        self._tick_count = 42
        self._timeframe = "1Min"
        self.now = datetime(2026, 9, 21, 14, 31, 15, tzinfo=timezone.utc)
        self._now_fn = lambda: self.now
        self.gate_result = (True, "passed")
        self.result = {"order_id": "database-uuid", "idempotency_key": "actual-client-id"}
        self.calls = 0
        self.error = None

    @evidence.observe_gate
    def gate(self, symbol, direction, features_by_symbol):
        return self.gate_result

    @evidence.observe_submission
    async def submit(self, symbol, shares, direction=1, entry_source="alpha",
                     strategy_id="alpha_baseline"):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "runtime_identity_snapshot", lambda: dict(IDENTITY))
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    engine = Engine(tmp_path)
    frame = pd.DataFrame({"timestamp": pd.date_range("2026-09-21T14:29:00Z", periods=3, freq="min"),
                          "close": [99., 100., 101.]})
    return engine, frame


def receipts(engine):
    path = engine.brain.brain_dir / evidence.EVIDENCE_FILE
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.asyncio
async def test_exact_gate_frame_and_returned_client_identity(setup):
    engine, frame = setup
    original = frame.copy(deep=True)
    assert engine.gate("AAPL", 1, {"AAPL": frame}) is engine.gate_result
    assert await engine.submit("AAPL", 6) is engine.result
    assert engine.calls == 1
    record, = receipts(engine)
    assert record["status"] == "OBSERVED"
    assert record["entry_order_id"] == "database-uuid"
    assert record["client_order_id"] == "actual-client-id"
    assert record["broker_order_id"] == ""
    assert record["bar_age_seconds"] == 15
    assert record["frame_rows"] == 3
    assert record["frame_hash"] == evidence._frame_receipt(engine, "AAPL", 1, frame)["frame_hash"]
    assert all(record[key] == value for key, value in IDENTITY.items())
    pd.testing.assert_frame_equal(frame, original)
    changed = frame.copy()
    changed.loc[0, "close"] = 98.
    assert evidence._frame_receipt(engine, "AAPL", 1, changed)["frame_hash"] != record["frame_hash"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["new_tick", "wrong_direction", "rejected_gate", "no_gate"])
async def test_missing_matching_pass_is_never_verified(setup, fault):
    engine, frame = setup
    if fault != "no_gate":
        engine.gate("AAPL", 1, {"AAPL": frame})
    if fault == "new_tick":
        engine._tick_count += 1
    if fault == "rejected_gate":
        engine.gate_result = (False, "blocked")
        engine.gate("AAPL", 1, {"AAPL": frame})
    assert await engine.submit("AAPL", 6, direction=-1 if fault == "wrong_direction" else 1) is engine.result
    record, = receipts(engine)
    assert record["status"] == "UNVERIFIED"
    assert "no_matching_gate_receipt" in record["reasons"]
    assert engine.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing", "naive", "future", "duplicate", "reversed", "nat"])
async def test_bad_timestamps_remain_visible_and_unverified(setup, fault):
    engine, frame = setup
    if fault == "missing":
        frame = frame.drop(columns="timestamp")
    elif fault == "naive":
        frame["timestamp"] = frame.timestamp.dt.tz_localize(None)
    elif fault == "future":
        frame.loc[2, "timestamp"] = pd.Timestamp("2026-09-21T15:00:00Z")
    elif fault == "duplicate":
        frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    elif fault == "reversed":
        frame = frame.iloc[::-1]
    else:
        frame.loc[1, "timestamp"] = pd.NaT
    engine.gate("AAPL", 1, {"AAPL": frame})
    await engine.submit("AAPL", 6)
    record, = receipts(engine)
    assert record["status"] == "UNVERIFIED"
    assert record["reasons"]


@pytest.mark.asyncio
async def test_identity_change_or_absent_client_id_is_explicit(setup, monkeypatch):
    engine, frame = setup
    engine.gate("AAPL", 1, {"AAPL": frame})
    monkeypatch.setattr(evidence, "runtime_identity_snapshot", lambda: {**IDENTITY, "image_sha": "image-b"})
    engine.result = {"order_id": "database-uuid"}
    await engine.submit("AAPL", 6)
    record, = receipts(engine)
    assert record["status"] == "UNVERIFIED"
    assert set(record["reasons"]) == {"runtime_changed_since_gate", "missing_client_order_id"}


@pytest.mark.asyncio
async def test_publication_failure_preserves_success_and_never_retries(setup, monkeypatch):
    engine, frame = setup
    engine.gate("AAPL", 1, {"AAPL": frame})
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(evidence, "append_receipt", fail)
    assert await engine.submit("AAPL", 6) is engine.result
    assert engine.calls == 1
    assert not (engine.brain.brain_dir / evidence.EVIDENCE_FILE).exists()


@pytest.mark.asyncio
async def test_original_submission_error_propagates_once_without_receipt(setup):
    engine, frame = setup
    engine.gate("AAPL", 1, {"AAPL": frame})
    error = RuntimeError("submission failed")
    engine.error = error
    with pytest.raises(RuntimeError) as caught:
        await engine.submit("AAPL", 6)
    assert caught.value is error
    assert engine.calls == 1
    assert not (engine.brain.brain_dir / evidence.EVIDENCE_FILE).exists()


@pytest.mark.asyncio
async def test_datetime_index_and_explicit_broker_identity(setup):
    engine, frame = setup
    engine._timeframe = "5Min"
    engine.gate("AAPL", 1, {"AAPL": frame.set_index("timestamp")})
    engine.result["broker_order_id"] = "broker-uuid"
    await engine.submit("AAPL", 6)
    record, = receipts(engine)
    assert record["status"] == "OBSERVED"
    assert record["broker_order_id"] == "broker-uuid"
    assert record["timeframe"] == "5Min"
