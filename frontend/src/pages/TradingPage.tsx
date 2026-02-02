/**
 * Trading Page
 * Main trading interface with chart, quotes, indicators, and drawing tools
 */

import React, { useState, useRef } from 'react';
import { Layout, Row, Col, Input, Space, Typography, Card } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { ChartContainer } from '../components/market/ChartContainer';
import { QuotePanel } from '../components/market/QuotePanel';
import { IndicatorPanel } from '../components/market/IndicatorPanel';
import { DrawingTools } from '../components/market/DrawingTools';
import { IndicatorTooltip } from '../components/market/IndicatorTooltip';
import { IndicatorLegend } from '../components/market/IndicatorLegend';
import WatchlistManager from '../components/market/WatchlistManager';
import TemplateSelector from '../components/market/TemplateSelector';
import { useMarketDataWebSocket } from '../hooks/useMarketDataWebSocket';
import { useIndicators } from '../hooks/useIndicators';
import { useDrawingTools } from '../hooks/useDrawingTools';
import type { Timeframe } from '../types/chart.types';
import type { ChartTemplate } from '../services/chartTemplateApi';
import type { IChartApi } from 'lightweight-charts';

const { Header, Content, Sider } = Layout;
const { Title, Text } = Typography;

/**
 * Trading Page Component
 */
export const TradingPage: React.FC = () => {
  const [currentSymbol, setCurrentSymbol] = useState('AAPL');
  const [searchQuery, setSearchQuery] = useState('');
  const [timeframe] = useState<Timeframe>('1D');
  const [chart, setChart] = useState<IChartApi | null>(null);
  const chartWrapperRef = useRef<HTMLDivElement>(null);

  const { connectionState } = useMarketDataWebSocket();
  
  // Initialize indicators
  const indicators = useIndicators({
    chart,
    symbol: currentSymbol,
    timeframe,
  });
  
  // Initialize drawing tools
  const drawingTools = useDrawingTools({
    chart,
    symbol: currentSymbol,
    timeframe,
  });

  /**
   * Handle symbol selection
   */
  const handleSymbolSelect = (symbol: string) => {
    setCurrentSymbol(symbol.toUpperCase());
    setSearchQuery('');
  };

  /**
   * Handle search
   */
  const handleSearch = (value: string) => {
    const symbol = value.trim().toUpperCase();
    if (symbol && symbol.length > 0) {
      handleSymbolSelect(symbol);
    }
  };

  /**
   * Apply a chart template
   */
  const handleApplyTemplate = (template: ChartTemplate) => {
    // Clear existing indicators
    indicators.indicators.forEach(ind => {
      indicators.removeIndicator(ind.id);
    });

    // Apply template indicators
    template.indicators.forEach(indicator => {
      indicators.addIndicator({
        id: `${indicator.type}-${Date.now()}-${Math.random()}`,
        name: indicator.type,
        displayName: indicator.type,
        category: 'trend',
        params: (indicator.params || {}) as Record<string, number>,
        color: indicator.color || '#2196F3',
        enabled: true,
      });
    });

    // TODO: Apply template settings (theme, grid, etc.) to chart
  };

  /**
   * Connection status color
   */
  const getConnectionColor = () => {
    if (connectionState === 'CONNECTED') return '#52c41a';
    if (connectionState === 'CONNECTING' || connectionState === 'RECONNECTING') return '#faad14';
    return '#ff4d4f';
  };

  return (
    <Layout style={{ minHeight: '100vh', background: '#000' }}>
      {/* Top Header */}
      <Header style={{ 
        background: '#141414', 
        padding: '0 24px', 
        borderBottom: '1px solid #f0f0f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <Space>
          <Title level={4} style={{ margin: 0, color: '#fff' }}>
            Trading Platform
          </Title>
          <div style={{ 
            width: 8, 
            height: 8, 
            borderRadius: '50%', 
            backgroundColor: getConnectionColor(),
            marginLeft: 8
          }} />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {connectionState === 'DISCONNECTED' ? 'Using Mock Data' : connectionState}
          </Text>
        </Space>

        <Input
          prefix={<SearchOutlined />}
          placeholder="Search symbol (e.g., AAPL)"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onPressEnter={() => handleSearch(searchQuery)}
          style={{ width: 300 }}
          size="large"
        />
      </Header>

      <Layout>
        {/* Left Sidebar - Watchlist */}
        <Sider 
          width={300} 
          style={{ 
            background: '#141414', 
            borderRight: '1px solid #303030',
            overflow: 'auto',
            height: 'calc(100vh - 64px)'
          }}
        >
          <div style={{ padding: 16 }}>
            <WatchlistManager 
              onSymbolClick={handleSymbolSelect}
              compact
            />
          </div>
        </Sider>

        {/* Main Content */}
        <Layout style={{ padding: 24, background: '#000' }}>
          <Content>
            <Row gutter={[16, 16]}>
              {/* Quote Panel */}
              <Col span={24}>
                <QuotePanel symbol={currentSymbol} />
              </Col>

              {/* Drawing Tools Toolbar */}
              <Col span={24}>
                <Card size="small" styles={{ body: { padding: '8px 16px' } }}>
                  <Space split style={{ width: '100%', justifyContent: 'space-between' }}>
                    <DrawingTools
                      selectedTool={drawingTools.selectedTool}
                      onToolSelect={drawingTools.selectTool}
                      style={drawingTools.style}
                      onStyleChange={drawingTools.updateStyle}
                      drawingsCount={drawingTools.drawings.length}
                      onSaveDrawings={drawingTools.saveDrawings}
                      onClearDrawings={drawingTools.clearDrawings}
                      onUndo={drawingTools.undoLastDrawing}
                      loading={drawingTools.loading}
                    />
                    <TemplateSelector
                      chart={chart}
                      activeIndicators={indicators.indicators.map(ind => ({
                        type: ind.config.name,
                        params: ind.config.params as Record<string, unknown>,
                        color: ind.config.color,
                      }))}
                      onApplyTemplate={handleApplyTemplate}
                    />
                  </Space>
                </Card>
              </Col>

              {/* Chart and Indicators */}
              <Col span={17}>
                <div 
                  ref={chartWrapperRef}
                  style={{ height: 'calc(100vh - 320px)', minHeight: 700, position: 'relative' }}
                >
                  <ChartContainer 
                    symbol={currentSymbol}
                    onSymbolChange={handleSymbolSelect}
                    onChartReady={setChart}
                  />
                  
                  {/* Indicator Legend */}
                  <IndicatorLegend indicators={indicators.indicators} />
                  
                  {/* Indicator Tooltip */}
                  <IndicatorTooltip
                    chart={chart}
                    indicators={indicators.indicators}
                    containerRef={chartWrapperRef}
                  />
                </div>
              </Col>

              {/* Indicator Panel */}
              <Col span={7}>
                <div style={{ height: 'calc(100vh - 320px)', minHeight: 700, overflow: 'auto' }}>
                  <IndicatorPanel
                    onIndicatorAdd={indicators.addIndicator}
                    onIndicatorRemove={indicators.removeIndicator}
                    onIndicatorUpdate={indicators.updateIndicator}
                    activeIndicators={indicators.indicators.map(ind => ind.config)}
                  />
                </div>
              </Col>
            </Row>
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
};

export default TradingPage;
