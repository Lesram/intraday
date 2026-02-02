/**
 * Training Form Component
 * Form for starting new ML model training jobs
 * Phase 6 Day 4 Implementation
 */

import React from 'react';
import {
  Form,
  Input,
  Select,
  InputNumber,
  Button,
  Card,
  Space,
  Typography,
  Row,
  Col,
  Divider,
  Alert,
  Collapse,
  Switch,
  App,
} from 'antd';
import {
  RocketOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { mlApi, mlQueryKeys } from '@/services/mlApi';
import type { ModelTrainingRequest, ModelType } from '@/types/ml';
import { colors } from '@/styles/theme';

const { Title, Text } = Typography;
const { Option } = Select;
const { TextArea } = Input;

export interface TrainingFormProps {
  onTrainingStarted?: (trainingId: string) => void;
}

/**
 * Training Form Component
 * Comprehensive form for configuring and starting model training
 */
export const TrainingForm: React.FC<TrainingFormProps> = ({ onTrainingStarted }) => {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  const queryClient = useQueryClient();

  // Available model types
  const modelTypes = [
    { value: 'ensemble', label: 'Ensemble (Recommended)', description: 'Combines multiple models for best accuracy' },
    { value: 'lstm', label: 'LSTM', description: 'Neural network for time series' },
    { value: 'xgboost', label: 'XGBoost', description: 'Gradient boosting for tabular data' },
    { value: 'random_forest', label: 'Random Forest', description: 'Ensemble of decision trees' },
    { value: 'regression', label: 'Linear Regression', description: 'Simple linear model' },
    { value: 'classification', label: 'Classification', description: 'Binary classification model' },
  ];

  // Available symbols (in real app, fetch from API)
  const availableSymbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN', 'META', 'NVDA', 'SPY', 'QQQ'];

  // Available features (in real app, fetch from API)
  const availableFeatures = [
    'open', 'high', 'low', 'close', 'volume',
    'sma_20', 'sma_50', 'ema_12', 'ema_26',
    'rsi', 'macd', 'bb_upper', 'bb_lower',
    'atr', 'obv', 'vwap',
  ];

  // Start training mutation
  const startTrainingMutation = useMutation({
    mutationFn: (request: ModelTrainingRequest) => mlApi.startTraining(request),
    onSuccess: (response) => {
      message.success(`Training started successfully! Training ID: ${response.training_id}`);
      form.resetFields();
      
      // Invalidate queries
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.lists() });
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.stats() });
      
      // Notify parent
      if (onTrainingStarted) {
        onTrainingStarted(response.training_id);
      }
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: unknown } } };
      // Handle validation errors (422) - detail is an array of error objects
      if (axiosError.response?.data?.detail && Array.isArray(axiosError.response.data.detail)) {
        const errorMessages = axiosError.response.data.detail
          .map((err: unknown) => {
            const errObj = err as { message?: string; msg?: string };
            return errObj.message || errObj.msg || String(err);
          })
          .join(', ');
        message.error(errorMessages || 'Validation error occurred');
      } else if (typeof axiosError.response?.data?.detail === 'string') {
        message.error(axiosError.response.data.detail);
      } else {
        message.error('Failed to start training');
      }
    },
  });

  // Handle form submission
  const handleSubmit = async (values: Record<string, unknown>) => {
    try {
      const request: ModelTrainingRequest = {
        model_type: values.model_type as ModelType,
        model_name: values.model_name as string,
        features: (values.features as string[]) || [],
        symbols: (values.symbols as string[]) || [],
        lookback_days: (values.lookback_days as number) || 365,
        test_size: (values.test_size as number) || 0.2,
        hyperparameters: values.hyperparameters ? JSON.parse(values.hyperparameters as string) : undefined,
        retrain: (values.retrain as boolean) || false,
      };

      await startTrainingMutation.mutateAsync(request);
    } catch (_error) {
      // Error handled in mutation
    }
  };

  // Handle reset
  const handleReset = () => {
    form.resetFields();
  };

  return (
    <Card>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Header */}
        <div>
          <Title level={4} style={{ margin: 0, color: colors.text.primary }}>
            <RocketOutlined style={{ marginRight: 8 }} />
            Train New Model
          </Title>
          <Text type="secondary">
            Configure and start a new model training job
          </Text>
        </div>

        {/* Info Alert */}
        <Alert
          message="Training Time"
          description="Model training can take 5-30 minutes depending on data size and model complexity. You can monitor progress in real-time below."
          type="info"
          showIcon
        />

        {/* Form */}
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{
            model_type: 'ensemble',
            lookback_days: 365,
            test_size: 0.2,
            retrain: false,
          }}
          aria-label="ML model training configuration form"
        >
          <Row gutter={[16, 0]}>
            {/* Model Name */}
            <Col xs={24} md={12}>
              <Form.Item
                label="Model Name"
                name="model_name"
                rules={[
                  { required: true, message: 'Please enter a model name' },
                  { min: 3, message: 'Name must be at least 3 characters' },
                  { max: 50, message: 'Name must not exceed 50 characters' },
                  { pattern: /^[a-zA-Z0-9_-]+$/, message: 'Only letters, numbers, hyphens, and underscores allowed' },
                ]}
                tooltip="Unique identifier for your model"
              >
                <Input 
                  placeholder="e.g., ensemble_model_v1" 
                  aria-label="Model name"
                  aria-required="true"
                  aria-describedby="model-name-help"
                />
              </Form.Item>
              <span id="model-name-help" className="sr-only">
                Enter a unique name for your model. Use only letters, numbers, hyphens, and underscores.
              </span>
            </Col>

            {/* Model Type */}
            <Col xs={24} md={12}>
              <Form.Item
                label="Model Type"
                name="model_type"
                rules={[{ required: true, message: 'Please select a model type' }]}
                tooltip="Algorithm used for training"
              >
                <Select 
                  placeholder="Select model type"
                  aria-label="Model type"
                  aria-required="true"
                >
                  {modelTypes.map((type) => (
                    <Option key={type.value} value={type.value}>
                      <div>
                        <div>{type.label}</div>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {type.description}
                        </Text>
                      </div>
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>

            {/* Symbols */}
            <Col xs={24}>
              <Form.Item
                label="Symbols"
                name="symbols"
                rules={[{ required: true, message: 'Please select at least one symbol' }]}
                tooltip="Stock symbols to train on"
              >
                <Select
                  mode="multiple"
                  placeholder="Select symbols"
                  maxTagCount="responsive"
                  showSearch
                  aria-label="Stock symbols for training"
                  aria-required="true"
                >
                  {availableSymbols.map((symbol) => (
                    <Option key={symbol} value={symbol}>
                      {symbol}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>

            {/* Features */}
            <Col xs={24}>
              <Form.Item
                label="Features"
                name="features"
                tooltip="Technical indicators and price data to use"
              >
                <Select
                  mode="multiple"
                  placeholder="Select features (leave empty for auto-selection)"
                  maxTagCount="responsive"
                  showSearch
                >
                  {availableFeatures.map((feature) => (
                    <Option key={feature} value={feature}>
                      {feature}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>

            {/* Lookback Days */}
            <Col xs={24} md={12}>
              <Form.Item
                label="Lookback Days"
                name="lookback_days"
                rules={[
                  { required: true, message: 'Please enter lookback days' },
                  { type: 'number', min: 30, message: 'Minimum 30 days' },
                  { type: 'number', max: 1825, message: 'Maximum 5 years (1825 days)' },
                ]}
                tooltip="Number of historical days to use for training"
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={30}
                  max={1825}
                  placeholder="365"
                  addonAfter="days"
                />
              </Form.Item>
            </Col>

            {/* Test Size */}
            <Col xs={24} md={12}>
              <Form.Item
                label="Test Size"
                name="test_size"
                rules={[
                  { required: true, message: 'Please enter test size' },
                  { type: 'number', min: 0.1, message: 'Minimum 10%' },
                  { type: 'number', max: 0.5, message: 'Maximum 50%' },
                ]}
                tooltip="Percentage of data reserved for testing"
              >
                <InputNumber<number>
                  style={{ width: '100%' }}
                  min={0.1}
                  max={0.5}
                  step={0.05}
                  placeholder="0.2"
                  formatter={(value) => `${(Number(value) * 100).toFixed(0)}%`}
                  parser={(value) => {
                    const parsed = Number(value?.replace('%', '')) / 100;
                    return parsed || 0;
                  }}
                />
              </Form.Item>
            </Col>

            {/* Retrain Option */}
            <Col xs={24}>
              <Form.Item
                name="retrain"
                valuePropName="checked"
                tooltip="Retrain an existing model with new data"
              >
                <Space>
                  <Switch />
                  <Text>Retrain existing model (if name exists)</Text>
                </Space>
              </Form.Item>
            </Col>
          </Row>

          {/* Advanced Settings */}
          <Collapse
            ghost
            items={[
              {
                key: 'advanced',
                label: (
                  <Space>
                    <SettingOutlined />
                    <Text strong>Advanced Settings</Text>
                  </Space>
                ),
                children: (
                  <Form.Item
                    label="Hyperparameters (JSON)"
                    name="hyperparameters"
                    tooltip="Custom hyperparameters in JSON format"
                  >
                    <TextArea
                      rows={6}
                      placeholder={`{\n  "learning_rate": 0.001,\n  "batch_size": 32,\n  "epochs": 100\n}`}
                      style={{ fontFamily: 'monospace' }}
                    />
                  </Form.Item>
                ),
              },
            ]}
          />

          <Divider />

          {/* Action Buttons */}
          <Form.Item style={{ marginBottom: 0 }}>
            <Space>
              <Button
                type="primary"
                htmlType="submit"
                icon={<ThunderboltOutlined />}
                loading={startTrainingMutation.isPending}
                size="large"
              >
                Start Training
              </Button>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleReset}
                disabled={startTrainingMutation.isPending}
              >
                Reset
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Space>
    </Card>
  );
};

export default TrainingForm;
