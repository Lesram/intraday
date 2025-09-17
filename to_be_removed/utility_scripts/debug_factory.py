#!/usr/bin/env python3

"""Test if there's an import error in factory"""

import traceback

try:
    from backend.api.factory import create_app
    print("Factory import successful")
    
    app = create_app()
    print("App creation successful")
    
    print("Routes:")
    for route in app.routes:
        if "portfolio" in route.path.lower():
            print(f"  {route.methods} {route.path}")
            
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
