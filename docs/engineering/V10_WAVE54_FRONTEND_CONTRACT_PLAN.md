# V10 Wave-54 — Frontend/Backend Contract Plan

**Date:** 2026-05-03
**Status:** Backend-side fixes shipped (VV-3 OrderStatus enum widening). Frontend
changes proposed for follow-up.

## V10 VV findings recap

V10 Track VV (frontend/backend contract drift) surfaced 5 findings.
Wave-54 ships the safe backend changes; the frontend-side changes are
sketched here for the next deploy cycle (requires frontend build +
manual UI verification).

## Shipped (backend-only, this wave)

### VV-3: `OrderStatus` enum widened

`backend/risk/types.py::OrderStatus` now includes the full Alpaca wire
vocabulary:

- Added: `PENDING_NEW`, `SUBMITTING`, `ACCEPTED`, `ACCEPTED_FOR_BIDDING`,
  `PARTIALLY_FILLED`, `EXPIRED`, `DONE_FOR_DAY`, `STOPPED`, `REPLACED`,
  `CALCULATED`.
- Aliases preserved: `PARTIAL` (legacy → `PARTIALLY_FILLED`),
  `CANCELLED` (UK spelling alongside `CANCELED`).

Frontend `OrderStatus` should be regenerated from OpenAPI to match
this set; until then, frontend code that compares strings will silently
ignore unknown statuses (default-branch fall-through).

## Deferred (frontend-side, next deploy)

### VV-1: `OrderValidationResponse` snake_case ↔ camelCase

Backend emits `estimated_cost`, `estimated_buying_power_after`,
`current_value`, `limit_value`. Frontend `frontend/src/types/trading.ts`
reads camelCase. Pre-trade UI shows `undefined` / `N/A`.

**Recommended fix:** add `model_config = ConfigDict(alias_generator=to_camel)`
to the pydantic schema OR rename frontend keys to snake_case. Either
works; pydantic-side is one-line and removes a long-tail of similar
drift. Apply when shipping next wave.

### VV-2: Risk endpoints serialize Decimals as strings

Backend's pydantic serializes `Decimal` as JSON string by default.
Frontend `RiskMetric.current_value: number` lies; it's actually
`current_value: string` and frontend `RiskMetricCard.tsx`,
`RiskViolationList.tsx`, `RiskLimitsConfig.tsx` mask with
`parseFloat(x.toString())`.

**Recommended fix:** add a serializer `@field_serializer('current_value')`
that returns float, OR fix the TS type to honestly say `string` and
let frontend parse. Float is friendlier; pick one and ship.

### VV-4: WebSocket `settings_update` broadcast has no FE listener

`backend/api/socketio_server.py::broadcast_settings_update` emits the
event. `frontend/src/services/websocketManager.ts` has zero listeners
and `WebSocketTopic` enum lacks `'settings'`. Settings updates from
one tab never propagate to others.

**Recommended fix:** add `'settings'` to `WebSocketTopic`; add a
listener that invalidates the settings query / store.

### VV-5: Rich error envelope dropped on the floor

Backend emits `{"error": {code, message, context, field, timestamp,
path}}` (e.g. `RiskReasonCode` payloads).
`frontend/src/services/api.ts::handleApiError` reads only `data.detail`.

**Recommended fix:** extend `handleApiError` to surface
`data.error.code` + `data.error.context` for user-facing error
messages. The hand-rolled `ApiError` interface in `types/index.ts` is
unused dead code; replace it with the backend envelope shape.

## V11 forward: ship `openapi-typescript` codegen

The single highest-leverage long-term fix for frontend/backend
contract discipline.  Proposed sequence:
1. Add OpenAPI export to backend (FastAPI builds it natively via `/openapi.json`).
2. Add `npm install --save-dev openapi-typescript` in `frontend/`.
3. Add a `generate:api-types` npm script that pulls from `/openapi.json` → `frontend/src/types/api.generated.ts`.
4. Make the frontend build depend on this script.
5. Delete the three layers of hand-rolled DTOs (`types/index.ts`, `store/ordersStore.ts` types, `store/positionsStore.ts` types).
6. Add a CI step that asserts `api.generated.ts` is checked in and current.

This eliminates VV-1, VV-2, VV-3 by construction. VV-4 and VV-5 still
need explicit listener / handler additions.

## Tracking

- **Wave 54** (this wave): backend OrderStatus widening shipped.
- **Wave 54-FE** (next deploy): VV-1, VV-2, VV-4, VV-5 — frontend-side.
- **V11**: ship `openapi-typescript` codegen.
