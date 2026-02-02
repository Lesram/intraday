/**
 * OrderPreview Modal Component
 * 
 * Modal dialog for previewing and confirming orders before submission.
 * Displays order details, pre-trade validation checks, cost breakdown,
 * and risk impact.
 * 
 * Features:
 * - Order summary (symbol, side, quantity, type, price)
 * - Embedded PreTradeChecks component
 * - Cost breakdown visualization
 * - Risk impact display
 * - Confirm button (disabled if validation fails)
 * - Cancel button
 * - Loading states
 * - Responsive design
 * - Accessible (keyboard navigation, ARIA labels)
 * 
 * Integration:
 * - Follows PHASE_2_1_COMPREHENSIVE_ANALYSIS.md Section 7, Phase 4
 * - Uses types from @/types/trading
 * - Integrates PreTradeChecks component
 * - Uses theme colors from @/styles/theme
 * - Matches existing modal patterns
 */

import React from 'react';
import {
  Modal,
  Space,
  Typography,
  Row,
  Col,
  Divider,
  Statistic,
  Button,
  Tag,
  Card,
  Descriptions,
  Alert
} from 'antd';
import {
  DollarOutlined,
  RiseOutlined,
  FallOutlined,
  ShoppingOutlined,
  WarningOutlined,
  CheckCircleOutlined
} from '@ant-design/icons';
import { colors } from '@/styles/theme';
import { PreTradeChecks } from './PreTradeChecks';
import type { 
  OrderValidationResponse,
  OrderFormData 
} from '@/types/trading';
import { formatCurrency } from '@/types/trading';

const { Title, Text, Paragraph } = Typography;

interface OrderPreviewProps {
  /** Whether the modal is visible */
  open: boolean;
  
  /** Order data to preview */
  orderData: OrderFormData;
  
  /** Validation result from backend */
  validationResult: OrderValidationResponse | null;
  
  /** Loading state while validating */
  validating?: boolean;
  
  /** Loading state while submitting order */
  submitting?: boolean;
  
  /** Callback when modal is closed/cancelled */
  onCancel: () => void;
  
  /** Callback when order is confirmed */
  onConfirm: () => void;
}

/**
 * Order Summary Section
 * Displays key order details in a clean format
 */
const OrderSummary: React.FC<{ orderData: OrderFormData }> = ({ orderData }) => {
  const { symbol, side, quantity, orderType, limitPrice, stopPrice, timeInForce } = orderData;
  
  // Side-specific icon
  const SideIcon = side === 'buy' ? RiseOutlined : FallOutlined;
  
  return (
    <Card 
      size="small"
      style={{ 
        backgroundColor: colors.backgrounds.tertiary,
        borderColor: colors.backgrounds.border,
      }}
    >
      <Space direction="vertical" size="small" style={{ width: '100%' }}>
        {/* Header: Symbol and Side */}
        <Row justify="space-between" align="middle">
          <Col>
            <Space>
              <Title level={4} style={{ margin: 0, color: colors.text.primary }}>
                {symbol}
              </Title>
              <Tag 
                color={side === 'buy' ? 'success' : 'error'} 
                icon={<SideIcon />}
                style={{ fontSize: '14px', padding: '4px 12px' }}
              >
                {side.toUpperCase()}
              </Tag>
            </Space>
          </Col>
          <Col>
            <Text style={{ fontSize: '12px', color: colors.text.tertiary }}>
              {orderType.toUpperCase().replace('_', ' ')}
            </Text>
          </Col>
        </Row>

        <Divider style={{ margin: '8px 0' }} />

        {/* Order Details */}
        <Descriptions 
          column={2} 
          size="small"
          styles={{
            label: { color: colors.text.secondary },
            content: { color: colors.text.primary, fontWeight: 500 }
          }}
        >
          <Descriptions.Item label="Quantity">
            {quantity.toLocaleString()}
          </Descriptions.Item>
          
          {limitPrice && (
            <Descriptions.Item label="Limit Price">
              {formatCurrency(limitPrice)}
            </Descriptions.Item>
          )}
          
          {stopPrice && (
            <Descriptions.Item label="Stop Price">
              {formatCurrency(stopPrice)}
            </Descriptions.Item>
          )}
          
          {timeInForce && (
            <Descriptions.Item label="Time in Force">
              {timeInForce.toUpperCase()}
            </Descriptions.Item>
          )}
        </Descriptions>
      </Space>
    </Card>
  );
};

/**
 * Risk Impact Section
 * Shows the impact of the order on portfolio risk metrics
 */
