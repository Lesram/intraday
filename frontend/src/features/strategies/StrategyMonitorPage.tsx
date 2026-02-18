/**
 * Strategy Monitor Page
 * Unified view of strategy engine status, live signals, and strategy controls
 */

import { useState, useEffect, useCallback } from 'react';
import { Card, Row, Col, Table, Tag, Button, Space, Spin, Typography, Alert, Statistic, Badge, Tooltip, message } from 'antd';
import {
  ThunderboltOutlined, PlayCircleOutlined, PauseCircleOutlined,
  StopOutlined, ReloadOutlined, RadarChartOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { apiClient } from '@/services/api';

const { Title, Text } = Typography;

interface EngineStatus {
  status: string;
  active_strategies: number;
  last_update: string;
  features_processed: number;
  signals_generated: number;
}

interface Strategy {
  strategyId: string;
  name: string;
  strategyType: string;
  status: string;
  symbols: string[];
  performance: {
    totalTrades: number;
    winRate: number;
    totalPnL: number;
    sharpeRatio: number;
    maxDrawdown: number;
  };
  lastExecutedAt: string | null;
}

interface SignalEntry {
  symbol: string;
  action: string;
  confidence: number;
  tp_pct: number;
  sl_pct: number;
  reason?: string;
}

interface ExecutionMode {
  mode: string;
  source: string;
  overridden: boolean;
  alpaca_paper: boolean;
}

const WATCHLIST_SYMBOLS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'SPY', 'QQQ', 'IWM'];

