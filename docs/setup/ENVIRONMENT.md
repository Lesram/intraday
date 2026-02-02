# Environment Variables Reference

**Last Updated:** October 7, 2025

## 🚨 CRITICAL: Standard Variable Names

The platform uses **STANDARDIZED** variable names. **DO NOT use old/deprecated names** - they won't work!

### ✅ CORRECT Variable Names (Use These!)

```bash
# Alpaca API Credentials
ALPACA_API_KEY_ID=PK_YOUR_KEY_ID_HERE           # Your Alpaca API Key ID
ALPACA_API_SECRET_KEY=YOUR_SECRET_KEY_HERE      # Your Alpaca Secret Key
ALPACA_PAPER=true                                # true for paper trading, false for live
ALPACA_BASE_URL=https://paper-api.alpaca.markets # Auto-set based on ALPACA_PAPER

# Broker Mode
USE_MOCK_BROKER=false  # false = Real Alpaca, true = Mock/Testing
```

### ❌ DEPRECATED Variable Names (DO NOT USE!)

```bash
# These NO LONGER WORK:
ALPACA_API_KEY=...        # ❌ Wrong! Use ALPACA_API_KEY_ID
ALPACA_SECRET_KEY=...     # ❌ Wrong! Use ALPACA_API_SECRET_KEY
```

## 📁 Environment Files

### `.env` (Main Configuration - NOT in Git)
Your main configuration file with real credentials. **NEVER commit this file!**

**Location:** `c:\Users\Marsel\intra\algotrading_platform\.env`

**Required Variables:**
```bash
# Alpaca Paper Trading
USE_MOCK_BROKER=false
ALPACA_PAPER=true
ALPACA_API_KEY_ID=your_key_here
ALPACA_API_SECRET_KEY=your_secret_here

# Database
DATABASE_URL=postgresql+asyncpg://algotrading_user:password@localhost:5432/algotrading

# Security
JWT_SECRET_KEY=your_random_64_character_secret_key_here
```

### `.env.example` (Template for New Developers)
Template showing all available variables. Safe to commit.

**Location:** `c:\Users\Marsel\intra\algotrading_platform\.env.example`

### `.env.alpaca_example` (Alpaca Setup Guide)
Detailed guide for configuring Alpaca API credentials.

**Location:** `c:\Users\Marsel\intra\algotrading_platform\.env.alpaca_example`

### `.env.production.template` (Production Template)
Template for production deployment with live trading.

**Location:** `c:\Users\Marsel\intra\algotrading_platform\.env.production.template`

### `.env.test` (Testing Configuration)
Configuration for running tests with mocks and SQLite.

**Location:** `c:\Users\Marsel\intra\algotrading_platform\.env.test`

## 🔑 Complete Variable Reference

### Alpaca Trading API

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ALPACA_API_KEY_ID` | **YES** | - | Alpaca API Key ID (starts with "PK" for paper, "AK" for live) |
| `ALPACA_API_SECRET_KEY` | **YES** | - | Alpaca API Secret Key (40 characters) |
| `ALPACA_PAPER` | No | `true` | Paper trading mode (`true`) or live trading (`false`) |
| `ALPACA_BASE_URL` | No | Auto-set | API endpoint (paper or live, set automatically) |
| `ALPACA_DATA_URL` | No | `https://data.alpaca.markets/v2` | Market data endpoint |
| `ALPACA_STREAM_URL` | No | Auto-set | WebSocket stream endpoint |
| `ALPACA_RATE_LIMIT_PER_MINUTE` | No | `200` | API rate limit |

### Broker Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `USE_MOCK_BROKER` | No | `false` | `true` = Mock fills (testing), `false` = Real Alpaca orders |

### Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | **YES** | - | Full database connection URL |
| `DATABASE_POOL_SIZE` | No | `20` | Connection pool size |
| `DATABASE_MAX_OVERFLOW` | No | `10` | Max overflow connections |
| `DATABASE_ECHO` | No | `false` | SQL query logging |

### Application

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_ENVIRONMENT` | No | `development` | Environment: `development`, `production`, `testing` |
| `APP_HOST` | No | `0.0.0.0` | Server bind address |
| `APP_PORT` | No | `8000` | Server port |
| `APP_LOG_LEVEL` | No | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `DEBUG` | No | `false` | Debug mode |

### Security

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_SECRET_KEY` | **YES** | - | Secret key for JWT tokens (64+ characters) |
| `JWT_ALGORITHM` | No | `HS256` | JWT algorithm |
| `JWT_EXPIRE_MINUTES` | No | `60` | Token expiration time |

### CORS

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_CORS_ORIGINS` | No | `["http://localhost:5173"]` | Allowed CORS origins (JSON array) |

## 🔄 Variable Name Compatibility

The `AlpacaBrokerClient` has been updated to support **multiple naming conventions** for backward compatibility:

```python
# All of these are checked in order:
self.api_key = (
    os.getenv("ALPACA_API_KEY_ID") or      # ✅ Standard (preferred)
    os.getenv("ALPACA_API_KEY") or         # Legacy support
    os.getenv("APCA_API_KEY_ID")           # Alpaca SDK default
)

