/**
 * Strategy Performance Chart
 * Displays strategy performance metrics with visual charts
 */

import React from 'react';
import { Card, Row, Col, Statistic, Typography, Space } from 'antd';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  TrophyOutlined,
  LineChartOutlined,
} from '@ant-design/icons';
import type { PerformanceMetrics } from '@/types/strategy';
import { colors, fontSizes } from '@/styles/theme';
import { formatCurrency, formatPercent } from '@/utils/formatters';

const { Title, Text } = Typography;

interface StrategyPerformanceChartProps {
  performance: PerformanceMetrics;
  strategyName?: string;
}

export const StrategyPerformanceChart: React.FC<StrategyPerformanceChartProps> = ({
  performance,
  strategyName,
}) => {
  const isProfitable = performance.totalPnL >= 0;
  const isGoodWinRate = performance.winRate >= 0.5;
  const isGoodSharpe = performance.sharpeRatio >= 1.0;

  return (
    <Card
      title={
        <Space>
          <LineChartOutlined />
          <span>Performance Metrics</span>
          {strategyName && <Text type="secondary">- {strategyName}</Text>}
        </Space>
      }
      style={{
        background: colors.backgrounds.secondary,
        borderColor: colors.backgrounds.border,
      }}
    >
      <Row gutter={[24, 24]}>
        {/* Total P&L */}
        <Col xs={24} sm={12} lg={6}>
          <Statistic
            title="Total P&L"
            value={performance.totalPnL}
            precision={2}
            valueStyle={{
              color: isProfitable ? colors.semantic.profit : colors.semantic.loss,
              fontSize: fontSizes['2xl'],
            }}
            prefix={isProfitable ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
            suffix="$"
          />
        </Col>

        {/* Win Rate */}
        <Col xs={24} sm={12} lg={6}>
          <Statistic
            title="Win Rate"
            value={performance.winRate * 100}
            precision={1}
            valueStyle={{
              color: isGoodWinRate ? colors.semantic.success : colors.semantic.warning,
              fontSize: fontSizes['2xl'],
            }}
            prefix={isGoodWinRate ? <TrophyOutlined /> : undefined}
            suffix="%"
          />
        </Col>

        {/* Total Trades */}
        <Col xs={24} sm={12} lg={6}>
          <Statistic
            title="Total Trades"
            value={performance.totalTrades}
            valueStyle={{
              color: colors.text.primary,
              fontSize: fontSizes['2xl'],
            }}
          />
        </Col>

        {/* Sharpe Ratio */}
        <Col xs={24} sm={12} lg={6}>
          <Statistic
            title="Sharpe Ratio"
            value={performance.sharpeRatio}
            precision={2}
            valueStyle={{
              color: isGoodSharpe ? colors.semantic.success : colors.text.secondary,
              fontSize: fontSizes['2xl'],
            }}
          />
        </Col>
      </Row>

      {/* Additional Metrics Row */}
      <Row
        gutter={[24, 24]}
        style={{
          marginTop: 24,
          paddingTop: 24,
          borderTop: `1px solid ${colors.backgrounds.border}`,
        }}
      >
        <Col xs={24} sm={12}>
          <Space direction="vertical" size={4}>
            <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
              Maximum Drawdown
            </Text>
            <Text
              strong
              style={{
                fontSize: fontSizes.xl,
                color: colors.semantic.loss,
              }}
            >
              {formatCurrency(performance.maxDrawdown)}
            </Text>
          </Space>
        </Col>

        <Col xs={24} sm={12}>
          <Space direction="vertical" size={4}>
            <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
              Average P&L per Trade
            </Text>
            <Text
              strong
              style={{
                fontSize: fontSizes.xl,
                color:
                  performance.totalTrades > 0 && performance.totalPnL >= 0
                    ? colors.semantic.profit
                    : colors.semantic.loss,
              }}
            >
              {performance.totalTrades > 0
                ? formatCurrency(performance.totalPnL / performance.totalTrades)
                : formatCurrency(0)}
            </Text>
          </Space>
        </Col>
      </Row>

      {/* Performance Summary */}
      <div
        style={{
          marginTop: 24,
          padding: 16,
          background: colors.backgrounds.tertiary,
          borderRadius: 8,
        }}
      >
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Title level={5} style={{ margin: 0 }}>
            Performance Summary
          </Title>
          <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
            {isProfitable ? (
              <>
                This strategy is <Text type="success">profitable</Text> with a total
                P&L of {formatCurrency(performance.totalPnL)}.
              </>
            ) : (
              <>
                This strategy is currently <Text type="danger">unprofitable</Text>{' '}
                with a total loss of {formatCurrency(Math.abs(performance.totalPnL))}.
              </>
            )}{' '}
            {isGoodWinRate ? (
              <>
                The win rate of {formatPercent(performance.winRate)} is{' '}
                <Text type="success">above average</Text>.
              </>
            ) : (
              <>
                The win rate of {formatPercent(performance.winRate)} could be{' '}
                <Text type="warning">improved</Text>.
              </>
            )}
          </Text>
          {isGoodSharpe ? (
            <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
              The Sharpe ratio of {performance.sharpeRatio.toFixed(2)} indicates{' '}
              <Text type="success">good risk-adjusted returns</Text>.
            </Text>
          ) : (
            <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
              The Sharpe ratio of {performance.sharpeRatio.toFixed(2)} suggests{' '}
              <Text type="warning">room for optimization</Text> in risk management.
            </Text>
          )}
        </Space>
      </div>
    </Card>
  );
};
