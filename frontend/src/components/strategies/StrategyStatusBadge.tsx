/**
 * Strategy Status Badge
 * Displays strategy status with appropriate color coding and animations
 */

import React from 'react';
import { Tag, Tooltip } from 'antd';
import {
  CheckCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import type { StrategyStatus } from '@/types/strategy';
import { colors } from '@/styles/theme';

interface StrategyStatusBadgeProps {
  status: StrategyStatus;
  size?: 'small' | 'default';
  errorMessage?: string;
}

const statusConfig: Record<
  StrategyStatus,
  { color: string; icon: React.ReactNode; label: string; description: string }
> = {
  active: {
    color: colors.semantic.active,
    icon: <CheckCircleOutlined />,
    label: 'Running',
    description: 'Strategy is actively trading',
  },
  paused: {
    color: colors.semantic.pending,
    icon: <PauseCircleOutlined />,
    label: 'Paused',
    description: 'Strategy is paused, no new trades',
  },
  stopped: {
    color: colors.semantic.stopped,
    icon: <StopOutlined />,
    label: 'Stopped',
    description: 'Strategy is inactive',
  },
  error: {
    color: colors.semantic.error,
    icon: <ExclamationCircleOutlined />,
    label: 'Error',
    description: 'Strategy encountered an error',
  },
};

export const StrategyStatusBadge: React.FC<StrategyStatusBadgeProps> = ({
  status,
  size = 'default',
  errorMessage,
}) => {
  const config = statusConfig[status];

  const badgeContent = (
    <Tag
      icon={config.icon}
      color={config.color}
      style={{
        fontSize: size === 'small' ? 12 : 14,
        padding: size === 'small' ? '2px 8px' : '4px 12px',
        borderRadius: 4,
        animation: status === 'active' ? 'pulse 2s ease-in-out infinite' : 'none',
      }}
    >
      <style>{`
        @keyframes pulse {
          0%, 100% {
            opacity: 1;
            box-shadow: 0 0 0 0 ${config.color}40;
          }
          50% {
            opacity: 0.9;
            box-shadow: 0 0 8px 2px ${config.color}60;
          }
        }
      `}</style>
      {config.label}
    </Tag>
  );

  // Show tooltip for errors or always show description
  if (status === 'error' && errorMessage) {
    return (
      <Tooltip title={errorMessage}>
        {badgeContent}
      </Tooltip>
    );
  }

  return (
    <Tooltip title={config.description}>
      {badgeContent}
    </Tooltip>
  );
};
