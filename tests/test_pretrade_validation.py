"""                                                                             
Automated Pre-Trade Validation Feature Tests
Tests all scenarios from MANUAL_TESTING_SCRIPT.md

NOTE: These are INTEGRATION tests that require a running backend server at localhost:8000.
Run the server first, then execute these tests.
"""

import pytest
import requests
import time
from typing import Dict, Any, List
from datetime import datetime


def _server_is_running() -> bool:
    """Check if the backend server is running."""
    try:
        resp = requests.get("http://localhost:8000/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


# Mark all tests in this module as requiring live server
pytestmark = pytest.mark.skipif(
    not _server_is_running(),
    reason="Pre-trade validation integration tests require running server at localhost:8000. "
           "Start server with 'python start_backend.py' then run these tests directly."
)

# Configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

# Test credentials
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Admin123!@#"

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def print_header(text: str):
    """Print a test section header"""
    print(f"\n{'='*80}")
    print(f"{Colors.BLUE}{text}{Colors.RESET}")
    print('='*80)

def print_test(test_num: int, name: str):
    """Print test name"""
    print(f"\n{Colors.YELLOW}Test {test_num}: {name}{Colors.RESET}")

def print_pass(message: str = "PASS"):
    """Print pass message"""
    print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")

def print_fail(message: str = "FAIL"):
    """Print fail message"""
    print(f"{Colors.RED}❌ {message}{Colors.RESET}")

def print_info(message: str):
    """Print info message"""
    print(f"   {message}")

class TestResults:
    """Track test results"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.tests = []
    
    def add_pass(self, test_name: str):
        self.passed += 1
        self.tests.append((test_name, "PASS"))
    
    def add_fail(self, test_name: str, reason: str = ""):
        self.failed += 1
        self.tests.append((test_name, f"FAIL: {reason}"))
    
    def add_skip(self, test_name: str, reason: str = ""):
        self.skipped += 1
        self.tests.append((test_name, f"SKIP: {reason}"))
    
    def summary(self):
        total = self.passed + self.failed + self.skipped
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        
        print_header("TEST SUMMARY")
        print(f"Total Tests: {total}")
        print(f"Passed: {Colors.GREEN}{self.passed}{Colors.RESET}")
        print(f"Failed: {Colors.RED}{self.failed}{Colors.RESET}")
        print(f"Skipped: {Colors.YELLOW}{self.skipped}{Colors.RESET}")
        print(f"Pass Rate: {pass_rate:.1f}%")
        
        if self.failed > 0:
            print(f"\n{Colors.RED}Failed Tests:{Colors.RESET}")
            for name, result in self.tests:
                if "FAIL" in result:
                    print(f"  - {name}: {result}")

# Global results tracker
results = TestResults()

def login() -> str:
    """Login and return access token"""
    print_header("AUTHENTICATION")
    print_info("Logging in...")
    
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={
                "username": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            print_pass(f"Logged in as {ADMIN_EMAIL}")
            return token
        else:
            print_fail(f"Login failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print_fail(f"Login error: {e}")
        return None

def validate_order(token: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an order"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(
            f"{API_BASE}/orders/validate",
            json=order_data,
            headers=headers
        )
        return {
            "status_code": response.status_code,
            "data": response.json() if response.status_code == 200 else None,
            "error": response.text if response.status_code != 200 else None
        }
    except Exception as e:
        return {
            "status_code": 0,
            "data": None,
            "error": str(e)
        }

def submit_order(token: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Submit an order"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(
            f"{API_BASE}/orders",
            json=order_data,
            headers=headers
        )
        return {
            "status_code": response.status_code,
            "data": response.json() if response.status_code in [200, 201] else None,
            "error": response.text if response.status_code not in [200, 201] else None
        }
    except Exception as e:
        return {
            "status_code": 0,
            "data": None,
            "error": str(e)
        }

# Test Functions

def test_valid_market_buy(token: str):
    """Test 1: Valid Market Buy Order"""
    print_test(1, "Valid Market Buy Order")
    
    order = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10,
        "orderType": "market",
        "timeInForce": "gtc"
    }
    
    # Validate
    result = validate_order(token, order)
    
    if result["status_code"] == 200:
        data = result["data"]
        checks = data.get("checks", [])  # Changed from "validation_checks"
        all_passed = all(check.get("passed", False) for check in checks)
        
        if all_passed:
            print_pass(f"Validation passed with {len(checks)} checks")
            results.add_pass("Test 1: Valid Market Buy")
        else:
            failed_checks = [c["name"] for c in checks if not c.get("passed", False)]
            print_fail(f"Some checks failed: {', '.join(failed_checks)}")
            results.add_fail("Test 1: Valid Market Buy", "Validation checks failed")
    else:
        print_fail(f"Validation failed: {result['status_code']} - {result['error']}")
        results.add_fail("Test 1: Valid Market Buy", f"Status {result['status_code']}")

def test_invalid_symbol(token: str):
    """Test 2: Invalid Symbol"""
    print_test(2, "Invalid Symbol (Empty)")
    
    order = {
        "symbol": "",
        "side": "buy",
        "quantity": 10,
        "orderType": "market",
        "timeInForce": "gtc"
    }
    
    result = validate_order(token, order)
    
    # Should fail validation
    if result["status_code"] in [400, 422]:
        print_pass("Correctly rejected empty symbol")
        results.add_pass("Test 2: Invalid Symbol")
    elif result["status_code"] == 200:
        data = result["data"]
        checks = data.get("checks", [])
        symbol_check = next((c for c in checks if "symbol" in c.get("name", "").lower()), None)
        
        if symbol_check and not symbol_check.get("passed", True):
            print_pass("Symbol validation check failed as expected")
            results.add_pass("Test 2: Invalid Symbol")
        else:
            print_fail("Empty symbol was not caught by validation")
            results.add_fail("Test 2: Invalid Symbol", "Empty symbol accepted")
    else:
        print_fail(f"Unexpected response: {result['status_code']}")
        results.add_fail("Test 2: Invalid Symbol", f"Status {result['status_code']}")

def test_zero_quantity(token: str):
    """Test 3: Zero Quantity"""
    print_test(3, "Zero Quantity")
    
    order = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 0,
        "orderType": "market",
        "timeInForce": "gtc"
    }
    
    result = validate_order(token, order)
    
    # Should fail validation
    if result["status_code"] in [400, 422]:
        print_pass("Correctly rejected zero quantity")
        results.add_pass("Test 3: Zero Quantity")
    elif result["status_code"] == 200:
        data = result["data"]
        checks = data.get("checks", [])
        qty_check = next((c for c in checks if "quantity" in c.get("name", "").lower()), None)
        
        if qty_check and not qty_check.get("passed", True):
            print_pass("Quantity validation check failed as expected")
            results.add_pass("Test 3: Zero Quantity")
        else:
            print_fail("Zero quantity was not caught by validation")
            results.add_fail("Test 3: Zero Quantity", "Zero quantity accepted")
    else:
        print_fail(f"Unexpected response: {result['status_code']}")
        results.add_fail("Test 3: Zero Quantity", f"Status {result['status_code']}")

def test_insufficient_funds(token: str):
    """Test 4: Large Order (Insufficient Funds)"""
    print_test(4, "Large Order (Insufficient Funds)")
    
    order = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10000,
        "orderType": "market",
        "timeInForce": "gtc"
    }
    
    result = validate_order(token, order)
    
    if result["status_code"] == 200:
        data = result["data"]
        checks = data.get("checks", [])
        buying_power_check = next((c for c in checks if "buying power" in c.get("name", "").lower()), None)
        
        if buying_power_check and not buying_power_check.get("passed", True):
            print_pass("Buying power check failed as expected")
            results.add_pass("Test 4: Insufficient Funds")
        else:
            print_fail("Large order was not caught by buying power check")
            results.add_fail("Test 4: Insufficient Funds", "Buying power check passed incorrectly")
    else:
        print_fail(f"Validation request failed: {result['status_code']}")
        results.add_fail("Test 4: Insufficient Funds", f"Status {result['status_code']}")

def test_limit_order(token: str):
    """Test 5: Limit Order with Price"""
    print_test(5, "Limit Order with Price")
    
    order = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 5,
        "orderType": "limit",
        "limitPrice": 150.00,
        "timeInForce": "gtc"
    }
    
    result = validate_order(token, order)
    
    if result["status_code"] == 200:
        data = result["data"]
        checks = data.get("checks", [])
        all_passed = all(check.get("passed", False) for check in checks)
        
        if all_passed:
            print_pass(f"Limit order validation passed")
            results.add_pass("Test 5: Limit Order")
        else:
            failed_checks = [c["name"] for c in checks if not c.get("passed", False)]
            print_fail(f"Some checks failed: {', '.join(failed_checks)}")
            results.add_fail("Test 5: Limit Order", "Validation checks failed")
    else:
        print_fail(f"Validation failed: {result['status_code']}")
        results.add_fail("Test 5: Limit Order", f"Status {result['status_code']}")

def test_checks_count(token: str):
    """Test 8: Validation Checks Display"""
    print_test(8, "Validation Checks Count")
    
    order = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10,
        "orderType": "market",
        "timeInForce": "gtc"
    }
    
    result = validate_order(token, order)
    
    if result["status_code"] == 200:
        data = result["data"]
        checks = data.get("checks", [])
        check_count = len(checks)
        
        if check_count >= 6:
            print_pass(f"Found {check_count} validation checks (expected 6-8)")
            print_info(f"Checks: {', '.join([c.get('name', 'Unknown') for c in checks])}")
            results.add_pass("Test 8: Validation Checks")
        else:
            print_fail(f"Only {check_count} checks found (expected 6-8)")
            results.add_fail("Test 8: Validation Checks", f"Only {check_count} checks")
    else:
        print_fail(f"Validation failed: {result['status_code']}")
        results.add_fail("Test 8: Validation Checks", f"Status {result['status_code']}")

def test_cost_estimation(token: str):
    """Test 9: Cost Summary Display"""
    print_test(9, "Cost Estimation")
    
    order = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 10,
        "orderType": "market",
        "timeInForce": "gtc"
    }
    
    result = validate_order(token, order)
    
    if result["status_code"] == 200:
        data = result["data"]
        estimated_cost = data.get("estimated_cost")
        estimated_buying_power_after = data.get("estimated_buying_power_after")
        
        if estimated_cost is not None and estimated_buying_power_after is not None:
            print_pass(f"Cost estimation: ${estimated_cost:,.2f}")
            print_info(f"Buying power after: ${estimated_buying_power_after:,.2f}")
            results.add_pass("Test 9: Cost Estimation")
        else:
            print_fail("Cost estimation fields missing")
            results.add_fail("Test 9: Cost Estimation", "Missing cost fields")
    else:
        print_fail(f"Validation failed: {result['status_code']}")
        results.add_fail("Test 9: Cost Estimation", f"Status {result['status_code']}")

def run_all_tests():
    """Run all automated tests"""
    print_header("PRE-TRADE VALIDATION AUTOMATED TESTS")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Backend: {BASE_URL}")
    
    # Login
    token = login()
    if not token:
        print_fail("Cannot proceed without authentication")
        return
    
    # Run tests
    print_header("RUNNING TESTS")
    
    test_valid_market_buy(token)
    test_invalid_symbol(token)
    test_zero_quantity(token)
    test_insufficient_funds(token)
    test_limit_order(token)
    test_checks_count(token)
    test_cost_estimation(token)
    
    # Summary
    results.summary()
    
    # Return exit code
    return 0 if results.failed == 0 else 1

if __name__ == "__main__":
    exit_code = run_all_tests()
    exit(exit_code)


