import pytest
from backend.models.ensemble_model import EnsembleModel

def test_ensemble_model_smoke():
    """Basic smoke test for ensemble model"""
    model = EnsembleModel()
    assert model is not None
