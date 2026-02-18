# Frontend Organism Integration Blueprint (Execution-Ready)

Date: 2026-02-16 (Revised)  
Scope: Full frontend ↔ backend connectivity audit, TypeScript build hygiene, and the Evolving Organism experience (no mock/hardcoded frontend organism values).

---

## 1) Audit Findings (Current State)

### 1.1 Existing organism UI and overlap
- Existing page: `frontend/src/features/organism/OrganismDashboard.tsx`
- Existing parallel monitoring page: `frontend/src/features/strategies/StrategyMonitorPage.tsx`
- Both expose live/system monitoring and controls, producing overlap in UX ownership.

### 1.2 Route/navigation duplication
- Two user-visible entries for adjacent concerns:
  - `/organism` ("Living Organism")
  - `/strategy-monitor` ("Strategy Monitor")
- This duplicates mental model and fragments "live run visibility".

### 1.3 Backend organism surface already available
- `GET /api/v1/organism/status`
- `GET /api/v1/organism/policy`
- `GET /api/v1/organism/attribution`
- `GET /api/v1/organism/brain`
- `GET /api/v1/organism/runs?limit=N`
- `POST /api/v1/organism/{freeze|unfreeze|halt|resume|train|tick}`
- `POST /api/v1/organism/{promote|rollback|compute-attribution}`

### 1.4 Realtime integration
- Organism scheduler broadcasts via **both** raw WebSocket manager and Socket.IO server.
- Frontend Socket.IO manager maps `organism_tick` events to `'organism'` topic.
- Frontend `useWebSocket('organism', handler)` hook subscribes to organism topic.
- Dual broadcast path (`broadcast_to_topic` + `sio_broadcast_to_topic`) ensures coverage.

### 1.5 Frontend typed API surface
- `frontend/src/features/organism/organismApi.ts` — typed methods for all organism endpoints.
- Interfaces: `OrganismRun`, `OrganismStatus`, `OrganismRunsResponse`, `OrganismPolicyResponse`, `OrganismAttributionResponse`.
- WebSocket types: `OrganismTickMessage` in `types/websocket.ts`.

### 1.6 Frontend build hygiene debt (17 errors)
Pre-existing TypeScript strict-mode violations (NOT in organism files) block `npm run build`:

| # | File | Issue | Category |
|---|------|-------|----------|
| 1 | `components/market/ChartContainer.tsx:10` | Unused import `Bar` | TS6196 |
| 2-3 | `features/portfolio/PortfolioPage.tsx:7` | Unused imports `Tag`, `Progress` | TS6133 |
| 4-9 | `features/strategies/StrategyMonitorPage.tsx` | Unused `Select`, `SyncOutlined`, 3× catch `e`, unused `statusColors` | TS6133 |
| 10 | `features/trading/components/ActiveOrdersTable.tsx:56` | Unused `_removeOrder` | TS6133 |
| 11 | `hooks/useIndicators.ts:208` | Unused param `paneIndex` | TS6133 |
| 12 | `lib/queryKeys.ts:15` | Unused `_createQueryKeys` | TS6133 |
| 13 | `services/authService.ts:125` | Unused param `token` | TS6133 |
| 14 | `services/authService.ts:65` | Missing `expires_in` property | TS2741 |
| 15-17 | `types/ml.ts:68,176,274` | `ModelStatus` not in scope (re-export without import under `verbatimModuleSyntax`) | TS2304 |

### 1.7 Integration infrastructure confirmation
- **API client** (`services/api.ts`): Axios with `VITE_API_BASE_URL` + `/api/v1`, token injection, 401 refresh interceptor.
- **WebSocket** (`services/websocketManager.ts`): Socket.IO with `VITE_WS_BASE_URL`, auto-reconnect, heartbeat, topic subscription.
- **Auth store** (`store/authStore.ts`): Zustand with persist, `accessToken`/`refreshToken`/`user`/`tokenExpiresAt`.
- **Backend factory** (`backend/api/factory.py`): Organism routes registered on protected router, scheduler started in lifespan when `ENABLE_ORGANISM_SCHEDULER=1`.
- **Env config** (`frontend/.env.example`): Defines `VITE_API_BASE_URL`, `VITE_WS_BASE_URL`, feature flags.

