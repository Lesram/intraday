/**
 * Strategy Creation Wizard
 * Multi-step form for creating strategies with better UX
 */

import React, { useState } from 'react';
import {
  Steps,
  Card,
  Form,
  Input,
  Select,
  Button,
  Row,
  Col,
  Typography,
  Space,
  App,
  Divider,
  InputNumber,
  Tooltip,
  Tag,
} from 'antd';
import {
  ArrowLeftOutlined,
  InfoCircleOutlined,
  CheckCircleOutlined,
  RightOutlined,
  LeftOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { strategiesService } from '@/services/strategiesService';
import type { CreateStrategyRequest, Strategy } from '@/types/strategy';
import { colors, fontSizes } from '@/styles/theme';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { Step } = Steps;

// Strategy type definitions with descriptions and parameter templates
// NOTE: These must match backend VALID_STRATEGY_TYPES in strategy_service.py
const STRATEGY_TYPES = [
  // Implementation types (algorithmic approach)
  {
    value: 'momentum',
    label: 'Momentum',
    description: 'Capitalize on trend continuation with momentum indicators',
    icon: '🚀',
    defaultParams: {
      lookbackPeriod: 20,
      momentumThreshold: 0.05,
      stopLoss: 0.02,
      takeProfit: 0.06,
    },
  },
  {
    value: 'mean_reversion',
    label: 'Mean Reversion',
    description: 'Trade on the assumption that prices will revert to their mean',
    icon: '↩️',
    defaultParams: {
      lookbackPeriod: 50,
      zScoreEntry: 2.0,
      zScoreExit: 0.5,
      maxHoldingPeriod: 10,
    },
  },
  {
    value: 'ensemble',
    label: 'Ensemble Model',
    description: 'Combine predictions from multiple ML models',
    icon: '🤖',
    defaultParams: {
      models: ['lstm', 'random_forest', 'xgboost'],
      votingMethod: 'weighted',
      minAgreement: 0.7,
    },
  },
  {
    value: 'stat_arb',
    label: 'Statistical Arbitrage',
    description: 'Exploit statistical mispricing between correlated assets',
    icon: '⚖️',
    defaultParams: {
      pairSelection: 'cointegration',
      entryZScore: 2.0,
      exitZScore: 0.5,
      hedgeRatio: 'dynamic',
    },
  },
  // Classification types (trading philosophy)
  {
    value: 'technical',
    label: 'Technical Analysis',
    description: 'Trade based on chart patterns and technical indicators',
    icon: '📊',
    defaultParams: {
      indicators: ['RSI', 'MACD', 'BollingerBands'],
      chartPatterns: ['Head and Shoulders', 'Double Bottom'],
      timeframe: '1h',
      signalThreshold: 0.7,
    },
  },
  {
    value: 'fundamental',
    label: 'Fundamental Analysis',
    description: 'Trade based on company financials and valuations',
    icon: '📈',
    defaultParams: {
      metrics: ['P/E', 'P/B', 'ROE', 'Debt/Equity'],
      screenerCriteria: 'value',
      minMarketCap: 1000000000,
      rebalanceFrequency: 'quarterly',
    },
  },
  {
    value: 'quantitative',
    label: 'Quantitative',
    description: 'Trade using mathematical models and statistical methods',
    icon: '🔢',
    defaultParams: {
      modelType: 'regression',
      features: ['volume', 'volatility', 'momentum'],
      backtestPeriod: 252,
      confidenceLevel: 0.95,
    },
  },
  {
    value: 'hybrid',
    label: 'Hybrid Strategy',
    description: 'Combine multiple approaches (technical + fundamental + quant)',
    icon: '🎯',
    defaultParams: {
      technicalWeight: 0.4,
      fundamentalWeight: 0.3,
      quantitativeWeight: 0.3,
      rebalanceMethod: 'dynamic',
    },
  },
];

interface WizardData {
  // Step 1: Basic Info
  name?: string;
  description?: string;
  strategyType?: string;
  symbols?: string;
  
  // Step 2: Parameters
  parameters?: Record<string, unknown>;
  
  // Step 3: Risk Limits
  maxPositionSize?: number;
  maxDailyLoss?: number;
  maxDrawdown?: number;
  stopLossPercent?: number;
}

export const StrategyWizard: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [currentStep, setCurrentStep] = useState(0);
  const [selectedType, setSelectedType] = useState<string | undefined>(undefined);
  
  // Check if cloning from an existing strategy
  const cloneFrom = location.state?.cloneFrom as Strategy | undefined;
  
  // Initialize wizard data with cloned strategy if available
  const [wizardData, setWizardData] = useState<WizardData>(() => {
    if (cloneFrom) {
      const riskLimits = (cloneFrom.parameters?.riskLimits || {}) as {
        maxPositionSize?: number;
        maxDailyLoss?: number;
        maxDrawdown?: number;
        stopLossPercent?: number;
      };
      return {
        name: `${cloneFrom.name} (Copy)`,
        description: cloneFrom.description,
        strategyType: cloneFrom.strategyType,
        symbols: cloneFrom.symbols.join(', '),
        parameters: cloneFrom.parameters,
        maxPositionSize: riskLimits.maxPositionSize || 10000,
        maxDailyLoss: riskLimits.maxDailyLoss || 1000,
        maxDrawdown: riskLimits.maxDrawdown || 15,
        stopLossPercent: riskLimits.stopLossPercent || 2,
      };
    }
    return {};
  });

  // Initialize selectedType from cloned strategy
  React.useEffect(() => {
    if (cloneFrom?.strategyType) {
      setSelectedType(cloneFrom.strategyType);
    }
  }, [cloneFrom]);

  // Create strategy mutation
  const createMutation = useMutation({
    mutationFn: (data: CreateStrategyRequest) => {
      return strategiesService.createStrategy(data);
    },
    onSuccess: (newStrategy) => {
      message.success({
        content: `Strategy "${newStrategy.name}" created successfully! 🎉`,
        duration: 3,
      });
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      navigate(`/strategies/${newStrategy.strategyId}`);
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { detail?: string } } };
      console.error('Create strategy error:', error);
      console.error('Error response:', err?.response);
      console.error('Error data:', err?.response?.data);
      message.error(err?.response?.data?.detail || 'Failed to create strategy');
    },
  });

  const selectedStrategyType = STRATEGY_TYPES.find(
    (t) => t.value === selectedType
  );

  const handleNext = async () => {
    try {
      const values = await form.validateFields();
      setWizardData({ ...wizardData, ...values });
      setCurrentStep(currentStep + 1);
    } catch (_error) {
      // Validation failed - user will see field errors
    }
  };

  const handlePrev = () => {
    setCurrentStep(currentStep - 1);
  };

  const handleFinish = async () => {
    try {
      const values = await form.validateFields();
      const finalData = { ...wizardData, ...values };

      // Parse symbols
      const symbols = finalData.symbols
        ? finalData.symbols.split(',').map((s: string) => s.trim()).filter((s: string) => s.length > 0)
        : [];

      // Parse parameters from JSON string to object
      let parsedParameters = {};
      if (finalData.parameters) {
        try {
          // If it's already an object, use it directly; if it's a string, parse it
          parsedParameters = typeof finalData.parameters === 'string' 
            ? JSON.parse(finalData.parameters)
            : finalData.parameters;
        } catch (error) {
          console.error('Failed to parse parameters:', error);
          message.error('Invalid parameters format');
          return;
        }
      }

      // Combine parameters with risk limits
      const parameters = {
        ...parsedParameters,
        riskLimits: {
          maxPositionSize: finalData.maxPositionSize,
          maxDailyLoss: finalData.maxDailyLoss,
          maxDrawdown: finalData.maxDrawdown,
          stopLossPercent: finalData.stopLossPercent,
        },
      };

      const createData: CreateStrategyRequest = {
        name: finalData.name!,
        description: finalData.description || '',
        strategyType: finalData.strategyType!,
        symbols,
        parameters,
      };

      createMutation.mutate(createData);
    } catch (_error) {
      // Validation failed - user will see field errors
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return renderBasicInfo();
      case 1:
        return renderParameters();
      case 2:
        return renderRiskLimits();
      case 3:
        return renderReview();
      default:
        return null;
    }
  };

  const renderBasicInfo = () => (
    <div>
      <Title level={4}>Basic Information</Title>
      <Paragraph type="secondary">
        Choose a name, type, and trading symbols for your strategy
      </Paragraph>

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
          placeholder="e.g., Moving Average Crossover Strategy"
          size="large"
          prefix={<InfoCircleOutlined style={{ color: colors.text.secondary }} />}
        />
      </Form.Item>

      <Form.Item
        name="description"
        label="Description"
        rules={[
          { max: 500, message: 'Description must be less than 500 characters' },
        ]}
      >
        <TextArea
          placeholder="Describe what this strategy does and when it should be used..."
          rows={4}
          showCount
          maxLength={500}
        />
      </Form.Item>

      <Form.Item
        name="strategyType"
        label="Strategy Type"
        rules={[{ required: true, message: 'Please select a strategy type' }]}
      >
        <Select
          size="large"
          placeholder="Choose a strategy type"
          onChange={(value) => {
            setSelectedType(value);
            const strategyType = STRATEGY_TYPES.find((t) => t.value === value);
            if (strategyType) {
              // Set default parameters for this type as JSON string
              form.setFieldsValue({
                parameters: JSON.stringify(strategyType.defaultParams, null, 2),
              });
            }
          }}
        >
          {STRATEGY_TYPES.map((type) => (
            <Select.Option key={type.value} value={type.value}>
              <Space>
                <span style={{ fontSize: '18px' }}>{type.icon}</span>
                <div>
                  <div>{type.label}</div>
                  <Text type="secondary" style={{ fontSize: fontSizes.xs }}>
                    {type.description}
                  </Text>
                </div>
              </Space>
            </Select.Option>
          ))}
        </Select>
      </Form.Item>

      {selectedStrategyType && (
        <Card
          size="small"
          style={{
            background: colors.backgrounds.tertiary,
            borderColor: colors.backgrounds.border,
            marginBottom: 16,
          }}
        >
          <Space>
            <span style={{ fontSize: '24px' }}>{selectedStrategyType.icon}</span>
            <div>
              <Text strong>{selectedStrategyType.label}</Text>
              <br />
              <Text type="secondary" style={{ fontSize: fontSizes.sm }}>
                {selectedStrategyType.description}
              </Text>
            </div>
          </Space>
        </Card>
      )}

      <Form.Item
        name="symbols"
        label={
          <Space>
            Trading Symbols
            <Tooltip title="Enter stock symbols separated by commas. The strategy will trade these securities.">
              <InfoCircleOutlined style={{ color: colors.text.secondary }} />
            </Tooltip>
          </Space>
        }
        rules={[
          { required: true, message: 'Please enter at least one symbol' },
        ]}
        extra={
          <Text type="secondary" style={{ fontSize: fontSizes.xs }}>
            Separate multiple symbols with commas (e.g., AAPL, MSFT, GOOGL)
          </Text>
        }
      >
        <Input
          placeholder="AAPL, MSFT, GOOGL"
          size="large"
        />
      </Form.Item>
    </div>
  );

  const renderParameters = () => {
    const strategyType = STRATEGY_TYPES.find(
      (t) => t.value === (wizardData.strategyType || form.getFieldValue('strategyType'))
    );

    return (
      <div>
        <Title level={4}>Strategy Parameters</Title>
        <Paragraph type="secondary">
          Configure the specific parameters for your {strategyType?.label || 'strategy'}
        </Paragraph>

        {strategyType && (
          <Card
            size="small"
            style={{
              background: colors.backgrounds.tertiary,
              borderColor: colors.backgrounds.border,
              marginBottom: 24,
            }}
          >
            <Text type="secondary">
              Default parameters for {strategyType.label}. You can customize these or use the defaults.
            </Text>
          </Card>
        )}

        <Form.Item
          name="parameters"
          label={
            <Space>
              Parameters (JSON)
              <Tooltip title="Configure strategy parameters as JSON object. These control the strategy's behavior.">
                <InfoCircleOutlined style={{ color: colors.text.secondary }} />
              </Tooltip>
            </Space>
          }
          rules={[
            { required: true, message: 'Please enter strategy parameters' },
            {
              validator: (_, value) => {
                try {
                  if (typeof value === 'string') {
                    JSON.parse(value);
                  }
                  return Promise.resolve();
                } catch {
                  return Promise.reject(new Error('Invalid JSON format'));
                }
              },
            },
          ]}
          extra={
            <Text type="secondary" style={{ fontSize: fontSizes.xs }}>
              Parameters must be valid JSON. Use the template above or customize as needed.
            </Text>
          }
        >
          <TextArea
            rows={12}
            placeholder='{"key": "value"}'
            style={{ fontFamily: 'monospace', fontSize: fontSizes.sm }}
          />
        </Form.Item>

        {strategyType && (
          <Card
            title="Parameter Guide"
            size="small"
            style={{
              background: colors.backgrounds.tertiary,
              borderColor: colors.backgrounds.border,
            }}
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              {Object.entries(strategyType.defaultParams).map(([key, value]) => (
                <div key={key}>
                  <Text strong code>{key}</Text>: {' '}
                  <Text type="secondary">{JSON.stringify(value)}</Text>
                </div>
              ))}
            </Space>
          </Card>
        )}
      </div>
    );
  };

  const renderRiskLimits = () => (
    <div>
      <Title level={4}>Risk Management</Title>
      <Paragraph type="secondary">
        Set risk limits to protect your capital and control exposure
      </Paragraph>

      <Card
        size="small"
        style={{
          background: colors.semantic.warning + '15',
          borderColor: colors.semantic.warning,
          marginBottom: 24,
        }}
      >
        <Space>
          <InfoCircleOutlined style={{ color: colors.semantic.warning }} />
          <Text style={{ color: colors.semantic.warning }}>
            These limits help prevent excessive losses. The strategy will automatically stop if any limit is breached.
          </Text>
        </Space>
      </Card>

      <Row gutter={24}>
        <Col xs={24} md={12}>
          <Form.Item
            name="maxPositionSize"
            label={
              <Space>
                Max Position Size ($)
                <Tooltip title="Maximum dollar amount for a single position. Prevents overexposure to any one trade.">
                  <InfoCircleOutlined style={{ color: colors.text.secondary }} />
                </Tooltip>
              </Space>
            }
            rules={[
              { required: true, message: 'Please enter max position size' },
              { type: 'number', min: 100, message: 'Minimum $100' },
            ]}
          >
            <InputNumber
              style={{ width: '100%' }}
              size="large"
              min={100}
              step={1000}
              formatter={(value) => `$ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
              parser={(value) => parseFloat(value!.replace(/\$\s?|(,*)/g, '')) as unknown as 100}
            />
          </Form.Item>
        </Col>

        <Col xs={24} md={12}>
          <Form.Item
            name="maxDailyLoss"
            label={
              <Space>
                Max Daily Loss ($)
                <Tooltip title="Maximum loss allowed in a single trading day. Strategy stops if exceeded.">
                  <InfoCircleOutlined style={{ color: colors.text.secondary }} />
                </Tooltip>
              </Space>
            }
            rules={[
              { required: true, message: 'Please enter max daily loss' },
              { type: 'number', min: 100, message: 'Minimum $100' },
            ]}
          >
            <InputNumber
              style={{ width: '100%' }}
              size="large"
              min={100}
              step={100}
              formatter={(value) => `$ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
              parser={(value) => parseFloat(value!.replace(/\$\s?|(,*)/g, '')) as unknown as 100}
            />
          </Form.Item>
        </Col>

        <Col xs={24} md={12}>
          <Form.Item
            name="maxDrawdown"
            label={
              <Space>
                Max Drawdown (%)
                <Tooltip title="Maximum percentage decline from peak equity. Strategy stops if drawdown exceeds this.">
                  <InfoCircleOutlined style={{ color: colors.text.secondary }} />
                </Tooltip>
              </Space>
            }
            rules={[
              { required: true, message: 'Please enter max drawdown' },
              { type: 'number', min: 1, max: 50, message: 'Must be between 1-50%' },
            ]}
          >
            <InputNumber
              style={{ width: '100%' }}
              size="large"
              min={1}
              max={50}
              step={1}
              formatter={(value) => `${value}%`}
              parser={(value) => parseFloat(value!.replace('%', '')) as unknown as 1}
            />
          </Form.Item>
        </Col>

        <Col xs={24} md={12}>
          <Form.Item
            name="stopLossPercent"
            label={
              <Space>
                Stop Loss (%)
                <Tooltip title="Percentage loss at which to automatically close a position. Per-trade risk control.">
                  <InfoCircleOutlined style={{ color: colors.text.secondary }} />
                </Tooltip>
              </Space>
            }
            rules={[
              { required: true, message: 'Please enter stop loss percentage' },
              { type: 'number', min: 0.5, max: 10, message: 'Must be between 0.5-10%' },
            ]}
          >
            <InputNumber
              style={{ width: '100%' }}
              size="large"
              min={0.5}
              max={10}
              step={0.5}
              formatter={(value) => `${value}%`}
              parser={(value) => parseFloat(value!.replace('%', '')) as unknown as 0.5}
            />
          </Form.Item>
        </Col>
      </Row>
    </div>
  );

  const renderReview = () => {
    const strategyType = STRATEGY_TYPES.find(
      (t) => t.value === wizardData.strategyType
    );

    const symbols = wizardData.symbols
      ? wizardData.symbols.split(',').map((s) => s.trim()).filter((s) => s.length > 0)
      : [];

    return (
      <div>
        <Title level={4}>Review & Create</Title>
        <Paragraph type="secondary">
          Review your strategy configuration before creating
        </Paragraph>

        <Card
          style={{
            background: colors.backgrounds.tertiary,
            borderColor: colors.backgrounds.border,
            marginBottom: 24,
          }}
        >
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            {/* Basic Info */}
            <div>
              <Text type="secondary">Strategy Name</Text>
              <Title level={5} style={{ margin: '4px 0' }}>
                {wizardData.name}
              </Title>
            </div>

            {wizardData.description && (
              <div>
                <Text type="secondary">Description</Text>
                <Paragraph style={{ margin: '4px 0' }}>
                  {wizardData.description}
                </Paragraph>
              </div>
            )}

            <div>
              <Text type="secondary">Strategy Type</Text>
              <div style={{ marginTop: 4 }}>
                <Space>
                  <span style={{ fontSize: '20px' }}>{strategyType?.icon}</span>
                  <Text strong>{strategyType?.label}</Text>
                </Space>
              </div>
            </div>

            <div>
              <Text type="secondary">Trading Symbols ({symbols.length})</Text>
              <div style={{ marginTop: 4 }}>
                <Space wrap>
                  {symbols.map((symbol) => (
                    <Tag key={symbol} color="blue">
                      {symbol}
                    </Tag>
                  ))}
                </Space>
              </div>
            </div>

            <Divider />

            {/* Parameters */}
            <div>
              <Text type="secondary">Parameters</Text>
              <div style={{ marginTop: 8 }}>
                <Card size="small" style={{ background: colors.backgrounds.primary }}>
                  <pre style={{ margin: 0, fontSize: fontSizes.sm }}>
                    {typeof wizardData.parameters === 'string'
                      ? wizardData.parameters
                      : JSON.stringify(wizardData.parameters, null, 2)}
                  </pre>
                </Card>
              </div>
            </div>

            <Divider />

            {/* Risk Limits */}
            <div>
              <Text type="secondary">Risk Limits</Text>
              <Row gutter={16} style={{ marginTop: 8 }}>
                <Col span={12}>
                  <Card size="small" style={{ background: colors.backgrounds.primary }}>
                    <Text type="secondary">Max Position Size</Text>
                    <Title level={5} style={{ margin: '4px 0', color: colors.semantic.info }}>
                      ${wizardData.maxPositionSize?.toLocaleString()}
                    </Title>
                  </Card>
                </Col>
                <Col span={12}>
                  <Card size="small" style={{ background: colors.backgrounds.primary }}>
                    <Text type="secondary">Max Daily Loss</Text>
                    <Title level={5} style={{ margin: '4px 0', color: colors.semantic.error }}>
                      ${wizardData.maxDailyLoss?.toLocaleString()}
                    </Title>
                  </Card>
                </Col>
                <Col span={12}>
                  <Card size="small" style={{ background: colors.backgrounds.primary }}>
                    <Text type="secondary">Max Drawdown</Text>
                    <Title level={5} style={{ margin: '4px 0', color: colors.semantic.warning }}>
                      {wizardData.maxDrawdown}%
                    </Title>
                  </Card>
                </Col>
                <Col span={12}>
                  <Card size="small" style={{ background: colors.backgrounds.primary }}>
                    <Text type="secondary">Stop Loss</Text>
                    <Title level={5} style={{ margin: '4px 0', color: colors.semantic.warning }}>
                      {wizardData.stopLossPercent}%
                    </Title>
                  </Card>
                </Col>
              </Row>
            </div>
          </Space>
        </Card>

        <Card
          size="small"
          style={{
            background: colors.semantic.success + '15',
            borderColor: colors.semantic.success,
          }}
        >
          <Space>
            <CheckCircleOutlined style={{ color: colors.semantic.success }} />
            <Text style={{ color: colors.semantic.success }}>
              Ready to create! Your strategy will be created in 'stopped' status. You can start it from the strategy detail page.
            </Text>
          </Space>
        </Card>
      </div>
    );
  };

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
              {cloneFrom ? `Clone Strategy: ${cloneFrom.name}` : 'Create New Strategy'}
            </Title>
          </Space>
        </Col>
      </Row>

      {/* Clone notification */}
      {cloneFrom && (
        <Card
          size="small"
          style={{
            background: colors.semantic.info + '15',
            borderColor: colors.semantic.info,
            marginBottom: 24,
          }}
        >
          <Space>
            <CopyOutlined style={{ color: colors.semantic.info }} />
            <Text style={{ color: colors.semantic.info }}>
              Cloning from "<strong>{cloneFrom.name}</strong>". All settings have been copied. 
              You can modify them as needed before creating the new strategy.
            </Text>
          </Space>
        </Card>
      )}

      {/* Steps */}
      <Card
        style={{
          background: colors.backgrounds.secondary,
          borderColor: colors.backgrounds.border,
          marginBottom: 24,
        }}
      >
        <Steps current={currentStep}>
          <Step title="Basic Info" description="Name and type" />
          <Step title="Parameters" description="Configure strategy" />
          <Step title="Risk Limits" description="Set safety limits" />
          <Step title="Review" description="Confirm and create" />
        </Steps>
      </Card>

      {/* Form Content */}
      <Card
        style={{
          background: colors.backgrounds.secondary,
          borderColor: colors.backgrounds.border,
        }}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={cloneFrom ? {
            name: wizardData.name,
            description: wizardData.description,
            strategyType: wizardData.strategyType,
            symbols: wizardData.symbols,
            parameters: typeof wizardData.parameters === 'string' 
              ? wizardData.parameters 
              : JSON.stringify(wizardData.parameters, null, 2),
            maxPositionSize: wizardData.maxPositionSize,
            maxDailyLoss: wizardData.maxDailyLoss,
            maxDrawdown: wizardData.maxDrawdown,
            stopLossPercent: wizardData.stopLossPercent,
          } : {
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
            maxPositionSize: 10000,
            maxDailyLoss: 1000,
            maxDrawdown: 15,
            stopLossPercent: 2,
          }}
        >
          {renderStepContent()}

          {/* Navigation Buttons */}
          <Divider />
          <Row justify="space-between">
            <Col>
              {currentStep > 0 && (
                <Button
                  size="large"
                  onClick={handlePrev}
                  icon={<LeftOutlined />}
                >
                  Previous
                </Button>
              )}
            </Col>
            <Col>
              {currentStep < 3 && (
                <Button
                  type="primary"
                  size="large"
                  onClick={handleNext}
                  icon={<RightOutlined />}
                  iconPosition="end"
                >
                  Next
                </Button>
              )}
              {currentStep === 3 && (
                <Button
                  type="primary"
                  size="large"
                  onClick={handleFinish}
                  loading={createMutation.isPending}
                  icon={<CheckCircleOutlined />}
                  style={{
                    background: colors.semantic.success,
                    borderColor: colors.semantic.success,
                  }}
                >
                  Create Strategy
                </Button>
              )}
            </Col>
          </Row>
        </Form>
      </Card>
    </div>
  );
};

