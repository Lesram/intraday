/**
 * Mobile Model Card Component
 * Card-based view for ML models on mobile devices
 * Replaces table view on small screens
 */

import React from 'react';
import { Card, Space, Tag, Button, Typography, Row, Col, Popconfirm, Progress } from 'antd';
import {
  EyeOutlined,
  DeleteOutlined,
  RocketOutlined,
  StopOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CalendarOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { ModelInfo } from '@/types/ml';
import { getModelStatusColor, formatAccuracy } from '@/services/mlApi';
import { colors } from '@/styles/theme';

const { Text, Title } = Typography;

interface MobileModelCardProps {
  model: ModelInfo;
  onViewDetails: (id: string) => void;
  onToggleActive: (id: string, active: boolean) => void;
  onDelete: (id: string) => void;
  isActivating?: boolean;
  isDeleting?: boolean;
}

/**
 * Mobile-optimized model card with large touch targets
 */
export const MobileModelCard: React.FC<MobileModelCardProps> = ({
  model,
  onViewDetails,
  onToggleActive,
  onDelete,
  isActivating,
  isDeleting,
}) => {
  const accuracy = model.metrics?.accuracy;
  const accuracyPercent = accuracy ? Math.round(accuracy * 100) : 0;

  return (
    <Card
      style={{
        marginBottom: 16,
        borderRadius: 12,
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)',
      }}
      styles={{ body: { padding: 16 } }}
    >
      {/* Header: Name + Status */}
      <div style={{ marginBottom: 12 }}>
        <Row justify="space-between" align="top">
          <Col flex="auto">
            <Title level={5} style={{ margin: 0, marginBottom: 4 }}>
              {model.name}
            </Title>
            <Space size={4}>
              <Tag color={getModelStatusColor(model.status)}>{model.status}</Tag>
              {model.active && (
                <Tag color="green" icon={<CheckCircleOutlined />}>
                  Active
                </Tag>
              )}
              <Text type="secondary" style={{ fontSize: 12 }}>
                v{model.version}
              </Text>
            </Space>
          </Col>
        </Row>
      </div>

      {/* Model Type Badge */}
      <div style={{ marginBottom: 12 }}>
        <Tag color="blue" style={{ fontSize: 13, padding: '4px 12px' }}>
          {model.model_type}
        </Tag>
      </div>

      {/* Metrics */}
      {accuracy !== undefined && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 8 }}>
            <Text strong>Accuracy</Text>
            <Text style={{ float: 'right', fontSize: 16, fontWeight: 600, color: colors.semantic.success }}>
              {formatAccuracy(accuracy)}
            </Text>
          </div>
          <Progress
            percent={accuracyPercent}
            strokeColor={{
              '0%': colors.semantic.error,
              '50%': colors.semantic.warning,
              '100%': colors.semantic.success,
            }}
            showInfo={false}
            size="small"
          />
        </div>
      )}

      {/* Additional Info */}
      <Space direction="vertical" size={8} style={{ width: '100%', marginBottom: 16 }}>
        <Row justify="space-between">
          <Col>
            <Space size={4}>
              <ClockCircleOutlined style={{ color: colors.text.tertiary, fontSize: 14 }} />
              <Text type="secondary" style={{ fontSize: 13 }}>
                Training Time
              </Text>
            </Space>
          </Col>
          <Col>
            <Text style={{ fontSize: 13 }}>
              {model.metrics?.training_time
                ? `${Math.round(model.metrics.training_time / 60)}m`
                : 'N/A'}
            </Text>
          </Col>
        </Row>

        <Row justify="space-between">
          <Col>
            <Space size={4}>
              <CalendarOutlined style={{ color: colors.text.tertiary, fontSize: 14 }} />
              <Text type="secondary" style={{ fontSize: 13 }}>
                Created
              </Text>
            </Space>
          </Col>
          <Col>
            <Text style={{ fontSize: 13 }}>
              {dayjs(model.created_at).format('MMM DD, YYYY')}
            </Text>
          </Col>
        </Row>

        {model.trained_at && (
          <Row justify="space-between">
            <Col>
              <Space size={4}>
                <CheckCircleOutlined style={{ color: colors.text.tertiary, fontSize: 14 }} />
                <Text type="secondary" style={{ fontSize: 13 }}>
                  Last Trained
                </Text>
              </Space>
            </Col>
            <Col>
              <Text style={{ fontSize: 13 }}>
                {dayjs(model.trained_at).format('MMM DD, YYYY')}
              </Text>
            </Col>
          </Row>
        )}
      </Space>

      {/* Actions - Large touch targets */}
      <Space style={{ width: '100%' }} size={8}>
        <Button
          type="primary"
          icon={<EyeOutlined />}
          onClick={() => onViewDetails(model.id)}
          size="large"
          block
          style={{ flex: 1 }}
        >
          View Details
        </Button>

        <Button
          icon={model.active ? <StopOutlined /> : <RocketOutlined />}
          onClick={() => onToggleActive(model.id, model.active)}
          loading={isActivating}
          size="large"
          style={{
            color: model.active ? colors.semantic.warning : colors.semantic.success,
            borderColor: model.active ? colors.semantic.warning : colors.semantic.success,
            minWidth: 48,
          }}
        />

        <Popconfirm
          title="Delete Model"
          description="Are you sure you want to delete this model?"
          onConfirm={() => onDelete(model.id)}
          okText="Yes"
          cancelText="No"
        >
          <Button
            danger
            icon={<DeleteOutlined />}
            loading={isDeleting}
            size="large"
            style={{ minWidth: 48 }}
          />
        </Popconfirm>
      </Space>
    </Card>
  );
};

/**
 * Grid layout for multiple mobile cards
 */
export const MobileModelCardGrid: React.FC<{
  models: ModelInfo[];
  onViewDetails: (id: string) => void;
  onToggleActive: (id: string, active: boolean) => void;
  onDelete: (id: string) => void;
  activatingId?: string;
  deletingId?: string;
}> = ({ models, onViewDetails, onToggleActive, onDelete, activatingId, deletingId }) => {
  return (
    <div style={{ padding: '0 8px' }}>
      {models.map((model) => (
        <MobileModelCard
          key={model.id}
          model={model}
          onViewDetails={onViewDetails}
          onToggleActive={onToggleActive}
          onDelete={onDelete}
          isActivating={activatingId === model.id}
          isDeleting={deletingId === model.id}
        />
      ))}
    </div>
  );
};

export default MobileModelCard;
