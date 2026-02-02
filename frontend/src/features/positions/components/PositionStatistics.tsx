/**
 * Position Statistics Component
 * Displays aggregate position statistics in card format
 */

import React from 'react';
import { Card, Row, Col, Statistic } from 'antd';
import {
  RiseOutlined,
  FallOutlined,
  DollarOutlined,
  LineChartOutlined,
} from '@ant-design/icons';
import { usePositionStatistics } from '../hooks/usePositions';

export const PositionStatistics: React.FC = () => {
  const stats = usePositionStatistics();

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value);
  };

  const plColor = stats.totalUnrealizedPl >= 0 ? '#52c41a' : '#ff4d4f';
  const plPrefix = stats.totalUnrealizedPl >= 0 ? <RiseOutlined /> : <FallOutlined />;

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} sm={12} lg={6}>
        <Card>
          <Statistic
            title="Total Unrealized P&L"
            value={stats.totalUnrealizedPl}
            precision={2}
            valueStyle={{ color: plColor }}
            prefix={plPrefix}
            suffix="USD"
            formatter={(value) => formatCurrency(value as number)}
          />
        </Card>
      </Col>

      <Col xs={24} sm={12} lg={6}>
        <Card>
          <Statistic
            title="Open Positions"
            value={stats.openPositions}
            prefix={<LineChartOutlined />}
            suffix={`/ ${stats.totalPositions}`}
          />
        </Card>
      </Col>

      <Col xs={24} sm={12} lg={6}>
        <Card>
          <Statistic
            title="Total Market Value"
            value={stats.totalMarketValue}
            precision={2}
            prefix={<DollarOutlined />}
            formatter={(value) => formatCurrency(value as number)}
          />
        </Card>
      </Col>

      <Col xs={24} sm={12} lg={6}>
        <Card>
          <Statistic
            title="Win Rate"
            value={stats.winRate}
            precision={1}
            suffix="%"
            valueStyle={{
              color: stats.winRate >= 50 ? '#52c41a' : '#ff4d4f',
            }}
          />
          <div style={{ fontSize: '12px', color: '#8c8c8c', marginTop: '8px' }}>
            {stats.winningPositions} winning / {stats.losingPositions} losing
          </div>
        </Card>
      </Col>
    </Row>
  );
};
