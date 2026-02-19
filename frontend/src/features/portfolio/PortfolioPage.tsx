/**
 * Portfolio Dashboard Page
 * Real-time portfolio overview with positions, P&L, performance metrics
 */

import { useState, useEffect, useCallback } from 'react';
import { Card, Row, Col, Statistic, Table, Button, Space, Spin, Typography, Alert } from 'antd';
import {
  DollarOutlined, ArrowUpOutlined, ArrowDownOutlined,
  SyncOutlined, FundOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { apiClient } from '@/services/api';

const { Title, Text } = Typography;

interface PortfolioSummary {
  totalEquity: number;
  cash: number;
  buyingPower: number;
  marginUsed: number;
  totalPnL: number;
  totalPnLPercent: number;
  dayPnL: number;
  dayPnLPercent: number;
  positions: Position[];
}

interface Position {
  symbol: string;
  qty: string;
  avg_price: string;
  market_value: string;
  unrealized_pnl: string;
}

interface PerformanceMetrics {
  total_return: number;
  daily_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
}

const PortfolioPage = () => {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [performance, setPerformance] = useState<PerformanceMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [summaryRes, perfRes] = await Promise.all([
        apiClient.get('/portfolio/'),
        apiClient.get('/portfolio/performance'),
      ]);
      setSummary(summaryRes.data);
      setPerformance(perfRes.data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch portfolio data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // Refresh every 60s as backup — WebSocket provides real-time updates
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await apiClient.post('/portfolio/sync');
      await fetchData();
    } catch (err: any) {
      setError('Sync failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSyncing(false);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (error && !summary) {
    return (
      <div style={{ padding: 24 }}>
        <Alert message="Portfolio Error" description={error} type="error" showIcon
          action={<Button onClick={fetchData} icon={<ReloadOutlined />}>Retry</Button>}
        />
      </div>
    );
  }

  const positionColumns = [
    { title: 'Symbol', dataIndex: 'symbol', key: 'symbol', render: (v: string) => <Text strong>{v}</Text> },
    { title: 'Qty', dataIndex: 'qty', key: 'qty', render: (v: string) => parseFloat(v).toFixed(2) },
    { title: 'Avg Price', dataIndex: 'avg_price', key: 'avg_price', render: (v: string) => `$${parseFloat(v).toFixed(2)}` },
    { title: 'Market Value', dataIndex: 'market_value', key: 'market_value', render: (v: string) => `$${parseFloat(v).toFixed(2)}` },
    {
      title: 'Unrealized P&L',
      dataIndex: 'unrealized_pnl',
      key: 'unrealized_pnl',
      render: (v: string) => {
        const val = parseFloat(v);
        return <Text type={val >= 0 ? 'success' : 'danger'}>${val.toFixed(2)}</Text>;
      },
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3}><FundOutlined /> Portfolio Dashboard</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchData}>Refresh</Button>
          <Button type="primary" icon={<SyncOutlined spin={syncing} />} onClick={handleSync} loading={syncing}>
            Sync with Broker
          </Button>
        </Space>
      </div>

      {error && <Alert message={error} type="warning" showIcon closable style={{ marginBottom: 16 }} />}

      {/* Account Overview */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="Total Equity"
              value={summary?.totalEquity ?? 0}
              precision={2}
              prefix={<DollarOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Cash"
              value={summary?.cash ?? 0}
              precision={2}
              prefix="$"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Total P&L"
              value={summary?.totalPnL ?? 0}
              precision={2}
              prefix={<DollarOutlined />}
              valueStyle={{ color: (summary?.totalPnL ?? 0) >= 0 ? '#3f8600' : '#cf1322' }}
              suffix={summary?.totalPnLPercent ? `(${summary.totalPnLPercent.toFixed(1)}%)` : ''}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Day P&L"
              value={summary?.dayPnL ?? 0}
              precision={2}
              prefix={(summary?.dayPnL ?? 0) >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
              valueStyle={{ color: (summary?.dayPnL ?? 0) >= 0 ? '#3f8600' : '#cf1322' }}
              suffix={summary?.dayPnLPercent ? `(${summary.dayPnLPercent.toFixed(1)}%)` : ''}
            />
          </Card>
        </Col>
      </Row>

      {/* Performance Metrics */}
      {performance && (
        <Card title="Performance Metrics" style={{ marginBottom: 16 }}>
          <Row gutter={[16, 8]}>
            <Col span={4}><Statistic title="Total Return" value={performance.total_return} precision={2} suffix="%" /></Col>
            <Col span={4}><Statistic title="Sharpe" value={performance.sharpe_ratio} precision={3} /></Col>
            <Col span={4}><Statistic title="Max Drawdown" value={performance.max_drawdown} precision={2} suffix="%" valueStyle={{ color: '#cf1322' }} /></Col>
            <Col span={4}><Statistic title="Win Rate" value={performance.win_rate} precision={1} suffix="%" /></Col>
            <Col span={4}><Statistic title="Profit Factor" value={performance.profit_factor} precision={2} /></Col>
            <Col span={4}><Statistic title="Total Trades" value={performance.total_trades} /></Col>
          </Row>
        </Card>
      )}

      {/* Positions Table */}
      <Card title={`Positions (${summary?.positions?.length ?? 0})`}>
        <Table
          dataSource={summary?.positions ?? []}
          columns={positionColumns}
          rowKey="symbol"
          pagination={false}
          size="small"
          locale={{ emptyText: 'No open positions' }}
        />
      </Card>
    </div>
  );
};

export default PortfolioPage;
