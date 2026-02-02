/**
 * Risk Violation List Component
 * Displays list of risk violations with severity and resolution options
 */

import React from 'react';
import { List, Tag, Space, Typography, Button, Empty, Avatar } from 'antd';
import {
  WarningOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
  CheckOutlined,
} from '@ant-design/icons';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { RiskViolation } from '../../types/risk';
import { SEVERITY_CONFIGS } from '../../types/risk';
import { riskApi } from '../../services/riskApi';

const { Text } = Typography;

interface RiskViolationListProps {
  violations: RiskViolation[];
  className?: string;
  showResolved?: boolean;
  onResolve?: (violationId: string) => void;
}

const RiskViolationList: React.FC<RiskViolationListProps> = ({
  violations,
  className = '',
  showResolved = false,
  onResolve,
}) => {
  const queryClient = useQueryClient();

  const resolveViolationMutation = useMutation({
    mutationFn: (violationId: string) => riskApi.resolveViolation(violationId),
    onSuccess: (_, violationId) => {
      queryClient.invalidateQueries({ queryKey: ['risk'] });
      onResolve?.(violationId);
    },
  });

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'low':
        return <WarningOutlined style={{ color: SEVERITY_CONFIGS.low.color }} />;
      case 'medium':
        return <ExclamationCircleOutlined style={{ color: SEVERITY_CONFIGS.medium.color }} />;
      case 'high':
        return <ExclamationCircleOutlined style={{ color: SEVERITY_CONFIGS.high.color }} />;
      case 'critical':
        return <CloseCircleOutlined style={{ color: SEVERITY_CONFIGS.critical.color }} />;
      default:
        return <WarningOutlined />;
    }
  };

  const getViolationTypeColor = (type: string): string => {
    switch (type) {
      case 'warning':
        return 'orange';
      case 'breach':
        return 'red';
      default:
        return 'default';
    }
  };

  const formatMetricName = (name: string): string => {
    return name
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
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

  // Filter violations based on showResolved prop
  const filteredViolations = showResolved 
    ? violations 
    : violations.filter(v => !v.resolved);

  if (filteredViolations.length === 0) {
    return (
      <div className={className}>
        <Empty
          description={
            showResolved 
              ? "No risk violations found" 
              : "No unresolved risk violations"
          }
          style={{ padding: '40px 0' }}
        />
      </div>
    );
  }

  return (
    <div className={`risk-violation-list ${className}`}>
      <List
        dataSource={filteredViolations}
        renderItem={(violation) => (
          <List.Item
            key={violation.id}
            actions={[
              !violation.resolved && (
                <Button
                  type="link"
                  size="small"
                  icon={<CheckOutlined />}
                  loading={resolveViolationMutation.isPending}
                  onClick={() => resolveViolationMutation.mutate(violation.id)}
                >
                  Resolve
                </Button>
              ),
            ].filter(Boolean)}
          >
            <List.Item.Meta
              avatar={
                <Avatar
                  icon={getSeverityIcon(violation.severity)}
                  style={{
                    backgroundColor: SEVERITY_CONFIGS[violation.severity as keyof typeof SEVERITY_CONFIGS]?.color || '#d9d9d9',
                  }}
                />
              }
              title={
                <Space>
                  <span>{formatMetricName(violation.metric_name)}</span>
                  <Tag color={getViolationTypeColor(violation.violation_type)}>
                    {violation.violation_type.toUpperCase()}
                  </Tag>
                  <Tag color={SEVERITY_CONFIGS[violation.severity as keyof typeof SEVERITY_CONFIGS]?.color}>
                    {violation.severity.toUpperCase()}
                  </Tag>
                  {violation.resolved && (
                    <Tag color="green" icon={<CheckOutlined />}>
                      RESOLVED
                    </Tag>
                  )}
                </Space>
              }
              description={
                <div>
                  <div style={{ marginBottom: 8 }}>
                    <Text>{violation.message}</Text>
                  </div>
                  <Space split={<span>•</span>}>
                    <Text type="secondary">
                      Current: {formatValue(parseFloat(violation.current_value.toString()))}
                    </Text>
                    <Text type="secondary">
                      Limit: {formatValue(parseFloat(violation.limit_value.toString()))}
                    </Text>
                    <Text type="secondary">
                      {new Date(violation.created_at).toLocaleString()}
                    </Text>
                    {violation.resolved && violation.resolved_at && (
                      <Text type="secondary">
                        Resolved: {new Date(violation.resolved_at).toLocaleString()}
                      </Text>
                    )}
                  </Space>
                </div>
              }
            />
          </List.Item>
        )}
      />
    </div>
  );
};

export default RiskViolationList;