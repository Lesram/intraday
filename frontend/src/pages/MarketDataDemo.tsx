/**
 * Market Data Demo Page
 * 
 * Test page for real-time market data WebSocket integration
 */

import React, { useState } from 'react';
import { Layout, Typography, Space, Input, Button, Alert, Row, Col, Card, Statistic } from 'antd';
import { PlusOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import { QuotePanel } from '../components/market/QuotePanel';
import { useMarketDataWebSocket } from '../hooks/useMarketDataWebSocket';
import { useMarketDataStats } from '../store/marketDataStore';
import { ConnectionState } from '../types/marketData';

const { Header, Content } = Layout;
const { Title, Text } = Typography;

/**
 * Connection status badge
 */
const ConnectionStatus: React.FC<{ state: ConnectionState }> = ({ state }) => {
  const colors: Record<ConnectionState, string> = {
    [ConnectionState.CONNECTED]: 'success',
    [ConnectionState.CONNECTING]: 'processing',
    [ConnectionState.RECONNECTING]: 'warning',
    [ConnectionState.DISCONNECTED]: 'default',
    [ConnectionState.FAILED]: 'error',
  };
  
  const texts: Record<ConnectionState, string> = {
    [ConnectionState.CONNECTED]: 'Connected',
    [ConnectionState.CONNECTING]: 'Connecting...',
    [ConnectionState.RECONNECTING]: 'Reconnecting...',
    [ConnectionState.DISCONNECTED]: 'Disconnected',
    [ConnectionState.FAILED]: 'Connection Failed',
  };
  
  return (
    <Alert
      message={texts[state]}
      type={colors[state] as 'success' | 'warning' | 'info' | 'error'}
      showIcon
      style={{ marginBottom: 16 }}
    />
  );
};

/**
 * Market Data Demo Page
 */
export const MarketDataDemo: React.FC = () => {
  const [symbols, setSymbols] = useState<string[]>(['AAPL', 'GOOGL', 'MSFT']);
  const [newSymbol, setNewSymbol] = useState('');
  
  const { 
    connected, 
    connecting,
    connectionState, 
    error, 
    reconnect,
    subscriptions 
  } = useMarketDataWebSocket();
  
  const stats = useMarketDataStats();
  
  /**
   * Add symbol
   */
  const handleAddSymbol = () => {
    const symbol = newSymbol.trim().toUpperCase();
    if (symbol && !symbols.includes(symbol)) {
      setSymbols([...symbols, symbol]);
      setNewSymbol('');
    }
  };
  
  /**
   * Remove symbol
   */
  const handleRemoveSymbol = (symbol: string) => {
    setSymbols(symbols.filter(s => s !== symbol));
  };
  
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ background: '#fff', padding: '0 24px', borderBottom: '1px solid #f0f0f0' }}>
        <Title level={3} style={{ margin: '16px 0' }}>
          Market Data WebSocket Demo
        </Title>
      </Header>
      
      <Content style={{ padding: '24px' }}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          {/* Connection Status */}
          <ConnectionStatus state={connectionState} />
          
          {/* Error Display */}
          {error && (
            <Alert
              message="Error"
              description={error}
              type="error"
              closable
              showIcon
            />
          )}
          
          {/* Statistics */}
          <Card title="Service Statistics" size="small">
            <Row gutter={16}>
              <Col span={6}>
                <Statistic 
                  title="Connection" 
                  value={connected ? 'Connected' : connecting ? 'Connecting...' : 'Disconnected'}
                  valueStyle={{ color: connected ? '#52c41a' : '#999' }}
                />
              </Col>
              <Col span={6}>
                <Statistic 
                  title="Active Subscriptions" 
                  value={stats.activeSubscriptions}
                />
              </Col>
              <Col span={6}>
                <Statistic 
                  title="Total Updates" 
                  value={stats.totalUpdates}
                />
              </Col>
              <Col span={6}>
                <Statistic 
                  title="Quotes in Memory" 
                  value={stats.quotesInMemory}
                />
              </Col>
            </Row>
            <Row style={{ marginTop: 16 }}>
              <Col>
                <Text type="secondary">
                  Last Update: {
                    stats.lastUpdateTime 
                      ? new Date(stats.lastUpdateTime).toLocaleTimeString() 
                      : 'Never'
                  }
                </Text>
              </Col>
            </Row>
            <Row style={{ marginTop: 8 }}>
              <Col>
                <Button 
                  icon={<ReloadOutlined />} 
                  onClick={reconnect}
                  disabled={connected}
                >
                  Reconnect
                </Button>
              </Col>
            </Row>
          </Card>
          
          {/* Add Symbol */}
          <Card title="Manage Symbols" size="small">
            <Space.Compact style={{ width: '100%' }}>
              <Input
                placeholder="Enter symbol (e.g., AAPL)"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                onPressEnter={handleAddSymbol}
                style={{ flex: 1 }}
              />
              <Button 
                type="primary" 
                icon={<PlusOutlined />}
                onClick={handleAddSymbol}
                disabled={!newSymbol.trim()}
              >
                Add
              </Button>
            </Space.Compact>
            <div style={{ marginTop: 12 }}>
              <Text type="secondary">
                Current symbols: {symbols.join(', ') || 'None'}
              </Text>
            </div>
            <div style={{ marginTop: 8 }}>
              <Text type="secondary">
                Subscribed: {subscriptions.join(', ') || 'None'}
              </Text>
            </div>
          </Card>
          
          {/* Quote Panels */}
          <div>
            <Title level={4}>Live Quotes</Title>
            
            {symbols.length === 0 ? (
              <Alert
                message="No symbols added"
                description="Add a symbol above to see real-time market data"
                type="info"
                showIcon
              />
            ) : (
              <Row gutter={[16, 16]}>
                {symbols.map((symbol) => (
                  <Col key={symbol} xs={24} sm={12} lg={8} xl={6}>
                    <div style={{ position: 'relative' }}>
                      <Button
                        danger
                        size="small"
                        icon={<DeleteOutlined />}
                        onClick={() => handleRemoveSymbol(symbol)}
                        style={{ 
                          position: 'absolute', 
                          top: 8, 
                          right: 8, 
                          zIndex: 1 
                        }}
                      />
                      <QuotePanel symbol={symbol} compact />
                    </div>
                  </Col>
                ))}
              </Row>
            )}
          </div>
          
          {/* Full Quote Panel Example */}
          {symbols.length > 0 && (
            <div>
              <Title level={4}>Detailed Quote View</Title>
              <Row gutter={16}>
                <Col span={24} lg={12}>
                  <QuotePanel symbol={symbols[0]} />
                </Col>
              </Row>
            </div>
          )}
        </Space>
      </Content>
    </Layout>
  );
};

export default MarketDataDemo;
