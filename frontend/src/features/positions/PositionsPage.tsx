/**
 * Positions Page
 * Main page for viewing and managing trading positions
 */

import React, { useState } from 'react';
import { Card, Tabs, Space, message, Modal } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { PositionsTable } from './components/PositionsTable';
import { PositionDetailModal } from './components/PositionDetailModal';
import { PositionStatistics } from './components/PositionStatistics';
import { usePositions } from './hooks/usePositions';
import { type Position } from '@/store/portfolioStore';
import { ordersService } from '@/services/ordersService';

const { confirm } = Modal;

export const PositionsPage: React.FC = () => {
  const { data: positions, isLoading } = usePositions();
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [activeTab, setActiveTab] = useState('open');

  // Filter positions based on active tab
  const filteredPositions = React.useMemo(() => {
    if (!positions) return [];

    switch (activeTab) {
      case 'open':
        return positions.filter((p) => p.quantity > 0);
      case 'all':
        return positions;
      default:
        return positions.filter((p) => p.quantity > 0);
    }
  }, [positions, activeTab]);

  const handleViewDetails = (position: Position) => {
    setSelectedPosition(position);
    setDetailModalVisible(true);
  };

  const handleClosePosition = (position: Position) => {
    confirm({
      title: `Close ${position.symbol} Position?`,
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>
            This will create a <strong>market sell order</strong> for{' '}
            <strong>{position.quantity}</strong> shares of <strong>{position.symbol}</strong>.
          </p>
          <p>
            Current market value: <strong>${position.marketValue.toFixed(2)}</strong>
          </p>
          <p>
            Unrealized P&L:{' '}
            <strong style={{ color: position.unrealizedPnL >= 0 ? '#52c41a' : '#ff4d4f' }}>
              ${position.unrealizedPnL.toFixed(2)} ({position.unrealizedPnLPercent.toFixed(2)}%)
            </strong>
          </p>
        </div>
      ),
      okText: 'Close Position',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          await ordersService.submitOrder({
            symbol: position.symbol,
            side: 'sell',
            orderType: 'market',
            quantity: position.quantity,
            timeInForce: 'gtc',
          });

          message.success(`Market sell order submitted for ${position.symbol}`);
        } catch (error: unknown) {
          const err = error as { message?: string };
          message.error(`Failed to close position: ${err.message || 'Unknown error'}`);
        }
      },
    });
  };

  const handleAddToPosition = (position: Position) => {
    confirm({
      title: `Add to ${position.symbol} Position?`,
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>
            This will create a <strong>market buy order</strong> for{' '}
            <strong>{position.symbol}</strong>.
          </p>
          <p>How many shares would you like to add?</p>
          <input
            id="add-quantity-input"
            type="number"
            min="1"
            defaultValue="10"
            style={{
              width: '100%',
              padding: '8px',
              marginTop: '8px',
              border: '1px solid #d9d9d9',
              borderRadius: '4px',
            }}
          />
        </div>
      ),
      okText: 'Add to Position',
      okType: 'primary',
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          const quantityInput = document.getElementById('add-quantity-input') as HTMLInputElement;
          const quantity = parseInt(quantityInput?.value || '10', 10);

          if (quantity <= 0) {
            message.error('Quantity must be greater than 0');
            return;
          }

          await ordersService.submitOrder({
            symbol: position.symbol,
            side: 'buy',
            orderType: 'market',
            quantity,
            timeInForce: 'gtc',
          });

          message.success(`Market buy order submitted for ${quantity} shares of ${position.symbol}`);
        } catch (error: unknown) {
          const err = error as { message?: string };
          message.error(`Failed to add to position: ${err.message || 'Unknown error'}`);
        }
      },
    });
  };

  return (
    <div style={{ padding: '24px' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Page Header */}
        <div>
          <h1 style={{ margin: 0, fontSize: '28px', fontWeight: 'bold' }}>Positions</h1>
          <p style={{ margin: '4px 0 0 0', color: '#8c8c8c' }}>
            Manage and monitor your trading positions
          </p>
        </div>

        {/* Statistics Cards */}
        <PositionStatistics />

        {/* Positions Table */}
        <Card>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'open',
                label: `Open Positions (${positions?.filter((p) => p.quantity > 0).length || 0})`,
                children: (
                  <PositionsTable
                    positions={filteredPositions}
                    loading={isLoading}
                    onViewDetails={handleViewDetails}
                    onClosePosition={handleClosePosition}
                    onAddToPosition={handleAddToPosition}
                  />
                ),
              },
              {
                key: 'all',
                label: `All Positions (${positions?.length || 0})`,
                children: (
                  <PositionsTable
                    positions={filteredPositions}
                    loading={isLoading}
                    onViewDetails={handleViewDetails}
                    onClosePosition={handleClosePosition}
                    onAddToPosition={handleAddToPosition}
                  />
                ),
              },
            ]}
          />
        </Card>
      </Space>

      {/* Position Detail Modal */}
      <PositionDetailModal
        position={selectedPosition}
        visible={detailModalVisible}
        onClose={() => setDetailModalVisible(false)}
        onClosePosition={handleClosePosition}
        onAddToPosition={handleAddToPosition}
      />
    </div>
  );
};

export default PositionsPage;
