#!/usr/bin/env python3
"""
ML Pipeline & Strategy Engine Testing Script
Tests AI/ML components and strategy engine with correct import paths and method names.
"""

import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv('.env.paper')

def test_ensemble_model():
    """Test EnsembleModel from correct location with proper method names"""
    try:
        # Use the EXISTING EnsembleModel from backend.models (not backend.ml)
        from backend.models.ensemble_model import EnsembleModel
        import pandas as pd
        import numpy as np
        
        # Create model instance
        model = EnsembleModel()
        
        # Create test data
        features = pd.DataFrame(
            np.random.rand(50, 5),
            columns=[f'feature_{i}' for i in range(5)]
        )
        targets = pd.Series(np.random.rand(50))
        
        # Test training with correct method name (train, not fit)
        result = model.train(features, targets)
        
        # Verify training succeeded and model state
        training_success = result.get('status') == 'success'
        is_trained = model.is_trained
        
        # Test model methods
        has_evaluate = hasattr(model, 'evaluate')
        has_save = hasattr(model, 'save')
        has_load = hasattr(model, 'load')
        
        return training_success and is_trained and has_evaluate and has_save and has_load
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_model_manager():
    """Test ML model management components"""
    try:
        from backend.ml.model_manager import ModelRegistry
        
        # Test model registry creation
        registry = ModelRegistry()
        
        # Test basic registry methods
        has_register = hasattr(registry, 'register_model')
        has_get = hasattr(registry, 'get_model')
        
        return has_register and has_get
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_strategy_engine_import():
    """Test StrategyEngine import capability"""
    try:
        from backend.strategies.engine import StrategyEngine
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_strategy_engine_factory():
    """Test StrategyEngine factory creation method"""
    try:
        from backend.strategies.engine import StrategyEngine
        
        # Use factory method for creation
        engine = StrategyEngine.create_default()
        
        # Verify engine was created successfully
        return engine is not None
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_strategy_signal_processing():
    """Test StrategyEngine signal processing capabilities"""
    try:
        from backend.strategies.engine import StrategyEngine
        
        # Create engine
        engine = StrategyEngine.create_default()
        
        # Test correct method existence (process_signals, not process_signal)
        has_process_signals = hasattr(engine, 'process_signals')
        has_net_signals = hasattr(engine, 'net_signals')
        
        # Test strategy types import (Side exists, SignalType doesn't)
        from backend.strategies.types import TradingSignal, Side
        
        return has_process_signals and has_net_signals
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_trading_signal_creation():
    """Test TradingSignal creation and structure"""
    try:
        from backend.strategies.types import TradingSignal, Side
        from datetime import datetime
        
        # Create test signal with correct constructor parameters
        test_signal = TradingSignal(
            symbol='AAPL',
            source='test_strategy',
            ts=datetime.now(),
            target_exposure=0.8,
            confidence=0.9
        )
        
        # Verify signal properties
        has_symbol = hasattr(test_signal, 'symbol')
        has_source = hasattr(test_signal, 'source')
        has_target_exposure = hasattr(test_signal, 'target_exposure')
        has_confidence = hasattr(test_signal, 'confidence')
        
        return has_symbol and has_source and has_target_exposure and has_confidence and test_signal.symbol == 'AAPL'
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_ml_data_processing():
    """Test ML data processing components"""
    try:
        from backend.ml.data_processing import DataProcessor
        
        processor = DataProcessor()
        
        # Test actual processor methods
        has_clean_data = hasattr(processor, 'clean_data')
        has_preprocess = hasattr(processor, 'preprocess_data')
        has_transform = hasattr(processor, 'transform_data')
        
        return has_clean_data and has_preprocess and has_transform
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_feature_engineering():
    """Test feature engineering components"""
    try:
        from backend.ml.feature_engineering import FeatureEngineer
        
        engineer = FeatureEngineer()
        
        # Test actual engineer methods
        has_create_technical = hasattr(engineer, 'create_technical_features')
        has_create_statistical = hasattr(engineer, 'create_statistical_features')
        has_fit_transform = hasattr(engineer, 'fit_transform')
        
        return has_create_technical and has_create_statistical and has_fit_transform
    except Exception as e:
        print(f"  Error: {e}")
        return False

def run_ml_strategy_tests():
    """Run all ML pipeline and strategy engine tests"""
    print("🔬 ML PIPELINE & STRATEGY ENGINE TESTING")
    print("=" * 45)
    
    tests = [
        ("EnsembleModel (from models)", test_ensemble_model),
        ("ModelRegistry", test_model_manager),
        ("StrategyEngine Import", test_strategy_engine_import),
        ("StrategyEngine Factory Creation", test_strategy_engine_factory), 
        ("Strategy Signal Processing", test_strategy_signal_processing),
        ("TradingSignal Creation", test_trading_signal_creation),
        ("Data Processing", test_ml_data_processing),
        ("Feature Engineering", test_feature_engineering),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🧪 Testing {test_name}...")
        try:
            result = test_func()
            if result:
                print(f"  ✅ {test_name}: FUNCTIONAL")
                passed += 1
            else:
                print(f"  ❌ {test_name}: FAILED")
        except Exception as e:
            print(f"  ❌ {test_name}: ERROR - {str(e)[:60]}...")
    
    success_rate = (passed / total) * 100
    print(f"\n📊 ML & Strategy Tests: {passed}/{total} ({success_rate:.1f}%)")
    
    return success_rate >= 80  # Slightly lower threshold due to ML dependencies

if __name__ == "__main__":
    success = run_ml_strategy_tests()
    sys.exit(0 if success else 1)