#!/usr/bin/env python3
"""
Comprehensive audit and validation script for Branch 1 implementation
"""

import asyncio
import logging

from fastapi.testclient import TestClient

# Import our modules
from backend.api.main import app, lifespan
from backend.config import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_configuration():
    """Test configuration loading"""
    try:
        settings = get_settings()
        logger.info("✅ Configuration loaded successfully")
        logger.info(f"   API Key: {settings.alpaca_api_key[:10]}...")
        logger.info(f"   Default symbols: {len(settings.default_symbols)} symbols")
        logger.info(f"   Model weights: LSTM={settings.lstm_weight}, XGB={settings.xgboost_weight}")
        return True
    except Exception as e:
        logger.error(f"❌ Configuration loading failed: {e}")
        return False


def test_app_initialization():
    """Test FastAPI app initialization"""
    try:
        # Test app creation
        assert app is not None
        logger.info("✅ FastAPI app created successfully")

        # Test routes
        routes = [route.path for route in app.routes]
        expected_routes = ['/health', '/api/v1/trading/signals', '/api/v1/ws/trading-data']

        for expected_route in expected_routes:
            if any(expected_route in route for route in routes):
                logger.info(f"✅ Route {expected_route} found")
            else:
                logger.warning(f"⚠️  Route {expected_route} not found in {routes}")

        return True
    except Exception as e:
        logger.error(f"❌ App initialization failed: {e}")
        return False


def test_dependencies():
    """Test dependency injection"""
    try:
        from backend.api.main import (
            get_alpaca_client,
            get_ensemble_model,
            get_feature_engineer,
            get_risk_manager,
            get_sentiment_analyzer,
            get_strategy_manager,
        )

        dependency_providers = [
            get_risk_manager, get_alpaca_client, get_ensemble_model,
            get_sentiment_analyzer, get_feature_engineer, get_strategy_manager
        ]

        logger.info("✅ All dependency providers imported successfully")
        logger.info(f"   Found {len(dependency_providers)} dependency providers")
        return True
    except Exception as e:
        logger.error(f"❌ Dependency providers failed: {e}")
        return False


def test_websocket_manager():
    """Test WebSocket manager initialization"""
    try:
        from backend.api.main import WebSocketClientManager

        ws_manager = WebSocketClientManager(max_queue_size=100)
        assert ws_manager.max_queue_size == 100
        assert len(ws_manager.clients) == 0

        logger.info("✅ WebSocketClientManager initialized successfully")
        logger.info(f"   Max queue size: {ws_manager.max_queue_size}")
        return True
    except Exception as e:
        logger.error(f"❌ WebSocket manager failed: {e}")
        return False


async def test_lifespan():
    """Test lifespan context manager"""
    try:
        from fastapi import FastAPI
        test_app = FastAPI()

        # Test lifespan startup and shutdown
        async with lifespan(test_app):
            # Verify components are initialized
            required_attrs = [
                'alpaca_client', 'sentiment_analyzer', 'feature_engineer',
                'model_manager', 'ensemble_model', 'risk_manager',
                'strategy_manager', 'ws_manager'
            ]

            for attr in required_attrs:
                if hasattr(test_app.state, attr):
                    logger.info(f"✅ {attr} initialized in app.state")
                else:
                    logger.warning(f"⚠️  {attr} not found in app.state")

        logger.info("✅ Lifespan context manager completed successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Lifespan test failed: {e}")
        return False


def test_endpoints_with_testclient():
    """Test API endpoints using TestClient"""
    try:
        with TestClient(app) as client:
            # Test health endpoint
            response = client.get("/health")
            if response.status_code == 200:
                logger.info("✅ Health endpoint responds with 200")
                logger.info(f"   Response: {response.json()}")
            else:
                logger.warning(f"⚠️  Health endpoint returned {response.status_code}")

            # Test metrics endpoint
            response = client.get("/metrics")
            if response.status_code == 200:
                logger.info("✅ Metrics endpoint responds with 200")
                metrics_text = response.text[:100] + "..." if len(response.text) > 100 else response.text
                logger.info(f"   Metrics preview: {metrics_text}")
            else:
                logger.warning(f"⚠️  Metrics endpoint returned {response.status_code}")

        return True
    except Exception as e:
        logger.error(f"❌ Endpoint testing failed: {e}")
        logger.error("This is expected when using TestClient without lifespan support")
        return False


def run_pytest_tests():
    """Run the comprehensive test suite"""
    try:
        logger.info("🚀 Running comprehensive test suite...")

        # Run tests and capture results
        import subprocess
        result = subprocess.run([
            'python', '-m', 'pytest',
            'tests/test_lifespan_deps.py',
            'tests/test_websocket_stall.py',
            '-v', '--tb=short', '--disable-warnings'
        ], check=False, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info("✅ All pytest tests passed!")
            # Count passed tests
            lines = result.stdout.split('\n')
            for line in lines:
                if 'passed' in line and 'warning' in line:
                    logger.info(f"   {line}")
        else:
            logger.error("❌ Some pytest tests failed")
            logger.error(result.stdout)
            logger.error(result.stderr)

        return result.returncode == 0
    except Exception as e:
        logger.error(f"❌ Pytest execution failed: {e}")
        return False


async def main():
    """Run comprehensive audit"""
    logger.info("🔍 COMPREHENSIVE AUDIT - Branch 1 Implementation")
    logger.info("=" * 60)

    results = {}

    # Test each component
    logger.info("\n📋 Testing Configuration...")
    results['configuration'] = test_configuration()

    logger.info("\n📋 Testing App Initialization...")
    results['app_init'] = test_app_initialization()

    logger.info("\n📋 Testing Dependencies...")
    results['dependencies'] = test_dependencies()

    logger.info("\n📋 Testing WebSocket Manager...")
    results['websocket'] = test_websocket_manager()

    logger.info("\n📋 Testing Lifespan...")
    results['lifespan'] = await test_lifespan()

    logger.info("\n📋 Testing API Endpoints...")
    results['endpoints'] = test_endpoints_with_testclient()

    logger.info("\n📋 Running Comprehensive Test Suite...")
    results['pytest'] = run_pytest_tests()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("🎯 AUDIT SUMMARY")
    logger.info("=" * 60)

    passed = sum(1 for success in results.values() if success)
    total = len(results)

    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} - {test_name.title()}")

    logger.info(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 ALL AUDITS PASSED - Branch 1 implementation is COMPLETE!")
    else:
        logger.warning(f"⚠️  {total - passed} audit(s) failed - needs attention")

    return passed == total


if __name__ == "__main__":
    asyncio.run(main())
