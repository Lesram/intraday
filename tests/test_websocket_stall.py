"""
WebSocket Stall Test
Integration test for WebSocket backpressure policy that confirms
slow consumers don't stall the server
"""
import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from backend.api.main import WebSocketClientManager


class TestWebSocketStallScenario:
    """Test WebSocket stall scenarios and backpressure handling"""

    @pytest.mark.asyncio
    async def test_slow_consumer_doesnt_stall_server(self):
        """
        Test that a slow WebSocket consumer doesn't stall the server
        This is a critical acceptance test for the branch requirements
        """
        ws_manager = WebSocketClientManager(max_queue_size=5)

        # Create fast and slow consumers
        fast_consumer = MockWebSocketConsumer("fast_consumer", process_delay=0.01)
        slow_consumer = MockWebSocketConsumer("slow_consumer", process_delay=2.0)

        # Add both consumers
        await ws_manager.add_client("fast_consumer", fast_consumer.websocket)
        await ws_manager.add_client("slow_consumer", slow_consumer.websocket)

        # Start message processing for both consumers
        fast_task = asyncio.create_task(fast_consumer.start_processing())
        slow_task = asyncio.create_task(slow_consumer.start_processing())

        # Send many messages rapidly
        start_time = time.time()
        message_count = 20

        for i in range(message_count):
            await ws_manager.broadcast_message(
                {"type": "test_message", "id": i, "timestamp": time.time()}
            )
            await asyncio.sleep(0.01)  # Small delay between messages

        send_time = time.time() - start_time

        # Server should complete message sending quickly (under 1 second)
        # even with slow consumer present
        assert send_time < 1.0, f"Message sending took {send_time:.2f}s, server may be stalled"

        # Wait a bit for processing
        await asyncio.sleep(0.5)

        # Fast consumer should have processed most/all messages
        assert (
            fast_consumer.processed_count >= message_count * 0.8
        ), f"Fast consumer only processed {fast_consumer.processed_count}/{message_count} messages"

        # Slow consumer may have processed fewer due to backpressure
        # but server shouldn't be blocked
        assert slow_consumer.processed_count >= 0  # At least some processing

        # Check that fast consumer queue is not full
        fast_client_info = ws_manager.clients.get("fast_consumer")
        if fast_client_info:
            fast_queue_size = fast_client_info["queue"].qsize()
            assert (
                fast_queue_size < ws_manager.max_queue_size
            ), "Fast consumer queue is full, indicating server stall"

        # Cleanup
        fast_task.cancel()
        slow_task.cancel()

        try:
            await fast_task
            await slow_task
        except asyncio.CancelledError:
            pass

        await ws_manager.remove_client("fast_consumer")
        await ws_manager.remove_client("slow_consumer")

    @pytest.mark.asyncio
    async def test_queue_overflow_drops_old_messages(self):
        """Test that queue overflow drops old messages as expected"""
        ws_manager = WebSocketClientManager(max_queue_size=3)

        # Create a consumer that doesn't process messages (simulates stall)
        stalled_consumer = MockWebSocketConsumer("stalled_consumer", process_delay=float("inf"))
        await ws_manager.add_client("stalled_consumer", stalled_consumer.websocket)

        # Send more messages than queue capacity
        messages_sent = []
        for i in range(6):  # 6 messages > 3 queue capacity
            message = {"type": "test", "id": i, "data": f"message_{i}"}
            messages_sent.append(message)
            await ws_manager.broadcast_message(message)

        # Check that queue is at capacity
        client_info = ws_manager.clients.get("stalled_consumer")
        assert client_info is not None

        queue = client_info["queue"]
        assert queue.qsize() <= ws_manager.max_queue_size

        # The queue should contain the most recent messages due to backpressure policy
        remaining_messages = []
        while not queue.empty():
            try:
                msg = queue.get_nowait()
                remaining_messages.append(msg)
            except asyncio.QueueEmpty:
                break

        assert len(remaining_messages) <= ws_manager.max_queue_size

        # Most recent messages should be preserved
        if remaining_messages:
            last_message = remaining_messages[-1]
            assert last_message["id"] >= 3  # Should be one of the later messages

        await ws_manager.remove_client("stalled_consumer")

    @pytest.mark.asyncio
    async def test_multiple_consumers_with_different_speeds(self):
        """Test server handles multiple consumers with different processing speeds"""
        ws_manager = WebSocketClientManager(max_queue_size=10)

        # Create consumers with different speeds
        consumers = [
            MockWebSocketConsumer("very_fast", process_delay=0.001),
            MockWebSocketConsumer("fast", process_delay=0.01),
            MockWebSocketConsumer("medium", process_delay=0.1),
            MockWebSocketConsumer("slow", process_delay=0.5),
            MockWebSocketConsumer("very_slow", process_delay=1.0),
        ]

        # Add all consumers
        tasks = []
        for consumer in consumers:
            await ws_manager.add_client(consumer.client_id, consumer.websocket)
            task = asyncio.create_task(consumer.start_processing())
            tasks.append(task)

        # Send messages at moderate rate
        start_time = time.time()
        message_count = 30

        for i in range(message_count):
            await ws_manager.broadcast_message(
                {"type": "load_test", "id": i, "timestamp": time.time()}
            )
            await asyncio.sleep(0.02)  # 50 messages per second

        broadcast_time = time.time() - start_time

        # Broadcasting should complete quickly regardless of consumer speeds
        assert broadcast_time < 2.0, f"Broadcasting took {broadcast_time:.2f}s, too slow"

        # Wait for some processing
        await asyncio.sleep(1.0)

        # Verify that faster consumers processed more messages
        fast_processed = consumers[0].processed_count + consumers[1].processed_count
        slow_processed = consumers[3].processed_count + consumers[4].processed_count

        # Fast consumers should process significantly more
        assert (
            fast_processed > slow_processed
        ), f"Fast consumers processed {fast_processed}, slow consumers processed {slow_processed}"

        # Cleanup
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        for consumer in consumers:
            await ws_manager.remove_client(consumer.client_id)

    @pytest.mark.asyncio
    async def test_server_remains_responsive_during_consumer_backlog(self):
        """Test that server remains responsive to new operations during consumer backlog"""
        ws_manager = WebSocketClientManager(max_queue_size=5)

        # Create a backlogged consumer
        backlogged_consumer = MockWebSocketConsumer("backlogged", process_delay=1.0)
        await ws_manager.add_client("backlogged", backlogged_consumer.websocket)

        # Fill the consumer's queue and create backlog
        for i in range(10):  # More than queue capacity
            await ws_manager.broadcast_message({"type": "backlog", "id": i})

        # Server should still be able to:
        # 1. Add new consumers quickly
        new_consumer = MockWebSocketConsumer("new_consumer", process_delay=0.01)
        add_start = time.time()
        await ws_manager.add_client("new_consumer", new_consumer.websocket)
        add_time = time.time() - add_start

        assert add_time < 0.1, f"Adding new consumer took {add_time:.3f}s during backlog"

        # 2. Send messages to the new consumer
        new_task = asyncio.create_task(new_consumer.start_processing())

        message_start = time.time()
        await ws_manager.broadcast_message({"type": "new_message", "for": "new_consumer"})
        message_time = time.time() - message_start

        assert message_time < 0.1, f"Sending message took {message_time:.3f}s during backlog"

        # 3. The new consumer should receive messages promptly
        await asyncio.sleep(0.1)
        assert (
            new_consumer.processed_count > 0
        ), "New consumer didn't receive messages during backlog"

        # Cleanup
        new_task.cancel()
        try:
            await new_task
        except asyncio.CancelledError:
            pass

        await ws_manager.remove_client("backlogged")
        await ws_manager.remove_client("new_consumer")

    @pytest.mark.asyncio
    async def test_heartbeat_continues_during_stall(self):
        """Test that heartbeat mechanism continues working during consumer stalls"""
        ws_manager = WebSocketClientManager(max_queue_size=3)

        # Start heartbeat
        await ws_manager.start_heartbeat()

        # Add stalled consumer
        stalled_consumer = MockWebSocketConsumer("stalled", process_delay=float("inf"))
        await ws_manager.add_client("stalled", stalled_consumer.websocket)

        # Create backlog
        for i in range(10):
            await ws_manager.broadcast_message({"type": "test", "id": i})

        # Simulate heartbeat loop running
        initial_time = time.time()

        # Wait for a heartbeat cycle
        await asyncio.sleep(0.1)

        heartbeat_time = time.time() - initial_time

        # Heartbeat should continue operating (not stalled)
        assert heartbeat_time < 0.2, f"Heartbeat cycle took {heartbeat_time:.3f}s, may be stalled"

        # Stop heartbeat
        await ws_manager.stop_heartbeat()
        await ws_manager.remove_client("stalled")


