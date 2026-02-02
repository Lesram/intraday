/**
 * Risk Limits Configuration Component
 * Admin interface for managing risk limits and thresholds
 */

import React, { useState } from 'react';
import {
  Card,
  Form,
  Input,
  InputNumber,
  Switch,
  Button,
  Table,
  Space,
  Typography,
  Modal,
  message,
  Popconfirm,
  Tag,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  SaveOutlined,

} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { RiskLimit, UpdateRiskLimitRequest } from '../../types/risk';
import { riskApi } from '../../services/riskApi';
import type { ColumnsType } from 'antd/es/table';

const { Title, Text } = Typography;


interface RiskLimitsConfigProps {
  className?: string;
  editable?: boolean;
  onSave?: (limits: RiskLimit[]) => void;
}

interface LimitFormData {
  limit_name: string;
  limit_value: number;
  warning_threshold: number;
  critical_threshold: number;
  enabled: boolean;
}

const RiskLimitsConfig: React.FC<RiskLimitsConfigProps> = ({
  className = '',
  editable = true,
  onSave,
}) => {
  const [form] = Form.useForm<LimitFormData>();
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingLimit, setEditingLimit] = useState<RiskLimit | null>(null);
  const queryClient = useQueryClient();

  // Fetch risk limits
  const {
    data: limits = [],
    isLoading,
    error,
  } = useQuery<RiskLimit[]>({
    queryKey: ['risk', 'limits'],
    queryFn: riskApi.getLimits,
  });

  // Create/Update risk limit mutation
  const updateLimitMutation = useMutation({
    mutationFn: (request: UpdateRiskLimitRequest) => riskApi.updateLimit(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['risk'] });
      message.success(
        editingLimit 
          ? 'Risk limit updated successfully' 
          : 'Risk limit created successfully'
      );
      handleCloseModal();
      onSave?.(queryClient.getQueryData(['risk', 'limits']) || []);
    },
    onError: (error: unknown) => {
      const errWithMessage = error as { message?: string };
      message.error(`Failed to save risk limit: ${errWithMessage.message || 'Unknown error'}`);
    },
  });

  // Delete risk limit mutation
  const deleteLimitMutation = useMutation({
    mutationFn: (limitId: string) => riskApi.deleteLimit(limitId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['risk'] });
      message.success('Risk limit deleted successfully');
      onSave?.(queryClient.getQueryData(['risk', 'limits']) || []);
    },
    onError: (error: unknown) => {
      const errWithMessage = error as { message?: string };
      message.error(`Failed to delete risk limit: ${errWithMessage.message || 'Unknown error'}`);
    },
  });

  const handleAddLimit = () => {
    form.resetFields();
    setEditingLimit(null);
    setShowAddModal(true);
  };

  const handleEditLimit = (limit: RiskLimit) => {
    form.setFieldsValue({
      limit_name: limit.limit_name,
      limit_value: parseFloat(limit.limit_value.toString()),
      warning_threshold: parseFloat(limit.warning_threshold.toString()),
      critical_threshold: parseFloat(limit.critical_threshold.toString()),
      enabled: limit.enabled,
    });
    setEditingLimit(limit);
    setShowAddModal(true);
  };

  const handleCloseModal = () => {
    setShowAddModal(false);
    setEditingLimit(null);
    form.resetFields();
  };

  const handleSubmit = async (values: LimitFormData) => {
    const request: UpdateRiskLimitRequest = {
      limit_name: values.limit_name,
      limit_value: values.limit_value,
      warning_threshold: values.warning_threshold,
      critical_threshold: values.critical_threshold,
      enabled: values.enabled,
    };

    updateLimitMutation.mutate(request);
  };

  const handleDeleteLimit = (limitId: string) => {
    deleteLimitMutation.mutate(limitId);
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

  const columns: ColumnsType<RiskLimit> = [
    {
      title: 'Limit Name',
      dataIndex: 'limit_name',
      key: 'limit_name',
      render: (name: string) => (
        <Text strong>{formatMetricName(name)}</Text>
      ),
    },
    {
      title: 'Limit Value',
      dataIndex: 'limit_value',
      key: 'limit_value',
      render: (value: number) => (
        <Text>{formatValue(value)}</Text>
      ),
    },
    {
      title: 'Warning Threshold',
      dataIndex: 'warning_threshold',
      key: 'warning_threshold',
      render: (threshold: number) => (
        <Tag color="orange">{threshold}%</Tag>
      ),
    },
    {
      title: 'Critical Threshold',
      dataIndex: 'critical_threshold',
      key: 'critical_threshold',
      render: (threshold: number) => (
        <Tag color="red">{threshold}%</Tag>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'green' : 'red'}>
          {enabled ? 'Enabled' : 'Disabled'}
        </Tag>
      ),
    },
    {
      title: 'Updated',
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (date: string) => (
        <Text type="secondary">
          {new Date(date).toLocaleDateString()}
        </Text>
      ),
    },
    ...(editable ? [{
      title: 'Actions',
      key: 'actions',
      render: (_: unknown, record: RiskLimit) => (
        <Space>
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEditLimit(record)}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete Risk Limit"
            description="Are you sure you want to delete this risk limit?"
            onConfirm={() => handleDeleteLimit(record.id)}
            okText="Delete"
            cancelText="Cancel"
            okButtonProps={{ danger: true }}
          >
            <Button
              type="text"
              size="small"
              icon={<DeleteOutlined />}
              danger
              loading={deleteLimitMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    }] : []),
  ];

  if (error) {
    return (
      <Card className={className}>
        <Text type="danger">Failed to load risk limits: {error.message}</Text>
      </Card>
    );
  }

  return (
    <div className={`risk-limits-config ${className}`}>
      <Card
        title={
          <Space>
            <Title level={4} style={{ margin: 0 }}>
              Risk Limits Configuration
            </Title>
            <Text type="secondary">({limits.length} limits)</Text>
          </Space>
        }
        extra={
          editable && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleAddLimit}
            >
              Add Limit
            </Button>
          )
        }
      >
        <Table
          columns={columns}
          dataSource={limits}
          rowKey="id"
          loading={isLoading}
          pagination={false}
          size="small"
        />
      </Card>

      {/* Add/Edit Modal */}
      <Modal
        title={editingLimit ? 'Edit Risk Limit' : 'Add Risk Limit'}
        open={showAddModal}
        onCancel={handleCloseModal}
        footer={null}
        width={600}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{
            warning_threshold: 80,
            critical_threshold: 95,
            enabled: true,
          }}
        >
          <Form.Item
            name="limit_name"
            label="Limit Name"
            rules={[
              { required: true, message: 'Please enter a limit name' },
              { min: 3, message: 'Limit name must be at least 3 characters' },
              { max: 50, message: 'Limit name must be less than 50 characters' },
            ]}
          >
            <Input
              placeholder="e.g., daily_loss_limit, position_size_limit"
              disabled={!!editingLimit}
            />
          </Form.Item>

          <Form.Item
            name="limit_value"
            label="Limit Value ($)"
            rules={[
              { required: true, message: 'Please enter a limit value' },
              { type: 'number', min: 0, message: 'Limit value must be positive' },
            ]}
          >
            <InputNumber
              style={{ width: '100%' }}
              placeholder="Enter limit value in dollars"
              min={0}
              step={1000}
              formatter={(value) => `$ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
              parser={(value) => parseFloat(value?.replace(/\$\s?|(,*)/g, '') || '0') as unknown as 0}
            />
          </Form.Item>

          <Form.Item
            name="warning_threshold"
            label="Warning Threshold (%)"
            rules={[
              { required: true, message: 'Please enter warning threshold' },
              { type: 'number', min: 0, max: 100, message: 'Must be between 0 and 100' },
            ]}
          >
            <InputNumber
              style={{ width: '100%' }}
              placeholder="Warning threshold percentage"
              min={0}
              max={100}
              step={5}
              formatter={(value) => `${value}%`}
              parser={(value) => parseFloat(value?.replace('%', '') || '0') as unknown as 0}
            />
          </Form.Item>

          <Form.Item
            name="critical_threshold"
            label="Critical Threshold (%)"
            rules={[
              { required: true, message: 'Please enter critical threshold' },
              { type: 'number', min: 0, max: 100, message: 'Must be between 0 and 100' },
            ]}
          >
            <InputNumber
              style={{ width: '100%' }}
              placeholder="Critical threshold percentage"
              min={0}
              max={100}
              step={5}
              formatter={(value) => `${value}%`}
              parser={(value) => parseFloat(value?.replace('%', '') || '0') as unknown as 0}
            />
          </Form.Item>

          <Form.Item
            name="enabled"
            label="Status"
            valuePropName="checked"
          >
            <Switch
              checkedChildren="Enabled"
              unCheckedChildren="Disabled"
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, marginTop: 24 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={handleCloseModal}>
                Cancel
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                icon={<SaveOutlined />}
                loading={updateLimitMutation.isPending}
              >
                {editingLimit ? 'Update Limit' : 'Create Limit'}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default RiskLimitsConfig;