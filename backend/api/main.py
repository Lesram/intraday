# backend/api/main.py
"""
FastAPI Gateway - Thin Entrypoint
Main entry point that delegates to factory for actual app creation.
"""

from .factory import create_app

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
