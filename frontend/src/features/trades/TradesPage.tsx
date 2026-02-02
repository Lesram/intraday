/**
 * Trade History & Analytics Page
 * Main container for trade history with filters, table, and analytics
 */

import React, { useState } from 'react';
import { Card, Tabs, Space, DatePicker, Input, Radio, Button, Table, Statistic, Row, Col, App, Tag } from 'antd';
import { DownloadOutlined, ReloadOutlined, FilterOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useTradeHistory, useTradeAnalytics } from './hooks/useTradeHistory';
import { tradesService } from '@/services/tradesService';
import { TradeDetailModal } from './components/TradeDetailModal';
import { InstitutionalMetricsDisplay } from './components/InstitutionalMetricsDisplay';
import { useAuthStore } from '@/store/authStore';
import type { Trade, TradeFilters } from '@/types/trades';
import dayjs from 'dayjs';

const { RangePicker } = DatePicker;

export const TradesPage: React.FC = () => {
  const { message } = App.useApp();
  const [filters, setFilters] = useState<TradeFilters>({
    limit: 100,
    offset: 0,
  });
  
  const [tempFilters, setTempFilters] = useState({
    dateRange: null as [dayjs.Dayjs, dayjs.Dayjs] | null,
    symbol: '',
    side: 'all' as 'all' | 'buy' | 'sell',
  });

  // Modal state
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [closingOrderId, setClosingOrderId] = useState<string | null>(null);

  // Fetch data
  const { data: historyData, isLoading, refetch } = useTradeHistory(filters);
  const { data: analyticsData } = useTradeAnalytics(filters);

  // Handle filter changes
  const handleApplyFilters = () => {
    const newFilters: TradeFilters = {
      limit: 100,
      offset: 0,
    };

    if (tempFilters.dateRange) {
      newFilters.startDate = tempFilters.dateRange[0].format('YYYY-MM-DD');
      newFilters.endDate = tempFilters.dateRange[1].format('YYYY-MM-DD');
    }

    if (tempFilters.symbol) {
      newFilters.symbol = tempFilters.symbol.toUpperCase();
    }

    if (tempFilters.side !== 'all') {
      newFilters.side = tempFilters.side;
    }

    setFilters(newFilters);
  };

  const handleResetFilters = () => {
    setTempFilters({
      dateRange: null,
      symbol: '',
      side: 'all',
    });
    setFilters({ limit: 100, offset: 0 });
  };

  // Handle CSV export
  const handleExport = async () => {
    try {
      message.loading({ content: 'Generating CSV...', key: 'export' });
      await tradesService.downloadCSV(filters);
      message.success({ content: 'CSV downloaded successfully!', key: 'export', duration: 2 });
    } catch (_error) {
      message.error({ content: 'Failed to export CSV', key: 'export', duration: 2 });
    }
  };

  // Handle row click to open detail modal
  const handleRowClick = (record: Trade) => {
    setSelectedTrade(record);
    setDetailModalVisible(true);
  };

  // Handle close position from modal
  const handleClosePosition = async (symbol: string, quantity: number, orderId: string) => {
    setClosingOrderId(orderId);
    try {
      message.loading({ content: `Submitting sell order for ${quantity} ${symbol}...`, key: 'close' });
      
      // Get token from Zustand store (same way as api.ts does it)
      const token = useAuthStore.getState().accessToken;
      
      if (!token) {
        throw new Error('Not authenticated. Please login again.');
      }
      
      // Use environment-aware API URL instead of hardcoded localhost
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const response = await fetch(`${apiBaseUrl}/api/v1/orders/${orderId}/close-position`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to close position');
      }
      
      const data = await response.json();
      
      if (data.success) {
        message.success({ 
          content: `Position closed! Sold ${quantity} shares of ${symbol}`, 
          key: 'close',
          duration: 3
        });
        
        // Close modal first
        setDetailModalVisible(false);
        setSelectedTrade(null);
        
        // Then refresh data
        refetch();
      }
    } catch (error: unknown) {
      const err = error as { message?: string };
      const errorMsg = err.message || 'Failed to close position';
      message.error({ content: errorMsg, key: 'close', duration: 4 });
    } finally {
      setClosingOrderId(null);
    }
  };

  // Table columns
  const columns: ColumnsType<Trade> = [
    {
      title: 'Date',
      dataIndex: 'submittedAt',
      key: 'date',
      width: 110,
      render: (date: string) => dayjs(date).format('MM/DD/YY'),
      sorter: (a, b) => dayjs(a.submittedAt).unix() - dayjs(b.submittedAt).unix(),
    },
    {
      title: 'Time',
      dataIndex: 'submittedAt',
      key: 'time',
      width: 90,
      render: (date: string) => dayjs(date).format('HH:mm:ss'),
    },
    {
      title: 'Symbol',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 100,
    },
    {
      title: 'Side',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: string) => (
        <Tag color={side === 'buy' ? 'green' : 'red'}>
          {side.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Source',
      key: 'source',
      width: 100,
      render: (_, record) => {
        const isImported = record.attributes?.imported === true;
        return (
          <Tag color={isImported ? 'blue' : 'green'} icon={isImported ? '📥' : '🔸'}>
            {isImported ? 'Imported' : 'Local'}
          </Tag>
        );
      },
    },
    {
      title: 'Position',
      key: 'positionStatus',
      width: 120,
      render: (_, record) => {
        const status = record.positionStatus;
        const note = record.positionNote;
        
        // Only show position status for filled buy orders
        if (record.side !== 'buy' || record.status !== 'filled') {
          return <span style={{ color: '#999' }}>N/A</span>;
        }
        
        let color = 'default';
        let icon = '';
        let text = 'Unknown';
        
        switch (status) {
          case 'open':
            color = 'success';
            icon = '✅';
            text = 'Open';
            break;
          case 'partially_closed':
            color = 'warning';
            icon = '⚠️';
            text = 'Partial';
            break;
          case 'closed':
            color = 'warning';
            icon = '⚠️';
            text = 'Closed';
            break;
          case 'closed_by_sell':
            color = 'default';
            icon = '✓';
            text = 'Sold';
            break;
          default:
            color = 'default';
            icon = '❓';
            text = 'Unknown';
        }
        
        return (
          <Tag color={color} title={note}>
            <span style={{ marginRight: '4px' }}>{icon}</span>
            {text}
          </Tag>
        );
      },
    },
    {
      title: 'Quantity',
      dataIndex: 'filledQty',
      key: 'quantity',
      width: 100,
      align: 'right',
      render: (qty: number) => (qty !== null && qty !== undefined) ? qty.toFixed(2) : '0.00',
    },
    {
      title: 'Price',
      dataIndex: 'avgFillPrice',
      key: 'price',
      width: 100,
      align: 'right',
      render: (price: number | null) => price ? `$${price.toFixed(2)}` : 'N/A',
    },
    {
      title: 'Total Value',
      key: 'value',
      width: 120,
      align: 'right',
      render: (_, record) => {
        const qty = record.filledQty || 0;
        const price = record.avgFillPrice || 0;
        const value = qty * price;
        return value > 0 ? `$${value.toFixed(2)}` : 'N/A';
      },
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const statusColors: Record<string, string> = {
          filled: 'success',
          partially_filled: 'processing',
          cancelled: 'default',
          rejected: 'error',
          failed: 'error',
          expired: 'warning',
        };
        return (
          <Tag color={statusColors[status] || 'default'}>
            {status.replace('_', ' ').toUpperCase()}
          </Tag>
        );
      },
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Header */}
        <div>
          <h1 style={{ margin: 0 }}>Trade History & Analytics</h1>
          <p style={{ color: '#666', marginTop: '8px' }}>
            View your trading history, analyze performance, and export data
          </p>
        </div>

        {/* Filters */}
        <Card>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space wrap>
              <RangePicker
                value={tempFilters.dateRange}
                onChange={(dates) => setTempFilters({ ...tempFilters, dateRange: dates as [dayjs.Dayjs, dayjs.Dayjs] | null })}
                format="YYYY-MM-DD"
                placeholder={['Start Date', 'End Date']}
              />
              <Input
                placeholder="Symbol (e.g., AAPL)"
                value={tempFilters.symbol}
                onChange={(e) => setTempFilters({ ...tempFilters, symbol: e.target.value })}
                style={{ width: 200 }}
              />
              <Radio.Group
                value={tempFilters.side}
                onChange={(e) => setTempFilters({ ...tempFilters, side: e.target.value })}
              >
                <Radio.Button value="all">All</Radio.Button>
                <Radio.Button value="buy">Buy</Radio.Button>
                <Radio.Button value="sell">Sell</Radio.Button>
              </Radio.Group>
              <Button type="primary" icon={<FilterOutlined />} onClick={handleApplyFilters}>
                Apply Filters
              </Button>
              <Button onClick={handleResetFilters}>Reset</Button>
              <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
                Refresh
              </Button>
              <Button icon={<DownloadOutlined />} onClick={handleExport}>
                Export CSV
              </Button>
            </Space>
          </Space>
        </Card>

        {/* Tabs with new items API */}
        <Tabs
          defaultActiveKey="history"
          items={[
            {
              key: 'history',
              label: 'Trade History',
              children: (
                <Card>
                  <Table
                    columns={columns}
                    dataSource={historyData?.trades || []}
                    loading={isLoading}
                    rowKey="orderId"
                    onRow={(record) => ({
                      onClick: () => handleRowClick(record),
                      style: { cursor: 'pointer' }
                    })}
                    pagination={{
                      total: historyData?.total || 0,
                      current: (filters.offset || 0) / (filters.limit || 100) + 1,
                      pageSize: filters.limit || 100,
                      showSizeChanger: true,
                      showTotal: (total) => `Total ${total} trades`,
                      onChange: (page, pageSize) => {
                        setFilters({
                          ...filters,
                          offset: (page - 1) * pageSize,
                          limit: pageSize,
                        });
                      },
                    }}
                  />
                </Card>
              ),
            },
            {
              key: 'analytics',
              label: 'Analytics',
              children: (
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  {/* Statistics Cards */}
                  <Row gutter={16}>
                    <Col xs={24} sm={12} lg={6}>
                      <Card>
                        <Statistic
                          title="Total Trades"
                          value={analyticsData?.totalTrades || 0}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} sm={12} lg={6}>
                      <Card>
                        <Statistic
                          title="Win Rate"
                          value={analyticsData?.winRate || 0}
                          precision={1}
                          suffix="%"
                          valueStyle={{ color: (analyticsData?.winRate || 0) >= 50 ? '#3f8600' : '#cf1322' }}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} sm={12} lg={6}>
                      <Card>
                        <Statistic
                          title="Total P&L"
                          value={analyticsData?.totalRealizedPnL || 0}
                          precision={2}
                          prefix="$"
                          valueStyle={{ color: (analyticsData?.totalRealizedPnL || 0) >= 0 ? '#3f8600' : '#cf1322' }}
                        />
                      </Card>
                    </Col>
                    <Col xs={24} sm={12} lg={6}>
                      <Card>
                        <Statistic
                          title="Total Volume"
                          value={analyticsData?.totalVolume || 0}
                          precision={2}
                          prefix="$"
                        />
                      </Card>
                    </Col>
                  </Row>

                  {/* Additional Stats */}
                  <Row gutter={16}>
                    <Col xs={24} sm={12}>
                      <Card title="Best Trade" variant="outlined">
                        {analyticsData?.bestTrade ? (
                          <>
                            <p><strong>Symbol:</strong> {analyticsData.bestTrade.symbol}</p>
                            <p><strong>P&L:</strong> <span style={{ color: '#3f8600', fontSize: '18px', fontWeight: 'bold' }}>${analyticsData.bestTrade.pnl.toFixed(2)}</span></p>
                            <p><strong>Date:</strong> {dayjs(analyticsData.bestTrade.date).format('MMM DD, YYYY')}</p>
                          </>
                        ) : (
                          <p>No data available</p>
                        )}
                      </Card>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Card title="Worst Trade" variant="outlined">
                        {analyticsData?.worstTrade ? (
                          <>
                            <p><strong>Symbol:</strong> {analyticsData.worstTrade.symbol}</p>
                            <p><strong>P&L:</strong> <span style={{ color: '#cf1322', fontSize: '18px', fontWeight: 'bold' }}>${analyticsData.worstTrade.pnl.toFixed(2)}</span></p>
                            <p><strong>Date:</strong> {dayjs(analyticsData.worstTrade.date).format('MMM DD, YYYY')}</p>
                          </>
                        ) : (
                          <p>No data available</p>
                        )}
                      </Card>
                    </Col>
                  </Row>

                  {/* Institutional Metrics */}
                  {analyticsData?.institutionalMetrics && (
                    <InstitutionalMetricsDisplay metrics={analyticsData.institutionalMetrics} />
                  )}
                </Space>
              ),
            },
          ]}
        />

        {/* Trade Detail Modal */}
        <TradeDetailModal
          trade={selectedTrade}
          visible={detailModalVisible}
          onClose={() => {
            setDetailModalVisible(false);
            setSelectedTrade(null);
          }}
          onClosePosition={handleClosePosition}
          isClosing={closingOrderId === selectedTrade?.orderId}
        />
      </Space>
    </div>
  );
};

export default TradesPage;
