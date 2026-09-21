/**
 * Kill Switch Button Component
 * Emergency stop functionality with confirmation modal
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Button, Modal, Typography, Alert, Space, message } from 'antd';
import { FireOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { riskApi } from '../../services/riskApi';
import type { TriggerEmergencyStopRequest } from '../../types/risk';
import './KillSwitchButton.css';

const { Text } = Typography;

interface KillSwitchButtonProps {
  className?: string;
  size?: 'small' | 'middle' | 'large';
  disabled?: boolean;
  onConfirm?: () => void;
  onCancel?: () => void;
}

const KillSwitchButton: React.FC<KillSwitchButtonProps> = ({
  className = '',
  size = 'large',
  disabled = false,
  onConfirm,
  onCancel,
}) => {
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [reason, setReason] = useState('');
  const [countdown, setCountdown] = useState(10);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const queryClient = useQueryClient();

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const emergencyStopMutation = useMutation({
    mutationFn: (request: TriggerEmergencyStopRequest) => riskApi.triggerEmergencyStop(request),
    onSuccess: () => {
      message.success('New entries halted. Entry order cancellation confirmed; protective exits remain active.');
      queryClient.invalidateQueries({ queryKey: ['risk'] });
      setShowConfirmModal(false);
      onConfirm?.();
    },
    onError: (error: unknown) => {
      const detail = isAxiosError(error) ? error.response?.data?.detail : undefined;
      queryClient.invalidateQueries({ queryKey: ['risk'] });
      if (detail?.control?.entries_halted === true) {
        const exits = detail.control.protective_exits_active === true
          ? 'Protective exits remain active.'
          : 'Exit management could not be verified; check engine and broker positions immediately.';
        message.warning(`New entries are halted, but the emergency stop is incomplete. Check pending entry orders and the audit status. ${exits}`, 12);
      } else {
        message.error('Emergency stop could not be confirmed. Check engine status and broker orders immediately.', 12);
      }
    },
  });

  const handleKillSwitchClick = useCallback(() => {
    setShowConfirmModal(true);
    setCountdown(10);

    // Clear any previous timer
    if (timerRef.current) clearInterval(timerRef.current);

    timerRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          timerRef.current = null;
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  const handleConfirmEmergencyStop = () => {
    const request: TriggerEmergencyStopRequest = {
      reason: reason || 'Manual emergency stop triggered',
    };

    emergencyStopMutation.mutate(request);
  };

  const handleCancel = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setShowConfirmModal(false);
    setReason('');
    setCountdown(10);
    onCancel?.();
  }, [onCancel]);

  return (
    <>
      <Button
        type="primary"
        danger
        size={size}
        icon={<FireOutlined />}
        className={`kill-switch-button ${className}`}
        onClick={handleKillSwitchClick}
        disabled={disabled || emergencyStopMutation.isPending}
        loading={emergencyStopMutation.isPending}
      >
        EMERGENCY STOP
      </Button>

      <Modal
        title={
          <Space>
            <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />
            <span style={{ color: '#ff4d4f' }}>EMERGENCY STOP CONFIRMATION</span>
          </Space>
        }
        open={showConfirmModal}
        onOk={handleConfirmEmergencyStop}
        onCancel={handleCancel}
        okText={`CONFIRM STOP ${countdown > 0 ? `(${countdown})` : ''}`}
        cancelText="Cancel"
        okButtonProps={{
          danger: true,
          disabled: countdown > 0,
          loading: emergencyStopMutation.isPending,
        }}
        closable={false}
        maskClosable={false}
        width={600}
        className="kill-switch-modal"
      >
        <Alert
          type="error"
          showIcon
          message="Halt new entries and cancel verified pending entry orders"
          description={
            <div style={{ marginTop: 16 }}>
              <p><strong>This action will:</strong></p>
              <ul>
                <li>Block new entries and additions to positions</li>
                <li>Request cancellation of entry orders verified as belonging to this engine</li>
                <li>Leave protective exits and end-of-day management enabled; confirm the engine is running</li>
                <li>Preserve other orders and report incomplete cancellations</li>
                <li>Record the outcome in the audit trail</li>
              </ul>
              <p style={{ marginTop: 16 }}>
                <strong>This action cannot be undone automatically.</strong> 
                An operator must explicitly resume entries. Other risk blocks remain in force.
              </p>
              
              <div style={{ marginTop: 16 }}>
                <Text strong>Reason for emergency stop:</Text>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Optional: Describe the reason for the emergency stop..."
                  style={{
                    width: '100%',
                    marginTop: 8,
                    padding: 8,
                    border: '1px solid #d9d9d9',
                    borderRadius: 4,
                    minHeight: 80,
                  }}
                />
              </div>

              {countdown > 0 && (
                <div style={{ marginTop: 16, textAlign: 'center' }}>
                  <Text type="secondary">
                    Confirmation available in {countdown} seconds...
                  </Text>
                </div>
              )}
            </div>
          }
        />
      </Modal>
    </>
  );
};

export default KillSwitchButton;
