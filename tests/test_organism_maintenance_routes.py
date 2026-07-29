from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_close_shorts_defaults_to_dry_run(monkeypatch) -> None:
    from backend.organism import routes
    import backend.integrations.alpaca_broker as alpaca

    broker = SimpleNamespace(
        get_positions=AsyncMock(return_value=[{"symbol": "XYZ", "qty": "-3"}]),
        place_order=AsyncMock(),
    )
    monkeypatch.setattr(alpaca, "get_alpaca_broker_client", lambda: broker)
    monkeypatch.setenv("ORGANISM_LONG_ONLY", "true")

    result = await routes.close_legacy_shorts(
        request=SimpleNamespace(client=SimpleNamespace(host="test")),
        _admin=None,
    )

    assert result["dry_run"] is True
    assert result["closed"] == [
        {
            "symbol": "XYZ",
            "qty_to_cover": 3,
            "dry_run": True,
            "status": "preview",
        }
    ]
    broker.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_close_shorts_requires_confirmation_for_live_submit(monkeypatch) -> None:
    from backend.organism import routes

    monkeypatch.setenv("ORGANISM_LONG_ONLY", "true")

    with pytest.raises(HTTPException) as exc:
        await routes.close_legacy_shorts(
            request=SimpleNamespace(client=SimpleNamespace(host="test")),
            dry_run=False,
            _admin=None,
        )

    assert exc.value.status_code == 400
    assert "confirm=CLOSE_SHORTS" in exc.value.detail


@pytest.mark.asyncio
async def test_close_shorts_confirmed_live_submit_is_explicit(monkeypatch) -> None:
    from backend.organism import routes
    import backend.integrations.alpaca_broker as alpaca

    broker = SimpleNamespace(
        get_positions=AsyncMock(return_value=[{"symbol": "XYZ", "qty": "-3"}]),
        place_order=AsyncMock(return_value={"id": "broker-1", "status": "accepted"}),
    )
    monkeypatch.setattr(alpaca, "get_alpaca_broker_client", lambda: broker)
    monkeypatch.setenv("ORGANISM_LONG_ONLY", "true")

    result = await routes.close_legacy_shorts(
        request=SimpleNamespace(client=SimpleNamespace(host="test")),
        dry_run=False,
        confirm="CLOSE_SHORTS",
        _admin=None,
    )

    broker.place_order.assert_awaited_once_with(
        symbol="XYZ",
        side="buy",
        qty=3,
        type="market",
        tif="day",
    )
    assert result["dry_run"] is False
    assert result["closed"][0]["broker_order_id"] == "broker-1"
