"""
Test Secure Pickle Utilities.

Tests the HMAC-verified pickle serialization to ensure
proper security against pickle-based code execution attacks.
"""

import os
import pickle
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.utils.secure_pickle import (
    HEADER_SIZE,
    SIGNATURE_LENGTH,
    PickleSecurityError,
    TamperedPickleError,
    UnsignedPickleError,
    is_signed_pickle,
    migrate_pickle_file,
    secure_dump,
    secure_dump_to_path,
    secure_dumps,
    secure_load,
    secure_load_from_path,
    secure_loads,
)


class TestSecurePickleBasics:
    """Test basic secure pickle operations."""

    def test_dumps_loads_roundtrip(self):
        """Data survives secure pickle roundtrip."""
        original = {"key": "value", "number": 42, "list": [1, 2, 3]}
        signed = secure_dumps(original)
        restored = secure_loads(signed)
        assert restored == original

    def test_dumps_adds_signature(self):
        """secure_dumps adds header and signature."""
        data = {"test": True}
        signed = secure_dumps(data)
        
        # Should be larger than plain pickle
        plain = pickle.dumps(data)
        assert len(signed) > len(plain)
        
        # Should have header + data + signature
        assert len(signed) == HEADER_SIZE + len(plain) + SIGNATURE_LENGTH

    def test_different_data_types(self):
        """Various data types serialize correctly."""
        test_cases = [
            42,
            3.14159,
            "hello world",
            [1, 2, 3],
            {"nested": {"dict": True}},
            (1, 2, 3),
            None,
            True,
            False,
        ]
        
        for original in test_cases:
            signed = secure_dumps(original)
            restored = secure_loads(signed)
            assert restored == original, f"Failed for {type(original)}"


class TestSecurePickleFile:
    """Test file-based secure pickle operations."""

    def test_dump_load_file(self, tmp_path):
        """secure_dump and secure_load work with files."""
        data = {"model": "test", "weights": [0.1, 0.2, 0.3]}
        file_path = tmp_path / "test.pkl"
        
        with open(file_path, 'wb') as f:
            secure_dump(data, f)
        
        with open(file_path, 'rb') as f:
            restored = secure_load(f)
        
        assert restored == data

    def test_dump_load_path(self, tmp_path):
        """Path-based helpers work correctly."""
        data = {"config": "value", "params": [1, 2, 3]}
        file_path = tmp_path / "subdir" / "test.pkl"
        
        # Should create subdirectory
        secure_dump_to_path(data, file_path)
        assert file_path.exists()
        
        restored = secure_load_from_path(file_path)
        assert restored == data


class TestSignatureVerification:
    """Test HMAC signature verification."""

    def test_tampered_data_rejected(self):
        """Tampered data is rejected."""
        original = {"secret": "data"}
        signed = secure_dumps(original)
        
        # Tamper with the data portion
        tampered = bytearray(signed)
        data_start = HEADER_SIZE
        tampered[data_start + 5] ^= 0xFF  # Flip bits
        
        with pytest.raises(TamperedPickleError, match="signature verification failed"):
            secure_loads(bytes(tampered))

    def test_tampered_signature_rejected(self):
        """Tampered signature is rejected."""
        original = {"data": "value"}
        signed = secure_dumps(original)
        
        # Tamper with the signature
        tampered = bytearray(signed)
        tampered[-1] ^= 0xFF  # Flip last byte of signature
        
        with pytest.raises(TamperedPickleError, match="signature verification failed"):
            secure_loads(bytes(tampered))

    def test_truncated_data_rejected(self):
        """Truncated data is rejected."""
        original = {"data": "value"}
        signed = secure_dumps(original)
        
        # Truncate
        truncated = signed[:-10]
        
        with pytest.raises(UnsignedPickleError, match="length mismatch"):
            secure_loads(truncated)


