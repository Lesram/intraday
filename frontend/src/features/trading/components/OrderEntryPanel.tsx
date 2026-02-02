/**
 * Order Entry Panel
 * Professional trade ticket for submitting orders
 */

import React, { useState } from 'react';
import {
  Card,
  Form,
  Input,
  InputNumber,
  Button,
  Select,
  Space,
  Radio,
  Divider,
  App,
  Tooltip,
  Row,
  Col,
  Typography,
  Alert,
} from 'antd';
import {
  DollarOutlined,
  SwapOutlined,
  InfoCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useSubmitOrder } from '@/hooks/useData';
import type { OrderSide, OrderType, TimeInForce } from '@/store/ordersStore';

const { Title } = Typography;
const { Option } = Select;

interface OrderFormValues {
  symbol: string;
  side: OrderSide;
  orderType: OrderType;
  quantity: number;
  limitPrice?: number;
  stopPrice?: number;
  timeInForce: TimeInForce;
}

export const OrderEntryPanel: React.FC = () => {
  const { message } = App.useApp();
  const [form] = Form.useForm<OrderFormValues>();
  const [side, setSide] = useState<OrderSide>('buy');
  const [orderType, setOrderType] = useState<OrderType>('market');
  const { mutate: submitOrder, isPending } = useSubmitOrder();
  
  // Watch form values to avoid calling form.getFieldValue during render
  const symbolValue = Form.useWatch('symbol', form);

  const handleSubmit = async (values: OrderFormValues) => {
    try {
      await submitOrder(
        {
          symbol: values.symbol.toUpperCase(),
          side: values.side,
          orderType: values.orderType,
          quantity: values.quantity,
          limitPrice: values.limitPrice,
          stopPrice: values.stopPrice,
          timeInForce: values.timeInForce,
        },
        {
          onSuccess: () => {
            message.success(
              `${values.side.toUpperCase()} order for ${values.quantity} ${values.symbol} submitted successfully`
            );
            form.resetFields(['symbol', 'quantity', 'limitPrice', 'stopPrice']);
          },
          onError: (error: unknown) => {
            const err = error as { response?: { data?: { detail?: string } } };
            message.error(
              err?.response?.data?.detail || 'Failed to submit order'
            );
          },
        }
      );
    } catch (error) {
      console.error('Order submission error:', error);
    }
  };

  const handleSideChange = (newSide: OrderSide) => {
    setSide(newSide);
    // Form automatically updates via name prop - no need for setFieldValue
  };

  const handleOrderTypeChange = (newType: OrderType) => {
    setOrderType(newType);
    // Form automatically updates via name prop - no need for setFieldValue
  };

  const requiresLimitPrice = orderType === 'limit' || orderType === 'stop_limit';
  const requiresStopPrice = orderType === 'stop' || orderType === 'stop_limit';

  return (
    <Card
      title={
        <Space>
          <ThunderboltOutlined />
          <Title level={5} style={{ margin: 0 }}>
            Quick Trade
          </Title>
        </Space>
      }
      style={{ height: '100%' }}
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        preserve={false}
        initialValues={{
          side: 'buy',
          orderType: 'market',
          timeInForce: 'gtc',
          quantity: 1,
        }}
      >
        {/* Buy/Sell Toggle */}
        <Form.Item label="Side" name="side" required>
          <Radio.Group
            onChange={(e) => handleSideChange(e.target.value)}
            buttonStyle="solid"
            size="large"
            style={{ width: '100%' }}
          >
            <Radio.Button
              value="buy"
              style={{
                width: '50%',
                textAlign: 'center',
                backgroundColor: side === 'buy' ? '#52c41a' : undefined,
                borderColor: side === 'buy' ? '#52c41a' : undefined,
                color: side === 'buy' ? '#fff' : undefined,
              }}
            >
              <strong>BUY</strong>
            </Radio.Button>
            <Radio.Button
              value="sell"
              style={{
                width: '50%',
                textAlign: 'center',
                backgroundColor: side === 'sell' ? '#ff4d4f' : undefined,
                borderColor: side === 'sell' ? '#ff4d4f' : undefined,
                color: side === 'sell' ? '#fff' : undefined,
              }}
            >
              <strong>SELL</strong>
            </Radio.Button>
          </Radio.Group>
        </Form.Item>

        {/* Symbol Input */}
        <Form.Item
          label="Symbol"
          name="symbol"
          rules={[
            { required: true, message: 'Please enter a symbol' },
            {
              pattern: /^[A-Z]{1,5}$/i,
              message: 'Symbol must be 1-5 letters',
            },
          ]}
        >
          <Input
            placeholder="AAPL"
            size="large"
            style={{ textTransform: 'uppercase' }}
            prefix={<DollarOutlined />}
          />
        </Form.Item>

        {/* Order Type */}
        <Form.Item
          label={
            <Space>
              <span>Order Type</span>
              <Tooltip title="Market orders execute immediately at current price. Limit orders only execute at your specified price or better.">
                <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
              </Tooltip>
            </Space>
          }
          name="orderType"
        >
          <Select
            size="large"
            onChange={handleOrderTypeChange}
          >
            <Option value="market">Market</Option>
            <Option value="limit">Limit</Option>
            <Option value="stop">Stop</Option>
            <Option value="stop_limit">Stop Limit</Option>
          </Select>
        </Form.Item>

        <Row gutter={16}>
          {/* Quantity */}
          <Col span={12}>
            <Form.Item
              label="Quantity"
              name="quantity"
              rules={[
                { required: true, message: 'Required' },
                { type: 'number', min: 1, message: 'Min 1' },
              ]}
            >
              <InputNumber
                min={1}
                precision={0}
                size="large"
                style={{ width: '100%' }}
                placeholder="1"
              />
            </Form.Item>
          </Col>

          {/* Limit Price (if needed) */}
          {requiresLimitPrice && (
            <Col span={12}>
              <Form.Item
                label="Limit Price"
                name="limitPrice"
                rules={[
                  {
                    required: true,
                    message: 'Required for limit orders',
                  },
                  { type: 'number', min: 0.01, message: 'Min $0.01' },
                ]}
              >
                <InputNumber
                  min={0.01}
                  precision={2}
                  size="large"
                  style={{ width: '100%' }}
                  placeholder="0.00"
                  prefix="$"
                />
              </Form.Item>
            </Col>
          )}
        </Row>

        {/* Stop Price (if needed) */}
        {requiresStopPrice && (
          <Form.Item
            label="Stop Price"
            name="stopPrice"
            rules={[
              { required: true, message: 'Required for stop orders' },
              { type: 'number', min: 0.01, message: 'Min $0.01' },
            ]}
          >
            <InputNumber
              min={0.01}
              precision={2}
              size="large"
              style={{ width: '100%' }}
              placeholder="0.00"
              prefix="$"
            />
          </Form.Item>
        )}

        {/* Time in Force */}
        <Form.Item
          label={
            <Space>
              <span>Time in Force</span>
              <Tooltip title="GTC = Good 'til Cancelled, DAY = Day order, IOC = Immediate or Cancel, FOK = Fill or Kill">
                <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
              </Tooltip>
            </Space>
          }
          name="timeInForce"
        >
          <Select size="large">
            <Option value="gtc">GTC (Good 'Til Cancelled)</Option>
            <Option value="day">Day</Option>
            <Option value="ioc">IOC (Immediate or Cancel)</Option>
            <Option value="fok">FOK (Fill or Kill)</Option>
          </Select>
        </Form.Item>

        <Divider />

        {/* Market Warning for Market Orders */}
        {orderType === 'market' && (
          <Alert
            message="Market Order"
            description="This order will execute immediately at the current market price, which may differ from the displayed price."
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        {/* Submit Button */}
        <Form.Item style={{ marginBottom: 0 }}>
          <Button
            type="primary"
            htmlType="submit"
            size="large"
            block
            loading={isPending}
            icon={<SwapOutlined />}
            style={{
              backgroundColor: side === 'buy' ? '#52c41a' : '#ff4d4f',
              borderColor: side === 'buy' ? '#52c41a' : '#ff4d4f',
              height: 50,
              fontSize: 16,
              fontWeight: 'bold',
            }}
          >
            {side === 'buy' ? 'BUY' : 'SELL'} {symbolValue || 'STOCK'}
          </Button>
        </Form.Item>
      </Form>
    </Card>
  );
};
