/**
 * Data Hooks
 * React Query hooks for fetching and mutating data
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { App } from 'antd';
import { portfolioService } from '@/services/portfolioService';
import {
  ordersService,
  type SubmitOrderRequest,
  type OrdersQueryParams,
} from '@/services/ordersService';
import {
  strategiesService,
  type CreateStrategyRequest,
  type UpdateStrategyRequest,
} from '@/services/strategiesService';
import { usePortfolioStore } from '@/store/portfolioStore';
import { useOrdersStore } from '@/store/ordersStore';
import { useStrategiesStore } from '@/store/strategiesStore';

// ============= Portfolio Hooks =============

export const usePortfolio = () => {
  const setPortfolio = usePortfolioStore((state) => state.setPortfolio);
  const portfolio = usePortfolioStore((state) => state.portfolio);

  const query = useQuery({
    queryKey: ['portfolio'],
    queryFn: portfolioService.getPortfolio,
    // CRITICAL: Disable auto-refetch - WebSocket provides real-time updates
    // Without this, API would overwrite WebSocket updates every N seconds
    refetchInterval: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: Infinity,
  });

  // Only update store on initial load - WebSocket handles all subsequent updates
  useEffect(() => {
    if (query.data && !portfolio) {
      setPortfolio(query.data);
    }
  }, [query.data, setPortfolio, portfolio]);

  return query;
};

export const usePositions = () => {
  const setPositions = usePortfolioStore((state) => state.setPositions);

  const query = useQuery({
    queryKey: ['positions'],
    queryFn: portfolioService.getPositions,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  // Update store when data changes - use useEffect to avoid setState during render
  useEffect(() => {
    if (query.data) {
      setPositions(query.data);
    }
  }, [query.data, setPositions]);

  return query;
};

export const usePosition = (symbol: string) => {
  return useQuery({
    queryKey: ['position', symbol],
    queryFn: () => portfolioService.getPosition(symbol),
    enabled: !!symbol,
  });
};

export const usePortfolioHistory = (params?: {
  startDate?: string;
  endDate?: string;
  interval?: '1m' | '5m' | '15m' | '1h' | '1d';
}) => {
  return useQuery({
    queryKey: ['portfolioHistory', params],
    queryFn: () => portfolioService.getPortfolioHistory(params),
    staleTime: 60000, // 1 minute
  });
};

// ============= Orders Hooks =============

export const useOrders = (params?: OrdersQueryParams) => {
  const setOrders = useOrdersStore((state) => state.setOrders);

  const query = useQuery({
    queryKey: ['orders', params],
    queryFn: () => ordersService.getOrders(params),
    refetchInterval: 5000, // Refetch every 5 seconds
    staleTime: 3000,
  });

  // Update store when data changes - use useEffect to avoid setState during render
  useEffect(() => {
    if (query.data) {
      setOrders(query.data);
    }
  }, [query.data, setOrders]);

  return query;
};

export const useOrder = (orderId: string) => {
  return useQuery({
    queryKey: ['order', orderId],
    queryFn: () => ordersService.getOrder(orderId),
    enabled: !!orderId,
  });
};

export const useSubmitOrder = () => {
  const queryClient = useQueryClient();
  const addOrder = useOrdersStore((state) => state.addOrder);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (data: SubmitOrderRequest) => ordersService.submitOrder(data),
    onSuccess: (order) => {
      addOrder(order);
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      queryClient.invalidateQueries({ queryKey: ['positions'] });
      // Invalidate trade history and analytics for immediate updates
      queryClient.invalidateQueries({ queryKey: ['trades', 'history'] });
      queryClient.invalidateQueries({ queryKey: ['trades', 'analytics'] });
      message.success('Order submitted successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { message?: string } } };
      message.error(axiosError.response?.data?.message || 'Failed to submit order');
    },
  });
};

export const useCancelOrder = () => {
  const queryClient = useQueryClient();
  const updateOrder = useOrdersStore((state) => state.updateOrder);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (orderId: string) => ordersService.cancelOrder(orderId),
    onSuccess: (order) => {
      updateOrder(order.orderId, order);
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      message.success('Order cancelled successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { message?: string } } };
      message.error(axiosError.response?.data?.message || 'Failed to cancel order');
    },
  });
};

export const useModifyOrder = () => {
  const queryClient = useQueryClient();
  const updateOrder = useOrdersStore((state) => state.updateOrder);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: ({
      orderId,
      updates,
    }: {
      orderId: string;
      updates: Partial<SubmitOrderRequest>;
    }) => ordersService.modifyOrder(orderId, updates),
    onSuccess: (order) => {
      updateOrder(order.orderId, order);
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      message.success('Order modified successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { message?: string } } };
      message.error(axiosError.response?.data?.message || 'Failed to modify order');
    },
  });
};

export const useCancelAllOrders = () => {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (symbol?: string) => ordersService.cancelAllOrders(symbol),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      message.success(`Cancelled ${result.cancelled} orders`);
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { message?: string } } };
      message.error(
        axiosError.response?.data?.message || 'Failed to cancel orders'
      );
    },
  });
};

// ============= Strategies Hooks =============

export const useStrategies = () => {
  const setStrategies = useStrategiesStore((state) => state.setStrategies);

  const query = useQuery({
    queryKey: ['strategies'],
    queryFn: strategiesService.getStrategies,
    refetchInterval: 15000, // Refetch every 15 seconds
    staleTime: 10000,
  });

  // Update store when data changes - use useEffect to avoid setState during render
  useEffect(() => {
    if (query.data) {
      setStrategies(query.data);
    }
  }, [query.data, setStrategies]);

  return query;
};

export const useStrategy = (strategyId: string) => {
  return useQuery({
    queryKey: ['strategy', strategyId],
    queryFn: () => strategiesService.getStrategy(strategyId),
    enabled: !!strategyId,
  });
};

export const useCreateStrategy = () => {
  const queryClient = useQueryClient();
  const addStrategy = useStrategiesStore((state) => state.addStrategy);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (data: CreateStrategyRequest) =>
      strategiesService.createStrategy(data),
    onSuccess: (strategy) => {
      addStrategy(strategy);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      message.success('Strategy created successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { message?: string } } };
      message.error(
        axiosError.response?.data?.message || 'Failed to create strategy'
      );
    },
  });
};

export const useUpdateStrategy = () => {
  const queryClient = useQueryClient();
  const updateStrategy = useStrategiesStore((state) => state.updateStrategy);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: ({
      strategyId,
      updates,
    }: {
      strategyId: string;
      updates: UpdateStrategyRequest;
    }) => strategiesService.updateStrategy(strategyId, updates),
    onSuccess: (strategy) => {
      updateStrategy(strategy.strategyId, strategy);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      queryClient.invalidateQueries({ queryKey: ['strategy', strategy.strategyId] });
      message.success('Strategy updated successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { message?: string } } };
      message.error(
        axiosError.response?.data?.message || 'Failed to update strategy'
      );
    },
  });
};

export const useDeleteStrategy = () => {
  const queryClient = useQueryClient();
  const removeStrategy = useStrategiesStore((state) => state.removeStrategy);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (strategyId: string) =>
      strategiesService.deleteStrategy(strategyId),
    onSuccess: (_, strategyId) => {
      removeStrategy(strategyId);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      message.success('Strategy deleted successfully');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { message?: string } } };
      message.error(
        axiosError.response?.data?.message || 'Failed to delete strategy'
      );
    },
  });
};

export const useStartStrategy = () => {
  const queryClient = useQueryClient();
  const updateStrategy = useStrategiesStore((state) => state.updateStrategy);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (strategyId: string) =>
      strategiesService.startStrategy(strategyId),
    onSuccess: (strategy) => {
      updateStrategy(strategy.strategyId, strategy);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      message.success('Strategy started');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { message?: string } } };
      message.error(
        axiosError.response?.data?.message || 'Failed to start strategy'
      );
    },
  });
};

export const useStopStrategy = () => {
  const queryClient = useQueryClient();
  const updateStrategy = useStrategiesStore((state) => state.updateStrategy);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (strategyId: string) =>
      strategiesService.stopStrategy(strategyId),
    onSuccess: (strategy) => {
      updateStrategy(strategy.strategyId, strategy);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      message.success('Strategy stopped');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { message?: string } } };
      message.error(
        axiosError.response?.data?.message || 'Failed to stop strategy'
      );
    },
  });
};

export const usePauseStrategy = () => {
  const queryClient = useQueryClient();
  const updateStrategy = useStrategiesStore((state) => state.updateStrategy);
  const { message } = App.useApp();

  return useMutation({
    mutationFn: (strategyId: string) =>
      strategiesService.pauseStrategy(strategyId),
    onSuccess: (strategy) => {
      updateStrategy(strategy.strategyId, strategy);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      message.success('Strategy paused');
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { message?: string } } };
      message.error(
        axiosError.response?.data?.message || 'Failed to pause strategy'
      );
    },
  });
};

export const useStrategyPerformance = (
  strategyId: string,
  params?: {
    startDate?: string;
    endDate?: string;
  }
) => {
  return useQuery({
    queryKey: ['strategyPerformance', strategyId, params],
    queryFn: () => strategiesService.getStrategyPerformance(strategyId),
    enabled: !!strategyId,
    staleTime: 60000, // 1 minute
  });
};
