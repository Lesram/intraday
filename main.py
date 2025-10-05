"""
Main Application Entry Point
Algorithmic Trading Platform
"""
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)

# Create logs directory
Path('logs').mkdir(exist_ok=True)

def main():
    """Main application entry point"""
    import uvicorn

    from backend.config import get_settings

    settings = get_settings()

    print("🚀 Starting Algorithmic Trading Platform")
    print("=" * 50)
    print(f"Environment: {settings.environment}")
    print("API Server: http://localhost:8000")
    print("Documentation: http://localhost:8000/docs")
    print("WebSocket: ws://localhost:8000/socket.io")
    print("=" * 50)
    
    # ============================================================================
    # CRITICAL FIX: Initialize database BEFORE starting uvicorn
    # Socket.IO wrapper doesn't forward ASGI lifespan events properly!
    # ============================================================================
    try:
        from backend.infra.db import init_db
        
        # Get database URL from settings
        database_url = None
        if hasattr(settings, 'database') and hasattr(settings.database, 'url'):
            database_url = settings.database.url
        elif hasattr(settings, 'data') and hasattr(settings.data, 'database_url'):
            database_url = settings.data.database_url
        else:
            import os
            database_url = os.getenv('DATABASE_URL')
        
        if database_url:
            print(f"📊 Initializing database: {database_url.split('@')[0]}@...")
            engine, sessionmaker = init_db(database_url)
            print("✅ Database initialized successfully")
            
            # Store in app.state for access by the app
            from backend.api.main import app
            app.state.sessionmaker = sessionmaker
            app.state.db_sessionmaker = sessionmaker  # Backward compatibility
            
        else:
            print("⚠️ No DATABASE_URL configured, skipping database initialization")
            
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        print("   Server will start but database features may not work")
        import traceback
        traceback.print_exc()

    # Start the FastAPI server with Socket.IO support
    uvicorn.run(
        "backend.api.main:socketio_app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.environment == "development" else False,
        log_level="info",
        access_log=True
    )

if __name__ == "__main__":
    main()
