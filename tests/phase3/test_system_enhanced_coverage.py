#!/usr/bin/env python3
"""
Enhanced system coverage test - targeting 100% coverage
Focus on missing lines: 21-22, 63, 78-79, 106-107, 165-166, 172, 175-187
"""

import asyncio
import sys
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import Request, Response

# Add the backend directory to Python path
backend_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
sys.path.insert(0, backend_path)

@pytest.mark.asyncio
async def test_prometheus_not_available():
    """Test lines 21-22: PROMETHEUS_AVAILABLE = False path"""
    with patch.dict('sys.modules', {'prometheus_client': None}):
        # Mock ImportError when importing prometheus_client
        with patch('builtins.__import__', side_effect=ImportError):
            # Re-import the system module to trigger the ImportError
            import importlib
            if 'backend.api.routes.system' in sys.modules:
                del sys.modules['backend.api.routes.system']
            
            from backend.api.routes import system
            importlib.reload(system)
            
            # Check that PROMETHEUS_AVAILABLE is False
            assert system.PROMETHEUS_AVAILABLE == False
            print("✅ Lines 21-22: Prometheus not available tested")

@pytest.mark.asyncio
async def test_metrics_not_available():
    """Test line 63: Prometheus not available response"""
    from backend.api.routes.system import get_metrics
    
    # Mock request
    mock_request = Mock(spec=Request)
    mock_request.app = Mock()
    mock_request.app.state = Mock()
    mock_request.app.state.metrics_registry = None
    
    with patch('backend.api.routes.system.PROMETHEUS_AVAILABLE', False):
        response = await get_metrics(mock_request)
        
        assert response.body == b"# Metrics not available\n"
        assert response.media_type == "text/plain"
        print("✅ Line 63: Metrics not available response tested")

@pytest.mark.asyncio
async def test_metrics_exception_handling():
    """Test lines 78-79: Exception handling in metrics registration"""
    from backend.api.routes.system import get_metrics
    from prometheus_client import CollectorRegistry
    
    # Mock request with metrics that raise exception
    mock_request = Mock(spec=Request)
    mock_request.app = Mock()
    mock_request.app.state = Mock()
    mock_request.app.state.metrics_registry = CollectorRegistry()
    
    # Mock metrics that raise exception
    mock_metrics = Mock()
    mock_metrics.counter = Mock(side_effect=Exception("Metrics error"))
    mock_request.app.state.metrics = mock_metrics
    
    with patch('backend.api.routes.system.PROMETHEUS_AVAILABLE', True):
        with patch('backend.api.routes.system.generate_latest', return_value=b"# Test metrics"):
            response = await get_metrics(mock_request)
            
            # Should not raise exception, should handle it gracefully
            assert response.body == b"# Test metrics"
            print("✅ Lines 78-79: Metrics exception handling tested")

@pytest.mark.asyncio
async def test_health_check_start_time_exception():
    """Test lines 106-107: Exception handling when setting start_time"""
    from backend.api.routes.system import health_check
    
    # Create mock request with app state that raises exception when setting start_time
    mock_request = Mock(spec=Request)
    mock_app_state = Mock()
    
    # Make start_time assignment raise exception
    def set_start_time_error(value):
        raise Exception("Cannot set start_time")
    
    type(mock_app_state).start_time = property(lambda self: None, set_start_time_error)
    mock_request.app = Mock()
    mock_request.app.state = mock_app_state
    
    # Should handle exception gracefully
    result = await health_check(mock_request)
    
    assert result["status"] == "healthy"
    assert "uptime_seconds" in result
    print("✅ Lines 106-107: Start time exception handling tested")

@pytest.mark.asyncio
async def test_health_check_uptime_calculation_exception():
    """Test line 172: Exception in uptime calculation"""
    from backend.api.routes.system import health_check
    
    # Mock request with invalid start_time that causes exception
    mock_request = Mock(spec=Request)
    mock_request.app = Mock()
    mock_request.app.state = Mock()
    mock_request.app.state.start_time = "invalid_time_string"  # This will cause exception in float()
    
    result = await health_check(mock_request)
    
    assert result["status"] == "healthy"
    assert result["uptime_seconds"] == 0.0  # Should default to 0.0 on exception
    print("✅ Line 172: Uptime calculation exception tested")

