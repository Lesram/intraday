"""
Main Application Entry Point
Algorithmic Trading Platform

Note: Database initialization is handled in backend.api.factory.create_app()
via the FastAPI lifespan context manager. This ensures proper async initialization
and cleanup, as well as consistent behavior across all entry points.
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
    # NOTE: Database initialization is handled by FastAPI lifespan in factory.py
    # 
    # The factory.create_app() function configures the lifespan context manager
    # which properly initializes:
    # - Database engine and sessionmaker
    # - Outbox worker for background order processing  
    # - Alpaca WebSocket stream for real-time updates
    # - Portfolio and order sync on startup
    #
    # This ensures single-source-of-truth for initialization logic.
    # ============================================================================

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
