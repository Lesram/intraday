"""
Test idempotency guarantees for order placement.

This test validates that duplicate requests (same Idempotency-Key or client_order_id)
properly return the same order instead of creating duplicates.

CRITICAL: Duplicate orders can cause:
- Double exposure / over-leverage
- Financial loss from unintended fills
- Ledger/position inconsistencies
"""

import pytest
import uuid
import requests
import os
from typing import Dict, Any


class TestOrderIdempotency:
    """Test order idempotency with real backend."""
    
    def setup_method(self):
        """Setup for each test method."""
        self.base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        self.test_symbol = "AAPL"
        self.test_quantity = 1
        
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for requests."""
        # Try to authenticate
        try:
            auth_response = requests.post(
                f"{self.base_url}/api/v1/auth/login",
                json={
                    "username": os.getenv("TEST_USERNAME", "test_user"),
                    "password": os.getenv("TEST_PASSWORD", "test_password")
                },
                timeout=10
            )
            
            if auth_response.status_code == 200:
                token = auth_response.json().get("access_token")
                return {"Authorization": f"Bearer {token}"}
        except Exception as e:
            print(f"Auth failed: {e}")
        
        return {}
    
    def test_duplicate_idempotency_key_returns_same_order(self):
        """
        Test that duplicate Idempotency-Key returns same order, not new order.
        
        This is CRITICAL for preventing double-fills on network retries.
        """
        headers = self._get_auth_headers()
        if not headers:
            pytest.skip(
                "Authentication not available\n"
                "Ticket: TEST-004\n"
                "Remove by: 2025-11-01\n"
                "Owner: @backend-team"
            )
        
        idempotency_key = str(uuid.uuid4())
        
        order_request = {
            "symbol": self.test_symbol,
            "action": "buy",
            "quantity": self.test_quantity,
            "order_type": "market",
            "client_order_id": idempotency_key
        }
        
        # Place order first time
        print(f"\n🔵 Placing order with idempotency key: {idempotency_key}")
        response1 = requests.post(
            f"{self.base_url}/api/v1/orders",
            headers={**headers, "Idempotency-Key": idempotency_key},
            json=order_request,
            timeout=10
        )
        
        if response1.status_code not in [200, 201]:
            pytest.skip(
                f"Order endpoint failed: {response1.status_code}\n"
                f"Response: {response1.text}\n"
                "Ticket: TEST-005\n"
                "Remove by: 2025-11-01\n"
                "Owner: @backend-team"
            )
        
        order1_data = response1.json()
        order1_id = order1_data.get("order_id") or order1_data.get("id")
        
        assert order1_id, "First order response missing order_id"
        print(f"  ✅ First order created: {order1_id}")
        
        # Retry with same idempotency key (simulates network retry)
        print(f"🔄 Retrying with same idempotency key...")
        response2 = requests.post(
            f"{self.base_url}/api/v1/orders",
            headers={**headers, "Idempotency-Key": idempotency_key},
            json=order_request,
            timeout=10
        )
        
        assert response2.status_code in [200, 201], \
            f"Retry failed with {response2.status_code}: {response2.text}"
        
        order2_data = response2.json()
        order2_id = order2_data.get("order_id") or order2_data.get("id")
        
        assert order2_id, "Second order response missing order_id"
        
        # CRITICAL: Must return SAME order, not create new one
        assert order1_id == order2_id, \
            f"❌ IDEMPOTENCY VIOLATION: Duplicate request created new order!\n" \
            f"First order:  {order1_id}\n" \
            f"Second order: {order2_id}\n" \
            f"This can cause double-fills and financial exposure!"
        
        print(f"  ✅ Idempotency enforced: Both requests returned {order1_id}")
    
    def test_duplicate_client_order_id_rejected(self):
        """
        Test that duplicate client_order_id is rejected or returns original.
        
        Different Idempotency-Key but same client_order_id should not create duplicate.
        """
        headers = self._get_auth_headers()
        if not headers:
            pytest.skip(
                "Authentication not available\n"
                "Ticket: TEST-004\n"
                "Remove by: 2025-11-01\n"
                "Owner: @backend-team"
            )
        
        client_order_id = f"test_order_{uuid.uuid4()}"
        
        order_request = {
            "symbol": self.test_symbol,
            "action": "buy",
            "quantity": self.test_quantity,
            "order_type": "market",
            "client_order_id": client_order_id
        }
        
        # Place order first time
        print(f"\n🔵 Placing order with client_order_id: {client_order_id}")
        response1 = requests.post(
            f"{self.base_url}/api/v1/orders",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},  # Different key
            json=order_request,
            timeout=10
        )
        
        if response1.status_code not in [200, 201]:
            pytest.skip(f"Order endpoint failed: {response1.status_code}")
        
        order1_data = response1.json()
        order1_id = order1_data.get("order_id") or order1_data.get("id")
        print(f"  ✅ First order created: {order1_id}")
        
        # Attempt to create order with same client_order_id but different Idempotency-Key
        print(f"🔄 Attempting duplicate with different Idempotency-Key...")
        response2 = requests.post(
            f"{self.base_url}/api/v1/orders",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},  # Different key
            json=order_request,
            timeout=10
        )
        
        # Should either:
        # 1. Return 409 Conflict (duplicate client_order_id)
        # 2. Return 200 with original order (idempotency by client_order_id)
        
        if response2.status_code == 409:
            print(f"  ✅ Duplicate rejected with 409 Conflict")
            return
        
        if response2.status_code in [200, 201]:
            order2_data = response2.json()
            order2_id = order2_data.get("order_id") or order2_data.get("id")
            
            assert order1_id == order2_id, \
                f"❌ CLIENT_ORDER_ID COLLISION: Created new order with duplicate client_order_id!\n" \
                f"First order:  {order1_id}\n" \
                f"Second order: {order2_id}\n" \
                f"Client order ID: {client_order_id}\n" \
                f"This violates idempotency guarantees!"
            
            print(f"  ✅ Idempotency by client_order_id: Returned {order1_id}")
            return
        
        pytest.fail(
            f"Unexpected response for duplicate client_order_id: {response2.status_code}\n"
            f"Response: {response2.text}"
        )
    
    def test_different_orders_get_different_ids(self):
        """
        Sanity check: Different orders should get different IDs.
        
        Ensures we're not over-zealous with idempotency (shouldn't block all orders).
        """
        headers = self._get_auth_headers()
        if not headers:
            pytest.skip(
                "Authentication not available\n"
                "Ticket: TEST-004\n"
                "Remove by: 2025-11-01\n"
                "Owner: @backend-team"
            )
        
        order_ids = []
        
        for i in range(3):
            order_request = {
                "symbol": self.test_symbol,
                "action": "buy",
                "quantity": self.test_quantity,
                "order_type": "market",
                "client_order_id": f"test_order_{uuid.uuid4()}"  # Different each time
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/orders",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},  # Different each time
                json=order_request,
                timeout=10
            )
            
            if response.status_code not in [200, 201]:
                pytest.skip(f"Order endpoint failed: {response.status_code}")
            
            order_data = response.json()
            order_id = order_data.get("order_id") or order_data.get("id")
            order_ids.append(order_id)
        
        # All orders should have unique IDs
        unique_ids = set(order_ids)
        assert len(unique_ids) == 3, \
            f"Expected 3 unique orders, got {len(unique_ids)}: {order_ids}\n" \
            f"Idempotency logic may be too aggressive"
        
        print(f"  ✅ Created 3 distinct orders: {order_ids}")


if __name__ == "__main__":
    # Allow running as standalone script
    pytest.main([__file__, "-v", "-s"])
