/**
 * Strategy Detail
 * Detailed view of a single strategy with performance metrics and actions
 */

import React, { useEffect } from 'react';
import {
  Card,
  Row,
  Col,
  Button,
  Space,
  Typography,
  Descriptions,
  App,
  Popconfirm,
  Spin,
} from 'antd';
import {
  ArrowLeftOutlined,
  EditOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { strategiesService } from '@/services/strategiesService';
import { useStrategiesStore } from '@/store/strategiesStore';
import type { StrategyUpdateMessage } from '@/types/websocket';
import { useWebSocket } from '@/hooks/useWebSocket';
import { StrategyStatusBadge } from '@/components/strategies/StrategyStatusBadge';
import { StrategyPerformanceChart } from '@/components/strategies/StrategyPerformanceChart';
import { colors, fontSizes } from '@/styles/theme';

const { Title, Text } = Typography;

export const StrategyDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const updateStrategy = useStrategiesStore((state) => state.updateStrategy);

  // Fetch strategy details
  const {
    data: strategy,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['strategy', id],
    queryFn: () => strategiesService.getStrategy(id!),
    enabled: !!id,
  });

  // Update store when strategy data changes
  useEffect(() => {
    if (strategy) {
      updateStrategy(strategy.strategyId, strategy);
    }
  }, [strategy, updateStrategy]);

  // WebSocket handler for real-time strategy updates
  const handleStrategyUpdate = React.useCallback((wsMessage: StrategyUpdateMessage) => {
    // Only process updates for this specific strategy
    if (wsMessage.data.strategyId === id) {
      // Update local query cache
      queryClient.setQueryData(['strategy', id], wsMessage.data);
      
      // Update store
      updateStrategy(wsMessage.data.strategyId, wsMessage.data);
      
      // Show notification for status changes
      if (wsMessage.data.status === 'active') {
        message.success(`Strategy started`);
      } else if (wsMessage.data.status === 'paused') {
        message.info(`Strategy paused`);
      } else if (wsMessage.data.status === 'stopped') {
        message.info(`Strategy stopped`);
      } else if (wsMessage.data.status === 'error') {
        message.error(`Strategy encountered an error`);
      }
    }
  }, [id, updateStrategy, queryClient]);

  // Subscribe to strategy updates via WebSocket
  useWebSocket('strategies', handleStrategyUpdate);

  // Start strategy mutation
  const startMutation = useMutation({
    mutationFn: () => strategiesService.startStrategy(id!),
    onSuccess: (updatedStrategy) => {
      message.success(`Strategy "${updatedStrategy.name}" started successfully`);
      queryClient.invalidateQueries({ queryKey: ['strategy', id] });
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError?.response?.data?.detail || 'Failed to start strategy');
    },
  });

  // Pause strategy mutation
  const pauseMutation = useMutation({
    mutationFn: () => strategiesService.pauseStrategy(id!),
    onSuccess: (updatedStrategy) => {
      message.success(`Strategy "${updatedStrategy.name}" paused successfully`);
      queryClient.invalidateQueries({ queryKey: ['strategy', id] });
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError?.response?.data?.detail || 'Failed to pause strategy');
    },
  });

  // Stop strategy mutation
  const stopMutation = useMutation({
    mutationFn: () => strategiesService.stopStrategy(id!),
    onSuccess: (updatedStrategy) => {
      message.success(`Strategy "${updatedStrategy.name}" stopped successfully`);
      queryClient.invalidateQueries({ queryKey: ['strategy', id] });
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError?.response?.data?.detail || 'Failed to stop strategy');
    },
  });

  // Delete strategy mutation
  const deleteMutation = useMutation({
    mutationFn: () => strategiesService.deleteStrategy(id!),
    onSuccess: () => {
      message.success('Strategy deleted successfully');
      navigate('/strategies');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError?.response?.data?.detail || 'Failed to delete strategy');
    },
  });

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin size="large" spinning tip="Loading strategy...">
          <div style={{ minHeight: 200 }} />
        </Spin>
      </div>
    );
  }

  if (error || !strategy || !strategy.strategyId) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Text type="danger" style={{ fontSize: fontSizes.lg }}>
            Failed to load strategy. Please try again.
          </Text>
          <div style={{ marginTop: 16 }}>
            <Button onClick={() => navigate('/strategies')}>Back to Strategies</Button>
          </div>
        </div>
      </Card>
    );
  }

  const canStart = strategy?.status === 'stopped' || strategy?.status === 'paused';
  const canPause = strategy?.status === 'active';
  const canStop = strategy?.status === 'active' || strategy?.status === 'paused';
  const isLoading_actions =
    startMutation.isPending || pauseMutation.isPending || stopMutation.isPending || deleteMutation.isPending;

  return (
    <div>
      {/* Header */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <Space>
            <Button
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate('/strategies')}
            >
              Back
            </Button>
            <Title level={3} style={{ margin: 0 }}>
              {strategy?.name || 'Loading...'}
            </Title>
            <StrategyStatusBadge status={strategy?.status || 'stopped'} />
          </Space>
        </Col>
        <Col>
          <Space>
            {canStart && (
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={() => startMutation.mutate()}
                loading={isLoading_actions}
              >
                Start
              </Button>
            )}
            {canPause && (
              <Button
                icon={<PauseCircleOutlined />}
                onClick={() => pauseMutation.mutate()}
                loading={isLoading_actions}
              >
                Pause
              </Button>
            )}
            {canStop && (
              <Button
                danger
                icon={<StopOutlined />}
                onClick={() => stopMutation.mutate()}
                loading={isLoading_actions}
              >
                Stop
              </Button>
            )}
            <Button
              icon={<EditOutlined />}
              onClick={() => navigate(`/strategies/${id}/edit`)}
            >
              Edit
            </Button>
            <Button
              icon={<CopyOutlined />}
              onClick={() => {
                // Clone strategy by navigating to builder with strategy data pre-filled
                navigate('/strategies/builder', { 
                  state: { 
                    cloneFrom: strategy 
                  } 
                });
              }}
            >
              Clone
            </Button>
            <Popconfirm
              title="Delete Strategy"
              description="Are you sure you want to delete this strategy? This action cannot be undone."
              onConfirm={() => deleteMutation.mutate()}
              okText="Delete"
              cancelText="Cancel"
              okButtonProps={{ danger: true }}
            >
              <Button danger icon={<DeleteOutlined />} loading={isLoading_actions}>
                Delete
              </Button>
            </Popconfirm>
          </Space>
        </Col>
      </Row>

      {/* Strategy Details */}
      <Row gutter={[24, 24]}>
        <Col xs={24} lg={16}>
          <Card
            title="Strategy Information"
            style={{
              background: colors.backgrounds.secondary,
              borderColor: colors.backgrounds.border,
            }}
          >
            <Descriptions column={1} bordered>
              <Descriptions.Item label="Strategy ID">
                <Text copyable style={{ fontFamily: 'monospace' }}>
                  {strategy?.strategyId || 'N/A'}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="Name">{strategy?.name || 'N/A'}</Descriptions.Item>
              <Descriptions.Item label="Type">
                <Text style={{ textTransform: 'capitalize' }}>
                  {strategy?.strategyType || 'N/A'}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="Status">
                <StrategyStatusBadge status={strategy?.status || 'stopped'} />
              </Descriptions.Item>
              <Descriptions.Item label="Description">
                {strategy?.description || 'No description'}
              </Descriptions.Item>
              <Descriptions.Item label="Parameters">
                <pre
                  style={{
                    background: colors.backgrounds.tertiary,
                    padding: 12,
                    borderRadius: 4,
                    overflow: 'auto',
                    margin: 0,
                  }}
                >
                  {JSON.stringify(strategy.parameters, null, 2)}
                </pre>
              </Descriptions.Item>
              <Descriptions.Item label="Created">
                {new Date(strategy.createdAt).toLocaleString()}
              </Descriptions.Item>
              <Descriptions.Item label="Last Updated">
                {new Date(strategy.updatedAt).toLocaleString()}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card
            title="Quick Stats"
            style={{
              background: colors.backgrounds.secondary,
              borderColor: colors.backgrounds.border,
            }}
          >
            {strategy.performance ? (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <div>
                  <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
                    Total P&L
                  </Text>
                  <div>
                    <Text
                      strong
                      style={{
                        fontSize: fontSizes['2xl'],
                        color:
                          (strategy.performance.totalPnL ?? 0) >= 0
                            ? colors.semantic.profit
                            : colors.semantic.loss,
                      }}
                    >
                      ${(strategy.performance.totalPnL ?? 0).toFixed(2)}
                    </Text>
                  </div>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
                    Win Rate
                  </Text>
                  <div>
                    <Text strong style={{ fontSize: fontSizes.xl }}>
                      {((strategy.performance.winRate ?? 0) * 100).toFixed(1)}%
                    </Text>
                  </div>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
                    Total Trades
                  </Text>
                  <div>
                    <Text strong style={{ fontSize: fontSizes.xl }}>
                      {strategy.performance.totalTrades ?? 0}
                    </Text>
                  </div>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
                    Sharpe Ratio
                  </Text>
                  <div>
                    <Text
                      strong
                      style={{
                        fontSize: fontSizes.xl,
                        color:
                          (strategy.performance.sharpeRatio ?? 0) >= 1
                            ? colors.semantic.success
                            : colors.text.secondary,
                      }}
                    >
                      {(strategy.performance.sharpeRatio ?? 0).toFixed(2)}
                    </Text>
                  </div>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
                    Max Drawdown
                  </Text>
                  <div>
                    <Text
                      strong
                      style={{
                        fontSize: fontSizes.xl,
                        color: colors.semantic.loss,
                      }}
                    >
                      ${(strategy.performance.maxDrawdown ?? 0).toFixed(2)}
                    </Text>
                  </div>
                </div>
              </Space>
            ) : (
              <Text type="secondary">No performance data available yet.</Text>
            )}
          </Card>
        </Col>
      </Row>

      {/* Performance Chart */}
      {strategy.performance && (
        <div style={{ marginTop: 24 }}>
          <StrategyPerformanceChart
            performance={strategy.performance}
            strategyName={strategy.name}
          />
        </div>
      )}
    </div>
  );
};
