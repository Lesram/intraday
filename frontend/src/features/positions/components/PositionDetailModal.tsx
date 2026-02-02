/**
 * Position Detail Modal
 * Shows detailed information about a specific position
 */

import React from 'react';
import { Modal, Descriptions, Tag, Space, Button, Statistic, Row, Col } from 'antd';
import { CloseOutlined, PlusOutlined } from '@ant-design/icons';
import { type Position } from '@/store/portfolioStore';

interface PositionDetailModalProps {
  position: Position | null;
  visible: boolean;
  onClose: () => void;
  onClosePosition: (position: Position) => void;
  onAddToPosition: (position: Position) => void;
}

export const PositionDetailModal: React.FC<PositionDetailModalProps> = ({
  position,
  visible,
  onClose,
  onClosePosition,
  onAddToPosition,
}) => {
  if (!position) return null;

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value);
  };

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  const getPnLColor = (value: number) => {
    if (value > 0) return '#52c41a';
    if (value < 0) return '#ff4d4f';
    return '#8c8c8c';
  };

  const costBasis = position.averagePrice * position.quantity;
  const totalReturnPercent = position.unrealizedPnLPercent;

  return (
    <Modal
      title={
        <Space>
          <span style={{ fontSize: '20px', fontWeight: 'bold' }}>
            {position.symbol}
          </span>
          <Tag color={position.side === 'long' ? 'blue' : 'orange'}>
            {position.side.toUpperCase()}
          </Tag>
        </Space>
      }
      open={visible}
      onCancel={onClose}
      width={800}
      footer={[
        <Button key="close-modal" onClick={onClose}>
          Cancel
        </Button>,
        <Button
          key="add"
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            onAddToPosition(position);
            onClose();
          }}
          style={{ background: '#52c41a', borderColor: '#52c41a' }}
        >
          Add to Position
        </Button>,
        <Button
          key="close-position"
          danger
          icon={<CloseOutlined />}
          onClick={() => {
            onClosePosition(position);
            onClose();
          }}
        >
          Close Position
        </Button>,
      ]}
    >
      {/* Performance Summary */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Statistic
            title="Unrealized P&L"
            value={position.unrealizedPnL}
            precision={2}
            valueStyle={{ color: getPnLColor(position.unrealizedPnL) }}
            prefix={position.unrealizedPnL >= 0 ? '+' : ''}
            suffix="USD"
            formatter={(value) => formatCurrency(value as number)}
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="Return %"
            value={totalReturnPercent}
            precision={2}
            valueStyle={{ color: getPnLColor(totalReturnPercent) }}
            prefix={totalReturnPercent >= 0 ? '+' : ''}
            suffix="%"
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="Market Value"
            value={position.marketValue}
            precision={2}
            formatter={(value) => formatCurrency(value as number)}
          />
        </Col>
      </Row>

      {/* Position Details */}
      <Descriptions
        title="Position Details"
        bordered
        column={2}
        size="small"
        styles={{
          label: { fontWeight: 'bold', width: '40%' },
          content: { width: '60%' },
        }}
      >
        <Descriptions.Item label="Symbol">{position.symbol}</Descriptions.Item>
        <Descriptions.Item label="Side">
          <Tag color={position.side === 'long' ? 'blue' : 'orange'}>
            {position.side.toUpperCase()}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Quantity">
          {position.quantity.toLocaleString()} shares
        </Descriptions.Item>
        <Descriptions.Item label="Exchange">
          {position.exchange || 'N/A'}
        </Descriptions.Item>
        <Descriptions.Item label="Avg Entry Price">
          {formatCurrency(position.averagePrice)}
        </Descriptions.Item>
        <Descriptions.Item label="Current Price">
          {formatCurrency(position.currentPrice)}
        </Descriptions.Item>
        <Descriptions.Item label="Cost Basis">
          {formatCurrency(costBasis)}
        </Descriptions.Item>
        <Descriptions.Item label="Market Value">
          {formatCurrency(position.marketValue)}
        </Descriptions.Item>
        <Descriptions.Item label="Unrealized P&L">
          <span style={{ color: getPnLColor(position.unrealizedPnL), fontWeight: 'bold' }}>
            {formatCurrency(position.unrealizedPnL)}
          </span>
        </Descriptions.Item>
        <Descriptions.Item label="P&L %">
          <span style={{ color: getPnLColor(totalReturnPercent), fontWeight: 'bold' }}>
            {formatPercent(totalReturnPercent)}
          </span>
        </Descriptions.Item>
      </Descriptions>

      {/* Risk Metrics */}
      <Descriptions
        title="Risk Metrics"
        bordered
        column={2}
        size="small"
        style={{ marginTop: 16 }}
        styles={{
          label: { fontWeight: 'bold', width: '40%' },
          content: { width: '60%' },
        }}
      >
        <Descriptions.Item label="Price Change">
          {formatCurrency(position.currentPrice - position.averagePrice)}
          {' ('}
          {formatPercent(
            ((position.currentPrice - position.averagePrice) / position.averagePrice) * 100
          )}
          {')'}
        </Descriptions.Item>
        <Descriptions.Item label="Position Size">
          {formatCurrency(position.marketValue)}
        </Descriptions.Item>
      </Descriptions>

      {/* Info Notice */}
      <div
        style={{
          marginTop: 16,
          padding: 12,
          background: '#f0f2f5',
          borderRadius: 4,
          fontSize: '12px',
          color: '#595959',
        }}
      >
        <strong>Note:</strong> Position data updates in real-time via WebSocket. Close position
        will create a market sell order for the full quantity.
      </div>
    </Modal>
  );
};
