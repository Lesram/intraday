import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Dashboard from './Dashboard';
import { portfolioService } from '@/services/portfolioService';
import { usePortfolioStore } from '@/store/portfolioStore';
import { useAuthStore } from '@/store/authStore';
import { websocketManager } from '@/services/websocketManager';
import { portfolioFixture } from '@/test/portfolioFixture';
vi.mock('@/services/portfolioService', () => ({ portfolioService: { getPortfolio: vi.fn() } }));
vi.mock('@/hooks/useData', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/hooks/useData')>(),
  useOrders: () => ({ isLoading: false }), useStrategies: () => ({ isLoading: false }),
  usePortfolioHistory: () => ({ data: [], isLoading: false }),
}));
vi.mock('@/hooks/useWebSocket', async () => {
  const { useEffect } = await import('react');
  const { websocketManager: manager } = await import('@/services/websocketManager');
  return { useWebSocket: (topic: Parameters<typeof manager.subscribe>[0], handler: (data: unknown) => void) => {
    useEffect(() => { manager.subscribe(topic, handler); return () => manager.unsubscribe(topic, handler); }, [topic, handler]);
  } };
});
vi.mock('@/components/charts/PortfolioChart', () => ({ PortfolioChart: () => null }));
vi.mock('@/components/portfolio/PositionsTable', () => ({ PositionsTable: () => null }));
vi.mock('@/components/common/ConnectionStatus', () => ({ ConnectionStatus: () => null }));
beforeEach(() => {
  vi.clearAllMocks(); usePortfolioStore.getState().reset();
  useAuthStore.setState({ isAuthenticated: true, user: { id: 'alice', name: 'Alice', email: '', role: 'viewer', is_active: true, created_at: '' } });
});
it('actual manager direct payload updates displayed equity, rejects wrong user and malformed data', async () => {
  vi.mocked(portfolioService.getPortfolio).mockResolvedValue(portfolioFixture({ lastUpdate: new Date(Date.now() - 10000).toISOString() }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const { unmount } = render(<QueryClientProvider client={client}><Dashboard /></QueryClientProvider>);
  await screen.findByText('Portfolio Equity');
  const deliver = (data: unknown) => (websocketManager as unknown as { handleMessage: (message: unknown) => void }).handleMessage({ topic: 'portfolio', data });
  act(() => deliver(portfolioFixture({ totalEquity: 105555 })));
  await waitFor(() => expect(screen.getByText('$105,555.00')).toBeInTheDocument());
  act(() => deliver(portfolioFixture({ userId: 'bob', totalEquity: 999999 })));
  act(() => deliver({ totalEquity: 0, positions: [] }));
  expect(usePortfolioStore.getState().portfolio?.totalEquity).toBe(105555);
  expect(screen.queryByText('$999,999.00')).not.toBeInTheDocument();
  unmount(); client.clear();
});
it('failed API refresh hides old store rather than rendering flat or current account', async () => {
  usePortfolioStore.getState().setPortfolio(portfolioFixture());
  vi.mocked(portfolioService.getPortfolio).mockRejectedValue(new Error('unavailable'));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const { unmount } = render(<QueryClientProvider client={client}><Dashboard /></QueryClientProvider>);
  await screen.findByText('Failed to Load Portfolio');
  expect(screen.queryByText('Portfolio Equity')).not.toBeInTheDocument();
  unmount(); client.clear();
});
