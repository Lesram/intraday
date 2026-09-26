"""A failed dependency must never manufacture a healthy, flat account."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
import httpx
import pytest

from backend.api import portfolio as route
from backend.services import portfolio_service as service


@pytest.fixture
def portfolio(monkeypatch):
    cache = AsyncMock()
    cache.get.return_value = None
    monkeypatch.setattr(service, 'get_hot_data_cache', lambda: cache)
    obj = service.PortfolioService()
    obj._broker_client = AsyncMock()
    obj._broker_client.get_account.return_value = {'equity': '102000', 'last_equity': '100000', 'cash': '100000', 'buying_power': '200000'}
    obj._broker_client.get_positions.return_value = []
    obj._sync_service = AsyncMock()
    obj._sync_service.sync_full_portfolio.return_value = {'success': False}
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result

    @asynccontextmanager
    async def context():
        yield session

    monkeypatch.setattr(service, 'get_session_context', context)
    return obj, cache, session


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['broker', 'database', 'positions'])
async def test_dependency_failure_is_unavailable_not_synthetic_flat(portfolio, failure):
    obj, cache, session = portfolio
    error = RuntimeError('synthetic credential must not be returned')
    if failure == 'broker':
        obj._broker_client.get_account.side_effect = error
    elif failure == 'database':
        session.execute.side_effect = error
    else:
        obj._broker_client.get_positions.side_effect = error
    with pytest.raises(service.PortfolioUnavailableError, match='^Current portfolio unavailable$'):
        await obj.get_user_portfolio('synthetic-user')
    cache.set.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('account', [{}, {'equity': 'NaN', 'cash': '1', 'buying_power': '2'},
                                      {'equity': '1', 'cash': '2'},
                                      {'equity': '1', 'cash': '2', 'buying_power': 'Infinity'}])
async def test_missing_or_nonfinite_account_never_uses_demo_defaults(portfolio, account):
    obj, cache, _ = portfolio
    obj._broker_client.get_account.return_value = account
    with pytest.raises(service.PortfolioUnavailableError):
        await obj.get_user_portfolio('synthetic-user')
    cache.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_successful_flat_account_remains_available(portfolio):
    obj, cache, _ = portfolio
    result = await obj.get_user_portfolio('synthetic-user')
    assert result['totalEquity'] == 102000
    assert result['buyingPower'] == 200000
    assert result['positions'] == []
    assert result['lastUpdate']
    cache.set.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('unavailable', [True, False])
async def test_actual_portfolio_route_unavailability_and_recovery(monkeypatch, unavailable):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_authenticated_user] = lambda: SimpleNamespace(username='synthetic')
    monkeypatch.setattr(route, 'get_user_id', lambda _: 'synthetic')
    obj = SimpleNamespace(get_user_portfolio=AsyncMock())
    if unavailable:
        obj.get_user_portfolio.side_effect = service.PortfolioUnavailableError('synthetic credential')
    else:
        obj.get_user_portfolio.return_value = dict(totalEquity=102000, cash=100000, buyingPower=200000,
            totalPnL=0, dayPnL=0, positions=[], userId='synthetic', lastUpdate='2026-09-26T10:00:00+00:00')
    monkeypatch.setattr(route, 'get_portfolio_service', lambda: obj)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://synthetic') as client:
        response = await client.get('/portfolio/')
    assert response.status_code == (503 if unavailable else 200)
    if unavailable:
        assert response.json()['detail']['code'] == 'portfolio_unavailable'
        assert 'synthetic credential' not in response.text
        assert 'totalEquity' not in response.text and 'positions": []' not in response.text
    else:
        assert response.json()['totalEquity'] == 102000
        assert response.json()['positions'] == []

@pytest.mark.asyncio
@pytest.mark.parametrize('sync_failure', [False, True])
async def test_empty_local_inventory_cannot_hide_broker_position(portfolio, sync_failure):
    obj, cache, _ = portfolio
    obj._broker_client.get_positions.return_value = [{'symbol': 'AAPL', 'qty': '2'}]
    if sync_failure:
        obj._sync_service.sync_full_portfolio.side_effect = RuntimeError('private error')
    with pytest.raises(service.PortfolioUnavailableError):
        await obj.get_user_portfolio('synthetic-user')
    cache.set.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('broker_qty', ['3', 'NaN', '0'])
async def test_stale_local_quantity_cannot_be_published_as_current(portfolio, broker_qty):
    obj, cache, session = portfolio
    session.execute.return_value.scalars.return_value.all.return_value = [SimpleNamespace(symbol='AAPL', qty=2)]
    obj._broker_client.get_positions.return_value = [{'symbol': 'AAPL', 'qty': broker_qty}]
    with pytest.raises(service.PortfolioUnavailableError):
        await obj.get_user_portfolio('synthetic-user')
    cache.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_matching_position_uses_verified_broker_valuation(portfolio):
    from datetime import UTC, datetime
    obj, _, session = portfolio
    session.execute.return_value.scalars.return_value.all.return_value = [SimpleNamespace(symbol='AAPL', qty=2, avg_price=1, created_at=datetime.now(UTC))]
    session.execute.return_value.all.return_value = []
    obj._broker_client.get_positions.return_value = [{'symbol': 'AAPL', 'qty': '2', 'avg_entry_price': '100', 'current_price': '105', 'unrealized_pl': '10', 'unrealized_plpc': '.05', 'market_value': '210', 'side': 'long'}]
    result = await obj.get_user_portfolio('synthetic-user')
    assert result['positions'][0]['averagePrice'] == 100
    assert result['positions'][0]['quantity'] == 2
    assert result['positions'][0]['marketValue'] == 210

@pytest.mark.asyncio
@pytest.mark.parametrize('equity,last_equity,delta,pct', [
    ('102000', '100000', 2000, 2), ('98000', '100000', -2000, -2),
    ('100000', '100000', 0, 0), ('0', '0', 0, None), ('10', '0', 10, None),
])
async def test_day_metric_is_account_equity_change_with_explicit_zero_baseline(portfolio, equity, last_equity, delta, pct):
    obj, _, _ = portfolio
    obj._broker_client.get_account.return_value.update(equity=equity, last_equity=last_equity)
    result = await obj.get_user_portfolio('synthetic-user')
    assert result['dayPnL'] == delta and result['dayPnLPercent'] == pct


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [None, 'NaN', 'Infinity', '-1'])
async def test_missing_or_invalid_prior_equity_is_not_invented(portfolio, value):
    obj, cache, _ = portfolio
    if value is None:
        del obj._broker_client.get_account.return_value['last_equity']
    else:
        obj._broker_client.get_account.return_value['last_equity'] = value
    with pytest.raises(service.PortfolioUnavailableError):
        await obj.get_user_portfolio('synthetic-user')
    cache.set.assert_not_awaited()
