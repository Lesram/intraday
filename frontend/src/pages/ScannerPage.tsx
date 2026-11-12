/**
 * Scanner Page
 * Market scanner with filtering and analysis tools
 *
 * Phase 7 - Market Data & Charting
 * Created: October 16, 2025
 *
 * Audit 2026-10-05 A6-01: the scanner is disabled on the backend unless
 * DASHBOARD_SCANNER_ENABLED=true. The page asks GET /scanner/status once on
 * load; while the scanner is disabled (or the status cannot be read) it shows
 * a static notice and never polls, scans or opens the scanner websocket.
 */

import React, { useEffect, useState } from 'react';
import { Result, Spin } from 'antd';
import { Scanner } from '../components/market/Scanner';
import { apiClient } from '../services/api';

type ScannerAvailability = 'checking' | 'enabled' | 'disabled';

const ScannerPage: React.FC = () => {
  const [availability, setAvailability] = useState<ScannerAvailability>('checking');

  useEffect(() => {
    let active = true;
    apiClient
      .get<{ enabled?: boolean }>('/scanner/status')
      .then((response) => {
        if (active) setAvailability(response.data?.enabled === true ? 'enabled' : 'disabled');
      })
      .catch(() => {
        if (active) setAvailability('disabled');
      });
    return () => {
      active = false;
    };
  }, []);

  if (availability === 'checking') {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '48px' }}>
        <Spin />
      </div>
    );
  }

  if (availability === 'disabled') {
    return (
      <div style={{ padding: '24px', height: '100%' }}>
        <Result
          status="info"
          title="Market Scanner is disabled"
          subTitle={
            'The dashboard market scanner is turned off on this deployment because its ' +
            'market-data requests run in the same process as the trading engine. ' +
            'An operator can enable it with DASHBOARD_SCANNER_ENABLED=true.'
          }
        />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', height: '100%' }}>
      <Scanner />
    </div>
  );
};

export default ScannerPage;
