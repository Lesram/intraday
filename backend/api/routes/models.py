"""
ML Models API routes.
Handles model training, status, and management operations.
"""

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.infra.security import get_authenticated_user
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/models", tags=["ML Models", "Protected"])

# Service Dependencies
def get_model_service():
    """Get model service for dependency injection."""
    return type('ModelService', (), {
        'train_model': lambda **kwargs: {"model_id": "test-model", "status": "training"},
        'get_model_status': lambda model_id: {"model_id": model_id, "status": "ready"},
    })()

# Response Models
class ModelTrainingResponse(BaseModel):
    """Model training response."""
    training_id: str
    status: str
    message: str
    started_at: str


class ModelStatusResponse(BaseModel):
    """Model status response."""
    models: Dict[str, Any]
    training_status: str
    last_updated: str


# Mock Dependencies
def get_model_manager():
    """Get model manager - mock implementation"""
    class MockModelManager:
        def __init__(self):
            self.training_status = "idle"
            self.models = {
                "ensemble": {
                    "status": "trained",
                    "accuracy": 0.85,
                    "last_trained": "2025-01-01T12:00:00",
                    "version": "v1.0"
                },
                "lstm": {
                    "status": "training",
                    "progress": 0.75,
                    "eta": "10 minutes"
                }
            }
        
        async def start_training(self, model_config: Dict[str, Any]):
            """Start model training"""
            import uuid
            training_id = str(uuid.uuid4())
            self.training_status = "training"
            
            return {
                "training_id": training_id,
                "status": "started",
                "message": "Model training initiated",
                "started_at": datetime.now().isoformat()
            }
        
        def get_model_status(self):
            """Get current model status"""
            return {
                "models": self.models,
                "training_status": self.training_status,
                "last_updated": datetime.now().isoformat()
            }
    
    return MockModelManager()


def require_admin(current_user=Depends(get_authenticated_user)):
    """Dependency that requires authenticated admin user"""
    if not current_user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )
    
    # In production, would check admin roles
    user_roles = current_user.roles if hasattr(current_user, 'roles') else []
    if "admin" not in user_roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions"
        )
    
    return current_user


# Route Handlers
@router.post("/train", tags=["ML Models", "Protected"])
async def train_models(
    model_config: Dict[str, Any] = None,
    current_user=Depends(require_admin),
    model_manager=Depends(get_model_manager),
):
    """
    Train ML models with specified configuration.
    Requires admin privileges.
    """
    try:
        if model_config is None:
            model_config = {
                "model_type": "ensemble",
                "retrain": True,
                "features": ["technical", "sentiment", "fundamental"]
            }

        result = await model_manager.start_training(model_config)
        
        logger.info(f"Model training started: {result['training_id']}")
        return ModelTrainingResponse(**result)

    except Exception as e:
        logger.error(f"Model training failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Model training failed: {str(e)}"
        )


@router.get("/status", tags=["ML Models", "Protected"])
async def get_model_status(
    current_user=Depends(get_authenticated_user),  # Allow traders and admins
    model_manager=Depends(get_model_manager),
):
    """
    Get current model status and training information.
    Requires trader or admin privileges.
    """
    # Check user has proper role access (not read-only)
    user_roles = current_user.roles if hasattr(current_user, 'roles') else []
    if "read-only" in user_roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions"
        )
        
    try:
        status = model_manager.get_model_status()
        return ModelStatusResponse(**status)

    except Exception as e:
        logger.error(f"Failed to get model status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get model status: {str(e)}"
        )
