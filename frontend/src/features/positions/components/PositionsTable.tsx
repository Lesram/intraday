/**
 * Positions Table Component
 * Displays all positions in a sortable, filterable table
 */

import React, { useState, useMemo } from 'react';
import { Table, Tag, Space, Input, Button, Tooltip } from 'antd';
import {
  EyeOutlined,
  CloseOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import type { ColumnsType, SorterResult } from 'antd/es/table/interface';
import { type Position } from '@/store/portfolioStore';

interface PositionsTableProps {
  positions: Position[];
  loading?: boolean;
  onViewDetails: (position: Position) => void;
  onClosePosition: (position: Position) => void;
  onAddToPosition: (position: Position) => void;
}

export const PositionsTable: React.FC<PositionsTableProps> = ({
  positions,
  loading = false,
  onViewDetails,
  onClosePosition,
  onAddToPosition,
}) => {
  const [searchText, setSearchText] = useState('');
  const [sortedInfo, setSortedInfo] = useState<SorterResult<Position>>({});

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value);
  };

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  const getPnLColor = (value: number) => {
    if (value > 0) return '#52c41a';
    if (value < 0) return '#ff4d4f';
    return '#8c8c8c';
  };

  // Filter positions by search text
  const filteredPositions = useMemo(() => {
    if (!searchText) return positions;
    return positions.filter((p) =>
      p.symbol.toLowerCase().includes(searchText.toLowerCase())
    );
  }, [positions, searchText]);

  const columns: ColumnsType<Position> = [
    {
      title: 'Symbol',
      dataIndex: 'symbol',
      key: 'symbol',
      fixed: 'left',
      width: 120,
      sorter: (a, b) => a.symbol.localeCompare(b.symbol),
      sortOrder: sortedInfo.columnKey === 'symbol' ? sortedInfo.order : null,
      render: (symbol: string, record: Position) => (
        <Space>
          <strong>{symbol}</strong>
          <Tag color={record.side === 'long' ? 'blue' : 'orange'}>
            {record.side.toUpperCase()}
          </Tag>
        </Space>
      ),
    },
    {
      title: 'Quantity',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 100,
      align: 'right',
      sorter: (a, b) => a.quantity - b.quantity,
      sortOrder: sortedInfo.columnKey === 'quantity' ? sortedInfo.order : null,
      render: (qty: number) => qty.toLocaleString(),
    },
    {
      title: 'Avg Entry',
      dataIndex: 'averagePrice',
      key: 'averagePrice',
      width: 120,
      align: 'right',
      sorter: (a, b) => a.averagePrice - b.averagePrice,
      sortOrder: sortedInfo.columnKey === 'averagePrice' ? sortedInfo.order : null,
      render: (price: number) => formatCurrency(price),
    },
    {
      title: 'Current Price',
      dataIndex: 'currentPrice',
      key: 'currentPrice',
      width: 130,
      align: 'right',
      sorter: (a, b) => a.currentPrice - b.currentPrice,
      sortOrder: sortedInfo.columnKey === 'currentPrice' ? sortedInfo.order : null,
      render: (price: number) => formatCurrency(price),
    },
    {
      title: 'Market Value',
      dataIndex: 'marketValue',
      key: 'marketValue',
      width: 140,
      align: 'right',
      sorter: (a, b) => a.marketValue - b.marketValue,
      sortOrder: sortedInfo.columnKey === 'marketValue' ? sortedInfo.order : null,
      render: (value: number) => <strong>{formatCurrency(value)}</strong>,
    },
    {
      title: 'Unrealized P&L',
      dataIndex: 'unrealizedPnL',
      key: 'unrealizedPnL',
      width: 140,
      align: 'right',
      sorter: (a, b) => a.unrealizedPnL - b.unrealizedPnL,
      sortOrder: sortedInfo.columnKey === 'unrealizedPnL' ? sortedInfo.order : null,
      render: (pnl: number) => (
        <strong style={{ color: getPnLColor(pnl) }}>
          {pnl >= 0 ? '+' : ''}
          {formatCurrency(pnl)}
        </strong>
      ),
    },
    {
      title: 'P&L %',
      dataIndex: 'unrealizedPnLPercent',
      key: 'unrealizedPnLPercent',
      width: 100,
      align: 'right',
      sorter: (a, b) => a.unrealizedPnLPercent - b.unrealizedPnLPercent,
      sortOrder: sortedInfo.columnKey === 'unrealizedPnLPercent' ? sortedInfo.order : null,
      render: (percent: number) => (
        <strong style={{ color: getPnLColor(percent) }}>
          {formatPercent(percent)}
        </strong>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      fixed: 'right',
      width: 180,
      render: (_: unknown, record: Position) => (
        <Space size="small">
          <Tooltip title="View Details">
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => onViewDetails(record)}
            />
          </Tooltip>
          <Tooltip title="Add to Position">
            <Button
              type="text"
              size="small"
              icon={<PlusOutlined />}
              onClick={() => onAddToPosition(record)}
              style={{ color: '#52c41a' }}
            />
          </Tooltip>
          <Tooltip title="Close Position">
            <Button
              type="text"
              size="small"
              danger
              icon={<CloseOutlined />}
              onClick={() => onClosePosition(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const handleTableChange = (_pagination: unknown, _filters: unknown, sorter: SorterResult<Position> | SorterResult<Position>[]) => {
    // Handle single sorter (not array)
    if (!Array.isArray(sorter)) {
      setSortedInfo(sorter);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Input
          placeholder="Search by symbol..."
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          style={{ width: 300 }}
          allowClear
        />
      </div>

      <Table<Position>
        columns={columns}
        dataSource={filteredPositions}
        rowKey="symbol"
        loading={loading}
        onChange={handleTableChange}
        pagination={{
          pageSize: 20,
          showSizeChanger: true,
          showTotal: (total) => `Total ${total} positions`,
        }}
        scroll={{ x: 1200 }}
        size="middle"
      />
    </div>
  );
};
