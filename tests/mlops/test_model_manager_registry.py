import pytest

from backend.mlops.model_manager import InMemoryModelRegistry, NoopModel


class FakeModel:
    def __init__(self, val):
        self.val = val

    def predict(self, data):
        return {"prediction": self.val}


def test_register_load_predict():
    reg = InMemoryModelRegistry()
    reg.register("price_model", "1.0.0", FakeModel(42))

    mdl = reg.load("price_model", "1.0.0")
    assert mdl.predict({}) == {"prediction": 42}


def test_missing_returns_noop():
    reg = InMemoryModelRegistry()
    mdl = reg.load("missing_model")
    out = mdl.predict({})
    assert isinstance(mdl, NoopModel)
    assert out["prediction"] == 0.0
