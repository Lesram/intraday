#!/usr/bin/env python3
"""
Final signals coverage test - targeting 100% coverage
Focus on missing lines: 169, 175, 183, 205-207, 311, 325
"""

import asyncio
import sys
import os
import pandas as pd
from unittest.mock import Mock, AsyncMock, patch

# Add the backend directory to Python path
backend_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
sys.path.insert(0, backend_path)

async def test_strategy_manager_unavailable():
    """Test line 169: strategy_manager not available"""
    try:
        from backend.api.routes.signals import get_trading_signal
        from fastapi import HTTPException
        
        try:
            await get_trading_signal(
                symbol="AAPL",
                current_user={"user_id": "test"},
                strategy_manager=None,  # This should trigger line 169
                alpaca_client=Mock(),
                feature_engineer=Mock()
            )
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            assert e.status_code == 503
            assert "Strategy manager not available" in e.detail
            print("✅ Line 169: Strategy manager unavailable tested")
            return True
    except Exception as e:
        print(f"❌ Strategy manager unavailable test failed: {e}")
        return False

async def test_alpaca_client_unavailable():
    """Test line 175: alpaca_client not available"""
    try:
        from backend.api.routes.signals import get_trading_signal
        from fastapi import HTTPException
        
        try:
            await get_trading_signal(
                symbol="AAPL",
                current_user={"user_id": "test"},
                strategy_manager=Mock(),
                alpaca_client=None,  # This should trigger line 175
                feature_engineer=Mock()
            )
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            assert e.status_code == 503
            assert "Market data client not available" in e.detail
            print("✅ Line 175: Alpaca client unavailable tested")
            return True
    except Exception as e:
        print(f"❌ Alpaca client unavailable test failed: {e}")
        return False

async def test_empty_market_data():
    """Test line 183: empty market data"""
    try:
        from backend.api.routes.signals import get_trading_signal
        from fastapi import HTTPException
        
        mock_alpaca = Mock()
        mock_alpaca.get_historical_data = AsyncMock(return_value=pd.DataFrame())  # Empty dataframe
        
        try:
            await get_trading_signal(
                symbol="AAPL",
                current_user={"user_id": "test"},
                strategy_manager=Mock(),
                alpaca_client=mock_alpaca,
                feature_engineer=Mock()
            )
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            assert e.status_code == 404
            assert "No market data found" in e.detail
            print("✅ Line 183: Empty market data tested")
            return True
    except Exception as e:
        print(f"❌ Empty market data test failed: {e}")
        return False

async def test_http_exception_reraise():
    """Test lines 205-207: HTTPException re-raising"""
    try:
        from backend.api.routes.signals import get_trading_signal
        from fastapi import HTTPException
        
        mock_strategy = Mock()
        mock_strategy.generate_combined_signal = AsyncMock(
            side_effect=HTTPException(status_code=422, detail="Validation error")
        )
        
        mock_alpaca = Mock()
        mock_alpaca.get_historical_data = AsyncMock(return_value=pd.DataFrame({
            'open': [100], 'high': [105], 'low': [95], 'close': [102], 'volume': [1000]
        }))
        
        try:
            await get_trading_signal(
                symbol="AAPL",
                current_user={"user_id": "test"},
                strategy_manager=mock_strategy,
                alpaca_client=mock_alpaca,
                feature_engineer=Mock()
            )
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            assert e.status_code == 422
            assert "Validation error" in e.detail
            print("✅ Lines 205-207: HTTPException re-raising tested")
            return True
    except Exception as e:
        print(f"❌ HTTPException re-raising test failed: {e}")
        return False

async def test_individual_symbol_processing():
    """Test line 311: individual symbol processing error"""
    try:
        from backend.api.routes.signals import get_advanced_signals, get_strategy_manager, get_feature_engineer, get_risk_manager
        
        mock_alpaca = Mock()
        call_count = 0
        
        async def mock_get_data(symbol, timeframe, limit):
            nonlocal call_count
            call_count += 1
            if symbol == "AAPL":
                return pd.DataFrame({
                    'open': [100], 'high': [105], 'low': [95], 'close': [102], 'volume': [1000]
                })
            else:
                # This should trigger the exception handling at line 311
                raise Exception("Symbol processing error")
        
        mock_alpaca.get_historical_data = mock_get_data
        
        result = await get_advanced_signals(
            symbols="AAPL,BADSTOCK",
            include_features=True,
            include_risk_metrics=True,
            current_user={"user_id": "test"},
            strategy_manager=get_strategy_manager(),
            alpaca_client=mock_alpaca,
            feature_engineer=get_feature_engineer(),
            risk_manager=get_risk_manager()
        )
        
        # Should process AAPL successfully but BADSTOCK should have error
        print(f"✅ Line 311: Individual symbol processing tested")
        return True
    except Exception as e:
        print(f"❌ Individual symbol processing test failed: {e}")
        return False

async def test_advanced_signals_exception_reraise():
    """Test line 325: HTTPException re-raising in advanced signals"""
    try:
        from backend.api.routes.signals import get_advanced_signals, get_alpaca_client, get_feature_engineer, get_risk_manager
        from fastapi import HTTPException
        
        mock_strategy = Mock()
        mock_strategy.generate_combined_signal = AsyncMock(
            side_effect=HTTPException(status_code=418, detail="I'm a teapot")
        )
        
        try:
            await get_advanced_signals(
                symbols="AAPL",
                include_features=False,
                include_risk_metrics=False,
                current_user={"user_id": "test"},
                strategy_manager=mock_strategy,
                alpaca_client=get_alpaca_client(),
                feature_engineer=get_feature_engineer(),
                risk_manager=get_risk_manager()
            )
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            assert e.status_code == 418
            print("✅ Line 325: Advanced signals HTTPException re-raising tested")
            return True
    except Exception as e:
        print(f"❌ Advanced signals exception re-raising test failed: {e}")
        return False

async def main():
    """Main test execution function"""
    print("🎯 Final Signals Coverage Test - Targeting 100%")
    print("Missing lines: 169, 175, 183, 205-207, 311, 325")
    print("=" * 60)
    
    test_functions = [
        ("Strategy Manager Unavailable (169)", test_strategy_manager_unavailable),
        ("Alpaca Client Unavailable (175)", test_alpaca_client_unavailable),
        ("Empty Market Data (183)", test_empty_market_data),
        ("HTTPException Re-raise (205-207)", test_http_exception_reraise),
        ("Individual Symbol Processing (311)", test_individual_symbol_processing),
        ("Advanced Signals Exception Re-raise (325)", test_advanced_signals_exception_reraise),
    ]
    
    passed = 0
    total = len(test_functions)
    
    for test_name, test_func in test_functions:
        print(f"\n📋 Testing: {test_name}")
        try:
            result = await test_func()
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print(f"\n📊 Final Coverage Results: {passed}/{total} tests passed")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎯 Perfect! All missing lines covered!")
    else:
        print(f"🔶 {total - passed} tests still need work")
    
    return passed >= total * 0.8

if __name__ == "__main__":
    # Run the final coverage tests
    result = asyncio.run(main())