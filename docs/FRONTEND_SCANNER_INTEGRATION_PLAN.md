# Frontend Scanner Integration & Platform Communication Audit — Execution Plan

> **Goal:** Expose the Phase 5 Market Scanner and Dynamic Universe data to the
> frontend, add scanner/universe panels to the Organism Dashboard, and fix
> all front/back communication issues discovered during the platform audit.

---

## Table of Contents

1. [Platform Audit Findings](#1-platform-audit-findings)
2. [Step 1 — Backend: Add Scanner & Universe API Endpoints](#2-step-1--backend-add-scanner--universe-api-endpoints)
3. [Step 2 — Backend: Enrich WebSocket Tick Payload](#3-step-2--backend-enrich-websocket-tick-payload)
4. [Step 3 — Frontend: Extend `organismApi.ts`](#4-step-3--frontend-extend-organismapits)
5. [Step 4 — Frontend: Create Scanner Panel Component](#5-step-4--frontend-create-scanner-panel-component)
6. [Step 5 — Frontend: Create Universe Panel Component](#6-step-5--frontend-create-universe-panel-component)
7. [Step 6 — Frontend: Integrate Panels into Organism Dashboard](#7-step-6--frontend-integrate-panels-into-organism-dashboard)
8. [Step 7 — Frontend: Add Real-Time Updates via WebSocket](#8-step-7--frontend-add-real-time-updates-via-websocket)
9. [Step 8 — Fix Platform Communication Issues](#9-step-8--fix-platform-communication-issues)
10. [Verification & Testing](#10-verification--testing)

---

## 1. Platform Audit Findings

### Architecture Summary

| Layer | Stack | Notes |
|-------|-------|-------|
| Frontend | React 19, Vite, Ant Design 5, Zustand, React Query, Socket.IO | Dark theme, `@/` path aliases |
| API Client | Axios → `http://localhost:8000/api/v1` | JWT auth via interceptors |
| WebSocket | Socket.IO client → `http://localhost:8000` | Topic-based subscriptions |
| Backend | FastAPI, Python 3.11, `localhost:8000` | Gunicorn + uvicorn |
| WS Backend | Socket.IO (python-socketio) + native WebSocket manager | Dual WS system |
| Organism | `OrganismScheduler` → `OrganismLiveEngine` → tick every 10s | 1-min bars, SIP feed |

### Current Frontend → Backend Integration Map

| Frontend Feature | Backend Endpoint | Status |
|------------------|------------------|--------|
| Dashboard | `/api/v1/portfolio`, `/api/v1/orders`, `/api/v1/strategies` | OK |
| Orders | `/api/v1/orders` | OK |
| Positions | `/api/v1/positions` | OK |
| Portfolio | `/api/v1/portfolio/*` | OK |
| Strategies | `/api/v1/strategies/*` | OK |
| Backtesting | `/api/v1/backtest/*` | OK |
| ML Models | `/api/v1/models/*` | OK |
| Risk | `/api/v1/risk/*` | OK |
| Market Scanner (Phase 7) | `/api/v1/scanner/scan`, `/scanner/presets`, `ws /scanner/ws` | OK (separate from organism) |
| Organism Dashboard | `/api/v1/organism/status`, `/runs`, `/policy`, `/brain`, `/attribution` | OK |
| **Organism Scanner** | **NONE — no endpoints exist** | **MISSING** |
| **Organism Universe** | **NONE — no endpoints exist** | **MISSING** |

### Issues Found During Audit

#### CRITICAL — Missing Features
1. **No API endpoints** expose the Phase 5 `MarketScanner` data (scanned stocks, tension scores, candidate pool)
2. **No API endpoints** expose `DynamicUniverseSelector` state (active universe, fitness table, rotation history)
3. **No frontend UI** for viewing what stocks the organism's scanner discovered
4. **No frontend UI** for viewing the universe rotation decisions
5. The `live_engine.status()` method returns `universe_size` but NOT the actual symbols or fitness data

#### MODERATE — Communication Gaps
6. **WebSocket tick payload is thin:** `organism_tick` broadcast sends `LiveTickResult.to_dict()` which contains `signals_generated`, `orders_submitted`, `duration_s`, `errors` — but no scanner or universe info
7. **Organism Dashboard polls every 10s** via `setInterval` — this is fine for 10s ticks but polling + WS updates cause duplicate fetches. The WS handler only updates `runs` / `last_tick`, not scanner/universe state
8. **`live_engine.status()` is missing scanner data:** Returns `universe_size: int` but not `universe_symbols`, `scanner_candidates`, `scanner_last_scan_time`, or `fitness_table`

#### LOW — Style / UX
9. The Organism Dashboard has 3 tabs (Overview, Runs History, Learned State) but no tab for Scanner/Universe — the new panels should get their own tab
10. `Scanner.tsx` (Phase 7 market scanner) and the new organism scanner are completely separate systems with different purposes — this should be clear in the UI
11. The organism sidebar item uses `ApartmentOutlined` icon — acceptable but `RadarChartOutlined` or `ScanOutlined` would be more fitting for a scanning organism

---

## 2. Step 1 — Backend: Add Scanner & Universe API Endpoints

### File: `backend/organism/routes.py`

Add 3 new endpoints. These go AFTER the existing `/brain` and `/tick` endpoints.

#### 1a. Add imports at the top (after existing imports, around line 8):

Find:
```python
from backend.utils.logger import get_logger
```

Add after:
```python
from backend.organism.market_scanner import ScannedStock
```

#### 1b. Add response models (after `OrganismRunsResponse`, around line 60):

Add the following Pydantic models:

```python
class ScannerStatusResponse(BaseModel):
    enabled: bool = False
    scan_count: int = 0
    last_scan_time: str | None = None
    candidate_count: int = 0
    candidates: list[dict[str, Any]] = []  # ScannedStock.to_dict() items


class UniverseStatusResponse(BaseModel):
    active_symbols: list[str] = []
    universe_size: int = 0
    fitness_table: list[dict[str, Any]] = []
    scanner_candidates: list[str] = []
    rotation_count: int = 0
    config: dict[str, Any] = {}
```

#### 1c. Add `/organism/scanner` endpoint:

```python
@router.get("/scanner", response_model=ScannerStatusResponse)
async def get_scanner_status(request: Request):
    """Get Phase 5 Market Scanner status — discovered stocks, tension scores."""
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    engine = getattr(scheduler, "_engine", None) if scheduler else None

    if engine is None or engine.market_scanner is None:
        return ScannerStatusResponse(enabled=False)

    scanner = engine.market_scanner
    from datetime import datetime, UTC

    last_time = None
    if scanner.last_scan_time > 0:
        last_time = datetime.fromtimestamp(scanner.last_scan_time, tz=UTC).isoformat()

    return ScannerStatusResponse(
        enabled=True,
        scan_count=scanner.scan_count,
        last_scan_time=last_time,
        candidate_count=len(scanner.candidates),
        candidates=[s.to_dict() for s in scanner.scanned_stocks],
    )
```

#### 1d. Add `/organism/universe` endpoint:

```python
@router.get("/universe", response_model=UniverseStatusResponse)
async def get_universe_status(request: Request):
    """Get Dynamic Universe Selector status — active symbols, fitness, rotation."""
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    engine = getattr(scheduler, "_engine", None) if scheduler else None

    if engine is None:
        return UniverseStatusResponse()

    selector = engine.universe_selector
    fitness_list = [
        sf.to_dict()
        for sf in sorted(
            selector.fitness_table.values(),
            key=lambda sf: sf.fitness,
            reverse=True,
        )
    ]

    return UniverseStatusResponse(
        active_symbols=list(engine._universe),
        universe_size=len(engine._universe),
        fitness_table=fitness_list,
        scanner_candidates=engine._scanner_candidates,
        rotation_count=selector._rotation_count,
        config={
            "min_universe": selector._min,
            "max_universe": selector._max,
        },
    )
```

#### 1e. Add `/organism/scanner/history` endpoint (optional but useful):

```python
@router.get("/scanner/history")
async def get_scanner_history(request: Request):
    """Get the raw list of scanned stock details (latest scan only)."""
    scheduler = getattr(request.app.state, "organism_scheduler", None)
    engine = getattr(scheduler, "_engine", None) if scheduler else None

    if engine is None or engine.market_scanner is None:
        return {"stocks": [], "scan_count": 0}

    scanner = engine.market_scanner
    return {
        "stocks": [s.to_dict() for s in scanner.scanned_stocks],
        "scan_count": scanner.scan_count,
        "last_scan_time": scanner.last_scan_time,
    }
```

---

## 3. Step 2 — Backend: Enrich WebSocket Tick Payload

### File: `backend/organism/live_engine.py`

The `LiveTickResult.to_dict()` is broadcast via WebSocket after each tick. Enrich it with scanner/universe data so the frontend gets real-time updates without polling.

#### 2a. Add fields to `LiveTickResult` dataclass (around line 142):

Find the `LiveTickResult` dataclass:
```python
@dataclass
class LiveTickResult:
    """Return value from one ``live_tick()`` call."""
    timestamp: str = ""
    regime: str = RegimeLabel.UNKNOWN
    signals_generated: int = 0
    orders_submitted: int = 0
    exits_checked: int = 0
    trades_closed: int = 0
    brain_saved: bool = False
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0
```

Replace with:
```python
@dataclass
class LiveTickResult:
    """Return value from one ``live_tick()`` call."""
    timestamp: str = ""
    regime: str = RegimeLabel.UNKNOWN
    signals_generated: int = 0
    orders_submitted: int = 0
    exits_checked: int = 0
    trades_closed: int = 0
    brain_saved: bool = False
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    # Phase 5: Scanner & Universe metadata for frontend
    universe_size: int = 0
    scanner_candidates_count: int = 0
    scanner_ran: bool = False
```

#### 2b. Add to `to_dict()` method:

Find:
```python
    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "regime": self.regime,
            "signals_generated": self.signals_generated,
            "orders_submitted": self.orders_submitted,
            "exits_checked": self.exits_checked,
            "trades_closed": self.trades_closed,
            "brain_saved": self.brain_saved,
            "errors": self.errors,
            "duration_s": round(self.duration_s, 3),
        }
```

Replace with:
```python
    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "regime": self.regime,
            "signals_generated": self.signals_generated,
            "orders_submitted": self.orders_submitted,
            "exits_checked": self.exits_checked,
            "trades_closed": self.trades_closed,
            "brain_saved": self.brain_saved,
            "errors": self.errors,
            "duration_s": round(self.duration_s, 3),
            "universe_size": self.universe_size,
            "scanner_candidates_count": self.scanner_candidates_count,
            "scanner_ran": self.scanner_ran,
        }
```

#### 2c. Populate the new fields in `_live_tick_inner` (around the end of the try block, before the final `except`):

Find the section after entry orders are submitted (around line 755-760), near `# 12. BRAIN SAVE`:

After the brain save block and before `except Exception as e:`, add:

```python
            # Phase 5: Populate scanner/universe metadata
            result.universe_size = len(self._universe)
            result.scanner_candidates_count = len(self._scanner_candidates)
            result.scanner_ran = (
                self.market_scanner is not None
                and self._tick_count % SCAN_INTERVAL_TICKS == 0
            )
```

---

## 4. Step 3 — Frontend: Extend `organismApi.ts`

### File: `frontend/src/features/organism/organismApi.ts`

#### 3a. Add TypeScript interfaces (after `OrganismAttributionResponse`, around line 72):

```typescript
export interface ScannedStock {
  symbol: string;
  source: string;
  price: number;
  volume: number;
  change_pct: number;
  tension_score: number;
}

export interface ScannerStatus {
  enabled: boolean;
  scan_count: number;
  last_scan_time: string | null;
  candidate_count: number;
  candidates: ScannedStock[];
}

export interface SymbolFitness {
  symbol: string;
  fitness: number;
  total_trades: number;
  win_rate: number;
  avg_pnl: number;
  avg_volume_quality: number;
  last_rotated_gen: number;
}

export interface UniverseStatus {
  active_symbols: string[];
  universe_size: number;
  fitness_table: SymbolFitness[];
  scanner_candidates: string[];
  rotation_count: number;
  config: {
    min_universe: number;
    max_universe: number;
  };
}
```

#### 3b. Add API methods (in the `organismApi` object, before the closing `}`):

```typescript
  async getScanner() {
    const { data } = await apiClient.get<ScannerStatus>('/organism/scanner');
    return data;
  },

  async getUniverse() {
    const { data } = await apiClient.get<UniverseStatus>('/organism/universe');
    return data;
  },
```

#### 3c. Update `OrganismRun` interface to include new tick fields:

Find:
```typescript
export interface OrganismRun {
  timestamp?: string;
  regime?: string;
  signals_generated?: number;
  orders_submitted?: number;
  exits_checked?: number;
  trades_closed?: number;
  brain_saved?: boolean;
  errors?: string[];
  duration_s?: number;
}
```

Replace with:
```typescript
export interface OrganismRun {
  timestamp?: string;
  regime?: string;
  signals_generated?: number;
  orders_submitted?: number;
  exits_checked?: number;
  trades_closed?: number;
  brain_saved?: boolean;
  errors?: string[];
  duration_s?: number;
  // Phase 5: Scanner & Universe
  universe_size?: number;
  scanner_candidates_count?: number;
  scanner_ran?: boolean;
}
```

---

## 5. Step 4 — Frontend: Create Scanner Panel Component

### File: `frontend/src/features/organism/ScannerPanel.tsx` (NEW)

Create this new component. It displays:
- Scanner on/off status with colored badge
- Last scan time + scan count
- Number of candidates discovered
- Table of scanned stocks with: symbol, source, price, volume, change %, tension score (as progress bar)
- Sorted by tension score descending
- Color-coded rows: high tension (green), medium (blue), low (gray)

```tsx
import { Card, Table, Tag, Progress, Statistic, Row, Col, Badge, Empty, Typography } from 'antd';
import { RadarChartOutlined, ClockCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { ScannerStatus, ScannedStock } from './organismApi';

const { Text } = Typography;

interface ScannerPanelProps {
  scanner: ScannerStatus | null;
  loading?: boolean;
}

const tensionColor = (score: number): string => {
  if (score >= 0.7) return '#52c41a';  // green — high tension
  if (score >= 0.5) return '#1890ff';  // blue — medium
  if (score >= 0.3) return '#faad14';  // orange — low
  return '#8c8c8c';                     // gray — minimal
};

const sourceTag = (source: string) => {
  const colorMap: Record<string, string> = {
    most_actives: 'blue',
    movers_up: 'green',
    movers_down: 'red',
  };
  return <Tag color={colorMap[source] || 'default'}>{source.replace('_', ' ')}</Tag>;
};

const columns: ColumnsType<ScannedStock & { key: string }> = [
  {
    title: 'Symbol',
    dataIndex: 'symbol',
    key: 'symbol',
    width: 90,
    render: (sym: string) => <Text strong>{sym}</Text>,
  },
  {
    title: 'Source',
    dataIndex: 'source',
    key: 'source',
    width: 120,
    render: sourceTag,
  },
  {
    title: 'Price',
    dataIndex: 'price',
    key: 'price',
    width: 90,
    align: 'right',
    render: (v: number) => `$${v.toFixed(2)}`,
  },
  {
    title: 'Volume',
    dataIndex: 'volume',
    key: 'volume',
    width: 110,
    align: 'right',
    render: (v: number) => {
      if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
      if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
      return v.toString();
    },
    sorter: (a, b) => a.volume - b.volume,
  },
  {
    title: 'Change %',
    dataIndex: 'change_pct',
    key: 'change_pct',
    width: 90,
    align: 'right',
    render: (v: number) => (
      <Text type={v >= 0 ? 'success' : 'danger'}>{(v * 100).toFixed(2)}%</Text>
    ),
    sorter: (a, b) => a.change_pct - b.change_pct,
  },
  {
    title: 'Tension',
    dataIndex: 'tension_score',
    key: 'tension_score',
    width: 150,
    sorter: (a, b) => a.tension_score - b.tension_score,
    defaultSortOrder: 'descend',
    render: (score: number) => (
      <Progress
        percent={Math.round(score * 100)}
        size="small"
        strokeColor={tensionColor(score)}
        format={(pct) => `${pct}%`}
      />
    ),
  },
];

const ScannerPanel = ({ scanner, loading }: ScannerPanelProps) => {
  if (!scanner || !scanner.enabled) {
    return (
      <Card title={<><RadarChartOutlined /> Market Scanner</>}>
        <Empty description="Market Scanner is not enabled. Set SCANNER_ENABLED=true in .env" />
      </Card>
    );
  }

  const lastScan = scanner.last_scan_time
    ? new Date(scanner.last_scan_time).toLocaleTimeString()
    : 'Never';

  const dataSource = scanner.candidates.map((s) => ({ ...s, key: s.symbol }));

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="Status"
              value={scanner.enabled ? 'Active' : 'Off'}
              prefix={<Badge status={scanner.enabled ? 'processing' : 'default'} />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Scans Run" value={scanner.scan_count} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="Last Scan"
              value={lastScan}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Candidates" value={scanner.candidate_count} />
          </Card>
        </Col>
      </Row>

      <Card
        title={`Discovered Stocks (${dataSource.length})`}
        size="small"
      >
        <Table
          dataSource={dataSource}
          columns={columns}
          pagination={{ pageSize: 15, showSizeChanger: true, pageSizeOptions: ['10', '15', '30', '50'] }}
          size="small"
          loading={loading}
          scroll={{ y: 400 }}
          locale={{ emptyText: 'No stocks discovered yet — scanner runs every ~60s' }}
        />
      </Card>
    </div>
  );
};

export default ScannerPanel;
```

---

## 6. Step 5 — Frontend: Create Universe Panel Component

### File: `frontend/src/features/organism/UniversePanel.tsx` (NEW)

Displays:
- Active universe count + max capacity progress bar
- Rotation count
- Fitness table: symbol, fitness (progress bar), trades, win rate, avg PnL
- Visual split: active symbols (green) vs. inactive candidates (gray)
- Scanner candidates badge count

```tsx
import { Card, Table, Tag, Progress, Statistic, Row, Col, Typography, Tooltip } from 'antd';
import { GlobalOutlined, SwapOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { UniverseStatus, SymbolFitness } from './organismApi';

const { Text } = Typography;

interface UniversePanelProps {
  universe: UniverseStatus | null;
  loading?: boolean;
}

const fitnessColor = (fitness: number): string => {
  if (fitness >= 0.7) return '#52c41a';
  if (fitness >= 0.5) return '#1890ff';
  if (fitness >= 0.35) return '#faad14';
  return '#f5222d';
};

const columns = (activeSet: Set<string>): ColumnsType<SymbolFitness & { key: string }> => [
  {
    title: 'Symbol',
    dataIndex: 'symbol',
    key: 'symbol',
    width: 90,
    render: (sym: string) => (
      <Text strong>
        {sym}{' '}
        {activeSet.has(sym) ? (
          <Tag color="green" style={{ fontSize: 10, padding: '0 4px' }}>active</Tag>
        ) : (
          <Tag color="default" style={{ fontSize: 10, padding: '0 4px' }}>pool</Tag>
        )}
      </Text>
    ),
    filters: [
      { text: 'Active', value: 'active' },
      { text: 'Pool', value: 'pool' },
    ],
    onFilter: (value, record) =>
      value === 'active' ? activeSet.has(record.symbol) : !activeSet.has(record.symbol),
  },
  {
    title: 'Fitness',
    dataIndex: 'fitness',
    key: 'fitness',
    width: 140,
    sorter: (a, b) => a.fitness - b.fitness,
    defaultSortOrder: 'descend',
    render: (f: number) => (
      <Tooltip title={f.toFixed(4)}>
        <Progress
          percent={Math.round(f * 100)}
          size="small"
          strokeColor={fitnessColor(f)}
          format={(pct) => `${pct}%`}
        />
      </Tooltip>
    ),
  },
  {
    title: 'Trades',
    dataIndex: 'total_trades',
    key: 'total_trades',
    width: 70,
    align: 'right',
    sorter: (a, b) => a.total_trades - b.total_trades,
  },
  {
    title: 'Win Rate',
    dataIndex: 'win_rate',
    key: 'win_rate',
    width: 90,
    align: 'right',
    render: (v: number) => (
      <Text type={v >= 0.5 ? 'success' : v > 0 ? 'warning' : 'secondary'}>
        {(v * 100).toFixed(1)}%
      </Text>
    ),
    sorter: (a, b) => a.win_rate - b.win_rate,
  },
  {
    title: 'Avg PnL',
    dataIndex: 'avg_pnl',
    key: 'avg_pnl',
    width: 90,
    align: 'right',
    render: (v: number) => (
      <Text type={v >= 0 ? 'success' : 'danger'}>${v.toFixed(2)}</Text>
    ),
    sorter: (a, b) => a.avg_pnl - b.avg_pnl,
  },
  {
    title: 'Vol Quality',
    dataIndex: 'avg_volume_quality',
    key: 'avg_volume_quality',
    width: 90,
    align: 'right',
    render: (v: number) => `${(v * 100).toFixed(0)}%`,
  },
];

const UniversePanel = ({ universe, loading }: UniversePanelProps) => {
  if (!universe || universe.universe_size === 0) {
    return (
      <Card title={<><GlobalOutlined /> Universe</>}>
        <Text type="secondary">Universe data not available — engine may not be running.</Text>
      </Card>
    );
  }

  const activeSet = new Set(universe.active_symbols);
  const capacityPct = Math.round(
    (universe.universe_size / (universe.config.max_universe || 80)) * 100
  );

  const dataSource = universe.fitness_table.map((f) => ({ ...f, key: f.symbol }));

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Active Symbols" value={universe.universe_size} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Capacity" value={`${capacityPct}%`} />
            <Progress
              percent={capacityPct}
              size="small"
              showInfo={false}
              strokeColor={capacityPct > 90 ? '#f5222d' : '#1890ff'}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="Rotations"
              value={universe.rotation_count}
              prefix={<SwapOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Scanner Candidates" value={universe.scanner_candidates.length} />
          </Card>
        </Col>
      </Row>

      <Card
        title={`Fitness Table (${dataSource.length} symbols tracked)`}
        size="small"
      >
        <Table
          dataSource={dataSource}
          columns={columns(activeSet)}
          pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: ['10', '20', '40', '80'] }}
          size="small"
          loading={loading}
          scroll={{ y: 450 }}
          rowClassName={(record) => (activeSet.has(record.symbol) ? '' : 'ant-table-row-muted')}
        />
      </Card>
    </div>
  );
};

export default UniversePanel;
```

---

## 7. Step 6 — Frontend: Integrate Panels into Organism Dashboard

### File: `frontend/src/features/organism/OrganismDashboard.tsx`

#### 6a. Add imports (top of file):

Add after the existing icon imports:
```tsx
import {
  RadarChartOutlined,
  GlobalOutlined,
} from '@ant-design/icons';
```

Add component imports:
```tsx
import ScannerPanel from './ScannerPanel';
import UniversePanel from './UniversePanel';
```

Add type imports:
```tsx
import type { ScannerStatus, UniverseStatus } from './organismApi';
```

#### 6b. Add state variables (after existing `useState` calls, around line 53):

```tsx
const [scannerData, setScannerData] = useState<ScannerStatus | null>(null);
const [universeData, setUniverseData] = useState<UniverseStatus | null>(null);
```

#### 6c. Add scanner/universe to the `fetchAll` function:

In the `Promise.allSettled` array (around line 62), add two more calls:

```tsx
const [statusResult, runsResult, policyResult, brainResult, attributionResult, scannerResult, universeResult] = await Promise.allSettled([
  organismApi.getStatus(),
  organismApi.getRuns(120),
  organismApi.getPolicy(),
  organismApi.getBrain(),
  organismApi.getAttribution(),
  organismApi.getScanner(),
  organismApi.getUniverse(),
]);
```

Add result handling after existing handlers (around line 90):

```tsx
if (scannerResult.status === 'fulfilled') {
  setScannerData(scannerResult.value);
}

if (universeResult.status === 'fulfilled') {
  setUniverseData(universeResult.value);
}
```

#### 6d. Add stat cards for Scanner and Universe in the top row (around line 300):

Add two more `<Col>` items to the existing stat row:

```tsx
<Col xs={24} md={6}>
  <Card size="small">
    <Statistic
      title="Universe"
      value={universeData?.universe_size ?? '-'}
      prefix={<GlobalOutlined />}
      suffix={universeData ? `/ ${universeData.config?.max_universe ?? 80}` : ''}
    />
  </Card>
</Col>
<Col xs={24} md={6}>
  <Card size="small">
    <Statistic
      title="Scanner Candidates"
      value={scannerData?.candidate_count ?? '-'}
      prefix={<RadarChartOutlined />}
    />
  </Card>
</Col>
```

#### 6e. Add Scanner and Universe tabs (in the `<Tabs>` items array):

After the existing `'learned'` tab, add:

```tsx
{
  key: 'scanner',
  label: (
    <span>
      <RadarChartOutlined /> Scanner
      {scannerData?.candidate_count ? (
        <Badge count={scannerData.candidate_count} style={{ marginLeft: 8 }} size="small" />
      ) : null}
    </span>
  ),
  children: <ScannerPanel scanner={scannerData} loading={loading} />,
},
{
  key: 'universe',
  label: (
    <span>
      <GlobalOutlined /> Universe
      {universeData?.universe_size ? (
        <Badge count={universeData.universe_size} style={{ marginLeft: 8 }} size="small" />
      ) : null}
    </span>
  ),
  children: <UniversePanel universe={universeData} loading={loading} />,
},
```

Also add `Badge` to the antd import at the top of the file.

---

## 8. Step 7 — Frontend: Add Real-Time Updates via WebSocket

### File: `frontend/src/features/organism/OrganismDashboard.tsx`

#### 7a. Update the `handleTickMessage` callback to extract scanner/universe data:

The existing `handleTickMessage` updates `runs` and `status.live_engine.last_tick`. Extend it to also update scanner info from the enriched tick payload.

Find:
```tsx
const handleTickMessage = useCallback((wsPayload: unknown) => {
    const payload = wsPayload as Record<string, unknown>;
    const tickData = (payload?.data as OrganismRun | undefined) ?? (payload as OrganismRun);
    if (!tickData || typeof tickData !== 'object') return;

    setRuns((previous) => {
      const next = [tickData, ...previous];
      return next.slice(0, 200);
    });

    setStatus((previous) => {
      if (!previous) return previous;
      return {
        ...previous,
        live_engine: {
          ...(previous.live_engine ?? {}),
          last_tick: tickData,
        },
      };
    });
  }, []);
```

Replace with:
```tsx
const handleTickMessage = useCallback((wsPayload: unknown) => {
    const payload = wsPayload as Record<string, unknown>;
    const tickData = (payload?.data as OrganismRun | undefined) ?? (payload as OrganismRun);
    if (!tickData || typeof tickData !== 'object') return;

    setRuns((previous) => {
      const next = [tickData, ...previous];
      return next.slice(0, 200);
    });

    setStatus((previous) => {
      if (!previous) return previous;
      return {
        ...previous,
        live_engine: {
          ...(previous.live_engine ?? {}),
          last_tick: tickData,
        },
      };
    });

    // Phase 5: If scanner ran this tick, refresh scanner + universe data
    if (tickData.scanner_ran) {
      organismApi.getScanner().then(setScannerData).catch(() => {});
      organismApi.getUniverse().then(setUniverseData).catch(() => {});
    }
  }, []);
```

This avoids polling scanner/universe every 10s — instead it only fetches when the tick payload indicates the scanner actually ran (every ~60s).

---

## 9. Step 8 — Fix Platform Communication Issues

### Issue 6: WebSocket Tick Payload Enhancement
**Already addressed in Step 2** — `LiveTickResult` now includes `universe_size`, `scanner_candidates_count`, and `scanner_ran` fields.

### Issue 7: Duplicate Polling + WS Updates
**Severity: Low.** The current pattern (poll every 10s + WS) is acceptable since the poll fetches more data (brain, attribution, policy) that WS doesn't provide. No change needed.

### Issue 8: `live_engine.status()` Missing Data

#### File: `backend/organism/live_engine.py`

Find the `status()` method (around line 1336):
```python
    def status(self) -> dict[str, Any]:
        """Return organism engine status for API/monitoring."""
        return {
            "initialized": self._initialized,
            "tick_count": self._tick_count,
            "total_trades": len(self._all_trades),
            "brain_generation": self.brain.generation,
            "brain_total_runs": self.brain.total_runs,
            "evolved_generation": self.evolved_params.evolution_generation,
            "evolved_adaptations": self.evolved_params.total_adaptations,
            "peak_equity": self._peak_equity,
            "governance": self.governance.to_dict(),
            "universe_size": len(self._universe),
            "positions_tracked": len(self._entry_metadata),
        }
```

Replace with:
```python
    def status(self) -> dict[str, Any]:
        """Return organism engine status for API/monitoring."""
        scanner_info = {}
        if self.market_scanner is not None:
            scanner_info = {
                "scanner_enabled": True,
                "scanner_scan_count": self.market_scanner.scan_count,
                "scanner_candidates_count": len(self._scanner_candidates),
                "scanner_last_scan_time": self.market_scanner.last_scan_time,
            }
        return {
            "initialized": self._initialized,
            "tick_count": self._tick_count,
            "total_trades": len(self._all_trades),
            "brain_generation": self.brain.generation,
            "brain_total_runs": self.brain.total_runs,
            "evolved_generation": self.evolved_params.evolution_generation,
            "evolved_adaptations": self.evolved_params.total_adaptations,
            "peak_equity": self._peak_equity,
            "governance": self.governance.to_dict(),
            "universe_size": len(self._universe),
            "universe_symbols": list(self._universe),
            "positions_tracked": len(self._entry_metadata),
            **scanner_info,
        }
```

### Issue 9: Muted Row Styling for Universe Table

#### File: `frontend/src/features/organism/UniversePanel.tsx`

The `rowClassName` uses `'ant-table-row-muted'` which may not exist in Ant Design. Add inline style override.

Replace the `rowClassName` prop in the table:
```tsx
rowClassName={(record) => (activeSet.has(record.symbol) ? '' : 'universe-row-inactive')}
```

And add a `<style>` tag at the bottom of the component (or use CSS module):
```tsx
// Add just before export:
const UniversePanelWithStyle = (props: UniversePanelProps) => (
  <>
    <style>{`
      .universe-row-inactive td { opacity: 0.55; }
    `}</style>
    <UniversePanel {...props} />
  </>
);
export default UniversePanelWithStyle;
```

Or simpler: just use Ant Design's built-in approach — omit `rowClassName` and rely on the active/pool tag for visual distinction.

### Issue 10: UI Naming Clarity

The Phase 7 scanner (`/market-data` route, sidebar "Market Scanner") and the Phase 5 organism scanner are different:
- Phase 7: User-controlled technical filter scanner (RSI, MACD, etc.)
- Phase 5: AI-driven tension/breakout discovery scanner

**No code change needed** — they're on separate pages:
- `/market-data` → Phase 7 "Market Scanner"
- `/organism` → Tab "Scanner" within Living Organism

The tab labeling makes the distinction clear.

### Issue 11: Sidebar Icon (Optional)

#### File: `frontend/src/components/layout/AppSidebar.tsx`

Find:
```tsx
{ key: '/organism', icon: <ApartmentOutlined />, label: 'Living Organism' },
```

This is fine, but if desired, could be changed to:
```tsx
{ key: '/organism', icon: <ExperimentOutlined />, label: 'Living Organism' },
```

`ExperimentOutlined` is already imported. Low priority — skip unless requested.

---

## 10. Verification & Testing

### 10a. Backend Verification

After implementing Steps 1-2:

```powershell
# Start backend
python main.py

# Test new endpoints (wait for organism to initialize)
# Replace TOKEN with your JWT
$headers = @{ "Authorization" = "Bearer $TOKEN" }

# Scanner endpoint
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/organism/scanner" -Headers $headers

# Universe endpoint
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/organism/universe" -Headers $headers

# Full status (should now include scanner_* fields in engine)
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/organism/status" -Headers $headers
```

Expected behavior:
- `/organism/scanner` returns `{enabled: true, scan_count: N, candidates: [...], last_scan_time: "..."}` after first scanner tick
- `/organism/universe` returns `{active_symbols: [...], fitness_table: [...], rotation_count: N}`
- Tick results via WS now include `universe_size`, `scanner_candidates_count`, `scanner_ran`

### 10b. Frontend Verification

After implementing Steps 3-7:

```powershell
cd frontend
npm run dev
```

1. Navigate to `/organism`
2. Verify 5 top stat cards: State, Policy Version, Tick Count, Recorded Runs, **Universe**, **Scanner Candidates**
3. Click "Scanner" tab → see scanned stocks table with tension scores
4. Click "Universe" tab → see fitness table with active/pool tags
5. Wait 60 seconds → scanner should auto-refresh when `scanner_ran=true` comes via WebSocket
6. Verify no console errors

### 10c. TypeScript Compilation Check

```powershell
cd frontend
npx tsc --noEmit
```

### 10d. Rollback

If scanner panel causes issues:
- Backend: Set `SCANNER_ENABLED=false` in `.env` — scanner endpoint returns `{enabled: false}`, panel shows "not enabled" message
- Frontend: New tabs are lazy-rendered and have empty states — they gracefully degrade

---

## Summary of Files to Create/Modify

| File | Action | Key Change |
|------|--------|------------|
| `backend/organism/routes.py` | **MODIFY** | Add `/organism/scanner`, `/organism/universe`, `/organism/scanner/history` endpoints |
| `backend/organism/live_engine.py` | **MODIFY** | Enrich `LiveTickResult` with scanner/universe fields, enrich `status()` |
| `frontend/src/features/organism/organismApi.ts` | **MODIFY** | Add interfaces + API methods for scanner & universe |
| `frontend/src/features/organism/ScannerPanel.tsx` | **CREATE** | New component: scanned stocks table with tension scores |
| `frontend/src/features/organism/UniversePanel.tsx` | **CREATE** | New component: fitness table with active/pool visual |
| `frontend/src/features/organism/OrganismDashboard.tsx` | **MODIFY** | Add state, fetch calls, stat cards, two new tabs, WS handler for scanner_ran |

### Execution Order

1. **Backend first** — Add API endpoints (routes.py) + enrich tick payload (live_engine.py)
2. **Frontend API layer** — Extend organismApi.ts with types + methods
3. **Frontend components** — Create ScannerPanel.tsx, UniversePanel.tsx
4. **Frontend integration** — Wire panels into OrganismDashboard.tsx
5. **Test end-to-end** — Start backend → start frontend → verify tabs + WS updates

### Dependencies

- Steps 1-2 (backend) have no frontend dependencies
- Steps 3-7 (frontend) depend on Steps 1-2 being deployed
- All steps are safe to deploy incrementally — new endpoints return empty data if scanner hasn't run yet
