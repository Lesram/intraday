# API Rate Limits

This document describes the rate limiting policies for the Intraday Trading Platform API.

## Overview

The API implements rate limiting to ensure fair usage, prevent abuse, and maintain system stability. Rate limits are enforced using a **sliding window algorithm** with sub-second precision.

## Rate Limit Headers

All API responses include rate limit headers:

| Header | Description | Example |
|--------|-------------|---------|
| `X-RateLimit-Limit` | Maximum requests allowed per window | `60` |
| `X-RateLimit-Remaining` | Requests remaining in current window | `45` |
| `X-RateLimit-Reset` | Unix timestamp when window resets | `1737590400` |
| `Retry-After` | Seconds to wait (only when rate limited) | `30` |

## Rate Limit Responses

When rate limits are exceeded, the API returns:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1737590400
Retry-After: 30

{
  "detail": "Rate limit exceeded. Please wait 30 seconds before retrying.",
  "code": "RATE_LIMIT_EXCEEDED",
  "retry_after": 30
}
```

## Endpoint-Specific Limits

Rate limits vary by endpoint based on the operational impact and expected usage patterns.

### Order Endpoints

| Endpoint | Per Minute | Per Second | Burst |
|----------|-----------|------------|-------|
| `POST /api/v1/orders` | 30 | 2 | 5 |
| `GET /api/v1/orders` | 30 | 2 | 5 |
| `GET /api/v1/orders/{id}` | 30 | 2 | 5 |
| `DELETE /api/v1/orders/{id}` | 30 | 2 | 5 |

**Rationale:** Order operations are critical and expensive. Lower limits prevent accidental flooding and ensure order execution quality.

### Portfolio & Positions

| Endpoint | Per Minute | Per Second | Burst |
|----------|-----------|------------|-------|
| `GET /api/v1/portfolio` | 120 | 5 | 10 |
| `GET /api/v1/positions` | 120 | 5 | 10 |
| `GET /api/v1/positions/{symbol}` | 120 | 5 | 10 |

**Rationale:** Portfolio/position queries are hot paths for trading UIs. Higher limits accommodate real-time dashboards.

### Trades & History

| Endpoint | Per Minute | Per Second | Burst |
|----------|-----------|------------|-------|
| `GET /api/v1/trades` | 60 | 3 | 10 |
| `GET /api/v1/trades/{id}` | 60 | 3 | 10 |

**Rationale:** Historical data queries are moderately expensive but frequently accessed.

### ML Models

| Endpoint | Per Minute | Per Second | Burst |
|----------|-----------|------------|-------|
| `GET /api/v1/models` | 30 | 2 | 5 |
| `POST /api/v1/models/train` | 10 | 1 | 2 |
| `POST /api/v1/models/predict` | 30 | 2 | 5 |

**Rationale:** ML operations are computationally expensive. Training endpoints have stricter limits.

### Strategies

| Endpoint | Per Minute | Per Second | Burst |
|----------|-----------|------------|-------|
| `GET /api/v1/strategies` | 60 | 3 | 10 |
| `POST /api/v1/strategies` | 30 | 2 | 5 |
| `PUT /api/v1/strategies/{id}` | 30 | 2 | 5 |
| `POST /api/v1/strategies/{id}/backtest` | 10 | 1 | 2 |

**Rationale:** Strategy operations vary in cost. Backtesting is expensive and tightly limited.

### Risk Management

| Endpoint | Per Minute | Per Second | Burst |
|----------|-----------|------------|-------|
| `GET /api/v1/risk/dashboard` | 120 | 5 | 10 |
| `GET /api/v1/risk/limits` | 60 | 3 | 10 |
| `PUT /api/v1/risk/limits` | 30 | 2 | 5 |
| `POST /api/v1/risk/emergency-stop` | 10 | 1 | 3 |

**Rationale:** Risk dashboard is high-frequency; emergency stop is sensitive and limited.

### System & Health

| Endpoint | Per Minute | Per Second | Burst |
|----------|-----------|------------|-------|
| `GET /api/v1/health` | 300 | 20 | 50 |
| `GET /api/v1/system/status` | 120 | 5 | 20 |
| `GET /api/v1/metrics` | 120 | 5 | 20 |

**Rationale:** Health checks are used by load balancers and monitoring. High limits ensure availability checks succeed.

### Authentication

| Endpoint | Per Minute | Per Second | Burst |
|----------|-----------|------------|-------|
| `POST /api/v1/auth/login` | 10 | 1 | 3 |
| `POST /api/v1/auth/register` | 5 | 1 | 2 |
| `POST /api/v1/auth/refresh` | 60 | 3 | 10 |
| `POST /api/v1/auth/logout` | 30 | 2 | 5 |

**Rationale:** Login/register have strict limits to prevent brute force attacks. Token refresh is more permissive.

### Default Limits

For endpoints not explicitly listed:

| Per Minute | Per Second | Burst |
|-----------|------------|-------|
| 60 | 5 | 15 |

## User vs Global Rate Limits

### Per-User Limits

All rate limits listed above are **per authenticated user**. Each user has their own rate limit buckets, ensuring one user's activity doesn't affect others.

### Global Limits

Additionally, the platform enforces global limits to protect infrastructure:

| Scope | Limit | Window |
|-------|-------|--------|
| Total API requests | 10,000 | 1 minute |
| WebSocket connections | 100 | per server |
| Concurrent order submissions | 50 | system-wide |

## Burst Handling

The API supports request **bursting** for short spikes in traffic:

1. **Burst size**: Each endpoint allows a burst of N requests without delay
2. **Token bucket**: Tokens replenish at the per-second rate
3. **Overflow**: Requests exceeding burst are queued or rejected

Example for orders:
- Burst size: 5 requests
- Refill rate: 2 requests/second
- After sending 5 requests instantly, wait 500ms per additional request

## WebSocket Rate Limits

WebSocket connections have separate rate limiting:

| Action | Limit |
|--------|-------|
| Messages per second | 10 |
| Subscriptions per connection | 50 |
| Connection attempts (failed) | 5 per minute |

## Best Practices

### 1. Implement Exponential Backoff

```python
import time
import random

