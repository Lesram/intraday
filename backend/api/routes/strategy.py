"""
Strategy API routes.
Handles strategy management, feature ingestion, and signal batch operations.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/strategy", tags=["Strategy"])


class FeatureBatch(BaseModel):
    """Feature batch for strategy processing."""
    features: list[dict[str, Any]] = Field(..., description="List of feature vectors")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalBatch(BaseModel):
    """Signal batch for strategy processing."""
    signals: list[dict[str, Any]] = Field(..., description="List of signals")
    strategy_id: str = Field(..., description="Strategy identifier")
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/status")
async def get_strategy_status():
    """Get strategy system status."""
    return {
        "status": "operational",
        "active_strategies": 3,
        "last_update": datetime.now().isoformat(),
        "features_processed": 12500,
        "signals_generated": 450
    }


@router.post("/features/ingest")
async def ingest_features(request: Request, batch: FeatureBatch):
    """Ingest feature batch for strategy processing."""
    try:
        # Mock feature processing
        processed_count = len(batch.features)
        
        logger.info(f"Ingested {processed_count} features for strategy processing")
        
        return {
            "status": "accepted",
            "processed_count": processed_count,
            "batch_id": f"batch_{abs(hash(str(batch.features))) % 10000}",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Feature ingestion failed: {e}")
        raise HTTPException(status_code=500, detail="Feature ingestion failed")


@router.post("/signals/batch")
async def process_signal_batch(request: Request, batch: SignalBatch):
    """Process a batch of signals for strategy execution."""
    try:
        processed_signals = []
        
        for signal in batch.signals:
            # Mock signal processing
            processed_signal = {
                "signal_id": f"sig_{abs(hash(str(signal))) % 10000}",
                "original": signal,
                "status": "processed",
                "timestamp": datetime.now().isoformat()
            }
            processed_signals.append(processed_signal)
        
        return {
            "status": "completed",
            "strategy_id": batch.strategy_id,
            "processed_count": len(processed_signals),
            "signals": processed_signals,
            "batch_timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Signal batch processing failed: {e}")
        raise HTTPException(status_code=500, detail="Signal batch processing failed")


@router.post("/signals/submit")
async def submit_strategy_signal(request: Request):
    """Submit a single signal for strategy processing."""
    try:
        body = await request.json()
        
        # Mock single signal processing
        signal_id = f"sig_{abs(hash(str(body))) % 10000}"
        
        return {
            "signal_id": signal_id,
            "status": "submitted",
            "strategy": "default",
            "timestamp": datetime.now().isoformat(),
            "data": body
        }
        
    except Exception as e:
        logger.error(f"Signal submission failed: {e}")
        raise HTTPException(status_code=500, detail="Signal submission failed")
