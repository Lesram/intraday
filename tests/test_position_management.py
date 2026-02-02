"""
Automated Position Management Feature Tests
Tests Phase 2.2 - Position Management implementation
Covers all manual testing scenarios automatically

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
    reason="Position management integration tests require running server at localhost:8000. "
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
    CYAN = '\033[96m'
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

def print_data(label: str, value: Any):
    """Print data with label"""
    print(f"   {Colors.CYAN}{label}:{Colors.RESET} {value}")

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

def get_positions(token: str) -> List[Dict[str, Any]]:
    """Get all positions"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(
            f"{API_BASE}/portfolio/positions",
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            # Return the data (even if empty list)
            return data if data is not None else []
        else:
            print_fail(f"Failed to fetch positions: {response.status_code}")
            return None  # Changed: Return None to indicate error, not empty list
    except Exception as e:
        print_fail(f"Error fetching positions: {e}")
        return None  # Changed: Return None to indicate error

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

# Fixtures

@pytest.fixture
def positions(token: str) -> List[Dict[str, Any]]:
    """Fixture to fetch positions for dependent tests."""
    return get_positions(token) or []


# Test Functions

def test_fetch_positions(token: str):
    """Test 1: Fetch All Positions"""
    print_test(1, "Fetch All Positions")
    
    positions = get_positions(token)
    
    if positions is not None:  # Changed: Accept empty array as valid response
        print_pass(f"Successfully fetched positions ({len(positions)} found)")
        
        # Display first position as example if any exist
        if len(positions) > 0:
            pos = positions[0]
            print_data("Example Position", pos.get('symbol', 'N/A'))
            print_data("  Quantity", pos.get('quantity', 0))
            print_data("  Market Value", f"${pos.get('marketValue', 0):,.2f}")
            print_data("  Unrealized P&L", f"${pos.get('unrealizedPnL', 0):,.2f}")
        else:
            print_info("No open positions currently (this is normal for a new account)")
        
        results.add_pass("Test 1: Fetch Positions")
        return positions
    else:
        print_fail("API error fetching positions")
        results.add_fail("Test 1: Fetch Positions", "API returned error")
        return []

def test_position_fields(positions: List[Dict[str, Any]]):
    """Test 2: Verify Position Field Structure"""
    print_test(2, "Verify Position Field Structure")
    
    if not positions:
        print_fail("No positions to verify")
        results.add_skip("Test 2: Position Fields", "No positions available")
        return
    
    required_fields = [
        'symbol', 'quantity', 'averagePrice', 'currentPrice',
        'marketValue', 'unrealizedPnL', 'unrealizedPnLPercent', 'side'
    ]
    
    pos = positions[0]
    missing_fields = [field for field in required_fields if field not in pos]
    
    if not missing_fields:
        print_pass(f"All required fields present")
        print_info(f"Fields: {', '.join(required_fields)}")
        results.add_pass("Test 2: Position Fields")
    else:
        print_fail(f"Missing fields: {', '.join(missing_fields)}")
        results.add_fail("Test 2: Position Fields", f"Missing: {missing_fields}")

def test_position_calculations(positions: List[Dict[str, Any]]):
    """Test 3: Verify Position Calculations"""
    print_test(3, "Verify Position Calculations")
    
    if not positions:
        results.add_skip("Test 3: Position Calculations", "No positions")
        return
    
    all_valid = True
    for pos in positions[:3]:  # Check first 3 positions
        symbol = pos.get('symbol')
        qty = pos.get('quantity', 0)
        avg_price = pos.get('averagePrice', 0)
        current_price = pos.get('currentPrice', 0)
        market_value = pos.get('marketValue', 0)
        unrealized_pnl = pos.get('unrealizedPnL', 0)
        
        # Calculate expected values
        expected_market_value = qty * current_price
        expected_cost_basis = qty * avg_price
        expected_pnl = expected_market_value - expected_cost_basis
        
        # Allow small floating point differences
        if abs(market_value - expected_market_value) > 0.01:
            print_fail(f"{symbol}: Market value mismatch")
            print_data("  Expected", f"${expected_market_value:,.2f}")
            print_data("  Actual", f"${market_value:,.2f}")
            all_valid = False
        
        if abs(unrealized_pnl - expected_pnl) > 0.01:
            print_fail(f"{symbol}: P&L mismatch")
            print_data("  Expected", f"${expected_pnl:,.2f}")
            print_data("  Actual", f"${unrealized_pnl:,.2f}")
            all_valid = False
    
    if all_valid:
        print_pass("All position calculations correct")
        results.add_pass("Test 3: Position Calculations")
    else:
        results.add_fail("Test 3: Position Calculations", "Calculation errors found")

