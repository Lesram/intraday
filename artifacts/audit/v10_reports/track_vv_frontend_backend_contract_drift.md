# Track VV — Frontend / Backend Contract Drift (V10, NEW LENS)

- Repo: `/Users/marselkei/VS/intra`
- Branch: `rc-1.5-curated`
- HEAD: `c048103`
- OpenAPI fetched live: `docker exec intra-api-1 curl -s http://localhost:8000/openapi.json`
- 197 paths, 102 pydantic schemas in `backend/api/routes/**.py`
- Mode: read-only

## Inventory

### Frontend type sources

- Hand-authored TS only. **No OpenAPI codegen** in the toolchain (no `openapi-typescript`, `orval`, `swagger-codegen`, or generated client anywhere — confirmed against `frontend/package.json` and `find frontend/src -name "types"`). All ~69 `.ts` files in `frontend/src` ship hand-written interfaces.
- Three competing layers of type definitions for the same domain objects:
  1. `frontend/src/types/index.ts` — global "core" types (largely **abandoned** — no consumers for `Order`, `Position` here).
  2. `frontend/src/store/<ordersStore|portfolioStore>.ts` — Zustand stores, **camelCase**, the actually-imported types for orders/positions/portfolio.
  3. Per-feature interfaces in `services/*.ts` (e.g. `BackendOrder` in `ordersService.ts`) used as transport DTOs and manually transformed.
- Domain-specific extras: `types/risk.ts`, `types/trades.ts`, `types/strategy.ts`, `types/ml.ts`, `types/marketData.ts`, `types/websocket.ts`. These are also hand-rolled with no OpenAPI link.

### Backend serialization story (no global convention)

- No global `alias_generator=to_camel` anywhere in `backend/api/routes/`.
- `backend/utils/utilities.py:458` defines a `to_camel_case()` helper, but it is **never wired into a Pydantic model_config**.
- Three different per-route conventions emerge:
  - **Pure snake_case wire format** (default): `audit.py`, `auth.py`, `lots.py`, `orders.py` (`OrderResponse`, `OrderSubmissionResponse`), `risk.py`, `settings.py`.
  - **Pure camelCase with explicit `Field(alias=…)`**: `trades.py` (`Trade`, `TradeAnalytics`, `Execution`), `strategy.py` (`PerformanceMetrics`, …).
  - **Snake-case attrs + `serialization_alias=` to camelCase wire**: `positions.py::PositionDTO`, `api/portfolio.py::PositionResponse` (added 2026-05-02 by V4 O-2).

The frontend is forced to know which of three conventions applies per route — and there is no contract test enforcing it.

---

## Findings

### VV-1 (HIGH) — `OrderValidationResponse` JSON keys do not match the TS interface; defensive comment is wrong

**Backend** (`backend/api/routes/orders.py::OrderValidationResponse`, no alias config):

```
estimated_cost, estimated_price, estimated_buying_power_after,
checks[].current_value, checks[].limit_value
```

(Confirmed via OpenAPI: `jq '.components.schemas.OrderValidationResponse' /tmp/openapi.json` shows exactly those snake_case keys.)

**Frontend** (`frontend/src/types/trading.ts` lines 26-58, 99-110):

```ts
export interface OrderValidationResponse {
  ...
  estimatedCost?: number;
  estimatedBuyingPowerAfter?: number;
}
export interface ValidationCheck {
  ...
  currentValue?: number;
  limitValue?: number;
}
```

The file's own header comment claims:
> *"Field naming: Backend uses snake_case, FastAPI/Pydantic auto-converts to camelCase in JSON"*

That auto-conversion does not exist anywhere in the codebase. Result: every property the frontend reads off `OrderValidationResponse.checks[i].currentValue`, `.limitValue`, and `.estimatedCost`, `.estimatedBuyingPowerAfter` is `undefined` at runtime. `estimated_price` is also missing from the TS interface entirely. Pre-trade validation UI will silently render `N/A`/`undefined` for all of those fields without throwing.

