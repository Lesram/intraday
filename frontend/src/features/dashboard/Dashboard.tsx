import { Card, Row, Col, Statistic, Typography, Alert, Button } from 'antd';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  DollarOutlined,
  RiseOutlined,
} from '@ant-design/icons';
import { useMemo } from 'react';
import { colors } from '../../styles/theme';
import { formatCurrency, formatPercent } from '../../utils/formatters';
import { usePortfolio, useOrders, useStrategies, usePortfolioHistory } from '@/hooks/useData';
import { useWebSocket } from '@/hooks/useWebSocket';
import { usePortfolioStore } from '@/store/portfolioStore';
import { useOrdersStore } from '@/store/ordersStore';
import { useStrategiesStore } from '@/store/strategiesStore';
import type { PortfolioUpdateMessage, OrderUpdateMessage } from '@/types/websocket';
import { PageSkeleton } from '@/components/common/LoadingComponents';
import { ConnectionStatus } from '@/components/common/ConnectionStatus';
import { PositionsTable } from '@/components/portfolio/PositionsTable';
import { PortfolioChart } from '@/components/charts/PortfolioChart';

const { Title } = Typography;

const Dashboard = () => {
  // Fetch data from API with refetch capability
  const { 
    data: portfolioData, 
    isLoading: portfolioLoading, 
    error: portfolioError,
    refetch: refetchPortfolio 
  } = usePortfolio();
  const { isLoading: ordersLoading } = useOrders({ limit: 10 });
  const { isLoading: strategiesLoading } = useStrategies();
  const { data: portfolioHistory, isLoading: historyLoading } = usePortfolioHistory();

  // Get data from stores (updated by WebSocket)
  const portfolio = usePortfolioStore((state) => state.portfolio);
  const orders = useOrdersStore((state) => state.orders);
  const strategies = useStrategiesStore((state) => state.strategies);
  
  // Zustand store actions - memoized to prevent re-creation
  const setPortfolio = usePortfolioStore((state) => state.setPortfolio);
  const updateOrder = useOrdersStore((state) => state.updateOrder);
  const updateStrategy = useStrategiesStore((state) => state.updateStrategy);

  // WebSocket handlers - use useMemo to create stable references
  const handlePortfolioUpdate = useMemo(
    () => (message: PortfolioUpdateMessage) => {
      if (message.data) {
        // API now returns camelCase, map directly to store
        const data = message.data as any;
        setPortfolio({
          userId: data.userId || '',
          totalEquity: data.totalEquity || 0,
          cash: data.cash || 0,
          buyingPower: data.buyingPower || 0,
          marginUsed: data.marginUsed || 0,
          maintenanceMargin: data.maintenanceMargin || 0,
          totalPnL: data.totalPnL || 0,
          totalPnLPercent: data.totalPnLPercent || 0,
          dayPnL: data.dayPnL || 0,
          dayPnLPercent: data.dayPnLPercent || 0,
          positions: data.positions || [],
          lastUpdate: data.lastUpdate || new Date().toISOString(),
        });
      }
    },
    [setPortfolio]
  );

  const handleOrderUpdate = useMemo(
    () => (message: OrderUpdateMessage) => {
      if (message.data) {
        // Convert snake_case to camelCase
        const data = message.data as any;
        updateOrder(data.order_id, {
          orderId: data.order_id,
          symbol: data.symbol,
          side: data.side,
          orderType: data.order_type,
          quantity: data.quantity,
          filledQuantity: data.filled_quantity,
          status: data.status,
          limitPrice: data.price,
          stopPrice: data.stop_price,
          updatedAt: data.timestamp,
        } as any);
      }
    },
    [updateOrder]
  );

  const handleStrategyUpdate = useMemo(
    () => (message: any) => {
      if (message.data) {
        updateStrategy(message.data.strategyId, message.data);
      }
    },
    [updateStrategy]
  );

  // Subscribe to WebSocket updates
  useWebSocket('portfolio', handlePortfolioUpdate);
  useWebSocket('orders', handleOrderUpdate);
  useWebSocket('strategies', handleStrategyUpdate);

  // Loading state
  if (portfolioLoading || ordersLoading || strategiesLoading) {
    return <PageSkeleton />;
  }

  // Error state with retry functionality
  if (portfolioError) {
    return (
      <div style={{ padding: '24px' }}>
        <Alert
          message="Failed to Load Portfolio"
          description={
            <div>
              <p>Unable to fetch portfolio data from the server.</p>
              <p style={{ marginBottom: '12px' }}>
                {portfolioError instanceof Error 
                  ? portfolioError.message 
                  : 'Please check your connection and try again.'}
              </p>
              <Button 
                type="primary" 
                onClick={() => refetchPortfolio()}
                icon={<ArrowUpOutlined />}
              >
                Retry
              </Button>
            </div>
          }
          type="error"
          showIcon
        />
      </div>
    );
  }

  // Use portfolio from store (real-time) or API data
  const currentPortfolio = portfolio || portfolioData;
  
  // Calculate statistics
  const equity = currentPortfolio?.totalEquity || 0;
  const dailyPL = currentPortfolio?.dayPnL || 0;
  const dailyPLPercent = currentPortfolio?.dayPnLPercent || 0;
  const buyingPower = currentPortfolio?.buyingPower || 0;
  const positionsValue = currentPortfolio?.positions?.reduce(
    (sum, pos) => sum + pos.marketValue, 
    0
  ) || 0;
  const activeStrategiesCount = strategies.filter(s => s.status === 'active').length;
  const pendingOrdersCount = orders.filter(
    o => ['pending', 'submitted', 'partially_filled'].includes(o.status)
  ).length;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <Title level={2} style={{ color: colors.text.primary, margin: 0 }}>
          Dashboard
        </Title>
        <ConnectionStatus />
      </div>

      {/* Portfolio Summary Cards */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card style={{ background: colors.backgrounds.secondary }}>
            <Statistic
              title="Portfolio Equity"
              value={equity}
              precision={2}
              prefix={<DollarOutlined />}
              valueStyle={{ color: colors.text.primary, fontFamily: 'monospace' }}
              formatter={(value) => formatCurrency(value as number)}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card style={{ background: colors.backgrounds.secondary }}>
            <Statistic
              title="Daily P&L"
              value={dailyPL}
              precision={2}
              prefix={dailyPL >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
              valueStyle={{
                color: dailyPL >= 0 ? colors.semantic.profit : colors.semantic.loss,
                fontFamily: 'monospace',
              }}
              suffix={formatPercent(dailyPLPercent)}
              formatter={(value) => formatCurrency(value as number)}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card style={{ background: colors.backgrounds.secondary }}>
            <Statistic
              title="Buying Power"
              value={buyingPower}
              precision={2}
              prefix={<RiseOutlined />}
              valueStyle={{ color: colors.text.primary, fontFamily: 'monospace' }}
              formatter={(value) => formatCurrency(value as number)}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card style={{ background: colors.backgrounds.secondary }}>
            <Statistic
              title="Positions Value"
              value={positionsValue}
              precision={2}
              prefix={<DollarOutlined />}
              valueStyle={{ color: colors.text.primary, fontFamily: 'monospace' }}
              formatter={(value) => formatCurrency(value as number)}
            />
          </Card>
        </Col>
      </Row>

      {/* Additional Stats Row */}
      <Row gutter={[16, 16]} style={{ marginTop: '16px' }}>
        <Col xs={24} sm={12} lg={6}>
          <Card style={{ background: colors.backgrounds.secondary }}>
            <Statistic
              title="Active Strategies"
              value={activeStrategiesCount}
              valueStyle={{ color: colors.semantic.profit, fontFamily: 'monospace' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card style={{ background: colors.backgrounds.secondary }}>
            <Statistic
              title="Pending Orders"
              value={pendingOrdersCount}
              valueStyle={{ color: colors.brand.primary, fontFamily: 'monospace' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card style={{ background: colors.backgrounds.secondary }}>
            <Statistic
              title="Open Positions"
              value={currentPortfolio?.positions?.length || 0}
              valueStyle={{ color: colors.text.primary, fontFamily: 'monospace' }}
            />
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6}>
          <Card style={{ background: colors.backgrounds.secondary }}>
            <Statistic
              title="Total P&L"
              value={currentPortfolio?.totalPnL || 0}
              precision={2}
              prefix={<DollarOutlined />}
              valueStyle={{
                color: (currentPortfolio?.totalPnL || 0) >= 0 
                  ? colors.semantic.profit 
                  : colors.semantic.loss,
                fontFamily: 'monospace',
              }}
              formatter={(value) => formatCurrency(value as number)}
            />
          </Card>
        </Col>
      </Row>

      {/* More dashboard content will go here */}
      <Row gutter={[16, 16]} style={{ marginTop: '24px' }}>
        {/* Positions Table */}
        <Col xs={24}>
          <Card
            title="Open Positions"
            style={{ background: colors.backgrounds.secondary }}
          >
            <PositionsTable 
              positions={currentPortfolio?.positions || []} 
              loading={portfolioLoading}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: '24px' }}>
        <Col xs={24} lg={16}>
          <Card
            title="Portfolio Performance"
            style={{ background: colors.backgrounds.secondary }}
          >
            <PortfolioChart 
              data={portfolioHistory || []} 
              loading={historyLoading}
            />
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card
            title="Recent Activity"
            style={{ background: colors.backgrounds.secondary }}
          >
            <div style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ color: colors.text.tertiary }}>Activity feed will be implemented in Phase 3</span>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard;
