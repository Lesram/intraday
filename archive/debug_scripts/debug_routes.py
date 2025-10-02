#!/usr/bin/env python3
"""
Debug script to check available routes in the app
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.api.factory import create_app

def list_routes():
    """List all registered routes in the FastAPI app"""
    app = create_app()
    
    print("📋 Available Routes:")
    print("=" * 50)
    
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            methods = ', '.join(route.methods)
            print(f"{methods:12} {route.path}")
        elif hasattr(route, 'path'):
            print(f"{'MOUNT':12} {route.path}")
    
    print("\n📊 Route Summary:")
    print("=" * 50)
    print(f"Total routes: {len(app.routes)}")
    
    # Check for specific endpoints we need
    paths = [getattr(route, 'path', '') for route in app.routes]
    endpoints_to_check = ['/signals', '/signals/act', '/orders']
    
    for endpoint in endpoints_to_check:
        if any(endpoint in path for path in paths):
            print(f"✅ {endpoint} - Found")
        else:
            print(f"❌ {endpoint} - Missing")

if __name__ == "__main__":
    list_routes()