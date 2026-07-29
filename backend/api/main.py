"""
Main API application - FastAPI entry point using factory pattern
"""

from typing import Any

from backend.api.factory import create_app
from backend.api.logging_setup import configure_api_logging
from backend.config.settings import get_settings

# Create the real FastAPI application using factory pattern
settings = get_settings()
configure_api_logging(settings)
app = create_app(settings)

# Backward compatibility: Expose app state for any tests that might reference it
app_state = {
    "risk_manager": getattr(app.state, 'risk_manager', None),
    "ensemble_model": getattr(app.state, 'ensemble_model', None),
    "strategy_manager": getattr(app.state, 'strategy_manager', None),
    "alpaca_client": getattr(app.state, 'alpaca_client', None),
    "sentiment_analyzer": getattr(app.state, 'sentiment_analyzer', None),
    "feature_engineer": getattr(app.state, 'feature_engineer', None),
    "model_manager": getattr(app.state, 'model_manager', None),
    "active_websockets": getattr(app.state, 'active_websockets', []),
}

# ============================================================================
# OPENAPI SECURITY SCHEME CONFIGURATION
# ============================================================================
from fastapi.openapi.utils import get_openapi

app.openapi_schema = None

def custom_openapi():
    """
    Custom OpenAPI schema with Bearer authentication security scheme.

    Configures JWT Bearer token authentication as the global security requirement
    for all protected endpoints. Public routes can override this by setting
    openapi_extra={"security": []} in their route decorators.
    """
    if app.openapi_schema:
        return app.openapi_schema

    # Generate base OpenAPI schema
    schema = get_openapi(
        title="Algotrading Platform API",
        version="1.0.0",
        description="Algorithmic Trading Platform with real-time signals, risk management, and order execution",
        routes=app.routes
    )

    # Add Bearer authentication security scheme
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT Bearer token for API authentication. Use format: Bearer <your_jwt_token>"
    }

    # Set BearerAuth as global security requirement
    # Individual routes can override this with openapi_extra={"security": []}
    schema["security"] = [{"BearerAuth": []}]

    # Cache the schema
    app.openapi_schema = schema
    return schema

# Apply the custom OpenAPI function
app.openapi = custom_openapi

# ============================================================================
# NOTE: All API endpoints are registered via the factory pattern in
# backend.api.factory.create_app(). There are no standalone stub functions
# in this module. If tests need to call specific endpoint logic, they should
# use the FastAPI TestClient with the `app` instance above.
# ============================================================================

# ============================================================================
# SOCKET.IO INTEGRATION
# ============================================================================
from backend.api.socketio_server import create_socketio_app

# Create Socket.IO wrapped app for WebSocket support
socketio_app = create_socketio_app(app)

# Export both apps for flexibility
__all__ = ['app', 'socketio_app']
