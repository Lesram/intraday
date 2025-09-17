#!/usr/bin/env python3
"""
Quick validation script for testing infrastructure
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and report the result."""
    print(f"\n🔍 {description}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print(f"✅ SUCCESS: {description}")
            return True
        else:
            print(f"❌ FAILED: {description}")
            print(f"Exit code: {result.returncode}")
            if result.stdout:
                print(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                print(f"STDERR:\n{result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ TIMEOUT: {description}")
        return False
    except Exception as e:
        print(f"💥 ERROR: {description} - {e}")
        return False


def main():
    """Validate testing infrastructure components."""
    print("🚀 Testing Infrastructure Validation")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not Path("backend").exists():
        print("❌ Not in the correct directory - backend folder not found")
        return 1
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Check if Python and pytest work
    tests_total += 1
    if run_command([sys.executable, "-m", "pytest", "--version"], "Pytest version check"):
        tests_passed += 1
    
    # Test 2: Check coverage tool
    tests_total += 1
    if run_command([sys.executable, "-m", "coverage", "--version"], "Coverage tool check"):
        tests_passed += 1
    
    # Test 3: Check if our enhanced coverage checker exists and is syntactically valid
    tests_total += 1
    if Path("scripts/check_coverage.py").exists():
        if run_command([sys.executable, "-c", "import sys; sys.path.insert(0, 'scripts'); import check_coverage"], 
                      "Coverage checker import test"):
            tests_passed += 1
    else:
        print("❌ Coverage checker script not found")
    
    # Test 4: Simple pytest dry run
    tests_total += 1  
    if run_command([sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/"], "Test collection check"):
        tests_passed += 1
    
    # Results
    print(f"\n📊 Infrastructure Validation Results")
    print(f"=" * 40)
    print(f"Tests passed: {tests_passed}/{tests_total}")
    
    if tests_passed == tests_total:
        print("✅ All infrastructure components are working!")
        return 0
    else:
        print(f"❌ {tests_total - tests_passed} infrastructure components need attention")
        return 1


if __name__ == "__main__":
    sys.exit(main())
