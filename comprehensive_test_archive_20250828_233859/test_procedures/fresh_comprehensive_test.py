#!/usr/bin/env python3
"""
FRESH COMPREHENSIVE TEST EXECUTION - AUGUST 28, 2025
"""
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# ABSOLUTE PATH ENFORCEMENT
platform_root = r"C:\Users\Marsel\intra\algotrading_platform"
os.chdir(platform_root)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
results_file = f"comprehensive_test_results_{timestamp}.xml"

print("🚀 FRESH COMPREHENSIVE TEST EXECUTION")
print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"📁 Directory: {os.getcwd()}")
print(f"📂 Tests exist: {os.path.exists('tests')}")
print(f"📄 Results file: {results_file}")
print("=" * 80)

# COMPREHENSIVE COMMAND - RUN ALL TESTS REGARDLESS OF FAILURES
cmd = [
    "python", "-m", "pytest", 
    "tests/",
    "--maxfail=0",                      # Don't stop on failures (unlimited)
    "--continue-on-collection-errors",  # Continue if collection errors
    "--disable-warnings",               # No warning spam
    "--tb=no",                          # No traceback output
    f"--junit-xml={results_file}"       # XML results with timestamp
]

print(f"🔧 Command: {' '.join(cmd)}")
print("⏰ Starting fresh test execution...")
print("🎯 Target: ALL 3,907 tests")
print("=" * 80)

# EXECUTE WITH os.system for bulletproof directory handling
result_code = os.system(" ".join(cmd))

print("=" * 80)
print(f"✅ Test execution completed with return code: {result_code}")

# ANALYZE RESULTS
if os.path.exists(results_file):
    size = os.path.getsize(results_file)
    print(f"📄 Results file created: {results_file} ({size:,} bytes)")
    
    # Extract test counts
    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'tests=' in content:
                import re
                matches = re.findall(r'tests="(\d+)"', content)
                failures = re.findall(r'failures="(\d+)"', content)
                errors = re.findall(r'errors="(\d+)"', content)
                skipped = re.findall(r'skipped="(\d+)"', content)
                
                if matches:
                    total_tests = sum(int(m) for m in matches)
                    total_failures = sum(int(f) for f in failures) if failures else 0
                    total_errors = sum(int(e) for e in errors) if errors else 0
                    total_skipped = sum(int(s) for s in skipped) if skipped else 0
                    total_passed = total_tests - total_failures - total_errors - total_skipped
                    
                    print("📊 FRESH TEST RESULTS SUMMARY:")
                    print(f"🎯 TOTAL TESTS: {total_tests}")
                    print(f"✅ PASSED: {total_passed} ({total_passed/total_tests*100:.1f}%)")
                    print(f"❌ FAILED: {total_failures} ({total_failures/total_tests*100:.1f}%)")
                    print(f"💥 ERRORS: {total_errors} ({total_errors/total_tests*100:.1f}%)")
                    print(f"⏭️  SKIPPED: {total_skipped} ({total_skipped/total_tests*100:.1f}%)")
                    print(f"🎉 SUCCESS RATE: {total_passed/total_tests*100:.1f}%")
                    print(f"📈 COMPLETION: {total_tests/3907*100:.1f}% of target 3,907 tests")
    except Exception as e:
        print(f"⚠️  Could not parse results: {e}")
else:
    print("❌ No results file generated")

print("🏁 FRESH COMPREHENSIVE TEST EXECUTION COMPLETE")
