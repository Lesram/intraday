/**
 * Portfolio Dashboard Page
 * Real-time portfolio overview with positions, P&L, performance metrics
 *
 * Uses the same usePortfolio() hook + portfolioStore as Dashboard,
 * ensuring consistent data across all views.
 */

import { useState } from 'react';
import { Card, Row, Col, Statistic, Table, Button, Space, Spin, Typography, Alert, Tooltip } from 'antd';
import {
  DollarOutlined, ArrowUpOutlined, ArrowDownOutlined,
  SyncOutlined, FundOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/services/api';
import { usePortfolio } from '@/hooks/useData';
import { usePortfolioStore, type Position } from '@/store/portfolioStore';

const { Title, Text } = Typography;

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
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Use the same hook as Dashboard for portfolio data (WebSocket-backed store)
  const { isLoading: portfolioLoading, error: portfolioError, refetch: refetchPortfolio } = usePortfolio();
  const portfolio = usePortfolioStore((state) => state.portfolio);

  // Performance metrics (separate endpoint, not available via WebSocket)
  const { data: performance } = useQuery<PerformanceMetrics>({
    queryKey: ['portfolio', 'performance'],
    queryFn: async () => {
      const res = await apiClient.get('/portfolio/performance');
      return res.data;
    },
    staleTime: 60000,
    refetchInterval: 60000,
  });

  const handleSync = async () => {
    setSyncing(true);
    try {
      await apiClient.post('/portfolio/sync');
      await refetchPortfolio();
      setError(null);
    } catch (err: any) {
      setError('Sync failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSyncing(false);
    }
  };

  if (portfolioLoading && !portfolio) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (portfolioError && !portfolio) {
    return (
      <div style={{ padding: 24 }}>
        <Alert message="Portfolio Error" description={String(portfolioError)} type="error" showIcon
          action={<Button onClick={() => refetchPortfolio()} icon={<ReloadOutlined />}>Retry</Button>}
        />
      </div>
    );
  }

  const positionColumns = [
    { title: 'Symbol', dataIndex: 'symbol', key: 'symbol', render: (v: string) => <Text strong>{v}</Text> },
    { title: 'Qty', dataIndex: 'quantity', key: 'quantity', render: (v: number) => (v ?? 0).toFixed(2) },
    { title: 'Avg Price', dataIndex: 'averagePrice', key: 'averagePrice', render: (v: number) => `$${(v ?? 0).toFixed(2)}` },
    { title: 'Current Price', dataIndex: 'currentPrice', key: 'currentPrice', render: (v: number) => `$${(v ?? 0).toFixed(2)}` },
    { title: 'Market Value', dataIndex: 'marketValue', key: 'marketValue', render: (v: number) => `$${(v ?? 0).toFixed(2)}` },
    {
      title: 'Unrealized P&L',
      dataIndex: 'unrealizedPnL',
      key: 'unrealizedPnL',
      render: (v: number, record: Position) => {
        const val = v ?? 0;
        const pct = record.unrealizedPnLPercent ?? 0;
        return (
          <div>
            <Text type={val >= 0 ? 'success' : 'danger'}>${val.toFixed(2)}</Text>
            <div style={{ fontSize: 11, color: '#888' }}>{pct >= 0 ? '+' : ''}{pct.toFixed(2)}%</div>
          </div>
        );
      },
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3}><FundOutlined /> Portfolio Dashboard</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => refetchPortfolio()}>Refresh</Button>
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
            <Tooltip title="Total account value including cash and positions (from Alpaca broker)">
              <Statistic
                title="Total Equity"
                value={portfolio?.totalEquity ?? 0}
                precision={2}
                prefix={<DollarOutlined />}
              />
            </Tooltip>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Tooltip title="Available cash not invested in positions">
              <Statistic
                title="Cash"
                value={portfolio?.cash ?? 0}
                precision={2}
                prefix="$"
              />
            </Tooltip>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Tooltip title="Total unrealized P&L across all open positions">
              <Statistic
                title="Total P&L"
                value={portfolio?.totalPnL ?? 0}
                precision={2}
                prefix={<DollarOutlined />}
                valueStyle={{ color: (portfolio?.totalPnL ?? 0) >= 0 ? '#3f8600' : '#cf1322' }}
                suffix={portfolio?.totalPnLPercent ? `(${portfolio.totalPnLPercent.toFixed(1)}%)` : ''}
              />
            </Tooltip>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Tooltip title="Profit/loss for today's trading session">
              <Statistic
                title="Day P&L"
                value={portfolio?.dayPnL ?? 0}
                precision={2}
                prefix={(portfolio?.dayPnL ?? 0) >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                valueStyle={{ color: (portfolio?.dayPnL ?? 0) >= 0 ? '#3f8600' : '#cf1322' }}
                suffix={portfolio?.dayPnLPercent ? `(${portfolio.dayPnLPercent.toFixed(1)}%)` : ''}
              />
            </Tooltip>
          </Card>
        </Col>
      </Row>

      {/* Performance Metrics */}
      {performance && (
        <Card title="Performance Metrics" style={{ marginBottom: 16 }}>
          <Row gutter={[16, 8]}>
            <Col span={4}>
              <Tooltip title="Cumulative return since inception">
                <Statistic title="Total Return" value={performance.total_return} precision={2} suffix="%" />
              </Tooltip>
            </Col>
            <Col span={4}>
              <Tooltip title="Risk-adjusted return (annualized excess return / volatility). >1.0 is good, >2.0 is excellent">
                <Statistic title="Sharpe" value={performance.sharpe_ratio} precision={3} />
              </Tooltip>
            </Col>
            <Col span={4}>
              <Tooltip title="Largest peak-to-trough decline in portfolio value">
                <Statistic title="Max Drawdown" value={performance.max_drawdown} precision={2} suffix="%" valueStyle={{ color: '#cf1322' }} />
              </Tooltip>
            </Col>
            <Col span={4}>
              <Tooltip title="Percentage of closed trades that were profitable">
                <Statistic title="Win Rate" value={performance.win_rate} precision={1} suffix="%" />
              </Tooltip>
            </Col>
            <Col span={4}>
              <Tooltip title="Gross profits / gross losses. >1.0 means profitable overall">
                <Statistic title="Profit Factor" value={performance.profit_factor} precision={2} />
              </Tooltip>
            </Col>
            <Col span={4}>
              <Tooltip title="Total number of completed (closed) trades">
                <Statistic title="Total Trades" value={performance.total_trades} />
              </Tooltip>
            </Col>
          </Row>
        </Card>
      )}

      {/* Positions Table */}
      <Card title={`Positions (${portfolio?.positions?.length ?? 0})`}>
        <Table
          dataSource={portfolio?.positions ?? []}
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
