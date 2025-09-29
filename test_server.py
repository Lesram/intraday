#!/usr/bin/env python3
"""
Test server to debug the JWT authentication issue.
"""
import os
import uvicorn
from contextlib import asynccontextmanager
from backend.api.factory import create_app

if __name__ == "__main__":
    # Set the JWT secret
    os.environ["SECURITY_JWT_SECRET"] = "your-super-secret-jwt-key-for-development-only-change-in-production"
    
    # Create the app
    app = create_app()
    print("✅ App created successfully")
    
    # Replace lifespan with a simple no-op to avoid outbox worker issues
    @asynccontextmanager
    async def simple_lifespan(app):
        print("✅ Simple lifespan: startup")
        yield
        print("✅ Simple lifespan: shutdown")
    
    app.router.lifespan_context = simple_lifespan
    print("✅ Lifespan replaced to prevent startup issues")
    
    # Start the server
    print("🚀 Starting server on http://127.0.0.1:8001...")
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")