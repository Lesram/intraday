from backend.api.factory import create_app
from backend.infra.security import get_current_user as get_authenticated_user

# Test hook (patched by tests expecting this symbol)
def initialize_database(*args, **kwargs):
    pass

app = create_app()
__all__ = ["app", "get_authenticated_user", "initialize_database"]
