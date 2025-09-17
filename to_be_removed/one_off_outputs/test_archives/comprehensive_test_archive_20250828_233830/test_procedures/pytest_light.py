"""
Light Mode pytest execution wrapper.
This script ensures light mode is activated BEFORE pytest starts.
"""

import subprocess
import sys
import os

def activate_light_mode():
    """Activate light mode by importing the setup module"""
    print("Activating Light Mode for pytest...")
    import conftest_light_mode
    print("Light Mode activated successfully")

def run_pytest_with_light_mode(args=None):
    """Run pytest with light mode pre-activated"""
    if args is None:
        args = sys.argv[1:]  # Get command line args
    
    # Activate light mode first
    activate_light_mode()
    
    # Set additional environment variables for safety
    env = os.environ.copy()
    env.update({
        'PYTEST_RUNNING': '1',
        'DISABLE_ML': '1',
        'DISABLE_TORCH': '1',
        'DISABLE_TRANSFORMERS': '1',
        'DISABLE_TENSORFLOW': '1',
        'DISABLE_XGBOOST': '1',
        'PYTHONFAULTHANDLER': '1',
        'PYTHONIOENCODING': 'utf-8'  # Force UTF-8 encoding
    })
    
    # Build pytest command
    cmd = [sys.executable, '-m', 'pytest'] + args
    
    print(f"Running: {' '.join(cmd)}")
    print(f"Working directory: {os.getcwd()}")
    print(f"Environment secured with ML libraries disabled")
    
    # Run pytest with the modified environment
    result = subprocess.run(cmd, env=env)
    return result.returncode

if __name__ == "__main__":
    exit_code = run_pytest_with_light_mode()
    sys.exit(exit_code)