def api_request_with_retry(func, max_retries=5):
    for attempt in range(max_retries):
        response = func()
        
        if response.status_code != 429:
            return response
        
        # Get retry delay from header or calculate
        retry_after = int(response.headers.get('Retry-After', 0))
        if not retry_after:
            retry_after = (2 ** attempt) + random.uniform(0, 1)
        
        time.sleep(retry_after)
    
    raise Exception("Max retries exceeded")
```

### 2. Monitor Rate Limit Headers

```python
def check_rate_limits(response):
    remaining = int(response.headers.get('X-RateLimit-Remaining', -1))
    limit = int(response.headers.get('X-RateLimit-Limit', -1))
    
    if remaining != -1 and limit != -1:
        usage_percent = (limit - remaining) / limit * 100
        if usage_percent > 80:
            print(f"Warning: {usage_percent:.1f}% of rate limit used")
```

### 3. Batch Requests When Possible

Instead of:
```python
for symbol in symbols:
    get_position(symbol)  # N requests
```

Use:
```python
get_positions(symbols)  # 1 request
```

### 4. Use WebSocket for Real-Time Data

For frequently updating data (quotes, positions), use WebSocket subscriptions instead of polling:

```python
# Bad: Polling every second
while True:
    get_quote("AAPL")  # 60 requests/minute
    time.sleep(1)

# Good: WebSocket subscription
ws.subscribe("quotes", ["AAPL"])  # Real-time, 0 rate limit impact
```

## Configuration

Rate limits can be configured via environment variables for self-hosted deployments:

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_ENABLED` | Enable/disable rate limiting | `true` |
| `RATE_LIMIT_DEFAULT_PER_MINUTE` | Default requests per minute | `60` |
| `RATE_LIMIT_DEFAULT_BURST` | Default burst size | `15` |
| `RATE_LIMIT_REDIS_URL` | Redis URL for distributed limiting | (optional) |

## Rate Limit Tiers

For production deployments, different user tiers may have different limits:

| Tier | Multiplier | Example (Orders) |
|------|-----------|------------------|
| Free | 1x | 30/min |
| Pro | 3x | 90/min |
| Enterprise | 10x | 300/min |

Contact support for enterprise rate limit increases.

## Monitoring & Alerting

Rate limit violations are logged and can trigger alerts:

```json
{
  "level": "warning",
  "event": "rate_limit_exceeded",
  "user_id": "user_123",
  "endpoint": "/api/v1/orders",
  "limit": 30,
  "current": 31,
  "ip": "192.168.1.100"
}
```

## Changelog

| Date | Change |
|------|--------|
| 2026-01-18 | Initial rate limits documentation |
| 2026-01-18 | Added burst handling explanation |
| 2026-01-18 | Added WebSocket rate limits |
