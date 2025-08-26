"""
MLOps Integration Mocks for Testing
Provides mock MLOps services to enable testing of MLOps-dependent code paths
"""
import os
import sys
from unittest.mock import Mock, MagicMock
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add the backend directory to Python path
backend_path = Path(__file__).parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))


class MockModelManager:
    """Mock MLOps Model Manager"""
    
    def __init__(self):
        self.models = {}
        self.metadata = {}
    
    def register_model(self, model_name: str, model, metadata: dict = None):
        """Mock model registration"""
        self.models[model_name] = model
        self.metadata[model_name] = metadata or {}
        return {"model_id": f"mock_{model_name}_{datetime.now().timestamp()}"}
    
    def get_model(self, model_name: str):
        """Mock model retrieval"""
        return self.models.get(model_name)
    
    def validate_features(self, features: pd.DataFrame, schema_name: str = None) -> dict:
        """Mock feature validation"""
        return {
            "valid": True,
            "schema": schema_name or "default",
            "feature_count": len(features.columns),
            "row_count": len(features),
            "validation_timestamp": datetime.now().isoformat()
        }
    
    def log_prediction(self, model_name: str, inputs: dict, outputs: dict, metadata: dict = None):
        """Mock prediction logging"""
        return {
            "log_id": f"pred_{datetime.now().timestamp()}",
            "model_name": model_name,
            "timestamp": datetime.now().isoformat()
        }


class MockDriftDetector:
    """Mock ML Drift Detection Service"""
    
    def __init__(self):
        self.baseline_stats = {}
    
    def set_baseline(self, feature_name: str, baseline_data: pd.Series):
        """Set baseline statistics for drift detection"""
        self.baseline_stats[feature_name] = {
            "mean": baseline_data.mean(),
            "std": baseline_data.std(),
            "min": baseline_data.min(),
            "max": baseline_data.max()
        }
    
    def check_drift(self, features: pd.DataFrame, threshold: float = 0.1) -> dict:
        """Mock drift detection"""
        drift_results = {}
        
        for col in features.columns:
            if col in self.baseline_stats:
                # Simulate drift detection
                current_mean = features[col].mean()
                baseline_mean = self.baseline_stats[col]["mean"]
                drift_score = abs(current_mean - baseline_mean) / (baseline_mean + 1e-8)
                
                drift_results[col] = {
                    "drift_detected": drift_score > threshold,
                    "drift_score": drift_score,
                    "threshold": threshold
                }
            else:
                drift_results[col] = {
                    "drift_detected": False,
                    "drift_score": 0.0,
                    "threshold": threshold,
                    "status": "no_baseline"
                }
        
        return {
            "overall_drift": any(r["drift_detected"] for r in drift_results.values()),
            "feature_drift": drift_results,
            "timestamp": datetime.now().isoformat()
        }


class MockFeatureStore:
    """Mock Feature Store for feature pipeline testing"""
    
    def __init__(self):
        self.features = {}
        self.schemas = {}
    
    def get_features(self, feature_group: str, feature_names: List[str] = None) -> pd.DataFrame:
        """Mock feature retrieval"""
        if feature_group not in self.features:
            # Generate mock features
            n_rows = 100
            if feature_names:
                data = {name: np.random.randn(n_rows) for name in feature_names}
            else:
                data = {
                    "feature_1": np.random.randn(n_rows),
                    "feature_2": np.random.randn(n_rows),
                    "feature_3": np.random.randn(n_rows)
                }
            self.features[feature_group] = pd.DataFrame(data)
        
        df = self.features[feature_group]
        if feature_names:
            available_cols = [col for col in feature_names if col in df.columns]
            return df[available_cols]
        return df
    
    def register_schema(self, schema_name: str, schema: dict):
        """Register feature schema"""
        self.schemas[schema_name] = schema
        return {"schema_id": f"schema_{schema_name}_{datetime.now().timestamp()}"}
    
    def validate_schema(self, features: pd.DataFrame, schema_name: str) -> dict:
        """Mock schema validation"""
        schema = self.schemas.get(schema_name, {})
        
        return {
            "valid": True,
            "schema_name": schema_name,
            "feature_count": len(features.columns),
            "validation_errors": [],
            "timestamp": datetime.now().isoformat()
        }


class MockMLOpsLogger:
    """Mock MLOps Logging Service"""
    
    def __init__(self):
        self.logs = []
    
    def info(self, message: str, extra: dict = None):
        """Mock info logging"""
        log_entry = {
            "level": "INFO",
            "message": message,
            "extra": extra or {},
            "timestamp": datetime.now().isoformat()
        }
        self.logs.append(log_entry)
    
    def warning(self, message: str, extra: dict = None):
        """Mock warning logging"""
        log_entry = {
            "level": "WARNING", 
            "message": message,
            "extra": extra or {},
            "timestamp": datetime.now().isoformat()
        }
        self.logs.append(log_entry)
    
    def error(self, message: str, extra: dict = None):
        """Mock error logging"""
        log_entry = {
            "level": "ERROR",
            "message": message, 
            "extra": extra or {},
            "timestamp": datetime.now().isoformat()
        }
        self.logs.append(log_entry)


def get_model_manager():
    """Mock factory function for model manager"""
    return MockModelManager()


def get_drift_detector():
    """Mock factory function for drift detector"""
    return MockDriftDetector()


def get_feature_store():
    """Mock factory function for feature store"""
    return MockFeatureStore()


def get_mlops_logger():
    """Mock factory function for MLOps logger"""
    return MockMLOpsLogger()


# Create module-level instances for testing
mock_model_manager = MockModelManager()
mock_drift_detector = MockDriftDetector()
mock_feature_store = MockFeatureStore()
mock_mlops_logger = MockMLOpsLogger()

print("🔧 MLOps Mocks initialized - model_manager, drift_detector, feature_store, mlops_logger")
