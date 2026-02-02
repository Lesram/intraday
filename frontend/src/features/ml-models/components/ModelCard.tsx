/**
 * Model Card Component
 * Card view for displaying individual model summary
 * Phase 6 Implementation
 */

import React from 'react';
import { Card, Space, Typography, Tag, Button, Tooltip, Row, Col, Statistic } from 'antd';
import {
  EyeOutlined,
  RocketOutlined,
  StopOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { getModelStatusColor, formatAccuracy } from '@/services/mlApi';
import type { ModelInfo } from '@/types/ml';
import { colors } from '@/styles/theme';

dayjs.extend(relativeTime);

const { Title, Text } = Typography;

export interface ModelCardProps {
  model: ModelInfo;
  onActivate?: (modelId: string, active: boolean) => void;
  onView?: (modelId: string) => void;
  loading?: boolean;
}

/**
 * Model Card Component
 * Displays a summary card for a single ML model
 */
export const ModelCard: React.FC<ModelCardProps> = ({
  model,
  onActivate,
  onView,
  loading = false,
}) => {
  const navigate = useNavigate();

  // Handle view details
  const handleView = () => {
    if (onView) {
      onView(model.id);
    } else {
      navigate(`/ml-models/${model.id}`);
    }
  };

  // Handle activate/deactivate
  const handleToggleActive = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click
    if (onActivate) {
      onActivate(model.id, model.active);
    }
  };

  // Get status icon
  const getStatusIcon = () => {
    switch (model.status) {
      case 'ready':
        return <CheckCircleOutlined style={{ color: colors.semantic.success }} />;
      case 'training':
        return <ClockCircleOutlined style={{ color: colors.semantic.info }} />;
      case 'failed':
        return <WarningOutlined style={{ color: colors.semantic.error }} />;
      default:
        return null;
    }
  };

  // Calculate accuracy color
  const getAccuracyColor = (accuracy?: number) => {
    if (!accuracy) return colors.text.tertiary;
    if (accuracy >= 0.9) return colors.semantic.success;
    if (accuracy >= 0.7) return colors.semantic.warning;
    return colors.semantic.error;
  };

  return (
    <Card
      hoverable
      onClick={handleView}
      style={{ height: '100%' }}
      styles={{
        body: { padding: 20 },
      }}
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {/* Header */}
        <div>
          <Row justify="space-between" align="top">
            <Col>
              <Space direction="vertical" size={2}>
                <Title level={5} style={{ margin: 0, color: colors.text.primary }}>
                  {model.name}
                </Title>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  v{model.version}
                </Text>
              </Space>
            </Col>
            <Col>
              <Space>
                <Tag color={getModelStatusColor(model.status)}>
                  {model.status.toUpperCase()}
                </Tag>
                {model.active && (
                  <Tag color="success">ACTIVE</Tag>
                )}
              </Space>
            </Col>
          </Row>
        </div>

        {/* Model Type */}
        <div>
          <Tag color="blue" style={{ fontSize: 11 }}>
            {model.model_type.replace('_', ' ').toUpperCase()}
          </Tag>
        </div>

        {/* Metrics */}
        <Row gutter={16}>
          <Col span={8}>
            <Statistic
              title="Accuracy"
              value={model.metrics?.accuracy ? formatAccuracy(model.metrics.accuracy) : 'N/A'}
              valueStyle={{
                fontSize: 16,
                color: getAccuracyColor(model.metrics?.accuracy),
              }}
              suffix={
                model.metrics?.accuracy ? (
                  getStatusIcon()
                ) : null
              }
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="F1 Score"
              value={model.metrics?.f1_score ? formatAccuracy(model.metrics.f1_score) : 'N/A'}
              valueStyle={{ fontSize: 16, color: colors.text.secondary }}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="Predictions"
              value={model.prediction_count || 0}
              valueStyle={{ fontSize: 16, color: colors.text.secondary }}
            />
          </Col>
        </Row>

        {/* Additional Metrics */}
        {model.metrics && (
          <Row gutter={8}>
            {model.metrics.precision && (
              <Col span={8}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  Precision: <strong>{formatAccuracy(model.metrics.precision)}</strong>
                </Text>
              </Col>
            )}
            {model.metrics.recall && (
              <Col span={8}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  Recall: <strong>{formatAccuracy(model.metrics.recall)}</strong>
                </Text>
              </Col>
            )}
            {model.metrics.training_time && (
              <Col span={8}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  Training: <strong>{Math.round(model.metrics.training_time / 60)}m</strong>
                </Text>
              </Col>
            )}
          </Row>
        )}

        {/* Footer */}
        <div>
          <Row justify="space-between" align="middle">
            <Col>
              <Space direction="vertical" size={0}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  Trained {dayjs(model.trained_at).fromNow()}
                </Text>
                {model.features.length > 0 && (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {model.features.length} features
                  </Text>
                )}
              </Space>
            </Col>
            <Col>
              <Space size="small">
                <Tooltip title="View Details">
                  <Button
                    type="text"
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={handleView}
                  />
                </Tooltip>
                <Tooltip title={model.active ? 'Deactivate' : 'Activate'}>
                  <Button
                    type="text"
                    size="small"
                    icon={model.active ? <StopOutlined /> : <RocketOutlined />}
                    onClick={handleToggleActive}
                    loading={loading}
                    style={{
                      color: model.active ? colors.semantic.warning : colors.semantic.success,
                    }}
                  />
                </Tooltip>
              </Space>
            </Col>
          </Row>
        </div>
      </Space>
    </Card>
  );
};

export default ModelCard;
