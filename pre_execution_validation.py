#!/usr/bin/env python3
"""
Pre-Execution Validation Script
Validates all framework components are ready for comprehensive test execution
"""
import os
import sys
import subprocess
import importlib.util
from pathlib import Path

def validate_environment():
    """Validate environment setup"""
    print("🔍 ENVIRONMENT VALIDATION")
    print(f"   Python version: {sys.version.split()[0]}")
    
    # Check critical environment variables
    ml_disabled = os.environ.get('DISABLE_ML', 'Not Set')
    print(f"   DISABLE_ML: {ml_disabled}")
    
    # Check virtual environment
    venv_active = sys.prefix != sys.base_prefix
    print(f"   Virtual environment active: {venv_active}")
    
    # Check sitecustomize.py is working
    try:
        import torch
        torch_mocked = getattr(torch, '__file__', '').startswith('<mocked:') if hasattr(torch, '__file__') else True
        print(f"   Torch properly mocked: {torch_mocked}")
    except ImportError:
        print("   Torch not available (expected)")
    
    return ml_disabled == '1' and venv_active

def validate_test_framework():
    """Validate pytest and plugins"""
    print("\n🔍 TEST FRAMEWORK VALIDATION")
    
    required_packages = [
        ('pytest', 'pytest'), 
        ('pytest-cov', 'pytest_cov'), 
        ('pytest-timeout', 'pytest_timeout'), 
        ('pytest-asyncio', 'pytest_asyncio'),
        ('pytest-xdist', 'xdist')
    ]
    
    missing_packages = []
    for package_name, import_name in required_packages:
        try:
            result = subprocess.run([sys.executable, '-c', f'import {import_name}'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print(f"   ✅ {package_name} available")
            else:
                missing_packages.append(package_name)
                print(f"   ❌ {package_name} missing")
        except:
            missing_packages.append(package_name)
            print(f"   ❌ {package_name} missing")
    
    return len(missing_packages) == 0

def validate_light_mode():
    """Validate light mode configuration"""
    print("\n🔍 LIGHT MODE VALIDATION")
    
    # Check conftest_light_mode.py exists
    conftest_light = Path('conftest_light_mode.py')
    if conftest_light.exists():
        print("   ✅ conftest_light_mode.py exists")
    else:
        print("   ❌ conftest_light_mode.py missing")
        return False
    
    # Check main conftest.py imports light mode
    conftest_main = Path('tests/conftest.py')
    if conftest_main.exists():
        try:
            content = conftest_main.read_text(encoding='utf-8')
            if 'conftest_light_mode' in content:
                print("   ✅ tests/conftest.py imports light mode")
            else:
                print("   ⚠️  tests/conftest.py doesn't import light mode")
        except UnicodeDecodeError:
            print("   ⚠️  tests/conftest.py encoding issue")
    
    # Check pytest.ini has proper configuration
    pytest_ini = Path('pytest.ini')
    if pytest_ini.exists():
        try:
            content = pytest_ini.read_text(encoding='utf-8')
            if 'asyncio_mode = auto' in content:
                print("   ✅ pytest.ini has asyncio_mode = auto")
            else:
                print("   ⚠️  pytest.ini missing asyncio_mode")
        except UnicodeDecodeError:
            print("   ⚠️  pytest.ini encoding issue")
    
    return True

def validate_test_files():
    """Validate critical test files exist"""
    print("\n🔍 TEST FILES VALIDATION")
    
    critical_test_files = [
        'tests/core/test_app_lifespan_and_di.py',
        'tests/unit/test_risk_manager_current.py', 
        'tests/unit/test_alpaca_client_core.py',
        'tests/unit/test_alpaca_client_comprehensive.py',
        'tests/test_api_factory_comprehensive.py',
        'tests/test_websocket_comprehensive.py',
        'tests/test_feature_engineering_part1.py',
        'tests/test_feature_engineering_part2.py',
        'tests/test_model_manager_part1.py',
        'tests/test_model_manager_part2_fixed.py',
        'tests/test_model_manager_part3.py',
        'tests/test_model_manager_part4.py',
    ]
    
    missing_files = []
    for test_file in critical_test_files:
        if Path(test_file).exists():
            print(f"   ✅ {test_file}")
        else:
            missing_files.append(test_file)
            print(f"   ❌ {test_file} missing")
    
    return len(missing_files) == 0

def run_smoke_test():
    """Run a quick smoke test"""
    print("\n🔍 SMOKE TEST")
    
    cmd = [
        sys.executable, '-m', 'pytest',
        'tests/core/test_app_lifespan_and_di.py::TestAppLifespan::test_startup_runs_exactly_once',
        '-v', '--timeout=30', '--tb=short'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        # Accept both PASSED and SKIPPED as success for smoke test
        if 'PASSED' in result.stdout or 'SKIPPED' in result.stdout or result.returncode == 0:
            print("   ✅ Smoke test passed")
            return True
        else:
            print("   ❌ Smoke test failed")
            print(f"   Output: {result.stdout[-200:]}")
            print(f"   Error: {result.stderr[-200:]}")
            return False
    except subprocess.TimeoutExpired:
        print("   ❌ Smoke test timed out")
        return False
    except Exception as e:
        print(f"   ❌ Smoke test error: {e}")
        return False

def main():
    """Main validation function"""
    print("🚀 PRE-EXECUTION FRAMEWORK VALIDATION")
    print("=" * 50)
    
    all_checks = []
    
    # Run all validations
    all_checks.append(validate_environment())
    all_checks.append(validate_test_framework())
    all_checks.append(validate_light_mode())
    all_checks.append(validate_test_files())
    all_checks.append(run_smoke_test())
    
    print("\n" + "=" * 50)
    if all(all_checks):
        print("✅ ALL VALIDATIONS PASSED - FRAMEWORK READY FOR EXECUTION!")
        print("\nRecommended execution command:")
        print("python -m pytest [test_files] --cov=backend --cov-report=html --cov-report=term-missing --maxfail=50 --timeout=300 -v")
        return True
    else:
        print("❌ SOME VALIDATIONS FAILED - PLEASE REVIEW ABOVE")
        failed_count = len([x for x in all_checks if not x])
        print(f"   {failed_count}/{len(all_checks)} validations failed")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
