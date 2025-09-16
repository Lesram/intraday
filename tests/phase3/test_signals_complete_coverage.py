#!/usr/bin/env python3
"""
Complete Signals.py Coverage Test - targeting 100% coverage
Focus on remaining missing lines: 169, 175, 183, 205-207, 311, 325
"""

import asyncio
import sys
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch
import pandas as pd

# Add the backend directory to Python path
backend_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
sys.path.insert(0, backend_path)

@pytest.mark.asyncio
async def test_strategy_manager_unavailable_line_169():
    """Test line 169: Strategy manager not available in get_trading_signal"""
    from backend.api.routes.signals import get_trading_signal
    from fastapi import HTTPException
    
    mock_user = {"user_id": "test"}
    
    # Pass None strategy manager to trigger line 169
    try:
        await get_trading_signal(
            symbol="AAPL",
            current_user=mock_user,
            strategy_manager=None,  # This triggers line 169
            alpaca_client=Mock(),
            feature_engineer=Mock()
        )
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 503
        assert "Strategy manager not available" in e.detail
        print("✅ Line 169: Strategy manager unavailable tested")

@pytest.mark.asyncio
async def test_alpaca_client_unavailable_line_175():
    """Test line 175: Alpaca client not available in get_trading_signal"""
    from backend.api.routes.signals import get_trading_signal
    from fastapi import HTTPException
    
    mock_user = {"user_id": "test"}
    
    # Pass None alpaca client to trigger line 175
    try:
        await get_trading_signal(
            symbol="AAPL",
            current_user=mock_user,
            strategy_manager=Mock(),
            alpaca_client=None,  # This triggers line 175
            feature_engineer=Mock()
        )
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 503
        assert "Market data client not available" in e.detail
        print("✅ Line 175: Alpaca client unavailable tested")

@pytest.mark.asyncio
async def test_empty_market_data_line_183():
    """Test line 183: Empty market data in get_trading_signal"""
    from backend.api.routes.signals import get_trading_signal
    from fastapi import HTTPException
    
    mock_user = {"user_id": "test"}
    
    # Mock alpaca client to return empty DataFrame
    mock_alpaca = Mock()
    mock_alpaca.get_historical_data = AsyncMock(return_value=pd.DataFrame())  # Empty DataFrame
    
    try:
        await get_trading_signal(
            symbol="AAPL",
            current_user=mock_user,
            strategy_manager=Mock(),
            alpaca_client=mock_alpaca,
            feature_engineer=Mock()
        )
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 404
        assert "No market data found" in e.detail
        print("✅ Line 183: Empty market data tested")

@pytest.mark.asyncio
async def test_http_exception_reraise_lines_205_207():
    """Test lines 205-207: HTTPException re-raising in get_trading_signal"""
    from backend.api.routes.signals import get_trading_signal
    from fastapi import HTTPException
    
    mock_user = {"user_id": "test"}
    
    # Mock strategy manager to raise HTTPException directly
    mock_strategy = Mock()
    mock_strategy.generate_combined_signal = AsyncMock(
        side_effect=HTTPException(status_code=422, detail="Validation error")
    )
    
    # Mock alpaca client with valid data
    mock_alpaca = Mock()
    mock_alpaca.get_historical_data = AsyncMock(return_value=pd.DataFrame({
        'open': [100], 'high': [105], 'low': [95], 'close': [102], 'volume': [1000]
    }))
    
    # Mock feature engineer
    mock_feature_engineer = Mock()
    mock_feature_engineer.compute_all_features = Mock(return_value={})
    
    try:
        await get_trading_signal(
            symbol="AAPL",
            current_user=mock_user,
            strategy_manager=mock_strategy,
            alpaca_client=mock_alpaca,
            feature_engineer=mock_feature_engineer
        )
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 422
        assert "Validation error" in e.detail
        print("✅ Lines 205-207: HTTPException re-raising tested")

@pytest.mark.asyncio
async def test_individual_symbol_processing_line_311():
    """Test line 311: Individual symbol processing error in get_advanced_signals"""
    from backend.api.routes.signals import get_advanced_signals
    
    mock_user = {"user_id": "test"}
    
    # Mock feature engineer
    mock_feature_engineer = Mock()
    mock_feature_engineer.compute_all_features = Mock(return_value={})
    
    # Mock strategy manager
    mock_strategy = Mock()
    mock_strategy.generate_combined_signal = AsyncMock(return_value={
        "signal": "buy", "confidence": 0.8
    })
    
    # Mock alpaca client that fails for one symbol 
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
        current_user=mock_user,
        strategy_manager=mock_strategy,
        alpaca_client=mock_alpaca,
        feature_engineer=mock_feature_engineer,
        risk_manager=Mock()
    )
    
    # Should have AAPL with signal and BADSTOCK with error
    assert "AAPL" in result.signals
    assert "BADSTOCK" in result.signals
    assert "error" in result.signals["BADSTOCK"]
    print("✅ Line 311: Individual symbol processing error tested")

@pytest.mark.asyncio
async def test_http_exception_reraise_line_325():
    """Test line 325: HTTPException re-raising in get_advanced_signals"""
    from backend.api.routes.signals import get_advanced_signals
    from fastapi import HTTPException
    
    mock_user = {"user_id": "test"}
    
    # Create a mock that raises HTTPException during symbols.split() operation
    # by making symbols not a string
    with patch('backend.api.routes.signals.datetime') as mock_datetime:
        mock_datetime.now.side_effect = HTTPException(status_code=418, detail="Time service error")
        
        try:
            await get_advanced_signals(
                symbols="AAPL",
                include_features=False,
                include_risk_metrics=False,
                current_user=mock_user,
                strategy_manager=Mock(),
                alpaca_client=Mock(),
                feature_engineer=Mock(),
                risk_manager=Mock()
            )
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            # Should re-raise the original HTTPException at line 325
            assert e.status_code == 418
            assert "Time service error" in e.detail
            print("✅ Line 325: HTTPException re-raising in get_advanced_signals tested")

async def main():
    """Run complete signals coverage tests"""
    print("🎯 Complete Signals.py Coverage Test - Targeting 100%")
    print("Missing lines: 169, 175, 183, 205-207, 311, 325")
    print("=" * 70)
    
    test_functions = [
        ("Strategy Manager Unavailable (169)", test_strategy_manager_unavailable_line_169),
        ("Alpaca Client Unavailable (175)", test_alpaca_client_unavailable_line_175),
        ("Empty Market Data (183)", test_empty_market_data_line_183),
        ("HTTPException Re-raise (205-207)", test_http_exception_reraise_lines_205_207),
        ("Individual Symbol Processing (311)", test_individual_symbol_processing_line_311),
        ("HTTPException Re-raise Advanced (325)", test_http_exception_reraise_line_325),
    ]
    
    passed = 0
    total = len(test_functions)
    
    for test_name, test_func in test_functions:
        print(f"\n📋 Testing: {test_name}")
        try:
            await test_func()
            passed += 1
            print(f"✅ {test_name} passed")
        except Exception as e:
            print(f"❌ {test_name} failed: {e}")
    
    print(f"\n📊 Complete Coverage Results: {passed}/{total} tests passed")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎯 Perfect! All missing lines covered!")
    else:
        print(f"🔶 {total - passed} tests still need work")
    
    return passed == total

if __name__ == "__main__":
    # Run the complete coverage tests
    result = asyncio.run(main())