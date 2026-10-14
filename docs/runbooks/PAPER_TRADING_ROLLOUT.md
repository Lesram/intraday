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
  - `shadow` = do not submit to broker; the order row is finalized as `rejected`
    with zero fill and `attributes.execution_mode = "shadow"`, and its outbox event
    is marked sent
  - `execute` = normal behavior (submits to broker; paper/live controlled by `ALPACA_PAPER`)
  - `dry_run` = same as `shadow` (no Alpaca call, no simulated fill), recorded with
    `attributes.execution_mode = "dry_run"`

Notes:
- `TRADING_EXECUTION_MODE=paper` or `live` is treated as `execute`. A missing or
  unrecognized value resolves to `shadow` (fail closed).
- There is no `shadow` order status: the database status constraint does not allow
  it, so non-executed orders are recorded as `rejected` (audit 2026-10-05 A3-01).
- `USE_MOCK_BROKER` (legacy; tests and local development) makes the outbox worker
  acknowledge orders as `accepted` with a `MOCK_` broker id. It does not simulate
  fills or prices.

## Recommended Rollout

### Phase 0: Shadow Mode (no broker submission)
1. Set:
   - `ALPACA_PAPER=true`
   - `TRADING_EXECUTION_MODE=shadow`
   - `USE_MOCK_BROKER=false`
2. Start backend + outbox worker.
3. Let strategies run normally.
4. Verify:
   - Orders appear in DB/UI with status `rejected` and `attributes.execution_mode = "shadow"`
   - Outbox events are processed successfully (status `sent`)
   - No broker orders appear in Alpaca

Runtime override (manual orders only):
- An admin can view the runtime override via ML Models → Lifecycle Dashboard →
  "Execution" control or `GET/PUT/DELETE /api/v1/admin/trading/execution-mode`.
- The override applies to manual orders only. The organism engine evaluates the
  effective mode whenever it is constructed (process start and
  `POST /api/v1/settings/restart-engine`; its risk-limit guard checks the loss
  breakers in `execute` mode), so its own orders (entries, exits, EOD flatten)
  always follow the configured `TRADING_EXECUTION_MODE`, never the runtime override.
  Change the configured mode with a restart.
- `PUT` is refused with HTTP 423 while the research policy lock is on (the whole
  research period), with HTTP 409 whenever the process hosts the organism scheduler
  (running, stopped, mid-restart or after its task crashed), and with HTTP 422 for an
  unknown mode. `GET` reports `override_allowed` and `override_blocked_reason`.
  `DELETE` (back to the configured mode) stays allowed.
- The override is per-process and is lost on restart.

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
