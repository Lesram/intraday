/**
 * Indicator Panel Component
 * 
 * Provides UI for adding, configuring, and managing technical indicators on charts.
 * 
 * Features:
 * - Indicator selector with 20+ indicators
 * - Parameter configuration (periods, colors, etc.)
 * - Active indicators list with enable/disable
 * - Preset combinations (Trend, Momentum, Volatility, Volume)
 * - Real-time updates via useIndicators hook
 * 
 * Phase 7 - Market Data & Charting
 * Created: October 16, 2025
 */

import React, { useState } from 'react';
import {
  Card,
  Select,
  Button,
  Space,
  List,
  InputNumber,
  ColorPicker,
  Switch,
  Divider,
  Typography,
  Tooltip,
  Tag,
  Row,
  Col,
  App,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  LineChartOutlined,
  RiseOutlined,
  FallOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';

const { Text } = Typography;
const { Option } = Select;

// ============================================================================
// TYPES
// ============================================================================

export interface IndicatorConfig {
  id: string;
  name: string;
  displayName: string;
  category: 'trend' | 'momentum' | 'volatility' | 'volume' | 'advanced';
  params: Record<string, number>;
  color: string;
  enabled: boolean;
}

interface IndicatorMetadata {
  name: string;
  displayName: string;
  category: 'trend' | 'momentum' | 'volatility' | 'volume' | 'advanced';
  description: string;
  defaultParams: Record<string, number>;
  paramMeta: {
    name: string;
    label: string;
    default: number;
    min: number;
    max: number;
  }[];
  overlay: boolean; // true if drawn on price chart, false if separate pane
}

// ============================================================================
// INDICATOR DEFINITIONS
// ============================================================================

const INDICATOR_DEFINITIONS: Record<string, IndicatorMetadata> = {
  // TREND INDICATORS
  sma: {
    name: 'sma',
    displayName: 'Simple Moving Average',
    category: 'trend',
    description: 'Average price over N periods',
    defaultParams: { period: 20 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 20, min: 2, max: 200 },
    ],
    overlay: true,
  },
  ema: {
    name: 'ema',
    displayName: 'Exponential Moving Average',
    category: 'trend',
    description: 'Weighted average giving more weight to recent prices',
    defaultParams: { period: 20 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 20, min: 2, max: 200 },
    ],
    overlay: true,
  },
  wma: {
    name: 'wma',
    displayName: 'Weighted Moving Average',
    category: 'trend',
    description: 'Linear weighted average',
    defaultParams: { period: 20 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 20, min: 2, max: 200 },
    ],
    overlay: true,
  },
  
  // MOMENTUM INDICATORS
  rsi: {
    name: 'rsi',
    displayName: 'Relative Strength Index',
    category: 'momentum',
    description: 'Momentum oscillator (0-100). >70 overbought, <30 oversold',
    defaultParams: { period: 14 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 14, min: 2, max: 50 },
    ],
    overlay: false,
  },
  macd: {
    name: 'macd',
    displayName: 'MACD',
    category: 'momentum',
    description: 'Moving Average Convergence Divergence',
    defaultParams: { fast: 12, slow: 26, signal: 9 },
    paramMeta: [
      { name: 'fast', label: 'Fast Period', default: 12, min: 2, max: 50 },
      { name: 'slow', label: 'Slow Period', default: 26, min: 2, max: 100 },
      { name: 'signal', label: 'Signal Period', default: 9, min: 2, max: 50 },
    ],
    overlay: false,
  },
  stochastic: {
    name: 'stochastic',
    displayName: 'Stochastic Oscillator',
    category: 'momentum',
    description: 'Momentum oscillator comparing closing price to price range',
    defaultParams: { k_period: 14, d_period: 3 },
    paramMeta: [
      { name: 'k_period', label: 'K Period', default: 14, min: 2, max: 50 },
      { name: 'd_period', label: 'D Period', default: 3, min: 2, max: 20 },
    ],
    overlay: false,
  },
  williams_r: {
    name: 'williams_r',
    displayName: 'Williams %R',
    category: 'momentum',
    description: 'Momentum indicator measuring overbought/oversold levels',
    defaultParams: { period: 14 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 14, min: 2, max: 50 },
    ],
    overlay: false,
  },
  cci: {
    name: 'cci',
    displayName: 'Commodity Channel Index',
    category: 'momentum',
    description: 'Measures variation from statistical mean',
    defaultParams: { period: 20 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 20, min: 2, max: 50 },
    ],
    overlay: false,
  },
  
  // VOLATILITY INDICATORS
  bollinger: {
    name: 'bollinger',
    displayName: 'Bollinger Bands',
    category: 'volatility',
    description: 'Volatility bands around moving average',
    defaultParams: { period: 20, std_dev: 2 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 20, min: 2, max: 100 },
      { name: 'std_dev', label: 'Std Deviations', default: 2, min: 1, max: 3 },
    ],
    overlay: true,
  },
  atr: {
    name: 'atr',
    displayName: 'Average True Range',
    category: 'volatility',
    description: 'Measures market volatility',
    defaultParams: { period: 14 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 14, min: 2, max: 50 },
    ],
    overlay: false,
  },
  donchian: {
    name: 'donchian',
    displayName: 'Donchian Channels',
    category: 'volatility',
    description: 'Price channels based on highest high and lowest low',
    defaultParams: { period: 20 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 20, min: 2, max: 100 },
    ],
    overlay: true,
  },
  keltner: {
    name: 'keltner',
    displayName: 'Keltner Channels',
    category: 'volatility',
    description: 'Volatility-based envelope around EMA',
    defaultParams: { period: 20, multiplier: 2 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 20, min: 2, max: 100 },
      { name: 'multiplier', label: 'Multiplier', default: 2, min: 1, max: 3 },
    ],
    overlay: true,
  },
  
  // VOLUME INDICATORS
  volume_ma: {
    name: 'volume_ma',
    displayName: 'Volume Moving Average',
    category: 'volume',
    description: 'Moving average of volume',
    defaultParams: { period: 20 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 20, min: 2, max: 100 },
    ],
    overlay: false,
  },
  obv: {
    name: 'obv',
    displayName: 'On Balance Volume',
    category: 'volume',
    description: 'Cumulative volume indicator',
    defaultParams: {},
    paramMeta: [],
    overlay: false,
  },
  mfi: {
    name: 'mfi',
    displayName: 'Money Flow Index',
    category: 'volume',
    description: 'Volume-weighted RSI',
    defaultParams: { period: 14 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 14, min: 2, max: 50 },
    ],
    overlay: false,
  },
  vwap: {
    name: 'vwap',
    displayName: 'VWAP',
    category: 'volume',
    description: 'Volume Weighted Average Price',
    defaultParams: {},
    paramMeta: [],
    overlay: true,
  },
  
  // ADVANCED INDICATORS
  adx: {
    name: 'adx',
    displayName: 'Average Directional Index',
    category: 'advanced',
    description: 'Trend strength indicator. >25 strong trend, <20 weak',
    defaultParams: { period: 14 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 14, min: 2, max: 50 },
    ],
    overlay: false,
  },
  ichimoku: {
    name: 'ichimoku',
    displayName: 'Ichimoku Cloud',
    category: 'advanced',
    description: 'Comprehensive trend system with 5 lines',
    defaultParams: {},
    paramMeta: [],
    overlay: true,
  },
  parabolic_sar: {
    name: 'parabolic_sar',
    displayName: 'Parabolic SAR',
    category: 'advanced',
    description: 'Stop and Reverse indicator',
    defaultParams: {},
    paramMeta: [],
    overlay: true,
  },
  pivot_points: {
    name: 'pivot_points',
    displayName: 'Pivot Points',
    category: 'advanced',
    description: 'Support and resistance levels',
    defaultParams: {},
    paramMeta: [],
    overlay: true,
  },
  
  // NEW ENHANCED INDICATORS
  aroon: {
    name: 'aroon',
    displayName: 'Aroon Indicator',
    category: 'trend',
    description: 'Identifies trend changes. Up/Down lines and oscillator',
    defaultParams: { period: 25 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 25, min: 5, max: 100 },
    ],
    overlay: false,
  },
  cmf: {
    name: 'cmf',
    displayName: 'Chaikin Money Flow',
    category: 'volume',
    description: 'Measures buying/selling pressure. >0 buying, <0 selling',
    defaultParams: { period: 20 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 20, min: 5, max: 50 },
    ],
    overlay: false,
  },
  trix: {
    name: 'trix',
    displayName: 'TRIX',
    category: 'momentum',
    description: 'Triple exponential average momentum oscillator',
    defaultParams: { period: 15 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 15, min: 5, max: 50 },
    ],
    overlay: false,
  },
  vwma: {
    name: 'vwma',
    displayName: 'Volume Weighted MA',
    category: 'volume',
    description: 'Moving average weighted by volume',
    defaultParams: { period: 20 },
    paramMeta: [
      { name: 'period', label: 'Period', default: 20, min: 5, max: 100 },
    ],
    overlay: true,
  },
  kst: {
    name: 'kst',
    displayName: 'Know Sure Thing',
    category: 'momentum',
    description: 'Momentum oscillator based on 4 ROC values',
    defaultParams: {},
    paramMeta: [],
    overlay: false,
  },
  uo: {
    name: 'uo',
    displayName: 'Ultimate Oscillator',
    category: 'momentum',
    description: 'Multi-timeframe momentum. 0-100 scale',
    defaultParams: {},
    paramMeta: [],
    overlay: false,
  },
  ao: {
    name: 'ao',
    displayName: 'Awesome Oscillator',
    category: 'momentum',
    description: 'Momentum indicator using midpoint of bars',
    defaultParams: {},
    paramMeta: [],
    overlay: false,
  },
};

