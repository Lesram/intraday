#!/bin/bash
# Docker container entrypoint script
# Handles database migrations and application startup

set -e

echo "=============================================="
echo "  Trading Platform Container Startup"
echo "=============================================="

# Wait for database to be ready
echo "[1/4] Waiting for database to be ready..."
MAX_RETRIES=30
RETRY_INTERVAL=2

for i in $(seq 1 $MAX_RETRIES); do
    if python -c "
import asyncio
import asyncpg
import os

async def check_db():
    url = os.getenv('DATABASE_URL', '')
    # Extract connection params from URL
    if 'postgresql+asyncpg://' in url:
        url = url.replace('postgresql+asyncpg://', 'postgresql://')
    try:
        conn = await asyncpg.connect(url)
        await conn.close()
        return True
    except Exception as e:
        return False

result = asyncio.run(check_db())
exit(0 if result else 1)
" 2>/dev/null; then
        echo "   ✓ Database is ready"
        break
    fi
    
    if [ $i -eq $MAX_RETRIES ]; then
        echo "   ✗ Database not ready after $MAX_RETRIES attempts, exiting"
        exit 1
    fi
    
    echo "   Waiting for database... (attempt $i/$MAX_RETRIES)"
    sleep $RETRY_INTERVAL
done

# Run database migrations
echo "[2/4] Running database migrations..."
if alembic upgrade head; then
    echo "   ✓ Migrations completed successfully"
else
    echo "   ⚠ Migration warning (may already be applied)"
fi

# Verify critical tables exist
echo "[3/4] Verifying database schema..."
python -c "
import asyncio
import asyncpg
import os
import sys

async def verify_schema():
    url = os.getenv('DATABASE_URL', '')
    if 'postgresql+asyncpg://' in url:
        url = url.replace('postgresql+asyncpg://', 'postgresql://')
    
    required_tables = ['users', 'orders', 'positions', 'outbox_events', 'executions']
    
    try:
        conn = await asyncpg.connect(url)
        result = await conn.fetch('''
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
        ''')
        existing_tables = [row['table_name'] for row in result]
        await conn.close()
        
        missing = [t for t in required_tables if t not in existing_tables]
        if missing:
            print(f'   ✗ Missing tables: {missing}')
            sys.exit(1)
        else:
            print(f'   ✓ All {len(required_tables)} critical tables present')
            return True
    except Exception as e:
        print(f'   ✗ Schema verification failed: {e}')
        sys.exit(1)

asyncio.run(verify_schema())
" || exit 1

# Start the application
echo "[4/4] Starting application server..."
echo "=============================================="
echo ""

# Execute the main command (uvicorn)
exec "$@"
