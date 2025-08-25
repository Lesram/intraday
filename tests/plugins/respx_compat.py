"""
respx Compatibility Plugin for Test Suite

Ensures respx.MockRouter and respx.mock are available for chaos/integration tests.
This plugin provides compatibility shims for different respx versions.
"""

import respx

# MockRouter should be available in respx 0.22.0+
if not hasattr(respx, 'MockRouter'):
    # Fallback for older versions - try to alias Router to MockRouter
    if hasattr(respx, 'Router'):
        respx.MockRouter = respx.Router
    else:
        # Last resort - create a minimal MockRouter shim
        class MockRouter:
            def __init__(self, *args, **kwargs):
                self._args = args
                self._kwargs = kwargs
            
            def __enter__(self):
                return respx
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        
        respx.MockRouter = MockRouter

# Ensure respx.mock is available (should be in modern versions)
if not hasattr(respx, 'mock'):
    def mock(*args, **kwargs):
        return respx.MockRouter(*args, **kwargs)
    respx.mock = mock
