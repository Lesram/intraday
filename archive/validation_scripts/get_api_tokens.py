#!/usr/bin/env python3
"""
Quick Token Generator for API Testing
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.infra.security import create_access_token

def get_admin_token():
    """Get admin token for API testing."""
    return create_access_token("admin", ["admin", "trader"])

def get_user_token():
    """Get user token for API testing."""
    return create_access_token("testuser", ["user", "trader"])

if __name__ == "__main__":
    print("API Authentication Tokens")
    print("=" * 40)
    
    admin_token = get_admin_token()
    user_token = get_user_token()
    
    print(f"Admin Token:")
    print(f"{admin_token}")
    print()
    print(f"User Token:")
    print(f"{user_token}")
    print()
    
    print("Usage:")
    print(f'curl -H "Authorization: Bearer {admin_token}" http://localhost:8000/api/v1/trading/signals')
