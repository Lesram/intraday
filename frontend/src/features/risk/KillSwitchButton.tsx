/**
 * Kill Switch Button Component
 * Emergency stop functionality with confirmation modal
 */

import React, { useState } from 'react';
import { Button, Modal, Typography, Alert, Space, message } from 'antd';
import { FireOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { useMutation, useQueryClient } from '@tanstack/react-query';
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
  const queryClient = useQueryClient();

  const emergencyStopMutation = useMutation({
    mutationFn: (request: TriggerEmergencyStopRequest) => riskApi.triggerEmergencyStop(request),
    onSuccess: () => {
      message.success('Emergency stop activated successfully');
      queryClient.invalidateQueries({ queryKey: ['risk'] });
      setShowConfirmModal(false);
      onConfirm?.();
    },
    onError: (error: unknown) => {
      const err = error as { message?: string };
      message.error(`Failed to activate emergency stop: ${err.message}`);
    },
  });

  const handleKillSwitchClick = () => {
    setShowConfirmModal(true);
    setCountdown(10);
    
    // Start countdown
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  const handleConfirmEmergencyStop = () => {
    const request: TriggerEmergencyStopRequest = {
      reason: reason || 'Manual emergency stop triggered',
      stop_all_strategies: true,
      cancel_all_orders: true,
      notify_admin: true,
    };

    emergencyStopMutation.mutate(request);
  };

  const handleCancel = () => {
    setShowConfirmModal(false);
    setReason('');
    setCountdown(10);
    onCancel?.();
  };

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
          message="WARNING: This will immediately stop all trading activity"
          description={
            <div style={{ marginTop: 16 }}>
              <p><strong>This action will:</strong></p>
              <ul>
                <li>Stop all active trading strategies</li>
                <li>Cancel all pending orders</li>
                <li>Halt all automated trading</li>
                <li>Notify system administrators</li>
                <li>Create an audit trail record</li>
              </ul>
              <p style={{ marginTop: 16 }}>
                <strong>This action cannot be undone automatically.</strong> 
                Manual intervention will be required to resume trading.
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