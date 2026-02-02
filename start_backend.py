"""
Debug script to start backend with detailed error logging
"""
import sys
import traceback
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

try:
    logger.info("Importing uvicorn...")
    import uvicorn
    
    logger.info("Importing backend app...")
    from backend.api.main import socketio_app
    
    logger.info("App imported successfully!")
    logger.info(f"App: {socketio_app}")
    
    logger.info("Starting uvicorn server...")
    uvicorn.run(
        socketio_app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )
    
except Exception as e:
    logger.error(f"Failed to start backend: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)
