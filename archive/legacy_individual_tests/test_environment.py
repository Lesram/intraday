#!/usr/bin/env python3
"""
Environment & Dependencies Testing Script
Tests core Python packages and system dependencies with proper functional validation.
"""

import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv('.env.paper')

def test_sklearn_functionality():
    """Test scikit-learn ML operations (not just imports)"""
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.datasets import make_classification
        
        # Generate test data
        X, y = make_classification(n_samples=100, n_features=4, random_state=42)
        
        # Create and train model
        clf = RandomForestClassifier(n_estimators=10, random_state=42)
        clf.fit(X, y)
        
        # Make predictions
        predictions = clf.predict(X[:5])
        
        return len(predictions) == 5 and clf.n_features_in_ == 4
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_pandas_functionality():
    """Test pandas data operations"""
    try:
        import pandas as pd
        import numpy as np
        
        # Create test DataFrame
        df = pd.DataFrame({
            'symbol': ['AAPL', 'GOOGL', 'MSFT'],
            'price': [150.0, 2500.0, 300.0],
            'volume': [1000, 500, 800]
        })
        
        # Test operations
        grouped = df.groupby('symbol').sum()
        mean_price = df['price'].mean()
        
        return len(grouped) == 3 and mean_price > 0
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_numpy_functionality():
    """Test numpy mathematical operations"""
    try:
        import numpy as np
        
        # Create test arrays
        arr1 = np.array([1, 2, 3, 4, 5])
        arr2 = np.array([2, 4, 6, 8, 10])
        
        # Test operations
        mean_val = np.mean(arr1)
        dot_product = np.dot(arr1, arr2)
        correlation = np.corrcoef(arr1, arr2)[0, 1]
        
        return abs(mean_val - 3.0) < 0.01 and dot_product == 110
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_docker_availability():
    """Test Docker runtime availability and basic functionality"""
    try:
        import subprocess
        
        # Test Docker version
        version_result = subprocess.run(
            ['docker', '--version'], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        
        if version_result.returncode != 0:
            return False
        
        # Test Docker daemon connectivity
        info_result = subprocess.run(
            ['docker', 'info'], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        
        return (version_result.returncode == 0 and 
                'Docker version' in version_result.stdout and
                info_result.returncode == 0)
        
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_k6_availability():
    """Test K6 load testing tool availability"""
    try:
        import subprocess
        result = subprocess.run(
            ['k6', 'version'], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        return result.returncode == 0 and 'k6' in result.stdout.lower()
    except Exception as e:
        print(f"  Error: {e}")
        return False

def test_python_packages():
    """Test all required Python packages are available and functional"""
    try:
        # Test core data science packages
        import pandas as pd
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier
        
        # Test async packages
        import asyncio
        import aiohttp
        
        # Test database packages
        import sqlalchemy
        from sqlalchemy.ext.asyncio import create_async_engine
        
        # Test FastAPI and web packages
        import fastapi
        import uvicorn
        
        # Test testing packages
        import pytest
        
        # Test environment packages
        from dotenv import load_dotenv
        
        return True
    except ImportError as e:
        print(f"  Missing package: {e}")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False

def run_environment_tests():
    """Run all environment tests"""
    print("🔬 ENVIRONMENT & DEPENDENCIES TESTING")
    print("=" * 45)
    
    tests = [
        ("Python Package Dependencies", test_python_packages),
        ("Scikit-learn ML Operations", test_sklearn_functionality),
        ("Pandas Data Processing", test_pandas_functionality),
        ("NumPy Mathematical Operations", test_numpy_functionality),
        ("Docker Runtime & Daemon", test_docker_availability),
        ("K6 Load Testing Tool", test_k6_availability),
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
    print(f"\n📊 Environment Tests: {passed}/{total} ({success_rate:.1f}%)")
    
    return success_rate >= 90

if __name__ == "__main__":
    success = run_environment_tests()
    sys.exit(0 if success else 1)