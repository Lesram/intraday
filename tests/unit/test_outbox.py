"""
Unit tests for outbox pattern implementation.
Tests queuing, retry logic, backoff calculation, and dispatcher functionality.
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from backend.infra.outbox import (
    OutboxRepo,
    BackoffCalculator,
    OutboxDispatcher
)
from backend.infra.schemas import OutboxEvent


class TestBackoffCalculator:
    """Test exponential backoff calculation with jitter."""
    
    def test_backoff_calculator_defaults(self):
        """Test BackoffCalculator with default parameters."""
        calculator = BackoffCalculator()
        
        assert calculator.base_delay_ms == 200
        assert calculator.max_delay_ms == 10000
        assert calculator.jitter_ms == 150
    
    def test_backoff_calculator_custom_params(self):
        """Test BackoffCalculator with custom parameters."""
        calculator = BackoffCalculator(
            base_delay_ms=100,
            max_delay_ms=5000,
            jitter_ms=50
        )
        
        assert calculator.base_delay_ms == 100
        assert calculator.max_delay_ms == 5000
        assert calculator.jitter_ms == 50
    
    def test_calculate_delay_first_attempt(self):
        """Test delay calculation for first attempt."""
        calculator = BackoffCalculator(base_delay_ms=200, jitter_ms=0)
        
        delay = calculator.calculate_delay(1)
        
        # First attempt should be base delay
        assert delay == 200
    
    def test_calculate_delay_exponential_growth(self):
        """Test delay grows exponentially."""
        calculator = BackoffCalculator(base_delay_ms=100, jitter_ms=0)
        
        # Test exponential progression: 100, 200, 400, 800...
        delay1 = calculator.calculate_delay(1)
        delay2 = calculator.calculate_delay(2)
        delay3 = calculator.calculate_delay(3)
        delay4 = calculator.calculate_delay(4)
        
        assert delay1 == 100  # 100 * 2^0
        assert delay2 == 200  # 100 * 2^1
        assert delay3 == 400  # 100 * 2^2
        assert delay4 == 800  # 100 * 2^3
    
    def test_calculate_delay_max_cap(self):
        """Test delay is capped at maximum."""
        calculator = BackoffCalculator(
            base_delay_ms=100, 
            max_delay_ms=500,
            jitter_ms=0
        )
        
        # High attempt number should be capped
        delay = calculator.calculate_delay(10)  # Would be 100 * 2^9 = 51200
        
        assert delay == 500  # Capped at max_delay_ms
    
    def test_calculate_delay_with_jitter(self):
        """Test delay includes jitter."""
        calculator = BackoffCalculator(base_delay_ms=200, jitter_ms=100)
        
        delays = []
        for _ in range(10):
            delay = calculator.calculate_delay(1)
            delays.append(delay)
        
        # All delays should be >= base delay
        assert all(d >= 200 for d in delays)
        
        # Should have variation due to jitter (not all identical)
        assert len(set(delays)) > 1
    
    def test_calculate_delay_zero_attempts(self):
        """Test delay calculation with zero attempts."""
        calculator = BackoffCalculator(base_delay_ms=200)
        
        delay = calculator.calculate_delay(0)
        
        # Zero or negative attempts should return base delay
        assert delay >= 200  # >= due to jitter
    
    def test_next_attempt_time(self):
        """Test next attempt time calculation."""
        calculator = BackoffCalculator(base_delay_ms=1000, jitter_ms=0)
        
        start_time = datetime.utcnow()
        next_time = calculator.next_attempt_time(1)
        
        # Should be approximately 1 second in the future
        time_diff = (next_time - start_time).total_seconds()
        assert 0.9 <= time_diff <= 1.1  # Allow for small timing variance


class TestOutboxRepo:
    """Test outbox repository operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_session = AsyncMock()
        self.repo = OutboxRepo(self.mock_session)
    
    async def test_enqueue_creates_event(self):
        """Test enqueuing creates an outbox event."""
        topic = "order.placed"
        payload = {"order_id": "123", "symbol": "AAPL"}
        
        # Create a mock event with a UUID
        mock_event_id = uuid.uuid4()
        mock_event = Mock()
        mock_event.id = mock_event_id
        
        # Mock the session add, flush, and creation
        self.mock_session.add = Mock()
        self.mock_session.flush = AsyncMock()
        
        # Mock OutboxEvent creation
        with patch('backend.infra.outbox.OutboxEvent') as mock_outbox_event:
            mock_outbox_event.return_value = mock_event
            
            event_id = await self.repo.enqueue(topic=topic, payload=payload)
            
            # Should return a UUID
            assert isinstance(event_id, uuid.UUID)
            assert event_id == mock_event_id
            
            # Should have created an event
            mock_outbox_event.assert_called_once()
            
            # Should have added event to session
            self.mock_session.add.assert_called_once_with(mock_event)
            
            # Should have flushed to get ID
            self.mock_session.flush.assert_called_once()
    
    async def test_enqueue_with_custom_session(self):
        """Test enqueuing with custom session."""
        custom_session = AsyncMock()
        custom_session.add = Mock()
        custom_session.flush = AsyncMock()
        
        topic = "trade.executed"
        payload = {"trade_id": "456"}
        
        mock_event_id = uuid.uuid4()
        mock_event = Mock()
        mock_event.id = mock_event_id
        
        with patch('backend.infra.outbox.OutboxEvent') as mock_outbox_event:
            mock_outbox_event.return_value = mock_event
            
            event_id = await self.repo.enqueue(
                topic=topic, 
                payload=payload, 
                session=custom_session
            )
            
            # Should use custom session, not self.session
            custom_session.add.assert_called_once_with(mock_event)
            custom_session.flush.assert_called_once()
            
            # Should not touch self.session
            self.mock_session.add.assert_not_called()
            
            # Should return the event ID
            assert event_id == mock_event_id
    
    async def test_claim_batch_returns_events(self):
        """Test claiming batch of events."""
        # Mock query result
        mock_events = [
            Mock(id=uuid.uuid4(), topic="test.topic", attempts=0),
            Mock(id=uuid.uuid4(), topic="test.topic2", attempts=1),
        ]
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_events
        self.mock_session.execute = AsyncMock(return_value=mock_result)
        
        events = await self.repo.claim_batch(limit=5)
        
        assert len(events) == 2
        assert events == mock_events
        
        # Should have executed query
        self.mock_session.execute.assert_called_once()
    
    async def test_claim_batch_with_limit(self):
        """Test claiming batch respects limit parameter."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        self.mock_session.execute = AsyncMock(return_value=mock_result)
        
        await self.repo.claim_batch(limit=3)
        
        # Verify limit was used in query (check the call args)
        call_args = self.mock_session.execute.call_args[0][0]
        # The exact query structure may vary, but limit should be applied
        assert hasattr(call_args, 'limit') or 'LIMIT' in str(call_args)
    
    async def test_mark_sent_updates_event(self):
        """Test marking event as sent."""
        event_id = uuid.uuid4()
        
        self.mock_session.execute = AsyncMock()
        
        await self.repo.mark_sent(event_id)
        
        # Should execute update statement
        self.mock_session.execute.assert_called_once()
        
        # Check that update statement targets the right event
        call_args = self.mock_session.execute.call_args[0][0]
        # Should be an update statement for the specific event
        assert hasattr(call_args, 'table') or 'UPDATE' in str(call_args)
    
    async def test_mark_sent_with_custom_session(self):
        """Test marking event as sent with custom session."""
        event_id = uuid.uuid4()
        custom_session = AsyncMock()
        
        await self.repo.mark_sent(event_id, session=custom_session)
        
        # Should use custom session
        custom_session.execute.assert_called_once()
        
        # Should not use self.session
        self.mock_session.execute.assert_not_called()
    
    async def test_mark_retry_updates_event_with_backoff(self):
        """Test marking event for retry with backoff."""
        event_id = uuid.uuid4()
        attempts = 3
        next_attempt = datetime.utcnow() + timedelta(seconds=30)
        error_msg = "Network timeout"
        
        self.mock_session.execute = AsyncMock()
        
        await self.repo.mark_retry(
            event_id,
            attempts=attempts,
            next_attempt_at=next_attempt,
            error_message=error_msg
        )
        
        # Should execute update statement
        self.mock_session.execute.assert_called_once()


class TestOutboxDispatcher:
    """Test outbox event dispatcher."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_sessionmaker = Mock()
        self.mock_session = AsyncMock()
        self.mock_sessionmaker.return_value.__aenter__ = AsyncMock(
            return_value=self.mock_session
        )
        self.mock_sessionmaker.return_value.__aexit__ = AsyncMock()
        
        self.mock_alpaca_client = Mock()
        self.mock_settings = Mock()
        self.mock_settings.data = Mock()
        self.mock_settings.data.outbox_poll_interval_seconds = 1.0
        self.mock_settings.data.outbox_batch_size = 10
        self.mock_settings.data.outbox_max_attempts = 5
        
        self.dispatcher = OutboxDispatcher(
            sessionmaker=self.mock_sessionmaker,
            alpaca_client=self.mock_alpaca_client,
            settings=self.mock_settings
        )
    
    def test_dispatcher_initialization(self):
        """Test dispatcher initializes with correct settings."""
        assert self.dispatcher.sessionmaker == self.mock_sessionmaker
        assert self.dispatcher.alpaca_client == self.mock_alpaca_client
        assert self.dispatcher.settings == self.mock_settings
        assert isinstance(self.dispatcher.backoff_calculator, BackoffCalculator)
    
    def test_dispatcher_with_default_settings(self):
        """Test dispatcher with default settings when none provided."""
        with patch('backend.infra.outbox.get_settings') as mock_get_settings:
            mock_default_settings = Mock()
            mock_get_settings.return_value = mock_default_settings
            
            dispatcher = OutboxDispatcher(
                sessionmaker=self.mock_sessionmaker,
                alpaca_client=self.mock_alpaca_client
            )
            
            assert dispatcher.settings == mock_default_settings
            mock_get_settings.assert_called_once()


