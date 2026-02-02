"""
Test Credentials Helper

Provides centralized test credential management for all test files.
Credentials are read from environment variables (set by conftest.py).

Usage in tests:
    from test.test_credentials import get_test_admin_credentials, get_test_login_data
    
    # Get credentials tuple
    username, password = get_test_admin_credentials()
    
    # Get login dictionary for API requests
    login_data = get_test_login_data()
    response = requests.post(f"{base_url}/api/v1/auth/login", json=login_data)
"""

import os


def get_test_admin_credentials() -> tuple[str, str]:
    """
    Get test admin credentials from environment variables.
    
    Environment variables are set by test/conftest.py before tests run.
    
    Returns:
        Tuple of (username, password)
    
    Environment Variables:
        TEST_ADMIN_USERNAME: Admin username (default: testadmin)
        TEST_ADMIN_PASSWORD: Admin password (default: TestP@ssw0rd123)
    """
    username = os.getenv("TEST_ADMIN_USERNAME", "testadmin")
    password = os.getenv("TEST_ADMIN_PASSWORD", "TestP@ssw0rd123")
    return username, password


def get_test_login_data() -> dict[str, str]:
    """
    Get test login data as a dictionary for API requests.
    
    Returns:
        Dictionary with 'username' and 'password' keys
    """
    username, password = get_test_admin_credentials()
    return {"username": username, "password": password}


# Module-level constants for backwards compatibility with existing tests
TEST_USERNAME, TEST_PASSWORD = get_test_admin_credentials()

