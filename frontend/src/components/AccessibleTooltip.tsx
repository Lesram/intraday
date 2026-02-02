/**
 * Accessible Tooltip Component
 * Enhanced tooltip with keyboard support and motion preferences
 */
import React from 'react';
import { Tooltip } from 'antd';
import type { TooltipProps as AntTooltipProps } from 'antd';
import { usePrefersReducedMotion } from '@/hooks/useAccessibility';

export interface AccessibleTooltipProps extends Omit<AntTooltipProps, 'children'> {
  children: React.ReactElement;
}

export const AccessibleTooltip: React.FC<AccessibleTooltipProps> = ({
  children,
  ...props
}) => {
  const prefersReducedMotion = usePrefersReducedMotion();

  const defaultProps = {
    mouseEnterDelay: 0.3,
    mouseLeaveDelay: 0,
  };

  return (
    <Tooltip
      {...defaultProps}
      {...props}
      transitionName={prefersReducedMotion ? '' : props.transitionName}
    >
      {children}
    </Tooltip>
  );
};
