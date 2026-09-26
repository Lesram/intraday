import type { Portfolio } from '@/store/portfolioStore';

// The server cache is 10s. Expire observations even if a refresh never settles.
export const PORTFOLIO_REFRESH_MS = 10_000;
export const PORTFOLIO_MAX_AGE_MS = 30_000;

const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

export function isCurrentPortfolio(value: unknown, userId?: string, now = Date.now()): value is Portfolio {
  if (!object(value) || typeof value.userId !== 'string' || !value.userId || (userId !== undefined && value.userId !== userId)) return false;
  if (typeof value.lastUpdate !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(value.lastUpdate)) return false;
  const age = now - Date.parse(value.lastUpdate);
  if (!Number.isFinite(age) || age < 0 || age > PORTFOLIO_MAX_AGE_MS) return false;
  if (!['totalEquity', 'cash', 'buyingPower', 'marginUsed', 'maintenanceMargin', 'totalPnL', 'totalPnLPercent', 'dayPnL'].every((key) => finite(value[key]))) return false;
  if (value.dayPnLPercent !== null && !finite(value.dayPnLPercent)) return false;
  return Array.isArray(value.positions) && value.positions.every((position: unknown) =>
    object(position) && typeof position.symbol === 'string' && position.symbol.length > 0
    && ['quantity', 'averagePrice', 'currentPrice', 'marketValue', 'unrealizedPnL', 'unrealizedPnLPercent'].every((key) => finite(position[key]))
    && (position.side === 'long' || position.side === 'short') && typeof position.exchange === 'string');
}

export function newestPortfolio(first: Portfolio | null | undefined, second: Portfolio | null | undefined, userId: string, now = Date.now()): Portfolio | undefined {
  const a = isCurrentPortfolio(first, userId, now) ? first : undefined;
  const b = isCurrentPortfolio(second, userId, now) ? second : undefined;
  return a && (!b || Date.parse(a.lastUpdate) >= Date.parse(b.lastUpdate)) ? a : b;
}
