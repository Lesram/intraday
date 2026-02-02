-- Migration: Add brute-force protection columns to existing users table
-- Author: System
-- Date: 2025-10-04
-- Description: Adds failed_login_attempts, locked_until, last_login, and roles columns

-- Add roles column (TEXT ARRAY)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'roles'
    ) THEN
        ALTER TABLE users ADD COLUMN roles TEXT[] NOT NULL DEFAULT '{}';
        RAISE NOTICE 'Added roles column';
    ELSE
        RAISE NOTICE 'roles column already exists';
    END IF;
END $$;

-- Add failed_login_attempts column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'failed_login_attempts'
    ) THEN
        ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0;
        RAISE NOTICE 'Added failed_login_attempts column';
    ELSE
        RAISE NOTICE 'failed_login_attempts column already exists';
    END IF;
END $$;

-- Add locked_until column
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'locked_until'
    ) THEN
        ALTER TABLE users ADD COLUMN locked_until TIMESTAMP WITH TIME ZONE;
        RAISE NOTICE 'Added locked_until column';
    ELSE
        RAISE NOTICE 'locked_until column already exists';
    END IF;
END $$;

-- Add last_login column (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'last_login'
    ) THEN
        ALTER TABLE users ADD COLUMN last_login TIMESTAMP WITH TIME ZONE;
        RAISE NOTICE 'Added last_login column';
    ELSE
        RAISE NOTICE 'last_login column already exists';
    END IF;
END $$;

-- Create index on locked_until (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE schemaname = 'public' AND tablename = 'users' AND indexname = 'idx_users_locked_until'
    ) THEN
        CREATE INDEX idx_users_locked_until ON users(locked_until);
        RAISE NOTICE 'Created index on locked_until';
    ELSE
        RAISE NOTICE 'idx_users_locked_until already exists';
    END IF;
END $$;

-- Initialize failed_login_attempts to 0 for existing users
UPDATE users SET failed_login_attempts = 0 WHERE failed_login_attempts IS NULL;

-- Add default 'user' role to existing users without roles
UPDATE users SET roles = ARRAY['user'] WHERE roles = '{}' OR roles IS NULL;

-- Verify the changes
DO $$
DECLARE
    col_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_name = 'users' 
    AND column_name IN ('roles', 'failed_login_attempts', 'locked_until', 'last_login');
    
    IF col_count = 4 THEN
        RAISE NOTICE '✅ All brute-force protection columns added successfully';
    ELSE
        RAISE WARNING '⚠️  Expected 4 columns, found %', col_count;
    END IF;
END $$;

COMMENT ON COLUMN users.failed_login_attempts IS 'Number of consecutive failed login attempts';
COMMENT ON COLUMN users.locked_until IS 'Account locked until this timestamp (for brute force protection)';
COMMENT ON COLUMN users.last_login IS 'Timestamp of last successful login';
COMMENT ON COLUMN users.roles IS 'User roles array (e.g., admin, trader, user)';
