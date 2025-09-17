#!/usr/bin/env python3
# TEST ISOLATION RUNNER
# Purpose: Run tests in isolated environment to prevent failures

import subprocess
import sys
import os
from pathlib import Path

def run_isolated_tests(test_pattern=None, max_workers=1):
    '''Run tests in isolated environment'''
    
    # Set test environment variables
    test_env = os.environ.copy()
    test_env.update({
        'PYTEST_CURRENT_TEST': 'true',
        'TEST_DATABASE_URL': 'sqlite:///test_data/test_database.db',
        'ENVIRONMENT': 'test',
        'MOCK_EXTERNAL_APIS': 'true'
    })
    
    # Base pytest command with isolation settings
    cmd = [
        sys.executable, '-m', 'pytest',
        '--tb=short',
        '--maxfail=3',
        '--disable-warnings',
        '-v',
        '--durations=10'
    ]
    
    if test_pattern:
        cmd.extend(['-k', test_pattern])
    
    if max_workers > 1:
        cmd.extend(['-n', str(max_workers)])
    
    # Run with timeout
    try:
        result = subprocess.run(
            cmd,
            env=test_env,
            timeout=1800,  # 30 minute timeout
            capture_output=False
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("FAIL: Tests timed out - possible hanging tests detected")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Run isolated tests')
    parser.add_argument('--pattern', '-k', help='Test pattern to match')
    parser.add_argument('--workers', '-n', type=int, default=1, help='Number of workers')
    
    args = parser.parse_args()
    
    success = run_isolated_tests(args.pattern, args.workers)
    sys.exit(0 if success else 1)
