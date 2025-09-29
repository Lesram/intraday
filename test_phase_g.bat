@echo off
REM Set environment variables for Phase G validation
set SECURITY_JWT_SECRET=your-super-secret-jwt-key-for-development-only-change-in-production

REM Start server
echo Starting server with JWT secret...
start /B uvicorn backend.api.main:app --host 0.0.0.0 --port 8000

REM Wait for server
echo Waiting for server to start...
timeout /t 5 /nobreak > nul

REM Test endpoints
echo.
echo Testing endpoints...
curl -s http://localhost:8000/health
echo.

REM Get token and test authenticated endpoints
python -c "
import os, sys, requests
sys.path.append('.')
try:
    from backend.infra.security import create_access_token
    token = create_access_token('admin', ['admin', 'trader'], 60)
    headers = {'Authorization': f'Bearer {token}'}
    
    print('Testing /api/v1/positions...')
    r = requests.get('http://localhost:8000/api/v1/positions', headers=headers, timeout=5)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'Positions count: {len(data)}')
    
    print('\nTesting /api/v1/signals...')
    r = requests.get('http://localhost:8000/api/v1/signals?symbol=AAPL', headers=headers, timeout=5)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'Signal action: {data.get(\"action\", \"none\")}')
        
except Exception as e:
    print(f'Error: {e}')
"

REM Kill server
taskkill /F /IM uvicorn.exe > nul 2>&1
taskkill /F /IM python.exe > nul 2>&1