/**
 * Global Status Bar Component
 * Displays real-time status indicators for:
 * - Market status (Open/Closed/Extended Hours)
 * - Current EST time
 * - WebSocket connection status
 * - Broker (Alpaca) connection status
 * 
 * This component is always visible in the header regardless of the current page.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Space, Tooltip, Tag } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  SyncOutlined,
  ClockCircleOutlined,
  ApiOutlined,
  WifiOutlined,
  DisconnectOutlined,
  LoginOutlined,
} from '@ant-design/icons';
import { getMarketStatus, type MarketHours } from '@/utils/marketHours';
import { websocketManager } from '@/services/websocketManager';
import { apiClient } from '@/services/api';
import { colors } from '@/styles/theme';
import { useAuthStore } from '@/store/authStore';

interface BrokerStatus {
  connected: boolean;
  lastCheck: Date | null;
  error?: string;
  notAuthenticated?: boolean;
}

export const GlobalStatusBar: React.FC = () => {
  // Auth status
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  
  // Market status
  const [marketStatus, setMarketStatus] = useState<MarketHours>(() => getMarketStatus());
  const [currentTime, setCurrentTime] = useState<string>('');
  
  // WebSocket status
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  
  // Broker status
  const [brokerStatus, setBrokerStatus] = useState<BrokerStatus>({
    connected: false,
    lastCheck: null,
  });
  const [checkingBroker, setCheckingBroker] = useState<boolean>(false);

  // Format current EST time
  const formatESTTime = useCallback(() => {
    const now = new Date();
    return now.toLocaleString('en-US', {
      timeZone: 'America/New_York',
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    }) + ' EST';
  }, []);

  // Check broker connection - only if authenticated
  const checkBrokerConnection = useCallback(async () => {
    // Skip check if not authenticated
    if (!isAuthenticated) {
      setBrokerStatus({
        connected: false,
        lastCheck: new Date(),
        notAuthenticated: true,
      });
      return;
    }
    
    setCheckingBroker(true);
    try {
      // Call a lightweight endpoint to verify broker connectivity
      // Use /portfolio/ (not /portfolio/summary) as that's the actual endpoint
      const response = await apiClient.get('/portfolio/');
      if (response.status === 200) {
        setBrokerStatus({
          connected: true,
          lastCheck: new Date(),
        });
      }
    } catch (error) {
      const axiosError = error as { response?: { status?: number } };
      setBrokerStatus({
        connected: false,
        lastCheck: new Date(),
        error: axiosError?.response?.status === 401 
          ? 'Not authenticated' 
          : (error instanceof Error ? error.message : 'Unknown error'),
        notAuthenticated: axiosError?.response?.status === 401,
      });
    } finally {
      setCheckingBroker(false);
    }
  }, [isAuthenticated]);

  // Update time every second
  useEffect(() => {
    const updateTime = () => {
      setCurrentTime(formatESTTime());
      setMarketStatus(getMarketStatus());
    };
    
    updateTime(); // Initial
    const interval = setInterval(updateTime, 1000);
    
    return () => clearInterval(interval);
  }, [formatESTTime]);

  // Monitor WebSocket connection
  useEffect(() => {
    const handleConnectionChange = (connected: boolean) => {
      setWsConnected(connected);
    };
    
    // onConnectionChange returns a cleanup function
    const cleanup = websocketManager.onConnectionChange(handleConnectionChange);
    
    // Check initial state
    setWsConnected(websocketManager.isConnected());
    
    return cleanup;
  }, []);

  // Check broker connection periodically
  useEffect(() => {
    checkBrokerConnection(); // Initial check
    const interval = setInterval(checkBrokerConnection, 30000); // Every 30 seconds
    
    return () => clearInterval(interval);
  }, [checkBrokerConnection]);

  const getMarketIcon = () => {
    if (marketStatus.isOpen) return <CheckCircleFilled />;
    if (marketStatus.isExtendedHours) return <SyncOutlined spin />;
    return <CloseCircleFilled />;
  };

  return (
    <Space 
      size="middle" 
      style={{ 
        padding: '0 16px',
        borderLeft: `1px solid ${colors.backgrounds.border}`,
        marginLeft: 16,
      }}
    >
      {/* EST Time */}
      <Tooltip title="Current Eastern Standard Time">
        <Space size={4}>
          <ClockCircleOutlined style={{ color: colors.text.secondary }} />
          <span style={{ 
            color: colors.text.secondary, 
            fontSize: 12,
            fontFamily: 'monospace',
            minWidth: 200,
          }}>
            {currentTime}
          </span>
        </Space>
      </Tooltip>

      {/* Market Status */}
      <Tooltip 
        title={
          <div>
            <div>{marketStatus.message}</div>
            {marketStatus.warning && (
              <div style={{ color: colors.semantic.warning, marginTop: 4 }}>
                {marketStatus.warning}
              </div>
            )}
            {marketStatus.nextOpen && (
              <div style={{ marginTop: 4 }}>
                Opens: {marketStatus.nextOpen.toLocaleString('en-US', {
                  timeZone: 'America/New_York',
                  weekday: 'short',
                  hour: 'numeric',
                  minute: '2-digit',
                })} EST
              </div>
            )}
          </div>
        }
      >
        <Tag 
          icon={getMarketIcon()} 
          color={marketStatus.isOpen ? 'success' : marketStatus.isExtendedHours ? 'warning' : 'default'}
          style={{ 
            margin: 0,
            fontWeight: 500,
          }}
        >
          {marketStatus.isOpen 
            ? 'MARKET OPEN' 
            : marketStatus.isExtendedHours 
              ? 'EXTENDED' 
              : 'MARKET CLOSED'}
        </Tag>
      </Tooltip>

      {/* WebSocket Status */}
      <Tooltip 
        title={wsConnected ? 'Real-time data connected' : 'Real-time data disconnected'}
      >
        <Tag 
          icon={wsConnected ? <WifiOutlined /> : <DisconnectOutlined />}
          color={wsConnected ? 'success' : 'error'}
          style={{ margin: 0 }}
        >
          WS: {wsConnected ? 'LIVE' : 'OFFLINE'}
        </Tag>
      </Tooltip>

      {/* Broker (Alpaca) Status */}
      <Tooltip 
        title={
          <div>
            {brokerStatus.notAuthenticated ? (
              <div>Please log in to check broker connection</div>
            ) : (
              <>
                <div>Alpaca Broker: {brokerStatus.connected ? 'Connected' : 'Disconnected'}</div>
                {brokerStatus.error && !brokerStatus.notAuthenticated && (
                  <div style={{ color: colors.semantic.error, marginTop: 4 }}>
                    Error: {brokerStatus.error}
                  </div>
                )}
                {brokerStatus.lastCheck && (
                  <div style={{ marginTop: 4, color: colors.text.disabled }}>
                    Last checked: {brokerStatus.lastCheck.toLocaleTimeString()}
                  </div>
                )}
              </>
            )}
          </div>
        }
      >
        <Tag 
          icon={checkingBroker ? <SyncOutlined spin /> : brokerStatus.notAuthenticated ? <LoginOutlined /> : <ApiOutlined />}
          color={brokerStatus.connected ? 'success' : brokerStatus.notAuthenticated ? 'warning' : 'error'}
          style={{ margin: 0 }}
        >
          ALPACA: {brokerStatus.connected ? 'OK' : brokerStatus.notAuthenticated ? 'LOGIN' : 'ERROR'}
        </Tag>
      </Tooltip>
    </Space>
  );
};

export default GlobalStatusBar;
