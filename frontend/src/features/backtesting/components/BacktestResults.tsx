/**
 * BacktestResults Component
 * 
 * Main component for displaying comprehensive backtest results.
 * Uses tabs to organize equity curve, metrics, trades, and monthly returns.
 */

import React from 'react';
import { Card, Tabs, Row, Col, Statistic, Tag, Space, Table, Empty } from 'antd';
import { 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import type { BacktestResult, MonthlyReturn } from '../../../types/backtest';
import { EquityCurveChart } from './EquityCurveChart';
import { MetricsTable } from './MetricsTable';
import { TradeLogTable } from './TradeLogTable';

interface BacktestResultsProps {
  result: BacktestResult;
}

export const BacktestResults: React.FC<BacktestResultsProps> = ({ result }) => {
  // Status badge
  const getStatusBadge = (status: string) => {
    const statusConfig = {
      completed: { color: 'success', icon: <CheckCircleOutlined />, text: 'Completed' },
      running: { color: 'processing', icon: <LoadingOutlined />, text: 'Running' },
      pending: { color: 'default', icon: <ClockCircleOutlined />, text: 'Pending' },
      failed: { color: 'error', icon: <CloseCircleOutlined />, text: 'Failed' },
    };

    const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.pending;
    
    return (
      <Tag color={config.color} icon={config.icon}>
        {config.text}
      </Tag>
    );
  };

  // Monthly returns table columns
  const monthlyReturnsColumns: ColumnsType<MonthlyReturn> = [
    {
      title: 'Month',
      dataIndex: 'month',
      key: 'month',
      render: (month: string) => dayjs(month).format('MMMM YYYY'),
    },
    {
      title: 'Return',
      dataIndex: 'return_pct',
      key: 'return_pct',
      align: 'right',
      sorter: (a, b) => a.return_pct - b.return_pct,
      render: (returnPct: number) => {
        const color = returnPct >= 0 ? '#52c41a' : '#ff4d4f';
        return (
          <span style={{ color, fontWeight: 600 }}>
            {returnPct >= 0 ? '+' : ''}{(returnPct * 100).toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: 'Trades',
      dataIndex: 'trades',
      key: 'trades',
      align: 'right',
      sorter: (a, b) => a.trades - b.trades,
    },
    {
      title: 'Winning',
      dataIndex: 'winning_trades',
      key: 'winning_trades',
      align: 'right',
      render: (winning: number) => (
        <span style={{ color: '#52c41a' }}>{winning}</span>
      ),
    },
    {
      title: 'Losing',
      dataIndex: 'losing_trades',
      key: 'losing_trades',
      align: 'right',
      render: (losing: number) => (
        <span style={{ color: '#ff4d4f' }}>{losing}</span>
      ),
    },
  ];

  // Tab items
  const tabItems = [
    {
      key: 'overview',
      label: 'Overview',
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          {/* Summary Stats */}
          <Card>
            <Row gutter={[16, 16]}>
              <Col xs={24} sm={12} md={6}>
                <Statistic
                  title="Initial Capital"
                  value={result.initial_capital}
                  precision={2}
                  prefix="$"
                />
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Statistic
                  title="Final Equity"
                  value={result.final_equity}
                  precision={2}
                  prefix="$"
                  valueStyle={{ 
                    color: result.final_equity >= result.initial_capital ? '#52c41a' : '#ff4d4f' 
                  }}
                />
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Statistic
                  title="Period"
                  value={`${dayjs(result.start_date).format('MMM DD, YYYY')} - ${dayjs(result.end_date).format('MMM DD, YYYY')}`}
                  valueStyle={{ fontSize: '16px' }}
                />
              </Col>
              <Col xs={24} sm={12} md={6}>
                <Statistic
                  title="Status"
                  value=""
                  formatter={() => getStatusBadge(result.status)}
                />
              </Col>
            </Row>
          </Card>

          {/* Equity Curve */}
          <EquityCurveChart
            equityCurve={result.equity_curve}
            initialCapital={result.initial_capital}
          />

          {/* Key Metrics Preview */}
          {result.metrics && (
            <Card title="Key Performance Indicators">
              <Row gutter={[16, 16]}>
                <Col xs={24} sm={12} md={6}>
                  <Statistic
                    title="Total Return"
                    value={result.metrics.total_return}
                    precision={2}
                    suffix="%"
                    valueStyle={{ 
                      color: result.metrics.total_return >= 0 ? '#52c41a' : '#ff4d4f' 
                    }}
                  />
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <Statistic
                    title="Sharpe Ratio"
                    value={result.metrics.sharpe_ratio}
                    precision={2}
                  />
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <Statistic
                    title="Max Drawdown"
                    value={result.metrics.max_drawdown}
                    precision={2}
                    suffix="%"
                    valueStyle={{ color: '#ff4d4f' }}
                  />
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <Statistic
                    title="Win Rate"
                    value={result.metrics.win_rate}
                    precision={2}
                    suffix="%"
                  />
                </Col>
              </Row>
            </Card>
          )}
        </Space>
      ),
    },
    {
      key: 'metrics',
      label: 'Detailed Metrics',
      children: <MetricsTable metrics={result.metrics} />,
    },
    {
      key: 'trades',
      label: `Trade Log (${result.trade_log.length})`,
      children: <TradeLogTable trades={result.trade_log} />,
    },
    {
      key: 'monthly',
      label: 'Monthly Returns',
      children: result.monthly_returns && result.monthly_returns.length > 0 ? (
        <Card title="Monthly Performance Breakdown">
          <Table
            columns={monthlyReturnsColumns}
            dataSource={result.monthly_returns}
            rowKey="month"
            pagination={{ pageSize: 12 }}
            size="small"
          />
        </Card>
      ) : (
        <Card>
          <Empty description="No monthly return data available" />
        </Card>
      ),
    },
  ];

  return (
    <div>
      {/* Header */}
      <Card style={{ marginBottom: 16 }}>
        <Row align="middle" justify="space-between">
          <Col>
            <Space direction="vertical" size={0}>
              <h2 style={{ margin: 0 }}>{result.strategy_name}</h2>
              <span style={{ color: '#8c8c8c' }}>
                Backtest ID: {result.id}
              </span>
            </Space>
          </Col>
          <Col>
            {getStatusBadge(result.status)}
          </Col>
        </Row>
      </Card>

      {/* Error Message */}
      {result.error_message && (
        <Card style={{ marginBottom: 16, borderColor: '#ff4d4f' }}>
          <Space>
            <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: '20px' }} />
            <div>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Error</div>
              <div style={{ color: '#8c8c8c' }}>{result.error_message}</div>
            </div>
          </Space>
        </Card>
      )}

      {/* Tabs */}
      <Tabs 
        defaultActiveKey="overview" 
        items={tabItems}
        size="large"
      />
    </div>
  );
};

export default BacktestResults;
