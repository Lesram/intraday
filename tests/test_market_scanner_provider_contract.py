"""Provider-shaped scanner discovery and snapshot qualification contracts."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest

from backend.organism.market_scanner import MarketScanner, ScannedStock
from backend.organism import market_scanner as module


def snapshot(price=100.4, volume=10_000_000):
    scale = price / 100.4
    return {
        "dailyBar": {"o": 100.0 * scale, "h": 100.5 * scale, "l": 99.8 * scale, "c": price, "v": volume},
        "minuteBar": {"o": 100.35, "h": 100.45, "l": 100.3, "c": 100.42, "v": 200_000},
        "prevDailyBar": {"o": 99.0, "h": 101.0, "l": 98.0, "c": 100.0, "v": 5_000_000},
    }


@pytest.fixture
def scanner():
    with patch("backend.organism.market_scanner.httpx.AsyncClient") as client:
        client.return_value = AsyncMock()
        yield MarketScanner()


def install_provider(scanner, *, actives=None, gainers=None, losers=None, snapshots=None):
    """Actual screener shapes: actives have no price; movers have no volume."""
    calls = []

    async def request(url, params=None):
        calls.append((url, dict(params or {})))
        if url.endswith("/most-actives"):
            return {"most_actives": deepcopy(actives or [])}
        if url.endswith("/movers"):
            return {"gainers": deepcopy(gainers or []), "losers": deepcopy(losers or [])}
        if url.endswith("/snapshots"):
            return deepcopy(snapshots or {})
        raise AssertionError("unexpected request")

    scanner._request = AsyncMock(side_effect=request)
    return calls


@pytest.mark.asyncio
async def test_real_provider_shapes_reach_one_snapshot_batch_and_return_candidates(scanner, monkeypatch):
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    calls = install_provider(
        scanner,
        actives=[{"symbol": "AAPL", "trade_count": 1000, "volume": 10_000_000},
                 {"symbol": "TQQQ", "trade_count": 1000, "volume": 10_000_000}],
        gainers=[{"symbol": "META", "price": 100.0, "change": 2.0, "percent_change": 2.04},
                 {"symbol": "AAPL", "price": 100.0, "change": 2.0, "percent_change": 2.04}],
        losers=[{"symbol": "AMD", "price": 100.0, "change": -2.0, "percent_change": -1.96}],
        snapshots={s: snapshot() for s in ("AAPL", "META", "AMD")},
    )
    assert await scanner.scan() == ["AAPL", "META", "AMD"]
    assert len(calls) == 4  # Three unchanged screener requests, one shared snapshot batch.
    assert calls[-1][1] == {"symbols": "AAPL,META,AMD", "feed": "iex"}
    assert [s.source for s in scanner.scanned_stocks] == ["most_actives", "movers_up", "movers_down"]
    assert all(s.price == 100.4 and s.volume == 10_000_000 for s in scanner.scanned_stocks)
    assert scanner.scanned_stocks[1].change_pct == 2.04
    assert scanner.candidates == ["AAPL", "META", "AMD"]


@pytest.mark.asyncio
async def test_failed_discovery_clears_old_candidates_and_details(scanner):
    scanner._cached_candidates = ["PREVIOUS"]
    scanner._cached_scanned = [ScannedStock("PREVIOUS", "most_actives", price=100, volume=10_000_000)]
    scanner._request = AsyncMock(return_value=None)
    assert await scanner.scan() == []
    assert scanner.candidates == []
    assert scanner.scanned_stocks == []


@pytest.mark.asyncio
async def test_partial_snapshot_response_keeps_only_complete_qualified_candidates(scanner):
    incomplete = snapshot()
    del incomplete["dailyBar"]["v"]
    install_provider(
        scanner,
        actives=[{"symbol": s, "trade_count": 100, "volume": 10_000_000}
                 for s in ("VALID", "MISSING", "INCOMPLETE")],
        snapshots={"VALID": snapshot(), "INCOMPLETE": incomplete},
    )
    assert await scanner.scan() == ["VALID"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,field", [("active", "price"), ("active", "volume"),
                                       ("mover", "price"), ("mover", "volume"),
                                       ("mover", "percent_change")])
@pytest.mark.parametrize("invalid", [None, True, "100", float("nan"), float("inf")])
async def test_malformed_supplied_field_is_not_treated_as_missing(scanner, kind, field, invalid):
    row = {"symbol": "BAD", "trade_count": 100, "volume": 10_000_000} if kind == "active" else {
        "symbol": "BAD", "price": 100.0, "change": 1.0, "percent_change": 1.0}
    row[field] = invalid
    calls = install_provider(scanner, actives=[row] if kind == "active" else [],
                             gainers=[row] if kind == "mover" else [], snapshots={"BAD": snapshot()})
    assert await scanner.scan() == []
    assert not any(url.endswith("/snapshots") for url, _ in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("section,field,invalid", [
    ("dailyBar", "c", None), ("dailyBar", "c", True), ("dailyBar", "c", "100.4"),
    ("dailyBar", "c", float("nan")), ("dailyBar", "h", float("inf")),
    ("dailyBar", "l", -1), ("dailyBar", "o", 0), ("dailyBar", "v", None),
    ("dailyBar", "v", -1), ("dailyBar", "v", 1_000_000.5), ("dailyBar", "v", float("inf")),
    ("minuteBar", "c", float("nan")), ("minuteBar", "v", True),
    ("prevDailyBar", "c", float("inf")), ("prevDailyBar", "v", "5000000"),
])
async def test_invalid_snapshot_cannot_qualify_even_with_valid_screener_fields(scanner, section, field, invalid):
    bad = snapshot()
    bad[section][field] = invalid
    install_provider(scanner, actives=[{"symbol": "BAD", "price": 100.4, "volume": 10_000_000}],
                     snapshots={"BAD": bad})
    assert scanner._score_tension(bad) == 0
    assert await scanner.scan() == []
    assert scanner.scanned_stocks == []


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["o", "h", "l", "c", "v"])
async def test_incomplete_daily_bar_is_not_reconstructed_from_screener_values(scanner, missing):
    bad = snapshot()
    del bad["dailyBar"][missing]
    install_provider(scanner, actives=[{"symbol": "BAD", "price": 100.4, "volume": 10_000_000}],
                     snapshots={"BAD": bad})
    assert await scanner.scan() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("price,volume,accepted", [
    (module.SCAN_MIN_PRICE, module.SCAN_MIN_VOLUME, True),
    (module.SCAN_MAX_PRICE, 10_000_000, True),
    (module.SCAN_MIN_PRICE - .01, 10_000_000, False),
    (module.SCAN_MAX_PRICE + .01, 10_000_000, False),
    (100.4, module.SCAN_MIN_VOLUME - 1, False),
])
async def test_snapshot_filters_keep_existing_inclusive_thresholds(scanner, price, volume, accepted):
    install_provider(scanner, actives=[{"symbol": "EDGE", "volume": 10_000_000}],
                     snapshots={"EDGE": snapshot(price, volume)})
    assert await scanner.scan() == (["EDGE"] if accepted else [])


@pytest.mark.asyncio
async def test_success_then_snapshot_failure_never_reuses_prior_candidates(scanner):
    install_provider(scanner, actives=[{"symbol": "AAPL", "volume": 10_000_000}],
                     snapshots={"AAPL": snapshot()})
    assert await scanner.scan() == ["AAPL"]
    # The screener can still succeed while enrichment fails.
    scanner._fetch_snapshots = AsyncMock(side_effect=TimeoutError("synthetic timeout"))
    assert await scanner.scan() == []
    assert scanner.candidates == scanner.scanned_stocks == []
    assert scanner.scan_count == 2


@pytest.mark.asyncio
async def test_snapshot_failure_and_empty_response_have_no_unvalidated_candidates(scanner):
    install_provider(scanner, actives=[{"symbol": "AAPL", "price": 100.4, "volume": 10_000_000}])
    assert await scanner.scan() == []
    assert scanner.candidates == scanner.scanned_stocks == []


@pytest.mark.asyncio
async def test_bad_discovery_rows_do_not_poison_other_candidates(scanner):
    install_provider(scanner, actives=[None, [], {"symbol": True}, {"symbol": " "},
                                      {"symbol": "BAD", "volume": float("nan")},
                                      {"symbol": "GOOD", "volume": 10_000_000}],
                     snapshots={"GOOD": snapshot()})
    assert await scanner.scan() == ["GOOD"]


@pytest.mark.asyncio
async def test_scoring_order_and_candidate_cap_are_preserved(scanner, monkeypatch):
    monkeypatch.setattr(module, "SCAN_MAX_CANDIDATES", 1)
    low = snapshot(volume=1_000_000)
    high = snapshot(volume=20_000_000)
    assert scanner._score_tension(high) > scanner._score_tension(low) >= module.SCAN_TENSION_THRESHOLD
    install_provider(scanner, actives=[{"symbol": s, "volume": 10_000_000} for s in ("LOW", "HIGH")],
                     snapshots={"LOW": low, "HIGH": high})
    assert await scanner.scan() == ["HIGH"]
    assert len(scanner.scanned_stocks) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_volume", [1_000_000.5, 10 ** 400, -1])
async def test_invalid_discovery_volume_is_not_rounded_or_repaired(scanner, invalid_volume):
    calls = install_provider(scanner, actives=[{"symbol": "BAD", "volume": invalid_volume}],
                             snapshots={"BAD": snapshot()})
    assert await scanner.scan() == []
    assert not any(url.endswith("/snapshots") for url, _ in calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [None, [], {"dailyBar": None}, {"dailyBar": []},
                                {**snapshot(), "minuteBar": None},
                                {**snapshot(), "prevDailyBar": []}])
async def test_malformed_snapshot_structure_fails_closed(scanner, bad):
    install_provider(scanner, actives=[{"symbol": "BAD", "volume": 10_000_000}],
                     snapshots={"BAD": bad})
    assert await scanner.scan() == []


@pytest.mark.asyncio
async def test_qualification_diagnostics_distinguish_missing_invalid_and_threshold_failures(scanner, caplog):
    import logging

    caplog.set_level(logging.INFO, logger=module.__name__)
    install_provider(scanner, actives=[{"symbol": s, "volume": 10_000_000}
                                      for s in ("VALID", "MISSING", "INVALID", "LOWVOL")],
                     snapshots={"VALID": snapshot(), "INVALID": {"dailyBar": {}},
                                "LOWVOL": snapshot(volume=1)})
    assert await scanner.scan() == ["VALID"]
    assert any("discovered=4 missing_snapshots=1 invalid_snapshots=1 "
               "price_volume_rejected=1 qualified=1 tension_rejected=0" in r.getMessage()
               for r in caplog.records)
