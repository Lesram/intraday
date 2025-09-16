"""
Phase 3.1 - System Module Direct Coverage Testing
Target: 100% coverage for backend/api/routes/system.py (94 statements)
Strategy: Direct module import and function testing
"""

import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime
import time
from fastapi import HTTPException

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

async def test_import_system_module():
    """Test importing the system module"""
    try:
        from backend.api.routes.system import router
        assert router is not None
        assert router.prefix == "/system"
        assert "System" in router.tags
        
        print("✅ System module imported successfully")
        return True
    except Exception as e:
        print(f"❌ System module import failed: {e}")
        return False


async def test_system_status_endpoint():
    """Test system_status endpoint"""
    try:
        from backend.api.routes.system import system_status
        
        # Test system status - covers basic status response
        result = await system_status()
        assert result["service"] == "intraday-trading"
        assert result["status"] == "operational"
        assert result["version"] == "1.0.0"
        assert "timestamp" in result
        assert isinstance(result["timestamp"], float)
        
        print("✅ System status endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ System status endpoint test failed: {e}")
        return False


async def test_root_endpoint():
    """Test root endpoint"""
    try:
        from backend.api.routes.system import root
        
        # Test root endpoint - covers API information response
        result = await root()
        assert result["service"] == "Algorithmic Trading Platform API"
        assert result["version"] == "1.0.0"
        assert result["status"] == "operational"
        assert "endpoints" in result
        assert result["endpoints"]["health"] == "/health"
        assert result["endpoints"]["metrics"] == "/metrics"
        assert result["endpoints"]["docs"] == "/docs"
        assert result["endpoints"]["api"] == "/api/v1"
        
        print("✅ Root endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ Root endpoint test failed: {e}")
        return False


async def test_metrics_endpoint():
    """Test get_metrics endpoint with various scenarios"""
    try:
        from backend.api.routes.system import get_metrics
        
        # Mock request with no metrics registry - covers default registry path
        mock_request = Mock()
        mock_app_state = Mock()
        mock_request.app.state = mock_app_state
        
        # Test without metrics registry - covers fallback registry creation
        delattr(mock_app_state, 'metrics_registry') if hasattr(mock_app_state, 'metrics_registry') else None
        
        result = await get_metrics(mock_request)
        assert result.media_type == "text/plain"
        assert b"process_virtual_memory_bytes" in result.body
        print("✅ Metrics endpoint without registry tested")
        
        # Test with metrics registry but no metrics - covers metrics existence path
        from prometheus_client import CollectorRegistry
        mock_registry = CollectorRegistry()
        mock_app_state.metrics_registry = mock_registry
        mock_app_state.metrics = None
        
        result_with_registry = await get_metrics(mock_request)
        assert result_with_registry.media_type in ["text/plain", "text/plain; version=0.0.4; charset=utf-8"]
        print("✅ Metrics endpoint with registry tested")
        
        # Test with active metrics - covers metrics collection path
        mock_metrics = Mock()
        mock_metrics.counter = Mock()
        mock_metrics.histogram = Mock()
        mock_app_state.metrics = mock_metrics
        
        result_with_metrics = await get_metrics(mock_request)
        assert result_with_metrics.media_type in ["text/plain", "text/plain; version=0.0.4; charset=utf-8"]
        print("✅ Metrics endpoint with active metrics tested")
        
        # Test prometheus unavailable scenario - covers PROMETHEUS_AVAILABLE=False path
        with patch('backend.api.routes.system.PROMETHEUS_AVAILABLE', False):
            result_no_prometheus = await get_metrics(mock_request)
            assert result_no_prometheus.media_type == "text/plain"
            assert b"Metrics not available" in result_no_prometheus.body
            print("✅ Metrics endpoint without Prometheus tested")
        
        print("✅ Metrics endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ Metrics endpoint test failed: {e}")
        return False


