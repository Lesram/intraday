#!/usr/bin/env python3
"""
FINAL TEST RUNNER - NO EXCUSES VERSION
"""
import os
import subprocess
from pathlib import Path

# ABSOLUTE PATH ENFORCEMENT
platform_root = r"C:\Users\Marsel\intra\algotrading_platform"
os.chdir(platform_root)

print("🎯 FINAL TEST EXECUTION ATTEMPT")
print(f"Directory: {os.getcwd()}")
print(f"Tests exist: {os.path.exists('tests')}")

# BULLETPROOF COMMAND - NO STOPPING ON FAILURES
cmd = [
    "python", "-m", "pytest", 
    "tests/",
    "--maxfail=0",  # Don't stop on failures (0 = unlimited)
    "--continue-on-collection-errors",
    "--disable-warnings",
    "--tb=no",      # No traceback to avoid output spam
    "--junit-xml=final_test_results.xml"
]

print(f"Command: {' '.join(cmd)}")
print("Starting...")

# RUN FROM CORRECT DIRECTORY
os.system(" ".join(cmd))

# CHECK RESULTS
if os.path.exists("final_test_results.xml"):
    size = os.path.getsize("final_test_results.xml")
    print(f"\n✅ Results generated: final_test_results.xml ({size} bytes)")
    
    with open("final_test_results.xml", "r") as f:
        content = f.read()
        if "tests=" in content:
            import re
            matches = re.findall(r'tests="(\d+)"', content)
            if matches:
                print(f"📊 Tests found in XML: {matches}")
else:
    print("\n❌ No results file generated")

print("✅ DONE")
