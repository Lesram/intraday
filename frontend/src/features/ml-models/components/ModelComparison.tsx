import React from 'react';
import { Card, Select, Table, Space, Button, Typography, Row, Col, Statistic, Tag, Empty, Alert } from 'antd';
import { TrophyOutlined, DownloadOutlined, BarChartOutlined, RadarChartOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Radar, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
} from 'chart.js';
import { mlApi, mlQueryKeys, mlQueryOptions } from '@/services/mlApi';
import { colors } from '@/styles/theme';
import type { ModelInfo, ModelComparisonResult } from '@/types/ml';
import { useIsMobile, useResponsiveValue } from '@/hooks/useResponsive';
import { useMemoizedValue } from '@/hooks/usePerformance';

// Register Chart.js components
ChartJS.register(
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
);

const { Title: AntTitle, Text } = Typography;
const { Option } = Select;

interface ModelComparisonProps {
  preselectedModels?: string[];
}

export const ModelComparison: React.FC<ModelComparisonProps> = ({ preselectedModels = [] }) => {
  const [selectedModelIds, setSelectedModelIds] = React.useState<string[]>(preselectedModels);
  const [chartType, setChartType] = React.useState<'radar' | 'bar'>('radar');
  const isMobile = useIsMobile();
  
  // Responsive chart height
  const chartHeight = useResponsiveValue({
    xs: 280,
    sm: 320,
    md: 360,
    lg: 400,
    default: 400,
  });

  // Fetch all models for selection
  const { data: modelsData } = useQuery({
    queryKey: mlQueryKeys.lists(),
    queryFn: () => mlApi.listModels(),
    ...mlQueryOptions.models,
  });

  // Fetch comparison data for selected models
  const { data: comparisonData, isLoading, error } = useQuery({
    queryKey: ['ml-models', 'comparison', selectedModelIds],
    queryFn: () => mlApi.compareModels({ model_ids: selectedModelIds }),
    enabled: selectedModelIds.length >= 2,
  });

  // Log comparison data in development only
  React.useEffect(() => {
    if (comparisonData && import.meta.env.DEV) {
      console.log('[ModelComparison] Loaded', comparisonData.models?.length, 'models');
    }
  }, [comparisonData]);

  // Handle model selection
  const handleModelSelect = (modelIds: string[]) => {
    if (modelIds.length <= 4) {
      setSelectedModelIds(modelIds);
    }
  };

  // Export comparison data
  const handleExport = () => {
    if (!comparisonData) return;

    const csv = generateCSV(comparisonData);
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `model-comparison-${new Date().toISOString()}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // Generate CSV from comparison data
  const generateCSV = (data: ModelComparisonResult): string => {
    const headers = ['Metric', ...data.models.map((m: ModelInfo) => m.name)];
    const rows = [
      headers.join(','),
      ...Object.keys(data.models[0].metrics).map((metric) =>
        [metric, ...data.models.map((m: ModelInfo) => (m.metrics as Record<string, unknown>)[metric] ?? 'N/A')].join(',')
      ),
    ];
    return rows.join('\n');
  };

  // Get color for model by index - MUST be before chartData useMemo
  const getModelColor = (index: number): string => {
    const colorPalette = [
      colors.brand.primary,
      colors.semantic.success,
      colors.semantic.warning,
      colors.semantic.info,
    ];
    return colorPalette[index % colorPalette.length];
  };

  // Prepare chart data - memoized for performance
  const chartData = useMemoizedValue(() => {
    if (!comparisonData || !comparisonData.models || comparisonData.models.length === 0) return null;

    // Define core metrics for chart display (filter out time-based metrics)
    const metricKeys = ['accuracy', 'precision', 'recall', 'f1_score'];
    const labels = metricKeys;
    
    const datasets = comparisonData.models.map((model: ModelInfo, index: number) => ({
      label: model.name,
      data: metricKeys.map((key) => {
        const metrics = model.metrics as Record<string, number | undefined>;
        const value = metrics[key];
        return typeof value === 'number' ? value : 0;
      }),
      backgroundColor: `${getModelColor(index)}33`,
      borderColor: getModelColor(index),
      borderWidth: 2,
      pointBackgroundColor: getModelColor(index),
      pointBorderColor: '#fff',
      pointHoverBackgroundColor: '#fff',
      pointHoverBorderColor: getModelColor(index),
    }));

    return { labels, datasets };
  }, [comparisonData]);

  // Find winner for each metric
  const getWinner = (metric: string): string | null => {
    if (!comparisonData || !comparisonData.models) return null;

    const values = comparisonData.models.map((m: ModelInfo) => ({
      name: m.name,
      value: (m.metrics as Record<string, number | undefined>)[metric] ?? 0,
    }));

    // Filter out models with no value for this metric
    const validValues = values.filter((v) => v.value !== null && v.value !== undefined && v.value !== 0);
    if (validValues.length === 0) return null;

    // Higher is better for most metrics (accuracy, precision, etc.)
    // Lower is better for loss/error/time metrics
    const isLossMetric = metric.toLowerCase().includes('loss') || 
                         metric.toLowerCase().includes('error') || 
                         metric.toLowerCase().includes('time');
    
    const winner = validValues.reduce((best, current) => {
      if (!best) return current;
      return isLossMetric
        ? current.value < best.value ? current : best
        : current.value > best.value ? current : best;
    });

    return winner.name;
  };

  // Prepare table columns
  const tableColumns = [
    {
      title: 'Metric',
      dataIndex: 'metric',
      key: 'metric',
      fixed: 'left' as const,
      width: 150,
      render: (text: string) => <Text strong>{text}</Text>,
    },
    ...(comparisonData?.models || []).map((model: ModelInfo) => {
      const modelKey = model.id;
      return {
        title: (
          <Space direction="vertical" size={0}>
            <Text strong>{model.name}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>v{model.version}</Text>
          </Space>
        ),
        dataIndex: modelKey,
        key: modelKey,
        width: 120,
        render: (value: number | string, record: { metric: string }) => {
          const isWinner = getWinner(record.metric) === model.name;
          // Convert to number if it's a string
          const numValue = typeof value === 'string' ? parseFloat(value) : value;
          const displayValue = typeof numValue === 'number' && !isNaN(numValue) 
            ? numValue.toFixed(4) 
            : 'N/A';
          
          return (
            <Space>
              <Text style={{ color: isWinner ? colors.semantic.success : undefined }}>
                {displayValue}
              </Text>
              {isWinner && <TrophyOutlined style={{ color: colors.semantic.success }} />}
            </Space>
          );
        },
      };
    }),
  ];

  // Prepare table data
  const tableData = React.useMemo(() => {
    if (!comparisonData || !comparisonData.models || comparisonData.models.length === 0) return [];

    // Define all possible metrics (since metrics is an object, not a flat dictionary)
    const allMetricKeys = [
      'accuracy',
      'precision',
      'recall',
      'f1_score',
      'mae',
      'rmse',
      'r2_score',
      'mape',
      'training_time',
      'inference_time',
    ];

    // Filter to only show metrics that at least ONE model has a value for
    const metricKeys = allMetricKeys.filter(metric => 
      comparisonData.models.some((model: ModelInfo) => {
        const metrics = model.metrics as Record<string, number | undefined>;
        const value = metrics[metric];
        return value !== null && value !== undefined;
      })
    );

    return metricKeys.map((metric) => {
      const row: { metric: string; key: string; [modelId: string]: string | number | undefined } = { metric, key: metric };
      comparisonData.models.forEach((model: ModelInfo) => {
        // Use model.id as the key
        const modelKey = model.id;
        // Access metrics object properties
        const metrics = model.metrics as Record<string, number | undefined>;
        row[modelKey] = metrics[metric];
      });
      return row;
    });
  }, [comparisonData]);

  // Chart options
  const radarOptions = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      r: {
        beginAtZero: true,
        max: 1,
        ticks: { 
          color: colors.text.secondary,
          font: { size: isMobile ? 10 : 12 },
        },
        grid: { color: colors.backgrounds.border },
        pointLabels: { 
          color: colors.text.primary,
          font: { size: isMobile ? 10 : 12 },
        },
      },
    },
    plugins: {
      legend: {
        position: isMobile ? ('bottom' as const) : ('right' as const),
        labels: { 
          color: colors.text.primary,
          font: { size: isMobile ? 11 : 12 },
          padding: isMobile ? 8 : 10,
        },
      },
      tooltip: {
        enabled: true,
        titleFont: { size: isMobile ? 12 : 14 },
        bodyFont: { size: isMobile ? 11 : 13 },
      },
    },
    interaction: {
      mode: 'nearest' as const,
      intersect: false,
    },
  };

  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: {
        ticks: { 
          color: colors.text.secondary,
          font: { size: isMobile ? 10 : 12 },
        },
        grid: { color: colors.backgrounds.border },
      },
      y: {
        beginAtZero: true,
        max: 1,
        ticks: { 
          color: colors.text.secondary,
          font: { size: isMobile ? 10 : 12 },
        },
        grid: { color: colors.backgrounds.border },
      },
    },
    plugins: {
      legend: {
        position: isMobile ? ('bottom' as const) : ('right' as const),
        labels: { 
          color: colors.text.primary,
          font: { size: isMobile ? 11 : 12 },
          padding: isMobile ? 8 : 10,
        },
      },
      tooltip: {
        enabled: true,
        titleFont: { size: isMobile ? 12 : 14 },
        bodyFont: { size: isMobile ? 11 : 13 },
      },
    },
    interaction: {
      mode: 'nearest' as const,
      intersect: false,
    },
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* Model Selection */}
      <Card>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <AntTitle level={4}>Select Models to Compare</AntTitle>
          <Select
            mode="multiple"
            style={{ width: '100%' }}
            placeholder="Select 2-4 models to compare"
            value={selectedModelIds}
            onChange={handleModelSelect}
            maxTagCount="responsive"
          >
            {modelsData?.models?.map((model: ModelInfo) => (
              <Option key={model.id} value={model.id}>
                {model.name} (v{model.version}) - {model.status}
              </Option>
            ))}
          </Select>
          {selectedModelIds.length > 4 && (
            <Alert
              message="Maximum 4 models can be compared at once"
              type="warning"
              showIcon
              closable
            />
          )}
        </Space>
      </Card>

      {/* Comparison Results */}
      {selectedModelIds.length < 2 ? (
        <Card>
          <Empty
            description="Select at least 2 models to compare"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </Card>
      ) : error ? (
        <Card>
          <Alert
            message="Error Loading Comparison"
            description={(error as Error).message}
            type="error"
            showIcon
          />
        </Card>
      ) : (
        <>
          {/* Summary Statistics */}
          {comparisonData && (
            <Card
              title={
                <Space>
                  <TrophyOutlined />
                  <span>Comparison Summary</span>
                </Space>
              }
              extra={
                <Button icon={<DownloadOutlined />} onClick={handleExport}>
                  Export CSV
                </Button>
              }
            >
              <Row gutter={16}>
                {comparisonData.models.map((model: ModelInfo, index: number) => {
                  const overallScore = (model as ModelInfo & { overall_score?: number }).overall_score;
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
                        <Text strong style={{ fontSize: 16 }}>
                          {model.name}
                        </Text>
                        <Text type="secondary">Version {model.version}</Text>
                        <Tag color={model.status === 'ready' ? 'success' : 'default'}>
                          {model.status}
                        </Tag>
                        <Statistic
                          title="Overall Score"
                          value={overallScore || 0}
                          precision={2}
                          suffix="/ 1.00"
                          valueStyle={{
                            color:
                              (overallScore ?? 0) > 0.8
                                ? colors.semantic.success
                                : (overallScore ?? 0) > 0.6
                                ? colors.semantic.warning
                                : colors.semantic.error,
                          }}
                        />
                      </Space>
                    </Card>
                  </Col>
                  );
                })}
              </Row>
            </Card>
          )}

          {/* Visualization */}
          {chartData && (
            <Card
              title="Performance Comparison"
              extra={
                !isMobile && (
                  <Space>
                    <Button
                      type={chartType === 'radar' ? 'primary' : 'default'}
                      icon={<RadarChartOutlined />}
                      onClick={() => setChartType('radar')}
                      size={isMobile ? 'small' : 'middle'}
                    >
                      {isMobile ? '' : 'Radar'}
                    </Button>
                    <Button
                      type={chartType === 'bar' ? 'primary' : 'default'}
                      icon={<BarChartOutlined />}
                      onClick={() => setChartType('bar')}
                      size={isMobile ? 'small' : 'middle'}
                    >
                      {isMobile ? '' : 'Bar'}
                    </Button>
                  </Space>
                )
              }
            >
              {isMobile && (
                <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'center' }}>
                  <Button
                    type={chartType === 'radar' ? 'primary' : 'default'}
                    icon={<RadarChartOutlined />}
                    onClick={() => setChartType('radar')}
                    block
                  >
                    Radar Chart
                  </Button>
                  <Button
                    type={chartType === 'bar' ? 'primary' : 'default'}
                    icon={<BarChartOutlined />}
                    onClick={() => setChartType('bar')}
                    block
                  >
                    Bar Chart
                  </Button>
                </Space>
              )}
              <div style={{ height: chartHeight, touchAction: 'pan-y' }}>
                {chartType === 'radar' ? (
                  <Radar data={chartData} options={radarOptions} />
                ) : (
                  <Bar data={chartData} options={barOptions} />
                )}
              </div>
            </Card>
          )}

          {/* Detailed Metrics Table */}
          <Card title="Detailed Metrics Comparison">
            <Table
              columns={tableColumns}
              dataSource={tableData}
              loading={isLoading}
              pagination={false}
              scroll={{ x: true }}
              bordered
              size={isMobile ? 'small' : 'middle'}
            />
          </Card>
        </>
      )}
    </Space>
  );
};
