/**
 * Basic Info Step - Step 1 of Strategy Builder
 * 
 * Collects:
 * - Strategy name (unique, required)
 * - Description (optional but recommended)
 * - Strategy type (template selector)
 * - Symbols to trade (multi-select with search)
 * 
 * @module features/strategies/wizard/BasicInfoStep
 */

import React, { useEffect, useState } from 'react';
import { Form, Input, Select, Card, Typography, Alert, Spin } from 'antd';
import type { StrategyFormData, StepValidation } from '@/types/strategy';
import { useStrategyTemplates } from '@/hooks/useStrategyTemplates';

const { TextArea } = Input;
const { Option } = Select;
const { Title, Paragraph } = Typography;

interface BasicInfoStepProps {
  formData: StrategyFormData;
  onChange: (data: Partial<StrategyFormData>) => void;
  onValidationChange: (validation: StepValidation) => void;
}

/**
 * Common stock symbols for quick selection
 */
const COMMON_SYMBOLS = [
  'AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META',
  'JPM', 'V', 'WMT', 'JNJ', 'PG', 'UNH', 'HD', 'BAC', 'DIS'
];

export const BasicInfoStep: React.FC<BasicInfoStepProps> = ({
  formData,
  onChange,
  onValidationChange,
}) => {
  const [form] = Form.useForm();
  const { data: templates, isLoading, error } = useStrategyTemplates();
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  /**
   * Validate form fields
   */
  const validateForm = (): StepValidation => {
    const errors: Record<string, string> = {};
    
    if (!formData.name || formData.name.trim().length === 0) {
      errors.name = 'Strategy name is required';
    } else if (formData.name.length < 3) {
      errors.name = 'Strategy name must be at least 3 characters';
    } else if (formData.name.length > 100) {
      errors.name = 'Strategy name must be less than 100 characters';
    }
    
    if (!formData.strategyType) {
      errors.strategyType = 'Strategy type is required';
    }
    
    if (!formData.symbols || formData.symbols.length === 0) {
      errors.symbols = 'At least one symbol is required';
    } else if (formData.symbols.length > 50) {
      errors.symbols = 'Maximum 50 symbols allowed';
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
  }, [formData.name, formData.strategyType, formData.symbols]);

  /**
   * Handle field changes
   */
  const handleFieldChange = (field: keyof StrategyFormData, value: unknown) => {
    onChange({ [field]: value });
  };

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        <Spin size="large" />
        <Paragraph style={{ marginTop: 16 }}>Loading strategy templates...</Paragraph>
      </div>
    );
  }

  if (error) {
    return (
      <Alert
        type="error"
        message="Failed to load strategy templates"
        description={error.message}
        showIcon
      />
    );
  }

  return (
    <div>
      <Title level={3}>Basic Information</Title>
      <Paragraph type="secondary">
        Start by naming your strategy, selecting a type, and choosing which symbols to trade.
      </Paragraph>

      <Form
        form={form}
        layout="vertical"
        initialValues={{
          name: formData.name,
          description: formData.description,
          strategyType: formData.strategyType,
          symbols: formData.symbols,
        }}
      >
        {/* Strategy Name */}
        <Form.Item
          label="Strategy Name"
          required
          validateStatus={localErrors.name ? 'error' : ''}
          help={localErrors.name}
        >
          <Input
            placeholder="e.g., AAPL Momentum Strategy"
            value={formData.name}
            onChange={e => handleFieldChange('name', e.target.value)}
            maxLength={100}
            showCount
          />
        </Form.Item>

        {/* Description */}
        <Form.Item
          label="Description"
          tooltip="Describe the strategy's logic, goals, and expected behavior"
        >
          <TextArea
            placeholder="e.g., Momentum strategy targeting AAPL with 20-day moving average crossovers"
            value={formData.description}
            onChange={e => handleFieldChange('description', e.target.value)}
            rows={3}
            maxLength={500}
            showCount
          />
        </Form.Item>

        {/* Strategy Type (Template Selector) */}
        <Form.Item
          label="Strategy Type"
          required
          validateStatus={localErrors.strategyType ? 'error' : ''}
          help={localErrors.strategyType}
          tooltip="Select a pre-configured template with appropriate parameters"
        >
          <Select
            placeholder="Select a strategy template"
            value={formData.strategyType}
            onChange={value => handleFieldChange('strategyType', value)}
            showSearch
            optionFilterProp="children"
          >
            {templates?.map(template => (
              <Option key={template.type} value={template.type}>
                <div>
                  <strong>{template.name}</strong>
                  <div style={{ fontSize: '12px', color: '#888' }}>
                    {template.description}
                  </div>
                </div>
              </Option>
            ))}
          </Select>
        </Form.Item>

        {/* Template Info Card */}
        {formData.strategyType && templates && (
          <Card size="small" style={{ marginBottom: 16, backgroundColor: '#f9f9f9' }}>
            {(() => {
              const selectedTemplate = templates.find(t => t.type === formData.strategyType);
              return selectedTemplate ? (
                <div>
                  <strong>{selectedTemplate.name}</strong>
                  <Paragraph type="secondary" style={{ marginBottom: 0, fontSize: '13px' }}>
                    {selectedTemplate.description}
                  </Paragraph>
                  <Paragraph type="secondary" style={{ marginBottom: 0, fontSize: '12px', marginTop: 8 }}>
                    <strong>Category:</strong> {selectedTemplate.category} | 
                    <strong> Parameters:</strong> {selectedTemplate.parameters.length}
                  </Paragraph>
                </div>
              ) : null;
            })()}
          </Card>
        )}

        {/* Symbols */}
        <Form.Item
          label="Symbols to Trade"
          required
          validateStatus={localErrors.symbols ? 'error' : ''}
          help={localErrors.symbols || `${formData.symbols.length} selected`}
          tooltip="Select one or more stock symbols to trade with this strategy"
        >
          <Select
            mode="tags"
            placeholder="Type or select symbols (e.g., AAPL, GOOGL)"
            value={formData.symbols}
            onChange={value => handleFieldChange('symbols', value)}
            tokenSeparators={[',', ' ']}
            style={{ width: '100%' }}
          >
            {COMMON_SYMBOLS.map(symbol => (
              <Option key={symbol} value={symbol}>
                {symbol}
              </Option>
            ))}
          </Select>
        </Form.Item>
      </Form>
    </div>
  );
};
