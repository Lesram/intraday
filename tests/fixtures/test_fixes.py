"""
Test configuration fixes for common issues.
This module provides utilities to fix test setup problems.
"""

import os
import warnings
from unittest.mock import MagicMock, patch

# Suppress TensorFlow warnings and compatibility issues
import os
import warnings

# Comprehensive TensorFlow warning suppression
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF2_BEHAVIOR'] = '1'

# Suppress all TensorFlow deprecation warnings at the module level
warnings.filterwarnings("ignore", category=DeprecationWarning, module="tensorflow")
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")
warnings.filterwarnings("ignore", category=UserWarning, module="tensorflow")
warnings.filterwarnings("ignore", message=r".*tf\..*deprecated.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=r".*The name tf\..*is deprecated.*", category=DeprecationWarning)

# Suppress at import time
import logging
tf_logger = logging.getLogger('tensorflow')
tf_logger.setLevel(logging.ERROR)
tf_logger.propagate = False


class MockJwtVerifier:
    """Mock JWT verifier that doesn't use jose library."""
    
    def __init__(self):
        self._jwt_error = Exception  # Use standard Exception instead of JWTError
        
    @property 
    def JWTError(self):
        return self._jwt_error
    
    def encode(self, payload, key, algorithm="HS256"):
        """Mock JWT encode."""
        return "mock.jwt.token"
    
    def decode(self, token, key, algorithms=None):
        """Mock JWT decode.""" 
        if token == "invalid":
            raise self.JWTError("Invalid token")
        return {
            "sub": "test_user",
            "roles": ["user"],
            "iss": "test_issuer",
            "aud": "test_audience",
            "exp": 9999999999,
            "iat": 1234567890,
            "jti": "test_token_id"
        }


def fix_transformers_keras_issue():
    """Fix transformers/keras compatibility issues."""
    import sys
    from unittest.mock import MagicMock
    
    # Mock tf_keras module before any imports
    if 'tf_keras' not in sys.modules:
        mock_keras = MagicMock()
        mock_keras.activations = MagicMock()
        mock_keras.layers = MagicMock()
        mock_keras.models = MagicMock()
        sys.modules['tf_keras'] = mock_keras
        
    # Prevent transformers from trying to import tf_keras and problematic modules
    try:
        import transformers.utils.import_utils
        if hasattr(transformers.utils.import_utils, '_transformers_available'):
            transformers.utils.import_utils._tf_available = False
        # Disable other problematic imports
        if hasattr(transformers.utils.import_utils, '_sentencepiece_available'):
            transformers.utils.import_utils._sentencepiece_available = False
    except (ImportError, AttributeError):
        pass
        
    # Mock problematic transformers modules preemptively
    problematic_modules = [
        'transformers.activations_tf',
        'transformers.models.deprecated.open_llama.tokenization_open_llama_fast',
        'transformers.models.m2m_100.tokenization_m2m_100', 
        'transformers.models.deberta_v2.tokenization_deberta_v2',
        'transformers.optimization_tf',
        'transformers.modeling_tf_utils',
        'sentencepiece'
    ]
    
    for module_name in problematic_modules:
        if module_name not in sys.modules:
            sys.modules[module_name] = MagicMock()
    
    # Set environment variables to disable problematic imports
    import os
    os.environ['USE_TF'] = '0'
    os.environ['TRANSFORMERS_VERBOSITY'] = 'error'


def create_test_app():
    """Create a test FastAPI app with proper mocking."""
    from backend.api.factory import create_app
    from backend.infra.security_hardening import jwt_verifier
    
    app = create_app()
    
    # Mock required app state dependencies
    app.state.risk_manager = MagicMock()
    app.state.ws_manager = MagicMock()
    app.state.metrics = MagicMock()
    if not hasattr(app.state, 'alpaca_client'):
        app.state.alpaca_client = MagicMock()
    
    return app


def get_mock_patches():
    """Get standard mock patches for testing."""
    from backend.infra.security_hardening import jwt_verifier
    mock_jwt = MockJwtVerifier()
    
    return [
        patch('backend.infra.db.get_session'),  # Fix: correct function name
        patch.object(jwt_verifier, 'encode', mock_jwt.encode),
        patch.object(jwt_verifier, 'decode', mock_jwt.decode),
        # Don't patch JWTError property - use alternative approach
    ]
