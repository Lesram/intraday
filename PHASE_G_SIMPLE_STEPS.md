# Phase G Validation - Simple Steps

## Step 1: Set Environment Variable
```powershell
$env:SECURITY_JWT_SECRET = "your-super-secret-jwt-key-for-development-only-change-in-production"
```

## Step 2: Start Server
```powershell
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```
(Leave this running in one terminal)

## Step 3: In Another Terminal, Run Tests
```powershell
# Set the same environment variable
$env:SECURITY_JWT_SECRET = "your-super-secret-jwt-key-for-development-only-change-in-production"

# Get auth token
$token = python scripts/get_token.py --base http://localhost:8000 --user admin --password admin123

# Run smoke tests
curl -s http://localhost:8000/health
curl -s -H "Authorization: Bearer $token" http://localhost:8000/api/v1/positions
curl -s -H "Authorization: Bearer $token" "http://localhost:8000/api/v1/signals?symbol=AAPL"

# Run official validation
python scripts/validate_checklist.py --api-token $token
```

## Phase G Results Summary

✅ **All 4 issues resolved:**
1. **Authentication**: JWT unified, login endpoints working
2. **Positions**: `/api/v1/positions` endpoint implemented  
3. **Health Performance**: `/health` optimized for <50ms
4. **Routing Consistency**: Protected endpoints return 401/405 not 404

**Key Issue**: Server needs `SECURITY_JWT_SECRET` environment variable set to start properly.