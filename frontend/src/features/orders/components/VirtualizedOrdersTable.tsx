/**
 * Virtualized Orders Table
 * High-performance orders table using AG Grid for large datasets
 * 
 * Use this component when:
 * - Displaying 500+ orders
 * - Real-time streaming updates from WebSocket
 * - Need smooth scrolling with large datasets
 * 
 * For smaller datasets (<500 rows), the standard ActiveOrdersTable
 * with Ant Design Table is sufficient.
 */

import React, { useMemo, useCallback } from 'react';
import { Button, Tooltip, Popconfirm, Tag } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import type { ColDef, ICellRendererParams, GetRowIdParams } from 'ag-grid-community';
import VirtualizedGrid from '@/components/VirtualizedGrid';
import { gridFormatters } from '@/components/gridUtils';
import { useCancelOrder } from '@/hooks/useData';
import { colors } from '@/styles/theme';
import type { Order, OrderStatus } from '@/store/ordersStore';

interface VirtualizedOrdersTableProps {
  orders: Order[];
  loading?: boolean;
  height?: number | string;
}

// Status color mapping
const statusColors: Record<OrderStatus, string> = {
  pending: colors.semantic.warning,
  submitted: colors.semantic.info,
  accepted: colors.semantic.info,
  partially_filled: colors.semantic.warning,
  filled: colors.semantic.success,
  cancelled: colors.text.secondary,
  rejected: colors.semantic.error,
};

// Status tag cell renderer using React
const StatusCellRenderer: React.FC<ICellRendererParams<Order>> = (props) => {
  const status = props.value as OrderStatus;
  const color = statusColors[status] || colors.text.secondary;
  
  return (
    <Tag 
      color={color}
      style={{ 
        margin: 0,
        textTransform: 'uppercase',
        fontSize: '10px',
        fontWeight: 600,
      }}
    >
      {status}
    </Tag>
  );
};

// Side indicator cell renderer
const SideCellRenderer: React.FC<ICellRendererParams<Order>> = (props) => {
  const side = props.value as string;
  const isBuy = side?.toLowerCase() === 'buy';
  const color = isBuy ? colors.semantic.success : colors.semantic.error;
  
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '4px',
      color,
      fontWeight: 600,
    }}>
      <span style={{
        display: 'inline-block',
        width: '6px',
        height: '6px',
        borderRadius: '50%',
        backgroundColor: color,
      }} />
      {side?.toUpperCase()}
    </span>
  );
};

// Actions cell renderer with cancel button
const ActionsCellRenderer: React.FC<ICellRendererParams<Order>> = (props) => {
  const cancelOrderMutation = useCancelOrder();
  const order = props.data;
  
  if (!order) return null;
  
  const canCancel = ['pending', 'submitted', 'accepted', 'partially_filled'].includes(order.status);
  
  if (!canCancel) return null;
  
  const handleCancel = async () => {
    try {
      await cancelOrderMutation.mutateAsync(order.orderId);
    } catch (error) {
      console.error('Failed to cancel order:', error);
    }
  };
  
  return (
    <Popconfirm
      title="Cancel Order"
      description={`Cancel ${order.side} order for ${order.symbol}?`}
      onConfirm={handleCancel}
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
  );
};

export const VirtualizedOrdersTable: React.FC<VirtualizedOrdersTableProps> = ({
  orders,
  loading = false,
  height = 600,
}) => {
  // Column definitions for AG Grid
  const columnDefs = useMemo<ColDef<Order>[]>(() => [
    {
      headerName: 'Date & Time',
      field: 'createdAt',
      width: 170,
      valueFormatter: gridFormatters.dateTime,
      sort: 'desc',
    },
    {
      headerName: 'Symbol',
      field: 'symbol',
      width: 100,
      cellStyle: { fontWeight: 600, fontFamily: 'monospace' },
    },
    {
      headerName: 'Side',
      field: 'side',
      width: 80,
      cellRenderer: SideCellRenderer,
    },
    {
      headerName: 'Type',
      field: 'orderType',
      width: 90,
      valueFormatter: (params) => params.value?.toUpperCase() || '-',
    },
    {
      headerName: 'Qty',
      field: 'quantity',
      width: 80,
      type: 'numericColumn',
      valueFormatter: gridFormatters.number(0),
    },
    {
      headerName: 'Filled',
      field: 'filledQuantity',
      width: 80,
      type: 'numericColumn',
      valueFormatter: gridFormatters.number(0),
    },
    {
      headerName: 'Limit Price',
      field: 'limitPrice',
      width: 110,
      type: 'numericColumn',
      valueFormatter: gridFormatters.currency,
    },
    {
      headerName: 'Avg Fill',
      field: 'averageFillPrice',
      width: 110,
      type: 'numericColumn',
      valueFormatter: gridFormatters.currency,
    },
    {
      headerName: 'Status',
      field: 'status',
      width: 130,
      cellRenderer: StatusCellRenderer,
    },
    {
      headerName: 'TIF',
      field: 'timeInForce',
      width: 70,
      valueFormatter: (params) => params.value?.toUpperCase() || '-',
    },
    {
      headerName: 'Strategy',
      field: 'strategyId',
      width: 120,
      valueFormatter: (params) => params.value || '-',
    },
    {
      headerName: '',
      field: 'orderId',
      width: 60,
      sortable: false,
      filter: false,
      resizable: false,
      cellRenderer: ActionsCellRenderer,
    },
  ], []);

  // Row ID getter
  const getRowId = useCallback((params: GetRowIdParams<Order>) => {
    return params.data.orderId;
  }, []);

  // Row class for highlighting recently updated rows
  const getRowClass = useCallback((params: { data?: Order }) => {
    if (!params.data) return undefined;
    const updatedAt = new Date(params.data.updatedAt).getTime();
    const isRecent = Date.now() - updatedAt < 3000;
    return isRecent ? 'highlight-row' : undefined;
  }, []);

  return (
    <VirtualizedGrid<Order>
      rowData={orders}
      columnDefs={columnDefs}
      getRowId={getRowId}
      getRowClass={getRowClass}
      loading={loading}
      height={height}
      rowHeight={40}
    />
  );
};

export default VirtualizedOrdersTable;
