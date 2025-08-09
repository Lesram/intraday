"""
Main Application Entry Point
Algorithmic Trading Platform
"""
import asyncio
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
    print(f"API Server: http://localhost:8000")
    print(f"Documentation: http://localhost:8000/docs")
    print("=" * 50)
    
    # Start the FastAPI server
    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.environment == "development" else False,
        log_level="info",
        access_log=True
    )

if __name__ == "__main__":
    main()
