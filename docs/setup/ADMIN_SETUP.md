# Admin Account Setup Instructions

## Quick Setup (Recommended)

### Option 1: Use the Frontend (Easiest)
1. Open `http://localhost:5173` in your browser
2. Click "Register" on the login page
3. Fill in the registration form:
   - **Name**: Admin User
   - **Email**: admin@test.com
   - **Password**: Admin123!@#Test (must have uppercase, lowercase, number, special char)
   - **Confirm Password**: Admin123!@#Test
4. Click "Create Account"
5. You'll be automatically logged in!

### Option 2: Using API (if backend has database configured)
```powershell
$body = @{
    email='admin@test.com'
    password='Admin123!@#Test'
    name='Admin User'
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/auth/login' -Body $body -ContentType 'application/json'
```

Then login with:
- **Username**: admin@test.com
- **Password**: Admin123!@#Test

## If Login Still Fails

### Check Backend Configuration
Your backend needs `DATABASE_URL` environment variable set. Check:
```powershell
cd C:\Users\Marsel\intra\algotrading_platform
Get-Content .env
```

If `DATABASE_URL` is not set or using SQLite without proper setup, the backend uses in-memory storage which resets on restart.

### Restart Backend
If you made configuration changes:
```powershell
# Kill existing backend
Get-Process python | Where-Object {$_.Path -like "*algotrading_platform*"} | Stop-Process

# Start fresh
cd C:\Users\Marsel\intra\algotrading_platform
python -m uvicorn backend.api.factory:app --reload --port 8000
```

## Current Status

Based on testing:
- ✅ Backend API is running on `http://localhost:8000`
- ✅ Frontend is running on `http://localhost:5173`
- ✅ Registration endpoint works
- ❌ DATABASE_URL not configured (using in-memory storage)
- ⚠️  Passwords might not persist between backend restarts

## Troubleshooting

### "Invalid username or password"
- The backend uses **email as username** for login
- Try: username = `admin@test.com`, not just `admin`
- Password must match exactly what you registered with

### "Account is locked"
- Too many failed login attempts lock the account for 15 minutes
- Wait 15 minutes or restart the backend server

### Password Requirements
Must contain:
- At least 8 characters
- One uppercase letter
- One lowercase letter  
- One number
- One special character (!@#$%^&*)

## Recommended Production Setup

For production, configure PostgreSQL:
```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/trading_db
```

Then run migrations to create tables and seed admin user.
