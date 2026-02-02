/**
 * Performance Charts Component
 * Historical performance tracking and trend analysis
 * Phase 6 Day 5 Implementation
 */

import React from 'react';
import {
  Card,
  Select,
  Space,
  Typography,
  Row,
  Col,
  DatePicker,
  Button,
  Empty,
  Alert,
  message,
  Statistic,
  Tag,
  Spin,
} from 'antd';
import {
  LineChartOutlined,
  DownloadOutlined,
  RiseOutlined,
  FallOutlined,
} from '@ant-design/icons';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import type { TooltipItem } from 'chart.js';
import dayjs, { Dayjs } from 'dayjs';
import { mlApi, mlQueryKeys, mlQueryOptions } from '@/services/mlApi';
import { colors } from '@/styles/theme';
import type { ModelInfo, MonitoringSnapshot } from '@/types/ml';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

const { RangePicker } = DatePicker;
const { Text } = Typography;
const { Option } = Select;

interface PerformanceChartsProps {
  preselectedModelIds?: string[];
}

export const PerformanceCharts: React.FC<PerformanceChartsProps> = ({
  preselectedModelIds = [],
}) => {
  const queryClient = useQueryClient();
  const [selectedModelIds, setSelectedModelIds] = React.useState<string[]>(
    preselectedModelIds
  );
  const [selectedMetric, setSelectedMetric] = React.useState<string>('total_return');
  const [dateRange, setDateRange] = React.useState<[Dayjs, Dayjs]>([
    dayjs().subtract(30, 'days'),
    dayjs(),
  ]);

  // Fetch all models for selection
  const { data: modelsData } = useQuery({
    queryKey: mlQueryKeys.lists(),
    queryFn: () => mlApi.listModels(),
    ...mlQueryOptions.models,
  });

  const runMonitoringMutation = useMutation({
    mutationFn: (modelId: string) => mlApi.runMonitoring(modelId, { lookback_days: 60 }),
    onSuccess: (_data, modelId) => {
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.monitoring(modelId) });
    },
  });

  const retrainIfNeededMutation = useMutation({
    mutationFn: (modelId: string) =>
      mlApi.retrainIfNeeded(modelId, {
        lookback_days: 60,
        min_return_drop: 0.02,
        psi_threshold: 0.15,
      }),
    onSuccess: (data, modelId) => {
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.monitoring(modelId) });
      queryClient.invalidateQueries({ queryKey: mlQueryKeys.lists() });

      if (data.should_retrain) {
        message.success(
          `Retrain triggered for ${modelId}${data.training_id ? ` (job ${data.training_id})` : ''}`
        );
      } else {
        message.info(`No retrain needed for ${modelId}`);
      }

      if (data.reasons?.length) {
        message.info(data.reasons.join(' • '));
      }
    },
  });

  const monitoringQueries = useQueries({
    queries: selectedModelIds.map((modelId) => ({
      queryKey: mlQueryKeys.monitoringSnapshots(modelId, { limit: 500 }),
      queryFn: () => mlApi.listMonitoringSnapshots(modelId, { limit: 500 }),
      enabled: !!modelId,
      staleTime: 30000,
    })),
  });

  const snapshotsById = React.useMemo(() => {
    const map = new Map<string, MonitoringSnapshot[]>();
    selectedModelIds.forEach((id, idx) => {
      const data = monitoringQueries[idx]?.data;
      map.set(id, data?.snapshots || []);
    });
    return map;
  }, [monitoringQueries, selectedModelIds]);

  // Handle model selection (max 4 models)
  const handleModelSelect = (modelIds: string[]) => {
    if (modelIds.length <= 4) {
      setSelectedModelIds(modelIds);
    }
  };

  const handleCollectSnapshot = async () => {
    for (const id of selectedModelIds) {
      await runMonitoringMutation.mutateAsync(id);
    }
  };

  const handleRetrainIfNeeded = async () => {
    for (const id of selectedModelIds) {
      await retrainIfNeededMutation.mutateAsync(id);
    }
  };

  const getSnapshotMetricValue = (
    snapshot: MonitoringSnapshot,
    metric: string
  ): number | null => {
    if (metric === 'psi_score') {
      const psi = (snapshot.drift as Record<string, unknown>)?.psi_score;
      return typeof psi === 'number' ? psi : null;
    }

    const val = (snapshot.metrics as Record<string, unknown>)?.[metric];
    return typeof val === 'number' ? val : null;
  };

  // Prepare chart data
  const chartData = React.useMemo(() => {
    if (!modelsData?.models || selectedModelIds.length === 0) return null;

    const selectedModels = modelsData.models.filter((m: ModelInfo) =>
      selectedModelIds.includes(m.id)
    );

    if (selectedModels.length === 0) return null;

    const start = dateRange[0].startOf('day');
    const end = dateRange[1].endOf('day');

    const dateSet = new Set<string>();
    selectedModels.forEach((m) => {
      (snapshotsById.get(m.id) || []).forEach((s) => {
        const ts = dayjs(s.window_end || s.created_at);
        if (ts.isAfter(start) && ts.isBefore(end)) {
          dateSet.add(ts.format('YYYY-MM-DD'));
        }
      });
    });

    const dates = Array.from(dateSet).sort();
    if (dates.length === 0) return null;

    const datasets = selectedModels.map((model: ModelInfo, index: number) => {
      const color = getModelColor(index);

      const snaps = snapshotsById.get(model.id) || [];
      const byDate = new Map<string, MonitoringSnapshot>();
      snaps.forEach((s) => {
        byDate.set(dayjs(s.window_end || s.created_at).format('YYYY-MM-DD'), s);
      });

      const series = dates.map((d) => {
        const s = byDate.get(d);
        if (!s) return null;
        return getSnapshotMetricValue(s, selectedMetric);
      });

      return {
        label: `${model.name} (v${model.version})`,
        data: series,
        borderColor: color,
        backgroundColor: `${color}33`,
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        fill: true,
        tension: 0.4,
      };
    });

    return { labels: dates, datasets };
  }, [modelsData, selectedModelIds, selectedMetric, dateRange, snapshotsById]);

  // Get color for model by index
  const getModelColor = (index: number): string => {
    const colorPalette = [
      colors.brand.primary,
      colors.semantic.success,
      colors.semantic.warning,
      colors.semantic.info,
    ];
    return colorPalette[index % colorPalette.length];
  };

  // Chart options
  const isPercentMetric = (metric: string): boolean =>
    ['total_return', 'cagr', 'max_drawdown'].includes(metric);

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    scales: {
      x: {
        ticks: {
          color: colors.text.secondary,
          maxRotation: 45,
          minRotation: 45,
        },
        grid: { color: colors.backgrounds.border },
        title: {
          display: true,
          text: 'Date',
          color: colors.text.primary,
        },
      },
      y: {
        beginAtZero: selectedMetric === 'psi_score',
        ticks: {
          color: colors.text.secondary,
          callback: (value: string | number) => {
            const num = Number(value);
            if (Number.isNaN(num)) return '';
            if (selectedMetric === 'psi_score') return num.toFixed(3);
            if (selectedMetric === 'sharpe') return num.toFixed(2);
            if (isPercentMetric(selectedMetric)) return `${(num * 100).toFixed(1)}%`;
            return num.toFixed(4);
          },
        },
        grid: { color: colors.backgrounds.border },
        title: {
          display: true,
          text: selectedMetric.charAt(0).toUpperCase() + selectedMetric.slice(1),
          color: colors.text.primary,
        },
      },
    },
    plugins: {
      legend: {
        position: 'bottom' as const,
        labels: {
          color: colors.text.primary,
          usePointStyle: true,
          padding: 15,
        },
      },
      tooltip: {
        callbacks: {
          label: (context: TooltipItem<'line'>) => {
            const label = context.dataset.label || '';
            const y = context.parsed.y;
            if (y === null || y === undefined) return `${label}: n/a`;
            const num = Number(y);
            if (selectedMetric === 'psi_score') return `${label}: ${num.toFixed(3)}`;
            if (selectedMetric === 'sharpe') return `${label}: ${num.toFixed(2)}`;
            if (isPercentMetric(selectedMetric)) return `${label}: ${(num * 100).toFixed(2)}%`;
            return `${label}: ${num.toFixed(4)}`;
          },
        },
      },
    },
  };

  const calculateTrend = (
    modelId: string
  ): { direction: 'up' | 'down' | 'flat'; change: number } => {
    const snaps = (snapshotsById.get(modelId) || [])
      .map((s) => ({
        ts: dayjs(s.window_end || s.created_at),
        value: getSnapshotMetricValue(s, selectedMetric),
      }))
      .filter((x) => x.value !== null && x.ts.isAfter(dateRange[0]) && x.ts.isBefore(dateRange[1]))
      .sort((a, b) => a.ts.valueOf() - b.ts.valueOf());

    if (snaps.length < 2) return { direction: 'flat', change: 0 };

    const first = snaps[0].value as number;
    const last = snaps[snaps.length - 1].value as number;
    const delta = last - first;

    const threshold = selectedMetric === 'psi_score' ? 0.01 : isPercentMetric(selectedMetric) ? 0.005 : 0.05;
    const direction = delta > threshold ? 'up' : delta < -threshold ? 'down' : 'flat';
    const change = isPercentMetric(selectedMetric) ? Math.abs(delta) * 100 : Math.abs(delta);

    return { direction, change };
  };

  // Available metrics
  const availableMetrics = [
    { value: 'total_return', label: 'Total Return' },
    { value: 'cagr', label: 'CAGR' },
    { value: 'sharpe', label: 'Sharpe' },
    { value: 'max_drawdown', label: 'Max Drawdown' },
    { value: 'psi_score', label: 'PSI (Drift)' },
  ];

  // Export data
  const handleExport = () => {
    if (!chartData) return;

    const csv = [
      ['Date', ...chartData.datasets.map((d) => d.label)].join(','),
      ...chartData.labels.map((date, i) =>
        [date, ...chartData.datasets.map((d) => d.data[i])].join(',')
      ),
    ].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `performance-${selectedMetric}-${new Date().toISOString()}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* Controls */}
      <Card>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Text type="secondary">Select Models (up to 4)</Text>
                <Select
                  mode="multiple"
                  style={{ width: '100%' }}
                  placeholder="Select models to track performance"
                  value={selectedModelIds}
                  onChange={handleModelSelect}
                  maxTagCount="responsive"
                >
                  {modelsData?.models?.map((model: ModelInfo) => (
                    <Option key={model.id} value={model.id}>
                      {model.name} (v{model.version})
                    </Option>
                  ))}
                </Select>
              </Space>
            </Col>
            <Col xs={24} md={6}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Text type="secondary">Metric</Text>
                <Select
                  style={{ width: '100%' }}
                  value={selectedMetric}
                  onChange={setSelectedMetric}
                >
                  {availableMetrics.map((metric) => (
                    <Option key={metric.value} value={metric.value}>
                      {metric.label}
                    </Option>
                  ))}
                </Select>
              </Space>
            </Col>
            <Col xs={24} md={6}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Text type="secondary">Date Range</Text>
                <RangePicker
                  style={{ width: '100%' }}
                  value={dateRange}
                  onChange={(dates) => {
                    if (dates && dates[0] && dates[1]) {
                      setDateRange([dates[0], dates[1]]);
                    }
                  }}
                  presets={[
                    { label: 'Last 7 days', value: [dayjs().subtract(7, 'days'), dayjs()] },
                    { label: 'Last 30 days', value: [dayjs().subtract(30, 'days'), dayjs()] },
                    { label: 'Last 90 days', value: [dayjs().subtract(90, 'days'), dayjs()] },
                  ]}
                />
              </Space>
            </Col>
          </Row>

          <Row justify="end">
            <Space>
              <Button
                onClick={handleCollectSnapshot}
                loading={runMonitoringMutation.isPending}
                disabled={selectedModelIds.length === 0}
              >
                Collect Snapshot
              </Button>
              <Button
                onClick={handleRetrainIfNeeded}
                loading={retrainIfNeededMutation.isPending}
                disabled={selectedModelIds.length === 0}
              >
                Retrain if Needed
              </Button>
              <Button icon={<DownloadOutlined />} onClick={handleExport} disabled={!chartData}>
                Export CSV
              </Button>
            </Space>
          </Row>

          {selectedModelIds.length > 4 && (
            <Alert
              message="Maximum 4 models can be displayed at once"
              type="warning"
              showIcon
              closable
            />
          )}
        </Space>
      </Card>

      {/* Summary Stats */}
      {selectedModelIds.length > 0 && modelsData && (
        <Card title="Performance Summary">
          <Row gutter={16}>
            {modelsData.models
              .filter((m: ModelInfo) => selectedModelIds.includes(m.id))
              .map((model: ModelInfo, index: number) => {
                const trend = calculateTrend(model.id);
                const snaps = snapshotsById.get(model.id) || [];
                const latest = snaps
                  .map((s) => ({ s, ts: dayjs(s.window_end || s.created_at) }))
                  .filter((x) => x.ts.isAfter(dateRange[0]) && x.ts.isBefore(dateRange[1]))
                  .sort((a, b) => b.ts.valueOf() - a.ts.valueOf())[0]?.s;

                const currentValue = latest ? getSnapshotMetricValue(latest, selectedMetric) : null;

                const displayValue = () => {
                  if (currentValue === null) return 'n/a';
                  if (selectedMetric === 'psi_score') return currentValue.toFixed(3);
                  if (selectedMetric === 'sharpe') return currentValue.toFixed(2);
                  if (isPercentMetric(selectedMetric)) return (currentValue * 100).toFixed(2);
                  return currentValue.toFixed(4);
                };

                const suffix = () => {
                  if (currentValue === null) return '';
                  if (selectedMetric === 'psi_score' || selectedMetric === 'sharpe') return '';
                  if (isPercentMetric(selectedMetric)) return '%';
                  return '';
                };

                return (
                  <Col key={model.id} xs={24} sm={12} lg={6}>
                    <Card
                      variant="outlined"
                      style={{
                        borderColor: getModelColor(index),
                        borderWidth: 2,
                      }}
                    >
                      <Space direction="vertical" size="small" style={{ width: '100%' }}>
                        <Text strong>{model.name}</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          v{model.version}
                        </Text>
                        <Statistic
                          title={
                            selectedMetric.charAt(0).toUpperCase() + selectedMetric.slice(1)
                          }
                          value={displayValue()}
                          suffix={suffix()}
                          valueStyle={{
                            fontSize: 20,
                            color:
                              trend.direction === 'up'
                                ? colors.semantic.success
                                : trend.direction === 'down'
                                ? colors.semantic.warning
                                : colors.text.primary,
                          }}
                        />
                        <Tag
                          icon={
                            trend.direction === 'up' ? (
                              <RiseOutlined />
                            ) : trend.direction === 'down' ? (
                              <FallOutlined />
                            ) : null
                          }
                          color={
                            trend.direction === 'up'
                              ? 'success'
                              : trend.direction === 'down'
                              ? 'error'
                              : 'default'
                          }
                        >
                          {trend.direction === 'flat'
                            ? 'Stable'
                            : selectedMetric === 'psi_score' || selectedMetric === 'sharpe'
                            ? `${trend.change.toFixed(2)}`
                            : `${trend.change.toFixed(1)}%`}
                        </Tag>
                        {!latest && (
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            No monitoring snapshots yet
                          </Text>
                        )}
                      </Space>
                    </Card>
                  </Col>
                );
              })}
          </Row>
        </Card>
      )}

      {/* Chart */}
      {selectedModelIds.length === 0 ? (
        <Card>
          <Empty
            description="Select models to view performance trends"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </Card>
      ) : (
        <Card
          title={
            <Space>
              <LineChartOutlined />
              <span>Performance Over Time</span>
            </Space>
          }
        >
          <div style={{ height: 400 }}>
            {chartData ? (
              <Line data={chartData} options={chartOptions} />
            ) : (
              <Spin tip="No snapshots in this range. Click Collect Snapshot." />
            )}
          </div>
        </Card>
      )}
    </Space>
  );
};
