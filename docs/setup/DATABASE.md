# Database Setup Guide

## Overview

This application **requires** a PostgreSQL database. SQLite is **only** used for automated tests.

## Quick Start (Recommended)

### 1. Start PostgreSQL with Docker

```powershell
# Navigate to project directory
cd C:\Users\Marsel\intra\algotrading_platform

# Start PostgreSQL (and other services)
docker-compose up -d db

# Verify it's running
docker-compose ps
```

### 2. Set Environment Variable

**PowerShell (Windows):**
```powershell
$env:DATABASE_URL = "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"
```

**Bash/Zsh (Linux/Mac):**
```bash
export DATABASE_URL="postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"
```

### 3. Start the Application

```powershell
# Start backend
python main.py

# Or with uvicorn
python -m uvicorn backend.api.main:app --reload --port 8000
```

---

## Alternative: Local PostgreSQL Installation

If you don't want to use Docker:

### Install PostgreSQL

**Windows:**
- Download from: https://www.postgresql.org/download/windows/
- Use default port: 5432

**Mac (Homebrew):**
```bash
brew install postgresql@16
brew services start postgresql@16
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install postgresql-16
sudo systemctl start postgresql
```

### Create Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database and user
CREATE DATABASE algotrading;
CREATE USER trading WITH PASSWORD 'trading_password';
GRANT ALL PRIVILEGES ON DATABASE algotrading TO trading;
\q
```

### Set Environment Variable

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"
```

---

## Environment Variables

### Required

- `DATABASE_URL` - PostgreSQL connection string (REQUIRED)

### Optional

- `DATABASE_POOL_SIZE` - Connection pool size (default: 10)
- `DATABASE_MAX_OVERFLOW` - Max overflow connections (default: 20)
- `DATABASE_POOL_TIMEOUT` - Pool checkout timeout (default: 30)
- `DATABASE_ECHO` - Log SQL queries (default: false)

### Example .env File

Create a `.env` file in the project root:

```env
# Database Configuration
DATABASE_URL=postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30
DATABASE_ECHO=false

# Application Settings
APP_ENVIRONMENT=development
APP_LOG_LEVEL=INFO
APP_DEBUG=false

# Security (change in production!)
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
```

---

## Testing

Tests use **in-memory SQLite** automatically. You don't need to configure anything.

```powershell
# Run tests (uses SQLite automatically)
pytest

# Run specific test file
pytest tests/test_user_service.py

# Run with coverage
pytest --cov=backend --cov-report=html
```

The test configuration in `test/conftest.py` automatically sets:
```python
DATABASE_URL = "sqlite+aiosqlite:///:memory:"
```

---

## Docker Compose Services

The `docker-compose.yml` includes:

### PostgreSQL Database
- **Port:** 5432
- **Database:** algotrading
- **User:** trading
- **Password:** trading_password
- **Data:** Persisted in `postgres_data` volume

### Redis Cache
- **Port:** 6379
- **Memory:** 256MB max

### Full Stack

```powershell
# Start everything (API + DB + Redis)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop everything
docker-compose down

# Remove volumes (DELETES DATA)
docker-compose down -v
```

---

## Troubleshooting

### Error: "DATABASE_URL environment variable is required"

**Solution:** Set the DATABASE_URL environment variable as shown above.

### Error: "Connection refused" or "Can't connect to PostgreSQL"

**Solution:** 
1. Check if PostgreSQL is running: `docker-compose ps`
2. If not running: `docker-compose up -d db`
3. Check logs: `docker-compose logs db`

### Error: "Docker won't start"

**Solution:**
- Restart Docker Desktop
- Or restart your system
- Check Docker Desktop settings

### Database Schema Issues

If you encounter schema errors:

```powershell
# Stop the backend
# Drop and recreate the database
docker-compose down
docker volume rm algotrading_platform_postgres_data
docker-compose up -d db

# The schema will be created automatically on next startup
```

---

## Production Deployment

For production, use managed PostgreSQL services:

- **AWS:** RDS PostgreSQL
- **Azure:** Azure Database for PostgreSQL
- **Google Cloud:** Cloud SQL for PostgreSQL
- **Heroku:** Heroku Postgres
- **DigitalOcean:** Managed Databases

Example production DATABASE_URL:
```
postgresql+asyncpg://username:password@prod-db.example.com:5432/algotrading?ssl=require
```

---

## Migration from SQLite

If you have data in an old SQLite database:

1. Export data from SQLite
2. Start PostgreSQL
3. Import data using `pg_restore` or custom migration script

**Note:** The previous SQLite fallback has been removed to prevent schema inconsistencies and ensure production readiness.

---

## Additional Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [SQLAlchemy Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
