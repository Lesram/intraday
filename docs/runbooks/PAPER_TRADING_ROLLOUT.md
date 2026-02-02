# Paper Trading Rollout (Shadow → Paper)

## Goals
- Verify end-to-end signal → risk → order pipeline without risking real capital.
- Measure operational reliability (outbox queue, broker latency, failure handling).
- Confirm risk controls and circuit breaker behavior before scaling.

## Key Environment Variables
- `ALPACA_PAPER`:
  - `true` = use Alpaca paper endpoint
  - `false` = use Alpaca live endpoint
- `TRADING_EXECUTION_MODE`:
  - `shadow` = do not submit to broker; orders are recorded and marked `shadow`
  - `execute` = normal behavior (submits to broker; paper/live controlled by `ALPACA_PAPER`)
  - `dry_run` = simulate broker submission (no Alpaca call)

Notes:
- `TRADING_EXECUTION_MODE=paper` or `live` is treated as `execute`.
- `USE_MOCK_BROKER` (legacy) forces the outbox worker to simulate broker responses.

## Recommended Rollout

### Phase 0: Shadow Mode (no broker submission)
1. Set:
   - `ALPACA_PAPER=true`
   - `TRADING_EXECUTION_MODE=shadow`
   - `USE_MOCK_BROKER=false`
2. Start backend + outbox worker.
3. Let strategies run normally.
4. Verify:
   - Orders appear in DB/UI with status `shadow`
   - Outbox events are processed successfully
   - No broker orders appear in Alpaca

Tip (runtime toggle):
- If you're logged in as an admin, you can flip execution mode at runtime (no restart)
  via:
  - UI: ML Models → Lifecycle Dashboard → "Execution" control
  - API: `GET/PUT/DELETE /api/v1/admin/trading/execution-mode`
  - Note: this override is per-process (if you run multiple workers, set env vars
    consistently or add a shared override store).

### Phase 1: Paper Execution (real broker submission to paper)
1. Set:
   - `ALPACA_PAPER=true`
   - `TRADING_EXECUTION_MODE=execute`
   - `USE_MOCK_BROKER=false`
2. Verify:
   - Outbox worker submits orders to Alpaca paper
   - Order status updates reflect broker responses
   - Portfolio/positions update from paper account

### Phase 2: Scale & Guardrails
- Start with a small symbol universe and low max notional per trade.
- Monitor:
  - outbox queue depth
  - broker submission latency
  - order failure / retry rates
  - risk rejections and circuit breaker state

## Quick PowerShell Examples
- Shadow mode:
  - `$env:ALPACA_PAPER='true'`
  - `$env:TRADING_EXECUTION_MODE='shadow'`

- Paper execution:
  - `$env:TRADING_EXECUTION_MODE='execute'`