self.api_secret = (
    os.getenv("ALPACA_API_SECRET_KEY") or  # ✅ Standard (preferred)
    os.getenv("ALPACA_SECRET_KEY") or      # Legacy support
    os.getenv("APCA_API_SECRET_KEY")       # Alpaca SDK default
)
```

**Recommendation:** Use `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY` (standard names) in all new configurations.

## 🧪 Testing vs Production

### Development/Paper Trading (Current Setup)
```bash
USE_MOCK_BROKER=false
ALPACA_PAPER=true
ALPACA_API_KEY_ID=PK...  # Paper trading key
ALPACA_API_SECRET_KEY=...
```

### Unit Tests
```bash
USE_MOCK_BROKER=true  # Fast mock fills for testing
DATABASE_URL=sqlite:///./test_trading_platform.db
```

### Production (Live Trading) ⚠️
```bash
USE_MOCK_BROKER=false
ALPACA_PAPER=false  # ⚠️ LIVE TRADING - REAL MONEY!
ALPACA_API_KEY_ID=AK...  # Live trading key (starts with AK)
ALPACA_API_SECRET_KEY=...
DATABASE_URL=postgresql+asyncpg://...  # Production database
```

## 📝 How to Set Up

### 1. Get Alpaca API Credentials

1. Go to https://app.alpaca.markets/paper/dashboard/overview
2. Navigate to: **Your Account → API Keys**
3. Click **Generate New Key**
4. Copy the **Key ID** (starts with `PK` for paper)
5. Copy the **Secret Key** (40 characters)

### 2. Update Your .env File

```bash
# Open your .env file
code .env

# Add/update these lines:
USE_MOCK_BROKER=false
ALPACA_PAPER=true
ALPACA_API_KEY_ID=PK_YOUR_KEY_ID_HERE
ALPACA_API_SECRET_KEY=YOUR_SECRET_KEY_HERE
```

### 3. Restart Backend Server

```bash
# Stop backend (Ctrl+C)
# Start backend
uvicorn backend.api.main:app --reload
```

### 4. Verify Configuration

Check logs for:
```
AlpacaBrokerClient initialized: is_paper=True, base_url=https://paper-api.alpaca.markets
AlpacaOutboxDispatcher initialized: use_mock_broker=False
```

## 🐛 Troubleshooting

### Orders Not Appearing in Alpaca Dashboard

**Symptoms:** Order submits successfully but doesn't show in Alpaca
**Cause:** `USE_MOCK_BROKER=true` (mock broker is enabled)
**Solution:** Set `USE_MOCK_BROKER=false` in `.env`

### "Alpaca API credentials not configured"

**Symptoms:** Error in logs when submitting order
**Cause:** Missing or incorrect variable names
**Solution:** 
1. Check `.env` has `ALPACA_API_KEY_ID` (not `ALPACA_API_KEY`)
2. Check `.env` has `ALPACA_API_SECRET_KEY` (not `ALPACA_SECRET_KEY`)
3. Restart backend server

### Orders Have "MOCK_" Prefix

**Symptoms:** Order IDs like `MOCK_AAPL_1759864517`
**Cause:** Mock broker is enabled
**Solution:** Set `USE_MOCK_BROKER=false` and restart

### Database Connection Failed

**Symptoms:** `'UnifiedSettings' object has no attribute 'database'`
**Cause:** Database connection error (fixed in code)
**Solution:** Already fixed in `unified_database.py`

## 📊 Configuration Check Script

Run this to verify your configuration:

```python
import os
print(f"USE_MOCK_BROKER: {os.getenv('USE_MOCK_BROKER', 'not set')}")
print(f"ALPACA_PAPER: {os.getenv('ALPACA_PAPER', 'not set')}")
print(f"ALPACA_API_KEY_ID: {'✅ Set' if os.getenv('ALPACA_API_KEY_ID') else '❌ NOT SET'}")
print(f"ALPACA_API_SECRET_KEY: {'✅ Set' if os.getenv('ALPACA_API_SECRET_KEY') else '❌ NOT SET'}")
```

Expected output:
```
USE_MOCK_BROKER: false
ALPACA_PAPER: true
ALPACA_API_KEY_ID: ✅ Set
ALPACA_API_SECRET_KEY: ✅ Set
```

## 🔒 Security Best Practices

1. **NEVER commit `.env` files** - Already in `.gitignore`
2. **Use strong JWT secrets** - 64+ random characters
3. **Rotate API keys regularly** - Every 90 days
4. **Use paper trading for development** - `ALPACA_PAPER=true`
5. **Separate credentials for prod/dev** - Different keys
6. **Monitor API usage** - Stay within rate limits

## 📚 Related Documentation

- [MOCK_DATA_ELIMINATION_PLAN.md](./MOCK_DATA_ELIMINATION_PLAN.md) - Mock data removal strategy
- [ALPACA_SYNC_QUICKSTART.md](./ALPACA_SYNC_QUICKSTART.md) - Alpaca integration guide
- [MASTER_IMPLEMENTATION_PLAN.md](./MASTER_IMPLEMENTATION_PLAN.md) - Overall project plan
