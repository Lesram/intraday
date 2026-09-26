import type { Portfolio } from '@/store/portfolioStore';

export const portfolioFixture = (changes: Partial<Portfolio> = {}): Portfolio => ({
  userId: 'alice', totalEquity: 102000, cash: 102000, buyingPower: 204000,
  marginUsed: 0, maintenanceMargin: 0, totalPnL: 0, totalPnLPercent: 0,
  dayPnL: 0, dayPnLPercent: 0, positions: [], lastUpdate: new Date().toISOString(), ...changes,
});
