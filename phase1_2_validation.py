#!/usr/bin/env python3
"""Phase 1.2 Validation Script - Test our AssertionError fixes"""

import subprocess
import sys

def run_test(test_path):
    """Run a single test and return if it passes"""
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pytest', test_path, '-v'
        ], capture_output=True, text=True, cwd='.')
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def main():
    print("=== PHASE 1.2 VALIDATION: ASSERTIONERROR FIXES ===\n")
    
    # Test our fixed errors
    tests_to_validate = [
        # Feature Engineering fixes
        'tests/test_feature_engineering_coverage.py::TestConfigurationModes::test_basic_feature_mode',
        'tests/test_feature_engineering_coverage.py::TestConfigurationModes::test_advanced_feature_mode',
        
        # Model Prediction fixes  
        'tests/test_model_manager_part2.py::TestModelManager::test_predict_with_registered_model',
        'tests/test_ensemble_model_focused_coverage.py::TestLoggingPaths::test_audit_logging_in_train_models',
        'tests/test_ensemble_model_phase7b4_final.py::TestModuleConstantsPhase7B4::test_environment_variable_handling',
    ]
    
    passed = 0
    failed = 0
    
    for test in tests_to_validate:
        print(f"Testing: {test}")
        is_passing, output = run_test(test)
        
        if is_passing:
            print(f"  ✅ PASS")
            passed += 1
        else:
            print(f"  ❌ FAIL") 
            print(f"  Error: {output[-200:]}")  # Last 200 chars of error
            failed += 1
        print()
    
    print("=== SUMMARY ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {passed/(passed+failed)*100:.1f}%")
    
    if failed == 0:
        print("\n🎉 ALL PHASE 1.2 ASSERTIONERROR FIXES VALIDATED!")
        print("Ready to continue with metrics and other assertion categories")
    else:
        print(f"\n⚠️ {failed} tests still failing - need additional fixes")

if __name__ == "__main__":
    main()
