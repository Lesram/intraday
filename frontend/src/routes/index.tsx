import { Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import MainLayout from '../components/layout/MainLayout';
import ProtectedRoute from '../components/auth/ProtectedRoute';
import { Spin } from 'antd';

// Page Loading Fallback
const PageLoader = () => (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
    <Spin size="large" />
  </div>
);

// Critical pages loaded eagerly (auth required immediately)
import LoginPage from '../features/auth/LoginPage';
import RegisterPage from '../features/auth/RegisterPage';
import Dashboard from '../features/dashboard/Dashboard';

// Lazy-loaded pages for better bundle splitting
const OrdersPage = lazy(() => import('../features/orders/OrdersPage'));
const TradingPage = lazy(() => import('../pages/TradingPage'));
const ScannerPage = lazy(() => import('../pages/ScannerPage'));
const PositionsPage = lazy(() => import('../features/positions/PositionsPage'));
const TradesPage = lazy(() => import('../features/trades/TradesPage'));
const ComingSoon = lazy(() => import('../components/common/ComingSoon'));

// Strategy pages (nested, loaded together)
const StrategiesPage = lazy(() => import('../features/strategies/StrategiesPage').then(m => ({ default: m.StrategiesPage })));
const StrategiesList = lazy(() => import('../features/strategies/StrategiesList').then(m => ({ default: m.StrategiesList })));
const StrategyDetail = lazy(() => import('../features/strategies/StrategyDetail').then(m => ({ default: m.StrategyDetail })));
const StrategyForm = lazy(() => import('../features/strategies/StrategyForm').then(m => ({ default: m.StrategyForm })));
const StrategyBuilderPage = lazy(() => import('../features/strategies/StrategyBuilderPage').then(m => ({ default: m.StrategyBuilderPage })));

// Heavy feature pages (backtesting, ML, risk) - always lazy
const BacktestingPage = lazy(() => import('../features/backtesting/BacktestingPage').then(m => ({ default: m.BacktestingPage })));
const MLModelsPage = lazy(() => import('../features/ml-models/pages/MLModelsPage').then(m => ({ default: m.MLModelsPage })));
const RiskManagement = lazy(() => import('../features/risk').then(m => ({ default: m.RiskManagement })));

// Portfolio, Organism, Strategy Monitor, Settings
const PortfolioPage = lazy(() => import('../features/portfolio/PortfolioPage'));
const OrganismDashboard = lazy(() => import('../features/organism/OrganismDashboard'));
const SettingsPage = lazy(() => import('../features/settings/SettingsPage'));

// Suspense wrapper for lazy components
const LazyRoute = ({ children }: { children: React.ReactNode }) => (
  <Suspense fallback={<PageLoader />}>{children}</Suspense>
);

const AppRoutes = () => {
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Protected Routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <MainLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="orders" element={<LazyRoute><OrdersPage /></LazyRoute>} />
        <Route path="trading" element={<LazyRoute><TradingPage /></LazyRoute>} />
        <Route path="positions" element={<LazyRoute><PositionsPage /></LazyRoute>} />
        <Route path="trades" element={<LazyRoute><TradesPage /></LazyRoute>} />
        <Route path="portfolio" element={<LazyRoute><PortfolioPage /></LazyRoute>} />
        
        {/* Strategies Routes */}
        <Route path="strategies" element={<LazyRoute><StrategiesPage /></LazyRoute>}>
          <Route index element={<LazyRoute><StrategiesList /></LazyRoute>} />
          {/* Static routes MUST come before dynamic :id route */}
          <Route path="new" element={<LazyRoute><StrategyForm mode="create" /></LazyRoute>} />
          <Route path="builder" element={<LazyRoute><StrategyBuilderPage /></LazyRoute>} />
          {/* Dynamic routes last */}
          <Route path=":id" element={<LazyRoute><StrategyDetail /></LazyRoute>} />
          <Route path=":id/edit" element={<LazyRoute><StrategyForm mode="edit" /></LazyRoute>} />
        </Route>
        
        {/* Backtesting Route - Phase 3.2 */}
        <Route path="backtesting" element={<LazyRoute><BacktestingPage /></LazyRoute>} />
        
        {/* ML Models Route - Phase 6 */}
        <Route path="ml-models" element={<LazyRoute><MLModelsPage /></LazyRoute>} />
        
        <Route path="risk" element={<LazyRoute><RiskManagement /></LazyRoute>} />
        <Route path="organism" element={<LazyRoute><OrganismDashboard /></LazyRoute>} />
        <Route path="market-data" element={<LazyRoute><ScannerPage /></LazyRoute>} />
        <Route path="reports" element={<LazyRoute><ComingSoon title="Reports" /></LazyRoute>} />
        <Route path="admin" element={<LazyRoute><ComingSoon title="Admin" /></LazyRoute>} />
        <Route path="settings" element={<LazyRoute><SettingsPage /></LazyRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
};

export default AppRoutes;
