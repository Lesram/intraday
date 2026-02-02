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
      previousPriceRef.current = displayQuote.last;
    }
  }, [quote?.last]);
  
  // Use mock data if no quote available (not connected)
  const displayQuote = React.useMemo(() => {
    if (quote) return quote;
    
    // Generate mock quote for display when disconnected
    const basePrice = 150 + Math.random() * 10;
    return {
      symbol: symbol.toUpperCase(),
      bid: basePrice - 0.05,
      ask: basePrice + 0.05,
      bid_size: Math.floor(100 + Math.random() * 500),
      ask_size: Math.floor(100 + Math.random() * 500),
      last: basePrice,
      mid: basePrice,
      spread: 0.10,
      timestamp: new Date().toISOString(),
      updateCount: 0
    };
  }, [quote, symbol]);
  
  const priceColor = getPriceColor(displayQuote.last, previousPriceRef.current);
  const lastPrice = displayQuote.last || displayQuote.mid;
  const prevPrice = previousPriceRef.current;
  const priceIncreased = lastPrice && prevPrice ? lastPrice > prevPrice : false;
  const priceDecreased = lastPrice && prevPrice ? lastPrice < prevPrice : false;
  
  if (compact) {
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
            {displayQuote.spread !== undefined && (
              <Col>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Spread: ${displayQuote.spread.toFixed(3)}
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
                {formatPrice(displayQuote.bid)}
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                {formatSize(displayQuote.bid_size)}
              </Typography.Text>
            </Col>
            
            <Col span={12} style={{ textAlign: 'center' }}>
              <Typography.Text type="success" style={{ fontSize: 11, display: 'block' }}>
                Ask
              </Typography.Text>
              <Typography.Text strong style={{ color: '#52c41a' }}>
                {formatPrice(displayQuote.ask)}
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                {formatSize(displayQuote.ask_size)}
              </Typography.Text>
            </Col>
          </Row>
        </Space>
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
            {quote ? (
              <>
                <Tag icon={<SignalFilled />} color="success">Live</Tag>
                {displayQuote.updateCount && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {displayQuote.updateCount} updates
                  </Typography.Text>
                )}
              </>
            ) : (
              <Tag color="default">Mock Data</Tag>
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
        {displayQuote.timestamp && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Updated: {new Date(displayQuote.timestamp).toLocaleTimeString()}
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
              value={displayQuote.bid}
              precision={2}
              prefix="$"
              valueStyle={{ color: '#ff4d4f', fontSize: 28 }}
            />
            <Row justify="space-between" style={{ marginTop: 8 }}>
              <Col>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>Size:</Typography.Text>
              </Col>
              <Col>
                <Typography.Text strong>{formatSize(displayQuote.bid_size)}</Typography.Text>
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
              value={displayQuote.ask}
              precision={2}
              prefix="$"
              valueStyle={{ color: '#52c41a', fontSize: 28 }}
            />
            <Row justify="space-between" style={{ marginTop: 8 }}>
              <Col>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>Size:</Typography.Text>
              </Col>
              <Col>
                <Typography.Text strong>{formatSize(displayQuote.ask_size)}</Typography.Text>
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
            {formatPrice(displayQuote.mid)}
          </Typography.Text>
        </Col>
        
        <Col span={12}>
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
            Spread
          </Typography.Text>
          <Typography.Text strong style={{ fontSize: 16 }}>
            ${displayQuote.spread.toFixed(3)} ({((displayQuote.spread / displayQuote.mid) * 100).toFixed(2)}%)
          </Typography.Text>
        </Col>
      </Row>
    </Card>
  );
};

export default QuotePanel;