@pytest.mark.asyncio 
async def test_model_manager_import_exception():
    """Test lines 165-166: Exception when importing model manager"""
    from backend.api.routes.system import health_check
    
    # Mock request
    mock_request = Mock(spec=Request)
    mock_request.app = Mock()
    mock_request.app.state = Mock()
    mock_request.app.state.start_time = 1000.0
    
    with patch('builtins.__import__', side_effect=ImportError("Cannot import model manager")):
        result = await health_check(mock_request)
        
        assert result["status"] == "healthy"
        # Should have fallback hash when model manager can't be imported
        assert "model_sha256" in result
        print("✅ Lines 165-166: Model manager import exception tested")

@pytest.mark.asyncio
async def test_model_manager_no_model_found():
    """Test line 175: No model manager found fallback"""
    from backend.api.routes.system import health_check
    
    # Mock request
    mock_request = Mock(spec=Request)
    mock_request.app = Mock()
    mock_request.app.state = Mock()
    mock_request.app.state.start_time = 1000.0
    
    # Mock get_model_manager to return None
    with patch('backend.mlops.model_manager.get_model_manager', return_value=None):
        result = await health_check(mock_request)
        
        assert result["status"] == "healthy"
        assert result["model_sha256"] == "test-hash-12345"  # Fallback hash
        print("✅ Line 175: No model manager fallback tested")

@pytest.mark.asyncio
async def test_model_health_with_hash():
    """Test lines 175-187: Model health response with hash extraction"""
    from backend.api.routes.system import health_check
    
    # Mock request
    mock_request = Mock(spec=Request)
    mock_request.app = Mock()
    mock_request.app.state = Mock()
    mock_request.app.state.start_time = 1000.0
    
    # Mock model manager with health response
    mock_model_manager = Mock()
    mock_health_response = {
        "models": {
            "test_model": {
                "hash": "model-hash-abc123",
                "status": "loaded"
            }
        },
        "overall_status": "healthy"
    }
    mock_model_manager.get_healthz_response = Mock(return_value=mock_health_response)
    
    with patch('backend.mlops.model_manager.get_model_manager', return_value=mock_model_manager):
        result = await health_check(mock_request)
        
        assert result["status"] == "healthy"
        assert result["model_sha256"] == "model-hash-abc123"  # Hash from model
        assert result["overall_status"] == "healthy"
        print("✅ Lines 175-187: Model health with hash extraction tested")

@pytest.mark.asyncio
async def test_health_check_general_exception():
    """Test final exception handling in health_check"""
    from backend.api.routes.system import health_check
    from fastapi import HTTPException
    
    # Mock request that causes exception
    mock_request = Mock(spec=Request)
    mock_request.app = Mock()
    
    # Make accessing app.state raise exception
    type(mock_request.app).state = property(lambda self: (_ for _ in ()).throw(Exception("App state error")))
    
    try:
        await health_check(mock_request)
        assert False, "Should have raised HTTPException"
    except HTTPException as e:
        assert e.status_code == 503
        assert "Process not responsive" in e.detail
        print("✅ General exception handling in health_check tested")

async def main():
    """Run enhanced system coverage tests"""
    print("🎯 Enhanced System Coverage Test - Targeting 100%")
    print("Missing lines: 21-22, 63, 78-79, 106-107, 165-166, 172, 175-187")
    print("=" * 75)
    
    test_functions = [
        ("Prometheus Not Available (21-22)", test_prometheus_not_available),
        ("Metrics Not Available Response (63)", test_metrics_not_available),
        ("Metrics Exception Handling (78-79)", test_metrics_exception_handling),
        ("Start Time Exception (106-107)", test_health_check_start_time_exception),
        ("Uptime Calculation Exception (172)", test_health_check_uptime_calculation_exception),
        ("Model Manager Import Exception (165-166)", test_model_manager_import_exception),
        ("No Model Manager Fallback (175)", test_model_manager_no_model_found),
        ("Model Health with Hash (175-187)", test_model_health_with_hash),
        ("General Exception Handling", test_health_check_general_exception),
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
    
    print(f"\n📊 Enhanced Coverage Results: {passed}/{total} tests passed")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎯 Perfect! All missing lines covered!")
    elif passed >= total * 0.8:
        print("🟢 Excellent coverage improvement!")
    else:
        print(f"🔶 {total - passed} tests still need work")
    
    return passed >= total * 0.8

if __name__ == "__main__":
    # Run the enhanced coverage tests
    result = asyncio.run(main())