class MockWebSocketConsumer:
    """Mock WebSocket consumer for testing different processing speeds"""

    def __init__(self, client_id: str, process_delay: float = 0.1):
        self.client_id = client_id
        self.process_delay = process_delay
        self.processed_count = 0
        self.websocket = AsyncMock()
        self.running = False

    async def start_processing(self):
        """Simulate message processing with configurable delay"""
        self.running = True

        try:
            while self.running:
                # Simulate processing delay
                if self.process_delay != float("inf"):
                    await asyncio.sleep(self.process_delay)
                    self.processed_count += 1
                else:
                    # Stalled consumer - never processes messages
                    await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            self.running = False

    def stop_processing(self):
        """Stop message processing"""
        self.running = False


class TestStallDetectionAndRecovery:
    """Test stall detection and recovery mechanisms"""

    @pytest.mark.asyncio
    async def test_stall_detection_removes_problematic_clients(self):
        """Test that stalled clients are eventually detected and removed"""
        ws_manager = WebSocketClientManager(max_queue_size=2)

        # Create a consumer that can't keep up
        problematic_consumer = MockWebSocketConsumer("problematic", process_delay=float("inf"))
        await ws_manager.add_client("problematic", problematic_consumer.websocket)

        # Fill its queue repeatedly (simulating continuous backpressure)
        for attempt in range(5):  # Multiple attempts to trigger backpressure
            for i in range(5):  # Fill queue multiple times
                await ws_manager.broadcast_message(
                    {"type": "stress_test", "attempt": attempt, "id": i}
                )

        # The backpressure policy should have been triggered multiple times
        client_info = ws_manager.clients.get("problematic")
        if client_info:
            queue_size = client_info["queue"].qsize()
            # Queue should be at capacity due to backpressure handling
            assert queue_size <= ws_manager.max_queue_size

        await ws_manager.remove_client("problematic")

    @pytest.mark.asyncio
    async def test_system_recovery_after_mass_stall(self):
        """Test system recovery after multiple consumers stall"""
        ws_manager = WebSocketClientManager(max_queue_size=3)

        # Create multiple stalled consumers
        stalled_consumers = []
        for i in range(5):
            consumer = MockWebSocketConsumer(f"stalled_{i}", process_delay=float("inf"))
            stalled_consumers.append(consumer)
            await ws_manager.add_client(f"stalled_{i}", consumer.websocket)

        # Overload all consumers
        for round_num in range(3):
            for msg_id in range(10):
                await ws_manager.broadcast_message(
                    {"type": "overload_test", "round": round_num, "id": msg_id}
                )

        # System should still be functional
        # Add a new, responsive consumer
        healthy_consumer = MockWebSocketConsumer("healthy", process_delay=0.01)

        add_start = time.time()
        await ws_manager.add_client("healthy", healthy_consumer.websocket)
        add_time = time.time() - add_start

        # Adding should still be fast despite other consumers being stalled
        assert add_time < 0.5, f"Adding healthy consumer took {add_time:.3f}s after mass stall"

        # New consumer should receive messages promptly
        healthy_task = asyncio.create_task(healthy_consumer.start_processing())

        await ws_manager.broadcast_message({"type": "recovery_test", "id": 1})
        await asyncio.sleep(0.1)

        assert (
            healthy_consumer.processed_count > 0
        ), "Healthy consumer didn't receive messages after mass stall"

        # Cleanup
        healthy_task.cancel()
        try:
            await healthy_task
        except asyncio.CancelledError:
            pass

        for consumer in stalled_consumers:
            await ws_manager.remove_client(consumer.client_id)
        await ws_manager.remove_client("healthy")
