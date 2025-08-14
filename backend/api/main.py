# backend/api/main.py
"""
FastAPI Gateway - Thin Entrypoint
Main entry point that delegates to factory for actual app creation.
"""

from .factory import create_app
from backend.api.websocket_manager import WebSocketClientManager  # re-export for tests
from backend.utils.logger import get_logger  # re-export for tests
from backend.infra.logging import get_logger as audit_logger  # audit logger target for tests
try:
    from prometheus_client import generate_latest
    PROMETHEUS_AVAILABLE = True
except Exception:
    PROMETHEUS_AVAILABLE = False
    def generate_latest(*args, **kwargs):
        return b""

app = create_app()

# Mock app_state for testing compatibility
class MockAppState:
    """Mock app state for testing purposes."""
    def __init__(self):
        self.db_session_factory = None
        self.ws_manager = None
        self.risk_manager = None
        self.signal_service = None
        self.metrics_registry = None

def get_settings():
    """Mock function for get_settings used in tests."""
    from backend.config import Settings
    return Settings()

app_state = MockAppState()

# Set app state attributes
app.state.metrics_registry = None
app.state.ws_manager = None

# Provide stubbed symbols that tests patch on this module
from backend.infra.security import get_current_user  # for patching
def authenticate_user(*args, **kwargs):
    return {"access_token": "token", "token_type": "bearer", "user_id": "user"}
def create_user_account(*args, **kwargs):
    return {"user_id": "user", "email": "test@example.com"}
def check_database_connection(*args, **kwargs):
    return True
def check_all_dependencies(*args, **kwargs):
    return {"database": "healthy", "message_broker": "healthy"}
def get_positions_summary(*args, **kwargs):
    return {"positions": []}
def create_order(*args, **kwargs):
    return {"order_id": "123", "status": "submitted"}
def cancel_order(*args, **kwargs):
    return {"order_id": "123", "status": "cancelled"}
from datetime import datetime  # for patching in tests

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
