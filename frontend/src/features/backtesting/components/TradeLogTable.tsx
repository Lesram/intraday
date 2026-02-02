/**
 * TradeLogTable Component
 * 
 * Displays the detailed trade log from a backtest in a sortable, paginated table.
 * Shows entry/exit prices, P&L, duration, and other trade details.
 */

import React from 'react';
import { Card, Table, Tag, Empty, Spin } from 'antd';
import { UnorderedListOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import type { Trade } from '../../../types/backtest';

interface TradeLogTableProps {
  trades: Trade[];
  loading?: boolean;
}

export const TradeLogTable: React.FC<TradeLogTableProps> = ({ trades, loading = false }) => {
  // Define table columns
  const columns: ColumnsType<Trade> = [
    {
      title: 'Symbol',
      dataIndex: 'symbol',
      key: 'symbol',
      fixed: 'left',
      width: 100,
      render: (symbol: string) => (
        <span style={{ fontWeight: 600 }}>{symbol}</span>
      ),
    },
    {
      title: 'Side',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      filters: [
        { text: 'Buy', value: 'buy' },
        { text: 'Sell', value: 'sell' },
      ],
      onFilter: (value, record) => record.side === value,
      render: (side: 'buy' | 'sell') => (
        <Tag 
          color={side === 'buy' ? 'green' : 'red'}
          icon={side === 'buy' ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
        >
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
    },
    {
      title: 'Entry Date',
      dataIndex: 'entry_date',
      key: 'entry_date',
      width: 120,
      sorter: (a, b) => new Date(a.entry_date).getTime() - new Date(b.entry_date).getTime(),
      render: (date: string) => dayjs(date).format('MMM DD, YYYY'),
    },
    {
      title: 'Entry Price',
      dataIndex: 'entry_price',
      key: 'entry_price',
      width: 120,
      align: 'right',
      sorter: (a, b) => a.entry_price - b.entry_price,
      render: (price: number) => `$${price.toFixed(2)}`,
    },
    {
      title: 'Exit Date',
      dataIndex: 'exit_date',
      key: 'exit_date',
      width: 120,
      sorter: (a, b) => {
        if (!a.exit_date) return 1;
        if (!b.exit_date) return -1;
        return new Date(a.exit_date).getTime() - new Date(b.exit_date).getTime();
      },
      render: (date: string | undefined | null) => 
        date ? dayjs(date).format('MMM DD, YYYY') : <Tag>Open</Tag>,
    },
    {
      title: 'Exit Price',
      dataIndex: 'exit_price',
      key: 'exit_price',
      width: 120,
      align: 'right',
      sorter: (a, b) => (a.exit_price || 0) - (b.exit_price || 0),
      render: (price: number | undefined | null) => 
        price !== undefined && price !== null ? `$${price.toFixed(2)}` : '-',
    },
    {
      title: 'Duration',
      dataIndex: 'duration_days',
      key: 'duration_days',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.duration_days || 0) - (b.duration_days || 0),
      render: (days: number | undefined | null) => 
        days !== undefined && days !== null ? `${days} days` : '-',
    },
    {
      title: 'P&L',
      dataIndex: 'pnl',
      key: 'pnl',
      width: 120,
      align: 'right',
      sorter: (a, b) => (a.pnl || 0) - (b.pnl || 0),
      render: (pnl: number | undefined | null) => {
        if (pnl === undefined || pnl === null) return '-';
        const color = pnl >= 0 ? '#52c41a' : '#ff4d4f';
        return (
          <span style={{ color, fontWeight: 600 }}>
            {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
          </span>
        );
      },
    },
    {
      title: 'P&L %',
      dataIndex: 'pnl_percent',
      key: 'pnl_percent',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.pnl_percent || 0) - (b.pnl_percent || 0),
      render: (pnl_percent: number | undefined | null) => {
        if (pnl_percent === undefined || pnl_percent === null) return '-';
        const color = pnl_percent >= 0 ? '#52c41a' : '#ff4d4f';
        return (
          <span style={{ color, fontWeight: 600 }}>
            {pnl_percent >= 0 ? '+' : ''}{(pnl_percent * 100).toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: 'Commission',
      dataIndex: 'commission',
      key: 'commission',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.commission || 0) - (b.commission || 0),
      render: (commission: number | undefined | null) => 
        commission !== undefined && commission !== null ? `$${commission.toFixed(2)}` : '$0.00',
    },
  ];

  if (loading) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <Spin size="large" />
        </div>
      </Card>
    );
  }

  if (!trades || trades.length === 0) {
    return (
      <Card>
        <Empty description="No trades executed during this backtest" />
      </Card>
    );
  }

  return (
    <Card
      title={
        <span>
          <UnorderedListOutlined style={{ marginRight: 8 }} />
          Trade Log ({trades.length} trades)
        </span>
      }
    >
      <Table
        columns={columns}
        dataSource={trades}
        rowKey={(record) => `${record.symbol}-${record.entry_date}-${record.entry_price}`}
        pagination={{
          defaultPageSize: 10,
          showSizeChanger: true,
          showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} trades`,
          pageSizeOptions: ['10', '20', '50', '100'],
        }}
        scroll={{ x: 1300 }}
        size="small"
      />
    </Card>
  );
};

export default TradeLogTable;
