# Quick Start Guide

Get the platform running locally in under 10 minutes.

## Prerequisites

- **Python 3.11+** with pip
- **Node.js 18+** with npm
- **Docker** and Docker Compose (for PostgreSQL + Redis)
- **Alpaca** paper trading account ([signup](https://app.alpaca.markets/signup))

## 1. Clone and Install

```bash
git clone <repo-url> algotrading_platform
cd algotrading_platform

# Backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"

# Frontend
cd frontend
npm install
cd ..
```

## 2. Start Services

```bash
docker-compose up -d db redis
```

This starts PostgreSQL on port 5432 and Redis on port 6379.

## 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Required
DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading
JWT_SECRET_KEY=<random-secret-at-least-32-chars>
REDIS_URL=redis://localhost:6379/0

# Alpaca (paper trading)
ALPACA_API_KEY_ID=<your-key>
ALPACA_API_SECRET_KEY=<your-secret>
ALPACA_PAPER=true

# Optional: Enable Living Organism
ORGANISM_ENABLED=1
ENABLE_ORGANISM_SCHEDULER=1
```

See [ENVIRONMENT.md](ENVIRONMENT.md) for the full variable reference.

## 4. Initialize Database

```bash
alembic -c alembic.ini upgrade head
```

## 5. Create Admin User

```bash
python scripts/unlock_admin.py
```

## 6. Start the Platform

Terminal 1 — Backend:
```bash
python main.py
```

Terminal 2 — Frontend:
```bash
cd frontend
npm run dev
```

## 7. Verify

- Open **http://localhost:5173** in your browser
- Log in with admin credentials
- Check the Dashboard shows portfolio data from Alpaca
- If `ORGANISM_ENABLED=1`, the Organism Dashboard should show tick activity

### Automated Verification

```bash
# Smoke test (requires running backend)
python scripts/smoke_test_live.py

# Trading verification
python scripts/trading_verification.py
```

## Common Issues

| Issue | Solution |
|-------|----------|
| `DATABASE_URL not set` | Ensure `.env` exists and has `DATABASE_URL` |
| `Connection refused` on port 5432 | Run `docker-compose up -d db` |
| Frontend CORS errors | Backend must be on port 8000, frontend on 5173 |
| `alembic upgrade` fails | Ensure PostgreSQL is running and DB exists |

## Next Steps

- [Database Setup](DATABASE.md) — Advanced DB configuration
- [Authentication](AUTHENTICATION.md) — Auth system details
- [Architecture Overview](../architecture/SYSTEM_OVERVIEW.md) — System design
- [Test Strategy](../testing/TEST_STRATEGY.md) — Running tests
