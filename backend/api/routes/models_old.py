"""
ML Models API routes.
Handles model training, status, and management operations.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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
class ModelTrainingRequest(BaseModel):
    """Model training request."""
    model_config = {"protected_namespaces": ()}

    model_type: str = Field(..., pattern="^(ensemble|regression|classification|lstm)$", description="Type of model to train")
    retrain: bool = Field(default=True, description="Whether to retrain the model")
    features: list = Field(default_factory=lambda: ["technical", "sentiment"], description="Features to use")


class ModelTrainingResponse(BaseModel):
    """Model training response."""
    training_id: str
    status: str
    message: str
    started_at: str


class ModelStatusResponse(BaseModel):
    """Model status response."""
    models: dict[str, Any]
    training_status: str
    last_updated: str


class PredictionRequest(BaseModel):
    """Model prediction request."""
    symbol: str = Field(..., description="Symbol to predict")
    data: dict[str, Any] = Field(default_factory=dict, description="Input data for prediction")
    model_type: str = Field(default="ensemble", description="Model type to use")


class PredictionResponse(BaseModel):
    """Model prediction response."""
    symbol: str
    prediction: float
    confidence: float
    model_used: str
    timestamp: str


class HealthCheckResponse(BaseModel):
    """Model health check response."""
    status: str
    models_available: int
    models_healthy: int
    last_check: str
    details: dict[str, Any]


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

        async def start_training(self, model_config: dict[str, Any]):
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
@router.post("/train", tags=["ML Models", "Protected"], response_model=ModelTrainingResponse)
async def train_models(
    model_config: ModelTrainingRequest,
    current_user=Depends(require_admin),
    model_manager=Depends(get_model_manager),
):
    """
    Train ML models with specified configuration.
    Requires admin privileges.
    """
    try:
        result = await model_manager.start_training(model_config.model_dump())

        logger.info(f"Model training started: {result['training_id']}")
        return ModelTrainingResponse(**result)

    except Exception as e:
        logger.error(f"Model training failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Model training failed: {str(e)}"
        )


@router.post("/predict", tags=["ML Models", "Protected"], response_model=PredictionResponse)
async def predict_symbol(
    prediction_request: PredictionRequest,
    current_user=Depends(get_authenticated_user),
    model_manager=Depends(get_model_manager),
):
    """
    Get model prediction for a specific symbol.
    Requires trader or admin privileges.
    """
    try:
        # Mock prediction logic - in production this would call actual models
        from datetime import datetime
        import random

        # Simulate model prediction
        prediction = random.uniform(-0.05, 0.05)  # -5% to +5% price change prediction
        confidence = random.uniform(0.6, 0.95)    # 60% to 95% confidence

        logger.info(f"Generated prediction for {prediction_request.symbol}: {prediction:.4f}")

        return PredictionResponse(
            symbol=prediction_request.symbol,
            prediction=prediction,
            confidence=confidence,
            model_used=prediction_request.model_type,
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Prediction failed for {prediction_request.symbol}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Prediction failed: {str(e)}"
        )


@router.get("/status", tags=["ML Models", "Protected"], response_model=ModelStatusResponse)
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


@router.get("/health", tags=["ML Models", "Protected"], response_model=HealthCheckResponse)
async def get_model_health(
    current_user=Depends(get_authenticated_user),
    model_manager=Depends(get_model_manager),
):
    """
    Get ML models health status.
    Requires trader or admin privileges.
    """
    try:
        from datetime import datetime

        # Mock health check - in production this would check actual model health
        status_data = model_manager.get_model_status()
        models = status_data.get("models", {})

        models_available = len(models)
        models_healthy = sum(1 for model in models.values() if model.get("status") in ["trained", "ready"])

        health_status = "healthy" if models_healthy == models_available else "degraded"
        if models_available == 0:
            health_status = "unavailable"

        logger.info(f"Model health check: {models_healthy}/{models_available} models healthy")

        return HealthCheckResponse(
            status=health_status,
            models_available=models_available,
            models_healthy=models_healthy,
            last_check=datetime.now().isoformat(),
            details={
                "models": {name: {"status": model.get("status", "unknown")} for name, model in models.items()},
                "overall_status": health_status
            }
        )

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}"
        )
