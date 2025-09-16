#!/usr/bin/env python3
"""
Comprehensive Test Runner for AI Review Preparation
Compares current test status to AI Report 2 baseline
"""

import subprocess
import sys
import re
from datetime import datetime

def run_comprehensive_tests():
    """Run all tests and capture detailed statistics"""
    
    print("=" * 60)
    print("COMPREHENSIVE PLATFORM TEST ANALYSIS")
    print("=" * 60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"AI Report 2 Baseline: 82.3% pass rate (1,833 passed, 270 failed, 36 errors, 88 skipped)")
    print()
    
    # Run pytest with json report
    print("Running comprehensive test suite...")
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            '--tb=short',
            '--disable-warnings',
            '-v'
        ], capture_output=True, text=True, timeout=600)  # 10 minute timeout
        
        output = result.stdout
        
        # Extract statistics
        passed = len(re.findall(r'PASSED', output))
        failed = len(re.findall(r'FAILED', output)) 
        errors = len(re.findall(r'ERROR', output))
        skipped = len(re.findall(r'SKIPPED', output))
        
        # Try to find summary line
        summary_match = re.search(r'=+ (.+) =+$', output, re.MULTILINE)
        summary_line = summary_match.group(1) if summary_match else "No summary found"
        
        total = passed + failed + errors + skipped
        
        print()
        print("=" * 40)
        print("DETAILED RESULTS")
        print("=" * 40)
        print(f"Total Tests Executed: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Errors: {errors}")
        print(f"⏭️  Skipped: {skipped}")
        
        if total > 0:
            pass_rate = (passed / total) * 100
            print(f"📊 Pass Rate: {pass_rate:.1f}%")
            
            # Compare to baseline
            baseline_total = 1833 + 270 + 36 + 88  # 2227 from AI report
            baseline_pass_rate = 82.3
            
            print()
            print("=" * 40)
            print("COMPARISON TO AI REPORT 2")
            print("=" * 40)
            print(f"Previous: {baseline_pass_rate}% pass rate ({baseline_total} total tests)")
            print(f"Current:  {pass_rate:.1f}% pass rate ({total} total tests)")
            
            improvement = pass_rate - baseline_pass_rate
            test_change = total - baseline_total
            
            print(f"📈 Pass Rate Change: {improvement:+.1f} percentage points")
            print(f"📊 Test Count Change: {test_change:+d} tests")
            
            if improvement > 5:
                print("🎉 SIGNIFICANT IMPROVEMENT!")
            elif improvement > 0:
                print("✅ Improvement detected")
            elif improvement < -5:
                print("🚨 SIGNIFICANT REGRESSION!")
            else:
                print("➡️  Stable performance")
        
        # Show test summary
        print()
        print("=" * 40)
        print("PYTEST SUMMARY")
        print("=" * 40)
        print(summary_line)
        
        # Show sample failures if any
        if failed > 0:
            print()
            print("=" * 40)
            print("SAMPLE FAILURES (First 10)")
            print("=" * 40)
            failure_lines = re.findall(r'FAILED (.+?) -', output)[:10]
            for i, failure in enumerate(failure_lines, 1):
                print(f"{i:2d}. {failure}")
        
        # Return statistics for further analysis
        return {
            'total': total,
            'passed': passed,
            'failed': failed,
            'errors': errors,
            'skipped': skipped,
            'pass_rate': pass_rate if total > 0 else 0,
            'improvement': improvement if total > 0 else 0
        }
        
    except subprocess.TimeoutExpired:
        print("❌ Test execution timed out after 10 minutes")
        return None
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return None

if __name__ == "__main__":
    stats = run_comprehensive_tests()
    if stats:
        print()
        print("=" * 60)
        print("Test analysis complete. Use these statistics for AI review.")
        print("=" * 60)