---

## 2) Target UX (Exact)

Single dedicated tab/page: **Living Organism** at `/organism` with:
- Current status + governance controls (freeze/unfreeze, halt/resume, trigger train/tick).
- Live run status and latest tick metrics pushed via Socket.IO.
- Past runs history (timestamp/regime/signals/orders/errors/duration).
- Improvement indicators computed from real run history (no fabricated metrics).
- Learned state surface from backend truth (`policy`, `brain`, `attribution`).

No additional parallel page for equivalent monitoring concerns in primary navigation.

---

## 3) Execution Plan

### Phase A — Backend readiness for frontend truth [DONE]
1. ✅ Add in-memory bounded run history in organism scheduler (`deque(maxlen=history_limit)`).
2. ✅ Expose `GET /organism/runs?limit=N` endpoint.
3. ✅ Extend scheduler broadcast to emit Socket.IO `organism_tick` to topic `organism`.
4. ✅ Manual tick endpoint also broadcasts via WebSocket.

### Phase B — Frontend integration hardening [DONE]
1. ✅ Add typed organism API service module (`organismApi.ts`).
2. ✅ Extend WebSocket topic types with `'organism'` and wire `organism_tick` event mapping.
3. ✅ Refactor organism dashboard to consume all backend endpoints + websocket tick updates.

### Phase C — Deduplicate UX [DONE]
1. ✅ Remove `/strategy-monitor` from sidebar navigation.
2. ✅ Remove `/strategy-monitor` route registration.
3. ✅ Keep old component file (non-routable) to avoid unrelated refactor risk.

### Phase D — Frontend build hygiene (17 errors) [DONE]
Fix all TypeScript strict-mode violations to achieve clean `npm run build`:

1. ✅ `ChartContainer.tsx` — Remove unused `Bar` import.
2. ✅ `PortfolioPage.tsx` — Remove unused `Tag`, `Progress` imports.
3. ✅ `StrategyMonitorPage.tsx` — Remove unused `Select`, `SyncOutlined` imports; fix 3× catch param `(e)` → `()`; remove unused `statusColors` const.
4. ✅ `ActiveOrdersTable.tsx` — Remove unused `_removeOrder` variable.
5. ✅ `useIndicators.ts` — Prefix unused param `paneIndex` → `_paneIndex`.
6. ✅ `queryKeys.ts` — Remove unused `_createQueryKeys` helper.
7. ✅ `authService.ts` — Add missing `expires_in` to return object; prefix unused `token` → `_token`.
8. ✅ `types/ml.ts` — Convert `export type { ModelStatus } from './index'` to import-then-re-export pattern for `verbatimModuleSyntax` compatibility.

### Phase E — Validation gate [DONE]
1. Run `npm run build` in `frontend/` — must exit 0 with zero TS errors.
2. Run `npx tsc --noEmit` — must report no diagnostics.
3. Verify organism page file has no mock/hardcoded values.
4. Verify route table has no `/strategy-monitor` entry.
5. Verify sidebar has no "Strategy Monitor" item.

---

## 4) Acceptance Criteria

- [x] `npm run build` exits 0 — zero TypeScript errors.
- [x] No mock organism values in the organism page.
- [x] Organism page renders from backend endpoints only.
- [x] Run history is visible and refreshes with real backend data.
- [x] Live updates are accepted from Socket.IO `organism_tick` events.
- [x] Duplicate strategy monitor navigation path is removed from user menu and route table.
- [x] All 17 pre-existing TS errors are resolved.

---

## 5) Validation Checklist

1. Type-check/build frontend (`npm run build` in `frontend/`).
2. Ensure `/organism` loads with auth and shows real backend state.
3. Confirm `POST /organism/tick` updates UI via websocket or polling refresh.
4. Confirm no `/strategy-monitor` menu item or route remains active.
5. Grep for mock/hardcoded organism data in `OrganismDashboard.tsx` — none expected.

---

## 6) Out-of-Scope (This Pass)

- New visual themes/components beyond existing Ant Design primitives.
- Historical persistence beyond scheduler process lifetime (DB-backed run history).
- Deleting legacy monitor component source files.
- Non-organism frontend feature development.
