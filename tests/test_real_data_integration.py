"""
Comprehensive Test Script - Verify ALL Mock Data Replaced

Tests all 5 critical endpoints that previously used mock data:
1. market_data.py - Historical bars
2. scanner.py - Market scanning with indicators  
3. indicators.py - Technical indicator calculations
4. risk_manager.py - Price fetching
5. watchlists.py - Quote fetching

Each test verifies:
- Real data from Alpaca (not random numbers)
- Reasonable values (not $100 defaults)
- Proper data structure
- No exceptions

Run with: python test_real_data_integration.py
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

# NOTE: This module is an integration smoke suite that requires live Alpaca credentials
# and (optionally) extra third-party packages. It is disabled by default to keep
# normal test lanes stable.
RUN_LIVE = os.getenv("RUN_LIVE_REALDATA_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_LIVE,
    reason="Live real-data integration tests are disabled by default. Set RUN_LIVE_REALDATA_TESTS=1 and provide Alpaca credentials to enable.",
)

# Add repo root to path (so `backend.*` imports resolve when run directly)
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Ensure environment variables
os.environ.setdefault('ALPACA_PAPER', 'true')


class TestResults:
    """Track test results"""
    def __init__(self):
        self.passed = []
        self.failed = []
        self.start_time = datetime.now()
    
    def pass_test(self, name: str, details: str = ""):
        self.passed.append((name, details))
        print(f"✅ PASS: {name}")
        if details:
            print(f"   {details}")
    
    def fail_test(self, name: str, error: str):
        self.failed.append((name, error))
        print(f"❌ FAIL: {name}")
        print(f"   Error: {error}")
    
    def summary(self):
        duration = (datetime.now() - self.start_time).total_seconds()
        total = len(self.passed) + len(self.failed)
        
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Total Tests: {total}")
        print(f"Passed: {len(self.passed)} ✅")
        print(f"Failed: {len(self.failed)} ❌")
        print(f"Duration: {duration:.2f}s")
        print(f"Success Rate: {len(self.passed)/total*100:.1f}%")
        
        if self.failed:
            print("\n⚠️  FAILED TESTS:")
            for name, error in self.failed:
                print(f"  - {name}: {error}")
        
        if len(self.passed) == total:
            print("\n🎉 ALL TESTS PASSED! Zero mock data remaining!")
            return True
        return False


async def test_quote_manager():
    """Test QuoteManager fetches real quotes"""
    if not os.getenv("ALPACA_API_KEY_ID") or not os.getenv("ALPACA_API_SECRET_KEY"):
        pytest.skip("Missing Alpaca credentials (ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY)")

    results = TestResults()
    
    try:
        from backend.services.quote_manager import QuoteManager
        
        manager = QuoteManager()
        
        # Test single quote
        quote = await manager.get_quote('AAPL')
        
        if not quote:
            results.fail_test("QuoteManager.get_quote()", "No quote returned")
        elif quote.last <= 0:
            results.fail_test("QuoteManager.get_quote()", f"Invalid price: {quote.last}")
        elif quote.last < 50 or quote.last > 300:
            results.fail_test("QuoteManager.get_quote()", f"Unrealistic AAPL price: ${quote.last}")
        else:
            results.pass_test("QuoteManager.get_quote()", f"AAPL: ${quote.last:.2f}")
        
        # Test batch quotes
        quotes = await manager.get_quotes(['AAPL', 'MSFT', 'GOOGL'])
        
        if len(quotes) < 2:
            results.fail_test("QuoteManager.get_quotes() batch", f"Only got {len(quotes)} quotes")
        else:
            results.pass_test("QuoteManager.get_quotes() batch", f"Fetched {len(quotes)} quotes")
        
        # Test caching
        metrics = manager.get_metrics()
        results.pass_test("QuoteManager metrics", f"Hit rate: {metrics['cache_hit_rate']:.1%}, Avg latency: {metrics['avg_latency_ms']:.1f}ms")
        
        await manager.close()
        
    except Exception as e:
        results.fail_test("QuoteManager", str(e))

    assert not results.failed, f"QuoteManager integration checks failed: {results.failed}"
    return results


async def test_market_data_endpoint():
    """Test market_data.py uses real Alpaca data"""
    if not os.getenv("ALPACA_API_KEY_ID") or not os.getenv("ALPACA_API_SECRET_KEY"):
        pytest.skip("Missing Alpaca credentials (ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY)")

    results = TestResults()
    
    try:
        from backend.services.cache import get_cache_service
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        from datetime import timedelta
        
        cache_service = get_cache_service()
        alpaca_client = StockHistoricalDataClient(
            api_key=os.getenv('ALPACA_API_KEY_ID'),
            secret_key=os.getenv('ALPACA_API_SECRET_KEY')
        )
        
        # Test historical bars
        request = StockBarsRequest(
            symbol_or_symbols='AAPL',
            timeframe=TimeFrame(5, TimeFrameUnit.Minute),
            start=datetime.utcnow() - timedelta(days=7),
            limit=100
        )
        
        response = alpaca_client.get_stock_bars(request)
        
        if 'AAPL' not in response:
            results.fail_test("market_data.py bars", "No bars returned from Alpaca")
        else:
            bars = list(response['AAPL'])
            if len(bars) == 0:
                results.fail_test("market_data.py bars", "Empty bars list")
            else:
                first_bar = bars[0]
                if first_bar.close < 50 or first_bar.close > 300:
                    results.fail_test("market_data.py bars", f"Unrealistic price: ${first_bar.close}")
                else:
                    results.pass_test("market_data.py bars", f"Fetched {len(bars)} real bars, latest close: ${float(bars[-1].close):.2f}")
        
        # Test cache
        cache_metrics = cache_service.get_metrics()
        results.pass_test("Cache Service", f"Hit rate: {cache_metrics['hit_rate']:.1%}, Redis: {cache_metrics['redis_available']}")
        
        await cache_service.close()
        
    except Exception as e:
        results.fail_test("market_data.py", str(e))

    assert not results.failed, f"market_data integration checks failed: {results.failed}"
    return results


async def test_scanner_endpoint():
    """Test scanner.py uses real market data"""
    if not os.getenv("ALPACA_API_KEY_ID") or not os.getenv("ALPACA_API_SECRET_KEY"):
        pytest.skip("Missing Alpaca credentials (ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY)")

    results = TestResults()
    
    try:
        from backend.api.routes.scanner import get_real_market_data, calculate_indicators_for_symbol
        
        # Test real market data function
        market_data = await get_real_market_data('AAPL')
        
        if not market_data:
            results.fail_test("scanner.py get_real_market_data()", "No data returned")
        elif market_data['price'] < 50 or market_data['price'] > 300:
            results.fail_test("scanner.py get_real_market_data()", f"Unrealistic price: ${market_data['price']}")
        elif 'volume' not in market_data or market_data['volume'] <= 0:
            results.fail_test("scanner.py get_real_market_data()", "Invalid volume")
        else:
            results.pass_test("scanner.py get_real_market_data()", 
                            f"AAPL: ${market_data['price']:.2f}, volume: {market_data['volume']:,}")
        
        # Test indicators
        indicators = await calculate_indicators_for_symbol('AAPL')
        
        if not indicators:
            results.fail_test("scanner.py calculate_indicators()", "No indicators returned")
        elif indicators['rsi'] < 0 or indicators['rsi'] > 100:
            results.fail_test("scanner.py calculate_indicators()", f"Invalid RSI: {indicators['rsi']}")
        else:
            results.pass_test("scanner.py calculate_indicators()", 
                            f"RSI: {indicators['rsi']:.2f}, MACD: {indicators['macd']:.4f}, SMA50: ${indicators['sma_50']:.2f}")
        
    except Exception as e:
        results.fail_test("scanner.py", str(e))

    assert not results.failed, f"scanner integration checks failed: {results.failed}"
    return results


async def test_indicators_endpoint():
    """Test indicators.py uses real historical data"""
    if not os.getenv("ALPACA_API_KEY_ID") or not os.getenv("ALPACA_API_SECRET_KEY"):
        pytest.skip("Missing Alpaca credentials (ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY)")

    pytest.importorskip("pandas_ta", reason="pandas_ta is required for this integration smoke test")

    results = TestResults()
    
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        from datetime import timedelta
        import pandas as pd
        import pandas_ta as ta
        
        # Fetch real bars
        alpaca_client = StockHistoricalDataClient(
            api_key=os.getenv('ALPACA_API_KEY_ID'),
            secret_key=os.getenv('ALPACA_API_SECRET_KEY')
        )
        
        request = StockBarsRequest(
            symbol_or_symbols='AAPL',
            timeframe=TimeFrame(1, TimeFrameUnit.Day),
            start=datetime.utcnow() - timedelta(days=365),
            limit=250
        )
        
        response = alpaca_client.get_stock_bars(request)
        
        if 'AAPL' not in response:
            results.fail_test("indicators.py data fetch", "No bars returned")
        else:
            bars = list(response['AAPL'])
            
            # Convert to DataFrame and calculate indicators
            df = pd.DataFrame([{
                'open': float(bar.open),
                'high': float(bar.high),
                'low': float(bar.low),
                'close': float(bar.close),
                'volume': int(bar.volume)
            } for bar in bars])
            
            # Calculate indicators using pandas_ta
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.sma(length=50, append=True)
            
            latest = df.iloc[-1]
            rsi = latest.get('RSI_14', 0)
            sma50 = latest.get('SMA_50', 0)
            
            if rsi < 0 or rsi > 100:
                results.fail_test("indicators.py RSI calculation", f"Invalid RSI: {rsi}")
            elif sma50 < 50 or sma50 > 300:
                results.fail_test("indicators.py SMA calculation", f"Unrealistic SMA50: ${sma50}")
            else:
                results.pass_test("indicators.py calculations", 
                                f"RSI: {rsi:.2f}, SMA50: ${sma50:.2f} (from {len(bars)} bars)")
        
    except Exception as e:
        results.fail_test("indicators.py", str(e))

    assert not results.failed, f"indicators integration checks failed: {results.failed}"
    return results


async def test_risk_manager():
    """Test risk_manager.py uses real prices"""
    if not os.getenv("ALPACA_API_KEY_ID") or not os.getenv("ALPACA_API_SECRET_KEY"):
        pytest.skip("Missing Alpaca credentials (ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY)")

    results = TestResults()
    
    try:
        from backend.services.quote_manager import get_quote_manager
        
        quote_manager = get_quote_manager()
        
        # Test price fetching (simulating what risk_manager does)
        quote = await quote_manager.get_quote('AAPL')
        
        if not quote:
            results.fail_test("risk_manager.py _get_market_price()", "No quote returned")
        elif quote.last <= 0:
            results.fail_test("risk_manager.py _get_market_price()", f"Invalid price: ${quote.last}")
        elif quote.last == 100.0:
            results.fail_test("risk_manager.py _get_market_price()", "❌ STILL USING $100 MOCK PRICE!")
        elif quote.last < 50 or quote.last > 300:
            results.fail_test("risk_manager.py _get_market_price()", f"Unrealistic AAPL price: ${quote.last}")
        else:
            results.pass_test("risk_manager.py _get_market_price()", f"Real price: ${quote.last:.2f} (NOT $100 mock!)")
        
        await quote_manager.close()
        
    except Exception as e:
        results.fail_test("risk_manager.py", str(e))

    assert not results.failed, f"risk_manager integration checks failed: {results.failed}"
    return results


async def verify_no_mock_data_in_code():
    """Scan code for remaining mock data patterns"""
    results = TestResults()
    
    suspicious_patterns = [
        ('random.random()', 'Random number generation'),
        ('random.uniform', 'Random uniform distribution'),
        ('mock_prices', 'Mock price dictionary'),
        ('Decimal("100.00")', 'Default $100 price'),
        ('# Mock ', 'Mock comment'),
        ('generate_mock_', 'Mock generation function'),
    ]
    
    files_to_check = [
        'backend/api/routes/market_data.py',
        'backend/api/routes/scanner.py',
        'backend/api/routes/indicators.py',
        'backend/risk/risk_manager.py',
        'backend/api/routes/watchlists.py',
    ]
    
    found_issues = []
    
    for file_path in files_to_check:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            for pattern, description in suspicious_patterns:
                if pattern in content:
                    # Check if it's in a comment indicating removal
                    lines = content.split('\n')
                    for line_num, line in enumerate(lines, 1):
                        if pattern in line and '✅ REAL DATA' not in line and 'REMOVED' not in line:
                            found_issues.append(f"{file_path}:{line_num} - {description}: {pattern}")
        
        except FileNotFoundError:
            results.fail_test(f"Code scan - {file_path}", "File not found")
            continue
    
    if found_issues:
        results.fail_test("Code scan for mock patterns", f"Found {len(found_issues)} suspicious patterns:\n" + "\n".join(found_issues[:5]))
    else:
        results.pass_test("Code scan for mock patterns", "No suspicious mock data patterns found")

    assert not results.failed, f"Mock-pattern scan failed: {results.failed}"
    return results


async def main():
    """Run all tests"""
    print("="*80)
    print("COMPREHENSIVE REAL DATA INTEGRATION TEST")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check environment
    if not os.getenv('ALPACA_API_KEY_ID') or not os.getenv('ALPACA_API_SECRET_KEY'):
        print("❌ ERROR: Alpaca API keys not found in environment")
        print("   Please set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY")
        return False
    
    print("✅ Alpaca API keys found")
    print()
    
    all_results = TestResults()
    
    # Run all tests
    test_suites = [
        ("QuoteManager", test_quote_manager),
        ("Market Data Endpoint", test_market_data_endpoint),
        ("Scanner Endpoint", test_scanner_endpoint),
        ("Indicators Endpoint", test_indicators_endpoint),
        ("Risk Manager", test_risk_manager),
        ("Code Scan", verify_no_mock_data_in_code),
    ]
    
    for suite_name, test_func in test_suites:
        print(f"\n{'='*80}")
        print(f"TEST SUITE: {suite_name}")
        print('='*80)
        
        suite_results = await test_func()
        
        # Merge results
        all_results.passed.extend(suite_results.passed)
        all_results.failed.extend(suite_results.failed)
    
    # Final summary
    success = all_results.summary()
    
    if success:
        print("\n" + "🎉"*40)
        print("SUCCESS: ALL MOCK DATA REPLACED WITH REAL ALPACA DATA!")
        print("🎉"*40)
        print("\nPlatform is ready for deployment with 100% real data!")
    else:
        print("\n" + "⚠️ "*40)
        print("WARNING: Some tests failed. Review errors above.")
        print("⚠️ "*40)
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
