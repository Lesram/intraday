import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DashboardOutlined,
  DollarOutlined,
  ExperimentOutlined,
  FilterOutlined,
  GlobalOutlined,
  HeartOutlined,
  LoadingOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  SafetyOutlined,
  ThunderboltOutlined,
  TrophyOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Tooltip } from 'antd';
import { useWebSocket } from '@/hooks/useWebSocket';
import { usePortfolio } from '@/hooks/useData';
import { usePortfolioStore } from '@/store/portfolioStore';
import { organismApi, type ActivityEvent, type EngineStats, type OrganismRun, type OrganismStatus, type OrganismAnalytics, type ScannerStatus, type UniverseStatus } from './organismApi';
import ScannerPanel from './ScannerPanel';
import UniversePanel from './UniversePanel';
import PositionHeatmap from '../positions/components/PositionHeatmap';
import PnLWaterfall from '../portfolio/components/PnLWaterfall';
import AttributionPanel from './components/AttributionChart';
import RegimeTimeline from './components/RegimeTimeline';
import DecisionDashboard from './components/DecisionDashboard';
import OrganismOrdersPanel from './components/OrganismOrdersPanel';

const { Title, Text } = Typography;

const safeNumber = (value: unknown, fallback = 0) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
};

const formatDateTime = (value?: string) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

// ── Tick Latency Sparkline (canvas-based) ───────────────────────

const LatencySparkline = ({ runs }: { runs: OrganismRun[] }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const data = useMemo(() => runs.slice(0, 50).map((r) => safeNumber(r.duration_s)).reverse(), [runs]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.length < 2) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    const max = Math.max(...data, 0.1);
    const min = Math.min(...data, 0);
    const range = max - min || 1;

    ctx.clearRect(0, 0, w, h);

    // Draw sparkline
    ctx.beginPath();
    ctx.strokeStyle = '#1890ff';
    ctx.lineWidth = 1.5;
    data.forEach((val, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = h - ((val - min) / range) * (h - 4) - 2;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // 2s threshold line
    const thresholdY = h - ((2 - min) / range) * (h - 4) - 2;
    if (thresholdY > 0 && thresholdY < h) {
      ctx.beginPath();
      ctx.setLineDash([3, 3]);
      ctx.strokeStyle = '#ff4d4f';
      ctx.lineWidth = 1;
      ctx.moveTo(0, thresholdY);
      ctx.lineTo(w, thresholdY);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }, [data]);

  const stats = useMemo(() => {
    if (data.length === 0) return { min: 0, avg: 0, max: 0 };
    return {
      min: Math.min(...data),
      avg: data.reduce((a, b) => a + b, 0) / data.length,
      max: Math.max(...data),
    };
  }, [data]);

  return (
    <Card title="Tick Latency" size="small">
      <canvas ref={canvasRef} width={280} height={60} style={{ width: '100%', height: 60 }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 11 }}>
        <Text type="secondary">Min: {stats.min.toFixed(3)}s</Text>
        <Text type="secondary">Avg: {stats.avg.toFixed(3)}s</Text>
        <Text type={stats.max > 2 ? 'danger' : 'secondary'}>Max: {stats.max.toFixed(3)}s</Text>
      </div>
    </Card>
  );
};

// ── Equity Curve (canvas-based) ─────────────────────────────────

