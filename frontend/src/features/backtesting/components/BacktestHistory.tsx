/**
 * BacktestHistory Component
 * 
 * Displays a list of past backtests with filtering, sorting, and actions.
 * Allows users to view results or delete backtests.
 */

import React, { useState } from 'react';
import { 
  Card, 
  Table, 
  Button, 
  Space, 
  Tag, 
  Popconfirm, 
  Empty,
  Input,
  Select,
} from 'antd';
import { 
  HistoryOutlined, 
  DeleteOutlined, 
  EyeOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import type { BacktestSummary } from '../../../types/backtest';

const { Search } = Input;

interface BacktestHistoryProps {
  backtests: BacktestSummary[];
  total: number;
  page: number;
  pageSize: number;
  loading?: boolean;
  onPageChange: (page: number, pageSize: number) => void;
  onView: (backtestId: string) => void;
  onDelete: (backtestId: string) => void;
  strategies?: Array<{ id: string; name: string }>;
  onStrategyFilter?: (strategyId: string | null) => void;
}

export const BacktestHistory: React.FC<BacktestHistoryProps> = ({
  backtests,
  total,
  page,
  pageSize,
  loading = false,
  onPageChange,
  onView,
  onDelete,
  strategies = [],
  onStrategyFilter,
}) => {
  const [searchText, setSearchText] = useState('');

  // Filter backtests by search text
  const filteredBacktests = searchText
    ? backtests.filter((bt) =>
        bt.strategy_name.toLowerCase().includes(searchText.toLowerCase()) ||
        bt.id.toLowerCase().includes(searchText.toLowerCase())
      )
    : backtests;

  // Status badge
  const getStatusTag = (status: string) => {
    const statusConfig = {
      completed: { color: 'success', text: 'Completed' },
      running: { color: 'processing', text: 'Running' },
      pending: { color: 'default', text: 'Pending' },
      failed: { color: 'error', text: 'Failed' },
    };

    const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.pending;
    return <Tag color={config.color}>{config.text}</Tag>;
  };

  const getOriginTag = (origin?: string) => {
    const normalized = (origin || 'ui').toLowerCase();
    if (normalized === 'optuna') return <Tag color="purple">Optuna</Tag>;
    if (normalized === 'backend') return <Tag color="geekblue">Backend</Tag>;
    return <Tag color="green">UI</Tag>;
  };

  const getEngineTag = (engine?: string) => {
    const normalized = (engine || 'platform').toLowerCase();
    if (normalized === 'research') return <Tag color="gold">Research</Tag>;
    return <Tag color="blue">Platform</Tag>;
  };

  // Table columns
  const columns: ColumnsType<BacktestSummary> = [
    {
      title: 'Strategy',
      dataIndex: 'strategy_name',
      key: 'strategy_name',
      fixed: 'left',
      width: 200,
      render: (name: string) => (
        <span style={{ fontWeight: 600 }}>{name}</span>
      ),
    },
    {
      title: 'Origin',
      dataIndex: 'origin',
      key: 'origin',
      width: 110,
      render: (origin: string | undefined) => getOriginTag(origin),
    },
    {
      title: 'Engine',
      dataIndex: 'engine',
      key: 'engine',
      width: 120,
      render: (engine: string | undefined) => getEngineTag(engine),
    },
    {
      title: 'Period',
      key: 'period',
      width: 200,
      render: (_, record) => (
        <span>
          {dayjs(record.start_date).format('MMM DD, YYYY')} - {dayjs(record.end_date).format('MMM DD, YYYY')}
        </span>
      ),
    },
    {
      title: 'Initial Capital',
      dataIndex: 'initial_capital',
      key: 'initial_capital',
      width: 140,
      align: 'right',
      render: (capital: number) => `$${capital.toLocaleString()}`,
    },
    {
      title: 'Final Equity',
      dataIndex: 'final_equity',
      key: 'final_equity',
      width: 140,
      align: 'right',
      sorter: (a, b) => (a.final_equity || 0) - (b.final_equity || 0),
      render: (equity: number | undefined, record) => {
        if (equity === undefined) return '-';
        const color = equity >= record.initial_capital ? '#52c41a' : '#ff4d4f';
        return (
          <span style={{ color, fontWeight: 600 }}>
            ${equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        );
      },
    },
    {
      title: 'Return',
      dataIndex: 'total_return',
      key: 'total_return',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.total_return || 0) - (b.total_return || 0),
      render: (returnValue: number | undefined) => {
        if (returnValue === undefined) return '-';
        const color = returnValue >= 0 ? '#52c41a' : '#ff4d4f';
        return (
          <span style={{ color, fontWeight: 600 }}>
            {returnValue >= 0 ? '+' : ''}{(returnValue * 100).toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: 'Sharpe',
      dataIndex: 'sharpe_ratio',
      key: 'sharpe_ratio',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.sharpe_ratio || 0) - (b.sharpe_ratio || 0),
      render: (sharpe: number | undefined) => 
        sharpe !== undefined ? sharpe.toFixed(2) : '-',
    },
    {
      title: 'Max DD',
      dataIndex: 'max_drawdown',
      key: 'max_drawdown',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.max_drawdown || 0) - (b.max_drawdown || 0),
      render: (drawdown: number | undefined) => 
        drawdown !== undefined ? `${(drawdown * 100).toFixed(2)}%` : '-',
    },
    {
      title: 'Trades',
      dataIndex: 'total_trades',
      key: 'total_trades',
      width: 80,
      align: 'right',
      sorter: (a, b) => (a.total_trades || 0) - (b.total_trades || 0),
      render: (trades: number | undefined) => trades || '-',
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      filters: [
        { text: 'Completed', value: 'completed' },
        { text: 'Running', value: 'running' },
        { text: 'Pending', value: 'pending' },
        { text: 'Failed', value: 'failed' },
      ],
      onFilter: (value, record) => record.status === value,
      render: (status: string) => getStatusTag(status),
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 140,
      sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      render: (date: string) => dayjs(date).format('MMM DD, HH:mm'),
    },
    {
      title: 'Actions',
      key: 'actions',
      fixed: 'right',
      width: 140,
      render: (_, record) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => onView(record.id)}
          >
            View
          </Button>
          <Popconfirm
            title="Delete backtest"
            description="Are you sure you want to delete this backtest?"
            onConfirm={() => onDelete(record.id)}
            okText="Delete"
            okType="danger"
            cancelText="Cancel"
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={
        <Space>
          <HistoryOutlined />
          Backtest History
        </Space>
      }
      extra={
        <Space>
          {strategies.length > 0 && onStrategyFilter && (
            <Select
              placeholder="Filter by strategy"
              style={{ width: 200 }}
              allowClear
              onChange={onStrategyFilter}
            >
              {strategies.map((strategy) => (
                <Select.Option key={strategy.id} value={strategy.id}>
                  {strategy.name}
                </Select.Option>
              ))}
            </Select>
          )}
          <Search
            placeholder="Search backtests..."
            allowClear
            style={{ width: 250 }}
            onChange={(e) => setSearchText(e.target.value)}
            prefix={<SearchOutlined />}
          />
        </Space>
      }
    >
      {filteredBacktests.length === 0 && !loading ? (
        <Empty
          description="No backtests found"
          style={{ padding: '60px 0' }}
        />
      ) : (
        <Table
          columns={columns}
          dataSource={filteredBacktests}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            onChange: onPageChange,
            showSizeChanger: true,
            showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} backtests`,
            pageSizeOptions: ['10', '20', '50'],
          }}
          scroll={{ x: 1600 }}
          size="small"
        />
      )}
    </Card>
  );
};

export default BacktestHistory;
