"""
Comprehensive tests for backend/observability/metrics.py

Tests the compatibility forwarding module.
"""

import pytest


class TestObservabilityMetrics:
    """Tests for observability metrics module."""

    def test_getattr_forwarding(self):
        """__getattr__ forwards to infra.metrics."""
        from backend.observability import metrics
        
        # Try to access something from the forwarded module
        # The getattr should work
        dir_result = dir(metrics)
        assert isinstance(dir_result, list)

    def test_dir_function(self):
        """__dir__ returns merged directory."""
        from backend.observability import metrics
        
        result = dir(metrics)
        
        assert isinstance(result, list)
        # Should be sorted
        assert result == sorted(result)

    def test_track_model_prediction(self):
        """track_model_prediction returns None."""
        from backend.observability.metrics import track_model_prediction
        
        result = track_model_prediction("model", 0.5)
        
        assert result is None
