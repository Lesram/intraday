/**
 * Strategies Page
 * Main wrapper for strategy management features
 */

import React from 'react';
import { Typography } from 'antd';
import { Outlet, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { strategiesService } from '@/services/strategiesService';
import { useStrategiesStore } from '@/store/strategiesStore';
import { useWebSocketConnection } from '@/hooks/useWebSocket';
import { WebSocketIndicator } from '@/components/common/WebSocketIndicator';
import { LoadingSpinner } from '@/components/common/LoadingComponents';
import { colors } from '@/styles/theme';

const { Title } = Typography;

export const StrategiesPage: React.FC = () => {
  const location = useLocation();
  const setStrategies = useStrategiesStore((state) => state.setStrategies);
  const { isConnected } = useWebSocketConnection();

  // Fetch strategies list (only on list page)
  const isListPage = location.pathname === '/strategies';
  
  const { isLoading, error } = useQuery({
    queryKey: ['strategies'],
    queryFn: async () => {
      const strategies = await strategiesService.getStrategies();
      setStrategies(strategies);
      return strategies;
    },
    enabled: isListPage,
    staleTime: 30000, // Cache for 30 seconds
    refetchOnWindowFocus: true,
  });

  // Show loading spinner only on initial list page load
  if (isListPage && isLoading) {
    return <LoadingSpinner tip="Loading strategies..." />;
  }

  // Show error only on list page
  if (isListPage && error) {
    return (
      <div
        style={{
          textAlign: 'center',
          padding: 48,
          background: colors.backgrounds.secondary,
          borderRadius: 8,
        }}
      >
        <Title level={4} type="danger">
          Failed to load strategies
        </Title>
        <p>Please check your connection and try again.</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px' }}>
      {/* WebSocket Connection Indicator - Show on list page */}
      {isListPage && (
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
          <WebSocketIndicator isConnected={isConnected} />
        </div>
      )}
      <Outlet />
    </div>
  );
};
