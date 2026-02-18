/**
 * Strategy Card
 * Reusable card component for displaying strategy information
 */

import React from 'react';
import { Card, Typography, Space, Row, Col, Button, Tooltip, Tag } from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  EditOutlined,
  DeleteOutlined,
  LineChartOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { Strategy } from '@/types/strategy';
import { StrategyStatusBadge } from './StrategyStatusBadge';
import { colors, fontSizes } from '@/styles/theme';
import { formatCurrency, formatNumber, formatPercent } from '@/utils/formatters';
import { getStrategyTypeConfig } from '@/utils/strategyTypeConfig';

const { Text, Title } = Typography;

interface StrategyCardProps {
  strategy: Strategy;
  onStart?: (strategyId: string) => void;
  onPause?: (strategyId: string) => void;
  onStop?: (strategyId: string) => void;
  onEdit?: (strategyId: string) => void;
  onDelete?: (strategyId: string) => void;
  loading?: boolean;
}

export const StrategyCard: React.FC<StrategyCardProps> = ({
  strategy,
  onStart,
  onPause,
  onStop,
  onEdit,
  onDelete,
  loading = false,
}) => {
  const navigate = useNavigate();
  const typeConfig = getStrategyTypeConfig(strategy.strategyType);
  const parameters = (strategy.parameters || {}) as Record<string, unknown>;
  const origin = typeof parameters._origin === 'string' ? parameters._origin : 'ui';
  const originTag = (() => {
    const normalized = origin.toLowerCase();
    if (normalized === 'optuna') return { label: 'Optuna', color: 'purple' };
    if (normalized === 'backend') return { label: 'Backend', color: 'geekblue' };
    return { label: 'UI', color: 'green' };
  })();

  const handleCardClick = (e: React.MouseEvent) => {
    // Only navigate if not clicking on a button
    if ((e.target as HTMLElement).closest('button')) {
      return;
    }
    navigate(`/strategies/${strategy.strategyId}`);
  };

  const canStart = strategy.status === 'stopped' || strategy.status === 'paused';
  const canPause = strategy.status === 'active';
  const canStop = strategy.status === 'active' || strategy.status === 'paused';

  return (
    <Card
      hoverable
      onClick={handleCardClick}
      style={{
        background: colors.backgrounds.secondary,
        borderColor: colors.backgrounds.border,
        cursor: 'pointer',
      }}
      styles={{
        body: { padding: 20 },
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space direction="vertical" size={4}>
              <Space>
                <span style={{ fontSize: '20px' }}>{typeConfig.icon}</span>
                <Title level={5} style={{ margin: 0, color: colors.text.primary }}>
                  {strategy.name}
                </Title>
              </Space>
              <Tooltip title={typeConfig.description}>
                <Text 
                  type="secondary" 
                  style={{ 
                    fontSize: fontSizes.sm,
                    color: typeConfig.color,
                    fontWeight: 500,
                    cursor: 'help',
                  }}
                >
                  {typeConfig.label}
                </Text>
              </Tooltip>
              <Tag color={originTag.color}>{originTag.label}</Tag>
            </Space>
          </Col>
          <Col>
            <StrategyStatusBadge status={strategy.status} />
          </Col>
        </Row>
      </div>

      {/* Description */}
      {strategy.description && (
        <div style={{ marginBottom: 16 }}>
          <Text
            type="secondary"
            style={{
              fontSize: fontSizes.sm,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {strategy.description}
          </Text>
        </div>
      )}

      {/* Performance Metrics */}
      {strategy.performance && (
        <div
          style={{
            marginBottom: 16,
            padding: 12,
            background: colors.backgrounds.tertiary,
            borderRadius: 8,
          }}
        >
          <Row gutter={[16, 8]}>
            <Col span={12}>
              <Space direction="vertical" size={0}>
                <Text type="secondary" style={{ fontSize: fontSizes.xs }}>
                  Total P&L
                </Text>
                <Text
                  strong
                  style={{
                    fontSize: fontSizes.lg,
                    color:
                      strategy.performance.totalPnL >= 0
                        ? colors.semantic.profit
                        : colors.semantic.loss,
                  }}
                >
                  {formatCurrency(strategy.performance.totalPnL)}
                </Text>
              </Space>
            </Col>
            <Col span={12}>
              <Space direction="vertical" size={0}>
                <Text type="secondary" style={{ fontSize: fontSizes.xs }}>
                  Win Rate
                </Text>
                <Text strong style={{ fontSize: fontSizes.lg }}>
                  {formatPercent(strategy.performance.winRate / 100)}
                </Text>
              </Space>
            </Col>
            <Col span={12}>
              <Space direction="vertical" size={0}>
                <Text type="secondary" style={{ fontSize: fontSizes.xs }}>
                  Total Trades
                </Text>
                <Text strong style={{ fontSize: fontSizes.base }}>
                  {formatNumber(strategy.performance.totalTrades)}
                </Text>
              </Space>
            </Col>
            <Col span={12}>
              <Space direction="vertical" size={0}>
                <Text type="secondary" style={{ fontSize: fontSizes.xs }}>
                  Sharpe Ratio
                </Text>
                <Text strong style={{ fontSize: fontSizes.base }}>
                  {strategy.performance.sharpeRatio?.toFixed(2) ?? 'N/A'}
                </Text>
              </Space>
            </Col>
          </Row>
        </div>
      )}

      {/* Actions */}
      <Row gutter={8}>
        <Col flex="auto">
          <Space size={8}>
            {canStart && onStart && (
              <Tooltip title="Start Strategy">
                <Button
                  type="primary"
                  size="small"
                  icon={<PlayCircleOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    onStart(strategy.strategyId);
                  }}
                  loading={loading}
                  disabled={loading}
                >
                  Start
                </Button>
              </Tooltip>
            )}
            {canPause && onPause && (
              <Tooltip title="Pause Strategy">
                <Button
                  size="small"
                  icon={<PauseCircleOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    onPause(strategy.strategyId);
                  }}
                  loading={loading}
                  disabled={loading}
                >
                  Pause
                </Button>
              </Tooltip>
            )}
            {canStop && onStop && (
              <Tooltip title="Stop Strategy">
                <Button
                  danger
                  size="small"
                  icon={<StopOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    onStop(strategy.strategyId);
                  }}
                  loading={loading}
                  disabled={loading}
                >
                  Stop
                </Button>
              </Tooltip>
            )}
          </Space>
        </Col>
        <Col>
          <Space size={8}>
            <Tooltip title="View Performance">
              <Button
                type="text"
                size="small"
                icon={<LineChartOutlined />}
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/strategies/${strategy.strategyId}`);
                }}
              />
            </Tooltip>
            {onEdit && (
              <Tooltip title="Edit Strategy">
                <Button
                  type="text"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    onEdit(strategy.strategyId);
                  }}
                />
              </Tooltip>
            )}
            {onDelete && (
              <Tooltip title="Delete Strategy">
                <Button
                  type="text"
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(strategy.strategyId);
                  }}
                />
              </Tooltip>
            )}
          </Space>
        </Col>
      </Row>
    </Card>
  );
};
