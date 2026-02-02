# Authentication System Documentation

## Overview

The platform uses **database-backed authentication** with JWT tokens. All authentication credentials are stored securely in the database with bcrypt password hashing and brute-force protection.

**✅ NO HARDCODED CREDENTIALS** - All credentials are managed via environment variables and database storage.

---

## 🔐 Security Features

### 1. **Database-Backed Authentication**
- All users stored in PostgreSQL database
- Passwords hashed with bcrypt (production-grade security)
- No hardcoded credentials in source code

### 2. **Brute-Force Protection**
- Account locked after 5 failed login attempts
- 15-minute lockout period
- Automatic unlock after timeout
- Failed attempts reset on successful login

### 3. **JWT Token Security**
- HS256 algorithm
- 60-minute token expiration
- Secure token generation with secret key
- Role-based access control (RBAC)

### 4. **Audit Trail**
- Last login timestamp tracking
- Failed login attempt logging
- Account lockout events logged

---

## 🚀 Setup Instructions

### Step 1: Configure Environment Variables

#### For Production (Kubernetes):

Edit `k8s/secrets.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: algotrading-secrets
stringData:
  # CRITICAL: Change these before deployment!
  admin-username: "admin"
  admin-password: "YOUR_STRONG_PASSWORD_HERE"  # Min 12 characters
```

#### For Local Development:

Create `.env` file (or copy from `.env.example`):

```bash
# Admin User Credentials
ADMIN_USERNAME=admin
ADMIN_PASSWORD=MyStr0ng!P@ssw0rd123  # Min 12 characters

# Database Connection
DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading

# JWT Configuration
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
```

#### For Testing:

Set in `pytest.ini` or as environment variables:

```bash
export TEST_ADMIN_USERNAME=testadmin
export TEST_ADMIN_PASSWORD=TestP@ssw0rd123
```

---

### Step 2: Create Admin User

#### Option A: Using Setup Script (Recommended)

```bash
# Set credentials via environment
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD='MyStr0ng!P@ssw0rd123'
export DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading

# Run setup script
python scripts/create_admin_user.py
```

#### Option B: Using Command-Line Arguments

```bash
python scripts/create_admin_user.py \
  --username admin \
  --password 'MyStr0ng!P@ssw0rd123' \
  --roles admin,trader
```

#### Option C: Using Kubernetes Job

Create `k8s/admin-user-job.yaml`:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: create-admin-user
  namespace: algotrading
spec:
  template:
    spec:
      containers:
      - name: create-admin
        image: algotrading-platform:latest
        command: ["python", "scripts/create_admin_user.py"]
        env:
        - name: ADMIN_USERNAME
          valueFrom:
            secretKeyRef:
              name: algotrading-secrets
              key: admin-username
        - name: ADMIN_PASSWORD
          valueFrom:
            secretKeyRef:
              name: algotrading-secrets
              key: admin-password
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: algotrading-secrets
              key: database-url
      restartPolicy: OnFailure
```

Deploy:

```bash
kubectl apply -f k8s/admin-user-job.yaml
kubectl logs job/create-admin-user -n algotrading
```

---

### Step 3: Verify Authentication

Test login endpoint:

```bash
# Get JWT token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"MyStr0ng!P@ssw0rd123"}'

# Response:
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}

# Verify token
curl -X GET http://localhost:8000/api/v1/auth/verify \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# Response:
{
  "sub": "admin",
  "roles": ["admin", "trader"],
  "iss": "algotrading-platform",
  "aud": "algotrading-api",
  "exp": 1696464000,
  "iat": 1696460400
}
```

---

## 📝 API Reference

### POST /api/v1/auth/login

**Request:**
```json
{
  "username": "admin",
  "password": "your_password"
}
```

**Response (Success):**
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Response (Failed - Invalid Credentials):**
```json
{
  "detail": "Invalid username or password, or account is locked due to too many failed login attempts"
}
```
HTTP Status: 401 Unauthorized

**Response (Failed - Account Locked):**
```json
{
  "detail": "Invalid username or password, or account is locked due to too many failed login attempts"
}
```
HTTP Status: 401 Unauthorized

### GET /api/v1/auth/verify

**Headers:**
```
Authorization: Bearer YOUR_JWT_TOKEN
```

**Response:**
```json
{
  "sub": "admin",
  "roles": ["admin", "trader"],
  "iss": "algotrading-platform",
  "aud": "algotrading-api",
  "exp": 1696464000,
  "iat": 1696460400
}
```

---

## 🧪 Testing

### Using Test Credentials

All test files should use the centralized test credentials helper:

```python
from test.test_credentials import get_test_admin_credentials, get_test_login_data

# Get credentials
username, password = get_test_admin_credentials()

# Get login data for API requests
login_data = get_test_login_data()
response = requests.post(f"{base_url}/api/v1/auth/login", json=login_data)
```

### Setting Test Credentials

#### Method 1: Environment Variables
```bash
export TEST_ADMIN_USERNAME=testadmin
export TEST_ADMIN_PASSWORD=TestP@ssw0rd123
pytest test/
```

#### Method 2: pytest.ini (Already Configured)
```ini
[pytest]
env =
    TEST_ADMIN_USERNAME=testadmin
    TEST_ADMIN_PASSWORD=TestP@ssw0rd123
