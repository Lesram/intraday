import React, { useEffect, useMemo, useState } from 'react';
import { App, Card, Col, Descriptions, Row, Space, Table, Tag, Typography, Button, Select, Tooltip } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { mlApi, mlQueryKeys } from '@/services/mlApi';
import type { LifecycleModelSummary, LifecycleSummaryResponse } from '@/types/ml';
import type { TradingExecutionMode, TradingExecutionModeResponse } from '@/types/ml';
import { useAuthStore } from '@/store/authStore';

const { Text, Title } = Typography;

export const LifecycleDashboard: React.FC = () => {
  const { message: appMessage } = App.useApp();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';

  const { data, isLoading, error } = useQuery({
    queryKey: mlQueryKeys.lifecycleSummary(),
    queryFn: () => mlApi.getLifecycleSummary(),
    staleTime: 15000,
    refetchInterval: 15000,
  });

  const runDaily = useMutation({
    mutationFn: () => mlApi.runDailyMonitoringJob({ lookback_days: 60 }),
    onSuccess: (res) => {
      appMessage.success(res.message);
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.lifecycleSummary() });
    },
  });

  const runWeekly = useMutation({
    mutationFn: () =>
      mlApi.runWeeklyRetrainJob({
        lookback_days: 60,
        min_return_drop: 0.02,
        psi_threshold: 0.15,
      }),
    onSuccess: (res) => {
      appMessage.success(res.message);
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.lifecycleSummary() });
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.lists() });
    },
  });

  const runMonthly = useMutation({
    mutationFn: () => mlApi.runMonthlyReviewJob(),
    onSuccess: (res) => {
      appMessage.success(res.message);
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.lifecycleSummary() });
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.lists() });
    },
  });

  const summary: LifecycleSummaryResponse | undefined = data;

  const {
    data: executionMode,
    isLoading: isLoadingExecutionMode,
    error: executionModeError,
  } = useQuery({
    queryKey: mlQueryKeys.tradingExecutionMode(),
    queryFn: () => mlApi.getTradingExecutionMode(),
    enabled: isAdmin,
    staleTime: 5000,
    refetchInterval: 5000,
  });

  const allowedModes: TradingExecutionMode[] = useMemo(() => {
    const serverAllowed = executionMode?.allowed_modes;
    if (serverAllowed && serverAllowed.length) return serverAllowed;
    return ['execute', 'shadow', 'dry_run'];
  }, [executionMode?.allowed_modes]);

  const [selectedMode, setSelectedMode] = useState<TradingExecutionMode>('execute');

  useEffect(() => {
    if (executionMode?.mode) setSelectedMode(executionMode.mode);
  }, [executionMode?.mode]);

  const setMode = useMutation({
    mutationFn: (mode: TradingExecutionMode) => mlApi.setTradingExecutionMode(mode),
    onSuccess: (res: TradingExecutionModeResponse) => {
      appMessage.success(`Execution mode set to: ${res.mode}`);
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.tradingExecutionMode() });
    },
    onError: () => {
      appMessage.error('Failed to update execution mode (admin only)');
    },
  });

  const clearMode = useMutation({
    mutationFn: () => mlApi.clearTradingExecutionModeOverride(),
    onSuccess: (res: TradingExecutionModeResponse) => {
      appMessage.success(`Execution mode reverted to env: ${res.mode}`);
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.tradingExecutionMode() });
    },
    onError: () => {
      appMessage.error('Failed to clear execution mode override (admin only)');
    },
  });

  const rows = (summary?.active_models || []).map((m: LifecycleModelSummary) => {
    const s = m.last_snapshot;
    const metrics = (s?.metrics || {}) as Record<string, unknown>;
    const drift = (s?.drift || {}) as Record<string, unknown>;

    const totalReturn = typeof metrics.total_return === 'number' ? metrics.total_return : null;
    const sharpe = typeof metrics.sharpe === 'number' ? metrics.sharpe : null;
    const maxDd = typeof metrics.max_drawdown === 'number' ? metrics.max_drawdown : null;
    const psi = typeof drift.psi_score === 'number' ? drift.psi_score : null;

    return {
      key: m.model_id,
      model_name: m.model_name,
      model_version: m.model_version,
      last_snapshot_at: s?.created_at,
      total_return: totalReturn,
      sharpe,
      max_drawdown: maxDd,
      psi,
      retrain: m.last_retrain_decision,
    };
  });

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Row justify="space-between" align="middle">
        <Col>
          <Space direction="vertical" size={4}>
            <Title level={4} style={{ margin: 0 }}>
              ML Lifecycle Dashboard
            </Title>
            <Text type="secondary">Daily monitor → weekly retrain → monthly promotion review</Text>
          </Space>
        </Col>
        <Col>
          <Space>
            <Tooltip
              title={
                isAdmin
                  ? 'Controls whether outbox submits orders to the broker'
                  : 'Admin-only: controls whether orders are submitted to broker'
              }
            >
              <Space>
                <Tag color={executionMode?.mode === 'execute' ? 'green' : executionMode?.mode === 'shadow' ? 'orange' : 'blue'}>
                  Execution: {isAdmin ? (executionMode?.mode ?? (isLoadingExecutionMode ? 'loading' : 'n/a')) : 'admin-only'}
                </Tag>
                {isAdmin && !executionModeError ? (
                  <>
                    <Select<TradingExecutionMode>
                      value={selectedMode}
                      style={{ width: 140 }}
                      options={allowedModes.map((m) => ({ value: m, label: m }))}
                      onChange={(v) => setSelectedMode(v)}
                      disabled={isLoadingExecutionMode || setMode.isPending}
                    />
                    <Button
                      onClick={() => setMode.mutate(selectedMode)}
                      loading={setMode.isPending}
                      disabled={isLoadingExecutionMode}
                    >
                      Apply
                    </Button>
                    <Button
                      onClick={() => clearMode.mutate()}
                      loading={clearMode.isPending}
                      disabled={isLoadingExecutionMode}
                    >
                      Clear Override
                    </Button>
                  </>
                ) : null}
              </Space>
            </Tooltip>
            <Button onClick={() => runDaily.mutate()} loading={runDaily.isPending}>
              Run Daily Monitoring
            </Button>
            <Button onClick={() => runWeekly.mutate()} loading={runWeekly.isPending}>
              Run Weekly Retrain
            </Button>
            <Button onClick={() => runMonthly.mutate()} loading={runMonthly.isPending}>
              Run Monthly Review
            </Button>
          </Space>
        </Col>
      </Row>

      <Card loading={isLoading}>
        {error ? (
          <Text type="danger">Failed to load lifecycle summary</Text>
        ) : (
          <Descriptions size="small" bordered column={2}>
            <Descriptions.Item label="Scheduler Enabled">
              <Tag color={summary?.scheduler_enabled ? 'green' : 'default'}>
                {summary?.scheduler_enabled ? 'Yes' : 'No'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Promotion Mode">
              <Text>{String(summary?.scheduler_state?.promotion_mode ?? 'immediate')}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Next Daily">
              <Text>{String(summary?.scheduler_state?.next_daily ?? 'n/a')}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Next Weekly">
              <Text>{String(summary?.scheduler_state?.next_weekly ?? 'n/a')}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Next Monthly" span={2}>
              <Text>{String(summary?.scheduler_state?.next_monthly ?? 'n/a')}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Last Promotion Review" span={2}>
              <Text>{summary?.last_promotion_review ? JSON.stringify(summary.last_promotion_review) : 'n/a'}</Text>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Card>

      <Card title="Active Models (latest snapshot)">
        <Table
          size="small"
          dataSource={rows}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: 'Name', dataIndex: 'model_name', key: 'model_name' },
            { title: 'Version', dataIndex: 'model_version', key: 'model_version' },
            {
              title: 'Last Snapshot',
              dataIndex: 'last_snapshot_at',
              key: 'last_snapshot_at',
              render: (v) => <Text>{v ? String(v) : 'n/a'}</Text>,
            },
            {
              title: 'Total Return',
              dataIndex: 'total_return',
              key: 'total_return',
              render: (v) => (typeof v === 'number' ? <Text>{(v * 100).toFixed(2)}%</Text> : 'n/a'),
            },
            {
              title: 'Sharpe',
              dataIndex: 'sharpe',
              key: 'sharpe',
              render: (v) => (typeof v === 'number' ? <Text>{v.toFixed(2)}</Text> : 'n/a'),
            },
            {
              title: 'Max DD',
              dataIndex: 'max_drawdown',
              key: 'max_drawdown',
              render: (v) => (typeof v === 'number' ? <Text>{(v * 100).toFixed(2)}%</Text> : 'n/a'),
            },
            {
              title: 'PSI',
              dataIndex: 'psi',
              key: 'psi',
              render: (v) => (typeof v === 'number' ? <Text>{v.toFixed(3)}</Text> : 'n/a'),
            },
          ]}
        />
      </Card>
    </Space>
  );
};