// Preset indicator combinations
const INDICATOR_PRESETS = {
  trend_analysis: {
    name: 'Trend Analysis',
    icon: <LineChartOutlined />,
    indicators: ['sma', 'ema'],
    params: {
      sma: { period: 50 },
      ema: { period: 20 },
    },
  },
  momentum_trading: {
    name: 'Momentum Trading',
    icon: <RiseOutlined />,
    indicators: ['rsi', 'macd'],
    params: {
      rsi: { period: 14 },
      macd: { fast: 12, slow: 26, signal: 9 },
    },
  },
  volatility_analysis: {
    name: 'Volatility Analysis',
    icon: <ThunderboltOutlined />,
    indicators: ['bollinger', 'atr'],
    params: {
      bollinger: { period: 20, std_dev: 2 },
      atr: { period: 14 },
    },
  },
  volume_analysis: {
    name: 'Volume Analysis',
    icon: <FallOutlined />,
    indicators: ['volume_ma', 'vwap', 'cmf'],
    params: {
      volume_ma: { period: 20 },
      vwap: {},
      cmf: { period: 20 },
    },
  },
  advanced_momentum: {
    name: 'Advanced Momentum',
    icon: <ThunderboltOutlined />,
    indicators: ['kst', 'uo', 'trix'],
    params: {
      kst: {},
      uo: {},
      trix: { period: 15 },
    },
  },
  trend_detection: {
    name: 'Trend Detection',
    icon: <LineChartOutlined />,
    indicators: ['aroon', 'adx', 'vwma'],
    params: {
      aroon: { period: 25 },
      adx: { period: 14 },
      vwma: { period: 20 },
    },
  },
};

