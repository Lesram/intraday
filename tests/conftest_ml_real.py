"""
ML-Enabled Test Configuration - Specifically disables light mode for ML testing
"""
import os
import sys
from pathlib import Path

# FORCE DISABLE the light mode stubbing for this test
os.environ.pop("DISABLE_ML", None)
os.environ.pop("DISABLE_TORCH", None) 
os.environ.pop("DISABLE_TRANSFORMERS", None)
os.environ.pop("DISABLE_TENSORFLOW", None)
os.environ.pop("DISABLE_XGBOOST", None)
os.environ.pop("PYTEST_RUNNING", None)

# Clear any existing stubbed modules that were set by light mode
MODULES_TO_CLEAR = [
    "torch", "transformers", "tensorflow", "xgboost",
    "torch.nn", "torch.optim", "torch.utils", "torch.utils.data",
    "tensorflow.keras", "tensorflow.keras.models", "tensorflow.keras.layers",
    "transformers.utils", "transformers.utils.import_utils",
    "sklearn.ensemble", "backend.models.ensemble_model"
]

for module_name in MODULES_TO_CLEAR:
    if module_name in sys.modules:
        # Check if it's a mocked module
        module = sys.modules[module_name]
        if hasattr(module, '__file__') and module.__file__ and 'mocked:' in module.__file__:
            del sys.modules[module_name]

# Add the backend directory to Python path
backend_path = Path(__file__).parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

print("🚀 ML ENABLED MODE - Light mode disabled, real ML libraries available")