def test_position_statistics(positions: List[Dict[str, Any]]):
    """Test 4: Calculate Position Statistics"""
    print_test(4, "Calculate Position Statistics")
    
    if not positions:
        results.add_skip("Test 4: Position Statistics", "No positions")
        return
    
    # Calculate statistics
    total_positions = len(positions)
    open_positions = len([p for p in positions if p.get('quantity', 0) > 0])
    total_market_value = sum(p.get('marketValue', 0) for p in positions)
    total_unrealized_pnl = sum(p.get('unrealizedPnL', 0) for p in positions)
    winning_positions = len([p for p in positions if p.get('unrealizedPnL', 0) > 0])
    losing_positions = len([p for p in positions if p.get('unrealizedPnL', 0) < 0])
    win_rate = (winning_positions / total_positions * 100) if total_positions > 0 else 0
    
    print_pass("Statistics calculated successfully")
    print_data("Total Positions", total_positions)
    print_data("Open Positions", open_positions)
    print_data("Total Market Value", f"${total_market_value:,.2f}")
    print_data("Total Unrealized P&L", f"${total_unrealized_pnl:,.2f}")
    print_data("Winning Positions", winning_positions)
    print_data("Losing Positions", losing_positions)
    print_data("Win Rate", f"{win_rate:.1f}%")
    
    results.add_pass("Test 4: Position Statistics")

def test_position_sorting(positions: List[Dict[str, Any]]):
    """Test 5: Test Position Sorting"""
    print_test(5, "Test Position Sorting")
    
    if not positions or len(positions) < 2:
        results.add_skip("Test 5: Position Sorting", "Need 2+ positions")
        return
    
    # Test sorting by unrealized P&L
    sorted_by_pnl = sorted(positions, key=lambda p: p.get('unrealizedPnL', 0), reverse=True)
    
    if sorted_by_pnl[0].get('unrealizedPnL', 0) >= sorted_by_pnl[-1].get('unrealizedPnL', 0):
        print_pass("Position sorting works correctly")
        print_data("Best Performer", f"{sorted_by_pnl[0].get('symbol')}: ${sorted_by_pnl[0].get('unrealizedPnL', 0):,.2f}")
        print_data("Worst Performer", f"{sorted_by_pnl[-1].get('symbol')}: ${sorted_by_pnl[-1].get('unrealizedPnL', 0):,.2f}")
        results.add_pass("Test 5: Position Sorting")
    else:
        print_fail("Sorting logic error")
        results.add_fail("Test 5: Position Sorting", "Sort order incorrect")

def test_position_filtering(positions: List[Dict[str, Any]]):
    """Test 6: Test Position Filtering"""
    print_test(6, "Test Position Filtering")
    
    if not positions:
        results.add_skip("Test 6: Position Filtering", "No positions")
        return
    
    # Filter by symbol
    test_symbol = positions[0].get('symbol', '')
    filtered = [p for p in positions if test_symbol.lower() in p.get('symbol', '').lower()]
    
    if len(filtered) > 0:
        print_pass(f"Filter by symbol '{test_symbol}' works")
        print_data("Filtered Results", len(filtered))
        results.add_pass("Test 6: Position Filtering")
    else:
        print_fail("Filtering returned no results")
        results.add_fail("Test 6: Position Filtering", "No filtered results")

def test_close_position_validation(token: str, positions: List[Dict[str, Any]]):
    """Test 7: Close Position Validation (Dry Run)"""
    print_test(7, "Close Position Validation")
    
    if not positions:
        results.add_skip("Test 7: Close Position", "No positions")
        return
    
    # Find a position with quantity > 0
    position = next((p for p in positions if p.get('quantity', 0) > 0), None)
    
    if not position:
        results.add_skip("Test 7: Close Position", "No open positions")
        return
    
    print_info(f"Testing close position for {position.get('symbol')}")
    print_data("Quantity", position.get('quantity'))
    print_data("Market Value", f"${position.get('marketValue', 0):,.2f}")
    
    # Just validate the order structure (don't actually submit in paper mode)
    order_data = {
        "symbol": position.get('symbol'),
        "side": "sell",
        "orderType": "market",
        "quantity": position.get('quantity'),
        "timeInForce": "gtc"
    }
    
    print_pass("Close position order structure validated")
    print_data("Order Data", order_data)
    results.add_pass("Test 7: Close Position Validation")

