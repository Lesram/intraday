"""
Key Management Service

Lightweight key management for encryption and signing without external deps.
Features:
- Symmetric key generation and rotation
- XOR-based reversible encryption (for testing) and HMAC-SHA256 signing
- Key status/expiry checks
- Simple persistence to/from JSON file
- Thread-safe operations and metrics

Note: XOR encryption here is meant for testing/demo only and is NOT secure.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class KeyType(Enum):
    SYMMETRIC = "symmetric"
    HMAC = "hmac"


class KeyStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class KeyRecord:
    key_id: str
    version: int
    type: KeyType
    value_b64: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    status: KeyStatus = KeyStatus.ACTIVE
    usage: str = "encrypt,sign"

    @property
    def value(self) -> bytes:
        return base64.b64decode(self.value_b64)

    def is_usable(self) -> bool:
        if self.status != KeyStatus.ACTIVE:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True


@dataclass
class KeyMetrics:
    key_id: str
    total_encrypts: int = 0
    total_decrypts: int = 0
    total_signs: int = 0
    total_verifies: int = 0
    rotations: int = 0


class KeyManagementService:
    def __init__(self):
        self._keys: Dict[str, Dict[int, KeyRecord]] = {}
        self._current_version: Dict[str, int] = {}
        self._metrics: Dict[str, KeyMetrics] = {}
        self._lock = threading.RLock()

    # Key lifecycle
    def create_key(
        self,
        key_id: str,
        key_type: KeyType = KeyType.SYMMETRIC,
        length: int = 32,
        ttl: Optional[timedelta] = None,
        usage: str = "encrypt,sign",
    ) -> KeyRecord:
        with self._lock:
            version = self._current_version.get(key_id, 0) + 1
            raw = os.urandom(length)
            record = KeyRecord(
                key_id=key_id,
                version=version,
                type=key_type,
                value_b64=base64.b64encode(raw).decode(),
                expires_at=(datetime.now(timezone.utc) + ttl) if ttl else None,
                status=KeyStatus.ACTIVE,
                usage=usage,
            )
            self._keys.setdefault(key_id, {})[version] = record
            self._current_version[key_id] = version
            self._metrics.setdefault(key_id, KeyMetrics(key_id=key_id))
            return record

    def rotate_key(self, key_id: str, length: int = 32) -> KeyRecord:
        with self._lock:
            if key_id not in self._keys:
                raise KeyError(f"Key {key_id} not found")
            rec = self.create_key(key_id, KeyType.SYMMETRIC, length)
            self._metrics[key_id].rotations += 1
            return rec

    def get_key(self, key_id: str, version: Optional[int] = None) -> KeyRecord:
        with self._lock:
            if key_id not in self._keys:
                raise KeyError(f"Key {key_id} not found")
            ver = version or self._current_version[key_id]
            record = self._keys[key_id].get(ver)
            if not record:
                raise KeyError(f"Key {key_id} version {ver} not found")
            return record

    def disable_key(self, key_id: str, version: Optional[int] = None):
        with self._lock:
            rec = self.get_key(key_id, version)
            rec.status = KeyStatus.INACTIVE

    def revoke_key(self, key_id: str, version: Optional[int] = None):
        with self._lock:
            rec = self.get_key(key_id, version)
            rec.status = KeyStatus.REVOKED

    # Crypto operations
    def encrypt(self, key_id: str, plaintext: bytes | str, version: Optional[int] = None) -> str:
        rec = self.get_key(key_id, version)
        if not rec.is_usable():
            raise PermissionError("Key is not usable")
        data = plaintext.encode() if isinstance(plaintext, str) else plaintext
        key = rec.value
        # XOR stream cipher-like (for tests only)
        out = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        token = {
            "k": rec.key_id,
            "v": rec.version,
            "c": base64.b64encode(out).decode(),
        }
        self._metrics[rec.key_id].total_encrypts += 1
        return base64.b64encode(json.dumps(token).encode()).decode()

    def decrypt(self, token: str) -> bytes:
        obj = json.loads(base64.b64decode(token.encode()).decode())
        key_id = obj["k"]
        version = obj["v"]
        ciphertext = base64.b64decode(obj["c"].encode())
        rec = self.get_key(key_id, version)
        if not rec.is_usable():
            raise PermissionError("Key is not usable")
        key = rec.value
        out = bytes(b ^ key[i % len(key)] for i, b in enumerate(ciphertext))
        self._metrics[rec.key_id].total_decrypts += 1
        return out

    def sign(self, key_id: str, message: bytes | str, version: Optional[int] = None) -> str:
        rec = self.get_key(key_id, version)
        if not rec.is_usable():
            raise PermissionError("Key is not usable")
        data = message.encode() if isinstance(message, str) else message
        sig = hmac.new(rec.value, data, hashlib.sha256).hexdigest()
        self._metrics[rec.key_id].total_signs += 1
        return f"v{rec.version}:{sig}"

    def verify(self, key_id: str, message: bytes | str, signature: str) -> bool:
        if signature.startswith("v") and ":" in signature:
            ver_str, sig_hex = signature.split(":", 1)
            version = int(ver_str[1:])
        else:
            version = None
            sig_hex = signature
        rec = self.get_key(key_id, version)
        data = message.encode() if isinstance(message, str) else message
        expected = hmac.new(rec.value, data, hashlib.sha256).hexdigest()
        self._metrics[rec.key_id].total_verifies += 1
        return hmac.compare_digest(expected, sig_hex)

    # Metrics and persistence
    def get_metrics(self, key_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            if key_id:
                m = self._metrics.get(key_id)
                return {key_id: asdict(m)} if m else {}
            return {k: asdict(v) for k, v in self._metrics.items()}

    def save_keys(self, path: str | Path):
        with self._lock:
            serial: Dict[str, Dict[str, Any]] = {}
            for key_id, versions in self._keys.items():
                serial[key_id] = {
                    "current": self._current_version[key_id],
                    "versions": {
                        str(ver): {
                            **asdict(rec),
                            "type": rec.type.value,
                            "status": rec.status.value,
                            "created_at": rec.created_at.isoformat(),
                            "expires_at": rec.expires_at.isoformat() if rec.expires_at else None,
                        }
                        for ver, rec in versions.items()
                    },
                }
            Path(path).write_text(json.dumps(serial))

    def load_keys(self, path: str | Path):
        with self._lock:
            data = json.loads(Path(path).read_text())
            self._keys.clear()
            self._current_version.clear()
            for key_id, meta in data.items():
                self._current_version[key_id] = int(meta["current"])
                self._keys[key_id] = {}
                for ver_str, rec in meta["versions"].items():
                    record = KeyRecord(
                        key_id=rec["key_id"],
                        version=int(rec["version"]),
                        type=KeyType(rec["type"]),
                        value_b64=rec["value_b64"],
                        created_at=datetime.fromisoformat(rec["created_at"]),
                        expires_at=(datetime.fromisoformat(rec["expires_at"]) if rec["expires_at"] else None),
                        status=KeyStatus(rec["status"]),
                        usage=rec.get("usage", "encrypt,sign"),
                    )
                    self._keys[key_id][record.version] = record
                self._metrics.setdefault(key_id, KeyMetrics(key_id=key_id))


# Global instance and helpers
_key_manager: Optional[KeyManagementService] = None


def get_key_manager() -> KeyManagementService:
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyManagementService()
    return _key_manager


def set_key_manager(manager: KeyManagementService):
    global _key_manager
    _key_manager = manager


def encrypt_data(key_id: str, plaintext: bytes | str) -> str:
    return get_key_manager().encrypt(key_id, plaintext)


def decrypt_data(token: str) -> bytes:
    return get_key_manager().decrypt(token)


def sign_message(key_id: str, message: bytes | str) -> str:
    return get_key_manager().sign(key_id, message)


def verify_signature(key_id: str, message: bytes | str, signature: str) -> bool:
    return get_key_manager().verify(key_id, message, signature)