class TestUnsignedPickleMigration:
    """Test migration from unsigned to signed pickle."""

    def test_unsigned_pickle_rejected_by_default(self):
        """Unsigned pickle is rejected when allow_unsigned=False."""
        data = {"old": "format"}
        unsigned = pickle.dumps(data)
        
        with pytest.raises(UnsignedPickleError):
            secure_loads(unsigned)

    def test_unsigned_pickle_allowed_with_flag(self):
        """Unsigned pickle works with allow_unsigned=True."""
        data = {"legacy": "model"}
        unsigned = pickle.dumps(data)
        
        # Should work with warning
        with pytest.warns(RuntimeWarning, match="unsigned pickle"):
            restored = secure_loads(unsigned, allow_unsigned=True)
        
        assert restored == data

    def test_migrate_pickle_file(self, tmp_path):
        """Unsigned pickle file can be migrated."""
        data = {"model": "weights"}
        file_path = tmp_path / "unsigned.pkl"
        
        # Create unsigned pickle
        with open(file_path, 'wb') as f:
            pickle.dump(data, f)
        
        # Migrate
        result = migrate_pickle_file(file_path)
        assert result is True
        
        # Should now be signed
        with open(file_path, 'rb') as f:
            signed_data = f.read()
        assert is_signed_pickle(signed_data)
        
        # Should load without allow_unsigned
        restored = secure_load_from_path(file_path)
        assert restored == data

    def test_already_signed_not_double_signed(self, tmp_path):
        """Already signed files are not re-signed."""
        data = {"already": "signed"}
        file_path = tmp_path / "signed.pkl"
        
        # Create signed pickle
        secure_dump_to_path(data, file_path)
        original_size = file_path.stat().st_size
        
        # Migrate (should be no-op)
        result = migrate_pickle_file(file_path)
        assert result is True
        
        # Size should be same
        assert file_path.stat().st_size == original_size


class TestIsSignedPickle:
    """Test signed pickle detection."""

    def test_detect_signed_pickle(self):
        """Correctly detects signed pickle format."""
        data = {"test": True}
        signed = secure_dumps(data)
        
        assert is_signed_pickle(signed) is True

    def test_detect_unsigned_pickle(self):
        """Correctly detects unsigned pickle."""
        data = {"test": True}
        unsigned = pickle.dumps(data)
        
        assert is_signed_pickle(unsigned) is False

    def test_detect_too_short(self):
        """Too-short data is not signed."""
        assert is_signed_pickle(b"short") is False

    def test_detect_random_data(self):
        """Random data is not signed."""
        assert is_signed_pickle(os.urandom(100)) is False


class TestHMACKey:
    """Test HMAC key derivation."""

    def test_key_derived_from_env(self):
        """HMAC key is derived from environment variable."""
        with patch.dict(os.environ, {"PICKLE_HMAC_SECRET": "test_secret_123"}):
            data = {"sensitive": "data"}
            signed1 = secure_dumps(data)
            signed2 = secure_dumps(data)
            
            # Same key produces same signature
            assert signed1 == signed2

    def test_different_keys_different_signatures(self):
        """Different secrets produce different signatures."""
        data = {"test": "data"}
        
        with patch.dict(os.environ, {"PICKLE_HMAC_SECRET": "secret_one"}):
            signed1 = secure_dumps(data)
        
        with patch.dict(os.environ, {"PICKLE_HMAC_SECRET": "secret_two"}):
            signed2 = secure_dumps(data)
        
        # Signatures should differ (last 32 bytes)
        assert signed1[-SIGNATURE_LENGTH:] != signed2[-SIGNATURE_LENGTH:]

    def test_cross_key_verification_fails(self):
        """Data signed with one key can't be verified with another."""
        data = {"test": "data"}
        
        with patch.dict(os.environ, {"PICKLE_HMAC_SECRET": "secret_one"}):
            signed = secure_dumps(data)
        
        with patch.dict(os.environ, {"PICKLE_HMAC_SECRET": "secret_two"}):
            with pytest.raises(TamperedPickleError):
                secure_loads(signed)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_dict(self):
        """Empty dict serializes correctly."""
        signed = secure_dumps({})
        assert secure_loads(signed) == {}

    def test_empty_list(self):
        """Empty list serializes correctly."""
        signed = secure_dumps([])
        assert secure_loads(signed) == []

    def test_large_data(self):
        """Large data serializes correctly."""
        large_data = {"items": list(range(10000))}
        signed = secure_dumps(large_data)
        restored = secure_loads(signed)
        assert restored == large_data

    def test_nested_structures(self):
        """Deeply nested structures work."""
        nested = {"a": {"b": {"c": {"d": {"e": [1, 2, 3]}}}}}
        signed = secure_dumps(nested)
        assert secure_loads(signed) == nested

    def test_binary_data(self):
        """Binary data in values works."""
        data = {"binary": b"\x00\x01\x02\xff\xfe\xfd"}
        signed = secure_dumps(data)
        assert secure_loads(signed) == data


class TestDevModeWarning:
    """Test development mode warnings."""

    def test_warns_when_no_secret_set(self):
        """Warning issued when PICKLE_HMAC_SECRET not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if present
            os.environ.pop("PICKLE_HMAC_SECRET", None)
            
            with pytest.warns(RuntimeWarning, match="PICKLE_HMAC_SECRET not set"):
                secure_dumps({"test": True})


# Marker for unit tests
pytestmark = pytest.mark.unit
