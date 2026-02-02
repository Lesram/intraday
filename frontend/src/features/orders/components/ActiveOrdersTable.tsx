/**
 * Active Orders Table
 * Displays pending/open orders with real-time updates via WebSocket
 */

import { Table, Tag, Button, Space, Typography, Tooltip, Popconfirm } from 'antd';
import { 
  DeleteOutlined, 
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { formatCurrency, formatDateTime } from '@/utils/formatters';
import { useCancelOrder } from '@/hooks/useData';
import { colors } from '@/styles/theme';
import type { Order, OrderStatus } from '@/store/ordersStore';

const { Text } = Typography;

interface ActiveOrdersTableProps {
  orders: Order[];
  loading?: boolean;
}

// Status color mapping
const getStatusColor = (status: OrderStatus): string => {
  switch (status) {
    case 'pending':
    case 'submitted':
      return 'processing';
    case 'partially_filled':
      return 'warning';
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

// Status icon mapping
const getStatusIcon = (status: OrderStatus) => {
  switch (status) {
    case 'pending':
    case 'submitted':
      return <SyncOutlined spin />;
    case 'partially_filled':
      return <ClockCircleOutlined />;
    case 'filled':
      return <CheckCircleOutlined />;
    case 'cancelled':
      return <CloseCircleOutlined />;
    case 'rejected':
      return <CloseCircleOutlined />;
    default:
      return null;
  }
};

export const ActiveOrdersTable: React.FC<ActiveOrdersTableProps> = ({ 
  orders, 
  loading = false 
}) => {
  const cancelOrderMutation = useCancelOrder();

  const handleCancelOrder = async (orderId: string) => {
    try {
      await cancelOrderMutation.mutateAsync(orderId);
    } catch (error) {
      console.error('Failed to cancel order:', error);
    }
  };

  const columns: ColumnsType<Order> = [
    {
      title: 'Date & Time',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 180,
      render: (createdAt: string) => {
        const date = new Date(createdAt);
        const dateStr = date.toLocaleDateString('en-US', { 
          year: 'numeric', 
          month: '2-digit', 
          day: '2-digit' 
        });
        const timeStr = date.toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false
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
      title: 'Qty',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 80,
      align: 'right',
      render: (quantity: number) => (
        <Text style={{ fontFamily: 'monospace' }}>{quantity}</Text>
      ),
    },
    {
      title: 'Filled',
      dataIndex: 'filledQuantity',
      key: 'filledQuantity',
      width: 80,
      align: 'right',
      render: (filledQuantity: number, record: Order) => (
        <Text 
          style={{ 
            fontFamily: 'monospace',
            color: filledQuantity > 0 ? colors.semantic.profit : colors.text.secondary
          }}
        >
          {filledQuantity} / {record.quantity}
        </Text>
      ),
    },
    {
      title: 'Limit Price',
      dataIndex: 'limitPrice',
      key: 'limitPrice',
      width: 120,
      align: 'right',
      render: (limitPrice?: number) => (
        <Text style={{ fontFamily: 'monospace' }}>
          {limitPrice ? formatCurrency(limitPrice) : '-'}
        </Text>
      ),
    },
    {
      title: 'Avg Fill',
      dataIndex: 'averageFillPrice',
      key: 'averageFillPrice',
      width: 120,
      align: 'right',
      render: (avgFillPrice?: number) => (
        <Text style={{ fontFamily: 'monospace' }}>
          {avgFillPrice ? formatCurrency(avgFillPrice) : '-'}
        </Text>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 140,
      render: (status: OrderStatus) => (
        <Tag 
          color={getStatusColor(status)}
          icon={getStatusIcon(status)}
        >
          {status.replace('_', ' ').toUpperCase()}
        </Tag>
      ),
      filters: [
        { text: 'Pending', value: 'pending' },
        { text: 'Submitted', value: 'submitted' },
        { text: 'Partially Filled', value: 'partially_filled' },
        { text: 'Filled', value: 'filled' },
      ],
      onFilter: (value, record) => record.status === value,
    },
    {
      title: 'TIF',
      dataIndex: 'timeInForce',
      key: 'timeInForce',
      width: 60,
      render: (tif: string) => (
        <Text type="secondary" style={{ fontSize: '11px' }}>
          {tif.toUpperCase()}
        </Text>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 100,
      align: 'center',
      fixed: 'right',
      render: (_: unknown, record: Order) => {
        const canCancel = ['pending', 'submitted', 'partially_filled'].includes(record.status);
        
        if (!canCancel) {
          return <Text type="secondary" style={{ fontSize: '12px' }}>-</Text>;
        }

        return (
          <Space size="small">
            <Popconfirm
              title="Cancel Order"
              description={`Cancel ${record.side} order for ${record.symbol}?`}
              onConfirm={() => handleCancelOrder(record.orderId)}
              okText="Yes"
              cancelText="No"
              okButtonProps={{ danger: true }}
            >
              <Tooltip title="Cancel Order">
                <Button
                  type="text"
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                  loading={cancelOrderMutation.isPending}
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <Table<Order>
      columns={columns}
      dataSource={orders}
      rowKey="orderId"
      loading={loading}
      pagination={{
        pageSize: 20,
        showSizeChanger: true,
        showTotal: (total) => `Total ${total} orders`,
        pageSizeOptions: ['10', '20', '50', '100'],
      }}
      scroll={{ x: 1200 }}
      size="small"
      style={{
        background: colors.backgrounds.secondary,
      }}
      rowClassName={(record) => {
        // Highlight recently updated rows
        const updatedRecently = new Date().getTime() - new Date(record.updatedAt).getTime() < 3000;
        return updatedRecently ? 'highlight-row' : '';
      }}
    />
  );
};
