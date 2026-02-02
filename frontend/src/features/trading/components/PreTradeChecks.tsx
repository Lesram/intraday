/**
 * PreTradeChecks Component
 * 
 * Displays pre-trade validation check results with color-coded indicators,
 * icons, and clear error/warning messaging.
 * 
 * Features:
 * - 8 validation checks with visual feedback
 * - Color coding: Green (pass), Yellow (warning), Red (error)
 * - Icons: ✅ (pass), ⚠️ (warning), ❌ (error)
 * - Separate warnings and errors sections
 * - Cost summary with buying power impact
 * - Loading state with spinner
 * - Responsive design
 * - Accessible (keyboard navigation, ARIA labels)
 * 
 * Integration:
 * - Follows PHASE_2_1_COMPREHENSIVE_ANALYSIS.md Section 7, Phase 3
 * - Uses types from @/types/trading
 * - Matches existing component patterns (Card, Alert, Space)
 * - Uses theme colors from @/styles/theme
 */

import React from 'react';
import { 
  Card, 
  Space, 
  Alert, 
  Badge, 
  Typography, 
  Row, 
  Col, 
  Divider,
  Spin,
  Statistic,
  Tooltip
} from 'antd';
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  CloseCircleOutlined,
  DollarOutlined,
  InfoCircleOutlined,
  WarningOutlined
} from '@ant-design/icons';
import { colors } from '@/styles/theme';
import type { 
  ValidationCheck, 
  OrderValidationResponse 
} from '@/types/trading';
import { 
  getSeverityColor, 
  formatCurrency
} from '@/types/trading';

const { Title, Text } = Typography;

interface PreTradeChecksProps {
  /** Validation response data from backend */
  validationResult: OrderValidationResponse | null;
  
  /** Loading state while validation is in progress */
  loading?: boolean;
  
  /** Error state if validation request failed */
  error?: Error | null;
  
  /** Show compact version (for inline display) */
  compact?: boolean;
  
  /** Custom title */
  title?: string;
}

/**
 * Individual check item component
 * Displays a single validation check with icon, message, and values
 */
const CheckItem: React.FC<{ check: ValidationCheck }> = ({ check }) => {
  const color = getSeverityColor(check.severity);
  
  // Determine Ant Design icon component based on severity
  const IconComponent = check.passed 
    ? CheckCircleOutlined 
    : check.severity === 'warning' 
      ? WarningOutlined 
      : CloseCircleOutlined;
  
  return (
    <Row 
      align="middle" 
      style={{ 
        padding: '8px 0',
        borderBottom: `1px solid ${colors.backgrounds.border}`,
      }}
    >
      <Col span={2}>
        <IconComponent 
          style={{ 
            fontSize: '18px', 
            color: color,
          }} 
        />
      </Col>
      <Col span={14}>
        <Space direction="vertical" size={0}>
          <Text strong style={{ color: colors.text.primary }}>
            {check.name}
          </Text>
          <Text 
            type="secondary" 
            style={{ 
              fontSize: '12px',
              color: colors.text.tertiary 
            }}
          >
            {check.message}
          </Text>
        </Space>
      </Col>
      <Col span={8} style={{ textAlign: 'right' }}>
        {check.currentValue !== undefined && check.limitValue !== undefined && (
          <Tooltip title={`Limit: ${formatCurrency(check.limitValue)}`}>
            <Text 
              style={{ 
                fontSize: '12px',
                color: check.passed ? colors.semantic.success : colors.semantic.error
              }}
            >
              {formatCurrency(check.currentValue)}
              {check.limitValue && (
                <span style={{ color: colors.text.tertiary }}>
                  {' / '}
                  {formatCurrency(check.limitValue)}
                </span>
              )}
            </Text>
          </Tooltip>
        )}
        {check.currentValue !== undefined && check.limitValue === undefined && (
          <Text style={{ fontSize: '12px', color: colors.text.secondary }}>
            {typeof check.currentValue === 'number' 
              ? formatCurrency(check.currentValue)
              : check.currentValue}
          </Text>
        )}
      </Col>
    </Row>
  );
};

/**
 * Cost summary component
 * Shows estimated cost and buying power impact
 */
const CostSummary: React.FC<{
  estimatedCost?: number;
  estimatedBuyingPowerAfter?: number;
}> = ({ estimatedCost, estimatedBuyingPowerAfter }) => {
  if (!estimatedCost && !estimatedBuyingPowerAfter) {
    return null;
  }

  return (
    <>
      <Divider style={{ margin: '12px 0' }} />
      <Row gutter={16}>
        {estimatedCost !== undefined && (
          <Col span={12}>
            <Statistic
              title={
                <span style={{ color: colors.text.secondary }}>
                  Estimated Cost
                </span>
              }
              value={estimatedCost}
              precision={2}
              prefix={<DollarOutlined />}
              valueStyle={{ 
                fontSize: '16px',
                color: colors.text.primary 
              }}
            />
          </Col>
        )}
        {estimatedBuyingPowerAfter !== undefined && (
          <Col span={12}>
            <Statistic
              title={
                <span style={{ color: colors.text.secondary }}>
                  Buying Power After
                </span>
              }
              value={estimatedBuyingPowerAfter}
              precision={2}
              prefix={<DollarOutlined />}
              valueStyle={{ 
                fontSize: '16px',
                color: colors.text.primary 
              }}
            />
          </Col>
        )}
      </Row>
    </>
  );
};

/**
 * Main PreTradeChecks component
 */
