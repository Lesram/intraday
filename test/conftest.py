"""
Consolidated test fixtures for the algotrading platform.
Provides common fixtures to eliminate duplicate setup code across consolidated test modules.
"""

import pytest
import sys
import os
import pandas as pd
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta, UTC

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def mock_settings():
    """Mock settings object for testing."""
    settings = Mock()
    settings.app = Mock()
    settings.app.debug = True
    settings.app.environment = "test"
    
    settings.data = Mock()
    settings.data.database_url = "sqlite:///:memory:"
    
    settings.security = Mock()
    settings.security.jwt_secret = "test-secret"
    settings.security.jwt_expire_minutes = 60
    settings.security.jwt_issuer = "test-issuer"
    settings.security.jwt_audience = "test-audience"
    settings.security.jwt_algorithm = "HS256"
    
    return settings


@pytest.fixture
def sample_dataframe():
    """Sample DataFrame for testing."""
    return pd.DataFrame({
        'feature1': [1.0, 2.0, 3.0, 4.0, 5.0],
        'feature2': [0.5, 1.5, 2.5, 3.5, 4.5],
        'feature3': [10.0, 20.0, 30.0, 40.0, 50.0],
        'price': [100.0, 105.0, 102.0, 108.0, 110.0],
        'volume': [1000, 1200, 950, 1300, 1100]
    })


@pytest.fixture
def sample_series():
    """Sample Series for testing."""
    return pd.Series([0, 1, 0, 1, 0], name='target')


@pytest.fixture
def sample_numpy_array():
    """Sample numpy array for testing."""
    return np.array([
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
        [7.0, 8.0, 9.0]
    ])


@pytest.fixture
def mock_model():
    """Mock ML model for testing."""
    model = Mock()
    model.predict.return_value = [0.5, 0.7, 0.3]
    model.fit.return_value = None
    model.score.return_value = 0.85
    model.get_params.return_value = {'n_estimators': 100}
    return model


@pytest.fixture
def mock_database_session():
    """Mock database session for testing."""
    session = Mock()
    session.query.return_value = session
    session.filter.return_value = session
    session.first.return_value = Mock()
    session.all.return_value = []
    session.commit.return_value = None
    session.rollback.return_value = None
    session.close.return_value = None
    return session


@pytest.fixture
def mock_request():
    """Mock FastAPI request for testing."""
    request = Mock()
    request.method = "GET"
    request.url = Mock()
    request.url.path = "/test"
    request.headers = {}
    request.client = Mock()
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def test_timestamps():
    """Common test timestamps."""
    now = datetime.now(UTC)
    return {
        'now': now,
        'past': now - timedelta(days=1),
        'future': now + timedelta(days=1),
        'start_of_day': now.replace(hour=0, minute=0, second=0, microsecond=0),
        'end_of_day': now.replace(hour=23, minute=59, second=59, microsecond=999999)
    }


@pytest.fixture(autouse=True)
def reset_mocks():
    """Auto-reset all mocks between tests."""
    yield
    # Any cleanup can be added here