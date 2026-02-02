/**
 * Review Step - Step 5 of Strategy Builder
 * 
 * Final review of all configuration before submission.
 * Displays complete strategy configuration in organized sections.
 * 
 * @module features/strategies/wizard/ReviewStep
 */

import React from 'react';
import { Typography, Card, Descriptions, Tag, Space } from 'antd';
import type { StrategyFormData } from '@/types/strategy';
import { useStrategyTemplates } from '@/hooks/useStrategyTemplates';

const { Title, Paragraph } = Typography;

interface ReviewStepProps {
  formData: StrategyFormData;
}

export const ReviewStep: React.FC<ReviewStepProps> = ({ formData }) => {
  const { data: templates } = useStrategyTemplates();
  
  // Find the template to show the display name
  const selectedTemplate = templates?.find(t => t.type === formData.strategyType);
  const strategyTypeName = selectedTemplate?.name || formData.strategyType;
  
  return (
    <div>
      <Title level={3}>Review & Confirm</Title>
      <Paragraph type="secondary">
        Review your strategy configuration before creating. You can go back to edit any section.
      </Paragraph>

      {/* Basic Info */}
      <Card title="Basic Information" size="small" style={{ marginBottom: 16 }}>
        <Descriptions column={1}>
          <Descriptions.Item label="Strategy Name">
            <strong>{formData.name}</strong>
          </Descriptions.Item>
          <Descriptions.Item label="Description">
            {formData.description || <em>No description provided</em>}
          </Descriptions.Item>
          <Descriptions.Item label="Strategy Type">
            <Tag color="blue">{strategyTypeName}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Symbols">
            <Space size={[0, 8]} wrap>
              {formData.symbols.map(symbol => (
                <Tag key={symbol}>{symbol}</Tag>
              ))}
            </Space>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Parameters */}
      <Card title="Strategy Parameters" size="small" style={{ marginBottom: 16 }}>
        <Descriptions column={2}>
          {Object.entries(formData.parameters).map(([key, value]) => (
            <Descriptions.Item label={key} key={key}>
              {typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)}
            </Descriptions.Item>
          ))}
        </Descriptions>
        {Object.keys(formData.parameters).length === 0 && (
          <Paragraph type="secondary">No custom parameters configured</Paragraph>
        )}
      </Card>

      {/* Risk Limits */}
      <Card title="Risk Management" size="small" style={{ marginBottom: 16 }}>
        <Descriptions column={2}>
          <Descriptions.Item label="Max Position Size">
            ${formData.riskLimits.maxPositionSize.toLocaleString()}
          </Descriptions.Item>
          <Descriptions.Item label="Daily Loss Limit">
            ${formData.riskLimits.dailyLossLimit.toLocaleString()}
          </Descriptions.Item>
          <Descriptions.Item label="Max Drawdown">
            {(formData.riskLimits.maxDrawdown * 100).toFixed(1)}%
          </Descriptions.Item>
          <Descriptions.Item label="Stop Loss">
            {(formData.riskLimits.stopLoss * 100).toFixed(1)}%
          </Descriptions.Item>
          <Descriptions.Item label="Take Profit">
            {(formData.riskLimits.takeProfit * 100).toFixed(1)}%
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Execution Settings */}
      <Card title="Execution Settings" size="small" style={{ marginBottom: 16 }}>
        <Descriptions column={2}>
          <Descriptions.Item label="Trading Hours">
            {formData.executionSettings.tradingHoursStart} - {formData.executionSettings.tradingHoursEnd} ET
          </Descriptions.Item>
          <Descriptions.Item label="Execution Frequency">
            {formData.executionSettings.executionFrequency}
          </Descriptions.Item>
          <Descriptions.Item label="Max Trades Per Day">
            {formData.executionSettings.maxTradesPerDay}
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  );
};
