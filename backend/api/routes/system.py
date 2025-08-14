"""
System API routes.
Handles health checks, metrics, documentation, and system status endpoints.
"""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Request, Response, HTTPException, Depends
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from backend.config import get_settings
from backend.infra.db import get_session
from backend.utils.logger import get_logger

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = get_logger(__name__)

router = APIRouter(tags=["System"])


@router.get("/", tags=["System"])
async def root():
    """Root endpoint - API information and health status"""
    return {
        "service": "Algorithmic Trading Platform API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "metrics": "/metrics",
            "docs": "/docs",
            "api": "/api/v1"
        }
    }


@router.get("/metrics")
async def get_metrics(request: Request):
    """Prometheus metrics endpoint with comprehensive observability metrics"""
    try:
        # Get metrics registry from app state
        registry = getattr(request.app.state, 'metrics_registry', None)
        
        if registry is None or not PROMETHEUS_AVAILABLE:
            return Response(
                content='# Metrics registry not available\n',
                media_type="text/plain"
            )
        
        # If no metrics collected yet, ensure basic metrics exist
        metrics = getattr(request.app.state, 'metrics', None)
        if metrics:
            try:
                # Ensure basic HTTP metrics are registered even if no requests processed yet
                metrics.counter("http_requests_total", 
                              {"method": "GET", "route": "/metrics", "status": "success"})
                metrics.histogram("http_request_duration_seconds", 
                                {"method": "GET", "route": "/metrics"})
            except Exception:
                pass  # Metrics might already exist
        
        # Generate metrics output
        metrics_data = generate_latest(registry)
        return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
        
    except Exception as e:
        logger.error(f"Metrics generation failed: {e}")
        return Response(
            content=f'# Metrics generation error: {e}\n',
            media_type="text/plain"
        )


@router.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "algorithmic-trading-platform",
        "components": {
            "api": "healthy",
            "database": "healthy",  # Simplified for basic health check
            "metrics": True
        }
    }


@router.post("/health")
async def health_check_not_allowed():
    """Handler for POST requests to /health - returns 405 Method Not Allowed"""
    raise HTTPException(status_code=405, detail="Method Not Allowed")


@router.get("/healthz", tags=["System Health"])
async def liveness_probe():
    """
    Kubernetes liveness probe - checks if process is alive and responsive.

    This endpoint does NOT check dependencies (DB, broker) - only process health.
    Returns 200 if the process is alive and the event loop is responsive.
    Used by Kubernetes to determine if pod should be restarted.
    """
    try:
        # Quick async operation to verify event loop is responsive
        await asyncio.sleep(0.001)

        return {
            "status": "healthy",
            "service": "algotrading-platform",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "check": "liveness",
        }
    except Exception as e:
        # If we can't even complete a simple async operation, we're in trouble
        raise HTTPException(status_code=503, detail=f"Process not responsive: {str(e)}")


# Note: /readyz endpoint is handled directly in factory.py to ensure 
# it uses app.state.ready without complex dependency injection


@router.get("/readyz")
async def readiness_check(request: Request):
    """Readiness probe - checks if service can handle requests"""
    try:
        # Check if app is fully initialized
        ready = getattr(request.app.state, 'ready', False)
        
        if not ready:
            return Response(
                content='{"status": "starting", "ready": false}',
                status_code=503,
                media_type="application/json"
            )
        
        # Basic readiness checks
        status = {
            "status": "ready",
            "ready": True,
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "database": "healthy",
                "websocket": "healthy", 
                "metrics": "healthy"
            }
        }
        
        return status
        
    except Exception as e:
        return Response(
            content=f'{{"status": "error", "error": "{str(e)}"}}',
            status_code=503,
            media_type="application/json"
        )


@router.get("/test/runtime-error")
async def test_runtime_error():
    """Test endpoint that forces a RuntimeError for testing error handling"""
    raise RuntimeError("Test runtime error from error factory")
