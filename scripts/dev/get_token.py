#!/usr/bin/env python3
"""
Token helper script for getting authentication tokens for testing.

Usage:
    # Get staging API key (if available)
    python scripts/get_token.py --base http://localhost:8000

    # Login with credentials to get JWT
    python scripts/get_token.py --base http://localhost:8000 --user admin --password admin123
    
    # Use environment variables
    ALGO_USER=admin ALGO_PASS=admin123 python scripts/get_token.py --base http://localhost:8000
"""

import argparse
import os
import sys
from typing import Optional

import requests


def get_staging_api_key() -> Optional[str]:
    """Get staging API key from environment if available."""
    return os.environ.get("STAGING_API_KEY")


def get_jwt_token(base_url: str, username: str, password: str) -> Optional[str]:
    """
    Get JWT token by logging in with credentials.
    
    Args:
        base_url: Base API URL
        username: Username for login
        password: Password for login
        
    Returns:
        JWT token string or None if login failed
    """
    try:
        login_url = f"{base_url.rstrip('/')}/api/v1/auth/login"
        
        # Use session for connection reuse
        with requests.Session() as session:
            response = session.post(
                login_url,
                json={"username": username, "password": password},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("access_token")
            else:
                print(f"Login failed: {response.status_code} - {response.text}", file=sys.stderr)
                return None
            
    except Exception as e:
        print(f"Error during login: {e}", file=sys.stderr)
        return None


def main():
    """Main function to handle token retrieval."""
    parser = argparse.ArgumentParser(
        description="Get authentication token for API testing"
    )
    parser.add_argument(
        "--base", 
        required=True,
        help="Base API URL (e.g., http://localhost:8000)"
    )
    parser.add_argument(
        "--user",
        help="Username for login (alternative to ALGO_USER env var)"
    )
    parser.add_argument(
        "--password", 
        help="Password for login (alternative to ALGO_PASS env var)"
    )
    parser.add_argument(
        "--type",
        choices=["jwt", "api-key", "auto"],
        default="auto",
        help="Type of token to retrieve (default: auto - try API key first, then JWT)"
    )
    
    args = parser.parse_args()
    
    # Auto mode: try staging API key first
    if args.type in ("auto", "api-key"):
        staging_key = get_staging_api_key()
        if staging_key:
            print(staging_key)
            return
        elif args.type == "api-key":
            print("No staging API key found in STAGING_API_KEY environment variable", file=sys.stderr)
            sys.exit(1)
    
    # JWT mode: get credentials and login
    if args.type in ("auto", "jwt"):
        username = args.user or os.environ.get("ALGO_USER")
        password = args.password or os.environ.get("ALGO_PASS")
        
        if not username or not password:
            print("Username and password required. Use --user/--password or set ALGO_USER/ALGO_PASS env vars", file=sys.stderr)
            sys.exit(1)
            
        token = get_jwt_token(args.base, username, password)
        if token:
            print(token)
        else:
            print("Failed to get JWT token", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()