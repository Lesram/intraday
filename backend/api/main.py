from backend.api.factory import create_app
from backend.infra.security import get_current_user as get_authenticated_user

# Test hook (patched by tests expecting this symbol)
def initialize_database(*args, **kwargs):
    pass

# Compatibility shims for tests that import these symbols
# TODO: Remove these after tests are updated to import from correct locations
try:
    from backend.api.websocket_manager import WebSocketClientManager
    from backend.utils.logger import get_logger as audit_logger
except ImportError:
    # Fallback in case modules are not available
    WebSocketClientManager = None
    audit_logger = None

app = create_app()
__all__ = ["app", "get_authenticated_user", "initialize_database", "WebSocketClientManager", "audit_logger"]
