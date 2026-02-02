/**
 * Connection Status Indicator
 * Shows WebSocket connection state
 */

import React, { useEffect, useState } from 'react';
import { Badge, Tooltip } from 'antd';
import { websocketManager } from '@/services/websocketManager';
import { useUIStore } from '@/store/uiStore';

export const ConnectionStatus: React.FC = () => {
  const [isConnected, setIsConnected] = useState(websocketManager.isConnected());
  const setWebSocketConnected = useUIStore((state) => state.setWebSocketConnected);

  useEffect(() => {
    // Subscribe to connection state changes
    const unsubscribe = websocketManager.onConnectionChange((connected) => {
      setIsConnected(connected);
      setWebSocketConnected(connected);
    });

    // Initial state
    setIsConnected(websocketManager.isConnected());
    setWebSocketConnected(websocketManager.isConnected());

    return unsubscribe;
  }, [setWebSocketConnected]);

  return (
    <Tooltip title={isConnected ? 'Connected to server' : 'Disconnected from server'}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Badge
          status={isConnected ? 'success' : 'error'}
          text={isConnected ? 'Live' : 'Offline'}
        />
      </div>
    </Tooltip>
  );
};
