-- Initialize trading platform database
-- Production-ready PostgreSQL setup

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create indexes for better performance
-- Note: Actual table creation handled by SQLAlchemy migrations

-- Performance optimization settings
ALTER DATABASE trading_platform SET timezone TO 'UTC';
ALTER DATABASE trading_platform SET default_transaction_isolation TO 'read committed';

-- Create roles for different access levels
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'trading_readonly') THEN
        CREATE ROLE trading_readonly;
    END IF;
    
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'trading_readwrite') THEN
        CREATE ROLE trading_readwrite;
    END IF;
END
$$;

-- Grant permissions
GRANT CONNECT ON DATABASE trading_platform TO trading_readonly;
GRANT CONNECT ON DATABASE trading_platform TO trading_readwrite;

-- Schema will be created by SQLAlchemy, but prepare for it
COMMENT ON DATABASE trading_platform IS 'Trading Platform Production Database - Optimized for concurrent operations';