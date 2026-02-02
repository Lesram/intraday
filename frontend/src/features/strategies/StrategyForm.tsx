/**
 * Strategy Form
 * Form for creating and editing strategies
 */

import React, { useEffect } from 'react';
import {
  Form,
  Input,
  Select,
  Button,
  Card,
  Row,
  Col,
  Typography,
  Space,
  App,
  Spin,
} from 'antd';
import { ArrowLeftOutlined, SaveOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { strategiesService } from '@/services/strategiesService';
import type {
  CreateStrategyRequest,
  UpdateStrategyRequest,
} from '@/types/strategy';
import { colors, fontSizes } from '@/styles/theme';

const { Title, Text } = Typography;
const { TextArea } = Input;

type FormMode = 'create' | 'edit';

interface StrategyFormProps {
  mode?: FormMode;
}

export const StrategyForm: React.FC<StrategyFormProps> = ({ mode = 'create' }) => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const [form] = Form.useForm();

  const isEditMode = mode === 'edit' && !!id;

  // Fetch strategy for edit mode
  const {
    data: strategy,
    isLoading: isLoadingStrategy,
    error: loadError,
  } = useQuery({
    queryKey: ['strategy', id],
    queryFn: () => strategiesService.getStrategy(id!),
    enabled: isEditMode,
  });

  // Populate form in edit mode
  useEffect(() => {
    if (strategy && isEditMode) {
      form.setFieldsValue({
        name: strategy.name,
        description: strategy.description,
        strategyType: strategy.strategyType,
        symbols: strategy.symbols.join(', '),
        parameters: JSON.stringify(strategy.parameters, null, 2),
      });
    }
  }, [strategy, isEditMode, form]);

  // Create strategy mutation
  const createMutation = useMutation({
    mutationFn: (data: CreateStrategyRequest) =>
      strategiesService.createStrategy(data),
    onSuccess: (newStrategy) => {
      message.success(`Strategy "${newStrategy.name}" created successfully`);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      navigate(`/strategies/${newStrategy.strategyId}`);
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError?.response?.data?.detail || 'Failed to create strategy');
    },
  });

  // Update strategy mutation
  const updateMutation = useMutation({
    mutationFn: (data: UpdateStrategyRequest) =>
      strategiesService.updateStrategy(id!, data),
    onSuccess: (updatedStrategy) => {
      message.success(`Strategy "${updatedStrategy.name}" updated successfully`);
      queryClient.invalidateQueries({ queryKey: ['strategy', id] });
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      navigate(`/strategies/${updatedStrategy.strategyId}`);
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      message.error(axiosError?.response?.data?.detail || 'Failed to update strategy');
    },
  });

  const handleSubmit = (values: Record<string, unknown>) => {
    try {
      // Parse parameters JSON
      const parameters = values.parameters
        ? JSON.parse(values.parameters as string)
        : {};

      // Parse symbols (comma-separated string to array)
      const symbolsValue = values.symbols as string | undefined;
      const symbols = symbolsValue
        ? symbolsValue.split(',').map((s: string) => s.trim()).filter((s: string) => s.length > 0)
        : [];

      if (isEditMode) {
        // Update existing strategy
        const updateData: UpdateStrategyRequest = {
          name: values.name as string,
          description: values.description as string,
          strategyType: values.strategyType as UpdateStrategyRequest['strategyType'],
          symbols: symbols.length > 0 ? symbols : undefined,
          parameters,
        };
        updateMutation.mutate(updateData);
      } else {
        // Create new strategy
        const createData: CreateStrategyRequest = {
          name: values.name as string,
          description: values.description as string,
          strategyType: values.strategyType as CreateStrategyRequest['strategyType'],
          symbols,
          parameters,
        };
        createMutation.mutate(createData);
      }
    } catch (_error) {
      message.error('Invalid parameters JSON. Please check your input.');
    }
  };

  const isLoading = createMutation.isPending || updateMutation.isPending;

  if (isEditMode && isLoadingStrategy) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Spin size="large" tip="Loading strategy..." />
      </div>
    );
  }

  if (isEditMode && (loadError || !strategy)) {
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

  return (
    <div>
      {/* Header */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 24 }}>
        <Col>
          <Space>
            <Button
              icon={<ArrowLeftOutlined />}
              onClick={() =>
                navigate(isEditMode ? `/strategies/${id}` : '/strategies')
              }
            >
              Back
            </Button>
            <Title level={3} style={{ margin: 0 }}>
              {isEditMode ? 'Edit Strategy' : 'Create New Strategy'}
            </Title>
          </Space>
        </Col>
      </Row>

      {/* Form */}
      <Card
        style={{
          background: colors.backgrounds.secondary,
          borderColor: colors.backgrounds.border,
        }}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{
            strategyType: 'momentum',
            symbols: 'AAPL',
            parameters: JSON.stringify(
              {
                timeframe: '1D',
                indicators: ['SMA', 'RSI'],
                riskPerTrade: 0.02,
              },
              null,
              2
            ),
          }}
        >
          <Row gutter={24}>
            <Col xs={24} lg={12}>
              <Form.Item
                name="name"
                label="Strategy Name"
                rules={[
                  { required: true, message: 'Please enter a strategy name' },
                  { min: 3, message: 'Name must be at least 3 characters' },
                  { max: 100, message: 'Name must be less than 100 characters' },
                ]}
              >
                <Input
                  placeholder="e.g., Moving Average Crossover"
                  size="large"
                />
              </Form.Item>
            </Col>

            <Col xs={24} lg={12}>
              <Form.Item
                name="strategyType"
                label="Strategy Type"
                rules={[{ required: true, message: 'Please select a strategy type' }]}
              >
                <Select
                  size="large"
                  options={[
                    {
                      label: 'Technical',
                      value: 'technical',
                      title: 'Technical analysis trading strategy',
                    },
                    {
                      label: 'Fundamental',
                      value: 'fundamental',
                      title: 'Fundamental analysis trading strategy',
                    },
                    {
                      label: 'Quantitative',
                      value: 'quantitative',
                      title: 'Quantitative/mathematical trading strategy',
                    },
                    {
                      label: 'Hybrid',
                      value: 'hybrid',
                      title: 'Hybrid strategy combining multiple approaches',
                    },
                    {
                      label: 'Momentum',
                      value: 'momentum',
                      title: 'Momentum-based trading strategy',
                    },
                    {
                      label: 'Mean Reversion',
                      value: 'mean_reversion',
                      title: 'Mean reversion trading strategy',
                    },
                    {
                      label: 'Ensemble',
                      value: 'ensemble',
                      title: 'Ensemble model combining multiple strategies',
                    },
                    {
                      label: 'Statistical Arbitrage',
                      value: 'stat_arb',
                      title: 'Statistical arbitrage trading strategy',
                    },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="symbols"
            label="Trading Symbols"
            rules={[
              { required: true, message: 'Please enter at least one symbol' },
            ]}
            extra={
              <Text type="secondary" style={{ fontSize: fontSizes.xs }}>
                Enter stock symbols separated by commas (e.g., AAPL, MSFT, GOOGL)
              </Text>
            }
          >
            <Input
              placeholder="AAPL, MSFT, GOOGL"
              size="large"
            />
          </Form.Item>

          <Form.Item
            name="description"
            label="Description"
            rules={[
              { required: true, message: 'Please enter a description' },
              { min: 10, message: 'Description must be at least 10 characters' },
              { max: 500, message: 'Description must be less than 500 characters' },
            ]}
          >
            <TextArea
              rows={4}
              placeholder="Describe your strategy logic, entry/exit rules, and key parameters..."
              showCount
              maxLength={500}
            />
          </Form.Item>

          <Form.Item
            name="parameters"
            label="Parameters (JSON)"
            rules={[
              { required: true, message: 'Please enter strategy parameters' },
              {
                validator: (_, value) => {
                  if (!value) return Promise.resolve();
                  try {
                    JSON.parse(value);
                    return Promise.resolve();
                  } catch (_error) {
                    return Promise.reject('Invalid JSON format');
                  }
                },
              },
            ]}
            extra={
              <Text type="secondary" style={{ fontSize: fontSizes.xs }}>
                Enter strategy parameters as JSON. Example: timeframe, indicators,
                risk per trade, etc.
              </Text>
            }
          >
            <TextArea
              rows={10}
              placeholder='{\n  "timeframe": "1D",\n  "indicators": ["SMA", "RSI"],\n  "riskPerTrade": 0.02\n}'
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button
                type="primary"
                htmlType="submit"
                icon={<SaveOutlined />}
                size="large"
                loading={isLoading}
                disabled={isLoading}
              >
                {isEditMode ? 'Update Strategy' : 'Create Strategy'}
              </Button>
              <Button
                size="large"
                onClick={() =>
                  navigate(isEditMode ? `/strategies/${id}` : '/strategies')
                }
                disabled={isLoading}
              >
                Cancel
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      {/* Help Section */}
      <Card
        title="Strategy Parameters Help"
        style={{
          marginTop: 24,
          background: colors.backgrounds.secondary,
          borderColor: colors.backgrounds.border,
        }}
      >
        <Space direction="vertical" size={16}>
          <div>
            <Title level={5}>Common Parameters:</Title>
            <ul style={{ marginBottom: 0 }}>
              <li>
                <Text>
                  <strong>timeframe:</strong> Trading timeframe (e.g., "1m", "5m",
                  "1h", "1D")
                </Text>
              </li>
              <li>
                <Text>
                  <strong>indicators:</strong> List of technical indicators (e.g.,
                  ["SMA", "RSI", "MACD"])
                </Text>
              </li>
              <li>
                <Text>
                  <strong>riskPerTrade:</strong> Risk per trade as decimal (e.g.,
                  0.02 = 2%)
                </Text>
              </li>
              <li>
                <Text>
                  <strong>stopLoss:</strong> Stop loss percentage (e.g., 0.05 = 5%)
                </Text>
              </li>
              <li>
                <Text>
                  <strong>takeProfit:</strong> Take profit percentage (e.g., 0.10 =
                  10%)
                </Text>
              </li>
            </ul>
          </div>

          <div>
            <Title level={5}>Example Parameters:</Title>
            <pre
              style={{
                background: colors.backgrounds.tertiary,
                padding: 12,
                borderRadius: 4,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(
                {
                  timeframe: '1D',
                  indicators: ['SMA_20', 'SMA_50', 'RSI_14'],
                  entryRules: {
                    sma_crossover: true,
                    rsi_oversold: 30,
                  },
                  exitRules: {
                    sma_crossunder: true,
                    rsi_overbought: 70,
                  },
                  riskManagement: {
                    riskPerTrade: 0.02,
                    stopLoss: 0.05,
                    takeProfit: 0.10,
                    maxPositions: 5,
                  },
                },
                null,
                2
              )}
            </pre>
          </div>
        </Space>
      </Card>
    </div>
  );
};
