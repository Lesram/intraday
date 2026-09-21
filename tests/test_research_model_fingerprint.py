"""Identity follows complete learned RF state, not pickle allocator/memo details."""
import hashlib
import json
import os
import pickle
from pathlib import Path
import subprocess
import sys

import joblib
import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.tree import _tree

from backend.organism.model_fingerprint import (
    RF_FINGERPRINT_PREFIX,
    UnsupportedModelState,
    _StateWriter,
    random_forest_fingerprint,
)
from backend.organism.research_baseline import _fingerprint


@pytest.fixture(params=["classifier", "regressor"])
def forest(request):
    rng = np.random.default_rng(67421)
    features = rng.normal(size=(96, 5))
    if request.param == "classifier":
        model = RandomForestClassifier(n_estimators=4, max_depth=3, random_state=109, n_jobs=1)
        target = (features[:, 0] + features[:, 1] * 0.25 > 0).astype(int)
    else:
        model = RandomForestRegressor(n_estimators=4, max_depth=3, random_state=110, n_jobs=1)
        target = features[:, 0] * 0.4 - features[:, 2] * 0.2 + np.sin(features[:, 4])
    return model.fit(features, target), features


def test_saved_restore_roundtrips_preserve_full_identity_and_predictions(forest, tmp_path):
    model, features = forest
    expected = random_forest_fingerprint(model)
    assert expected.startswith(RF_FINGERPRINT_PREFIX)
    assert len(expected.removeprefix(RF_FINGERPRINT_PREFIX)) == 64
    path = tmp_path / "synthetic.joblib"
    joblib.dump(model, path)
    saved_bytes = path.read_bytes()
    for _ in range(3):
        loaded = joblib.load(path)
        assert random_forest_fingerprint(loaded) == expected
        for _ in range(3):
            loaded = pickle.loads(pickle.dumps(loaded, protocol=5))
            assert random_forest_fingerprint(loaded) == expected
            np.testing.assert_array_equal(model.predict(features), loaded.predict(features))
    assert path.read_bytes() == saved_bytes


