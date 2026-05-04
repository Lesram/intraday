/**
 * Positions Table Component
 * Displays current portfolio positions with sorting and real-time updates
 */

import { useState } from 'react';
import { Table, Tag, Button, App } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ArrowUpOutlined, ArrowDownOutlined, CloseOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { colors } from '@/styles/theme';
import { formatCurrency, formatPercent } from '@/utils/formatters';
import type { Position } from '@/store/portfolioStore';
import { useAuthStore } from '@/store/authStore';
// V13 W98 (Lens 7): the shared axios instance is exported as
// `apiClient`, not `api`.  Aliasing here keeps call-site readability
// while fixing the missing export that broke `npm run build`.
import { apiClient as api } from '@/services/api';

interface PositionsTableProps {
  positions: Position[];
  loading?: boolean;
  onPositionClosed?: () => void;
}

export const PositionsTable: React.FC<PositionsTableProps> = ({ 
  positions, 
  loading = false,
  onPositionClosed
}) => {
  const { message, modal } = App.useApp();
  const [closingPositions, setClosingPositions] = useState<Set<string>>(new Set());

  // Handle close position
  const handleClosePosition = async (symbol: string, quantity: number) => {
    let quantityToClose: number | undefined = undefined;
    
    modal.confirm({
      title: 'Close Position',
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>Position: <strong>{symbol}</strong></p>
          <p>Current Quantity: <strong>{quantity}</strong> shares</p>
          <div style={{ marginTop: 16 }}>
            <label style={{ display: 'block', marginBottom: 8 }}>
              <strong>Quantity to close:</strong>
            </label>
            <input
              type="number"
              id="close-quantity-input"
              min="0.01"
              max={quantity}
              step="0.01"
              placeholder={`${quantity} (all shares)`}
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid #d9d9d9',
                borderRadius: 4,
                fontSize: 14,
                backgroundColor: '#ffffff',
                color: '#000000',
              }}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                quantityToClose = isNaN(val) || val <= 0 ? undefined : val;
              }}
            />
            <small style={{ color: '#8c8c8c', display: 'block', marginTop: 4 }}>
              Leave empty to close entire position
            </small>
          </div>
        </div>
      ),
      okText: 'Close Position',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          setClosingPositions(prev => new Set(prev).add(symbol));
          
          // Get the input value at execution time
          const inputEl = document.getElementById('close-quantity-input') as HTMLInputElement;
          if (inputEl && inputEl.value) {
            const val = parseFloat(inputEl.value);
            if (!isNaN(val) && val > 0 && val <= quantity) {
              quantityToClose = val;
            }
          }
          
          const qtyText = quantityToClose ? `${quantityToClose}` : 'all';
          message.loading({ content: `Closing ${qtyText} shares of ${symbol}...`, key: symbol });
          
          // V4 O-5: auth is attached by the api axios instance.
          if (!useAuthStore.getState().accessToken) {
            throw new Error('Not authenticated. Please login again.');
          }

          // Build request body
          const body: { quantity?: number } = {};
          if (quantityToClose !== undefined) {
            body.quantity = quantityToClose;
          }
          
          // V4 O-5 (2026-05-02): use the shared axios instance — it
          // routes via VITE_API_BASE_URL, attaches the auth header,
          // refreshes tokens, and works behind a reverse proxy. The
          // previous raw fetch hardcoded localhost:8000.
          const { data } = await api.post(
            `/positions/${symbol}/close`,
            body,
          );
          
          message.success({ 
            content: data.message || `Successfully closed ${qtyText} shares of ${symbol}`, 
            key: symbol,
            duration: 3
          });
          
          // Notify parent to refresh data
          if (onPositionClosed) {
            onPositionClosed();
          }
          
        } catch (error: unknown) {
          const err = error as { message?: string };
          const errorMsg = err.message || 'Failed to close position';
          message.error({ content: errorMsg, key: symbol, duration: 4 });
        } finally {
          setClosingPositions(prev => {
            const newSet = new Set(prev);
            newSet.delete(symbol);
            return newSet;
          });
        }
      }
    });
  };

  const columns: ColumnsType<Position> = [
    {
      title: 'Symbol',
      dataIndex: 'symbol',
      key: 'symbol',
      fixed: 'left',
      width: 100,
      sorter: (a, b) => a.symbol.localeCompare(b.symbol),
      render: (symbol: string) => (
        <strong style={{ color: colors.brand.primary }}>{symbol}</strong>
      ),
    },
    {
      title: 'Side',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      filters: [
        { text: 'Long', value: 'long' },
        { text: 'Short', value: 'short' },
      ],
      onFilter: (value, record) => record.side === value,
      render: (side: 'long' | 'short' | undefined) => (
        <Tag color={side === 'long' ? 'green' : side === 'short' ? 'red' : 'blue'}>
          {side ? side.toUpperCase() : 'LONG'}
        </Tag>
      ),
    },
    {
      title: 'Quantity',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 100,
      align: 'right',
      sorter: (a, b) => a.quantity - b.quantity,
      render: (qty: number) => qty.toLocaleString(),
    },
    {
      title: 'Avg Price',
      dataIndex: 'averagePrice',
      key: 'averagePrice',
      width: 120,
      align: 'right',
      sorter: (a, b) => a.averagePrice - b.averagePrice,
      render: (price: number) => formatCurrency(price),
    },
    {
      title: 'Current Price',
      dataIndex: 'currentPrice',
      key: 'currentPrice',
      width: 130,
      align: 'right',
      sorter: (a, b) => a.currentPrice - b.currentPrice,
      render: (price: number) => formatCurrency(price),
    },
    {
      title: 'Market Value',
      dataIndex: 'marketValue',
      key: 'marketValue',
      width: 140,
      align: 'right',
      sorter: (a, b) => a.marketValue - b.marketValue,
      render: (value: number) => (
        <strong>{formatCurrency(value)}</strong>
      ),
    },
    {
      title: 'Unrealized P&L',
      dataIndex: 'unrealizedPnL',
      key: 'unrealizedPnL',
      width: 150,
      align: 'right',
      sorter: (a, b) => a.unrealizedPnL - b.unrealizedPnL,
      defaultSortOrder: 'descend',
      render: (pnl: number | undefined, record: Position) => {
        const actualPnl = pnl || 0;
        const isProfit = actualPnl >= 0;
        const icon = isProfit ? <ArrowUpOutlined /> : <ArrowDownOutlined />;
        const color = isProfit ? colors.semantic.profit : colors.semantic.loss;
        
        return (
          <div style={{ color, fontWeight: 'bold' }}>
            {icon} {formatCurrency(Math.abs(actualPnl))}
            <div style={{ fontSize: '12px', opacity: 0.8 }}>
              {formatPercent(record.unrealizedPnLPercent || 0)}
            </div>
          </div>
        );
      },
    },
    {
      title: 'Entry Date',
      dataIndex: 'entryDate',
      key: 'entryDate',
      width: 140,
      sorter: (a, b) => {
        if (!a.entryDate || !b.entryDate) return 0;
        return new Date(a.entryDate).getTime() - new Date(b.entryDate).getTime();
      },
      render: (date: string | undefined) => {
        if (!date) return <span style={{ color: colors.text.tertiary }}>-</span>;
        const d = new Date(date);
        
        // Detect user's timezone automatically
        const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        
        const dateStr = d.toLocaleDateString('en-US', { 
          month: '2-digit', 
          day: '2-digit', 
          year: '2-digit',
          timeZone: userTimezone
        });
        
        const timeStr = d.toLocaleTimeString('en-US', { 
          hour: '2-digit', 
          minute: '2-digit', 
          hour12: false,
          timeZone: userTimezone
        });
        
        return (
          <div style={{ fontSize: '13px' }}>
            <div>{dateStr}</div>
            <div style={{ color: colors.text.secondary, fontSize: '11px' }}>
              {timeStr}
            </div>
          </div>
        );
      },
    },
    {
      title: 'Exchange',
      dataIndex: 'exchange',
      key: 'exchange',
      width: 100,
      filters: [
        { text: 'NYSE', value: 'NYSE' },
        { text: 'NASDAQ', value: 'NASDAQ' },
        { text: 'AMEX', value: 'AMEX' },
      ],
      onFilter: (value, record) => record.exchange === value,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 100,
      align: 'center',
      fixed: 'right',
      render: (_: unknown, record: Position) => (
        <Button
          type="primary"
          danger
          size="small"
          icon={<CloseOutlined />}
          loading={closingPositions.has(record.symbol)}
          onClick={() => handleClosePosition(record.symbol, record.quantity)}
        >
          Close
        </Button>
      ),
    },
  ];

  // Empty state
  if (!loading && positions.length === 0) {
    return (
      <div
        style={{
          textAlign: 'center',
          padding: '48px 24px',
          color: colors.text.tertiary,
        }}
      >
        <p style={{ fontSize: '16px', marginBottom: '8px' }}>
          No open positions
        </p>
        <p style={{ fontSize: '14px' }}>
          Place an order to see your positions here
        </p>
      </div>
    );
  }

  return (
    <Table<Position>
      columns={columns}
      dataSource={positions}
      loading={loading}
      rowKey="symbol"
      pagination={false}
      scroll={{ x: 1000 }}
      size="middle"
      style={{
        background: colors.backgrounds.secondary,
      }}
      rowClassName={(record) => {
        // Highlight profitable positions
        return record.unrealizedPnL > 0 ? 'position-row-profit' : '';
      }}
    />
  );
};
