/**
 * Positions Table Component
 * Displays current portfolio positions with sorting and real-time updates
 */

import { Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { colors } from '@/styles/theme';
import { formatCurrency, formatPercent } from '@/utils/formatters';
import type { Position } from '@/store/portfolioStore';

interface PositionsTableProps {
  positions: Position[];
  loading?: boolean;
}

export const PositionsTable: React.FC<PositionsTableProps> = ({ 
  positions, 
  loading = false 
}) => {
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
      render: (side: 'long' | 'short') => (
        <Tag color={side === 'long' ? 'green' : 'red'}>
          {side.toUpperCase()}
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
      render: (pnl: number, record: Position) => {
        const isProfit = pnl >= 0;
        const icon = isProfit ? <ArrowUpOutlined /> : <ArrowDownOutlined />;
        const color = isProfit ? colors.semantic.profit : colors.semantic.loss;
        
        return (
          <div style={{ color, fontWeight: 'bold' }}>
            {icon} {formatCurrency(Math.abs(pnl))}
            <div style={{ fontSize: '12px', opacity: 0.8 }}>
              {formatPercent(record.unrealizedPnLPercent)}
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
