#!/usr/bin/env python3
"""
Comprehensive Platform Testing Suite
Runs all test categories and provides overall platform health assessment.
"""

import sys
import os
import subprocess
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def run_test_script(script_name, description):
    """Run a test script and return results"""
    script_path = Path(__file__).parent / script_name
    
    print(f"\n🚀 Running {description}...")
    print("-" * 50)
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=False,  # Show output in real time
            text=True,
            cwd=project_root
        )
        
        success = result.returncode == 0
        print(f"\n{'✅' if success else '❌'} {description}: {'PASSED' if success else 'FAILED'}")
        return success
    except Exception as e:
        print(f"❌ Error running {description}: {e}")
        return False

def run_comprehensive_tests():
    """Run all platform tests in sequence"""
    print("🎯 COMPREHENSIVE PLATFORM TESTING SUITE")
    print("=" * 50)
    print(f"Project Root: {project_root}")
    print(f"Python Version: {sys.version}")
    print()
    
    # Test configurations - comprehensive platform testing
    test_suites = [
        ("test_environment.py", "Environment & Dependencies"),
        ("test_core_platform.py", "Core Platform Components"),
        ("test_ml_strategy.py", "ML Pipeline & Strategy Engine"),
        ("test_api_integration.py", "API & Integration Layer"),
        ("test_security_performance.py", "Security & Performance"),
    ]
    
    results = []
    
    # Run each test suite
    for script, description in test_suites:
        success = run_test_script(script, description)
        results.append((description, success))
    
    # Calculate overall results
    passed = sum(1 for _, success in results if success)
    total = len(results)
    overall_rate = (passed / total) * 100
    
    print("\n" + "=" * 60)
    print("🏆 COMPREHENSIVE TESTING RESULTS")
    print("=" * 60)
    
    for description, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"  {description:.<40} {status}")
    
    print(f"\nOverall Success Rate: {passed}/{total} ({overall_rate:.1f}%)")
    
    if overall_rate >= 90:
        print("🎉 EXCELLENT - Platform ready for production!")
        verdict = "PRODUCTION_READY"
    elif overall_rate >= 75:
        print("🎯 GOOD - Platform functional with minor issues")
        verdict = "FUNCTIONAL"
    elif overall_rate >= 50:
        print("⚠️ NEEDS WORK - Significant issues to address")
        verdict = "NEEDS_IMPROVEMENT"
    else:
        print("🔧 CRITICAL - Major platform failures")
        verdict = "CRITICAL_ISSUES"
    
    print(f"\nPlatform Status: {verdict}")
    
    # Import for timestamp
    try:
        import pandas as pd
        timestamp = pd.Timestamp.now()
    except ImportError:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Create results summary file
    results_file = project_root / "test_results_summary.txt"
    with open(results_file, "w") as f:
        f.write(f"Platform Testing Results - {timestamp}\n")
        f.write("=" * 50 + "\n\n")
        
        for description, success in results:
            f.write(f"{description}: {'PASSED' if success else 'FAILED'}\n")
        
        f.write(f"\nOverall: {passed}/{total} ({overall_rate:.1f}%)\n")
        f.write(f"Status: {verdict}\n")
    
    print(f"\nResults saved to: {results_file}")
    
    return overall_rate >= 75

def main():
    """Main test execution"""
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()