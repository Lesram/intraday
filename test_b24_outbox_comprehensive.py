"""
Comprehensive tests for B2.4 Exactly-Once Order Submission
Tests outbox pattern, idempotency, and transactional guarantees.
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from backend.config import get_settings
from backend.infra.schemas import OutboxEvent, Order
from backend.infra.outbox import OutboxRepo, OutboxDispatcher, BackoffCalculator
from backend.services.order_service import OrderService


@pytest.fixture
async def db_session():
    """Create an in-memory SQLite session for testing."""
    settings = get_settings()
    
    # Use in-memory SQLite for tests
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False
    )
    
    # Create tables
    from backend.infra.schemas import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    
    async with sessionmaker() as session:
        yield session
    
    await engine.dispose()


@pytest.fixture
def mock_alpaca_client():
    """Mock Alpaca client for testing."""
    mock_client = AsyncMock()
    mock_client.submit_order.return_value = {"id": "ALPACA_ORDER_123"}
    return mock_client


class TestOutboxRepo:
    """Test OutboxRepo operations."""
    
    async def test_enqueue_outbox_event(self, db_session):
        """Test enqueuing an outbox event."""
        repo = OutboxRepo(db_session)
        
        payload = {
            "order_id": str(uuid.uuid4()),
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100.0
        }
        
        event_id = await repo.enqueue(
            topic="order_submitted",
            payload=payload,
            session=db_session
        )
        
        await db_session.commit()
        
        assert event_id is not None
        assert isinstance(event_id, uuid.UUID)
        
        # Verify event was created
        event = await db_session.get(OutboxEvent, event_id)
        assert event is not None
        assert event.topic == "order_submitted"
        assert event.status == "pending"
        assert event.payload == payload
        assert event.attempts == 0
    
    async def test_claim_batch(self, db_session):
        """Test claiming a batch of events."""
        repo = OutboxRepo(db_session)
        
        # Create multiple events
        event_ids = []
        for i in range(5):
            payload = {"test": f"data_{i}"}
            event_id = await repo.enqueue(
                topic="test_topic",
                payload=payload,
                session=db_session
            )
            event_ids.append(event_id)
        
        await db_session.commit()
        
        # Claim batch
        events = await repo.claim_batch(limit=3, session=db_session)
        
        assert len(events) == 3
        for event in events:
            assert event.status == "pending"
            assert event.topic == "test_topic"
            assert event.id in event_ids
    
    async def test_mark_sent(self, db_session):
        """Test marking event as sent."""
        repo = OutboxRepo(db_session)
        
        event_id = await repo.enqueue(
            topic="test",
            payload={"test": "data"},
            session=db_session
        )
        
        await db_session.commit()
        
        # Mark as sent
        await repo.mark_sent(event_id, session=db_session)
        await db_session.commit()
        
        # Verify status change
        event = await db_session.get(OutboxEvent, event_id)
        assert event.status == "sent"
        assert event.sent_at is not None
        assert event.last_error is None
    
    async def test_mark_retry(self, db_session):
        """Test marking event for retry."""
        repo = OutboxRepo(db_session)
        
        event_id = await repo.enqueue(
            topic="test",
            payload={"test": "data"},
            session=db_session
        )
        
        await db_session.commit()
        
        # Mark for retry
        next_attempt = datetime.utcnow() + timedelta(minutes=5)
        await repo.mark_retry(
            event_id,
            attempts=1,
            next_attempt_at=next_attempt,
            error_message="Test error",
            session=db_session
        )
        await db_session.commit()
        
        # Verify retry state
        event = await db_session.get(OutboxEvent, event_id)
        assert event.attempts == 1
        assert event.next_attempt_at == next_attempt
        assert event.last_error == "Test error"
    
    async def test_mark_failed(self, db_session):
        """Test marking event as permanently failed."""
        repo = OutboxRepo(db_session)
        
        event_id = await repo.enqueue(
            topic="test",
            payload={"test": "data"},
            session=db_session
        )
        
        await db_session.commit()
        
        # Mark as failed
        await repo.mark_failed(
            event_id,
            attempts=5,
            error_message="Max retries exceeded",
            session=db_session
        )
        await db_session.commit()
        
        # Verify failed state
        event = await db_session.get(OutboxEvent, event_id)
        assert event.status == "failed"
        assert event.attempts == 5
        assert event.last_error == "Max retries exceeded"


class TestBackoffCalculator:
    """Test backoff calculation logic."""
    
    def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        calculator = BackoffCalculator(
            base_delay_ms=200,
            max_delay_ms=10000,
            jitter_ms=0  # No jitter for predictable testing
        )
        
        # Test backoff progression
        assert calculator.calculate_delay(1) == 200  # Base delay
        assert calculator.calculate_delay(2) == 400  # 2^1 * 200
        assert calculator.calculate_delay(3) == 800  # 2^2 * 200
        assert calculator.calculate_delay(4) == 1600  # 2^3 * 200
    
    def test_max_delay_cap(self):
        """Test that delay is capped at max_delay_ms."""
        calculator = BackoffCalculator(
            base_delay_ms=200,
            max_delay_ms=1000,
            jitter_ms=0
        )
        
        # High attempt count should be capped
        assert calculator.calculate_delay(10) == 1000
        assert calculator.calculate_delay(100) == 1000
    
    def test_jitter_adds_randomness(self):
        """Test that jitter adds randomness to delay."""
        calculator = BackoffCalculator(
            base_delay_ms=200,
            max_delay_ms=10000,
            jitter_ms=100
        )
        
        # Generate multiple delays and verify they differ (due to jitter)
        delays = [calculator.calculate_delay(1) for _ in range(10)]
        
        # All delays should be different due to jitter
        assert len(set(delays)) > 1
        
        # All delays should be >= base delay
        assert all(delay >= 200 for delay in delays)
        
        # All delays should be <= base delay + jitter
        assert all(delay <= 300 for delay in delays)


class TestOutboxDispatcher:
    """Test OutboxDispatcher background processing."""
    
    async def test_single_event_processing(self, db_session, mock_alpaca_client):
        """Test processing a single outbox event."""
        settings = get_settings()
        settings.outbox.enabled = True
        settings.outbox.max_attempts = 3
        
        sessionmaker = MagicMock()
        sessionmaker.return_value.__aenter__.return_value = db_session
        
        dispatcher = OutboxDispatcher(
            sessionmaker=sessionmaker,
            alpaca_client=mock_alpaca_client,
            settings=settings
        )
        
        # Create an outbox event
        repo = OutboxRepo(db_session)
        payload = {
            "order_id": str(uuid.uuid4()),
            "client_idempotency_key": "TEST_IDEMPOTENCY_KEY",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "market",
            "tif": "gtc"
        }
        
        event_id = await repo.enqueue(
            topic="order_submitted",
            payload=payload,
            session=db_session
        )
        await db_session.commit()
        
        # Process the event
        event = await db_session.get(OutboxEvent, event_id)
        await dispatcher._dispatch_event(event, db_session)
        await db_session.commit()
        
        # Verify Alpaca client was called
        mock_alpaca_client.submit_order.assert_called_once()
        call_args = mock_alpaca_client.submit_order.call_args
        
        assert call_args.kwargs["symbol"] == "AAPL"
        assert call_args.kwargs["side"] == "buy"
        assert call_args.kwargs["quantity"] == 100
        
        # Verify event was marked as sent
        await db_session.refresh(event)
        assert event.status == "sent"
        assert event.sent_at is not None
    
    async def test_retry_on_failure(self, db_session, mock_alpaca_client):
        """Test retry logic when Alpaca client fails."""
        settings = get_settings()
        settings.outbox.enabled = True
        settings.outbox.max_attempts = 3
        
        # Make Alpaca client fail
        mock_alpaca_client.submit_order.side_effect = Exception("Network error")
        
        sessionmaker = MagicMock()
        sessionmaker.return_value.__aenter__.return_value = db_session
        
        dispatcher = OutboxDispatcher(
            sessionmaker=sessionmaker,
            alpaca_client=mock_alpaca_client,
            settings=settings
        )
        
        # Create an outbox event
        repo = OutboxRepo(db_session)
        payload = {
            "order_id": str(uuid.uuid4()),
            "client_idempotency_key": "TEST_IDEMPOTENCY_KEY",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "market",
            "tif": "gtc"
        }
        
        event_id = await repo.enqueue(
            topic="order_submitted",
            payload=payload,
            session=db_session
        )
        await db_session.commit()
        
        # Process the event (should fail and retry)
        event = await db_session.get(OutboxEvent, event_id)
        await dispatcher._dispatch_event(event, db_session)
        await db_session.commit()
        
        # Verify event was marked for retry
        await db_session.refresh(event)
        assert event.status == "pending"  # Still pending for retry
        assert event.attempts == 1
        assert event.last_error == "Network error"
        assert event.next_attempt_at > datetime.utcnow()


class TestOrderService:
    """Test OrderService transactional operations."""
    
    async def test_submit_order_transactionally(self, db_session):
        """Test transactional order submission."""
        service = OrderService(db_session)
        
        result = await service.submit_order_transactionally(
            symbol="AAPL",
            side="buy",
            qty=100.0,
            order_type="market",
            tif="gtc"
        )
        
        # Verify result structure
        assert "order_id" in result
        assert "client_order_id" in result
        assert "outbox_event_id" in result
        assert result["status"] == "pending_submission"
        assert result["symbol"] == "AAPL"
        assert result["side"] == "buy"
        assert result["qty"] == 100.0
        assert result["submission_mode"] == "transactional"
        
        # Verify order was created in database
        order_id = uuid.UUID(result["order_id"])
        order = await db_session.get(Order, order_id)
        assert order is not None
        assert order.symbol == "AAPL"
        assert order.side == "buy"
        assert order.qty == 100.0
        assert order.status == "pending_submission"
        
        # Verify outbox event was created
        outbox_event_id = uuid.UUID(result["outbox_event_id"])
        event = await db_session.get(OutboxEvent, outbox_event_id)
        assert event is not None
        assert event.topic == "order_submitted"
        assert event.status == "pending"
        assert event.payload["order_id"] == result["order_id"]
        assert event.payload["symbol"] == "AAPL"
    
    async def test_idempotency_protection(self, db_session):
        """Test idempotency protection for duplicate orders."""
        service = OrderService(db_session)
        
        client_order_id = "TEST_CLIENT_ORDER_123"
        
        # Submit first order
        result1 = await service.submit_order_transactionally(
            symbol="AAPL",
            side="buy",
            qty=100.0,
            client_order_id=client_order_id
        )
        
        # Submit duplicate order with same client_order_id
        result2 = await service.submit_order_transactionally(
            symbol="AAPL",
            side="buy",
            qty=100.0,
            client_order_id=client_order_id
        )
        
        # Verify idempotent response
        assert result2["order_id"] == result1["order_id"]
        assert result2["client_order_id"] == client_order_id
        assert result2["submission_mode"] == "idempotent"
        assert "outbox_event_id" not in result2  # No new outbox event
    
    async def test_order_validation(self, db_session):
        """Test order parameter validation."""
        service = OrderService(db_session)
        
        # Test invalid side
        with pytest.raises(ValueError, match="Invalid side"):
            await service.submit_order_transactionally(
                symbol="AAPL",
                side="invalid_side",
                qty=100.0
            )
        
        # Test invalid quantity
        with pytest.raises(ValueError, match="Invalid order parameters"):
            await service.submit_order_transactionally(
                symbol="AAPL",
                side="buy",
                qty=-100.0
            )
        
        # Test missing limit price for limit order
        with pytest.raises(ValueError, match="limit_price required"):
            await service.submit_order_transactionally(
                symbol="AAPL",
                side="buy",
                qty=100.0,
                order_type="limit"
            )
    
    async def test_get_order_status(self, db_session):
        """Test getting order status."""
        service = OrderService(db_session)
        
        # Submit order
        result = await service.submit_order_transactionally(
            symbol="AAPL",
            side="buy",
            qty=100.0
        )
        
        # Get status
        status = await service.get_order_status(result["order_id"])
        
        assert status is not None
        assert status["order_id"] == result["order_id"]
        assert status["status"] == "pending_submission"
        assert status["symbol"] == "AAPL"
        assert status["side"] == "buy"
        assert status["qty"] == 100.0
    
    async def test_cancel_order(self, db_session):
        """Test order cancellation."""
        service = OrderService(db_session)
        
        # Submit order
        result = await service.submit_order_transactionally(
            symbol="AAPL",
            side="buy",
            qty=100.0
        )
        
        # Cancel order
        cancel_result = await service.cancel_order(result["order_id"])
        
        assert cancel_result["order_id"] == result["order_id"]
        assert cancel_result["status"] == "pending_cancel"
        assert cancel_result["cancellation_mode"] == "transactional"
        assert "outbox_event_id" in cancel_result
        
        # Verify order status was updated
        order_id = uuid.UUID(result["order_id"])
        order = await db_session.get(Order, order_id)
        assert order.status == "pending_cancel"


class TestIntegration:
    """Integration tests for complete outbox pattern flow."""
    
    async def test_end_to_end_order_flow(self, db_session, mock_alpaca_client):
        """Test complete end-to-end order flow."""
        settings = get_settings()
        settings.outbox.enabled = True
        settings.outbox.max_attempts = 3
        
        sessionmaker = MagicMock()
        sessionmaker.return_value.__aenter__.return_value = db_session
        
        # Create services
        order_service = OrderService(db_session)
        dispatcher = OutboxDispatcher(
            sessionmaker=sessionmaker,
            alpaca_client=mock_alpaca_client,
            settings=settings
        )
        
        # 1. Submit order transactionally
        order_result = await order_service.submit_order_transactionally(
            symbol="AAPL",
            side="buy",
            qty=100.0
        )
        
        assert order_result["submission_mode"] == "transactional"
        
        # 2. Process outbox event
        repo = OutboxRepo(db_session)
        events = await repo.claim_batch(limit=1, session=db_session)
        
        assert len(events) == 1
        event = events[0]
        assert event.topic == "order_submitted"
        
        # 3. Dispatch event
        await dispatcher._dispatch_event(event, db_session)
        await db_session.commit()
        
        # 4. Verify Alpaca submission
        mock_alpaca_client.submit_order.assert_called_once()
        
        # 5. Verify event marked as sent
        await db_session.refresh(event)
        assert event.status == "sent"
        assert event.sent_at is not None
    
    async def test_concurrent_order_processing(self, db_session, mock_alpaca_client):
        """Test concurrent processing of multiple orders."""
        settings = get_settings()
        settings.outbox.enabled = True
        
        order_service = OrderService(db_session)
        
        # Submit multiple orders concurrently
        order_tasks = []
        for i in range(5):
            task = order_service.submit_order_transactionally(
                symbol=f"STOCK{i}",
                side="buy",
                qty=100.0 * (i + 1),
                client_order_id=f"CLIENT_ORDER_{i}"
            )
            order_tasks.append(task)
        
        results = await asyncio.gather(*order_tasks)
        
        # Verify all orders were created
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result["symbol"] == f"STOCK{i}"
            assert result["qty"] == 100.0 * (i + 1)
            assert result["submission_mode"] == "transactional"
        
        # Verify all outbox events were created
        repo = OutboxRepo(db_session)
        events = await repo.claim_batch(limit=10, session=db_session)
        assert len(events) == 5
        
        # Verify all events have correct payloads
        event_symbols = [event.payload["symbol"] for event in events]
        expected_symbols = [f"STOCK{i}" for i in range(5)]
        assert set(event_symbols) == set(expected_symbols)


@pytest.mark.asyncio
class TestPerformance:
    """Performance and load testing for outbox pattern."""
    
    async def test_high_throughput_order_submission(self, db_session):
        """Test high-throughput order submission performance."""
        order_service = OrderService(db_session)
        
        # Submit 100 orders rapidly
        start_time = datetime.utcnow()
        
        tasks = []
        for i in range(100):
            task = order_service.submit_order_transactionally(
                symbol="AAPL",
                side="buy" if i % 2 == 0 else "sell",
                qty=float(i + 1),
                client_order_id=f"PERF_TEST_{i}"
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        # Performance assertions
        assert len(results) == 100
        assert duration < 10.0  # Should complete within 10 seconds
        
        throughput = 100 / duration
        print(f"Order submission throughput: {throughput:.2f} orders/second")
        
        # Verify all orders and outbox events were created correctly
        repo = OutboxRepo(db_session)
        events = await repo.claim_batch(limit=200, session=db_session)
        assert len(events) == 100
        
        # Verify no duplicate order IDs
        order_ids = [result["order_id"] for result in results]
        assert len(set(order_ids)) == 100  # All unique
    
    async def test_batch_processing_efficiency(self, db_session, mock_alpaca_client):
        """Test efficiency of batch outbox processing."""
        settings = get_settings()
        settings.outbox.enabled = True
        settings.outbox.batch_size = 10
        
        sessionmaker = MagicMock()
        sessionmaker.return_value.__aenter__.return_value = db_session
        
        dispatcher = OutboxDispatcher(
            sessionmaker=sessionmaker,
            alpaca_client=mock_alpaca_client,
            settings=settings
        )
        
        # Create 50 outbox events
        repo = OutboxRepo(db_session)
        event_ids = []
        
        for i in range(50):
            payload = {
                "order_id": str(uuid.uuid4()),
                "client_idempotency_key": f"BATCH_TEST_{i}",
                "symbol": "AAPL",
                "side": "buy",
                "qty": 100,
                "order_type": "market",
                "tif": "gtc"
            }
            
            event_id = await repo.enqueue(
                topic="order_submitted",
                payload=payload,
                session=db_session
            )
            event_ids.append(event_id)
        
        await db_session.commit()
        
        # Process all events in batches
        start_time = datetime.utcnow()
        
        while True:
            batch = await repo.claim_batch(limit=10, session=db_session)
            if not batch:
                break
            
            # Process batch concurrently
            dispatch_tasks = [
                dispatcher._dispatch_event(event, db_session)
                for event in batch
            ]
            await asyncio.gather(*dispatch_tasks, return_exceptions=True)
            await db_session.commit()
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        # Performance assertions
        assert mock_alpaca_client.submit_order.call_count == 50
        assert duration < 5.0  # Should process 50 events within 5 seconds
        
        throughput = 50 / duration
        print(f"Outbox processing throughput: {throughput:.2f} events/second")
        
        # Verify all events were processed successfully
        stats = await repo.get_queue_stats()
        assert stats["sent"] == 50
        assert stats["pending"] == 0
        assert stats["failed"] == 0


if __name__ == "__main__":
    # Run specific test
    import sys
    
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        pytest.main([f"-v", f"-k", test_name, __file__])
    else:
        # Run all tests
        pytest.main(["-v", __file__])
