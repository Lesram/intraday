import os
from datetime import UTC, datetime

import pandas as pd
import pytest

from backend.ml.active_model_pointer import write_active_model_pointer
from backend.utils.secure_pickle import secure_dump_to_path


class DummyPriceRegressor:
    """Pickle-safe dummy regressor returning a constant next-price prediction."""

    def __init__(self, value: float = 123.45):
        self.value = float(value)

    def predict(self, X):
        # Return 1 prediction per row
        try:
            n = len(X)
        except Exception:
            n = 1
        return [self.value] * n


@pytest.mark.unit
def test_live_ensemble_uses_active_trained_artifact(tmp_path, monkeypatch):
    # Ensure the live path is enabled.
    monkeypatch.setenv("ENABLE_ML_MODELS", "1")

    # Keep everything inside a temp model store.
    monkeypatch.setenv("MODEL_STORE_PATH", str(tmp_path))

    # Tell live inference which pointer name to use.
    monkeypatch.setenv("LIVE_MODEL_NAME", "market_model")

    # Create and persist a dummy trained model artifact.
    model = DummyPriceRegressor(value=123.45)
    artifact_path = tmp_path / "dummy_model.pkl"
    secure_dump_to_path(model, artifact_path)

    # Write the pointer file that live trading uses.
    write_active_model_pointer(
        model_name="market_model",
        model_path=str(artifact_path),
        version="1",
        trained_at=datetime.now(UTC),
        target_kind="next_close",
        feature_columns=["f1", "f2"],
        extra={"smoke_test": True},
    )

    # Import after env vars are set so the module uses the intended settings.
    from backend.models.ensemble_model import EnsembleModel

    em = EnsembleModel()

    # Minimal price + feature frames. Only the latest row is used for inference.
    idx = pd.date_range("2025-01-01", periods=3, freq="D", tz="UTC")
    price_data = pd.DataFrame({"close": [100.0, 101.0, 102.0]}, index=idx)
    features = pd.DataFrame({"f1": [1.0, 2.0, 3.0], "f2": [10.0, 11.0, 12.0]}, index=idx)

    result = em.predict(price_data=price_data, features=features, symbol="AAPL")

    assert result.metadata.get("active_model_used") is True
    assert result.metadata.get("active_model_name") == "market_model"
    assert abs(float(result.ensemble_prediction) - 123.45) < 1e-9
    assert "active_trained_model" in (result.predictions or {})