const RiskImpact: React.FC<{
  validationResult: OrderValidationResponse | null;
}> = ({ validationResult }) => {
  if (!validationResult) return null;

  const { estimatedCost, estimatedBuyingPowerAfter } = validationResult;
  
  // Calculate impact percentages
  const buyingPower = estimatedBuyingPowerAfter && estimatedCost 
    ? estimatedBuyingPowerAfter + estimatedCost 
    : 100000; // Default fallback
    
  const impactPercent = estimatedCost && buyingPower
    ? (estimatedCost / buyingPower * 100)
    : 0;

  return (
    <Card
      title={
        <Space>
          <WarningOutlined style={{ color: colors.semantic.warning }} />
          <Text strong style={{ color: colors.text.primary }}>
            Risk Impact
          </Text>
        </Space>
      }
      size="small"
      style={{ 
        backgroundColor: colors.backgrounds.tertiary,
        borderColor: colors.backgrounds.border,
      }}
      styles={{
        header: {
          backgroundColor: colors.backgrounds.secondary,
          borderBottom: `1px solid ${colors.backgrounds.border}`,
        }
      }}
    >
      <Row gutter={16}>
        <Col span={12}>
          <Statistic
            title={
              <span style={{ color: colors.text.secondary, fontSize: '12px' }}>
                Capital Deployed
              </span>
            }
            value={impactPercent}
            precision={2}
            suffix="%"
            valueStyle={{ 
              fontSize: '20px',
              color: impactPercent > 25 
                ? colors.semantic.error 
                : impactPercent > 15 
                  ? colors.semantic.warning 
                  : colors.semantic.success
            }}
          />
        </Col>
        <Col span={12}>
          <Statistic
            title={
              <span style={{ color: colors.text.secondary, fontSize: '12px' }}>
                Estimated Cost
              </span>
            }
            value={estimatedCost || 0}
            precision={2}
            prefix={<DollarOutlined />}
            valueStyle={{ 
              fontSize: '20px',
              color: colors.text.primary
            }}
          />
        </Col>
      </Row>
      
      {impactPercent > 25 && (
        <>
          <Divider style={{ margin: '12px 0' }} />
          <Alert
            message="High Capital Deployment"
            description="This order uses more than 25% of your buying power. Consider reducing position size."
            type="warning"
            showIcon
            style={{ 
              backgroundColor: 'rgba(250, 173, 20, 0.1)',
              border: `1px solid ${colors.semantic.warning}`,
            }}
          />
        </>
      )}
    </Card>
  );
};

/**
 * Main OrderPreview Modal Component
 */
export const OrderPreview: React.FC<OrderPreviewProps> = ({
  open,
  orderData,
  validationResult,
  validating = false,
  submitting = false,
  onCancel,
  onConfirm,
}) => {
  const isValid = validationResult?.valid ?? false;
  const hasErrors = (validationResult?.errors.length ?? 0) > 0;
  const hasWarnings = (validationResult?.warnings.length ?? 0) > 0;

  // Determine if confirm button should be disabled
  const confirmDisabled = !isValid || hasErrors || validating || submitting;

  return (
    <Modal
      title={
        <Space>
          <ShoppingOutlined style={{ color: colors.brand.primary }} />
          <span style={{ color: colors.text.primary }}>
            Order Preview & Confirmation
          </span>
        </Space>
      }
      open={open}
      onCancel={onCancel}
      width={720}
      centered
      footer={[
        <Button 
          key="cancel" 
          onClick={onCancel}
          disabled={submitting}
          style={{
            borderColor: colors.backgrounds.border,
            color: colors.text.primary,
          }}
        >
          Cancel
        </Button>,
        <Button
          key="confirm"
          type="primary"
          icon={isValid ? <CheckCircleOutlined /> : <WarningOutlined />}
          loading={submitting}
          disabled={confirmDisabled}
          onClick={onConfirm}
          style={{
            backgroundColor: isValid ? colors.semantic.success : colors.backgrounds.disabled,
            borderColor: isValid ? colors.semantic.success : colors.backgrounds.disabled,
          }}
        >
          {submitting ? 'Submitting...' : isValid ? 'Confirm & Submit Order' : 'Cannot Submit'}
        </Button>,
      ]}
      styles={{
        header: {
          backgroundColor: colors.backgrounds.secondary,
          borderBottom: `1px solid ${colors.backgrounds.border}`,
        },
        body: {
          backgroundColor: colors.backgrounds.secondary,
          maxHeight: '70vh',
          overflowY: 'auto',
        },
        footer: {
          backgroundColor: colors.backgrounds.secondary,
          borderTop: `1px solid ${colors.backgrounds.border}`,
        }
      }}
    >
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Order Summary */}
        <OrderSummary orderData={orderData} />

        {/* Pre-Trade Validation Checks */}
        <PreTradeChecks
          validationResult={validationResult}
          loading={validating}
          title="Pre-Trade Validation"
        />

        {/* Risk Impact */}
        {validationResult && !validating && (
          <RiskImpact 
            validationResult={validationResult}
          />
        )}

        {/* Information Footer */}
        {isValid && !hasErrors && (
          <Alert
            message="Ready to Submit"
            description={
              hasWarnings 
                ? "Validation passed with warnings. Please review carefully before confirming."
                : "All validation checks passed. Your order is ready for submission."
            }
            type={hasWarnings ? "warning" : "success"}
            showIcon
            style={{ 
              backgroundColor: hasWarnings 
                ? 'rgba(250, 173, 20, 0.1)' 
                : 'rgba(82, 196, 26, 0.1)',
              border: `1px solid ${hasWarnings ? colors.semantic.warning : colors.semantic.success}`,
            }}
          />
        )}

        {/* Disclaimer */}
        <Paragraph 
          type="secondary" 
          style={{ 
            fontSize: '11px', 
            margin: 0,
            color: colors.text.tertiary,
            textAlign: 'center'
          }}
        >
          Orders are executed at market prices and may differ from estimates.
          Past performance does not guarantee future results.
        </Paragraph>
      </Space>
    </Modal>
  );
};

export default OrderPreview;
