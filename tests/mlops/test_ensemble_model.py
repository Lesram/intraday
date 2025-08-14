import pytest

from backend.models.ensemble_model import LightweightEnsemble


class M1:
    def predict(self, data):
        return 1.0


class M2:
    def predict(self, data):
        return 3.0


def test_weighted_average():
    ens = LightweightEnsemble(M1(), M2(), w1=0.25, w2=0.75)
    y = ens.predict({})
    assert abs(y - (0.25 * 1.0 + 0.75 * 3.0)) < 1e-9


def test_shape_mismatch_raises():
    class Bad:
        def predict(self, data):
            return [1, 2]  # non-scalar

    ens = LightweightEnsemble(M1(), Bad())
    with pytest.raises(ValueError):
        ens.predict({})
