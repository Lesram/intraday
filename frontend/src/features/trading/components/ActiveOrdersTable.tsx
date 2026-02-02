/**
 * Active Orders Table
 * Displays open/pending orders with real-time updates
 */

import React, { useMemo } from 'react';
import { Table, Tag, Button, Space, Popconfirm, message, Typography, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CloseOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { useOrdersStore } from '@/store/ordersStore';
import type { Order, OrderStatus, OrderSide } from '@/store/ordersStore';
import { formatCurrency, formatNumber } from '@/utils/formatters';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ordersService } from '@/services/ordersService';

const { Text } = Typography;

const getStatusColor = (status: OrderStatus): string => {
  const colors: Record<OrderStatus, string> = {
    pending: 'blue',
    submitted: 'cyan',
    accepted: 'cyan',
    partially_filled: 'orange',
    filled: 'green',
    cancelled: 'default',
    rejected: 'red',
  };
  return colors[status] || 'default';
};

const getStatusIcon = (status: OrderStatus): React.ReactNode => {
  const icons: Record<OrderStatus, React.ReactNode> = {
    pending: <ClockCircleOutlined />,
    submitted: <ClockCircleOutlined />,
    accepted: <CheckCircleOutlined />,
    partially_filled: <SyncOutlined spin />,
    filled: <CheckCircleOutlined />,
    cancelled: <CloseOutlined />,
    rejected: <CloseOutlined />,
  };
  return icons[status] || null;
};

const getSideColor = (side: OrderSide): string => {
  return side === 'buy' ? '#52c41a' : '#ff4d4f';
};

export const ActiveOrdersTable: React.FC = () => {
  const orders = useOrdersStore((state) => state.orders);
  const updateOrder = useOrdersStore((state) => state.updateOrder);
  const _removeOrder = useOrdersStore((state) => state.removeOrder);
  const queryClient = useQueryClient();

  // Only show active orders (pending, submitted, partially_filled)
  const activeOrders = useMemo(() => {
    return orders.filter((order) =>
      ['pending', 'submitted', 'partially_filled'].includes(order.status)
    );
  }, [orders]);

  const { mutate: cancelOrder, isPending: isCancelling } = useMutation({
    mutationFn: (orderId: string) => ordersService.cancelOrder(orderId),
    onSuccess: (cancelledOrder) => {
      message.success(`Order ${cancelledOrder.orderId} cancelled successfully`);
      updateOrder(cancelledOrder.orderId, cancelledOrder);
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || 'Failed to cancel order');
    },
  });

  const handleCancel = (orderId: string) => {
    cancelOrder(orderId);
  };

  const columns: ColumnsType<Order> = [
    {
      title: 'Time',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 100,
      render: (date: string) => {
        const d = new Date(date);
        return (
          <Tooltip title={d.toLocaleString()}>
            <Text>{d.toLocaleTimeString()}</Text>
          </Tooltip>
        );
      },
    },
    {
      title: 'Symbol',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 100,
      render: (symbol: string) => (
        <Text strong style={{ fontSize: 14 }}>
          {symbol}
        </Text>
      ),
    },
    {
      title: 'Side',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: OrderSide) => (
        <Tag color={getSideColor(side)} style={{ fontWeight: 'bold' }}>
          {side.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Type',
      dataIndex: 'orderType',
      key: 'orderType',
      width: 100,
      render: (type: string) => <Text>{type.toUpperCase()}</Text>,
    },
    {
      title: 'Quantity',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 100,
      align: 'right',
      render: (qty: number, record: Order) => (
        <Space direction="vertical" size={0}>
          <Text>{formatNumber(qty)}</Text>
          {record.filledQuantity > 0 && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              Filled: {formatNumber(record.filledQuantity)}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: 'Limit Price',
      dataIndex: 'limitPrice',
      key: 'limitPrice',
      width: 120,
      align: 'right',
      render: (price?: number) =>
        price ? <Text>{formatCurrency(price)}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Stop Price',
      dataIndex: 'stopPrice',
      key: 'stopPrice',
      width: 120,
      align: 'right',
      render: (price?: number) =>
        price ? <Text>{formatCurrency(price)}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (status: OrderStatus) => (
        <Tag icon={getStatusIcon(status)} color={getStatusColor(status)}>
          {status.toUpperCase().replace('_', ' ')}
        </Tag>
      ),
    },
    {
      title: 'TIF',
      dataIndex: 'timeInForce',
      key: 'timeInForce',
      width: 80,
      render: (tif: string) => (
        <Tooltip title={tif === 'gtc' ? 'Good Til Cancelled' : tif.toUpperCase()}>
          <Text>{tif.toUpperCase()}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 120,
      fixed: 'right',
      render: (_, record: Order) => {
        const canCancel = ['pending', 'submitted', 'partially_filled'].includes(
          record.status
        );

        return (
          <Space size="small">
            {canCancel && (
              <Popconfirm
                title="Cancel Order"
                description="Are you sure you want to cancel this order?"
                onConfirm={() => handleCancel(record.orderId)}
                okText="Yes"
                cancelText="No"
                okButtonProps={{ danger: true }}
              >
                <Button
                  size="small"
                  danger
                  icon={<CloseOutlined />}
                  loading={isCancelling}
                  disabled={isCancelling}
                >
                  Cancel
                </Button>
              </Popconfirm>
            )}
            {!canCancel && <Text type="secondary">—</Text>}
          </Space>
        );
      },
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={activeOrders}
      rowKey="orderId"
      pagination={{
        pageSize: 10,
        showSizeChanger: true,
        showTotal: (total) => `Total ${total} active orders`,
      }}
      size="small"
      loading={false}
      locale={{
        emptyText: 'No active orders',
      }}
      scroll={{ x: 1200 }}
    />
  );
};
