"""
Secure Pickle Utilities.

Provides HMAC-verified pickle serialization to prevent pickle-based
code execution attacks. All model/artifact serialization should use
these utilities instead of raw pickle.

Security Model:
- All pickled data is signed with HMAC-SHA256
- Secret key is derived from environment variable
- Signature verification before any unpickling
- Tampered or unsigned data is rejected
"""

import hashlib
import hmac
import os
from pathlib import Path
import pickle
import struct
from typing import Any, BinaryIO

# Configuration
HMAC_KEY_ENV = "PICKLE_HMAC_SECRET"
DEFAULT_KEY_DERIVATION_SALT = b"algotrading_platform_pickle_v1"
SIGNATURE_LENGTH = 32  # SHA256 produces 32 bytes
HEADER_FORMAT = "<I"  # Unsigned int for data length
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


class PickleSecurityError(Exception):
    """Raised when pickle security verification fails."""
    pass


class UnsignedPickleError(PickleSecurityError):
    """Raised when loading unsigned pickle data."""
    pass


class TamperedPickleError(PickleSecurityError):
    """Raised when pickle signature verification fails."""
    pass


def _get_hmac_key() -> bytes:
    """
    Get HMAC key for pickle signing.
    
    Key is derived from environment variable. In production, this should
    be a strong secret managed via secrets manager.
    
    Returns:
        bytes: The HMAC key
        
    Raises:
        EnvironmentError: If HMAC secret is not configured
    """
    secret = os.getenv(HMAC_KEY_ENV)

    if not secret:
        # In development, derive a key from a default (NOT for production!)
        import warnings
        warnings.warn(
            f"PICKLE_HMAC_SECRET not set. Using development default. "
            f"Set {HMAC_KEY_ENV} environment variable for production.",
            RuntimeWarning,
            stacklevel=3
        )
        # Derive key from machine-specific info for dev consistency
        secret = f"dev_key_{os.getenv('COMPUTERNAME', 'unknown')}"

    # Derive key using PBKDF2-style approach
    key = hashlib.pbkdf2_hmac(
        'sha256',
        secret.encode('utf-8'),
        DEFAULT_KEY_DERIVATION_SALT,
        iterations=100000,
        dklen=32
    )
    return key


def _compute_signature(data: bytes) -> bytes:
    """Compute HMAC-SHA256 signature for data."""
    key = _get_hmac_key()
    return hmac.new(key, data, hashlib.sha256).digest()


def _verify_signature(data: bytes, signature: bytes) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected = _compute_signature(data)
    return hmac.compare_digest(expected, signature)


def secure_dumps(obj: Any) -> bytes:
    """
    Securely serialize an object to bytes with HMAC signature.
    
    Format: [4-byte length][pickle data][32-byte HMAC signature]
    
    Args:
        obj: Object to serialize
        
    Returns:
        Signed pickle bytes
    """
    # Serialize object
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)

    # Compute signature
    signature = _compute_signature(data)

    # Pack: length + data + signature
    length = struct.pack(HEADER_FORMAT, len(data))
    return length + data + signature


def secure_loads(signed_data: bytes, allow_unsigned: bool = False) -> Any:
    """
    Securely deserialize bytes with HMAC verification.
    
    Args:
        signed_data: The signed pickle bytes
        allow_unsigned: If True, attempt to load unsigned pickle (for migration)
        
    Returns:
        The deserialized object
        
    Raises:
        UnsignedPickleError: If data is not in signed format
        TamperedPickleError: If signature verification fails
    """
    if len(signed_data) < HEADER_SIZE + SIGNATURE_LENGTH + 1:
        if allow_unsigned:
            # Attempt to load as plain pickle (migration path)
            import warnings
            warnings.warn(
                "Loading unsigned pickle data. Re-save with secure_dump to sign.",
                RuntimeWarning,
                stacklevel=2
            )
            return pickle.loads(signed_data)
        raise UnsignedPickleError("Data too short to be signed pickle")

    # Extract length
    length_bytes = signed_data[:HEADER_SIZE]
    data_length = struct.unpack(HEADER_FORMAT, length_bytes)[0]

    # Validate structure
    expected_total = HEADER_SIZE + data_length + SIGNATURE_LENGTH
    if len(signed_data) != expected_total:
        if allow_unsigned:
            import warnings
            warnings.warn(
                "Loading unsigned pickle data. Re-save with secure_dump to sign.",
                RuntimeWarning,
                stacklevel=2
            )
            return pickle.loads(signed_data)
        raise UnsignedPickleError(
            f"Data length mismatch: expected {expected_total}, got {len(signed_data)}"
        )

    # Extract data and signature
    data = signed_data[HEADER_SIZE:HEADER_SIZE + data_length]
    signature = signed_data[HEADER_SIZE + data_length:]

    # Verify signature
    if not _verify_signature(data, signature):
        raise TamperedPickleError("HMAC signature verification failed - data may be tampered")

    # Safe to unpickle
    return pickle.loads(data)


def secure_dump(obj: Any, file: BinaryIO) -> None:
    """
    Securely serialize an object to a file with HMAC signature.
    
    Args:
        obj: Object to serialize
        file: Binary file handle open for writing
    """
    signed_data = secure_dumps(obj)
    file.write(signed_data)


def secure_load(file: BinaryIO, allow_unsigned: bool = False) -> Any:
    """
    Securely deserialize from a file with HMAC verification.
    
    Args:
        file: Binary file handle open for reading
        allow_unsigned: If True, attempt to load unsigned pickle
        
    Returns:
        The deserialized object
    """
    signed_data = file.read()
    return secure_loads(signed_data, allow_unsigned=allow_unsigned)


def secure_dump_to_path(obj: Any, path: str | Path) -> None:
    """
    Securely serialize an object to a file path.
    
    Args:
        obj: Object to serialize
        path: File path to write to
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'wb') as f:
        secure_dump(obj, f)


def secure_load_from_path(path: str | Path, allow_unsigned: bool = False) -> Any:
    """
    Securely deserialize from a file path.
    
    Args:
        path: File path to read from
        allow_unsigned: If True, attempt to load unsigned pickle
        
    Returns:
        The deserialized object
    """
    with open(path, 'rb') as f:
        return secure_load(f, allow_unsigned=allow_unsigned)


def is_signed_pickle(data: bytes) -> bool:
    """
    Check if data appears to be in signed pickle format.
    
    Args:
        data: The bytes to check
        
    Returns:
        True if data appears to be signed pickle format
    """
    if len(data) < HEADER_SIZE + SIGNATURE_LENGTH + 1:
        return False

    try:
        length_bytes = data[:HEADER_SIZE]
        data_length = struct.unpack(HEADER_FORMAT, length_bytes)[0]
        expected_total = HEADER_SIZE + data_length + SIGNATURE_LENGTH
        return len(data) == expected_total
    except Exception:
        return False


def migrate_pickle_file(
    input_path: str | Path,
    output_path: str | Path | None = None
) -> bool:
    """
    Migrate an unsigned pickle file to signed format.
    
    Args:
        input_path: Path to unsigned pickle file
        output_path: Path for signed output (defaults to input_path)
        
    Returns:
        True if migration was successful
    """
    input_path = Path(input_path)
    output_path = Path(output_path) if output_path else input_path

    # Load unsigned pickle
    with open(input_path, 'rb') as f:
        data = f.read()

    # Check if already signed
    if is_signed_pickle(data):
        return True  # Already signed

    # Load and re-save with signature
    obj = pickle.loads(data)
    secure_dump_to_path(obj, output_path)

    return True
