/**
 * Accessible Loading Component
 * Loading states that respect motion preferences and announce to screen readers
 */
import React from 'react';
import { Spin } from 'antd';
import type { SpinProps } from 'antd';
import { usePrefersReducedMotion, useLoadingAnnouncement } from '@/hooks/useAccessibility';

export interface AccessibleLoadingProps extends SpinProps {
  loadingMessage?: string;
  children?: React.ReactNode;
}

export const AccessibleLoading: React.FC<AccessibleLoadingProps> = ({
  spinning = true,
  loadingMessage = 'Loading',
  children,
  ...props
}) => {
  const prefersReducedMotion = usePrefersReducedMotion();
  
  // Announce loading state to screen readers
  useLoadingAnnouncement(spinning, loadingMessage);

  if (prefersReducedMotion) {
    // Simple loading indicator without animation
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          padding: '20px',
        }}
        role="status"
        aria-live="polite"
        aria-busy={spinning}
      >
        {spinning && (
          <div style={{ textAlign: 'center' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                border: '3px solid #f0f0f0',
                borderTopColor: '#1890ff',
                borderRadius: '50%',
                margin: '0 auto 8px',
              }}
            />
            <div>{loadingMessage}...</div>
          </div>
        )}
        {!spinning && children}
      </div>
    );
  }

  return (
    <Spin
      spinning={spinning}
      tip={loadingMessage}
      {...props}
      wrapperClassName={`${props.wrapperClassName || ''} accessible-loading`}
    >
      <div role="status" aria-live="polite" aria-busy={spinning}>
        {children}
      </div>
    </Spin>
  );
};
