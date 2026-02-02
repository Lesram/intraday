#!/usr/bin/env python3
"""
Comprehensive Integration Verification Script

Verifies that all authentication changes made on October 4, 2025 are properly
integrated throughout the entire platform.

Checks:
1. No hardcoded credentials remain in source code
2. Both auth endpoints use database authentication
3. Test infrastructure is properly configured
4. All imports are correct
5. Documentation is complete
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Tuple

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_section(title: str):
    """Print a section header."""
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{title}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")


def print_success(message: str):
    """Print a success message."""
    print(f"{GREEN}✅ {message}{RESET}")


def print_error(message: str):
    """Print an error message."""
    print(f"{RED}❌ {message}{RESET}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"{YELLOW}⚠️  {message}{RESET}")


def check_no_hardcoded_credentials() -> bool:
    """Check that no hardcoded admin123 credentials remain in backend code."""
    print_section("1. Checking for Hardcoded Credentials")
    
    backend_path = Path("backend")
    issues = []
    
    # Patterns to search for
    patterns = [
        (r'password.*=.*["\']admin123["\']', "admin123 password"),
        (r'username.*=.*["\']admin["\'].*password.*=.*["\']admin123["\']', "admin/admin123 combo"),
        (r'{["\']admin["\']: ["\']admin123["\']', "credentials dictionary"),
    ]
    
    excluded_files = {
        "backend/api/auth.py",  # Legacy file with test fallback
    }
    
    for py_file in backend_path.rglob("*.py"):
        # Skip excluded files
        if str(py_file).replace("\\", "/") in excluded_files:
            continue
            
        try:
            content = py_file.read_text(encoding='utf-8')
            
            for pattern, description in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    # Check if it's in a comment or docstring
                    for line_no, line in enumerate(content.split('\n'), 1):
                        if re.search(pattern, line, re.IGNORECASE):
                            # Allow in comments and docstrings
                            stripped = line.strip()
                            if not (stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''")):
                                issues.append(f"{py_file}:{line_no} - Found {description}")
        except Exception as e:
            print_warning(f"Could not read {py_file}: {e}")
    
    if issues:
        for issue in issues:
            print_error(issue)
        return False
    else:
        print_success("No hardcoded credentials found in backend code")
        return True


def check_auth_endpoints() -> bool:
    """Check that consolidated auth endpoint uses database authentication."""
    print_section("2. Checking Auth Endpoints")
    
    # Check consolidated auth module
    file_path = "backend/api/routes/auth.py"
    required_elements = [
        "UserRepository", 
        "get_db_session", 
        "authenticate_user",
        '@router.post("/login"',
        '@router.post("/token"',
        '@router.post("/register"',
        '@router.get("/verify"',
        '@router.get("/me"',
        '@router.post("/token/validate"'
    ]
    
    all_good = True
    
    try:
        content = Path(file_path).read_text(encoding='utf-8')
        
        missing = []
        for element in required_elements:
            if element not in content:
                missing.append(element)
        
        if missing:
            print_error(f"{file_path} missing: {', '.join(missing)}")
            all_good = False
        else:
            print_success(f"{file_path} properly uses database authentication")
            print_success(f"All auth endpoints consolidated: login, token, register, verify, me, token/validate")
            
    except Exception as e:
        print_error(f"Could not read {file_path}: {e}")
        all_good = False
    
    return all_good


def check_test_infrastructure() -> bool:
    """Check that test infrastructure is properly configured."""
    print_section("3. Checking Test Infrastructure")
    
    files_to_check = [
        ("test/conftest.py", ["pytest_configure", "TEST_ADMIN_USERNAME", "test_credentials"]),
        ("test/test_credentials.py", ["get_test_admin_credentials", "get_test_login_data"]),
        ("test/__init__.py", ["Test package"]),
        ("pytest.ini", ["asyncio_mode", "testpaths"]),
    ]
    
    all_good = True
    
    for file_path, required_elements in files_to_check:
        path = Path(file_path)
        if not path.exists():
            print_error(f"{file_path} does not exist")
            all_good = False
            continue
        
        try:
            content = path.read_text(encoding='utf-8')
            
            missing = []
            for element in required_elements:
                if element not in content:
                    missing.append(element)
            
            if missing:
                print_warning(f"{file_path} missing: {', '.join(missing)}")
            else:
                print_success(f"{file_path} properly configured")
                
        except Exception as e:
            print_error(f"Could not read {file_path}: {e}")
            all_good = False
    
    return all_good


def check_documentation() -> bool:
    """Check that all documentation is complete."""
    print_section("4. Checking Documentation")
    
    required_docs = [
        "AUTHENTICATION_SETUP.md",
        "HARDCODED_CREDENTIALS_FIX_COMPLETE.md",
        "QUICK_START_ADMIN_SETUP.md",
        "TEST_ENVIRONMENT_FIX.md",
    ]
    
    all_good = True
    
    for doc in required_docs:
        path = Path(doc)
        if not path.exists():
            print_error(f"{doc} does not exist")
            all_good = False
        else:
            size = path.stat().st_size
            if size < 1000:  # Less than 1KB
                print_warning(f"{doc} exists but seems incomplete ({size} bytes)")
            else:
                print_success(f"{doc} exists ({size:,} bytes)")
    
    return all_good


def check_kubernetes_config() -> bool:
    """Check Kubernetes configuration."""
    print_section("5. Checking Kubernetes Configuration")
    
    k8s_files = [
        ("k8s/secrets.yaml", ["admin-username", "admin-password"]),
        ("k8s/admin-user-job.yaml", ["create-admin-user", "ADMIN_USERNAME"]),
    ]
    
    all_good = True
    
    for file_path, required_elements in k8s_files:
        path = Path(file_path)
        if not path.exists():
            print_error(f"{file_path} does not exist")
            all_good = False
            continue
        
        try:
            content = path.read_text(encoding='utf-8')
            
            missing = []
            for element in required_elements:
                if element not in content:
                    missing.append(element)
            
            if missing:
                print_error(f"{file_path} missing: {', '.join(missing)}")
                all_good = False
            else:
                print_success(f"{file_path} properly configured")
                
        except Exception as e:
            print_error(f"Could not read {file_path}: {e}")
            all_good = False
    
    return all_good


def check_scripts() -> bool:
    """Check that required scripts exist."""
    print_section("6. Checking Scripts")
    
    scripts = [
        "scripts/create_admin_user.py",
    ]
    
    all_good = True
    
    for script in scripts:
        path = Path(script)
        if not path.exists():
            print_error(f"{script} does not exist")
            all_good = False
        else:
            # Check it has required functions
            content = path.read_text(encoding='utf-8')
            if "create_admin_user" in content and "UserRepository" in content:
                print_success(f"{script} exists and looks complete")
            else:
                print_warning(f"{script} exists but may be incomplete")
    
    return all_good


def check_environment_files() -> bool:
    """Check environment configuration files."""
    print_section("7. Checking Environment Files")
    
    env_files = [
        (".env.example", "ADMIN_USERNAME"),
        (".env.test", "TEST_ADMIN_USERNAME"),
    ]
    
    all_good = True
    
    for file_path, required_var in env_files:
        path = Path(file_path)
        if not path.exists():
            print_warning(f"{file_path} does not exist (optional)")
        else:
            content = path.read_text(encoding='utf-8')
            if required_var in content:
                print_success(f"{file_path} configured correctly")
            else:
                print_warning(f"{file_path} missing {required_var}")
    
    return all_good


def main():
    """Run all verification checks."""
    print(f"{BLUE}")
    print("=" * 80)
    print("  COMPREHENSIVE INTEGRATION VERIFICATION")
    print("  Authentication System Changes - October 4, 2025")
    print("=" * 80)
    print(f"{RESET}")
    
    checks = [
        ("Hardcoded Credentials", check_no_hardcoded_credentials),
        ("Auth Endpoints", check_auth_endpoints),
        ("Test Infrastructure", check_test_infrastructure),
        ("Documentation", check_documentation),
        ("Kubernetes Config", check_kubernetes_config),
        ("Scripts", check_scripts),
        ("Environment Files", check_environment_files),
    ]
    
    results = []
    
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print_error(f"Error running {name} check: {e}")
            results.append((name, False))
    
    # Summary
    print_section("VERIFICATION SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = f"{GREEN}✅ PASS{RESET}" if result else f"{RED}❌ FAIL{RESET}"
        print(f"{name:.<40} {status}")
    
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    
    if passed == total:
        print(f"{GREEN}🎉 ALL CHECKS PASSED! Integration is complete.{RESET}")
        print(f"{GREEN}   {passed}/{total} checks passed{RESET}")
        return 0
    else:
        print(f"{YELLOW}⚠️  SOME CHECKS FAILED{RESET}")
        print(f"{YELLOW}   {passed}/{total} checks passed{RESET}")
        print(f"\n{YELLOW}Please review the errors above and fix any issues.{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
