/**
 * Training Progress Monitor Component
 * Real-time display of model training progress
 * Phase 6 Day 4 Implementation
 */

import React, { useEffect } from 'react';
import {
  Card,
  Progress,
  Space,
  Typography,
  Row,
  Col,
  Statistic,
  Button,
  Tag,
  Divider,
  Empty,
  Spin,
  Alert,
  App,
} from 'antd';
import {
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import duration from 'dayjs/plugin/duration';
import relativeTime from 'dayjs/plugin/relativeTime';
import { mlApi, mlQueryKeys, mlQueryOptions } from '@/services/mlApi';
import { colors } from '@/styles/theme';

dayjs.extend(duration);
dayjs.extend(relativeTime);

const { Title, Text } = Typography;

export interface TrainingProgressMonitorProps {
  trainingId?: string;
}

/**
 * Training Progress Monitor Component
 * Displays real-time training status and metrics
 */
export const TrainingProgressMonitor: React.FC<TrainingProgressMonitorProps> = ({ trainingId }) => {
  const { message } = App.useApp();
  const queryClient = useQueryClient();

  // Fetch training status with auto-refresh
  const {
    data: progress,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: mlQueryKeys.trainingJob(trainingId || ''),
    queryFn: () => mlApi.getTrainingStatus(trainingId!),
    enabled: !!trainingId,
    ...mlQueryOptions.training, // 2s polling
  });

  // Cancel training mutation
  const cancelMutation = useMutation({
    mutationFn: (id: string) => mlApi.cancelTraining(id),
    onSuccess: () => {
      message.success('Training cancelled successfully');
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.trainingJob(trainingId || '') });
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.stats() });
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || 'Failed to cancel training');
    },
  });

  // Auto-stop polling when training completes
  useEffect(() => {
    if (progress && (progress.status === 'completed' || progress.status === 'failed' || progress.status === 'cancelled')) {
      queryClient.cancelQueries({ queryKey: mlQueryKeys.trainingJob(trainingId || '') });
    }
  }, [progress, trainingId, queryClient]);

  // Handle cancel
  const handleCancel = () => {
    if (trainingId) {
      cancelMutation.mutate(trainingId);
    }
  };

  // Get status color
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return colors.semantic.info;
      case 'completed':
        return colors.semantic.success;
      case 'failed':
        return colors.semantic.error;
      case 'cancelled':
        return colors.semantic.warning;
      default:
        return colors.text.tertiary;
    }
  };

  // Get status icon
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
      case 'pending':
        return <ClockCircleOutlined style={{ color: colors.semantic.info }} />;
      case 'completed':
        return <CheckCircleOutlined style={{ color: colors.semantic.success }} />;
      case 'failed':
        return <CloseCircleOutlined style={{ color: colors.semantic.error }} />;
      case 'cancelled':
        return <StopOutlined style={{ color: colors.semantic.warning }} />;
      default:
        return null;
    }
  };

  // Format ETA
  const formatETA = (seconds?: number) => {
    if (!seconds) return 'Calculating...';
    const dur = dayjs.duration(seconds, 'seconds');
    const hours = Math.floor(dur.asHours());
    const minutes = dur.minutes();
    const secs = dur.seconds();
    
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  };

  // No training ID
  if (!trainingId) {
    return (
      <Card>
        <Empty
          description="No training in progress"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        >
          <Text type="secondary">
            Start a new training job to see progress here
          </Text>
        </Empty>
      </Card>
    );
  }

  // Loading
  if (isLoading) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin size="large" />
          <div style={{ marginTop: 16 }}>
            <Text type="secondary">Loading training status...</Text>
          </div>
        </div>
      </Card>
    );
  }

  // Error
  if (error) {
    return (
      <Card>
        <Alert
          message="Failed to load training status"
          description={(error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Unknown error'}
          type="error"
          showIcon
          action={
            <Button size="small" onClick={() => refetch()}>
              Retry
            </Button>
          }
        />
      </Card>
    );
  }

  // No data
  if (!progress) {
    return (
      <Card>
        <Empty
          description="Training data not found"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Card>
    );
  }

  const isActive = progress.status === 'running' || progress.status === 'pending';
  const isCompleted = progress.status === 'completed';
  const isFailed = progress.status === 'failed';

  return (
    <Card>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Header */}
        <div>
          <Row justify="space-between" align="middle">
            <Col>
              <Space>
                <Title level={4} style={{ margin: 0, color: colors.text.primary }}>
                  {getStatusIcon(progress.status)}
                  <span style={{ marginLeft: 8 }}>Training Progress</span>
                </Title>
                <Tag color={getStatusColor(progress.status)}>
                  {progress.status.toUpperCase()}
                </Tag>
              </Space>
            </Col>
            <Col>
              <Space>
                <Button
                  icon={<ReloadOutlined />}
                  onClick={() => refetch()}
                  loading={isLoading}
                >
                  Refresh
                </Button>
                {isActive && (
                  <Button
                    danger
                    icon={<StopOutlined />}
                    onClick={handleCancel}
                    loading={cancelMutation.isPending}
                  >
                    Cancel Training
                  </Button>
                )}
              </Space>
            </Col>
          </Row>
        </div>

        {/* Training ID */}
        <div>
          <Text type="secondary">Training ID: </Text>
          <Text code>{progress.training_id}</Text>
        </div>

        {/* Progress Bar */}
        <div>
          <Progress
            percent={progress.progress * 100}
            status={isFailed ? 'exception' : isCompleted ? 'success' : 'active'}
            strokeColor={
              isFailed
                ? colors.semantic.error
                : isCompleted
                ? colors.semantic.success
                : colors.semantic.info
            }
            size="default"
          />
        </div>

        {/* Epoch Progress */}
        {progress.total_epochs && (
          <div>
            <Row gutter={16} align="middle">
              <Col>
                <ThunderboltOutlined style={{ color: colors.semantic.info, fontSize: 20 }} />
              </Col>
              <Col flex="auto">
                <Text strong>
                  Epoch {progress.current_epoch || 0} of {progress.total_epochs}
                </Text>
                <br />
                <Progress
                  percent={
                    progress.total_epochs
                      ? ((progress.current_epoch || 0) / progress.total_epochs) * 100
                      : 0
                  }
                  showInfo={false}
                  size={['100%', 8]}
                  strokeColor={colors.brand.primary}
                />
              </Col>
            </Row>
          </div>
        )}

        <Divider />

        {/* Statistics */}
        <Row gutter={[16, 16]}>
          {/* Started At */}
          <Col xs={24} sm={12} md={8}>
            <Statistic
              title="Started"
              value={dayjs(progress.started_at).format('MMM DD, HH:mm')}
              valueStyle={{ fontSize: 14 }}
            />
          </Col>

          {/* ETA */}
          {isActive && progress.eta_seconds && (
            <Col xs={24} sm={12} md={8}>
              <Statistic
                title="Estimated Time Remaining"
                value={formatETA(progress.eta_seconds)}
                valueStyle={{ fontSize: 14, color: colors.semantic.info }}
                prefix={<ClockCircleOutlined />}
              />
            </Col>
          )}

          {/* Completed At */}
          {isCompleted && (
            <Col xs={24} sm={12} md={8}>
              <Statistic
                title="Completed"
                value={dayjs(progress.started_at).fromNow()}
                valueStyle={{ fontSize: 14, color: colors.semantic.success }}
                prefix={<CheckCircleOutlined />}
              />
            </Col>
          )}
        </Row>

        {/* Current Metrics */}
        {progress.current_metrics && Object.keys(progress.current_metrics).length > 0 && (
          <>
            <Divider />
            <div>
              <Title level={5}>Current Metrics</Title>
              <Row gutter={[16, 16]}>
                {Object.entries(progress.current_metrics).map(([key, value]) => (
                  <Col key={key} xs={12} sm={8} md={6}>
                    <Statistic
                      title={key.replace(/_/g, ' ').toUpperCase()}
                      value={typeof value === 'number' ? value.toFixed(4) : value}
                      valueStyle={{ fontSize: 14 }}
                    />
                  </Col>
                ))}
              </Row>
            </div>
          </>
        )}

        {/* Message */}
        {progress.message && (
          <>
            <Divider />
            <Alert
              message={progress.message}
              type={isFailed ? 'error' : isCompleted ? 'success' : 'info'}
              showIcon
            />
          </>
        )}

        {/* Completion Message */}
        {isCompleted && (
          <Alert
            message="Training completed successfully!"
            description="Your model is now ready for predictions. Check the Model Registry for details."
            type="success"
            showIcon
          />
        )}
      </Space>
    </Card>
  );
};

export default TrainingProgressMonitor;
