/**
 * Scanner Page
 * Market scanner with filtering and analysis tools
 * 
 * Phase 7 - Market Data & Charting
 * Created: October 16, 2025
 */

import React from 'react';
import { Scanner } from '../components/market/Scanner';

const ScannerPage: React.FC = () => {
  return (
    <div style={{ padding: '24px', height: '100%' }}>
      <Scanner />
    </div>
  );
};

export default ScannerPage;
