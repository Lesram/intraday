"""Real scanner discovery feeds the gated engine; stale pools cannot persist."""
from __future__ import annotations

import json

import pytest

from tests.test_v13_w100_live_tick_coverage import _assert_real_ticks, _minute_bars, _replay


@pytest.mark.timeout(60)
@pytest.mark.asyncio
@pytest.mark.parametrize("discovery", ["most_actives", "mover"])
@pytest.mark.parametrize("next_scan", ["empty", "exception"])
async def test_scanner_discovery_admits_entry_and_invalidates_pool(
    monkeypatch, tmp_path, record_property, discovery, next_scan,
):
    from backend.organism.live_engine import OrganismLiveEngine, SCAN_INTERVAL_TICKS
    from backend.organism.market_scanner import MarketScanner

    bars = _minute_bars(symbols=("AAPL", "MSFT", "SPY", "QQQ"))
    base_universe = {"AAPL", "SPY", "QQQ"}
    replay, engines, feature_calls = _replay(
        monkeypatch, tmp_path, bars, universe=sorted(base_universe))
    scanner = MarketScanner()
    requests = []
    observations = []
    real_scan = scanner.scan
    scan_attempts = 0

    async def provider_response(url, params=None):
        # Mock only external I/O. The real discovery parsers, snapshot
        # qualification, tension scores, engine injection and gates all run.
        requests.append((scan_attempts, url.rsplit("/", 1)[-1]))
        if url.endswith("most-actives"):
            return {"most_actives": ([{"symbol": "MSFT", "volume": 8_000_000,
                                       "trade_count": 100_000}]
                                      if scan_attempts == 1 and discovery == "most_actives" else [])}
        if url.endswith("movers"):
            return {"gainers": ([{"symbol": "MSFT", "price": 102.0,
                                   "change": 3.0, "percent_change": 3.03}]
                                  if scan_attempts == 1 and discovery == "mover" else []),
                    "losers": []}
        assert url.endswith("snapshots") and params["symbols"] == "MSFT"
        return {"MSFT": {"dailyBar": {"o": 100., "h": 102.2, "l": 99.8,
                                      "c": 102., "v": 8_000_000},
                         "minuteBar": {"o": 101.5, "c": 102., "v": 50_000},
                         "prevDailyBar": {"c": 99., "h": 100., "l": 95., "v": 1_000_000}}}

    async def scan_then_invalidate():
        nonlocal scan_attempts
        scan_attempts += 1
        if scan_attempts > 1 and next_scan == "exception":
            raise RuntimeError("synthetic scanner boundary failure")
        return await real_scan()

    monkeypatch.setattr(scanner, "_request", provider_response)
    monkeypatch.setattr(scanner, "scan", scan_then_invalidate)
    real_tick = OrganismLiveEngine.live_tick

    async def observe_tick(engine):
        # Replay deliberately disables external discovery; attach this offline
        # scanner after its setup, without changing decisions or tick order.
        engine.market_scanner = scanner
        result = await real_tick(engine)
        observations.append({"tick": engine._tick_count,
                             "candidates": list(engine._scanner_candidates),
                             "universe": set(engine._universe),
                             "held": set(await engine._positions_service.get_all_positions())})
        return result

    monkeypatch.setattr(OrganismLiveEngine, "live_tick", observe_tick)
    try:
        result = await replay.run(max_ticks=2 * SCAN_INTERVAL_TICKS + 1)
    finally:
        await scanner.close()
    _assert_real_ticks(result, 2 * SCAN_INTERVAL_TICKS + 1)
    assert scan_attempts == 2
    discovered = observations[SCAN_INTERVAL_TICKS - 1]
    invalidated = observations[2 * SCAN_INTERVAL_TICKS - 1]
    assert discovered["candidates"] == ["MSFT"]
    assert "MSFT" in discovered["held"]
    assert invalidated["candidates"] == []
    assert invalidated["universe"] >= base_universe | {"MSFT"}
    assert "MSFT" in invalidated["held"]
    entries = [order for order in result.orders if order["side"] == "buy"]
    assert any(order["symbol"] == "MSFT" for order in entries)
    assert any(symbol == "MSFT" for symbol, _ in feature_calls)
    receipts = [json.loads(line) for line in (tmp_path / "brain/entry_evidence.jsonl").read_text().splitlines()]
    accepted = [row for row in receipts if row["symbol"] == "MSFT"]
    assert accepted and all(row["gate_passed"] and row["timeframe"] == "1Min"
                            and row["timestamp_complete"] and row["timestamp_ordered"]
                            and 0 <= row["bar_age_seconds"] <= 120 for row in accepted)
    assert engines[0]._ml_isolation_mode and engines[0]._fixed_risk_sizing_mode
    assert engines[0]._scanner_consecutive_failures == (next_scan == "exception")
    assert (1, "snapshots") in requests
    record_property("discovery", discovery)
    record_property("next_scan", next_scan)
    record_property("actual_entry_orders", len(entries))
    record_property("valid_admission_receipts", len(accepted))