const EquityCurve = ({ runs }: { runs: OrganismRun[] }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Extract equity-like data from tick history (cumulative orders)
    const data = runs
      .slice(0, 100)
      .reverse()
      .map((r) => safeNumber(r.orders_submitted) - safeNumber(r.trades_closed));

    // Build cumulative curve
    const cumulative: number[] = [];
    let sum = 0;
    for (const d of data) {
      sum += d;
      cumulative.push(sum);
    }

    if (cumulative.length < 2) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#999';
      ctx.font = '12px sans-serif';
      ctx.fillText('Insufficient data', 10, 35);
      return;
    }

    const w = canvas.width;
    const h = canvas.height;
    const max = Math.max(...cumulative);
    const min = Math.min(...cumulative);
    const range = max - min || 1;

    ctx.clearRect(0, 0, w, h);

    // Fill under curve
    ctx.beginPath();
    ctx.fillStyle = 'rgba(24, 144, 255, 0.08)';
    cumulative.forEach((val, i) => {
      const x = (i / (cumulative.length - 1)) * w;
      const y = h - ((val - min) / range) * (h - 8) - 4;
      if (i === 0) { ctx.moveTo(x, h); ctx.lineTo(x, y); }
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(w, h);
    ctx.fill();

    // Draw line
    ctx.beginPath();
    const lastVal = cumulative[cumulative.length - 1];
    ctx.strokeStyle = lastVal >= 0 ? '#52c41a' : '#ff4d4f';
    ctx.lineWidth = 1.5;
    cumulative.forEach((val, i) => {
      const x = (i / (cumulative.length - 1)) * w;
      const y = h - ((val - min) / range) * (h - 8) - 4;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }, [runs]);

  return (
    <Card title="Equity Curve (Net Orders)" size="small">
      <canvas ref={canvasRef} width={280} height={80} style={{ width: '100%', height: 80 }} />
    </Card>
  );
};

// ── Signal Heat Map ─────────────────────────────────────────────

const SignalHeatMap = ({ runs }: { runs: OrganismRun[] }) => {
  const heatData = useMemo(() => {
    const symbolCounts: Record<string, number> = {};
    const recent = runs.slice(0, 20);

    for (const run of recent) {
      if (!Array.isArray(run.activity)) continue;
      for (const evt of run.activity) {
        if (evt.type === 'signal' && evt.symbol) {
          symbolCounts[evt.symbol] = (symbolCounts[evt.symbol] || 0) + 1;
        }
      }
    }

    return Object.entries(symbolCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12);
  }, [runs]);

  if (heatData.length === 0) {
    return (
      <Card title="Signal Heat Map" size="small">
        <Text type="secondary">No signal data in recent ticks</Text>
      </Card>
    );
  }

  const maxCount = Math.max(...heatData.map(([, c]) => c), 1);

  return (
    <Card title="Signal Heat Map (Last 20 Ticks)" size="small">
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {heatData.map(([symbol, count]) => {
          const intensity = count / maxCount;
          const bg = `rgba(24, 144, 255, ${0.15 + intensity * 0.75})`;
          return (
            <Tag
              key={symbol}
              style={{
                backgroundColor: bg,
                color: intensity > 0.5 ? '#fff' : '#333',
                fontWeight: intensity > 0.5 ? 600 : 400,
              }}
            >
              {symbol}: {count}
            </Tag>
          );
        })}
      </div>
    </Card>
  );
};

// ── Training Status Indicator ───────────────────────────────────

const TrainingStatus = ({ latestTick }: { latestTick: OrganismRun | null }) => {
  const status = (latestTick as any)?.training_status as string | undefined;
  const meta = (latestTick as any)?.training_metadata as Record<string, unknown> | undefined;

  let icon: React.ReactNode;
  let color: string;
  let label: string;

  switch (status) {
    case 'training':
      icon = <LoadingOutlined spin />;
      color = 'processing';
      label = 'Training in progress...';
      break;
    case 'completed':
      icon = <CheckCircleOutlined />;
      color = 'success';
      label = `Model accepted (${safeNumber(meta?.duration_s).toFixed(1)}s)`;
      break;
    case 'rejected':
      icon = <WarningOutlined />;
      color = 'warning';
      label = meta?.error ? `Rejected: ${meta.error}` : 'Model rejected';
      break;
    default:
      icon = <ClockCircleOutlined />;
      color = 'default';
      label = meta?.last_trained_tick
        ? `Last trained: tick #${meta.last_trained_tick}`
        : 'No training yet';
  }

  return (
    <Card title="Training Status" size="small">
      <Badge status={color as any} text={<Space>{icon}<Text>{label}</Text></Space>} />
    </Card>
  );
};

// ── Regime Explanations ─────────────────────────────────────────

const REGIME_INFO: Record<string, { label: string; color: string; description: string }> = {
  trending_up:   { label: 'Trending Up',   color: '#52c41a', description: 'Strong uptrend — 1.2x position sizing, no time exit' },
  trending:      { label: 'Trending',      color: '#73d13d', description: 'General trend — 1.0x sizing, no time exit' },
  normal:        { label: 'Normal',        color: '#1890ff', description: 'Standard conditions — 0.85x sizing, 40-bar max hold' },
  trending_down: { label: 'Trending Down', color: '#faad14', description: 'Downtrend — 0.6x sizing, 30-bar max hold' },
  chop:          { label: 'Choppy',        color: '#fa8c16', description: 'Sideways/noisy — 0.5x sizing, 25-bar max hold' },
  high_vol:      { label: 'High Vol',      color: '#ff7a45', description: 'Elevated volatility — 0.7x sizing, 30-bar max hold' },
  stress:        { label: 'Stress',        color: '#ff4d4f', description: 'Market stress — 0.3x sizing, 20-bar max hold' },
  crisis:        { label: 'Crisis',        color: '#cf1322', description: 'Extreme stress — 0.1x sizing, 15-bar max hold' },
};

const RegimeTag = ({ regime }: { regime?: string }) => {
  const r = regime && REGIME_INFO[regime];
  if (!r) return <Tag>{regime || 'UNKNOWN'}</Tag>;
  return (
    <Tooltip title={r.description}>
      <Tag color={r.color} style={{ cursor: 'help' }}>{r.label}</Tag>
    </Tooltip>
  );
};

// ── Performance Summary Card ────────────────────────────────────

const PerformanceSummary = ({ engine }: { engine?: EngineStats }) => {
  if (!engine) return null;

  const pnl = safeNumber(engine.cumulative_pnl);
  const winRate = safeNumber(engine.win_rate) * 100;
  const totalTrades = safeNumber(engine.total_trades);
  const equity = safeNumber(engine.current_equity);
  const peakEquity = safeNumber(engine.peak_equity);
  const drawdown = peakEquity > 0 ? ((peakEquity - equity) / peakEquity) * 100 : 0;

  return (
    <Card title={<><DollarOutlined /> <Tooltip title="Organism engine's internal P&L tracking from trades it manages. This tracks only organism-initiated trades.">Engine Performance</Tooltip></>} size="small">
      <Row gutter={[12, 12]}>
        <Col span={8}>
          <Tooltip title="Sum of realized P&L from all closed organism trades">
            <Statistic
              title="Cumulative P&L"
              value={pnl}
              precision={2}
              prefix={pnl >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
              suffix="$"
              valueStyle={{ color: pnl >= 0 ? '#3f8600' : '#cf1322', fontSize: 18 }}
            />
          </Tooltip>
        </Col>
        <Col span={8}>
          <Tooltip title="Percentage of closed organism trades that were profitable (realized only)">
            <Statistic
              title="Win Rate"
              value={winRate}
              precision={1}
              suffix="%"
              prefix={<TrophyOutlined />}
              valueStyle={{ color: winRate >= 50 ? '#3f8600' : winRate > 0 ? '#faad14' : '#999', fontSize: 18 }}
            />
          </Tooltip>
        </Col>
        <Col span={8}>
          <Tooltip title="Total number of round-trip trades completed by the organism">
            <Statistic
              title="Total Trades"
              value={totalTrades}
              valueStyle={{ fontSize: 18 }}
            />
          </Tooltip>
        </Col>
        <Col span={8}>
          <Tooltip title="Engine's internal equity tracking (starting capital + cumulative P&L)">
            <Statistic title="Engine Equity" value={equity} precision={2} prefix="$" valueStyle={{ fontSize: 14 }} />
          </Tooltip>
        </Col>
        <Col span={8}>
          <Tooltip title="Average dollar profit on winning trades">
            <Statistic title="Avg Win" value={safeNumber(engine.avg_win)} precision={2} prefix="$" valueStyle={{ color: '#3f8600', fontSize: 14 }} />
          </Tooltip>
        </Col>
        <Col span={8}>
          <Tooltip title="Average dollar loss on losing trades">
            <Statistic title="Avg Loss" value={safeNumber(engine.avg_loss)} precision={2} prefix="$" valueStyle={{ color: '#cf1322', fontSize: 14 }} />
          </Tooltip>
        </Col>
      </Row>
      {drawdown > 0.5 && (
        <Tooltip title="Peak-to-trough decline in engine equity. >5% triggers circuit breaker review.">
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">Drawdown: </Text>
            <Text type={drawdown > 2 ? 'danger' : 'warning'}>{drawdown.toFixed(2)}%</Text>
          </div>
        </Tooltip>
      )}
    </Card>
  );
};

// ── System Health Card ──────────────────────────────────────────

const SystemHealth = ({ engine, runs }: { engine?: EngineStats; runs: OrganismRun[] }) => {
  const recentErrors = runs.slice(0, 20).reduce((acc, r) => acc + (r.errors?.length ?? 0), 0);
  const errorRate = runs.length > 0 ? (recentErrors / Math.min(runs.length, 20)) * 100 : 0;
  const mlTrained = engine?.ml_trained ?? false;
  const mlAccuracy = safeNumber(engine?.ml_accuracy) * 100;
  const positions = safeNumber(engine?.positions_tracked);
  const generation = safeNumber(engine?.brain_generation);

  return (
    <Card title={<><HeartOutlined /> System Health</>} size="small">
      <Descriptions column={1} size="small">
        <Descriptions.Item label={<Tooltip title="XGBoost direction model. Trains on accumulated bar data to predict price direction. Accuracy shown is walk-forward validation.">ML Model</Tooltip>}>
          {mlTrained
            ? <Tag color="success">Trained ({mlAccuracy.toFixed(1)}% acc)</Tag>
            : <Tag color="warning">Not trained — needs {30} ticks of data</Tag>
          }
        </Descriptions.Item>
        <Descriptions.Item label={<Tooltip title="Evolution generation counter. Increments when the brain self-adapts parameters (feature weights, regime scales, Kelly sizing).">Brain Generation</Tooltip>}>
          <Tag color="blue">Gen {generation}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label={<Tooltip title="Number of positions the organism is actively managing with exit rules (stop-loss, trailing stop, partial take-profit, time exit).">Tracked Positions</Tooltip>}>
          {positions}
        </Descriptions.Item>
        <Descriptions.Item label={<Tooltip title="Whether short selling is enabled. Controlled by evolved_params. Requires positive short win rate and sufficient trade history to auto-enable.">Shorts</Tooltip>}>
          <Tag color={engine?.shorts_enabled ? 'orange' : 'default'}>
            {engine?.shorts_enabled ? 'Enabled' : 'Disabled'}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label={<Tooltip title="Percentage of recent ticks that completed without errors. Below 70% indicates systemic issues.">Error Rate (last 20 ticks)</Tooltip>}>
          <Progress
            percent={Math.round(100 - errorRate)}
            size="small"
            status={errorRate > 30 ? 'exception' : errorRate > 10 ? 'active' : 'success'}
            format={() => `${(100 - errorRate).toFixed(0)}% clean`}
          />
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
};

// ── Broker Portfolio Card (same data source as Dashboard) ─────
const BrokerPortfolio = () => {
  usePortfolio(); // ensure initial fetch
  const portfolio = usePortfolioStore((state) => state.portfolio);

  if (!portfolio) {
    return (
      <Card title={<><DollarOutlined /> <Tooltip title="Live broker account data from Alpaca. Same source as the Dashboard tab — updates in real-time via WebSocket.">Broker Portfolio</Tooltip></>} size="small">
        <Text type="secondary">Loading broker data...</Text>
      </Card>
    );
  }

  const totalPnL = portfolio.totalPnL ?? 0;
  const dayPnL = portfolio.dayPnL ?? 0;
  const posCount = portfolio.positions?.length ?? 0;
  const totalMV = portfolio.positions?.reduce((s, p) => s + (p.marketValue ?? 0), 0) ?? 0;

  return (
    <Card title={<><DollarOutlined /> <Tooltip title="Live broker account data from Alpaca. Same source as the Dashboard tab — updates in real-time via WebSocket.">Broker Portfolio</Tooltip></>} size="small">
      <Row gutter={[12, 12]}>
        <Col span={8}>
          <Tooltip title="Total account value (cash + positions) reported by Alpaca broker">
            <Statistic
              title="Account Equity"
              value={portfolio.totalEquity ?? 0}
              precision={2}
              prefix="$"
              valueStyle={{ fontSize: 18 }}
            />
          </Tooltip>
        </Col>
        <Col span={8}>
          <Tooltip title="Today's profit/loss across all positions (broker-calculated)">
            <Statistic
              title="Day P&L"
              value={dayPnL}
              precision={2}
              prefix={dayPnL >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
              suffix={portfolio.dayPnLPercent ? `(${portfolio.dayPnLPercent.toFixed(1)}%)` : ''}
              valueStyle={{ color: dayPnL >= 0 ? '#3f8600' : '#cf1322', fontSize: 18 }}
            />
          </Tooltip>
        </Col>
        <Col span={8}>
          <Tooltip title="Total unrealized P&L across all open positions (broker-calculated)">
            <Statistic
              title="Total P&L"
              value={totalPnL}
              precision={2}
              prefix={totalPnL >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
              valueStyle={{ color: totalPnL >= 0 ? '#3f8600' : '#cf1322', fontSize: 18 }}
            />
          </Tooltip>
        </Col>
        <Col span={8}>
          <Tooltip title="Available cash not invested in positions">
            <Statistic title="Cash" value={portfolio.cash ?? 0} precision={2} prefix="$" valueStyle={{ fontSize: 14 }} />
          </Tooltip>
        </Col>
        <Col span={8}>
          <Tooltip title="Total market value of all open positions">
            <Statistic title="Positions Value" value={totalMV} precision={2} prefix="$" valueStyle={{ fontSize: 14 }} />
          </Tooltip>
        </Col>
        <Col span={8}>
          <Tooltip title="Number of open positions in the broker account">
            <Statistic title="Open Positions" value={posCount} valueStyle={{ fontSize: 14 }} />
          </Tooltip>
        </Col>
      </Row>
      {posCount > 0 && (
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Positions: {portfolio.positions.map(p => {
              const pnl = p.unrealizedPnL ?? 0;
              return (
                <Tag key={p.symbol} color={pnl >= 0 ? 'success' : 'error'} style={{ marginBottom: 2 }}>
                  {p.symbol} ${pnl.toFixed(0)}
                </Tag>
              );
            })}
          </Text>
        </div>
      )}
    </Card>
  );
};

const OrganismDashboard = () => {
  const [status, setStatus] = useState<OrganismStatus | null>(null);
  const [runs, setRuns] = useState<OrganismRun[]>([]);
  const [policy, setPolicy] = useState<Record<string, number>>({});
  const [brain, setBrain] = useState<Record<string, unknown> | null>(null);
  const [attribution, setAttribution] = useState<Record<string, unknown> | null>(null);
  const [scannerData, setScannerData] = useState<ScannerStatus | null>(null);
  const [universeData, setUniverseData] = useState<UniverseStatus | null>(null);
  const [analyticsData, setAnalyticsData] = useState<OrganismAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [activityFeed, setActivityFeed] = useState<ActivityEvent[]>([]);
  const [activityFilter, setActivityFilter] = useState<string>('all');

  const fetchAll = useCallback(async (withSpinner = false) => {
    if (withSpinner) setLoading(true);
    try {
      const [statusResult, runsResult, policyResult, brainResult, attributionResult, scannerResult, universeResult, analyticsResult] = await Promise.allSettled([
        organismApi.getStatus(),
        organismApi.getRuns(120),
        organismApi.getPolicy(),
        organismApi.getBrain(),
        organismApi.getAttribution(),
        organismApi.getScanner(),
        organismApi.getUniverse(),
        organismApi.getAnalytics(),
      ]);

      if (statusResult.status === 'fulfilled') {
        if (statusResult.value?.enabled === false) {
          setError('Organism is not enabled in backend configuration.');
          setStatus(statusResult.value);
          setRuns([]);
          return;
        }
        setStatus(statusResult.value);
      }

      if (runsResult.status === 'fulfilled') {
        setRuns(Array.isArray(runsResult.value?.runs) ? runsResult.value.runs : []);
      }

      if (policyResult.status === 'fulfilled') {
        setPolicy(policyResult.value?.weights ?? {});
      }

      if (brainResult.status === 'fulfilled') {
        setBrain(brainResult.value);
      }

      if (attributionResult.status === 'fulfilled') {
        setAttribution((attributionResult.value?.attribution ?? null) as Record<string, unknown> | null);
      }

      if (scannerResult.status === 'fulfilled') {
        setScannerData(scannerResult.value);
      }

      if (universeResult.status === 'fulfilled') {
        setUniverseData(universeResult.value);
      }

      if (analyticsResult.status === 'fulfilled') {
        setAnalyticsData(analyticsResult.value);
      }

      setError(null);
    } catch {
      setError('Failed to load organism data from backend.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll(true);
    const interval = setInterval(() => {
      fetchAll(false);
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleTickMessage = useCallback((wsPayload: unknown) => {
    const payload = wsPayload as Record<string, unknown>;
    const tickData = (payload?.data as OrganismRun | undefined) ?? (payload as OrganismRun);
    if (!tickData || typeof tickData !== 'object') return;

    setRuns((previous) => {
      const next = [tickData, ...previous];
      return next.slice(0, 200);
    });

    // Accumulate activity events from tick
    if (Array.isArray(tickData.activity) && tickData.activity.length > 0) {
      setActivityFeed((prev) => [...tickData.activity!, ...prev].slice(0, 200));
    }

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

    // Refresh scanner & universe data when a scan just ran
    if (tickData.scanner_ran) {
      organismApi.getScanner().then(setScannerData).catch((err) => {
        console.warn('Failed to refresh scanner data:', err);
      });
      organismApi.getUniverse().then(setUniverseData).catch((err) => {
        console.warn('Failed to refresh universe data:', err);
      });
    }
  }, []);

  useWebSocket('organism', handleTickMessage);

  const handleAction = useCallback(async (action: 'freeze' | 'unfreeze' | 'halt' | 'resume' | 'train' | 'tick') => {
    setActionLoading(action);
    try {
      await organismApi.action(action);
      message.success(`Organism ${action} completed`);
      await fetchAll(false);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || `Failed to ${action}`);
    } finally {
      setActionLoading(null);
    }
  }, [fetchAll]);

  const governance = status?.governance ?? {};
  const engineStats = status?.live_engine?.engine as EngineStats | undefined;
  const latestTick = useMemo(() => {
    if (status?.live_engine?.last_tick) return status.live_engine.last_tick;
    return runs[0] ?? null;
  }, [runs, status]);

  const runStats = useMemo(() => {
    const validRuns = runs.filter((run) => run?.timestamp);
    const total = validRuns.length;
    const recent = validRuns.slice(0, 10);
    const prev = validRuns.slice(10, 20);

    const avgDurationRecent = recent.length
      ? recent.reduce((acc, item) => acc + safeNumber(item.duration_s), 0) / recent.length
      : 0;
    const avgDurationPrev = prev.length
      ? prev.reduce((acc, item) => acc + safeNumber(item.duration_s), 0) / prev.length
      : 0;
    const durationImprovementPct = avgDurationPrev > 0
      ? ((avgDurationPrev - avgDurationRecent) / avgDurationPrev) * 100
      : 0;

    const errorFreeRecent = recent.filter((item) => (item.errors ?? []).length === 0).length;
    const errorFreeRate = recent.length > 0 ? (errorFreeRecent / recent.length) * 100 : 0;

    const avgSignalsRecent = recent.length
      ? recent.reduce((acc, item) => acc + safeNumber(item.signals_generated), 0) / recent.length
      : 0;

    return {
      total,
      avgDurationRecent,
      durationImprovementPct,
      errorFreeRate,
      avgSignalsRecent,
    };
  }, [runs]);

  const runColumns = [
    {
      title: 'Timestamp',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (value: string) => formatDateTime(value),
    },
    {
      title: 'Regime',
      dataIndex: 'regime',
      key: 'regime',
      render: (value: string) => <RegimeTag regime={value} />,
    },
    {
      title: 'Signals',
      dataIndex: 'signals_generated',
      key: 'signals_generated',
      render: (value: number) => safeNumber(value),
    },
    {
      title: 'Orders',
      dataIndex: 'orders_submitted',
      key: 'orders_submitted',
      render: (value: number) => safeNumber(value),
    },
    {
      title: 'Errors',
      dataIndex: 'errors',
      key: 'errors',
      render: (errors: string[] | undefined) => {
        const count = Array.isArray(errors) ? errors.length : 0;
        return <Tag color={count === 0 ? 'success' : 'error'}>{count}</Tag>;
      },
    },
    {
      title: 'Duration (s)',
      dataIndex: 'duration_s',
      key: 'duration_s',
      render: (value: number) => safeNumber(value).toFixed(3),
    },
  ];

  const policyRows = Object.entries(policy).map(([key, value]) => ({
    key,
    metric: key,
    value: safeNumber(value),
  }));

  const brainRows = Object.entries(brain ?? {}).map(([key, value]) => ({
    key,
    field: key,
    value: typeof value === 'object' ? JSON.stringify(value) : String(value),
  }));

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (error) {
    const isNotEnabled = error.includes('not enabled');
    return (
      <div style={{ maxWidth: 640, margin: '48px auto' }}>
        <Alert
          message={isNotEnabled ? 'Living Organism — Not Activated' : 'Organism Unavailable'}
          description={
            isNotEnabled ? (
              <div>
                <p>The Living Organism subsystem is <strong>opt-in</strong> and currently disabled on the backend.</p>
                <p style={{ marginBottom: 4 }}>To activate it, add these to your <code>.env</code> and restart the server:</p>
                <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, fontSize: 13 }}>
{`ORGANISM_ENABLED=1
ENABLE_ORGANISM_SCHEDULER=1   # optional — starts the live tick loop`}
                </pre>
                <p style={{ marginTop: 8, marginBottom: 0, color: '#888' }}>
                  The backend also needs a running database session (<code>sessionmaker</code>) for governance &amp; promotion controllers.
                </p>
              </div>
            ) : (
              error
            )
          }
          type={isNotEnabled ? 'info' : 'warning'}
          showIcon
          action={<Button icon={<ReloadOutlined />} onClick={() => fetchAll(true)}>Retry</Button>}
        />
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>
          <ExperimentOutlined /> Living Organism
        </Title>
        <Button icon={<ReloadOutlined />} onClick={() => fetchAll(false)}>
          Refresh
        </Button>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={6}>
          <Card size="small">
            <Tooltip title="ACTIVE = trading normally. FROZEN = adaptation/evolution paused but still trading. HALTED = no trading.">
              <Statistic
                title="State"
                value={governance.halted ? 'HALTED' : governance.frozen ? 'FROZEN' : 'ACTIVE'}
                prefix={governance.halted ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              />
            </Tooltip>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Tooltip title="Governance policy version. Increments when circuit breakers or risk limits are updated.">
              <Statistic title="Policy Version" value={safeNumber(governance.policy_version)} prefix={<SafetyOutlined />} />
            </Tooltip>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Tooltip title="Total number of live ticks executed since engine started. Each tick fetches data, generates signals, and manages exits.">
              <Statistic title="Tick Count" value={safeNumber(status?.tick_count)} prefix={<ThunderboltOutlined />} />
            </Tooltip>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Tooltip title="Number of tick results stored in history (used for charts and analysis).">
              <Statistic title="Recorded Runs" value={runStats.total} prefix={<DashboardOutlined />} />
            </Tooltip>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Tooltip title="Number of symbols in the active trading universe. Scanner rotates symbols in/out based on fitness scores.">
              <Statistic title="Universe" value={universeData?.universe_size ?? 0} prefix={<GlobalOutlined />} />
            </Tooltip>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Tooltip title="Symbols identified by the scanner as potential rotation candidates (high tension score, volume, momentum).">
              <Statistic title="Scanner Candidates" value={scannerData?.candidate_count ?? 0} prefix={<RadarChartOutlined />} />
            </Tooltip>
          </Card>
        </Col>
      </Row>

      <Card title="Controls" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Button
            type={governance.frozen ? 'primary' : 'default'}
            onClick={() => handleAction(governance.frozen ? 'unfreeze' : 'freeze')}
            loading={actionLoading === 'freeze' || actionLoading === 'unfreeze'}
          >
            {governance.frozen ? 'Unfreeze Adaptation' : 'Freeze Adaptation'}
          </Button>
          <Button
            danger={!governance.halted}
            type={governance.halted ? 'primary' : 'default'}
            onClick={() => handleAction(governance.halted ? 'resume' : 'halt')}
            loading={actionLoading === 'halt' || actionLoading === 'resume'}
          >
            {governance.halted ? 'Resume Trading' : 'Halt Trading'}
          </Button>
          <Button onClick={() => handleAction('train')} loading={actionLoading === 'train'}>
            Trigger Training
          </Button>
          <Button onClick={() => handleAction('tick')} loading={actionLoading === 'tick'}>
            Trigger Live Tick
          </Button>
        </Space>
      </Card>

      <Tabs
        items={[
          {
            key: 'overview',
            label: 'Overview',
            children: (
              <Row gutter={[16, 16]}>
                {/* ── Broker Portfolio (single source of truth) ── */}
                <Col xs={24}>
                  <BrokerPortfolio />
                </Col>

                {/* ── Engine Performance & Health ── */}
                <Col xs={24} lg={14}>
                  <PerformanceSummary engine={engineStats} />
                </Col>
                <Col xs={24} lg={10}>
                  <SystemHealth engine={engineStats} runs={runs} />
                </Col>

                {/* ── Latest Run + Indicators ── */}
                <Col xs={24} lg={12}>
                  <Card title={<Tooltip title="Results from the most recent engine tick cycle">Latest Run</Tooltip>}>
                    <Descriptions column={1} size="small">
                      <Descriptions.Item label="Timestamp">{formatDateTime(latestTick?.timestamp)}</Descriptions.Item>
                      <Descriptions.Item label={<Tooltip title="Market regime detected from SPY analysis. Determines position sizing scale and max hold duration.">Regime</Tooltip>}><RegimeTag regime={latestTick?.regime || status?.regime?.last_regime} /></Descriptions.Item>
                      <Descriptions.Item label={<Tooltip title="Number of buy/sell signals generated by the alpha pipeline (ML + breakout + composite indicators)">Signals</Tooltip>}>{safeNumber(latestTick?.signals_generated)}</Descriptions.Item>
                      <Descriptions.Item label={<Tooltip title="Orders submitted to Alpaca broker this tick (after Kelly sizing, position limits, and cooldown filtering)">Orders</Tooltip>}>{safeNumber(latestTick?.orders_submitted)}</Descriptions.Item>
                      <Descriptions.Item label={<Tooltip title="Wall-clock time for this tick (data fetch + feature computation + signal generation + order management). Target: <2s">Duration</Tooltip>}>{safeNumber(latestTick?.duration_s).toFixed(3)}s</Descriptions.Item>
                      <Descriptions.Item label="Errors">
                        <Tag color={(latestTick?.errors?.length ?? 0) === 0 ? 'success' : 'error'}>
                          {(latestTick?.errors?.length ?? 0) === 0 ? 'none' : latestTick?.errors?.length}
                        </Tag>
                      </Descriptions.Item>
                    </Descriptions>
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card title={<Tooltip title="Compares recent 10 ticks vs previous 10 ticks to detect performance trends">Improvement Indicators</Tooltip>}>
                    <Descriptions column={1} size="small">
                      <Descriptions.Item label={<Tooltip title="% of last 10 ticks that completed with zero errors">Recent error-free rate</Tooltip>}>
                        <Progress percent={Math.round(runStats.errorFreeRate)} size="small" />
                      </Descriptions.Item>
                      <Descriptions.Item label={<Tooltip title="Average number of trading signals per tick (higher = more alpha opportunities detected)">Avg signals (recent 10)</Tooltip>}>
                        {runStats.avgSignalsRecent.toFixed(2)}
                      </Descriptions.Item>
                      <Descriptions.Item label={<Tooltip title="How much faster recent ticks are vs previous window. Positive = improving.">Duration improvement</Tooltip>}>
                        <Text type={runStats.durationImprovementPct >= 0 ? 'success' : 'danger'}>
                          {runStats.durationImprovementPct.toFixed(2)}%
                        </Text>
                      </Descriptions.Item>
                      <Descriptions.Item label={<Tooltip title="Average tick execution time over last 10 ticks">Avg duration (recent 10)</Tooltip>}>
                        {runStats.avgDurationRecent.toFixed(3)}s
                      </Descriptions.Item>
                    </Descriptions>
                  </Card>
                </Col>

                {/* ── Charts row ── */}
                <Col xs={24} lg={8}>
                  <LatencySparkline runs={runs} />
                </Col>
                <Col xs={24} lg={8}>
                  <EquityCurve runs={runs} />
                </Col>
                <Col xs={24} lg={8}>
                  <TrainingStatus latestTick={latestTick} />
                </Col>
                <Col xs={24}>
                  <SignalHeatMap runs={runs} />
                </Col>

                {/* ── Position Heatmap + P&L Waterfall ── */}
                <Col xs={24} lg={12}>
                  <PositionHeatmap />
                </Col>
                <Col xs={24} lg={12}>
                  <PnLWaterfall />
                </Col>

                {/* ── Regime Timeline ── */}
                <Col xs={24}>
                  <RegimeTimeline data={analyticsData?.regime_timeline ?? []} />
                </Col>
              </Row>
            ),
          },
          {
            key: 'decisions',
            label: (
              <span>
                <DashboardOutlined /> Decisions
              </span>
            ),
            children: <DecisionDashboard />,
          },
          {
            key: 'runs',
            label: 'Runs History',
            children: (
              <Card title="Recent Organism Runs">
                <Table
                  dataSource={runs.map((run, index) => ({ key: `${run.timestamp ?? index}-${index}`, ...run }))}
                  columns={runColumns}
                  pagination={{ pageSize: 20 }}
                  size="small"
                />
              </Card>
            ),
          },
          {
            key: 'activity',
            label: (
              <span>
                <ThunderboltOutlined /> Activity Feed{' '}
                <Badge count={activityFeed.length} overflowCount={999} style={{ backgroundColor: '#722ed1' }} />
              </span>
            ),
            children: (() => {
              const colorMap: Record<string, string> = {
                signal: 'blue', order: 'green', exit: 'orange',
                scanner: 'purple', retrain: 'cyan', regime: 'geekblue',
                skip: 'default', error: 'red',
              };
              const severityBorder: Record<string, string> = {
                error: '#ff4d4f', exit: '#fa8c16', order: '#52c41a',
                signal: '#1890ff', retrain: '#13c2c2',
              };
              const filteredFeed = activityFilter === 'all'
                ? activityFeed
                : activityFeed.filter((evt) => evt.type === activityFilter);

              return (
                <Card
                  title="Real-Time Activity Feed"
                  extra={
                    <Space>
                      <FilterOutlined />
                      <Select
                        size="small"
                        value={activityFilter}
                        onChange={setActivityFilter}
                        style={{ width: 130 }}
                        options={[
                          { value: 'all', label: 'All Events' },
                          { value: 'signal', label: 'Signals' },
                          { value: 'order', label: 'Orders' },
                          { value: 'exit', label: 'Exits' },
                          { value: 'retrain', label: 'Retraining' },
                          { value: 'scanner', label: 'Scanner' },
                          { value: 'regime', label: 'Regime' },
                          { value: 'skip', label: 'Skipped' },
                        ]}
                      />
                      <Button size="small" onClick={() => setActivityFeed([])}>Clear</Button>
                    </Space>
                  }
                >
                  {filteredFeed.length === 0 ? (
                    <Text type="secondary">
                      {activityFilter === 'all'
                        ? 'No activity yet. Events appear here as the organism ticks.'
                        : `No "${activityFilter}" events yet.`}
                    </Text>
                  ) : (
                    <div style={{ maxHeight: 600, overflowY: 'auto' }}>
                      {filteredFeed.map((evt, idx) => (
                        <div
                          key={`${evt.timestamp}-${idx}`}
                          style={{
                            padding: '6px 0',
                            borderBottom: '1px solid #f0f0f0',
                            borderLeft: `3px solid ${severityBorder[evt.type] ?? '#d9d9d9'}`,
                            paddingLeft: 8,
                          }}
                        >
                          <Space>
                            <Tag color={colorMap[evt.type] ?? 'default'}>{evt.type.toUpperCase()}</Tag>
                            {evt.symbol && <Tag>{evt.symbol}</Tag>}
                            <Text style={{ fontSize: 13 }}>{evt.message}</Text>
                            <Text type="secondary" style={{ fontSize: 11 }}>{formatDateTime(evt.timestamp)}</Text>
                          </Space>
                        </div>
                      ))}
                    </div>
                  )}
                </Card>
              );
            })(),
          },
          {
            key: 'orders',
            label: (
              <span>
                <DollarOutlined /> Orders
              </span>
            ),
            children: <OrganismOrdersPanel />,
          },
          {
            key: 'scanner',
            label: (
              <span>
                <RadarChartOutlined /> Scanner{' '}
                <Badge count={scannerData?.candidate_count ?? 0} overflowCount={999} style={{ backgroundColor: '#1890ff' }} />
              </span>
            ),
            children: <ScannerPanel scanner={scannerData} loading={loading} />,
          },
          {
            key: 'universe',
            label: (
              <span>
                <GlobalOutlined /> Universe{' '}
                <Badge count={universeData?.universe_size ?? 0} overflowCount={999} style={{ backgroundColor: '#52c41a' }} />
              </span>
            ),
            children: <UniversePanel universe={universeData} loading={loading} />,
          },
          {
            key: 'analytics',
            label: (
              <span>
                <ExperimentOutlined /> Analytics
              </span>
            ),
            children: (
              <AttributionPanel
                sectorExposure={analyticsData?.sector_exposure ?? []}
                confidenceDist={analyticsData?.confidence_distribution ?? []}
                regimeKellyStats={analyticsData?.regime_kelly_stats ?? {}}
              />
            ),
          },
          {
            key: 'learned',
            label: 'Learned State',
            children: (
              <Row gutter={[16, 16]}>
                <Col xs={24} lg={12}>
                  <Card title="Policy Weights">
                    <Table
                      dataSource={policyRows}
                      columns={[
                        { title: 'Metric', dataIndex: 'metric', key: 'metric' },
                        {
                          title: 'Weight',
                          dataIndex: 'value',
                          key: 'value',
                          render: (value: number) => value.toFixed(4),
                        },
                      ]}
                      pagination={false}
                      size="small"
                      locale={{ emptyText: 'No policy weights available from backend' }}
                    />
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card title="Brain Manifest">
                    <Table
                      dataSource={brainRows}
                      columns={[
                        { title: 'Field', dataIndex: 'field', key: 'field' },
                        { title: 'Value', dataIndex: 'value', key: 'value', ellipsis: true },
                      ]}
                      pagination={{ pageSize: 8 }}
                      size="small"
                      locale={{ emptyText: 'Brain details unavailable' }}
                    />
                  </Card>
                </Col>
                <Col xs={24}>
                  <Card title="Attribution Snapshot">
                    <Text type="secondary">
                      {attribution ? JSON.stringify(attribution).slice(0, 1500) : 'No attribution data available'}
                    </Text>
                  </Card>
                </Col>
              </Row>
            ),
          },
        ]}
      />
    </div>
  );
};

export default OrganismDashboard;
