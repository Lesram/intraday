import { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, Input, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { organismApi, type OrganismOrder } from '../organismApi';

const { Text } = Typography;

const STATUS_COLORS: Record<string, string> = {
  filled: 'success',
  partially_filled: 'processing',
  accepted: 'default',
  submitted: 'default',
  cancelled: 'warning',
  rejected: 'error',
  expired: 'warning',
};

const formatDateTime = (value?: string | null) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const formatPrice = (value?: number | null) => {
  if (value == null) return '-';
  return `$${value.toFixed(2)}`;
};

const formatReason = (reason?: string | null) => {
  if (!reason) return '-';
  return reason.replace(/_/g, ' ').replace(/organism /i, '');
};

const OrganismOrdersPanel = () => {
  const [orders, setOrders] = useState<OrganismOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchSymbol, setSearchSymbol] = useState('');

  const fetchOrders = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true);
    try {
      const result = await organismApi.getOrders(200);
      setOrders(result.orders);
    } catch {
      // silently fail — tab just shows empty
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrders(true);
    const interval = setInterval(() => fetchOrders(false), 15000);
    return () => clearInterval(interval);
  }, [fetchOrders]);

  const filteredOrders = useMemo(() => {
    if (!searchSymbol) return orders;
    const q = searchSymbol.toUpperCase();
    return orders.filter((o) => o.symbol.includes(q));
  }, [orders, searchSymbol]);

  const summary = useMemo(() => {
    let filled = 0;
    let cancelled = 0;
    let totalVolume = 0;
    for (const o of orders) {
      if (o.status === 'filled') filled++;
      if (o.status === 'cancelled') cancelled++;
      totalVolume += o.filled_qty ?? 0;
    }
    return { filled, cancelled, totalVolume, total: orders.length };
  }, [orders]);

  const columns: ColumnsType<OrganismOrder> = [
    {
      title: 'Time',
      dataIndex: 'submitted_at',
      key: 'submitted_at',
      width: 170,
      render: (val: string) => <Text style={{ fontSize: 12 }}>{formatDateTime(val)}</Text>,
    },
    {
      title: 'Symbol',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 80,
      render: (val: string) => <Text strong>{val}</Text>,
    },
    {
      title: 'Side',
      dataIndex: 'side',
      key: 'side',
      width: 60,
      render: (val: string) => (
        <Tag color={val === 'buy' ? 'green' : 'orange'}>{val.toUpperCase()}</Tag>
      ),
    },
    {
      title: 'Type',
      dataIndex: 'reason',
      key: 'type',
      width: 80,
      render: (reason: string | null) => {
        const isEntry = reason?.includes('entry');
        const isExit = reason?.includes('exit') || reason?.includes('stop') || reason?.includes('close');
        if (isEntry) return <Tag color="blue">Entry</Tag>;
        if (isExit) return <Tag color="volcano">Exit</Tag>;
        return <Tag>-</Tag>;
      },
    },
    {
      title: 'Qty',
      dataIndex: 'qty',
      key: 'qty',
      width: 70,
      align: 'right',
      render: (val: number) => val?.toFixed(0) ?? '-',
    },
    {
      title: 'Filled',
      dataIndex: 'filled_qty',
      key: 'filled_qty',
      width: 70,
      align: 'right',
      render: (val: number) => val?.toFixed(0) ?? '-',
    },
    {
      title: 'Avg Price',
      dataIndex: 'avg_fill_price',
      key: 'avg_fill_price',
      width: 90,
      align: 'right',
      render: (val: number | null) => formatPrice(val),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (val: string) => (
        <Tag color={STATUS_COLORS[val] ?? 'default'}>{val}</Tag>
      ),
    },
    {
      title: 'Reason',
      dataIndex: 'reason',
      key: 'reason',
      width: 120,
      render: (val: string | null) => (
        <Text style={{ fontSize: 12 }}>{formatReason(val)}</Text>
      ),
    },
    {
      title: 'Conf',
      dataIndex: 'confidence',
      key: 'confidence',
      width: 60,
      align: 'right',
      render: (val: number | null) => (val != null ? val.toFixed(2) : '-'),
    },
    {
      title: 'Tick',
      dataIndex: 'tick',
      key: 'tick',
      width: 55,
      align: 'right',
      render: (val: number | null) => val ?? '-',
    },
  ];

  return (
    <Card
      title="Organism Orders"
      extra={
        <Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {summary.total} total | {summary.filled} filled | {summary.cancelled} cancelled | {summary.totalVolume.toFixed(0)} shares
          </Text>
          <Input.Search
            placeholder="Filter symbol..."
            allowClear
            size="small"
            style={{ width: 160 }}
            onSearch={setSearchSymbol}
            onChange={(e) => { if (!e.target.value) setSearchSymbol(''); }}
          />
        </Space>
      }
    >
      <Table
        dataSource={filteredOrders.map((o) => ({ key: o.order_id, ...o }))}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: ['20', '50', '100'] }}
        size="small"
        scroll={{ x: 1000 }}
        locale={{ emptyText: 'No organism orders found. Orders will appear here as the organism trades.' }}
      />
    </Card>
  );
};

export default OrganismOrdersPanel;
