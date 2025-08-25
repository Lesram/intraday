from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Dict
import uuid

router = APIRouter(prefix="/api/v1", tags=["signals"])


class SignalRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol")
    signal_strength: float = Field(..., description="Signal strength")
    timestamp: str = Field(..., description="Signal timestamp")
    features: Dict[str, float] = Field(default_factory=dict, description="Signal features")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Signal metadata")


@router.post("/signals")
async def create_signal(request: Request, signal_request: SignalRequest):
    """Create a new trading signal."""
    # Generate signal ID
    signal_id = str(uuid.uuid4())
    
    # Mock signal processing - in reality this would convert to orders
    return {
        "signal_id": signal_id,
        "status": "accepted",
        "symbol": signal_request.symbol,
        "signal_strength": signal_request.signal_strength,
        "processed_at": datetime.now().isoformat(),
    }
