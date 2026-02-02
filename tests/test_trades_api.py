"""Test trades API endpoint

NOTE: This is an INTEGRATION test that requires a running backend server
and manual token input, so it's always skipped in automated runs.
"""
import pytest
import asyncio
import httpx

# Mark all tests in this module as requiring manual interaction
pytestmark = pytest.mark.skipif(
    True,  # Always skip - requires manual token input
    reason="Trades API integration test requires manual token input. Run directly with 'python -m pytest tests/test_trades_api.py -s'."
)

async def test_trades():
    # Get auth token - you'll need to replace with your actual token
    token = input("Enter your auth token (from browser localStorage or login): ")
    
    headers = {"Authorization": f"Bearer {token}"}
    base_url = "http://localhost:8000"
    
    print(f'\n=== Testing Trades API ===\n')
    
    # Test trade history endpoint
    print('1. Testing GET /api/v1/trades/history')
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/api/v1/trades/history",
                headers=headers,
                params={"limit": 10}
            )
            print(f'   Status: {response.status_code}')
            if response.status_code == 200:
                data = response.json()
                print(f'   Total trades: {data.get("total", 0)}')
                print(f'   Trades returned: {len(data.get("trades", []))}')
                if data.get("trades"):
                    print('\n   First trade:')
                    trade = data["trades"][0]
                    print(f'   - Order ID: {trade.get("order_id")}')
                    print(f'   - Symbol: {trade.get("symbol")}')
                    print(f'   - Side: {trade.get("side")}')
                    print(f'   - Qty: {trade.get("filled_qty")}')
                    print(f'   - Status: {trade.get("status")}')
                else:
                    print('   NO TRADES FOUND!')
            else:
                print(f'   Error: {response.text}')
    except Exception as e:
        print(f'   Exception: {e}')
    
    # Test analytics endpoint
    print('\n2. Testing GET /api/v1/trades/analytics')
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/api/v1/trades/analytics",
                headers=headers
            )
            print(f'   Status: {response.status_code}')
            if response.status_code == 200:
                data = response.json()
                print(f'   Total trades: {data.get("total_trades", 0)}')
                print(f'   Total volume: {data.get("total_volume", 0)}')
                print(f'   Total P&L: {data.get("total_realized_pnl", 0)}')
            else:
                print(f'   Error: {response.text}')
    except Exception as e:
        print(f'   Exception: {e}')

if __name__ == '__main__':
    asyncio.run(test_trades())
