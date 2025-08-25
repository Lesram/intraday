"""
API v1 router that includes all v1 endpoints.
"""
from fastapi import APIRouter

from . import trades, models, system, signals

router = APIRouter(prefix="/api/v1", tags=["api"])

# Include sub-routers
router.include_router(trades.router)
router.include_router(models.router) 
router.include_router(system.router)
router.include_router(signals.router)
