/**
 * Parameters Step - Step 2 of Strategy Builder
 * 
 * Dynamically renders parameter form based on selected strategy type.
 * Loads template definition and creates appropriate input controls for each parameter.
 * 
 * @module features/strategies/wizard/ParametersStep
 */

import React, { useEffect, useState } from 'react';
import { Form, InputNumber, Select, Switch, Typography, Alert, Spin, Slider } from 'antd';
import type { StrategyFormData, StepValidation, ParameterDefinition } from '@/types/strategy';
import { useStrategyTemplate, getDefaultParameters } from '@/hooks/useStrategyTemplates';

const { Title, Paragraph } = Typography;
const { Option } = Select;

interface ParametersStepProps {
  formData: StrategyFormData;
  onChange: (data: Partial<StrategyFormData>) => void;
  onValidationChange: (validation: StepValidation) => void;
}

export const ParametersStep: React.FC<ParametersStepProps> = ({
  formData,
  onChange,
  onValidationChange,
}) => {
  const [form] = Form.useForm();
  const { data: template, isLoading } = useStrategyTemplate(formData.strategyType);
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  /**
   * Initialize parameters with template defaults when template loads
   */
  useEffect(() => {
    if (template && Object.keys(formData.parameters).length === 0) {
      const defaults = getDefaultParameters(template);
      onChange({ parameters: defaults });
    }
  }, [template]);

  /**
   * Validate parameter values
   */
  const validateParameters = (): StepValidation => {
    const errors: Record<string, string> = {};
    
    if (!template) {
      errors.template = 'Strategy type not selected';
      return { valid: false, errors };
    }

    // Validate each parameter
    template.parameters.forEach((param: ParameterDefinition) => {
      const value = formData.parameters[param.name];
      
      // Check required
      if (param.required && (value === undefined || value === null || value === '')) {
        errors[param.name] = `${param.label || param.name} is required`;
        return;
      }
      
      // Validate number constraints
      if (param.type === 'number' && value !== undefined && value !== null) {
        const numValue = value as number;
        if (param.min !== undefined && numValue < param.min) {
          errors[param.name] = `Must be at least ${param.min}`;
        }
        if (param.max !== undefined && numValue > param.max) {
          errors[param.name] = `Must be at most ${param.max}`;
        }
      }
    });
    
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
    if (template) {
      const validation = validateParameters();
      onValidationChange(validation);
    }
  }, [formData.parameters, template]);

  /**
   * Handle parameter value changes
   */
  const handleParameterChange = (paramName: string, value: unknown) => {
    onChange({
      parameters: {
        ...formData.parameters,
        [paramName]: value,
      },
    });
  };

  /**
   * Render input control based on parameter type
   */
  const renderParameterInput = (param: ParameterDefinition) => {
    const rawValue = formData.parameters[param.name] ?? param.default;

    switch (param.type) {
      case 'number': {
        const value = (typeof rawValue === 'number' ? rawValue : param.default) as number | undefined;
        // If min/max are defined and range is reasonable, use slider + input
        if (param.min !== undefined && param.max !== undefined && (param.max - param.min) <= 1000) {
          return (
            <div>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <Slider
                  min={param.min}
                  max={param.max}
                  value={value}
                  onChange={val => handleParameterChange(param.name, val)}
                  style={{ flex: 1 }}
                  step={param.max - param.min > 100 ? 1 : 0.01}
                />
                <InputNumber<number>
                  min={param.min}
                  max={param.max}
                  value={value}
                  onChange={val => handleParameterChange(param.name, val ?? param.default)}
                  style={{ width: 120 }}
                  step={param.max - param.min > 100 ? 1 : 0.01}
                />
              </div>
              <div style={{ fontSize: '12px', color: '#888', marginTop: 4 }}>
                Range: {param.min} - {param.max}
              </div>
            </div>
          );
        } else {
          // Otherwise just input
          return (
            <div>
              <InputNumber<number>
                min={param.min}
                max={param.max}
                value={value}
                onChange={val => handleParameterChange(param.name, val ?? param.default)}
                style={{ width: '100%' }}
              />
              {(param.min !== undefined || param.max !== undefined) && (
                <div style={{ fontSize: '12px', color: '#888', marginTop: 4 }}>
                  {param.min !== undefined && `Min: ${param.min}`}
                  {param.min !== undefined && param.max !== undefined && ' | '}
                  {param.max !== undefined && `Max: ${param.max}`}
                </div>
              )}
            </div>
          );
        }
      }

      case 'select':
        return (
          <Select
            value={rawValue as string | undefined}
            onChange={val => handleParameterChange(param.name, val)}
            style={{ width: '100%' }}
            placeholder={`Select ${param.label || param.name}`}
          >
            {param.options?.map(opt => (
              <Option key={opt.value} value={opt.value}>
                {opt.label}
              </Option>
            ))}
          </Select>
        );

      case 'multiselect':
        return (
          <Select
            mode="multiple"
            value={rawValue as string[] | undefined}
            onChange={val => handleParameterChange(param.name, val)}
            style={{ width: '100%' }}
            placeholder={`Select ${param.label || param.name}`}
          >
            {param.options?.map(opt => (
              <Option key={opt.value} value={opt.value}>
                {opt.label}
              </Option>
            ))}
          </Select>
        );

      case 'boolean':
        return (
          <Switch
            checked={rawValue as boolean | undefined}
            onChange={val => handleParameterChange(param.name, val)}
          />
        );

      case 'string':
      default:
        return (
          <input
            type="text"
            value={(rawValue as string) ?? ''}
            onChange={e => handleParameterChange(param.name, e.target.value)}
            style={{ width: '100%' }}
          />
        );
    }
  };

  if (!formData.strategyType) {
    return (
      <Alert
        type="warning"
        message="Strategy Type Required"
        description="Please go back and select a strategy type first."
        showIcon
      />
    );
  }

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        <Spin size="large" />
        <Paragraph style={{ marginTop: 16 }}>Loading parameters for {formData.strategyType}...</Paragraph>
      </div>
    );
  }

  if (!template) {
    return (
      <Alert
        type="error"
        message="Template Not Found"
        description={`Could not load parameters for strategy type: ${formData.strategyType}`}
        showIcon
      />
    );
  }

  return (
    <div>
      <Title level={3}>{template.name} Parameters</Title>
      <Paragraph type="secondary">
        {template.description}
      </Paragraph>

      <Form form={form} layout="vertical" style={{ maxWidth: 800 }}>
        {template.parameters.map((param: ParameterDefinition) => (
          <Form.Item
            key={param.name}
            label={param.label || param.name}
            required={param.required}
            validateStatus={localErrors[param.name] ? 'error' : ''}
            help={localErrors[param.name] || param.description}
            tooltip={param.description}
          >
            {renderParameterInput(param)}
          </Form.Item>
        ))}
      </Form>
    </div>
  );
};
