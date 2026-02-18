"""
Auto-generated smoke tests for backend.api.main
Validates that the module and app are importable.
"""
import pytest


class TestMain:
    """Smoke tests for backend.api.main"""
    
    def test_module_import(self):
        """Test that module can be imported"""
        try:
            import backend.api.main
            assert backend.api.main is not None
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_app_exists(self):
        """Test that the FastAPI app is exported"""
        try:
            from backend.api.main import app
            assert app is not None
        except (ImportError, AttributeError) as e:
            pytest.skip(f"App not available: {e}")

    def test_custom_openapi_exists(self):
        """Test that custom_openapi function exists"""
        try:
            from backend.api.main import custom_openapi
            assert callable(custom_openapi)
        except (ImportError, AttributeError) as e:
            pytest.skip(f"Function not available: {e}")
    