// ============================================================================
// COMPONENT
// ============================================================================

interface IndicatorPanelProps {
  onIndicatorAdd?: (config: IndicatorConfig) => void;
  onIndicatorRemove?: (id: string) => void;
  onIndicatorUpdate?: (id: string, config: Partial<IndicatorConfig>) => void;
  activeIndicators?: IndicatorConfig[];
}

export const IndicatorPanel: React.FC<IndicatorPanelProps> = ({
  onIndicatorAdd,
  onIndicatorRemove,
  onIndicatorUpdate,
  activeIndicators = [],
}) => {
  // Get message API from App context
  const { message } = App.useApp();
  
  // State
  const [selectedIndicator, setSelectedIndicator] = useState<string | undefined>();
  const [params, setParams] = useState<Record<string, number>>({});
  const [color, setColor] = useState<string>('#2962FF');

  // Get selected indicator metadata
  const selectedMeta = selectedIndicator
    ? INDICATOR_DEFINITIONS[selectedIndicator]
    : undefined;

  // Handle indicator selection
  const handleIndicatorSelect = (name: string) => {
    setSelectedIndicator(name);
    const meta = INDICATOR_DEFINITIONS[name];
    setParams(meta.defaultParams);
  };

  // Handle parameter change
  const handleParamChange = (paramName: string, value: number | null) => {
    if (value !== null) {
      setParams((prev) => ({ ...prev, [paramName]: value }));
    }
  };

  // Add indicator
  const handleAddIndicator = () => {
    if (!selectedIndicator || !selectedMeta) {
      message.warning('Please select an indicator');
      return;
    }

    const config: IndicatorConfig = {
      id: `${selectedIndicator}_${Date.now()}`,
      name: selectedIndicator,
      displayName: selectedMeta.displayName,
      category: selectedMeta.category,
      params,
      color,
      enabled: true,
    };

    onIndicatorAdd?.(config);
    message.success(`Added ${selectedMeta.displayName}`);

    // Reset form
    setSelectedIndicator(undefined);
    setParams({});
  };

  // Load preset
  const handleLoadPreset = (presetKey: string) => {
    const preset = INDICATOR_PRESETS[presetKey as keyof typeof INDICATOR_PRESETS];
    if (!preset) return;

    preset.indicators.forEach((indicatorName) => {
      const meta = INDICATOR_DEFINITIONS[indicatorName];
      const presetParams = (preset.params as Record<string, Record<string, number>>)[indicatorName];
      const config: IndicatorConfig = {
        id: `${indicatorName}_${Date.now()}_${Math.random()}`,
        name: indicatorName,
        displayName: meta.displayName,
        category: meta.category,
        params: presetParams || meta.defaultParams,
        color: '#2962FF',
        enabled: true,
      };
      onIndicatorAdd?.(config);
    });

    message.success(`Loaded ${preset.name} preset`);
  };

  // Category colors
  const categoryColors = {
    trend: 'blue',
    momentum: 'green',
    volatility: 'orange',
    volume: 'purple',
    advanced: 'red',
  };

  return (
    <Card
      title={
        <Space>
          <LineChartOutlined />
          <span>Technical Indicators</span>
        </Space>
      }
      size="small"
      style={{ height: '100%', overflow: 'auto' }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {/* Indicator Selector */}
        <div>
          <Text strong>Add Indicator</Text>
          <Select
            style={{ width: '100%', marginTop: 8 }}
            placeholder="Select an indicator..."
            value={selectedIndicator}
            onChange={handleIndicatorSelect}
            showSearch
            optionFilterProp="children"
          >
            {Object.entries(INDICATOR_DEFINITIONS).map(([key, meta]) => (
              <Option key={key} value={key}>
                <Space>
                  <Tag color={categoryColors[meta.category]}>{meta.category}</Tag>
                  {meta.displayName}
                </Space>
              </Option>
            ))}
          </Select>
        </div>

        {/* Parameter Configuration */}
        {selectedMeta && (
          <>
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {selectedMeta.description}
              </Text>
            </div>

            {selectedMeta.paramMeta.length > 0 && (
              <div>
                <Text strong>Parameters</Text>
                <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
                  {selectedMeta.paramMeta.map((param) => (
                    <Row key={param.name} gutter={8} align="middle">
                      <Col span={12}>
                        <Text>{param.label}</Text>
                      </Col>
                      <Col span={12}>
                        <InputNumber
                          style={{ width: '100%' }}
                          min={param.min}
                          max={param.max}
                          value={params[param.name] ?? param.default}
                          onChange={(value) => handleParamChange(param.name, value)}
                        />
                      </Col>
                    </Row>
                  ))}
                </Space>
              </div>
            )}

            {/* Color Picker */}
            <div>
              <Row gutter={8} align="middle">
                <Col span={12}>
                  <Text strong>Color</Text>
                </Col>
                <Col span={12}>
                  <ColorPicker
                    value={color}
                    onChange={(_, hex) => setColor(hex)}
                    showText
                  />
                </Col>
              </Row>
            </div>

            {/* Add Button */}
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleAddIndicator}
              block
            >
              Add Indicator
            </Button>
          </>
        )}

        <Divider />

        {/* Preset Buttons */}
        <div>
          <Text strong>Quick Presets</Text>
          <Space wrap style={{ marginTop: 8 }}>
            {Object.entries(INDICATOR_PRESETS).map(([key, preset]) => (
              <Tooltip key={key} title={`Load ${preset.name}`}>
                <Button
                  size="small"
                  icon={preset.icon}
                  onClick={() => handleLoadPreset(key)}
                >
                  {preset.name.split(' ')[0]}
                </Button>
              </Tooltip>
            ))}
          </Space>
        </div>

        <Divider />

        {/* Active Indicators List */}
        <div>
          <Text strong>Active Indicators ({activeIndicators.length})</Text>
          <List
            style={{ marginTop: 8 }}
            size="small"
            dataSource={activeIndicators}
            locale={{ emptyText: 'No indicators added' }}
            renderItem={(indicator) => (
              <List.Item
                actions={[
                  <Switch
                    key="toggle"
                    size="small"
                    checked={indicator.enabled}
                    onChange={(checked) =>
                      onIndicatorUpdate?.(indicator.id, { enabled: checked })
                    }
                  />,
                  <Tooltip key="delete" title="Remove">
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => onIndicatorRemove?.(indicator.id)}
                    />
                  </Tooltip>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <div
                        style={{
                          width: 12,
                          height: 12,
                          borderRadius: 2,
                          backgroundColor: indicator.color,
                        }}
                      />
                      <Text>{indicator.displayName}</Text>
                      <Tag color={categoryColors[indicator.category]} style={{ fontSize: 10 }}>
                        {indicator.category}
                      </Tag>
                    </Space>
                  }
                  description={
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {Object.entries(indicator.params)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(', ') || 'Default'}
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        </div>
      </Space>
    </Card>
  );
};

export default IndicatorPanel;