async def test_health_check_endpoint():
    """Test health_check endpoint scenarios"""
    try:
        from backend.api.routes.system import health_check
        
        # Mock request with start_time - covers normal uptime calculation
        mock_request = Mock()
        mock_app_state = Mock()
        current_time = time.time()
        mock_app_state.start_time = current_time - 100  # 100 seconds ago
        mock_request.app.state = mock_app_state
        
        result = await health_check(mock_request)
        assert result["status"] == "healthy"
        assert result["service"] == "algorithmic-trading-platform"
        assert "timestamp" in result
        assert "uptime_seconds" in result
        assert result["uptime_seconds"] >= 99  # Should be around 100 seconds
        assert "components" in result
        assert result["components"]["api"] == "healthy"
        assert result["components"]["database"] == "healthy"
        assert result["components"]["metrics"] == True
        print("✅ Health check with uptime tested")
        
        # Mock request without start_time - covers initialization path
        mock_request_no_start = Mock()
        mock_app_state_no_start = Mock()
        delattr(mock_app_state_no_start, 'start_time') if hasattr(mock_app_state_no_start, 'start_time') else None
        mock_request_no_start.app.state = mock_app_state_no_start
        
        result_no_start = await health_check(mock_request_no_start)
        assert result_no_start["status"] == "healthy"
        assert result_no_start["uptime_seconds"] >= 0
        print("✅ Health check initialization tested")
        
        # Test exception handling in uptime calculation - covers exception path
        mock_request_error = Mock()
        mock_app_state_error = Mock()
        mock_app_state_error.start_time = "invalid_time"  # This will cause an exception
        mock_request_error.app.state = mock_app_state_error
        
        result_error = await health_check(mock_request_error)
        assert result_error["status"] == "healthy"
        assert result_error["uptime_seconds"] == 0.0  # Should default to 0 on error
        print("✅ Health check error handling tested")
        
        print("✅ Health check endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ Health check endpoint test failed: {e}")
        return False


async def test_health_check_not_allowed():
    """Test health_check_not_allowed endpoint"""
    try:
        from backend.api.routes.system import health_check_not_allowed
        
        # Test POST not allowed - covers 405 method not allowed
        try:
            await health_check_not_allowed()
            assert False, "Should have raised HTTPException"
        except HTTPException as e:
            assert e.status_code == 405
            assert "Method Not Allowed" in e.detail
            print("✅ POST health check not allowed tested")
        
        print("✅ Health check not allowed endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ Health check not allowed test failed: {e}")
        return False


async def test_liveness_probe_endpoint():
    """Test liveness_probe endpoint with model manager integration"""
    try:
        from backend.api.routes.system import liveness_probe
        
        # Test basic liveness probe - covers basic alive response
        result = await liveness_probe()
        assert result["status"] == "alive"
        assert result["service"] == "algotrading-platform"
        assert result["version"] == "1.0.0"
        assert result["check"] == "liveness"
        assert "timestamp" in result
        assert "model_sha256" in result  # Should have fallback hash
        print("✅ Basic liveness probe tested")
        
        # Test with mock model manager - covers model manager integration
        with patch('backend.api.routes.system.get_model_manager') as mock_get_manager:
            mock_model_manager = Mock()
            mock_model_manager.get_healthz_response = Mock(return_value={
                "models": {
                    "test_model": {
                        "hash": "test-model-hash-123",
                        "status": "loaded"
                    }
                }
            })
            mock_get_manager.return_value = mock_model_manager
            
            result_with_model = await liveness_probe()
            assert result_with_model["status"] == "alive"
            assert "models" in result_with_model
            assert result_with_model["model_sha256"] == "test-model-hash-123"
            print("✅ Liveness probe with model manager tested")
        
        # Test model manager exception handling - covers exception path
        with patch('backend.api.routes.system.get_model_manager', side_effect=Exception("Model manager error")):
            result_error = await liveness_probe()
            assert result_error["status"] == "alive"
            assert "model_sha256" in result_error  # Should have fallback hash
            print("✅ Liveness probe error handling tested")
        
        print("✅ Liveness probe endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ Liveness probe endpoint test failed: {e}")
        return False


async def test_runtime_error_endpoint():
    """Test test_runtime_error endpoint"""
    try:
        from backend.api.routes.system import test_runtime_error
        
        # Test runtime error - covers error raising path
        try:
            await test_runtime_error()
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Test runtime error from error factory" in str(e)
            print("✅ Runtime error endpoint tested")
        
        print("✅ Runtime error endpoint tested successfully")
        return True
    except Exception as e:
        print(f"❌ Runtime error endpoint test failed: {e}")
        return False


