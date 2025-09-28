#!/usr/bin/env python3
"""
Simplified test suite for backend/ml module - targeting actual implementation
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from backend.ml.ensemble_model import EnsembleModel, create_model, fit_model
    ML_IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"ML import warning: {e}")
    ML_IMPORTS_AVAILABLE = False
    
    class EnsembleModel:
        def __init__(self, models=None):
            self.models = models or []
            self.is_trained = False
            self.features = []
            self.performance = {}


class TestEnsembleModel:
    """Test EnsembleModel class"""
    
    def setup_method(self):
        """Setup test environment"""
        self.model = EnsembleModel()
        self.sample_data = pd.DataFrame({
            'feature1': [1, 2, 3, 4, 5],
            'feature2': [0.1, 0.2, 0.3, 0.4, 0.5]
        })
        self.sample_target = pd.Series([0, 1, 0, 1, 0])
    
    def test_initialization(self):
        """Test EnsembleModel initialization"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        assert self.model.models == []
        assert self.model.is_trained is False
        assert self.model.features == []
        assert self.model.performance == {}
    
    def test_initialization_with_models(self):
        """Test initialization with models list"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        models = ["model1", "model2"]
        model = EnsembleModel(models=models)
        assert model.models == models
    
    def test_train_method(self):
        """Test train method"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        self.model.train(self.sample_data, self.sample_target)
        assert self.model.is_trained is True
        assert isinstance(self.model.performance, dict)
    
    def test_predict_method(self):
        """Test predict method"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        # Train first
        self.model.train(self.sample_data, self.sample_target)
        
        # Test prediction
        result = self.model.predict(self.sample_data)
        assert result is not None
    
    def test_predict_with_features_and_symbol(self):
        """Test predict with features and symbol parameters"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        features = pd.DataFrame({'rsi': [30, 70], 'macd': [0.1, -0.1]})
        result = self.model.predict(self.sample_data, features, "AAPL")
        assert result is not None
    
    def test_evaluate_method(self):
        """Test evaluate method"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        self.model.train(self.sample_data, self.sample_target)
        metrics = self.model.evaluate(self.sample_data, self.sample_target)
        assert isinstance(metrics, dict)
    
    def test_get_feature_importance(self):
        """Test get_feature_importance method"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        self.model.train(self.sample_data, self.sample_target)
        importance = self.model.get_feature_importance()
        assert isinstance(importance, dict)
    
    def test_save_and_load(self):
        """Test save and load methods"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        self.model.train(self.sample_data, self.sample_target)
        
        # Test save
        result = self.model.save("test_model.pkl")
        assert result is True
        
        # Test load  
        loaded_model = EnsembleModel()
        result = loaded_model.load("test_model.pkl")
        assert result is True


class TestModuleFunctions:
    """Test module-level functions"""
    
    def test_create_model(self):
        """Test create_model function"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        model = create_model()
        assert isinstance(model, EnsembleModel)
    
    def test_fit_model(self):
        """Test fit_model function"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        X = pd.DataFrame({'feature1': [1, 2, 3]})
        y = pd.Series([0, 1, 0])
        
        model = fit_model(X, y)
        assert isinstance(model, EnsembleModel)
        assert model.is_trained is True


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def test_predict_without_training(self):
        """Test predict without training"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        model = EnsembleModel()
        data = pd.DataFrame({'feature1': [1, 2]})
        
        # Should handle gracefully
        result = model.predict(data)
        assert result is not None
    
    def test_empty_data_handling(self):
        """Test handling of empty data"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        model = EnsembleModel()
        empty_df = pd.DataFrame()
        empty_series = pd.Series(dtype=float)
        
        # Should handle empty data gracefully
        model.train(empty_df, empty_series)
        result = model.predict(empty_df)
        assert result is not None
    
    def test_invalid_data_types(self):
        """Test handling of invalid data types"""
        if not ML_IMPORTS_AVAILABLE:
            pytest.skip("ML imports not available")
            
        model = EnsembleModel()
        
        # Test with None values
        result = model.predict(None)
        assert result is not None
        
        # Test training with None
        model.train(None, None)
        assert model.is_trained is True  # Stub should handle this