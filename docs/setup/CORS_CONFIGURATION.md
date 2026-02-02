# CORS Configuration Guide

## Overview

Cross-Origin Resource Sharing (CORS) configuration for the Trading Platform API to enable secure UI integration.

## Current Configuration

The API is configured with CORS middleware that supports:

### Allowed Origins
- `http://localhost:3000` (React/Next.js default)
- `https://localhost:3000` (HTTPS development)
- `http://localhost:5173` (Vite default)
- `https://localhost:5173` (Vite HTTPS)
- `http://localhost:3001` (Alternative Next.js port)
- Custom staging origins (configurable)

### Allowed Methods
- `GET` - Reading data
- `POST` - Creating resources  
- `PUT` - Updating resources
- `DELETE` - Deleting resources
- `OPTIONS` - Preflight requests
- `PATCH` - Partial updates

### Allowed Headers
- `Authorization` - JWT bearer tokens
- `Content-Type` - Request content type
- `Accept` - Response content type preferences
- `Accept-Language` - Localization
- `Accept-Encoding` - Compression preferences
- `Origin` - Request origin
- `X-Requested-With` - AJAX identification
- Standard HTTP headers

### Exposed Headers
- `Content-Length` - Response size
- `Content-Range` - Pagination info
- `X-Total-Count` - Total items in collection
- `X-Rate-Limit-Remaining` - Rate limiting info
- `X-Rate-Limit-Reset` - Rate limit reset time

## Environment-Specific Configuration

### Development
```python
# Automatically configured for local development
cors_origins = [
    "http://localhost:3000",   # React/Next.js
    "https://localhost:3000",  # HTTPS development
    "http://localhost:5173",   # Vite
    "https://localhost:5173",  # Vite HTTPS
    "http://localhost:3001",   # Alternative Next.js
]
```

### Staging
```bash
# Environment variables for staging
export CORS_ORIGINS="https://staging-ui.trading-platform.com,http://localhost:3000"

# Or in settings.py
class StagingSettings:
    api = {
        "cors_origins": [
            "https://staging-ui.trading-platform.com",
            "http://localhost:3000"  # Keep for local testing
        ]
    }
```

### Production
```bash
# Environment variables for production
export CORS_ORIGINS="https://app.trading-platform.com"

# Or in settings.py
class ProductionSettings:
    api = {
        "cors_origins": [
            "https://app.trading-platform.com"
        ]
    }
```

## Authentication with CORS

### JWT Bearer Token Usage
```javascript
// Frontend JavaScript example
const response = await fetch('http://localhost:8000/api/v1/signals', {
  method: 'GET',
  headers: {
    'Authorization': 'Bearer ' + jwtToken,
    'Content-Type': 'application/json'
  },
  credentials: 'include'  // Important for CORS with credentials
});
```

### TypeScript API Client Usage
```typescript
import { TradingApiClient } from '@trading-platform/api-client';

const client = new TradingApiClient('http://localhost:8000');
client.setAuthToken('your-jwt-token');

// Client handles CORS headers automatically
const signals = await client.getSignals('AAPL');
```

## UI Framework Integration

### React/Next.js
```typescript
// next.config.js for local development
module.exports = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*'
      }
    ];
  }
};

// Or use environment variables
// NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Vue/Vite
```typescript
// vite.config.ts for local development
import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false
      }
    }
  }
});

// Or use environment variables
// VITE_API_URL=http://localhost:8000
```

### Angular
```typescript
// proxy.conf.json for local development
{
  "/api/*": {
    "target": "http://localhost:8000",
    "secure": false,
    "changeOrigin": true,
    "logLevel": "debug"
  }
}

// angular.json
"serve": {
  "builder": "@angular-devkit/build-angular:dev-server",
  "options": {
    "proxyConfig": "proxy.conf.json"
  }
}
```

## Security Considerations

### Production Checklist
- [ ] **Restrict origins** to only production UI domain
- [ ] **Use HTTPS** for all production origins
- [ ] **Validate JWT tokens** on all protected endpoints
- [ ] **Enable rate limiting** to prevent abuse
- [ ] **Monitor CORS errors** in application logs
- [ ] **Audit allowed headers** regularly

### Common Issues

#### 1. CORS Preflight Failures
```javascript
// Problem: Complex requests trigger preflight OPTIONS request
// Solution: Ensure OPTIONS method is allowed and responds correctly

// The API automatically handles OPTIONS requests
// No additional configuration needed
```

#### 2. Credential Issues
```javascript
// Problem: JWT token not sent with requests
// Solution: Set credentials and ensure server allows credentials

fetch('/api/v1/orders', {
  credentials: 'include',  // Important!
  headers: { 'Authorization': 'Bearer ' + token }
});
```

#### 3. Header Restrictions
```javascript
// Problem: Custom headers blocked by CORS
// Solution: Add header to allowed_headers list in CORS config

// Already configured for common headers:
// - Authorization (JWT)
// - Content-Type (JSON)
// - Accept (response format)
```

## Testing CORS Configuration

### Manual Testing
```bash
# Test preflight request
curl -X OPTIONS http://localhost:8000/api/v1/signals \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization" \
  -v

# Expected response includes:
# Access-Control-Allow-Origin: http://localhost:3000
# Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS, PATCH
# Access-Control-Allow-Headers: Authorization, Content-Type, ...
```

### Automated Testing
```javascript
// Use the TypeScript client for automated testing
import { TradingApiClient } from '@trading-platform/api-client';

const client = new TradingApiClient('http://localhost:8000');
client.setAuthToken(testToken);

// This will automatically handle CORS
const health = await client.healthCheck();
console.log('CORS working:', health.status === 'ok');
```

## Troubleshooting

### Common Error Messages

#### "CORS policy: No 'Access-Control-Allow-Origin'"
- **Cause**: Request origin not in allowed origins list
- **Solution**: Add origin to `cors_origins` configuration

#### "CORS policy: Request header field 'Authorization' is not allowed"  
- **Cause**: Authorization header not in allowed headers
- **Solution**: Already configured - check token format

#### "CORS policy: The value of the 'Access-Control-Allow-Credentials' header"
- **Cause**: Credentials mismatch between client and server
- **Solution**: Ensure both client and server have credentials enabled

### Debug Mode
```python
# Enable CORS debug logging in development
import logging

logging.getLogger("fastapi.middleware.cors").setLevel(logging.DEBUG)
```

## Updates for Staging UI

When your staging UI is deployed, update the configuration:

```python
# In backend/config/settings.py or environment variables
STAGING_CORS_ORIGINS = [
    "https://staging-ui.your-domain.com",
    "http://localhost:3000"  # Keep for local development
]
```

Or set via environment variable:
```bash
export CORS_ORIGINS="https://staging-ui.your-domain.com,http://localhost:3000"
```

The CORS middleware will automatically pick up these settings and allow your staging UI to connect to the API securely.

## Integration with Phase 5

This CORS configuration is designed to support Phase 5 limited rollout:

- ✅ **Local development** - Full support for all common UI frameworks
- ✅ **Staging environment** - Ready for staging UI deployment  
- ✅ **Security hardening** - Production-ready CORS restrictions
- ✅ **JWT authentication** - Full support for bearer token auth
- ✅ **API client integration** - Works seamlessly with TypeScript client

The configuration automatically adapts based on environment settings, making it safe for both development and production use.