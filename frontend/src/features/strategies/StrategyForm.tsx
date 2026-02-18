/**
 * Strategy Form
 * Form for creating and editing strategies
 */

import React, { useEffect, useState } from 'react';
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
  Switch,
  InputNumber,
  Divider,
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
  const [overlayEnabled, setOverlayEnabled] = useState(false);

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
      const params = strategy.parameters || {};
      const overlayPresent = Boolean(
        params.overlay_kill_switch ||
        params.overlay_vol_enabled ||
        params.overlay_gap_enabled ||
        params.overlay_risk_off_adjust
      );
      setOverlayEnabled(overlayPresent);
      form.setFieldsValue({
        name: strategy.name,
        description: strategy.description,
        strategyType: strategy.strategyType,
        symbols: strategy.symbols.join(', '),
        parameters: JSON.stringify(strategy.parameters, null, 2),
        overlayKillSwitch: Boolean(params.overlay_kill_switch ?? 0),
        overlayKillDdPct: Number(params.overlay_kill_dd_pct ?? 0.18),
        overlayKillCooldownDays: Number(params.overlay_kill_cooldown_days ?? 10),
        overlayKillForceExit: Boolean(params.overlay_kill_force_exit ?? 1),
        overlayVolEnabled: Boolean(params.overlay_vol_enabled ?? 0),
        overlayVolTarget: Number(params.overlay_vol_target ?? 0.18),
        overlayVolWindow: Number(params.overlay_vol_window ?? 20),
        overlayVolMinMult: Number(params.overlay_vol_min_mult ?? 0.5),
        overlayVolMaxMult: Number(params.overlay_vol_max_mult ?? 1.5),
        overlayGapEnabled: Boolean(params.overlay_gap_enabled ?? 0),
        overlayGapMaxPct: Number(params.overlay_gap_max_pct ?? 0.04),
        overlayRiskOffAdjust: Boolean(params.overlay_risk_off_adjust ?? 0),
        overlayRiskOffStopMult: Number(params.overlay_risk_off_stop_mult ?? 0.7),
        overlayRiskOffTakeMult: Number(params.overlay_risk_off_take_mult ?? 0.8),
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

      const overlayKeys = [
        'overlay_kill_switch',
        'overlay_kill_dd_pct',
        'overlay_kill_cooldown_days',
        'overlay_kill_force_exit',
        'overlay_vol_enabled',
        'overlay_vol_target',
        'overlay_vol_window',
        'overlay_vol_min_mult',
        'overlay_vol_max_mult',
        'overlay_gap_enabled',
        'overlay_gap_max_pct',
        'overlay_risk_off_adjust',
        'overlay_risk_off_stop_mult',
        'overlay_risk_off_take_mult',
      ];

      if (overlayEnabled) {
        parameters.overlay_kill_switch = Number(Boolean(values.overlayKillSwitch));
        parameters.overlay_kill_dd_pct = values.overlayKillDdPct;
        parameters.overlay_kill_cooldown_days = values.overlayKillCooldownDays;
        parameters.overlay_kill_force_exit = Number(Boolean(values.overlayKillForceExit));
        parameters.overlay_vol_enabled = Number(Boolean(values.overlayVolEnabled));
        parameters.overlay_vol_target = values.overlayVolTarget;
        parameters.overlay_vol_window = values.overlayVolWindow;
        parameters.overlay_vol_min_mult = values.overlayVolMinMult;
        parameters.overlay_vol_max_mult = values.overlayVolMaxMult;
        parameters.overlay_gap_enabled = Number(Boolean(values.overlayGapEnabled));
        parameters.overlay_gap_max_pct = values.overlayGapMaxPct;
        parameters.overlay_risk_off_adjust = Number(Boolean(values.overlayRiskOffAdjust));
        parameters.overlay_risk_off_stop_mult = values.overlayRiskOffStopMult;
        parameters.overlay_risk_off_take_mult = values.overlayRiskOffTakeMult;
      } else {
        overlayKeys.forEach((key) => {
          if (key in parameters) {
            delete parameters[key];
          }
        });
      }

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
            overlayKillDdPct: 0.18,
            overlayKillCooldownDays: 10,
            overlayKillForceExit: true,
            overlayVolTarget: 0.18,
            overlayVolWindow: 20,
            overlayVolMinMult: 0.5,
            overlayVolMaxMult: 1.5,
            overlayGapMaxPct: 0.04,
            overlayRiskOffStopMult: 0.7,
            overlayRiskOffTakeMult: 0.8,
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

          <Divider style={{ margin: '8px 0 12px' }} />

          <Form.Item label="Enable Risk Overlays" style={{ marginBottom: 8 }}>
            <Switch
              checked={overlayEnabled}
              onChange={setOverlayEnabled}
            />
          </Form.Item>

          {overlayEnabled && (
            <Card size="small" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item label="Kill Switch" name="overlayKillSwitch" valuePropName="checked">
                    <Switch />
                  </Form.Item>

                  <Form.Item
                    label="Kill DD % (decimal)"
                    name="overlayKillDdPct"
                    rules={[
                      { type: 'number', min: 0.05, max: 0.5, message: 'Must be between 5% and 50%' },
                    ]}
                  >
                    <InputNumber<number> style={{ width: '100%' }} min={0.05} max={0.5} step={0.01} />
                  </Form.Item>

                  <Form.Item
                    label="Kill Cooldown Days"
                    name="overlayKillCooldownDays"
                    rules={[
                      { type: 'number', min: 1, max: 30, message: 'Must be between 1 and 30 days' },
                    ]}
                  >
                    <InputNumber<number> style={{ width: '100%' }} min={1} max={30} step={1} />
                  </Form.Item>

                  <Form.Item label="Kill Force Exit" name="overlayKillForceExit" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Col>

                <Col xs={24} md={12}>
                  <Form.Item label="Vol Targeting" name="overlayVolEnabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>

                  <Form.Item
                    label="Vol Target (annualized)"
                    name="overlayVolTarget"
                    rules={[
                      { type: 'number', min: 0.05, max: 0.5, message: 'Must be between 5% and 50%' },
                    ]}
                  >
                    <InputNumber<number> style={{ width: '100%' }} min={0.05} max={0.5} step={0.01} />
                  </Form.Item>

                  <Form.Item
                    label="Vol Window"
                    name="overlayVolWindow"
                    rules={[
                      { type: 'number', min: 5, max: 60, message: 'Must be between 5 and 60 days' },
                    ]}
                  >
                    <InputNumber<number> style={{ width: '100%' }} min={5} max={60} step={1} />
                  </Form.Item>

                  <Form.Item
                    label="Vol Min Mult"
                    name="overlayVolMinMult"
                    dependencies={['overlayVolMaxMult']}
                    rules={[
                      { type: 'number', min: 0.1, max: 1.0, message: 'Must be between 0.1 and 1.0' },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          const max = getFieldValue('overlayVolMaxMult');
                          if (value === undefined || max === undefined || value <= max) {
                            return Promise.resolve();
                          }
                          return Promise.reject(new Error('Min multiplier cannot exceed max multiplier'));
                        },
                      }),
                    ]}
                  >
                    <InputNumber<number> style={{ width: '100%' }} min={0.1} max={1.0} step={0.1} />
                  </Form.Item>

                  <Form.Item
                    label="Vol Max Mult"
                    name="overlayVolMaxMult"
                    dependencies={['overlayVolMinMult']}
                    rules={[
                      { type: 'number', min: 1.0, max: 3.0, message: 'Must be between 1.0 and 3.0' },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          const min = getFieldValue('overlayVolMinMult');
                          if (value === undefined || min === undefined || value >= min) {
                            return Promise.resolve();
                          }
                          return Promise.reject(new Error('Max multiplier cannot be below min multiplier'));
                        },
                      }),
                    ]}
                  >
                    <InputNumber<number> style={{ width: '100%' }} min={1.0} max={3.0} step={0.1} />
                  </Form.Item>
                </Col>
              </Row>

              <Divider style={{ margin: '8px 0 12px' }} />

              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item label="Gap Guard" name="overlayGapEnabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>

                  <Form.Item
                    label="Max Gap % (decimal)"
                    name="overlayGapMaxPct"
                    rules={[
                      { type: 'number', min: 0.01, max: 0.15, message: 'Must be between 1% and 15%' },
                    ]}
                  >
                    <InputNumber<number> style={{ width: '100%' }} min={0.01} max={0.15} step={0.01} />
                  </Form.Item>
                </Col>

                <Col xs={24} md={12}>
                  <Form.Item label="Risk-Off Stop/TP Adjust" name="overlayRiskOffAdjust" valuePropName="checked">
                    <Switch />
                  </Form.Item>

                  <Form.Item
                    label="Risk-Off Stop Mult"
                    name="overlayRiskOffStopMult"
                    rules={[
                      { type: 'number', min: 0.3, max: 1.0, message: 'Must be between 0.3 and 1.0' },
                    ]}
                  >
                    <InputNumber<number> style={{ width: '100%' }} min={0.3} max={1.0} step={0.1} />
                  </Form.Item>

                  <Form.Item
                    label="Risk-Off Take Mult"
                    name="overlayRiskOffTakeMult"
                    rules={[
                      { type: 'number', min: 0.3, max: 1.0, message: 'Must be between 0.3 and 1.0' },
                    ]}
                  >
                    <InputNumber<number> style={{ width: '100%' }} min={0.3} max={1.0} step={0.1} />
                  </Form.Item>
                </Col>
              </Row>
            </Card>
          )}

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
