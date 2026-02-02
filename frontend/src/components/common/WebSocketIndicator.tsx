/**
 * WebSocket Connection Indicator
 * Displays the current WebSocket connection status
 */

import React from 'react';
import { Tag, Tooltip } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { colors } from '@/styles/theme';

interface WebSocketIndicatorProps {
  isConnected: boolean;
  showLabel?: boolean;
  size?: 'small' | 'default';
}

export const WebSocketIndicator: React.FC<WebSocketIndicatorProps> = ({
  isConnected,
  showLabel = true,
  size = 'default',
}) => {
  if (isConnected) {
    return (
      <Tooltip title="WebSocket connected - Real-time updates active">
        <Tag
          icon={<CheckCircleOutlined />}
          color={colors.semantic.success}
          style={{
            fontSize: size === 'small' ? 12 : 14,
            padding: size === 'small' ? '2px 8px' : '4px 12px',
            borderRadius: 4,
          }}
        >
          {showLabel && 'Live'}
        </Tag>
      </Tooltip>
    );
  }

  return (
    <Tooltip title="WebSocket disconnected - Real-time updates inactive">
      <Tag
        icon={<CloseCircleOutlined />}
        color={colors.semantic.stopped}
        style={{
          fontSize: size === 'small' ? 12 : 14,
          padding: size === 'small' ? '2px 8px' : '4px 12px',
          borderRadius: 4,
        }}
      >
        {showLabel && 'Offline'}
      </Tag>
    </Tooltip>
  );
};

/**
 * WebSocket Reconnecting Indicator
 */
export const WebSocketReconnecting: React.FC = () => {
  return (
    <Tooltip title="Reconnecting to WebSocket...">
      <Tag
        icon={<SyncOutlined spin />}
        color={colors.semantic.warning}
        style={{
          fontSize: 14,
          padding: '4px 12px',
          borderRadius: 4,
        }}
      >
        Reconnecting...
      </Tag>
    </Tooltip>
  );
};