const StrategyMonitorPage = () => {
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [signals, setSignals] = useState<Record<string, SignalEntry>>({});
  const [executionMode, setExecutionMode] = useState<ExecutionMode | null>(null);
  const [loading, setLoading] = useState(true);
  const [runningOnce, setRunningOnce] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const partialErrors: string[] = [];
      const [statusRes, strategiesRes, signalsRes] = await Promise.all([
        apiClient.get('/strategies/status').catch(() => { partialErrors.push('strategies/status'); return { data: null }; }),
        apiClient.get('/strategies/').catch(() => { partialErrors.push('strategies'); return { data: [] }; }),
        apiClient.get(`/signals/?symbols=${WATCHLIST_SYMBOLS.join(',')}`).catch(() => { partialErrors.push('signals'); return { data: { signals: {} } }; }),
      ]);

      setEngineStatus(statusRes.data);
      setStrategies(Array.isArray(strategiesRes.data) ? strategiesRes.data : []);
      setSignals(signalsRes.data?.signals || {});

      // Try execution mode (admin only)
      try {
        const modeRes = await apiClient.get('/admin/trading/execution-mode');
        setExecutionMode(modeRes.data);
      } catch {
        // Not admin, skip
      }

      if (partialErrors.length > 0) {
        setError(`Some data failed to load: ${partialErrors.join(', ')}`);
      } else {
        setError(null);
      }
    } catch (err: any) {
      setError('Failed to load strategy monitor data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 10000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleStrategyAction = async (strategyId: string, action: 'start' | 'stop' | 'pause') => {
    try {
      await apiClient.post(`/strategies/${strategyId}/${action}`);
      message.success(`Strategy ${action}ed`);
      await fetchAll();
    } catch (err: any) {
      message.error(err.response?.data?.detail || `Failed to ${action} strategy`);
    }
  };

  const handleRunOnce = async () => {
    setRunningOnce(true);
    try {
      const res = await apiClient.post('/multi-strategy-live/run-once');
      message.success(`Engine cycle complete: ${res.data.engine_signals_count} signals, ${res.data.submitted?.length ?? 0} orders`);
      await fetchAll();
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Engine run failed');
    } finally {
      setRunningOnce(false);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  const actionColors: Record<string, string> = {
    buy: 'green',
    sell: 'red',
    hold: 'default',
  };

  const strategyColumns = [
    { title: 'Name', dataIndex: 'name', key: 'name', render: (v: string) => <Text strong>{v}</Text> },
    { title: 'Type', dataIndex: 'strategyType', key: 'type', render: (v: string) => <Tag>{v}</Tag> },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => <Badge status={v === 'active' ? 'processing' : v === 'paused' ? 'warning' : 'default'} text={v.toUpperCase()} />,
    },
    { title: 'Symbols', dataIndex: 'symbols', key: 'symbols', render: (v: string[]) => v?.slice(0, 3).join(', ') + (v?.length > 3 ? ` +${v.length - 3}` : '') },
    { title: 'Win Rate', key: 'winRate', render: (_: any, r: Strategy) => `${((r.performance?.winRate ?? 0) * 100).toFixed(1)}%` },
    { title: 'P&L', key: 'pnl', render: (_: any, r: Strategy) => {
      const v = r.performance?.totalPnL ?? 0;
      return <Text type={v >= 0 ? 'success' : 'danger'}>${v.toFixed(2)}</Text>;
    }},
    { title: 'Trades', key: 'trades', render: (_: any, r: Strategy) => r.performance?.totalTrades ?? 0 },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, r: Strategy) => (
        <Space size="small">
          {r.status !== 'active' && (
            <Tooltip title="Start"><Button size="small" icon={<PlayCircleOutlined />} onClick={() => handleStrategyAction(r.strategyId, 'start')} /></Tooltip>
          )}
          {r.status === 'active' && (
            <Tooltip title="Pause"><Button size="small" icon={<PauseCircleOutlined />} onClick={() => handleStrategyAction(r.strategyId, 'pause')} /></Tooltip>
          )}
          {r.status !== 'stopped' && (
            <Tooltip title="Stop"><Button size="small" danger icon={<StopOutlined />} onClick={() => handleStrategyAction(r.strategyId, 'stop')} /></Tooltip>
          )}
        </Space>
      ),
    },
  ];

  const signalData = Object.entries(signals).map(([symbol, sig]) => ({
    key: symbol,
    symbol,
    action: sig.action || 'hold',
    confidence: sig.confidence || 0,
    tp_pct: sig.tp_pct,
    sl_pct: sig.sl_pct,
    reason: sig.reason,
  }));

  const signalColumns = [
    { title: 'Symbol', dataIndex: 'symbol', key: 'symbol', render: (v: string) => <Text strong>{v}</Text> },
    { title: 'Signal', dataIndex: 'action', key: 'action', render: (v: string) => <Tag color={actionColors[v] || 'default'}>{v.toUpperCase()}</Tag> },
    { title: 'Confidence', dataIndex: 'confidence', key: 'confidence', render: (v: number) => `${(v * 100).toFixed(0)}%` },
    { title: 'TP%', dataIndex: 'tp_pct', key: 'tp_pct', render: (v: number) => v ? `${v.toFixed(1)}%` : '-' },
    { title: 'SL%', dataIndex: 'sl_pct', key: 'sl_pct', render: (v: number) => v ? `${v.toFixed(1)}%` : '-' },
    { title: 'Reason', dataIndex: 'reason', key: 'reason', ellipsis: true },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3}><RadarChartOutlined /> Strategy Monitor</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchAll}>Refresh</Button>
          <Button type="primary" icon={<RocketOutlined />} onClick={handleRunOnce} loading={runningOnce}>
            Run Engine Cycle
          </Button>
        </Space>
      </div>

      {error && <Alert message={error} type="warning" showIcon closable style={{ marginBottom: 16 }} />}

      {/* Engine Status */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={5}>
          <Card size="small">
            <Statistic
              title="Engine"
              value={engineStatus?.status || 'unknown'}
              valueStyle={{ color: engineStatus?.status === 'operational' ? '#3f8600' : '#faad14' }}
              prefix={<ThunderboltOutlined />}
            />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic title="Active Strategies" value={engineStatus?.active_strategies ?? 0} />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic title="Signals Generated" value={engineStatus?.signals_generated ?? 0} />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic title="Features Processed" value={engineStatus?.features_processed ?? 0} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title="Execution Mode"
              value={executionMode?.mode || 'N/A'}
              valueStyle={{ color: executionMode?.mode === 'execute' ? '#cf1322' : executionMode?.mode === 'shadow' ? '#3f8600' : '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Live Signals */}
      <Card title="Live Signals" style={{ marginBottom: 16 }}>
        <Table
          dataSource={signalData}
          columns={signalColumns}
          pagination={false}
          size="small"
          locale={{ emptyText: 'No signals available. Run engine cycle to generate.' }}
        />
      </Card>

      {/* Strategies Table */}
      <Card title={`Strategies (${strategies.length})`}>
        <Table
          dataSource={strategies}
          columns={strategyColumns}
          rowKey="strategyId"
          pagination={false}
          size="small"
          locale={{ emptyText: 'No strategies configured' }}
        />
      </Card>
    </div>
  );
};

export default StrategyMonitorPage;
