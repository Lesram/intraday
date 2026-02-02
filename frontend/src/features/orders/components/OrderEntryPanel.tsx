/**
 * Order Entry Panel
 * Component for submitting trading orders with full order ticket functionality
 * 
 * Features:
 * - Pre-trade validation before order submission
 * - Order preview modal with validation checks
 * - Risk impact analysis
 * - Real-time form validation
 */

import { useState } from 'react';
import { 
  Card, 
  Form, 
  Input, 
  InputNumber, 
  Button, 
  Select, 
  Radio, 
  Space, 
  Divider,
  Typography,
  Alert,
  Row,
  Col,
  message
} from 'antd';
import { 
  DollarOutlined, 
  RiseOutlined, 
  FallOutlined,
  ThunderboltOutlined,
  EyeOutlined
} from '@ant-design/icons';
import { useSubmitOrder } from '@/hooks/useData';
import { colors } from '@/styles/theme';
import type { OrderSide, OrderType } from '@/store/ordersStore';
import { usePreTradeValidation } from '@/features/trading/hooks/usePreTradeValidation';
import { OrderPreview } from '@/features/trading/components/OrderPreview';
import { PreTradeChecksCompact } from '@/features/trading/components/PreTradeChecks';
import type { OrderFormData } from '@/types/trading';
import { MarketStatusBanner } from '@/components/market/MarketStatusBanner';
import { getRecommendedTIF } from '@/utils/marketHours';

const { Title, Text } = Typography;
const { Option } = Select;

interface OrderEntryPanelProps {
  defaultSymbol?: string;
  onOrderSubmitted?: () => void;
}

