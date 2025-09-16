#!/usr/bin/env python3
"""
BULLETPROOF TEST RUNNER - RUNS ALL TESTS NO MATTER WHAT
"""
import os
import sys
import subprocess
from pathlib import Path

# FORCE CORRECT DIRECTORY
platform_root = Path(r"C:\Users\Marsel\intra\algotrading_platform")
os.chdir(platform_root)

print("🚀 BULLETPROOF TEST EXECUTION")
print(f"📁 Working Directory: {os.getcwd()}")
print(f"📂 Tests Directory Exists: {(platform_root / 'tests').exists()}")
print(f"🎯 Target: ALL 3,907 tests (no matter what failures occur)")
print("=" * 60)

# BULLETPROOF PYTEST COMMAND - CONTINUES NO MATTER WHAT
cmd = [
    sys.executable, "-m", "pytest", 
    "tests/",
    "--forked",                  # Run each test in separate process
    "--tb=no",                   # No traceback output
    "--maxfail=999999",         # Allow massive failures
    "--continue-on-collection-errors",
    "--disable-warnings",
    "--junit-xml=bulletproof_all_tests.xml"
]

print(f"🔧 Command: {' '.join(cmd)}")
print("⏰ Starting execution...")
print("=" * 60)

# RUN WITH FORCED WORKING DIRECTORY
result = subprocess.run(cmd, cwd=platform_root, capture_output=False)

print("=" * 60)
print(f"✅ Test execution completed with return code: {result.returncode}")

# CHECK RESULTS
results_file = platform_root / "bulletproof_all_tests.xml"
if results_file.exists():
    size = results_file.stat().st_size
    print(f"📄 Results file created: bulletproof_all_tests.xml ({size} bytes)")
    
    # Try to extract test count from XML
    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'tests=' in content:
                import re
                matches = re.findall(r'tests="(\d+)"', content)
                if matches:
                    total_tests = sum(int(m) for m in matches)
                    print(f"🎉 TOTAL TESTS EXECUTED: {total_tests}")
    except Exception as e:
        print(f"⚠️  Could not parse test count: {e}")
else:
    print("❌ No results file generated")

print("🏁 BULLETPROOF TEST EXECUTION COMPLETE")