def test_fresh_process_engine_import_order_and_repeated_loads_are_equivalent(forest, tmp_path):
    model, _ = forest
    path = tmp_path / "synthetic.joblib"
    joblib.dump(model, path)
    expected = random_forest_fingerprint(model)
    program = """
import json, sys, pickle
from pathlib import Path
import joblib
if sys.argv[2] == 'before':
    import backend.organism.live_engine
from backend.organism.model_fingerprint import random_forest_fingerprint
model = joblib.load(sys.argv[1])
hashes = [random_forest_fingerprint(model)]
if sys.argv[2] == 'after':
    import backend.organism.live_engine
hashes.append(random_forest_fingerprint(model))
hashes.append(random_forest_fingerprint(joblib.load(sys.argv[1])))
hashes.append(random_forest_fingerprint(pickle.loads(pickle.dumps(model, protocol=5))))
Path(sys.argv[3]).write_text(json.dumps(hashes))
"""
    for mode in ("before", "after", "neither"):
        output = tmp_path / f"{mode}.json"
        result = subprocess.run(
            [sys.executable, "-B", "-c", program, str(path), mode, str(output)],
            cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(),
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(output.read_text()) == [expected] * 4


def test_padding_and_aliases_are_ignored_without_mutating_models(forest):
    model, features = forest
    other = pickle.loads(pickle.dumps(model, protocol=5))
    nodes = other.estimators_[0].tree_.__getstate__()["nodes"]
    occupied = set()
    for name in nodes.dtype.names:
        dtype, offset = nodes.dtype.fields[name][:2]
        occupied.update(range(offset, offset + dtype.itemsize))
    padding = sorted(set(range(nodes.dtype.itemsize)) - occupied)
    assert padding  # The exact supported sklearn Tree format has anonymous bytes.
    nodes.view(np.uint8).reshape(-1, nodes.dtype.itemsize)[:, padding] = 173
    other.estimator_params = tuple(list(other.estimator_params))
    before = pickle.dumps(other, protocol=5)
    predictions = other.predict(features)
    assert random_forest_fingerprint(other) == random_forest_fingerprint(model)
    assert pickle.dumps(other, protocol=5) == before
    np.testing.assert_array_equal(other.predict(features), predictions)


@pytest.mark.parametrize("change", [
    "threshold", "value", "feature", "missing_direction", "children", "node_samples", "impurity",
    "forest_order", "forest_parameter", "tree_parameter", "extra_state", "scalar_type",
    "tree_dimensions", "forest_class", "array_dtype", "array_shape", "array_order",
])
def test_all_prediction_state_changes_change_identity(forest, change):
    model, _ = forest
    expected = random_forest_fingerprint(model)
    tree = model.estimators_[0].tree_
    if change == "threshold": tree.threshold[0] += 0.125
    elif change == "value": tree.value[0, 0, 0] += 0.01
    elif change == "feature": tree.feature[0] = (tree.feature[0] + 1) % model.n_features_in_
    elif change == "missing_direction": tree.missing_go_to_left[0] = 1 - tree.missing_go_to_left[0]
    elif change == "children": tree.children_left[0], tree.children_right[0] = tree.children_right[0], tree.children_left[0]
    elif change == "node_samples": tree.n_node_samples[0] += 1
    elif change == "impurity": tree.impurity[0] += 0.01
    elif change == "forest_order": model.estimators_.reverse()
    elif change == "forest_parameter": model.max_depth += 1
    elif change == "tree_parameter": model.estimators_[0].min_samples_leaf += 1
    elif change == "extra_state": model.unexpected_state = True
    elif change == "scalar_type": model.n_features_in_ = np.int64(model.n_features_in_)
    elif change == "tree_dimensions":
        replacement = _tree.Tree(tree.n_features + 1, tree.n_classes, tree.n_outputs)
        replacement.__setstate__(tree.__getstate__())
        model.estimators_[0].tree_ = replacement
    elif change == "forest_class":
        model.__class__ = RandomForestRegressor if type(model) is RandomForestClassifier else RandomForestClassifier
    else:
        model.extra_array = np.array([[1, 2], [3, 4]], dtype=np.int64)
        expected = random_forest_fingerprint(model)
        if change == "array_dtype": model.extra_array = model.extra_array.astype(np.int32)
        elif change == "array_shape": model.extra_array = model.extra_array.reshape(4)
        else: model.extra_array = model.extra_array[::-1].copy()
    assert random_forest_fingerprint(model) != expected


@pytest.mark.parametrize("component", ["forest", "tree"])
def test_classifier_class_order_is_part_of_identity(component):
    features = np.arange(40, dtype=float).reshape(20, 2)
    model = RandomForestClassifier(n_estimators=3, random_state=5).fit(features, np.arange(20) % 2)
    expected = random_forest_fingerprint(model)
    target = model if component == "forest" else model.estimators_[0]
    target.classes_ = target.classes_[::-1].copy()
    assert random_forest_fingerprint(model) != expected


@pytest.mark.parametrize("unsupported", ["object", "callable", "cycle", "void_dtype", "ambiguous_keys"])
def test_unsupported_state_is_rejected_without_fallback(forest, unsupported):
    model, _ = forest
    value = {"object": object(), "callable": lambda: None,
             "cycle": [model], "void_dtype": np.zeros(2, dtype="V8"),
             "ambiguous_keys": {float("nan"): 1, float("nan"): 2}}[unsupported]
    model.extra = value
    with pytest.raises(UnsupportedModelState):
        _fingerprint(model)


def test_unknown_rf_subclass_cannot_fall_back_to_pickle():
    class ExtendedForest(RandomForestClassifier):
        pass
    with pytest.raises(UnsupportedModelState, match="Exact Random Forest"):
        _fingerprint(ExtendedForest())


def test_fingerprinting_never_loads_or_predicts(forest, monkeypatch):
    model, _ = forest
    expected = _fingerprint(model)
    def forbidden(*args, **kwargs):
        raise AssertionError("Fingerprint tried to deserialize or predict")
    monkeypatch.setattr(pickle, "load", forbidden)
    monkeypatch.setattr(pickle, "loads", forbidden)
    monkeypatch.setattr(joblib, "load", forbidden)
    monkeypatch.setattr(type(model), "predict", forbidden)
    assert _fingerprint(model) == expected


def test_non_rf_fingerprints_keep_the_exact_legacy_method():
    for value in ({"weights": [1, 2]}, np.array([[1., 2.], [3., 4.]])):
        assert _fingerprint(value) == hashlib.sha256(pickle.dumps(value, protocol=5)).hexdigest()


def test_noncontiguous_array_values_stream_in_bounded_chunks():
    base = np.arange(200_000, dtype=np.float64).reshape(1000, 200)
    noncontiguous = base[:, ::2]
    expected = hashlib.sha256()
    _StateWriter(expected.update).value(noncontiguous.copy(order="C"))
    actual = hashlib.sha256()
    writes = []
    def record(data):
        writes.append(len(data))
        actual.update(data)
    _StateWriter(record).value(noncontiguous)
    assert actual.hexdigest() == expected.hexdigest()
    assert max(writes) <= 8192 * noncontiguous.dtype.itemsize
    assert noncontiguous[0, 1] == 2
