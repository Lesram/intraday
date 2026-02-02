/**
 * Risk Dashboard Component
 * Main interface for risk management monitoring with real-time updates
 */

import React, { useState, useCallback } from 'react';
import {
  Card,
  Row,
  Col,
  Typography,
  Alert,
  Space,
  Statistic,
  Badge,
  Button,
  Spin,
  message,
} from 'antd';
import {
  WarningOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  FireOutlined,
 } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useWebSocket, useWebSocketConnection } from '../../hooks/useWebSocket';
import type {
  RiskDashboardData,
  RiskMetric,
  RiskWebSocketEvent,
} from '../../types/risk';
import {
  RiskStatus,
  DEFAULT_REFRESH_INTERVAL,
} from '../../types/risk';
import { riskApi } from '../../services/riskApi';
import KillSwitchButton from './KillSwitchButton';
import RiskMetricCard from './RiskMetricCard';
import RiskViolationList from './RiskViolationList';
import './RiskDashboard.css';

const { Title, Text } = Typography;

interface RiskDashboardProps {
  className?: string;
  showKillSwitch?: boolean;
  autoRefresh?: boolean;
  refreshInterval?: number;
}

const RiskDashboard: React.FC<RiskDashboardProps> = ({
  className = '',
  showKillSwitch = true,
  autoRefresh = true,
  refreshInterval = DEFAULT_REFRESH_INTERVAL,
}) => {
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  // Fetch dashboard data
  const {
    data: dashboardData,
    isLoading,
    error,
    refetch,
  } = useQuery<RiskDashboardData>({
    queryKey: ['risk', 'dashboard'],
    queryFn: riskApi.getDashboard,
    refetchInterval: autoRefresh ? refreshInterval : false,
    staleTime: 1000, // 1 second
  });

  // WebSocket connection for real-time updates
  const { isConnected } = useWebSocketConnection();
  
  // Subscribe to risk updates
  useWebSocket('risk', handleWebSocketMessage);

  function handleWebSocketMessage(event: RiskWebSocketEvent) {
    setLastUpdate(new Date());
    
    switch (event.type) {
      case 'risk_metric_update':
        // Trigger a refetch to get updated data
        refetch();
        break;
      
      case 'risk_violation_alert':
        message.error({
          content: `Risk Violation: ${event.data.message}`,
          duration: 10,
          key: `violation-${event.data.id}`,
        });
        refetch();
        break;
      
      case 'emergency_stop_event':
        message.error({
          content: `Emergency Stop Triggered: ${event.data.reason}`,
          duration: 0, // Don't auto-close
          key: `emergency-${event.data.id}`,
        });
        refetch();
        break;
    }
  }

  const handleManualRefresh = useCallback(() => {
    refetch();
    setLastUpdate(new Date());
  }, [refetch]);

  const renderConnectionStatus = () => (
    <Space>
      <Badge status={isConnected ? 'success' : 'error'} />
      <Text type="secondary">
        {isConnected ? 'Real-time connected' : 'Offline mode'}
      </Text>
      <Text type="secondary" style={{ fontSize: '12px' }}>
        Last update: {lastUpdate.toLocaleTimeString()}
      </Text>
      <Button
        type="text"
        size="small"
        icon={<ReloadOutlined />}
        onClick={handleManualRefresh}
        loading={isLoading}
      >
        Refresh
      </Button>
    </Space>
  );

  const renderEmergencyAlert = () => {
    if (!dashboardData?.emergency_status || dashboardData.emergency_status.status === 'resolved') {
      return null;
    }

    return (
      <Alert
        type="error"
        showIcon
        icon={<FireOutlined />}
        message="EMERGENCY STOP ACTIVE"
        description={
          <div>
            <p><strong>Reason:</strong> {dashboardData.emergency_status.reason}</p>
            <p><strong>Triggered:</strong> {new Date(dashboardData.emergency_status.triggered_at).toLocaleString()}</p>
            <p>
              <strong>Actions taken:</strong> {dashboardData.emergency_status.strategies_stopped} strategies stopped, {' '}
              {dashboardData.emergency_status.orders_cancelled} orders cancelled
            </p>
          </div>
        }
        style={{ marginBottom: 16 }}
      />
    );
  };

  const renderSummaryCards = () => {
    if (!dashboardData) return null;

    const { summary } = dashboardData;

    return (
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="Total Metrics"
              value={summary.total_metrics}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="Warning"
              value={summary.warning_metrics}
              prefix={<WarningOutlined style={{ color: '#faad14' }} />}
              valueStyle={{ color: summary.warning_metrics > 0 ? '#faad14' : '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="Critical"
              value={summary.critical_metrics}
              prefix={<ExclamationCircleOutlined style={{ color: '#fa8c16' }} />}
              valueStyle={{ color: summary.critical_metrics > 0 ? '#fa8c16' : '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small">
            <Statistic
              title="Breached"
              value={summary.breached_metrics}
              prefix={<CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
              valueStyle={{ color: summary.breached_metrics > 0 ? '#ff4d4f' : '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>
    );
  };

  const renderRiskMetrics = () => {
    if (!dashboardData?.metrics.length) {
      return (
        <Card>
          <Text type="secondary">No risk metrics configured</Text>
        </Card>
      );
    }

    return (
      <Row gutter={[16, 16]}>
        {dashboardData.metrics.map((metric: RiskMetric) => (
          <Col key={metric.id} xs={24} sm={12} lg={8}>
            <RiskMetricCard metric={metric} showDetails />
          </Col>
        ))}
      </Row>
    );
  };

  const getOverallRiskLevel = (): { level: RiskStatus; color: string } => {
    if (!dashboardData) return { level: RiskStatus.NORMAL, color: '#52c41a' };

    const { summary } = dashboardData;
    
    if (summary.breached_metrics > 0) {
      return { level: RiskStatus.BREACHED, color: '#ff4d4f' };
    }
    if (summary.critical_metrics > 0) {
      return { level: RiskStatus.CRITICAL, color: '#fa8c16' };
    }
    if (summary.warning_metrics > 0) {
      return { level: RiskStatus.WARNING, color: '#faad14' };
    }
    
    return { level: RiskStatus.NORMAL, color: '#52c41a' };
  };

  if (error) {
    return (
      <div className={`risk-dashboard error ${className}`}>
        <Alert
          type="error"
          message="Failed to load risk dashboard"
          description={error.message}
          action={
            <Button size="small" danger onClick={() => refetch()}>
              Retry
            </Button>
          }
        />
      </div>
    );
  }

  const overallRisk = getOverallRiskLevel();

  return (
    <div className={`risk-dashboard ${className}`}>
      <Spin spinning={isLoading && !dashboardData}>
        {/* Header with Kill Switch */}
        <Card className="dashboard-header" style={{ marginBottom: 16 }}>
          <Row justify="space-between" align="middle">
            <Col>
              <Space direction="vertical" size="small">
                <Title level={3} style={{ margin: 0, color: overallRisk.color }}>
                  Risk Management Dashboard
                </Title>
                {renderConnectionStatus()}
              </Space>
            </Col>
            {showKillSwitch && (
              <Col>
                <KillSwitchButton size="large" />
              </Col>
            )}
          </Row>
        </Card>

        {/* Emergency Alert */}
        {renderEmergencyAlert()}

        {/* Summary Cards */}
        <div style={{ marginBottom: 24 }}>
          {renderSummaryCards()}
        </div>

        {/* Risk Metrics */}
        <Card
          title={
            <Space>
              <span>Risk Metrics</span>
              <Badge
                count={dashboardData?.metrics.length || 0}
                style={{ backgroundColor: overallRisk.color }}
              />
            </Space>
          }
          style={{ marginBottom: 24 }}
        >
          {renderRiskMetrics()}
        </Card>

        {/* Recent Violations */}
        <Card
          title={
            <Space>
              <span>Recent Violations</span>
              <Badge
                count={dashboardData?.recent_violations.length || 0}
                style={{ backgroundColor: '#ff4d4f' }}
              />
            </Space>
          }
        >
          <RiskViolationList
            violations={dashboardData?.recent_violations || []}
            showResolved={false}
          />
        </Card>
      </Spin>
    </div>
  );
};

export default RiskDashboard;