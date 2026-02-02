/**
 * Order History Table
 * Displays completed and cancelled orders with filters and search
 */

import { Table, Tag, Typography, Tooltip, DatePicker, Input, Space, Button } from 'antd';
import { SearchOutlined, DownloadOutlined } from '@ant-design/icons';
import { useState } from 'react';
import type { ColumnsType } from 'antd/es/table';
import type { Dayjs } from 'dayjs';
import { formatCurrency, formatDateTime } from '@/utils/formatters';
import { colors } from '@/styles/theme';
import type { Order, OrderStatus } from '@/store/ordersStore';

const { Text } = Typography;
const { RangePicker } = DatePicker;

interface OrderHistoryTableProps {
  orders: Order[];
  loading?: boolean;
}

// Status color mapping
const getStatusColor = (status: OrderStatus): string => {
  switch (status) {
    case 'filled':
      return 'success';
    case 'cancelled':
      return 'default';
    case 'rejected':
      return 'error';
    default:
      return 'default';
  }
};

export const OrderHistoryTable: React.FC<OrderHistoryTableProps> = ({ 
  orders, 
  loading = false 
}) => {
  const [searchText, setSearchText] = useState('');
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);

  // Filter orders based on search and date range
  const filteredOrders = orders.filter(order => {
    const matchesSearch = !searchText || 
      order.symbol.toLowerCase().includes(searchText.toLowerCase()) ||
      order.orderId.toLowerCase().includes(searchText.toLowerCase());
    
    const matchesDateRange = !dateRange || !dateRange[0] || !dateRange[1] || (
      new Date(order.createdAt) >= dateRange[0].toDate() &&
      new Date(order.createdAt) <= dateRange[1].toDate()
    );

    return matchesSearch && matchesDateRange;
  });

  const handleExport = () => {
    // Export to CSV
    const headers = ['Time', 'Symbol', 'Side', 'Type', 'Quantity', 'Filled', 'Avg Price', 'Status'];
    const rows = filteredOrders.map(order => [
      formatDateTime(order.createdAt),
      order.symbol,
      order.side,
      order.orderType,
      order.quantity,
      order.filledQuantity,
      order.averageFillPrice || '',
      order.status,
    ]);

    const csv = [
      headers.join(','),
      ...rows.map(row => row.join(','))
    ].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `order-history-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const columns: ColumnsType<Order> = [
    {
      title: 'Date & Time',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 180,
      render: (createdAt: string) => {
        const date = new Date(createdAt);
        
        // Detect user's timezone automatically
        const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        
        const dateStr = date.toLocaleDateString('en-US', { 
          year: 'numeric', 
          month: '2-digit', 
          day: '2-digit',
          timeZone: userTimezone
        });
        const timeStr = date.toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
          timeZone: userTimezone
        });
        return (
          <Tooltip title={formatDateTime(createdAt)}>
            <div style={{ fontFamily: 'monospace', fontSize: '12px' }}>
              <div style={{ fontWeight: 'bold' }}>{dateStr}</div>
              <div style={{ color: colors.text.secondary }}>{timeStr}</div>
            </div>
          </Tooltip>
        );
      },
      sorter: (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
      defaultSortOrder: 'descend',
    },
    {
      title: 'Symbol',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 100,
      render: (symbol: string) => (
        <Text strong style={{ fontFamily: 'monospace', fontSize: '14px' }}>
          {symbol}
        </Text>
      ),
      sorter: (a, b) => a.symbol.localeCompare(b.symbol),
    },
    {
      title: 'Side',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: 'buy' | 'sell') => (
        <Tag 
          color={side === 'buy' ? 'green' : 'red'}
          style={{ fontWeight: 'bold' }}
        >
          {side.toUpperCase()}
        </Tag>
      ),
      filters: [
        { text: 'Buy', value: 'buy' },
        { text: 'Sell', value: 'sell' },
      ],
      onFilter: (value, record) => record.side === value,
    },
    {
      title: 'Type',
      dataIndex: 'orderType',
      key: 'orderType',
      width: 100,
      render: (orderType: string) => (
        <Tag color="blue">{orderType.toUpperCase()}</Tag>
      ),
    },
    {
      title: 'Quantity',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 100,
      align: 'right',
      render: (quantity: number) => (
        <Text style={{ fontFamily: 'monospace' }}>{quantity}</Text>
      ),
    },
    {
      title: 'Filled',
      dataIndex: 'filledQuantity',
      key: 'filledQuantity',
      width: 100,
      align: 'right',
      render: (filledQuantity: number, record: Order) => {
        const percentage = record.quantity > 0 
          ? (filledQuantity / record.quantity * 100).toFixed(0) 
          : 0;
        
        return (
          <Tooltip title={`${percentage}% filled`}>
            <Text 
              style={{ 
                fontFamily: 'monospace',
                color: filledQuantity === record.quantity 
                  ? colors.semantic.profit 
                  : colors.text.secondary
              }}
            >
              {filledQuantity} / {record.quantity}
            </Text>
          </Tooltip>
        );
      },
    },
    {
      title: 'Avg Price',
      dataIndex: 'averageFillPrice',
      key: 'averageFillPrice',
      width: 120,
      align: 'right',
      render: (avgFillPrice?: number) => (
        <Text style={{ fontFamily: 'monospace', fontWeight: avgFillPrice ? 'bold' : 'normal' }}>
          {avgFillPrice ? formatCurrency(avgFillPrice) : '-'}
        </Text>
      ),
    },
    {
      title: 'Total Value',
      key: 'totalValue',
      width: 120,
      align: 'right',
      render: (_: unknown, record: Order) => {
        const totalValue = record.averageFillPrice && record.filledQuantity
          ? record.averageFillPrice * record.filledQuantity
          : 0;
        
        return (
          <Text 
            strong 
            style={{ 
              fontFamily: 'monospace',
              color: totalValue > 0 ? colors.text.primary : colors.text.secondary
            }}
          >
            {totalValue > 0 ? formatCurrency(totalValue) : '-'}
          </Text>
        );
      },
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: OrderStatus, record: Order) => (
        <Tooltip 
          title={
            status === 'rejected' && record.rejectionReason 
              ? `Rejected: ${record.rejectionReason}` 
              : undefined
          }
        >
          <Tag color={getStatusColor(status)}>
            {status.replace('_', ' ').toUpperCase()}
          </Tag>
        </Tooltip>
      ),
      filters: [
        { text: 'Filled', value: 'filled' },
        { text: 'Cancelled', value: 'cancelled' },
        { text: 'Rejected', value: 'rejected' },
      ],
      onFilter: (value, record) => record.status === value,
    },
    {
      title: 'Completed At',
      key: 'completedAt',
      width: 180,
      render: (_: unknown, record: Order) => {
        const completedAt = record.filledAt || record.cancelledAt;
        return completedAt ? (
          <Text style={{ fontSize: '12px', fontFamily: 'monospace' }}>
            {formatDateTime(completedAt)}
          </Text>
        ) : (
          <Text type="secondary">-</Text>
        );
      },
      sorter: (a, b) => {
        const aTime = a.filledAt || a.cancelledAt || '';
        const bTime = b.filledAt || b.cancelledAt || '';
        return new Date(bTime).getTime() - new Date(aTime).getTime();
      },
    },
  ];

  return (
    <div>
      {/* Filters */}
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <Input
            placeholder="Search by symbol or order ID"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 250 }}
            allowClear
          />
          <RangePicker
            onChange={(dates) => setDateRange(dates)}
            style={{ width: 300 }}
            placeholder={['Start Date', 'End Date']}
          />
        </Space>
        <Button
          icon={<DownloadOutlined />}
          onClick={handleExport}
          disabled={filteredOrders.length === 0}
        >
          Export CSV
        </Button>
      </Space>

      {/* Table */}
      <Table<Order>
        columns={columns}
        dataSource={filteredOrders}
        rowKey="orderId"
        loading={loading}
        pagination={{
          pageSize: 50,
          showSizeChanger: true,
          showTotal: (total) => `Total ${total} orders`,
          pageSizeOptions: ['20', '50', '100', '200'],
        }}
        scroll={{ x: 1400 }}
        size="small"
        style={{
          background: colors.backgrounds.secondary,
        }}
        summary={(pageData) => {
          // Calculate summary statistics
          const totalFilled = pageData.filter(o => o.status === 'filled').length;
          const totalCancelled = pageData.filter(o => o.status === 'cancelled').length;
          const totalRejected = pageData.filter(o => o.status === 'rejected').length;
          
          const totalVolume = pageData
            .filter(o => o.averageFillPrice && o.filledQuantity)
            .reduce((sum, o) => sum + (o.averageFillPrice! * o.filledQuantity), 0);

          return (
            <Table.Summary fixed>
              <Table.Summary.Row style={{ background: colors.backgrounds.tertiary }}>
                <Table.Summary.Cell index={0} colSpan={2}>
                  <Text strong>Summary (Page)</Text>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={2} colSpan={2}>
                  <div style={{ display: 'flex', gap: '12px', flexWrap: 'nowrap', whiteSpace: 'nowrap' }}>
                    <Text type="success" style={{ fontSize: '13px' }}>Filled: {totalFilled}</Text>
                    <Text type="secondary" style={{ fontSize: '13px' }}>Cancelled: {totalCancelled}</Text>
                    <Text type="danger" style={{ fontSize: '13px' }}>Rejected: {totalRejected}</Text>
                  </div>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={4} colSpan={4} align="right">
                  <Text strong>Total Volume: {formatCurrency(totalVolume)}</Text>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={8} colSpan={2} />
              </Table.Summary.Row>
            </Table.Summary>
          );
        }}
      />
    </div>
  );
};
