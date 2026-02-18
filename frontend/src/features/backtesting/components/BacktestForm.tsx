/**
 * BacktestForm Component
 * 
 * Form for configuring and running a backtest on a trading strategy.
 * Allows users to set date ranges, initial capital, and optional parameter overrides.
 */

import React, { useEffect, useState } from 'react';
import { 
  Form, 
  Select, 
  DatePicker, 
  InputNumber, 
  Button, 
  Card, 
  Space,
  Switch,
  Collapse,
  Alert,
  Divider
} from 'antd';
import { PlayCircleOutlined, SettingOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import type { BacktestRequest } from '../../../types/backtest';
import { useStrategy } from '@/hooks/useData';

const { RangePicker } = DatePicker;

interface BacktestFormProps {
  strategies: Array<{ id: string; name: string; type: string }>;
  onSubmit: (strategyId: string, request: BacktestRequest) => void;
  loading?: boolean;
}

export const BacktestForm: React.FC<BacktestFormProps> = ({ 
  strategies, 
  onSubmit, 
  loading = false 
}) => {
  const [form] = Form.useForm();
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null);
  const [useCustomParams, setUseCustomParams] = useState(false);
  const [overrideFeatureToggles, setOverrideFeatureToggles] = useState(false);
  const [engine, setEngine] = useState<'platform' | 'research'>('platform');
  const [overlayEnabled, setOverlayEnabled] = useState(false);

  const { data: strategyDetails } = useStrategy(selectedStrategy || '');

  useEffect(() => {
    if (!strategyDetails) return;
    const params = strategyDetails.parameters || {};

    form.setFieldsValue({
      useOptunaLeverage: Boolean(params.use_optuna_leverage ?? params.allow_leverage),
      maxGrossExposure: Number(params.max_gross_exposure ?? 1),
      useOptunaPositionSize: Boolean(params.use_optuna_position_size),
      positionSizePct: Number(params.position_size_pct ?? 0.1),
      useOptunaMaxPositions: Boolean(params.use_optuna_max_positions),
      maxPositions: Number(params.max_positions ?? 10),
      useOptunaMinPositionDollars: Boolean(params.use_optuna_min_position_dollars),
      minPositionDollars: Number(params.min_position_dollars ?? 0),
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
  }, [strategyDetails, form]);

  const handleSubmit = (values: Record<string, unknown>) => {
    const dateRange = values.dateRange as [Dayjs, Dayjs];
    const [startDate, endDate] = dateRange;
    
    const request: BacktestRequest = {
      strategy_id: values.strategyId as string,
      engine: (values.engine as 'platform' | 'research') || 'platform',
      start_date: startDate.format('YYYY-MM-DD'),
      end_date: endDate.format('YYYY-MM-DD'),
      initial_capital: values.initialCapital as number,
    };

    const overrideParams: Record<string, unknown> = {};

    if (overrideFeatureToggles) {
      overrideParams.use_optuna_leverage = Boolean(values.useOptunaLeverage);
      overrideParams.allow_leverage = Boolean(values.useOptunaLeverage);
      overrideParams.max_gross_exposure = values.maxGrossExposure;

      overrideParams.use_optuna_position_size = Boolean(values.useOptunaPositionSize);
      overrideParams.position_size_pct = values.positionSizePct;

      overrideParams.use_optuna_max_positions = Boolean(values.useOptunaMaxPositions);
      overrideParams.max_positions = values.maxPositions;

      overrideParams.use_optuna_min_position_dollars = Boolean(values.useOptunaMinPositionDollars);
      overrideParams.min_position_dollars = values.minPositionDollars;
    }

    if (useCustomParams && values.customParameters) {
      Object.assign(overrideParams, values.customParameters as Record<string, unknown>);
    }

    if (overlayEnabled) {
      overrideParams.overlay_kill_switch = Number(Boolean(values.overlayKillSwitch));
      overrideParams.overlay_kill_dd_pct = values.overlayKillDdPct;
      overrideParams.overlay_kill_cooldown_days = values.overlayKillCooldownDays;
      overrideParams.overlay_kill_force_exit = Number(Boolean(values.overlayKillForceExit));
      overrideParams.overlay_vol_enabled = Number(Boolean(values.overlayVolEnabled));
      overrideParams.overlay_vol_target = values.overlayVolTarget;
      overrideParams.overlay_vol_window = values.overlayVolWindow;
      overrideParams.overlay_vol_min_mult = values.overlayVolMinMult;
      overrideParams.overlay_vol_max_mult = values.overlayVolMaxMult;
      overrideParams.overlay_gap_enabled = Number(Boolean(values.overlayGapEnabled));
      overrideParams.overlay_gap_max_pct = values.overlayGapMaxPct;
      overrideParams.overlay_risk_off_adjust = Number(Boolean(values.overlayRiskOffAdjust));
      overrideParams.overlay_risk_off_stop_mult = values.overlayRiskOffStopMult;
      overrideParams.overlay_risk_off_take_mult = values.overlayRiskOffTakeMult;
    }

    if (Object.keys(overrideParams).length > 0) {
      request.parameters = overrideParams;
    }

    onSubmit(values.strategyId as string, request);
  };

  // Default date range: last 6 months
  const defaultDateRange: [Dayjs, Dayjs] = [
    dayjs().subtract(6, 'months'),
    dayjs()
  ];

  // Disable future dates
  const disabledDate = (current: Dayjs) => {
    return current && current > dayjs().endOf('day');
  };

  return (
    <Card 
      title={
        <Space>
          <PlayCircleOutlined />
          Run Backtest
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{
          dateRange: defaultDateRange,
          initialCapital: 100000,
          engine: 'platform',
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
        {/* Strategy Selection */}
        <Form.Item
          label="Trading Strategy"
          name="strategyId"
          rules={[{ required: true, message: 'Please select a strategy' }]}
        >
          <Select
            placeholder="Select a strategy to backtest"
            onChange={setSelectedStrategy}
            showSearch
            optionFilterProp="children"
            size="large"
          >
            {strategies.map((strategy) => (
              <Select.Option key={strategy.id} value={strategy.id}>
                <Space>
                  <span style={{ fontWeight: 500 }}>{strategy.name}</span>
                  <span style={{ color: '#8c8c8c' }}>({strategy.type})</span>
                </Space>
              </Select.Option>
            ))}
          </Select>
        </Form.Item>

        {/* Date Range */}
        <Form.Item
          label="Backtest Period"
          name="dateRange"
          rules={[{ required: true, message: 'Please select date range' }]}
        >
          <RangePicker
            style={{ width: '100%' }}
            size="large"
            disabledDate={disabledDate}
            format="YYYY-MM-DD"
            allowClear={false}
          />
        </Form.Item>

        {/* Initial Capital */}
        <Form.Item
          label="Initial Capital"
          name="initialCapital"
          rules={[
            { required: true, message: 'Please enter initial capital' },
            { 
              type: 'number', 
              min: 1000, 
              message: 'Minimum capital is $1,000' 
            },
          ]}
        >
          <InputNumber<number>
            style={{ width: '100%' }}
            size="large"
            formatter={(value) => `$ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
            parser={(value) => Number(value?.replace(/\$\s?|(,*)/g, '')) || 0}
            step={1000}
            min={1000}
          />
        </Form.Item>

        {/* Advanced Options */}
        <Collapse 
          ghost
          items={[
            {
              key: 'advanced',
              label: (
                <Space>
                  <SettingOutlined />
                  Advanced Options
                </Space>
              ),
              children: (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Form.Item label="Engine" name="engine" style={{ marginBottom: 8 }}>
                    <Select
                      onChange={(v) => setEngine(v as 'platform' | 'research')}
                      options={[
                        { value: 'platform', label: 'Platform (live-parity)' },
                        { value: 'research', label: 'Research (experimental)' },
                      ]}
                    />
                  </Form.Item>

                  {engine === 'research' && (
                    <Alert
                      message="Research engine is experimental"
                      description="This mode uses the research harness simulator and may not match live execution semantics. Use for exploration/compare only."
                      type="warning"
                      showIcon
                      style={{ marginBottom: 16 }}
                    />
                  )}

                  {/* Custom Parameters Toggle */}
                  <Form.Item label="Use Custom Parameters" style={{ marginBottom: 8 }}>
                    <Switch 
                      checked={useCustomParams}
                      onChange={setUseCustomParams}
                    />
                  </Form.Item>

                  {useCustomParams && (
                    <Alert
                      message="Custom Parameters"
                      description="Custom parameter overrides will be added in the next iteration. The backtest will use the strategy's default parameters."
                      type="info"
                      showIcon
                      style={{ marginBottom: 16 }}
                    />
                  )}

                  <Divider style={{ margin: '8px 0 12px' }} />

                  <Form.Item label="Override Strategy Feature Toggles" style={{ marginBottom: 8 }}>
                    <Switch
                      checked={overrideFeatureToggles}
                      onChange={setOverrideFeatureToggles}
                    />
                  </Form.Item>

                  {!overrideFeatureToggles && (
                    <Alert
                      message="Defaults Applied"
                      description="By default, backtests follow the strategy's stored settings exactly (including Optuna toggles). Turn this on only to override them for this run."
                      type="info"
                      showIcon
                      style={{ marginBottom: 16 }}
                    />
                  )}

                  {overrideFeatureToggles && (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Form.Item label="Use Leverage" name="useOptunaLeverage" valuePropName="checked">
                        <Switch />
                      </Form.Item>

                      <Form.Item label="Max Gross Exposure" name="maxGrossExposure">
                        <InputNumber<number>
                          style={{ width: '100%' }}
                          min={1}
                          step={0.1}
                        />
                      </Form.Item>

                      <Form.Item label="Use Optuna Position Size" name="useOptunaPositionSize" valuePropName="checked">
                        <Switch />
                      </Form.Item>

                      <Form.Item label="Position Size %" name="positionSizePct">
                        <InputNumber<number>
                          style={{ width: '100%' }}
                          min={0.01}
                          max={5}
                          step={0.05}
                        />
                      </Form.Item>

                      <Form.Item label="Use Optuna Max Positions" name="useOptunaMaxPositions" valuePropName="checked">
                        <Switch />
                      </Form.Item>

                      <Form.Item label="Max Positions" name="maxPositions">
                        <InputNumber<number>
                          style={{ width: '100%' }}
                          min={1}
                          step={1}
                        />
                      </Form.Item>

                      <Form.Item label="Use Optuna Min Position Dollars" name="useOptunaMinPositionDollars" valuePropName="checked">
                        <Switch />
                      </Form.Item>

                      <Form.Item label="Min Position Dollars" name="minPositionDollars">
                        <InputNumber<number>
                          style={{ width: '100%' }}
                          min={0}
                          step={50}
                        />
                      </Form.Item>
                    </Space>
                  )}
                </Space>
              ),
            },
          ]}
        />

        <Divider style={{ margin: '8px 0 12px' }} />

        <Form.Item label="Enable Risk Overlays" style={{ marginBottom: 8 }}>
          <Switch
            checked={overlayEnabled}
            onChange={setOverlayEnabled}
          />
        </Form.Item>

        {overlayEnabled && (
          <Space direction="vertical" style={{ width: '100%' }}>
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

            <Divider style={{ margin: '8px 0 12px' }} />

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

            <Divider style={{ margin: '8px 0 12px' }} />

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

            <Divider style={{ margin: '8px 0 12px' }} />

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
          </Space>
        )}

        {/* Submit Button */}
        <Form.Item style={{ marginTop: 24, marginBottom: 0 }}>
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            disabled={!selectedStrategy || loading}
            size="large"
            block
            icon={<PlayCircleOutlined />}
          >
            {loading ? 'Running Backtest...' : 'Run Backtest'}
          </Button>
        </Form.Item>

        {/* Info Alert */}
        {selectedStrategy && (
          <Alert
            message="Backtest Information"
            description="The backtest will simulate your strategy's performance using historical data. This may take a few moments depending on the date range selected."
            type="info"
            showIcon
            style={{ marginTop: 16 }}
          />
        )}
      </Form>
    </Card>
  );
};

export default BacktestForm;
