"""
CRITICAL: Light Mode Setup - Must run before any other imports
This file must be imported first to prevent heavy ML library loading
"""
import os
import sys
import types
from unittest.mock import MagicMock

# Set environment variables IMMEDIATELY
os.environ["DISABLE_ML"] = "1"
os.environ["DISABLE_TORCH"] = "1" 
os.environ["DISABLE_TRANSFORMERS"] = "1"
os.environ["DISABLE_TENSORFLOW"] = "1"
os.environ["DISABLE_XGBOOST"] = "1"
os.environ["PYTEST_RUNNING"] = "1"

# Heavy ML libraries that cause stalls on Windows
HEAVY_MODULES = [
    "torch", 
    "transformers", 
    "tensorflow", 
    "xgboost",
    "torch.nn",
    "torch.optim", 
    "torch.utils",
    "torch.utils.data",
    "tensorflow.keras",
    "tensorflow.keras.models",
    "tensorflow.keras.layers",
    "transformers.utils",
    "transformers.utils.import_utils",
    "sklearn.ensemble"
]

# Stub all heavy modules IMMEDIATELY
stubbed_count = 0
for module_name in HEAVY_MODULES:
    if module_name not in sys.modules:
        # Create a mock module to prevent actual imports
        mock_module = types.ModuleType(module_name)
        mock_module.__version__ = "mocked"
        mock_module.__file__ = f"<mocked:{module_name}>"
        
        # For torch, add common attributes
        if module_name == "torch":
            mock_module.cuda = MagicMock()
            mock_module.cuda.is_available = MagicMock(return_value=False)
        
        sys.modules[module_name] = mock_module
        stubbed_count += 1

print(f"LIGHT MODE ACTIVATED: {stubbed_count} heavy ML modules pre-stubbed")
print(f"   Environment variables set: DISABLE_ML, DISABLE_TORCH, etc.")
torch_file = getattr(sys.modules.get('torch'), '__file__', None)
torch_mocked = torch_file and isinstance(torch_file, str) and torch_file.startswith('<mocked:')
print(f"   Torch mocked: {torch_mocked}")

# Export for other modules to check
LIGHT_MODE_ACTIVE = True