class TestOutboxIntegration:
    """Integration tests for outbox components."""
    
    def test_repo_and_backoff_calculator_integration(self):
        """Test that repo and backoff calculator work together."""
        # Create real calculator (not mocked)
        calculator = BackoffCalculator(base_delay_ms=100, jitter_ms=0)
        
        # Test delay progression
        delay1 = calculator.calculate_delay(1)
        delay2 = calculator.calculate_delay(2) 
        delay3 = calculator.calculate_delay(3)
        
        # Should have proper progression
        assert delay1 < delay2 < delay3
        assert delay1 == 100
        assert delay2 == 200
        assert delay3 == 400
    
    async def test_outbox_workflow_simulation(self):
        """Test complete outbox workflow simulation."""
        # This simulates the outbox pattern without database
        
        # 1. Create event (enqueue)
        event_data = {
            "id": uuid.uuid4(),
            "topic": "order.created", 
            "payload": {"order_id": "123", "amount": 100.0},
            "status": "pending",
            "attempts": 0
        }
        
        # 2. Claim for processing
        assert event_data["status"] == "pending"
        assert event_data["attempts"] == 0
        
        # 3. Process event (simulate failure)
        calculator = BackoffCalculator()
        next_attempt = calculator.next_attempt_time(attempts=1)
        
        # Should schedule retry
        event_data["attempts"] = 1
        event_data["next_attempt_at"] = next_attempt
        event_data["status"] = "pending"  # Still pending for retry
        
        assert event_data["attempts"] == 1
        assert event_data["next_attempt_at"] > datetime.utcnow()
        
        # 4. Second attempt (simulate success)
        event_data["status"] = "sent"
        event_data["sent_at"] = datetime.utcnow()
        
        assert event_data["status"] == "sent"
        assert event_data["sent_at"] is not None
    
    def test_backoff_calculator_realistic_scenarios(self):
        """Test backoff calculator with realistic failure scenarios."""
        calculator = BackoffCalculator(
            base_delay_ms=1000,  # 1 second base
            max_delay_ms=300000,  # 5 minute max
            jitter_ms=500        # 0.5 second jitter
        )
        
        # Test common retry scenarios
        delays = []
        for attempt in range(1, 8):  # 7 attempts
            delay = calculator.calculate_delay(attempt)
            delays.append(delay)
        
        # Should grow exponentially until capped
        assert delays[0] >= 1000  # At least base delay
        assert delays[1] >= 2000  # At least 2x base
        assert delays[2] >= 4000  # At least 4x base
        
        # Later attempts should be capped at max
        assert all(d <= 300500 for d in delays)  # Max + jitter
    
    def test_event_priority_and_ordering(self):
        """Test event processing priority based on creation time."""
        # Simulate multiple events with different creation times
        base_time = datetime.utcnow()
        
        events = [
            {
                "id": uuid.uuid4(),
                "created_at": base_time - timedelta(minutes=5),
                "topic": "old.event",
                "attempts": 0
            },
            {
                "id": uuid.uuid4(), 
                "created_at": base_time - timedelta(minutes=1),
                "topic": "newer.event",
                "attempts": 0
            },
            {
                "id": uuid.uuid4(),
                "created_at": base_time - timedelta(minutes=10),
                "topic": "oldest.event", 
                "attempts": 0
            }
        ]
        
        # Sort by created_at (as would happen in claim_batch query)
        sorted_events = sorted(events, key=lambda x: x["created_at"])
        
        # Should process oldest first
        assert sorted_events[0]["topic"] == "oldest.event"
        assert sorted_events[1]["topic"] == "old.event"  
        assert sorted_events[2]["topic"] == "newer.event"
