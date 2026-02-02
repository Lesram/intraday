/**
 * Orders Service
 * API endpoints for order management
 */

import { apiClient } from './api';
import type { Order, OrderSide, OrderType, OrderStatus, TimeInForce } from '@/store/ordersStore';

export interface SubmitOrderRequest {
  symbol: string;
  side: OrderSide;
  orderType: OrderType;
  quantity: number;
  limitPrice?: number;
  stopPrice?: number;
  timeInForce?: TimeInForce;
  strategyId?: string;
}

export interface OrdersQueryParams {
  status?: string;
  symbol?: string;
  startDate?: string;
  endDate?: string;
  limit?: number;
}

/** Backend order response shape (snake_case) */
interface BackendOrder {
  order_id: string;
  user_id?: string;
  symbol: string;
  side: OrderSide;
  order_type?: OrderType;
  qty: number;
  filled_qty?: number;
  limit_price?: number;
  stop_price?: number;
  avg_fill_price?: number;
  status: string;
  time_in_force?: TimeInForce;
  exchange?: string;
  strategy_id?: string;
  submitted_at?: string;
  updated_at?: string;
}

/**
 * Transform backend order (snake_case) to frontend Order type (camelCase)
 */
const transformBackendOrder = (backendOrder: BackendOrder): Order => {
  return {
    orderId: backendOrder.order_id,
    userId: backendOrder.user_id || '',
    symbol: backendOrder.symbol,
    side: backendOrder.side as OrderSide,
    orderType: (backendOrder.order_type || 'market') as OrderType,
    quantity: backendOrder.qty,
    filledQuantity: backendOrder.filled_qty || 0,
    remainingQuantity: (backendOrder.qty || 0) - (backendOrder.filled_qty || 0),
    limitPrice: backendOrder.limit_price,
    stopPrice: backendOrder.stop_price,
    averageFillPrice: backendOrder.avg_fill_price,
    status: backendOrder.status as OrderStatus,
    timeInForce: (backendOrder.time_in_force || 'day') as TimeInForce,
    exchange: backendOrder.exchange || 'UNKNOWN',
    strategyId: backendOrder.strategy_id,
    createdAt: backendOrder.submitted_at || new Date().toISOString(),
    updatedAt: backendOrder.updated_at || new Date().toISOString(),
  };
};

export const ordersService = {
  /**
   * Get all orders
   */
  getOrders: async (params?: OrdersQueryParams): Promise<Order[]> => {
    const response = await apiClient.get<BackendOrder[]>('/orders', { params });
    return response.data.map(transformBackendOrder);
  },

  /**
   * Get order by ID
   */
  getOrder: async (orderId: string): Promise<Order> => {
    const response = await apiClient.get<BackendOrder>(`/orders/${orderId}`);
    return transformBackendOrder(response.data);
  },

  /**
   * Submit new order
   */
  submitOrder: async (data: SubmitOrderRequest): Promise<Order> => {
    // Transform camelCase to snake_case for backend
    const backendData = {
      symbol: data.symbol,
      side: data.side,
      qty: data.quantity,  // quantity -> qty
      order_type: data.orderType,  // orderType -> order_type
      time_in_force: data.timeInForce,  // timeInForce -> time_in_force
      limit_price: data.limitPrice,  // limitPrice -> limit_price
      stop_price: data.stopPrice,  // stopPrice -> stop_price
      strategy_id: data.strategyId,  // strategyId -> strategy_id
    };
    
    const response = await apiClient.post<BackendOrder>('/orders', backendData);  // Changed from '/orders/submit' to '/orders'
    return transformBackendOrder(response.data);
  },

  /**
   * Cancel order
   */
  cancelOrder: async (orderId: string): Promise<Order> => {
    const response = await apiClient.delete<BackendOrder>(`/orders/${orderId}/cancel`);
    return transformBackendOrder(response.data);
  },

  /**
   * Modify order
   */
  modifyOrder: async (
    orderId: string,
    updates: Partial<SubmitOrderRequest>
  ): Promise<Order> => {
    // Transform camelCase to snake_case for backend
    const backendUpdates: Record<string, unknown> = {};
    if (updates.quantity !== undefined) backendUpdates.qty = updates.quantity;
    if (updates.orderType) backendUpdates.order_type = updates.orderType;
    if (updates.timeInForce) backendUpdates.time_in_force = updates.timeInForce;
    if (updates.limitPrice !== undefined) backendUpdates.limit_price = updates.limitPrice;
    if (updates.stopPrice !== undefined) backendUpdates.stop_price = updates.stopPrice;
    
    const response = await apiClient.patch<BackendOrder>(`/orders/${orderId}`, backendUpdates);
    return transformBackendOrder(response.data);
  },

  /**
   * Cancel all orders
   */
  cancelAllOrders: async (symbol?: string): Promise<{ cancelled: number }> => {
    const response = await apiClient.delete('/orders/cancel-all', {
      params: { symbol },
    });
    return response.data;
  },
};
