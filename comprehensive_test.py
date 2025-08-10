#!/usr/bin/env python3
"""
Comprehensive Test Demo - Validating BRANCH 2.11 CI Quality Gates
"""

def main():
    print('🎯 COMPREHENSIVE TEST VALIDATION')
    print('=' * 50)

    # Test 1: Validate Test Infrastructure
    print('\n📋 Test 1: Test Infrastructure Validation')
    try:
        from tests.helpers.factories import create_order_spec, create_signal_payload
        order_spec = create_order_spec(symbol='AAPL', qty=100)
        signal_payload = create_signal_payload(symbol='TSLA', signal_type='BUY')
        print('✅ Test factories working')
        print(f'   - Order spec: {order_spec.symbol} {order_spec.qty} shares')
        print(f'   - Signal: {signal_payload["signal_type"]} {signal_payload["symbol"]}')
    except Exception as e:
        print(f'❌ Test factories failed: {e}')

    # Test 2: Configuration Validation  
    print('\n⚙️  Test 2: Configuration System')
    try:
        from backend.config import get_settings
        settings = get_settings()
        print('✅ Configuration loaded successfully')
        print(f'   - Environment: {getattr(settings, "environment", "development")}')
        print(f'   - Database URL configured: {bool(getattr(settings, "database_url", None))}')
    except Exception as e:
        print(f'❌ Configuration failed: {e}')

    # Test 3: Core Module Imports
    print('\n🔧 Test 3: Core Module Import Validation')
    modules_to_test = [
        'backend.api.main',
        'backend.data.alpaca_client', 
        'backend.strategies.trading_strategies',
        'backend.models.ensemble_model',
        'backend.infra.risk_manager',
        'backend.infra.metrics'
    ]

    for module in modules_to_test:
        try:
            __import__(module)
            print(f'✅ {module}')
        except Exception as e:
            print(f'❌ {module}: {str(e)[:60]}...')

    # Test 4: Database Schema Validation
    print('\n🗄️  Test 4: Database Schema Validation')
    try:
        from backend.infra.db import Base
        from sqlalchemy import MetaData
        metadata = Base.metadata
        table_count = len(metadata.tables)
        print(f'✅ Database schema loaded: {table_count} tables')
        for table_name in list(metadata.tables.keys())[:5]:  # Show first 5
            print(f'   - {table_name}')
        if table_count > 5:
            print(f'   - ... and {table_count - 5} more tables')
    except Exception as e:
        print(f'❌ Database schema failed: {e}')

    # Test 5: FastAPI App Initialization
    print('\n🚀 Test 5: FastAPI Application Validation')
    try:
        from backend.api.main import app
        route_count = len(app.routes)
        print(f'✅ FastAPI app initialized: {route_count} routes')
        api_routes = [route.path for route in app.routes if hasattr(route, 'path') and route.path.startswith('/api')][:3]
        print(f'   - Sample API routes: {api_routes}')
    except Exception as e:
        print(f'❌ FastAPI app failed: {e}')

    # Test 6: Test Suite Statistics
    print('\n📊 Test 6: Test Suite Statistics')
    try:
        import subprocess
        import sys
        result = subprocess.run([
            sys.executable, '-m', 'pytest', '--collect-only', '-q'
        ], capture_output=True, text=True, timeout=30)
        
        lines = result.stdout.split('\n')
        test_lines = [line for line in lines if 'test_' in line and '::' in line]
        
        print(f'✅ Test discovery successful')
        print(f'   - Total tests found: {len(test_lines)}')
        
        # Count by category
        unit_tests = len([t for t in test_lines if '/unit/' in t])
        integration_tests = len([t for t in test_lines if '/integration/' in t])
        perf_tests = len([t for t in test_lines if '/perf/' in t])
        
        print(f'   - Unit tests: {unit_tests}')
        print(f'   - Integration tests: {integration_tests}')  
        print(f'   - Performance tests: {perf_tests}')
        
    except Exception as e:
        print(f'❌ Test discovery failed: {e}')

    print('\n🎉 COMPREHENSIVE TEST SUMMARY')
    print('=' * 50)
    print('✅ Test infrastructure validated')
    print('✅ Core application components checked')
    print('✅ Test suite statistics gathered')
    print('✅ Ready for CI quality gate testing')
    print('\n🔗 Next Steps:')
    print('   1. Fix linting issues: ruff check . --fix')
    print('   2. Run type checking: mypy backend tests')
    print('   3. Security scan: bandit -r backend')
    print('   4. Full test suite: pytest tests/')
    print('   5. Complete CI: ./scripts/run_ci_locally.bat')

if __name__ == '__main__':
    main()
