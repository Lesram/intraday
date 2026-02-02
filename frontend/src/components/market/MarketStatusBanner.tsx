/**
 * Market Status Banner Component
 * Shows current market status, hours, and warnings
 */

import React, { useState, useEffect } from 'react';
import { Alert, Space, Typography } from 'antd';
import { 
  ClockCircleOutlined, 
  CheckCircleOutlined, 
  WarningOutlined,
  CloseCircleOutlined 
} from '@ant-design/icons';
import { getMarketStatus, formatTimeUntil, getMarketStatusColor, type MarketHours } from '@/utils/marketHours';

const { Text } = Typography;

interface MarketStatusBannerProps {
  /** Show in compact mode (less detail) */
  compact?: boolean;
  /** Custom className */
  className?: string;
}

export const MarketStatusBanner: React.FC<MarketStatusBannerProps> = ({ 
  compact = false,
  className 
}) => {
  const [status, setStatus] = useState<MarketHours>(getMarketStatus());
  
  // Update status every minute
  useEffect(() => {
    const interval = setInterval(() => {
      setStatus(getMarketStatus());
    }, 60000); // Update every minute
    
    return () => clearInterval(interval);
  }, []);
  
  // Determine alert type
  const getAlertType = (): 'success' | 'warning' | 'info' | 'error' => {
    if (status.isOpen) return 'success';
    if (status.isExtendedHours) return 'warning';
    if (!status.canTrade) return 'error';
    return 'info';
  };
  
  // Get icon
  const getIcon = () => {
    if (status.isOpen) return <CheckCircleOutlined />;
    if (status.isExtendedHours) return <WarningOutlined />;
    if (!status.canTrade) return <CloseCircleOutlined />;
    return <ClockCircleOutlined />;
  };
  
  // Compact mode
  if (compact) {
    return (
      <Space size="small" className={className}>
        <span style={{ color: getMarketStatusColor(status) }}>
          {getIcon()}
        </span>
        <Text style={{ color: getMarketStatusColor(status) }}>
          {status.message}
        </Text>
      </Space>
    );
  }
  
  // Full mode
  return (
    <Alert
      message={
        <Space>
          {getIcon()}
          <strong>{status.message}</strong>
          {status.nextOpen && (
            <Text type="secondary">
              • Opens in {formatTimeUntil(status.nextOpen)}
            </Text>
          )}
          {status.nextClose && (
            <Text type="secondary">
              • Closes in {formatTimeUntil(status.nextClose)}
            </Text>
          )}
        </Space>
      }
      description={status.warning}
      type={getAlertType()}
      showIcon={false}
      banner
      className={className}
      style={{ marginBottom: 16 }}
    />
  );
};

export default MarketStatusBanner;
