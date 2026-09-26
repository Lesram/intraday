import { describe, it, expect } from 'vitest';
import { isCurrentPortfolio, newestPortfolio } from './portfolioSnapshot';
import { portfolioFixture } from '@/test/portfolioFixture';


describe('portfolio observation validation', () => {
  it('accepts a genuine current empty account without inventing positions', () => {
    expect(isCurrentPortfolio(portfolioFixture(), 'alice')).toBe(true);
  });
  it.each([
    { totalEquity: NaN }, { cash: Infinity }, { lastUpdate: '2026-09-26T10:00:00' },
    { lastUpdate: new Date(Date.now() - 31000).toISOString() },
    { lastUpdate: new Date(Date.now() + 60000).toISOString() }, { userId: 'bob' },
    { positions: [{ symbol: 'AAPL' }] }, { buyingPower: '2000' }, {},
  ])('rejects malformed/stale/wrong-user snapshot %j', (changes) => {
    const data = Object.keys(changes).length ? { ...portfolioFixture(), ...changes } : {};
    expect(isCurrentPortfolio(data, 'alice')).toBe(false);
  });
  it('chooses by observation timestamp, not arrival order', () => {
    const recent = portfolioFixture();
    const old = portfolioFixture({ lastUpdate: new Date(Date.now() - 10000).toISOString() });
    expect(newestPortfolio(old, recent, 'alice')).toBe(recent);
  });
});
