"""
Comprehensive test suite for Module 87: Key Management Service
"""

import json
from pathlib import Path
from datetime import timedelta
import pytest

from backend.services.key_management import (
    KeyManagementService, KeyType, KeyStatus, get_key_manager, set_key_manager,
    encrypt_data, decrypt_data, sign_message, verify_signature
)


class TestKeyManagementService:
    @pytest.mark.timeout(5)
    def test_create_encrypt_decrypt(self, tmp_path: Path):
        kms = KeyManagementService()
        set_key_manager(kms)
        rec = kms.create_key("k1", KeyType.SYMMETRIC, length=16)
        token = encrypt_data("k1", "hello")
        plain = decrypt_data(token)
        assert plain == b"hello"
        m = kms.get_metrics("k1")["k1"]
        assert m["total_encrypts"] == 1 and m["total_decrypts"] == 1

    @pytest.mark.timeout(5)
    def test_sign_verify_and_rotation(self):
        kms = KeyManagementService()
        set_key_manager(kms)
        rec = kms.create_key("k2", length=32)
        sig = sign_message("k2", "msg")
        assert verify_signature("k2", "msg", sig) is True
        # Rotate and ensure old sig still verifies when versioned
        kms.rotate_key("k2")
        assert verify_signature("k2", "msg", sig) is True
        # New signature uses new version
        sig2 = sign_message("k2", "msg")
        assert sig2 != sig

    @pytest.mark.timeout(5)
    def test_disable_and_revoke(self):
        kms = KeyManagementService()
        rec = kms.create_key("k3")
        kms.disable_key("k3")
        with pytest.raises(PermissionError):
            kms.encrypt("k3", b"x")
        kms.rotate_key("k3")
        kms.revoke_key("k3")  # revoke latest
        with pytest.raises(PermissionError):
            kms.sign("k3", b"x")

    @pytest.mark.timeout(5)
    def test_expiry(self):
        kms = KeyManagementService()
        rec = kms.create_key("k4", ttl=timedelta(seconds=0))
        # force expiry
        rec.expires_at = rec.created_at
        with pytest.raises(PermissionError):
            kms.encrypt("k4", b"data")

    @pytest.mark.timeout(5)
    def test_persistence(self, tmp_path: Path):
        kms = KeyManagementService()
        kms.create_key("k5")
        file = tmp_path / "keys.json"
        kms.save_keys(file)

        kms2 = KeyManagementService()
        kms2.load_keys(file)
        rec2 = kms2.get_key("k5")
        assert rec2.key_id == "k5"

    @pytest.mark.timeout(5)
    def test_verify_without_version_and_errors(self):
        kms = KeyManagementService()
        kms.create_key("kv")
        # Manual signature without version prefix
        sig = kms.sign("kv", b"m").split(":")[1]
        assert kms.verify("kv", b"m", sig) is True
        # key not found
        with pytest.raises(KeyError):
            kms.get_key("missing")
        # version not found
        with pytest.raises(KeyError):
            kms.get_key("kv", 999)
        # malformed decrypt token
        with pytest.raises(Exception):
            kms.decrypt("not_base64")
        # disable specific version
        v1 = kms.get_key("kv").version
        kms.disable_key("kv", v1)
        with pytest.raises(PermissionError):
            kms.encrypt("kv", b"x", v1)

    @pytest.mark.timeout(5)
    def test_metrics_all_and_helpers(self):
        from backend.services.key_management import get_key_manager, encrypt_data, decrypt_data, sign_message, verify_signature
        kms = KeyManagementService()
        set_key_manager(kms)
        kms.create_key("g1")
        token = encrypt_data("g1", "a")
        assert decrypt_data(token) == b"a"
        sig = sign_message("g1", "m")
        assert verify_signature("g1", "m", sig) is True
        allm = kms.get_metrics()
        assert "g1" in allm and allm["g1"]["total_encrypts"] >= 1
