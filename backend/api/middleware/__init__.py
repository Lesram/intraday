"""
API Middleware Package

Contains custom middleware for request processing:
- deduplication: Prevents duplicate order submissions using idempotency keys
- rate_limit: Per-endpoint rate limiting with sliding window algorithm
"""

from .deduplication import RequestDeduplicationMiddleware
from .rate_limit import RateLimitConfig, RateLimitMiddleware

__all__ = ["RequestDeduplicationMiddleware", "RateLimitMiddleware", "RateLimitConfig"]