export const OrderEntryPanel: React.FC<OrderEntryPanelProps> = ({
  defaultSymbol = '',
  onOrderSubmitted,
}) => {
  const [form] = Form.useForm();
  const [side, setSide] = useState<OrderSide>('buy');
  const [orderType, setOrderType] = useState<OrderType>('market');
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [orderDataForPreview, setOrderDataForPreview] = useState<OrderFormData | null>(null);
  
  const submitOrderMutation = useSubmitOrder();
  const validation = usePreTradeValidation();

  // Calculate estimated cost
  const quantity = Form.useWatch('quantity', form);
  const limitPrice = Form.useWatch('limitPrice', form);
  
  const estimatedCost = quantity && limitPrice ? quantity * limitPrice : 0;

  // Handle preview order (validate before showing modal)
  const handlePreviewOrder = async () => {
    try {
      // Validate form fields first
      const values = await form.validateFields();
      
      // Prepare order data
      const orderData: OrderFormData = {
        symbol: values.symbol.toUpperCase(),
        side,
        orderType,
        quantity: values.quantity,
        limitPrice: orderType === 'limit' || orderType === 'stop_limit' ? values.limitPrice : undefined,
        stopPrice: orderType === 'stop' || orderType === 'stop_limit' ? values.stopPrice : undefined,
        timeInForce: values.timeInForce || 'day',
      };
      
      // Store order data for preview
      setOrderDataForPreview(orderData);
      
      // Trigger validation
      validation.mutate(orderData, {
        onSuccess: () => {
          // Open modal regardless of validation result (user can see what's wrong)
          setPreviewModalOpen(true);
        },
        onError: (error) => {
          message.error('Failed to validate order. Please try again.');
          console.error('Validation error:', error);
        },
      });
    } catch (error) {
      // Form validation failed
      console.error('Form validation failed:', error);
    }
  };

  // Handle order confirmation from modal
  const handleConfirmOrder = async () => {
    if (!orderDataForPreview) return;
    
    try {
      await submitOrderMutation.mutateAsync({
        symbol: orderDataForPreview.symbol,
        side: orderDataForPreview.side,
        orderType: orderDataForPreview.orderType,
        quantity: orderDataForPreview.quantity,
        limitPrice: orderDataForPreview.limitPrice,
        stopPrice: orderDataForPreview.stopPrice,
        timeInForce: orderDataForPreview.timeInForce,
      });

      // Close modal
      setPreviewModalOpen(false);
      
      // Reset form on success
      form.resetFields();
      setOrderType('market');
      setOrderDataForPreview(null);
      
      // Show success message
      message.success('Order submitted successfully!');
      
      // Callback
      onOrderSubmitted?.();
    } catch (error) {
      // Error is handled by react-query
      console.error('Order submission failed:', error);
      message.error('Failed to submit order. Please try again.');
    }
  };

  // Handle modal cancel
  const handleCancelPreview = () => {
    setPreviewModalOpen(false);
  };

  return (
    <>
      <Card 
        style={{ 
          background: colors.backgrounds.secondary,
          border: `1px solid ${colors.backgrounds.border}`,
        }}
      >
        <Title level={4} style={{ color: colors.text.primary, marginTop: 0 }}>
          <ThunderboltOutlined /> Order Entry
        </Title>

        {/* Market Status Banner */}
        <MarketStatusBanner />

        <Form
          form={form}
          layout="vertical"
          initialValues={{
            symbol: defaultSymbol,
            quantity: 1,
            timeInForce: getRecommendedTIF(), // Smart default based on market hours
          }}
        >
        {/* Side Selector */}
        <Form.Item label={<Text style={{ color: colors.text.secondary }}>Side</Text>}>
          <Radio.Group
            value={side}
            onChange={(e) => setSide(e.target.value)}
            buttonStyle="solid"
            size="large"
            style={{ width: '100%' }}
          >
            <Radio.Button 
              value="buy" 
              style={{ 
                width: '50%',
                textAlign: 'center',
                backgroundColor: side === 'buy' ? colors.semantic.profit : undefined,
                borderColor: side === 'buy' ? colors.semantic.profit : undefined,
              }}
            >
              <RiseOutlined /> BUY
            </Radio.Button>
            <Radio.Button 
              value="sell" 
              style={{ 
                width: '50%',
                textAlign: 'center',
                backgroundColor: side === 'sell' ? colors.semantic.loss : undefined,
                borderColor: side === 'sell' ? colors.semantic.loss : undefined,
              }}
            >
              <FallOutlined /> SELL
            </Radio.Button>
          </Radio.Group>
        </Form.Item>

        {/* Symbol Input */}
        <Form.Item
          name="symbol"
          label={<Text style={{ color: colors.text.secondary }}>Symbol</Text>}
          rules={[
            { required: true, message: 'Please enter a symbol' },
            { pattern: /^[A-Z]{1,10}$/i, message: 'Invalid symbol format' },
          ]}
        >
          <Input 
            placeholder="AAPL" 
            size="large"
            style={{ 
              textTransform: 'uppercase',
              fontWeight: 'bold',
              fontFamily: 'monospace',
            }}
          />
        </Form.Item>

        {/* Order Type */}
        <Form.Item
          label={<Text style={{ color: colors.text.secondary }}>Order Type</Text>}
        >
          <Select
            value={orderType}
            onChange={setOrderType}
            size="large"
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
              name="quantity"
              label={<Text style={{ color: colors.text.secondary }}>Quantity</Text>}
              rules={[
                { required: true, message: 'Required' },
                { type: 'number', min: 1, message: 'Must be >= 1' },
              ]}
            >
              <InputNumber
                min={1}
                max={10000}
                size="large"
                style={{ width: '100%' }}
                placeholder="100"
              />
            </Form.Item>
          </Col>

          {/* Limit Price (for limit orders) */}
          {(orderType === 'limit' || orderType === 'stop_limit') && (
            <Col span={12}>
              <Form.Item
                name="limitPrice"
                label={<Text style={{ color: colors.text.secondary }}>Limit Price</Text>}
                rules={[
                  { required: true, message: 'Required' },
                  { type: 'number', min: 0.01, message: 'Must be > 0' },
                ]}
              >
                <InputNumber
                  min={0.01}
                  step={0.01}
                  precision={2}
                  size="large"
                  style={{ width: '100%' }}
                  placeholder="150.00"
                  prefix={<DollarOutlined />}
                />
              </Form.Item>
            </Col>
          )}

          {/* Stop Price (for stop orders) */}
          {(orderType === 'stop' || orderType === 'stop_limit') && (
            <Col span={12}>
              <Form.Item
                name="stopPrice"
                label={<Text style={{ color: colors.text.secondary }}>Stop Price</Text>}
                rules={[
                  { required: true, message: 'Required' },
                  { type: 'number', min: 0.01, message: 'Must be > 0' },
                ]}
              >
                <InputNumber
                  min={0.01}
                  step={0.01}
                  precision={2}
                  size="large"
                  style={{ width: '100%' }}
                  placeholder="145.00"
                  prefix={<DollarOutlined />}
                />
              </Form.Item>
            </Col>
          )}
        </Row>

        {/* Time in Force */}
        <Form.Item
          name="timeInForce"
          label={<Text style={{ color: colors.text.secondary }}>Time in Force</Text>}
        >
          <Select size="large">
            <Option value="day">Day</Option>
            <Option value="gtc">Good Till Cancel (GTC)</Option>
            <Option value="ioc">Immediate or Cancel (IOC)</Option>
            <Option value="fok">Fill or Kill (FOK)</Option>
          </Select>
        </Form.Item>

        {/* Estimated Cost Display */}
        {orderType === 'limit' && estimatedCost > 0 && (
          <Alert
            message={
              <Space>
                <Text>Estimated Cost:</Text>
                <Text strong style={{ fontFamily: 'monospace' }}>
                  ${estimatedCost.toFixed(2)}
                </Text>
              </Space>
            }
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}

        {/* Inline Validation Display (Compact) */}
        {validation.data && !previewModalOpen && (
          <div style={{ marginBottom: 16 }}>
            <PreTradeChecksCompact
              validationResult={validation.data}
              loading={validation.isPending}
            />
          </div>
        )}

        {/* Error Display */}
        {validation.isError && (
          <Alert
            message="Validation Failed"
            description={
              validation.error instanceof Error
                ? validation.error.message
                : 'Failed to validate order. Please try again.'
            }
            type="error"
            showIcon
            closable
            onClose={() => validation.reset()}
            style={{ marginBottom: 16 }}
          />
        )}

        <Divider />

        {/* Preview Order Button */}
        <Form.Item style={{ marginBottom: 0 }}>
          <Button
            type="primary"
            size="large"
            block
            icon={<EyeOutlined />}
            loading={validation.isPending}
            onClick={handlePreviewOrder}
            style={{
              backgroundColor: side === 'buy' ? colors.semantic.profit : colors.semantic.loss,
              borderColor: side === 'buy' ? colors.semantic.profit : colors.semantic.loss,
              fontWeight: 'bold',
            }}
          >
            Preview & Validate Order
          </Button>
        </Form.Item>

        {/* Order Type Info */}
        <div style={{ marginTop: 12, textAlign: 'center' }}>
          <Text type="secondary" style={{ fontSize: '12px' }}>
            {orderType === 'market' && 'Executes immediately at current market price'}
            {orderType === 'limit' && 'Executes only at specified limit price or better'}
            {orderType === 'stop' && 'Converts to market order when stop price is reached'}
            {orderType === 'stop_limit' && 'Converts to limit order when stop price is reached'}
          </Text>
        </div>
      </Form>
    </Card>

    {/* Order Preview Modal */}
    {orderDataForPreview && (
      <OrderPreview
        open={previewModalOpen}
        orderData={orderDataForPreview}
        validationResult={validation.data ?? null}
        validating={validation.isPending}
        submitting={submitOrderMutation.isPending}
        onCancel={handleCancelPreview}
        onConfirm={handleConfirmOrder}
      />
    )}
  </>
  );
};
