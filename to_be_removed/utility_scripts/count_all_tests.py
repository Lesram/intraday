#!/usr/bin/env python3
"""
Complete test count analysis for the algotrading platform
"""
import os
import subprocess
import sys
from pathlib import Path

def count_tests_in_directory(directory):
    """Count tests in a specific directory using pytest --collect-only"""
    try:
        cmd = [sys.executable, "-m", "pytest", directory, "--collect-only", "-q", "--tb=no", "--disable-warnings"]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            test_count = 0
            for line in lines:
                if ':' in line and line.strip().endswith(('0', '1', '2', '3', '4', '5', '6', '7', '8', '9')):
                    parts = line.split(':')
                    if len(parts) == 2:
                        try:
                            count = int(parts[1].strip())
                            test_count += count
                        except ValueError:
                            continue
            return test_count
        else:
            print(f"Error running pytest in {directory}: {result.stderr}")
            return 0
    except Exception as e:
        print(f"Exception counting tests in {directory}: {e}")
        return 0

def main():
    print("🧪 COMPLETE TEST SUITE ANALYSIS")
    print("=" * 50)
    
    # Directory structure to analyze
    test_directories = [
        "tests/unit",
        "tests/api", 
        "tests/integration",
        "tests/e2e",
        "tests/services",
        "tests/mlops",
        "tests/security",
        "tests/performance",
        "tests/risk",
        "tests/chaos",
        "tests/behavioral",
        "tests/contract",
        "tests/models",
        "tests/strategies",
        "tests/core",
        "tests/database",
        "tests/db",
        "tests/infra",
        "tests/smoke",
        "tests/comprehensive",
    ]
    
    total_tests = 0
    
    for directory in test_directories:
        if os.path.exists(directory):
            count = count_tests_in_directory(directory)
            print(f"{directory:30} {count:>6} tests")
            total_tests += count
        else:
            print(f"{directory:30} {'N/A':>6} (not found)")
    
    # Count root level test files
    root_test_files = [f for f in os.listdir('.') if f.startswith('test_') and f.endswith('.py')]
    if root_test_files:
        root_count = count_tests_in_directory('.')
        print(f"{'Root directory':30} {root_count:>6} tests")
        total_tests += root_count
    
    print("=" * 50)
    print(f"🎯 TOTAL TESTS DISCOVERED: {total_tests}")
    
    # Also try to get pytest's total discovery
    try:
        cmd = [sys.executable, "-m", "pytest", ".", "--collect-only", "-q", "--tb=no", "--disable-warnings"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and "collected" in result.stdout:
            for line in result.stdout.split('\n'):
                if "collected" in line:
                    print(f"📊 PyTest Discovery: {line.strip()}")
                    break
    except Exception as e:
        print(f"Could not run full pytest discovery: {e}")

if __name__ == "__main__":
    main()
