import pytest

try:
    from backend.mlops.model_manager import ModelRegistry
except Exception:
    ModelRegistry = None


class NoOpModel:
    def predict(self, X):
        return [0 for _ in range(len(X))]


def test_model_registry_register_get_predict():
    if ModelRegistry is None:
        pytest.skip("ModelRegistry not available")
    reg = ModelRegistry()
    reg.register_model("noop", NoOpModel())
    model = reg.get_model("noop")
    assert model is not None
    assert model.predict([[1],[2]]) == [0,0]
