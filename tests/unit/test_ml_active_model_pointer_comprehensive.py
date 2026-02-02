"""
Comprehensive tests for backend/ml/active_model_pointer.py
Targets: _pointer_dir, _safe_name, ActiveModelInfo, write_active_model_pointer,
         load_active_model_pointer
"""

import json
import os
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from backend.ml.active_model_pointer import (
    _pointer_dir,
    _safe_name,
    ActiveModelInfo,
    write_active_model_pointer,
    load_active_model_pointer,
)


# =============================================================================
# _pointer_dir Tests
# =============================================================================
class TestPointerDir:
    """Tests for _pointer_dir function."""

    def test_default_path(self):
        """Test default path when no env vars set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove our env vars
            for key in ["ACTIVE_MODEL_POINTER_DIR", "MODEL_STORE_PATH"]:
                os.environ.pop(key, None)
            
            result = _pointer_dir()
            assert "models" in str(result) or "active_models" in str(result)

    def test_active_model_pointer_dir_env(self):
        """Test ACTIVE_MODEL_POINTER_DIR takes precedence."""
        with patch.dict(os.environ, {
            "ACTIVE_MODEL_POINTER_DIR": "/custom/pointer/dir",
            "MODEL_STORE_PATH": "/other/path"
        }):
            result = _pointer_dir()
            assert result == Path("/custom/pointer/dir") / "active_models"

    def test_model_store_path_env(self):
        """Test MODEL_STORE_PATH used when ACTIVE_MODEL_POINTER_DIR not set."""
        with patch.dict(os.environ, {
            "MODEL_STORE_PATH": "/custom/model/store"
        }, clear=False):
            os.environ.pop("ACTIVE_MODEL_POINTER_DIR", None)
            result = _pointer_dir()
            assert result == Path("/custom/model/store") / "active_models"

    def test_returns_path_object(self):
        """Test returns Path object."""
        result = _pointer_dir()
        assert isinstance(result, Path)


# =============================================================================
# _safe_name Tests
# =============================================================================
class TestSafeName:
    """Tests for _safe_name function."""

    def test_alphanumeric_unchanged(self):
        """Test alphanumeric names stay unchanged."""
        assert _safe_name("model123") == "model123"
        assert _safe_name("TestModel") == "TestModel"

    def test_allowed_special_chars(self):
        """Test dashes, underscores, and dots are allowed."""
        assert _safe_name("my-model") == "my-model"
        assert _safe_name("my_model") == "my_model"
        assert _safe_name("model.v1") == "model.v1"
        assert _safe_name("my-model_v1.0") == "my-model_v1.0"

    def test_special_chars_replaced(self):
        """Test special characters are replaced with underscore."""
        assert _safe_name("model/test") == "model_test"
        assert _safe_name("model@v1") == "model_v1"
        assert _safe_name("model name") == "model_name"
        assert _safe_name("model:1.0") == "model_1.0"

    def test_strips_whitespace(self):
        """Test whitespace is stripped."""
        assert _safe_name("  model  ") == "model"
        assert _safe_name("\tmodel\n") == "model"

    def test_empty_string(self):
        """Test empty string handling."""
        assert _safe_name("") == ""
        assert _safe_name("   ") == ""


# =============================================================================
# ActiveModelInfo Tests
# =============================================================================
class TestActiveModelInfo:
    """Tests for ActiveModelInfo dataclass."""

    def test_basic_creation(self):
        """Test creating ActiveModelInfo with all fields."""
        info = ActiveModelInfo(
            name="test_model",
            version="1.0.0",
            path="/path/to/model",
            trained_at="2024-01-01T00:00:00",
            target_kind="direction_up",
            feature_columns=["feature1", "feature2"],
            extra={"key": "value"},
        )
        assert info.name == "test_model"
        assert info.version == "1.0.0"
        assert info.path == "/path/to/model"
        assert info.trained_at == "2024-01-01T00:00:00"
        assert info.target_kind == "direction_up"
        assert info.feature_columns == ["feature1", "feature2"]
        assert info.extra == {"key": "value"}

    def test_with_none_values(self):
        """Test creating ActiveModelInfo with None values."""
        info = ActiveModelInfo(
            name="test_model",
            version=None,
            path="/path",
            trained_at=None,
            target_kind=None,
            feature_columns=None,
            extra={},
        )
        assert info.name == "test_model"
        assert info.version is None
        assert info.trained_at is None

    def test_is_frozen(self):
        """Test dataclass is frozen (immutable)."""
        info = ActiveModelInfo(
            name="test",
            version="1.0",
            path="/path",
            trained_at=None,
            target_kind=None,
            feature_columns=None,
            extra={},
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            info.name = "new_name"


# =============================================================================
# write_active_model_pointer Tests
# =============================================================================
class TestWriteActiveModelPointer:
    """Tests for write_active_model_pointer function."""

    @pytest.fixture
    def temp_pointer_dir(self, tmp_path):
        """Create temporary pointer directory."""
        pointer_dir = tmp_path / "active_models"
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            yield pointer_dir

    def test_write_basic_pointer(self, temp_pointer_dir):
        """Test writing basic pointer file."""
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(temp_pointer_dir.parent)}):
            result = write_active_model_pointer(
                model_name="test_model",
                model_path="/path/to/model.bin",
            )

            assert result.exists()
            assert result.name == "test_model.json"

            data = json.loads(result.read_text())
            assert data["name"] == "test_model"
            assert data["path"] == "/path/to/model.bin"

    def test_write_with_all_fields(self, temp_pointer_dir):
        """Test writing pointer with all fields."""
        trained_at = datetime(2024, 1, 15, 10, 30, 0)
        
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(temp_pointer_dir.parent)}):
            result = write_active_model_pointer(
                model_name="full_model",
                model_path="/path/to/full_model.bin",
                version="2.0.0",
                trained_at=trained_at,
                target_kind="next_close",
                feature_columns=["col1", "col2", "col3"],
                extra={"origin": "training_job", "job_id": 123},
            )

            data = json.loads(result.read_text())
            assert data["name"] == "full_model"
            assert data["path"] == "/path/to/full_model.bin"
            assert data["version"] == "2.0.0"
            assert data["trained_at"] == "2024-01-15T10:30:00"
            assert data["target_kind"] == "next_close"
            assert data["feature_columns"] == ["col1", "col2", "col3"]
            assert data["extra"]["origin"] == "training_job"
            assert data["extra"]["job_id"] == 123

    def test_write_creates_directory(self, tmp_path):
        """Test writing creates directory if not exists."""
        new_dir = tmp_path / "new_pointer_dir"
        
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(new_dir)}):
            result = write_active_model_pointer(
                model_name="test",
                model_path="/path",
            )

            assert result.exists()
            assert (new_dir / "active_models").exists()

    def test_write_overwrites_existing(self, temp_pointer_dir):
        """Test writing overwrites existing pointer file."""
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(temp_pointer_dir.parent)}):
            # Write first version
            write_active_model_pointer(
                model_name="overwrite_test",
                model_path="/path/v1",
                version="1.0",
            )

            # Write second version
            result = write_active_model_pointer(
                model_name="overwrite_test",
                model_path="/path/v2",
                version="2.0",
            )

            data = json.loads(result.read_text())
            assert data["path"] == "/path/v2"
            assert data["version"] == "2.0"

    def test_write_special_characters_in_name(self, temp_pointer_dir):
        """Test writing pointer with special characters in name."""
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(temp_pointer_dir.parent)}):
            result = write_active_model_pointer(
                model_name="my/special:model@name",
                model_path="/path",
            )

            # Filename should be sanitized
            assert "my_special_model_name.json" == result.name

    def test_write_none_values(self, temp_pointer_dir):
        """Test writing pointer with None values."""
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(temp_pointer_dir.parent)}):
            result = write_active_model_pointer(
                model_name="none_test",
                model_path="/path",
                version=None,
                trained_at=None,
                target_kind=None,
                feature_columns=None,
                extra=None,
            )

            data = json.loads(result.read_text())
            assert data["version"] is None
            assert data["trained_at"] is None
            assert data["target_kind"] is None
            assert data["feature_columns"] is None
            assert data["extra"] == {}


# =============================================================================
# load_active_model_pointer Tests
# =============================================================================
class TestLoadActiveModelPointer:
    """Tests for load_active_model_pointer function."""

    def test_load_basic_pointer(self, tmp_path):
        """Test loading basic pointer file."""
        pointer_dir = tmp_path / "active_models"
        pointer_dir.mkdir(parents=True)
        
        # Create pointer file
        pointer_file = pointer_dir / "test_model.json"
        pointer_file.write_text(json.dumps({
            "name": "test_model",
            "version": "1.0.0",
            "path": "/path/to/model",
            "trained_at": "2024-01-01T00:00:00",
            "target_kind": "direction_up",
            "feature_columns": ["col1"],
            "extra": {"key": "value"},
        }))

        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            result = load_active_model_pointer("test_model")

            assert result is not None
            assert result.name == "test_model"
            assert result.version == "1.0.0"
            assert result.path == "/path/to/model"

    def test_load_nonexistent_returns_none(self, tmp_path):
        """Test loading non-existent pointer returns None."""
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            result = load_active_model_pointer("nonexistent_model")
            assert result is None

    def test_load_invalid_json_returns_none(self, tmp_path):
        """Test loading invalid JSON returns None."""
        pointer_dir = tmp_path / "active_models"
        pointer_dir.mkdir(parents=True)
        
        # Write invalid JSON
        invalid_file = pointer_dir / "invalid_model.json"
        invalid_file.write_text("not valid json {{{")
        
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            result = load_active_model_pointer("invalid_model")
            assert result is None

    def test_load_non_dict_returns_none(self, tmp_path):
        """Test loading non-dict JSON returns None."""
        pointer_dir = tmp_path / "active_models"
        pointer_dir.mkdir(parents=True)
        
        # Write array instead of dict
        array_file = pointer_dir / "array_model.json"
        array_file.write_text("[1, 2, 3]")
        
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            result = load_active_model_pointer("array_model")
            assert result is None

    def test_load_with_missing_fields(self, tmp_path):
        """Test loading pointer with missing optional fields."""
        pointer_dir = tmp_path / "active_models"
        pointer_dir.mkdir(parents=True)
        
        # Minimal data
        minimal_file = pointer_dir / "minimal_model.json"
        minimal_file.write_text(json.dumps({
            "path": "/path/to/model"
        }))
        
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            result = load_active_model_pointer("minimal_model")
            
            assert result is not None
            assert result.name == "minimal_model"  # Falls back to input name
            assert result.path == "/path/to/model"
            assert result.version is None
            assert result.extra == {}

    def test_load_with_invalid_extra_type(self, tmp_path):
        """Test loading pointer with invalid extra type."""
        pointer_dir = tmp_path / "active_models"
        pointer_dir.mkdir(parents=True)
        
        # extra as string instead of dict
        file = pointer_dir / "invalid_extra.json"
        file.write_text(json.dumps({
            "name": "test",
            "path": "/path",
            "extra": "not a dict"
        }))
        
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            result = load_active_model_pointer("invalid_extra")
            
            assert result is not None
            assert result.extra == {}  # Falls back to empty dict

    def test_load_with_invalid_feature_columns_type(self, tmp_path):
        """Test loading pointer with invalid feature_columns type."""
        pointer_dir = tmp_path / "active_models"
        pointer_dir.mkdir(parents=True)
        
        # feature_columns as string instead of list
        file = pointer_dir / "invalid_fc.json"
        file.write_text(json.dumps({
            "name": "test",
            "path": "/path",
            "feature_columns": "not a list"
        }))
        
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            result = load_active_model_pointer("invalid_fc")
            
            assert result is not None
            assert result.feature_columns is None  # Falls back to None

    def test_load_with_empty_path(self, tmp_path):
        """Test loading pointer with empty path."""
        pointer_dir = tmp_path / "active_models"
        pointer_dir.mkdir(parents=True)
        
        file = pointer_dir / "empty_path.json"
        file.write_text(json.dumps({
            "name": "test",
            "path": ""
        }))
        
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            result = load_active_model_pointer("empty_path")
            
            assert result is not None
            assert result.path == ""


# =============================================================================
# Integration Tests
# =============================================================================
class TestActiveModelPointerIntegration:
    """Integration tests for write and load cycle."""

    def test_write_and_load_cycle(self, tmp_path):
        """Test complete write and load cycle."""
        trained_at = datetime(2024, 6, 15, 12, 0, 0)
        
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            # Write
            write_active_model_pointer(
                model_name="integration_test",
                model_path="/models/integration_test.bin",
                version="3.0.0",
                trained_at=trained_at,
                target_kind="direction_up",
                feature_columns=["f1", "f2", "f3"],
                extra={"test": True},
            )

            # Load
            result = load_active_model_pointer("integration_test")

            assert result is not None
            assert result.name == "integration_test"
            assert result.version == "3.0.0"
            assert result.path == "/models/integration_test.bin"
            assert result.trained_at == "2024-06-15T12:00:00"
            assert result.target_kind == "direction_up"
            assert result.feature_columns == ["f1", "f2", "f3"]
            assert result.extra == {"test": True}

    def test_multiple_models(self, tmp_path):
        """Test managing multiple model pointers."""
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            # Write multiple models
            for i in range(3):
                write_active_model_pointer(
                    model_name=f"model_{i}",
                    model_path=f"/path/model_{i}.bin",
                    version=f"{i}.0.0",
                )

            # Load each
            for i in range(3):
                result = load_active_model_pointer(f"model_{i}")
                assert result is not None
                assert result.version == f"{i}.0.0"

    def test_version_update(self, tmp_path):
        """Test updating a model's pointer to new version."""
        with patch.dict(os.environ, {"ACTIVE_MODEL_POINTER_DIR": str(tmp_path)}):
            # Initial version
            write_active_model_pointer(
                model_name="versioned_model",
                model_path="/v1/model.bin",
                version="1.0.0",
            )

            result1 = load_active_model_pointer("versioned_model")
            assert result1.version == "1.0.0"

            # Update to new version
            write_active_model_pointer(
                model_name="versioned_model",
                model_path="/v2/model.bin",
                version="2.0.0",
            )

            result2 = load_active_model_pointer("versioned_model")
            assert result2.version == "2.0.0"
            assert result2.path == "/v2/model.bin"
