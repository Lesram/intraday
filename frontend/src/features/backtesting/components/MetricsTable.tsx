/**
 * MetricsTable Component
 * 
 * Displays comprehensive performance metrics from a backtest in an organized grid layout.
 * Shows returns, risk metrics, trade statistics, and streaks.
 */

import React from 'react';
import { Card, Row, Col, Statistic, Divider, Empty, Spin, Tag } from 'antd';
import { 
  RiseOutlined, 
  FallOutlined,
  LineChartOutlined,
  DollarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import type { PerformanceMetrics } from '../../../types/backtest';

interface MetricsTableProps {
  metrics: PerformanceMetrics | null;
  loading?: boolean;
}

export const MetricsTable: React.FC<MetricsTableProps> = ({ metrics, loading = false }) => {
  if (loading) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <Spin size="large" />
        </div>
      </Card>
    );
  }

  if (!metrics) {
    return (
      <Card>
        <Empty description="No metrics data available" />
      </Card>
    );
  }

  // Helper to get color based on value
  const getValueColor = (value: number, inverse = false) => {
    if (value === 0) return undefined;
    const isPositive = inverse ? value < 0 : value > 0;
    return isPositive ? '#52c41a' : '#ff4d4f';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Returns Section */}
      <Card 
        title={
          <span>
            <RiseOutlined style={{ marginRight: 8 }} />
            Returns
          </span>
        }
      >
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Total Return"
              value={metrics.total_return}
              precision={2}
              suffix="%"
              valueStyle={{ color: getValueColor(metrics.total_return) }}
              prefix={metrics.total_return >= 0 ? <RiseOutlined /> : <FallOutlined />}
            />
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Annualized Return"
              value={metrics.annualized_return}
              precision={2}
              suffix="%"
              valueStyle={{ color: getValueColor(metrics.annualized_return) }}
            />
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Volatility (Ann.)"
              value={metrics.volatility}
              precision={2}
              suffix="%"
            />
          </Col>
        </Row>
      </Card>

      {/* Risk-Adjusted Metrics */}
      <Card
        title={
          <span>
            <LineChartOutlined style={{ marginRight: 8 }} />
            Risk-Adjusted Metrics
          </span>
        }
      >
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Sharpe Ratio"
              value={metrics.sharpe_ratio}
              precision={2}
              valueStyle={{ 
                color: metrics.sharpe_ratio > 1 ? '#52c41a' : 
                       metrics.sharpe_ratio > 0 ? '#faad14' : '#ff4d4f' 
              }}
            />
            <div style={{ fontSize: '12px', color: '#8c8c8c', marginTop: '4px' }}>
              {metrics.sharpe_ratio > 2 && <Tag color="green">Excellent</Tag>}
              {metrics.sharpe_ratio > 1 && metrics.sharpe_ratio <= 2 && <Tag color="blue">Good</Tag>}
              {metrics.sharpe_ratio > 0 && metrics.sharpe_ratio <= 1 && <Tag color="orange">Fair</Tag>}
              {metrics.sharpe_ratio <= 0 && <Tag color="red">Poor</Tag>}
            </div>
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Sortino Ratio"
              value={metrics.sortino_ratio}
              precision={2}
              valueStyle={{ 
                color: metrics.sortino_ratio > 1 ? '#52c41a' : 
                       metrics.sortino_ratio > 0 ? '#faad14' : '#ff4d4f' 
              }}
            />
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Calmar Ratio"
              value={metrics.calmar_ratio}
              precision={2}
              valueStyle={{ 
                color: metrics.calmar_ratio > 1 ? '#52c41a' : 
                       metrics.calmar_ratio > 0 ? '#faad14' : '#ff4d4f' 
              }}
            />
          </Col>
        </Row>

        {(metrics.alpha !== undefined || metrics.beta !== undefined) && (
          <>
            <Divider />
            <Row gutter={[16, 16]}>
              {metrics.alpha !== undefined && (
                <Col xs={24} sm={12} md={8}>
                  <Statistic
                    title="Alpha"
                    value={metrics.alpha}
                    precision={2}
                    suffix="%"
                    valueStyle={{ color: getValueColor(metrics.alpha) }}
                  />
                </Col>
              )}
              {metrics.beta !== undefined && (
                <Col xs={24} sm={12} md={8}>
                  <Statistic
                    title="Beta"
                    value={metrics.beta}
                    precision={2}
                  />
                </Col>
              )}
            </Row>
          </>
        )}
      </Card>

      {/* Risk Metrics */}
      <Card
        title={
          <span>
            <FallOutlined style={{ marginRight: 8 }} />
            Risk Metrics
          </span>
        }
      >
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Max Drawdown"
              value={metrics.max_drawdown}
              precision={2}
              suffix="%"
              valueStyle={{ color: getValueColor(metrics.max_drawdown, true) }}
              prefix={<FallOutlined />}
            />
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Max Drawdown Duration"
              value={metrics.max_drawdown_duration_days}
              suffix="days"
            />
          </Col>
        </Row>
      </Card>

      {/* Trade Statistics */}
      <Card
        title={
          <span>
            <DollarOutlined style={{ marginRight: 8 }} />
            Trade Statistics
          </span>
        }
      >
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={6}>
            <Statistic
              title="Total Trades"
              value={metrics.total_trades}
            />
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Statistic
              title="Win Rate"
              value={metrics.win_rate}
              precision={2}
              suffix="%"
              valueStyle={{ 
                color: metrics.win_rate >= 50 ? '#52c41a' : '#faad14' 
              }}
            />
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Statistic
              title="Winning Trades"
              value={metrics.winning_trades}
              valueStyle={{ color: '#52c41a' }}
            />
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Statistic
              title="Losing Trades"
              value={metrics.losing_trades}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Col>
        </Row>

        <Divider />

        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Profit Factor"
              value={metrics.profit_factor}
              precision={2}
              valueStyle={{ 
                color: metrics.profit_factor > 1 ? '#52c41a' : '#ff4d4f' 
              }}
            />
            <div style={{ fontSize: '12px', color: '#8c8c8c', marginTop: '4px' }}>
              {metrics.profit_factor > 2 && <Tag color="green">Excellent</Tag>}
              {metrics.profit_factor > 1 && metrics.profit_factor <= 2 && <Tag color="blue">Good</Tag>}
              {metrics.profit_factor <= 1 && <Tag color="red">Poor</Tag>}
            </div>
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Avg Trade P&L"
              value={metrics.avg_trade_pnl}
              precision={2}
              prefix="$"
              valueStyle={{ color: getValueColor(metrics.avg_trade_pnl) }}
            />
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Avg Trade Duration"
              value={metrics.avg_trade_duration_days}
              precision={1}
              suffix="days"
            />
          </Col>
        </Row>

        <Divider />

        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={6}>
            <Statistic
              title="Avg Win"
              value={metrics.avg_win}
              precision={2}
              prefix="$"
              valueStyle={{ color: '#52c41a' }}
            />
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Statistic
              title="Avg Loss"
              value={metrics.avg_loss}
              precision={2}
              prefix="$"
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Statistic
              title="Largest Win"
              value={metrics.largest_win}
              precision={2}
              prefix="$"
              valueStyle={{ color: '#52c41a' }}
            />
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Statistic
              title="Largest Loss"
              value={metrics.largest_loss}
              precision={2}
              prefix="$"
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Col>
        </Row>
      </Card>

      {/* Streaks & Other */}
      <Card
        title={
          <span>
            <ThunderboltOutlined style={{ marginRight: 8 }} />
            Streaks & Other
          </span>
        }
      >
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Max Consecutive Wins"
              value={metrics.max_consecutive_wins}
              valueStyle={{ color: '#52c41a' }}
            />
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Max Consecutive Losses"
              value={metrics.max_consecutive_losses}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Col>
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Total Commission"
              value={metrics.total_commission}
              precision={2}
              prefix="$"
            />
          </Col>
        </Row>
      </Card>
    </div>
  );
};

export default MetricsTable;
