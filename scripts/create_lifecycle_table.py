"""Create the model_lifecycle_events table if it doesn't exist."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL not set")
        return

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        # Check if table already exists
        result = await conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'model_lifecycle_events')")
        )
        exists = result.scalar()
        if exists:
            print("model_lifecycle_events table already exists")
            return

        # Check if model_registry exists (for FK)
        result = await conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'model_registry')")
        )
        has_registry = result.scalar()

        # Create the table
        fk_clause = ""
        if has_registry:
            fk_clause = (
                ", CONSTRAINT fk_model_lifecycle_events_model_id_model_registry "
                "FOREIGN KEY (model_id) REFERENCES model_registry(id) ON DELETE SET NULL"
            )

        await conn.execute(text(f"""
            CREATE TABLE model_lifecycle_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                model_id UUID,
                model_name VARCHAR(100) NOT NULL,
                model_version VARCHAR(50),
                event_type VARCHAR(64) NOT NULL,
                payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                {fk_clause}
            )
        """))

        # Create indexes
        await conn.execute(text(
            "CREATE INDEX ix_model_lifecycle_name_created "
            "ON model_lifecycle_events (model_name, created_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX ix_model_lifecycle_type_created "
            "ON model_lifecycle_events (event_type, created_at)"
        ))
        await conn.execute(text(
            "CREATE INDEX ix_model_lifecycle_model_created "
            "ON model_lifecycle_events (model_id, created_at)"
        ))

        print("model_lifecycle_events table created successfully")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
