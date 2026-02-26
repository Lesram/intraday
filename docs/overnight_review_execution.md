# Overnight Code Review: Live Trading Platform (2026-02-22)

**Scope**: Deep line-by-line review of 5 critical integration files before first real paper trading day

**Review Date**: 2026-02-22  
**Reviewer**: Claude Haiku 4.5  
**Verdict**: 6 CRITICAL findings + 5 WARNINGs + 2 INFOs requiring immediate attention

---

## CRITICAL FINDINGS

### CRITICAL-1: Weak Idempotency Key Generation (High Duplicate Order Risk)

**File**: `/Users/marselkei/VS/intra/backend/organism/live_engine.py`  
**Lines**: 1901-1903, 1931-1934  
**Severity**: CRITICAL

#### Issue
The idempotency key uses only seconds precision (`'%Y%m%d_%H%M%S'`), meaning multiple orders submitted in the same second will have identical keys:

```python
# _submit_entry_order (line 1901-1903)
idem_key = (
    f"organism_{symbol}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
)

# _submit_exit_order (line 1931-1934)
idem_key = (
    f"organism_exit_{symbol}"
    f"_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
)
```

#### Risk
If 10 ticks occur within the same second (likely with 100ms tick intervals), and multiple symbols match entry criteria, retries will generate identical keys. Alpaca's `client_order_id` uniqueness constraint will reject duplicates with 422 errors, then the recovery logic at line 414 attempts to fetch existing orders—but if a different symbol was submitted with the same second-timestamp, this could lead to:
- Wrong position recovery (fetching wrong symbol's order)
- Silent order placement failures
- Position tracking desynchronization

#### Example Scenario
```
Tick 0 (10:30:45.001s): Submit BUY AAPL, idem_key="organism_AAPL_20260222_103045"
Tick 1 (10:30:45.101s): Submit BUY MSFT, idem_key="organism_MSFT_20260222_103045"  ← Same second!
Tick 2 (10:30:45.201s): Network timeout on MSFT order
Retry MSFT with same idem_key → Alpaca says "already exists"
Recovery tries GET /v2/orders:by_client_order_id → Could return AAPL order by coincidence
```

#### Recommendation
**IMMEDIATE**: Add microsecond precision + atomic counter:

```python
import uuid
idem_key = f"organism_{symbol}_{uuid.uuid4().hex[:12]}"
```

Or use tick count:
```python
idem_key = f"organism_{symbol}_t{self._tick_count}_{uuid.uuid4().hex[:4]}"
```

---

### CRITICAL-2: Race Condition Between Position Check and Order Submission

**File**: `/Users/marselkei/VS/intra/backend/organism/live_engine.py`  
**Lines**: 1132-1151  
**Severity**: CRITICAL

#### Issue
Fresh position check happens, but there's a gap between check and order submission where Alpaca's state could change:

```python
# Line 1132-1136: Fresh position check
try:
    fresh_positions = await self._positions_service.get_all_positions()
    fresh_open = set(fresh_positions.keys())
except Exception:
    fresh_open = open_symbols

# Lines 1138-1151: Order submission loop
for sz in sizes:
    if sz.symbol in fresh_open:
        logger.info(
            "Skipping entry for %s — position already exists at broker",
            sz.symbol,
        )
        continue
    # ... order submission
```

#### Risk
Between `get_all_positions()` call and `_submit_entry_order()` call, another system component could open a position for the same symbol. Since there's no locking, the engine would submit a duplicate entry order, resulting in:
- Two positions for same symbol
- Pyramid tracker confusion (expects 1 position, gets 2)
- Exit logic breaks (tries to close 1 position but 2 exist)
- Position tracking metadata inconsistency

#### Example Scenario
```
T0: get_all_positions() → {AAPL, MSFT}
T1: External API call opens position in TSLA (via another system)
T2: _submit_entry_order(TSLA) proceeds (TSLA not in fresh_open)
T3: Broker now has 2 TSLA positions, engine thinks it has 1
```

#### Recommendation
**IMMEDIATE**: Use idempotency key + Alpaca's built-in duplicate detection. Since this is already in place for orders, ensure the order service properly routes to idempotent broker calls. Add a database lock table or atomic insert in outbox if needed.

---

### CRITICAL-3: Unbounded Queue with No Overflow Guarantees (Order Update Loss)

**File**: `/Users/marselkei/VS/intra/backend/integrations/alpaca_stream.py`  
**Lines**: 70-77  
**Severity**: CRITICAL

#### Issue
The trade update queue is documented as "UNBOUNDED" but has no memory limit or drop protection:

```python
# Lines 70-77
# Update queue for backpressure handling.
# UNBOUNDED for trade updates — we must NEVER drop fill/cancel/reject
# messages as that causes state divergence and missed exits.
# Non-critical messages (heartbeats, etc.) are not queued.
self.update_queue: asyncio.Queue = asyncio.Queue()
self.queue_processor_task = None
self._queue_high_water_mark = 0
self._queue_overflow_count = 0
```

#### Risk
While `asyncio.Queue()` doesn't drop messages by design, the comment about "unbounded" indicates false confidence. If the queue processor (`_process_update_queue`) becomes blocked (e.g., database slowness), messages accumulate in memory. With high-frequency trading (10ms ticks), the queue can grow unbounded:
- Each Alpaca trade_update adds 1 item to queue
- If processor stalls for 1 second, 100 items accumulate
- If database connection pooling exhausts, processor stalls indefinitely
- Memory consumption → OOM crash → all queued updates lost

#### Proof of Vulnerability
Line 322-329 warns about queue depth:
```python
qsize = self.update_queue.qsize()
self._queue_high_water_mark = max(self._queue_high_water_mark, qsize)
if qsize > 500:
    self._queue_overflow_count += 1
    logger.warning(
        "Trade update queue depth high: %d (hwm=%d, overflow_events=%d)",
        qsize, self._queue_high_water_mark, self._queue_overflow_count,
    )
```

But there's no action taken when queue exceeds threshold—just logging.

#### Recommendation
**IMMEDIATE**: Implement a bounded queue with drop strategy:

```python
# Use bounded queue (e.g., 5000 max pending updates)
self.update_queue: asyncio.Queue = asyncio.Queue(maxsize=5000)

# In _process_trade_update, add timeout retry or circuit breaker:
try:
    await self.update_queue.put(data, timeout=1.0)  # Fail fast if queue full
except asyncio.QueueFull:
    logger.critical("Trade update queue FULL — order updates LOST")
    # Emit critical alert, trigger failover
```

---

### CRITICAL-4: Duplicate Order Submission on Worker Restart (No Deduplication After Broker Response)

**File**: `/Users/marselkei/VS/intra/backend/infra/outbox_worker.py`  
**Lines**: 297-409  
**Severity**: CRITICAL

#### Issue
The outbox worker's order submission flow does not atomically mark events as "sent" before confirming broker response:

```python
# Lines 297-409: _process_order_submitted
# Submits order to broker, but if DB update fails, event stays in outbox
if result.get("success", False):
    final_status = result.get("status", "submitted")
    # ...
    await self._update_order_status(  # Line 383
        order_id=order_id,
        status=final_status,
        broker_order_id=result.get("broker_order_id"),
        details=result
    )
    # Then mark as sent:
    await self._mark_event_succeeded(event_id, result)  # Line 236 (in _process_event)
```

#### Risk
Consider this failure scenario:
1. Worker claims outbox event "order_123"
2. Calls broker, gets back order ID "alpaca_456"
3. Starts updating database with `attach_broker_result()` 
4. Database connection dies mid-write
5. `_update_order_status()` raises exception (line 636)
6. Exception propagates, `_mark_event_succeeded()` never called (line 236 skipped)
7. Worker's session.commit() never happens for the event
8. Event stays in outbox with status="pending"
9. Next worker instance picks it up, submits again
10. Alpaca now has TWO orders with different client_order_ids for same symbol

This is a classic **distributed transaction failure**—order sent but DB not updated.

#### Proof
Line 636 in `_update_order_status()`:
```python
except Exception as e:
    logger.error("Failed to update order status via ORM", ...)
    # Re-raise to ensure failure is propagated
    raise  # ← Exception propagates to _process_event
```

Line 261-295 in `_process_event()` catches this exception and calls `_move_to_dlq()`, but only if `_update_order_status()` raises. The order has ALREADY been sent to Alpaca at this point.

#### Recommendation
**IMMEDIATE**: Implement idempotent order submission with Alpaca's `client_order_id`. The current code at line 239 passes `client_order_id=client_key`, but `client_key` must be stable across retries:

```python
# Ensure client_key is deterministic, not random:
# BAD: client_key = str(uuid.uuid4())  # Different each retry
# GOOD: client_key = f"outbox_{event_id}"  # Same across retries
```

Verify `client_key` in outbox payload is deterministic.

---

### CRITICAL-5: WebSocket Reconnection Gap (30-60 seconds of Lost Updates)

**File**: `/Users/marselkei/VS/intra/backend/integrations/alpaca_stream.py`  
**Lines**: 554-599  
**Severity**: CRITICAL

#### Issue
When WebSocket connection is lost, there's a gap between disconnect and reconnect where order updates are not received:

```python
# Lines 554-599: start_with_reconnect()
while self.should_reconnect:
    try:
        if await self.connect():  # Line 566
            # Reset reconnection delay on successful connect
            self.reconnect_delay = 1.0
            self.reconnect_attempts = 0
            
            # Listen for messages
            await self.listen()  # Line 574
            
        # Connection lost, attempt reconnection
        if self.should_reconnect:
            self.reconnect_attempts += 1
            # ... exponential backoff ...
            await asyncio.sleep(self.reconnect_delay)  # Line 605
            # Exponential backoff can reach 60 seconds (max_reconnect_delay=60.0)
```

#### Risk
If Alpaca WebSocket disconnects (network hiccup, server restart), the stream client:
1. Detects connection lost during `listen()` (line 289)
2. Sets `is_connected=False`
3. Tries to reconnect with exponential backoff: 1s → 2s → 4s → 8s → 16s → 32s → 60s → 60s...
4. After 10 failed attempts, enters "slow retry" mode with 5-30 minute delays (line 589)

During this gap (0s-60s minimum, up to 30 minutes), **all trade_updates are lost**. When reconnect succeeds, positions are out of sync:
- Broker may have filled/cancelled orders that stream never received
- Position state diverges from engine's tracking
- Exit logic uses stale position data
- Can miss stop-losses, profit targets

#### Real-World Scenario
```
T0: Order AAPL+100 submitted
T+5s: WebSocket drops (Alpaca server restart)
T+5-65s: Reconnect backoff (min 1 min)
T+65s: Stream reconnects
Result: Engine doesn't know AAPL order was filled at T+10s
        Engine still thinks it's pending
        Exit logic never triggers (position not recognized)
```

#### Recommendation
**IMMEDIATE**: Implement order status reconciliation on reconnect:

```python
async def _reconnected_handler(self):
    """Called after successful reconnect to sync state."""
    logger.info("Stream reconnected, reconciling order state...")
    
    # Query all open orders from REST API
    broker_client = get_alpaca_broker_client()
    broker_orders = await broker_client.get_open_orders()
    
    # Compare with in-memory tracking, update any mismatches
    for order_id in self._pending_orders:
        if order_id not in broker_orders:
            # Order was filled/cancelled while stream was down
            await self._handle_order_status_update(...)
```

---

### CRITICAL-6: Cooldown Logic Can Permanently Block Legitimate Exits

**File**: `/Users/marselkei/VS/intra/backend/organism/live_engine.py`  
**Lines**: 785, 820, 840, 882, 902, 942-943, 996-997  
**Severity**: CRITICAL

#### Issue
When an exit order is submitted, the symbol is added to `_exit_cooldown` for 3 ticks (~30 seconds):

```python
# Line 785, 820, 840, 882: Exit cooldown is set
self._exit_cooldown[sym] = self._tick_count

# Lines 942-943: Cooldown blocks pyramiding
if sym in self._exit_cooldown:
    continue  # Don't pyramid a symbol with pending exit

# Lines 996-997: Cooldown blocks new entries
if c.symbol in self._exit_cooldown:
    continue  # Wash trade cooldown
```

But there's a critical bug: if an exit order **fails** (network error, validation error), the cooldown is still set:

```python
# Lines 901-903: Bug — cooldown set even on failure
except Exception as e:
    result.errors.append(f"Safety net exit failed for {sym}: {e}")
finally:
    self._exit_cooldown[sym] = self._tick_count  # ← Always set, even on failure!
```

#### Risk
Scenario:
1. Position in AAPL at -8% loss (max loss threshold reached)
2. Engine calls `_submit_exit_order()` → network timeout → fails
3. Cooldown set: `_exit_cooldown[AAPL] = 100`
4. AAPL continues to drop to -9%, -10%, -11%...
5. Next exit check (tick 103): AAPL skipped due to cooldown (line 996)
6. Cooldown expires after 3 ticks, but by then AAPL is -15% loss
7. Portfolio suffers unnecessary $500k loss

This directly violates the safety net's purpose (max 15% loss protection).

#### Proof
Lines 780-785 and 837-840:
```python
except Exception as e:
    result.errors.append(f"Safety net exit (no features) failed for {sym}: {e}")
finally:
    self._exit_cooldown[sym] = self._tick_count  # ← BUG: Always set
```

Only set cooldown on **success**, not on failure.

#### Recommendation
**IMMEDIATE**: Only set cooldown on successful order submission:

```python
try:
    await self._submit_exit_order(...)
    # Only mark cooldown if order was actually submitted
    self._exit_cooldown[sym] = self._tick_count
    exits_submitted += 1
except Exception as e:
    result.errors.append(...)
    # Do NOT set cooldown on failure — allow retry next tick
```

---

## WARNING FINDINGS

### WARNING-1: Retry Logic Can Submit Orders to Wrong Endpoint During Alpaca API Changes

**File**: `/Users/marselkei/VS/intra/backend/integrations/alpaca_broker.py`  
**Lines**: 420-423  
**Severity**: WARNING

#### Issue
The duplicate order recovery uses a non-standard Alpaca endpoint that may not exist:

```python
# Lines 420-423
url = f"{self.base_url}/v2/orders:by_client_order_id"
resp = await self._make_request_with_retry(
    "GET", url, params={"client_order_id": client_order_id}
)
```

The `:by_client_order_id` syntax is specific to Alpaca, but if this endpoint is deprecated or removed in future API versions, the recovery will fail silently and the order will be treated as lost.

#### Recommendation
Add fallback to standard `/v2/orders` list endpoint if `:by_client_order_id` fails.

---

### WARNING-2: Stream Message Handler Cannot Distinguish Old vs New Alpaca API Response Formats

**File**: `/Users/marselkei/VS/intra/backend/integrations/alpaca_stream.py`  
**Lines**: 312-341  
**Severity**: WARNING

#### Issue
The message handler checks both old and new API formats but logs success without verifying consistency:

```python
# Lines 312-341
msg_type = data.get("T") or data.get("stream")

if msg_type == "trade_updates":
    await self.update_queue.put(data)
    # ...
elif msg_type == "success":
    logger.debug("Success message received", msg=data.get("msg"))
elif msg_type == "error":
    logger.error("Error message from stream", error=data)
```

If Alpaca sends mixed-format responses (some with "T" field, some with "stream"), the handler will silently accept malformed messages. The `_process_trade_update()` then tries to extract `data.get("data", {}).get("order", ...)` which may not exist.

#### Recommendation
Add strict format validation and reject messages that don't match expected structure.

---

### WARNING-3: Order Status Update Missing Transaction Boundaries

**File**: `/Users/marselkei/VS/intra/backend/infra/outbox_worker.py`  
**Lines**: 620, 654, 710, 770  
**Severity**: WARNING

#### Issue
Database commits happen after potentially complex operations with no rollback strategy:

```python
# Line 620: Commit after _update_order_status
await session.commit()

# But if _update_order_status raised and was caught elsewhere,
# partial state may be committed
```

The code doesn't use database transactions consistently. If multiple operations happen in sequence and one fails mid-way, the database could be left in an inconsistent state.

#### Recommendation
Wrap entire order processing in a single transaction using explicit savepoints or SQLAlchemy's nested transaction support.

---

### WARNING-4: Alpaca Broker Client Has No Circuit Breaker (Cascading Failures)

**File**: `/Users/marselkei/VS/intra/backend/integrations/alpaca_broker.py`  
**Lines**: 29-75  
**Severity**: WARNING

#### Issue
The retry decorator will exhaust retries quickly but doesn't implement a circuit breaker. If Alpaca is experiencing degraded service, the engine will:
1. Retry aggressively (3 retries with exponential backoff)
2. Fail and raise `HTTPException`
3. Next order immediately attempts 3 more retries
4. Result: 30 orders × 3 retries = 90 API calls to a failing service

#### Recommendation
Implement circuit breaker pattern: after N consecutive failures, fail-fast for subsequent requests.

---

### WARNING-5: Position Fetching Can Return Stale Data (Eventual Consistency Issue)

**File**: `/Users/marselkei/VS/intra/backend/organism/live_engine.py`  
**Lines**: 1132-1136  
**Severity**: WARNING

#### Issue
`get_all_positions()` is assumed to return fresh data, but there's no guarantee:

```python
try:
    fresh_positions = await self._positions_service.get_all_positions()
    fresh_open = set(fresh_positions.keys())
except Exception:
    fresh_open = open_symbols  # Fallback to stale data!
```

If the positions service has a cache layer or uses eventual consistency, the returned positions could be 5-10 seconds old. Meanwhile, the engine's internal state (`open_symbols`) could be more recent.

#### Recommendation
Add timestamp to positions response and warn if data is older than 2 ticks.

---

## INFO FINDINGS

### INFO-1: Mock Broker Has No Failure Rate Ceiling (Can Exceed Production Error Budget)

**File**: `/Users/marselkei/VS/intra/backend/infra/outbox_worker.py`  
**Lines**: 449-456  
**Severity**: INFO

#### Issue
The mock broker can simulate failures based on `MOCK_BROKER_FAILURE_RATE` env var:

```python
mock_failure_rate = float(os.getenv("MOCK_BROKER_FAILURE_RATE", "0"))
if mock_failure_rate > 0 and random.random() < mock_failure_rate:
    return {
        "success": False,
        "error": "Simulated broker error",
        "order_id": order_id
    }
```

If `MOCK_BROKER_FAILURE_RATE=1.0` (100% failures), the entire system becomes non-functional. There's no validation or warning.

#### Recommendation
Add validation: clamp `MOCK_BROKER_FAILURE_RATE` to [0, 0.1] (max 10% failures).

---

### INFO-2: Heartbeat Ping-Pong Implementation Assumes websockets Library Version Compatibility

**File**: `/Users/marselkei/VS/intra/backend/integrations/alpaca_stream.py`  
**Lines**: 510-533  
**Severity**: INFO

#### Issue
The heartbeat loop sends pings:

```python
if self.websocket and self.is_connected:
    try:
        await self.websocket.ping()  # Line 523
        self.last_heartbeat = current_time
```

The `websockets` library version may not implement `.ping()` the same way. If using an older version, `.ping()` might not exist or behave differently.

#### Recommendation
Add version check and fallback to manual ping/pong messages.

---

## SUMMARY TABLE

| ID | Finding | Severity | Fix Effort | Risk If Not Fixed |
|-----|---------|----------|-----------|-------------------|
| CRIT-1 | Weak idempotency keys (second precision) | CRITICAL | 30min | Duplicate orders every high-frequency second |
| CRIT-2 | Race condition (position check → order gap) | CRITICAL | 1hr | Position desynchronization, duplicate entries |
| CRIT-3 | Unbounded trade update queue | CRITICAL | 1.5hr | OOM crash, all order updates lost |
| CRIT-4 | No atomic order + DB commit | CRITICAL | 2hr | Duplicate orders after worker restart |
| CRIT-5 | WebSocket reconnect gap (60s) | CRITICAL | 1.5hr | Lost fills/cancels, position stale data |
| CRIT-6 | Cooldown blocks exits on failure | CRITICAL | 30min | Max loss protection disabled |
| WARN-1 | Deprecated Alpaca endpoint dependency | WARNING | 30min | API deprecation breaks recovery |
| WARN-2 | No format validation for stream messages | WARNING | 1hr | Silent message corruption |
| WARN-3 | Missing transaction boundaries | WARNING | 1hr | Partial state commits |
| WARN-4 | No circuit breaker on broker client | WARNING | 1.5hr | Cascading failures during outages |
| WARN-5 | Stale position data fallback | WARNING | 30min | Inconsistent entry decisions |
| INFO-1 | Mock failure rate unchecked | INFO | 15min | Test infrastructure explosion |
| INFO-2 | WebSocket library version assumption | INFO | 30min | Compatibility issues on deployment |

---

## IMMEDIATE ACTION ITEMS (Before Paper Trading)

**Priority 1 - MUST FIX (Blocking):**
1. [ ] CRIT-1: Change idempotency key to use microseconds + UUID
2. [ ] CRIT-6: Only set cooldown on successful exit submission
3. [ ] CRIT-4: Verify `client_key` in outbox is deterministic

**Priority 2 - SHOULD FIX (High Risk):**
4. [ ] CRIT-2: Add database-level position lock or use strict serialization
5. [ ] CRIT-3: Implement bounded queue with overflow protection
6. [ ] CRIT-5: Add reconciliation logic on WebSocket reconnect

**Priority 3 - NICE TO FIX (Medium Risk):**
7. [ ] WARN-4: Implement circuit breaker for Alpaca client
8. [ ] WARN-2: Add strict message format validation
9. [ ] WARN-3: Use explicit database transactions

---

## TESTING RECOMMENDATIONS

Before first trade:
- [ ] **High-frequency test**: Submit 100 orders in 1 second, verify no duplicates
- [ ] **WebSocket disconnect test**: Kill stream, verify orders still tracked after reconnect
- [ ] **Outbox worker restart test**: Kill worker mid-order, restart, verify no duplicates
- [ ] **Cool down edge case**: Trigger failed exit, verify next tick retries (not blocked)
- [ ] **Stale position test**: Introduce 30s delay in position fetch, verify no duplicate entries

---

**End of Report**
