#!/usr/bin/env python3
"""
STANDARDIZED TEST EXECUTION SCRIPT
Fixed working directory: C:/Users/Marsel/intra/algotrading_platform
No more directory confusion or repeated reinvention
"""

import os
import subprocess
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# STANDARDIZED CONFIGURATION - NO DEVIATION
PLATFORM_ROOT = Path("C:/Users/Marsel/intra/algotrading_platform")
TESTS_DIR = PLATFORM_ROOT / "tests"
RESULTS_FILE = PLATFORM_ROOT / "full_test_results.xml"
LOG_FILE = PLATFORM_ROOT / "test_execution.log"

class StandardizedTestRunner:
    """Standardized test runner - no more reinventing the wheel"""
    
    def __init__(self):
        self.root_dir = PLATFORM_ROOT
        self.start_time = datetime.now()
        
    def ensure_correct_directory(self):
        """Enforce correct working directory - no exceptions"""
        if not self.root_dir.exists():
            raise FileNotFoundError(f"Platform root not found: {self.root_dir}")
        
        if not TESTS_DIR.exists():
            raise FileNotFoundError(f"Tests directory not found: {TESTS_DIR}")
            
        # Change to correct directory
        os.chdir(str(self.root_dir))
        print(f"✅ Working directory: {os.getcwd()}")
        print(f"✅ Tests directory exists: {TESTS_DIR.exists()}")
        
    def run_comprehensive_tests(self):
        """Run all 3,907 tests with standardized configuration"""
        self.ensure_correct_directory()
        
        # Clean up any existing results
        if RESULTS_FILE.exists():
            RESULTS_FILE.unlink()
            
        print(f"🚀 STANDARDIZED TEST EXECUTION")
        print(f"📁 Directory: {self.root_dir}")
        print(f"🎯 Target: All 3,907 tests")
        print(f"⏰ Started: {self.start_time}")
        print("=" * 60)
        
        # Standardized pytest command - no more variations
        cmd = [
            sys.executable, "-m", "pytest", "tests/",
            "--tb=line",
            "-v", 
            "--continue-on-collection-errors",
            "--maxfail=9999",
            "--disable-warnings",
            f"--junit-xml={RESULTS_FILE}",
            "--durations=10"
        ]
        
        print(f"📋 Command: {' '.join(cmd)}")
        print()
        
        # Execute with proper working directory
        try:
            result = subprocess.run(cmd, cwd=str(self.root_dir), text=True)
            
            print(f"✅ Test execution completed")
            print(f"📄 Results file: {RESULTS_FILE}")
            print(f"📊 Return code: {result.returncode}")
            
            return result.returncode == 0
            
        except Exception as e:
            print(f"❌ Test execution failed: {e}")
            return False
    
    def verify_results(self):
        """Verify test results were generated"""
        if not RESULTS_FILE.exists():
            print(f"❌ Results file not found: {RESULTS_FILE}")
            return False
            
        size = RESULTS_FILE.stat().st_size
        print(f"✅ Results file exists: {RESULTS_FILE} ({size} bytes)")
        return True

def main():
    """Main execution function"""
    print("STANDARDIZED ALGOTRADING PLATFORM TEST RUNNER")
    print("=" * 80)
    print(f"🏠 Fixed Platform Root: {PLATFORM_ROOT}")
    print(f"📂 Tests Directory: {TESTS_DIR}")
    print(f"📄 Results File: {RESULTS_FILE}")
    print()
    
    runner = StandardizedTestRunner()
    
    try:
        # Run comprehensive tests
        success = runner.run_comprehensive_tests()
        
        # Verify results
        if success:
            runner.verify_results()
            print("\n🎉 STANDARDIZED TEST EXECUTION COMPLETE!")
        else:
            print("\n⚠️ Test execution completed with issues")
            
    except Exception as e:
        print(f"💥 CRITICAL ERROR: {e}")
        return 1
        
    return 0

if __name__ == "__main__":
    exit(main())
