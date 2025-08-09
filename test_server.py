#!/usr/bin/env python3
"""Quick test of the FastAPI application"""

import uvicorn
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    uvicorn.run(
        "backend.api.main:app",
        host="127.0.0.1",
        port=8080,
        log_level="info",
        reload=False
    )
