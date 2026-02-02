/**
 * Risk Metric Card Component
 * Displays individual risk metric with status and progress
 */

import React from 'react';
import { Card, Progress, Typography, Space, Tag } from 'antd';
import {
  CheckCircleOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import type { RiskMetric } from '../../types/risk';
import { RISK_STATUS_CONFIGS } from '../../types/risk';

const { Text } = Typography;

interface RiskMetricCardProps {
  metric: RiskMetric;
  className?: string;
  showDetails?: boolean;
}

const RiskMetricCard: React.FC<RiskMetricCardProps> = ({
  metric,
  className = '',
  showDetails = false,
}) => {
  const statusConfig = RISK_STATUS_CONFIGS[metric.status];
  
  const getStatusIcon = () => {
    switch (metric.status) {
      case 'normal':
        return <CheckCircleOutlined style={{ color: statusConfig.color }} />;
      case 'warning':
        return <WarningOutlined style={{ color: statusConfig.color }} />;
      case 'critical':
        return <ExclamationCircleOutlined style={{ color: statusConfig.color }} />;
      case 'breached':
        return <CloseCircleOutlined style={{ color: statusConfig.color }} />;
      default:
        return <CheckCircleOutlined />;
    }
  };

  const getProgressStatus = (): 'success' | 'normal' | 'exception' => {
    switch (metric.status) {
      case 'normal':
        return 'success';
      case 'warning':
      case 'critical':
        return 'normal';
      case 'breached':
        return 'exception';
      default:
        return 'normal';
    }
  };

  const formatValue = (value: number): string => {
    if (value >= 1000000) {
      return `$${(value / 1000000).toFixed(2)}M`;
    }
    if (value >= 1000) {
      return `$${(value / 1000).toFixed(2)}K`;
    }
    return `$${value.toFixed(2)}`;
  };

  const formatMetricName = (name: string): string => {
    return name
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  return (
    <Card
      size="small"
      className={`risk-metric-card ${metric.status} ${className}`}
      title={
        <Space>
          {getStatusIcon()}
          <span>{formatMetricName(metric.metric_name)}</span>
        </Space>
      }
      extra={
        <Tag color={statusConfig.color} style={{ borderRadius: 12 }}>
          {metric.status.toUpperCase()}
        </Tag>
      }
    >
      <div style={{ marginBottom: 16 }}>
        <Progress
          percent={parseFloat(metric.percent_used.toString())}
          status={getProgressStatus()}
          strokeColor={statusConfig.color}
          trailColor="#f0f0f0"
          size="small"
        />
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text type="secondary">Current:</Text>
        <Text strong>{formatValue(parseFloat(metric.current_value.toString()))}</Text>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text type="secondary">Limit:</Text>
        <Text>{formatValue(parseFloat(metric.limit_value.toString()))}</Text>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text type="secondary">Usage:</Text>
        <Text style={{ color: statusConfig.color }}>
          {metric.percent_used.toString()}%
        </Text>
      </div>

      {showDetails && (
        <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #f0f0f0' }}>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            Last updated: {new Date(metric.last_updated).toLocaleString()}
          </Text>
        </div>
      )}
    </Card>
  );
};

export default RiskMetricCard;