"""Credential redaction for log text.

Standard library only, so the API logging bootstrap can use it before the rest
of the application is imported. Values are masked; the surrounding text stays:

* URL userinfo: ``redis://:pw@redis:6379/0`` -> ``redis://***REDACTED***@redis:6379/0``
* credential query parameters: ``/ws?token=abc`` -> ``/ws?token=***REDACTED***``
* JSON-style credential fields: ``{"token": "abc"}`` -> ``{"token": "***REDACTED***"}``
* ``Bearer <value>`` and JWT-shaped strings.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

MASK = "***REDACTED***"

# scheme://userinfo@host -- the userinfo runs to the last "@" before the host,
# so a password containing a raw "@" is masked as a whole.
URL_USERINFO_PATTERN = re.compile(
    r"(?P<scheme>\b[A-Za-z][A-Za-z0-9+.\-]*://)(?P<userinfo>[^\s/?#'\"<>]*)@"
)

SENSITIVE_QUERY_PARAM_PATTERN = re.compile(
    r"(?P<prefix>[?&;](?:access_token|refresh_token|id_token|token|jwt|auth|authorization"
    r"|api[_-]?key|apikey|api_secret|client_secret|secret|password|passwd|pwd)=)"
    r"(?P<value>[^&#\s'\"]*)",
    re.IGNORECASE,
)

JSON_CREDENTIAL_FIELD_PATTERN = re.compile(
    r"(?P<prefix>\"(?:token|access_token|refresh_token|id_token|jwt|authorization"
    r"|api_key|apikey|secret|password|passwd)\"\s*:\s*\")(?P<value>(?:[^\"\\]|\\.)*)\"",
    re.IGNORECASE,
)

BEARER_PATTERN = re.compile(r"(?P<prefix>\bBearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)

JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_\-]*\.eyJ[A-Za-z0-9_\-]*\.[A-Za-z0-9_\-]*")

# Matched against the case-folded text: HTTP auth schemes are case-insensitive
# ("BEARER", "bearer"), like BEARER_PATTERN itself.
_TRIGGERS = ("://", "=", '"', "bearer", "eyj")


def redact_credentials(text: str) -> str:
    """Return ``text`` with credential values masked (non-strings pass through)."""
    if not isinstance(text, str):
        return text
    folded = text.casefold()
    if not any(trigger in folded for trigger in _TRIGGERS):
        return text
    result = URL_USERINFO_PATTERN.sub(lambda m: f"{m.group('scheme')}{MASK}@", text)
    result = SENSITIVE_QUERY_PARAM_PATTERN.sub(lambda m: f"{m.group('prefix')}{MASK}", result)
    result = JSON_CREDENTIAL_FIELD_PATTERN.sub(lambda m: f'{m.group("prefix")}{MASK}"', result)
    result = BEARER_PATTERN.sub(lambda m: f"{m.group('prefix')}{MASK}", result)
    return JWT_PATTERN.sub(MASK, result)


def safe_url(url: str) -> str:
    """Describe a connection URL as ``scheme://host:port/path``.

    Userinfo, query string and fragment are dropped, so the result can be
    logged. Unparseable input falls back to :func:`redact_credentials`.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
    except (TypeError, ValueError):
        return redact_credentials(str(url))
    if not parts.scheme or not host:
        return redact_credentials(str(url))
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    return f"{parts.scheme}://{host}{port}{parts.path}"
