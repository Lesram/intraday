import { ConfigProvider, App as AntApp } from 'antd';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';
import { darkTheme } from './styles/theme';
import { BrowserRouter } from 'react-router-dom';
import AppRoutes from './routes';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { KeyboardShortcuts } from './components/KeyboardShortcuts';
import './styles/accessibility.css';

// L-11 FIX: Lazy load DevTools only in development
const ReactQueryDevtools = import.meta.env.DEV
  ? lazy(() =>
      import('@tanstack/react-query-devtools').then((mod) => ({
        default: mod.ReactQueryDevtools,
      }))
    )
  : () => null;

// Create React Query client with optimized caching settings
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Caching behavior
      staleTime: 5 * 60 * 1000, // 5 minutes - data considered fresh
      gcTime: 30 * 60 * 1000, // 30 minutes - keep in cache (formerly cacheTime)
      
      // Refetch behavior - conservative to reduce API load
      refetchOnWindowFocus: false,
      refetchOnReconnect: 'always', // Refetch when network reconnects
      refetchOnMount: true, // Refetch when component mounts if stale
      
      // Retry behavior
      retry: 2,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      
      // Network mode - fetch when online
      networkMode: 'online',
    },
    mutations: {
      retry: 1,
      retryDelay: 1000,
      networkMode: 'online',
    },
  },
});

function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ConfigProvider theme={darkTheme}>
          <AntApp>
            <BrowserRouter>
              <KeyboardShortcuts />
              <AppRoutes />
            </BrowserRouter>
          </AntApp>
        </ConfigProvider>
        {/* L-11 FIX: DevTools only load in development mode */}
        <Suspense fallback={null}>
          <ReactQueryDevtools initialIsOpen={false} />
        </Suspense>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
