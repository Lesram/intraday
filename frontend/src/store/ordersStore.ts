/**
 * Orders Store
 * Manages orders state and real-time updates
 */

import { create } from 'zustand';

// Types
export type OrderSide = 'buy' | 'sell';
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit';
export type OrderStatus = 'pending' | 'submitted' | 'accepted' | 'partially_filled' | 'filled' | 'cancelled' | 'rejected';
export type TimeInForce = 'day' | 'gtc' | 'ioc' | 'fok';

export interface Order {
  orderId: string;
  userId: string;
  symbol: string;
  side: OrderSide;
  orderType: OrderType;
  quantity: number;
  filledQuantity: number;
  remainingQuantity: number;
  limitPrice?: number;
  stopPrice?: number;
  averageFillPrice?: number;
  status: OrderStatus;
  timeInForce: TimeInForce;
  exchange: string;
  strategyId?: string;
  createdAt: string;
  updatedAt: string;
  filledAt?: string;
  cancelledAt?: string;
  rejectionReason?: string;
}

interface OrdersState {
  orders: Order[];
  isLoading: boolean;
  error: string | null;

  // Actions
  setOrders: (orders: Order[]) => void;
  addOrder: (order: Order) => void;
  updateOrder: (orderId: string, updates: Partial<Order>) => void;
  removeOrder: (orderId: string) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;

  // Computed
  getPendingOrders: () => Order[];
  getFilledOrders: () => Order[];
  getOrdersBySymbol: (symbol: string) => Order[];
}

const initialState = {
  orders: [],
  isLoading: false,
  error: null,
};

export const useOrdersStore = create<OrdersState>((set, get) => ({
  ...initialState,

  setOrders: (orders) =>
    set({
      orders,
      error: null,
    }),

  addOrder: (order) =>
    set((state) => ({
      orders: [order, ...state.orders],
    })),

  updateOrder: (orderId, updates) =>
    set((state) => ({
      orders: state.orders.map((order) =>
        order.orderId === orderId ? { ...order, ...updates } : order
      ),
    })),

  removeOrder: (orderId) =>
    set((state) => ({
      orders: state.orders.filter((order) => order.orderId !== orderId),
    })),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  reset: () => set(initialState),

  // Computed
  getPendingOrders: () =>
    get().orders.filter((order) => 
      ['pending', 'submitted', 'partially_filled'].includes(order.status)
    ),

  getFilledOrders: () =>
    get().orders.filter((order) => order.status === 'filled'),

  getOrdersBySymbol: (symbol) =>
    get().orders.filter((order) => order.symbol === symbol),
}));