```

### Creating Test User Before Tests

Add to your test setup:

```python
import pytest
from backend.infra.db import init_db
from backend.infra.users import UserRepository

@pytest.fixture(scope="session")
async def setup_test_user():
    """Create test admin user for integration tests."""
    from test.test_credentials import get_test_admin_credentials
    
    database_url = os.getenv("DATABASE_URL", "sqlite:///./test_trading_platform.db")
    engine, sessionmaker = init_db(database_url)
    
    async with sessionmaker() as session:
        user_repo = UserRepository(db_session=session)
        username, password = get_test_admin_credentials()
        
        try:
            await user_repo.create_user(username, password, ["admin", "trader"])
        except ValueError:
            pass  # User already exists
    
    yield
    
    await engine.dispose()
```

---

## 🔄 Migration from Hardcoded Credentials

### What Changed

**Before (Insecure):**
```python
# backend/api/routes/auth.py
if request.username == "admin" and request.password == "admin123":
    token = create_access_token(sub="admin", roles=["admin", "trader"])
    return LoginResponse(access_token=token, ...)
```

**After (Secure):**
```python
# backend/api/routes/auth.py
user_repo = UserRepository(db_session=db)
user = await user_repo.authenticate_user(request.username, request.password)

if not user:
    raise HTTPException(status_code=401, detail="Invalid credentials")

token = create_access_token(sub=user.username, roles=user.roles)
return LoginResponse(access_token=token, ...)
```

### Migration Checklist

- [x] Remove hardcoded `admin/admin123` from `backend/api/routes/auth.py`
- [x] Remove hardcoded admin creation from `backend/infra/users.py`
- [x] Add `ADMIN_USERNAME` and `ADMIN_PASSWORD` to `k8s/secrets.yaml`
- [x] Add admin credentials to `.env.example`
- [x] Create `scripts/create_admin_user.py` setup script
- [x] Add `TEST_ADMIN_USERNAME` and `TEST_ADMIN_PASSWORD` to `pytest.ini`
- [x] Create `test/test_credentials.py` helper module
- [ ] **TODO: Update existing test files to use `test.test_credentials`**
- [ ] **TODO: Run admin user creation script before deployment**
- [ ] **TODO: Change default admin password in production**

---

## 🛡️ Security Best Practices

### Password Requirements

✅ **Minimum length**: 12 characters  
✅ **Recommended length**: 16+ characters  
✅ **Include**: Uppercase, lowercase, numbers, special characters  
✅ **Avoid**: Dictionary words, personal information, common patterns  

### Production Deployment

1. **Change Default Credentials**
   ```bash
   # Generate strong password
   openssl rand -base64 32
   
   # Update k8s/secrets.yaml
   admin-password: "$(openssl rand -base64 32)"
   ```

2. **Rotate Credentials Regularly**
   - Schedule: Every 90 days
   - Method: Update user password in database
   - Documentation: Keep audit trail

3. **Secure Secret Storage**
   - Use Kubernetes Secrets (not ConfigMaps)
   - Enable encryption at rest
   - Limit secret access with RBAC

4. **Monitor Authentication**
   - Enable audit logging
   - Alert on failed login spikes
   - Monitor account lockouts

### Database Security

- Always use parameterized queries (already implemented)
- Enable SSL/TLS for database connections
- Use separate database user for application
- Grant minimum required privileges

---

## 🐛 Troubleshooting

### Issue: "Invalid username or password"

**Possible Causes:**
1. User not created in database
2. Wrong password
3. Account locked (5 failed attempts)

**Solution:**
```bash
# Verify user exists
python -c "
from backend.infra.db import init_db
from backend.infra.users import UserRepository
import asyncio
async def check():
    engine, sm = init_db('your_db_url')
    async with sm() as session:
        repo = UserRepository(session)
        user = await repo.get_user('admin')
        print(f'User found: {user}')
    await engine.dispose()
asyncio.run(check())
"

# Recreate user if needed
python scripts/create_admin_user.py --force
```

### Issue: "Account is locked"

**Cause:** Too many failed login attempts (5+)

**Solution:**
Wait 15 minutes or reset manually:

```python
# Reset failed attempts
from sqlalchemy import text
await session.execute(
    text("UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE username = :username"),
    {"username": "admin"}
)
await session.commit()
```

### Issue: Database connection error

**Check:**
1. Database is running
2. `DATABASE_URL` environment variable is set
3. Database credentials are correct
4. Network connectivity

```bash
# Test database connection
psql postgresql://trading:trading_password@localhost:5432/algotrading
```

---

## 📚 Additional Resources

- [JWT RFC 7519](https://datatracker.ietf.org/doc/html/rfc7519)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [bcrypt Password Hashing](https://github.com/pyca/bcrypt/)
- [FastAPI Security Documentation](https://fastapi.tiangolo.com/tutorial/security/)

---

## 📞 Support

For security issues, contact: security@yourcompany.com

For general questions, see: `docs/` directory or create an issue.
