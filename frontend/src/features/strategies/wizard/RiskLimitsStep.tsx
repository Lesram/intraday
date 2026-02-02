/**
 * Risk Limits Step - Step 3 of Strategy Builder
 * 
 * Configures risk management parameters:
 * - Position size limits
 * - Loss limits (daily/max drawdown)
 * - Stop loss / Take profit percentages
 * 
 * @module features/strategies/wizard/RiskLimitsStep
 */

import React, { useEffect, useState } from 'react';
import { Form, InputNumber, Typography, Card, Row, Col, Slider } from 'antd';
import type { StrategyFormData, StepValidation } from '@/types/strategy';

const { Title, Paragraph, Text } = Typography;

interface RiskLimitsStepProps {
  formData: StrategyFormData;
  onChange: (data: Partial<StrategyFormData>) => void;
  onValidationChange: (validation: StepValidation) => void;
}

export const RiskLimitsStep: React.FC<RiskLimitsStepProps> = ({
  formData,
  onChange,
  onValidationChange,
}) => {
  const [form] = Form.useForm();
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  /**
   * Validate risk limits
   */
  const validateForm = (): StepValidation => {
    const errors: Record<string, string> = {};
    const { riskLimits } = formData;
    
    if (!riskLimits.maxPositionSize || riskLimits.maxPositionSize <= 0) {
      errors.maxPositionSize = 'Must be greater than 0';
    }
    
    if (!riskLimits.dailyLossLimit || riskLimits.dailyLossLimit <= 0) {
      errors.dailyLossLimit = 'Must be greater than 0';
    }
    
    if (riskLimits.maxDrawdown <= 0 || riskLimits.maxDrawdown >= 1) {
      errors.maxDrawdown = 'Must be between 0% and 100%';
    }
    
    if (riskLimits.stopLoss <= 0 || riskLimits.stopLoss >= 1) {
      errors.stopLoss = 'Must be between 0% and 100%';
    }
    
    if (riskLimits.takeProfit <= 0 || riskLimits.takeProfit >= 2) {
      errors.takeProfit = 'Must be between 0% and 200%';
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
  }, [formData.riskLimits]);

  /**
   * Handle field changes
   */
  const handleFieldChange = (field: keyof typeof formData.riskLimits, value: number | null) => {
    onChange({
      riskLimits: {
        ...formData.riskLimits,
        [field]: value ?? 0,
      },
    });
  };

  return (
    <div>
      <Title level={3}>Risk Management</Title>
      <Paragraph type="secondary">
        Configure risk limits to protect your capital. These limits will automatically stop or limit trading
        when thresholds are reached.
      </Paragraph>

      <Form form={form} layout="vertical" style={{ maxWidth: 800 }}>
        <Row gutter={24}>
          {/* Position Size Limit */}
          <Col span={12}>
            <Card size="small" style={{ marginBottom: 16 }}>
              <Form.Item
                label="Max Position Size"
                required
                validateStatus={localErrors.maxPositionSize ? 'error' : ''}
                help={localErrors.maxPositionSize || 'Maximum dollar value for a single position'}
              >
                <InputNumber
                  value={formData.riskLimits.maxPositionSize}
                  onChange={val => handleFieldChange('maxPositionSize', val)}
                  formatter={value => `$ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={(value) => value?.replace(/\$\s?|(,*)/g, '') as unknown as number}
                  min={100}
                  max={1000000}
                  step={1000}
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </Card>
          </Col>

          {/* Daily Loss Limit */}
          <Col span={12}>
            <Card size="small" style={{ marginBottom: 16 }}>
              <Form.Item
                label="Daily Loss Limit"
                required
                validateStatus={localErrors.dailyLossLimit ? 'error' : ''}
                help={localErrors.dailyLossLimit || 'Max loss per day (trading pauses if reached)'}
              >
                <InputNumber
                  value={formData.riskLimits.dailyLossLimit}
                  onChange={val => handleFieldChange('dailyLossLimit', val)}
                  formatter={value => `$ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={(value) => value?.replace(/\$\s?|(,*)/g, '') as unknown as number}
                  min={10}
                  max={100000}
                  step={100}
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </Card>
          </Col>
        </Row>

        {/* Max Drawdown */}
        <Card size="small" style={{ marginBottom: 16 }}>
          <Form.Item
            label="Maximum Drawdown"
            required
            validateStatus={localErrors.maxDrawdown ? 'error' : ''}
            help={localErrors.maxDrawdown || 'Maximum portfolio decline from peak (strategy stops if exceeded)'}
          >
            <Row gutter={12}>
              <Col span={18}>
                <Slider
                  min={1}
                  max={50}
                  value={formData.riskLimits.maxDrawdown * 100}
                  onChange={val => handleFieldChange('maxDrawdown', val / 100)}
                  marks={{
                    5: '5%',
                    10: '10%',
                    15: '15%',
                    20: '20%',
                    30: '30%',
                    50: '50%',
                  }}
                />
              </Col>
              <Col span={6}>
                <InputNumber
                  min={1}
                  max={50}
                  value={formData.riskLimits.maxDrawdown * 100}
                  onChange={val => handleFieldChange('maxDrawdown', (val ?? 15) / 100)}
                  formatter={value => `${value}%`}
                  parser={(value) => value?.replace('%', '') as unknown as number}
                  style={{ width: '100%' }}
                />
              </Col>
            </Row>
          </Form.Item>
        </Card>

        <Row gutter={24}>
          {/* Stop Loss */}
          <Col span={12}>
            <Card size="small" style={{ marginBottom: 16 }}>
              <Form.Item
                label="Stop Loss"
                required
                validateStatus={localErrors.stopLoss ? 'error' : ''}
                help={localErrors.stopLoss || 'Exit position if price drops by this percentage'}
              >
                <Row gutter={12}>
                  <Col span={16}>
                    <Slider
                      min={1}
                      max={20}
                      value={formData.riskLimits.stopLoss * 100}
                      onChange={val => handleFieldChange('stopLoss', val / 100)}
                    />
                  </Col>
                  <Col span={8}>
                    <InputNumber
                      min={1}
                      max={20}
                      value={formData.riskLimits.stopLoss * 100}
                      onChange={val => handleFieldChange('stopLoss', (val ?? 5) / 100)}
                      formatter={value => `${value}%`}
                      parser={(value) => value?.replace('%', '') as unknown as number}
                      style={{ width: '100%' }}
                    />
                  </Col>
                </Row>
              </Form.Item>
            </Card>
          </Col>

          {/* Take Profit */}
          <Col span={12}>
            <Card size="small" style={{ marginBottom: 16 }}>
              <Form.Item
                label="Take Profit"
                required
                validateStatus={localErrors.takeProfit ? 'error' : ''}
                help={localErrors.takeProfit || 'Exit position if price rises by this percentage'}
              >
                <Row gutter={12}>
                  <Col span={16}>
                    <Slider
                      min={1}
                      max={50}
                      value={formData.riskLimits.takeProfit * 100}
                      onChange={val => handleFieldChange('takeProfit', val / 100)}
                    />
                  </Col>
                  <Col span={8}>
                    <InputNumber
                      min={1}
                      max={50}
                      value={formData.riskLimits.takeProfit * 100}
                      onChange={val => handleFieldChange('takeProfit', (val ?? 10) / 100)}
                      formatter={value => `${value}%`}
                      parser={(value) => value?.replace('%', '') as unknown as number}
                      style={{ width: '100%' }}
                    />
                  </Col>
                </Row>
              </Form.Item>
            </Card>
          </Col>
        </Row>

        {/* Summary Card */}
        <Card 
          size="small" 
          style={{ 
            backgroundColor: '#e6f4ff', 
            marginTop: 16,
            border: '2px solid #1890ff'
          }}
        >
          <Title level={5} style={{ marginTop: 0, marginBottom: 16, color: '#000' }}>
            Risk Summary
          </Title>
          <Row gutter={16}>
            <Col span={12}>
              <Text style={{ color: '#000', fontSize: '14px' }}>Max Position Size:</Text>
              <br />
              <Text strong style={{ fontSize: '18px', color: '#000' }}>
                ${formData.riskLimits.maxPositionSize.toLocaleString()}
              </Text>
            </Col>
            <Col span={12}>
              <Text style={{ color: '#000', fontSize: '14px' }}>Daily Loss Limit:</Text>
              <br />
              <Text strong style={{ fontSize: '18px', color: '#000' }}>
                ${formData.riskLimits.dailyLossLimit.toLocaleString()}
              </Text>
            </Col>
          </Row>
          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={8}>
              <Text style={{ color: '#000', fontSize: '14px' }}>Max Drawdown:</Text>
              <br />
              <Text strong style={{ fontSize: '18px', color: '#d32029' }}>
                {(formData.riskLimits.maxDrawdown * 100).toFixed(1)}%
              </Text>
            </Col>
            <Col span={8}>
              <Text style={{ color: '#000', fontSize: '14px' }}>Stop Loss:</Text>
              <br />
              <Text strong style={{ fontSize: '18px', color: '#d32029' }}>
                {(formData.riskLimits.stopLoss * 100).toFixed(1)}%
              </Text>
            </Col>
            <Col span={8}>
              <Text style={{ color: '#000', fontSize: '14px' }}>Take Profit:</Text>
              <br />
              <Text strong style={{ fontSize: '18px', color: '#52c41a' }}>
                {(formData.riskLimits.takeProfit * 100).toFixed(1)}%
              </Text>
            </Col>
          </Row>
        </Card>
      </Form>
    </div>
  );
};
