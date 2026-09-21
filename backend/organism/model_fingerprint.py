"""Deterministic identity of already loaded Random Forest prediction state.

Pickle bytes include object-sharing decisions and uninitialized structured-array
padding after joblib restoration. Neither is learned state. Hash the complete
supported state by typed value instead, without modifying or reloading models.
Unknown types fail closed; this is deliberately not a generic object serializer.
"""
from __future__ import annotations

import hashlib
import io
import struct
from collections.abc import Callable
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor, _tree

RF_FINGERPRINT_PREFIX = "rf-state-v1:"
_FORESTS = (RandomForestClassifier, RandomForestRegressor)
_ESTIMATORS = (*_FORESTS, DecisionTreeClassifier, DecisionTreeRegressor)
_TREE_DIMENSIONS = (
    "n_features", "n_outputs", "n_classes", "max_n_classes", "node_count", "capacity", "max_depth",
)
_ARRAY_BUFFER_ITEMS = 8192


class UnsupportedModelState(TypeError):
    """The identity contract cannot account for this complete model state."""


def is_random_forest(value: Any) -> bool:
    """Include subclasses here so unsupported RF subclasses cannot use pickle fallback."""
    return isinstance(value, _FORESTS)


def _type_name(value: Any) -> str:
    return f"{type(value).__module__}.{type(value).__qualname__}"


class _StateWriter:
    """Write length-framed typed state to a digest, retaining only small buffers."""

    def __init__(self, write: Callable[[bytes], Any], active: set[int] | None = None):
        self.write = write
        self.active = set() if active is None else active

    def _size(self, size: int) -> None:
        self.write(size.to_bytes(8, "big"))

    def _frame(self, value: bytes) -> None:
        self._size(len(value))
        self.write(value)

    def _dtype(self, dtype: np.dtype) -> None:
        """Keep the full dtype layout, but never anonymous padding contents."""
        if dtype.names is not None:
            fields = []
            for name in dtype.names:
                field = dtype.fields[name]
                fields.append((name, field[0], field[1], field[2] if len(field) > 2 else None))
            self._frame(b"structured_dtype")
            self.value((dtype.itemsize, dtype.isalignedstruct))
            self._size(len(fields))
            for name, field_dtype, offset, title in fields:
                self.value((name, offset, title))
                self._dtype(field_dtype)
        elif dtype.subdtype is not None:
            base, shape = dtype.subdtype
            self._frame(b"subarray_dtype")
            self.value(shape)
            self._dtype(base)
        else:
            # Extended floating formats can themselves contain anonymous padding.
            if (dtype.kind not in "biufcSUmMO"
                    or (dtype.kind == "f" and dtype.itemsize not in (2, 4, 8))
                    or (dtype.kind == "c" and dtype.itemsize not in (8, 16))):
                raise UnsupportedModelState("Unsupported Random Forest state dtype")
            self._frame(b"primitive_dtype")
            self.value(dtype.str)
        self.value(dict(dtype.metadata) if dtype.metadata is not None else None)

    def _array(self, value: np.ndarray) -> None:
        self._dtype(value.dtype)
        self.value(value.shape)
        if value.dtype.names is not None:
            self._frame(b"named_fields")
            self._size(len(value.dtype.names))
            for name in value.dtype.names:
                self.value(name)
                self.value(value[name])
        elif value.dtype.hasobject:
            self._frame(b"object_values")
            self._size(value.size)
            for element in value.flat:
                self.value(element)
        else:
            self._frame(b"array_data")
            self._size(value.size * value.dtype.itemsize)
            # C-order logical values make layout/strides irrelevant. Buffering
            # avoids materializing an entire forest or a noncontiguous array.
            with np.nditer(value, flags=["external_loop", "buffered", "zerosize_ok"],
                           op_flags=["readonly"], order="C",
                           buffersize=_ARRAY_BUFFER_ITEMS) as chunks:
                for chunk in chunks:
                    self.write(chunk.tobytes(order="C"))

    def value(self, value: Any) -> None:
        kind = type(value)
        if value is None:
            self._frame(b"none")
            return
        if kind is bool:
            self._frame(b"bool")
            self._frame(b"1" if value else b"0")
            return
        if kind is int:
            self._frame(b"int")
            self._frame(str(value).encode("ascii"))
            return
        if kind is float:
            self._frame(b"float64")
            self._frame(struct.pack(">d", value))
            return
        if kind in (str, bytes):
            self._frame(b"str" if kind is str else b"bytes")
            self._frame(value.encode("utf-8") if kind is str else value)
            return

        identity = id(value)
        if identity in self.active:
            raise UnsupportedModelState("Cyclic Random Forest state is unsupported")
        self.active.add(identity)
        try:
            if kind is dict:
                self._frame(b"dict")
                # Only keys are buffered; large array/model values stream below.
                pairs = []
                for key, item in value.items():
                    buffer = io.BytesIO()
                    _StateWriter(buffer.write, self.active).value(key)
                    pairs.append((buffer.getvalue(), item))
                pairs.sort(key=lambda pair: pair[0])
                self._size(len(pairs))
                previous_key = None
                for key, item in pairs:
                    if key == previous_key:
                        raise UnsupportedModelState("Ambiguous canonical dictionary keys")
                    previous_key = key
                    self._frame(key)
                    self.value(item)
            elif kind in (list, tuple):
                self._frame(b"list" if kind is list else b"tuple")
                self._size(len(value))
                for item in value:
                    self.value(item)
            elif kind is np.ndarray:
                self._frame(b"ndarray")
                self._array(value)
            elif isinstance(value, np.generic) and kind is value.dtype.type:
                self._frame(b"numpy_scalar")
                self.value(_type_name(value))
                self.value(np.asarray(value))
            elif kind is _tree.Tree:
                self._frame(b"sklearn_tree")
                self.value(_type_name(value))
                self.value({name: getattr(value, name) for name in _TREE_DIMENSIONS})
                self.value(value.__getstate__())
            elif kind in _ESTIMATORS:
                self._frame(b"sklearn_estimator")
                self.value(_type_name(value))
                self.value(value.get_params(deep=False))
                self.value(value.__getstate__())
            else:
                raise UnsupportedModelState("Unsupported Random Forest state type")
        finally:
            self.active.remove(identity)


def random_forest_fingerprint(model: Any) -> str:
    """Hash complete supported RF state; never deserialize, predict or mutate it.

    Exact estimator classes, parameters, every serialized state field, Tree
    dimensions, array dtypes/shapes/values and sequence order are included.
    The version prefix prevents treating an older raw pickle hash as equivalent.
    """
    if type(model) not in _FORESTS:
        raise UnsupportedModelState("Exact Random Forest classifier or regressor required")
    digest = hashlib.sha256()
    writer = _StateWriter(digest.update)
    writer.value(RF_FINGERPRINT_PREFIX)
    writer.value(model)
    return RF_FINGERPRINT_PREFIX + digest.hexdigest()