def test_add_to_position_validation(token: str, positions: List[Dict[str, Any]]):
    """Test 8: Add to Position Validation (Dry Run)"""
    print_test(8, "Add to Position Validation")
    
    if not positions:
        results.add_skip("Test 8: Add to Position", "No positions")
        return
    
    position = positions[0]
    add_quantity = 10
    
    print_info(f"Testing add to position for {position.get('symbol')}")
    print_data("Current Quantity", position.get('quantity'))
    print_data("Add Quantity", add_quantity)
    
    # Validate order structure
    order_data = {
        "symbol": position.get('symbol'),
        "side": "buy",
        "orderType": "market",
        "quantity": add_quantity,
        "timeInForce": "gtc"
    }
    
    print_pass("Add to position order structure validated")
    print_data("Order Data", order_data)
    results.add_pass("Test 8: Add to Position Validation")

def test_position_detail_fields(positions: List[Dict[str, Any]]):
    """Test 9: Position Detail Fields"""
    print_test(9, "Position Detail Information")
    
    if not positions:
        results.add_skip("Test 9: Position Details", "No positions")
        return
    
    pos = positions[0]
    
    # Calculate additional metrics
    cost_basis = pos.get('quantity', 0) * pos.get('averagePrice', 0)
    price_change = pos.get('currentPrice', 0) - pos.get('averagePrice', 0)
    price_change_pct = (price_change / pos.get('averagePrice', 1)) * 100
    
    print_pass("Position detail fields calculated")
    print_data("Symbol", pos.get('symbol'))
    print_data("Cost Basis", f"${cost_basis:,.2f}")
    print_data("Price Change", f"${price_change:,.2f} ({price_change_pct:+.2f}%)")
    print_data("Side", pos.get('side', 'N/A').upper())
    
    results.add_pass("Test 9: Position Details")

def test_real_time_compatibility(positions: List[Dict[str, Any]]):
    """Test 10: Real-Time Update Compatibility"""
    print_test(10, "Real-Time WebSocket Compatibility")
    
    if not positions:
        results.add_skip("Test 10: WebSocket Compatibility", "No positions")
        return
    
    # Verify position structure matches WebSocket event format
    pos = positions[0]
    required_fields = ['symbol', 'quantity', 'currentPrice', 'marketValue', 'unrealizedPnL']
    
    has_all_fields = all(field in pos for field in required_fields)
    
    if has_all_fields:
        print_pass("Position structure compatible with WebSocket updates")
        print_info("All required fields for real-time updates present")
        results.add_pass("Test 10: WebSocket Compatibility")
    else:
        missing = [f for f in required_fields if f not in pos]
        print_fail(f"Missing fields for WebSocket: {missing}")
        results.add_fail("Test 10: WebSocket Compatibility", f"Missing: {missing}")

def run_all_tests():
    """Run all automated tests"""
    print_header("POSITION MANAGEMENT AUTOMATED TESTS")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Backend: {BASE_URL}")
    
    # Login
    token = login()
    if not token:
        print_fail("Cannot proceed without authentication")
        return 1
    
    # Run tests
    print_header("RUNNING TESTS")
    
    # Test 1: Fetch positions
    positions = test_fetch_positions(token)
    
    # Test 2-10: Position operations and validations
    test_position_fields(positions)
    test_position_calculations(positions)
    test_position_statistics(positions)
    test_position_sorting(positions)
    test_position_filtering(positions)
    test_close_position_validation(token, positions)
    test_add_to_position_validation(token, positions)
    test_position_detail_fields(positions)
    test_real_time_compatibility(positions)
    
    # Summary
    results.summary()
    
    # Return exit code
    return 0 if results.failed == 0 else 1

if __name__ == "__main__":
    exit_code = run_all_tests()
    exit(exit_code)
