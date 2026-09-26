import type { ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePortfolio } from './useData';
import { portfolioService } from '@/services/portfolioService';
import { usePortfolioStore } from '@/store/portfolioStore';
import { useAuthStore } from '@/store/authStore';
import { portfolioFixture } from '@/test/portfolioFixture';
vi.mock('@/services/portfolioService', () => ({ portfolioService: { getPortfolio: vi.fn() } }));

function harness() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return { ...renderHook(usePortfolio, { wrapper }), client };
}
beforeEach(() => {
  vi.clearAllMocks(); usePortfolioStore.getState().reset();
  useAuthStore.setState({ isAuthenticated: true, user: { id: 'alice', name: 'Alice', email: 'alice@example.test', role: 'viewer', is_active: true, created_at: '' } });
});
describe('current portfolio hook', () => {
  it('refresh replaces existing store and failure hides balances until verified recovery', async () => {
    const old = portfolioFixture({ lastUpdate: new Date(Date.now() - 10000).toISOString() });
    usePortfolioStore.getState().setPortfolio(old);
    vi.mocked(portfolioService.getPortfolio).mockResolvedValue(portfolioFixture({ totalEquity: 103000 }));
    const { result, client } = harness();
    await waitFor(() => expect(result.current.data?.totalEquity).toBe(103000));
    expect(usePortfolioStore.getState().portfolio?.totalEquity).toBe(103000);
    vi.mocked(portfolioService.getPortfolio).mockRejectedValue(new Error('private provider error'));
    await act(async () => { await result.current.refetch(); });
    await waitFor(() => expect(result.current.data).toBeUndefined()); expect(result.current.error?.message).not.toContain('private');
    vi.mocked(portfolioService.getPortfolio).mockResolvedValue(portfolioFixture({ totalEquity: 104000 }));
    await act(async () => { await result.current.refetch(); });
    await waitFor(() => expect(result.current.data?.totalEquity).toBe(104000)); client.clear();
  });
  it('does not overwrite a newer WebSocket observation with older HTTP cache data', async () => {
    const recent = portfolioFixture({ totalEquity: 105000 }); usePortfolioStore.getState().setPortfolio(recent);
    vi.mocked(portfolioService.getPortfolio).mockResolvedValue(portfolioFixture({ lastUpdate: new Date(Date.now() - 10000).toISOString() }));
    const { result, client } = harness(); await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(recent); expect(usePortfolioStore.getState().portfolio).toEqual(recent); client.clear();
  });
  it('expires an observation even if the refresh is hanging', async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(portfolioService.getPortfolio).mockImplementation(() => new Promise(() => {}));
      usePortfolioStore.getState().setPortfolio(portfolioFixture());
      const { result, client, unmount } = harness();
      expect(result.current.data).toBeDefined();
      await act(async () => { vi.advanceTimersByTime(31000); });
      expect(result.current.data).toBeUndefined(); unmount(); client.clear();
    } finally { vi.useRealTimers(); }
  });
  it('polls again after ten seconds and never shows a previous user portfolio', async () => {
    vi.useFakeTimers();
    try {
      usePortfolioStore.getState().setPortfolio(portfolioFixture({ userId: 'bob' }));
      vi.mocked(portfolioService.getPortfolio).mockResolvedValue(portfolioFixture());
      const { result, client, unmount } = harness();
      expect(result.current.data).toBeUndefined();
      await act(async () => { await vi.advanceTimersByTimeAsync(100); });
      expect(result.current.data?.userId).toBe('alice');
      await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
      expect(portfolioService.getPortfolio).toHaveBeenCalledTimes(2);
      act(() => useAuthStore.setState({ isAuthenticated: false, user: null }));
      expect(result.current.data).toBeUndefined(); unmount(); client.clear();
    } finally { vi.useRealTimers(); }
  });
});
