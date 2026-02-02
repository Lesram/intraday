#!/usr/bin/env python3
"""
Pipeline Validation Script
Quick validation that the test execution pipeline is properly configured.
"""

import subprocess
import sys
from pathlib import Path

def check_file_exists(file_path: str, description: str) -> bool:
    """Check if a required file exists."""
    if Path(file_path).exists():
        print(f"✅ {description}: {file_path}")
        return True
    else:
        print(f"❌ {description}: {file_path} (missing)")
        return False

def check_python_module(module_name: str) -> bool:
    """Check if a Python module is available."""
    try:
        result = subprocess.run([
            sys.executable, "-c", f"import {module_name}; print('OK')"
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print(f"✅ Python module: {module_name}")
            return True
        else:
            print(f"❌ Python module: {module_name} (not available)")
            return False
    except Exception as e:
        print(f"❌ Python module: {module_name} (error: {e})")
        return False

def check_pytest_markers() -> bool:
    """Check if pytest markers are properly configured."""
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", "--markers"
        ], capture_output=True, text=True, timeout=10)
        
        required_markers = ['unit', 'api', 'services', 'risk', 'strategies']
        markers_found = []
        
        for marker in required_markers:
            if f"{marker}:" in result.stdout:
                markers_found.append(marker)
        
        if len(markers_found) >= 3:  # At least 3 core markers
            print(f"✅ Pytest markers: {len(markers_found)} found")
            return True
        else:
            print(f"❌ Pytest markers: Only {len(markers_found)} found, need at least 3")
            return False
            
    except Exception as e:
        print(f"❌ Pytest markers: Error checking - {e}")
        return False

def main():
    """Run validation checks."""
    print("🔍 Validating Test Execution Pipeline Configuration")
    print("=" * 60)
    
    checks = []
    
    # Core files
    checks.append(check_file_exists(
        "scripts/run_all_tests_and_report.py", 
        "Python orchestrator script"
    ))
    checks.append(check_file_exists(
        "run_all_tests_and_report.ps1", 
        "PowerShell wrapper"
    ))
    checks.append(check_file_exists(
        ".vscode/tasks.json", 
        "VS Code tasks configuration"
    ))
    
    # Configuration files
    checks.append(check_file_exists(
        "pytest.ini", 
        "Pytest configuration"
    ))
    checks.append(check_file_exists(
        ".coveragerc", 
        "Coverage configuration"
    ))
    checks.append(check_file_exists(
        "requirements-dev.txt", 
        "Development dependencies"
    ))
    
    # Python modules
    required_modules = [
        'pytest', 'coverage', 'xml.etree.ElementTree', 
        'json', 'pathlib', 'subprocess'
    ]
    
    for module in required_modules:
        checks.append(check_python_module(module))
    
    # Pytest configuration
    checks.append(check_pytest_markers())
    
    # Summary
    print("\n" + "=" * 60)
    passed = sum(checks)
    total = len(checks)
    
    if passed == total:
        print(f"🎉 All {total} validation checks passed!")
        print("\n💡 Pipeline is ready to use:")
        print("   .\\run_all_tests_and_report.ps1")
        return 0
    else:
        print(f"⚠️ {total - passed} of {total} checks failed.")
        print("\n🔧 Fix the issues above before running the pipeline.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