Endpoint: `POST /api/v1/orders/validate`. Consumer: `frontend/src/services/api.ts` callers + components reading `getSeverityColor`, `formatCurrency` in `types/trading.ts`.

---

### VV-2 (HIGH) — Risk endpoints return Decimal-as-string; TS declares `number`; UI quietly hides the mismatch with `parseFloat(x.toString())`

**Backend** (`backend/api/routes/risk.py` → OpenAPI `RiskMetric`, `RiskViolation`, `RiskLimit`, `EmergencyStop`): `current_value`, `limit_value`, `percent_used` are serialized as **`type: "string"`** (Pydantic `Decimal` → string for precision):

```json
"current_value": {"type":"string","pattern":"^...\\d*\\.?\\d*$"}
```

**Frontend** (`frontend/src/types/risk.ts:38-75`, repeated for `RiskViolation`, `RiskLimit`, `EmergencyStop`):

```ts
export interface RiskMetric {
  current_value: number;
  limit_value: number;
  percent_used: number;
  ...
}
```

The TS type says `number`, the runtime value is a `string`. The drift is *invisible to the type-checker* because the frontend works around it everywhere it touches the value:

- `frontend/src/features/risk/RiskMetricCard.tsx:96,106,111,117` — `parseFloat(metric.percent_used.toString())`, `parseFloat(metric.current_value.toString())`, etc.
- `frontend/src/features/risk/RiskViolationList.tsx:160,163` — `parseFloat(violation.current_value.toString())`.
- `frontend/src/features/risk/RiskLimitsConfig.tsx:113` — `parseFloat(limit.limit_value.toString())`.

The defensive `parseFloat(x.toString())` calls confirm engineers already know the type lies. Any future consumer who trusts the declared `number` type and writes plain arithmetic (`metric.current_value * 100`, `metric.percent_used.toFixed(2)`) will compile cleanly and produce `"15.7100"` (string concatenation) or runtime `TypeError` at first call. The same Decimal-as-string pattern likely applies to other endpoints (e.g. anything backed by Numeric columns in `risk/types.py`) — the Risk types are the worst offender because they are the whole API surface.

---

### VV-3 (HIGH) — `OrderStatus` is the most-drifted enum on the platform; defined three times, none matches the broker

Three independent definitions on the frontend, plus the broker upstream:

| Source | Values |
|---|---|
| `frontend/src/store/ordersStore.ts:11` (the *used* one) | `'pending' \| 'submitted' \| 'accepted' \| 'partially_filled' \| 'filled' \| 'cancelled' \| 'rejected'` |
| `frontend/src/types/index.ts:55` (zero consumers) | `'pending' \| 'open' \| 'partially_filled' \| 'filled' \| 'cancelled' \| 'rejected' \| 'expired'` |
| `backend/risk/types.py:28 OrderStatus` enum | `new, submitted, partial, filled, canceled, rejected, pending` |
| Alpaca SDK upstream (real wire values) | `new, pending_new, accepted, accepted_for_bidding, partially_filled, filled, done_for_day, canceled, expired, replaced, pending_cancel, pending_replace, stopped, rejected, suspended, calculated, pending_review` |

The frontend `OrderResponse.status` field is typed as bare `str` in OpenAPI (no enum exposed) and the orders route literally just forwards whatever the broker emits (`backend/api/routes/orders.py:108 "status": order.status`). The `partial`/`partially_filled` mismatch between `risk/types.py` and the frontend store is a hard miss; `cancelled`/`canceled` is a US/UK orthography mismatch (Alpaca emits `canceled`, frontend tag is `cancelled`); statuses like `pending_new`, `done_for_day`, `expired`, `replaced`, `stopped`, `accepted_for_bidding`, `pending_cancel`, `pending_replace`, `calculated`, `suspended` are unknown to all three frontend definitions and will render as raw strings in `getStatusColor` (`frontend/src/features/orders/components/{OrderHistoryTable,ActiveOrdersTable}.tsx`). When `OrderStatus` is used as a TS narrowing type guard (`status: data.status as OrderStatus`, `OrdersPage.tsx:66,85`), real broker payloads silently fail the unioned set and degrade UI affordances (color, icon, filter).

