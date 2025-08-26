#!/usr/bin/env python3
"""
Generate accurate test inventory by collecting actual pytest test names
"""

import subprocess
import sys
import os
from pathlib import Path

def get_test_collection(test_file):
    """Get actual test collection for a file"""
    try:
        cmd = [
            sys.executable, "-m", "pytest", 
            "--collect-only", test_file, 
            "-q", "--tb=no"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            # Parse test names from output
            tests = []
            for line in result.stdout.split('\n'):
                if '::' in line and 'test_' in line and not line.strip().startswith('='):
                    # Clean up the line
                    test_name = line.strip()
                    tests.append(test_name)
            
            # Check if any tests were skipped
            skipped_count = result.stdout.count('SKIPPED') + result.stdout.count('skipped')
            if skipped_count > 0 and len(tests) == 0:
                return tests, len(tests), f"ALL_SKIPPED ({skipped_count} skipped)"
            
            return tests, len(tests), "SUCCESS"
        else:
            return [], 0, f"COLLECTION_ERROR: {result.stderr[:100]}"
    except subprocess.TimeoutExpired:
        return [], 0, "TIMEOUT"
    except Exception as e:
        return [], 0, f"ERROR: {str(e)[:100]}"

def main():
    """Generate comprehensive test inventory"""
    os.chdir(Path(__file__).parent)
    
    # Key test files from our inventory
    test_files = [
        # Core Infrastructure
        "tests/core/test_app_lifespan_and_di.py",
        "tests/core/test_routes_and_dtos_contract.py",
        "tests/unit/test_risk_manager_current.py",
        "tests/unit/test_risk_manager_comprehensive_fixed.py",
        "tests/unit/test_alpaca_client_core.py",
        "tests/unit/test_alpaca_client_comprehensive.py",
        "tests/unit/test_ensemble_model_comprehensive.py",
        "tests/unit/test_order_service_comprehensive_fixed.py",
        
        # API & WebSocket Tests
        "tests/test_api_factory_comprehensive.py",
        "tests/test_api_factory_coverage.py",
        "tests/test_websocket_comprehensive.py",
        "tests/api/test_ws_manager_comprehensive.py",
        
        # Trading & Strategy Tests
        "tests/test_trading_strategies_core.py",
        "tests/test_trading_strategies_integration.py",
        "tests/test_trading_strategies_coverage.py",
        "tests/strategies/test_trading_strategies_behavior.py",
        "tests/strategies/test_strategy_comprehensive.py",
        
        # Feature Engineering & Model Management
        "tests/test_feature_engineering_part1.py",
        "tests/test_feature_engineering_part2.py",
        "tests/test_feature_engineering_coverage.py",
        "tests/test_model_manager_part1.py",
        "tests/test_model_manager_part2_fixed.py",
        "tests/test_model_manager_part3.py",
        "tests/test_model_manager_part4.py",
        "tests/test_model_manager_coverage.py",
        
        # Phase 7A Tests
        "tests/test_alpaca_client_phase7a2.py",
        "tests/test_ensemble_model_phase7a1.py",
        "tests/test_ensemble_model_phase7a1_extended.py",
        
        # Phase 7B Tests
        "tests/test_market_data_phase7b1.py",
        "tests/test_market_data_phase7b1_extended.py", 
        "tests/test_market_data_phase7b1_final.py",
        "tests/test_social_sentiment_phase7b2.py",
        "tests/test_social_sentiment_phase7b2_extended.py",
        "tests/test_social_sentiment_phase7b2_final.py",
        "tests/test_order_service_phase7b3.py",
        "tests/test_order_service_phase7b3_extended.py",
        "tests/test_order_service_phase7b3_final.py",
        "tests/test_order_service_phase7b3_max_coverage.py",
        "tests/test_ensemble_model_phase7b4.py",
        "tests/test_ensemble_model_phase7b4_extended.py",
        "tests/test_ensemble_model_phase7b4_final.py",
        "tests/test_ensemble_model_phase7b4_deep_coverage.py",
        "tests/test_trading_strategies_phase7b5.py",
        "tests/test_websocket_manager_phase7b6.py",
        "tests/test_order_service_phase7b6.py",
        
        # Coverage & Config Tests
        "tests/test_config_coverage_quick_win.py",
        "tests/test_config_hardening.py",
        "tests/test_b25_observability.py",
        "tests/test_alpaca_client_coverage.py",
        "tests/test_async_risk_manager_modern.py",
        "tests/test_risk_manager_coverage.py",
        "tests/test_logging_coverage_quick_win.py",
        "tests/test_ml_direct_coverage.py",
        "tests/test_minimal_metrics.py"
    ]
    
    print("# ACCURATE TEST INVENTORY REPORT")
    print("=" * 60)
    
    total_tests = 0
    runnable_files = 0
    skipped_files = 0
    error_files = 0
    
    runnable_test_files = []
    
    for test_file in test_files:
        if not os.path.exists(test_file):
            print(f"\n❌ MISSING: {test_file}")
            continue
            
        tests, count, status = get_test_collection(test_file)
        
        if status == "SUCCESS" and count > 0:
            print(f"\n✅ {test_file} ({count} tests)")
            total_tests += count
            runnable_files += 1
            runnable_test_files.append(test_file)
            # Show first few test names as sample
            for test in tests[:3]:
                print(f"   - {test}")
            if len(tests) > 3:
                print(f"   - ... and {len(tests)-3} more tests")
                
        elif "ALL_SKIPPED" in status or count == 0:
            print(f"\n⚠️  SKIPPED: {test_file} - {status}")
            skipped_files += 1
            
        else:
            print(f"\n❌ ERROR: {test_file} - {status}")
            error_files += 1
    
    print(f"\n" + "=" * 60)
    print(f"SUMMARY:")
    print(f"✅ Runnable files: {runnable_files}")
    print(f"⚠️  Skipped files: {skipped_files}")
    print(f"❌ Error files: {error_files}")
    print(f"🧪 Total tests discovered: {total_tests}")
    
    # Generate corrected pytest command
    if runnable_test_files:
        print(f"\n" + "=" * 60)
        print("CORRECTED PYTEST COMMAND:")
        print("pytest \\")
        for i, test_file in enumerate(runnable_test_files):
            ending = " \\" if i < len(runnable_test_files) - 1 else ""
            print(f"  {test_file}{ending}")
        print("  --cov=backend --cov-report=html --cov-report=term-missing \\")
        print("  --maxfail=10 --timeout=180 -v")

if __name__ == "__main__":
    main()