export const PreTradeChecks: React.FC<PreTradeChecksProps> = ({
  validationResult,
  loading = false,
  error = null,
  compact = false,
  title = 'Pre-Trade Validation'
}) => {
  // Loading state
  if (loading) {
    return (
      <Card 
        style={{ 
          backgroundColor: colors.backgrounds.secondary,
          borderColor: colors.backgrounds.border,
        }}
      >
        <Space direction="vertical" align="center" style={{ width: '100%' }}>
          <Spin size="large" />
          <Text style={{ color: colors.text.secondary }}>
            Validating order...
          </Text>
        </Space>
      </Card>
    );
  }

  // Error state
  if (error) {
    return (
      <Card 
        style={{ 
          backgroundColor: colors.backgrounds.secondary,
          borderColor: colors.backgrounds.border,
        }}
      >
        <Alert
          message="Validation Error"
          description={error.message || 'Failed to validate order. Please try again.'}
          type="error"
          icon={<CloseCircleOutlined />}
          showIcon
        />
      </Card>
    );
  }

  // No data state
  if (!validationResult) {
    return (
      <Card 
        style={{ 
          backgroundColor: colors.backgrounds.secondary,
          borderColor: colors.backgrounds.border,
        }}
      >
        <Space direction="vertical" align="center" style={{ width: '100%' }}>
          <InfoCircleOutlined 
            style={{ 
              fontSize: '32px', 
              color: colors.text.tertiary 
            }} 
          />
          <Text style={{ color: colors.text.secondary }}>
            Enter order details to see validation checks
          </Text>
        </Space>
      </Card>
    );
  }

  const { valid, checks, warnings, errors, estimatedCost, estimatedBuyingPowerAfter } = validationResult;

  return (
    <Card
      title={
        <Space>
          <Title level={5} style={{ margin: 0, color: colors.text.primary }}>
            {title}
          </Title>
          <Badge 
            status={valid ? 'success' : 'error'} 
            text={
              <span style={{ color: colors.text.secondary }}>
                {valid ? 'All checks passed' : 'Validation failed'}
              </span>
            }
          />
        </Space>
      }
      style={{ 
        backgroundColor: colors.backgrounds.secondary,
        borderColor: valid 
          ? colors.semantic.success 
          : colors.semantic.error,
        borderWidth: '2px',
      }}
      styles={{
        header: {
          backgroundColor: colors.backgrounds.tertiary,
          borderBottom: `1px solid ${colors.backgrounds.border}`,
        },
        body: {
          padding: compact ? '12px' : '16px',
        }
      }}
    >
      {/* Validation Checks */}
      <Space direction="vertical" style={{ width: '100%' }} size={0}>
        {checks.map((check, index) => (
          <CheckItem key={`${check.name}-${index}`} check={check} />
        ))}
      </Space>

      {/* Warnings Section */}
      {warnings.length > 0 && (
        <>
          <Divider style={{ margin: '12px 0' }} />
          <Alert
            message="Warnings"
            description={
              <ul style={{ margin: '8px 0 0 0', paddingLeft: '20px' }}>
                {warnings.map((warning, index) => (
                  <li key={index} style={{ color: colors.text.secondary }}>
                    {warning}
                  </li>
                ))}
              </ul>
            }
            type="warning"
            icon={<ExclamationCircleOutlined />}
            showIcon
            style={{ 
              backgroundColor: 'rgba(250, 173, 20, 0.1)',
              border: `1px solid ${colors.semantic.warning}`,
            }}
          />
        </>
      )}

      {/* Errors Section */}
      {errors.length > 0 && (
        <>
          <Divider style={{ margin: '12px 0' }} />
          <Alert
            message="Errors - Order Cannot Proceed"
            description={
              <ul style={{ margin: '8px 0 0 0', paddingLeft: '20px' }}>
                {errors.map((error, index) => (
                  <li key={index} style={{ color: colors.text.secondary }}>
                    {error}
                  </li>
                ))}
              </ul>
            }
            type="error"
            icon={<CloseCircleOutlined />}
            showIcon
            style={{ 
              backgroundColor: 'rgba(245, 34, 45, 0.1)',
              border: `1px solid ${colors.semantic.error}`,
            }}
          />
        </>
      )}

      {/* Cost Summary */}
      {!compact && (
        <CostSummary 
          estimatedCost={estimatedCost} 
          estimatedBuyingPowerAfter={estimatedBuyingPowerAfter} 
        />
      )}
    </Card>
  );
};

/**
 * Compact version for inline display
 * Shows just pass/fail status with icon
 */
export const PreTradeChecksCompact: React.FC<{
  validationResult: OrderValidationResponse | null;
  loading?: boolean;
}> = ({ validationResult, loading }) => {
  if (loading) {
    return <Spin size="small" />;
  }

  if (!validationResult) {
    return null;
  }

  const { valid, errors } = validationResult;
  const errorCount = errors.length;

  return (
    <Space>
      {valid ? (
        <CheckCircleOutlined style={{ color: colors.semantic.success, fontSize: '16px' }} />
      ) : (
        <CloseCircleOutlined style={{ color: colors.semantic.error, fontSize: '16px' }} />
      )}
      <Text 
        style={{ 
          color: valid ? colors.semantic.success : colors.semantic.error,
          fontSize: '12px'
        }}
      >
        {valid ? 'Validation passed' : `${errorCount} error${errorCount !== 1 ? 's' : ''}`}
      </Text>
    </Space>
  );
};

export default PreTradeChecks;
