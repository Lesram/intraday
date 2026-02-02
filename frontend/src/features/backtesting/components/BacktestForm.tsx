/**
 * BacktestForm Component
 * 
 * Form for configuring and running a backtest on a trading strategy.
 * Allows users to set date ranges, initial capital, and optional parameter overrides.
 */

import React, { useState } from 'react';
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
  Alert
} from 'antd';
import { PlayCircleOutlined, SettingOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import type { BacktestRequest } from '../../../types/backtest';

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

  const handleSubmit = (values: Record<string, unknown>) => {
    const dateRange = values.dateRange as [Dayjs, Dayjs];
    const [startDate, endDate] = dateRange;
    
    const request: BacktestRequest = {
      strategy_id: values.strategyId as string,
      start_date: startDate.format('YYYY-MM-DD'),
      end_date: endDate.format('YYYY-MM-DD'),
      initial_capital: values.initialCapital as number,
    };

    if (useCustomParams && values.customParameters) {
      request.parameters = values.customParameters as Record<string, unknown>;
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
                </Space>
              ),
            },
          ]}
        />

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
