"""
Database migration runner for creating users table.
Run this script to apply the users table migration.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from backend.database import DatabaseManager
from backend.config.unified import get_database_url


async def run_migration():
    """Run the users table migration."""
    print("🔄 Starting database migration...")
    
    # Get database URL
    db_url = get_database_url()
    print(f"📊 Database: {db_url}")
    
    # For SQLite, convert to sync URL for raw SQL execution
    if db_url.startswith('sqlite'):
        import sqlite3
        db_path = db_url.replace('sqlite:///', '').replace('sqlite:', '')
        print("Using SQLite database")
        return await run_sqlite_migration(db_path)
    else:
        # For PostgreSQL, use async approach
        return await run_async_migration(db_url)


async def run_sqlite_migration(db_path: str) -> bool:
    """Run migration for SQLite database."""
    import sqlite3
    
    try:
        # Read SQLite-specific migration SQL
        migration_path = Path(__file__).parent / "migrations" / "001_create_users_table_sqlite.sql"
        
        if not migration_path.exists():
            print(f"❌ Migration file not found: {migration_path}")
            return False
        
        print(f"📄 Reading migration: {migration_path}")
        migration_sql = migration_path.read_text()
        
        print("🔨 Executing migration...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Execute the entire SQL script
        cursor.executescript(migration_sql)
        
        conn.commit()
        
        # Verify table was created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if cursor.fetchone():
            print("✅ Users table created successfully!")
            
            # Check if admin user exists
            cursor.execute("SELECT username, roles FROM users WHERE username = 'admin'")
            admin = cursor.fetchone()
            if admin:
                print(f"\n👤 Admin user verified:")
                print(f"   Username: {admin[0]}")
                print(f"   Roles: {admin[1]}")
                print(f"   Password: admin123")
                print(f"   ⚠️  CHANGE THIS PASSWORD IN PRODUCTION!")
        else:
            print("⚠️  Warning: Users table may not have been created")
        
        conn.close()
        
        print("\n📋 Users table structure:")
        print("   - id (INTEGER PRIMARY KEY)")
        print("   - username (TEXT UNIQUE)")
        print("   - hashed_password (TEXT)")
        print("   - roles (TEXT - JSON array)")
        print("   - is_active (INTEGER)")
        print("   - failed_login_attempts (INTEGER)")
        print("   - locked_until (TIMESTAMP)")
        print("   - created_at, updated_at, last_login (TIMESTAMP)")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_async_migration(db_url: str) -> bool:
    """Run migration for PostgreSQL database."""
    # Initialize database manager
    db_manager = DatabaseManager(db_url)
    await db_manager.initialize()
    
    print("✅ Database connection established")
    
    # Read migration SQL
    migration_path = Path(__file__).parent / "migrations" / "001_create_users_table.sql"
    
    if not migration_path.exists():
        print(f"❌ Migration file not found: {migration_path}")
        return False
    
    print(f"📄 Reading migration: {migration_path}")
    migration_sql = migration_path.read_text()
    
    # Execute migration
    try:
        print("🔨 Executing migration...")
        async with db_manager.get_session() as session:
            # Split into individual statements
            statements = [s.strip() for s in migration_sql.split(';') if s.strip() and not s.strip().startswith('--')]
            
            for i, statement in enumerate(statements, 1):
                if statement:
                    print(f"   Executing statement {i}/{len(statements)}...")
                    await session.execute(text(statement))
            
            await session.commit()
        
        print("✅ Migration completed successfully!")
        print("\n📋 Users table created with:")
        print("   - username (unique)")
        print("   - hashed_password")
        print("   - roles (array)")
        print("   - is_active (boolean)")
        print("   - failed_login_attempts (integer)")
        print("   - locked_until (timestamp)")
        print("   - created_at, updated_at, last_login")
        print("\n👤 Default admin user created:")
        print("   Username: admin")
        print("   Password: admin123")
        print("   ⚠️  CHANGE THIS PASSWORD IN PRODUCTION!")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await db_manager.close()


if __name__ == "__main__":
    print("=" * 60)
    print("DATABASE MIGRATION: Create Users Table")
    print("=" * 60)
    print()
    
    success = asyncio.run(run_migration())
    
    print()
    print("=" * 60)
    if success:
        print("✅ Migration completed successfully!")
    else:
        print("❌ Migration failed!")
        sys.exit(1)
    print("=" * 60)
