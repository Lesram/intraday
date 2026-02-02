"""
Comprehensive tests for backend/database/models_production.py

Tests the production database models for idempotency and event tracking.
"""

import pytest
from datetime import date, datetime


class TestOrderEventModel:
    """Tests for OrderEvent model."""

    def test_model_exists(self):
        """OrderEvent model can be imported."""
        from backend.database.models_production import OrderEvent
        
        assert OrderEvent is not None

    def test_table_name(self):
        """OrderEvent has correct table name."""
        from backend.database.models_production import OrderEvent
        
        assert OrderEvent.__tablename__ == "order_events"

    def test_columns(self):
        """OrderEvent has expected columns."""
        from backend.database.models_production import OrderEvent
        
        columns = [col.name for col in OrderEvent.__table__.columns]
        
        expected = ["id", "order_id", "broker_order_id", "event_type", 
                    "event_time", "event_data", "processed_at", "created_at"]
        
        for col in expected:
            assert col in columns, f"Missing column: {col}"

    def test_unique_constraint(self):
        """OrderEvent has deduplication unique constraint."""
        from backend.database.models_production import OrderEvent
        
        constraints = [c.name for c in OrderEvent.__table__.constraints]
        
        assert "uq_events_broker_type_time" in constraints


class TestDailyLedgerModel:
    """Tests for DailyLedger model."""

    def test_model_exists(self):
        """DailyLedger model can be imported."""
        from backend.database.models_production import DailyLedger
        
        assert DailyLedger is not None

    def test_table_name(self):
        """DailyLedger has correct table name."""
        from backend.database.models_production import DailyLedger
        
        assert DailyLedger.__tablename__ == "daily_ledger"

    def test_columns(self):
        """DailyLedger has expected columns."""
        from backend.database.models_production import DailyLedger
        
        columns = [col.name for col in DailyLedger.__table__.columns]
        
        expected = ["id", "account_id", "day_utc", "orders_count",
                    "submitted_notional_usd", "filled_notional_usd", 
                    "created_at", "updated_at"]
        
        for col in expected:
            assert col in columns, f"Missing column: {col}"

    def test_unique_constraint(self):
        """DailyLedger has account_day unique constraint."""
        from backend.database.models_production import DailyLedger
        
        constraints = [c.name for c in DailyLedger.__table__.constraints]
        
        assert "uq_daily_ledger_account_day" in constraints

    def test_indexes(self):
        """DailyLedger has expected indexes."""
        from backend.database.models_production import DailyLedger
        
        indexes = [idx.name for idx in DailyLedger.__table__.indexes]
        
        assert "idx_daily_ledger_account_day" in indexes
