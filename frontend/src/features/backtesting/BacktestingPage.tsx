/**
 * BacktestingPage Component
 * 
 * Main page for the backtesting feature. Allows users to:
 * - Run new backtests on their strategies
 * - View backtest results with detailed analytics
 * - Browse backtest history
 * - Export backtest data
 */

import React, { useState } from 'react';
import { Row, Col, Space, Button, App } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { BacktestForm } from './components/BacktestForm';
import { BacktestResults } from './components/BacktestResults';
import { BacktestHistory } from './components/BacktestHistory';
import { 
  useRunBacktest, 
  useBacktestHistory, 
  useBacktestResult,
  useDeleteBacktest,
  useExportBacktest,
} from './hooks/useBacktest';
import { useStrategies } from '@/hooks/useData';
import type { BacktestRequest } from '../../types/backtest';

export const BacktestingPage: React.FC = () => {
  const { message } = App.useApp();
  const [selectedBacktestId, setSelectedBacktestId] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyPageSize, setHistoryPageSize] = useState(20);
  const [strategyFilter, setStrategyFilter] = useState<string | undefined>();

  // React Query hooks
  const { data: strategiesData, isLoading: strategiesLoading } = useStrategies();
  const runBacktestMutation = useRunBacktest();

  // Map Strategy type to component format
  const strategies = strategiesData?.map(s => ({
    id: s.strategyId,
    name: s.name,
    type: s.strategyType,
  })) || [];
  const { data: historyData, isLoading: historyLoading } = useBacktestHistory({
    page: historyPage,
    pageSize: historyPageSize,
    strategyId: strategyFilter,
  });
  const { data: backtestResult, isLoading: resultLoading } = useBacktestResult(selectedBacktestId);
  const deleteBacktestMutation = useDeleteBacktest();
  const exportBacktestMutation = useExportBacktest();

  // Handlers
  const handleRunBacktest = async (strategyId: string, request: BacktestRequest) => {
    try {
      const result = await runBacktestMutation.mutateAsync({ strategyId, request });
      setSelectedBacktestId(result.id);
      message.success('Backtest started successfully!');
    } catch (error) {
      console.error('Failed to start backtest:', error);
    }
  };

  const handleViewBacktest = (backtestId: string) => {
    setSelectedBacktestId(backtestId);
    // Scroll to top to show results
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDeleteBacktest = async (backtestId: string) => {
    try {
      await deleteBacktestMutation.mutateAsync(backtestId);
      if (selectedBacktestId === backtestId) {
        setSelectedBacktestId(null);
      }
    } catch (error) {
      console.error('Failed to delete backtest:', error);
    }
  };

  const handleExportBacktest = async (format: 'csv' | 'json') => {
    if (!selectedBacktestId) {
      message.warning('Please select a backtest to export');
      return;
    }
    
    try {
      await exportBacktestMutation.mutateAsync({
        backtestId: selectedBacktestId,
        format,
      });
    } catch (error) {
      console.error('Failed to export backtest:', error);
    }
  };

  const handlePageChange = (page: number, pageSize: number) => {
    setHistoryPage(page);
    setHistoryPageSize(pageSize);
  };

  const handleStrategyFilter = (strategyId: string | null) => {
    setStrategyFilter(strategyId || undefined);
    setHistoryPage(1); // Reset to first page when filtering
  };

  return (
    <div style={{ padding: '24px' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Page Header */}
        <div>
          <h1 style={{ marginBottom: 8 }}>Backtesting</h1>
          <p style={{ color: '#8c8c8c', marginBottom: 0 }}>
            Test your trading strategies against historical data to evaluate performance and risk metrics.
          </p>
        </div>

        {/* Main Content */}
        <Row gutter={[24, 24]}>
          {/* Left Column: Form and Results */}
          <Col xs={24} lg={16}>
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              {/* Backtest Form */}
              {strategiesLoading ? (
                <div style={{ textAlign: 'center', padding: '60px 0' }}>
                  Loading strategies...
                </div>
              ) : (
                <BacktestForm
                  strategies={strategies || []}
                  onSubmit={handleRunBacktest}
                  loading={runBacktestMutation.isPending}
                />
              )}

              {/* Backtest Results */}
              {backtestResult && (
                <>
                  <div style={{ textAlign: 'right' }}>
                    <Space>
                      <Button
                        icon={<DownloadOutlined />}
                        onClick={() => handleExportBacktest('csv')}
                        loading={exportBacktestMutation.isPending}
                      >
                        Export CSV
                      </Button>
                      <Button
                        icon={<DownloadOutlined />}
                        onClick={() => handleExportBacktest('json')}
                        loading={exportBacktestMutation.isPending}
                      >
                        Export JSON
                      </Button>
                    </Space>
                  </div>
                  <BacktestResults result={backtestResult} />
                </>
              )}

              {resultLoading && selectedBacktestId && (
                <div style={{ textAlign: 'center', padding: '60px 0' }}>
                  Loading backtest results...
                </div>
              )}
            </Space>
          </Col>

          {/* Right Column: Quick Stats / Info (Future Enhancement) */}
          <Col xs={24} lg={8}>
            {/* Placeholder for future enhancements:
                - Recent backtests widget
                - Strategy performance comparison
                - Quick tips
            */}
          </Col>
        </Row>

        {/* Backtest History */}
        <BacktestHistory
          backtests={historyData?.items || []}
          total={historyData?.total || 0}
          page={historyPage}
          pageSize={historyPageSize}
          loading={historyLoading}
          onPageChange={handlePageChange}
          onView={handleViewBacktest}
          onDelete={handleDeleteBacktest}
          strategies={strategies || []}
          onStrategyFilter={handleStrategyFilter}
        />
      </Space>
    </div>
  );
};

export default BacktestingPage;
