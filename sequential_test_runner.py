"""
Sequential Test Runner - Runs tests one by one to avoid hanging issues
"""

import subprocess
import sys
import os
import time
from pathlib import Path

def get_test_files(test_dirs):
    """Get all test files from specified directories"""
    test_files = []
    for test_dir in test_dirs:
        test_path = Path(test_dir)
        if test_path.is_file():
            test_files.append(str(test_path))
        elif test_path.is_dir():
            # Find all test files in directory
            for file_path in test_path.rglob("test_*.py"):
                test_files.append(str(file_path))
    return sorted(test_files)

def run_single_test(test_file, timeout=30):
    """Run a single test file"""
    print(f"\nRunning: {test_file}")
    
    cmd = [
        sys.executable, "pytest_light.py", test_file,
        "-v", "--tb=short", f"--timeout={timeout}", "--maxfail=5"
    ]
    
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd, 
            timeout=timeout+10, 
            capture_output=True, 
            text=True,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        )
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            print(f"  PASS in {elapsed:.1f}s")
            return True, elapsed
        else:
            print(f"  FAIL in {elapsed:.1f}s (exit code: {result.returncode})")
            if result.stderr:
                print(f"  Error: {result.stderr[-200:]}")  # Last 200 chars
            return False, elapsed
            
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        print(f"  TIMEOUT after {elapsed:.1f}s")
        return False, elapsed

def main():
    """Main execution"""
    if len(sys.argv) < 2:
        print("Usage: python sequential_test_runner.py <test_dirs...> [--timeout N]")
        print("Example: python sequential_test_runner.py tests/api tests/utils")
        sys.exit(1)
    
    # Parse arguments
    args = sys.argv[1:]
    timeout = 30
    test_dirs = []
    
    i = 0
    while i < len(args):
        if args[i] == "--timeout":
            timeout = int(args[i+1])
            i += 2
        else:
            test_dirs.append(args[i])
            i += 1
    
    print("Sequential Test Runner with Light Mode")
    print(f"Test Directories: {test_dirs}")
    print(f"Timeout per test: {timeout}s")
    
    # Get test files
    test_files = get_test_files(test_dirs)
    if not test_files:
        print("No test files found")
        sys.exit(1)
    
    print(f"Found {len(test_files)} test files")
    
    # Run tests sequentially
    passed = 0
    failed = 0
    total_time = 0
    failed_tests = []
    
    for test_file in test_files:
        success, elapsed = run_single_test(test_file, timeout)
        total_time += elapsed
        
        if success:
            passed += 1
        else:
            failed += 1
            failed_tests.append(test_file)
    
    # Summary
    print(f"\n" + "="*60)
    print(f"FINAL RESULTS:")
    print(f"  Total: {len(test_files)} tests")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Success Rate: {(passed/len(test_files)*100):.1f}%")
    print(f"  Total Time: {total_time:.1f}s")
    print(f"  Average Time: {(total_time/len(test_files)):.1f}s per test")
    
    if failed_tests:
        print(f"\nFailed Tests:")
        for test_file in failed_tests:
            print(f"  - {test_file}")
    
    # Exit with error if any tests failed
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