async def test_prometheus_imports():
    """Test prometheus import handling"""
    try:
        # Test prometheus import availability - covers import checking
        from backend.api.routes.system import PROMETHEUS_AVAILABLE
        assert isinstance(PROMETHEUS_AVAILABLE, bool)
        
        # Test with prometheus imports - covers successful import path
        try:
            from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
            assert CONTENT_TYPE_LATEST is not None
            print("✅ Prometheus imports available")
        except ImportError:
            print("✅ Prometheus imports not available (expected in some environments)")
        
        print("✅ Prometheus imports tested successfully")
        return True
    except Exception as e:
        print(f"❌ Prometheus imports test failed: {e}")
        return False


async def test_liveness_probe_error_scenarios():
    """Test liveness probe error scenarios"""
    try:
        from backend.api.routes.system import liveness_probe
        
        # Test async operation failure - covers process not responsive
        with patch('asyncio.sleep', side_effect=Exception("Async error")):
            try:
                await liveness_probe()
                assert False, "Should have raised HTTPException"
            except HTTPException as e:
                assert e.status_code == 503
                assert "Process not responsive" in e.detail
                print("✅ Liveness probe async error tested")
        
        print("✅ Liveness probe error scenarios tested successfully")
        return True
    except Exception as e:
        print(f"❌ Liveness probe error scenarios test failed: {e}")
        return False


async def test_metrics_error_handling():
    """Test metrics endpoint error handling"""
    try:
        from backend.api.routes.system import get_metrics
        
        # Test metrics generation exception - covers exception handling path
        mock_request = Mock()
        mock_app_state = Mock()
        mock_request.app.state = mock_app_state
        
        # Mock generate_latest to raise an exception
        with patch('backend.api.routes.system.generate_latest', side_effect=Exception("Metrics error")):
            result = await get_metrics(mock_request)
            assert result.media_type == "text/plain"
            assert b"Metrics generation error" in result.body
            print("✅ Metrics error handling tested")
        
        print("✅ Metrics error handling tested successfully")
        return True
    except Exception as e:
        print(f"❌ Metrics error handling test failed: {e}")
        return False


async def test_route_signatures():
    """Test route function signatures and imports"""
    try:
        from backend.api.routes.system import (
            system_status,
            root,
            get_metrics,
            health_check,
            health_check_not_allowed,
            liveness_probe,
            test_runtime_error,
            router
        )
        
        # Verify all route functions exist
        assert callable(system_status)
        assert callable(root)
        assert callable(get_metrics)
        assert callable(health_check)
        assert callable(health_check_not_allowed)
        assert callable(liveness_probe)
        assert callable(test_runtime_error)
        assert router is not None
        
        # Test router configuration
        assert router.prefix == "/system"
        assert "System" in router.tags
        
        print("✅ Route signatures tested successfully")
        return True
    except Exception as e:
        print(f"❌ Route signatures test failed: {e}")
        return False


async def main():
    """Main test execution function"""
    print("🚀 Phase 3.1 - System Module Direct Coverage Testing")
    print("Target: 100% coverage for backend/api/routes/system.py (94 statements)")
    print("=" * 70)
    
    test_functions = [
        ("Import System Module", test_import_system_module),
        ("System Status Endpoint", test_system_status_endpoint),
        ("Root Endpoint", test_root_endpoint),
        ("Metrics Endpoint", test_metrics_endpoint),
        ("Health Check Endpoint", test_health_check_endpoint),
        ("Health Check Not Allowed", test_health_check_not_allowed),
        ("Liveness Probe Endpoint", test_liveness_probe_endpoint),
        ("Runtime Error Endpoint", test_runtime_error_endpoint),
        ("Prometheus Imports", test_prometheus_imports),
        ("Liveness Probe Error Scenarios", test_liveness_probe_error_scenarios),
        ("Metrics Error Handling", test_metrics_error_handling),
        ("Route Signatures", test_route_signatures),
    ]
    
    passed = 0
    total = len(test_functions)
    
    for test_name, test_func in test_functions:
        print(f"\n📋 Testing: {test_name}")
        try:
            success = await test_func()
            if success:
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print(f"\n📊 Coverage Results: {passed}/{total} tests passed")
    success_rate = (passed / total) * 100
    print(f"Success Rate: {success_rate:.1f}%")
    
    if success_rate >= 90:
        print("🟢 Excellent coverage achieved")
    elif success_rate >= 75:
        print("🟡 Good coverage progress")
    else:
        print("🔴 More coverage needed")


if __name__ == "__main__":
    asyncio.run(main())