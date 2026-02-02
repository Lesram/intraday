/**
 * Execution Settings Step - Step 4 of Strategy Builder
 * 
 * Configures when and how often the strategy executes:
 * - Trading hours (market hours)
 * - Execution frequency (realtime, 1min, 5min, etc.)
 * - Max trades per day
 * 
 * @module features/strategies/wizard/ExecutionSettingsStep
 */

import React, { useEffect, useState } from 'react';
import { Form, Select, InputNumber, Typography, Card, TimePicker } from 'antd';
import dayjs from 'dayjs';
import type { StrategyFormData, StepValidation } from '@/types/strategy';

const { Title, Paragraph } = Typography;
const { Option } = Select;

interface ExecutionSettingsStepProps {
  formData: StrategyFormData;
  onChange: (data: Partial<StrategyFormData>) => void;
  onValidationChange: (validation: StepValidation) => void;
}

export const ExecutionSettingsStep: React.FC<ExecutionSettingsStepProps> = ({
  formData,
  onChange,
  onValidationChange,
}) => {
  const [form] = Form.useForm();
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  /**
   * Validate execution settings
   */
  const validateForm = (): StepValidation => {
    const errors: Record<string, string> = {};
    const { executionSettings } = formData;
    
    if (!executionSettings.tradingHoursStart) {
      errors.tradingHoursStart = 'Start time is required';
    }
    
    if (!executionSettings.tradingHoursEnd) {
      errors.tradingHoursEnd = 'End time is required';
    }
    
    if (!executionSettings.executionFrequency) {
      errors.executionFrequency = 'Frequency is required';
    }
    
    if (!executionSettings.maxTradesPerDay || executionSettings.maxTradesPerDay <= 0) {
      errors.maxTradesPerDay = 'Must be at least 1';
    }
    
    setLocalErrors(errors);
    return {
      valid: Object.keys(errors).length === 0,
      errors,
    };
  };

  /**
   * Notify parent of validation changes
   */
  useEffect(() => {
    const validation = validateForm();
    onValidationChange(validation);
  }, [formData.executionSettings]);

  /**
   * Handle field changes
   */
  const handleFieldChange = (field: keyof typeof formData.executionSettings, value: unknown) => {
    onChange({
      executionSettings: {
        ...formData.executionSettings,
        [field]: value,
      },
    });
  };

  return (
    <div>
      <Title level={3}>Execution Settings</Title>
      <Paragraph type="secondary">
        Configure when and how often your strategy executes trades.
      </Paragraph>

      <Form form={form} layout="vertical" style={{ maxWidth: 600 }}>
        {/* Trading Hours */}
        <Card size="small" style={{ marginBottom: 16 }}>
          <Form.Item label="Trading Hours">
            <Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 12 }}>
              Strategy will only execute during these hours (Eastern Time)
            </Paragraph>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <Form.Item
                label="Start"
                style={{ flex: 1, marginBottom: 0 }}
                validateStatus={localErrors.tradingHoursStart ? 'error' : ''}
                help={localErrors.tradingHoursStart}
              >
                <TimePicker
                  value={dayjs(formData.executionSettings.tradingHoursStart, 'HH:mm')}
                  onChange={(time) => handleFieldChange('tradingHoursStart', time?.format('HH:mm') || '09:30')}
                  format="HH:mm"
                  style={{ width: '100%' }}
                />
              </Form.Item>
              <span style={{ paddingTop: 8 }}>to</span>
              <Form.Item
                label="End"
                style={{ flex: 1, marginBottom: 0 }}
                validateStatus={localErrors.tradingHoursEnd ? 'error' : ''}
                help={localErrors.tradingHoursEnd}
              >
                <TimePicker
                  value={dayjs(formData.executionSettings.tradingHoursEnd, 'HH:mm')}
                  onChange={(time) => handleFieldChange('tradingHoursEnd', time?.format('HH:mm') || '16:00')}
                  format="HH:mm"
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </div>
          </Form.Item>
        </Card>

        {/* Execution Frequency */}
        <Form.Item
          label="Execution Frequency"
          required
          validateStatus={localErrors.executionFrequency ? 'error' : ''}
          help={localErrors.executionFrequency || 'How often the strategy evaluates and executes trades'}
        >
          <Select
            value={formData.executionSettings.executionFrequency}
            onChange={val => handleFieldChange('executionFrequency', val)}
          >
            <Option value="realtime">Realtime (Tick-by-tick)</Option>
            <Option value="1min">Every 1 minute</Option>
            <Option value="5min">Every 5 minutes</Option>
            <Option value="15min">Every 15 minutes</Option>
            <Option value="1hour">Every hour</Option>
          </Select>
        </Form.Item>

        {/* Max Trades Per Day */}
        <Form.Item
          label="Max Trades Per Day"
          required
          validateStatus={localErrors.maxTradesPerDay ? 'error' : ''}
          help={localErrors.maxTradesPerDay || 'Maximum number of trades to execute in a single day'}
        >
          <InputNumber
            value={formData.executionSettings.maxTradesPerDay}
            onChange={val => handleFieldChange('maxTradesPerDay', val ?? 10)}
            min={1}
            max={1000}
            style={{ width: '100%' }}
          />
        </Form.Item>
      </Form>
    </div>
  );
};
