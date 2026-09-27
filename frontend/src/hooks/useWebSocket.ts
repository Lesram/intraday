/**
 * WebSocket Hook
 * React hook for subscribing to WebSocket topics
 */

import { useEffect } from 'react';
import { websocketManager } from '@/services/websocketManager';
import { useAuthStore } from '@/store/authStore';
import type { WebSocketTopic } from '@/types/websocket';

/**
 * Subscribe to a WebSocket topic
 * Automatically connects and subscribes when authenticated
 */
export const useWebSocket = <T = unknown>(
  topic: WebSocketTopic,
  handler: (data: T) => void,
  symbols?: string[]
) => {
  const accessToken = useAuthStore((state) => state.accessToken);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const userId = useAuthStore((state) => state.user?.id);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) return;

    // Connect if not already connected
    websocketManager.connect(accessToken);

    // Subscribe to topic
    websocketManager.subscribe(topic, handler as (data: unknown) => void, symbols);

    // Cleanup: Unsubscribe when component unmounts
    return () => {
      websocketManager.unsubscribe(topic, handler as (data: unknown) => void);
    };
  }, [topic, handler, symbols, accessToken, isAuthenticated, userId]);
};

/**
 * Hook to monitor WebSocket connection state
 */
export const useWebSocketConnection = () => {
  const accessToken = useAuthStore((state) => state.accessToken);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const userId = useAuthStore((state) => state.user?.id);

  useEffect(() => {
    if (isAuthenticated && accessToken) websocketManager.connect(accessToken);
    else websocketManager.disconnect();
  }, [isAuthenticated, accessToken, userId]);

  return {
    isConnected: websocketManager.isConnected(),
    connect: (token: string) => websocketManager.connect(token),
    disconnect: () => websocketManager.disconnect(),
  };
};