---

### VV-4 (MEDIUM) — Socket.IO emits `settings_update`, the frontend has no listener for it

`backend/api/socketio_server.py:394-405` declares `broadcast_settings_update` (event name `'settings_update'`), called from `backend/api/routes/settings.py:310-313` whenever organism / trading / ML settings are PATCHed.

Frontend handlers (`frontend/src/services/websocketManager.ts:127-163`) register listeners for: `order_update, position_update, portfolio_update, market_data, signal, strategy_update, alert, risk_update, organism_tick`. There is **no** `socket.on('settings_update', …)`, no `'settings_update'` literal anywhere under `frontend/src` (verified by `grep -rn 'settings_update' frontend/src` → no matches), and `WebSocketTopic` in `types/websocket.ts:14-23` does not include `'settings'`. 

Practical impact: when a user (or another tab) updates trading/ML settings via API, every other open browser session will *silently* keep stale settings until manual reload. This is the kind of soft drift the type system cannot catch.

Adjacent note: `PositionUpdateMessage.data` (`types/websocket.ts:69-81`) is declared with snake_case fields (`average_price`, `unrealized_pnl`), but the recently-fixed `PositionDTO` (REST, 2026-05-02 V4 O-2) emits camelCase keys. WS path was not touched. Whether the WS `position_update` payload is ever populated in this branch I could not confirm — no producer was found for it in `backend/`. Either it is dead (FE listener never fires) or the producer exists elsewhere and will mismatch the FE expectation. Worth a follow-up.

---

### VV-5 (MEDIUM) — Two REST error envelopes; FE only reads one of them

`backend/api/errors.py:106-219` runs the standardized `create_error_response()` factory only when `request.app.state.is_platform_app == True`; otherwise it falls back to vanilla FastAPI `{"detail": …}`. The factory itself emits **both**:

```json
{"detail": "...", "error": {"type": "...", "code": "...", "message": "...", "context": {...}, "timestamp": "...", "path": "..."}}
```

Frontend `frontend/src/services/api.ts:165-179`:

```ts
export const handleApiError = (error: unknown): string => {
  ...
  const data = error.response.data ?? {};
  const rendered = _renderDetail(data?.detail);
  if (rendered) return rendered;
  const fallback = data?.message || error.message;
  ...
};
```

Frontend reads only `data.detail` (and falls back to `data.message`, which neither envelope sets at top level). The richer `data.error.code`, `data.error.context`, `data.error.field` payload — explicitly populated for risk-limit breaches and structured API errors via `RiskReasonCode` enum (`backend/risk/types.py:58-67`) — is **dropped on the floor**. Toasts show generic messages instead of structured reasons. The hand-written `ApiError` interface in `types/index.ts:327-331` declares `{code, message, details}` which mirrors *neither* envelope, and is not imported anywhere — pure dead docs.

---

## TL;DR

The frontend has **no OpenAPI-driven contract**: every type is hand-rolled, often two or three times for the same concept, and the backend has **no global serialization convention** — three coexisting styles (raw snake_case, explicit camelCase aliases, snake_case-with-serialization_alias-only) make per-route memorization the only enforcement mechanism. The result is silent drift that the TypeScript compiler is structurally incapable of catching: `OrderValidationResponse` is fully misnamed and ships with a comment that lies about Pydantic auto-conversion (VV-1); risk fields arrive as `Decimal`-strings while declared as `number`, papered over by `parseFloat(x.toString())` workarounds (VV-2); `OrderStatus` is split across three FE definitions and matches neither the backend enum nor the Alpaca wire vocabulary (VV-3); a real Socket.IO event (`settings_update`) has no listener at all (VV-4); and the structured `{"error": {...}}` envelope is silently truncated to `{detail}` by the FE error handler (VV-5). The single highest-leverage remediation is wiring an `openapi-typescript` step that regenerates a `frontend/src/types/api.generated.ts` on every backend change and replacing the three hand-rolled DTO layers with that single source of truth — until that exists, every backend rename is one tab-swap away from a silent UI bug.
