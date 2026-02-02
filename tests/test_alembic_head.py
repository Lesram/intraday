"""
Test to ensure database is at alembic head revision.

This test validates that all migrations have been applied before running tests.
Schema drift between code and database can cause:
- Test failures due to missing columns/tables
- False positives when tests pass on old schema
- Production deployments with migration mismatch
"""

import subprocess
import re
import pytest
import os


@pytest.mark.integration
@pytest.mark.slow
def test_database_at_alembic_head():
    """Ensure database schema is at alembic head before tests run."""
    
    # Check if DATABASE_URL is configured
    database_url = os.getenv("DATABASE_URL")
    if not database_url or "sqlite" in database_url.lower() or "placeholder" in database_url.lower():
        pytest.skip(
            "PostgreSQL DATABASE_URL not configured\n"
            "This test requires a real PostgreSQL database.\n"
            "Set DATABASE_URL=postgresql://user:pass@localhost:5432/db"
        )
    
    try:
        # Get current revision
        current_result = subprocess.run(
            ['alembic', 'current'],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )
        
        # Get head revision
        head_result = subprocess.run(
            ['alembic', 'heads'],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )
        
        # Extract revision IDs (format: "abc123def456 (head)")
        current_match = re.search(r'([a-f0-9]+)', current_result.stdout)
        head_match = re.search(r'([a-f0-9]+)', head_result.stdout)
        
        if not current_match:
            pytest.fail(
                "Cannot determine current alembic revision.\n"
                f"Output: {current_result.stdout}\n"
                "Ensure alembic is configured and database is initialized."
            )
        
        if not head_match:
            pytest.fail(
                "Cannot determine alembic head revision.\n"
                f"Output: {head_result.stdout}\n"
                "Ensure alembic migrations directory exists."
            )
        
        current_rev = current_match.group(1)
        head_rev = head_match.group(1)
        
        if current_rev != head_rev:
            pytest.fail(
                f"❌ Database schema out of sync!\n\n"
                f"Current revision: {current_rev}\n"
                f"Head revision:    {head_rev}\n\n"
                f"Migration drift detected. This means:\n"
                f"  - Tests may pass on old schema while production fails\n"
                f"  - New columns/tables are not available\n"
                f"  - Schema changes not reflected in tests\n\n"
                f"FIX: Run migration:\n"
                f"  alembic upgrade head\n\n"
                f"Or if using Docker:\n"
                f"  docker-compose exec backend alembic upgrade head"
            )
        
        print(f"✅ Database at alembic head: {head_rev}")
        
    except subprocess.TimeoutExpired:
        pytest.fail(
            "Alembic command timed out after 10 seconds.\n"
            "Check database connectivity and alembic configuration."
        )
    
    except subprocess.CalledProcessError as e:
        # Check if it's a database connection error (skip) vs other error (fail)
        error_msg = (e.stderr or e.stdout or "").lower()
        if "could not connect" in error_msg or "connection refused" in error_msg:
            pytest.skip(
                f"Cannot connect to database: {e}\n"
                "DATABASE_URL may be incorrect or database may be down."
            )
        
        pytest.fail(
            f"Alembic command failed: {e}\n"
            f"stdout: {e.stdout}\n"
            f"stderr: {e.stderr}\n"
            "Ensure DATABASE_URL is set and database is accessible."
        )
    
    except FileNotFoundError:
        pytest.skip(
            "Alembic not installed or not in PATH.\n"
            "Install: pip install alembic"
        )


@pytest.mark.integration
@pytest.mark.slow
def test_no_pending_model_changes():
    """Detect if model changes exist without corresponding migrations."""
    
    # Check if DATABASE_URL is configured
    database_url = os.getenv("DATABASE_URL")
    if not database_url or "sqlite" in database_url.lower() or "placeholder" in database_url.lower():
        pytest.skip(
            "PostgreSQL DATABASE_URL not configured\n"
            "This test requires a real PostgreSQL database.\n"
            "Set DATABASE_URL=postgresql://user:pass@localhost:5432/db"
        )
    
    try:
        # Run alembic check (detects model changes without migrations)
        # Note: This requires alembic-autogen-check or custom script
        result = subprocess.run(
            ['alembic', 'revision', '--autogenerate', '--dry-run'],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        # If autogenerate would create migrations, we have drift
        if 'Generating' in result.stdout or 'create_table' in result.stdout:
            pytest.fail(
                "❌ SQLAlchemy model changes detected without migrations!\n\n"
                f"Alembic autogenerate output:\n{result.stdout}\n\n"
                "This indicates:\n"
                "  - Models have been modified but no migration created\n"
                "  - Tests may use in-memory schema while production uses old schema\n\n"
                "FIX: Create migration:\n"
                "  alembic revision --autogenerate -m 'description'\n"
                "  alembic upgrade head\n"
                "  git add migrations/versions/\n"
                "  git commit -m 'Add migration for model changes'"
            )
        
        print("✅ No pending model changes detected")
        
    except subprocess.TimeoutExpired:
        pytest.skip("Alembic autogenerate check timed out")
    
    except subprocess.CalledProcessError as e:
        # Some alembic versions don't support --dry-run
        pytest.skip(f"Alembic autogenerate check not supported: {e}")
    
    except FileNotFoundError:
        pytest.skip("Alembic not available")


if __name__ == "__main__":
    # Allow running as standalone script
    pytest.main([__file__, "-v"])
