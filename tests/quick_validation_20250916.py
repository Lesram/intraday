# Quick Test Suite Runner
# Created: September 16, 2025
# Status: CAN BE REMOVED (Temporary validation script)

import subprocess
import sys
from pathlib import Path

def run_sample_tests():
    """Run a small sample of tests to validate the setup"""
    project_root = Path(".")
    python_exe = "C:/Users/Marsel/intra/algotrading_platform/venv/Scripts/python.exe"
    
    # Create test_results directory
    test_results_dir = project_root / "test_results"
    test_results_dir.mkdir(exist_ok=True)
    
    print("[START] Running sample test validation...")
    
    # Run a few key tests with coverage
    cmd = [
        python_exe, "-m", "pytest",
        "tests/test_auth.py", 
        "tests/test_api.py",
        "--cov=backend",
        "--cov-report=term-missing:skip-covered",
        "--cov-report=html:test_results/coverage_html_validation",
        "--cov-report=xml:test_results/coverage_validation.xml",
        "--junitxml=test_results/test_results_validation.xml",
        "--tb=short",
        "-v",
        "--timeout=30"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        print(f"[INFO] Exit code: {result.returncode}")
        print(f"[INFO] Tests run with {len(result.stdout.split('PASSED')) + len(result.stdout.split('FAILED'))} assertions")
        
        # Check if coverage files were created
        coverage_xml = test_results_dir / "coverage_validation.xml"
        if coverage_xml.exists():
            print("[PASS] Coverage XML generated successfully")
        else:
            print("[WARN] Coverage XML not found")
            
        coverage_html = test_results_dir / "coverage_html_validation" / "index.html"
        if coverage_html.exists():
            print("[PASS] Coverage HTML generated successfully")
        else:
            print("[WARN] Coverage HTML not found")
            
        return result.returncode == 0 or result.returncode == 1  # 1 = tests failed but ran
        
    except Exception as e:
        print(f"[FAIL] Error running sample tests: {e}")
        return False

if __name__ == "__main__":
    success = run_sample_tests()
    if success:
        print("[SUCCESS] Sample test validation completed")
    else:
        print("[FAIL] Sample test validation failed")