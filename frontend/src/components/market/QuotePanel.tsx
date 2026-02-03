/**
 * Quote Panel Component
 * 
 * Displays real-time market data for a symbol
 * Shows bid, ask, last price, spread, and size
 */

import React from 'react';
import { Card, Typography, Row, Col, Badge, Statistic, Space, Tag } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, SignalFilled } from '@ant-design/icons';
import { useSymbolQuote } from '../../hooks/useMarketDataWebSocket';

interface QuotePanelProps {
  symbol: string;
  compact?: boolean;
}

/**
 * Format price with 2 decimal places
 */
const formatPrice = (price: number | undefined): string => {
  return price !== undefined ? `$${price.toFixed(2)}` : '--';
};

/**
 * Format size
 */
const formatSize = (size: number | undefined): string => {
  return size !== undefined ? size.toLocaleString() : '--';
};

/**
 * Get price change color
 */
const getPriceColor = (current: number | undefined, previous: number | undefined): string => {
  if (!current || !previous) return 'text.primary';
  if (current > previous) return 'success.main';
  if (current < previous) return 'error.main';
  return 'text.primary';
};

/**
 * QuotePanel Component
 */
export const QuotePanel: React.FC<QuotePanelProps> = ({ symbol, compact = false }) => {
  const quote = useSymbolQuote(symbol);
  const previousPriceRef = React.useRef<number | undefined>(undefined);
  
  // Track previous price for color indication
  React.useEffect(() => {
    if (quote?.last) {
      previousPriceRef.current = quote.last;
    }
  }, [quote?.last]);
  
  // NO MOCK DATA - Only display real data or "No Data" state
  // If quote is null/undefined, we show a disconnected state
  const hasRealData = quote !== null && quote !== undefined;
  
  const priceColor = hasRealData ? getPriceColor(quote.last, previousPriceRef.current) : 'text.primary';
  const lastPrice = hasRealData ? (quote.last || quote.mid) : undefined;
  const prevPrice = previousPriceRef.current;
  const priceIncreased = lastPrice && prevPrice ? lastPrice > prevPrice : false;
  const priceDecreased = lastPrice && prevPrice ? lastPrice < prevPrice : false;
  
  if (compact) {
    // Compact view - No Data state
    if (!hasRealData) {
      return (
        <Card size="small" style={{ borderRadius: 8, background: '#141414', border: '1px solid #303030' }}>
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <Row justify="space-between" align="middle">
              <Col>
                <Typography.Text strong style={{ color: '#fff' }}>{symbol}</Typography.Text>
              </Col>
              <Col>
                <Tag color="error">No Data</Tag>
              </Col>
            </Row>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Waiting for real-time data connection...
            </Typography.Text>
          </Space>
        </Card>
      );
    }

    return (
      <Card size="small" style={{ borderRadius: 8, background: '#141414', border: '1px solid #303030' }}>
        <Space direction="vertical" style={{ width: '100%' }} size="small">
          <Row justify="space-between" align="middle">
            <Col>
              <Typography.Text strong style={{ color: '#fff' }}>{symbol}</Typography.Text>
            </Col>
            <Col>
              <Badge status="success" text={<SignalFilled style={{ color: '#52c41a' }} />} />
            </Col>
          </Row>
          
          <Row justify="space-between" align="middle">
            <Col>
              <Typography.Title level={4} style={{ margin: 0, color: priceColor }}>
                {formatPrice(lastPrice)}
              </Typography.Title>
            </Col>
            {quote.spread !== undefined && (
              <Col>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Spread: ${quote.spread.toFixed(3)}
                </Typography.Text>
              </Col>
            )}
          </Row>
          
          <Row gutter={16} style={{ marginTop: 8 }}>
            <Col span={12} style={{ textAlign: 'center' }}>
              <Typography.Text type="danger" style={{ fontSize: 11, display: 'block' }}>
                Bid
              </Typography.Text>
              <Typography.Text strong style={{ color: '#ff4d4f' }}>
                {formatPrice(quote.bid)}
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                {formatSize(quote.bid_size)}
              </Typography.Text>
            </Col>
            
            <Col span={12} style={{ textAlign: 'center' }}>
              <Typography.Text type="success" style={{ fontSize: 11, display: 'block' }}>
                Ask
              </Typography.Text>
              <Typography.Text strong style={{ color: '#52c41a' }}>
                {formatPrice(quote.ask)}
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                {formatSize(quote.ask_size)}
              </Typography.Text>
            </Col>
          </Row>
        </Space>
      </Card>
    );
  }
  
  // Full view - No Data state
  if (!hasRealData) {
    return (
      <Card title={null} style={{ borderRadius: 8, background: '#141414', border: '1px solid #303030' }}>
        <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
          <Col>
            <Typography.Title level={4} style={{ margin: 0, color: '#fff' }}>
              {symbol}
            </Typography.Title>
          </Col>
          <Col>
            <Tag color="error">No Data</Tag>
          </Col>
        </Row>
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Typography.Text type="secondary" style={{ fontSize: 14 }}>
            Waiting for real-time data connection...
          </Typography.Text>
          <br />
          <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 8, display: 'block' }}>
            Please check WebSocket connection status in the header.
          </Typography.Text>
        </div>
      </Card>
    );
  }

  return (
    <Card title={null} style={{ borderRadius: 8, background: '#141414', border: '1px solid #303030' }}>
      {/* Header */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Typography.Title level={4} style={{ margin: 0, color: '#fff' }}>
            {symbol}
          </Typography.Title>
        </Col>
        <Col>
          <Space>
            <Tag icon={<SignalFilled />} color="success">Live</Tag>
            {quote.updateCount && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {quote.updateCount} updates
              </Typography.Text>
            )}
          </Space>
        </Col>
      </Row>
      
      {/* Last Price */}
      <div style={{ marginBottom: 24 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
          Last Price
        </Typography.Text>
        <Space align="baseline">
          <Typography.Title level={1} style={{ margin: 0, color: priceColor }}>
            {formatPrice(lastPrice)}
          </Typography.Title>
          {lastPrice && prevPrice && lastPrice !== prevPrice && (
            priceIncreased ? (
              <ArrowUpOutlined style={{ fontSize: 24, color: '#52c41a' }} />
            ) : priceDecreased ? (
              <ArrowDownOutlined style={{ fontSize: 24, color: '#ff4d4f' }} />
            ) : null
          )}
        </Space>
        {quote.timestamp && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Updated: {new Date(quote.timestamp).toLocaleTimeString()}
          </Typography.Text>
        )}
      </div>
      
      {/* Bid/Ask Grid */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        {/* Bid */}
        <Col span={12}>
          <Card 
            size="small" 
            style={{ 
              borderColor: '#ff4d4f', 
              borderWidth: 2,
              borderRadius: 8
            }}
          >
            <Typography.Text type="danger" strong style={{ fontSize: 12, display: 'block' }}>
              BID
            </Typography.Text>
            <Statistic
              value={quote.bid}
              precision={2}
              prefix="$"
              valueStyle={{ color: '#ff4d4f', fontSize: 28 }}
            />
            <Row justify="space-between" style={{ marginTop: 8 }}>
              <Col>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>Size:</Typography.Text>
              </Col>
              <Col>
                <Typography.Text strong>{formatSize(quote.bid_size)}</Typography.Text>
              </Col>
            </Row>
          </Card>
        </Col>
        
        {/* Ask */}
        <Col span={12}>
          <Card 
            size="small" 
            style={{ 
              borderColor: '#52c41a', 
              borderWidth: 2,
              borderRadius: 8
            }}
          >
            <Typography.Text type="success" strong style={{ fontSize: 12, display: 'block' }}>
              ASK
            </Typography.Text>
            <Statistic
              value={quote.ask}
              precision={2}
              prefix="$"
              valueStyle={{ color: '#52c41a', fontSize: 28 }}
            />
            <Row justify="space-between" style={{ marginTop: 8 }}>
              <Col>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>Size:</Typography.Text>
              </Col>
              <Col>
                <Typography.Text strong>{formatSize(quote.ask_size)}</Typography.Text>
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>
      
      {/* Additional Info */}
      <Row gutter={16}>
        <Col span={12}>
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
            Mid Price
          </Typography.Text>
          <Typography.Text strong style={{ fontSize: 16 }}>
            {formatPrice(quote.mid)}
          </Typography.Text>
        </Col>
        
        <Col span={12}>
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
            Spread
          </Typography.Text>
          <Typography.Text strong style={{ fontSize: 16 }}>
            ${quote.spread?.toFixed(3) ?? '--'} {quote.spread && quote.mid ? `(${((quote.spread / quote.mid) * 100).toFixed(2)}%)` : ''}
          </Typography.Text>
        </Col>
      </Row>
    </Card>
  );
};

export default QuotePanel;


