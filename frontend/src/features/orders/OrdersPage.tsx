/**
 * Orders Page
 * Main page for order management with tabs for active orders and history
 */

import { useState, useMemo } from 'react';
import { Typography, Tabs, Row, Col, Card, Statistic, Space } from 'antd';
import { 
  ThunderboltOutlined, 
  ClockCircleOutlined,
  CheckCircleOutlined,
  FileTextOutlined
} from '@ant-design/icons';
import { OrderEntryPanel } from './components/OrderEntryPanel';
import { ActiveOrdersTable } from './components/ActiveOrdersTable';
import { OrderHistoryTable } from './components/OrderHistoryTable';
import { ConnectionStatus } from '@/components/common/ConnectionStatus';
import { useOrders } from '@/hooks/useData';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useOrdersStore, type OrderSide, type OrderType, type OrderStatus, type TimeInForce } from '@/store/ordersStore';
import type { OrderUpdateMessage } from '@/types/websocket';
import { colors } from '@/styles/theme';

const { Title } = Typography;

const OrdersPage = () => {
  const [activeTab, setActiveTab] = useState('active');
  
  // Fetch orders from API (initial load)
  const { isLoading } = useOrders();
  
  // Get orders from store (updated by WebSocket)
  const orders = useOrdersStore((state) => state.orders);
  const updateOrder = useOrdersStore((state) => state.updateOrder);
  const addOrder = useOrdersStore((state) => state.addOrder);

  // WebSocket handler for order updates
  const handleOrderUpdate = useMemo(
    () => (message: OrderUpdateMessage) => {
      if (message.data) {
        const data = message.data as { 
          order_id?: string; 
          status?: string; 
          filled_quantity?: number; 
          avg_fill_price?: number; 
          timestamp?: string; 
          user_id?: string; 
          symbol?: string; 
          side?: string; 
          order_type?: string; 
          quantity?: number; 
          time_in_force?: string;
          limit_price?: number;
          stop_price?: number;
          exchange?: string;
          strategy_id?: string;
          submitted_at?: string;
        };
        
        // Check if order exists in store
        const existingOrder = orders.find(o => o.orderId === data.order_id);
        
        if (existingOrder && data.order_id) {
          // Update existing order
          updateOrder(data.order_id, {
            status: data.status as OrderStatus | undefined,
            filledQuantity: data.filled_quantity || existingOrder.filledQuantity,
            averageFillPrice: data.avg_fill_price,
            updatedAt: data.timestamp || new Date().toISOString(),
          });
        } else if (data.order_id && data.symbol && data.side && data.quantity !== undefined && data.status) {
          // Add new order (if just submitted)
          addOrder({
            orderId: data.order_id,
            userId: data.user_id || '',
            symbol: data.symbol,
            side: data.side as OrderSide,
            orderType: (data.order_type || 'market') as OrderType,
            quantity: data.quantity,
            filledQuantity: data.filled_quantity || 0,
            remainingQuantity: data.quantity - (data.filled_quantity || 0),
            limitPrice: data.limit_price,
            stopPrice: data.stop_price,
            averageFillPrice: data.avg_fill_price,
            status: data.status as OrderStatus,
            timeInForce: (data.time_in_force || 'day') as TimeInForce,
            exchange: data.exchange || 'UNKNOWN',
            strategyId: data.strategy_id,
            createdAt: data.submitted_at || new Date().toISOString(),
            updatedAt: data.timestamp || new Date().toISOString(),
          });
        }
      }
    },
    [orders, updateOrder, addOrder]
  );

  // Subscribe to order updates
  useWebSocket('orders', handleOrderUpdate);

  // Separate orders by status
  const activeOrders = useMemo(
    () => orders.filter(o => ['pending', 'submitted', 'partially_filled', 'accepted'].includes(o.status)),
    [orders]
  );

  const historyOrders = useMemo(
    () => orders.filter(o => ['filled', 'cancelled', 'rejected'].includes(o.status)),
    [orders]
  );

  const filledCount = historyOrders.filter(o => o.status === 'filled').length;

  return (
    <div>
      {/* Header */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        marginBottom: '24px' 
      }}>
        <Title level={2} style={{ color: colors.text.primary, margin: 0 }}>
          <ThunderboltOutlined /> Orders
        </Title>
        <ConnectionStatus />
      </div>

      {/* Statistics Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: '24px' }}>
        <Col xs={24} sm={8}>
          <Card style={{ background: colors.backgrounds.secondary }}>
            <Statistic
              title="Active Orders"
              value={activeOrders.length}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: colors.brand.primary }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card style={{ background: colors.backgrounds.secondary }}>
            <Statistic
              title="Filled Today"
              value={filledCount}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: colors.semantic.profit }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card style={{ background: colors.backgrounds.secondary }}>
            <Statistic
              title="Total Orders"
              value={orders.length}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: colors.text.primary }}
            />
          </Card>
        </Col>
      </Row>

      {/* Main Content */}
      <Row gutter={[16, 16]}>
        {/* Order Entry Panel */}
        <Col xs={24} lg={8}>
          <OrderEntryPanel 
            onOrderSubmitted={() => {
              // Optional: Switch to active orders tab after submission
              setActiveTab('active');
            }}
          />
        </Col>

        {/* Orders Tables */}
        <Col xs={24} lg={16}>
          <Card 
            style={{ 
              background: colors.backgrounds.secondary,
              minHeight: '600px'
            }}
            styles={{ body: { padding: '12px' } }}
          >
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              items={[
                {
                  key: 'active',
                  label: (
                    <Space>
                      <ClockCircleOutlined />
                      <span>Active Orders</span>
                      {activeOrders.length > 0 && (
                        <span style={{ 
                          background: colors.brand.primary, 
                          color: 'white',
                          padding: '2px 8px',
                          borderRadius: '12px',
                          fontSize: '12px',
                          fontWeight: 'bold'
                        }}>
                          {activeOrders.length}
                        </span>
                      )}
                    </Space>
                  ),
                  children: (
                    <ActiveOrdersTable 
                      orders={activeOrders} 
                      loading={isLoading}
                    />
                  ),
                },
                {
                  key: 'history',
                  label: (
                    <Space>
                      <FileTextOutlined />
                      <span>Order History</span>
                    </Space>
                  ),
                  children: (
                    <OrderHistoryTable 
                      orders={historyOrders} 
                      loading={isLoading}
                    />
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default OrdersPage;
