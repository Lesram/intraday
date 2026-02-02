/**
 * Trade Detail Modal
 * Comprehensive view of individual trade/order with execution details and actions
 */

import React, { useState } from 'react';
import {
  Modal,
  Descriptions,
  Table,
  Tag,
  Button,
  Space,
  Statistic,
  Row,
  Col,
  Card,
  Alert,
  App,
  Divider
} from 'antd';
import {
  DollarOutlined,
  CloseCircleOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExportOutlined,
  LinkOutlined,
  TrophyOutlined
} from '@ant-design/icons';
import type { Trade } from '@/types/trades';
import { useCancelOrder } from '@/hooks/useData';
import { useTradeAnalytics } from '../hooks/useTradeHistory';
import { InstitutionalMetricsDisplay } from './InstitutionalMetricsDisplay';
import dayjs from 'dayjs';

interface TradeDetailModalProps {
  trade: Trade | null;
  visible: boolean;
  onClose: () => void;
  onClosePosition?: (symbol: string, quantity: number, orderId: string) => void;
  isClosing?: boolean;
}

export const TradeDetailModal: React.FC<TradeDetailModalProps> = ({
  trade,
  visible,
  onClose,
  onClosePosition,
  isClosing: isClosingProp = false
}) => {
  const { modal, message } = App.useApp();
  const { mutate: cancelOrder, isPending: isCancelling } = useCancelOrder();
  const [isClosing, setIsClosing] = useState(false);

  // Fetch analytics for institutional metrics (optional, shows if available)
  const { data: analyticsData } = useTradeAnalytics({
    symbol: trade?.symbol
  }, !!trade && visible);

  if (!trade) return null;

  const handleClosePosition = async () => {
    if (!trade.currentQty || !onClosePosition) return;

    modal.confirm({
      title: 'Close Position?',
      content: (
        <>
          <p>This will submit a market order to sell <strong>{trade.currentQty}</strong> shares of <strong>{trade.symbol}</strong>.</p>
          <p>Current market price: <strong>${trade.currentPrice?.toFixed(2) || 'N/A'}</strong></p>
          <p>Estimated value: <strong>${((trade.currentQty || 0) * (trade.currentPrice || 0)).toFixed(2)}</strong></p>
        </>
      ),
      okText: 'Close Position',
      okButtonProps: { danger: true, loading: isClosing || isClosingProp },
      onOk: async () => {
        setIsClosing(true);
        try {
          await onClosePosition(trade.symbol, trade.currentQty!, trade.orderId);
          // Don't close modal or reset state here - parent will handle refresh
        } catch (_error) {
          message.error('Failed to close position');
          setIsClosing(false);
        }
      }
    });
  };

  const handleCancelOrder = () => {
    modal.confirm({
      title: 'Cancel Order?',
      content: `Are you sure you want to cancel this ${trade.side} order for ${trade.qty} shares of ${trade.symbol}?`,
      okText: 'Cancel Order',
      okButtonProps: { danger: true },
      onOk: () => {
        cancelOrder(trade.orderId);
        onClose();
      }
    });
  };

  const handleExportDetails = () => {
    const detailsJSON = JSON.stringify(trade, null, 2);
    const blob = new Blob([detailsJSON], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trade-${trade.orderId}.json`;
    a.click();
    URL.revokeObjectURL(url);
    message.success('Trade details exported');
  };

  // Calculate metrics
  const totalValue = (trade.filledQty || 0) * (trade.avgFillPrice || 0);
  const isImported = trade.attributes?.imported === true;
  const isPendingOrder = ['new', 'pending_new', 'accepted'].includes(trade.status);
  const isOpenPosition = trade.positionStatus === 'open' && trade.side === 'buy' && trade.status === 'filled';
  const canClosePosition = isOpenPosition && trade.currentQty && trade.currentQty > 0 && onClosePosition;

  // Status color mapping
  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      filled: 'success',
      partial: 'warning',
      cancelled: 'default',
      rejected: 'error',
      new: 'processing',
      accepted: 'processing'
    };
    return colors[status] || 'default';
  };

  // Execution table columns
  const executionColumns = [
    {
      title: 'Time',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (ts: string) => dayjs(ts).format('MM/DD/YY HH:mm:ss')
    },
    {
      title: 'Quantity',
      dataIndex: 'fillQty',
      key: 'quantity',
      align: 'right' as const,
      render: (qty: number) => qty.toFixed(4)
    },
    {
      title: 'Price',
      dataIndex: 'fillPrice',
      key: 'price',
      align: 'right' as const,
      render: (price: number) => `$${price.toFixed(2)}`
    },
    {
      title: 'Value',
      key: 'value',
      align: 'right' as const,
      render: (_: unknown, record: { fillQty: number; fillPrice: number }) => `$${(record.fillQty * record.fillPrice).toFixed(2)}`
    },
    {
      title: 'Venue',
      dataIndex: 'venue',
      key: 'venue'
    }
  ];

  return (
    <Modal
      open={visible}
      onCancel={onClose}
      width={900}
      title={
        <Space>
          <span>Order Details</span>
          <Tag color={trade.side === 'buy' ? 'green' : 'red'}>
            {trade.side.toUpperCase()}
          </Tag>
          <Tag>{trade.symbol}</Tag>
          <Tag color={getStatusColor(trade.status)}>{trade.status.toUpperCase()}</Tag>
        </Space>
      }
      footer={[
        <Button key="export" icon={<ExportOutlined />} onClick={handleExportDetails}>
          Export
        </Button>,
        <Button
          key="alpaca"
          icon={<LinkOutlined />}
          onClick={() => window.open(`https://app.alpaca.markets/paper/dashboard/overview`, '_blank')}
        >
          View in Alpaca
        </Button>,
        isPendingOrder && (
          <Button
            key="cancel"
            danger
            icon={<CloseCircleOutlined />}
            onClick={handleCancelOrder}
            loading={isCancelling}
          >
            Cancel Order
          </Button>
        ),
        canClosePosition && (
          <Button
            key="closePosition"
            type="primary"
            danger
            icon={<DollarOutlined />}
            onClick={handleClosePosition}
            loading={isClosing || isClosingProp}
            disabled={isClosing || isClosingProp}
          >
            Close Position
          </Button>
        ),
        <Button key="close" type="primary" onClick={onClose}>
          Close
        </Button>
      ].filter(Boolean)}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        
        {/* Source Alert */}
        {isImported && (
          <Alert
            message="Imported Order"
            description="This order was imported from Alpaca and may not have complete execution details."
            type="info"
            showIcon
            icon={<LinkOutlined />}
          />
        )}

        {/* Key Metrics */}
        <Row gutter={16}>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="Quantity"
                value={trade.qty}
                precision={2}
                suffix="shares"
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="Filled"
                value={trade.filledQty || 0}
                precision={2}
                valueStyle={{ color: trade.filledQty === trade.qty ? '#3f8600' : '#cf1322' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="Avg Price"
                value={trade.avgFillPrice || 0}
                precision={2}
                prefix="$"
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="Total Value"
                value={totalValue}
                precision={2}
                prefix="$"
              />
            </Card>
          </Col>
        </Row>

        {/* Position Status (for buy orders) */}
        {trade.side === 'buy' && trade.status === 'filled' && (
          <Card title="Position Status" size="small">
            <Row gutter={16}>
              <Col span={8}>
                <Statistic
                  title="Status"
                  value={trade.positionStatus || 'unknown'}
                  valueStyle={{
                    color: trade.positionStatus === 'open' ? '#3f8600' : '#999'
                  }}
                />
              </Col>
              {trade.currentQty !== null && (
                <Col span={8}>
                  <Statistic
                    title="Current Quantity"
                    value={trade.currentQty}
                    precision={2}
                  />
                </Col>
              )}
              {trade.unrealizedPnL !== null && (
                <Col span={8}>
                  <Statistic
                    title="Unrealized P&L"
                    value={trade.unrealizedPnL}
                    precision={2}
                    prefix="$"
                    valueStyle={{
                      color: (trade.unrealizedPnL || 0) >= 0 ? '#3f8600' : '#cf1322'
                    }}
                  />
                </Col>
              )}
            </Row>
            {trade.positionNote && (
              <Alert
                message={trade.positionNote}
                type="info"
                showIcon
                style={{ marginTop: 12 }}
              />
            )}
          </Card>
        )}

        {/* Order Information */}
        <Descriptions title="Order Information" bordered size="small" column={2}>
          <Descriptions.Item label="Order ID">{trade.orderId}</Descriptions.Item>
          <Descriptions.Item label="Symbol">{trade.symbol}</Descriptions.Item>
          <Descriptions.Item label="Side">
            <Tag color={trade.side === 'buy' ? 'green' : 'red'}>
              {trade.side.toUpperCase()}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Type">{trade.orderType.toUpperCase()}</Descriptions.Item>
          <Descriptions.Item label="Status">
            <Tag color={getStatusColor(trade.status)} icon={
              trade.status === 'filled' ? <CheckCircleOutlined /> :
              isPendingOrder ? <ClockCircleOutlined /> :
              <CloseCircleOutlined />
            }>
              {trade.status.toUpperCase()}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Source">
            <Tag color={isImported ? 'blue' : 'green'}>
              {isImported ? 'Imported' : 'Local'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Submitted">
            {dayjs(trade.submittedAt).format('MM/DD/YY HH:mm:ss')}
          </Descriptions.Item>
          <Descriptions.Item label="Updated">
            {dayjs(trade.updatedAt).format('MM/DD/YY HH:mm:ss')}
          </Descriptions.Item>
          {trade.strategyId && (
            <Descriptions.Item label="Strategy" span={2}>
              {trade.strategyId}
            </Descriptions.Item>
          )}
        </Descriptions>

        {/* Execution Details */}
        {trade.executions && trade.executions.length > 0 && (
          <>
            <Divider orientation="left">Execution Details</Divider>
            <Table
              dataSource={trade.executions}
              columns={executionColumns}
              size="small"
              pagination={false}
              rowKey="executionId"
              summary={() => (
                <Table.Summary>
                  <Table.Summary.Row>
                    <Table.Summary.Cell index={0}><strong>Total</strong></Table.Summary.Cell>
                    <Table.Summary.Cell index={1} align="right">
                      <strong>{trade.filledQty?.toFixed(4)}</strong>
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={2} align="right">
                      <strong>${trade.avgFillPrice?.toFixed(2)}</strong>
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={3} align="right">
                      <strong>${totalValue.toFixed(2)}</strong>
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={4} />
                  </Table.Summary.Row>
                </Table.Summary>
              )}
            />
          </>
        )}

        {/* Institutional Metrics (if available for this symbol) */}
        {analyticsData?.institutionalMetrics && (
          <>
            <Divider orientation="left">
              <TrophyOutlined style={{ marginRight: 8 }} />
              Performance Metrics for {trade.symbol}
            </Divider>
            <InstitutionalMetricsDisplay metrics={analyticsData.institutionalMetrics} />
          </>
        )}

      </Space>
    </Modal>
  );
};
